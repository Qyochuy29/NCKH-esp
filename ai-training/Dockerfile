FROM python:3.11-slim

WORKDIR /app

# Cài đặt ffmpeg và libsndfile1 cho xử lý âm thanh (pydub, librosa, faster-whisper)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ARG INSTALL_CUDA_LIBS=0
RUN if [ "$INSTALL_CUDA_LIBS" = "1" ]; then \
    pip install --no-cache-dir 'nvidia-cublas-cu12>=12,<13' 'nvidia-cudnn-cu12>=9,<10'; \
    fi

# Copy toàn bộ mã nguồn
COPY server.py transcription.py asr_runtime.py windows_cuda.py analysis_pipeline.py audio_events.py context_analysis.py yamnet_class_map.csv ./

# Set biến môi trường
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV UPLOAD_DIR=/tai-lieu
ENV WHISPER_MODEL_SIZE=medium
ENV ASR_MODE=local
ENV REASONING_MODE=rules

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "1", "--timeout", "900", "--access-logfile", "-", "--error-logfile", "-", "server:app"]

