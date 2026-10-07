"""Real CPU decoding smoke test; does not change the running service's configuration."""
import json
import os
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ai-training'))
os.environ['ASR_MODE']='local'
os.environ['WHISPER_MODEL_SIZE']='medium'
from asr_runtime import FallbackWhisper
from transcription import transcribe_audio
from pydub import AudioSegment

runtime=FallbackWhisper('medium','cpu',gpu_available=True)
result=transcribe_audio(runtime,AudioSegment.from_mp3(ROOT/'.runtime/validation/help.mp3'),speech_expected=True)
assert runtime.device=='cpu' and result['has_speech']
assert 'đừng' in result['normalized_transcript'].lower() and 'cứu' in result['normalized_transcript'].lower()
output=dict(device=runtime.device,asr=result,cpu_real_decode=True)
(ROOT/'.runtime/validation/cpu-result.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(device=runtime.device,transcript=result['normalized_transcript'],cpu_real_decode=True),ensure_ascii=False),flush=True)
