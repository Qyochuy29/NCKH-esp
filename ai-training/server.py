import os
import sys
import site

# Fix: Tự động nạp thư viện DLL của NVIDIA từ pip packages cho Windows
if hasattr(os, "add_dll_directory"):
    for sp in site.getsitepackages() + [site.getusersitepackages()]:
        for module in ["cublas", "cudnn", "cuda_nvrtc"]:
            dll_path = os.path.join(sp, "nvidia", module, "bin")
            if os.path.exists(dll_path):
                try:
                    os.add_dll_directory(dll_path)
                except Exception:
                    pass

sys.stdout.reconfigure(encoding='utf-8')

# Thêm đường dẫn FFMPEG vào PATH nếu có trên Windows
ffmpeg_path = r"C:\Users\admin\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin"
if os.path.exists(ffmpeg_path) and ffmpeg_path not in os.environ.get("PATH", ""):
    os.environ["PATH"] += os.pathsep + ffmpeg_path

import re
import uuid
import tempfile
import numpy as np
import tensorflow as tf

gpus = tf.config.experimental.list_physical_devices('GPU')
if gpus:
    try:
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)
    except RuntimeError as e:
        print(e)

import tensorflow_hub as hub
import librosa
from pydub import AudioSegment
from flask import Flask, request, jsonify
from faster_whisper import WhisperModel
import unicodedata

# Import các helper đã được tối ưu hóa chuẩn xác cho tiếng Việt
from transcription import (
    get_whisper_waveform,
    transcribe_vietnamese,
    transcribe_auto,        # Tự động dùng Groq API nếu có key, fallback local
    censor_audio_and_text,
    DEFAULT_PROFANITY_WORDS,
)

# ============================================================
# THƯ MỤC AUDIO ĐƯỢC PHÉP ĐỌC
# ============================================================
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.abspath("../tai-lieu"))
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_FILE_SIZE_MB = 20
CONFIDENCE_THRESHOLD = 0.55

PROFANITY_WORDS = DEFAULT_PROFANITY_WORDS

THREAT_PHRASES = [
    'thích chết', 'ăn đấm', 'chán sống', 'xanh cỏ',
    'câm cái mồm', 'câm mồm', 'câm họng', 'nín ngay', 'vả vỡ mồm', 'sủa tiếp', 'tuổi lồn',
    'đánh vỡ mồm', 'đập vỡ mồm', 'vỡ mồm', 'đánh chết', 'chết mẹ mày', 'chết cha mày',
    'nhờn với mày', 'nhờn với bố', 'nhờn với tao', 'nhợn với', 'tuổi lồn sánh vai',
    'ngon thì', 'nhào vô', 'bước ra', 'đụng vào tao', 'sờ vào người',
    'gọi người', 'gọi hội', 'gọi anh em', 'bốc máy',
    'chém chết', 'xin tí huyết', 'đập gãy', 'phá nát', 'nhập viện',
    'biết nhà', 'coi chừng tao', 'gặp đâu đánh đó', 'bắt được',
]

THREAT_WEAK_WORDS = ['đánh', 'giết', 'chết', 'tát']

SAFE_COLLOCATIONS = [
    'đánh răng', 'đánh đàn', 'đánh giá', 'đánh máy', 'đánh cờ', 'đánh bóng',
    'chết máy', 'chết điện', 'chết wifi', 'chết mạng', 'tát nước',
]

EMERGENCY_WORDS = [
    # Kêu cứu khẩn cấp
    'cứu tôi', 'giúp tôi', 'cứu em', 'cứu cháu', 'cứu con', 'cứu tao', 'cứu với', 'có ai không',
    'cứu', 'buông tao', 'thả tao', 'buông em', 'thả em', 'bỏ em ra', 'buông ra', 'thả ra', 'bỏ tao ra',
    'cướp', 'giết người', 'bỏ ra', 'công an', 'bảo vệ', 'có dao', 'có súng', 'nó đâm',
    'cấp cứu', 'bệnh viện', 'xe thương', 'chảy máu', 'gãy xương', 'ngất',
    'đột quỵ', 'hộc máu', 'thở không được', 'ép tim',
    'cháy', 'nổ', 'sập', 'ngập', 'lụt', 'chìm', 'kẹt', 'ngạt khói', 'phá cửa',

    # Van xin & Lạy lục (Học đường / Nạn nhân bị bạo hành)
    'em xin anh', 'em xin chị', 'cháu xin chú', 'cháu xin cô', 'con xin ba', 'con xin mẹ', 'con xin bố',
    'con lạy ba', 'con lạy mẹ', 'con lạy bố', 'em lạy anh', 'em lạy chị', 'lạy anh', 'lạy chị', 'lạy mày',
    'tha cho em', 'tha cho con', 'tha cho cháu', 'tha cho mình', 'tha cho tôi', 'tha cho tao',
    'tha em đi', 'tha cho em đi', 'tha con đi', 'tha cháu đi', 'tha em lần này', 'tha cho một lần',
    'xin tha', 'xin tha mạng', 'tha mạng', 'van xin', 'lạy lục', 'cho em xin', 'cho con xin', 'làm ơn',
    'đừng đánh', 'đừng đánh em', 'đừng đánh con', 'đừng đánh cháu', 'đừng đánh nữa', 'đừng đánh tao',
    'đừng đập em', 'đừng tát em', 'đừng đá em', 'đừng bắt nạt em', 'đừng ép em', 'đừng kéo tóc',
    'đừng mà', 'xin đừng', 'đau quá', 'đau em', 'đau em quá', 'đau con quá', 'đau quá mẹ ơi', 'đau quá anh ơi',
    'em đau', 'đau lắm', 'đau rồi', 'đau quá rồi', 'em đau rồi', 'đau người', 'đau mình', 'đau',
    'em có làm gì đâu', 'sao lại đánh em', 'sao lại đánh con', 'sao lại đánh', 'em biết lỗi rồi', 'con biết lỗi rồi', 'em xin lỗi', 'em xin lỗi mà', 'xin lỗi mà',
    'mẹ ơi', 'cứu con với', 'bố ơi', 'ba ơi', 'chết mất', 'tha lỗi',
    'em xin', 'con xin', 'cháu xin', 'xin anh', 'xin chị', 'xin bạn', 'xin tha cho em',
    'đánh người', 'bị đánh', 'đánh đập', 'bị tát', 'tát em', 'đá em', 'đấm em', 'đấm đá', 'tha em', 'tha con',

    # Tiếng thốt kêu cứu & rên rỉ đau đớn
    'ối giời ơi', 'ối mẹ ơi', 'ối ba ơi', 'ối giời', 'ối trời ơi', 'ối đau quá', 'á đau quá'
]

app = Flask(__name__)

print("Đang tải bộ não AI YAMNet từ Google...")
try:
    yamnet_model_handle = 'https://tfhub.dev/google/yamnet/1'
    yamnet_model = hub.load(yamnet_model_handle)
    print("✅ Đã tải xong YAMNet!")
except Exception as e:
    print(f"⚠️ Lỗi tải YAMNet: {e}")

whisper_model_size = os.environ.get("WHISPER_MODEL_SIZE", "small")
whisper_model = None
print(f"Đang tải Faster Whisper Model ({whisper_model_size})...")
try:
    whisper_model = WhisperModel(whisper_model_size, device="cuda", compute_type="int8_float16")
    print(f"✅ Đã tải xong WhisperModel ({whisper_model_size}) trên CUDA!")
except Exception as e:
    print(f"ℹ️ Không dùng CUDA ({e}), tự động chuyển sang CPU...")
    try:
        whisper_model = WhisperModel(whisper_model_size, device="cpu", compute_type="int8")
        print(f"✅ Đã tải xong WhisperModel ({whisper_model_size}) trên CPU!")
    except Exception as e_cpu:
        print(f"⚠️ Lỗi tải WhisperModel {whisper_model_size} trên CPU: {e_cpu}")
        try:
            whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
            print("✅ Đã tải fallback WhisperModel (base) trên CPU!")
        except Exception as e_base:
            print(f"❌ Không thể tải WhisperModel: {e_base}")

def resolve_safe_path(filename: str):
    if not filename:
        return None
    safe_name = os.path.basename(filename)
    full_path = os.path.abspath(os.path.join(UPLOAD_DIR, safe_name))
    if not full_path.lower().startswith(UPLOAD_DIR.lower()):
        return None
    return full_path

def contains_word(text: str, phrase: str) -> bool:
    pattern = r'(?<!\w)' + re.escape(phrase) + r'(?!\w)'
    return re.search(pattern, text, flags=re.UNICODE) is not None

def detect_threat_weak_word(text: str, word: str) -> bool:
    if not contains_word(text, word):
        return False
    for safe in SAFE_COLLOCATIONS:
        if word in safe and contains_word(text, safe):
            return False
    return True

def analyze_transcript(transcript: str):
    lower_text = transcript.lower()
    has_vulgarity = any(contains_word(lower_text, w) for w in PROFANITY_WORDS) or '***' in lower_text or '*' in lower_text
    is_threat = any(contains_word(lower_text, p) for p in THREAT_PHRASES)
    if not is_threat:
        weak_hits = sum(1 for w in THREAT_WEAK_WORDS if detect_threat_weak_word(lower_text, w))
        is_threat = weak_hits >= 2
    is_emergency = any(contains_word(lower_text, w) for w in EMERGENCY_WORDS)
    return has_vulgarity, is_threat, is_emergency

import subprocess

def save_censored_audio(censored_audio, filepath):
    ext = os.path.splitext(filepath)[1].lstrip('.').lower()
    if ext in ['mp4', 'webm', 'mkv', 'mov', 'avi']:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tf:
            temp_wav = tf.name
        temp_out = filepath + ".tmp." + ext
        try:
            censored_audio.export(temp_wav, format="wav")
            cmd = [
                "ffmpeg", "-y",
                "-i", filepath,
                "-i", temp_wav,
                "-c:v", "copy",
                "-map", "0:v:0?",
                "-map", "1:a:0",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                temp_out
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0 and os.path.exists(temp_out) and os.path.getsize(temp_out) > 0:
                os.replace(temp_out, filepath)
            else:
                censored_audio.export(filepath, format="mp3")
        except Exception as err:
            print(f"Lỗi khi thay audio cho video bằng ffmpeg: {err}")
        finally:
            if os.path.exists(temp_wav):
                try: os.remove(temp_wav)
                except Exception: pass
            if os.path.exists(temp_out):
                try: os.remove(temp_out)
                except Exception: pass
    else:
        fmt = ext if ext in ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'] else 'mp3'
        censored_audio.export(filepath, format=fmt)


# ============================================================
# CẤU HÌNH NHÃN YAMNET CHUẨN XÁC TỪ GOOGLE AUDIOSET
# ============================================================
# Nhóm Gào thét / La hét
YAMNET_SCREAM_CLASSES = [
    6,   # Shout
    7,   # Bellow
    9,   # Yell
    10,  # Children shouting
    11,  # Screaming (Gào thét chuẩn)
]

# Nhóm Khóc lóc / Nức nở / Rên rỉ (Tách rõ nhóm chính chuẩn xác và nhóm phụ)
YAMNET_CRY_PRIMARY_CLASSES = [
    19,  # Crying, sobbing (Khóc nức nở chuẩn)
    20,  # Baby cry, infant cry
    21,  # Whimper (Thút thít)
    22,  # Wail, moan (Kêu khóc, rên rỉ)
]
YAMNET_CRY_SECONDARY_CLASSES = [
    33,  # Groan (Rên rỉ đau đớn)
    39,  # Gasp (Thở dốc / hoảng loạn)
]
YAMNET_CRY_CLASSES = YAMNET_CRY_PRIMARY_CLASSES + YAMNET_CRY_SECONDARY_CLASSES

# Nhóm Va đập / Đập phá
YAMNET_IMPACT_CLASSES = [
    459, # Slam (Đập sầm cửa, va đập mạnh)
    460, # Bang (Tiếng nổ/đập bang)
    461, # Slap, smack (Cú tát)
    462, # Whack, thwack (Cú đánh mạnh)
    463, # Smash, crash (Đập phá, vỡ tan tành)
    464, # Breaking (Gãy vỡ)
    472, # Crushing (Nghiền nát)
]

YAMNET_SPEECH_CLASSES = [0, 1, 2, 3, 4, 5]
DANGEROUS_YAMNET_CLASSES = YAMNET_SCREAM_CLASSES + YAMNET_CRY_CLASSES + YAMNET_IMPACT_CLASSES

def classify_audio(audio_data):
    try:
        if isinstance(audio_data, AudioSegment):
            waveform = get_whisper_waveform(audio_data)
        else:
            waveform = audio_data
            
        scores, embeddings, spectrogram = yamnet_model(waveform)
        scores_np = scores.numpy()
        max_scores = np.max(scores_np, axis=0)
        
        scream_score = float(max(max_scores[c] for c in YAMNET_SCREAM_CLASSES))
        cry_primary_score = float(max(max_scores[c] for c in YAMNET_CRY_PRIMARY_CLASSES))
        cry_score = float(max(max_scores[c] for c in YAMNET_CRY_CLASSES))
        impact_score = float(max(max_scores[c] for c in YAMNET_IMPACT_CLASSES))
        speech_score = float(max(max_scores[c] for c in YAMNET_SPEECH_CLASSES))
        
        scream_timestamps = []
        cry_timestamps = []
        impact_timestamps = []
        for i, frame in enumerate(scores_np):
            t = round(i * 0.48, 2)
            # Chỉ ghi nhận tiếng khóc nếu là lớp khóc chuẩn >= 0.32 hoặc lớp phụ >= 0.65
            if any(frame[c] >= 0.32 for c in YAMNET_CRY_PRIMARY_CLASSES) or any(frame[c] >= 0.65 for c in YAMNET_CRY_SECONDARY_CLASSES):
                cry_timestamps.append(t)
            if any(frame[c] >= 0.38 for c in YAMNET_SCREAM_CLASSES):
                scream_timestamps.append(t)
            if any(frame[c] >= 0.50 for c in YAMNET_IMPACT_CLASSES):
                impact_timestamps.append(t)
                
        # Phát hiện tiếng khóc lóc: cần ít nhất 2 frames để loại trừ thở dài/nấc cụt/hát
        has_cry_sound = (cry_primary_score >= 0.35 and len(cry_timestamps) >= 2) or (cry_primary_score >= 0.55 and len(cry_timestamps) >= 1)
        has_scream_sound = (scream_score >= 0.40 and len(scream_timestamps) >= 2) or scream_score >= 0.55

        # Phát hiện va đập cơ học:
        if speech_score >= 0.30:
            has_impact_sound = (impact_score >= 0.55 and len(impact_timestamps) >= 2) or impact_score >= 0.75
        else:
            has_impact_sound = (impact_score >= 0.45 and len(impact_timestamps) >= 2) or impact_score >= 0.65

        # ƯU TIÊN 1: Khóc lóc (crying) luôn được ưu tiên hàng đầu, không bị đập phá đè
        if has_cry_sound:
            return 'crying', cry_primary_score, cry_timestamps, scream_timestamps, impact_timestamps, speech_score
        elif has_scream_sound:
            return 'scream', scream_score, cry_timestamps, scream_timestamps, impact_timestamps, speech_score
        elif has_impact_sound and not has_cry_sound:
            return 'dap_pha', impact_score, cry_timestamps, scream_timestamps, impact_timestamps, speech_score
        elif speech_score >= 0.20:
            return 'speech', speech_score, cry_timestamps, scream_timestamps, impact_timestamps, speech_score
        else:
            return 'unknown', speech_score, cry_timestamps, scream_timestamps, impact_timestamps, speech_score
            
    except Exception as e:
        print(f"Lỗi YAMNet: {e}")
        return 'unknown', 0.1, [], [], [], 0.0

def decide_final_class(model_class_code, confidence, has_vulgarity, is_threat, is_emergency):
    is_uncertain = False

    if is_threat:
        final_class = 'threat'
    elif has_vulgarity:
        final_class = 'argument'
    elif is_emergency or model_class_code == 'crying':
        final_class = 'help'
    elif model_class_code == 'dap_pha':
        final_class = 'dap_pha'
    elif model_class_code == 'scream' and confidence >= 0.35:
        final_class = 'scream'
    else:
        # Tiếng nói bình thường hoặc âm thanh an toàn
        final_class = 'normal'

    return final_class, is_uncertain


CRYING_ONOMATOPOEIA_WORDS = {
    'hu', 'huhu', 'hức', 'hic', 'híc', 'oa', 'á', 'ối', 'ơ', 'ư', 'ức',
    'uh', 'um', 'hừ', 'hừm', 'chậc', 'a', 'ha', 'hơ', 'ô', 'ố', 'ơi'
}

def check_has_real_dialogue(text: str, speech_score: float = 0.0, has_threat: bool = False, has_vulgarity: bool = False, has_emergency: bool = False):
    """
    Kiểm tra xem văn bản STT có thực sự là lời thoại (lời nói có ý nghĩa) hay chỉ là tiếng khóc,
    tiếng nấc, tiếng thở, va đập hoặc ảo giác của STT.
    Trả về: (has_real_dialogue: bool, clean_text: str)
    Nếu không có lời thoại, clean_text sẽ là 'Không có lời thoại'.
    """
    if not text or not text.strip():
        return False, "Không có lời thoại"
        
    cleaned = text.strip()
    if cleaned.lower() in ["không có lời thoại", "khong co loi thoai"]:
        return False, "Không có lời thoại"

    # Chuẩn hóa loại bỏ dấu câu để đếm từ
    words = [re.sub(r'[^\w]', '', w.lower()) for w in cleaned.split()]
    words = [w for w in words if w]
    
    if not words:
        return False, "Không có lời thoại"

    # Lọc các từ không phải là từ tượng thanh tiếng khóc
    meaningful_words = [w for w in words if w not in CRYING_ONOMATOPOEIA_WORDS]

    # 1. Nếu toàn bộ từ đều là từ tượng thanh khóc lóc (ví dụ: "hu hu", "hức hức", "oa oa")
    if not meaningful_words:
        return False, "Không có lời thoại"

    # 2. Nếu có từ khóa chửi thề, đe dọa hoặc từ ngữ kêu cứu rõ ràng
    if has_threat or has_vulgarity or has_emergency:
        if len(meaningful_words) >= 1 or speech_score >= 0.15:
            return True, cleaned

    # 3. Nếu số từ có nghĩa >= 2, Whisper đã nhận dạng chính xác lời thoại tiếng Việt có nghĩa
    if len(meaningful_words) >= 2:
        return True, cleaned

    # 4. Nếu chỉ có đúng 1 từ đơn lẻ và điểm speech thấp (< 0.20) mà không có từ nguy hiểm -> có thể là âm thanh ảo giác
    if len(meaningful_words) <= 1 and speech_score < 0.20:
        return False, "Không có lời thoại"

    return True, cleaned


@app.route('/predict', methods=['POST'])
def predict():
    data = request.get_json(silent=True) or {}
    filename = data.get('filepath')

    if not filename:
        return jsonify({"error": "Missing filepath parameter"}), 400

    filepath = resolve_safe_path(filename)
    if filepath is None or not os.path.exists(filepath):
        return jsonify({"error": "Invalid filename or not found"}), 404

    try:
        audio = AudioSegment.from_file(filepath)
        predicted_class, confidence, cry_timestamps, scream_timestamps, impact_timestamps, speech_score = classify_audio(audio)

        transcript, whisper_words, segments, confidence_stt = transcribe_auto(
            whisper_model, audio, vad_filter=True
        )

        censored_audio, censored_transcript, beep_intervals = censor_audio_and_text(
            audio, transcript, whisper_words, profanity_list=PROFANITY_WORDS
        )

        # Ghi đè file audio bằng phiên bản đã đè tiếng bíp nếu phát hiện chửi thề
        if beep_intervals:
            try:
                save_censored_audio(censored_audio, filepath)
            except Exception as censor_err:
                print(f"Censoring Export Error: {censor_err}")

        has_vulgarity, is_threat, is_emergency = analyze_transcript(transcript)
        if not has_vulgarity and beep_intervals:
            has_vulgarity = True

        final_class, is_uncertain = decide_final_class(
            predicted_class, confidence, has_vulgarity, is_threat, is_emergency
        )

        # Xử lý quy tắc: Nếu là đập phá hoặc tiếng khóc mà không có lời thoại
        has_dialogue, final_transcript = check_has_real_dialogue(
            censored_transcript,
            speech_score=speech_score,
            has_threat=is_threat,
            has_vulgarity=has_vulgarity,
            has_emergency=is_emergency
        )
        if final_class in ['dap_pha', 'help', 'scream'] or predicted_class in ['dap_pha', 'crying', 'impact']:
            if not has_dialogue:
                final_transcript = "Không có lời thoại"
                has_vulgarity = False
                has_threat = False
                has_emergency = False

        return jsonify({
            "status": "success",
            "soundType": final_class,
            "confidence": round(confidence * 100, 2),
            "is_uncertain": is_uncertain,
            "has_vulgarity": has_vulgarity,
            "is_threat": is_threat,
            "is_emergency": is_emergency,
            "transcript": final_transcript
        })
    except Exception as e:
        import traceback
        return jsonify({"error": str(e) + "\n" + traceback.format_exc()}), 500


@app.route('/analyze-dialog', methods=['POST'])
def analyze_dialog():
    data = request.get_json(silent=True) or {}
    filename = data.get('filepath')

    if not filename:
        return jsonify({"error": "Missing filepath parameter"}), 400

    filepath = resolve_safe_path(filename)
    if filepath is None or not os.path.exists(filepath):
        return jsonify({"error": "File not found or invalid path"}), 404

    try:
        audio = AudioSegment.from_file(filepath)
        total_duration_ms = len(audio)

        # Lọc yên tĩnh / nhiễu nền: Nếu âm thanh quá nhỏ (< -38 dBFS hoặc peak < 300), bỏ qua ngay
        if audio.dBFS < -38.0 or audio.max < 300:
            return jsonify({
                "dialogue": [],
                "violence_probability": 0,
                "has_scream": False,
                "has_crying": False,
                "has_impact": False,
                "threats_count": 0,
                "vulgarity_count": 0,
                "emergency_count": 0,
                "no_dialogue": True,
                "dialogue_text": "Không có lời thoại",
                "status_label": "Khoảng im lặng / An toàn"
            })

        predicted_class, conf, cry_timestamps, scream_timestamps, impact_timestamps, speech_score = classify_audio(audio)
        has_scream = (predicted_class == 'scream') or (len(scream_timestamps) >= 2 and conf >= 0.40)
        has_crying = (predicted_class == 'crying') or (len(cry_timestamps) >= 2 and conf >= 0.35)
        has_impact = (predicted_class in ['dap_pha', 'impact'] and conf >= 0.55 and not has_crying) or (len(impact_timestamps) >= 2 and conf >= 0.60 and not has_crying)

        transcript, whisper_words, segments, confidence_stt = transcribe_auto(
            whisper_model, audio, vad_filter=True
        )

        censored_audio, censored_transcript, beep_intervals = censor_audio_and_text(
            audio, transcript, whisper_words, profanity_list=PROFANITY_WORDS
        )

        if beep_intervals:
            try:
                save_censored_audio(censored_audio, filepath)
            except Exception as exp_err:
                print(f"Lỗi khi export: {exp_err}")

        dialogue = []
        current_speaker = "Người A"
        last_seg_end = 0.0
        total_threats = 0
        total_vulgarity = 0
        total_emergency = 0

        for seg in segments:
            if last_seg_end > 0 and (seg.start - last_seg_end) > 1.0:
                current_speaker = "Người B" if current_speaker == "Người A" else "Người A"

            _, seg_censored_text, _ = censor_audio_and_text(
                audio[:0], seg.text, getattr(seg, "words", []) or [], profanity_list=PROFANITY_WORDS
            )
            v, t, e = analyze_transcript(seg.text)
            if not v and seg_censored_text != seg.text:
                v = True
            if has_impact and any(w in re.sub(r'[^\w\s]', '', seg.text.lower()).split() for w in ['ơ', 'á', 'ối', 'đau', 'hic', 'ức', 'hu', 'huhu', 'xin', 'tha', 'lạy']):
                e = True
            if v: total_vulgarity += 1
            if t: total_threats += 1
            if e: total_emergency += 1

            dialogue.append({
                "speaker": current_speaker,
                "text": seg_censored_text,
                "timestamp_s": round(seg.start, 1),
                "start_time": round(seg.start, 1),
                "end_time": round(seg.end, 1),
                "has_vulgarity": v,
                "is_threat": t,
                "is_emergency": e,
            })
            last_seg_end = seg.end

        # Kiểm tra xem có lời thoại thực sự hay không
        all_raw_text = " ".join([d.get("text", "") for d in dialogue]).strip()
        has_dialogue, _ = check_has_real_dialogue(
            all_raw_text,
            speech_score=speech_score,
            has_threat=total_threats > 0,
            has_vulgarity=total_vulgarity > 0,
            has_emergency=total_emergency > 0
        )

        # Nếu là tiếng khóc hoặc đập phá mà không có lời thoại
        if (has_crying or has_impact or predicted_class in ['crying', 'dap_pha', 'impact']) and not has_dialogue:
            dialogue = []
            total_threats = 0
            total_vulgarity = 0
            total_emergency = 0

        # Tính toán xác suất bạo lực (bắt đầu từ 0%, chỉ tăng khi có từ ngữ/âm thanh nguy hiểm thật)
        probability = 0
        if has_scream: probability += 35
        if has_crying: probability += 35
        if has_impact: probability += 35
        if total_emergency > 0: probability += 40 + (min(total_emergency, 3) * 5)
        if total_threats > 0: probability += 30 + (min(total_threats, 3) * 5)
        if total_vulgarity > 0: probability += 25 + (min(total_vulgarity, 3) * 5)

        probability = min(probability, 99)
        if not (has_scream or has_crying or has_impact or total_threats > 0 or total_vulgarity > 0 or total_emergency > 0):
            probability = 0

        dialog_result = {
            "dialogue": dialogue,
            "violence_probability": probability,
            "has_scream": has_scream,
            "has_crying": has_crying,
            "has_impact": has_impact,
            "threats_count": total_threats,
            "vulgarity_count": total_vulgarity,
            "emergency_count": total_emergency,
            "no_dialogue": not has_dialogue,
            "dialogue_text": "Không có lời thoại" if not has_dialogue else all_raw_text
        }
        return jsonify(dialog_result)

    except Exception as e:
        import traceback
        return jsonify({"error": str(e) + "\n" + traceback.format_exc()}), 500


def extract_incident_alerts(censored_audio, total_duration_ms, dialogue, whisper_words,
                            has_scream, scream_timestamps,
                            has_crying, cry_timestamps,
                            has_impact, impact_timestamps,
                            beep_intervals, overall_prob):
    alerts_found = []
    total_dur_s = total_duration_ms / 1000.0

    # 1. Thu thập tất cả các mốc thời gian nguy hiểm thực sự
    danger_events = []

    # Đối thoại nguy hiểm (đe dọa, chửi thề, khẩn cấp)
    for d in (dialogue or []):
        if d.get('is_threat'):
            danger_events.append((d['start_time'], d['end_time'], 'threat', d.get('text', '')))
        elif d.get('is_emergency'):
            danger_events.append((d['start_time'], d['end_time'], 'help', d.get('text', '')))
        elif d.get('has_vulgarity'):
            danger_events.append((d['start_time'], d['end_time'], 'argument', d.get('text', '')))

    # Các đoạn đã bị đè tiếng bíp do chửi thề
    for s_ms, e_ms in (beep_intervals or []):
        s_sec = s_ms / 1000.0
        e_sec = e_ms / 1000.0
        danger_events.append((s_sec, e_sec, 'argument', ''))

    # Sự kiện âm thanh gào thét
    if has_scream and scream_timestamps:
        for t in scream_timestamps:
            danger_events.append((max(0.0, t - 1.0), min(total_dur_s, t + 2.0), 'scream', ''))

    # Sự kiện âm thanh khóc lóc
    if has_crying and cry_timestamps:
        for t in cry_timestamps:
            danger_events.append((max(0.0, t - 1.0), min(total_dur_s, t + 2.0), 'help', ''))

    # Sự kiện âm thanh đập phá
    if has_impact and impact_timestamps:
        for t in impact_timestamps:
            danger_events.append((max(0.0, t - 0.5), min(total_dur_s, t + 2.0), 'dap_pha', ''))

    if not danger_events:
        return []

    # 2. Hợp nhất các sự kiện gần nhau thành các cửa sổ cảnh báo thông minh (tối đa 10s-12s)
    # Nếu file <= 12s, giữ nguyên 1 cửa sổ duy nhất bao trọn file
    if total_dur_s <= 12.0:
        candidate_windows = [(0.0, total_dur_s)]
    else:
        # Sắp xếp các sự kiện theo thời gian bắt đầu
        danger_events.sort(key=lambda x: x[0])
        clusters = []
        current_cluster = [danger_events[0]]

        for ev in danger_events[1:]:
            prev_end = max(e[1] for e in current_cluster)
            new_dur = max(prev_end, ev[1]) - min(e[0] for e in current_cluster)
            # Nếu sự kiện tiếp theo cách cluster hiện tại <= 3.0s và tổng thời gian <= 10.0s
            if (ev[0] - prev_end <= 3.0) and new_dur <= 10.0:
                current_cluster.append(ev)
            else:
                clusters.append(current_cluster)
                current_cluster = [ev]
        if current_cluster:
            clusters.append(current_cluster)

        candidate_windows = []
        for c in clusters:
            c_start = min(e[0] for e in c)
            c_end = max(e[1] for e in c)
            # Thêm đệm ngữ cảnh 1.0s trước và sau
            w_start = max(0.0, c_start - 1.0)
            w_end = min(total_dur_s, c_end + 1.0)
            # Đảm bảo độ dài tối thiểu 4s để người nghe nghe rõ
            if (w_end - w_start) < 4.0:
                pad = (4.0 - (w_end - w_start)) / 2.0
                w_start = max(0.0, w_start - pad)
                w_end = min(total_dur_s, w_end + pad)
            # Giới hạn tối đa 10.0s
            if (w_end - w_start) > 10.0:
                w_end = min(total_dur_s, w_start + 10.0)

            # Tránh trùng lặp với window trước đó
            if candidate_windows:
                last_w = candidate_windows[-1]
                if w_start < last_w[1] - 1.0:
                    if (w_end - last_w[0]) <= 10.0:
                        candidate_windows[-1] = (last_w[0], max(last_w[1], w_end))
                        continue
                    else:
                        w_start = last_w[1]

            if w_end > w_start:
                candidate_windows.append((w_start, w_end))

    # 3. Phân tích nội dung và trích xuất clip cho từng cửa sổ
    for win_start, win_end in candidate_windows:
        win_start_s = round(win_start, 1)
        win_end_s = round(win_end, 1)
        if win_end_s <= win_start_s:
            continue

        # Cắt file audio
        start_ms = int(win_start_s * 1000)
        end_ms = int(win_end_s * 1000)
        snippet = censored_audio[start_ms:end_ms]

        alert_filename = f"alert_10s_{uuid.uuid4().hex[:8]}.wav"
        alert_filepath = os.path.join(UPLOAD_DIR, alert_filename)
        try:
            snippet.export(alert_filepath, format="wav")
        except Exception as err:
            print(f"Lỗi export audio snippet: {err}")

        # Lấy lời thoại CỤ THỂ của riêng đoạn cắt này
        local_words = [
            getattr(w, 'word', '').strip()
            for w in (whisper_words or [])
            if (win_start_s - 0.2 <= getattr(w, 'start', 0.0) <= win_end_s + 0.2)
            or (win_start_s - 0.2 <= getattr(w, 'end', 0.0) <= win_end_s + 0.2)
        ]
        local_words = [w for w in local_words if w]

        if local_words:
            raw_text = " ".join(local_words)
            raw_text = unicodedata.normalize("NFC", raw_text)
            for p in PROFANITY_WORDS:
                if p and p.strip():
                    raw_text = re.sub(r"(?i)(?<!\w)" + re.escape(p.strip()) + r"(?!\w)", "***", raw_text)
        else:
            overlapping_d = [
                d['text'] for d in (dialogue or [])
                if max(win_start_s, d['start_time']) < min(win_end_s, d['end_time'])
            ]
            raw_text = " ".join(overlapping_d) if overlapping_d else ""

        # Kiểm tra xem đoạn cắt này có lời thoại hay không
        b_has_dialogue, b_text = check_has_real_dialogue(raw_text)
        local_text = b_text if b_has_dialogue else "Không có lời thoại"

        # Đánh giá các nhãn nguy cơ CỤC BỘ cho riêng đoạn này
        local_threat = any(contains_word(local_text.lower(), p) for p in THREAT_PHRASES) or any(
            d.get('is_threat') for d in (dialogue or []) if max(win_start_s, d['start_time']) < min(win_end_s, d['end_time'])
        )
        local_vulgarity = any(contains_word(local_text.lower(), p) for p in PROFANITY_WORDS) or ('***' in local_text) or any(
            d.get('has_vulgarity') for d in (dialogue or []) if max(win_start_s, d['start_time']) < min(win_end_s, d['end_time'])
        ) or any(win_start_s <= (s / 1000.0) <= win_end_s for s, _ in (beep_intervals or []))

        local_emergency = any(contains_word(local_text.lower(), p) for p in EMERGENCY_WORDS) or any(
            d.get('is_emergency') for d in (dialogue or []) if max(win_start_s, d['start_time']) < min(win_end_s, d['end_time'])
        )
        local_scream = has_scream and any(win_start_s <= t <= win_end_s for t in (scream_timestamps or []))
        local_crying = has_crying and any(win_start_s <= t <= win_end_s for t in (cry_timestamps or []))
        local_impact = has_impact and any(win_start_s <= t <= win_end_s for t in (impact_timestamps or []))

        # Nếu có va đập / đánh đập (cú tát, cú đánh) kết hợp với tiếng rên đau đớn ("ơ", "á", "ối", "đau") hoặc lời van xin:
        # -> ĐÂY LÀ HÀNH VI ĐÁNH ĐẬP BẠO LỰC / NẠN NHÂN KÊU CỨU -> Ưu tiên chuyển thành 'help' (Kêu cứu / Van xin)!
        groan_pain = any(w in re.sub(r'[^\w\s]', '', local_text.lower()).split() for w in ['ơ', 'á', 'ối', 'đau', 'hic', 'ức', 'hu', 'huhu', 'xin', 'tha', 'lạy'])
        if local_impact and (groan_pain or local_emergency or 'đau' in local_text.lower()):
            local_emergency = True

        # Quyết định soundType cho riêng đoạn này
        # ƯU TIÊN 1: Đe dọa bạo lực
        if local_threat:
            local_type = 'threat'
        # ƯU TIÊN 2: Khóc lóc / Kêu cứu
        elif local_crying or local_emergency:
            local_type = 'help'
        # ƯU TIÊN 3: La hét
        elif local_scream:
            local_type = 'scream'
        # ƯU TIÊN 4: Đập phá
        elif local_impact:
            local_type = 'dap_pha'
        # ƯU TIÊN 5: Chửi bới / Cãi vã
        elif local_vulgarity:
            local_type = 'argument'
        else:
            # Không có bất kỳ nguy cơ nào trong đoạn này -> BỎ QUA, không tạo cảnh báo giả!
            continue

        if (local_type in ['dap_pha', 'help']) and not b_has_dialogue:
            local_text = "Không có lời thoại"

        # Tính toán độ tin cậy cục bộ
        local_conf = 80.0
        if local_type == 'threat': local_conf = 90.0 + (5.0 if local_vulgarity else 0.0)
        elif local_type == 'help': local_conf = 85.0 + (5.0 if local_emergency else 0.0)
        elif local_type == 'scream': local_conf = 85.0
        elif local_type == 'dap_pha': local_conf = 80.0
        elif local_type == 'argument': local_conf = 85.0

        alerts_found.append({
            "start_time_seconds": win_start_s,
            "end_time_seconds": win_end_s,
            "filename": alert_filename,
            "soundType": local_type,
            "confidence": round(local_conf, 1),
            "transcript": local_text.strip(),
            "has_vulgarity": local_vulgarity,
            "is_threat": local_threat,
            "is_emergency": local_emergency,
            "has_crying": local_crying,
            "has_scream": local_scream,
            "has_impact": local_impact
        })

    return alerts_found


@app.route('/analyze-full', methods=['POST'])
def analyze_full():
    data = request.get_json(silent=True) or {}
    filename = data.get('filepath')

    if not filename:
        return jsonify({"error": "Missing filepath parameter"}), 400

    filepath = resolve_safe_path(filename)
    if filepath is None or not os.path.exists(filepath):
        return jsonify({"error": "File not found or invalid path"}), 404

    try:
        audio = AudioSegment.from_file(filepath)
        total_duration_ms = len(audio)

        # Lọc yên tĩnh / nhiễu nền: Nếu âm thanh quá nhỏ (< -38 dBFS hoặc peak < 300), bỏ qua ngay
        if audio.dBFS < -38.0 or audio.max < 300:
            return jsonify({
                "dialog_data": {
                    "dialogue": [],
                    "violence_probability": 0,
                    "has_scream": False,
                    "has_crying": False,
                    "has_impact": False,
                    "threats_count": 0,
                    "vulgarity_count": 0,
                    "emergency_count": 0,
                    "no_dialogue": True,
                    "dialogue_text": "Không có lời thoại",
                    "status_label": "Khoảng im lặng / An toàn"
                },
                "alerts": [],
                "transcript": "Không có lời thoại",
                "censored_transcript": "Không có lời thoại",
                "audio_url": f"/uploads/{filename}",
                "total_duration_seconds": round(total_duration_ms / 1000.0, 1),
                "is_uncertain": False
            })

        # 1. Nhận diện sự kiện âm thanh bằng YAMNet (ngưỡng chuẩn xác, ưu tiên tiếng khóc)
        predicted_class, conf, cry_timestamps, scream_timestamps, impact_timestamps, speech_score = classify_audio(audio)
        has_scream = (predicted_class == 'scream') or (len(scream_timestamps) >= 2 and conf >= 0.40)
        has_crying = (predicted_class == 'crying') or (len(cry_timestamps) >= 2 and conf >= 0.35)
        has_impact = (predicted_class in ['dap_pha', 'impact'] and conf >= 0.55 and not has_crying) or (len(impact_timestamps) >= 2 and conf >= 0.60 and not has_crying)

        # 2. Nhận diện giọng nói tiếng Việt (Groq API nếu có key, fallback Whisper local)
        transcript, whisper_words, segments, confidence_stt = transcribe_auto(
            whisper_model, audio, vad_filter=True
        )

        # 3. Kiểm duyệt âm thanh (đè tiếng bíp 1000Hz) & văn bản (thay bằng ***)
        censored_audio, censored_transcript, beep_intervals = censor_audio_and_text(
            audio, transcript, whisper_words, profanity_list=PROFANITY_WORDS
        )

        # Ghi đè file audio gốc trong tai-lieu bằng phiên bản đã chèn tiếng bíp
        if beep_intervals:
            try:
                save_censored_audio(censored_audio, filepath)
            except Exception as exp_err:
                print(f"Lỗi khi ghi đè file audio đã kiểm duyệt: {exp_err}")

        # 4. Phân tích đối thoại theo từng câu & người nói
        dialogue = []
        current_speaker = "Người A"
        last_seg_end = 0.0
        total_threats = 0
        total_vulgarity = 0
        total_emergency = 0

        for seg in segments:
            if last_seg_end > 0 and (seg.start - last_seg_end) > 1.0:
                current_speaker = "Người B" if current_speaker == "Người A" else "Người A"

            _, seg_censored_text, _ = censor_audio_and_text(
                audio[:0], seg.text, getattr(seg, "words", []) or [], profanity_list=PROFANITY_WORDS
            )
            v, t, e = analyze_transcript(seg.text)
            if not v and seg_censored_text != seg.text:
                v = True
            if has_impact and any(w in re.sub(r'[^\w\s]', '', seg.text.lower()).split() for w in ['ơ', 'á', 'ối', 'đau', 'hic', 'ức', 'hu', 'huhu', 'xin', 'tha', 'lạy']):
                e = True
            if v: total_vulgarity += 1
            if t: total_threats += 1
            if e: total_emergency += 1

            dialogue.append({
                "speaker": current_speaker,
                "text": seg_censored_text,
                "timestamp_s": round(seg.start, 1),
                "start_time": round(seg.start, 1),
                "end_time": round(seg.end, 1),
                "has_vulgarity": v,
                "is_threat": t,
                "is_emergency": e,
            })
            last_seg_end = seg.end

        # Kiểm tra xem có lời thoại thực sự hay không
        all_raw_text = " ".join([d.get("text", "") for d in dialogue]).strip()
        has_dialogue, _ = check_has_real_dialogue(
            all_raw_text,
            speech_score=speech_score,
            has_threat=total_threats > 0,
            has_vulgarity=total_vulgarity > 0,
            has_emergency=total_emergency > 0
        )

        # Nếu là tiếng khóc hoặc đập phá mà không có lời thoại
        if (has_crying or has_impact or predicted_class in ['crying', 'dap_pha', 'impact']) and not has_dialogue:
            dialogue = []
            total_threats = 0
            total_vulgarity = 0
            total_emergency = 0

        # Tính toán xác suất bạo lực: Bắt đầu từ 0%, chỉ tăng khi có bằng chứng thực tế
        probability = 0 
        if has_scream: probability += 35
        if has_crying: probability += 35
        if has_impact: probability += 35
        if total_emergency > 0: probability += 40 + (min(total_emergency, 3) * 5)
        if total_threats > 0: probability += 30 + (min(total_threats, 3) * 5)
        if total_vulgarity > 0: probability += 25 + (min(total_vulgarity, 3) * 5)
            
        probability = min(probability, 99)
        if not (has_scream or has_crying or has_impact or total_threats > 0 or total_vulgarity > 0 or total_emergency > 0):
            probability = 0
            
        dialog_result = {
            "dialogue": dialogue,
            "violence_probability": probability,
            "has_scream": has_scream,
            "has_crying": has_crying,
            "has_impact": has_impact,
            "threats_count": total_threats,
            "vulgarity_count": total_vulgarity,
            "emergency_count": total_emergency,
            "no_dialogue": not has_dialogue,
            "dialogue_text": "Không có lời thoại" if not has_dialogue else all_raw_text,
            "status_label": "Nói chuyện bình thường (An toàn)" if (has_dialogue and probability == 0) else ("Không có lời thoại" if not has_dialogue else "Cảnh báo nguy cơ")
        }

        # 5. Xuất các đoạn clip cảnh báo thông minh theo từng sự kiện nguy hiểm (tối đa 10s-12s/clip)
        alerts_found = extract_incident_alerts(
            censored_audio=censored_audio,
            total_duration_ms=total_duration_ms,
            dialogue=dialogue,
            whisper_words=whisper_words,
            has_scream=has_scream,
            scream_timestamps=scream_timestamps,
            has_crying=has_crying,
            cry_timestamps=cry_timestamps,
            has_impact=has_impact,
            impact_timestamps=impact_timestamps,
            beep_intervals=beep_intervals,
            overall_prob=probability
        )
            
        return jsonify({
            "status": "success",
            "total_duration_seconds": total_duration_ms // 1000,
            "alerts_count": len(alerts_found),
            "alerts": alerts_found,
            "dialog_data": dialog_result
        })

    except Exception as e:
        import traceback
        return jsonify({"error": str(e) + "\n" + traceback.format_exc()}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)