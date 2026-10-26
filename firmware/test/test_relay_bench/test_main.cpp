#include <unity.h>
#include <cstring>
#include <vector>
#include "RelayBenchCore.h"
#include "RelayBenchHardware.h"
#include "Wire.h"

using namespace basu;

void setUp() { fake::resetGpio(); Wire.reset(); }
void tearDown() {}

struct BenchIo final : RelayBenchIo {
  uint16_t word = 0;
  bool enabled = false;
  unsigned writes = 0;
  unsigned enables = 0;
  std::vector<char> actions;
  void writeDisabledWord(uint16_t value) override {
    word = value;
    enabled = false;
    ++writes;
    actions.push_back('D');
  }
  void enableOutputs() override {
    enabled = true;
    ++enables;
    actions.push_back('E');
  }
};

void prepareBaseline(RelayBenchCore& core, uint16_t word = 0, uint32_t now = 0, uint32_t id = 10) {
  core.heartbeat(now);
  TEST_ASSERT_NULL(core.probe(id, word, 100, true, now));
  core.tick(now + 100);
  TEST_ASSERT_NULL(core.confirm(id, word, true, true, now + 100));
}

RelayBenchReply request(RelayBenchCore& core, const char* frame, uint32_t now) {
  JsonDocument document;
  RelayBenchReply result;
  result.error = decodeObject(frame, std::strlen(frame), document);
  if (result.error) return result;
  return handleRelayBenchRequest(core, document.as<JsonVariantConst>(), now);
}

void test_boot_disables_oe_before_other_gpio_and_never_touches_interfaces() {
  RelayBenchHardware hardware;
  TEST_ASSERT_EQUAL(0, fake::gpioCalls);
  hardware.begin();
  TEST_ASSERT_TRUE(fake::gpioEvents.size() > 2);
  TEST_ASSERT_TRUE(fake::gpioEvents[0].write);
  TEST_ASSERT_EQUAL(5, fake::gpioEvents[0].pin);
  TEST_ASSERT_EQUAL(HIGH, fake::gpioEvents[0].value);
  TEST_ASSERT_FALSE(fake::gpioEvents[1].write);
  TEST_ASSERT_EQUAL(5, fake::gpioEvents[1].pin);
  TEST_ASSERT_EQUAL(OUTPUT, fake::gpioEvents[1].value);
  for (const auto& call : fake::gpioEvents) {
    TEST_ASSERT_TRUE(call.pin == 14 || call.pin == 13 || call.pin == 12 || call.pin == 5);
    if (call.write && call.pin == 5) TEST_ASSERT_EQUAL(HIGH, call.value);
  }
  TEST_ASSERT_EQUAL(HIGH, fake::levels[5]);
  TEST_ASSERT_EQUAL(0, Wire.beginCount);
  TEST_ASSERT_EQUAL(0, Wire.transactionCount);
}

void test_hardware_disables_before_latching_all_sixteen_bits_msb_first() {
  RelayBenchHardware hardware;
  hardware.begin();
  hardware.enableOutputs();
  fake::resetGpio();
  hardware.writeDisabledWord(0xa315);
  TEST_ASSERT_TRUE(fake::gpioEvents[0].write);
  TEST_ASSERT_EQUAL(5, fake::gpioEvents[0].pin);
  TEST_ASSERT_EQUAL(HIGH, fake::gpioEvents[0].value);
  TEST_ASSERT_EQUAL(12, fake::gpioEvents[1].pin);
  TEST_ASSERT_EQUAL(LOW, fake::gpioEvents[1].value);
  uint16_t shifted = 0;
  unsigned clocks = 0;
  int data = 0;
  for (const auto& call : fake::gpioEvents) {
    TEST_ASSERT_TRUE(call.pin == 14 || call.pin == 13 || call.pin == 12 || call.pin == 5);
    if (call.write && call.pin == 14) data = call.value;
    if (call.write && call.pin == 13 && call.value == HIGH) {
      shifted = static_cast<uint16_t>((shifted << 1) | data);
      ++clocks;
    }
    if (call.write && call.pin == 5) TEST_ASSERT_EQUAL(HIGH, call.value);
  }
  TEST_ASSERT_EQUAL(16, clocks);
  TEST_ASSERT_EQUAL_HEX16(0xa315, shifted);
  TEST_ASSERT_EQUAL(12, fake::gpioEvents.back().pin);
  TEST_ASSERT_EQUAL(HIGH, fake::gpioEvents.back().value);
  TEST_ASSERT_EQUAL(HIGH, fake::levels[5]);
}

void test_probe_requires_fresh_heartbeat_valid_duration_and_unloaded_attestation() {
  BenchIo io;
  RelayBenchCore core(io);
  TEST_ASSERT_NOT_NULL(core.probe(1, 0, 500, true, 0));
  core.heartbeat(0);
  TEST_ASSERT_NOT_NULL(core.probe(1, 0, 500, false, 0));
  TEST_ASSERT_NOT_NULL(core.probe(1, 1, 500, true, 0));
  TEST_ASSERT_NOT_NULL(core.probe(1, 0, 99, true, 0));
  TEST_ASSERT_NOT_NULL(core.probe(1, 0, 2001, true, 0));
  TEST_ASSERT_NOT_NULL(core.probe(0, 0, 500, true, 0));
  TEST_ASSERT_NOT_NULL(core.probe(1, 0, 500, true, 1000));
  TEST_ASSERT_EQUAL(0, io.writes);
  TEST_ASSERT_EQUAL(0, io.enables);
  TEST_ASSERT_EQUAL_STRING("disarmed", relayBenchStateName(core.state()));
}

void test_probe_completion_disables_outputs_before_confirmation() {
  BenchIo io;
  RelayBenchCore core(io);
  core.heartbeat(10);
  TEST_ASSERT_NULL(core.probe(7, 65535, 500, true, 10));
  TEST_ASSERT_EQUAL_HEX16(0xffff, io.word);
  TEST_ASSERT_TRUE(io.enabled);
  TEST_ASSERT_EQUAL('D', io.actions[0]);
  TEST_ASSERT_EQUAL('E', io.actions[1]);
  TEST_ASSERT_NOT_NULL(core.confirm(7, 65535, true, true, 509));
  TEST_ASSERT_EQUAL(1, core.remainingMs(509));
  TEST_ASSERT_FALSE(core.probeCompleted());
  core.tick(510);
  TEST_ASSERT_FALSE(io.enabled);
  TEST_ASSERT_TRUE(core.probeCompleted());
  TEST_ASSERT_FALSE(core.baselineConfirmed());
  TEST_ASSERT_EQUAL(7, core.probeId());
  TEST_ASSERT_EQUAL_STRING("disarmed", relayBenchStateName(core.state()));
  TEST_ASSERT_EQUAL(0, core.remainingMs(510));
  TEST_ASSERT_NOT_NULL(core.confirm(6, 65535, true, true, 510));
  TEST_ASSERT_NOT_NULL(core.confirm(7, 0, true, true, 510));
  TEST_ASSERT_NOT_NULL(core.confirm(7, 65535, false, true, 510));
  TEST_ASSERT_NOT_NULL(core.confirm(7, 65535, true, false, 510));
  TEST_ASSERT_NULL(core.confirm(7, 65535, true, true, 510));
  TEST_ASSERT_EQUAL_STRING("ready", relayBenchStateName(core.state()));
  TEST_ASSERT_FALSE(core.outputsEnabled());
  TEST_ASSERT_FALSE(io.enabled);
}

void test_pulse_toggles_exactly_one_raw_bit_for_either_baseline() {
  for (uint32_t baseline : {0U, 65535U}) {
    BenchIo io;
    RelayBenchCore core(io);
    prepareBaseline(core, static_cast<uint16_t>(baseline));
    for (uint32_t bit = 0; bit < 16; ++bit) {
      const uint32_t now = 100 + bit * 100;
      core.heartbeat(now);
      TEST_ASSERT_NULL(core.pulse(bit, 100, now));
      TEST_ASSERT_EQUAL_HEX16(baseline ^ (1U << bit), io.word);
      TEST_ASSERT_TRUE(io.enabled);
      TEST_ASSERT_EQUAL(bit, core.pulseBit());
      core.tick(now + 100);
      TEST_ASSERT_FALSE(io.enabled);
      TEST_ASSERT_EQUAL_HEX16(baseline, io.word);
      TEST_ASSERT_EQUAL(-1, core.pulseBit());
      TEST_ASSERT_EQUAL_STRING("ready", relayBenchStateName(core.state()));
      TEST_ASSERT_TRUE(core.baselineConfirmed());
    }
  }
}

void test_busy_replacement_cannot_extend_deadline_or_change_baseline() {
  BenchIo io;
  RelayBenchCore core(io);
  prepareBaseline(core);
  TEST_ASSERT_NULL(core.pulse(5, 500, 100));
  const auto writes = io.writes;
  TEST_ASSERT_NOT_NULL(core.pulse(6, 2000, 400));
  TEST_ASSERT_NOT_NULL(core.probe(20, 65535, 2000, true, 400));
  TEST_ASSERT_EQUAL(writes, io.writes);
  TEST_ASSERT_EQUAL(0, core.baselineWord());
  TEST_ASSERT_EQUAL(5, core.pulseBit());
  core.tick(600);
  TEST_ASSERT_FALSE(io.enabled);
  TEST_ASSERT_EQUAL_STRING("ready", relayBenchStateName(core.state()));
}

void test_hard_two_second_cap_is_not_extended_by_heartbeats() {
  BenchIo io;
  RelayBenchCore core(io);
  core.heartbeat(0);
  TEST_ASSERT_NULL(core.probe(1, 0, 2000, true, 0));
  for (uint32_t now = 250; now < 2000; now += 250) core.heartbeat(now);
  core.tick(1999);
  TEST_ASSERT_TRUE(io.enabled);
  TEST_ASSERT_EQUAL(1, core.remainingMs(1999));
  core.tick(2000);
  TEST_ASSERT_FALSE(io.enabled);
  TEST_ASSERT_TRUE(core.probeCompleted());
  TEST_ASSERT_NULL(core.confirm(1, 0, true, true, 2000));
  TEST_ASSERT_NOT_NULL(core.pulse(16, 100, 2000));
  TEST_ASSERT_NOT_NULL(core.pulse(0, 2001, 2000));
  TEST_ASSERT_NULL(core.pulse(0, 2000, 2000));
  for (uint32_t now = 2250; now < 4000; now += 250) core.heartbeat(now);
  core.tick(4000);
  TEST_ASSERT_FALSE(io.enabled);
  TEST_ASSERT_TRUE(core.baselineConfirmed());
}

void test_unplug_deadline_disables_and_late_heartbeat_cannot_rearm() {
  BenchIo io;
  RelayBenchCore core(io);
  prepareBaseline(core);
  core.heartbeat(100);
  TEST_ASSERT_NULL(core.pulse(3, 2000, 100));
  core.tick(1099);
  TEST_ASSERT_TRUE(io.enabled);
  core.heartbeat(1100);  // Timeout must run before accepting this late heartbeat.
  TEST_ASSERT_FALSE(io.enabled);
  TEST_ASSERT_EQUAL_STRING("fault", relayBenchStateName(core.state()));
  TEST_ASSERT_EQUAL_STRING("heartbeat_timeout", core.fault().c_str());
  TEST_ASSERT_FALSE(core.baselineConfirmed());
  TEST_ASSERT_FALSE(core.probeCompleted());
  TEST_ASSERT_EQUAL(0, core.probeId());
  TEST_ASSERT_NOT_NULL(core.pulse(3, 100, 1101));
  TEST_ASSERT_NOT_NULL(core.probe(2, 0, 100, true, 1101));
  core.stop();
  TEST_ASSERT_TRUE(core.fault().empty());
  TEST_ASSERT_EQUAL_STRING("disarmed", relayBenchStateName(core.state()));
  TEST_ASSERT_NOT_NULL(core.confirm(10, 0, true, true, 1101));
  TEST_ASSERT_NULL(core.probe(2, 0, 100, true, 1101));
}

void test_ready_and_completed_probe_expire_even_with_outputs_disabled() {
  for (bool confirm : {false, true}) {
    BenchIo io;
    RelayBenchCore core(io);
    core.heartbeat(0);
    TEST_ASSERT_NULL(core.probe(3, 0, 100, true, 0));
    core.tick(100);
    if (confirm) TEST_ASSERT_NULL(core.confirm(3, 0, true, true, 100));
    TEST_ASSERT_FALSE(io.enabled);
    core.tick(1000);
    TEST_ASSERT_EQUAL_STRING("fault", relayBenchStateName(core.state()));
    TEST_ASSERT_FALSE(core.probeCompleted());
    TEST_ASSERT_FALSE(core.baselineConfirmed());
    TEST_ASSERT_EQUAL(0, core.probeId());
  }
}

void test_stop_and_new_probe_invalidate_old_observation() {
  BenchIo io;
  RelayBenchCore core(io);
  prepareBaseline(core);
  core.heartbeat(100);
  TEST_ASSERT_NULL(core.probe(11, 65535, 100, true, 100));
  TEST_ASSERT_FALSE(core.probeCompleted());
  TEST_ASSERT_FALSE(core.baselineConfirmed());
  core.tick(200);
  TEST_ASSERT_NOT_NULL(core.confirm(10, 65535, true, true, 200));
  TEST_ASSERT_NULL(core.confirm(11, 65535, true, true, 200));
  TEST_ASSERT_NULL(core.pulse(15, 500, 200));
  core.stop();
  TEST_ASSERT_FALSE(io.enabled);
  TEST_ASSERT_FALSE(core.baselineConfirmed());
  TEST_ASSERT_FALSE(core.probeCompleted());
  TEST_ASSERT_EQUAL(0, core.probeId());
  TEST_ASSERT_EQUAL_HEX16(65535, io.word);
  TEST_ASSERT_NOT_NULL(core.pulse(0, 500, 200));
  TEST_ASSERT_NOT_NULL(core.confirm(11, 65535, true, true, 200));
}

void test_new_hello_disarms_existing_session_and_requires_new_heartbeat() {
  BenchIo io;
  RelayBenchCore core(io);
  prepareBaseline(core);
  TEST_ASSERT_NULL(core.pulse(1, 500, 100));
  const auto result = request(core, R"({"v":1,"id":20,"cmd":"hello"})", 101);
  TEST_ASSERT_NULL(result.error);
  TEST_ASSERT_TRUE(result.hello);
  TEST_ASSERT_EQUAL(20, result.id);
  TEST_ASSERT_FALSE(io.enabled);
  TEST_ASSERT_FALSE(core.baselineConfirmed());
  TEST_ASSERT_EQUAL(0, core.probeId());
  TEST_ASSERT_NOT_NULL(core.probe(21, 0, 500, true, 102));
  TEST_ASSERT_NULL(request(core, R"({"v":1,"id":21,"cmd":"heartbeat"})", 102).error);
  TEST_ASSERT_NULL(core.probe(22, 0, 500, true, 102));
}

void test_timer_and_heartbeat_use_unsigned_millis_rollover() {
  BenchIo io;
  RelayBenchCore core(io);
  const uint32_t start = UINT32_MAX - 300;
  core.heartbeat(start);
  TEST_ASSERT_NULL(core.probe(1, 65535, 500, true, start));
  core.heartbeat(start + 250);
  core.tick(start + 500);
  TEST_ASSERT_TRUE(core.probeCompleted());
  TEST_ASSERT_NULL(core.confirm(1, 65535, true, true, start + 500));
  TEST_ASSERT_NULL(core.pulse(15, 500, start + 500));
  core.tick(start + 999);
  TEST_ASSERT_TRUE(io.enabled);
  core.tick(start + 1000);
  TEST_ASSERT_FALSE(io.enabled);
  TEST_ASSERT_TRUE(core.baselineConfirmed());
  core.tick(start + 1250);
  TEST_ASSERT_EQUAL_STRING("heartbeat_timeout", core.fault().c_str());
}

void test_json_types_and_experiment_commands_cannot_touch_gpio_or_refresh_lease() {
  BenchIo io;
  RelayBenchCore core(io);
  const char* invalid[] = {
    R"({"v":1,"id":1,"cmd":"start"})",
    R"({"v":1,"id":2,"cmd":"manual","valves":[true],"pump_percent":100})",
    R"({"v":1,"id":3,"cmd":"load_recipe","recipe":{}})",
    R"({"v":1,"id":4,"cmd":"bench_probe","baseline_word":false,"duration_ms":500,"loads_disconnected":true})",
    R"({"v":1,"id":5,"cmd":"bench_probe","baseline_word":0,"duration_ms":500.0,"loads_disconnected":true})",
    R"({"v":1,"id":6,"cmd":"bench_probe","baseline_word":0,"duration_ms":500,"loads_disconnected":1})",
    R"({"v":1,"id":7,"cmd":"bench_probe","baseline_word":0,"duration_ms":4294967296,"loads_disconnected":true})",
    R"({"v":1,"id":8,"cmd":"bench_probe","baseline_word":-1,"duration_ms":500,"loads_disconnected":true})",
    R"({"v":1,"id":9,"cmd":"bench_pulse","bit":true,"duration_ms":500})",
    R"({"v":1,"id":10,"cmd":"bench_confirm","probe_id":true,"baseline_word":0,"loads_disconnected":true,"all_relays_off":true})",
    R"({"v":1,"id":true,"cmd":"stop"})",
    R"({"v":2,"id":11,"cmd":"heartbeat"})",
  };
  for (const auto* frame : invalid) TEST_ASSERT_NOT_NULL(request(core, frame, 0).error);
  TEST_ASSERT_EQUAL(0, io.writes);
  TEST_ASSERT_EQUAL(0, io.enables);
  TEST_ASSERT_EQUAL(0, fake::gpioCalls);
  TEST_ASSERT_NOT_NULL(core.probe(12, 0, 500, true, 0));
  prepareBaseline(core);
  TEST_ASSERT_NOT_NULL(request(core, R"({"v":2,"id":13,"cmd":"heartbeat"})", 999).error);
  core.tick(1000);
  TEST_ASSERT_FALSE(core.baselineConfirmed());
  TEST_ASSERT_EQUAL_STRING("heartbeat_timeout", core.fault().c_str());
}

void test_valid_json_workflow_requires_exact_completed_probe_id() {
  BenchIo io;
  RelayBenchCore core(io);
  TEST_ASSERT_NULL(request(core, R"({"v":1,"id":1,"cmd":"heartbeat"})", 0).error);
  TEST_ASSERT_NULL(request(core, R"({"v":1,"id":2,"cmd":"bench_probe","baseline_word":0,"duration_ms":100,"loads_disconnected":true})", 0).error);
  core.tick(100);
  TEST_ASSERT_NOT_NULL(request(core, R"({"v":1,"id":3,"cmd":"bench_confirm","probe_id":1,"baseline_word":0,"loads_disconnected":true,"all_relays_off":true})", 100).error);
  TEST_ASSERT_NULL(request(core, R"({"v":1,"id":4,"cmd":"bench_confirm","probe_id":2,"baseline_word":0,"loads_disconnected":true,"all_relays_off":true})", 100).error);
  TEST_ASSERT_NULL(request(core, R"({"v":1,"id":5,"cmd":"bench_pulse","bit":15,"duration_ms":500})", 100).error);
  TEST_ASSERT_EQUAL_HEX16(0x8000, io.word);
  TEST_ASSERT_NULL(request(core, R"({"v":1,"id":6,"cmd":"stop"})", 101).error);
  TEST_ASSERT_FALSE(io.enabled);
  TEST_ASSERT_EQUAL_STRING("disarmed", relayBenchStateName(core.state()));
}

void test_real_gpio_adapter_stop_disables_before_restore_with_no_other_pins() {
  RelayBenchHardware hardware;
  hardware.begin();
  RelayBenchCore core(hardware);
  prepareBaseline(core);
  TEST_ASSERT_NULL(core.pulse(4, 500, 100));
  TEST_ASSERT_EQUAL(LOW, fake::levels[5]);
  fake::resetGpio();
  core.stop();
  TEST_ASSERT_EQUAL(5, fake::gpioEvents[0].pin);
  TEST_ASSERT_EQUAL(HIGH, fake::gpioEvents[0].value);
  TEST_ASSERT_EQUAL(HIGH, fake::levels[5]);
  for (const auto& call : fake::gpioEvents)
    TEST_ASSERT_TRUE(call.pin == 14 || call.pin == 13 || call.pin == 12 || call.pin == 5);
  TEST_ASSERT_EQUAL(0, Wire.beginCount);
  TEST_ASSERT_EQUAL(0, Wire.transactionCount);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_boot_disables_oe_before_other_gpio_and_never_touches_interfaces);
  RUN_TEST(test_hardware_disables_before_latching_all_sixteen_bits_msb_first);
  RUN_TEST(test_probe_requires_fresh_heartbeat_valid_duration_and_unloaded_attestation);
  RUN_TEST(test_probe_completion_disables_outputs_before_confirmation);
  RUN_TEST(test_pulse_toggles_exactly_one_raw_bit_for_either_baseline);
  RUN_TEST(test_busy_replacement_cannot_extend_deadline_or_change_baseline);
  RUN_TEST(test_hard_two_second_cap_is_not_extended_by_heartbeats);
  RUN_TEST(test_unplug_deadline_disables_and_late_heartbeat_cannot_rearm);
  RUN_TEST(test_ready_and_completed_probe_expire_even_with_outputs_disabled);
  RUN_TEST(test_stop_and_new_probe_invalidate_old_observation);
  RUN_TEST(test_new_hello_disarms_existing_session_and_requires_new_heartbeat);
  RUN_TEST(test_timer_and_heartbeat_use_unsigned_millis_rollover);
  RUN_TEST(test_json_types_and_experiment_commands_cannot_touch_gpio_or_refresh_lease);
  RUN_TEST(test_valid_json_workflow_requires_exact_completed_probe_id);
  RUN_TEST(test_real_gpio_adapter_stop_disables_before_restore_with_no_other_pins);
  return UNITY_END();
}
