# Chạy SafeVoice trực tiếp trên Windows

Không cần Docker, WSL hoặc khởi động lại máy. Các thành phần:

- .NET SDK 9 để build và chạy backend hiện tại (`net9.0`).
- Python 3.11 và môi trường riêng `.venv` cho AI/receiver.
- FFmpeg để đọc audio/video.
- PostgreSQL 15 dạng binaries trong `.runtime/postgresql`, database riêng
  `.runtime/pgdata`, chỉ nghe ở `127.0.0.1:5433`.
- Waitress phục vụ AI trên Windows; backend phục vụ HTML/CSS/JS và SignalR.

Nhấp đúp **Chay_Website_Windows.bat** để bật database, backend, AI và receiver.
**Chay_He_Thong.bat** cũng đã chuyển sang chạy Windows trực tiếp.
Script chờ sẵn sàng rồi mở `http://localhost:3000/dang-nhap.html`.
Nhấp đúp **Tat_Website_Windows.bat** để tắt các tiến trình của website.
Lần tải model đầu tiên cần Internet và có thể mất nhiều phút.

**Cai_Dat_Website.bat** tự cài .NET/Python/FFmpeg còn thiếu qua winget, tải
PostgreSQL binaries nếu chưa có, cài thư viện trong `.venv`, build lại backend
và khởi tạo PostgreSQL chỉ khi chưa có database. Có thể cần quyền Administrator
cho bộ cài hệ thống; script không tự khởi động lại Windows.

Mật khẩu/JWT được tạo riêng trong `.runtime/windows-settings.json`.
Không xóa file này hoặc `.runtime/pgdata` nếu cần giữ dữ liệu.
Audio dùng chung trong `backend-csharp/uploads`; cache AI trong `.runtime/cache`.
Log từng dịch vụ ở `.runtime/logs`. Các tiến trình chạy ngầm, đóng cửa sổ
khởi động không tắt website. Whisper tự chọn GPU NVIDIA nếu khả dụng và fallback CPU
khi GPU lỗi; YAMNet dùng CPU. Máy hiện tại đã kiểm thử `large-v3` trên RTX 3060.

Cấu hình riêng trong `.runtime/windows-settings.json`: `WhisperModel` (medium,
large-v3 hoặc large-v3-turbo), `WhisperDevice` (auto/cuda/cpu), `AsrMode`
(local/cloud/hybrid) và `ReasoningMode` (hiện thực hiện rules). Script chuyển
các giá trị này thành `WHISPER_MODEL_SIZE`, `WHISPER_DEVICE`, `ASR_MODE`, `REASONING_MODE`.
Sau khi đổi cấu hình, chạy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Restart-AI.ps1
```

Xem báo cáo pipeline, API và giới hạn kiểm thử trong [AI_PIPELINE.md](AI_PIPELINE.md).

Database mới có tài khoản demo `admin@gmail.com` / `password123`.
Dữ liệu từ database máy cũ/Docker không được tự nhập hoặc ghi đè.
ESP32 dùng cổng HTTP 3000 hoặc WebSocket 8765 và device token trong settings.

Nguồn PostgreSQL binaries: https://www.enterprisedb.com/download-postgresql-binaries
