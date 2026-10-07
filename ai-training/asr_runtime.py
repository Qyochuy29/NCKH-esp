"""Local ASR runtime: preserve the configured model when falling back to CPU."""
import os


class FallbackWhisper:
    def __init__(self, name, requested='auto', gpu_available=False, model_factory=None):
        if model_factory is None:
            from faster_whisper import WhisperModel
            model_factory = WhisperModel
        self.model_factory = model_factory
        self.name = name
        self.device = 'cuda' if requested != 'cpu' and gpu_available else 'cpu'
        self.model = None
        self.fallback_reason = None
        self.last_inference_device = None
        try:
            self._load()
        except Exception as exc:
            self.fallback_reason = str(exc)
            print(f'[ASR] {self.device} initialization failed: {exc}', flush=True)
            if self.device == 'cuda':
                self.device = 'cpu'
                try:
                    self._load()
                except Exception as cpu_exc:
                    print(f'[ASR] CPU unavailable: {cpu_exc}', flush=True)
        print(f'[ASR] device: {self.device}', flush=True)
        print(f'[ASR] model: {name}', flush=True)

    def _load(self):
        self.compute_type = os.environ.get('WHISPER_COMPUTE_TYPE','float16') if self.device=='cuda' else 'int8'
        self.model = self.model_factory(self.name, device=self.device,
            compute_type=self.compute_type)

    def transcribe(self, *args, **kwargs):
        if self.model is None:
            raise RuntimeError('Local Whisper is unavailable')
        try:
            decoded, info = self.model.transcribe(*args, **kwargs)
            # Whisper decodes lazily; keep iteration within the fallback guard.
            segments=list(decoded)
            self.last_inference_device=self.device
            return iter(segments), info
        except Exception as exc:
            if self.device != 'cuda':
                raise
            print(f'[ASR] CUDA inference failed; falling back to CPU: {exc}', flush=True)
            self.fallback_reason=str(exc)
            self.device = 'cpu'
            self.model = None  # Release the failed GPU model before loading CPU.
            self._load()
            print('[ASR] device: cpu', flush=True)
            decoded, info = self.model.transcribe(*args, **kwargs)
            segments=list(decoded)
            self.last_inference_device='cpu'
            return iter(segments), info
