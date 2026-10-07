"""Actual device HTTP and database integration checks, no connected ESP32 hardware assumed."""
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid
import requests

sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[1]
settings=json.loads((ROOT/'.runtime/windows-settings.json').read_text(encoding='utf-8-sig'))
BASE='http://127.0.0.1:3000'
login=requests.post(BASE+'/api/auth/login',json=dict(email='admin@gmail.com',password='password123'),timeout=20)
login.raise_for_status()
auth={'Authorization':'Bearer '+login.json()['access_token']}
device_headers={'X-Device-Token':settings['DeviceToken'],'Content-Type':'audio/wav'}
devices=requests.get(BASE+'/api/devices',headers=auth,timeout=20).json()
if isinstance(devices,dict):
    devices=devices.get('data',[])
device=devices[0]['id']
event_id='validation_'+uuid.uuid4().hex
data=(ROOT/'.runtime/validation/normal.wav').read_bytes()
checksum=hashlib.sha256(data).hexdigest()
params={'device_id':device,'type':'scream','confidence':99,'edge_class':'scream','event_id':event_id}
response=requests.post(BASE+'/api/alerts/device-recording',params=params,headers=device_headers,data=data,timeout=30)
response.raise_for_status()
assert response.json()['queued']
file=response.json()['file']
# Same event with different bytes cannot overwrite the original while analysis is pending.
changed=bytearray(data)
changed[-2]^=1
conflict=requests.post(BASE+'/api/alerts/device-recording',params=params,headers=device_headers,data=changed,timeout=30)
assert conflict.status_code in (200,409)
marker=ROOT/'backend-csharp/uploads'/(event_id+'.analyzed')
deadline=time.monotonic()+120
while not marker.exists() and time.monotonic()<deadline:
    time.sleep(.5)
assert marker.exists(),'Device job did not complete'
original=requests.get(BASE+'/tai-lieu/'+file,timeout=20)
original.raise_for_status()
assert hashlib.sha256(original.content).hexdigest()==checksum
listing=requests.get(BASE+'/api/alerts/analyses?limit=100',headers=auth,timeout=30)
listing.raise_for_status()
row=next(a for a in listing.json()['data'] if a['audio_file_url']=='/tai-lieu/'+file)
detail=requests.get(BASE+'/api/alerts/analyses/'+row['id'],headers=auth,timeout=30)
detail.raise_for_status()
result=detail.json()
assert result['analysis']['risk_level']=='low','Fake edge score must not override local context'
assert result['asr']['has_speech'] and result['edge_evidence']['model_score']==99
dup=requests.post(BASE+'/api/alerts/device-recording',params=params,headers=device_headers,data=data,timeout=30)
dup.raise_for_status()
assert dup.json()['duplicate']
listing_after=requests.get(BASE+'/api/alerts/analyses?limit=100',headers=auth,timeout=30).json()
assert sum(a['audio_file_url']=='/tai-lieu/'+file for a in listing_after['data'])==1
assert requests.get(BASE+'/api/alerts/analyses',timeout=20).status_code==401
assert requests.post(BASE+'/api/alerts/upload',files={'audio':('no-auth.wav',data,'audio/wav')},timeout=20).status_code==401
assert requests.post('http://127.0.0.1:5000/analyze-full',json={'filepath':'../appsettings.json'},timeout=20).status_code==404
checks=dict(device_http_pipeline=True,original_immutable=True,edge_score_does_not_override_risk=True,
            original_asr_saved=True,retries_idempotent=True,analysis_access_requires_login=True,
            upload_requires_token=True,ai_path_traversal_rejected=True,analysis_id=row['id'],conflict_status=conflict.status_code)
(ROOT/'.runtime/validation/device-results.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
print(json.dumps(checks),flush=True)
