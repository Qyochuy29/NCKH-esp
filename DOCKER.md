# Chạy toàn bộ SafeVoice trong Docker

Gói gồm frontend và thư viện/font cục bộ, ASP.NET Core API/SignalR,
PostgreSQL, Redis, YAMNet + Faster Whisper, và server nhận âm thanh ESP32.
Frontend nằm trong image `safevoice-web`, không cần chạy Live Server.
Python, .NET, PostgreSQL và FFmpeg được cài bên trong các image.

## Bật và tắt

1. Máy cần Docker Desktop dùng Linux containers và WSL 2. Nếu vừa bật tính
   năng WSL/Virtual Machine Platform, khởi động lại Windows trước.
2. Nhấp đúp `Chay_Docker.bat`. Lần đầu tự tạo `.env`, build các image,
   tải mô hình AI, tạo database và tài khoản mẫu nếu database chưa có dữ liệu.
   Lần đầu cần Internet và có thể mất nhiều phút.
3. Script chờ các dịch vụ sẵn sàng rồi mở
   `http://localhost:3000/dang-nhap.html`. Đóng cửa sổ script không tắt web.
4. Những lần sau cũng dùng `Chay_Docker.bat`, hoặc bật nhóm **safevoice**
   trong Docker Desktop và mở địa chỉ trên. Trong Docker Desktop cần bật cả
   nhóm để có PostgreSQL, AI, backend và receiver.
5. Tắt bằng `Tat_Docker.bat` hoặc Stop nhóm **safevoice** trong Docker Desktop.

Tài khoản mẫu ban đầu: `admin@gmail.com` / `password123`. Database nhập từ
máy cũ giữ nguyên tài khoản của máy cũ. Chỉnh cổng trong `.env` nếu cần.

## Dữ liệu được giữ lại

Docker named volumes trong project `safevoice`:

| Volume | Nội dung |
|---|---|
| pg_data | Toàn bộ bảng SQL, tài khoản, thiết bị, lịch sử, dữ liệu audio trong DB |
| audio_data | Audio upload, file từ ESP32, clip AI, marker xử lý |
| redis_data | Dữ liệu Redis |
| ai_cache | Model YAMNet/Whisper đã tải và cache |
| dp_keys | Khóa ASP.NET Data Protection |

Backend đọc cùng volume audio qua `/uploads` và `/tai-lieu`; AI và receiver
đọc/ghi cùng volume. Không còn yêu cầu thư mục `C:\NKKH\tai-lieu`.
Stop/start và build lại image giữ dữ liệu. Không xóa các volume nếu cần giữ
dữ liệu; `docker compose down -v` sẽ xóa chúng.
Giữ `.env` cùng dữ liệu: mật khẩu PostgreSQL được thiết lập khi tạo volume
lần đầu, thay mật khẩu trong `.env` không tự đổi mật khẩu database đang có.

## Nhập dữ liệu cũ trước lần bật đầu tiên

Chưa tìm thấy PostgreSQL đang chạy hay thư mục audio cũ trên thiết bị lúc
đóng gói. SQL trong mã nguồn được tạo bằng EF Core cho database mới;
điều đó không thay thế việc nhập lịch sử từ database cũ.

Từ máy/database cũ, xuất PostgreSQL dạng custom:

```powershell
pg_dump -h localhost -U sguser -d school_guardian -Fc -f database.dump
```

Chép dump và thư mục ghi âm về máy này, rồi chạy **trước lần bật website đầu**:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Import-SafeVoiceData.ps1 -DatabaseDump "D:\du-lieu-cu\database.dump" -AudioDirectory "D:\du-lieu-cu\tai-lieu"
```

Script từ chối ghi đè database hoặc volume audio có dữ liệu. Nếu cần nhập
audio, script tự build image AI nếu chưa có.
Sau khi nhập chạy `Chay_Docker.bat`. Nếu dữ liệu cũ chia giữa nhiều thư mục,
gom thành một thư mục audio và kiểm tra tên file trùng trước khi nhập.

## Sao lưu

Nhấp đúp `Sao_Luu_Du_Lieu.bat` khi hệ thống đang chạy. Script tạm dừng
các dịch vụ ghi dữ liệu, xuất `database.dump`, `audio.tar.gz`, `ai-cache.tar.gz`,
`redis.tar.gz`, `keys.tar.gz` và `.env` vào `backups/<thời gian>`, rồi bật lại
các dịch vụ trước đó. Cache mô hình lớn nên sao lưu có thể mất nhiều phút.
Thư mục backup chứa cấu hình bí mật, chỉ chia sẻ cho người quản trị.

## GPU RTX 3060 (tùy chọn)

Mặc định dùng CPU để không phụ thuộc cấu hình NVIDIA/WSL. Bật Faster Whisper
trên GPU bằng:

```powershell
.\Chay_Docker.bat -Gpu -Rebuild
```

Chế độ được lưu trong `.docker-gpu` cho các lần bật sau. Docker Desktop phải
truy cập được GPU NVIDIA qua WSL 2. YAMNet/TensorFlow vẫn chạy CPU.
Quay lại CPU: `.\Chay_Docker.bat -Cpu`.

Pipeline mới mặc định `ASR_MODE=local`, model được chọn bằng `WHISPER_MODEL_SIZE`.
Có thể chọn `medium`, `large-v3`, `large-v3-turbo`; `hybrid` dùng local trước,
Groq chỉ fallback khi cần và khi có key. `REASONING_MODE=rules` không cần API trả phí.
Chi tiết API, bảo toàn audio gốc và kết quả kiểm thử: [AI_PIPELINE.md](AI_PIPELINE.md).

Lệnh Compose tương đương, sau khi `.env` đã được tạo:

```powershell
docker compose up --build -d
# GPU: build cùng Dockerfile với thư viện CUDA, không cần build image CPU trước.
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
```

Trên máy hiện tại Compose đã kiểm tra cú pháp thành công, nhưng build/up bị chặn
bởi `Docker Desktop is unable to start`. Bản Windows local đã được kiểm thử và
không yêu cầu khởi động lại PC. Khi chuyển sang Docker, dừng bản local để tránh
trùng cổng và nhập dữ liệu theo quy trình sao lưu; hai database không tự đồng bộ.

## ESP32 và cập nhật mã

Thiết bị gửi HTTP tới `http://<IP máy>:3000/api/alerts/device-recording` hoặc
PCM WebSocket tới `ws://<IP máy>:8765`. `DEVICE_TOKEN` trong `.env` cần khớp
firmware. Script tạo `.env` lấy token từ appsettings hiện có để giữ tương thích.
Database, Redis và AI chỉ mở trong mạng Docker; web và receiver mở ra máy host.

Sau khi sửa mã: `.\Chay_Docker.bat -Rebuild`.
Xem lỗi: `docker compose logs --tail 100 backend ai-service audio-receiver`.
Kiểm tra: `docker compose ps`, `http://localhost:3000/health`.

Mã huấn luyện dự phòng trong `huan-luyen-ai/` và firmware không phải dịch vụ
website; không chạy huấn luyện mỗi lần bật web. Dịch vụ AI hiện dùng YAMNet
và Faster Whisper; model tự huấn luyện chưa được server hiện tại nạp vào.

Tài liệu Docker: https://docs.docker.com/desktop/setup/install/windows-install/
