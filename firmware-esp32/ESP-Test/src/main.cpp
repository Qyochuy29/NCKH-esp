#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <driver/i2s.h>

// ==============================================================
// 1. CẤU HÌNH WIFI & SERVER  ← THAY ĐỔI CÁC GIÁ TRỊ NÀY
// ==============================================================
const char* ssid         = "TEN_WIFI_CUA_BAN";   // Tên WiFi
const char* password     = "MAT_KHAU_WIFI";       // Mật khẩu WiFi

// IP máy tính đang chạy Docker (không phải 127.0.0.1)
// Mở CMD: ipconfig → IPv4 Address, ví dụ: 192.168.1.100
const char* serverHost   = "192.168.1.9";
const int   serverPort   = 3000;
const char* uploadPath   = "/api/alerts/upload";

// Device Token phải KHỚP với DeviceToken trong appsettings.json của backend
const char* deviceToken  = "your_secure_device_token_123";

// ==============================================================
// 2. CẤU HÌNH CHÂN MICRO I2S (INMP441)
// ==============================================================
#define I2S_SCK   15   // Dây SCK (Xanh lá)
#define I2S_WS    16   // Dây WS  (Vàng)
#define I2S_SD    17   // Dây SD  (Trắng)
#define I2S_PORT  I2S_NUM_0

// ==============================================================
// 3. THÔNG SỐ ÂM THANH (YAMNet yêu cầu 16000Hz, Mono)
// ==============================================================
#define SAMPLE_RATE     16000
#define RECORD_TIME_SEC 4                                        // Ghi âm mỗi 4 giây
#define BUFFER_SIZE     (SAMPLE_RATE * RECORD_TIME_SEC * 2)     // 128,000 bytes (16-bit mono)

uint8_t* audioBuffer = nullptr;

// Khai báo hàm
void connectWiFi();
void initI2S();
void recordAndSend();
void createWavHeader(byte* header, int waveDataSize);

// ==============================================================
void setup() {
    Serial.begin(115200);
    delay(2000);

    Serial.println("\n--- KHOI DONG HE THONG THU AM ESP32 ---");
    Serial.printf("Server: http://%s:%d%s\n", serverHost, serverPort, uploadPath);

    audioBuffer = (uint8_t*)malloc(BUFFER_SIZE);
    if (!audioBuffer) {
        Serial.println("LOI: Khong du RAM cho Audio Buffer!");
        while (true) delay(1000);
    }
    Serial.printf("Audio Buffer: %d bytes OK\n", BUFFER_SIZE);

    connectWiFi();
    initI2S();

    Serial.println("He thong san sang thu am!\n");
}

void loop() {
    recordAndSend();
    delay(500);  // Nghỉ ngắn trước chu kỳ tiếp theo
}

// ==============================================================
void connectWiFi() {
    Serial.printf("Ket noi WiFi: %s\n", ssid);
    WiFi.begin(ssid, password);
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
        if (++attempts > 40) {
            Serial.println("\nKhong ket noi duoc WiFi! Reset...");
            ESP.restart();
        }
    }
    Serial.printf("\nWiFi OK! IP: %s\n", WiFi.localIP().toString().c_str());
}

// ==============================================================
void initI2S() {
    i2s_config_t cfg = {
        .mode                 = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
        .sample_rate          = SAMPLE_RATE,
        .bits_per_sample      = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format       = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count        = 8,
        .dma_buf_len          = 1024,
        .use_apll             = false,
        .tx_desc_auto_clear   = false,
        .fixed_mclk           = 0
    };
    i2s_pin_config_t pins = {
        .bck_io_num   = I2S_SCK,
        .ws_io_num    = I2S_WS,
        .data_out_num = I2S_PIN_NO_CHANGE,
        .data_in_num  = I2S_SD
    };
    i2s_driver_install(I2S_PORT, &cfg, 0, NULL);
    i2s_set_pin(I2S_PORT, &pins);
    Serial.println("Micro I2S OK.");
}

// ==============================================================
// Tạo WAV header chuẩn 44 bytes
// ==============================================================
void createWavHeader(byte* h, int dataSize) {
    uint32_t fileSize  = dataSize + 36;
    uint32_t byteRate  = SAMPLE_RATE * 2;  // 16-bit mono
    uint16_t blockAlign = 2;
    uint16_t bitsPerSample = 16;
    uint16_t numChannels = 1;
    uint16_t audioFormat = 1;  // PCM

    memcpy(h,      "RIFF", 4);
    memcpy(h + 4,  &fileSize,      4);
    memcpy(h + 8,  "WAVE", 4);
    memcpy(h + 12, "fmt ", 4);
    uint32_t fmtSize = 16;
    memcpy(h + 16, &fmtSize,       4);
    memcpy(h + 20, &audioFormat,   2);
    memcpy(h + 22, &numChannels,   2);
    memcpy(h + 24, (uint32_t*)&SAMPLE_RATE, 4);
    memcpy(h + 28, &byteRate,      4);
    memcpy(h + 32, &blockAlign,    2);
    memcpy(h + 34, &bitsPerSample, 2);
    memcpy(h + 36, "data", 4);
    memcpy(h + 40, &dataSize,      4);
}

// ==============================================================
// Ghi âm và gửi lên backend
// ==============================================================
void recordAndSend() {
    // --- Bước 1: Ghi âm ---
    Serial.printf("\n[1/3] Ghi am %d giay...\n", RECORD_TIME_SEC);
    size_t bytesRead = 0, total = 0;
    while (total < BUFFER_SIZE) {
        i2s_read(I2S_PORT, (char*)(audioBuffer + total),
                 BUFFER_SIZE - total, &bytesRead, portMAX_DELAY);
        total += bytesRead;
    }
    Serial.printf("     Ghi xong: %d bytes\n", total);

    // --- Bước 2: Kết nối TCP đến backend ---
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("Mat ket noi WiFi! Bo qua...");
        connectWiFi();
        return;
    }

    Serial.printf("[2/3] Ket noi %s:%d...\n", serverHost, serverPort);
    WiFiClient client;
    if (!client.connect(serverHost, serverPort)) {
        Serial.println("     LOI: Khong ket noi duoc server!");
        Serial.println("     Kiem tra: IP dung chua? Docker dang chay chua?");
        return;
    }
    Serial.println("     Ket noi OK!");

    // --- Bước 3: Tạo multipart/form-data và gửi ---
    const String boundary = "ESP32AudioBoundary";

    // Phần đầu của multipart
    String partHead = "--" + boundary + "\r\n";
    partHead += "Content-Disposition: form-data; name=\"audio\"; filename=\"esp32_audio.wav\"\r\n";
    partHead += "Content-Type: audio/wav\r\n\r\n";

    // Phần kết thúc của multipart
    String partTail = "\r\n--" + boundary + "--\r\n";

    // WAV header (44 bytes)
    byte wavHeader[44];
    createWavHeader(wavHeader, BUFFER_SIZE);

    // Tính tổng Content-Length
    uint32_t contentLength = partHead.length() + 44 + BUFFER_SIZE + partTail.length();

    // Gửi HTTP request headers
    client.printf("POST %s HTTP/1.1\r\n", uploadPath);
    client.printf("Host: %s:%d\r\n", serverHost, serverPort);
    client.printf("Content-Type: multipart/form-data; boundary=%s\r\n", boundary.c_str());
    client.printf("X-Device-Token: %s\r\n", deviceToken);
    client.printf("Content-Length: %u\r\n", contentLength);
    client.print("Connection: close\r\n");
    client.print("\r\n");  // Kết thúc headers

    // Gửi body
    client.print(partHead);          // Multipart part header
    client.write(wavHeader, 44);     // WAV file header (44 bytes)

    // Gửi audio data theo từng chunk 4KB để tránh watchdog timeout
    const int CHUNK = 4096;
    uint8_t* ptr = audioBuffer;
    uint32_t remaining = BUFFER_SIZE;
    Serial.print("[3/3] Dang gui audio ");
    while (remaining > 0) {
        uint32_t toSend = min((uint32_t)CHUNK, remaining);
        client.write(ptr, toSend);
        ptr += toSend;
        remaining -= toSend;
        Serial.print(".");
        delay(1);  // Yield để WiFi stack xử lý
    }
    client.print(partTail);          // Kết thúc multipart
    Serial.println(" Xong!");

    // --- Bước 4: Đọc phản hồi từ server ---
    client.setTimeout(30000);  // Chờ tối đa 30s (AI service cần thời gian phân tích)
    unsigned long waitStart = millis();

    // Chờ server phản hồi
    while (client.available() == 0) {
        if (millis() - waitStart > 60000) {
            Serial.println("LOI: Timeout cho phan hoi server (60s)!");
            client.stop();
            return;
        }
        delay(100);
    }

    // Đọc dòng status HTTP/1.1 200 OK
    String statusLine = client.readStringUntil('\n');
    statusLine.trim();
    Serial.printf("Server: %s\n", statusLine.c_str());

    // Parse HTTP status code
    int statusCode = 0;
    if (statusLine.startsWith("HTTP/")) {
        int spaceIdx = statusLine.indexOf(' ');
        if (spaceIdx != -1) {
            statusCode = statusLine.substring(spaceIdx + 1, spaceIdx + 4).toInt();
        }
    }

    // Bỏ qua phần headers, đọc đến body (sau \r\n\r\n)
    String body = "";
    bool inBody = false;
    while (client.connected() || client.available()) {
        if (client.available()) {
            String line = client.readStringUntil('\n');
            if (!inBody) {
                if (line == "\r" || line.length() == 0) {
                    inBody = true;  // Headers xong, bắt đầu body
                }
            } else {
                body += line;
                if (body.length() > 1000) break;  // Giới hạn để tránh tràn RAM
            }
        }
    }
    client.stop();

    // --- Kết quả ---
    if (statusCode == 200) {
        Serial.println("=== THANH CONG! Server da nhan va phan tich am thanh ===");
        // In tóm tắt kết quả (truncate nếu dài)
        if (body.length() > 500) body = body.substring(0, 500) + "...";
        Serial.println("Ket qua: " + body);
    } else if (statusCode == 401) {
        Serial.println("LOI 401: Device Token sai! Kiem tra lai 'deviceToken' trong code.");
    } else if (statusCode == 0) {
        Serial.println("LOI: Khong doc duoc phan hoi. Kiem tra ket noi mang.");
    } else {
        Serial.printf("LOI HTTP %d: %s\n", statusCode, body.c_str());
    }
}