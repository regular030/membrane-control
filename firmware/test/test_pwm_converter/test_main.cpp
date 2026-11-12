#include <unity.h>
#include <cmath>
#include <cstring>
#include <limits>
#include "Hardware.h"

using namespace basu;

void setUp() { fake::resetGpio(); fake::resetLedc(); fake::resetPcnt(); Wire.reset(); }
void tearDown() {}

BoardConfig pwmFixture() {
  // TEST ONLY: these values do not commission the real rig.
  BoardConfig config;
  config.verifiedBoardConfig = true;
  config.safeProfileVerified = true;
  config.pressureLimitPsi = 20;
  config.pumpCommandSource = PumpCommandSource::PwmConverter;
  config.pwmConverterInterfaceVerified = true;
  config.pumpPwmPin = 25;
  config.pumpContactPin = 26;
  config.pwmSettleMs = 100;
  config.shiftDataPin = 14; config.shiftClockPin = 13;
  config.shiftLatchPin = 12; config.shiftOePin = 5;
  config.valveBits = {{0, 1, 2, 3, 4, 5, 6}};
  config.pressure.source = AnalogSource::NativeAdc1;
  config.pressure.pin = 34;
  config.pressure.calibrationVerified = true;
  config.pressure.unitsPerVolt = 10;
  return config;
}

Outputs pump(double percent) { Outputs out; out.pumpPercent = percent; return out; }

void assertStopped(const BoardConfig& config) {
  TEST_ASSERT_EQUAL(LOW, fake::levels[config.pumpContactPin]);
  TEST_ASSERT_EQUAL(0, fake::ledcDuties[config.pumpPwmChannel]);
}

void test_default_and_unreviewed_pwm_never_touch_any_gpio_i2c_or_ledc() {
  TEST_ASSERT_TRUE(BoardConfig{}.pumpCommandSource == PumpCommandSource::Gp8403);
  for (bool simulation : {false, true}) {
    auto config = pwmFixture(); config.pwmConverterInterfaceVerified = false;
    Hardware hardware(config, simulation);
    TEST_ASSERT_EQUAL(simulation, hardware.begin());
    hardware.apply(pump(50), 0, true);
    hardware.sample(1000); hardware.safeStop();
    TEST_ASSERT_EQUAL(0, fake::gpioCalls);
    TEST_ASSERT_EQUAL(0, fake::ledcCalls);
    TEST_ASSERT_EQUAL(0, Wire.beginCount);
  }
}

void test_duty_encoding_zero_half_full_and_register_bounds() {
  uint32_t duty = 123;
  TEST_ASSERT_TRUE(encodePumpPwmDuty(0, 12, duty)); TEST_ASSERT_EQUAL(0, duty);
  TEST_ASSERT_TRUE(encodePumpPwmDuty(50, 12, duty)); TEST_ASSERT_EQUAL(2048, duty);
  TEST_ASSERT_TRUE(encodePumpPwmDuty(100, 12, duty)); TEST_ASSERT_EQUAL(4096, duty);
  for (int bits : {8, 12, 16}) {
    for (double percent : {0.000001, 1.0, 33.333, 99.999999, 100.0}) {
      TEST_ASSERT_TRUE(encodePumpPwmDuty(percent, bits, duty));
      TEST_ASSERT_TRUE(duty <= (1U << bits));
    }
  }
  for (double percent : {-0.1, 100.1, std::numeric_limits<double>::quiet_NaN(), std::numeric_limits<double>::infinity()})
    TEST_ASSERT_FALSE(encodePumpPwmDuty(percent, 12, duty));
  TEST_ASSERT_FALSE(encodePumpPwmDuty(50, 7, duty));
  TEST_ASSERT_FALSE(encodePumpPwmDuty(50, 17, duty));
}

void test_profile_rejects_reserved_and_overlapping_pwm_pins() {
  for (int pin : {-1, 1, 3, 4, 5, 6, 12, 13, 14, 26, 34, 40}) {
    auto config = pwmFixture(); config.pumpPwmPin = pin;
    TEST_ASSERT_NOT_NULL(validateBoardConfig(config));
  }
  auto config = pwmFixture(); config.pumpPwmPin = 32; config.pressure.pin = 32;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(config));
  config = pwmFixture(); config.i2cSdaPin = 25; config.i2cSclPin = 22;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(config));
  config = pwmFixture(); config.pumpContactPin = 4;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(config));
  config = pwmFixture(); config.pressure.source = AnalogSource::Disabled;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(config));
}

void test_profile_requires_reviewed_bounded_timer_and_measured_settling() {
  auto valid = pwmFixture();
  TEST_ASSERT_NULL(validateBoardConfig(valid));
  for (int channel : {-1, 16}) { auto c = valid; c.pumpPwmChannel = channel; TEST_ASSERT_NOT_NULL(validateBoardConfig(c)); }
  for (uint32_t freq : {0U, 21U, 20001U}) { auto c = valid; c.pumpPwmFrequencyHz = freq; TEST_ASSERT_NOT_NULL(validateBoardConfig(c)); }
  for (int bits : {7, 17}) { auto c = valid; c.pumpPwmResolutionBits = bits; TEST_ASSERT_NOT_NULL(validateBoardConfig(c)); }
  for (uint32_t delay : {0U, 9U, 5001U}) { auto c = valid; c.pwmSettleMs = delay; TEST_ASSERT_NOT_NULL(validateBoardConfig(c)); }
  for (uint32_t delay : {10U, 5000U}) { auto c = valid; c.pwmSettleMs = delay; TEST_ASSERT_NULL(validateBoardConfig(c)); }
  auto c = valid; c.pumpCommandSource = static_cast<PumpCommandSource>(99);
  TEST_ASSERT_NOT_NULL(validateBoardConfig(c));
}

void test_startup_zeros_stale_channel_before_run_and_native_adc_needs_no_i2c() {
  const auto config = pwmFixture();
  fake::ledcDuties[0] = 4096;  // Simulate retained global peripheral duty.
  Hardware hardware(config, false);
  TEST_ASSERT_TRUE(hardware.begin());
  TEST_ASSERT_EQUAL(26, fake::gpioEvents[0].pin);
  TEST_ASSERT_EQUAL(LOW, fake::gpioEvents[0].value);
  TEST_ASSERT_EQUAL(0, fake::ledcDuties[0]);
  TEST_ASSERT_EQUAL(25, fake::ledcPins[0]);
  bool attached = false;
  for (const auto& event : fake::ledcEvents) {
    TEST_ASSERT_TRUE(event.sequence > fake::gpioEvents[0].sequence);
    if (!std::strcmp(event.operation, "attach")) { TEST_ASSERT_EQUAL(0, event.value); attached = true; }
  }
  TEST_ASSERT_TRUE(attached);
  TEST_ASSERT_EQUAL(0, Wire.beginCount);
  hardware.sample(1000);
  TEST_ASSERT_EQUAL(0, Wire.transactionCount);
  TEST_ASSERT_TRUE(hardware.measurements().pressure.valid);
  TEST_ASSERT_TRUE(hardware.ready());
  assertStopped(config);
}

void test_nominal_pwm_and_settling_hold_stop_until_safety_checked_apply() {
  const auto config = pwmFixture(); Hardware hardware(config, false);
  TEST_ASSERT_TRUE(hardware.begin());
  TEST_ASSERT_TRUE(hardware.apply(pump(50), 1000, false));
  TEST_ASSERT_EQUAL(2048, fake::ledcDuties[0]);
  TEST_ASSERT_EQUAL(LOW, fake::levels[26]);
  hardware.sample(2000);  // Acquisition cannot start the pump.
  TEST_ASSERT_EQUAL(LOW, fake::levels[26]);
  TEST_ASSERT_TRUE(hardware.apply(pump(50), 2000, false));  // ACK path cannot start it.
  TEST_ASSERT_EQUAL(LOW, fake::levels[26]);
  TEST_ASSERT_TRUE(hardware.apply(pump(50), 2000, true));
  TEST_ASSERT_EQUAL(HIGH, fake::levels[26]);
  TEST_ASSERT_TRUE(hardware.apply(pump(100), 2001, true));
  TEST_ASSERT_EQUAL(4096, fake::ledcDuties[0]);
  TEST_ASSERT_EQUAL(LOW, fake::levels[26]);
  TEST_ASSERT_TRUE(hardware.apply(pump(100), 2100, true));
  TEST_ASSERT_EQUAL(LOW, fake::levels[26]);
  TEST_ASSERT_TRUE(hardware.apply(pump(100), 2101, true));
  TEST_ASSERT_EQUAL(HIGH, fake::levels[26]);
  TEST_ASSERT_TRUE(hardware.apply(pump(0), 2200, true));
  assertStopped(config);
}

void test_high_to_lower_command_waits_and_distinct_new_command_restarts_delay() {
  const auto config = pwmFixture(); Hardware hardware(config, false);
  TEST_ASSERT_TRUE(hardware.begin());
  hardware.apply(pump(100), 0, false); hardware.apply(pump(100), 100, true);
  TEST_ASSERT_EQUAL(HIGH, fake::levels[26]);
  hardware.apply(pump(25), 200, true);
  TEST_ASSERT_EQUAL(1024, fake::ledcDuties[0]);
  TEST_ASSERT_EQUAL(LOW, fake::levels[26]);
  hardware.apply(pump(25), 299, true); TEST_ASSERT_EQUAL(LOW, fake::levels[26]);
  hardware.apply(pump(50), 299, true);  // New voltage, new measured-settling window.
  hardware.apply(pump(50), 300, true); TEST_ASSERT_EQUAL(LOW, fake::levels[26]);
  hardware.apply(pump(50), 399, true); TEST_ASSERT_EQUAL(HIGH, fake::levels[26]);
}

void test_stop_cancels_pending_start_and_no_late_run_occurs() {
  const auto config = pwmFixture(); Hardware hardware(config, false);
  TEST_ASSERT_TRUE(hardware.begin());
  hardware.apply(pump(50), 0, false);
  hardware.safeStop();
  assertStopped(config);
  hardware.apply(Outputs{}, 10000, true);
  assertStopped(config);
  for (const auto& event : fake::gpioEvents)
    if (event.write && event.pin == 26) TEST_ASSERT_EQUAL(LOW, event.value);
}

void test_contact_stop_precedes_pwm_zero_and_pwm_command_precedes_run() {
  const auto config = pwmFixture(); Hardware hardware(config, false);
  TEST_ASSERT_TRUE(hardware.begin());
  hardware.apply(pump(50), 0, false); hardware.apply(pump(50), 100, true);
  unsigned commandAt = 0, runAt = 0;
  for (const auto& event : fake::ledcEvents)
    if (!std::strcmp(event.operation, "set") && event.value == 2048) commandAt = event.sequence;
  for (const auto& event : fake::gpioEvents)
    if (event.write && event.pin == 26 && event.value == HIGH) runAt = event.sequence;
  TEST_ASSERT_TRUE(commandAt > 0 && runAt > commandAt);
  fake::gpioEvents.clear(); fake::ledcEvents.clear();
  hardware.safeStop();
  TEST_ASSERT_EQUAL(26, fake::gpioEvents[0].pin);
  TEST_ASSERT_EQUAL(LOW, fake::gpioEvents[0].value);
  TEST_ASSERT_TRUE(fake::ledcEvents[0].sequence > fake::gpioEvents[0].sequence);
  TEST_ASSERT_EQUAL(0, fake::ledcEvents[0].value);
  assertStopped(config);
}

void test_pwm_with_ads_uses_only_ads_address_and_handles_i2c_initialization_failure() {
  auto config = pwmFixture();
  config.pressure.source = AnalogSource::Ads1115;
  config.pressure.adsChannel = 0;
  config.i2cSdaPin = 21; config.i2cSclPin = 22;
  config.gp8403Address = 0;  // Irrelevant in this source mode.
  Hardware hardware(config, false);
  TEST_ASSERT_TRUE(hardware.begin());
  TEST_ASSERT_EQUAL(1, Wire.beginCount);
  hardware.sample(1000);
  TEST_ASSERT_TRUE(Wire.transactionCount > 0);
  for (uint8_t address : Wire.addresses) TEST_ASSERT_EQUAL(0x48, address);
  Wire.reset(); Wire.beginSucceeds = false;
  Hardware failed(config, false);
  TEST_ASSERT_FALSE(failed.begin()); assertStopped(config);
}

void test_pwm_ads_probe_failure_zeroes_output_and_keeps_contact_stopped() {
  auto config = pwmFixture(); config.pressure.source = AnalogSource::Ads1115;
  config.pressure.adsChannel = 0; config.i2cSdaPin = 21; config.i2cSclPin = 22;
  Wire.failingAddress = 0x48;
  Hardware hardware(config, false);
  TEST_ASSERT_FALSE(hardware.begin());
  TEST_ASSERT_EQUAL_STRING("ads1115_not_responding", hardware.error());
  assertStopped(config);
}

void test_ledc_setup_frequency_and_attach_errors_cannot_run_pump() {
  for (int failure = 0; failure < 3; ++failure) {
    fake::resetGpio(); fake::resetLedc();
    if (failure == 0) fake::ledcSetupSucceeds = false;
    if (failure == 1) fake::ledcActualFrequency = 21000;
    if (failure == 2) fake::ledcAttachFails = true;
    const auto config = pwmFixture(); Hardware hardware(config, false);
    TEST_ASSERT_FALSE(hardware.begin());
    TEST_ASSERT_EQUAL_STRING("pwm_initialization_failed", hardware.error());
    TEST_ASSERT_FALSE(hardware.apply(pump(100), 10000, true));
    TEST_ASSERT_EQUAL(LOW, fake::levels[26]);
    TEST_ASSERT_EQUAL(LOW, fake::levels[25]);
  }
}

void test_checked_write_errors_latch_hardware_failure_with_independent_contact_stop() {
  for (bool updateFailure : {false, true}) {
    fake::resetGpio(); fake::resetLedc(); Wire.reset();
    const auto config = pwmFixture(); Hardware hardware(config, false);
    TEST_ASSERT_TRUE(hardware.begin());
    hardware.apply(pump(50), 0, false); hardware.apply(pump(50), 100, true);
    if (updateFailure) fake::ledcUpdateFails = true; else fake::ledcSetFails = true;
    TEST_ASSERT_FALSE(hardware.apply(pump(25), 200, false));
    TEST_ASSERT_FALSE(hardware.ready());
    TEST_ASSERT_EQUAL_STRING("pwm_write_failed", hardware.error());
    assertStopped(config);  // IDF stop fallback still works in these fixtures.
    TEST_ASSERT_FALSE(hardware.apply(pump(25), 10000, true));
  }
}

void test_even_failed_pwm_zero_cannot_prevent_independent_stop_contact() {
  const auto config = pwmFixture(); Hardware hardware(config, false);
  TEST_ASSERT_TRUE(hardware.begin());
  hardware.apply(pump(50), 0, false); hardware.apply(pump(50), 100, true);
  fake::ledcSetFails = fake::ledcStopFails = true;
  hardware.safeStop();
  TEST_ASSERT_EQUAL(LOW, fake::levels[26]);
  TEST_ASSERT_FALSE(hardware.ready());
  TEST_ASSERT_EQUAL_STRING("pwm_stop_failed", hardware.error());
  TEST_ASSERT_FALSE(hardware.apply(pump(50), 10000, true));
}

void test_invalid_pump_commands_reject_nonfinite_and_out_of_range_and_stop() {
  for (double percent : {-1.0, 100.01, std::numeric_limits<double>::quiet_NaN(), std::numeric_limits<double>::infinity()}) {
    fake::resetGpio(); fake::resetLedc(); Wire.reset();
    const auto config = pwmFixture(); Hardware hardware(config, false);
    TEST_ASSERT_TRUE(hardware.begin());
    hardware.apply(pump(50), 0, false); hardware.apply(pump(50), 100, true);
    TEST_ASSERT_FALSE(hardware.apply(pump(percent), 101, false));
    TEST_ASSERT_FALSE(hardware.ready()); assertStopped(config);
  }
}

void test_settling_timer_is_correct_across_millis_rollover() {
  const auto config = pwmFixture(); Hardware hardware(config, false);
  TEST_ASSERT_TRUE(hardware.begin());
  const uint32_t start = UINT32_MAX - 50;
  hardware.apply(pump(50), start, false);
  hardware.apply(pump(50), start + 99, true); TEST_ASSERT_EQUAL(LOW, fake::levels[26]);
  hardware.apply(pump(50), start + 100, true); TEST_ASSERT_EQUAL(HIGH, fake::levels[26]);
}

void test_pending_activation_cannot_beat_watchdog_or_pressure_fault() {
  for (bool pressureFault : {false, true}) {
    fake::resetGpio(); fake::resetLedc(); Wire.reset();
    auto config = pwmFixture(); config.pwmSettleMs = 5000;
    Hardware hardware(config, false); TEST_ASSERT_TRUE(hardware.begin());
    SafetyConfig safety;
    safety.simulation = false; safety.hardwareReady = true; safety.safeProfileVerified = true;
    safety.pressureLimitPsi = 20; safety.sensorMaxAgeMs = 3000;
    Controller core(safety);
    Recipe recipe; recipe.name = "Pending pump safety"; recipe.hardwareApproved = true; recipe.stepCount = 1;
    recipe.steps[0].name = "Observe";
    recipe.steps[0].durationSeconds = 30; recipe.steps[0].outputs.pumpPercent = 100;
    TEST_ASSERT_NULL(core.load(recipe));
    Measurements readings; readings.pressure = {5, true, 0}; core.setMeasurements(readings);
    TEST_ASSERT_NULL(core.start(0));
    TEST_ASSERT_TRUE(hardware.apply(core.outputs(), 0, false));
    const uint32_t faultAt = pressureFault ? 100 : 3000;
    readings.pressure = {pressureFault ? 30.0 : 5.0, true, faultAt}; core.setMeasurements(readings);
    core.tick(faultAt);
    TEST_ASSERT_TRUE(core.state() == State::Fault);
    hardware.safeStop();  // Same ordering as the actual main loop.
    hardware.apply(core.outputs(), faultAt, true);
    hardware.apply(core.outputs(), 10000, true);
    assertStopped(config);
    for (const auto& event : fake::gpioEvents)
      if (event.write && event.pin == 26) TEST_ASSERT_EQUAL(LOW, event.value);
  }
}

void test_low_pressure_start_requires_a_fresh_low_adc_sample_and_expires() {
  auto config = pwmFixture();
  config.pressureLimitPsi = 80;
  config.pressure.nativeAdcAttenuation = NativeAdcAttenuation::Db2_5;
  config.pressure.minPinVolts = 0.100;
  config.pressure.maxPinVolts = 1;
  config.pressure.unitsPerVolt = 100;
  config.pwmSettleMs = 1500;
  config.pressureStartupMs = 10000;
  config.pumpLimits.requiredValves = std::array<bool, kValveCount>{{true, false, true, false, false, false, false}};
  Hardware hardware(config, false);
  TEST_ASSERT_TRUE(hardware.begin());

  SafetyConfig safety;
  safety.simulation = false;
  safety.hardwareReady = true;
  safety.safeProfileVerified = true;
  safety.pressureLimitPsi = config.pressureLimitPsi;
  safety.pumpLimits = config.pumpLimits;
  safety.pressureStartupMs = config.pressureStartupMs;
  Controller core(safety);
  const Outputs pumping{*config.pumpLimits.requiredValves, 40};
  auto sample = [&](uint32_t now, uint32_t millivolts) {
    fake::adcMillivolts[config.pressure.pin] = millivolts;
    hardware.sample(now);
    core.setMeasurements(hardware.measurements());
    core.tick(now);
  };
  auto apply = [&](uint32_t now) {
    TEST_ASSERT_TRUE(hardware.apply(core.outputs(), now, true));
    if (hardware.pumpRunContactCommanded()) core.notePumpRunCommanded(now);
  };

  TEST_ASSERT_EQUAL_STRING("pressure_invalid_or_stale", core.manual(pumping, 0, true));
  sample(100, 0);
  TEST_ASSERT_NULL(core.manualPressureStartupStatus(100));
  sample(200, 1100);
  TEST_ASSERT_NULL(core.manualPressureStartupStatus(200));
  sample(300, 74);
  TEST_ASSERT_EQUAL_UINT32(74, hardware.pressureAdcMillivolts(300).value());
  TEST_ASSERT_FALSE(hardware.pressureAdcMillivolts(501).has_value());
  TEST_ASSERT_EQUAL_STRING("available", core.manualPressureStartupStatus(300));
  TEST_ASSERT_EQUAL_STRING("pressure_invalid_or_stale", core.manual(pumping, 501, true));
  sample(600, 74);
  TEST_ASSERT_EQUAL_STRING("pressure_invalid_or_stale", core.manual(pumping, 600));
  TEST_ASSERT_NULL(core.manual(pumping, 600, true));
  TEST_ASSERT_EQUAL_STRING("active", core.manualPressureStartupStatus(600));
  // Stage later than the command's timestamp, as can happen while processing serial input.
  TEST_ASSERT_TRUE(hardware.apply(core.outputs(), 700, false));
  sample(2199, 74);
  apply(2199);
  TEST_ASSERT_FALSE(hardware.pumpRunContactCommanded());
  apply(2200);
  TEST_ASSERT_TRUE(hardware.pumpRunContactCommanded());
  TEST_ASSERT_EQUAL_STRING("pressure_startup_in_progress", core.manual(pumping, 2200, true));
  for (uint32_t now = 2300; now <= 12100; now += 100) {
    core.heartbeat(now);
    sample(now, 74);
    apply(now);
    TEST_ASSERT_TRUE(hardware.pumpRunContactCommanded());
  }
  core.tick(12199);
  apply(12199);
  TEST_ASSERT_TRUE(hardware.pumpRunContactCommanded());
  core.tick(12200);
  apply(12200);
  TEST_ASSERT_EQUAL_STRING("pressure_startup_timeout", core.fault().c_str());
  TEST_ASSERT_FALSE(hardware.pumpRunContactCommanded());
  TEST_ASSERT_EQUAL(0, fake::ledcDuties[config.pumpPwmChannel]);
}

void test_gp8403_range_zero_and_health_probe_are_preserved_without_ledc_calls() {
  auto config = pwmFixture(); config.pumpCommandSource = PumpCommandSource::Gp8403;
  config.gp8403InterfaceVerified = true; config.i2cSdaPin = 21; config.i2cSclPin = 22;
  Hardware hardware(config, false); TEST_ASSERT_TRUE(hardware.begin());
  TEST_ASSERT_EQUAL(0, fake::ledcCalls);
  TEST_ASSERT_EQUAL(5, Wire.writes[0].size());
  TEST_ASSERT_EQUAL(0x02, Wire.writes[0][0]);
  for (std::size_t i = 1; i < Wire.writes[0].size(); ++i) TEST_ASSERT_EQUAL(0, Wire.writes[0][i]);
  TEST_ASSERT_EQUAL(0x01, Wire.writes[1][0]); TEST_ASSERT_EQUAL(0x11, Wire.writes[1][1]);
  TEST_ASSERT_TRUE(hardware.apply(pump(50)));
  TEST_ASSERT_EQUAL(HIGH, fake::levels[26]);
  Wire.failingAddress = config.gp8403Address;
  hardware.sample(1000);
  TEST_ASSERT_FALSE(hardware.ready());
  TEST_ASSERT_EQUAL_STRING("gp8403_disconnected", hardware.error());
  TEST_ASSERT_EQUAL(LOW, fake::levels[26]);
  TEST_ASSERT_EQUAL(0, fake::ledcCalls);
}

BoardConfig onboardContactFixture() {
  auto config = pwmFixture();
  config.pumpContactPin = -1;
  config.pumpContactBit = 15;  // Arbitrary test bit, never a factory assignment.
  config.valveBits = {{0, 1, 2, 3, 5, 4, 6}};
  return config;
}

struct LatchedWord { uint16_t word; unsigned sequence; };

std::vector<LatchedWord> latchedWords() {
  std::vector<LatchedWord> words;
  int data = 0;
  uint16_t word = 0;
  unsigned clocks = 0;
  for (const auto& event : fake::gpioEvents) {
    if (!event.write) continue;
    if (event.pin == 14) data = event.value;
    if (event.pin == 13 && event.value == HIGH) {
      word = static_cast<uint16_t>((word << 1) | data);
      ++clocks;
    }
    if (event.pin == 12 && event.value == HIGH) {
      TEST_ASSERT_EQUAL(16, clocks);
      words.push_back({word, event.sequence});
      word = 0;
      clocks = 0;
    }
  }
  return words;
}

void test_onboard_contact_must_be_spare_in_range_low_at_rest_and_exclusive() {
  TEST_ASSERT_EQUAL(-1, BoardConfig{}.pumpContactBit);
  TEST_ASSERT_NULL(validateBoardConfig(onboardContactFixture()));
  for (int bit : {-2, 0, 4, 6, 16}) {
    auto config = onboardContactFixture();
    config.pumpContactBit = bit;
    TEST_ASSERT_NOT_NULL(validateBoardConfig(config));
  }
  auto config = onboardContactFixture();
  config.shiftBitCount = 8;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(config));
  config = onboardContactFixture();
  config.pumpContactPin = 26;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(config));
  config = onboardContactFixture();
  config.shiftUnusedLevels = 0x8000;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(config));
  config = onboardContactFixture();
  config.pumpContactActiveHigh = false;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(config));
  config = onboardContactFixture();
  config.relayKind = RelayKind::DirectGpio;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(config));
}

void test_onboard_startup_latches_stopped_before_enabling_outputs() {
  Hardware hardware(onboardContactFixture(), false);
  TEST_ASSERT_TRUE(hardware.begin());
  TEST_ASSERT_EQUAL(5, fake::gpioEvents.front().pin);
  TEST_ASSERT_EQUAL(HIGH, fake::gpioEvents.front().value);
  const auto words = latchedWords();
  TEST_ASSERT_EQUAL(1, words.size());
  TEST_ASSERT_EQUAL_HEX16(0, words[0].word);
  TEST_ASSERT_TRUE(words[0].sequence < fake::ledcEvents.front().sequence);
  for (const auto& event : fake::gpioEvents) {
    TEST_ASSERT_NOT_EQUAL(26, event.pin);
    if (event.write && event.pin == 5 && event.value == LOW)
      TEST_ASSERT_TRUE(event.sequence > words[0].sequence);
  }
  TEST_ASSERT_EQUAL(LOW, fake::levels[5]);
}

void test_onboard_contact_opens_before_valve_and_pwm_changes_and_waits_to_run() {
  Hardware hardware(onboardContactFixture(), false);
  TEST_ASSERT_TRUE(hardware.begin());
  TEST_ASSERT_TRUE(hardware.pumpContactCommandAvailable());
  TEST_ASSERT_FALSE(hardware.pumpRunContactCommanded());
  fake::gpioEvents.clear();
  Outputs first = pump(50);
  first.valves[0] = true;
  TEST_ASSERT_TRUE(hardware.apply(first, 1000));
  TEST_ASSERT_TRUE(hardware.apply(first, 1099, true));
  TEST_ASSERT_TRUE(hardware.apply(first, 1100, false));
  TEST_ASSERT_FALSE(hardware.pumpRunContactCommanded());
  TEST_ASSERT_EQUAL(1, latchedWords().size());
  TEST_ASSERT_EQUAL_HEX16(0x0001, latchedWords()[0].word);
  TEST_ASSERT_TRUE(hardware.apply(first, 1100, true));
  TEST_ASSERT_TRUE(hardware.pumpRunContactCommanded());
  TEST_ASSERT_EQUAL(2, latchedWords().size());
  TEST_ASSERT_EQUAL_HEX16(0x8001, latchedWords()[1].word);

  fake::gpioEvents.clear();
  fake::ledcEvents.clear();
  Outputs next = pump(25);
  next.valves[1] = true;
  TEST_ASSERT_TRUE(hardware.apply(next, 1101, true));
  TEST_ASSERT_FALSE(hardware.pumpRunContactCommanded());
  const auto change = latchedWords();
  TEST_ASSERT_EQUAL(2, change.size());
  TEST_ASSERT_EQUAL_HEX16(0x0001, change[0].word);  // STOP preserves existing valves.
  TEST_ASSERT_EQUAL_HEX16(0x0002, change[1].word);
  TEST_ASSERT_TRUE(change[0].sequence < change[1].sequence);
  TEST_ASSERT_TRUE(change[1].sequence < fake::ledcEvents.front().sequence);
  TEST_ASSERT_TRUE(hardware.apply(next, 1201, true));
  TEST_ASSERT_TRUE(hardware.pumpRunContactCommanded());
  TEST_ASSERT_EQUAL_HEX16(0x8002, latchedWords().back().word);

  fake::gpioEvents.clear();
  fake::ledcEvents.clear();
  hardware.safeStop();
  TEST_ASSERT_FALSE(hardware.pumpRunContactCommanded());
  const auto stop = latchedWords();
  TEST_ASSERT_EQUAL(2, stop.size());
  TEST_ASSERT_EQUAL_HEX16(0x0002, stop[0].word);
  TEST_ASSERT_EQUAL_HEX16(0, stop[1].word);
  TEST_ASSERT_EQUAL(0, fake::ledcEvents.front().value);
  TEST_ASSERT_TRUE(stop[0].sequence < fake::ledcEvents.front().sequence);
  TEST_ASSERT_TRUE(fake::ledcEvents.front().sequence < stop[1].sequence);
}

void test_onboard_contact_opens_even_if_pwm_cannot_be_zeroed() {
  Hardware hardware(onboardContactFixture(), false);
  TEST_ASSERT_TRUE(hardware.begin());
  TEST_ASSERT_TRUE(hardware.apply(pump(50), 1000));
  TEST_ASSERT_TRUE(hardware.apply(pump(50), 1100, true));
  TEST_ASSERT_EQUAL_HEX16(0x8000, latchedWords().back().word);
  fake::gpioEvents.clear();
  fake::ledcEvents.clear();
  fake::ledcSetFails = fake::ledcStopFails = true;
  hardware.safeStop();
  const auto stop = latchedWords();
  TEST_ASSERT_FALSE(hardware.ready());
  TEST_ASSERT_EQUAL(2048, fake::ledcDuties[0]);
  TEST_ASSERT_EQUAL_HEX16(0, stop.front().word);
  TEST_ASSERT_TRUE(stop.front().sequence < fake::ledcEvents.front().sequence);
  TEST_ASSERT_FALSE(hardware.apply(pump(50), 2000, true));
  TEST_ASSERT_EQUAL_HEX16(0, latchedWords().back().word);
}

void test_hardware_profile_limits_cannot_be_bypassed() {
  auto config = onboardContactFixture();
  config.valveBits[kValve6Slot] = -1;
  config.pumpLimits.maxPercent = 50;
  const std::array<bool, kValveCount> requiredValves{{true, false, true, false, false, false, false}};
  config.pumpLimits.requiredValves = requiredValves;
  auto invalid = config;
  invalid.pumpLimits.maxPercent = NAN;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(invalid));
  invalid.pumpLimits.maxPercent = 100.01;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(invalid));
  invalid = config;
  (*invalid.pumpLimits.requiredValves)[kValve6Slot] = true;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(invalid));

  for (const bool wrongPath : {false, true}) {
    fake::resetGpio();
    fake::resetLedc();
    Hardware hardware(config, false);
    TEST_ASSERT_TRUE(hardware.begin());
    const Outputs allowed{requiredValves, 50};
    TEST_ASSERT_TRUE(hardware.apply(allowed, 1000));
    TEST_ASSERT_EQUAL_HEX16(0x0005, latchedWords().back().word);
    TEST_ASSERT_TRUE(hardware.apply(allowed, 1100, true));
    TEST_ASSERT_EQUAL_HEX16(0x8005, latchedWords().back().word);
    Outputs disallowed = allowed;
    if (wrongPath) disallowed.valves[1] = true;
    else disallowed.pumpPercent = 50.01;
    TEST_ASSERT_FALSE(hardware.apply(disallowed, 1101, true));
    TEST_ASSERT_EQUAL_STRING(wrongPath ? "pump_valve_path_mismatch" : "pump_percent_exceeds_profile_limit", hardware.error());
    TEST_ASSERT_EQUAL_HEX16(0, latchedWords().back().word);
    TEST_ASSERT_EQUAL(0, fake::ledcDuties[0]);
    TEST_ASSERT_FALSE(hardware.pumpRunContactCommanded());
    TEST_ASSERT_FALSE(hardware.apply(allowed, 5000, true));
  }
}

void test_manual_pump_handoff_holds_the_existing_valves_until_run() {
  auto config = onboardContactFixture();
  config.valveBits[kValve6Slot] = -1;
  config.pumpLimits.maxPercent = 50;
  config.pumpLimits.requiredValves = std::array<bool, kValveCount>{{true, false, true, false, false, false, false}};
  Hardware hardware(config, false);
  TEST_ASSERT_TRUE(hardware.begin());
  TEST_ASSERT_TRUE(hardware.beginManualValves(confirmedRigManualValves()));
  const Outputs pumping{*config.pumpLimits.requiredValves, 50};
  TEST_ASSERT_TRUE(hardware.applyManualValves(pumping.valves));
  TEST_ASSERT_EQUAL_HEX16(0x0005, latchedWords().back().word);
  fake::gpioEvents.clear();

  TEST_ASSERT_TRUE(hardware.apply(pumping, 1000, false));
  TEST_ASSERT_TRUE(hardware.apply(pumping, 1099, true));
  TEST_ASSERT_EQUAL_HEX16(0x0005, latchedWords().back().word);
  TEST_ASSERT_FALSE(hardware.pumpRunContactCommanded());
  TEST_ASSERT_EQUAL(2048, fake::ledcDuties[0]);
  TEST_ASSERT_TRUE(hardware.apply(pumping, 1100, true));
  TEST_ASSERT_TRUE(hardware.pumpRunContactCommanded());
  const auto words = latchedWords();
  TEST_ASSERT_EQUAL(2, words.size());
  TEST_ASSERT_EQUAL_HEX16(0x0005, words[0].word);
  TEST_ASSERT_EQUAL_HEX16(0x8005, words[1].word);
  for (const auto& event : fake::gpioEvents)
    if (event.write && event.pin == 5) TEST_ASSERT_EQUAL(LOW, event.value);

  hardware.safeStop();
  TEST_ASSERT_EQUAL_HEX16(0, latchedWords().back().word);
  TEST_ASSERT_EQUAL(0, fake::ledcDuties[0]);
}

void test_manual_valves_leave_onboard_contact_off_with_full_or_fallback_profile() {
  for (bool fullReady : {false, true}) {
    auto config = onboardContactFixture();
    config.verifiedBoardConfig = fullReady;
    Hardware hardware(config, false);
    TEST_ASSERT_EQUAL(fullReady, hardware.begin());
    TEST_ASSERT_TRUE(hardware.beginManualValves(confirmedRigManualValves()));
    fake::gpioEvents.clear();
    const unsigned pwmCalls = fake::ledcCalls;
    TEST_ASSERT_TRUE(hardware.applyManualValves({{true, true, true, true, true, false, true}}));
    TEST_ASSERT_EQUAL(pwmCalls, fake::ledcCalls);
    TEST_ASSERT_EQUAL(1, latchedWords().size());
    TEST_ASSERT_EQUAL_HEX16(0x006f, latchedWords()[0].word);
    hardware.safeStop();
    TEST_ASSERT_EQUAL_HEX16(0, latchedWords().back().word);
  }
}

void test_manual_fallback_rejects_pump_overlap_or_active_low_relay() {
  for (bool overlap : {false, true}) {
    auto config = onboardContactFixture();
    config.verifiedBoardConfig = false;
    config.pumpContactBit = overlap ? 6 : 15;
    config.pumpContactActiveHigh = overlap;
    Hardware hardware(config, false);
    TEST_ASSERT_FALSE(hardware.begin());
    TEST_ASSERT_FALSE(hardware.beginManualValves(confirmedRigManualValves()));
    TEST_ASSERT_FALSE(hardware.valveControlReady());
    TEST_ASSERT_EQUAL(0, fake::gpioCalls);
  }
}

void test_absent_v6_frees_bit4_and_rejects_commands_to_the_absent_valve() {
  auto config = onboardContactFixture();
  config.pumpContactBit = 4;
  config.valveBits[kValve6Slot] = -1;
  TEST_ASSERT_NULL(validateBoardConfig(config));
  auto invalid = config;
  invalid.safeValves[kValve6Slot] = true;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(invalid));
  invalid = config;
  invalid.valveBits[4] = -1;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(invalid));

  Outputs requested = pump(25);
  requested.valves[6] = true;
  requested.valves[kValve6Slot] = true;
  Recipe recipe;
  recipe.name = "V6 command";
  recipe.stepCount = 1;
  recipe.steps[0] = {"Test", 10, requested};
  SafetyConfig safety;
  safety.valve6Absent = true;
  Controller core(safety);
  TEST_ASSERT_NOT_NULL(core.load(recipe));
  TEST_ASSERT_NOT_NULL(core.manual(requested, 0));
  TEST_ASSERT_TRUE(core.state() == State::Idle);
  Controller legacy;
  TEST_ASSERT_NULL(legacy.load(recipe));
  TEST_ASSERT_NULL(legacy.manual(requested, 0));

  Hardware hardware(config, false);
  TEST_ASSERT_TRUE(hardware.begin());
  TEST_ASSERT_TRUE(hardware.beginManualValves(confirmedRigManualValves()));
  requested.valves[kValve6Slot] = false;
  TEST_ASSERT_TRUE(hardware.applyManualValves(requested.valves));
  TEST_ASSERT_EQUAL_HEX16(0x0040, latchedWords().back().word);
  hardware.safeStop();
  TEST_ASSERT_NULL(core.manual(requested, 0));
  TEST_ASSERT_TRUE(hardware.apply(requested, 1000));
  TEST_ASSERT_TRUE(hardware.apply(requested, 1100, true));
  TEST_ASSERT_EQUAL_HEX16(0x0050, latchedWords().back().word);
  requested.valves[kValve6Slot] = true;
  TEST_ASSERT_FALSE(hardware.apply(requested, 1101, true));
  TEST_ASSERT_EQUAL_HEX16(0, latchedWords().back().word);
}

void test_tach_is_optional_and_requires_a_free_pin_and_positive_pulses_per_revolution() {
  auto config = pwmFixture();
  Hardware withoutTach(config, false);
  TEST_ASSERT_TRUE(withoutTach.begin());
  TEST_ASSERT_NULL(withoutTach.pumpTachStatus(0));
  TEST_ASSERT_EQUAL(-1, fake::pcntPin);
  for (int pin : {-2, 0, 1, 2, 3, 4, 5, 6, 12, 13, 14, 15, 25, 26, 34, 39, 40}) {
    config.pumpTachPin = pin;
    TEST_ASSERT_NOT_NULL(validateBoardConfig(config));
  }
  config.pumpTachPin = 27;
  TEST_ASSERT_NULL(validateBoardConfig(config));
  config.pumpTachPulsesPerRevolution = 0;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(config));
}

void test_tach_counts_across_counter_and_clock_wraps_and_reports_zero_pulses() {
  auto config = pwmFixture();
  config.pumpTachPin = 27;
  Hardware hardware(config, false);
  TEST_ASSERT_TRUE(hardware.begin());
  TEST_ASSERT_EQUAL(27, fake::pcntPin);
  const uint32_t start = UINT32_MAX - 250U;
  fake::pcntCount = 32760;
  hardware.sample(start);
  double rpm = 0;
  TEST_ASSERT_FALSE(hardware.readPumpRpm(start, rpm));
  TEST_ASSERT_EQUAL_STRING("waiting", hardware.pumpTachStatus(start));

  fake::pcntCount = 243;  // 250 pulses across the high-limit reset.
  hardware.sample(start + 499U);
  TEST_ASSERT_FALSE(hardware.readPumpRpm(start + 499U, rpm));
  hardware.sample(start + 500U);
  TEST_ASSERT_TRUE(hardware.readPumpRpm(start + 500U, rpm));
  TEST_ASSERT_DOUBLE_WITHIN(0.001, 300, rpm);
  TEST_ASSERT_EQUAL_STRING("reading_received", hardware.pumpTachStatus(start + 500U));
  TEST_ASSERT_FALSE(hardware.pumpRunContactCommanded());  // RPM does not depend on the relay command.

  hardware.sample(start + 1000U);
  TEST_ASSERT_TRUE(hardware.readPumpRpm(start + 1000U, rpm));
  TEST_ASSERT_DOUBLE_WITHIN(0.001, 0, rpm);
  TEST_ASSERT_EQUAL_STRING("no_pulses", hardware.pumpTachStatus(start + 1000U));
}

void test_tach_errors_and_missed_windows_omit_rpm_without_blocking_control() {
  auto config = pwmFixture();
  config.pumpTachPin = 27;
  fake::pcntConfigFails = true;
  Hardware unavailable(config, false);
  TEST_ASSERT_TRUE(unavailable.begin());
  TEST_ASSERT_EQUAL_STRING("unavailable", unavailable.pumpTachStatus(0));
  TEST_ASSERT_TRUE(unavailable.ready());

  fake::pcntConfigFails = false;
  config.pumpTachPulsesPerRevolution = 50;
  Hardware hardware(config, false);
  TEST_ASSERT_TRUE(hardware.begin());
  hardware.sample(0);
  fake::pcntCount = 250;
  hardware.sample(500);
  double rpm = 0;
  TEST_ASSERT_TRUE(hardware.readPumpRpm(500, rpm));
  TEST_ASSERT_DOUBLE_WITHIN(0.001, 600, rpm);

  TEST_ASSERT_FALSE(hardware.readPumpRpm(1501, rpm));
  hardware.sample(1501);
  TEST_ASSERT_EQUAL_STRING("unavailable", hardware.pumpTachStatus(1501));
  fake::pcntReadFails = true;
  hardware.sample(2001);
  TEST_ASSERT_FALSE(hardware.readPumpRpm(2001, rpm));
  TEST_ASSERT_TRUE(hardware.ready());
  fake::pcntReadFails = false;
  hardware.sample(2501);
  TEST_ASSERT_EQUAL_STRING("waiting", hardware.pumpTachStatus(2501));
  fake::pcntCount += 250;
  hardware.sample(3001);
  TEST_ASSERT_TRUE(hardware.readPumpRpm(3001, rpm));
  TEST_ASSERT_DOUBLE_WITHIN(0.001, 600, rpm);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_default_and_unreviewed_pwm_never_touch_any_gpio_i2c_or_ledc);
  RUN_TEST(test_duty_encoding_zero_half_full_and_register_bounds);
  RUN_TEST(test_profile_rejects_reserved_and_overlapping_pwm_pins);
  RUN_TEST(test_profile_requires_reviewed_bounded_timer_and_measured_settling);
  RUN_TEST(test_startup_zeros_stale_channel_before_run_and_native_adc_needs_no_i2c);
  RUN_TEST(test_nominal_pwm_and_settling_hold_stop_until_safety_checked_apply);
  RUN_TEST(test_high_to_lower_command_waits_and_distinct_new_command_restarts_delay);
  RUN_TEST(test_stop_cancels_pending_start_and_no_late_run_occurs);
  RUN_TEST(test_contact_stop_precedes_pwm_zero_and_pwm_command_precedes_run);
  RUN_TEST(test_pwm_with_ads_uses_only_ads_address_and_handles_i2c_initialization_failure);
  RUN_TEST(test_pwm_ads_probe_failure_zeroes_output_and_keeps_contact_stopped);
  RUN_TEST(test_ledc_setup_frequency_and_attach_errors_cannot_run_pump);
  RUN_TEST(test_checked_write_errors_latch_hardware_failure_with_independent_contact_stop);
  RUN_TEST(test_even_failed_pwm_zero_cannot_prevent_independent_stop_contact);
  RUN_TEST(test_invalid_pump_commands_reject_nonfinite_and_out_of_range_and_stop);
  RUN_TEST(test_settling_timer_is_correct_across_millis_rollover);
  RUN_TEST(test_pending_activation_cannot_beat_watchdog_or_pressure_fault);
  RUN_TEST(test_low_pressure_start_requires_a_fresh_low_adc_sample_and_expires);
  RUN_TEST(test_gp8403_range_zero_and_health_probe_are_preserved_without_ledc_calls);
  RUN_TEST(test_onboard_contact_must_be_spare_in_range_low_at_rest_and_exclusive);
  RUN_TEST(test_onboard_startup_latches_stopped_before_enabling_outputs);
  RUN_TEST(test_onboard_contact_opens_before_valve_and_pwm_changes_and_waits_to_run);
  RUN_TEST(test_onboard_contact_opens_even_if_pwm_cannot_be_zeroed);
  RUN_TEST(test_hardware_profile_limits_cannot_be_bypassed);
  RUN_TEST(test_manual_pump_handoff_holds_the_existing_valves_until_run);
  RUN_TEST(test_manual_valves_leave_onboard_contact_off_with_full_or_fallback_profile);
  RUN_TEST(test_manual_fallback_rejects_pump_overlap_or_active_low_relay);
  RUN_TEST(test_absent_v6_frees_bit4_and_rejects_commands_to_the_absent_valve);
  RUN_TEST(test_tach_is_optional_and_requires_a_free_pin_and_positive_pulses_per_revolution);
  RUN_TEST(test_tach_counts_across_counter_and_clock_wraps_and_reports_zero_pulses);
  RUN_TEST(test_tach_errors_and_missed_windows_omit_rpm_without_blocking_control);
  return UNITY_END();
}
