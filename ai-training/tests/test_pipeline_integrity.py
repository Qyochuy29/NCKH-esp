import hashlib
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from asr_runtime import FallbackWhisper
import analysis_pipeline as pipeline
from pydub import AudioSegment
from transcription import _asr_result


class RuntimeAndIntegrityTests(unittest.TestCase):
    @patch.dict(os.environ,{'MAX_AUDIO_SECONDS':'0.2'})
    def test_long_recording_is_rejected_without_changing_original(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'original.wav'
            with path.open('wb') as stream:
                AudioSegment.silent(2000).export(stream,format='wav')
            before=path.read_bytes()
            with self.assertRaisesRegex(ValueError,'duration limit'):
                pipeline.analyze_file(path,directory,None,None)
            self.assertEqual(path.read_bytes(),before)

    def test_cuda_initialization_falls_back_without_model_downgrade(self):
        calls=[]
        def factory(name,device,compute_type):
            calls.append((name,device))
            if device=='cuda':
                raise RuntimeError('CUDA DLL unavailable')
            return SimpleNamespace()
        runtime=FallbackWhisper('large-v3','auto',True,factory)
        self.assertEqual(runtime.device,'cpu')
        self.assertEqual(calls,[('large-v3','cuda'),('large-v3','cpu')])

    def test_lazy_cuda_decode_error_falls_back(self):
        def broken():
            raise RuntimeError('CUDA failed during generator iteration')
            yield None
        cuda=SimpleNamespace(transcribe=lambda *a,**kw:(broken(),'info'))
        cpu=SimpleNamespace(transcribe=lambda *a,**kw:(iter(['actual segment']),'info'))
        runtime=FallbackWhisper('medium','cuda',True,lambda name,device,compute_type:cuda if device=='cuda' else cpu)
        segments,_=runtime.transcribe('audio')
        self.assertEqual(list(segments),['actual segment'])
        self.assertEqual(runtime.device,'cpu')

    def test_both_initializations_fail_without_server_exception(self):
        def factory(*a,**kw):
            raise RuntimeError('model unavailable')
        runtime=FallbackWhisper('medium','cuda',True,factory)
        self.assertIsNone(runtime.model)
        with self.assertRaises(RuntimeError):
            runtime.transcribe('audio')

    @patch.dict(os.environ,{'CREATE_CENSORED_AUDIO':'true','REASONING_MODE':'rules'})
    def test_censorship_writes_separate_file_and_preserves_raw(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'original.wav'
            with path.open('wb') as output:
                AudioSegment.silent(3000).export(output,format='wav')
            checksum=hashlib.sha256(path.read_bytes()).hexdigest()
            raw=' Mẹ kiếp game này khó thế. '
            asr=_asr_result([dict(start=.2,end=2.5,text=raw)],raw,'mock','test',
                [dict(start=.2,end=.5,word='Mẹ',probability=.8),
                 dict(start=.5,end=.8,word='kiếp',probability=.9)])
            sounds=dict(scores={},events=[],status='success')
            with patch.object(pipeline,'transcribe_audio',return_value=asr),patch.object(pipeline,'detect_audio_events',return_value=sounds):
                result=pipeline.analyze_file(path,folder,None,None)
            self.assertEqual(checksum,hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(result['asr']['raw_transcript'],raw)
            self.assertIn('/processed/',result['audio']['processed_audio_url'])
            self.assertEqual(result['analysis']['risk_level'],'low')


if __name__=='__main__':
    unittest.main()
