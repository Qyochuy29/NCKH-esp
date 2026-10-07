import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from context_analysis import analyze_context, speech_units
from audio_events import extract_events,detect_audio_events
from analysis_pipeline import build_timeline


def evaluate(text='',events=(),start=1,end=3,**overrides):
    speech=[{'start':start,'end':end,'text':text}] if text else []
    data={'raw_transcript':text,'normalized_transcript':text,'speech_segments':speech,
          'timeline':build_timeline(speech,list(events)),'sound_events':{},'asr_status':'success',
          'asr_quality':'usable','audio_events_status':'success',**overrides}
    return analyze_context(data)


def event(kind,start=3,end=4,score=.8):
    return dict(type=kind,start=start,end=end,score=score)


@patch.dict(os.environ,{'REASONING_MODE':'rules'})
class ContextTests(unittest.TestCase):
    def test_long_audio_chunking_preserves_global_timestamps(self):
        from pydub import AudioSegment
        from types import SimpleNamespace
        calls=[]
        def model(waveform):
            calls.append(len(waveform))
            scores=np.zeros((int(np.ceil(len(waveform)/7680)),521),dtype=np.float32)
            scores[:,11]=.8
            return SimpleNamespace(numpy=lambda:scores),None,None
        result=detect_audio_events(AudioSegment.silent(duration=65000,frame_rate=16000),model)
        self.assertEqual(result['status'],'success')
        self.assertEqual(len(calls),3)
        self.assertLessEqual(max(calls),64*7680+16000)
        scream=next(e for e in result['events'] if e['type']=='scream')
        self.assertEqual(scream['start'],0)
        self.assertEqual(scream['end'],65)

    def test_extended_negation_scope(self):
        for text in ['Tao không hề đánh chết mày','Tao chưa bao giờ giết chết nó','Tao không muốn đánh chết mày']:
            self.assertEqual(evaluate(text,[event('impact')])['risk_level'],'low')
        self.assertEqual(evaluate('Tao không đánh nó. Tao đánh chết mày',[event('impact')])['risk_level'],'high')

    def test_reported_sentence_does_not_hide_actual_help(self):
        result=evaluate('Trong phim có cảnh đánh nhau. Đừng đánh tao! Cứu với!', [event('impact')])
        self.assertEqual(result['risk_level'],'high')
        self.assertEqual(evaluate('Trong phim nó nói: "Tao đánh chết mày. Cứu với!"',[event('impact'),event('scream')])['risk_level'],'review')

    def test_unreliable_speech_cannot_alone_force_high(self):
        self.assertEqual(evaluate('Tao đánh chết mày',[event('impact')],asr_quality='review')['risk_level'],'review')
        self.assertEqual(evaluate('Tao đánh chết mày',[event('impact'),event('scream')],asr_quality='review')['risk_level'],'high')

    def test_baby_cry_is_separate_and_not_violence(self):
        import csv
        with open(Path(__file__).resolve().parents[1]/'yamnet_class_map.csv',encoding='utf-8-sig') as f:
            indices={r['display_name']:int(r['index']) for r in csv.DictReader(f)}
        scores=np.zeros((2,521),dtype=np.float32)
        scores[0,indices['Baby cry, infant cry']]=.9
        scores[1,indices['Thump, thud']]=.8
        events=extract_events(scores,1.44)['events']
        self.assertTrue(any(e['type']=='baby_cry' for e in events))
        self.assertEqual(evaluate(events=events)['risk_level'],'low')
        self.assertNotEqual(evaluate(events=[event('baby_cry'),event('crying'),event('impact')])['risk_level'],'high')

    def test_background_music_keeps_uncertain_sound_evidence(self):
        result=evaluate(events=[event('music'),event('scream'),event('impact')])
        self.assertEqual(result['risk_level'],'review')

    def test_verbal_abuse_is_a_suspected_sign_not_confirmed_school_incident(self):
        result=evaluate('Địt cái con mẹ mày')
        self.assertTrue(result['school_violence_detected'])
        self.assertFalse(result['school_violence_confirmed'])
        self.assertFalse(result['school_context_verified'])
        self.assertEqual(result['detection_status'],'suspected')
        self.assertIsNone(evaluate(asr_status='unavailable')['school_violence_detected'])

    def test_sentences_use_actual_word_times(self):
        seg={'start':0,'end':20,'text':'Trong phim. Cứu với!'}
        words=[dict(start=0,end=1,word='Trong'),dict(start=1,end=2,word='phim.'),
               dict(start=18,end=19,word='Cứu'),dict(start=19,end=20,word='với!')]
        units=speech_units([seg],words)
        self.assertEqual(units[1]['start'],18)
        self.assertEqual(units[1]['end'],20)
        result=evaluate('Trong phim. Cứu với!',[event('impact',3,4)],start=0,end=20,speech_words=words)
        self.assertNotEqual(result['risk_level'],'high')

    def test_complained_phrase_and_missing_profanity(self):
        for text in ['Địt mẹ', 'Địt   mẹ mày', 'Con đĩ']:
            result=evaluate(text)
            self.assertTrue(result['has_profanity'])
            self.assertTrue(result['possible_verbal_abuse'])
            self.assertEqual(result['risk_level'],'review')
        self.assertTrue(evaluate('Buồi')['has_profanity'])

    def test_unreliable_asr_does_not_claim_no_violence(self):
        result=evaluate('Hãy subscribe cho kênh',asr_quality='review')
        self.assertEqual(result['risk_level'],'review')
        self.assertIn('Chưa nhận dạng',result['summary'])

    def test_profanity_is_recorded_without_claiming_physical_violence(self):
        result=evaluate('Mẹ kiếp game này khó thế')
        self.assertTrue(result['has_profanity'])
        self.assertEqual(result['category'],'profanity')
        self.assertEqual(result['risk_level'],'low')
        self.assertTrue(result['evidence_items'])

    def test_direct_insults_need_review(self):
        for text in ['Mày là đồ ngu', 'Địt mẹ mày', 'Câm mồm']:
            result=evaluate(text)
            self.assertEqual(result['risk_level'],'review')
            self.assertTrue(result['possible_verbal_abuse'])
            self.assertIn('xúc phạm',result['summary'])

    def test_negation_is_not_a_threat(self):
        result=evaluate('Tao không đánh chết mày',[event('impact')])
        self.assertEqual(result['risk_level'],'low')

    def test_background_does_not_hide_explicit_distress(self):
        for text in ['Đừng đánh tao! Cứu với!', 'Vui quá! Đừng đánh tao! Cứu với!']:
            result=evaluate(text,[event('impact'),event('scream'),event('music',score=.99)])
            self.assertEqual(result['risk_level'],'high')

    def test_indirect_threats_need_review(self):
        for text in ['Ra cổng trường tao xử mày','Tao sẽ cho mày một trận']:
            self.assertEqual(evaluate(text)['risk_level'],'review')

    def test_normal_and_false_positive_language(self):
        for text in ['Xin chào, hôm nay học bài gì?', 'Lớp học hôm nay đông quá',
                     'Ra sân trường chơi nhé', 'Nhớ đánh răng trước khi ngủ',
                     'Chiều nay đi đánh cầu không?', 'Đánh giá bài này khó thật',
                     'Mẹ kiếp game này khó thế', 'Anh mày', 'Chơi nhau không?',
                     'Mày ra đây', 'Không phải tao. Mày nói sai rồi', 'Không được đánh nhau',
                     'Tao không đánh mày']:
            with self.subTest(text=text):
                self.assertEqual(evaluate(text)['risk_level'],'low')

    def test_benign_acoustic_explanations(self):
        for label in ['door','applause','music']:
            self.assertEqual(evaluate(events=[event('impact',score=.7),event(label,score=.9)])['risk_level'],'low')
        self.assertEqual(evaluate('Vui quá, thắng rồi!', [event('scream'),event('impact')])['risk_level'],'low')
        self.assertEqual(evaluate(events=[event('impact')])['risk_level'],'low')  # chair/slam alone

    def test_single_signals_need_review(self):
        for text in ['Tao đánh chết mày', 'Cứu với!', 'Đừng đánh tao']:
            self.assertEqual(evaluate(text)['risk_level'],'review')
        for kind in ['crying','scream']:
            self.assertEqual(evaluate(events=[event(kind)])['risk_level'],'review')
        self.assertEqual(evaluate('Không phải tao! Mày nói sai rồi!', [event('loud_speech')])['risk_level'],'review')

    def test_correlated_violence_signals(self):
        cases=[('Đừng đánh tao', [event('impact')]), ('Tao đánh chết mày',[event('impact'),event('scream')]),
               ('Cứu với',[event('impact'),event('crying')]), ('',[event('scream'),event('impact')]),
               ('',[event('crying'),event('impact')])]
        for text,events in cases:
            with self.subTest(text=text,events=events):
                result=evaluate(text,events)
                self.assertEqual(result['risk_level'],'high')
                self.assertTrue(result['needs_human_review'])
                self.assertTrue(result['evidence_items'])

    def test_distant_events_cannot_corroborate_threat(self):
        self.assertEqual(evaluate('Tao đánh chết mày',[event('impact',100,101)])['risk_level'],'review')

    def test_tentative_scream_requires_review_and_cannot_force_high(self):
        weak=dict(event('scream',score=.2),strength='tentative')
        self.assertEqual(evaluate(events=[weak,event('impact')])['risk_level'],'review')
        scores=np.zeros((2,521),dtype=np.float32)
        scores[0,11]=.2
        candidate=next(e for e in extract_events(scores,1)['events'] if e['type']=='scream')
        self.assertEqual(candidate['strength'],'tentative')

    def test_strong_and_tentative_event_times_are_not_merged(self):
        scores=np.zeros((2,521),dtype=np.float32)
        scores[:,11]=[.3,.8]
        events=[e for e in extract_events(scores,2)['events'] if e['type']=='scream']
        self.assertEqual(len(events),2)
        self.assertEqual(events[0]['strength'],'tentative')
        self.assertEqual(events[1]['strength'],'strong')
        self.assertEqual(events[1]['start'],.48)

    def test_reported_or_acted_threat_is_not_high(self):
        result=evaluate('Trong phim nó nói tao đánh chết mày',[event('impact'),event('scream')])
        self.assertEqual(result['risk_level'],'review')

    def test_incomplete_analysis_never_claims_safe(self):
        self.assertEqual(evaluate(asr_status='unavailable')['risk_level'],'review')

    def test_timeline_sort_and_exact_speech(self):
        timeline=build_timeline([dict(start=5,end=6,text='Cứu với!')],[event('impact',2,3)])
        self.assertEqual([t['start'] for t in timeline],[2,5])
        self.assertEqual(timeline[1]['text'],'Cứu với!')

    def test_yamnet_label_mapping_scores_and_timing(self):
        scores=np.zeros((4,521),dtype=np.float32)
        scores[0,459]=.9  # Basketball bounce must not be treated as Slam/impact.
        scores[1:3,11]=.82
        scores[3,461]=.74
        result=extract_events(scores,2.1)
        self.assertAlmostEqual(result['scores']['scream'],.82,places=5)
        self.assertAlmostEqual(result['scores']['impact'],.74,places=5)
        scream=next(e for e in result['events'] if e['type']=='scream')
        self.assertEqual(scream['start'],.48)
        self.assertEqual(scream['end'],1.92)
        self.assertFalse(any(e['type']=='impact' and e['start']==0 for e in result['events']))


if __name__=='__main__': unittest.main()
