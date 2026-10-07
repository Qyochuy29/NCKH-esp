# Sửa và tối ưu AI — 08/10/2026

## Kết quả đang chạy

- Local Faster-Whisper `large-v3`, RTX 3060, CUDA `float16`. Đã xác minh bằng nhận dạng thực tế, không chỉ kiểm tra model tải được.
- YAMNet chạy CPU, xử lý theo khối 30,72 giây với phần chồng ở biên; không nạp toàn bộ tensor trung gian của audio dài vào một lần.
- Context provider `rules`, phiên bản `rules-3.0`. Chưa cài thêm LLM suy luận; không tuyên bố đã hiểu mọi ngữ cảnh.
- Audio gốc giữ nguyên. Các kiểm tra lần này chỉ gọi AI với file đã có, không upload hay tạo bản ghi database.

## Các file đã sửa

| File | Thay đổi |
|---|---|
| `ai-training/context_analysis.py` | Xử lý phủ định mở rộng; phân tích theo câu; phạm vi trích dẫn; dùng timestamp từ ASR khi khớp; transcript yếu không tự ép HIGH; tách dấu hiệu nghi ngờ khỏi xác nhận; sửa xử lý nhạc nền; mở rộng lời xúc phạm; giảm phép ghép sự kiện không liên quan. |
| `ai-training/transcription.py` | Bỏ prompt ở lần giải mã đầu; clip có speech và dài tối đa 30 giây được giải mã đầy đủ để VAD không bỏ lời chửi; giữ cơ chế thử lại transcript đáng ngờ và audit cả hai lần; đoạn bị loại làm chất lượng toàn kết quả cần xem lại. |
| `ai-training/audio_events.py` | Tách `baby_cry`; giữ lớp YAMNet gốc trong sự kiện; cache class map; xử lý theo khối và giữ timestamp toàn file. |
| `ai-training/asr_runtime.py` | CUDA mặc định float16, CPU fallback int8; ghi nhận device đã inference và nguyên nhân fallback. |
| `ai-training/windows_cuda.py` | Phục hồi đường dẫn driver CUDA riêng cho ứng dụng khi thiếu DLL công khai; không tự sửa file Windows. |
| `ai-training/server.py` | Kiểm tra inference GPU lúc startup; health trả compute type, device inference và nguyên nhân fallback. |
| `ai-training/analysis_pipeline.py` | Truyền word timestamps cho context; hash audio theo luồng; giới hạn thời lượng giải mã, đo thời gian mỗi tầng. |
| `ai-training/inspect_recent.py` | Thay các import API cũ bị lỗi bằng gọi dịch vụ AI hiện tại; không nạp thêm model, không tạo lịch sử. |
| `ai-training/Dockerfile` | Đóng gói thêm helper Windows; trên Linux helper tự bỏ qua. |
| `frontend/dung-chung.js` | Nhận phiên bản rules mới và nhãn tiếng trẻ nhỏ khóc; giữ báo cáo gọn, cảnh báo kết quả cũ chưa được phân tích lại. |
| `ai-training/tests/test_context.py` | Thêm các tình huống phủ định, trích dẫn, ASR yếu, baby cry, nhạc nền và timestamp theo từ. |
| `ai-training/tests/test_transcription_contract.py` | Kiểm tra clip ngắn không bị VAD cắt mất và không thêm prompt định hướng nội dung. |
| `ai-training/tests/test_pipeline_integrity.py` | Kiểm tra từ chối audio quá dài nhưng không thay đổi file gốc. |

## GPU và Windows

Driver NVIDIA vẫn nhận RTX 3060 nhưng thiếu `C:\Windows\System32\nvcuda.dll` và `nvml.dll`.
Đã xác minh chữ ký hợp lệ rồi khôi phục đúng hai file thiếu từ driver hiện có trong DriverStore:
`nvcuda_loader64.dll` → `nvcuda.dll`, và `nvml.dll` → `nvml.dll`.
Không ghi đè file hiện có, không cài lại driver, không khởi động lại máy.

Thử riêng CUDA 12.8 tại `.runtime/cuda-compat` không giải quyết lỗi trước khi khôi phục DLL.
Thư mục đó chỉ là artifact chẩn đoán, không được dịch vụ đưa vào đường dẫn thư viện.
Dịch vụ dùng thư viện NVIDIA đã cài trong `.venv` và driver hệ thống.

## API kết luận

`school_violence_detected` biểu thị dấu hiệu nghi ngờ, không phải xác nhận sự việc:

- `true`: có dấu hiệu xung đột thể chất hoặc lời xúc phạm được đánh dấu nghi ngờ.
- `null`: chưa kết luận được, cần xem lại.
- `false`: chưa có đủ bằng chứng trong dữ liệu đã phân tích; không phải cam kết an toàn.

Các trường riêng: `school_violence_confirmed=false`, `school_context_verified=false`,
`possible_verbal_abuse`, `possible_physical_violence`, `has_profanity`, `has_insults`,
`detection_status`, `risk_level`, `evidence` và `analysis_version`.
Điểm YAMNet vẫn là điểm sự kiện, không phải xác suất bạo lực.

## Kiểm thử

- 44 unit test đạt: `python -m unittest discover -s ai-training/tests`.
- 42 audio hồi quy đã có đạt điều kiện kiểm tra, toàn bộ original hash giữ nguyên, inference chạy CUDA.
- 9 kiểm tra chọn lọc (hai video thực tế của người dùng và bảy mẫu nói cũng có trong bộ hồi quy): đạt điều kiện kiểm tra.
- Hai video từng chép thành “subscribe” đã chép được các lời chửi/xúc phạm; đều REVIEW, có lời xúc phạm và cần người xem lại. Một số từ vẫn có thể nghe sai.
- Thời gian quan sát cho hai clip: khoảng 3,5–3,6 giây ở lần kiểm tra GPU. Không phải benchmark tốc độ trên mọi file.
- YAMNet thật trên audio 65 giây: xử lý toàn file và theo khối đều có 135 × 521 scores; sai khác lớn nhất khoảng `7.45e-7`.
- Frontend JavaScript parse được; báo cáo chỉ có một mục kỹ thuật đóng; trang lịch sử đăng nhập được và không có page error trong kiểm tra.
- Docker Compose CPU/GPU kiểm tra cấu hình đạt; không tuyên bố đã build/chạy engine Docker.

Bằng chứng: `.runtime/validation/upgrade-results.json` và `upgrade-regression.json`.
Các mẫu bình thường trong một số bộ kiểm tra chỉ yêu cầu không HIGH; REVIEW cũng tính đạt.
Các kết quả này không phải độ chính xác/WER/precision/recall trên tập đánh giá độc lập.

## Chạy và kiểm tra

Website: `http://localhost:3000`. Mở `Chay_Website_Windows.bat` khi cần khởi động.
Nhấn Ctrl+F5 để tải giao diện mới; kết quả cũ trong database không tự đổi.
Upload audio/video ở trang Cảnh báo để tạo lần phân tích bằng bản mới.

Kiểm tra file gốc đã có mà không thêm lịch sử:

```powershell
.venv/Scripts/python.exe ai-training/inspect_recent.py TEN_FILE_TRONG_UPLOADS.mp4
Invoke-RestMethod http://127.0.0.1:5000/health
```

`MAX_AUDIO_SECONDS` mặc định 1800 (30 phút), có thể cấu hình cao hơn nếu đủ tài nguyên.
`WHISPER_MODEL_SIZE`, `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE`, `ASR_MODE` vẫn cấu hình được.
Nếu CUDA lỗi, model giữ nguyên tên và fallback CPU; không tự gửi audio lên cloud.

## Giới hạn còn lại

- Rules chưa thay thế mô hình suy luận ngữ cảnh; các cách nói chưa được bao phủ có thể bị bỏ sót.
- ASR và YAMNet có thể nhận sai khi chồng tiếng, nhiễu, tiếng nhỏ, giọng địa phương hoặc nhạc.
- Chưa có speaker diarization thật; không gán người nói giả.
- Không thể xác minh địa điểm trường học, danh tính học sinh hay sự việc diễn kịch chỉ từ pipeline này.
- Chưa có benchmark độc lập để tuyên bố một tỷ lệ chính xác. REVIEW/HIGH vẫn cần kiểm tra bằng audio gốc.
