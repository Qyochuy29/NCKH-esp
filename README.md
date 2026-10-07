# 🛡️ SafeVoice AI

Hệ thống giám sát và cảnh báo bạo lực học đường ứng dụng AI nhận diện âm thanh.

**Chạy trực tiếp trên Windows, không cần Docker:** xem [WINDOWS.md](WINDOWS.md).
Chạy `Cai_Dat_Website.bat` để cài, `Chay_Website_Windows.bat` để bật và
`Tat_Website_Windows.bat` để tắt.

**Chạy Docker trọn bộ:** xem [DOCKER.md](DOCKER.md). Nhấp đúp
`Chay_Docker.bat` để bật, `Tat_Docker.bat` để tắt và
`Sao_Luu_Du_Lieu.bat` để sao lưu. Lần đầu cần Docker Desktop/WSL 2 và Internet.

## 🚀 Khởi chạy nhanh

### Trên Windows
Chạy file script có sẵn (sẽ tự động mở Docker và trình duyệt):
```bash
Chay_He_Thong.bat
```

### Chạy thủ công bằng Docker
```bash
# Sau khi Chay_Docker.bat đã tạo .env
docker compose up --build -d --wait --wait-timeout 1800

# Truy cập trình duyệt
http://localhost:3000/dang-nhap.html
```

Hệ thống sẽ tự động:
1. Áp dụng schema CSDL và khởi tạo database (qua PostgreSQL).
2. Seed dữ liệu mẫu ban đầu (thiết bị, người dùng, lịch sử cảnh báo).
3. Khởi động backend (.NET C#) với `SimulatorBackgroundService` sinh cảnh báo giả lập tự động.

## 👥 Tài khoản demo

| Vai trò | Email | Mật khẩu |
|---------|-------|-----------|
| Quản trị viên | `admin@gmail.com` | `password123` |
| Ban giám hiệu | `bgh@gmail.com` | `password123` |
| Giám thị | `giamthi@gmail.com` | `password123` |
| Bảo vệ | `baove@gmail.com` | `password123` |

## 🏗️ Kiến trúc

```
[Mock AI / Simulator] ------------> [C# .NET Backend]
                                          |
                               +----------+----------+
                               |          |          |
                          [PostgreSQL]  [Redis]  [SignalR Hub]
                          (EF Core)                   |
                                                      v
                                      [HTML/CSS/JS Dashboard - Realtime]
```

## 📁 Cấu trúc thư mục

```
├── backend-csharp/   # API server chính bằng ASP.NET Core (C#)
├── backend/          # [Cũ] API server bằng NestJS/TypeScript (Có thể bỏ qua)
├── frontend/         # Giao diện web Vanilla HTML/CSS/JS
├── huan-luyen-ai/    # Mã nguồn huấn luyện mô hình AI (Python)
├── ai-training/      # Mã nguồn huấn luyện AI dự phòng (Python)
├── mobile/           # Ứng dụng di động (nếu có)
├── tai-lieu/         # Chứa tài liệu và các file tĩnh (audio, hình ảnh)
├── docker-compose.yml# Cấu hình các dịch vụ Docker
├── Chay_He_Thong.bat # Script chạy nhanh hệ thống (Windows)
└── README.md
```

## 🎯 Tính năng chính

- **Dashboard realtime** với sơ đồ trường học SVG và định vị thiết bị.
- **Cảnh báo trực tiếp** qua WebSocket (SignalR) với âm thanh thông báo.
- **4 loại âm thanh** nhận diện: La hét, Kêu cứu, Đe dọa, Cãi vã.
- **Phân quyền** theo vai trò (Admin, Ban giám hiệu, Giám thị, Bảo vệ).
- **Thống kê** với biểu đồ Chart.js (xu hướng, phân bổ, heatmap).
- **Giao diện đa thiết bị** hỗ trợ Dark mode và responsive trên mobile/tablet.
- **Xuất CSV** dữ liệu lịch sử cảnh báo.

## 🧠 Khởi chạy Server AI Thực Tế (Tùy chọn)

Mặc định, backend sẽ dùng dữ liệu giả lập (Simulator). Để hệ thống nhận diện âm thanh thực tế thông qua mô hình AI, bạn cần chạy AI Server (Python):

### Cách 1: Chạy bằng Docker (Khuyên dùng)
AI service đã được bật sẵn trong Docker Compose và có cache model lâu dài.
Khởi chạy bằng script hoặc lệnh:
   ```bash
   docker compose up --build -d --wait --wait-timeout 1800
   ```
AI chạy cổng `5000` trong mạng Docker, backend tự kết nối; chỉ cần mở web cổng `3000`.

### Cách 2: Chạy thủ công (không dùng Docker)
Nếu bạn muốn chạy server AI để tiện debug và test âm thanh:
```bash
# Di chuyển vào thư mục chứa server AI
cd ai-training

# Cài đặt các thư viện (yêu cầu Python 3.10+)
pip install flask tensorflow tensorflow_hub librosa pydub openai-whisper setuptools-rust

# Khởi chạy server AI
python server.py
```

*Lưu ý: Bạn cũng có thể vào thư mục `huan-luyen-ai/` để tham khảo mã nguồn tự huấn luyện mô hình âm thanh cá nhân.*
