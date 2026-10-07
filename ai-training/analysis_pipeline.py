"""One analysis path shared by all HTTP endpoints. Never overwrites input audio."""
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
import uuid
import time
from pydub import AudioSegment
from transcription import transcribe_audio, censor_audio_and_text
from audio_events import detect_audio_events
from context_analysis import analyze_context, speech_signals


def build_timeline(segments, events):
    timeline = [dict(start=s['start'],end=s['end'],type='speech',text=s['text'],
                     raw_text=s.get('raw_text',s['text'])) for s in segments if s.get('accepted',True)]
    timeline += [dict(e) for e in events]
    return sorted(timeline,key=lambda e:(e['start'],e['end'],e['type']))


def file_sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


def analyze_file(filepath, upload_dir, whisper_model, yamnet_model):
    started=time.monotonic()
    path=Path(filepath)
    original_hash=file_sha256(path)
    max_seconds=float(os.environ.get('MAX_AUDIO_SECONDS','1800'))
    if max_seconds<=0:
        raise ValueError('MAX_AUDIO_SECONDS must be positive')
    with path.open('rb') as source:
        audio=AudioSegment.from_file(source,format='wav' if path.suffix.lower()=='.wav' else None,
                                     duration=max_seconds+1)
    if not len(audio):
        raise ValueError('Empty audio')
    if len(audio)/1000>max_seconds:
        raise ValueError('Audio exceeds configured duration limit (MAX_AUDIO_SECONDS)')
    event_started=time.monotonic()
    sounds=detect_audio_events(audio,yamnet_model)
    event_seconds=time.monotonic()-event_started
    asr_started=time.monotonic()
    asr=transcribe_audio(whisper_model,audio,speech_expected=sounds['scores'].get('speech',0)>=.45)
    asr_seconds=time.monotonic()-asr_started
    timeline=build_timeline(asr['segments'],sounds['events'])
    analysis=analyze_context({'raw_transcript':asr['raw_transcript'],
        'normalized_transcript':asr['normalized_transcript'], 'speech_segments':asr['segments'],
        'speech_words':asr.get('words',[]),
        'sound_events':sounds['scores'],'timeline':timeline,'asr_status':asr['status'],
        'asr_quality':asr['quality'],'audio_events_status':sounds['status']})
    relative=path.relative_to(Path(upload_dir)).as_posix()
    original_url='/uploads/'+relative
    processed_url=None
    censored_text=None
    if os.environ.get('CREATE_CENSORED_AUDIO','false').lower()=='true':
        words=[SimpleNamespace(**w) for w in asr.get('words',[])]
        censored,censored_text,intervals=censor_audio_and_text(audio,asr['normalized_transcript'],words)
        if intervals:
            destination=Path(upload_dir)/'processed'/f'{path.stem}_{uuid.uuid4().hex[:8]}_censored.wav'
            destination.parent.mkdir(parents=True,exist_ok=True)
            with destination.open('wb') as output:
                censored.export(output,format='wav')
            processed_url='/uploads/'+destination.relative_to(Path(upload_dir)).as_posix()
    dialogue=[]
    for i,seg in enumerate(asr['segments']):
        if not seg.get('accepted',True):
            continue
        flags=speech_signals(seg['text'])
        dialogue.append({'segment_label':f'Segment {i+1}','text':seg['text'],
            'start_time':seg['start'],'end_time':seg['end'],'timestamp_s':seg['start'],
            'is_threat':flags['threat'],'is_emergency':flags['help'] or flags['victim'],
            'has_vulgarity':flags['profanity']})
    result={'status':'success','schema_version':'2.0',
        'processing':{'audio_events_seconds':round(event_seconds,3),'asr_seconds':round(asr_seconds,3),
                      'total_seconds':round(time.monotonic()-started,3)},
        'audio':{'duration_seconds':len(audio)/1000,'original_audio_url':original_url,
                 'original_sha256':original_hash,'processed_audio_url':processed_url},
        'asr':asr,'sound_events':sounds['scores'],'audio_events':sounds,
        'timeline':timeline,'analysis':analysis,'school_violence_analysis':analysis,
        'model_versions':{'asr':asr['model'],'audio_events':'yamnet/1','reasoning':analysis.get('reasoning_provider','unknown')},
        'transcript':asr['normalized_transcript'],'raw_transcript':asr['raw_transcript'],
        'normalized_transcript':asr['normalized_transcript'], 'segments':asr['segments'],
        'total_duration_seconds':len(audio)/1000,'audio_url':original_url,
        'censored_transcript':censored_text,'alerts':[]}
    # Legacy dialogue readers get the same evidence/risk result, without fictional speakers/scores.
    result['dialog_data']={**result,'dialogue':dialogue,'original_audio_url':original_url,
                           'no_dialogue':not asr['has_speech'],'dialogue_text':asr['normalized_transcript']}
    result['alerts_count']=0  # Backend alone persists review/high alerts.
    if file_sha256(path)!=original_hash:
        raise RuntimeError('Original audio unexpectedly changed during analysis')
    return result
