FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY websocket_receiver.py filter.py ./
EXPOSE 8765
CMD ["python", "websocket_receiver.py"]
