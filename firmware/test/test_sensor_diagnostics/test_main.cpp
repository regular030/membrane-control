#include <unity.h>
#include "Hardware.h"

using namespace basu;

void setUp() {
  fake::resetGpio(); fake::resetLedc(); Wire.reset();
  fake::adc2ReadFails = false;
  fake::adc2SetupFails = false;
  fake::adc2PulldownFails = false;
  fake::adc2PulldownEnabled.fill(false);
}
void tearDown() {}

BoardConfig sensorFixture() {
  // Native-only test fixture, never the installed rig's commissioned profile.
  BoardConfig config;
  config.verifiedBoardConfig = true;
  config.safeProfileVerified = true;
  config.pressureLimitPsi = 20;
  config.gp8403InterfaceVerified = true;
  config.pumpContactPin = 26;
  config.shiftDataPin = 14; config.shiftClockPin = 13;
  config.shiftLatchPin = 12; config.shiftOePin = 5;
  config.valveBits = {{0, 1, 2, 3, 4, 5, 6}};
  config.i2cSdaPin = 21; config.i2cSclPin = 22;
  config.pressure.source = config.flow.source = config.pumpFeedback.source = AnalogSource::NativeAdc1;
  config.pressure.pin = 34; config.flow.pin = 35; config.pumpFeedback.pin = 36;
  config.pressure.calibrationVerified = config.flow.calibrationVerified = config.pumpFeedback.calibrationVerified = true;
  return config;
}

void test_factory_disabled_inputs_are_distinct_from_configured_locked_inputs() {
  Hardware factory(BoardConfig{}, false);
  TEST_ASSERT_FALSE(factory.begin());
  for (std::size_t index = 0; index < 3; ++index)
    TEST_ASSERT_EQUAL_STRING("not_configured", factory.sensorStatus(index, 100));
  auto config = sensorFixture(); config.verifiedBoardConfig = false;
  Hardware locked(config, false);
  TEST_ASSERT_FALSE(locked.begin());
  for (unsigned repeat = 0; repeat < 50; ++repeat) {
    locked.sample(1000 + repeat);
    for (std::size_t index = 0; index < 3; ++index)
      TEST_ASSERT_EQUAL_STRING("profile_locked", locked.sensorStatus(index, 1000 + repeat));
  }
  TEST_ASSERT_EQUAL(0, fake::gpioCalls);
  TEST_ASSERT_EQUAL(0, fake::ledcCalls);
  TEST_ASSERT_EQUAL(0, Wire.beginCount);
  TEST_ASSERT_EQUAL(0, Wire.transactionCount);
  TEST_ASSERT_FALSE(locked.measurements().flow.valid);
}

void test_dry_run_status_is_explicit_and_diagnostics_do_not_create_readings() {
  Hardware hardware(BoardConfig{}, true);
  TEST_ASSERT_TRUE(hardware.begin());
  hardware.sample(1000);
  for (std::size_t index = 0; index < 3; ++index)
    TEST_ASSERT_EQUAL_STRING("simulated", hardware.sensorStatus(index, 1000));
  TEST_ASSERT_FALSE(hardware.measurements().pressure.valid);
  TEST_ASSERT_FALSE(hardware.measurements().flow.valid);
  TEST_ASSERT_FALSE(hardware.measurements().pumpFeedback.valid);
  TEST_ASSERT_EQUAL(0, fake::gpioCalls);
  TEST_ASSERT_EQUAL(0, Wire.beginCount);
}

void test_uncalibrated_channel_is_explained_without_initializing_other_inputs() {
  auto config = sensorFixture(); config.flow.calibrationVerified = false;
  Hardware hardware(config, false);
  TEST_ASSERT_FALSE(hardware.begin());
  TEST_ASSERT_EQUAL_STRING("uncalibrated", hardware.sensorStatus(1, 100));
  TEST_ASSERT_EQUAL_STRING("profile_locked", hardware.sensorStatus(0, 100));
  TEST_ASSERT_EQUAL(0, fake::gpioCalls);
  config = sensorFixture(); config.flow.maxPinVolts = 5;
  Hardware badRange(config, false);
  TEST_ASSERT_FALSE(badRange.begin());
  TEST_ASSERT_EQUAL_STRING("uncalibrated", badRange.sensorStatus(1, 100));
}

void test_configured_waiting_fresh_and_stale_native_readings_are_reported() {
  const auto config = sensorFixture(); Hardware hardware(config, false);
  TEST_ASSERT_TRUE(hardware.begin());
  TEST_ASSERT_EQUAL(ADC_11db, fake::adcAttenuation[config.pressure.pin]);
  TEST_ASSERT_EQUAL(ADC_11db, fake::adcAttenuation[config.flow.pin]);
  TEST_ASSERT_EQUAL(ADC_11db, fake::adcAttenuation[config.pumpFeedback.pin]);
  for (std::size_t index = 0; index < 3; ++index)
    TEST_ASSERT_EQUAL_STRING("stale", hardware.sensorStatus(index, 0));
  hardware.sample(100);
  const unsigned gpioCalls = fake::gpioCalls;
  for (std::size_t index = 0; index < 3; ++index) {
    TEST_ASSERT_EQUAL_STRING("reading_received", hardware.sensorStatus(index, 100));
    TEST_ASSERT_EQUAL_STRING("reading_received", hardware.sensorStatus(index, 1100));
    TEST_ASSERT_EQUAL_STRING("stale", hardware.sensorStatus(index, 1101));
  }
  TEST_ASSERT_EQUAL(gpioCalls, fake::gpioCalls);  // Status queries perform no reads.
}

void test_native_out_of_reviewed_range_is_not_a_valid_numeric_reading() {
  auto config = sensorFixture(); config.flow.maxPinVolts = 0.9;
  Hardware hardware(config, false); TEST_ASSERT_TRUE(hardware.begin());
  hardware.sample(100);  // Mock ADC supplies 1.0 V.
  TEST_ASSERT_EQUAL_STRING("out_of_range", hardware.sensorStatus(1, 100));
  TEST_ASSERT_FALSE(hardware.measurements().flow.valid);
  TEST_ASSERT_EQUAL_STRING("reading_received", hardware.sensorStatus(0, 100));
}

void test_adc2_pressure_separates_conversion_failure_from_a_low_sample() {
  auto config = sensorFixture();
  config.pressure.source = AnalogSource::NativeAdc2;
  config.pressure.pin = 26;
  TEST_ASSERT_EQUAL_STRING("ADC2 pin invalid or conflicting", validateBoardConfig(config));
  config.pressure.pin = 27;
  config.pressure.nativeAdcAttenuation = NativeAdcAttenuation::Db2_5;
  config.pressure.minPinVolts = 0.100;
  config.pressure.maxPinVolts = 1.000;
  config.pressure.unitsPerVolt = 100;

  fake::adc2SetupFails = true;
  Hardware setupFailure(config, false);
  TEST_ASSERT_FALSE(setupFailure.begin());
  TEST_ASSERT_EQUAL_STRING("adc2_initialization_failed", setupFailure.error());
  fake::adc2SetupFails = false;

  Hardware hardware(config, false);
  TEST_ASSERT_TRUE(hardware.begin());
  TEST_ASSERT_EQUAL(ADC_2_5db, fake::adcAttenuation[27]);
  fake::adcMillivolts[27] = 78;
  hardware.sample(100);
  TEST_ASSERT_TRUE(hardware.measurements().pressureBelowAdcRange);
  TEST_ASSERT_EQUAL_UINT32(78, hardware.pressureAdcMillivolts(100).value());
  TEST_ASSERT_EQUAL_STRING("out_of_range", hardware.sensorStatus(0, 100));

  fake::adc2ReadFails = true;
  hardware.sample(200);
  TEST_ASSERT_FALSE(hardware.measurements().pressureBelowAdcRange);
  TEST_ASSERT_FALSE(hardware.measurements().pressure.valid);
  TEST_ASSERT_FALSE(hardware.pressureAdcMillivolts(200).has_value());
  TEST_ASSERT_EQUAL_STRING("hardware_unavailable", hardware.sensorStatus(0, 200));
  TEST_ASSERT_EQUAL_STRING("reading_received", hardware.sensorStatus(1, 200));

  fake::adc2ReadFails = false;
  fake::adcMillivolts[27] = 810;
  hardware.sample(300);
  TEST_ASSERT_TRUE(hardware.measurements().pressure.valid);
  TEST_ASSERT_EQUAL_DOUBLE(81, hardware.measurements().pressure.value);
}

void test_adc2_pulldown_is_opt_in_and_applied_after_adc_setup() {
  auto config = sensorFixture();
  config.pressure.nativeAdc2Pulldown = true;
  TEST_ASSERT_EQUAL_STRING("internal pull-down requires a native ADC2 input", validateBoardConfig(config));

  config.pressure.source = AnalogSource::NativeAdc2;
  config.pressure.pin = 27;
  Hardware enabled(config, false);
  TEST_ASSERT_TRUE(enabled.begin());
  TEST_ASSERT_TRUE(fake::adc2PulldownEnabled[27]);
  TEST_ASSERT_FALSE(fake::adc2PulldownEnabled[config.flow.pin]);

  fake::adc2PulldownFails = true;
  Hardware failed(config, false);
  TEST_ASSERT_FALSE(failed.begin());
  TEST_ASSERT_EQUAL_STRING("adc2_pulldown_initialization_failed", failed.error());

  config.pressure.nativeAdc2Pulldown = false;
  fake::adc2PulldownEnabled.fill(false);
  Hardware disabled(config, false);
  TEST_ASSERT_TRUE(disabled.begin());
  TEST_ASSERT_FALSE(fake::adc2PulldownEnabled[27]);
}

void test_uncalibrated_adc2_pulldown_monitors_voltage_without_enabling_pump() {
  auto config = sensorFixture();
  config.pressure.source = AnalogSource::NativeAdc2;
  config.pressure.pin = 27;
  config.pressure.calibrationVerified = false;
  config.pressure.nativeAdc2Pulldown = true;
  Hardware hardware(config, false);
  TEST_ASSERT_FALSE(hardware.begin());
  TEST_ASSERT_TRUE(hardware.sensorMonitoringOnly());
  TEST_ASSERT_TRUE(fake::adc2PulldownEnabled[27]);
  TEST_ASSERT_EQUAL_STRING("pressure_calibration_pending", hardware.error());
  TEST_ASSERT_FALSE(hardware.pumpContactCommandAvailable());
  for (const auto& event : fake::gpioEvents) {
    TEST_ASSERT_FALSE(event.write);
    TEST_ASSERT_TRUE(event.pin == 27 || event.pin == config.flow.pin);
    TEST_ASSERT_EQUAL(INPUT, event.value);
  }
  Outputs pumping;
  pumping.pumpPercent = 25;
  TEST_ASSERT_FALSE(hardware.apply(pumping, 1000, true));
  fake::adcMillivolts[27] = 800;
  fake::adcMillivolts[config.flow.pin] = 500;
  hardware.sample(1100);
  TEST_ASSERT_EQUAL_UINT32(800, hardware.pressureAdcMillivolts(1100).value());
  TEST_ASSERT_FALSE(hardware.measurements().pressure.valid);
  TEST_ASSERT_EQUAL_STRING("uncalibrated", hardware.sensorStatus(0, 1100));
  TEST_ASSERT_EQUAL_UINT32(500, hardware.flowAdcMillivolts(1100).value());
  TEST_ASSERT_EQUAL_DOUBLE(0.5, hardware.measurements().flow.value);
  TEST_ASSERT_EQUAL_STRING("reading_received", hardware.sensorStatus(1, 1100));
  TEST_ASSERT_FALSE(hardware.measurements().pumpFeedback.valid);
  TEST_ASSERT_FALSE(hardware.pressureAdcMillivolts(1301).has_value());
  TEST_ASSERT_FALSE(hardware.flowAdcMillivolts(1301).has_value());
  TEST_ASSERT_EQUAL(0, Wire.transactionCount);
  TEST_ASSERT_EQUAL(0, fake::ledcCalls);
}

void test_native_low_attenuation_has_a_supported_per_pin_range() {
  auto config = sensorFixture();
  config.pressure.nativeAdcAttenuation = NativeAdcAttenuation::Db2_5;
  config.pressure.minPinVolts = 0.100;
  config.pressure.maxPinVolts = 1.250;
  Hardware hardware(config, false);
  TEST_ASSERT_TRUE(hardware.begin());
  TEST_ASSERT_EQUAL(ADC_2_5db, fake::adcAttenuation[34]);
  TEST_ASSERT_EQUAL(ADC_11db, fake::adcAttenuation[35]);
  TEST_ASSERT_EQUAL(ADC_11db, fake::adcAttenuation[36]);
  uint32_t now = 100;
  for (const uint32_t millivolts : {99, 100, 142, 1250, 1251}) {
    fake::adcMillivolts[34] = millivolts;
    hardware.sample(now);
    const bool inRange = millivolts >= 100 && millivolts <= 1250;
    const auto& reading = hardware.measurements().pressure;
    TEST_ASSERT_EQUAL(inRange, reading.fresh(now, config.sensorMaxAgeMs));
    if (inRange) {
      TEST_ASSERT_EQUAL_DOUBLE(millivolts / 1000.0, reading.value);
      TEST_ASSERT_FALSE(reading.fresh(now + config.sensorMaxAgeMs + 1, config.sensorMaxAgeMs));
    }
    now += 100;
  }
}

void test_native_low_attenuation_validation_does_not_change_ads() {
  auto config = sensorFixture();
  auto& input = config.pressure;
  input.nativeAdcAttenuation = NativeAdcAttenuation::Db2_5;
  input.minPinVolts = 0.099;
  input.maxPinVolts = 1.250;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(config));
  input.minPinVolts = 0.100;
  input.maxPinVolts = 1.251;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(config));
  input.maxPinVolts = 1.250;
  input.nativeAdcAttenuation = static_cast<NativeAdcAttenuation>(10);
  TEST_ASSERT_NOT_NULL(validateBoardConfig(config));
  input.source = AnalogSource::Ads1115;
  input.adsChannel = 0;
  input.nativeAdcAttenuation = NativeAdcAttenuation::Db2_5;
  input.minPinVolts = 0;
  input.maxPinVolts = 3;
  Hardware hardware(config, false);
  TEST_ASSERT_TRUE(hardware.begin());
  TEST_ASSERT_EQUAL(-1, fake::adcAttenuation[34]);
}

void test_real_zero_calibration_can_be_valid_without_claiming_sensor_connectivity() {
  auto config = sensorFixture();
  config.flow.rejectRails = false;
  const Reading zero = calibratedReading(config.flow, 0.0, 100);
  TEST_ASSERT_TRUE(zero.valid);
  TEST_ASSERT_EQUAL_DOUBLE(0.0, zero.value);
  TEST_ASSERT_EQUAL_STRING("reading_received", classifySensorStatus(config, config.flow, zero,
      SensorReadState::Reading, true, true, false, 100));
  config.flow.rejectRails = true;
  const Reading rejected = calibratedReading(config.flow, 0.0, 100);
  TEST_ASSERT_FALSE(rejected.valid);
  TEST_ASSERT_EQUAL_STRING("out_of_range", classifySensorStatus(config, config.flow, rejected,
      SensorReadState::OutOfRange, true, true, false, 100));
}

void test_ads_read_failure_and_conversion_timeout_are_unavailable_not_zero() {
  for (bool readFailure : {false, true}) {
    Wire.reset();
    auto config = sensorFixture(); config.flow.source = AnalogSource::Ads1115; config.flow.adsChannel = 1;
    Hardware hardware(config, false); TEST_ASSERT_TRUE(hardware.begin());
    hardware.sample(100);  // Starts the first ADS conversion.
    if (readFailure) Wire.failNext = true;
    hardware.sample(readFailure ? 110 : 131);
    TEST_ASSERT_EQUAL_STRING("hardware_unavailable", hardware.sensorStatus(1, 140));
    TEST_ASSERT_FALSE(hardware.measurements().flow.valid);
    TEST_ASSERT_EQUAL_STRING("reading_received", hardware.sensorStatus(0, 140));
  }
}

void test_ads_conversion_command_failure_is_unavailable_and_never_validates_old_data() {
  auto config = sensorFixture(); config.flow.source = AnalogSource::Ads1115; config.flow.adsChannel = 0;
  Hardware hardware(config, false); TEST_ASSERT_TRUE(hardware.begin());
  Wire.failNext = true;
  hardware.sample(100);
  TEST_ASSERT_EQUAL_STRING("hardware_unavailable", hardware.sensorStatus(1, 100));
  TEST_ASSERT_FALSE(hardware.measurements().flow.valid);
}

void test_hardware_initialization_and_later_health_failure_override_configured_readings() {
  auto config = sensorFixture(); Wire.beginSucceeds = false;
  Hardware unavailable(config, false); TEST_ASSERT_FALSE(unavailable.begin());
  TEST_ASSERT_EQUAL_STRING("hardware_unavailable", unavailable.sensorStatus(1, 100));
  Wire.reset();
  Hardware working(config, false); TEST_ASSERT_TRUE(working.begin());
  working.sample(100);
  TEST_ASSERT_EQUAL_STRING("reading_received", working.sensorStatus(1, 100));
  Wire.failingAddress = config.gp8403Address;
  working.sample(1000);
  TEST_ASSERT_FALSE(working.ready());
  TEST_ASSERT_EQUAL_STRING("hardware_unavailable", working.sensorStatus(1, 1000));
}

void test_disabled_channel_stays_not_configured_when_other_hardware_fails() {
  auto config = sensorFixture(); config.flow.source = AnalogSource::Disabled;
  Wire.beginSucceeds = false;
  Hardware hardware(config, false); TEST_ASSERT_FALSE(hardware.begin());
  TEST_ASSERT_EQUAL_STRING("not_configured", hardware.sensorStatus(1, 100));
  TEST_ASSERT_EQUAL_STRING("hardware_unavailable", hardware.sensorStatus(0, 100));
}

void test_freshness_survives_unsigned_millis_rollover() {
  const auto config = sensorFixture();
  Reading reading = calibratedReading(config.flow, 1.0, UINT32_MAX - 100);
  TEST_ASSERT_EQUAL_STRING("reading_received", classifySensorStatus(config, config.flow, reading,
      SensorReadState::Reading, true, true, false, 200));
  TEST_ASSERT_EQUAL_STRING("stale", classifySensorStatus(config, config.flow, reading,
      SensorReadState::Reading, true, true, false, 1000));
}

void test_source_names_are_fixed_diagnostic_codes() {
  TEST_ASSERT_EQUAL_STRING("disabled", analogSourceName(AnalogSource::Disabled));
  TEST_ASSERT_EQUAL_STRING("native_adc1", analogSourceName(AnalogSource::NativeAdc1));
  TEST_ASSERT_EQUAL_STRING("native_adc2", analogSourceName(AnalogSource::NativeAdc2));
  TEST_ASSERT_EQUAL_STRING("ads1115", analogSourceName(AnalogSource::Ads1115));
}

void test_factory_sensor_test_reads_three_input_pins_without_creating_process_readings() {
  Hardware hardware(BoardConfig{}, false);
  TEST_ASSERT_FALSE(hardware.begin());
  TEST_ASSERT_TRUE(hardware.beginManualValves(confirmedRigManualValves()));
  fake::resetGpio();
  fake::adcMillivolts[34] = 735;
  fake::adcMillivolts[36] = 0;
  fake::adcMillivolts[39] = 1821;

  SensorTestMillivolts result;
  TEST_ASSERT_TRUE(hardware.sensorTestAvailable(true));
  TEST_ASSERT_NULL(hardware.readSensorTestInputs(true, State::Idle, result));
  TEST_ASSERT_EQUAL_UINT32(735, result.pressure);
  TEST_ASSERT_EQUAL_UINT32(0, result.flow);
  TEST_ASSERT_EQUAL_UINT32(1821, result.pumpFeedback);
  TEST_ASSERT_EQUAL(ADC_2_5db, fake::adcAttenuation[34]);
  TEST_ASSERT_EQUAL(ADC_2_5db, fake::adcAttenuation[36]);
  TEST_ASSERT_EQUAL(ADC_11db, fake::adcAttenuation[39]);
  const int expectedPins[] = {34, 36, 39};
  TEST_ASSERT_EQUAL(3, fake::adcReadPins.size());
  TEST_ASSERT_EQUAL_INT_ARRAY(expectedPins, fake::adcReadPins.data(), 3);
  TEST_ASSERT_EQUAL(3, fake::gpioEvents.size());
  for (std::size_t i = 0; i < 3; ++i) {
    TEST_ASSERT_FALSE(fake::gpioEvents[i].write);
    TEST_ASSERT_EQUAL(expectedPins[i], fake::gpioEvents[i].pin);
    TEST_ASSERT_EQUAL(INPUT, fake::gpioEvents[i].value);
    TEST_ASSERT_EQUAL_STRING("not_configured", hardware.sensorStatus(i, 100));
  }
  TEST_ASSERT_FALSE(hardware.ready());
  TEST_ASSERT_TRUE(hardware.valveControlReady());
  TEST_ASSERT_FALSE(hardware.measurements().pressure.valid);
  TEST_ASSERT_FALSE(hardware.measurements().flow.valid);
  TEST_ASSERT_FALSE(hardware.measurements().pumpFeedback.valid);
  TEST_ASSERT_EQUAL(0, fake::ledcCalls);
  TEST_ASSERT_EQUAL(0, Wire.transactionCount);
}

void test_sensor_test_rejects_nonidle_simulated_and_custom_profiles_without_adc_access() {
  SensorTestMillivolts result{1, 2, 3};
  Hardware factory(BoardConfig{}, false);
  TEST_ASSERT_FALSE(factory.begin());
  for (State state : {State::Running, State::Manual, State::ManualValves, State::Fault})
    TEST_ASSERT_NOT_NULL(factory.readSensorTestInputs(true, state, result));
  constexpr auto live = SensorTestScope::IdleOrManualValves;
  for (State state : {State::Running, State::Manual, State::Fault})
    TEST_ASSERT_NOT_NULL(factory.readSensorTestInputs(true, state, result, live));
  TEST_ASSERT_FALSE(factory.sensorTestAvailable(false));
  TEST_ASSERT_NOT_NULL(factory.readSensorTestInputs(false, State::Idle, result, live));

  Hardware simulation(BoardConfig{}, true);
  TEST_ASSERT_FALSE(simulation.sensorTestAvailable(true));
  TEST_ASSERT_NOT_NULL(simulation.readSensorTestInputs(true, State::Idle, result, live));
  TEST_ASSERT_EQUAL(0, fake::gpioCalls);
  TEST_ASSERT_TRUE(fake::adcReadPins.empty());
  TEST_ASSERT_EQUAL_UINT32(1, result.pressure);
  TEST_ASSERT_EQUAL_UINT32(2, result.flow);
  TEST_ASSERT_EQUAL_UINT32(3, result.pumpFeedback);
}

void test_live_sensor_test_while_valves_are_active_leaves_outputs_and_measurements_unchanged() {
  Hardware hardware(BoardConfig{}, false);
  TEST_ASSERT_FALSE(hardware.begin());
  TEST_ASSERT_TRUE(hardware.beginManualValves(confirmedRigManualValves()));
  SensorTestMillivolts result;
  constexpr auto live = SensorTestScope::IdleOrManualValves;
  TEST_ASSERT_NULL(hardware.readSensorTestInputs(true, State::Idle, result, live));
  TEST_ASSERT_TRUE(hardware.applyManualValves({{true, false, false, false, false, false, true}}));

  const auto heldLevels = fake::levels;
  fake::gpioEvents.clear();
  fake::adcReadPins.clear();
  fake::adcMillivolts[34] = 610;
  fake::adcMillivolts[36] = 900;
  fake::adcMillivolts[39] = 1700;
  TEST_ASSERT_NULL(hardware.readSensorTestInputs(true, State::ManualValves, result, live));
  TEST_ASSERT_EQUAL_UINT32(610, result.pressure);
  TEST_ASSERT_EQUAL_UINT32(900, result.flow);
  TEST_ASSERT_EQUAL_UINT32(1700, result.pumpFeedback);
  TEST_ASSERT_EQUAL(3, fake::adcReadPins.size());
  const int expectedPins[] = {34, 36, 39};
  TEST_ASSERT_EQUAL_INT_ARRAY(expectedPins, fake::adcReadPins.data(), 3);
  TEST_ASSERT_TRUE(fake::gpioEvents.empty());  // The firmware does not repeat pin setup or write outputs.
  TEST_ASSERT_TRUE(fake::levels == heldLevels);
  TEST_ASSERT_FALSE(hardware.ready());
  TEST_ASSERT_FALSE(hardware.measurements().pressure.valid);
  TEST_ASSERT_FALSE(hardware.measurements().flow.valid);
  TEST_ASSERT_FALSE(hardware.measurements().pumpFeedback.valid);
  TEST_ASSERT_EQUAL(0, Wire.transactionCount);
  TEST_ASSERT_EQUAL(0, fake::ledcCalls);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_factory_disabled_inputs_are_distinct_from_configured_locked_inputs);
  RUN_TEST(test_dry_run_status_is_explicit_and_diagnostics_do_not_create_readings);
  RUN_TEST(test_uncalibrated_channel_is_explained_without_initializing_other_inputs);
  RUN_TEST(test_configured_waiting_fresh_and_stale_native_readings_are_reported);
  RUN_TEST(test_native_out_of_reviewed_range_is_not_a_valid_numeric_reading);
  RUN_TEST(test_adc2_pressure_separates_conversion_failure_from_a_low_sample);
  RUN_TEST(test_adc2_pulldown_is_opt_in_and_applied_after_adc_setup);
  RUN_TEST(test_uncalibrated_adc2_pulldown_monitors_voltage_without_enabling_pump);
  RUN_TEST(test_native_low_attenuation_has_a_supported_per_pin_range);
  RUN_TEST(test_native_low_attenuation_validation_does_not_change_ads);
  RUN_TEST(test_real_zero_calibration_can_be_valid_without_claiming_sensor_connectivity);
  RUN_TEST(test_ads_read_failure_and_conversion_timeout_are_unavailable_not_zero);
  RUN_TEST(test_ads_conversion_command_failure_is_unavailable_and_never_validates_old_data);
  RUN_TEST(test_hardware_initialization_and_later_health_failure_override_configured_readings);
  RUN_TEST(test_disabled_channel_stays_not_configured_when_other_hardware_fails);
  RUN_TEST(test_freshness_survives_unsigned_millis_rollover);
  RUN_TEST(test_source_names_are_fixed_diagnostic_codes);
  RUN_TEST(test_factory_sensor_test_reads_three_input_pins_without_creating_process_readings);
  RUN_TEST(test_sensor_test_rejects_nonidle_simulated_and_custom_profiles_without_adc_access);
  RUN_TEST(test_live_sensor_test_while_valves_are_active_leaves_outputs_and_measurements_unchanged);
  return UNITY_END();
}
