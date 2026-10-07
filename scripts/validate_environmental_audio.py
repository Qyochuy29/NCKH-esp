"""Real environmental samples from ESC-50 plus explicitly STAGED speech/event mixtures.

These recordings have no school-violence ground truth. Never report accuracy from this suite.
Source/license: https://github.com/karolpiczak/ESC-50 (CC BY-NC; individual metadata applies).
"""
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import requests
from pydub import AudioSegment

sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.runtime'/'validation'/'environmental'
OUT.mkdir(parents=True,exist_ok=True)
BASE='https://raw.githubusercontent.com/karolpiczak/ESC-50/master/'
metadata=requests.get(BASE+'meta/esc50.csv',timeout=30)
metadata.raise_for_status()
rows=list(csv.DictReader(io.StringIO(metadata.text)))
manifest=[]
for category in ['door_wood_knock','door_wood_creaks','clapping','crying_baby','glass_breaking','rain','laughing','brushing_teeth']:
    for row in [r for r in rows if r['category']==category][:2]:
        file=OUT/row['filename']
        if not file.exists():
            response=requests.get(BASE+'audio/'+row['filename'],timeout=60)
            response.raise_for_status()
            file.write_bytes(response.content)
        manifest.append(dict(name=category+'_'+row['filename'],file=str(file),source='ESC-50',
                             source_url=BASE+'audio/'+row['filename'],label=category,expected_risk='not_high'))

# Use actual glass-break acoustics and an actual baby-cry recording in a STAGED mix.
# This validates pipeline wiring; it does not represent an actual school incident.
help_audio=AudioSegment.from_mp3(ROOT/'.runtime/validation/help.mp3')
glass=AudioSegment.from_wav([Path(m['file']) for m in manifest if m['label']=='glass_breaking'][1])
cry=AudioSegment.from_wav([Path(m['file']) for m in manifest if m['label']=='crying_baby'][1])
staged=help_audio+glass[:2000]+cry
staged_file=OUT/'STAGED_help_glass_cry.wav'
with staged_file.open('wb') as f:
    staged.export(f,format='wav')
manifest.append(dict(name='STAGED_help_glass_cry',file=str(staged_file),source='STAGED_TTS_plus_ESC50',expected_risk='high'))
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
login=requests.post('http://127.0.0.1:3000/api/auth/login',json=dict(email='admin@gmail.com',password='password123'),timeout=20)
login.raise_for_status()
headers={'Authorization':'Bearer '+login.json()['access_token']}
results=[]
for sample in manifest:
    file=Path(sample['file'])
    checksum=hashlib.sha256(file.read_bytes()).hexdigest()
    with file.open('rb') as f:
        response=requests.post('http://127.0.0.1:3000/api/alerts/upload',headers=headers,
            files={'audio':(file.name,f,'audio/wav')},timeout=900)
    response.raise_for_status()
    payload=response.json()
    result=payload['result']
    risk=result['analysis']['risk_level']
    checks=dict(original_preserved=result['audio']['original_sha256']==checksum,
                expected_risk=risk!='high' if sample['expected_risk']=='not_high' else risk=='high')
    results.append(dict(sample=sample,checks=checks,analysis_id=payload['analysis_id'],result=result))
    (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(name=sample['name'],risk=risk,scores=result['sound_events'],
                         transcript=result['asr']['normalized_transcript'],checks=checks),ensure_ascii=False),flush=True)
failures=[r['sample']['name'] for r in results if not all(r['checks'].values())]
if failures:
    raise RuntimeError('Environmental checks failed: '+', '.join(failures))
