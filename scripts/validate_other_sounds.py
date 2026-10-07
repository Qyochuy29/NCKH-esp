"""Public sound effects and staged mixtures. Not real incidents or a violence benchmark."""
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile
import requests
from pydub import AudioSegment

sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.runtime/validation/other'
OUT.mkdir(parents=True,exist_ok=True)
source='https://opengameart.org/sites/default/files/female_screams.zip'
response=requests.get(source,timeout=45)
response.raise_for_status()
(OUT/'female_screams.zip').write_bytes(response.content)
samples=[]
with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
    for entry in archive.infolist():
        name=Path(entry.filename).name
        if name.startswith('._') or entry.is_dir():
            continue
        if name.lower().endswith('.txt'):
            (OUT/('credits-'+name)).write_bytes(archive.read(entry))
        if Path(name).suffix.lower() in {'.wav','.ogg','.mp3','.aiff'}:
            path=OUT/name
            path.write_bytes(archive.read(entry))
            samples.append(dict(name=name,file=path,source=source,expected_risk='review'))
if not samples:
    raise RuntimeError('Public scream archive contains no audio')
print('Public scream samples:',[s['name'] for s in samples],flush=True)
# The recording's acting/game context is kept in the manifest, not invented in ASR.
scream=AudioSegment.from_file(samples[-1]['file'])
glass=AudioSegment.from_wav(ROOT/'.runtime/validation/environmental/1-84536-A-39.wav')
joy=AudioSegment.from_mp3(ROOT/'.runtime/validation/joy.mp3')
weak_scream=AudioSegment.from_file(samples[0]['file'])
for name,audio,risk in [('STAGED_scream_impact',scream+glass[:2000],'high'),
                        ('STAGED_short_weak_scream_impact',weak_scream+glass[:2000],'review'),
                        ('STAGED_joy_scream',joy+scream,'low')]:
    path=OUT/(name+'.wav')
    with path.open('wb') as file:
        audio.export(file,format='wav')
    samples.append(dict(name=name,file=path,source='STAGED_TTS_plus_public_sounds',expected_risk=risk))
# A chair preview is public; original downloads may require a Freesound account.
chair_page='https://freesound.org/people/bangcorrupt/sounds/832998/'
page=requests.get(chair_page,timeout=30)
urls=re.findall(r'https://cdn\.freesound\.org/previews/[^\s\"<>]+?\.mp3',page.text)
if page.ok and urls:
    preview=requests.get(urls[0],timeout=45)
    preview.raise_for_status()
    path=OUT/'chair-preview.mp3'
    path.write_bytes(preview.content)
    samples.append(dict(name='chair_scrape',file=path,source=chair_page,expected_risk='not_high'))
else:
    print('Chair preview unavailable; chair real-audio test remains pending.',flush=True)

login=requests.post('http://127.0.0.1:3000/api/auth/login',json=dict(email='admin@gmail.com',password='password123'),timeout=20)
login.raise_for_status()
headers={'Authorization':'Bearer '+login.json()['access_token']}
results=[]
for sample in samples:
    path=sample['file']
    # Upload as a supported WAV regardless of the archive's encoding.
    audio=AudioSegment.from_file(path)
    buf=io.BytesIO()
    audio.export(buf,format='wav')
    data=buf.getvalue()
    response=requests.post('http://127.0.0.1:3000/api/alerts/upload',headers=headers,
        files={'audio':(path.stem+'.wav',data,'audio/wav')},timeout=900)
    response.raise_for_status()
    result=response.json()['result']
    risk=result['analysis']['risk_level']
    checks=dict(original_preserved=result['audio']['original_sha256']==hashlib.sha256(data).hexdigest(),
        expected_risk=risk!='high' if sample['expected_risk']=='not_high' else risk==sample['expected_risk'])
    results.append(dict(sample={**sample,'file':str(path)},result=result,checks=checks))
    (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(name=sample['name'],scores=result['sound_events'],risk=risk,checks=checks),ensure_ascii=False),flush=True)
failures=[r['sample']['name'] for r in results if not all(r['checks'].values())]
if failures:
    raise RuntimeError('Public sound checks failed: '+', '.join(failures))
