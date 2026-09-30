#include <Arduino.h>
#include "esp_camera.h"

static bool cameraReady = false;
static uint32_t sequenceNumber = 0;
static uint32_t chunkSize = 64;
static uint32_t chunkGapUs = 1000;
static camera_config_t cameraConfig = {};

static void automaticExposure() {
  sensor_t *sensor = esp_camera_sensor_get();
  sensor->set_colorbar(sensor, 0);
  sensor->set_special_effect(sensor, 0);
  sensor->set_brightness(sensor, 0);
  sensor->set_contrast(sensor, 0);
  sensor->set_whitebal(sensor, 1);
  sensor->set_awb_gain(sensor, 1);
  sensor->set_aec2(sensor, 0);
  sensor->set_ae_level(sensor, -1);
  sensor->set_exposure_ctrl(sensor, 1);
  sensor->set_gain_ctrl(sensor, 1);
}

static esp_err_t initializeCamera() {
  esp_err_t error = ESP_FAIL;
  for (int attempt = 0; attempt < 3; ++attempt) {
    // A CPU reset alone may leave the OV2640 in its previous state.
    pinMode(32, OUTPUT);
    digitalWrite(32, HIGH);
    delay(100);
    digitalWrite(32, LOW);
    delay(100);
    error = esp_camera_init(&cameraConfig);
    if (error == ESP_OK) {
      automaticExposure();
      // Let automatic exposure settle before the first requested frame.
      for (int warmup = 0; warmup < 8; ++warmup) {
        camera_fb_t *frame = esp_camera_fb_get();
        if (frame) esp_camera_fb_return(frame);
        delay(25);
      }
      return error;
    }
    esp_camera_deinit();
    delay(100);
  }
  return error;
}

static uint32_t frameCrc(const uint8_t *data, size_t size) {
  uint32_t crc = 0xffffffffUL;
  for (size_t i = 0; i < size; ++i) {
    crc ^= data[i];
    for (int bit = 0; bit < 8; ++bit)
      crc = (crc >> 1) ^ ((crc & 1) ? 0xedb88320UL : 0);
  }
  return crc ^ 0xffffffffUL;
}

static void put16(uint8_t *dst, uint16_t value) {
  dst[0] = value; dst[1] = value >> 8;
}
static void put32(uint8_t *dst, uint32_t value) {
  for (int i = 0; i < 4; ++i) dst[i] = value >> (i * 8);
}

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);
  pinMode(4, OUTPUT);
  digitalWrite(4, LOW); // Keep the bright flash LED off.

  camera_config_t &config = cameraConfig;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  // AI-Thinker ESP32-CAM / OV2640 pin map.
  config.pin_d0 = 5; config.pin_d1 = 18;
  config.pin_d2 = 19; config.pin_d3 = 21;
  config.pin_d4 = 36; config.pin_d5 = 39;
  config.pin_d6 = 34; config.pin_d7 = 35;
  config.pin_xclk = 0; config.pin_pclk = 22;
  config.pin_vsync = 25; config.pin_href = 23;
  config.pin_sccb_sda = 26; config.pin_sccb_scl = 27;
  config.pin_pwdn = 32; config.pin_reset = -1;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 20;
  const bool hasPsram = psramFound();
  config.fb_count = hasPsram ? 2 : 1;
  config.fb_location = hasPsram ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  config.grab_mode = hasPsram ? CAMERA_GRAB_LATEST : CAMERA_GRAB_WHEN_EMPTY;
  esp_err_t error = initializeCamera();
  if (error != ESP_OK) {
    Serial.printf("CAM_ERROR init=0x%x\n", error);
    return;
  }
  cameraReady = true;
  Serial.println("CAM_READY 320x240 JPEG UART=115200");
}

void loop() {
  if (!Serial.available()) { delay(1); return; }
  int command = Serial.read();
  if (command == 'I') {
    sensor_t *sensor = cameraReady ? esp_camera_sensor_get() : nullptr;
    if (!sensor) { Serial.println("CAM_ERROR not_ready"); return; }
    Serial.printf("CAM_INFO pid=0x%x aec=%d exposure=%d agc=%d gain=%d ae_level=%d\n",
                  sensor->id.PID, sensor->status.aec, sensor->status.aec_value,
                  sensor->status.agc, sensor->status.agc_gain, sensor->status.ae_level);
    return;
  }
  if (command == 'E') {
    uint32_t exposure = Serial.parseInt();
    if (!cameraReady || exposure > 1200) { Serial.println("CAM_ERROR exposure"); return; }
    sensor_t *sensor = esp_camera_sensor_get();
    if (exposure == 0) automaticExposure();
    else {
      sensor->set_exposure_ctrl(sensor, 0);
      sensor->set_gain_ctrl(sensor, 0);
      sensor->set_agc_gain(sensor, 0);
      sensor->set_aec_value(sensor, exposure);
    }
    Serial.printf("EXPOSURE %lu\n", (unsigned long)exposure);
    return;
  }
  if (command == 'T') {
    uint32_t size = Serial.parseInt();
    uint32_t gap = Serial.parseInt();
    if ((size != 32 && size != 64 && size != 128 && size != 256) || gap > 5000) {
      Serial.println("CAM_ERROR invalid_transfer");
      return;
    }
    chunkSize = size;
    chunkGapUs = gap;
    Serial.printf("TRANSFER %lu %lu\n", (unsigned long)size, (unsigned long)gap);
    Serial.flush();
    return;
  }
  if (command == 'B') {
    uint32_t baud = Serial.parseInt();
    if (baud != 115200 && baud != 230400 && baud != 460800 &&
        baud != 921600 && baud != 1500000 && baud != 2000000) {
      Serial.println("CAM_ERROR invalid_baud");
      return;
    }
    Serial.printf("BAUD %lu\n", (unsigned long)baud);
    Serial.flush();
    Serial.updateBaudRate(baud);
    return;
  }
  if (command != 'F') return;
  if (!cameraReady) cameraReady = initializeCamera() == ESP_OK;
  if (!cameraReady) { Serial.println("CAM_ERROR not_ready"); return; }
  camera_fb_t *frame = esp_camera_fb_get();
  if (!frame) { Serial.println("CAM_ERROR capture_failed"); return; }
  uint8_t header[20] = {'E', 'C', 'A', 'M'};
  put32(header + 4, frame->len);
  put32(header + 8, frameCrc(frame->buf, frame->len));
  put32(header + 12, sequenceNumber++);
  put16(header + 16, frame->width);
  put16(header + 18, frame->height);
  Serial.write(header, sizeof(header));
  // Give the USB-UART bridge time to drain between short bursts.
  for (size_t offset = 0; offset < frame->len; offset += chunkSize) {
    size_t count = min((size_t)chunkSize, frame->len - offset);
    Serial.write(frame->buf + offset, count);
    Serial.flush();
    delayMicroseconds(chunkGapUs);
  }
  esp_camera_fb_return(frame);
}
