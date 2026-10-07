"""Small ASR comparison on synthetic references, not an accuracy benchmark."""
import gc
import json
import os
from pathlib import Path
import re
import site
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ai-training'))
handles=[]
if hasattr(os,'add_dll_directory'):
    for sp in site.getsitepackages():
        for module in ['cublas','cudnn','cuda_nvrtc']:
            directory=Path(sp)/'nvidia'/module/'bin'
            if directory.exists():
                handles.append(os.add_dll_directory(str(directory)))
                os.environ['PATH']=str(directory)+os.pathsep+os.environ.get('PATH','')
import ctranslate2
from asr_runtime import FallbackWhisper
from transcription import transcribe_audio
from pydub import AudioSegment

OUT=ROOT/'.runtime'/'validation'
manifest=json.loads((OUT/'synthetic-manifest.json').read_text(encoding='utf-8'))
samples=[m for m in manifest if m['name'] in {'normal','badminton','phonetic_safety','help','negated_threat'}]
results=[]
os.environ['ASR_MODE']='local'
for name in ['medium','large-v3','large-v3-turbo']:
    os.environ['WHISPER_MODEL_SIZE']=name
    print('Loading comparison model:',name,flush=True)
    runtime=FallbackWhisper(name,'auto',ctranslate2.get_cuda_device_count()>0)
    for sample in samples:
        started=time.monotonic()
        result=transcribe_audio(runtime,AudioSegment.from_mp3(sample['file']),speech_expected=True)
        entry=dict(model=name,device=runtime.device,name=sample['name'],reference=sample['reference'],
                   source='synthetic_tts',seconds=round(time.monotonic()-started,2),asr=result)
        results.append(entry)
        (OUT/'model-comparison.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(dict(model=name,device=runtime.device,name=sample['name'],
                             transcript=result['normalized_transcript'],quality=result['quality']),ensure_ascii=False),flush=True)
    del runtime
    gc.collect()
if any(not r['asr']['has_speech'] for r in results):
    raise RuntimeError('At least one ASR comparison failed to transcribe speech')
