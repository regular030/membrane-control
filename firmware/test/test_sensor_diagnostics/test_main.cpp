#include <unity.h>
#include "Hardware.h"

using namespace basu;

void setUp() { fake::resetGpio(); fake::resetLedc(); Wire.reset(); }
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
  TEST_ASSERT_EQUAL_STRING("ads1115", analogSourceName(AnalogSource::Ads1115));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_factory_disabled_inputs_are_distinct_from_configured_locked_inputs);
  RUN_TEST(test_dry_run_status_is_explicit_and_diagnostics_do_not_create_readings);
  RUN_TEST(test_uncalibrated_channel_is_explained_without_initializing_other_inputs);
  RUN_TEST(test_configured_waiting_fresh_and_stale_native_readings_are_reported);
  RUN_TEST(test_native_out_of_reviewed_range_is_not_a_valid_numeric_reading);
  RUN_TEST(test_real_zero_calibration_can_be_valid_without_claiming_sensor_connectivity);
  RUN_TEST(test_ads_read_failure_and_conversion_timeout_are_unavailable_not_zero);
  RUN_TEST(test_ads_conversion_command_failure_is_unavailable_and_never_validates_old_data);
  RUN_TEST(test_hardware_initialization_and_later_health_failure_override_configured_readings);
  RUN_TEST(test_disabled_channel_stays_not_configured_when_other_hardware_fails);
  RUN_TEST(test_freshness_survives_unsigned_millis_rollover);
  RUN_TEST(test_source_names_are_fixed_diagnostic_codes);
  return UNITY_END();
}
