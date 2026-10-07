import os
import sys
import site
from windows_cuda import configure_windows_cuda

# Fix: Tự động nạp thư viện DLL của NVIDIA từ pip packages cho Windows
dll_handles = configure_windows_cuda()
if hasattr(os, "add_dll_directory"):
    for sp in site.getsitepackages() + [site.getusersitepackages()]:
        for module in ["cublas", "cudnn", "cuda_nvrtc"]:
            dll_path = os.path.join(sp, "nvidia", module, "bin")
            if os.path.exists(dll_path):
                try:
                    dll_handles.append(os.add_dll_directory(dll_path))
                    os.environ['PATH'] = dll_path + os.pathsep + os.environ.get('PATH', '')
                except Exception:
                    pass

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import tensorflow as tf

# Reserve GPU memory for Whisper; YAMNet stays on CPU.
tf.config.set_visible_devices([], 'GPU')

import tensorflow_hub as hub
from flask import Flask, request, jsonify
from pydub.exceptions import CouldntDecodeError

from pathlib import Path
import ctranslate2
from analysis_pipeline import analyze_file

UPLOAD_DIR = os.path.abspath(os.environ.get("UPLOAD_DIR", "../tai-lieu"))
os.makedirs(UPLOAD_DIR, exist_ok=True)
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

try:
    gpu_available = ctranslate2.get_cuda_device_count() > 0
except Exception:
    gpu_available = False
print(f"[AI] GPU available: {'YES' if gpu_available else 'NO'}", flush=True)


from asr_runtime import FallbackWhisper


whisper_model_size=os.environ.get("WHISPER_MODEL_SIZE","medium")
asr_mode=os.environ.get("ASR_MODE","local").lower()
whisper_model=None
if asr_mode != "cloud":
    whisper_model=FallbackWhisper(whisper_model_size,os.environ.get("WHISPER_DEVICE","auto"),gpu_available=gpu_available)
    if whisper_model.device=='cuda' and whisper_model.model is not None:
        try:
            import numpy as np
            warmup,_=whisper_model.transcribe(np.zeros(16000,dtype=np.float32),language='vi',vad_filter=False)
            list(warmup)
            print(f'[ASR] startup inference verified: {whisper_model.device}',flush=True)
        except Exception as exc:
            print(f'[ASR] startup inference failed: {exc}',flush=True)
else:
    print("[ASR] device: cloud",flush=True)
    print(f"[ASR] model: {os.environ.get('GROQ_ASR_MODEL','whisper-large-v3-turbo')}",flush=True)
yamnet_model=None
try:
    yamnet_model=hub.load('https://tfhub.dev/google/yamnet/1')
except Exception as exc:
    print(f"[YAMNet] load error: {exc}",flush=True)
print(f"[YAMNet] loaded: {'YES' if yamnet_model is not None else 'NO'}",flush=True)


@app.route('/health')
def health():
    local_ready=whisper_model is not None and whisper_model.model is not None
    cloud_ready=bool(os.environ.get('GROQ_API_KEY','').strip()) and asr_mode in {'cloud','hybrid'}
    ready=yamnet_model is not None and (local_ready or cloud_ready)
    return jsonify(status='healthy' if ready else 'unavailable',
        yamnet_loaded=yamnet_model is not None,whisper_loaded=local_ready,
        asr_mode=asr_mode,asr_model=os.environ.get('GROQ_ASR_MODEL','whisper-large-v3-turbo') if asr_mode=='cloud' else whisper_model_size,
        device=whisper_model.device if whisper_model else 'cloud',gpu_available=gpu_available,
        compute_type=whisper_model.compute_type if whisper_model else None,
        last_inference_device=whisper_model.last_inference_device if whisper_model else None,
        gpu_fallback_reason=whisper_model.fallback_reason if whisper_model else None),200 if ready else 503


def resolve_safe_path(filename):
    if not isinstance(filename,str) or not filename or Path(filename).is_absolute():
        return None
    root=Path(UPLOAD_DIR).resolve()
    candidate=(root/filename).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


@app.route('/analyze-full',methods=['POST'])
@app.route('/analyze-dialog',methods=['POST'])
@app.route('/predict',methods=['POST'])
def analyze_full():
    data=request.get_json(silent=True) or {}
    if not isinstance(data,dict) or not data.get('filepath'):
        return jsonify(error='Missing filepath parameter'),400
    filepath=resolve_safe_path(data['filepath'])
    if filepath is None:
        return jsonify(error='File not found or invalid path'),404
    if filepath.stat().st_size > 50*1024*1024:
        return jsonify(error='File exceeds 50MB limit'),413
    try:
        result=analyze_file(filepath,UPLOAD_DIR,whisper_model,yamnet_model)
        result['asr']['device']='cloud' if result['asr']['provider']=='groq' else whisper_model.device if whisper_model else 'unavailable'
        result['dialog_data']['asr']['device']=result['asr']['device']
        # Old /predict consumers retain a label, always alongside the actual transcript.
        risk=result['analysis']['risk_level']
        result['soundType']='normal' if risk=='low' else 'help' if any(
            e.get('signal') in {'help','victim'} for e in result['analysis']['evidence_items']) else 'threat' if any(
            e.get('signal')=='threat' for e in result['analysis']['evidence_items']) else 'scream' if result['sound_events'].get('scream',0)>=.45 else 'argument'
        return jsonify(result)
    except ValueError as exc:
        return jsonify(error=str(exc)),422
    except CouldntDecodeError:
        return jsonify(error='Audio could not be decoded; upload a valid WAV/MP3 file'),422
    except Exception:
        app.logger.exception('Audio analysis failed')
        return jsonify(error='Audio analysis failed; inspect AI service logs'),500


if __name__ == '__main__':
    app.run(host='0.0.0.0',port=5000)
