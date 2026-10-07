import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from pydub import AudioSegment
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import chunk_analysis as chunks
from context_analysis import analyze_context
from transcription import _asr_result


class ChunkTests(unittest.TestCase):
    def test_stronger_chunk_finding_is_not_hidden(self):
        whole=analyze_context({'speech_segments':[],'timeline':[]})
        part=analyze_context({'speech_segments':[dict(start=1,end=2,text='Địt mẹ mày')],'timeline':[]})
        merged=chunks.aggregate_chunk_results(whole,[dict(index=2,start=10,end=20,analysis=part)])
        self.assertEqual(merged['risk_level'],'review')
        self.assertTrue(merged['has_profanity'])
        self.assertEqual(merged['evidence_items'][0]['start'],11)
        self.assertEqual(whole['risk_level'],'low')

    def analyze(self,duration,folder,asr=None,events=None):
        asr=asr or _asr_result([],'','mock','test')
        sounds=dict(scores={},events=events or [],status='success')
        empty=_asr_result([],'','mock','test')
        with patch.object(chunks,'transcribe_audio',side_effect=lambda *a,**kw:dict(empty)),\
             patch.object(chunks,'detect_audio_events',return_value=dict(scores={},events=[],status='success')):
            return chunks.analyze_chunks(AudioSegment.silent(duration),folder,'test-hash',None,None,asr,sounds)

    def test_counts_lengths_and_actual_files(self):
        for duration,expected in [(10000,[]),(10001,[10,.001]),(25000,[10,10,5]),(30000,[10,10,10])]:
            with self.subTest(duration=duration),tempfile.TemporaryDirectory() as folder:
                result=self.analyze(duration,folder)
                self.assertEqual([c['duration_seconds'] for c in result],expected)
                for c in result:
                    path=Path(folder)/c['audio_url'].removeprefix('/uploads/')
                    self.assertTrue(path.is_file())
                    with path.open('rb') as stream:
                        self.assertAlmostEqual(len(AudioSegment.from_wav(stream))/1000,c['duration_seconds'],places=2)

    def test_derivatives_are_not_overwritten_on_reanalysis(self):
        with tempfile.TemporaryDirectory() as folder:
            self.analyze(25000,folder)
            paths=list(Path(folder).rglob('*.wav'))
            before={str(p):(p.stat().st_mtime_ns,p.read_bytes()) for p in paths}
            self.analyze(25000,folder)
            self.assertEqual(before,{str(p):(p.stat().st_mtime_ns,p.read_bytes()) for p in paths})

    def test_boundary_evidence_is_preserved_without_contaminating_empty_chunks(self):
        asr=_asr_result([dict(start=9.6,end=10.4,text='Cứu với!')],'Cứu với!','mock','test',
             [dict(start=9.6,end=10,word='Cứu'),dict(start=10,end=10.4,word='với!')])
        impact=dict(type='impact',start=10.5,end=11,score=.8,strength='strong')
        with tempfile.TemporaryDirectory() as folder:
            result=self.analyze(25000,folder,asr,[impact])
            self.assertEqual(result[0]['boundary_context']['risk_level'],'high')
            self.assertEqual(result[1]['boundary_context']['risk_level'],'high')
            self.assertIsNone(result[2]['boundary_context'])
