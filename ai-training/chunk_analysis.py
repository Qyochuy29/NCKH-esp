"""Analyze actual ten-second derivatives while retaining whole-file context."""
from pathlib import Path
from audio_events import detect_audio_events
from transcription import transcribe_audio
from context_analysis import analyze_context, speech_units


def aggregate_chunk_results(whole, chunks):
    """Never hide a stronger chunk finding behind a weaker whole-file decode."""
    if not chunks:
        return whole
    rank={'low':0,'review':1,'high':2}
    best=max(chunks,key=lambda c:rank[c['analysis']['risk_level']])
    result=dict(whole)
    if rank[best['analysis']['risk_level']]>rank[whole['risk_level']]:
        result=dict(best['analysis'])
        result['summary']=f"Đoạn cắt {best['index']} ({best['start']:.1f}–{best['end']:.1f}s): "+result['summary']
        result['evidence_items']=[dict(e,start=round(e['start']+best['start'],3),
            end=round(e['end']+best['start'],3),source_chunk=best['index']) for e in result['evidence_items']]
        result['evidence']=[f"Đoạn {best['index']}, tính từ {best['start']:.1f}s: {e}" for e in result['evidence']]
    result['has_profanity']=whole['has_profanity'] or any(c['analysis']['has_profanity'] for c in chunks)
    result['has_insults']=whole['has_insults'] or any(c['analysis']['has_insults'] for c in chunks)
    result['assessment_sources']=['whole_file','ten_second_chunks']
    return result


def analyze_chunks(audio, upload_dir, original_hash, whisper_model, yamnet_model, full_asr, full_sounds):
    if len(audio)<=10000:
        return []
    root=Path(upload_dir)
    directory=root/'processed'/'chunks'/original_hash
    directory.mkdir(parents=True,exist_ok=True)
    full_units=speech_units([s for s in full_asr['segments'] if s.get('accepted',True)],full_asr.get('words',[]))
    result=[]
    for index,start_ms in enumerate(range(0,len(audio),10000),1):
        end_ms=min(start_ms+10000,len(audio))
        piece=audio[start_ms:end_ms].set_channels(1).set_frame_rate(16000).set_sample_width(2)
        destination=directory/f'part_{index:03d}.wav'
        # Idempotent analysis never overwrites either original or existing derivative.
        if not destination.exists():
            with destination.open('xb') as stream:
                piece.export(stream,format='wav')
        sound=detect_audio_events(piece,yamnet_model)
        asr=transcribe_audio(whisper_model,piece,speech_expected=sound['scores'].get('speech',0)>=.45)
        asr['device']='cloud' if asr['provider']=='groq' else getattr(whisper_model,'device','unavailable')
        speech=[dict(start=s['start'],end=s['end'],type='speech',text=s['text'])
                for s in asr['segments'] if s.get('accepted',True)]
        timeline=sorted(speech+sound['events'],key=lambda e:(e['start'],e['end'],e['type']))
        analysis=analyze_context(dict(speech_segments=asr['segments'],speech_words=asr.get('words',[]),
            timeline=timeline,sound_events=sound['scores'],asr_status=asr['status'],
            asr_quality=asr['quality'],audio_events_status=sound['status']))
        start,end=start_ms/1000,end_ms/1000
        context_speech=[s for s in full_units if s['start']<end+3 and s['end']>start-3]
        context_events=[e for e in full_sounds['events'] if e['start']<end+3 and e['end']>start-3]
        context=analyze_context(dict(speech_segments=context_speech,
            timeline=context_events,sound_events=full_sounds['scores'],asr_status=full_asr['status'],
            asr_quality=full_asr['quality'],audio_events_status=full_sounds['status']))
        anchor=any(e['start']<end and e['end']>start for e in context['evidence_items'])
        boundary=context if anchor and context['risk_level']!='low' else None
        labels=[]
        if analysis['has_profanity']:labels.append('profanity')
        if analysis['possible_verbal_abuse']:labels.append('verbal_abuse')
        signals={e.get('signal') for e in analysis['evidence_items'] if not e.get('reported')}
        if 'threat' in signals:labels.append('threat')
        if signals & {'help','victim'}:labels.append('help')
        if analysis['possible_physical_violence']:labels.append('possible_physical_violence')
        for kind in ['scream','crying','impact','loud_speech']:
            if any(e['type']==kind for e in sound['events']):labels.append(kind)
        result.append(dict(index=index,start=start,end=end,duration_seconds=(end_ms-start_ms)/1000,
            audio_url='/uploads/'+destination.relative_to(root).as_posix(),
            asr=asr,sound_events=sound['scores'],timeline=timeline,analysis=analysis,
            labels=labels,boundary_context=boundary,timestamp_reference='chunk_start'))
    return result
