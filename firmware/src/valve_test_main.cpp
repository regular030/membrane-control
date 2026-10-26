#include <Arduino.h>
#include <ArduinoJson.h>
#include "ValveTestHardware.h"
#include "ValveTestProfile.h"

namespace {
basu::ValveTestHardware hardware;
basu::ValveTestCore core(basu::compiledValveTestConfig(), hardware);
char line[basu::kMaxLineBytes + 1];
std::size_t lineLength = 0;
bool discardingOversize = false;
uint32_t lastStatusMs = 0;

void writeStatus(uint32_t now) {
  JsonDocument document;
  document["v"] = 1;
  document["type"] = "valve_test_status";
  document["uptime_ms"] = now;
  document["state"] = basu::valveTestStateName(core.state());
  document["mode"] = "valve_test";
  document["profile_id"] = core.profileId();
  document["valve_profile_verified"] = core.profileVerified();
  document["outputs_enabled"] = core.outputsEnabled();
  document["active_valve"] = core.activeValve();
  document["remaining_ms"] = core.remainingMs(now);
  document["simulation"] = false;
  document["hardware_verified"] = false;
  document["pressure_psi"] = nullptr;
  document["flow_ml_min"] = nullptr;
  document["pump_feedback_v"] = nullptr;
  if (core.fault().empty()) document["fault"] = nullptr;
  else document["fault"] = core.fault();
  serializeJson(document, Serial);
  Serial.write('\n');
  lastStatusMs = now;
}

void reply(uint32_t id, const char* error = nullptr, bool hello = false) {
  JsonDocument document;
  document["v"] = 1;
  document["id"] = id;
  document["type"] = error ? "error" : hello ? "hello" : "ack";
  document["ok"] = error == nullptr;
  if (error) document["error"] = error;
  else if (hello) {
    document["device"] = "membrane-valve-test";
    document["mode"] = "valve_test";
    document["protocol_version"] = 1;
    document["firmware_version"] = "0.1.12";
    document["valve_count"] = 7;
    document["simulation"] = false;
    document["hardware_verified"] = false;
    document["valve_profile_verified"] = core.profileVerified();
    document["profile_id"] = core.profileId();
  }
  serializeJson(document, Serial);
  Serial.write('\n');
}

void handleLine() {
  core.tick(millis());
  JsonDocument request;
  if (const char* error = basu::decodeObject(line, lineLength, request)) {
    reply(0, error);
    return;
  }
  const auto result = basu::handleValveTestRequest(core, request.as<JsonVariantConst>(), millis());
  core.tick(millis());
  reply(result.id, result.error, result.hello);
  writeStatus(millis());
}

void readSerial() {
  unsigned budget = 512;
  while (budget-- && Serial.available()) {
    const char ch = static_cast<char>(Serial.read());
    if (ch == '\n') {
      core.tick(millis());
      if (discardingOversize) reply(0, "line exceeds 8192 bytes");
      else if (lineLength > 0) {
        line[lineLength] = '\0';
        handleLine();
      }
      lineLength = 0;
      discardingOversize = false;
    } else if (!discardingOversize) {
      if (lineLength == basu::kMaxLineBytes) {
        discardingOversize = true;
        lineLength = 0;
      } else line[lineLength++] = ch;
    }
  }
}
}  // namespace

void setup() {
  core.begin();  // Profile validation precedes every GPIO operation.
  Serial.begin(115200);
}

void loop() {
  core.tick(millis());
  readSerial();
  const uint32_t now = millis();
  core.tick(now);
  if (static_cast<uint32_t>(now - lastStatusMs) >= 250) writeStatus(now);
  yield();
}
