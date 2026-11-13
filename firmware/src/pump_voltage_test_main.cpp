#include <Arduino.h>
#include <driver/ledc.h>
#include <cstring>

namespace {
constexpr int kPwmPin = 25;
constexpr uint32_t kPwm50 = 2048;  // Half of the 12-bit timer period.
constexpr uint32_t kLeaseMs = 2000;
constexpr uint32_t kTestMs = 30000;
constexpr uint32_t kSettleMs = 1500;
constexpr uint32_t kRunMs = 10000;
constexpr ledc_mode_t kMode = LEDC_HIGH_SPEED_MODE;
constexpr ledc_channel_t kChannel = LEDC_CHANNEL_0;
constexpr int kData = 14, kClock = 13, kLatch = 12, kOutputEnable = 5;
#ifdef BASU_PUMP_OPEN_BUCKET_TEST
constexpr bool kRunEnabled = true;
constexpr int kFeedbackPin = 34;
#else
constexpr bool kRunEnabled = false;
constexpr int kFeedbackPin = 39;
#endif

bool pwmReady = false;
bool active = false;
bool running = false;
bool havePing = false;
uint32_t lastPingMs = 0;
uint32_t startedMs = 0;
uint32_t runStartedMs = 0;
char line[8];
size_t length = 0;
bool discarding = false;

void writeRunRelay(bool run) {
  // Only the dedicated RUN bit can be HIGH. The latch holds the previous
  // levels while clocking the new word in, so valves remain LOW throughout.
  digitalWrite(kLatch, LOW);
  for (int bit = 15; bit >= 0; --bit) {
    digitalWrite(kData, kRunEnabled && run && bit == 15 ? HIGH : LOW);
    digitalWrite(kClock, HIGH);
    digitalWrite(kClock, LOW);
  }
  digitalWrite(kLatch, HIGH);
}

void holdRelaysOff() {
  digitalWrite(kOutputEnable, HIGH);
  pinMode(kOutputEnable, OUTPUT);
  for (const int pin : {kData, kClock, kLatch}) {
    digitalWrite(pin, LOW);
    pinMode(pin, OUTPUT);
  }
  writeRunRelay(false);
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
  if (running) writeRunRelay(false);
  running = false;
  active = false;
  havePing = false;
  if (pwmReady) writeDuty(0);
}

void expire(uint32_t now) {
  if (active && (now - lastPingMs >= kLeaseMs || now - startedMs >= kTestMs ||
                 (running && now - runStartedMs >= kRunMs))) stopTest();
}

void report(uint32_t now) {
  if (!pwmReady) {
    Serial.println(kRunEnabled ? "PUMP_BENCH_FAULT" : "PUMP_TEST_FAULT");
    return;
  }
  const auto remaining = static_cast<unsigned long>(active ? kTestMs - (now - startedMs) : 0);
  const auto feedback = static_cast<unsigned long>(analogReadMilliVolts(kFeedbackPin));
  if constexpr (kRunEnabled) {
    const auto runRemaining = static_cast<unsigned long>(running ? kRunMs - (now - runStartedMs) : 0);
    Serial.printf("PUMP_BENCH %u %lu %lu %u %lu\n", active ? 50U : 0U, remaining,
                  feedback, running ? 1U : 0U, runRemaining);
  } else {
    Serial.printf("PUMP_TEST %u %lu %lu\n", active ? 50U : 0U, remaining, feedback);
  }
}

void command(uint32_t now) {
  if (length && line[length - 1] == '\r') --length;
  line[length] = '\0';
  const bool freshPing = havePing && now - lastPingMs < kLeaseMs;
  const uint32_t stageAge = now - startedMs;
  if (!std::strcmp(line, "PING")) {
    lastPingMs = now;
    havePing = true;
  } else if (!std::strcmp(line, "TEST50") && !active && freshPing) {
    havePing = false;
    startedMs = now;
    active = writeDuty(kPwm50);
  } else if (kRunEnabled && !std::strcmp(line, "RUN50") && active && !running && freshPing &&
             stageAge >= kSettleMs && stageAge <= kTestMs - kRunMs) {
    // TEST50 clears havePing, so RUN50 also needs a PING during this stage.
    writeRunRelay(true);
    runStartedMs = now;
    running = true;
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
  holdRelaysOff();
  digitalWrite(kPwmPin, LOW);
  pinMode(kPwmPin, OUTPUT);
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
  if (!writeDuty(0)) report(millis());
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
