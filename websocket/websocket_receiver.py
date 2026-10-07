
"""
WebSocket server nhận audio PCM thô từ ESP32 (INMP441) và lưu thành file .wav.

Tính năng:
- Hỗ trợ nhiều thiết bị ESP32 kết nối đồng thời (mỗi kết nối là 1 phiên ghi riêng)
- Đặt tên file theo deviceID + thời gian, tránh ghi đè
- Ghi kèm file metadata (.json) mô tả phiên ghi âm
- Dùng logging thay vì print, có thể chỉnh mức log qua config
- Đóng file an toàn khi mất kết nối hoặc server tắt (Ctrl+C)
- Validate header, bắt lỗi struct/IO thay vì crash
- Khử nhiễu/làm mịn âm thanh streaming (bandpass + spectral subtraction),
  trạng thái lọc tách riêng theo từng device_id (xem filter.py)
"""

from __future__ import annotations

import numpy as np
import os
import asyncio
import json
import logging
import signal
import struct
import wave
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import websockets

import filter as audio_filter

# ---------------------------------------------------------------------------
# Cấu hình
# ---------------------------------------------------------------------------

@dataclass
class Config:
    host: str = "0.0.0.0"
    port: int = 8765
    output_dir: Path = Path(__file__).parent.parent / "tai-lieu"
    backend_url: str = "http://localhost:3000/api/alerts/analyze-existing"
    device_token: str = "your_secure_device_token_123"
    log_level: int = logging.INFO
    # In thống kê (min/max/mean) mỗi N gói tin thay vì mỗi gói (tránh spam console)
    stats_log_interval: int = 200
    # Các bitDepth được hỗ trợ -> số byte mỗi sample
    supported_bit_depths: dict = field(default_factory=lambda: {8: 1, 16: 2, 24: 3, 32: 4})
    # Chế độ xử lý âm thanh:
    #   "off"     = chỉ loại DC-offset, giữ nguyên tất cả (không khử nhiễu)
    #   "denoise" = cắt tiếng quạt (rumble thấp) + hiss/rè (nhiễu ổn định),
    #               giữ nguyên âm thanh to đột ngột (súng, vỡ, hét...)
    denoise_mode: str = "off"
    # Các tham số sau CHỈ áp dụng khi denoise_mode="denoise":
    denoise_alpha: float = 1.5
    denoise_beta: float = 0.08


CONFIG = Config(
    host=os.environ.get("AUDIO_HOST", "0.0.0.0"),
    port=int(os.environ.get("AUDIO_PORT", "8765")),
    output_dir=Path(os.environ.get("UPLOAD_DIR", str(Path(__file__).parent.parent / "tai-lieu"))),
    backend_url=os.environ.get("BACKEND_URL", "http://localhost:3000/api/alerts/analyze-existing"),
    device_token=os.environ.get("DEVICE_TOKEN", "your_secure_device_token_123"),
)

HEADER_FORMAT = "<BBIBH"  # codec(B), deviceID(B), sampleRate(I), bitDepth(B), payloadLength(H)
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

logger = logging.getLogger("audio_server")


def setup_logging(level: int) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


# ---------------------------------------------------------------------------
# Recorder: quản lý 1 phiên ghi âm (1 kết nối ESP32)
# ---------------------------------------------------------------------------

class AudioRecorder:
    """Quản lý vòng đời của 1 file .wav cho một kết nối ESP32."""

    def __init__(self, device_id: int, sample_rate: int, bit_depth: int, output_dir: Path):
        self.device_id = device_id
        self.sample_rate = sample_rate
        self.bit_depth = bit_depth
        self.sample_width = CONFIG.supported_bit_depths[bit_depth]

        self.start_time = datetime.now(timezone.utc)
        timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")

        output_dir.mkdir(parents=True, exist_ok=True)
        self.wav_path = output_dir / f"device{device_id}_{timestamp}.wav"
        self.meta_path = self.wav_path.with_suffix(".json")

        self._wav = wave.open(str(self.wav_path), "wb")
        self._wav.setnchannels(1)
        self._wav.setframerate(sample_rate)
        self._wav.setsampwidth(self.sample_width)

        self.bytes_written = 0
        self.packet_count = 0

        logger.info(
            "Start recording | device=%s sampleRate=%s bitDepth=%s -> %s",
            device_id, sample_rate, bit_depth, self.wav_path,
        )

    def write(self, payload: bytes) -> None:
        # QUAN TRỌNG: truyền device_id để filter.py tách trạng thái lọc
        # (bandpass zi + hồ sơ nhiễu nền) riêng cho từng thiết bị/kết nối.
        # Nếu không truyền, nhiều ESP32 cùng kết nối sẽ dùng chung 1 trạng thái
        # lọc -> nhiễu nền của thiết bị này ảnh hưởng tới thiết bị khác.
        payload = audio_filter.process_audio(
            audio_numpy_array=np.frombuffer(payload, dtype=np.int16),
            sample_rate=self.sample_rate,
            device_id=self.device_id,
            mode=CONFIG.denoise_mode,
            alpha=CONFIG.denoise_alpha,
            beta=CONFIG.denoise_beta,
        )

        if not payload:
            # Gói tin đầu có thể chưa đủ 1 khung xử lý (FRAME_LEN), filter.py
            # sẽ giữ lại trong buffer nội bộ và xuất ra ở gói kế tiếp.
            return

        self._wav.writeframes(payload)
        self.bytes_written += len(payload)
        self.packet_count += 1

        if self.packet_count % CONFIG.stats_log_interval == 0:
            logger.debug(
                "device=%s: %d packets, %.1f KB, %.2fs",
                self.device_id, self.packet_count,
                self.bytes_written / 1024,
                self.duration_sec,
            )

    @property
    def duration_sec(self) -> float:
        bytes_per_sec = self.sample_rate * self.sample_width
        return self.bytes_written / bytes_per_sec if bytes_per_sec else 0.0

    def close(self) -> None:
        try:
            self._wav.close()
        except Exception:
            logger.exception("Loi khi dong file wav %s", self.wav_path)

        # Dọn trạng thái lọc (bandpass zi, hồ sơ nhiễu nền, buffer) của thiết
        # bị này để tránh rò rỉ bộ nhớ khi có nhiều phiên kết nối/ngắt liên tục.
        audio_filter.reset_device(self.device_id)

        end_time = datetime.now(timezone.utc)
        metadata = {
            "device_id": self.device_id,
            "sample_rate": self.sample_rate,
            "bit_depth": self.bit_depth,
            "channels": 1,
            "start_time": self.start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_sec": round(self.duration_sec, 3),
            "packet_count": self.packet_count,
            "bytes_written": self.bytes_written,
            "wav_file": self.wav_path.name,
        }
        try:
            self.meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
        except OSError:
            logger.exception("Loi khi ghi metadata %s", self.meta_path)

        logger.info(
            "Da luu: %s (%.2fs, %.1f KB, %d packets)",
            self.wav_path, self.duration_sec, self.bytes_written / 1024, self.packet_count,
        )

        # Gửi thông báo cho C# Backend để gọi AI phân tích
        if self.duration_sec >= 1.0: # Chỉ phân tích nếu thu được hơn 1 giây
            self._trigger_ai_analysis()

    def _trigger_ai_analysis(self) -> None:
        try:
            req_data = json.dumps({"file_name": self.wav_path.name}).encode('utf-8')
            req = urllib.request.Request(
                CONFIG.backend_url,
                data=req_data,
                headers={
                    'Content-Type': 'application/json',
                    'X-Device-Token': CONFIG.device_token
                }
            )
            logger.info("Dang gui yeu cau phan tich cho %s toi Backend...", self.wav_path.name)
            
            # Gửi request không đồng bộ để không block event loop
            asyncio.create_task(self._send_request(req))
            
        except Exception as e:
            logger.error("Loi tao request AI cho %s: %s", self.wav_path.name, e)

    async def _send_request(self, req: urllib.request.Request) -> None:
        loop = asyncio.get_running_loop()
        try:
            response = await loop.run_in_executor(None, urllib.request.urlopen, req)
            if response.status == 200:
                logger.info("AI Analysis Triggered Successfully cho file %s", self.wav_path.name)
            else:
                logger.warning("Backend tra ve status %s", response.status)
        except urllib.error.URLError as e:
            logger.error("Khong the ket noi toi C# Backend de phan tich AI: %s", e.reason)
        except Exception as e:
            logger.error("Loi khi call API AI: %s", e)


# ---------------------------------------------------------------------------
# Xử lý kết nối WebSocket
# ---------------------------------------------------------------------------

async def handle_connection(websocket) -> None:
    peer = websocket.remote_address
    logger.info("Device: %s", peer)

    recorder: AudioRecorder | None = None

    try:
        async for message in websocket:
            if not isinstance(message, (bytes, bytearray)):
                logger.warning("Skipping message that is not bytes from %s", peer)
                continue

            if len(message) < HEADER_SIZE:
                logger.warning("Message too short (%d bytes) from %s", len(message), peer)
                continue

            try:
                codec, device_id, sample_rate, bit_depth, payload_length = struct.unpack(
                    HEADER_FORMAT, message[:HEADER_SIZE]
                )
            except struct.error:
                logger.exception("Loi giai ma header tu %s", peer)
                continue

            payload = message[HEADER_SIZE:]

            if len(payload) != payload_length:
                logger.warning(
                    "Sai do dai payload: header=%d thuc te=%d (device=%s)",
                    payload_length, len(payload), device_id,
                )
                continue

            if bit_depth not in CONFIG.supported_bit_depths:
                logger.error("bitDepth khong ho tro: %s (device=%s)", bit_depth, device_id)
                continue

            if recorder is None:
                recorder = AudioRecorder(
                    device_id=device_id,
                    sample_rate=sample_rate,
                    bit_depth=bit_depth,
                    output_dir=CONFIG.output_dir,
                )

            recorder.write(payload)

    except websockets.exceptions.ConnectionClosed as e:
        logger.info("Device disconnected: %s (%s)", peer, e.reason or "no reason")
    except Exception:
        logger.exception("Loi xu ly ket noi %s", peer)
    finally:
        if recorder is not None:
            recorder.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    setup_logging(CONFIG.log_level)
    CONFIG.output_dir.mkdir(parents=True, exist_ok=True)

    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Windows không hỗ trợ add_signal_handler cho một số signal
            pass

    async with websockets.serve(handle_connection, CONFIG.host, CONFIG.port):
        logger.info("Server running: ws://%s:%s", CONFIG.host, CONFIG.port)
        logger.info("Thu muc luu file: %s", CONFIG.output_dir.resolve())
        await stop_event.wait()

    logger.info("Server stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
