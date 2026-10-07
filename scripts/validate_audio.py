"""Opt-in integration checks using SYNTHETIC Vietnamese TTS, never a school-audio benchmark.

Run in Windows-Common's environment so FFmpeg is on PATH. Files/results stay in .runtime.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import time
import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.runtime' / 'validation'
CASES = [
    ('normal', 'Xin chào các bạn. Hôm nay chúng ta học môn toán.', 'low'),
    ('classroom', 'Các em mở sách trang hai mươi. Bạn nào muốn trả lời câu hỏi?', 'low'),
    ('schoolyard', 'Giờ ra chơi rồi. Chúng mình ra sân trường chơi nhé.', 'low'),
    ('badminton', 'Chiều nay đi đánh cầu không? Nhớ mang vợt nhé.', 'low'),
    ('brush_teeth', 'Nhớ đánh răng trước khi ngủ.', 'low'),
    ('evaluate', 'Đánh giá bài này khó thật.', 'low'),
    ('phonetic_safety', 'Anh mày đang học bài. Chơi nhau không?', 'low'),
    ('profanity_game', 'Mẹ kiếp game này khó thế.', 'low'),
    ('argument', 'Không phải tao. Mày nói sai rồi.', 'low'),
    ('threat', 'Mày ra đây. Tao đánh chết mày.', 'review'),
    ('help', 'Đừng đánh tao. Cứu với!', 'review'),
    ('negated_threat', 'Tao không đánh mày. Không được đánh nhau.', 'low'),
    ('quoted_threat', 'Trong phim, người đó nói: tao đánh chết mày.', 'review'),
    ('joy', 'Vui quá! Chúng ta thắng rồi! Cổ vũ nào!', 'low'),
]


async def generate():
    import edge_tts
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, text, risk in CASES:
        file = OUT / (name + '.mp3')
        if not file.exists() or not file.stat().st_size:
            await asyncio.wait_for(edge_tts.Communicate(text, 'vi-VN-HoaiMyNeural').save(str(file)), 90)
        manifest.append(dict(name=name, reference=text, expected_risk=risk, file=str(file),
                             source='synthetic_tts', voice='vi-VN-HoaiMyNeural'))
        print('Generated synthetic:', name, flush=True)
    (OUT/'synthetic-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    # WAV uses the same reference, testing the second required upload format.
    from pydub import AudioSegment
    AudioSegment.from_mp3(OUT/'normal.mp3').export(OUT/'normal.wav',format='wav')


def analyze():
    OUT.mkdir(parents=True, exist_ok=True)
    login = requests.post('http://127.0.0.1:3000/api/auth/login',
                          json=dict(email='admin@gmail.com',password='password123'),timeout=20)
    login.raise_for_status()
    headers={'Authorization':'Bearer '+login.json()['access_token']}
    results=[]
    for name,text,risk in CASES + [('normal_wav',CASES[0][1],'low')]:
        file=OUT/(name+'.mp3') if name!='normal_wav' else OUT/'normal.wav'
        if not file.exists():
            continue
        checksum=hashlib.sha256(file.read_bytes()).hexdigest()
        started=time.monotonic()
        with file.open('rb') as f:
            response=requests.post('http://127.0.0.1:3000/api/alerts/upload',headers=headers,
                files={'audio':(file.name,f,'audio/wav' if file.suffix=='.wav' else 'audio/mpeg')},timeout=900)
        response.raise_for_status()
        payload=response.json()
        result=payload['result']
        asr=result['asr']
        timeline=result['timeline']
        original=requests.get('http://127.0.0.1:3000'+result['audio']['original_audio_url'],timeout=30)
        original.raise_for_status()
        checks={'has_actual_transcript':bool(asr['raw_transcript'].strip()),
                'timestamps_present':bool(asr['segments']),
                'timeline_sorted':timeline==sorted(timeline,key=lambda e:(e['start'],e['end'],e['type'])),
                'original_preserved':checksum==result['audio']['original_sha256']==hashlib.sha256(original.content).hexdigest(),
                'expected_risk':result['analysis']['risk_level']==risk,
                'no_fake_confidence':all(a.get('confidence_score') is None for a in payload.get('alerts',[]))}
        entry=dict(name=name,source='synthetic_tts',reference=text,expected_risk=risk,
                   seconds=round(time.monotonic()-started,2),checks=checks,result=result,
                   analysis_id=payload['analysis_id'])
        results.append(entry)
        (OUT/'audio-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(dict(name=name,transcript=asr['normalized_transcript'],risk=result['analysis']['risk_level'],
                              device=asr['device'],checks=checks),ensure_ascii=False),flush=True)
    if not results:
        raise RuntimeError('No synthetic audio files available')
    failures=[r['name'] for r in results if not all(r['checks'].values())]
    if failures:
        raise RuntimeError('Integration checks failed: '+', '.join(failures))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--generate',action='store_true')
    parser.add_argument('--analyze',action='store_true')
    args=parser.parse_args()
    if args.generate:
        asyncio.run(generate())
    if args.analyze:
        analyze()
