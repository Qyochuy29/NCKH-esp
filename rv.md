# BÁO CÁO RÀ SOÁT TOÀN DIỆN SAFEVOICE AI

> Thời điểm rà soát: 07/10/2026 (Asia/Saigon)  
> Phạm vi: toàn bộ mã nguồn trong `C:\NCKH-esp`, cấu hình chạy, AI, firmware ESP32, cơ sở dữ liệu, giao diện web và cấu hình phần cứng/phần mềm chính của laptop.  
> Lưu ý bảo mật: báo cáo **không chép lại giá trị mật khẩu, API key, JWT secret, Wi-Fi password hoặc device token** dù các giá trị này đang xuất hiện trong repository.

## 1. Kết luận nhanh

SafeVoice AI là một nguyên mẫu khá đầy đủ về mặt ý tưởng: ESP32-S3 thu âm và chạy AI biên, backend ASP.NET Core lưu cảnh báo vào PostgreSQL, AI server dùng YAMNet + Whisper + luật tiếng Việt để thẩm định, frontend nhận cảnh báo thời gian thực qua SignalR.

Tuy nhiên hệ thống **chưa phù hợp để triển khai thật tại trường học**. Ba nguyên nhân chính:

1. Bảo mật đang ở mức nguy hiểm: có khóa bí mật trong mã, endpoint rò rỉ người dùng/mật khẩu băm, đăng nhập xã hội giả, CORS mở toàn bộ và dữ liệu âm thanh có thể truy cập ẩn danh.
2. Chất lượng AI chưa được chứng minh: repository không có dataset huấn luyện thật, không có báo cáo precision/recall/F1 theo lớp, confidence phần server phần lớn là số gán bằng luật, YAMNet là model âm thanh tổng quát chứ không phải model bạo lực học đường.
3. Vận hành chưa ổn định: migration bị chia ở hai namespace/thư mục, ứng dụng dùng `EnsureCreated()` thay cho migration chuẩn, đường dẫn Windows ghi cứng và còn sai tên thư mục, Redis được khai báo nhưng không dùng, job AI chạy nền không có queue bền vững, không có test/CI/monitoring/backup/retention thật.

Đánh giá hiện tại:

| Hạng mục | Mức độ | Nhận xét |
|---|---:|---|
| Ý tưởng và demo | Khá | Có đủ thiết bị, web, API, AI, realtime |
| Backend cơ bản | Trung bình khá | Build được; CRUD, JWT, SignalR, thống kê đã có |
| Frontend | Trung bình khá | Đủ màn hình quản trị và responsive; vẫn là SPA thủ công rời rạc |
| AI server | Thử nghiệm | Có pipeline tốt về ý tưởng nhưng chưa có kiểm định khoa học |
| Edge AI ESP32 | Thử nghiệm nâng cao | Có Log-Mel/TFLite và luật va đập; cấu hình/ngưỡng còn không đồng nhất |
| Bảo mật | Yếu/nguy hiểm | Có nhiều lỗi mức P0 cần xử lý ngay |
| Dữ liệu và quyền riêng tư | Yếu | Âm thanh trẻ em là dữ liệu nhạy cảm nhưng chưa có vòng đời/quyền truy cập chặt |
| DevOps/vận hành | Yếu | Không test, CI, health check ứng dụng, metrics, queue, backup được kiểm chứng |
| Khả năng chạy trên laptop hiện tại | Có thể demo | RAM 12 GB và RTX 2050 4 GB là giới hạn lớn khi chạy đồng thời Docker + YAMNet + Whisper |

## 2. Kiến trúc hiện tại

```text
Micro INMP441
    |
    v
ESP32-S3 (16 kHz, WAV 10 giây, Log-Mel + TFLite + luật xung va đập)
    |
    | HTTP + X-Device-Token
    v
ASP.NET Core 9 API :3000
    |---- PostgreSQL 15 (EF Core/Npgsql)
    |---- SignalR /ws/alerts ----> Web HTML/CSS/JS
    |---- Firebase FCM (nếu có credential)
    |---- gọi HTTP /analyze-full
    v
Python Flask AI :5000
    |---- YAMNet / AudioSet
    |---- Groq Whisper large-v3-turbo nếu có key
    |---- Faster-Whisper small/base dự phòng cục bộ
    |---- luật từ khóa tiếng Việt + che tiếng tục + cắt clip sự cố
    v
Kết quả quay lại backend -> PostgreSQL -> SignalR/FCM -> người xử lý
```

Các thành phần chính:

| Thành phần | Thư mục | Vai trò | Trạng thái |
|---|---|---|---|
| Frontend | `frontend/` | Dashboard, cảnh báo, lịch sử, thống kê, thiết bị, khu vực, người dùng, cài đặt | Có mã hoàn chỉnh dạng Vanilla JS |
| Backend | `backend-csharp/` | REST API, JWT/RBAC, EF Core, SignalR, FCM, thống kê | Build thành công |
| AI runtime chính | `ai-training/` | Phân tích audio/video bằng YAMNet, Whisper và luật | Có mã; model tải lúc chạy |
| Pipeline train tham khảo | `ai-training/`, `huan-luyen-ai/` | MFCC + CNN PyTorch + export ONNX | Hai bản gần như trùng; chưa có dataset/model đầu ra trong repo |
| Firmware chính | `esp32-voice-recorder-.../esp32-voice-recorder/` | ESP32-S3 + INMP441 + TFLite Micro + upload | Có nhiều model header và mã firmware chính |
| Firmware thử nghiệm | `firmware-esp32/`, `ESP-Test/` | Test INMP441/MAX9814, upload WAV | Chỉ phục vụ thử nghiệm |
| WebSocket Python phụ | `websocket/` | Nhận/lọc dữ liệu âm thanh theo một luồng thử nghiệm khác | Không nằm trong Docker Compose chính |
| Scratch | `scratch/` | Kiểm tra model/ESP/Whisper/threshold | Không nên đưa vào production |

Repository có khoảng 1.765 file được Git theo dõi; trong đó khoảng 192 file build/cache (`bin`, `obj`, `__pycache__`) đang bị commit. Phần mã tự viết chính có khoảng 5.902 dòng C#, 4.621 dòng Python, 3.535 dòng C++, 1.977 dòng JavaScript và 1.835 dòng CSS; thư viện Edge Impulse nhúng làm số dòng header tăng mạnh nhưng không phải toàn bộ là mã tự viết.

## 3. Các luồng hoạt động

### 3.1 Đăng nhập và phiên làm việc

1. Người dùng gửi email/mật khẩu tới `POST /api/auth/login`.
2. Backend tìm user, kiểm tra BCrypt.
3. Backend phát access token JWT 30 phút và refresh token JWT 7 ngày.
4. Frontend lưu cả hai token trong `localStorage`.
5. API helper gắn `Authorization: Bearer ...`.
6. Khi access token hết hạn, frontend gọi `/api/auth/refresh`, lưu token mới rồi reload trang.

Vai trò hiện có: `admin`, `ban_giam_hieu`, `giam_thi`, `bao_ve`, `phu_huynh`.

Điểm chưa đạt: refresh token không có bảng phiên, không xoay vòng/revoke; logout chỉ xóa localStorage; social login không xác minh token của Google/Apple; route `/api/auth/dump` không yêu cầu đăng nhập.

### 3.2 Luồng ESP32 nhận diện tại biên

1. ESP32 lấy ID từ eFuse MAC, kết nối Wi-Fi trực tiếp hoặc WiFiManager.
2. INMP441 thu PCM mono 16 kHz, 32-bit I2S rồi chuyển thành WAV 16-bit.
3. Mỗi vòng thu 10 giây; model nhận cửa sổ 5 giây, nên firmware chia thành hai đoạn.
4. Lọc phòng im lặng theo peak/RMS.
5. Phân tích xung va đập theo các block 10 ms: peak chuẩn hóa, crest factor, tổng thời gian hoạt động, chuỗi hoạt động dài nhất và số transient.
6. Trích Log-Mel Spectrogram bằng Hann window, FFT 512, hop 160, 40 mel bins, 501 frame.
7. Quantize input, chạy TFLite Micro, lấy bốn xác suất: khóc, đập phá, chửi/cãi nhau, tiếng ồn.
8. Áp dụng luật ưu tiên; nếu nguy hiểm thì upload toàn bộ WAV 10 giây tới backend bằng device token.
9. Nếu nhãn chỉ là `analyze`, backend đưa file qua AI server để thẩm định nội dung; nếu là cảnh báo chắc chắn, backend có thể tạo cảnh báo trực tiếp.

Ngưỡng thực thi đang dùng trong `loop()`:

- Bỏ qua tiếng ồn nếu xác suất tiếng ồn ≥ 0,80 và không có va đập.
- Khóc/kêu cứu: xác suất ≥ 0,40; confidence gửi lên bị nâng tối thiểu thành 0,80.
- Đập phá: luật impact hoặc xác suất ≥ 0,45; confidence bị nâng tối thiểu thành 0,85.
- Chửi/cãi nhau: xác suất ≥ 0,40.
- Giọng lớn: tiếng ồn < 0,70 và peak ≥ 1.500 thì gửi để server phân tích.

Vấn đề: file model khai báo ngưỡng 0,70/0,75/0,55 nhưng đoạn quyết định lại ghi cứng 0,40/0,45/0,40. Log khởi động in ngưỡng từ header nên có thể khác hành vi thực tế. Đây là lỗi quản trị cấu hình cần hợp nhất.

### 3.3 Luồng AI server

1. Backend gửi tên file đến `POST /analyze-full`.
2. Flask chỉ lấy basename và ghép vào thư mục cho phép để giảm path traversal.
3. Pydub/FFmpeg đọc audio hoặc video; giới hạn logic 20 MB được khai báo nhưng cần kiểm tra việc áp dụng đồng đều.
4. YAMNet phân loại frame AudioSet:
   - Nhóm la hét: shout, bellow, yell, children shouting, screaming.
   - Nhóm khóc: crying/sobbing, baby cry, whimper, wail/moan; groan/gasp là nhóm phụ.
   - Nhóm va đập: slam, bang, slap, whack, smash/crash, breaking, crushing.
   - Nhóm speech để xác định có lời nói.
5. Groq Whisper `whisper-large-v3-turbo` được ưu tiên nếu có API key; nếu không có hoặc lỗi thì dùng Faster-Whisper `small` trên CUDA, sau đó CPU int8, cuối cùng `base` CPU.
6. Transcript tiếng Việt được chuẩn hóa, dò danh sách chửi tục, đe dọa, kêu cứu và loại trừ một số kết hợp an toàn như “đánh răng”.
7. Các từ tục được thay bằng `***`; audio tương ứng được thay bằng beep 1.000 Hz dựa trên word timestamp.
8. Xác suất bạo lực theo luật được cộng điểm: la hét +35, khóc +35, impact +35, kêu cứu +40 và phụ trội, đe dọa +30 và phụ trội, tục +25 và phụ trội; chặn tối đa 99.
9. Các sự kiện gần nhau ≤ 3 giây được gom thành cửa sổ; clip tối thiểu 4 giây, tối đa khoảng 10 giây, có đệm ngữ cảnh 1 giây.
10. Ưu tiên nhãn cục bộ: `threat` -> `help` -> `scream` -> `dap_pha` -> `argument`; đoạn an toàn bị bỏ qua.
11. AI trả danh sách clip, transcript đã che, flags và `dialog_data`; backend tạo từng cảnh báo.

Ngưỡng YAMNet đáng chú ý:

- Khóc chính ≥ 0,35 với ít nhất 2 frame, hoặc ≥ 0,55 với ít nhất 1 frame.
- La hét ≥ 0,40 với ít nhất 2 frame, hoặc score ≥ 0,55.
- Impact khi có speech đòi ngưỡng cao hơn; khi ít speech ngưỡng thấp hơn.

Hạn chế quan trọng: confidence từng cảnh báo hiện chủ yếu là hằng số luật (80, 85, 90, 95), không phải xác suất đã calibration. Không nên trình bày các số này cho người dùng như “độ chính xác AI”.

### 3.4 Luồng hợp nhất Edge AI và Server AI

Backend áp dụng cơ chế hai tầng:

- Nếu server tìm được sự kiện, dùng sự kiện server.
- Nếu server không tạo alert, backend đọc các cờ tổng hợp như scream/cry/impact/threat/vulgarity/emergency và xác suất bạo lực.
- Server có quyền phủ quyết cảnh báo Edge khi nội dung được đánh giá an toàn (`violence_probability < 30` và không có dấu hiệu khác).
- Server xác nhận nguy hiểm khi có cờ nguy hiểm hoặc xác suất ≥ 40.

Đây là hướng đúng để giảm false positive, nhưng hiện luật nằm rải ở Python, C# và C++; chưa có một “decision contract” có version nên rất khó tái lập kết quả.

### 3.5 Luồng cảnh báo thời gian thực

1. `SubmitDetection()` ghi `alerts` vào PostgreSQL.
2. Nạp device và area.
3. Gửi event `new-alert` qua SignalR.
4. Tra người được phép nhận thông báo và các FCM token.
5. Gửi push Firebase nếu có credential.
6. Frontend hiện toast, phát âm báo, cập nhật badge và danh sách.
7. Người xử lý cập nhật trạng thái/ghi chú; backend ghi `alert_logs` và phát `alert-updated`.

Lỗi quyền hiện tại: backend tính danh sách người được phép nhưng SignalR vẫn phát `Clients.All`. Frontend không phải ranh giới bảo mật; dữ liệu cần được gửi vào group/user tương ứng ngay tại server.

### 3.6 Luồng offline và lịch sử

- API `/api/alerts/sync` nhận danh sách hành động offline, kiểm tra quyền và áp dụng cập nhật.
- Lịch sử hỗ trợ lọc thời gian, khu vực, loại, trạng thái; phân trang offset/limit và xuất CSV.
- Audio có thể lấy từ URL file hoặc bytea trong DB.
- Cảnh báo có trạng thái `pending`, `confirmed`, `false_alarm`, `resolved`; có `is_evidence`, người xử lý, thời điểm xử lý và nhật ký.

### 3.7 Luồng phụ huynh

- Bảng `students` liên kết phụ huynh với lớp (`areas`).
- Phụ huynh chỉ được query các alert thuộc area/classroom của con.
- Có API thống kê hôm nay và tối đa 50 cảnh báo gần nhất.

Mô hình hiện tại giả định “lớp học = area”; chưa mô hình hóa trường, khối, năm học, lớp theo niên khóa, nhiều con/nhiều người giám hộ và thời khóa biểu.

## 4. Toàn bộ thuật toán và kỹ thuật chính

| Nhóm | Thuật toán/kỹ thuật | Nơi dùng | Nhận xét |
|---|---|---|---|
| Xử lý âm thanh Edge | RMS, dBFS, peak, clipping | ESP32 | Lọc im lặng/lỗi mic |
| Va đập Edge | Block 10 ms, peak norm, crest factor, active duration, transient count | ESP32 | Luật heuristic, cần tune bằng dữ liệu thật |
| Đặc trưng Edge | Hann + FFT 512 + Slaney Mel 40 bins + log | ESP32 | Khớp model 5 giây/16 kHz |
| Inference Edge | TFLite Micro int8, tensor arena 768 KB | ESP32-S3 | Chạy cục bộ, giảm băng thông |
| Phân loại server | YAMNet pretrained trên AudioSet | Python/TensorFlow Hub | Nhận âm thanh tổng quát, không chuyên biệt bạo lực |
| Speech-to-text | Groq Whisper large-v3-turbo | Cloud | Nhanh/chính xác hơn nhưng gửi dữ liệu ra bên thứ ba |
| Speech-to-text dự phòng | Faster-Whisper small/base, CUDA/CPU int8 | Laptop/server | Có thể chậm trên máy hiện tại |
| NLP luật | Regex biên từ, danh sách profanity/threat/emergency, safe collocations | Python | Dễ giải thích nhưng dễ lệch ngữ cảnh/giọng địa phương |
| Che nội dung | N-gram word timestamp + merge interval + beep 1 kHz | Python/Pydub | Tốt cho bản phát lại; phải giữ bản gốc theo chính sách chứng cứ |
| Gom sự cố | Event clustering theo khoảng cách thời gian, window 4–10 giây | Python | Hợp lý cho UI và bằng chứng |
| Điểm nguy cơ | Weighted additive rule, cap 99 | Python | Không phải xác suất thống kê/calibration |
| CNN train thử | MFCC 40x100 -> Conv1D 64/128/64 -> GAP -> Dense | Python/PyTorch | 20 epoch, Adam 0,001, batch 16, split 80/20 |
| Tiền xử lý train | Librosa resample 22.050 Hz, MFCC, pad/cắt 100 frame | Python | Không khớp trực tiếp pipeline Log-Mel 16 kHz của firmware |
| Xuất model | PyTorch -> ONNX opset 13 | Python | Backend C# hiện không nạp ONNX này |
| Mật khẩu | BCrypt | Backend | Phù hợp cơ bản; cost đang dùng mặc định/10 |
| Phiên | JWT HMAC-SHA256 | Backend/frontend | Thiếu issuer/audience, rotation, revoke, session store |
| Phân quyền | Role authorization + query filter riêng phụ huynh | Backend | Chưa áp dụng nhất quán cho realtime/audio/settings |
| Thống kê | GroupBy theo loại/khu vực/ngày/giờ, heatmap 30 ngày | EF Core/C# | Một số nhóm xử lý in-memory, cần tối ưu khi dữ liệu lớn |
| Soft delete | `is_active` + global query filter | User/Device/Area | Hữu ích nhưng thiếu quy trình phục hồi/audit |
| Realtime | SignalR reconnect tự động | C#/JS | Chưa chia group theo quyền/khu vực |
| Giả lập | Random 15–40 giây, loại/ngưỡng ngẫu nhiên | BackgroundService | Chỉ nên bật ở môi trường demo |

## 5. Các AI/model hiện đang có

### 5.1 AI đang được runtime chính gọi

| Tên | Loại | Đầu vào | Đầu ra | Nguồn/chế độ |
|---|---|---|---|---|
| YAMNet v1 | CNN âm thanh pretrained | waveform mono 16 kHz | điểm các lớp AudioSet theo frame | Tải từ TensorFlow Hub lúc khởi động |
| Groq Whisper large-v3-turbo | ASR tiếng nói | audio | transcript/segment/word timestamp | Cloud API nếu có `GROQ_API_KEY` |
| Faster-Whisper small | ASR cục bộ | audio | transcript/word timestamp | CUDA `int8_float16`, fallback CPU `int8` |
| Faster-Whisper base | ASR dự phòng cuối | audio | transcript | CPU `int8` |
| Custom TFLite `4NHAN91.h` | CNN 4 lớp | Log-Mel 40x501, 5 giây | khóc, đập phá, chửi nhau, tiếng ồn | Nhúng trực tiếp trong firmware ESP32 |

### 5.2 Model/pipeline có trong repo nhưng chưa chứng minh đang dùng production

- Nhiều header model: `model_data.h`, `model_data_4classes*.h`, `khoc_dappha_noischuyen_chuinhau.h`, `4NHAN91.h`; firmware chính chỉ include `4NHAN91.h`.
- Edge Impulse SDK/model đi kèm có metadata 16 kHz, 4 labels, nhưng firmware chính hiện dùng MicroTFLite và model header riêng.
- CNN PyTorch MFCC 4 lớp trong cả `ai-training/` và `huan-luyen-ai/`.
- Quy trình export ONNX tồn tại, nhưng không tìm thấy `.pth`, `.onnx`, `.npy`, `.npz` hoặc dataset thật trong hai thư mục training tại thời điểm rà soát.

### 5.3 Các bất nhất AI cần xử lý

1. Hai pipeline đặc trưng khác nhau: train tham khảo dùng MFCC 22.050 Hz/100 frame; firmware dùng Log-Mel 16 kHz/501 frame. Model train từ pipeline này không thể thay trực tiếp model Edge kia.
2. Tên lớp không thống nhất: `la_het/keu_cuu/de_doa/cai_vua`, `khoc/dap_pha/chui_nhau/tieng_on`, và API `scream/help/threat/argument/dap_pha`.
3. `cai_vua` nhiều khả năng là lỗi chính tả của `cai_va`; tên này đi vào dataset/model contract nên không thể sửa tùy tiện mà không migration.
4. Confidence Edge lúc là 0–1, lúc đổi thành 0–100; DTO/DB mong 0–100. Cần một chuẩn duy nhất.
5. Các confidence 80/85/90/95 của server là hằng số luật, không phản ánh xác suất model.
6. Ngưỡng khai báo trong model header khác ngưỡng thực thi ghi cứng trong firmware.
7. Không có model card, version, checksum, ngày train, dataset lineage hoặc benchmark theo thiết bị/phòng học.

## 6. Dữ liệu và SQL

### 6.1 Database

- Hệ quản trị: PostgreSQL 15 Alpine.
- Database: `school_guardian`.
- ORM: Entity Framework Core 9 + Npgsql 9.0.4.
- Cache/message component: Redis 7 được khai báo trong Compose nhưng chưa có mã sử dụng thực tế.
- Dữ liệu hiện hành trong PostgreSQL chưa kiểm tra được vì Docker daemon đang tắt khi rà soát.

### 6.2 Bảng và trường dữ liệu

| Bảng | Trường chính | Nghiệp vụ |
|---|---|---|
| `users` | id, full_name, email, password_hash, role, created_at, is_active | Tài khoản và vai trò |
| `user_devices` | id, user_id, fcm_token, device_name, last_active | Nhiều thiết bị nhận push cho một user |
| `areas` | id, name, description, created_at, is_active | Khu vực/lớp học |
| `devices` | id, name, area_id, floor, position_x/y, status, battery_level, last_seen, is_active | Cảm biến/ESP32 và vị trí |
| `alerts` | id, device_id, timestamp, sound_type, confidence_score, audio_file_url, audio_data, dialog_data, status, handled_by_id, resolved_at, notes, is_evidence, transcript, keywords, timestamp_seconds | Sự kiện/cảnh báo chính |
| `alert_logs` | id, alert_id, action, actor_id, timestamp | Nhật ký thao tác |
| `settings` | key, value | Cài đặt dạng key-value |
| `students` | id, full_name, parent_id, classroom_id, created_at | Liên kết học sinh–phụ huynh–lớp |

### 6.3 Enum/giá trị nghiệp vụ

- Role: admin, ban_giam_hieu, giam_thi, bao_ve, phu_huynh.
- Device status: online, offline, error.
- Sound type: scream, help, threat, argument, dap_pha.
- Alert status: pending, confirmed, false_alarm, resolved.

### 6.4 Index và quan hệ

- Unique: `users.email`, `areas.name`, `settings.key`.
- Alert indexes: timestamp, status, sound_type, `(status,timestamp)`, `(device_id,timestamp)`, handled_by_id.
- Device indexes: area_id, status.
- Student indexes: parent_id, classroom_id.
- `alert_logs` cascade theo alert; hầu hết quan hệ người dùng/device/area là restrict; `user_devices` cascade theo user.

### 6.5 File dữ liệu/model hiện thấy

- `ai-training/yamnet_class_map.csv`: bản đồ lớp AudioSet.
- Audio demo: ba file MP3 dưới `backend-csharp/wwwroot/assets/`.
- WAV dummy/scratch dùng kiểm tra.
- Một firmware backup `.bin` khoảng 16 MB.
- Các model TFLite được chuyển thành mảng byte trong nhiều file `.h`.
- Không thấy dataset `raw_audio/`, feature `processed/X.npy`, `y.npy`, model `.pth` hoặc `.onnx` đầu ra.

### 6.6 Vấn đề database/migration

1. Migration nằm ở cả `backend-csharp/Migrations/` và `backend-csharp/Data/Migrations/`, có namespace khác nhau.
2. App gọi `EnsureCreated()` thay vì `Database.Migrate()`, có thể tạo schema nhưng bỏ qua lịch sử migration.
3. `Program.cs` tự chạy `ALTER TABLE ...` rồi nuốt mọi exception; lỗi schema thật có thể bị che.
4. `update.sql`, `manual_update.sql`, `casts.sql` thể hiện nhiều giai đoạn chuyển enum/text không đồng nhất.
5. Model có `dialog_data` nhưng migration ban đầu không thể hiện rõ migration bổ sung riêng cho trường này.
6. Lưu đồng thời audio bằng file URL và `bytea` gây nhân đôi dung lượng, backup nặng và khó áp dụng retention.
7. Cài đặt `min_confidence_threshold` và `audio_retention_days` có trên UI nhưng chưa thấy được thực thi trong pipeline/cleanup.

## 7. Ngôn ngữ, framework và thư viện

| Lớp | Công nghệ |
|---|---|
| Backend | C#, ASP.NET Core 9, Entity Framework Core 9, Npgsql, SignalR, BCrypt, Firebase Admin |
| Frontend | HTML5, CSS3, Vanilla JavaScript, Bootstrap Icons, Chart.js, SignalR JS CDN |
| AI server | Python, Flask, NumPy, TensorFlow CPU, TensorFlow Hub, Librosa, Pydub, Faster-Whisper, Groq SDK, SpeechRecognition |
| Training | Python, PyTorch, scikit-learn, Librosa, ONNX, SoundFile |
| Firmware | C/C++, Arduino framework, ESP-IDF drivers, MicroTFLite, WiFiManager |
| Database | SQL/PostgreSQL; Redis được cấu hình nhưng chưa dùng |
| Hạ tầng | Docker, Docker Compose, Dockerfile, Windows batch, Cloudflared executable |
| Mô hình hóa | Visual Paradigm `.vpp` và các file backup |

Phụ thuộc frontend lấy từ CDN nên nếu trường mất Internet có thể thiếu icon/chart/SignalR client. Nên bundle và pin dependency vào bản phát hành.

## 8. Nghiệp vụ hiện có

- Đăng nhập, đổi mật khẩu, refresh token, đăng nhập xã hội dạng mock.
- Quản lý người dùng và vai trò; soft delete.
- Quản lý khu vực/lớp học.
- Quản lý thiết bị, vị trí theo tầng, pin, trạng thái và last seen.
- Nhận audio từ ESP32 hoặc upload thủ công.
- Nhận diện 5 nhóm cảnh báo: la hét, kêu cứu/khóc, đe dọa, cãi/chửi nhau, đập phá.
- Ghi transcript, từ khóa, audio, dữ liệu hội thoại và đoạn thời gian sự cố.
- Che tiếng tục trong transcript/audio.
- Xác nhận, báo giả, xử lý, ghi chú, đánh dấu chứng cứ.
- Theo dõi lịch sử và log người thao tác.
- Dashboard realtime và âm báo.
- Thống kê tổng quan, theo loại, khu vực, xu hướng, heatmap và tỷ lệ cảnh báo.
- Xuất CSV.
- Thông báo đẩy FCM nếu cấu hình Firebase.
- Quyền xem theo lớp cho phụ huynh.
- Đồng bộ hành động offline.
- Chế độ simulator phục vụ demo.

Nghiệp vụ còn thiếu nếu triển khai tại trường:

- Cấu trúc multi-school/campus/building/floor/room; năm học, lớp và thời khóa biểu.
- Ca trực, escalation theo SLA, phân công người xử lý, xác nhận hai bước.
- Quy trình sự cố: tiếp nhận -> xác minh -> điều phối -> đóng -> hậu kiểm.
- Liên hệ khẩn cấp, kịch bản cho từng mức độ, chống spam/bão cảnh báo.
- Đồng thuận phụ huynh/học sinh, chính sách lưu trữ và xóa audio, quyền truy cập chứng cứ.
- Chuỗi bảo quản chứng cứ: hash, chữ ký, immutable audit, ai tải/nghe/xuất.
- Quản lý firmware/OTA, certificate từng thiết bị, revoke thiết bị, inventory và health telemetry.
- Gán nhãn phản hồi để cải thiện AI và quy trình review chất lượng nhãn.

## 9. Cấu hình laptop hiện tại

### 9.1 Phần cứng/hệ điều hành

| Hạng mục | Cấu hình đọc được |
|---|---|
| Hãng/model | Lenovo 83GS |
| Kiến trúc | x64-based PC |
| Hệ điều hành | Windows 11 Pro for Workstations 64-bit |
| Version/build | 10.0.22631 / 22631 |
| BIOS | NECN53WW, ngày 15/06/2026 |
| CPU | Intel Core i5-12450HX Gen 12, 8 core/12 logical processor, reported max 2.400 MHz |
| RAM | 12 GB DDR5-4800 (Windows báo usable khoảng 11,71 GB), 1 module Ramaxel |
| GPU tích hợp | Intel UHD Graphics, driver 32.0.101.6314 |
| GPU rời | NVIDIA GeForce RTX 2050 Laptop, 4 GB VRAM, driver 566.50 |
| Màn hình hiện tại | 1.920 x 1.080 |
| SSD | Micron MTFDKCD512QGN, dung lượng thực khoảng 476,94 GB |
| Ổ C | NTFS 426,04 GB; trống khoảng 173,58 GB |
| Ổ E | NTFS 50 GB; trống khoảng 29,68 GB |
| Pin | L23B4PK4, trạng thái OK, 79% lúc kiểm tra |

### 9.2 Công cụ phát triển

| Công cụ | Phiên bản/trạng thái |
|---|---|
| .NET SDK | 9.0.102 và 10.0.302; project target .NET 9 |
| ASP.NET runtime | Có 6.0.36, 8.0.12, 9.0.1, 10.0.10 |
| Python | 3.12.10 |
| pip | 25.0.1 |
| Docker | 29.6.1 |
| Docker Compose | v5.1.4 |
| Node.js | v26.3.0 |
| npm | 11.16.0 |
| Git | 2.55.0.windows.2 |
| PlatformIO CLI | Không có trong PATH |
| NVIDIA | RTX 2050 4.096 MiB được `nvidia-smi` nhận diện |
| Docker daemon | Không chạy tại thời điểm kiểm tra |

### 9.3 Mức phù hợp của laptop

- Phù hợp: lập trình C#/frontend/firmware, chạy PostgreSQL + backend, demo một luồng AI với file ngắn.
- Có thể chạy nhưng chật: Docker Desktop + PostgreSQL + backend + TensorFlow/YAMNet + Faster-Whisper small cùng lúc. RAM 12 GB dễ paging; GPU 4 GB giới hạn batch/model và TensorFlow trong image hiện là `tensorflow-cpu` nên YAMNet không tận dụng RTX trong container.
- Không phù hợp: huấn luyện model âm thanh lớn, nhiều camera/micro đồng thời, tải production 24/7 hoặc Whisper large cục bộ.
- Nâng cấp hợp lý: RAM tối thiểu 24 GB, tốt hơn 32 GB dual-channel; production dùng server riêng 32–64 GB RAM và GPU 8–12 GB VRAM nếu chạy ASR cục bộ.
- Python 3.12 cần khóa dependency và kiểm thử; nhiều stack ML ổn định hơn khi dùng image Python 3.10/3.11 cố định.

## 10. Kết quả kiểm chứng kỹ thuật

- `dotnet build --no-restore`: **thành công**, không có lỗi compile; còn nhiều cảnh báo nullable và API Firebase obsolete.
- `docker compose config --quiet`: cấu hình Compose parse hợp lệ.
- `docker compose ps`: không thực hiện được vì Docker Desktop/Linux engine chưa chạy.
- Không tìm thấy project test tự động có ý nghĩa cho backend/frontend/AI/firmware.
- Không tìm thấy cấu hình CI/CD.
- PlatformIO CLI không có trong PATH nên chưa build firmware trong lượt rà soát.
- Git worktree đã có thay đổi ở file build `obj/` và `scratch/` trước khi tạo báo cáo; báo cáo không sửa các file đó.

## 11. Các vấn đề cần khắc phục

### P0 — phải làm ngay trước khi public/chạy thật

1. **Thu hồi và xoay toàn bộ bí mật**: Groq API key, Wi-Fi password, database password, JWT secrets, device token đã/đang ghi cứng trong Compose, appsettings, batch hoặc firmware. Xóa khỏi Git history bằng quy trình an toàn; dùng `.env`, Docker secrets/secret manager và provisioning thiết bị.
2. **Xóa hoặc khóa `/api/auth/dump`**: endpoint công khai trả entity user, bao gồm `password_hash`.
3. **Tắt social login giả**: hiện chỉ tin email/fullName client gửi và tự tạo tài khoản quyền `giam_thi`; phải xác minh issuer, audience, signature, expiry và nonce với nhà cung cấp.
4. **Khóa audio theo quyền**: `/api/alerts/{id}/audio` đang anonymous và code cho tất cả role nghe audio. Phải xác thực, kiểm tra area/role, log truy cập và dùng signed URL ngắn hạn.
5. **Sửa realtime RBAC**: thay `Clients.All` bằng SignalR group/user theo trường/khu vực/quyền.
6. **CORS allowlist**: bỏ `SetIsOriginAllowed(_ => true)` với credentials; chỉ cho phép domain cụ thể.
7. **HTTPS và device identity**: không dùng HTTP LAN + token chung. Dùng TLS, certificate/API key riêng từng device, hash token server-side, rotate/revoke và chống replay (timestamp + nonce/HMAC).
8. **Bảo vệ dữ liệu trẻ em**: thiết lập consent, retention, access log, encryption, quy trình xóa/xuất dữ liệu và đánh giá pháp lý trước pilot.

### P1 — cần làm để hệ thống ổn định

1. Hợp nhất migration; dùng `Database.Migrate()`, bỏ SQL tự sửa schema khi startup và không nuốt exception.
2. Sửa đường dẫn ghi cứng `C:\NKKH\tai-lieu` (khác workspace `NCKH-esp`) thành cấu hình cross-platform; thống nhất `/uploads`/`/tai-lieu`.
3. Đưa phân tích AI vào queue bền vững (RabbitMQ/Redis Streams/Hangfire/Quartz + persisted job), không dùng fire-and-forget `Task.Run` trong request.
4. Thêm health/readiness endpoint cho API, DB, AI, model, FFmpeg, disk; Compose healthcheck cho backend/AI.
5. Thêm timeout, retry có backoff, circuit breaker và idempotency cho upload/AI/FCM.
6. Chuẩn hóa confidence về 0–1 nội bộ và chỉ đổi sang phần trăm ở UI; tách `model_score`, `rule_score`, `risk_score`.
7. Đưa toàn bộ ngưỡng vào config có version; lưu `decision_version`, `model_version` trên từng alert.
8. Thực thi thật `min_confidence_threshold` và `audio_retention_days` hoặc bỏ khỏi UI.
9. Chọn một nơi lưu audio: object storage mã hóa (MinIO/S3/Azure Blob) thường tốt hơn `bytea`; DB chỉ lưu metadata/checksum/URL.
10. Thêm rate limit, request validation, MIME sniffing/decoder sandbox, antivirus nếu cho upload video.
11. Tắt simulator mặc định ngoài môi trường Demo; phân biệt dữ liệu demo bằng cờ riêng.
12. Không serve unknown file types; bổ sung security headers CSP, HSTS, X-Content-Type-Options, Referrer-Policy.

### P2 — chất lượng và khả năng bảo trì

1. Sửa encoding mojibake trong README và nhiều file C#/Python; chuẩn hóa UTF-8, `.editorconfig`, `.gitattributes`.
2. Dọn Git: untrack `bin/`, `obj/`, `__pycache__`, log, WAV dummy, backup lớn; giữ release artifact ở GitHub Releases/artifact registry.
3. Hợp nhất `ai-training` và `huan-luyen-ai`; phân biệt rõ `runtime/`, `training/`, `models/`, `datasets/`.
4. Xóa/di chuyển `scratch`, firmware cũ, model header cũ vào archive có README/version.
5. Thêm nullable initialization/`required` trong entities; cập nhật API Firebase obsolete.
6. Bundle frontend dependency thay vì phụ thuộc CDN; thêm CSP và tránh `innerHTML` với dữ liệu không escape. Hiện một số hàm escape đã có nhưng phải rà toàn bộ điểm render.
7. Chuyển frontend sang module/build pipeline nhẹ (Vite/TypeScript) nếu tiếp tục phát triển lớn; hiện 10 file global JS dễ xung đột và khó test.
8. Bổ sung OpenAPI/Swagger production có bảo vệ, API versioning, ProblemDetails và exception middleware thống nhất.

## 12. Giải pháp kiến trúc đề xuất

### 12.1 Kiến trúc mục tiêu cho pilot

```text
ESP32-S3
  - AI gate nhẹ + ring buffer
  - mTLS/device credential riêng
  - retry/idempotency/offline buffer
        |
        v
API Gateway / ASP.NET Core
  - auth, rate limit, RBAC/ABAC, upload metadata
  - PostgreSQL metadata
  - Object Storage audio mã hóa
        |
        v
Job Queue  ---> AI Worker
               - chuẩn hóa audio
               - Audio Event Detection
               - ASR tiếng Việt
               - NLP/risk fusion
               - model registry/version
        |
        v
Alert Orchestrator
  - deduplicate/cooldown/escalation/SLA
  - SignalR groups + FCM
  - immutable audit
```

Redis chỉ nên giữ nếu có mục đích rõ: distributed cache, rate limit, SignalR backplane hoặc queue. Nếu pilot một máy, có thể bỏ Redis để giảm phức tạp; nếu scale nhiều API instance, dùng Redis backplane/queue rõ ràng.

### 12.2 Chiến lược AI nên dùng

Không nên để một model quyết định “có bạo lực” trực tiếp. Nên dùng fusion có giải thích:

- Tầng 1 Edge: VAD/energy + event model nhỏ, ưu tiên recall, chỉ quyết định có upload hay không.
- Tầng 2 server: model audio event chuyên biệt + ASR + NLP + temporal smoothing.
- Tầng 3 nghiệp vụ: cooldown/dedup, khu vực, thời gian, thiết bị, lịch sử và người xác minh.
- Kết quả trả ra gồm: nhãn, score model gốc, score luật, bằng chứng thời gian, model version, lý do kích hoạt.

Tối thiểu phải xây bộ test “golden set” tiếng Việt thực tế với các lớp:

- khóc/kêu cứu;
- la hét vui chơi và la hét nguy hiểm;
- cãi nhau/chửi nhau;
- đe dọa;
- đập phá/đánh đập;
- nói chuyện bình thường;
- nhạc, trống trường, kéo ghế, đóng cửa, vỗ tay, thể dục, sân trường đông;
- im lặng, mic lỗi, clipping, gió/mưa/quạt.

Chia train/validation/test theo **người nói và địa điểm**, không chia ngẫu nhiên theo clip từ cùng một bản ghi vì sẽ rò rỉ dữ liệu. Báo cáo precision, recall, F1, confusion matrix, false alerts/giờ và miss rate cho từng lớp/khu vực. Với bài toán an toàn, cần đặt mục tiêu recall cao nhưng phải có cooldown/thẩm định để false alarm không làm người trực bỏ qua hệ thống.

### 12.3 Tối ưu hiệu năng

- ESP32: ring buffer liên tục, trigger rồi lấy cả 2–3 giây trước sự kiện; tránh thu–ngừng theo block làm mất đầu sự cố.
- Nén truyền tải bằng Opus/FLAC nếu CPU cho phép; giữ WAV chỉ cho debug/chuẩn hóa server.
- Server: load model một lần; worker process riêng; cache model; giới hạn concurrency phù hợp RAM/VRAM.
- Whisper: dùng Groq cho demo nếu có consent; production nhạy cảm nên cân nhắc ASR on-prem. Với RTX 2050 4 GB, dùng faster-whisper base/small int8 và concurrency 1.
- PostgreSQL: keyset pagination thay offset khi alert lớn; partition `alerts` theo tháng; index partial cho `pending`; thống kê tổng hợp/materialized view.
- Frontend: debounce/filter, lazy-load chart/audio, virtualize danh sách dài, không reload cả trang sau refresh token.
- Audio: lifecycle tiering; xóa clip không phải chứng cứ theo retention, giữ hash/metadata lâu hơn.

## 13. Lộ trình đề xuất

### Giai đoạn 0 — 1 đến 3 ngày: chặn rủi ro

- Rotate secret/key/password; vô hiệu key bị lộ.
- Xóa `/auth/dump`, khóa audio, social login mock và test endpoint.
- CORS allowlist, HTTPS cho server, đổi demo password.
- Tắt simulator ở production.
- Tạo `.env.example` không có secret và kiểm tra secret trong CI.

Tiêu chí xong: không còn secret thật trong working tree/history phát hành; kiểm thử quyền xác nhận user không thể đọc alert/audio ngoài phạm vi.

### Giai đoạn 1 — 1 đến 2 tuần: làm nền tảng chạy ổn

- Chuẩn hóa migration và đường dẫn lưu file.
- Queue AI, idempotency, retry, health checks và structured logging.
- Chuẩn hóa contract nhãn/confidence/model version.
- Test unit/integration cho auth, RBAC, upload, alert state machine, parent scope.
- CI build/test/secret scan/dependency scan; build firmware riêng.
- Backup/restore PostgreSQL và object storage được diễn tập.

Tiêu chí xong: deploy mới từ máy sạch; restart giữa lúc phân tích không mất job; restore được dữ liệu; test quyền chạy tự động.

### Giai đoạn 2 — 2 đến 6 tuần: chứng minh AI

- Thu thập và gán nhãn dataset có đồng thuận.
- Xây data manifest/version, loại trùng, split theo người/phòng.
- Benchmark Edge, YAMNet+rule và model mới trên cùng test set.
- Calibration threshold theo lớp và theo môi trường.
- Lưu phản hồi `confirmed/false_alarm` thành dataset review, không tự train trực tiếp từ nhãn chưa kiểm duyệt.
- Pilot nhỏ ở 1–2 khu vực với human-in-the-loop.

Tiêu chí xong: có model card, confusion matrix, false alert/giờ, miss rate, latency p50/p95 và tiêu chuẩn go/no-go.

### Giai đoạn 3 — 1 đến 3 tháng: hoàn thiện sản phẩm

- Multi-school/site, escalation/SLA/ca trực.
- OTA firmware có chữ ký, device registry và revoke.
- Audit chứng cứ bất biến, retention/consent, báo cáo quản trị.
- Observability: metrics, tracing, error tracking, dashboard và alert hạ tầng.
- Load test nhiều thiết bị; HA cho DB/object storage/API nếu cần.
- PWA/mobile push chỉ sau khi quyền và offline flow đã kiểm thử.

## 14. Những gì phù hợp và những gì đang bị hạn chế

### Phù hợp

- Đồ án nghiên cứu, demo hội đồng, proof-of-concept IoT + AI.
- Pilot có giám sát chặt, ít thiết bị, mạng LAN ổn định, người thật xác minh mọi cảnh báo.
- Nghiên cứu so sánh AI biên và AI server.
- Dashboard quản lý sự kiện âm thanh theo khu vực.

### Chưa phù hợp

- Dùng làm hệ thống quyết định kỷ luật tự động.
- Giám sát diện rộng 24/7 hoặc cam kết an toàn sinh mạng.
- Lưu/phát audio học sinh khi chưa có chính sách pháp lý và phân quyền.
- Chạy production trên laptop cá nhân.
- Khẳng định “độ chính xác X%” từ trường confidence hiện tại.
- Hoạt động hoàn toàn offline khi frontend còn phụ thuộc CDN và server có thể phụ thuộc Groq/TF Hub lúc khởi động.

### Giới hạn kỹ thuật cụ thể

- 12 GB RAM và RTX 2050 4 GB chỉ đủ demo nhẹ; dễ nghẽn khi nhiều file cùng lúc.
- Firmware dùng IP LAN ghi cứng; đổi mạng là mất kết nối.
- Một token thiết bị dùng chung làm một thiết bị bị lộ ảnh hưởng toàn hệ thống.
- Không có buffer upload bền vững khi mất mạng.
- Không có heartbeat thực tế rõ ràng để cập nhật online/offline/pin.
- Không có dataset/model artifact và benchmark có thể tái lập.
- Confidence chưa calibration, rule rải trên ba ngôn ngữ.
- Không có automated test, CI/CD, monitoring và disaster recovery đã kiểm chứng.

## 15. Danh sách ưu tiên thực dụng

Nếu chỉ có nguồn lực làm 10 việc, nên làm theo thứ tự này:

1. Rotate/xóa secret khỏi Git và firmware.
2. Đóng endpoint dump/audio/test; sửa social login và SignalR RBAC.
3. Chuẩn hóa migration + bỏ `EnsureCreated()`/ALTER tự động.
4. Sửa storage/path, đưa audio sang object storage và áp retention.
5. Đưa AI job vào queue bền vững.
6. Chuẩn hóa taxonomy, confidence và model/decision version.
7. Tạo golden dataset/test set thực tế; đo precision/recall/F1/false alarm per hour.
8. Viết test auth/RBAC/upload/state machine và CI.
9. Device credential riêng + TLS + OTA ký số.
10. Pilot human-in-the-loop, ghi phản hồi và chỉ mở rộng khi đạt KPI.

## 16. Kết luận cuối

Dự án có nền tảng tốt cho một đề tài NCKH vì đã kết nối được nhiều mảng khó: IoT, xử lý tín hiệu, Edge AI, ASR tiếng Việt, backend realtime và dashboard. Điểm yếu không nằm ở thiếu tính năng giao diện mà nằm ở **độ tin cậy, bảo mật, quản trị dữ liệu và khả năng chứng minh chất lượng AI**.

Vì vậy, không nên ưu tiên thêm nhiều màn hình hoặc thêm model mới ngay. Thứ tự đúng là: khóa bảo mật -> chuẩn hóa dữ liệu/contract -> làm pipeline vận hành bền -> đo AI bằng dataset độc lập -> pilot có người xác minh -> sau đó mới mở rộng tính năng và số thiết bị.
