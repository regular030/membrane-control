#include <Arduino.h>
#include <driver/ledc.h>
#include <cstring>

namespace {
constexpr int kPwmPin = 25;
constexpr int kFeedbackPin = 39;
constexpr uint32_t kPwm50 = 2048;  // Half of the 12-bit timer period.
constexpr uint32_t kLeaseMs = 2000;
constexpr uint32_t kTestMs = 30000;
constexpr ledc_mode_t kMode = LEDC_HIGH_SPEED_MODE;
constexpr ledc_channel_t kChannel = LEDC_CHANNEL_0;

bool pwmReady = false;
bool active = false;
bool havePing = false;
uint32_t lastPingMs = 0;
uint32_t startedMs = 0;
char line[8];
size_t length = 0;
bool discarding = false;

void holdRelaysOff() {
  // Known active-high 16-channel rig mapping. Only the all-off word is latched.
  constexpr int kData = 14, kClock = 13, kLatch = 12, kOutputEnable = 5;
  digitalWrite(kOutputEnable, HIGH);
  pinMode(kOutputEnable, OUTPUT);
  for (const int pin : {kData, kClock, kLatch}) {
    digitalWrite(pin, LOW);
    pinMode(pin, OUTPUT);
  }
  for (int bit = 0; bit < 16; ++bit) {
    digitalWrite(kClock, HIGH);
    digitalWrite(kClock, LOW);
  }
  digitalWrite(kLatch, HIGH);
  digitalWrite(kOutputEnable, LOW);
}

bool writeDuty(uint32_t duty) {
  if (pwmReady && ledc_set_duty(kMode, kChannel, duty) == ESP_OK &&
      ledc_update_duty(kMode, kChannel) == ESP_OK) return true;
  ledc_stop(kMode, kChannel, 0);
  pwmReady = false;
  return false;
}

void stopTest() {
  active = false;
  havePing = false;
  if (pwmReady) writeDuty(0);
}

void expire(uint32_t now) {
  if (active && (now - lastPingMs >= kLeaseMs || now - startedMs >= kTestMs)) stopTest();
}

void report(uint32_t now) {
  if (!pwmReady) {
    Serial.println("PUMP_TEST_FAULT");
    return;
  }
  const uint32_t remaining = active ? kTestMs - (now - startedMs) : 0;
  Serial.printf("PUMP_TEST %u %lu %lu\n", active ? 50U : 0U,
                static_cast<unsigned long>(remaining),
                static_cast<unsigned long>(analogReadMilliVolts(kFeedbackPin)));
}

void command(uint32_t now) {
  if (length && line[length - 1] == '\r') --length;
  line[length] = '\0';
  if (!std::strcmp(line, "PING")) {
    lastPingMs = now;
    havePing = true;
  } else if (!std::strcmp(line, "TEST50") && !active && havePing && now - lastPingMs < kLeaseMs) {
    havePing = false;
    startedMs = now;
    active = writeDuty(kPwm50);
  } else if (!std::strcmp(line, "STOP") || length) {
    // Unknown and out-of-sequence commands also return to zero.
    stopTest();
  } else {
    return;
  }
  report(now);
}
}  // namespace

void setup() {
  digitalWrite(kPwmPin, LOW);
  pinMode(kPwmPin, OUTPUT);
  holdRelaysOff();
  pinMode(kFeedbackPin, INPUT);
  analogSetPinAttenuation(kFeedbackPin, ADC_11db);
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
  channel.duty = 0;
  pwmReady = ledc_timer_config(&timer) == ESP_OK && ledc_channel_config(&channel) == ESP_OK;
  if (!writeDuty(0)) Serial.println("PUMP_TEST_FAULT");
}

void loop() {
  expire(millis());
  for (unsigned budget = 64; budget && Serial.available(); --budget) {
    const uint32_t now = millis();
    expire(now);
    const char ch = static_cast<char>(Serial.read());
    if (ch == '\n') {
      if (!discarding) command(now);
      discarding = false;
      length = 0;
    } else if (!discarding) {
      if (length == sizeof(line) - 1 || (ch != '\r' && (ch < ' ' || ch > '~'))) {
        stopTest();
        discarding = true;
      } else {
        line[length++] = ch;
      }
    }
  }
  yield();
}
