#include <unity.h>
#include <cmath>
#include <cstring>
#include <limits>
#include "Hardware.h"

using namespace basu;

void setUp() { fake::resetGpio(); fake::resetLedc(); Wire.reset(); }
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
  RUN_TEST(test_gp8403_range_zero_and_health_probe_are_preserved_without_ledc_calls);
  return UNITY_END();
}
