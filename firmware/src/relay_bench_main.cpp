#include <Arduino.h>
#include <ArduinoJson.h>
#include "RelayBenchHardware.h"

namespace {
basu::RelayBenchHardware hardware;
basu::RelayBenchCore bench(hardware);
char line[basu::kMaxLineBytes + 1];
std::size_t lineLength = 0;
bool discardingOversize = false;
uint32_t lastStatusMs = 0;

void writeStatus(uint32_t now) {
  JsonDocument document;
  document["v"] = 1;
  document["type"] = "bench_status";
  document["uptime_ms"] = now;
  document["state"] = basu::relayBenchStateName(bench.state());
  // These are commanded GPIO/register states. There is no physical feedback.
  document["outputs_enabled"] = bench.outputsEnabled();
  document["baseline_confirmed"] = bench.baselineConfirmed();
  document["baseline_word"] = bench.baselineWord();
  document["probe_completed"] = bench.probeCompleted();
  document["probe_id"] = bench.probeId();
  if (bench.pulseBit() < 0) document["pulse_bit"] = nullptr;
  else document["pulse_bit"] = bench.pulseBit();
  document["remaining_ms"] = bench.remainingMs(now);
  document["hardware_verified"] = false;
  document["simulation"] = false;
  document["pressure_psi"] = nullptr;
  document["flow_ml_min"] = nullptr;
  document["pump_feedback_v"] = nullptr;
  if (bench.fault().empty()) document["fault"] = nullptr;
  else document["fault"] = bench.fault();
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
    document["device"] = "membrane-relay-bench";
    document["protocol_version"] = 1;
    document["firmware_version"] = "0.1.8";
    document["relay_count"] = 16;
    document["simulation"] = false;
    document["hardware_verified"] = false;
  }
  serializeJson(document, Serial);
  Serial.write('\n');
}

void handleLine() {
  bench.tick(millis());
  JsonDocument request;
  if (const char* error = basu::decodeObject(line, lineLength, request)) {
    reply(0, error);
    return;
  }
  const auto result = basu::handleRelayBenchRequest(bench, request.as<JsonVariantConst>(), millis());
  bench.tick(millis());
  reply(result.id, result.error, result.hello);
  writeStatus(millis());
}

void readSerial() {
  // Bound input work and check deadlines between frames. Invalid input cannot
  // refresh the heartbeat or postpone the fixed probe/pulse expiry.
  unsigned budget = 512;
  while (budget-- && Serial.available()) {
    const char ch = static_cast<char>(Serial.read());
    if (ch == '\n') {
      bench.tick(millis());
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
  hardware.begin();  // OE disable is the first GPIO operation, before UART setup.
  Serial.begin(115200);
}

void loop() {
  bench.tick(millis());
  readSerial();
  const uint32_t now = millis();
  bench.tick(now);
  if (static_cast<uint32_t>(now - lastStatusMs) >= 250) writeStatus(now);
  yield();
}
