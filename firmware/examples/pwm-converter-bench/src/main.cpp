// Unloaded converter bench ONLY. GPIO25 is a candidate, not a commissioned map.
#include <Arduino.h>
#include <driver/ledc.h>
#include <cstring>

namespace {
constexpr int kPwmPin = 25;
constexpr uint32_t kLimitMs = 5000, kFullScale = 4096;  // 12-bit timer, 100% HIGH.
constexpr ledc_mode_t kMode = LEDC_HIGH_SPEED_MODE;
constexpr ledc_channel_t kChannel = LEDC_CHANNEL_0;
char line[32];
size_t length = 0;
bool discarding = false, ready = false, armed = false, active = false;
uint32_t armedAt = 0, startedAt = 0;

bool writeDuty(uint32_t duty) {
  if (ready && ledc_set_duty(kMode, kChannel, duty) == ESP_OK &&
      ledc_update_duty(kMode, kChannel) == ESP_OK) return true;
  ledc_stop(kMode, kChannel, 0);  // Best effort, no output feedback.
  ready = false;
  return false;
}

void stop(const char* reason) {
  armed = active = false;
  if (ready && !writeDuty(0)) Serial.println("FAULT: PWM write failed; reset required.");
  Serial.println(reason);
}

void expire() {
  const uint32_t now = millis();
  if (active && static_cast<uint32_t>(now - startedAt) >= kLimitMs)
    stop("TIME LIMIT: commanded zero. Re-enter PUMP DISCONNECTED for another test.");
  else if (armed && static_cast<uint32_t>(now - armedAt) >= kLimitMs)
    stop("Arm expired: commanded zero. Re-enter PUMP DISCONNECTED.");
}

void command() {
  if (length && line[length - 1] == '\r') --length;  // Accept one CRLF ending.
  line[length] = '\0';
  if (!std::strcmp(line, "STOP") || !std::strcmp(line, "0")) {
    stop("STOP: commanded zero; disarmed.");
    return;
  }
  if (!ready) { stop("LOCKED: PWM initialization/write failed; reset required."); return; }
  if (active) { stop("REJECTED: a test was active; commanded zero, no queued test."); return; }
  if (!std::strcmp(line, "PUMP DISCONNECTED")) {
    armed = true;
    armedAt = millis();
    Serial.println("Armed for ONE test within 5 s: enter 25, 50, 75 or 100.");
    return;
  }
  unsigned percent = 0;
  if (!std::strcmp(line, "25")) percent = 25;
  else if (!std::strcmp(line, "50")) percent = 50;
  else if (!std::strcmp(line, "75")) percent = 75;
  else if (!std::strcmp(line, "100")) percent = 100;
  if (!armed || !percent) { stop("REJECTED: invalid/unarmed command; commanded zero."); return; }
  armed = false;  // Consume the attestation; commands cannot extend a test.
  startedAt = millis();
  if (!writeDuty(percent * kFullScale / 100)) { stop("FAULT: PWM write failed."); return; }
  active = true;
  Serial.printf("COMMAND ONLY: %u%% PWM, max 5 s. Measure converter OUT yourself.\n", percent);
}

void readSerial() {
  for (unsigned budget = 64; budget && Serial.available(); --budget) {
    expire();
    const char ch = static_cast<char>(Serial.read());
    if (ch == '\n') {
      if (!discarding) command();
      length = 0;
      discarding = false;
    } else if (!discarding) {
      if (length >= sizeof(line) - 1 || (ch != '\r' && (ch < 32 || ch > 126))) {
        stop("REJECTED: oversized/invalid input; commanded zero.");
        discarding = true;
        length = 0;
      } else line[length++] = ch;
    }
  }
}
}  // namespace

void setup() {
  digitalWrite(kPwmPin, LOW);
  pinMode(kPwmPin, OUTPUT);  // Hold LOW before attaching the peripheral.
  Serial.begin(115200);
  ledc_timer_config_t timer{};
  timer.speed_mode = kMode;
  timer.duty_resolution = LEDC_TIMER_12_BIT;
  timer.timer_num = LEDC_TIMER_0;
  timer.freq_hz = 1000;
  timer.clk_cfg = LEDC_AUTO_CLK;
  ledc_channel_config_t channel{};
  channel.gpio_num = kPwmPin;
  channel.speed_mode = kMode;
  channel.channel = kChannel;
  channel.intr_type = LEDC_INTR_DISABLE;
  channel.timer_sel = LEDC_TIMER_0;
  channel.duty = 0;  // No stale nonzero channel duty at attachment.
  channel.hpoint = 0;
  ready = ledc_timer_config(&timer) == ESP_OK && ledc_channel_config(&channel) == ESP_OK;
  if (ready) ready = writeDuty(0);
  if (!ready) ledc_stop(kMode, kChannel, 0);
  Serial.println("UNLOADED PWM CONVERTER BENCH ONLY: GPIO25, 1 kHz, 3.3 V logic.");
  Serial.println("Keep ALL pump DB15 wires AND relay COM/NO/NC loads disconnected; isolate the pump stop circuit throughout.");
  Serial.println("No actuator control or voltage measurement. Lost PWM may leave converter OUT nonzero.");
  Serial.println(ready ? "Enter exact phrase PUMP DISCONNECTED, then one of 0/25/50/75/100. STOP always disarms."
                       : "LOCKED: PWM initialization failed; no testing. Reset after inspection.");
}

void loop() {
  expire();
  readSerial();
  expire();
  yield();
}
