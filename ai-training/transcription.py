"""Vietnamese speech-to-text and audio censoring helpers.

Prioritizes accuracy, correct tone marks, and precise word-level censoring (1000Hz beep)
over profanity words without altering the audio timing.
"""

from __future__ import annotations

import math
import os
import re
import unicodedata
from typing import List, Tuple, Dict, Any

import numpy as np
from pydub import AudioSegment
from pydub.generators import Sine


HALLUCINATION_PHRASES = (
    "subscribe",
    "đăng ký kênh",
    "đăng kí cho kênh",
    "theo dõi kênh",
    "cảm ơn các bạn",
    "hẹn gặp lại",
    "ghiền mì gõ",
    "like and share",
    "hãy like",
    "video sau",
    "chúc các bạn",
    "để không bỏ lỡ",
    "những video hấp dẫn",
    "video tiếp theo",
    "hãy đăng ký",
    "kênh lợi",
)

# Prompt ngắn gọn, chỉ cung cấp ngữ cảnh trường học — KHÔNG liệt kê từ vựng cụ thể
# vì liệt kê từ ngữ vào prompt khiến Whisper "ảo giác" copy lại đúng những từ đó vào kết quả!
VIETNAMESE_PROMPT = "Lời nói tiếng Việt."

DEFAULT_PROFANITY_WORDS = [
    # Cụm dài (match ưu tiên trước)
    'cái địt con mẹ mày',
    'địt con mẹ mày',
    'đit con mẹ mày',
    'đjt con mẹ mày',
    'mịt con mẹ mày',
    'cái mịt con mẹ mày',
    'mình còn mẹ à mày',
    'cái địt con mẹ',
    'cái mịt con mẹ',
    'địt cả lò nhà mày',
    'cả lò nhà mày',
    'địt con bà mày',
    'địt mẹ cha mày',
    'câm mẹ cái mồm mày đi',
    'cầm mẹ cái mồn mày đi',
    'câm mẹ cái mồm mày',
    'cầm mẹ cái mồn mày',
    'câm mẹ cái mồm',
    'cầm mẹ cái mồn',
    'câm mẹ cái mỏ',
    'câm mẹ mày mồm',
    'đánh vỡ mồm mày ra rồi',
    'đánh vỡ mồm mày',
    'đập vỡ mồm mày',
    'vả vỡ mồm mày',
    'với mồn mày ra rồi',
    'với mồm mày ra rồi',
    'vỡ mồm mày ra rồi',
    'tuổi lồn sánh vai',
    'tuổi lôn sánh vai',
    'tuổi lôn xánh mày',
    'tuổi lôn xảnh bay',
    'nhờn lồn với tao',
    'tao đánh chết mẹ',
    'đánh chết mẹ mày',
    'đánh chết cha mày',
    'bố mày nhờn với mày',
    'bố mày nhợn với mày',
    'bố mày nhớt với mày',
    'mày có cầm mẹ',
    'mày có câm mẹ',

    # Cụm 3 từ
    'địt con mẹ mà',
    'địt con mẹ',
    'đit con mẹ',
    'địt mẹ mày',
    'đit mẹ mày',
    'mịt mẹ mày',
    'địt bố mày',
    'địt cụ mày',
    'địt bà mày',
    'địt cha mày',
    'cái địt mẹ',
    'cái mịt mẹ',
    'con mẹ mày',
    'đụ má mày',
    'đụ mẹ mày',
    'câm cái mồm',
    'câm mẹ mồm',
    'câm mẹ mỏ',
    'cái đầu buồi',
    'đau bùi lắm bùi',
    'đau buồi lắm buồi',
    'buổi lắm buổi nha mày',
    'buồi lắm buồi nha mày',
    'cần cặc gì',
    'cận dịch cái',
    'cận dịch',
    'con chó đẻ',
    'con chó chết',
    'đồ chó chết',
    'đồ chó đẻ',
    'đồ súc vật',
    'đồ su vật',
    'loại súc vật',
    'loại su vật',
    'mùa xíu vật',
    'một xíu vật',
    'tổ sư cha',
    'tổ cha mày',
    'mả mẹ mày',
    'tiên sư mày',
    'thằng mặt lồn',
    'thằng mặt lôn',
    'con mặt lồn',
    'con mặt lôn',
    'nhờn với bố',
    'nhợn với bố',
    'nhờn với tao',
    'vỡ mồm mày',
    'với mồn mày',
    'chết mẹ mày',
    'chết cha mày',
    'tuổi lồn gì',
    'tuổi lôn gì',
    'tuổi cặc gì',
    'của tổ này',
    'cút mẹ mày',
    'biến mẹ mày',
    'tao lạy mày',
    'tao lại mày',

    # Cụm 2 từ
    'địt mẹ', 'đit mẹ', 'mịt mẹ',
    'địt cụ', 'đit cụ', 'mịt cụ',
    'địt mợ',
    'địt cha',
    'địt bà',
    'địt bố',
    'cái địt',
    'đụ má',
    'đụ mẹ',
    'mẹ mày',
    'bố mày',
    'mẹ kiếp',
    'đầu buồi',
    'đau bùi', 'đau buồi',
    'buổi lắm', 'buổi nha',
    'buồi lắm', 'buồi nha',
    'lồn buồi',
    'cái lồn', 'cái lôn',
    'láu lồn', 'láu lôn',
    'láo lồn', 'láo lôn',
    'mặt lồn', 'mặt lôn',
    'hãm lồn', 'hãm lôn',
    'nhờn lồn',
    'tuổi lồn', 'tuổi lôn',
    'tuổi cặc',
    'đầu cặc',
    'cái cặc',
    'con cặc',
    'con buồi',
    'con phò',
    'con đĩ',
    'chó chết',
    'chó đẻ',
    'chó má',
    'súc sinh',
    'súc vật', 'su vật',
    'đồ ngu',
    'đồ chó',
    'vô học',
    'rẻ rách',
    'rác rưởi',
    'câm mồm',
    'cầm mồn',
    'câm họng',
    'câm miệng',
    'câm mẹ',
    'cầm mẹ',
    'chết mẹ',
    'chết cha',
    'vỡ mồm',
    'với mồn',
    'với mồm',
    'đánh bỡi',
    'vê lờ',
    'vê cờ lờ',
    'đờ mờ',
    'con cụ',
    'thằng lồn', 'thằng lôn',
    'con lồn', 'con lôn',

    # Từ đơn tục tĩu
    'địt', 'đit', 'đjt', 'dit', 'djt', 'mịt',
    'đụ', 'du',
    'lồn', 'lon', 'lồz', 'loz', 'lôn',
    'cặc', 'kặc', 'cac', 'cặt',
    'buồi', 'buoi', 'bùi', 'buôi', 'buổi', 'bổi',
    'đĩ', 'di',
    'phò', 'pho',
    'đéo', 'deo', 'đek', 'đếch',
    'đm', 'đmm', 'đcm', 'dmm', 'dcm', 'dm',
    'vcl', 'vl', 'vcc', 'clm', 'clgt', 'vkl', 'vcll',
    'đb',
    'nứng', 'nung',
    'điếm',
    'ml', 'cức', 'cứt', 'ăn cức', 'ăn cứt', 'thằng ml', 'con ml',
]

# Các từ ngữ tục tĩu độc lập (xuất hiện đơn lẻ là PHẢI che tiếng bíp ngay)
STANDALONE_PROFANITY_TOKENS = {
    'địt', 'đit', 'đjt', 'dit', 'djt', 'mịt',
    'đụ', 'du',
    'lồn', 'lon', 'lồz', 'loz', 'lôn',
    'cặc', 'kặc', 'cac', 'cặt',
    'buồi', 'buoi', 'bùi', 'buôi', 'buổi', 'bổi',
    'đĩ', 'di', 'phò', 'pho',
    'đéo', 'deo', 'đek', 'đếch',
    'đm', 'đmm', 'đcm', 'dmm', 'dcm', 'dm',
    'vcl', 'vl', 'vcc', 'clm', 'clgt', 'vkl', 'vcll',
    'ml', 'cức', 'cứt',
}

# No phonetic substitution may manufacture threats/profanity from ordinary words.
PHONETIC_WORD_MAP = {}
PHONETIC_REGEX_FIXES = []


def correct_vietnamese_transcription(text: str) -> str:
    """Unicode/whitespace only. Never reinterpret the meaning of an ASR result."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()


def get_whisper_waveform(audio_segment: AudioSegment) -> np.ndarray:
    """Convert any pydub AudioSegment to normalized 16 kHz mono float32 for Whisper.
    
    Includes DC offset removal, Butterworth 80Hz high-pass filter (eliminating mic infrasound),
    and clean peak normalization for maximum Whisper acoustic model clarity.
    """
    audio = audio_segment.set_frame_rate(16000).set_channels(1)
    samples = np.asarray(audio.get_array_of_samples(), dtype=np.float32)
    if samples.size == 0:
        return samples
    max_value = float(2 ** (8 * audio.sample_width - 1))
    waveform = samples / max_value

    # DC offset removal
    waveform = waveform - float(np.mean(waveform))
    
    # 4th order Butterworth high-pass filter at 80 Hz to eliminate sub-bass mic rumble
    try:
        from scipy.signal import butter, sosfilt
        sos = butter(4, 80, btype='highpass', fs=16000, output='sos')
        waveform = sosfilt(sos, waveform)
    except Exception:
        pass

    # Clean peak normalization without dynamic compression distortion
    peak = float(np.max(np.abs(waveform)))
    if peak > 1e-4:
        if peak < 0.3:
            # Boost quiet recordings moderately
            gain = min(4.0, 0.90 / peak)
            waveform = waveform * gain
        else:
            waveform = waveform * (0.92 / peak)
            
    return np.clip(waveform, -1.0, 1.0).astype(np.float32)


def _normalized_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").strip()
    return re.sub(r"\s+", " ", text)


def is_hallucination(text: str) -> bool:
    """Check if the text is a common Whisper hallucination."""
    t = text.lower()
    for phrase in HALLUCINATION_PHRASES:
        if phrase in t:
            return True
    return False


def is_whisper_censor_token(raw_word: str) -> bool:
    """Check if Whisper automatically masked the word with asterisks (e.g. b****t, đ***, etc.)"""
    if not raw_word:
        return False
    return '*' in raw_word or '***' in raw_word


def _clean_word_for_matching(raw_word: str) -> str:
    """Remove punctuation, lowercase, and normalize phonetic typos for matching."""
    text = unicodedata.normalize("NFC", raw_word or "").lower()
    clean = re.sub(r"[^\w\s]", "", text).strip()
    return PHONETIC_WORD_MAP.get(clean, clean)


def _accept_segment(segment) -> bool:
    text = _normalized_text(getattr(segment, "text", ""))
    if not text:
        return False

    folded = text.casefold()
    avg_logprob = float(getattr(segment, "avg_logprob", 0.0) or 0.0)
    no_speech_prob = float(getattr(segment, "no_speech_prob", 0.0) or 0.0)

    # Discard known YouTube hallucinations immediately
    if any(phrase in folded for phrase in HALLUCINATION_PHRASES):
        if no_speech_prob > 0.3 or avg_logprob < -0.7:
            return False

    # Discard non-speech segments or extreme low-confidence noise
    # Relaxed thresholds so natural colloquial Vietnamese speech is never erroneously dropped
    if no_speech_prob > 0.85 or avg_logprob < -2.2:
        return False

    return True


def deduplicate_consecutive_phrases(text: str) -> str:
    """Remove consecutive duplicate phrases caused by Whisper decoder latching on trailing silence."""
    words = text.split()
    # Bắt vòng lặp từ đơn: "Ấy! Ấy! Ấy!" hay "Ơ! Ơ! Ơ!" lặp >= 3 lần
    text = re.sub(r'\b(\S+[!?.]?)\s+(?:\1\s+){2,}\1\b', r'\1', text, flags=re.UNICODE)
    text = re.sub(r'\b(\w+)\s+(?:\1\s*[!?.]*\s*){3,}', r'\1', text, flags=re.UNICODE)
    words = text.split()
    if len(words) < 4:
        return text
    for n in range(8, 1, -1):
        i = 0
        while i + 2 * n <= len(words):
            if words[i : i + n] == words[i + n : i + 2 * n]:
                words = words[: i + n] + words[i + 2 * n :]
            else:
                i += 1
    collapsed = " ".join(words)
    # Bắt từ đơn lặp liên tiếp >= 3 lần
    return re.sub(r'\b(\w+)(?:\s+\1){2,}\b', r'\1', collapsed, flags=re.UNICODE)


def _field(value, name, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _asr_result(raw_segments, raw_text, provider, model_name, words=None):
    segments = []
    warnings = []
    for index, seg in enumerate(raw_segments):
        text = _field(seg, "text", "") or ""
        try:
            start, end = float(_field(seg, "start")), float(_field(seg, "end"))
        except (ValueError, TypeError):
            warnings.append("ASR segment has no valid timestamps; raw text retained for audit")
            continue
        if not (math.isfinite(start) and math.isfinite(end) and end >= start >= 0):
            warnings.append("ASR segment has invalid timestamps; raw text retained for audit")
            continue
        lp = _field(seg, "avg_logprob")
        ns = _field(seg, "no_speech_prob")
        accepted = bool(text.strip()) and not (
            ns is not None and float(ns) > 0.85 or lp is not None and float(lp) < -2.2)
        if text.strip() and not accepted:
            warnings.append("A speech segment was excluded because ASR quality was insufficient")
        if is_hallucination(text):
            # A decoder can be confidently wrong. Flag for review even when its
            # native log probability is high; do not erase a genuine quoted ad.
            warnings.append("Stereotyped subscription/outro text requires verification against original audio")
        # Retain the raw ASR output, but exclude weak, stereotyped decoder hallucinations.
        if is_hallucination(text) and (ns is not None and float(ns) > .3 or lp is not None and float(lp) < -.7):
            accepted = False
            warnings.append("Possible ASR hallucination retained in raw transcript; excluded from evidence")
        segments.append({"start": start, "end": end, "text": correct_vietnamese_transcription(text),
                         "raw_text": text, "accepted": accepted,
                         "avg_logprob": lp, "no_speech_prob": ns})
    segments.sort(key=lambda seg: (seg["start"], seg["end"]))
    normalized = correct_vietnamese_transcription(raw_text)
    accepted = [seg for seg in segments if seg["accepted"]]
    # Quality is a routing signal, not an accuracy or violence probability.
    quality = "usable" if accepted else "no_speech"
    if warnings or (raw_text.strip() and not accepted) or any(seg["avg_logprob"] is not None and float(seg["avg_logprob"]) < -1.0 for seg in accepted):
        quality = "review"
    return {"provider": provider, "model": model_name, "has_speech": bool(accepted),
            "raw_transcript": raw_text, "normalized_transcript": normalized,
            "segments": segments, "words": words or [], "quality": quality,
            "status": "success", "warnings": warnings}


def transcribe_local(model, audio_segment, vad_filter=True, speech_expected=True):
    if model is None:
        raise RuntimeError("Local ASR model is unavailable")
    waveform = get_whisper_waveform(audio_segment)
    model_name = os.environ.get("WHISPER_MODEL_SIZE", "medium")
    if waveform.size == 0 or float(np.max(np.abs(waveform))) < 1e-6:
        return _asr_result([], "", "faster-whisper", model_name)
    options = dict(language="vi", task="transcribe", beam_size=5,
                   temperature=0.0, word_timestamps=True,
                   condition_on_previous_text=False)
    # Short, acoustically confirmed speech benefits from full decoding: VAD was
    # deleting insults in the user's clip. Long recordings still use VAD.
    if speech_expected and len(audio_segment)<=30000:
        vad_filter=False
    decoded, info = model.transcribe(waveform, vad_filter=vad_filter,
                                    vad_parameters={"threshold": 0.3, "min_silence_duration_ms": 400,
                                                    "speech_pad_ms": 400} if vad_filter else None, **options)
    raw_segments = list(decoded)
    # Do not force a transcript from music/impacts when VAD found no speech.
    if not raw_segments and vad_filter and speech_expected:
        decoded, info = model.transcribe(waveform, vad_filter=False, **options)
        raw_segments = list(decoded)
    words = [{"start": float(w.start), "end": float(w.end), "word": w.word,
              "probability": getattr(w, "probability", None)}
             for seg in raw_segments for w in (getattr(seg, "words", None) or [])]
    result = _asr_result(raw_segments, "".join(seg.text for seg in raw_segments),
                         "faster-whisper", model_name, words)
    if raw_segments and any(is_hallucination(seg.text) for seg in raw_segments):
        # Retry once without prompting/VAD conditioning. No profanity or threat
        # vocabulary is supplied to the decoder, and the first output is audited.
        retry_options = dict(options)
        retry_options.pop('initial_prompt', None)
        try:
            retried, _ = model.transcribe(waveform, vad_filter=False if speech_expected else vad_filter,
                                          **retry_options)
            retry_segments = list(retried)
            retry_words = [{"start":float(w.start),"end":float(w.end),"word":w.word,
                            "probability":getattr(w,"probability",None)}
                           for seg in retry_segments for w in (getattr(seg,'words',None) or [])]
            retry = _asr_result(retry_segments, ''.join(seg.text for seg in retry_segments),
                                'faster-whisper',model_name,retry_words)
            result['decoder_retry'] = {'initial_raw_transcript':result['raw_transcript'],
                                      'retry_raw_transcript':retry['raw_transcript']}
            if retry['has_speech'] and retry['quality']=='usable':
                retry['decoder_retry']=result['decoder_retry']
                return retry
        except Exception as exc:
            result['warnings'].append(f'Unprompted ASR retry failed: {exc}')
    return result


def transcribe_cloud(audio_segment):
    import io
    from groq import Groq
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ASR_MODE=cloud requires GROQ_API_KEY")
    model_name = os.environ.get("GROQ_ASR_MODEL", "whisper-large-v3-turbo")
    buf = io.BytesIO()
    audio_segment.set_frame_rate(16000).set_channels(1).set_sample_width(2).export(buf, format="wav")
    client = Groq(api_key=api_key, timeout=60)
    result = client.audio.transcriptions.create(file=("audio.wav", buf.getvalue(), "audio/wav"),
                model=model_name, language="vi", response_format="verbose_json",
                timestamp_granularities=["word", "segment"], temperature=0)
    segments = _field(result, "segments", []) or []
    words = [{"start": _field(w, "start"), "end": _field(w, "end"), "word": _field(w, "word"),
              "probability": None} for w in (_field(result, "words", []) or [])]
    return _asr_result(segments, _field(result, "text", "") or "", "groq", model_name, words)


def transcribe_audio(model, audio_segment, vad_filter=True, speech_expected=False):
    mode = os.environ.get("ASR_MODE", "local").lower()
    if mode not in {"local", "cloud", "hybrid"}:
        raise ValueError("ASR_MODE must be local, cloud or hybrid")
    attempts = []
    local = None
    if mode != "cloud":
        try:
            local = transcribe_local(model, audio_segment, vad_filter, speech_expected=speech_expected)
            attempts.append({"provider": "faster-whisper", "status": "success",
                             "raw_transcript": local["raw_transcript"], "quality": local["quality"]})
        except Exception as exc:
            attempts.append({"provider": "faster-whisper", "status": "error", "error": str(exc)})
        if mode == "local" or (local and local["quality"] == "usable") or (
                local and not speech_expected and local["quality"] == "no_speech"):
            if local:
                local["attempts"] = attempts
                if speech_expected and not local["has_speech"]:
                    local["quality"] = "review"
                    local["warnings"].append("Speech detected acoustically but ASR returned no usable speech")
                return local
    if mode == "cloud" or (mode == "hybrid" and os.environ.get("GROQ_API_KEY", "").strip()):
        try:
            cloud = transcribe_cloud(audio_segment)
            cloud["attempts"] = attempts + [{"provider": "groq", "status": "success"}]
            if cloud["has_speech"] or local is None:
                return cloud
            attempts.append({"provider": "groq", "status": "empty", "raw_transcript": cloud["raw_transcript"]})
        except Exception as exc:
            attempts.append({"provider": "groq", "status": "error", "error": str(exc)})
    if local:
        local["attempts"] = attempts
        if speech_expected and not local["has_speech"]:
            local["quality"] = "review"
            local["warnings"].append("Speech detected acoustically but ASR returned no usable speech")
        return local
    result = _asr_result([], "", "groq" if mode == "cloud" else "faster-whisper",
                         os.environ.get("GROQ_ASR_MODEL", "whisper-large-v3-turbo") if mode=="cloud" else os.environ.get("WHISPER_MODEL_SIZE", "medium"))
    result.update(status="unavailable", quality="review", attempts=attempts,
                  warnings=["Speech transcription could not be completed"])
    return result


def _legacy_tuple(result):
    from types import SimpleNamespace
    segments = [SimpleNamespace(start=s["start"], end=s["end"], text=s["text"], words=[])
                for s in result["segments"] if s["accepted"]]
    words = [SimpleNamespace(**w) for w in result["words"]]
    return result["normalized_transcript"], words, segments, None


def transcribe_vietnamese(model, audio_segment, vad_filter=True):
    return _legacy_tuple(transcribe_local(model, audio_segment, vad_filter))


def transcribe_vietnamese_groq(audio_segment):
    return _legacy_tuple(transcribe_cloud(audio_segment))


def transcribe_auto(model, audio_segment, vad_filter=True):
    return _legacy_tuple(transcribe_audio(model, audio_segment, vad_filter))


def censor_audio_and_text(
    audio_segment: AudioSegment,
    transcript: str,
    whisper_words: list,
    profanity_list: list = None,
    padding_ms: int = 180,
    beep_gain: float = -15.0,
) -> Tuple[AudioSegment, str, List[Tuple[int, int]]]:
    """Overlays 1000Hz Sine tone over profanity words in audio and replaces words with '***' in text.
    
    Uses robust multi-layer detection:
    1. Compound profanity phrases matching.
    2. Standalone swear words matching (e.g. 'địt', 'đụ', 'lồn', 'cặc', 'buồi', 'đéo', 'đĩ', etc.).
    3. Auto-censored Whisper tokens matching (words containing '*' like 'b****t', 'đ***').
    4. Safety acoustic padding (180ms) and close-interval merging (200ms) to ensure zero vocal leak.
    
    Returns:
        (censored_audio, censored_transcript, intervals_beeped)
    """
    if profanity_list is None:
        profanity_list = DEFAULT_PROFANITY_WORDS

    # Normalize profanity list
    normalized_profanity = [
        _clean_word_for_matching(p) for p in profanity_list if p.strip()
    ]
    # Sort profanity words by length descending so longer phrases match first
    normalized_profanity.sort(key=lambda x: len(x.split()), reverse=True)

    # 1. Text Censoring with regex
    censored_transcript = unicodedata.normalize("NFC", transcript)
    for p in profanity_list:
        if not p or not p.strip():
            continue
        pattern = r"(?i)(?<!\w)" + re.escape(p.strip()) + r"(?!\w)"
        censored_transcript = re.sub(pattern, "***", censored_transcript)

    # Also censor normalized profanity forms if not already replaced
    for p in normalized_profanity:
        if not p:
            continue
        pattern = r"(?i)(?<!\w)" + re.escape(p) + r"(?!\w)"
        censored_transcript = re.sub(pattern, "***", censored_transcript)

    # 2. Identify Word Timestamps for Beep Overlay
    words_map = []
    for w in whisper_words:
        raw = getattr(w, "word", "")
        clean_w = _clean_word_for_matching(raw)
        if not clean_w:
            continue
        start_ms = int(getattr(w, "start", 0.0) * 1000)
        end_ms = int(getattr(w, "end", 0.0) * 1000)
        has_star = is_whisper_censor_token(raw)

        tokens = clean_w.split()
        if len(tokens) > 1:
            # Distribute time if a single Whisper word segment contains multi-word text
            duration_per_token = (end_ms - start_ms) / len(tokens)
            for idx, tok in enumerate(tokens):
                words_map.append({
                    "raw": raw,
                    "clean": tok,
                    "start": int(start_ms + idx * duration_per_token),
                    "end": int(start_ms + (idx + 1) * duration_per_token),
                    "is_censor_token": has_star,
                })
        else:
            words_map.append({
                "raw": raw,
                "clean": clean_w,
                "start": max(0, start_ms),
                "end": max(0, end_ms),
                "is_censor_token": has_star,
            })

    total_duration = len(audio_segment)
    intervals_to_beep = []
    num_words = len(words_map)

    # Layer A: Match compound n-grams against profanity list
    for p in normalized_profanity:
        p_tokens = p.split()
        k = len(p_tokens)
        if k == 0:
            continue

        for i in range(num_words - k + 1):
            window_tokens = [words_map[i + j]["clean"] for j in range(k)]
            if window_tokens == p_tokens:
                # Add safety padding before and after the word to catch plosives/fricatives
                start_padded = max(0, words_map[i]["start"] - padding_ms)
                end_padded = min(total_duration, words_map[i + k - 1]["end"] + padding_ms)
                if end_padded > start_padded:
                    intervals_to_beep.append((start_padded, end_padded))

    # Layer B: Match standalone profanity tokens and Whisper auto-censored tokens (b****t, đ***, etc.)
    for wm in words_map:
        if wm["clean"] in STANDALONE_PROFANITY_TOKENS or wm["is_censor_token"]:
            start_padded = max(0, wm["start"] - padding_ms)
            end_padded = min(total_duration, wm["end"] + padding_ms)
            if end_padded > start_padded:
                intervals_to_beep.append((start_padded, end_padded))

    if not intervals_to_beep or len(audio_segment) == 0:
        return audio_segment, censored_transcript, []

    # 3. Merge overlapping or very close intervals (within 200ms to avoid tiny gap leaks)
    intervals_to_beep.sort(key=lambda x: x[0])
    merged_intervals = [list(intervals_to_beep[0])]
    for current in intervals_to_beep[1:]:
        last = merged_intervals[-1]
        if current[0] <= last[1] + 200:
            last[1] = max(last[1], current[1])
        else:
            merged_intervals.append(list(current))

    # 4. Generate Clean 1000Hz Sine Beep & Overlay without altering audio timing
    target_rate = audio_segment.frame_rate
    target_channels = audio_segment.channels
    target_sample_width = audio_segment.sample_width

    result_audio = audio_segment
    for start_ms, end_ms in merged_intervals:
        beep_len = end_ms - start_ms
        if beep_len <= 0:
            continue

        # Generate standard 1000Hz censor tone matching exact sample rate, channels & sample width
        beep = (
            Sine(1000)
            .to_audio_segment(duration=beep_len, volume=beep_gain)
            .set_frame_rate(target_rate)
            .set_channels(target_channels)
            .set_sample_width(target_sample_width)
        )

        # Splice: replace the profane segment completely with the beep tone.
        # This completely erases the profanity speech while preserving exact length.
        result_audio = result_audio[:start_ms] + beep + result_audio[end_ms:]

    return result_audio, censored_transcript, [(m[0], m[1]) for m in merged_intervals]
