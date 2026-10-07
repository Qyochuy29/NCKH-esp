"""YAMNet evidence with native scores and 0.96s frames / 0.48s hop."""
import csv
import os
from functools import lru_cache
from pathlib import Path
import numpy as np

GROUP_NAMES = {
    'scream': ['Screaming'],
    'cry': ['Crying, sobbing','Whimper','Wail, moan'],
    'baby_cry': ['Baby cry, infant cry'],
    'impact': ['Bang','Slap, smack','Whack, thwack','Smash, crash','Breaking','Thump, thud','Thunk'],
    'speech': ['Speech','Child speech, kid speaking','Conversation','Narration, monologue'],
    'loud_speech': ['Shout','Bellow','Yell','Children shouting'],
    'music': ['Music','Singing'], 'applause': ['Clapping','Applause','Cheering'],
    'door': ['Slam','Door'],
}
THRESHOLDS = {'scream': .45, 'cry': .4, 'baby_cry': .4, 'impact': .55, 'speech': .45,
              'loud_speech': .5, 'music': .5, 'applause': .5, 'door': .5}


def yamnet_waveform(audio):
    # Preserve event acoustics; ASR high-pass/normalization is a separate branch.
    mono = audio.set_channels(1).set_frame_rate(16000)
    samples = np.asarray(mono.get_array_of_samples(),dtype=np.float32)
    return samples / float(2 ** (8 * mono.sample_width - 1))


@lru_cache(maxsize=4)
def load_class_indices(class_map):
    with open(class_map, encoding='utf-8-sig',newline='') as stream:
        return {r['display_name']:int(r['index']) for r in csv.DictReader(stream)}


def extract_events(scores, duration, class_map=None):
    class_map = class_map or Path(__file__).with_name('yamnet_class_map.csv')
    indices=load_class_indices(str(class_map))
    scores = np.asarray(scores)
    if scores.ndim != 2 or scores.shape[1] != 521 or not np.all(np.isfinite(scores)):
        raise ValueError('Invalid YAMNet score matrix')
    peaks, events = {}, []
    for kind, names in GROUP_NAMES.items():
        candidate_threshold = float(os.environ.get('YAMNET_SCREAM_CANDIDATE_THRESHOLD', '.15')) if kind == 'scream' else THRESHOLDS[kind]
        if not 0 <= candidate_threshold <= THRESHOLDS[kind]:
            raise ValueError('Invalid YAMNet candidate threshold')
        columns = [indices[n] for n in names]
        values = np.max(scores[:,columns],axis=1)
        peaks[kind] = round(float(np.max(values)),6) if len(values) else 0.0
        run = None
        for i,value in enumerate(values):
            start,end = i*.48,min(duration,i*.48+.96)
            if start >= duration:
                break
            if float(value) >= candidate_threshold:
                event_type='crying' if kind=='cry' else 'speech_activity' if kind=='speech' else kind
                strength='strong' if float(value) >= THRESHOLDS[kind] else 'tentative'
                dominant = names[int(np.argmax(scores[i,columns]))]
                if run is not None and start <= run['end'] and run['strength']==strength:
                    run['end']=round(end,3)
                    run['score']=max(run['score'],round(float(value),6))
                else:
                    run={'start':round(start,3),'end':round(end,3),'type':event_type,
                         'score':round(float(value),6),'model':'yamnet','strength':strength,
                         'class_name':dominant}
                    events.append(run)
            else:
                run=None
    known = {indices[name] for names in GROUP_NAMES.values() for name in names} | {indices['Silence']}
    names_by_index = {index:name for name,index in indices.items()}
    for i,frame in enumerate(scores):
        top = int(np.argmax(frame))
        if top not in known and float(frame[top]) >= .6 and i*.48 < duration:
            events.append({'start':round(i*.48,3),'end':round(min(duration,i*.48+.96),3),
                           'type':'unusual','score':round(float(frame[top]),6),
                           'class_name':names_by_index[top],'model':'yamnet'})
    return {'scores':peaks,'events':sorted(events,key=lambda e:(e['start'],e['end'],e['type'])),
            'status':'success','frame_seconds':.96,'hop_seconds':.48,
            'limitations':['YAMNet scores là điểm sự kiện âm thanh, không phải xác suất bạo lực.',
                           'Tiếng nói lớn mô tả lớp Shout/Yell, không đo âm lượng tuyệt đối.',
                           'Unusual là lớp âm thanh ngoài nhóm theo dõi; chưa phải mô hình phát hiện bất thường.']}


def detect_audio_events(audio, model):
    if model is None:
        return {'scores':{},'events':[],'status':'unavailable','error':'YAMNet unavailable'}
    try:
        waveform=yamnet_waveform(audio)
        if not len(waveform):
            raise ValueError('Empty audio')
        # Bound TensorFlow intermediate tensors for long compressed recordings.
        # Starts are exact multiples of YAMNet's 0.48s hop; 1s lookahead keeps
        # boundary patches intact. Discard overlapping outputs before merging.
        hop_samples=7680
        block_frames=64
        block_samples=block_frames*hop_samples
        batches=[]
        for start in range(0,len(waveform),block_samples):
            chunk=waveform[start:start+block_samples+16000]
            scores,_,_=model(chunk)
            scores=scores.numpy()
            remaining_frames=int(np.ceil((len(waveform)-start)/hop_samples))
            batches.append(scores[:min(block_frames,remaining_frames)])
        return extract_events(np.concatenate(batches,axis=0),len(audio)/1000)
    except Exception as exc:
        return {'scores':{},'events':[],'status':'unavailable','error':str(exc)}
