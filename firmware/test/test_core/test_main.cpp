#include <unity.h>
#include <cstring>
#include <limits>
#include "BoardConfig.h"
#include "JsonRecipe.h"
#include "Hardware.h"

using namespace basu;

void setUp() {}
void tearDown() {}

Recipe exampleRecipe() {
  Recipe recipe;
  recipe.name = "Bench sequence";
  recipe.description = "No legacy process assumptions";
  recipe.stepCount = 2;
  recipe.steps[0].name = "First";
  recipe.steps[0].durationSeconds = 0.5;
  recipe.steps[0].outputs.valves[0] = true;
  recipe.steps[0].outputs.pumpPercent = 10;
  recipe.steps[1].name = "Second";
  recipe.steps[1].durationSeconds = 0.25;
  recipe.steps[1].outputs.valves[1] = true;
  recipe.repeat = 2;
  return recipe;
}

void test_sequence_repeats_and_stops() {
  Controller controller;
  TEST_ASSERT_NULL(controller.load(exampleRecipe()));
  TEST_ASSERT_NULL(controller.start(100));
  TEST_ASSERT_EQUAL(1, controller.cycle());
  TEST_ASSERT_TRUE(controller.outputs().valves[0]);
  controller.heartbeat(500);
  controller.tick(600);
  TEST_ASSERT_EQUAL(1, controller.stepIndex());
  TEST_ASSERT_TRUE(controller.outputs().valves[1]);
  controller.tick(850);
  TEST_ASSERT_EQUAL(2, controller.cycle());
  TEST_ASSERT_EQUAL(0, controller.stepIndex());
  controller.tick(1600);
  TEST_ASSERT_EQUAL(static_cast<int>(State::Idle), static_cast<int>(controller.state()));
  TEST_ASSERT_EQUAL(-1, controller.stepIndex());
  TEST_ASSERT_EQUAL_DOUBLE(0, controller.outputs().pumpPercent);
  for (bool value : controller.outputs().valves) TEST_ASSERT_FALSE(value);
}

void test_invalid_recipe_is_atomic() {
  Controller controller;
  auto good = exampleRecipe();
  TEST_ASSERT_NULL(controller.load(good));
  auto bad = good;
  bad.name = "Must not replace";
  bad.steps[1].outputs.pumpPercent = NAN;
  TEST_ASSERT_NOT_NULL(controller.load(bad));
  TEST_ASSERT_EQUAL_STRING(good.name.c_str(), controller.recipe().name.c_str());
  bad = good;
  bad.repeat = 100;
  bad.steps[0].durationSeconds = 86400;
  TEST_ASSERT_NOT_NULL(validateRecipe(bad));
  bad = good;
  bad.sampleIntervalSeconds = 0.09;
  TEST_ASSERT_NOT_NULL(validateRecipe(bad));
  bad = good;
  bad.steps[0].durationSeconds = 0.099;
  TEST_ASSERT_NOT_NULL(validateRecipe(bad));
  bad.steps[0].durationSeconds = 0.1;
  TEST_ASSERT_NULL(validateRecipe(bad));
}

void test_active_recipe_replacement_and_manual_rejected() {
  Controller controller;
  TEST_ASSERT_NULL(controller.load(exampleRecipe()));
  TEST_ASSERT_NULL(controller.start(0));
  TEST_ASSERT_NOT_NULL(controller.load(exampleRecipe()));
  Outputs manual;
  manual.pumpPercent = 80;
  TEST_ASSERT_NOT_NULL(controller.manual(manual, 1));
  TEST_ASSERT_EQUAL_DOUBLE(10, controller.outputs().pumpPercent);
}

void test_timeout_latches_and_stop_does_not_clear() {
  Controller controller;
  Outputs manual;
  manual.valves[3] = true;
  manual.pumpPercent = 30;
  TEST_ASSERT_NULL(controller.manual(manual, 100));
  controller.tick(3099);
  TEST_ASSERT_TRUE(controller.active());
  controller.tick(3100);
  TEST_ASSERT_EQUAL_STRING("heartbeat_timeout", controller.fault().c_str());
  TEST_ASSERT_EQUAL_DOUBLE(0, controller.outputs().pumpPercent);
  controller.heartbeat(3101);
  controller.stop();
  TEST_ASSERT_EQUAL(static_cast<int>(State::Fault), static_cast<int>(controller.state()));
  TEST_ASSERT_NOT_NULL(controller.manual(manual, 3102));
  TEST_ASSERT_NULL(controller.clearFault());
  TEST_ASSERT_FALSE(controller.active());
  TEST_ASSERT_TRUE(controller.fault().empty());
}

void test_timer_wraparound() {
  Controller controller;
  auto recipe = exampleRecipe();
  recipe.repeat = 1;
  TEST_ASSERT_NULL(controller.load(recipe));
  const uint32_t start = UINT32_MAX - 200;
  TEST_ASSERT_NULL(controller.start(start));
  controller.tick(static_cast<uint32_t>(start + 500));
  TEST_ASSERT_EQUAL(1, controller.stepIndex());
  controller.heartbeat(static_cast<uint32_t>(start + 600));
  controller.tick(static_cast<uint32_t>(start + 750));
  TEST_ASSERT_FALSE(controller.active());
}

void test_physical_commissioning_and_pressure_guards() {
  SafetyConfig safety;
  safety.simulation = false;
  Controller unverified(safety);
  auto recipe = exampleRecipe();
  recipe.hardwareApproved = true;
  TEST_ASSERT_NULL(unverified.load(recipe));
  TEST_ASSERT_EQUAL_STRING("hardware_not_verified", unverified.start(0));
  safety.hardwareReady = true;
  safety.safeProfileVerified = true;
  safety.pressureLimitPsi = 25;
  safety.safeValves[6] = true;
  Controller controller(safety);
  TEST_ASSERT_NULL(controller.load(recipe));
  TEST_ASSERT_EQUAL_STRING("pressure_invalid_or_stale", controller.start(0));
  Measurements measurements;
  measurements.pressure = {5, true, 0};
  controller.setMeasurements(measurements);
  TEST_ASSERT_NULL(controller.start(0));
  measurements.pressure = {26, true, 100};
  controller.setMeasurements(measurements);
  controller.tick(100);
  TEST_ASSERT_EQUAL_STRING("pressure_limit_exceeded", controller.fault().c_str());
  TEST_ASSERT_TRUE(controller.outputs().valves[6]);
  TEST_ASSERT_EQUAL_DOUBLE(0, controller.outputs().pumpPercent);
}

void test_physical_stale_sensor_and_recipe_approval() {
  SafetyConfig safety;
  safety.simulation = false;
  safety.hardwareReady = true;
  safety.safeProfileVerified = true;
  safety.pressureLimitPsi = 25;
  Controller controller(safety);
  auto recipe = exampleRecipe();
  TEST_ASSERT_NULL(controller.load(recipe));
  TEST_ASSERT_EQUAL_STRING("recipe is not hardware approved", controller.start(0));
  recipe.hardwareApproved = true;
  recipe.steps[0].durationSeconds = 10;
  TEST_ASSERT_NULL(controller.load(recipe));
  Measurements measurements;
  measurements.pressure = {5, true, 0};
  controller.setMeasurements(measurements);
  TEST_ASSERT_NULL(controller.start(0));
  controller.heartbeat(1000);
  controller.tick(1001);
  TEST_ASSERT_EQUAL_STRING("pressure_invalid_or_stale", controller.fault().c_str());
}

void test_config_rejects_unverified_defaults_and_conflicts() {
  BoardConfig config;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(config));
  config.verifiedBoardConfig = true;
  config.safeProfileVerified = true;
  config.pressureLimitPsi = 20;
  config.gp8403InterfaceVerified = true;
  config.pumpContactPin = 4;
  config.i2cSdaPin = 21;
  config.i2cSclPin = 22;
  config.shiftDataPin = 16;
  config.shiftClockPin = 17;
  config.shiftLatchPin = 18;
  config.shiftOePin = 19;
  config.valveBits = {{0, 1, 2, 3, 4, 5, 6}};
  config.pressure.source = AnalogSource::Ads1115;
  config.pressure.adsChannel = 0;
  config.pressure.calibrationVerified = true;
  TEST_ASSERT_NULL(validateBoardConfig(config));
  config.shiftLatchPin = config.i2cSdaPin;
  TEST_ASSERT_NOT_NULL(validateBoardConfig(config));
}

void test_shift_polarity_and_untouched_channels() {
  BoardConfig config;
  config.valveBits = {{0, 2, 4, 6, 8, 10, 12}};
  config.shiftUnusedLevels = 0x8000;
  config.valveActiveHigh[1] = false;
  Outputs outputs;
  outputs.valves[0] = true;
  TEST_ASSERT_EQUAL_HEX16(0x8005, shiftLevels(config, outputs));
  outputs.valves[1] = true;
  TEST_ASSERT_EQUAL_HEX16(0x8001, shiftLevels(config, outputs));
}

void test_calibration_and_input_rail_rejection() {
  AnalogConfig config;
  config.calibrationVerified = true;
  config.unitsPerVolt = 40;
  config.offset = -2;
  config.minValue = 0;
  config.maxValue = 100;
  auto reading = calibratedReading(config, 1.0, 20);
  TEST_ASSERT_TRUE(reading.valid);
  TEST_ASSERT_EQUAL_DOUBLE(38, reading.value);
  TEST_ASSERT_FALSE(calibratedReading(config, 5.0, 20).valid);
  TEST_ASSERT_FALSE(calibratedReading(config, 0, 20).valid);
  TEST_ASSERT_FALSE(calibratedReading(config, NAN, 20).valid);
}

void test_json_wrong_types_and_trailing_data_rejected() {
  JsonDocument document;
  const char* valid = "{\"v\":1,\"id\":1,\"cmd\":\"hello\"} \r";
  TEST_ASSERT_NULL(decodeObject(valid, std::strlen(valid), document));
  const char* trailing = "{\"v\":1}junk";
  TEST_ASSERT_NOT_NULL(decodeObject(trailing, std::strlen(trailing), document));
  const char* nested = "{\"x\":[[[[[[[[[[[1]]]]]]]]]]]}";
  TEST_ASSERT_NOT_NULL(decodeObject(nested, std::strlen(nested), document));
  const char* outputs = "{\"valves\":[true,false,false,false,false,false,1],\"pump_percent\":20}";
  TEST_ASSERT_NULL(decodeObject(outputs, std::strlen(outputs), document));
  Outputs destination;
  destination.pumpPercent = 7;
  TEST_ASSERT_NOT_NULL(parseOutputs(document["valves"], document["pump_percent"], destination));
  TEST_ASSERT_EQUAL_DOUBLE(7, destination.pumpPercent);
}

void test_recipe_json_validation_is_atomic() {
  const char* input = R"({"schema_version":1,"name":"JSON recipe","description":"test","hardware_approved":false,"repeat":1,"sample_interval_s":1.0,"require_balance":false,"steps":[{"name":"Observe","duration_s":1,"valves":[false,false,false,false,false,false,false],"pump_percent":0}]})";
  JsonDocument document;
  TEST_ASSERT_NULL(decodeObject(input, std::strlen(input), document));
  Recipe recipe;
  TEST_ASSERT_NULL(parseRecipe(document.as<JsonVariantConst>(), recipe));
  TEST_ASSERT_EQUAL_STRING("JSON recipe", recipe.name.c_str());
  document["steps"][0]["pump_percent"] = "90";
  TEST_ASSERT_NOT_NULL(parseRecipe(document.as<JsonVariantConst>(), recipe));
  TEST_ASSERT_EQUAL_DOUBLE(0, recipe.steps[0].outputs.pumpPercent);
  document["steps"][0]["pump_percent"] = 0;
  document["schema_version"] = true;
  TEST_ASSERT_NOT_NULL(parseRecipe(document.as<JsonVariantConst>(), recipe));
}

void test_protocol_envelope_rejects_boolean_versions_and_ids() {
  JsonDocument document;
  document["v"] = true;
  document["id"] = 1;
  document["cmd"] = "heartbeat";
  uint32_t id = 0;
  std::string command;
  TEST_ASSERT_NOT_NULL(parseEnvelope(document.as<JsonVariantConst>(), id, command));
  document["v"] = 1;
  document["id"] = true;
  TEST_ASSERT_NOT_NULL(parseEnvelope(document.as<JsonVariantConst>(), id, command));
  document["id"] = 2;
  TEST_ASSERT_NULL(parseEnvelope(document.as<JsonVariantConst>(), id, command));
  TEST_ASSERT_EQUAL(2, id);
}

void test_json_rejects_embedded_nul_and_malformed_unicode() {
  JsonDocument document;
  const char* invalid[] = {
    R"({"v":1,"id":1,"cmd":"stop\u0000junk"})",
    R"({"cmd":"\ud800"})", R"({"cmd":"\udc00"})",
    R"({"cmd":"\ud800x"})", R"({"cmd":"\ud800\u0041"})",
    "{\"cmd\":\"raw\nline\"}", "{\"cmd\":\"\xc0\xaf\"}",
    "{\"cmd\":\"\xed\xa0\x80\"}", "{\"cmd\":\"\xf4\x90\x80\x80\"}",
    "{'cmd':'stop'}", "{cmd:\"stop\"}",
    R"({"id":+1})", R"({"id":01})", R"({"id":1.})",
    R"({"id":.1})", R"({"id":1e})", R"({"id":1,"id":})"
  };
  for (const char* input : invalid)
    TEST_ASSERT_NOT_NULL_MESSAGE(decodeObject(input, std::strlen(input), document), input);
}

void test_json_accepts_unicode_escapes_and_exact_frame_limits() {
  JsonDocument document;
  const char* valid[] = {
    R"({"text":"\ud83d\ude80 \u00e9 \n \t \\u0000","number":-1.25e+2,"ok":true,"none":null})",
    "{\"text\":\"\xc3\xa9 \xf0\x9f\x9a\x80\"}",
    R"({"x":[[[[[[[1]]]]]]]})"
  };
  for (const char* input : valid)
    TEST_ASSERT_NULL_MESSAGE(decodeObject(input, std::strlen(input), document), input);
  std::string frame = "{}";
  frame.resize(kMaxLineBytes, ' ');
  TEST_ASSERT_NULL(decodeObject(frame.data(), frame.size(), document));
  frame.push_back(' ');
  TEST_ASSERT_NOT_NULL(decodeObject(frame.data(), frame.size(), document));
  const char* tooDeep = R"({"x":[[[[[[[[1]]]]]]]]})";
  TEST_ASSERT_NOT_NULL(decodeObject(tooDeep, std::strlen(tooDeep), document));
}

BoardConfig mockedPhysicalProfile() {
  // Test fixture only, never a production pin map.
  BoardConfig config;
  config.verifiedBoardConfig = true;
  config.safeProfileVerified = true;
  config.pressureLimitPsi = 20;
  config.gp8403InterfaceVerified = true;
  config.relayKind = RelayKind::DirectGpio;
  config.valvePins = {{13, 14, 16, 17, 18, 19, 23}};
  config.pumpContactPin = 4;
  config.i2cSdaPin = 21;
  config.i2cSclPin = 22;
  config.pressure.source = AnalogSource::Ads1115;
  config.pressure.adsChannel = 0;
  config.pressure.calibrationVerified = true;
  return config;
}

void test_dry_run_never_accesses_gpio_or_i2c() {
  fake::resetGpio();
  Wire.reset();
  Hardware hardware(BoardConfig{}, true);
  TEST_ASSERT_TRUE(hardware.begin());
  Outputs outputs;
  outputs.valves[0] = true;
  outputs.pumpPercent = 100;
  TEST_ASSERT_TRUE(hardware.apply(outputs));
  hardware.sample(1000);
  hardware.safeStop();
  TEST_ASSERT_EQUAL(0, fake::gpioCalls);
  TEST_ASSERT_EQUAL(0, Wire.beginCount);
  TEST_ASSERT_EQUAL(0, Wire.transactionCount);
}

void test_unverified_physical_profile_never_accesses_gpio_or_i2c() {
  fake::resetGpio();
  Wire.reset();
  Hardware hardware(BoardConfig{}, false);
  TEST_ASSERT_FALSE(hardware.begin());
  hardware.safeStop();
  TEST_ASSERT_EQUAL(0, fake::gpioCalls);
  TEST_ASSERT_EQUAL(0, Wire.beginCount);
  TEST_ASSERT_EQUAL(0, Wire.transactionCount);
}

void test_dac_failure_restores_valves_after_first_actuation_attempt() {
  fake::resetGpio();
  Wire.reset();
  const BoardConfig config = mockedPhysicalProfile();
  Hardware hardware(config, false);
  TEST_ASSERT_TRUE(hardware.begin());
  Outputs outputs;
  outputs.valves[0] = true;
  outputs.pumpPercent = 30;
  Wire.failNext = true;
  TEST_ASSERT_FALSE(hardware.apply(outputs));
  TEST_ASSERT_FALSE(hardware.ready());
  TEST_ASSERT_EQUAL(LOW, fake::levels[config.pumpContactPin]);
  for (int pin : config.valvePins) TEST_ASSERT_EQUAL(LOW, fake::levels[pin]);
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_sequence_repeats_and_stops);
  RUN_TEST(test_invalid_recipe_is_atomic);
  RUN_TEST(test_active_recipe_replacement_and_manual_rejected);
  RUN_TEST(test_timeout_latches_and_stop_does_not_clear);
  RUN_TEST(test_timer_wraparound);
  RUN_TEST(test_physical_commissioning_and_pressure_guards);
  RUN_TEST(test_physical_stale_sensor_and_recipe_approval);
  RUN_TEST(test_config_rejects_unverified_defaults_and_conflicts);
  RUN_TEST(test_shift_polarity_and_untouched_channels);
  RUN_TEST(test_calibration_and_input_rail_rejection);
  RUN_TEST(test_json_wrong_types_and_trailing_data_rejected);
  RUN_TEST(test_recipe_json_validation_is_atomic);
  RUN_TEST(test_protocol_envelope_rejects_boolean_versions_and_ids);
  RUN_TEST(test_json_rejects_embedded_nul_and_malformed_unicode);
  RUN_TEST(test_json_accepts_unicode_escapes_and_exact_frame_limits);
  RUN_TEST(test_dry_run_never_accesses_gpio_or_i2c);
  RUN_TEST(test_unverified_physical_profile_never_accesses_gpio_or_i2c);
  RUN_TEST(test_dac_failure_restores_valves_after_first_actuation_attempt);
  return UNITY_END();
}
