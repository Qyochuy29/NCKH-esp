"""Explainable, conservative context rules. Scores are evidence, not calibrated risk.

This provider detects corroborating signals; it cannot establish who is speaking,
whether an event occurred at school, or whether a recording is acted/quoted.
"""
import os
import re
import unicodedata
from typing import Protocol


class ReasoningProvider(Protocol):
    def analyze(self, data: dict) -> dict: ...


SAFE_ACTIVITY = re.compile(r'đánh\s+(?:răng|cầu(?:\s+lông)?|giá|đàn|máy|cờ|bóng|trống)|tát\s+nước', re.I)
VICTIM = re.compile(r'\b(?:đừng|không được|ngừng|dừng)\s+(?:đánh|đập|tát|đấm|đá|đâm|chém|bóp cổ|bắt nạt)\s+(?:tao|tôi|em|con|cháu|mình)\b|\b(?:sao|tại sao)\s+(?:lại\s+)?đánh\s+(?:tao|tôi|em|con)\b', re.I)
HELP = re.compile(r'\bcứu\s+(?:với|tôi|tao|em|con|cháu)|\b(?:giúp tôi với|buông tao ra|thả em ra|đau quá)\b', re.I)
THREAT = re.compile(r'\b(?:tao|tôi|bố mày)\s+(?:sẽ\s+)?(?:đánh|giết|đập|chém|tát|đấm)\s+(?:(?:chết|vỡ mồm|gãy chân|gãy tay)\s+)?(?:mày|nó|bạn|chúng mày)\b|\b(?:đánh chết|giết chết|đập chết|chém chết)\s+(?:mày|nó|bạn)\b', re.I)
REPORTED = re.compile(r'\b(?:trong phim|diễn kịch|diễn tập|đóng vai|ví dụ|trích dẫn|nó nói|cô nói|thầy nói|bài học)\b', re.I)
JOY = re.compile(r'\b(?:vui quá|thắng rồi|ghi bàn|hét vui|cổ vũ|ăn mừng)\b', re.I)
CONFLICT = re.compile(r'\b(?:không phải tao|mày nói sai|cãi nhau|im mồm|câm mồm|đồ ngu)\b', re.I)
PROFANITY = re.compile(r'\b(?:mẹ kiếp|địt|đụ|đéo|lồn|cặc|buồi|đĩ|vcl|đm|đcm|đkm)\b', re.I)
INSULT = re.compile(r'\b(?:đồ\s+(?:ngu|khốn|chó|mất dạy|vô học)|thằng\s+(?:ngu|chó|khốn)|con\s+(?:đĩ|khốn)|câm mồm|im mồm|địt\s+(?:cái\s+)?(?:con\s+)?mẹ|đụ má|đụ mẹ|tổ sư mày)\b', re.I)
INDIRECT_THREAT = re.compile(r'\b(?:tao\s+(?:sẽ\s+)?cho mày (?:một|1) trận|ra cổng trường tao xử mày)\b', re.I)
NEGATION_PREFIX = re.compile(r'\b(?:không|chưa|chẳng|chả|đừng|cấm)(?:\s+(?:hề|có|bao giờ|muốn|định|được|nên|dám|sẽ|phải|lại)){0,3}\s*$', re.I)
LABELS = {'scream': 'Tiếng hét', 'crying': 'Tiếng khóc', 'impact': 'Tiếng va đập',
          'loud_speech': 'Tiếng nói lớn', 'speech': 'Lời nói', 'speech_activity': 'Có tiếng nói (YAMNet)', 'music': 'Nhạc',
          'applause': 'Vỗ tay', 'door': 'Đóng cửa', 'unusual': 'Âm thanh chưa xác định'}


def speech_signals(text):
    text = re.sub(r'\s+',' ',unicodedata.normalize('NFC',text or '')).strip()
    # Remove only the benign collocation, never rewrite it into an assault.
    probe = SAFE_ACTIVITY.sub('', text)
    threats = list(THREAT.finditer(probe)) + list(INDIRECT_THREAT.finditer(probe))
    threat = any(not NEGATION_PREFIX.search(re.split(r'[.!?;,:]',probe[:m.start()])[-1]) for m in threats)
    return {'victim': bool(VICTIM.search(probe)), 'help': bool(HELP.search(probe)),
            'threat': threat,
            'insult': bool(INSULT.search(text)),
            'profanity': bool(PROFANITY.search(text)), 'conflict': bool(CONFLICT.search(probe)),
            'reported': bool(REPORTED.search(text)), 'joy': bool(JOY.search(text))}


def nearby(a, b, seconds=3.0):
    return max(a['start'], b['start']) - min(a['end'], b['end']) <= seconds


def speech_units(segments, words):
    """Scope language to sentences; use word timestamps, never invent new timings."""
    units=[]
    for seg in segments:
        text=unicodedata.normalize('NFC',seg.get('text',''))
        aligned=[]
        cursor=0
        for w in words:
            if w.get('start') is None or w.get('end') is None:
                continue
            if w['start'] < seg['start'] or w['end'] > seg['end']+.05:
                continue
            token=unicodedata.normalize('NFC',w.get('word','')).strip()
            if not token:
                continue
            at=text.find(token,cursor)
            if at>=0:
                aligned.append((at,at+len(token),w))
                cursor=at+len(token)
        quotes=[]
        for q in re.finditer(r'["“‘\'].*?["”’\']',text,re.S):
            prefix=re.split(r'[.!?;\n]',text[:q.start()])[-1]
            if REPORTED.search(prefix):
                quotes.append((q.start(),q.end()))
        for m in re.finditer(r'[^.!?;\n]+[.!?;]*',text):
            if not m.group().strip():
                continue
            unit=dict(seg,text=m.group().strip(),timestamp_scope='segment')
            matching=[w for a,b,w in aligned if a<m.end() and b>m.start()]
            if matching and len(' '.join(w['word'].strip() for w in matching)) >= .8*len(m.group().strip()):
                unit.update(start=matching[0]['start'],end=matching[-1]['end'],timestamp_scope='words')
            unit['reported_scope']=any(a<m.end() and b>m.start() for a,b in quotes)
            units.append(unit)
    return units


class RulesReasoningProvider:
    def analyze(self, data):
        segments = speech_units([s for s in data.get('speech_segments', []) if s.get('accepted', True)],data.get('speech_words',[]))
        events = [e for e in data.get('timeline', []) if e.get('type') != 'speech']
        suspicious = []
        for seg in segments:
            flags = speech_signals(seg.get('text', ''))
            flags['reported'] = flags['reported'] or seg.get('reported_scope',False)
            if any(flags[k] for k in ('victim','help','threat','conflict','profanity','insult')):
                suspicious.append((seg, flags))
        sounds = [e for e in events if e['type'] in {'scream','crying','impact'}]
        joy_segments = [s for s in segments if speech_signals(s.get('text',''))['joy']]
        reported_segments = [s for s in segments if speech_signals(s.get('text',''))['reported'] or s.get('reported_scope')]
        benign = [e for e in events if e['type'] in {'music','applause','door'}]
        baby_cry = [e for e in events if e['type']=='baby_cry']
        # Benign explanations are local in time, never a blanket veto of threats elsewhere.
        def confounded(event):
            # Background music/joy cannot veto explicit distress or threats nearby.
            if any(nearby(event,s) and (f['victim'] or f['help'] or f['threat']) and not f['reported'] for s,f in suspicious):
                return False
            if event['type']=='crying' and any(nearby(event,b,0) for b in baby_cry):
                return True
            # Scores from different classes are not calibrated likelihood ratios.
            # Keep music-backed distress as REVIEW rather than deleting evidence.
            return any(nearby(event,s) for s in joy_segments + reported_segments)
        corroborating = [e for e in sounds if not confounded(e)]
        strong_sounds = [e for e in corroborating if e.get('strength','strong')=='strong']
        high = False
        selected = []
        evidence_items = []
        for seg, flags in suspicious:
            if flags['victim'] or flags['help'] or flags['threat']:
                associated = [e for e in strong_sounds if nearby(seg,e)]
                # An impact with an explicit distress/threat utterance, or multiple distress
                # sound types near that utterance, warrants HIGH, always human-reviewed.
                paired = any(e['type']=='impact' for e in associated) or len({e['type'] for e in associated}) >= 2
                weak_asr = data.get('asr_quality')=='review' or data.get('asr_status')=='unavailable' or (
                    seg.get('avg_logprob') is not None and seg['avg_logprob'] < -1.0)
                if paired and not flags['reported'] and not weak_asr:
                    high = True
                    selected += associated
                evidence_items.append({'kind': 'speech', 'start': seg['start'], 'end': seg['end'],
                                       'text': seg['text'], 'reported':flags['reported'],
                                       'signal': 'victim' if flags['victim'] else 'help' if flags['help'] else 'threat'})
            if flags['profanity'] or flags['insult']:
                evidence_items.append({'kind':'speech','start':seg['start'],'end':seg['end'],
                                       'text':seg['text'],'signal':'insult' if flags['insult'] else 'profanity'})
        impacts=sorted((e for e in strong_sounds if e['type']=='impact'),key=lambda e:e['start'])
        distress=sorted((e for e in strong_sounds if e['type'] in {'scream','crying'}),key=lambda e:e['start'])
        floor=0
        for a in impacts:
            while floor<len(distress) and distress[floor]['end']<a['start']-3:
                floor+=1
            for b in distress[floor:]:
                if b['start']>a['end']+3:
                    break
                masked=any(nearby(a,e,0) or nearby(b,e,0) for e in benign)
                if nearby(a,b) and not masked:
                    high = True
                    selected += [a,b]
        if not selected:
            selected = [e for e in corroborating if e['type'] in {'scream','crying'}]
        for event in selected:
            item = dict(event, kind='sound')
            if item not in evidence_items:
                evidence_items.append(item)
        suspicious_language = any(f['victim'] or f['help'] or f['threat'] for _, f in suspicious)
        argument = any(f['conflict'] for _, f in suspicious)
        loud_argument = any(f['conflict'] and nearby(seg,e) for seg,f in suspicious for e in events if e['type']=='loud_speech')
        has_profanity = any(f['profanity'] for _,f in suspicious)
        has_insults = any(f['insult'] for _,f in suspicious)
        verbal_abuse = any(f['insult'] and not f['reported'] for _,f in suspicious)
        review = suspicious_language or bool(selected) or loud_argument or verbal_abuse
        risk = 'high' if high else 'review' if review else 'low'
        degraded = data.get('asr_status') == 'unavailable' or data.get('asr_quality') == 'review' or data.get('audio_events_status') == 'unavailable'
        if degraded and risk == 'low':
            risk = 'review'
        category = 'possible_physical_violence' if high else 'threat_or_distress' if suspicious_language else 'possible_verbal_abuse' if verbal_abuse else 'verbal_conflict' if loud_argument else 'profanity' if has_profanity else 'ambiguous_audio' if risk=='review' else 'insufficient_evidence'
        evidence_items = list({(e['kind'],e.get('type'),e.get('signal'),e['start'],e['end'],e.get('text')):e for e in evidence_items}.values())
        evidence_items.sort(key=lambda e: (e['start'],e['end']))
        evidence = []
        for item in evidence_items:
            stamp = f"{item['start']:.1f}–{item['end']:.1f}s"
            evidence.append(f"{stamp}: {'lời trích dẫn' if item.get('reported') else 'lời nói'} ‘{item['text']}’" if item['kind']=='speech' else f"{stamp}: {LABELS.get(item['type'],item['type'])}, điểm YAMNet {item.get('score',0):.3f}")
        if high:
            summary = 'Có nhiều dấu hiệu gần nhau theo thời gian cho thấy có thể có xung đột thể chất hoặc nguy hiểm; cần con người xác minh.'
        elif risk == 'review':
            summary = 'Có dấu hiệu đáng ngờ hoặc phân tích chưa đầy đủ; chưa đủ bằng chứng kết luận bạo lực học đường.'
        else:
            summary = 'Chưa có đủ bằng chứng về bạo lực trong các tín hiệu đã phân tích; đây không phải xác nhận tuyệt đối an toàn.'
        if not high and verbal_abuse:
            summary = 'Có lời xúc phạm/chửi nhắm vào người khác, có thể là bạo lực bằng lời nói; cần xem lại ngữ cảnh.'
        elif not high and has_profanity and not suspicious_language and not loud_argument:
            summary = 'Có chửi tục trong lời nói. Chưa đủ bằng chứng xác định lời chửi hướng vào người khác hoặc có bạo lực thể chất.'
        if degraded and not suspicious_language and not has_profanity and not has_insults and not selected:
            summary = 'Chưa nhận dạng lời nói đủ tin cậy để đánh giá. Cần nghe lại audio gốc; không thể kết luận không có chửi tục hoặc bạo lực.'
        if degraded:
            evidence.append('Một tầng ASR hoặc nhận diện âm thanh không khả dụng/cần kiểm tra; kết quả bị giới hạn.')
        if not evidence:
            evidence.append('Không có lời đe dọa/kêu cứu được hỗ trợ bởi sự kiện âm thanh tương ứng; chửi thề đơn lẻ không đủ để kết luận.')
        evidence_items.sort(key=lambda e: (e['start'],e['end']))
        suspected = high or verbal_abuse
        return {'school_violence_detected': True if suspected else None if risk=='review' else False,
                'school_violence_confirmed':False,'school_context_verified':False,
                'detection_status':'suspected' if suspected else 'inconclusive' if risk=='review' else 'insufficient_evidence',
                'possible_physical_violence':high,'detected':suspected,'risk_level':risk,
                'has_profanity':has_profanity, 'has_insults':has_insults,
                'possible_verbal_abuse':verbal_abuse,
                'analysis_version':'rules-3.0',
                'category': category, 'summary': summary, 'evidence': evidence,
                'evidence_items': evidence_items, 'needs_human_review': risk != 'low',
                'reasoning_provider': 'rules', 'limitations': ['Không xác định danh tính/người nói hoặc địa điểm trường học từ audio.',
                'Rules chưa thay thế mô hình hiểu ngữ cảnh; chưa có benchmark trên dữ liệu trường học.']}


PROVIDERS = {'rules': RulesReasoningProvider()}


def register_reasoning_provider(name: str, provider: ReasoningProvider):
    PROVIDERS[name] = provider


def analyze_context(data):
    mode = os.environ.get('REASONING_MODE','rules').lower()
    if mode not in {'rules','local','cloud','hybrid'}:
        raise ValueError('Invalid REASONING_MODE')
    provider = PROVIDERS.get(mode, PROVIDERS['rules'])
    result = provider.analyze(data)
    if mode not in PROVIDERS:
        result['limitations'].append(f'Provider {mode} chưa được cấu hình; đang dùng rules.')
    return result
