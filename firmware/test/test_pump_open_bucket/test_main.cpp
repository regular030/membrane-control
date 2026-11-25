#include <Arduino.h>
#include <driver/ledc.h>
#include <unity.h>
#include <cstdio>
#include <string>
#include <utility>

enum ledc_timer_bit_t { LEDC_TIMER_12_BIT = 12 };
enum ledc_clk_cfg_t { LEDC_AUTO_CLK };
struct ledc_timer_config_t {
  ledc_mode_t speed_mode;
  ledc_timer_bit_t duty_resolution;
  ledc_timer_t timer_num;
  uint32_t freq_hz;
  ledc_clk_cfg_t clk_cfg;
};
esp_err_t ledc_timer_config(const ledc_timer_config_t* config) {
  return ledcSetup(0, config->freq_hz, config->duty_resolution) ? ESP_OK : ESP_FAIL;
}

uint32_t testNow = 0;
uint32_t millis() { return testNow; }
void yield() {}

struct MockUsb {
  std::string input;
  std::string lastLine;
  void begin(int) {}
  bool available() const { return !input.empty(); }
  char read() {
    const char next = input.front();
    input.erase(0, 1);
    return next;
  }
  void println(const char* text) { lastLine = text; }
  template <typename... Args> void printf(const char* format, Args... args) {
    char text[80];
    std::snprintf(text, sizeof(text), format, args...);
    lastLine = text;
  }
} Serial;

#define BASU_PUMP_OPEN_BUCKET_TEST 1
#include "../../src/pump_voltage_test_main.cpp"

void setUp() {
  fake::resetGpio();
  fake::resetLedc();
  fake::adcMillivolts[34] = 460;
  Serial = {};
  testNow = 0;
  active = running = havePing = discarding = false;
  length = 0;
  startedMs = lastPingMs = runStartedMs = 0;
  setup();
}
void tearDown() {}

void send(const char* text, uint32_t now) {
  Serial.input = text;
  testNow = now;
  loop();
}

std::vector<std::pair<uint16_t, unsigned>> relayWords() {
  uint16_t bits = 0;
  bool data = false;
  std::vector<std::pair<uint16_t, unsigned>> words;
  for (const auto& event : fake::gpioEvents) {
    if (!event.write) continue;
    if (event.pin == kData) data = event.value == HIGH;
    if (event.pin == kClock && event.value == HIGH) bits = static_cast<uint16_t>((bits << 1) | data);
    if (event.pin == kLatch && event.value == HIGH) words.emplace_back(bits, event.sequence);
  }
  return words;
}

void stage() {
  send("PING\nTEST50\n", 0);
  TEST_ASSERT_TRUE(active);
  TEST_ASSERT_FALSE(running);
  TEST_ASSERT_EQUAL(2048, fake::ledcDuties[0]);
}

void startRun() {
  stage();
  send("PING\n", 1000);
  send("RUN50\n", 1500);
  TEST_ASSERT_TRUE(running);
  TEST_ASSERT_EQUAL_HEX16(0x8000, relayWords().back().first);
  TEST_ASSERT_EQUAL_STRING("PUMP_BENCH 50 28500 460 1 10000\n", Serial.lastLine.c_str());
  fake::gpioEvents.clear();
  fake::ledcEvents.clear();
}

void assertRunStopped() {
  TEST_ASSERT_FALSE(active);
  TEST_ASSERT_FALSE(running);
  TEST_ASSERT_EQUAL(0, fake::ledcDuties[0]);
  const auto words = relayWords();
  TEST_ASSERT_EQUAL(1, words.size());
  TEST_ASSERT_EQUAL_HEX16(0, words.back().first);
  TEST_ASSERT_FALSE(fake::ledcEvents.empty());
  TEST_ASSERT_TRUE(words.back().second < fake::ledcEvents.front().sequence);
}

void test_startup_and_staging_keep_relays_off() {
  TEST_ASSERT_EQUAL(1, relayWords().size());
  TEST_ASSERT_EQUAL_HEX16(0, relayWords().back().first);
  TEST_ASSERT_EQUAL(0, fake::ledcDuties[0]);
  TEST_ASSERT_EQUAL(ADC_11db, fake::adcAttenuation[34]);
  TEST_ASSERT_EQUAL(-1, fake::adcAttenuation[39]);
  send("TEST50\n", 0);
  TEST_ASSERT_FALSE(active);
  stage();
  TEST_ASSERT_EQUAL(1, relayWords().size());
}

void test_run_requires_settle_and_a_ping_after_staging() {
  stage();
  send("PING\n", 1000);
  send("RUN50\n", 1499);
  TEST_ASSERT_FALSE(active);
  TEST_ASSERT_EQUAL(1, relayWords().size());

  send("PING\nTEST50\n", 2000);
  send("RUN50\n", 3500);
  TEST_ASSERT_FALSE(active);
  TEST_ASSERT_EQUAL(1, relayWords().size());
}

void test_duplicate_run_opens_relay_before_zero_and_needs_a_new_stage() {
  startRun();
  send("RUN50\n", 1501);
  assertRunStopped();
  send("PING\nRUN50\n", 1502);
  TEST_ASSERT_FALSE(active);
  TEST_ASSERT_EQUAL(1, relayWords().size());
}

void test_expired_lease_opens_relay_before_zero() {
  startRun();
  send("PING\n", 2000);
  send("", 3999);
  TEST_ASSERT_TRUE(running);
  send("", 4000);
  assertRunStopped();
}

void test_run_timer_cannot_be_extended_by_pings() {
  startRun();
  for (uint32_t now = 2000; now <= 11000; now += 1000) send("PING\n", now);
  send("PING\n", 11499);
  TEST_ASSERT_TRUE(running);
  send("PING\n", 11500);
  assertRunStopped();
  TEST_ASSERT_EQUAL_STRING("PUMP_BENCH 0 0 460 0 0\n", Serial.lastLine.c_str());
}

void test_run_rejects_a_stage_with_less_than_ten_seconds_left() {
  stage();
  for (uint32_t now = 1000; now <= 20000; now += 1000) send("PING\n", now);
  send("RUN50\n", 20001);
  TEST_ASSERT_FALSE(active);
  TEST_ASSERT_EQUAL(1, relayWords().size());
}

void test_malformed_input_opens_relay_before_zero() {
  startRun();
  send("\x01\n", 1600);
  assertRunStopped();
}

void test_stop_opens_relay_before_zero() {
  startRun();
  send("STOP\n", 1600);
  assertRunStopped();
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_startup_and_staging_keep_relays_off);
  RUN_TEST(test_run_requires_settle_and_a_ping_after_staging);
  RUN_TEST(test_duplicate_run_opens_relay_before_zero_and_needs_a_new_stage);
  RUN_TEST(test_expired_lease_opens_relay_before_zero);
  RUN_TEST(test_run_timer_cannot_be_extended_by_pings);
  RUN_TEST(test_run_rejects_a_stage_with_less_than_ten_seconds_left);
  RUN_TEST(test_malformed_input_opens_relay_before_zero);
  RUN_TEST(test_stop_opens_relay_before_zero);
  return UNITY_END();
}
