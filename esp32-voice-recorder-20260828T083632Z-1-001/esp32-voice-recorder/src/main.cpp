/*
  ESP32-S3 + INMP441 - Ghi âm và gửi WAV lên website để AI phân tích
  Tích hợp Edge AI (Hybrid)
*/

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiManager.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include "driver/i2s.h"

// AI Includes
#include <esp_heap_caps.h>
#include <math.h>
#include <MicroTFLite.h>
#include "4NHAN91.h"

// ---------- CẤU HÌNH CHÂN I2S ----------
#define I2S_WS   5
#define I2S_SD   6
#define I2S_SCK  4
#define I2S_PORT I2S_NUM_0

// ---------- CẤU HÌNH GHI ÂM ----------
#define SAMPLE_RATE      16000
#define RECORD_SECONDS   10 // Phục hồi lại 10 giây để nhận diện cả 10s
#define SAMPLES_TOTAL    (SAMPLE_RATE * RECORD_SECONDS)    
#define BUFFER_BYTES     (SAMPLES_TOTAL * sizeof(int16_t)) 
#define I2S_READ_SAMPLES 1024

// ---------- CẤU HÌNH SERVER (Mạng LAN trực tiếp, không qua Cloudflare) ----------
const char* serverBase    = "http://192.168.1.110:3000";
const char* deviceToken   = "your_secure_device_token_123";
const char* deviceId      = "Cam-HL1";


// ---------- AUDIO BUFFER (PSRAM) ----------
uint8_t* wavBuf = nullptr;
int32_t i2sReadBuf[I2S_READ_SAMPLES];

#define BUTTON_BOOT 0  // Nút BOOT GPIO0 — giữ lúc khởi động để xóa WiFi

// ---------- AI VARIABLES ----------
// ============================================================
// MODEL CONTRACT
// ============================================================
static constexpr int SR = AUDIO_MODEL_SAMPLE_RATE;
static constexpr int NUM_SEC = AUDIO_MODEL_DURATION_SECONDS;
static constexpr int N_SAMPLES = AUDIO_MODEL_SAMPLES;
static constexpr int N_FFT = AUDIO_MODEL_N_FFT;
static constexpr int HOP = AUDIO_MODEL_HOP_LENGTH;
static constexpr int N_MELS = AUDIO_MODEL_N_MELS;
static constexpr int N_FRAMES = AUDIO_MODEL_FRAMES;
static constexpr int N_BINS = N_FFT / 2 + 1;
static constexpr int N_INPUTS = N_MELS * N_FRAMES;
static constexpr int N_CLASSES = 4;

// ============================================================
// MEMORY
// ============================================================
static constexpr size_t TENSOR_ARENA_SIZE = 768 * 1024;

static int16_t *g_audio = nullptr; // Will point to wavBuf
static float *g_melPower = nullptr;
static float *g_melFilter = nullptr;
static uint8_t *g_tensorArena = nullptr;

static float g_hann[N_FFT];
static float g_fftReal[N_FFT];
static float g_fftImag[N_FFT];
static float g_fftCos[N_FFT / 2];
static float g_fftSin[N_FFT / 2];
static float g_power[N_BINS];


// ============================================================
// PHAT HIEN VA DAP / GO BAN
// ============================================================
// Khong chi dua vao clipping.
// Phan tich RMS theo block 10 ms de nhan xung ngan kieu "BOP".
static bool g_audioClipped = false;
static uint32_t g_clippedSamples = 0;

static bool g_audioLikelyImpact = false;
static float g_impactPeakNorm = 0.0f;
static float g_impactCrest = 0.0f;
static float g_impactActiveMs = 0.0f;
static float g_impactLongestMs = 0.0f;
static int g_impactTransientCount = 0;

// Block 10 ms @ 16 kHz
static constexpr int IMPACT_BLOCK_MS = 10;
static constexpr int IMPACT_BLOCK_SAMPLES = SR * IMPACT_BLOCK_MS / 1000;
static constexpr int IMPACT_NUM_BLOCKS = N_SAMPLES / IMPACT_BLOCK_SAMPLES;

// Nguong bao thu, de tranh KHOC that bi ep thanh DAP_PHA.
// Co the tune sau neu can.
// FIX: khong bat buoc mic phai clipping moi duoc coi la va dap.
// Nguong phat hien va dap co hoc thuc te (tranh trong nhac, nhip hat gay bao dong gia):
static constexpr float IMPACT_SINGLE_MIN_PEAK_NORM = 0.35f; // Peak >= ~11400
static constexpr float IMPACT_SINGLE_MIN_CREST = 3.8f;       // Xung va dap dot bien
static constexpr float IMPACT_SINGLE_MAX_ACTIVE_MS = 400.0f;
static constexpr float IMPACT_SINGLE_MAX_LONGEST_MS = 250.0f;

static constexpr float IMPACT_MULTI_MIN_PEAK_NORM = 0.25f;  // Peak >= ~8100
static constexpr float IMPACT_MULTI_MIN_CREST = 3.5f;
static constexpr float IMPACT_MULTI_MAX_ACTIVE_MS = 500.0f;
static constexpr float IMPACT_MULTI_MAX_LONGEST_MS = 180.0f;


// ============================================================
// LABELS
// Thu tu phai trung voi file .h:
// 0 KHOC, 1 DAP_PHA, 2 CHUI_NHAU, 3 TIENG_ON
// ============================================================
static const char *LABELS[N_CLASSES] = {
    "KHOC",
    "DAP_PHA",
    "CHUI_NHAU",
    "TIENG_ON"};



// ============================================================
//  I2S INIT
// ============================================================
void i2sInit() {
  i2s_config_t cfg = {
    .mode                 = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate          = SAMPLE_RATE,
    .bits_per_sample      = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format       = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count        = 8,
    .dma_buf_len          = 1024,
    .use_apll             = false
  };
  i2s_pin_config_t pins = {
    .bck_io_num   = I2S_SCK,
    .ws_io_num    = I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num  = I2S_SD
  };
  i2s_driver_install(I2S_PORT, &cfg, 0, NULL);
  i2s_set_pin(I2S_PORT, &pins);
}

// ============================================================
//  WAV HEADER
// ============================================================
void writeWavHeader(uint8_t* hdr, uint32_t dataSize) {
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
}

// ============================================================
//  GHI ÂM
// ============================================================
float recordAudio(int16_t &peakOut) {
  int16_t* pcm = reinterpret_cast<int16_t*>(wavBuf + 44);
  size_t samplesWritten = 0;
  double sumSq = 0.0;
  int32_t peak = 0;
  uint32_t clippedSamples = 0;

  while (samplesWritten < SAMPLES_TOTAL) {
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

    if (result != ESP_OK || bytesRead == 0) {
      Serial.printf("[REC] I2S error: %d\n", static_cast<int>(result));
      return -120.0f;
    }

    const size_t samplesRead = bytesRead / sizeof(int32_t);
    for (size_t i = 0; i < samplesRead && samplesWritten < SAMPLES_TOTAL; i++) {
      // INMP441 gui 24-bit trong slot 32-bit (MSB-first). Dich phai 16 bit lay chuan 16-bit PCM:
      int32_t sample = i2sReadBuf[i] >> 16;
      if (sample > 32767) sample = 32767;
      if (sample < -32768) sample = -32768;

      const int16_t sample16 = static_cast<int16_t>(sample);
      pcm[samplesWritten++] = sample16;

      const int32_t av = (sample16 < 0) ? -(int32_t)sample16 : (int32_t)sample16;
      if (av > peak) peak = av;
      if (av >= 32700) ++clippedSamples;

      const double fv = (double)sample16 / 32768.0;
      sumSq += fv * fv;
    }
  }
  
  g_clippedSamples = clippedSamples;
  // Chi coi la bao hoa keo dai neu co tren 300 mau (~20ms) bi flatline clip lien tuc
  g_audioClipped = (clippedSamples > 300);
  peakOut = (int16_t)((peak > 32767) ? 32767 : peak);
  g_audioLikelyImpact = false;
  
  double rms = sqrt(sumSq / (double)SAMPLES_TOTAL);
  if (rms > 1e-12) return (float)(20.0 * log10(rms));
  return -120.0f;
}

// ============================================================
//  UPLOAD
// ============================================================
bool uploadToWebsite(uint8_t* wavData, size_t wavSize, const char* detectedClass, float confidence) {
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

  Serial.printf("[UPLOAD] POST %s (%d bytes)\n", url.c_str(), wavSize);

  HTTPClient http;
  int code = 0;

  if (url.startsWith("https://")) {
    WiFiClientSecure secureClient;
    secureClient.setInsecure();
    if (!http.begin(secureClient, url)) return false;
    http.addHeader("Content-Type", "audio/wav");
    http.addHeader("X-Device-Token", deviceToken);
    http.setConnectTimeout(10000);
    http.setTimeout(65000);
    code = http.sendRequest("POST", wavData, wavSize);
  } else {
    WiFiClient client;
    if (!http.begin(client, url)) return false;
    http.addHeader("Content-Type", "audio/wav");
    http.addHeader("X-Device-Token", deviceToken);
    http.setConnectTimeout(5000);
    http.setTimeout(65000);
    code = http.sendRequest("POST", wavData, wavSize);
  }

  if (code > 0) {
    Serial.printf("[UPLOAD] HTTP %d: %s\n", code, http.getString().c_str());
  } else {
    Serial.printf("[UPLOAD] Lỗi %d: %s\n", code, http.errorToString(code).c_str());
  }
  http.end();
  return code >= 200 && code < 300;
}

// ============================================================
// AI DSP FUNCTIONS
// ============================================================
// ============================================================
// PHAN TICH XUNG VA DAP / GO BAN
// ============================================================
static bool analyzeImpact(float rmsDbfs, int16_t peakSample)
{
    float blockRms[IMPACT_NUM_BLOCKS];

    float maxBlock = 0.0f;
    float meanBlock = 0.0f;

    for (int b = 0; b < IMPACT_NUM_BLOCKS; ++b)
    {
        double sumSq = 0.0;
        const int start = b * IMPACT_BLOCK_SAMPLES;

        for (int n = 0; n < IMPACT_BLOCK_SAMPLES; ++n)
        {
            const float x =
                (float)g_audio[start + n] / 32768.0f;

            sumSq += (double)x * (double)x;
        }

        const float rms =
            sqrtf((float)(sumSq / IMPACT_BLOCK_SAMPLES));

        blockRms[b] = rms;
        meanBlock += rms;

        if (rms > maxBlock)
        {
            maxBlock = rms;
        }
    }

    meanBlock /= (float)IMPACT_NUM_BLOCKS;

    const float overallRms =
        powf(10.0f, rmsDbfs / 20.0f);

    const float peakNorm =
        fabsf((float)peakSample) / 32768.0f;

    float crest = 0.0f;

    if (overallRms > 1e-8f)
    {
        crest = peakNorm / overallRms;
    }

    // Active threshold tu dong:
    // xung go thuong co 1 vai block cao hon nen rat nhieu.
    float activeTh = maxBlock * 0.18f;

    const float meanBased = meanBlock * 2.5f;
    if (activeTh < meanBased)
    {
        activeTh = meanBased;
    }

    if (activeTh < 0.0020f)
    {
        activeTh = 0.0020f;
    }

    int activeBlocks = 0;
    int longestRun = 0;
    int currentRun = 0;

    // Dem transient: block vuot 55% max, sau do phai ha xuong
    // duoi 22% max moi cho dem xung tiep theo.
    const float highTh = maxBlock * 0.55f;
    const float lowTh = maxBlock * 0.22f;

    int transientCount = 0;
    bool armed = true;

    for (int b = 0; b < IMPACT_NUM_BLOCKS; ++b)
    {
        const bool active = blockRms[b] >= activeTh;

        if (active)
        {
            ++activeBlocks;
            ++currentRun;

            if (currentRun > longestRun)
            {
                longestRun = currentRun;
            }
        }
        else
        {
            currentRun = 0;
        }

        if (armed &&
            highTh > 0.002f &&
            blockRms[b] >= highTh)
        {
            ++transientCount;
            armed = false;
        }

        if (!armed && blockRms[b] <= lowTh)
        {
            armed = true;
        }
    }

    const float activeMs =
        activeBlocks * IMPACT_BLOCK_MS;

    const float longestMs =
        longestRun * IMPACT_BLOCK_MS;

    g_impactPeakNorm = peakNorm;
    g_impactCrest = crest;
    g_impactActiveMs = activeMs;
    g_impactLongestMs = longestMs;
    g_impactTransientCount = transientCount;

    // ==========================================================
    // DIEU KIEN VA DAP - FIX
    // ==========================================================
    // KHONG bat buoc clipping. INMP441 co the thu mot cu dap rat manh
    // nhung peak van duoi 32700, nhu mau thuc te peakNorm=0.740.
    //
    // Gate A: 1 cu dap manh, xung rat nhon va ngan (khong phai nhip trong nhac lien tuc).
    const bool singleStrongImpact =
        transientCount >= 1 &&
        transientCount <= 4 &&
        peakNorm >= IMPACT_SINGLE_MIN_PEAK_NORM &&
        crest >= IMPACT_SINGLE_MIN_CREST &&
        activeMs <= IMPACT_SINGLE_MAX_ACTIVE_MS &&
        longestMs <= IMPACT_SINGLE_MAX_LONGEST_MS;

    // Gate B: co tu 2 den 4 transient dot bien (nhu 2-3 cu dap lien tiep).
    const bool multiTransientImpact =
        transientCount >= 2 &&
        transientCount <= 4 &&
        peakNorm >= IMPACT_MULTI_MIN_PEAK_NORM &&
        crest >= IMPACT_MULTI_MIN_CREST &&
        activeMs <= IMPACT_MULTI_MAX_ACTIVE_MS &&
        longestMs <= IMPACT_MULTI_MAX_LONGEST_MS;

    const bool impact = singleStrongImpact || multiTransientImpact;

    g_audioLikelyImpact = impact;

    Serial.println();
    Serial.println("============= IMPACT CHECK =============");
    Serial.printf("peakNorm   : %.3f\n", peakNorm);
    Serial.printf("crest      : %.2f\n", crest);
    Serial.printf("activeMs   : %.0f ms\n", activeMs);
    Serial.printf("longestMs  : %.0f ms\n", longestMs);
    Serial.printf("transients : %d\n", transientCount);
    Serial.printf("gateSingle : %s\n", singleStrongImpact ? "YES" : "NO");
    Serial.printf("gateMulti  : %s\n", multiTransientImpact ? "YES" : "NO");
    Serial.printf("impact     : %s\n", impact ? "YES" : "NO");
    Serial.println("========================================");

    return impact;
}


// ============================================================
// FFT 512 - chi dung de tao Log-Mel cho model
// KHONG dung FFT de override nhan.
// ============================================================
static void initFFT()
{
    for (int n = 0; n < N_FFT; ++n)
    {
        g_hann[n] =
            0.5f - 0.5f * cosf(2.0f * PI * (float)n / (float)N_FFT);
    }

    for (int k = 0; k < N_FFT / 2; ++k)
    {
        const float a = -2.0f * PI * (float)k / (float)N_FFT;
        g_fftCos[k] = cosf(a);
        g_fftSin[k] = sinf(a);
    }
}

static void fft512(float *re, float *im)
{
    unsigned j = 0;

    for (unsigned i = 1; i < N_FFT; ++i)
    {
        unsigned bit = N_FFT >> 1;

        while (j & bit)
        {
            j ^= bit;
            bit >>= 1;
        }

        j ^= bit;

        if (i < j)
        {
            float t = re[i];
            re[i] = re[j];
            re[j] = t;

            t = im[i];
            im[i] = im[j];
            im[j] = t;
        }
    }

    for (unsigned len = 2; len <= N_FFT; len <<= 1)
    {
        const unsigned half = len >> 1;
        const unsigned twStep = N_FFT / len;

        for (unsigned base = 0; base < N_FFT; base += len)
        {
            for (unsigned n = 0; n < half; ++n)
            {
                const unsigned tw = n * twStep;

                const float wr = g_fftCos[tw];
                const float wi = g_fftSin[tw];

                const unsigned even = base + n;
                const unsigned odd = even + half;

                const float orr = re[odd];
                const float oii = im[odd];

                const float tr = wr * orr - wi * oii;
                const float ti = wr * oii + wi * orr;

                const float er = re[even];
                const float ei = im[even];

                re[even] = er + tr;
                im[even] = ei + ti;
                re[odd] = er - tr;
                im[odd] = ei - ti;
            }
        }
    }
}

// ============================================================
// LIBROSA SLANEY MEL FILTER
// ============================================================
static float hzToMelSlaney(float hz)
{
    const float fMin = 0.0f;
    const float fSp = 200.0f / 3.0f;

    float mel = (hz - fMin) / fSp;

    const float minLogHz = 1000.0f;
    const float minLogMel = (minLogHz - fMin) / fSp;
    const float logStep = logf(6.4f) / 27.0f;

    if (hz >= minLogHz)
    {
        mel = minLogMel + logf(hz / minLogHz) / logStep;
    }

    return mel;
}

static float melToHzSlaney(float mel)
{
    const float fMin = 0.0f;
    const float fSp = 200.0f / 3.0f;

    float hz = fMin + fSp * mel;

    const float minLogHz = 1000.0f;
    const float minLogMel = (minLogHz - fMin) / fSp;
    const float logStep = logf(6.4f) / 27.0f;

    if (mel >= minLogMel)
    {
        hz = minLogHz * expf(logStep * (mel - minLogMel));
    }

    return hz;
}

static void initMelFilterBank()
{
    float melFreq[N_MELS + 2];

    const float fMin = 0.0f;
    const float fMax = SR * 0.5f;

    const float melMin = hzToMelSlaney(fMin);
    const float melMax = hzToMelSlaney(fMax);

    for (int i = 0; i < N_MELS + 2; ++i)
    {
        const float mel =
            melMin + (melMax - melMin) * (float)i / (float)(N_MELS + 1);

        melFreq[i] = melToHzSlaney(mel);
    }

    for (int m = 0; m < N_MELS; ++m)
    {
        const float left = melFreq[m];
        const float center = melFreq[m + 1];
        const float right = melFreq[m + 2];

        const float enorm = 2.0f / (right - left);

        for (int k = 0; k < N_BINS; ++k)
        {
            const float hz = (float)k * (float)SR / (float)N_FFT;

            const float lower = (hz - left) / (center - left);
            const float upper = (right - hz) / (right - center);

            float w = fminf(lower, upper);
            if (w < 0.0f)
                w = 0.0f;

            g_melFilter[m * N_BINS + k] = w * enorm;
        }
    }
}

// ============================================================
// LOG-MEL -> MODEL INPUT
// ============================================================
static bool buildLogMelAndSetModelInput()
{
    float maxMel = 0.0f;

    for (int frame = 0; frame < N_FRAMES; ++frame)
    {
        const int firstSample = frame * HOP - N_FFT / 2;

        for (int n = 0; n < N_FFT; ++n)
        {
            const int src = firstSample + n;

            float x = 0.0f;

            if (src >= 0 && src < N_SAMPLES)
            {
                x = (float)g_audio[src] / 32768.0f;
            }

            g_fftReal[n] = x * g_hann[n];
            g_fftImag[n] = 0.0f;
        }

        fft512(g_fftReal, g_fftImag);

        for (int k = 0; k < N_BINS; ++k)
        {
            const float re = g_fftReal[k];
            const float im = g_fftImag[k];

            g_power[k] = re * re + im * im;
        }

        for (int m = 0; m < N_MELS; ++m)
        {
            const float *filter = &g_melFilter[m * N_BINS];

            float e = 0.0f;

            for (int k = 0; k < N_BINS; ++k)
            {
                e += filter[k] * g_power[k];
            }

            g_melPower[m * N_FRAMES + frame] = e;

            if (e > maxMel)
            {
                maxMel = e;
            }
        }

        if ((frame & 31) == 0)
        {
            delay(0);
        }
    }

    const float amin = 1e-10f;
    const float refPower = fmaxf(maxMel, amin);
    const float refDb = 10.0f * log10f(refPower);

    int inputIndex = 0;

    for (int m = 0; m < N_MELS; ++m)
    {
        for (int frame = 0; frame < N_FRAMES; ++frame)
        {
            float p = g_melPower[m * N_FRAMES + frame];

            if (p < amin)
            {
                p = amin;
            }

            float db = 10.0f * log10f(p) - refDb;

            if (db < -80.0f)
                db = -80.0f;
            if (db > 0.0f)
                db = 0.0f;

            float feat = (db + 80.0f) / 80.0f;

            if (feat < 0.0f)
                feat = 0.0f;
            if (feat > 1.0f)
                feat = 1.0f;

            if (!ModelSetInput(feat, inputIndex))
            {
                Serial.printf("ModelSetInput fail tai index %d\n", inputIndex);
                return false;
            }

            ++inputIndex;
        }

        delay(0);
    }

    return inputIndex == N_INPUTS;
}



// ============================================================
//  SETUP
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(3000);
  Serial.println("\n\n=== ESP32 BOOT (Hybrid AI) ===");

  WiFiManager wm;
  pinMode(BUTTON_BOOT, INPUT_PULLUP);
  bool held = false;
  for (int s = 3; s > 0; s--) {
    Serial.printf("Giữ BOOT để xóa WiFi... còn %d giây\n", s);
    unsigned long t0 = millis();
    while (millis() - t0 < 1000) {
      if (digitalRead(BUTTON_BOOT) == LOW) held = true;
      delay(10);
    }
  }
  if (held) { Serial.println("Xóa WiFi!"); wm.resetSettings(); }

  // Ket noi uu tien truc tiep toi WiFi "Bui Tien Tuan"
  Serial.println("Dang ket noi WiFi: VP_127");
  WiFi.mode(WIFI_STA);
  WiFi.begin("VP_127", "Utehy@123");
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 25) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\nWiFi ket noi thanh cong! IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\nKet noi truc tiep khong duoc, bat WiFiManager Hotspot...");
    wm.setConfigPortalTimeout(120); // 2 phut timeout
    if (!wm.autoConnect("ESP32-VoiceRecorder")) {
      Serial.println("Không kết nối WiFi, restart...");
      delay(2000); ESP.restart();
    }
    while (WiFi.localIP()[0] == 0) { Serial.print("."); delay(500); }
    Serial.printf("\nIP: %s\n", WiFi.localIP().toString().c_str());
  }


  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(true);

  i2sInit();

  // PSRAM Allocation
  wavBuf = (uint8_t*) ps_malloc(BUFFER_BYTES + 44);
  if (!wavBuf) { Serial.println("Loi cap phat wavBuf"); while(1); }
  
  // Point g_audio directly to the PCM data in wavBuf to save RAM
  g_audio = reinterpret_cast<int16_t*>(wavBuf + 44);
  
  g_melPower = (float *)heap_caps_malloc(N_INPUTS * sizeof(float), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  g_melFilter = (float *)heap_caps_malloc(N_MELS * N_BINS * sizeof(float), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  g_tensorArena = (uint8_t *)heap_caps_malloc(TENSOR_ARENA_SIZE, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  
  if (!g_melPower || !g_melFilter || !g_tensorArena) {
    Serial.println("Loi cap phat PSRAM cho AI"); while(1);
  }

  initFFT();
  initMelFilterBank();
  
  Serial.println("Khoi tao TensorFlow Lite Micro...");
  if (!ModelInit(g_audio_model_data_4classes_5s, g_tensorArena, TENSOR_ARENA_SIZE)) {
      Serial.println("ModelInit that bai."); while(1);
  }

  Serial.println("\n================================================");
  Serial.println(" ESP32-S3 + INMP441 - HYBRID EDGE AI (10s)");
  Serial.println(" QUY TAC CANH BAO (Merged tu codetrainplatf):");
  Serial.printf(" - DAP_PHA: Xung va dap manh hoac CNN >= %.0f%% + Impact\n", AUDIO_THRESHOLD_DAP_PHA * 100.0f);
  Serial.printf(" - KHOC threshold: %.0f%%\n", AUDIO_THRESHOLD_KHOC * 100.0f);
  Serial.printf(" - CHUI_NHAU threshold: %.0f%%\n", AUDIO_THRESHOLD_CHUI_NHAU * 100.0f);
  Serial.println(" - TIENG ON / AN TOAN: Tu dong loai bo, KHONG gui!");
  Serial.println("================================================");
  Serial.println("ESP32 Ready — Hybrid AI Mode\n");
}

// ============================================================
//  LOOP
// ============================================================
void loop() {
  Serial.printf("[REC] Dang ghi am %d giay...\n", RECORD_SECONDS);
  writeWavHeader(wavBuf, BUFFER_BYTES);
  
  int16_t overallPeak = 0;
  float overallRmsDbfs = recordAudio(overallPeak);
  Serial.printf("[REC] Thu xong: Peak=%d | RMS=%.1f dBFS\n", overallPeak, overallRmsDbfs);

  if (overallPeak < 5) {
    Serial.println("[CANH BAO MIC] Tin hieu mic gan 0! Kiem tra day noi INMP441 (SCK:6, SD:5, WS:4, L/R:GND).");
  }

  // Lọc khoảng im lặng / phòng yên tĩnh (chỉnh nhẹ lên Peak < 220 hoặc RMS < -48 dBFS):
  if (overallRmsDbfs < -48.0f || overallPeak < 220) {
    Serial.printf("[REC] Loc im lang: phong yen tinh (Peak=%d < 220, RMS=%.1f dBFS < -48dBFS) -> Bo qua an toan.\n", overallPeak, overallRmsDbfs);
    delay(20);
    return;
  }

  Serial.printf("[REC] Phat hien am thanh (%.1f dBFS), phan tich Edge AI...\n", overallRmsDbfs);
  
  int16_t* original_audio = g_audio;
  bool shouldUpload = false;
  const char* uploadClass = "";
  float maxConfidence = 0.0f;

  int numChunks = SAMPLES_TOTAL / N_SAMPLES;
  if (numChunks == 0) numChunks = 1;

  for (int chunk = 0; chunk < numChunks; chunk++) {
      Serial.printf("\n>>> Phan tich nua %d (tu giay %d den %d)...\n", chunk + 1, chunk * 5, (chunk + 1) * 5);
      
      g_audio = original_audio + (chunk * N_SAMPLES);

      // Tinh peak, RMS va clipping rieng cho tung nua 5s
      int32_t chunkPeak = 0;
      double chunkSumSq = 0.0;
      uint32_t chunkClippedSamples = 0;
      for (int i = 0; i < N_SAMPLES; i++) {
          int16_t v = g_audio[i];
          int32_t av = (v < 0) ? -v : v;
          if (av > chunkPeak) chunkPeak = av;
          if (av >= 32700) ++chunkClippedSamples;
          double fv = (double)v / 32768.0;
          chunkSumSq += fv * fv;
      }
      double chunkRms = sqrt(chunkSumSq / (double)N_SAMPLES);
      float chunkRmsDbfs = (chunkRms > 1e-12) ? (float)(20.0 * log10(chunkRms)) : -120.0f;
      int16_t chunkPeak16 = (int16_t)((chunkPeak > 32767) ? 32767 : chunkPeak);
      bool chunkClipped = (chunkClippedSamples > 300);

      // 1. Phan tich xung va dap NGAY SAU KHI THU (Chuan tu codetrainplatf)
      analyzeImpact(chunkRmsDbfs, chunkPeak16);

      // Chi override DAP_PHA neu thuc su co cu dap manh (Peak >= 12000 hoac clipping)
      if (g_audioLikelyImpact && (chunkPeak16 >= 12000 || chunkClipped)) {
          Serial.println("\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!");
          Serial.println("=> PHAT HIEN XUNG VA DAP MANH / GO BAN / DAP PHA");
          Serial.println("=> KET QUA CUOI: DAP_PHA (Override truoc CNN)");
          Serial.println("=> KHONG DUA XUNG NAY VAO MODEL KHOC");
          Serial.println("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!");
          shouldUpload = true;
          uploadClass = "dap_pha";
          maxConfidence = 1.0f;
          break;
      }

      // 2. Chi bo qua neu bi loi phan cung mic (tren 50% so mau bi ket dinh o 32700)
      if (chunkClippedSamples > 40000) {
          Serial.printf("=> BO QUA: Loi phan cung mic bi bao hoa lien tuc (%u mau clip > 32700).\n", chunkClippedSamples);
          continue;
      }
      if (chunkClipped) {
          Serial.printf("=> AM THANH CUONG DO LON / GAO THET (%u mau clip > 32700), tiep tuc phan tich AI...\n", chunkClippedSamples);
      }

      // 3. Trich xuat dac trung Log-Mel Spectrogram 40x501
      if (!buildLogMelAndSetModelInput()) {
          Serial.println("Tao feature / nap input that bai.");
          continue;
      }

      // 4. Chay Inference TFLite Micro
      if (!ModelRunInference()) {
          Serial.println("ModelRunInference FAILED");
          continue;
      }

      float prob[N_CLASSES];
      for (int i = 0; i < N_CLASSES; ++i) {
          prob[i] = ModelGetOutput(i);
          if (!isfinite(prob[i])) prob[i] = 0.0f;
          if (prob[i] < 0.0f) prob[i] = 0.0f;
          if (prob[i] > 1.0f) prob[i] = 1.0f;
      }

      // 5. In ket qua AI formatted giong codetrainplatf
      Serial.println();
      Serial.println("============= KET QUA AI =============");
      Serial.printf("KHOC      : %6.2f %%\n", prob[AUDIO_CLASS_KHOC] * 100.0f);
      Serial.printf("DAP PHA   : %6.2f %%\n", prob[AUDIO_CLASS_DAP_PHA] * 100.0f);
      Serial.printf("CHUI NHAU : %6.2f %%\n", prob[AUDIO_CLASS_CHUI_NHAU] * 100.0f);
      Serial.printf("TIENG ON  : %6.2f %%\n", prob[AUDIO_CLASS_TIENG_ON] * 100.0f);
      Serial.println("--------------------------------------");

      // Xac dinh nhan chiem uu the cao nhat
      int maxClass = 0;
      float maxProb = prob[0];
      for (int i = 1; i < N_CLASSES; ++i) {
          if (prob[i] > maxProb) {
              maxProb = prob[i];
              maxClass = i;
          }
      }

      // LOC ON CHI KHI TIENG ON RAT CAO (>= 80%) VA KHONG CO VA DAP:
      if (prob[AUDIO_CLASS_TIENG_ON] >= 0.80f && !g_audioLikelyImpact) {
          Serial.printf("=> KET QUA: TIENG ON NEN CHIEM %.2f%%. Bo qua.\n", prob[AUDIO_CLASS_TIENG_ON] * 100.0f);
          continue;
      }

      // 6. Ap dung nguong quyet dinh Hybrid AI:
      // Uu tien 1: KHOC / KEU CUU
      if (prob[AUDIO_CLASS_KHOC] >= 0.40f) {
          Serial.printf("=> NHAN: KHOC (%.2f%%)\n", prob[AUDIO_CLASS_KHOC] * 100.0f);
          shouldUpload = true;
          uploadClass = "help";
          maxConfidence = max(prob[AUDIO_CLASS_KHOC], 0.80f);
          break;
      }
      // Uu tien 2: DAP PHA
      else if (g_audioLikelyImpact || prob[AUDIO_CLASS_DAP_PHA] >= 0.45f) {
          Serial.printf("=> NHAN: DAP_PHA (%.2f%%) [Impact: %s]\n", prob[AUDIO_CLASS_DAP_PHA] * 100.0f, g_audioLikelyImpact ? "YES" : "NO");
          shouldUpload = true;
          uploadClass = "dap_pha";
          maxConfidence = max(prob[AUDIO_CLASS_DAP_PHA], 0.85f);
          break;
      }
      // Uu tien 3: CAI NHAU / CHUI NHAU
      else if (prob[AUDIO_CLASS_CHUI_NHAU] >= 0.40f) {
          Serial.printf("=> NHAN: CO TIENG CAI NHAU (%.2f%%) -> Gui len Web AI de tham dinh!\n", prob[AUDIO_CLASS_CHUI_NHAU] * 100.0f);
          shouldUpload = true;
          uploadClass = "threat";
          maxConfidence = prob[AUDIO_CLASS_CHUI_NHAU];
          break;
      }
      // Uu tien 4: GIONG NOI TO / TRANH CAI (Chi thu am neu am luong rat lon Peak >= 1500 va khong phai on)
      else if (prob[AUDIO_CLASS_TIENG_ON] < 0.70f && overallPeak >= 1500) {
          Serial.printf("=> PHAT HIEN GIONG NOI TO (Tieng on: %.2f%%, Peak=%d) -> Gui len Web!\n", prob[AUDIO_CLASS_TIENG_ON] * 100.0f, overallPeak);
          shouldUpload = true;
          uploadClass = "analyze";
          maxConfidence = 0.50f;
          break;
      }
      else {
          Serial.printf("=> NOI CHUYEN BINH THUONG / TIENG ON (Tieng on: %.2f%%, Peak=%d) -> Bo qua an toan.\n", prob[AUDIO_CLASS_TIENG_ON] * 100.0f, overallPeak);
      }
  }

  g_audio = original_audio;

  // 7. Chi gui len Web Backend neu phat hien dung hanh vi nguy hiem
  if (shouldUpload) {
      Serial.println("\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!");
      Serial.printf("CANH BAO: %s | %.2f%%\n", uploadClass, maxConfidence * 100.0f);
      Serial.printf("=> Dang gui toan bo %d giay len Web...\n", RECORD_SECONDS);
      Serial.println("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n");
      uploadToWebsite(wavBuf, BUFFER_BYTES + 44, uploadClass, maxConfidence);
  } else {
      Serial.printf("\n=> TONG KET: Toan bo %ds la Tieng on / Binh thuong. Bo qua KHONG gui.\n", RECORD_SECONDS);
  }

  delay(20);
}
