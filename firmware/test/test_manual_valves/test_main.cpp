#include <unity.h>
#include <cstring>
#include "Hardware.h"
#include "JsonRecipe.h"

using namespace basu;

void setUp() { fake::resetGpio(); fake::resetLedc(); Wire.reset(); }
void tearDown() {}

std::array<bool, kValveCount> sixOn() { return {{true, true, true, true, true, false, true}}; }

Controller valveCore() {
  SafetyConfig safety;
  safety.simulation = false;
  safety.valveControlReady = true;
  // All full pump/pressure/recipe approvals deliberately remain false/invalid.
  return Controller(safety);
}

uint16_t shiftedWord() {
  uint16_t word = 0;
  int data = 0;
  unsigned clocks = 0;
  for (const auto& event : fake::gpioEvents) {
    if (event.write && event.pin == 14) data = event.value;
    if (event.write && event.pin == 13 && event.value == HIGH) {
      word = static_cast<uint16_t>((word << 1) | data);
      ++clocks;
    }
  }
  TEST_ASSERT_EQUAL(16, clocks);
  return word;
}

BoardConfig fullFixture() {
  // Test fixture only, not a commissioned rig profile.
  BoardConfig config;
  config.verifiedBoardConfig = true; config.safeProfileVerified = true;
  config.pressureLimitPsi = 20; config.gp8403InterfaceVerified = true;
  config.pumpContactPin = 26;
  config.i2cSdaPin = 21; config.i2cSclPin = 22;
  config.shiftDataPin = 14; config.shiftClockPin = 13;
  config.shiftLatchPin = 12; config.shiftOePin = 5;
  config.valveBits = {{0, 1, 2, 3, 5, 4, 6}};  // Slot5 is unused V6; slot6 is V7.
  config.pressure.source = AnalogSource::NativeAdc1;
  config.pressure.pin = 34; config.pressure.calibrationVerified = true;
  return config;
}

void test_confirmed_profile_is_six_valves_and_invalid_profiles_cannot_initialize() {
  const auto confirmed = confirmedRigManualValves();
  TEST_ASSERT_EQUAL(6, kManualValveCount);
  TEST_ASSERT_EQUAL(7, kValveCount);  // Wire compatibility only.
  TEST_ASSERT_NULL(validateManualValveConfig(confirmed));
  const int expectedBits[] = {0, 1, 2, 3, 5, 6};
  const int expectedIds[] = {1, 2, 3, 4, 5, 7};
  const std::size_t expectedSlots[] = {0, 1, 2, 3, 4, 6};
  for (std::size_t index = 0; index < kManualValveCount; ++index) {
    TEST_ASSERT_EQUAL(expectedBits[index], confirmed.bits[index]);
    TEST_ASSERT_EQUAL(expectedIds[index], kManualValveIds[index]);
    TEST_ASSERT_EQUAL(expectedSlots[index], kManualValveSlots[index]);
  }
  Hardware hardware(BoardConfig{}, false);
  TEST_ASSERT_FALSE(hardware.beginManualValves(ManualValveConfig{}));
  auto duplicate = confirmed; duplicate.bits[5] = 0;
  TEST_ASSERT_FALSE(hardware.beginManualValves(duplicate));
  auto invalid = confirmed; invalid.bits[5] = 16;
  TEST_ASSERT_FALSE(hardware.beginManualValves(invalid));
  TEST_ASSERT_EQUAL(0, fake::gpioCalls);
  TEST_ASSERT_FALSE(hardware.valveControlReady());
}

void test_factory_manual_initialization_only_touches_four_relay_pins_and_holds_off() {
  Hardware hardware(BoardConfig{}, false);
  TEST_ASSERT_FALSE(hardware.begin());
  TEST_ASSERT_TRUE(hardware.beginManualValves(confirmedRigManualValves()));
  TEST_ASSERT_TRUE(hardware.valveControlReady());
  TEST_ASSERT_FALSE(hardware.ready());
  TEST_ASSERT_TRUE(fake::gpioEvents[0].write);
  TEST_ASSERT_EQUAL(5, fake::gpioEvents[0].pin);
  TEST_ASSERT_EQUAL(HIGH, fake::gpioEvents[0].value);
  for (const auto& event : fake::gpioEvents)
    TEST_ASSERT_TRUE(event.pin == 14 || event.pin == 13 || event.pin == 12 || event.pin == 5);
  TEST_ASSERT_EQUAL(LOW, fake::levels[5]);
  TEST_ASSERT_EQUAL(0, Wire.beginCount);
  TEST_ASSERT_EQUAL(0, Wire.transactionCount);
  TEST_ASSERT_EQUAL(0, fake::ledcCalls);
  hardware.sample(1000);
  TEST_ASSERT_FALSE(hardware.measurements().pressure.valid);
  TEST_ASSERT_EQUAL_STRING("not_configured", hardware.sensorStatus(1, 1000));
}

void test_all_six_outputs_use_confirmed_physical_labels_and_all_unused_bits_stay_off() {
  Hardware hardware(BoardConfig{}, false);
  TEST_ASSERT_TRUE(hardware.beginManualValves(confirmedRigManualValves()));
  for (std::size_t valve = 0; valve < kManualValveCount; ++valve) {
    fake::resetGpio();
    std::array<bool, kValveCount> states{}; states[kManualValveSlots[valve]] = true;
    TEST_ASSERT_TRUE(hardware.applyManualValves(states));
    const int expectedBits[] = {0, 1, 2, 3, 5, 6};
    TEST_ASSERT_EQUAL_HEX16(1U << expectedBits[valve], shiftedWord());
  }
  fake::resetGpio();
  TEST_ASSERT_TRUE(hardware.applyManualValves(sixOn()));
  TEST_ASSERT_EQUAL_HEX16(0x006f, shiftedWord());
  TEST_ASSERT_EQUAL(0, Wire.transactionCount);
  TEST_ASSERT_EQUAL(0, fake::ledcCalls);
}

void test_v5_and_v7_keep_physical_wire_slots_and_nonconsecutive_relay_bits() {
  Hardware hardware(BoardConfig{}, false);
  hardware.beginManualValves(confirmedRigManualValves());
  auto core = valveCore();
  std::array<bool, kValveCount> v5{}; v5[4] = true;
  TEST_ASSERT_NULL(core.manualValves(v5, 0));
  fake::resetGpio(); hardware.applyManualValves(core.outputs().valves);
  TEST_ASSERT_EQUAL_HEX16(0x0020, shiftedWord());  // V5 is bit5, NOT bit4.
  const char* frame = R"({"v":1,"id":1,"cmd":"manual_valves","valves":[false,false,false,false,false,false,true]})";
  JsonDocument document; TEST_ASSERT_NULL(decodeObject(frame, std::strlen(frame), document));
  Outputs v7; TEST_ASSERT_NULL(parseManualValves(document.as<JsonVariantConst>(), v7));
  TEST_ASSERT_TRUE(v7.valves[6]); TEST_ASSERT_FALSE(v7.valves[5]);
  TEST_ASSERT_NULL(core.manualValves(v7.valves, 1));
  fake::resetGpio(); hardware.applyManualValves(core.outputs().valves);
  TEST_ASSERT_EQUAL_HEX16(0x0040, shiftedWord());  // V7 is wire slot6 and register bit6.
}

void test_held_command_is_not_a_pulse_and_stop_is_all_off_and_idempotent() {
  Hardware hardware(BoardConfig{}, false);
  hardware.beginManualValves(confirmedRigManualValves());
  hardware.applyManualValves(sixOn());
  const unsigned calls = fake::gpioCalls;
  for (unsigned index = 0; index < 100; ++index)
    TEST_ASSERT_TRUE(hardware.applyManualValves(sixOn()));
  TEST_ASSERT_EQUAL(calls, fake::gpioCalls);
  fake::resetGpio();
  hardware.safeStop();
  TEST_ASSERT_EQUAL_HEX16(0, shiftedWord());
  TEST_ASSERT_EQUAL(LOW, fake::levels[5]);
  const unsigned stoppedCalls = fake::gpioCalls;
  hardware.safeStop();
  TEST_ASSERT_EQUAL(stoppedCalls, fake::gpioCalls);
}

void test_unused_v6_wire_slot_is_rejected_without_changing_outputs() {
  Hardware hardware(BoardConfig{}, false);
  hardware.beginManualValves(confirmedRigManualValves());
  hardware.applyManualValves(sixOn());
  const unsigned calls = fake::gpioCalls;
  auto invalid = sixOn(); invalid[5] = true;
  TEST_ASSERT_FALSE(hardware.applyManualValves(invalid));
  TEST_ASSERT_EQUAL(calls, fake::gpioCalls);
  auto core = valveCore();
  TEST_ASSERT_NOT_NULL(core.manualValves(invalid, 0));
  TEST_ASSERT_TRUE(core.state() == State::Idle);
}

void test_valve_core_needs_no_sensors_recipe_balance_or_pump_approval() {
  auto core = valveCore();
  TEST_ASSERT_NULL(core.manualValves(sixOn(), 100));
  TEST_ASSERT_TRUE(core.state() == State::ManualValves);
  TEST_ASSERT_EQUAL_STRING("manual_valves", stateName(core.state()));
  TEST_ASSERT_TRUE(core.active());
  TEST_ASSERT_FALSE(core.hardwareVerified());
  TEST_ASSERT_EQUAL_DOUBLE(0, core.outputs().pumpPercent);
  TEST_ASSERT_EQUAL(0, core.remainingSeconds(100));
  for (uint32_t now = 600; now < 20000; now += 500) {
    core.heartbeat(now); core.tick(now);
    TEST_ASSERT_TRUE(core.state() == State::ManualValves);
    TEST_ASSERT_TRUE(core.outputs().valves == sixOn());
  }
}

void test_watchdog_stops_held_valves_and_commands_do_not_extend_heartbeat() {
  auto core = valveCore();
  core.manualValves(sixOn(), 0);
  TEST_ASSERT_NULL(core.manualValves(sixOn(), 2500));
  core.tick(2999); TEST_ASSERT_TRUE(core.state() == State::ManualValves);
  core.tick(3000); TEST_ASSERT_TRUE(core.state() == State::Fault);
  TEST_ASSERT_EQUAL_STRING("heartbeat_timeout", core.fault().c_str());
  for (bool state : core.outputs().valves) TEST_ASSERT_FALSE(state);
  TEST_ASSERT_EQUAL_DOUBLE(0, core.outputs().pumpPercent);
  TEST_ASSERT_NOT_NULL(core.manualValves(sixOn(), 3001));
  core.heartbeat(3001);
  TEST_ASSERT_NOT_NULL(core.manualValves(sixOn(), 3001));  // Late HB cannot clear fault.
}

void test_late_heartbeat_or_repeated_valve_command_cannot_conceal_expiry() {
  auto heartbeat = valveCore(); heartbeat.manualValves(sixOn(), 0);
  heartbeat.heartbeat(3000);
  TEST_ASSERT_TRUE(heartbeat.state() == State::Fault);
  auto command = valveCore(); command.manualValves(sixOn(), 0);
  TEST_ASSERT_NOT_NULL(command.manualValves(sixOn(), 3000));
  TEST_ASSERT_TRUE(command.state() == State::Fault);
}

void test_stop_and_hello_clear_valve_session_and_new_instance_starts_idle() {
  for (bool hello : {false, true}) {
    auto core = valveCore(); core.manualValves(sixOn(), 0);
    if (hello) core.onHello(); else core.stop();
    TEST_ASSERT_TRUE(core.state() == State::Idle);
    for (bool state : core.outputs().valves) TEST_ASSERT_FALSE(state);
    TEST_ASSERT_EQUAL_DOUBLE(0, core.outputs().pumpPercent);
  }
  auto restarted = valveCore();
  TEST_ASSERT_FALSE(restarted.active());
  for (bool state : restarted.outputs().valves) TEST_ASSERT_FALSE(state);
}

void test_valve_only_stop_and_fault_do_not_use_unrelated_full_process_safe_states() {
  SafetyConfig safety; safety.simulation = false; safety.valveControlReady = true;
  safety.safeValves.fill(true);  // Unrelated full process profile, NOT the confirmed manual rest.
  for (bool timeout : {false, true}) {
    Controller core(safety); TEST_ASSERT_NULL(core.manualValves(sixOn(), 0));
    if (timeout) core.tick(3000); else core.stop();
    for (bool state : core.outputs().valves) TEST_ASSERT_FALSE(state);
    if (timeout) { core.clearFault(); for (bool state : core.outputs().valves) TEST_ASSERT_FALSE(state); }
  }
}

void test_capability_loss_faults_valves_but_pressure_is_not_a_valve_only_gate() {
  auto core = valveCore(); core.manualValves(sixOn(), 0);
  Measurements invalid; invalid.pressure = {1000, false, 0}; core.setMeasurements(invalid);
  core.tick(1); TEST_ASSERT_TRUE(core.state() == State::ManualValves);
  core.setValveControlReady(false); core.tick(2);
  TEST_ASSERT_TRUE(core.state() == State::Fault);
  TEST_ASSERT_EQUAL_STRING("valve_control_not_ready", core.fault().c_str());
  for (bool state : core.outputs().valves) TEST_ASSERT_FALSE(state);
}

void test_valve_capability_cannot_unlock_pump_or_recipe_or_silent_mode_switches() {
  auto core = valveCore();
  Outputs pumping; pumping.pumpPercent = 50;
  TEST_ASSERT_NOT_NULL(core.manual(pumping, 0));
  TEST_ASSERT_NULL(core.manualValves(sixOn(), 0));
  TEST_ASSERT_NOT_NULL(core.manual(pumping, 1));
  Recipe recipe; recipe.name = "Full"; recipe.stepCount = 1;
  recipe.steps[0].name = "Flow"; recipe.steps[0].durationSeconds = 10;
  recipe.hardwareApproved = true;
  TEST_ASSERT_NOT_NULL(core.load(recipe));
  TEST_ASSERT_NOT_NULL(core.start(1));
  core.stop(); TEST_ASSERT_NULL(core.load(recipe));
  TEST_ASSERT_NOT_NULL(core.start(2));  // Still no full hardware/pressure approval.
  SafetyConfig simulation; Controller fullManual(simulation);
  TEST_ASSERT_NULL(fullManual.manual(pumping, 0));
  TEST_ASSERT_NOT_NULL(fullManual.manualValves(sixOn(), 1));
}

void test_full_ready_driver_is_reused_without_extra_dac_or_pwm_actuation() {
  Hardware hardware(fullFixture(), false); TEST_ASSERT_TRUE(hardware.begin());
  TEST_ASSERT_TRUE(hardware.beginManualValves(confirmedRigManualValves()));
  const auto wireCalls = Wire.transactionCount;
  const auto ledcCalls = fake::ledcCalls;
  TEST_ASSERT_TRUE(hardware.applyManualValves(sixOn()));
  TEST_ASSERT_EQUAL(wireCalls, Wire.transactionCount);
  TEST_ASSERT_EQUAL(ledcCalls, fake::ledcCalls);
  TEST_ASSERT_EQUAL(LOW, fake::levels[26]);
  hardware.safeStop();
  TEST_ASSERT_EQUAL(LOW, fake::levels[26]);
}

void test_optional_full_sensor_acquisition_works_without_pump_health_probe_in_valve_mode() {
  auto config = fullFixture(); config.flow.source = AnalogSource::NativeAdc1;
  config.flow.pin = 35; config.flow.calibrationVerified = true;
  Hardware hardware(config, false); TEST_ASSERT_TRUE(hardware.begin());
  hardware.beginManualValves(confirmedRigManualValves());
  const auto transactions = Wire.transactionCount;
  Wire.failNext = true;  // Would fail a GP8403 health probe if one were attempted.
  hardware.sample(1000, true);
  TEST_ASSERT_EQUAL(transactions, Wire.transactionCount);
  TEST_ASSERT_TRUE(hardware.ready());
  TEST_ASSERT_TRUE(hardware.measurements().flow.valid);
  hardware.sample(2000, false);
  TEST_ASSERT_FALSE(hardware.ready());  // Ordinary full-mode health gate is retained.
}

void test_incompatible_full_driver_cannot_be_overwritten_by_second_relay_driver() {
  auto config = fullFixture(); config.shiftDataPin = 27;
  Hardware hardware(config, false); TEST_ASSERT_TRUE(hardware.begin());
  const auto calls = fake::gpioCalls;
  TEST_ASSERT_FALSE(hardware.beginManualValves(confirmedRigManualValves()));
  TEST_ASSERT_FALSE(hardware.valveControlReady());
  TEST_ASSERT_EQUAL(calls, fake::gpioCalls);
  TEST_ASSERT_TRUE(hardware.ready());
}

void test_old_sequential_full_mapping_cannot_claim_the_corrected_manual_capability() {
  auto config = fullFixture(); config.valveBits = {{0, 1, 2, 3, 4, 5, 6}};
  Hardware hardware(config, false); TEST_ASSERT_TRUE(hardware.begin());
  const auto calls = fake::gpioCalls;
  TEST_ASSERT_FALSE(hardware.beginManualValves(confirmedRigManualValves()));
  TEST_ASSERT_FALSE(hardware.valveControlReady());
  TEST_ASSERT_EQUAL(calls, fake::gpioCalls);
}

void test_watchdog_and_stop_restore_real_adapter_without_pump_or_adc_calls() {
  Hardware hardware(BoardConfig{}, false); hardware.beginManualValves(confirmedRigManualValves());
  auto core = valveCore(); core.manualValves(sixOn(), 0); hardware.applyManualValves(core.outputs().valves);
  fake::resetGpio();
  core.tick(3000); hardware.safeStop();
  TEST_ASSERT_EQUAL_HEX16(0, shiftedWord());
  TEST_ASSERT_EQUAL(0, Wire.transactionCount);
  TEST_ASSERT_EQUAL(0, fake::ledcCalls);
}

void test_json_manual_valves_is_strict_atomic_and_accepts_no_pump_field() {
  const char* invalid[] = {
    R"({"v":1,"id":1,"cmd":"manual_valves","valves":[true,false,false,false,false,false]})",
    R"({"v":1,"id":1,"cmd":"manual_valves","valves":[1,false,false,false,false,false,false]})",
    R"({"v":1,"id":1,"cmd":"manual_valves","valves":[false,false,false,false,false,true,false]})",
    R"({"v":1,"id":1,"cmd":"manual_valves","valves":[false,false,false,false,false,false,false],"pump_percent":0})"
  };
  for (const char* frame : invalid) {
    JsonDocument document; TEST_ASSERT_NULL(decodeObject(frame, std::strlen(frame), document));
    Outputs destination; destination.pumpPercent = 99;
    TEST_ASSERT_NOT_NULL(parseManualValves(document.as<JsonVariantConst>(), destination));
    TEST_ASSERT_EQUAL_DOUBLE(99, destination.pumpPercent);
  }
  const char* frame = R"({"v":1,"id":9,"cmd":"manual_valves","valves":[true,true,true,true,true,false,true]})";
  JsonDocument document; TEST_ASSERT_NULL(decodeObject(frame, std::strlen(frame), document));
  Outputs destination; destination.pumpPercent = 99;
  TEST_ASSERT_NULL(parseManualValves(document.as<JsonVariantConst>(), destination));
  TEST_ASSERT_TRUE(destination.valves == sixOn());
  TEST_ASSERT_EQUAL_DOUBLE(0, destination.pumpPercent);
}

void test_manual_watchdog_uses_unsigned_millis_rollover() {
  auto core = valveCore(); const uint32_t start = UINT32_MAX - 1000;
  core.manualValves(sixOn(), start);
  core.tick(start + 2999); TEST_ASSERT_TRUE(core.state() == State::ManualValves);
  core.tick(start + 3000); TEST_ASSERT_TRUE(core.state() == State::Fault);
}

void test_simulated_manual_valves_never_initialize_gpio() {
  Hardware hardware(BoardConfig{}, true); TEST_ASSERT_TRUE(hardware.begin());
  TEST_ASSERT_TRUE(hardware.beginManualValves(confirmedRigManualValves()));
  TEST_ASSERT_TRUE(hardware.applyManualValves(sixOn())); hardware.safeStop();
  TEST_ASSERT_EQUAL(0, fake::gpioCalls);
  TEST_ASSERT_EQUAL(0, fake::ledcCalls);
  TEST_ASSERT_EQUAL(0, Wire.beginCount);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_confirmed_profile_is_six_valves_and_invalid_profiles_cannot_initialize);
  RUN_TEST(test_factory_manual_initialization_only_touches_four_relay_pins_and_holds_off);
  RUN_TEST(test_all_six_outputs_use_confirmed_physical_labels_and_all_unused_bits_stay_off);
  RUN_TEST(test_v5_and_v7_keep_physical_wire_slots_and_nonconsecutive_relay_bits);
  RUN_TEST(test_held_command_is_not_a_pulse_and_stop_is_all_off_and_idempotent);
  RUN_TEST(test_unused_v6_wire_slot_is_rejected_without_changing_outputs);
  RUN_TEST(test_valve_core_needs_no_sensors_recipe_balance_or_pump_approval);
  RUN_TEST(test_watchdog_stops_held_valves_and_commands_do_not_extend_heartbeat);
  RUN_TEST(test_late_heartbeat_or_repeated_valve_command_cannot_conceal_expiry);
  RUN_TEST(test_stop_and_hello_clear_valve_session_and_new_instance_starts_idle);
  RUN_TEST(test_valve_only_stop_and_fault_do_not_use_unrelated_full_process_safe_states);
  RUN_TEST(test_capability_loss_faults_valves_but_pressure_is_not_a_valve_only_gate);
  RUN_TEST(test_valve_capability_cannot_unlock_pump_or_recipe_or_silent_mode_switches);
  RUN_TEST(test_full_ready_driver_is_reused_without_extra_dac_or_pwm_actuation);
  RUN_TEST(test_optional_full_sensor_acquisition_works_without_pump_health_probe_in_valve_mode);
  RUN_TEST(test_incompatible_full_driver_cannot_be_overwritten_by_second_relay_driver);
  RUN_TEST(test_old_sequential_full_mapping_cannot_claim_the_corrected_manual_capability);
  RUN_TEST(test_watchdog_and_stop_restore_real_adapter_without_pump_or_adc_calls);
  RUN_TEST(test_json_manual_valves_is_strict_atomic_and_accepts_no_pump_field);
  RUN_TEST(test_manual_watchdog_uses_unsigned_millis_rollover);
  RUN_TEST(test_simulated_manual_valves_never_initialize_gpio);
  return UNITY_END();
}
