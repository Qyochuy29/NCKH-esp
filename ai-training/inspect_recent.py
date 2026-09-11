import os, glob, csv
import numpy as np
from pydub import AudioSegment
from transcription import get_whisper_waveform, transcribe_vietnamese
from server import yamnet_model, whisper_model, YAMNET_SCREAM_CLASSES, YAMNET_CRY_CLASSES, YAMNET_IMPACT_CLASSES, classify_audio

# Load yamnet class map
class_names = {}
if os.path.exists('/app/yamnet_class_map.csv'):
    with open('/app/yamnet_class_map.csv', 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if len(row) >= 3:
                class_names[int(row[0])] = row[2]

files = sorted(glob.glob('/tai-lieu/Cam-HL1_*_analyze.wav'), key=os.path.getmtime, reverse=True)[:6]
print(f'Inspecting {len(files)} latest files...')
for f in files:
    audio = AudioSegment.from_file(f)
    cls, conf, cry_ts, scr_ts, imp_ts, sp_score = classify_audio(audio)
    txt, words, segs, _ = transcribe_vietnamese(whisper_model, audio)
    
    waveform = get_whisper_waveform(audio)
    scores, _, _ = yamnet_model(waveform)
    scores_np = scores.numpy()
    max_scores = np.max(scores_np, axis=0)
    top_indices = np.argsort(max_scores)[-8:][::-1]
    
    print('='*60)
    print(f'FILE: {os.path.basename(f)}')
    print(f'Transcript: "{txt}"')
    print(f'classify_audio -> class: {cls}, conf: {conf:.2f}, cry_ts: {cry_ts}, scr_ts: {scr_ts}, imp_ts: {imp_ts}, speech_score: {sp_score:.2f}')
    print('Top YAMNet classes:')
    for idx in top_indices:
        name = class_names.get(idx, f"Unknown_{idx}")
        print(f'  Class {idx} ({name}): {max_scores[idx]:.3f}')
