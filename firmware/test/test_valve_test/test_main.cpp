#include <unity.h>
#include <cstring>
#include <vector>
#include "ValveTestCore.h"
#include "ValveTestHardware.h"
#include "ValveTestProfile.h"
#include "Wire.h"

using namespace basu;

void setUp() { fake::resetGpio(); Wire.reset(); }
void tearDown() {}

struct TestIo final : ValveTestIo {
  unsigned begins = 0;
  unsigned writes = 0;
  unsigned enables = 0;
  uint16_t word = 0;
  bool enabled = false;
  bool initialize = true;
  std::vector<char> actions;
  bool begin(const ValveTestConfig& config) override {
    ++begins;
    if (!initialize) return false;
    writeDisabledWord(static_cast<uint16_t>(config.restWord));
    return true;
  }
  void writeDisabledWord(uint16_t value) override {
    word = value;
    enabled = false;
    ++writes;
    actions.push_back('D');
  }
  void enableOutputs() override { enabled = true; ++enables; actions.push_back('E'); }
};

// Arbitrary nonsequential/mixed-polarity fixture, NEVER a real rig profile.
ValveTestConfig reviewedFixture() {
  ValveTestConfig config;
  config.profileId = "native-test.fixture-1";
  config.reviewed = true;
  config.mappingVerified = true;
  config.restWordVerified = true;
  config.resetOeSafeVerified = true;
  config.solenoidLoadsVerified = true;
  config.pumpExcludedVerified = true;
  config.valveBits = {{9, 1, 14, 6, 11, 3, 15}};
  config.restWord = 0xa55a;
  return config;
}

void armFixture(ValveTestCore& core, uint32_t now = 0) {
  core.begin();
  core.heartbeat(now);
  TEST_ASSERT_NULL(core.arm("native-test.fixture-1", true, true, true, now));
}

ValveTestReply request(ValveTestCore& core, const char* frame, uint32_t now) {
  JsonDocument document;
  ValveTestReply reply;
  reply.error = decodeObject(frame, std::strlen(frame), document);
  if (reply.error) return reply;
  return handleValveTestRequest(core, document.as<JsonVariantConst>(), now);
}

void test_factory_profile_is_locked_and_all_commands_leave_gpio_untouched() {
  ValveTestHardware hardware;
  ValveTestCore core(compiledValveTestConfig(), hardware);
  core.begin();
  TEST_ASSERT_FALSE(core.profileVerified());
  TEST_ASSERT_EQUAL_STRING("locked", valveTestStateName(core.state()));
  TEST_ASSERT_EQUAL_STRING("UNVERIFIED", core.profileId().c_str());
  TEST_ASSERT_FALSE(core.fault().empty());
  TEST_ASSERT_NULL(request(core, R"({"v":1,"id":1,"cmd":"hello"})", 0).error);
  core.heartbeat(0);
  TEST_ASSERT_NOT_NULL(core.arm("UNVERIFIED", true, true, true, 0));
  TEST_ASSERT_NOT_NULL(core.pulse(1, 500, 0));
  core.stop();
  core.tick(5000);
  TEST_ASSERT_EQUAL(0, fake::gpioCalls);
  TEST_ASSERT_EQUAL(0, Wire.beginCount);
  TEST_ASSERT_FALSE(core.outputsEnabled());
  TEST_ASSERT_EQUAL(0, core.activeValve());
  TEST_ASSERT_EQUAL(0, core.remainingMs(5000));
}

void test_each_missing_review_gate_prevents_even_io_initialization() {
  for (unsigned index = 0; index < 6; ++index) {
    auto config = reviewedFixture();
    bool* gates[] = {&config.reviewed, &config.mappingVerified, &config.restWordVerified,
                    &config.resetOeSafeVerified, &config.solenoidLoadsVerified, &config.pumpExcludedVerified};
    *gates[index] = false;
    TestIo io;
    ValveTestCore core(config, io);
    core.begin();
    TEST_ASSERT_FALSE(core.profileVerified());
    TEST_ASSERT_EQUAL(0, io.begins);
    TEST_ASSERT_EQUAL(0, io.writes);
    TEST_ASSERT_EQUAL(0, io.enables);
  }
}

void test_profile_requires_seven_unique_bits_full_rest_word_and_unambiguous_id() {
  auto config = reviewedFixture();
  TEST_ASSERT_NULL(validateValveTestConfig(config));
  config.valveBits[6] = config.valveBits[0];
  TEST_ASSERT_NOT_NULL(validateValveTestConfig(config));
  config = reviewedFixture(); config.valveBits[6] = 16;
  TEST_ASSERT_NOT_NULL(validateValveTestConfig(config));
  config = reviewedFixture(); config.valveBits[0] = -1;
  TEST_ASSERT_NOT_NULL(validateValveTestConfig(config));
  config = reviewedFixture(); config.restWord = 65536;
  TEST_ASSERT_NOT_NULL(validateValveTestConfig(config));
  for (const char* id : {"", "UNVERIFIED", "two words", "bad/id", "bad:id", "bad\\id"}) {
    config = reviewedFixture(); config.profileId = id;
    TEST_ASSERT_NOT_NULL(validateValveTestConfig(config));
  }
  config = reviewedFixture(); config.profileId = std::string(65, 'x');
  TEST_ASSERT_NOT_NULL(validateValveTestConfig(config));
  config.profileId = std::string(64, 'x');
  TEST_ASSERT_NULL(validateValveTestConfig(config));
}

void test_hardware_initialization_failure_cannot_report_a_verified_or_armed_profile() {
  TestIo io;
  io.initialize = false;
  ValveTestCore core(reviewedFixture(), io);
  core.begin();
  core.heartbeat(0);
  TEST_ASSERT_FALSE(core.profileVerified());
  TEST_ASSERT_EQUAL_STRING("locked", valveTestStateName(core.state()));
  TEST_ASSERT_NOT_NULL(core.arm("native-test.fixture-1", true, true, true, 0));
  TEST_ASSERT_EQUAL(0, io.enables);
}

void test_arm_requires_matching_profile_all_attestations_and_fresh_heartbeat() {
  TestIo io;
  ValveTestCore core(reviewedFixture(), io);
  core.begin();
  TEST_ASSERT_NOT_NULL(core.arm("native-test.fixture-1", true, true, true, 0));
  core.heartbeat(0);
  TEST_ASSERT_NOT_NULL(core.arm("another-profile", true, true, true, 0));
  TEST_ASSERT_NOT_NULL(core.arm("native-test.fixture-1", false, true, true, 0));
  TEST_ASSERT_NOT_NULL(core.arm("native-test.fixture-1", true, false, true, 0));
  TEST_ASSERT_NOT_NULL(core.arm("native-test.fixture-1", true, true, false, 0));
  TEST_ASSERT_NOT_NULL(core.arm("native-test.fixture-1", true, true, true, 1000));
  core.heartbeat(1001);
  TEST_ASSERT_NULL(core.arm("native-test.fixture-1", true, true, true, 1001));
  TEST_ASSERT_EQUAL_STRING("ready", valveTestStateName(core.state()));
  TEST_ASSERT_FALSE(core.outputsEnabled());
  TEST_ASSERT_FALSE(io.enabled);
  TEST_ASSERT_EQUAL(0, io.enables);
}

void test_each_named_valve_toggles_only_its_reviewed_bit_and_preserves_unused_outputs() {
  const auto config = reviewedFixture();
  TestIo io;
  ValveTestCore core(config, io);
  armFixture(core);
  for (uint32_t valve = 1; valve <= 7; ++valve) {
    const uint32_t now = valve * 100;
    core.heartbeat(now);
    TEST_ASSERT_NULL(core.pulse(valve, 100, now));
    TEST_ASSERT_EQUAL_HEX16(config.restWord ^ (1U << config.valveBits[valve - 1]), io.word);
    TEST_ASSERT_EQUAL(valve, core.activeValve());
    TEST_ASSERT_EQUAL(100, core.remainingMs(now));
    TEST_ASSERT_TRUE(io.enabled);
    TEST_ASSERT_TRUE(core.outputsEnabled());
    core.tick(now + 100);
    TEST_ASSERT_FALSE(io.enabled);
    TEST_ASSERT_FALSE(core.outputsEnabled());
    TEST_ASSERT_EQUAL_HEX16(config.restWord, io.word);
    TEST_ASSERT_EQUAL(0, core.activeValve());
    TEST_ASSERT_EQUAL(0, core.remainingMs(now + 100));
    TEST_ASSERT_EQUAL_STRING("ready", valveTestStateName(core.state()));
  }
}

void test_pulse_bounds_and_busy_requests_cannot_replace_or_extend_a_pulse() {
  TestIo io;
  ValveTestCore core(reviewedFixture(), io);
  armFixture(core);
  TEST_ASSERT_NOT_NULL(core.pulse(0, 500, 0));
  TEST_ASSERT_NOT_NULL(core.pulse(8, 500, 0));
  TEST_ASSERT_NOT_NULL(core.pulse(1, 99, 0));
  TEST_ASSERT_NOT_NULL(core.pulse(1, 2001, 0));
  TEST_ASSERT_NULL(core.pulse(3, 500, 0));
  const auto writes = io.writes;
  TEST_ASSERT_NOT_NULL(core.pulse(4, 2000, 400));
  TEST_ASSERT_NOT_NULL(core.arm("native-test.fixture-1", true, true, true, 400));
  TEST_ASSERT_EQUAL(writes, io.writes);
  TEST_ASSERT_EQUAL(3, core.activeValve());
  TEST_ASSERT_EQUAL(1, core.remainingMs(499));
  core.tick(500);
  TEST_ASSERT_FALSE(io.enabled);
}

void test_two_second_deadline_is_not_extended_by_fresh_heartbeats() {
  TestIo io;
  ValveTestCore core(reviewedFixture(), io);
  armFixture(core);
  TEST_ASSERT_NULL(core.pulse(7, 2000, 0));
  for (uint32_t now = 250; now < 2000; now += 250) core.heartbeat(now);
  core.tick(1999);
  TEST_ASSERT_TRUE(io.enabled);
  core.tick(2000);
  TEST_ASSERT_FALSE(io.enabled);
  TEST_ASSERT_EQUAL_STRING("ready", valveTestStateName(core.state()));
  TEST_ASSERT_EQUAL(0, core.activeValve());
}

void test_unplug_and_late_heartbeat_fault_and_cannot_rearm_without_stop() {
  TestIo io;
  ValveTestCore core(reviewedFixture(), io);
  armFixture(core);
  TEST_ASSERT_NULL(core.pulse(1, 2000, 0));
  core.tick(999);
  TEST_ASSERT_TRUE(io.enabled);
  core.heartbeat(1000);
  TEST_ASSERT_FALSE(io.enabled);
  TEST_ASSERT_EQUAL_STRING("fault", valveTestStateName(core.state()));
  TEST_ASSERT_EQUAL_STRING("heartbeat_timeout", core.fault().c_str());
  TEST_ASSERT_NOT_NULL(core.pulse(1, 500, 1000));
  TEST_ASSERT_NOT_NULL(core.arm("native-test.fixture-1", true, true, true, 1000));
  core.stop();
  TEST_ASSERT_NOT_NULL(core.arm("native-test.fixture-1", true, true, true, 1001));
  core.heartbeat(1001);
  TEST_ASSERT_NULL(core.arm("native-test.fixture-1", true, true, true, 1001));
  TEST_ASSERT_FALSE(io.enabled);
}

void test_ready_lease_expires_even_when_no_valve_was_pulsed() {
  TestIo io;
  ValveTestCore core(reviewedFixture(), io);
  armFixture(core);
  core.tick(1000);
  TEST_ASSERT_EQUAL_STRING("fault", valveTestStateName(core.state()));
  TEST_ASSERT_FALSE(io.enabled);
  TEST_ASSERT_EQUAL(0, io.enables);
}

void test_stop_and_new_hello_disable_and_invalidate_arm_and_heartbeat() {
  for (bool hello : {false, true}) {
    TestIo io;
    ValveTestCore core(reviewedFixture(), io);
    armFixture(core);
    TEST_ASSERT_NULL(core.pulse(2, 500, 0));
    const auto reply = request(core, hello ? R"({"v":1,"id":9,"cmd":"hello"})" :
                               R"({"v":1,"id":9,"cmd":"stop"})", 10);
    TEST_ASSERT_NULL(reply.error);
    TEST_ASSERT_EQUAL(9, reply.id);
    TEST_ASSERT_EQUAL(hello, reply.hello);
    TEST_ASSERT_FALSE(io.enabled);
    TEST_ASSERT_EQUAL_HEX16(reviewedFixture().restWord, io.word);
    TEST_ASSERT_EQUAL_STRING("disarmed", valveTestStateName(core.state()));
    TEST_ASSERT_NOT_NULL(core.pulse(2, 500, 11));
    TEST_ASSERT_NOT_NULL(core.arm("native-test.fixture-1", true, true, true, 11));
  }
}

void test_reboot_does_not_restore_prior_arm_or_pulse() {
  TestIo io;
  ValveTestCore previous(reviewedFixture(), io);
  armFixture(previous);
  TEST_ASSERT_NULL(previous.pulse(2, 500, 0));
  ValveTestCore restarted(reviewedFixture(), io);
  restarted.begin();
  TEST_ASSERT_FALSE(io.enabled);
  TEST_ASSERT_EQUAL_STRING("disarmed", valveTestStateName(restarted.state()));
  TEST_ASSERT_NOT_NULL(restarted.pulse(2, 500, 10));
}

void test_unsigned_millis_wrap_preserves_duration_and_heartbeat_deadline() {
  TestIo io;
  ValveTestCore core(reviewedFixture(), io);
  const uint32_t start = UINT32_MAX - 300;
  armFixture(core, start);
  TEST_ASSERT_NULL(core.pulse(6, 500, start));
  core.heartbeat(start + 250);
  core.tick(start + 499);
  TEST_ASSERT_TRUE(io.enabled);
  core.tick(start + 500);
  TEST_ASSERT_FALSE(io.enabled);
  TEST_ASSERT_EQUAL_STRING("ready", valveTestStateName(core.state()));
  core.tick(start + 1250);
  TEST_ASSERT_EQUAL_STRING("heartbeat_timeout", core.fault().c_str());
}

void test_strict_protocol_rejects_types_masks_pump_recipe_and_profile_mutations() {
  TestIo io;
  ValveTestCore core(reviewedFixture(), io);
  armFixture(core);
  const auto writes = io.writes;
  const char* frames[] = {
    R"({"v":1,"id":1,"cmd":"start"})",
    R"({"v":1,"id":2,"cmd":"load_recipe","recipe":{}})",
    R"({"v":1,"id":3,"cmd":"manual","pump_percent":100})",
    R"({"v":1,"id":4,"cmd":"bench_pulse","bit":1,"duration_ms":500})",
    R"({"v":1,"id":5,"cmd":"valve_pulse","valve":true,"duration_ms":500})",
    R"({"v":1,"id":6,"cmd":"valve_pulse","valve":1,"duration_ms":500.0})",
    R"({"v":1,"id":7,"cmd":"valve_pulse","valve":1,"duration_ms":-1})",
    R"({"v":1,"id":8,"cmd":"valve_pulse","valve":1,"duration_ms":4294967296})",
    R"({"v":1,"id":9,"cmd":"valve_pulse","valve":1,"duration_ms":500,"mask":65535})",
    R"({"v":1,"id":10,"cmd":"valve_arm","profile_id":"native-test.fixture-1","wiring_checked":1,"pump_isolated":true,"test_area_ready":true})",
    R"({"v":1,"id":11,"cmd":"set_profile","profile_id":"fake"})",
    R"({"v":true,"id":12,"cmd":"heartbeat"})",
    R"({"v":1,"id":true,"cmd":"stop"})",
    R"({"v":1,"id":13,"cmd":"heartbeat","mask":0})",
  };
  for (const char* frame : frames) TEST_ASSERT_NOT_NULL(request(core, frame, 900).error);
  TEST_ASSERT_EQUAL(writes, io.writes);
  TEST_ASSERT_EQUAL(0, io.enables);
  TEST_ASSERT_EQUAL_STRING("native-test.fixture-1", core.profileId().c_str());
  core.tick(1000);  // Invalid frames did not extend the lease.
  TEST_ASSERT_EQUAL_STRING("heartbeat_timeout", core.fault().c_str());
}

void test_json_workflow_needs_true_attestations_then_accepts_one_named_valve() {
  TestIo io;
  ValveTestCore core(reviewedFixture(), io);
  core.begin();
  TEST_ASSERT_NULL(request(core, R"({"v":1,"id":1,"cmd":"hello"})", 0).error);
  TEST_ASSERT_NULL(request(core, R"({"v":1,"id":2,"cmd":"heartbeat"})", 0).error);
  TEST_ASSERT_NOT_NULL(request(core, R"({"v":1,"id":3,"cmd":"valve_arm","profile_id":"native-test.fixture-1","wiring_checked":true,"pump_isolated":false,"test_area_ready":true})", 0).error);
  TEST_ASSERT_NULL(request(core, R"({"v":1,"id":4,"cmd":"valve_arm","profile_id":"native-test.fixture-1","wiring_checked":true,"pump_isolated":true,"test_area_ready":true})", 0).error);
  const auto reply = request(core, R"({"v":1,"id":5,"cmd":"valve_pulse","valve":4,"duration_ms":500})", 0);
  TEST_ASSERT_NULL(reply.error);
  TEST_ASSERT_EQUAL(5, reply.id);
  TEST_ASSERT_EQUAL(4, core.activeValve());
  TEST_ASSERT_TRUE(io.enabled);
}

void test_real_adapter_only_touches_reviewed_control_pins_disables_before_shift_and_stop() {
  ValveTestHardware hardware;
  TEST_ASSERT_FALSE(hardware.begin(ValveTestConfig{}));
  TEST_ASSERT_EQUAL(0, fake::gpioCalls);
  const auto config = reviewedFixture();
  ValveTestCore core(config, hardware);
  armFixture(core);
  TEST_ASSERT_EQUAL(5, fake::gpioEvents[0].pin);
  TEST_ASSERT_TRUE(fake::gpioEvents[0].write);
  TEST_ASSERT_EQUAL(HIGH, fake::gpioEvents[0].value);
  fake::resetGpio();
  TEST_ASSERT_NULL(core.pulse(5, 500, 0));
  TEST_ASSERT_EQUAL(5, fake::gpioEvents[0].pin);
  TEST_ASSERT_EQUAL(HIGH, fake::gpioEvents[0].value);
  uint16_t shifted = 0;
  int data = 0;
  unsigned clocks = 0;
  for (const auto& call : fake::gpioEvents) {
    TEST_ASSERT_TRUE(call.pin == 14 || call.pin == 13 || call.pin == 12 || call.pin == 5);
    if (call.write && call.pin == 14) data = call.value;
    if (call.write && call.pin == 13 && call.value == HIGH) {
      shifted = static_cast<uint16_t>((shifted << 1) | data);
      ++clocks;
    }
  }
  TEST_ASSERT_EQUAL(16, clocks);
  TEST_ASSERT_EQUAL_HEX16(config.restWord ^ (1U << config.valveBits[4]), shifted);
  TEST_ASSERT_EQUAL(LOW, fake::levels[5]);
  fake::resetGpio();
  core.stop();
  TEST_ASSERT_EQUAL(5, fake::gpioEvents[0].pin);
  TEST_ASSERT_EQUAL(HIGH, fake::gpioEvents[0].value);
  TEST_ASSERT_EQUAL(HIGH, fake::levels[5]);
  TEST_ASSERT_EQUAL(0, Wire.beginCount);
  TEST_ASSERT_EQUAL(0, Wire.transactionCount);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_factory_profile_is_locked_and_all_commands_leave_gpio_untouched);
  RUN_TEST(test_each_missing_review_gate_prevents_even_io_initialization);
  RUN_TEST(test_profile_requires_seven_unique_bits_full_rest_word_and_unambiguous_id);
  RUN_TEST(test_hardware_initialization_failure_cannot_report_a_verified_or_armed_profile);
  RUN_TEST(test_arm_requires_matching_profile_all_attestations_and_fresh_heartbeat);
  RUN_TEST(test_each_named_valve_toggles_only_its_reviewed_bit_and_preserves_unused_outputs);
  RUN_TEST(test_pulse_bounds_and_busy_requests_cannot_replace_or_extend_a_pulse);
  RUN_TEST(test_two_second_deadline_is_not_extended_by_fresh_heartbeats);
  RUN_TEST(test_unplug_and_late_heartbeat_fault_and_cannot_rearm_without_stop);
  RUN_TEST(test_ready_lease_expires_even_when_no_valve_was_pulsed);
  RUN_TEST(test_stop_and_new_hello_disable_and_invalidate_arm_and_heartbeat);
  RUN_TEST(test_reboot_does_not_restore_prior_arm_or_pulse);
  RUN_TEST(test_unsigned_millis_wrap_preserves_duration_and_heartbeat_deadline);
  RUN_TEST(test_strict_protocol_rejects_types_masks_pump_recipe_and_profile_mutations);
  RUN_TEST(test_json_workflow_needs_true_attestations_then_accepts_one_named_valve);
  RUN_TEST(test_real_adapter_only_touches_reviewed_control_pins_disables_before_shift_and_stop);
  return UNITY_END();
}
