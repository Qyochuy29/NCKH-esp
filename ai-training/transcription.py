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
    "tự nhiên",
)

# Prompt ngắn gọn, chỉ cung cấp ngữ cảnh trường học — KHÔNG liệt kê từ vựng cụ thể
# vì liệt kê từ ngữ vào prompt khiến Whisper "ảo giác" copy lại đúng những từ đó vào kết quả!
VIETNAMESE_PROMPT = "Cuộc trò chuyện tại trường học Việt Nam, học sinh nói chuyện với nhau, tiếng Việt khẩu ngữ tự nhiên."

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

PHONETIC_WORD_MAP = {
    'lôn': 'lồn',
    'lồz': 'lồn',
    'loz': 'lồn',
    'đit': 'địt',
    'đjt': 'địt',
    'dit': 'địt',
    'djt': 'địt',
    'mịt': 'địt',
    'mít': 'địt',
    'buoi': 'buồi',
    'bùi': 'buồi',
    'buôi': 'buồi',
    'buổi': 'buồi',
    'bổi': 'buồi',
    'kặc': 'cặc',
    'cac': 'cặc',
    'cặt': 'cặc',
    'mồn': 'mồm',
    'nhợn': 'nhờn',
    'nhớt': 'nhờn',
    'bỡi': 'vỡ',
}

PHONETIC_REGEX_FIXES = [
    # =====================================================================
    # NHÓM 1: TỪ TỤC / CHỬI BỚI - Sửa lỗi nhầm âm phổ biến
    # =====================================================================
    (r'(?i)\b(cái\s+)?mịt\s+con\s+mẹ\b', r'\1địt con mẹ'),
    (r'(?i)\bmịt\s+mẹ\b', 'địt mẹ'),
    (r'(?i)\bmịt\s+cụ\b', 'địt cụ'),
    (r'(?i)\bmình\s+còn\s+mẹ\s+à\s+mày\b', 'địt con mẹ mày'),
    (r'(?i)\bđit\b', 'địt'),
    (r'(?i)\bđjt\b', 'địt'),
    (r'(?i)\btuổi\s+lôn\s+(xánh|xảnh|sánh)\s+(mày|bay|vai)\b', 'tuổi lồn sánh vai'),
    (r'(?i)\btuổi\s+lôn\b', 'tuổi lồn'),
    (r'(?i)\bmặt\s+lôn\b', 'mặt lồn'),
    (r'(?i)\bhãm\s+lôn\b', 'hãm lồn'),
    (r'(?i)\bláo\s+lôn\b', 'láo lồn'),
    (r'(?i)\bcon\s+lôn\b', 'con lồn'),
    (r'(?i)\bthằng\s+lôn\b', 'thằng lồn'),
    (r'(?i)\bbố\s+mày\s+(nhợn|nhớt|nhận)\s+với\s+mày\b', 'bố mày nhờn với mày'),
    (r'(?i)\bnhợn\s+với\s+(tao|bố)\b', r'nhờn với \1'),
    (r'(?i)\b(đồ|con|loại|phật)\s+su\s+vật\b', r'đồ súc vật'),
    (r'(?i)\b(một|mùa)\s+xíu\s+vật\b', 'đồ súc vật'),
    (r'(?i)\btao\s+(lại|lạy)\s+(máy|mậy)\b', 'tao lạy mày'),
    (r'(?i)\bđánh\s+bỡi\b', 'đánh vỡ mồm'),
    (r'(?i)\bcầm\s+mẹ\s+cái\s+mồn\b', 'câm mẹ cái mồm'),
    (r'(?i)\bvới\s+mồn\s+mày\b', 'vỡ mồm mày'),
    (r'(?i)\bvới\s+mồm\s+mày\b', 'vỡ mồm mày'),
    (r'(?i)\bcận\s+dịch\b', 'cần cặc'),
    (r'(?i)\bđau\s+bùi\b', 'đầu buồi'),
    (r'(?i)\blắm\s+bùi\b', 'lắm buồi'),
    (r'(?i)\bbuổi\s+(nha|lắm|như|mày)\b', r'buồi \1'),
    (r'(?i)\bcủa\s+tổ\s+này\b', 'cả lò nhà mày'),
    (r'(?i)\btrao\s+hỏi\b', 'chào hỏi'),
    (r'(?i)\bcần\s+(dịnh|dịch)\b', 'cần cặc'),
    (r'(?i)\bđịt\s+con\s+(mê|mẹ\s+mà)\b', 'địt con mẹ'),

    # =====================================================================
    # NHÓM 2: ĐE DỌA / BẮT NẠT HỌC ĐƯỜNG - Whisper nghe nhầm
    # =====================================================================
    # "đánh mày / đập mày" - Whisper hay nghe thành "anh mày", "đạn mày"
    (r'(?i)\banh\s+mày\b(?!\s+ơi)', 'đánh mày'),          # "anh mày" → "đánh mày" (trừ "anh mày ơi")
    (r'(?i)\bđạn\s+mày\b', 'đánh mày'),
    (r'(?i)\băn\s+đây\s+chưa\b', 'ăn đấm chưa'),
    (r'(?i)\băn\s+đây\s+không\b', 'ăn đấm không'),
    (r'(?i)\băn\s+đầm\b', 'ăn đấm'),
    # "bắt nạt" - phổ biến trong học đường
    (r'(?i)\bbắc\s+nạt\b', 'bắt nạt'),
    (r'(?i)\bbắt\s+nhạt\b', 'bắt nạt'),
    (r'(?i)\bbắt\s+nặt\b', 'bắt nạt'),
    # "tao còn chưa sợ" / "tao không sợ mày"
    (r'(?i)\btao\s+con\s+chưa\s+sợ\b', 'tao còn chưa sợ'),
    (r'(?i)\btao\s+không\s+sợ\s+(mày|bay)\b', 'tao không sợ mày'),
    # "ngon thì ra đây"
    (r'(?i)\bngon\s+thì\s+ra\s+đây\b', 'ngon thì ra đây'),
    (r'(?i)\bngon\s+(thì|thời)\s+nhào\s+vô\b', 'ngon thì nhào vô'),
    (r'(?i)\bngon\s+không\s+(thì|thời)\b', 'ngon không thì'),
    # "xem mày làm được gì"
    (r'(?i)\bxem\s+(mày|bay)\s+làm\s+được\s+gì\b', 'xem mày làm được gì'),
    # "mày tưởng mày ngon"
    (r'(?i)\b(mày|bay)\s+tưởng\s+(mày|bay)\s+ngon\b', 'mày tưởng mày ngon'),
    # "liệu hồn" / "coi chừng"
    (r'(?i)\bliệu\s+hồng\b', 'liệu hồn'),
    (r''r'(?i)\bcoi\s+chừn\b', 'coi chừng'),

    # =====================================================================
    # NHÓM 3: VAN XIN / KÊU CỨU - Whisper nghe nhầm
    # =====================================================================
    (r'(?i)\btha\s+cho\s+(em|anh|chị|con|cháu|mình|tôi|tao)\s+đi\b', r'tha cho \1 đi'),
    (r'(?i)\btha\s+cho\s+(em|anh|chị|con|cháu|mình|tôi|tao)\s+lần\s+này\b', r'tha cho \1 lần này'),
    # "em xin" hay bị nghe thành "anh xin" hoặc "em sin"
    (r'(?i)\bem\s+sin\b', 'em xin'),
    (r'(?i)\bem\s+xin\s+(anh|chị)\s+đó\b', r'em xin \1 đó'),
    # "đừng đánh em" hay bị Whisper nói thành "đừng đánh em ơi" hoặc "đừng đần em"
    (r'(?i)\bđừng\s+đần\s+(em|con|mình)\b', r'đừng đánh \1'),
    (r'(?i)\bđừng\s+đâm\s+(em|con|mình)\b', r'đừng đánh \1'),
    # "em đau rồi / em đau lắm"
    (r'(?i)\bem\s+đao\s+rồi\b', 'em đau rồi'),
    (r'(?i)\bem\s+đao\s+lắm\b', 'em đau lắm'),
    (r'(?i)\bem\s+đao\s+quá\b', 'em đau quá'),
    (r'(?i)\bem\s+đao\b', 'em đau'),
    # "cứu tôi với / cứu em với"
    (r'(?i)\bcứu\s+(tôi|em|con|cháu)\s+với\b', r'cứu \1 với'),
    (r'(?i)\bcứu\s+(tôi|em|con|cháu)\s+vời\b', r'cứu \1 với'),

    # =====================================================================
    # NHÓM 4: TỪ TRƯỜNG HỌC - Whisper hay nhầm
    # =====================================================================
    # Số lớp học - Whisper dùng chữ số chữ thay vì số
    (r'(?i)\blớm\s+mở\b', 'từ lớp'),              # "lớm mở" → "từ lớp" (lỗi phổ biến nhất)
    (r'(?i)\blớm\s+một\b', 'lớp 1'),
    (r'(?i)\blớm\s+hai\b', 'lớp 2'),
    (r'(?i)\blớm\s+ba\b', 'lớp 3'),
    (r'(?i)\blớm\s+bốn\b', 'lớp 4'),
    (r'(?i)\blớm\s+năm\b', 'lớp 5'),
    (r'(?i)\blớp\s+một\b', 'lớp 1'),
    (r'(?i)\blớp\s+hai\b', 'lớp 2'),
    (r'(?i)\blớp\s+ba\b', 'lớp 3'),
    (r'(?i)\blớp\s+bốn\b', 'lớp 4'),
    (r'(?i)\blớp\s+năm\b', 'lớp 5'),
    (r'(?i)\blớp\s+sáu\b', 'lớp 6'),
    (r'(?i)\blớp\s+bảy\b', 'lớp 7'),
    (r'(?i)\blớp\s+tám\b', 'lớp 8'),
    (r'(?i)\blớp\s+chín\b', 'lớp 9'),
    (r'(?i)\blớp\s+mười\s+một\b', 'lớp 11'),      # 11 trước 10 để tránh match nhầm
    (r'(?i)\blớp\s+mười\s+hai\b', 'lớp 12'),
    (r'(?i)\blớp\s+mười\b', 'lớp 10'),
    # "thầy / cô / hiệu trưởng"
    (r'(?i)\bthầy\s+giáo\b', 'thầy giáo'),
    (r'(?i)\bcô\s+giáo\b', 'cô giáo'),
    (r'(?i)\bhiệu\s+trưởng\b', 'hiệu trưởng'),
    (r'(?i)\bhiệu\s+trường\b', 'hiệu trưởng'),     # Whisper hay nói "trường" thay "trưởng"
    (r'(?i)\bgiám\s+thị\b', 'giám thị'),
    (r'(?i)\bgiám\s+thi\b', 'giám thị'),
    # "chơi nhau" vs "chửi nhau" vs "đánh nhau"
    (r'(?i)\bchơi\s+nhau\s+không\b', 'đánh nhau không'),  # trong ngữ cảnh học đường
    # Tên các môn học (Whisper hay sai)
    (r'(?i)\btoán\s+học\b', 'toán học'),
    (r'(?i)\bvăn\s+học\b', 'văn học'),

    # =====================================================================
    # NHÓM 5: KHẨU NGỮ MIỀN NAM / MIỀN BẮC - Whisper hay nhầm lẫn
    # =====================================================================
    # "mày" hay bị nghe thành "bay", "máy", "mày"
    (r'(?i)\b(tao|tôi)\s+bay\b(?!\s+\w)', r'\1 mày'),    # "tao bay" → "tao mày" (không phải "bay đi")
    # "tao" hay bị nghe thành "dao", "đao", "thao"
    (r'(?i)\bđao\s+(đây|không|mà|thôi|nhé|nha)\b', r'tao \1'),
    (r'(?i)\bthao\s+(đây|không|mà|thôi|nhé|nha|ơi)\b', r'tao \1'),
    # "nó" hay bị nghe thành "ngó", "no"
    (r'(?i)\bngó\s+(không|đó|đây|kia|đánh|chạy)\b', r'nó \1'),
    # Tiếng miền Nam: "vậy" → Whisper hay nghe thành "vậy", "bậy"
    (r'(?i)\bbậy\s+là\b', 'vậy là'),
    (r'(?i)\bsao\s+bậy\b', 'sao vậy'),
    (r'(?i)\bchứ\s+bộ\b', 'chứ bộ'),             # Khẩu ngữ Nam: "chứ bộ" = "chứ gì nữa"
    # "ông/bà nội" = cách xưng hô thách thức ở miền Nam
    (r'(?i)\bông\s+nội\s+(mày|bay)\b', 'ông nội mày'),
    (r'(?i)\bbà\s+nội\s+(mày|bay)\b', 'bà nội mày'),

    # =====================================================================
    # NHÓM 6: LỖI NHỎ THƯỜNG GẶP CỦA WHISPER SMALL VỚI TIẾNG VIỆT
    # =====================================================================
    # "quay lại" hay bị nghe thành "quai lại", "quây lại"
    (r'(?i)\bquai\s+lại\b', 'quay lại'),
    (r'(?i)\bquây\s+lại\b', 'quay lại'),
    # "ra đây" hay bị nghe thành "ra đấy", "ra đày"
    (r'(?i)\bra\s+đày\b', 'ra đây'),
    # "đứng lại" → "đứn lại"
    (r'(?i)\bđứn\s+lại\b', 'đứng lại'),
    # "chạy đi" → "chạy đy", "chạy đi" (thường đúng)
    (r'(?i)\bchạy\s+đy\b', 'chạy đi'),
    # Tiếng rên / kêu đau - chuẩn hóa
    (r'(?i)\bới\s+ời\b', 'ơi'),
    (r'(?i)\bẩy\s*[!?.]*\s+(?=\bẩy\b)', 'ấy '),  # "ẩy" → "ấy"
    (r'(?i)\bôi\s+dào\b', 'ôi trời'),
    (r'(?i)\btrời\s+đát\b', 'trời đất'),
    (r'(?i)\btrời\s+ơi\s+đất\s+hỡi\b', 'trời ơi đất hỡi'),
    # Xưng hô đặc trưng học đường
    (r'(?i)\bthằng\s+đó\b', 'thằng đó'),
    (r'(?i)\bcon\s+đó\b', 'con đó'),
    # Lỗi dấu hỏi/ngã hay gặp
    (r'(?i)\bthậm\s+chí\b', 'thậm chí'),
    (r'(?i)\bkhỏe\s+không\b', 'khỏe không'),
]



def correct_vietnamese_transcription(text: str) -> str:
    """Correct common Whisper Vietnamese mis-transcriptions for slang and curses."""
    text = unicodedata.normalize("NFC", text or "").strip()
    for pat, rep in PHONETIC_REGEX_FIXES:
        text = re.sub(pat, rep, text)
    return text


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


def transcribe_vietnamese(model, audio_segment: AudioSegment, vad_filter: bool = True):
    """Return (text, accepted words, accepted segments, confidence_percent)."""
    waveform = get_whisper_waveform(audio_segment)
    if waveform.size == 0:
        return "", [], [], 0.0

    # VAD tuned to preserve shouting, swearing, crying, and natural schoolyard dialogue
    vad_params = {
        "threshold": 0.30,
        "min_speech_duration_ms": 150,
        "min_silence_duration_ms": 400,
        "speech_pad_ms": 500,
    }

    def _run_transcribe(use_vad: bool, temperature=0.0):
        return model.transcribe(
            waveform,
            language="vi",
            task="transcribe",
            beam_size=8,             # Tăng từ 5 → 8: tìm kiếm rộng hơn, đặc biệt cho câu ngắn
            best_of=5,
            patience=1.2,
            temperature=temperature,
            word_timestamps=True,
            vad_filter=use_vad,
            vad_parameters=vad_params if use_vad else None,
            condition_on_previous_text=False,
            no_speech_threshold=0.65,    # Tăng nhẹ: bỏ qua đoạn không có giọng nói rõ hơn
            log_prob_threshold=-1.8,     # Chặt hơn: loại bỏ ảo giác có độ tin thấp
            compression_ratio_threshold=2.4,
            repetition_penalty=1.4,      # Tăng mạnh: ngăn vòng lặp "Ấy! Ấy! Ấy!"
            hallucination_silence_threshold=1.5,
            initial_prompt=VIETNAMESE_PROMPT,
        )

    segments_gen, _ = _run_transcribe(vad_filter, temperature=0.0)
    raw_segments = list(segments_gen)

    # Nếu bật vad_filter mà không thu được segment hợp lệ nào (rất phổ biến khi nạn nhân bị đánh đập, khóc nấc, rên rỉ, van xin bị VAD chặn nhầm)
    # -> Fallback ngay lập tức sang chạy không dùng VAD để không bỏ sót tiếng van xin / kêu cứu của nạn nhân!
    if vad_filter and (not raw_segments or not any(_accept_segment(s) for s in raw_segments)):
        segments_gen, _ = _run_transcribe(False, temperature=0.0)
        raw_segments = list(segments_gen)

    # Nếu kết quả có độ tin thấp (avg_logprob < -1.2) → thử lại với temperature=0.2 để decoder thử hướng khác
    all_accepted = [s for s in raw_segments if _accept_segment(s)]
    if all_accepted:
        avg_lp = sum(getattr(s, 'avg_logprob', 0.0) for s in all_accepted) / len(all_accepted)
        if avg_lp < -1.2:
            segments_gen2, _ = _run_transcribe(vad_filter, temperature=0.2)
            raw_segments2 = list(segments_gen2)
            all_accepted2 = [s for s in raw_segments2 if _accept_segment(s)]
            if all_accepted2:
                avg_lp2 = sum(getattr(s, 'avg_logprob', 0.0) for s in all_accepted2) / len(all_accepted2)
                if avg_lp2 > avg_lp + 0.15:  # Chỉ dùng kết quả mới nếu tốt hơn rõ ràng
                    raw_segments = raw_segments2

    accepted_segments = []
    words = []
    texts = []
    probabilities = []
    for segment in raw_segments:
        if not _accept_segment(segment):
            continue

        # Correct phonetic mishearings and deduplicate any decoder latching loops
        corrected_text = correct_vietnamese_transcription(segment.text)
        corrected_text = deduplicate_consecutive_phrases(corrected_text)
        segment.text = corrected_text

        text = _normalized_text(corrected_text)
        texts.append(text)
        accepted_segments.append(segment)

        seg_words = getattr(segment, "words", None) or []
        for w in seg_words:
            w.word = correct_vietnamese_transcription(getattr(w, "word", ""))
        words.extend(seg_words)
        probabilities.append(math.exp(min(0.0, float(segment.avg_logprob))))

    raw_transcript = " ".join(texts).strip()
    transcript = deduplicate_consecutive_phrases(raw_transcript)
    if is_hallucination(transcript):
        return "", [], [], 0.0
    confidence = round(100.0 * sum(probabilities) / len(probabilities), 1) if probabilities else 0.0
    return transcript, words, accepted_segments, confidence


def transcribe_vietnamese_groq(audio_segment: AudioSegment) -> tuple[str, list, list, float]:
    """Bóc băng tiếng Việt bằng Groq API (Whisper large-v3) — chính xác hơn model local.
    
    Trả về (transcript, words, segments_dummy, confidence) — cùng interface với transcribe_vietnamese.
    Nếu không có API key hoặc lỗi mạng → trả về ('', [], [], 0.0) để caller fallback local.
    """
    import io
    import logging
    
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return "", [], [], 0.0

    try:
        from groq import Groq
        client = Groq(api_key=api_key, timeout=15.0)

        # Xuất audio ra bytes WAV để gửi lên API
        buf = io.BytesIO()
        audio_16k = audio_segment.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        audio_16k.export(buf, format="wav")
        buf.seek(0)
        wav_bytes = buf.read()

        result = client.audio.transcriptions.create(
            file=("audio.wav", wav_bytes, "audio/wav"),
            model="whisper-large-v3-turbo",   # Nhanh hơn large-v3 mà vẫn rất chính xác
            language="vi",
            response_format="verbose_json",    # Trả về timestamp + confidence
            timestamp_granularities=["word", "segment"] # Yêu cầu trả về timestamps từng từ
        )

        # Lấy transcript và áp dụng sửa lỗi phonetic giống local
        raw_text = getattr(result, "text", "") or ""
        raw_text = correct_vietnamese_transcription(raw_text)
        raw_text = deduplicate_consecutive_phrases(raw_text)
        transcript = _normalized_text(raw_text)

        # Groq trả về segments với timestamps
        groq_segments = getattr(result, "segments", []) or []
        confidence = 0.0
        if groq_segments:
            # avg_logprob không có trong Groq response → dùng 0.85 mặc định (large-v3 rất tốt)
            confidence = 85.0

        # Tạo dummy segments để tương thích với code hiện tại
        class _DummySeg:
            def __init__(self, s):
                if isinstance(s, dict):
                    self.start = float(s.get("start", 0.0))
                    self.end = float(s.get("end", 0.0))
                    text_val = s.get("text", "")
                else:
                    self.start = float(getattr(s, "start", 0.0))
                    self.end = float(getattr(s, "end", 0.0))
                    text_val = getattr(s, "text", "")
                
                self.text = correct_vietnamese_transcription(text_val)
                self.avg_logprob = -0.2   # Groq/large-v3 rất tự tin
                self.no_speech_prob = 0.05
                self.words = []

        dummy_segs = []
        for s in groq_segments:
            text_val = s.get("text", "") if isinstance(s, dict) else getattr(s, "text", "")
            if text_val.strip():
                dummy_segs.append(_DummySeg(s))

        # Lấy mảng words để gán vào whisper_words phục vụ censor_audio_and_text
        groq_words = getattr(result, "words", []) or []
        if isinstance(groq_words, dict):
             groq_words = groq_words.get("words", []) # Fallback just in case
        elif not isinstance(groq_words, list) and isinstance(result, dict):
             groq_words = result.get("words", [])
        
        class _DummyWord:
            def __init__(self, w):
                if isinstance(w, dict):
                    self.start = float(w.get("start", 0.0))
                    self.end = float(w.get("end", 0.0))
                    self.word = correct_vietnamese_transcription(w.get("word", ""))
                else:
                    self.start = float(getattr(w, "start", 0.0))
                    self.end = float(getattr(w, "end", 0.0))
                    self.word = correct_vietnamese_transcription(getattr(w, "word", ""))
                self.probability = 0.85

        dummy_words = []
        for w in groq_words:
            dummy_words.append(_DummyWord(w))

        # Gán words vào các segments tương ứng
        for seg in dummy_segs:
            seg.words = [w for w in dummy_words if w.start >= seg.start - 0.2 and w.end <= seg.end + 0.2]

        if is_hallucination(transcript):
            transcript = ""
            dummy_words = []
            dummy_segs = []
            confidence = 0.0

        if transcript:
            logging.info(f"[GROQ] ✅ Transcript ({len(transcript)} ký tự, {len(dummy_segs)} segs, {len(dummy_words)} words): {transcript[:80]}")
        return transcript, dummy_words, dummy_segs, confidence

    except Exception as e:
        import logging
        logging.warning(f"[GROQ] Lỗi API: {e} — fallback sang Whisper local")
        return "", [], [], 0.0


def transcribe_auto(model, audio_segment: AudioSegment, vad_filter: bool = True) -> tuple[str, list, list, float]:
    """Tự động chọn Groq API (nếu có key) hoặc Whisper local.
    
    Ưu tiên:
      1. Groq API (Whisper large-v3-turbo) — chính xác nhất, không tốn RAM máy
      2. Whisper small local — fallback khi không có internet / API key
    """
    import logging

    # Thử Groq trước
    transcript, words, segs, conf = transcribe_vietnamese_groq(audio_segment)
    if transcript:
        logging.info(f"[TRANSCRIBE] Dùng Groq API ✅ conf={conf}%")
        return transcript, words, segs, conf

    # Fallback về Whisper local
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if api_key:
        logging.warning("[TRANSCRIBE] Groq không trả kết quả — dùng Whisper local làm dự phòng")
    logging.info("[TRANSCRIBE] Dùng Whisper small local")
    return transcribe_vietnamese(model, audio_segment, vad_filter=vad_filter)


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
