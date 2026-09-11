import re
import os

source_file = 'c:/NKKH/esp32-voice-recorder-20260828T083632Z-1-001/esp32-voice-recorder/codetrainplatf_main.cpp'
target_file = 'c:/NKKH/esp32-voice-recorder-20260828T083632Z-1-001/esp32-voice-recorder/src/main.cpp'

with open(source_file, 'r', encoding='utf-8') as f:
    source = f.read()

with open(target_file, 'r', encoding='utf-8') as f:
    target = f.read()

# 1. Extract parts from source
vars_part = re.search(r'(// ============================================================\n// MODEL CONTRACT.*?)(?=// ============================================================\n// PHAT HIEN VA DAP / GO BAN)', source, re.DOTALL).group(1)
impact_vars_part = re.search(r'(// ============================================================\n// PHAT HIEN VA DAP / GO BAN.*?)(?=// ============================================================\n// LABELS)', source, re.DOTALL).group(1)
labels_part = re.search(r'(// ============================================================\n// LABELS.*?)(?=// ============================================================\n// HELPERS)', source, re.DOTALL).group(1)
analyze_impact_func = re.search(r'(// ============================================================\n// PHAN TICH XUNG VA DAP / GO BAN.*?)(?=// ============================================================\n// FFT 512)', source, re.DOTALL).group(1)
dsp_part = re.search(r'(// ============================================================\n// FFT 512 - chi dung de tao Log-Mel cho model.*?)(?=// ============================================================\n// ALERT)', source, re.DOTALL).group(1)

# Modify vars_part: remove `static int16_t *g_audio = nullptr;` because we'll point it to wavBuf
vars_part = vars_part.replace('static int16_t *g_audio = nullptr;', 'static int16_t *g_audio = nullptr; // Will point to wavBuf')

# 2. Re-write the target file
new_target = f"""/*
  ESP32-S3 + INMP441 - Ghi âm và gửi WAV lên website để AI phân tích
  Tích hợp Edge AI (Hybrid)
*/

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiManager.h>
#include <HTTPClient.h>
#include "driver/i2s.h"

// AI Includes
#include <esp_heap_caps.h>
#include <math.h>
#include <MicroTFLite.h>
#include "4NHAN91.h"

// ---------- CẤU HÌNH CHÂN I2S ----------
#define I2S_WS   4
#define I2S_SD   5
#define I2S_SCK  6
#define I2S_PORT I2S_NUM_0

// ---------- CẤU HÌNH GHI ÂM ----------
#define SAMPLE_RATE      16000
#define RECORD_SECONDS   5 // Changed to 5 seconds to match Edge AI model
#define SAMPLES_TOTAL    (SAMPLE_RATE * RECORD_SECONDS)    // 80000 samples int16
#define BUFFER_BYTES     (SAMPLES_TOTAL * sizeof(int16_t)) // 160000 bytes
#define I2S_READ_SAMPLES 1024

// ---------- CẤU HÌNH SERVER ----------
const char* serverBase    = "http://192.168.1.9:3000";
const char* deviceToken   = "your_secure_device_token_123";
const char* deviceId      = "Cam-HL1";

// ---------- AUDIO BUFFER (PSRAM) ----------
uint8_t* wavBuf = nullptr;
int32_t i2sReadBuf[I2S_READ_SAMPLES];

#define BUTTON_BOOT 0  // Nút BOOT GPIO0 — giữ lúc khởi động để xóa WiFi

// ---------- AI VARIABLES ----------
{vars_part}
{impact_vars_part}
{labels_part}

// ============================================================
//  I2S INIT
// ============================================================
void i2sInit() {{
  i2s_config_t cfg = {{
    .mode                 = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate          = SAMPLE_RATE,
    .bits_per_sample      = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format       = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count        = 8,
    .dma_buf_len          = 1024,
    .use_apll             = false
  }};
  i2s_pin_config_t pins = {{
    .bck_io_num   = I2S_SCK,
    .ws_io_num    = I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num  = I2S_SD
  }};
  i2s_driver_install(I2S_PORT, &cfg, 0, NULL);
  i2s_set_pin(I2S_PORT, &pins);
}}

// ============================================================
//  WAV HEADER
// ============================================================
void writeWavHeader(uint8_t* hdr, uint32_t dataSize) {{
  uint32_t fileSize   = dataSize + 36;
  uint16_t channels   = 1;
  uint32_t sr         = SAMPLE_RATE;
  uint16_t bps        = 16;
  uint32_t byteRate   = sr * channels * bps / 8;
  uint16_t blockAlign = channels * bps / 8;
  uint16_t audioFmt   = 1;
  uint32_t sub1Size   = 16;

  memcpy(hdr,      "RIFF", 4); memcpy(hdr+4,  &fileSize,   4);
  memcpy(hdr+8,    "WAVEfmt ", 8);
  memcpy(hdr+16,   &sub1Size,  4); memcpy(hdr+20, &audioFmt,   2);
  memcpy(hdr+22,   &channels,  2); memcpy(hdr+24, &sr,         4);
  memcpy(hdr+28,   &byteRate,  4); memcpy(hdr+32, &blockAlign, 2);
  memcpy(hdr+34,   &bps,       2);
  memcpy(hdr+36,   "data",     4); memcpy(hdr+40, &dataSize,   4);
}}

// ============================================================
//  GHI ÂM
// ============================================================
float recordAudio(int16_t &peakOut) {{
  int16_t* pcm = reinterpret_cast<int16_t*>(wavBuf + 44);
  size_t samplesWritten = 0;
  int64_t sumSquares = 0;
  int32_t peak = 0;
  uint32_t clippedSamples = 0;

  while (samplesWritten < SAMPLES_TOTAL) {{
    const size_t samplesRequested = min(
      static_cast<size_t>(I2S_READ_SAMPLES),
      static_cast<size_t>(SAMPLES_TOTAL) - samplesWritten
    );

    size_t bytesRead = 0;
    const esp_err_t result = i2s_read(
      I2S_PORT,
      i2sReadBuf,
      samplesRequested * sizeof(int32_t),
      &bytesRead,
      portMAX_DELAY
    );

    if (result != ESP_OK || bytesRead == 0) {{
      Serial.printf("[REC] I2S error: %d\\n", static_cast<int>(result));
      return -120.0f;
    }}

    const size_t samplesRead = bytesRead / sizeof(int32_t);
    for (size_t i = 0; i < samplesRead && samplesWritten < SAMPLES_TOTAL; i++) {{
      int32_t sample = i2sReadBuf[i] >> 14;
      sample = constrain(sample, -32768, 32767);

      const int16_t sample16 = static_cast<int16_t>(sample);
      pcm[samplesWritten++] = sample16;
      sumSquares += static_cast<int32_t>(sample16) * sample16;

      const int32_t av = (sample16 < 0) ? -(int32_t)sample16 : (int32_t)sample16;
      if (av > peak) peak = av;
      if (av >= 32700) ++clippedSamples;
    }}
  }}
  
  g_clippedSamples = clippedSamples;
  g_audioClipped = (clippedSamples > 0);
  peakOut = (int16_t)((peak > 32767) ? 32767 : peak);
  g_audioLikelyImpact = false;
  
  double rms = sqrt((double)sumSquares / (double)SAMPLES_TOTAL);
  if (rms > 1e-12) return (float)(20.0 * log10(rms));
  return -120.0f;
}}

// ============================================================
//  UPLOAD
// ============================================================
bool uploadToWebsite(uint8_t* wavData, size_t wavSize, const char* detectedClass, float confidence) {{
  if (WiFi.status() != WL_CONNECTED) return false;

  String eventId = String(deviceId) + "_" + String(millis());
  
  // Note: sending confidence and type up so the server knows why Edge AI sent it
  String url = String(serverBase)
    + "/api/alerts/device-recording"
    + "?device_id=" + String(deviceId)
    + "&type=analyze"
    + "&confidence=" + String(confidence, 2)
    + "&event_id=" + eventId
    + "&edge_class=" + String(detectedClass);

  Serial.printf("[UPLOAD] POST %s (%d bytes)\\n", url.c_str(), wavSize);

  WiFiClient client;
  HTTPClient http;
  if (!http.begin(client, url)) return false;
  
  http.addHeader("Content-Type", "audio/wav");
  http.addHeader("X-Device-Token", deviceToken);
  http.setConnectTimeout(5000);
  http.setTimeout(65000);

  int code = http.sendRequest("POST", wavData, wavSize);
  if (code > 0) {{
    Serial.printf("[UPLOAD] HTTP %d: %s\\n", code, http.getString().c_str());
  }} else {{
    Serial.printf("[UPLOAD] Lỗi %d: %s\\n", code, http.errorToString(code).c_str());
  }}
  http.end();
  return code >= 200 && code < 300;
}}

// ============================================================
// AI DSP FUNCTIONS
// ============================================================
{analyze_impact_func}
{dsp_part}

// ============================================================
//  SETUP
// ============================================================
void setup() {{
  Serial.begin(115200);
  delay(3000);
  Serial.println("\\n\\n=== ESP32 BOOT (Hybrid AI) ===");

  WiFiManager wm;
  pinMode(BUTTON_BOOT, INPUT_PULLUP);
  bool held = false;
  for (int s = 3; s > 0; s--) {{
    Serial.printf("Giữ BOOT để xóa WiFi... còn %d giây\\n", s);
    unsigned long t0 = millis();
    while (millis() - t0 < 1000) {{
      if (digitalRead(BUTTON_BOOT) == LOW) held = true;
      delay(10);
    }}
  }}
  if (held) {{ Serial.println("Xóa WiFi!"); wm.resetSettings(); }}

  if (!wm.autoConnect("ESP32-VoiceRecorder")) {{
    Serial.println("Không kết nối WiFi, restart...");
    delay(2000); ESP.restart();
  }}
  while (WiFi.localIP()[0] == 0) {{ Serial.print("."); delay(500); }}
  Serial.printf("\\nIP: %s\\n", WiFi.localIP().toString().c_str());

  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(true);

  i2sInit();

  // PSRAM Allocation
  wavBuf = (uint8_t*) ps_malloc(BUFFER_BYTES + 44);
  if (!wavBuf) {{ Serial.println("Loi cap phat wavBuf"); while(1); }}
  
  // Point g_audio directly to the PCM data in wavBuf to save RAM
  g_audio = reinterpret_cast<int16_t*>(wavBuf + 44);
  
  g_melPower = (float *)heap_caps_malloc(N_INPUTS * sizeof(float), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  g_melFilter = (float *)heap_caps_malloc(N_MELS * N_BINS * sizeof(float), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  g_tensorArena = (uint8_t *)heap_caps_malloc(TENSOR_ARENA_SIZE, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  
  if (!g_melPower || !g_melFilter || !g_tensorArena) {{
    Serial.println("Loi cap phat PSRAM cho AI"); while(1);
  }}

  initFFT();
  initMelFilterBank();
  
  Serial.println("Khoi tao TensorFlow Lite Micro...");
  if (!ModelInit(g_audio_model_data_4classes_5s, g_tensorArena, TENSOR_ARENA_SIZE)) {{
      Serial.println("ModelInit that bai."); while(1);
  }}

  Serial.println("ESP32 Ready — Hybrid AI Mode");
}}

// ============================================================
//  LOOP
// ============================================================
void loop() {{
  Serial.printf("[REC] Dang ghi am %d giay...\\n", RECORD_SECONDS);
  writeWavHeader(wavBuf, BUFFER_BYTES);
  
  int16_t peak = 0;
  float rmsDbfs = recordAudio(peak);
  
  if (rmsDbfs < -60.0f) {{
    Serial.printf("[REC] Yên tĩnh (%.1f dBFS), bỏ qua.\\n", rmsDbfs);
    delay(20);
    return;
  }}

  Serial.printf("[REC] Phát hiện âm thanh (%.1f dBFS), phân tích Edge AI...\\n", rmsDbfs);
  
  int16_t* original_audio = g_audio;
  bool shouldUpload = false;
  const char* uploadClass = "";
  float maxConfidence = 0.0f;

  int numChunks = SAMPLES_TOTAL / N_SAMPLES;
  if (numChunks == 0) numChunks = 1;

  for (int chunk = 0; chunk < numChunks; chunk++) {{
      Serial.printf(">>> Phân tích nửa %d (từ giây %d đến %d)...\\n", chunk + 1, chunk * 5, (chunk + 1) * 5);
      
      g_audio = original_audio + (chunk * N_SAMPLES);

      analyzeImpact(rmsDbfs, peak);

      if (g_audioLikelyImpact) {{
          Serial.println("=> PHAT HIEN XUNG VA DAP / GO BAN -> Ghi nhận (DAP_PHA)");
          shouldUpload = true;
          uploadClass = "DAP_PHA";
          maxConfidence = 1.0f;
          break;
      }}

      if (g_audioClipped && !g_audioLikelyImpact) {{
          Serial.println("=> BO QUA: tin hieu bi bao hoa keo dai.");
          continue;
      }}

      if (!buildLogMelAndSetModelInput()) {{
          Serial.println("Tao feature that bai.");
          continue;
      }}

      if (!ModelRunInference()) {{
          Serial.println("ModelRunInference FAILED");
          continue;
      }}

      float prob[N_CLASSES];
      for (int i = 0; i < N_CLASSES; ++i) {{
          prob[i] = ModelGetOutput(i);
          if (!isfinite(prob[i])) prob[i] = 0.0f;
          if (prob[i] < 0.0f) prob[i] = 0.0f;
          if (prob[i] > 1.0f) prob[i] = 1.0f;
      }}

      Serial.println("============= KET QUA EDGE AI =============");
      for(int i=0; i<N_CLASSES; i++) {{
        Serial.printf("%-10s: %6.2f %%\\n", LABELS[i], prob[i] * 100.0f);
      }}

      if (prob[AUDIO_CLASS_KHOC] >= 0.40f) {{
          Serial.println("=> NHAN: KHOC");
          shouldUpload = true;
          uploadClass = "KHOC";
          maxConfidence = prob[AUDIO_CLASS_KHOC];
          break;
      }}
      else if (prob[AUDIO_CLASS_DAP_PHA] >= 0.40f) {{
          Serial.println("=> NHAN: DAP_PHA");
          shouldUpload = true;
          uploadClass = "DAP_PHA";
          maxConfidence = prob[AUDIO_CLASS_DAP_PHA];
          break;
      }}
      else if (prob[AUDIO_CLASS_CHUI_NHAU] >= 0.40f) {{
          Serial.println("=> NHAN: CHUI_NHAU");
          shouldUpload = true;
          uploadClass = "CHUI_NHAU";
          maxConfidence = prob[AUDIO_CLASS_CHUI_NHAU];
          break;
      }}
      else {{
          Serial.println("=> Không rõ hoặc Tiếng Ồn.");
      }}
  }}

  g_audio = original_audio;

  if (shouldUpload) {{
      Serial.printf("=> TỔNG KẾT: Có tiếng đáng ngờ (%s). Đang gửi toàn bộ 10s lên Web...\\n", uploadClass);
      uploadToWebsite(wavBuf, BUFFER_BYTES + 44, uploadClass, maxConfidence);
  }} else {{
      Serial.println("=> TỔNG KẾT: Toàn bộ 10s là Tiếng ồn. Bỏ qua không gửi.");
  }}

  delay(20);
}}
"""

with open(target_file, 'w', encoding='utf-8') as f:
    f.write(new_target)

print("Merge done!")
