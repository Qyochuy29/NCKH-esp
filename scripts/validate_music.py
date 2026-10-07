"""Instrumental false-positive smoke tests from librosa's public example catalogue."""
import hashlib
import io
import json
from pathlib import Path
import sys
import requests
from pydub import AudioSegment

sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.runtime/validation/music'
OUT.mkdir(parents=True,exist_ok=True)
names=['sorohanro_-_solo-trumpet-06','Kevin_MacLeod_-_P_I_Tchaikovsky_Dance_of_the_Sugar_Plum_Fairy']
login=requests.post('http://127.0.0.1:3000/api/auth/login',json=dict(email='admin@gmail.com',password='password123'),timeout=20)
login.raise_for_status()
headers={'Authorization':'Bearer '+login.json()['access_token']}
results=[]
for name in names:
    source='https://librosa.org/data/audio/'+name+'.ogg'
    file=OUT/(name+'.ogg')
    if not file.exists():
        response=requests.get(source,timeout=60)
        response.raise_for_status()
        file.write_bytes(response.content)
    attribution=requests.get('https://librosa.org/data/audio/'+name+'.txt',timeout=30)
    attribution.raise_for_status()
    (OUT/(name+'.txt')).write_text(attribution.text,encoding='utf-8')
    with file.open('rb') as stream:
        audio=AudioSegment.from_file(stream)[:15000]
    buffer=io.BytesIO()
    audio.export(buffer,format='wav')
    data=buffer.getvalue()
    response=requests.post('http://127.0.0.1:3000/api/alerts/upload',headers=headers,
        files={'audio':(name+'.wav',data,'audio/wav')},timeout=900)
    response.raise_for_status()
    result=response.json()['result']
    checks=dict(original_preserved=result['audio']['original_sha256']==hashlib.sha256(data).hexdigest(),
                no_automatic_high=result['analysis']['risk_level']!='high')
    results.append(dict(name=name,source_url=source,excerpt_seconds=len(audio)/1000,result=result,checks=checks))
    (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(name=name,risk=result['analysis']['risk_level'],scores=result['sound_events'],checks=checks)),flush=True)
if not all(all(r['checks'].values()) for r in results):
    raise RuntimeError('Instrumental music checks failed')
