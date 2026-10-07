import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import transcription as tr
from pydub import AudioSegment
from pydub.generators import Sine


class ASRContractTests(unittest.TestCase):
    def test_short_confirmed_speech_is_not_truncated_by_vad(self):
        from unittest.mock import Mock
        model=Mock()
        model.transcribe.return_value=(iter([SimpleNamespace(start=0,end=2,text='Xin chào',words=[],avg_logprob=-.1,no_speech_prob=.01)]),None)
        tr.transcribe_local(model,Sine(300).to_audio_segment(duration=3000),speech_expected=True)
        self.assertFalse(model.transcribe.call_args.kwargs['vad_filter'])
        self.assertNotIn('initial_prompt',model.transcribe.call_args.kwargs)

    def test_confident_outro_still_needs_verification(self):
        text='Hãy subscribe cho kênh để không bỏ lỡ những video hấp dẫn'
        result=tr._asr_result([dict(start=0,end=10,text=text,avg_logprob=-.1,no_speech_prob=.01)],text,'faster-whisper','large-v3')
        self.assertEqual(result['quality'],'review')
        self.assertEqual(result['raw_transcript'],text)

    def test_partial_rejection_requires_review(self):
        result=tr._asr_result([dict(start=0,end=1,text='Xin chào',avg_logprob=-.1),
                              dict(start=2,end=3,text='Cứu với',avg_logprob=-3)],'Xin chào Cứu với','faster-whisper','large-v3')
        self.assertEqual(result['quality'],'review')

    def test_outro_retry_is_unprompted_and_audited(self):
        first=SimpleNamespace(start=0,end=2,text='Hãy subscribe cho kênh',words=[],avg_logprob=-.1,no_speech_prob=.01)
        second=SimpleNamespace(start=0,end=2,text='Xin chào',words=[],avg_logprob=-.1,no_speech_prob=.01)
        from unittest.mock import Mock
        model=Mock()
        model.transcribe.side_effect=[(iter([first]),None),(iter([second]),None)]
        result=tr.transcribe_local(model,Sine(300).to_audio_segment(duration=3000))
        self.assertEqual(result['raw_transcript'],'Xin chào')
        self.assertEqual(result['decoder_retry']['initial_raw_transcript'],first.text)
        self.assertNotIn('initial_prompt',model.transcribe.call_args.kwargs)

    def test_normalization_cannot_manufacture_violence(self):
        for text in ['anh mày', 'chơi nhau không', 'đừng đâm em', 'mình còn mẹ à mày',
                     'đánh răng', 'đánh cầu', 'đánh giá', 'buổi nha', 'em xin lỗi']:
            self.assertEqual(tr.correct_vietnamese_transcription(text), text)

    def test_raw_and_timestamps_are_preserved(self):
        original = '  Anh mày!  '
        segment = SimpleNamespace(text=original, start=1.2, end=3.0, words=[],
                                  avg_logprob=-0.2, no_speech_prob=0.1)
        model = SimpleNamespace(transcribe=lambda *a, **k: (iter([segment]), None))
        result = tr.transcribe_local(model, Sine(300).to_audio_segment(duration=4000))
        self.assertEqual(result['raw_transcript'], original)
        self.assertEqual(result['normalized_transcript'], 'Anh mày!')
        self.assertEqual(result['segments'][0]['start'], 1.2)
        self.assertEqual(segment.text, original)

    @patch.dict(os.environ, {'ASR_MODE': 'local', 'GROQ_API_KEY': 'not-used'})
    def test_local_never_calls_cloud(self):
        with patch.object(tr, 'transcribe_cloud', side_effect=AssertionError('cloud called')):
            result = tr.transcribe_audio(None, AudioSegment.silent(1000))
        self.assertEqual(result['status'], 'unavailable')

    @patch.dict(os.environ, {'ASR_MODE': 'hybrid', 'GROQ_API_KEY': 'test'})
    def test_hybrid_local_first_and_cloud_only_on_failure(self):
        local = tr._asr_result([dict(start=0,end=1,text='Xin chào')], 'Xin chào', 'faster-whisper', 'medium')
        with patch.object(tr, 'transcribe_local', return_value=local), patch.object(tr, 'transcribe_cloud') as cloud:
            self.assertEqual(tr.transcribe_audio(None, AudioSegment.silent(1000))['provider'], 'faster-whisper')
            cloud.assert_not_called()
        with patch.object(tr, 'transcribe_local', side_effect=RuntimeError('failure')), patch.object(tr, 'transcribe_cloud', return_value=local) as cloud:
            tr.transcribe_audio(None, AudioSegment.silent(1000))
            cloud.assert_called_once()

    def test_cloud_does_not_invent_model_scores(self):
        result = tr._asr_result([dict(start=0,end=1,text='Cứu với')], 'Cứu với', 'groq', 'whisper-large-v3')
        self.assertIsNone(result['segments'][0]['avg_logprob'])
        self.assertIsNone(result['segments'][0]['no_speech_prob'])

    def test_missing_timestamps_are_not_fabricated(self):
        result = tr._asr_result([dict(text='Cứu với')], 'Cứu với', 'groq', 'test')
        self.assertEqual(result['raw_transcript'], 'Cứu với')
        self.assertEqual(result['segments'], [])
        self.assertEqual(result['quality'], 'review')

    def test_rejected_nonempty_asr_is_review_not_silence(self):
        result = tr._asr_result([dict(start=0,end=1,text='Cứu với',no_speech_prob=.99)],
                                'Cứu với','faster-whisper','medium')
        self.assertFalse(result['has_speech'])
        self.assertEqual(result['quality'],'review')

    def test_no_vad_bypass_when_sound_detector_does_not_find_speech(self):
        from unittest.mock import Mock
        model=Mock()
        model.transcribe.return_value=(iter([]),None)
        result=tr.transcribe_local(model,Sine(300).to_audio_segment(duration=1000),speech_expected=False)
        self.assertEqual(result['raw_transcript'],'')
        self.assertEqual(model.transcribe.call_count,1)

    def test_weak_hallucination_preserves_raw_but_is_not_evidence(self):
        raw='Hãy đăng ký kênh nhé!'
        result=tr._asr_result([dict(start=0,end=1,text=raw,no_speech_prob=.7,avg_logprob=-.3)],raw,'test','test')
        self.assertEqual(result['raw_transcript'],raw)
        self.assertFalse(result['segments'][0]['accepted'])
        self.assertEqual(result['quality'],'review')


if __name__ == '__main__':
    unittest.main()
