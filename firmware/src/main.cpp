#include <Arduino.h>
#include <ArduinoJson.h>
#include "BoardProfile.h"
#include "Hardware.h"
#include "JsonRecipe.h"

#ifndef BASU_DRY_RUN
#define BASU_DRY_RUN 1
#endif
static_assert(BASU_DRY_RUN == 0 || BASU_DRY_RUN == 1, "BASU_DRY_RUN must be 0 or 1");

namespace {
constexpr bool kSimulation = BASU_DRY_RUN != 0;
const basu::BoardConfig board = basu::compiledBoardConfig();
basu::SafetyConfig makeSafety() {
  basu::SafetyConfig safety;
  safety.simulation = kSimulation;
  safety.safeProfileVerified = board.safeProfileVerified;
  safety.pressureLimitPsi = board.pressureLimitPsi;
  safety.safeValves = board.safeValves;
  safety.sensorMaxAgeMs = board.sensorMaxAgeMs;
  return safety;
}
basu::Controller controller(makeSafety());
basu::Hardware hardware(board, kSimulation);
char line[basu::kMaxLineBytes + 1];
std::size_t lineLength = 0;
bool discardingOversize = false;
uint32_t lastTelemetryMs = 0;
uint32_t lastSimulationSampleMs = 0;

void reply(uint32_t id, const char* error = nullptr, bool hello = false) {
  JsonDocument document;
  document["v"] = 1;
  document["id"] = id;
  document["type"] = error ? "error" : (hello ? "hello" : "ack");
  document["ok"] = error == nullptr;
  if (error) document["error"] = error;
  if (hello && !error) {
    document["device"] = "basu-membrane-control";
    document["firmware_version"] = "0.1.0";
    document["protocol_version"] = 1;
    document["valve_count"] = basu::kValveCount;
    document["hardware_verified"] = controller.hardwareVerified();
    document["simulation"] = kSimulation;
  }
  serializeJson(document, Serial);
  Serial.write('\n');
}

void handleLine(uint32_t now) {
  JsonDocument request;
  if (const char* decodeError = basu::decodeObject(line, lineLength, request)) { reply(0, decodeError); return; }
  uint32_t id = 0;
  std::string command;
  if (const char* envelopeError = basu::parseEnvelope(request.as<JsonVariantConst>(), id, command)) {
    reply(id, envelopeError); return;
  }
  const char* error = nullptr;
  if (command == "hello") { reply(id, nullptr, true); return; }
  if (command == "heartbeat") controller.heartbeat(now);
  else if (command == "stop") { controller.stop(); hardware.safeStop(); }
  else if (command == "clear_fault") error = controller.clearFault();
  else if (command == "load_recipe") {
    basu::Recipe candidate;
    error = basu::parseRecipe(request["recipe"], candidate);
    if (!error) error = controller.load(candidate);
  } else if (command == "start") error = controller.start(now);
  else if (command == "manual") {
    basu::Outputs candidate;
    error = basu::parseOutputs(request["valves"], request["pump_percent"], candidate);
    if (!error) error = controller.manual(candidate, now);
  } else error = "unknown command";
  // Apply before acknowledging an actuator command. Failure is a latched fault.
  if (!error && (command == "start" || command == "manual") && !hardware.apply(controller.outputs())) {
    controller.latchFault(hardware.error());
    hardware.safeStop();
    error = hardware.error();
  }
  reply(id, error);
}

void readSerial(uint32_t now) {
  // Bounded work per loop prevents a continuous malformed stream starving safety.
  unsigned int budget = 512;
  while (budget-- && Serial.available()) {
    const char ch = static_cast<char>(Serial.read());
    if (ch == '\n') {
      if (discardingOversize) reply(0, "line exceeds 8192 bytes");
      else if (lineLength > 0) { line[lineLength] = '\0'; handleLine(now); }
      lineLength = 0;
      discardingOversize = false;
    } else if (!discardingOversize) {
      if (lineLength == basu::kMaxLineBytes) { discardingOversize = true; lineLength = 0; }
      else line[lineLength++] = ch;
    }
  }
}

void updateMeasurements(uint32_t now) {
  if (!kSimulation) {
    hardware.sample(now);
    controller.setHardwareReady(hardware.ready());
    controller.setMeasurements(hardware.measurements());
    if (!hardware.ready() && controller.active()) {
      controller.setHardwareReady(false);
      controller.latchFault(hardware.error());
    }
    return;
  }
  if (static_cast<uint32_t>(now - lastSimulationSampleMs) < 100) return;
  lastSimulationSampleMs = now;
  const double pump = controller.outputs().pumpPercent;
  basu::Measurements simulated;
  simulated.pressure = {pump * 0.15, true, now};
  simulated.flow = {pump * 1.0, true, now};
  simulated.pumpFeedback = {pump * 0.1, true, now};
  controller.setMeasurements(simulated);
}

void writeTelemetry(uint32_t now) {
  JsonDocument document;
  document["v"] = 1;
  document["type"] = "telemetry";
  document["uptime_ms"] = now;
  document["state"] = basu::stateName(controller.state());
  document["step_index"] = controller.stepIndex();
  document["cycle"] = controller.cycle();
  document["remaining_s"] = controller.remainingSeconds(now);
  JsonArray valves = document["valves"].to<JsonArray>();
  for (bool state : controller.outputs().valves) valves.add(state);
  document["pump_percent"] = controller.outputs().pumpPercent;
  auto addReading = [&](const char* name, const basu::Reading& reading) {
    if (reading.fresh(now, controller.sensorMaxAgeMs())) document[name] = reading.value;
    else document[name] = nullptr;
  };
  addReading("pressure_psi", controller.measurements().pressure);
  addReading("flow_ml_min", controller.measurements().flow);
  addReading("pump_feedback_v", controller.measurements().pumpFeedback);
  if (controller.fault().empty()) document["fault"] = nullptr;
  else document["fault"] = controller.fault();
  document["hardware_verified"] = controller.hardwareVerified();
  document["simulation"] = kSimulation;
  serializeJson(document, Serial);
  Serial.write('\n');
}
}  // namespace

void setup() {
  Serial.begin(115200);
  const bool initialized = hardware.begin();
  controller.setHardwareReady(initialized && !kSimulation);
  // Unverified physical builds remain idle and refuse actuation; no GPIO was used.
  if (!initialized && board.verifiedBoardConfig) controller.latchFault(hardware.error());
}

void loop() {
  uint32_t now = millis();
  updateMeasurements(now);
  controller.tick(now);
  if (!kSimulation && controller.state() == basu::State::Fault) hardware.safeStop();
  readSerial(now);
  now = millis();
  controller.tick(now);
  if (!hardware.apply(controller.outputs()) && controller.active()) {
    controller.setHardwareReady(false);
    controller.latchFault(hardware.error());
    hardware.safeStop();
  }
  if (static_cast<uint32_t>(now - lastTelemetryMs) >= basu::kTelemetryIntervalMs) {
    lastTelemetryMs = now;
    writeTelemetry(now);
  }
  yield();
}
