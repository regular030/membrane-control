#include <Arduino.h>
#include <ArduinoJson.h>
#include <esp_system.h>
#include "BoardProfile.h"
#include "Hardware.h"
#include "JsonRecipe.h"

#ifndef BASU_DRY_RUN
#define BASU_DRY_RUN 1
#endif
static_assert(BASU_DRY_RUN == 0 || BASU_DRY_RUN == 1, "BASU_DRY_RUN must be 0 or 1");

#ifdef BASU_BLUETOOTH_DRY_RUN
static_assert(BASU_DRY_RUN == 1, "Bluetooth is only available for simulated operation");
#include <BluetoothSerial.h>
#include <atomic>
#include <esp_gap_bt_api.h>
#include <freertos/queue.h>
#endif
#ifdef BASU_BLUETOOTH_PHYSICAL
#ifdef BASU_BLUETOOTH_DRY_RUN
#error Physical and simulated Bluetooth transports are mutually exclusive
#endif
static_assert(BASU_DRY_RUN == 0, "Protected Bluetooth requires physical mode");
#include <cstring>
#include <esp_attr.h>
#include "ProtectedSpp.h"
#endif

namespace {
constexpr bool kSimulation = BASU_DRY_RUN != 0;
#ifdef BASU_VERIFIED_PROFILE_HEADER
constexpr bool kFactoryProfile = false;
#else
constexpr bool kFactoryProfile = true;
#endif
const basu::BoardConfig board = basu::compiledBoardConfig();
basu::SafetyConfig makeSafety() {
  basu::SafetyConfig safety;
  safety.simulation = kSimulation;
  safety.safeProfileVerified = board.safeProfileVerified;
  safety.pressureLimitPsi = board.pressureLimitPsi;
  safety.safeValves = board.safeValves;
  safety.valve6Absent = !kSimulation && basu::hasAbsentValve6(board);
  safety.sensorMaxAgeMs = board.sensorMaxAgeMs;
  safety.pumpLimits = board.pumpLimits;
  safety.pressureStartupMs = board.pressureStartupMs;
  return safety;
}
basu::Controller controller(makeSafety());
basu::Hardware hardware(board, kSimulation);
char line[basu::kMaxLineBytes + 1];
std::size_t lineLength = 0;
bool discardingOversize = false;
uint32_t lastTelemetryMs = 0;
uint32_t lastSimulationSampleMs = 0;
uint32_t lastManualValvesReceiptId = 0;

#ifdef BASU_BLUETOOTH_DRY_RUN
BluetoothSerial bluetooth;
QueueHandle_t bluetoothInput = nullptr;
uint32_t bluetoothClient = 0;  // Accessed only by the SPP callback task.
// Odd generations have a client. Open, close and receive overflow invalidate
// partial input and simulated state before the next command is handled.
std::atomic<uint32_t> bluetoothGeneration{0};
uint32_t currentBluetoothGeneration = 0;
bool bluetoothHello = false;

void bluetoothEvent(esp_spp_cb_event_t event, esp_spp_cb_param_t* data) {
  if (event == ESP_SPP_SRV_OPEN_EVT && data->srv_open.status == ESP_SPP_SUCCESS && !bluetoothClient) {
    xQueueReset(bluetoothInput);
    bluetoothClient = data->srv_open.handle;
    bluetoothGeneration.fetch_add(1);
  } else if (event == ESP_SPP_CLOSE_EVT && data->close.handle == bluetoothClient) {
    bluetoothGeneration.fetch_add(1);
    bluetoothClient = 0;
    xQueueReset(bluetoothInput);
  } else if (event == ESP_SPP_DATA_IND_EVT && bluetoothClient && data->data_ind.handle == bluetoothClient) {
    for (std::size_t index = 0; index < data->data_ind.len; ++index) {
      if (xQueueSend(bluetoothInput, data->data_ind.data + index, 0) != pdTRUE) {
        bluetoothGeneration.fetch_add(2);
        xQueueReset(bluetoothInput);
        break;
      }
    }
  }
}

bool bluetoothSessionCurrent() {
  return (currentBluetoothGeneration & 1U) && currentBluetoothGeneration == bluetoothGeneration.load();
}

void reportBenchBondCount() {
  Serial.printf("Bluetooth bench saved bonds: %d\r\n", esp_bt_gap_get_bond_device_num());
}
#endif

#ifdef BASU_BLUETOOTH_PHYSICAL
basu::BluetoothLinkToken physicalBluetoothToken;
basu::BluetoothCommandLease physicalBluetoothLease;
constexpr uint32_t kPairingBootMarker = 0x42545052;
constexpr uint32_t kPairingTimeoutMs = 120000;
RTC_NOINIT_ATTR uint32_t pairingBootMarker;
RTC_NOINIT_ATTR uint32_t pairingBootCheck;
bool pairingOnlyBoot = false;
uint32_t pairingStartedMs = 0;

bool physicalBluetoothCurrent() {
  return physicalBluetoothToken.handle && physicalBluetoothToken == basu::protectedSpp::current();
}

void stopBluetoothSession() {
  physicalBluetoothLease.reset();
  lastManualValvesReceiptId = 0;
  controller.endControlSession();
  hardware.safeStop();
}

void syncBluetoothSession() {
  const auto token = basu::protectedSpp::current();
  if (token == physicalBluetoothToken) return;
  physicalBluetoothToken = token;
  lineLength = 0;
  discardingOversize = false;
  stopBluetoothSession();
}

void restartAfterPairingMessage(const char* message) {
  Serial.println(message);
  Serial.flush();
  ESP.restart();
}

void handleUsbPairingLine(const char* command, std::size_t length) {
  if (length == 4 && std::memcmp(command, "PAIR", 4) == 0 && !pairingOnlyBoot) {
    if (controller.state() != basu::State::Idle && controller.state() != basu::State::Fault) {
      Serial.println("Bluetooth: stop the controller before USB pairing");
      return;
    }
    hardware.safeStop();
    if (!basu::protectedSpp::requestPairing()) {
      Serial.println("Bluetooth: could not store the USB pairing request");
      return;
    }
    pairingBootMarker = kPairingBootMarker;
    pairingBootCheck = ~kPairingBootMarker;
    restartAfterPairingMessage("Bluetooth: pairing command accepted; restarting in pairing mode");
  }
  if (!pairingOnlyBoot || length != 14 || std::memcmp(command, "CONFIRM ", 8) != 0) return;
  uint32_t code = 0;
  for (std::size_t index = 8; index < length; ++index) {
    if (command[index] < '0' || command[index] > '9') return;
    code = code * 10 + (command[index] - '0');
  }
  Serial.println(basu::protectedSpp::confirmPairing(code)
      ? "Bluetooth: pairing confirmation accepted" : "Bluetooth: pairing confirmation rejected");
}

void readUsbPairingCommands() {
  // Only a complete, bounded line from the wired console can enroll a PC.
  // Discard oversized lines through the newline, including any command suffix.
  static char command[16];
  static std::size_t length = 0;
  static bool discarding = false;
  for (unsigned count = 0; count < 64 && Serial.available(); ++count) {
    const char byte = static_cast<char>(Serial.read());
    if (byte == '\n') {
      if (!discarding) {
        if (length && command[length - 1] == '\r') --length;
        handleUsbPairingLine(command, length);
      }
      length = 0;
      discarding = false;
    } else if (!discarding) {
      if (length < sizeof(command)) command[length++] = byte;
      else discarding = true;
    }
  }
}

void serviceUsbPairing() {
  if (static_cast<uint32_t>(millis() - pairingStartedMs) >= kPairingTimeoutMs)
    restartAfterPairingMessage("Bluetooth: pairing timed out; physical control locked");
  uint32_t code;
  if (basu::protectedSpp::takePairingCode(code))
    Serial.printf("Bluetooth pairing code: %06lu\n", static_cast<unsigned long>(code));
  using basu::protectedSpp::PairingStatus;
  switch (basu::protectedSpp::pairingStatus()) {
    case PairingStatus::Waiting:
      break;
    case PairingStatus::Ready:
      if (basu::protectedSpp::savePairing()) {
        // Leave Windows time to finish service discovery before restarting.
        delay(2000);
        restartAfterPairingMessage("Bluetooth: pairing saved; restarting normal mode");
      }
      restartAfterPairingMessage("Bluetooth: pairing failed; physical control locked");
      break;
    case PairingStatus::Failed:
      restartAfterPairingMessage("Bluetooth: pairing failed; physical control locked");
      break;
  }
}
#endif

void writeDocument(const JsonDocument& document, bool telemetry = false) {
#ifdef BASU_BLUETOOTH_PHYSICAL
  if (!physicalBluetoothCurrent()) return;
#elif defined(BASU_BLUETOOTH_DRY_RUN)
  if (!bluetoothSessionCurrent()) return;
#endif
  // Only the controller loop serializes frames. Keep this buffer off its
  // stack and write the complete bounded frame to either transport at once.
  static char frame[1024];
  if (measureJson(document) >= sizeof(frame)) return;
  const std::size_t length = serializeJson(document, frame, sizeof(frame));
  frame[length] = '\n';
#ifdef BASU_BLUETOOTH_PHYSICAL
  static_assert(sizeof(frame) == basu::protectedSpp::kFrameBytes);
  basu::protectedSpp::send(physicalBluetoothToken, frame, length + 1, telemetry);
#elif defined(BASU_BLUETOOTH_DRY_RUN)
  bluetooth.write(reinterpret_cast<const uint8_t*>(frame), length + 1);
#else
  Serial.write(reinterpret_cast<const uint8_t*>(frame), length + 1);
#endif
}

const char* resetReasonName(esp_reset_reason_t reason) {
  switch (reason) {
    case ESP_RST_POWERON: return "power_on";
    case ESP_RST_EXT: return "external";
    case ESP_RST_SW: return "software";
    case ESP_RST_PANIC: return "panic";
    case ESP_RST_INT_WDT:
    case ESP_RST_TASK_WDT:
    case ESP_RST_WDT: return "watchdog";
    case ESP_RST_DEEPSLEEP: return "deep_sleep";
    case ESP_RST_BROWNOUT: return "brownout";
    case ESP_RST_SDIO: return "sdio";
    default: return "unknown";
  }
}

void addAdcPinMillivolts(JsonDocument& document, const basu::SensorTestMillivolts& reading) {
  JsonObject values = document["adc_pin_mv"].to<JsonObject>();
  values["pressure"] = reading.pressure;
  values["flow"] = reading.flow;
  values["pump_feedback"] = reading.pumpFeedback;
}

void reply(uint32_t id, const char* error = nullptr, bool hello = false,
           const basu::SensorTestMillivolts* sensorTest = nullptr) {
  JsonDocument document;
  document["v"] = 1;
  document["id"] = id;
  document["type"] = error ? "error" : (hello ? "hello" : "ack");
  document["ok"] = error == nullptr;
  if (error) document["error"] = error;
  if (sensorTest && !error) addAdcPinMillivolts(document, *sensorTest);
  if (hello && !error) {
    document["device"] = "basu-membrane-control";
    document["firmware_version"] = "0.1.28";
    document["reset_reason"] = resetReasonName(esp_reset_reason());
    document["sensor_test_available"] = hardware.sensorTestAvailable(kFactoryProfile);
    document["valve_control_ready"] = hardware.valveControlReady();
    document["manual_valve_count"] = basu::kManualValveCount;
    JsonArray ids = document["manual_valve_ids"].to<JsonArray>();
    for (int id : basu::kManualValveIds) ids.add(id);
    JsonArray bits = document["valve_bits"].to<JsonArray>();
    for (int bit : hardware.manualValveBits()) bits.add(bit);
    document["pump_command_source"] = basu::pumpCommandSourceName(board.pumpCommandSource);
    document["controller_mode"] = kSimulation ? "dry_run" : "physical";
#ifdef BASU_BLUETOOTH_PHYSICAL
    document["transport"] = "bluetooth_spp";
#endif
    if (kSimulation || hardware.ready()) document["hardware_status"] = nullptr;
    else document["hardware_status"] = std::string(hardware.error()).substr(0, 160);
    JsonObject sensorInputs = document["sensor_inputs"].to<JsonObject>();
    const char* names[] = {"pressure", "flow", "pump_feedback"};
    const basu::AnalogConfig* configured[] = {&board.pressure, &board.flow, &board.pumpFeedback};
    for (std::size_t index = 0; index < 3; ++index) {
      JsonObject input = sensorInputs[names[index]].to<JsonObject>();
      input["source"] = basu::analogSourceName(configured[index]->source);
      input["calibration_verified"] = configured[index]->calibrationVerified;
      if (basu::usesNativeAdc(configured[index]->source)) input["pin"] = configured[index]->pin;
      else if (configured[index]->source == basu::AnalogSource::Ads1115) input["channel"] = configured[index]->adsChannel;
    }
    document["protocol_version"] = 1;
    document["valve_count"] = basu::kValveCount;
    document["hardware_verified"] = controller.hardwareVerified();
    if (const auto* profile = controller.manualPumpProfile(); profile && hardware.ready()) {
      JsonObject manualPump = document["manual_pump_profile"].to<JsonObject>();
      manualPump["max_percent"] = profile->maxPercent;
      if (const auto startupMs = controller.manualPressureStartupMs()) manualPump["pressure_startup_ms"] = startupMs;
      JsonArray valves = manualPump["valves"].to<JsonArray>();
      for (bool valve : *profile->requiredValves) valves.add(valve);
    }
    document["simulation"] = kSimulation;
  }
  writeDocument(document);
}

void handleLine(uint32_t now) {
#ifdef BASU_BLUETOOTH_PHYSICAL
  if (!physicalBluetoothCurrent()) return;
#endif
  now = millis();
  controller.tick(now);
  if (controller.state() == basu::State::Fault) hardware.safeStop();
  JsonDocument request;
  if (const char* decodeError = basu::decodeObject(line, lineLength, request)) { reply(0, decodeError); return; }
  uint32_t id = 0;
  std::string command;
  if (const char* envelopeError = basu::parseEnvelope(request.as<JsonVariantConst>(), id, command)) {
    reply(id, envelopeError); return;
  }
#ifdef BASU_BLUETOOTH_PHYSICAL
  if (!physicalBluetoothCurrent()) return;
  const bool actuates = command == "start" || command == "manual" || command == "manual_valves";
  if (command == "hello") {
    stopBluetoothSession();
    physicalBluetoothLease.hello();
  } else if (command != "stop" && !physicalBluetoothLease.identified()) {
    reply(id, "hello required"); return;
  } else if (actuates && !physicalBluetoothLease.mayActuate(now)) {
    reply(id, "fresh Bluetooth heartbeat required"); return;
  } else if (command == "heartbeat") {
    physicalBluetoothLease.heartbeat(now);
  }
#endif
  const char* error = nullptr;
  if (command == "hello") {
#ifdef BASU_BLUETOOTH_DRY_RUN
    bluetoothHello = true;
#endif
    lastManualValvesReceiptId = 0;
    if (controller.state() == basu::State::ManualValves) { controller.onHello(); hardware.safeStop(); }
    reply(id, nullptr, true); return;
  }
#ifdef BASU_BLUETOOTH_DRY_RUN
  if (!bluetoothHello && command != "stop") { reply(id, "hello required"); return; }
#endif
  if (command == "heartbeat") controller.heartbeat(now);
  else if (command == "stop") {
    lastManualValvesReceiptId = 0;
    controller.stop();
    hardware.safeStop();
  } else if (command == "clear_fault") error = controller.clearFault();
  else if (command == "load_recipe") {
    basu::Recipe candidate;
    error = basu::parseRecipe(request["recipe"], candidate);
    if (!error) error = controller.load(candidate);
  } else if (command == "start") error = controller.start(now);
  else if (command == "manual") {
    basu::Outputs candidate;
    error = basu::parseOutputs(request["valves"], request["pump_percent"], candidate);
    const auto startup = request["allow_pressure_startup"];
    if (!error && !startup.isUnbound() && !startup.is<bool>())
      error = "allow_pressure_startup must be a boolean";
    if (!error) error = controller.manual(candidate, now, startup.as<bool>());
  } else if (command == "manual_valves") {
    basu::Outputs candidate;
    error = basu::parseManualValves(request.as<JsonVariantConst>(), candidate);
    if (!error) error = controller.manualValves(candidate.valves, now);
  } else if (command == "read_sensor_inputs") {
    basu::SensorTestMillivolts result;
    error = hardware.readSensorTestInputs(kFactoryProfile, controller.state(), result);
    reply(id, error, false, error ? nullptr : &result);
    return;
  } else error = "unknown command";
#ifdef BASU_BLUETOOTH_PHYSICAL
  if (!physicalBluetoothCurrent()) return;
#endif
  // Apply before acknowledging an actuator command. Failure is a latched fault.
  // A serial batch can take time: do not backdate a newly written PWM command's
  // settling interval to the loop timestamp captured before reading the batch.
  if (!error && (command == "start" || command == "manual") && !hardware.apply(controller.outputs(), millis(), false)) {
    controller.latchFault(hardware.error());
    hardware.safeStop();
    error = hardware.error();
  }
  if (!error && command == "manual_valves") {
    if (hardware.applyManualValves(controller.outputs().valves)) {
      lastManualValvesReceiptId = id;
    } else {
      controller.latchFault(hardware.valveError());
      hardware.safeStop();
      error = hardware.valveError();
    }
  }
  reply(id, error);
}

void readSerial(uint32_t now) {
  // Bounded work per loop prevents a continuous malformed stream starving safety.
  unsigned int budget = 512;
#ifdef BASU_BLUETOOTH_PHYSICAL
  uint8_t byte = 0;
  while (budget-- && basu::protectedSpp::read(physicalBluetoothToken, byte)) {
    const char ch = static_cast<char>(byte);
#elif defined(BASU_BLUETOOTH_DRY_RUN)
  const uint32_t generation = bluetoothGeneration.load();
  if (generation != currentBluetoothGeneration) {
    currentBluetoothGeneration = generation;
    bluetoothHello = false;
    lineLength = 0;
    discardingOversize = false;
    lastManualValvesReceiptId = 0;
    controller = basu::Controller(makeSafety());
    controller.setValveControlReady(hardware.valveControlReady());
  }
  uint8_t byte = 0;
  while (budget-- && bluetoothSessionCurrent() && xQueueReceive(bluetoothInput, &byte, 0) == pdTRUE) {
    if (!bluetoothSessionCurrent()) break;
    const char ch = static_cast<char>(byte);
#else
  while (budget-- && Serial.available()) {
    const char ch = static_cast<char>(Serial.read());
#endif
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
    // Optional already-configured inputs may update, but valve-only operation
    // neither requires them nor probes the stopped pump DAC for health.
    hardware.sample(now, controller.state() == basu::State::ManualValves);
    controller.setHardwareReady(hardware.ready());
    controller.setMeasurements(hardware.measurements());
    if (!hardware.ready() && controller.active() && controller.state() != basu::State::ManualValves) {
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
#ifdef BASU_BLUETOOTH_PHYSICAL
  if (!physicalBluetoothLease.identified() || !physicalBluetoothCurrent()) return;
#elif defined(BASU_BLUETOOTH_DRY_RUN)
  if (!bluetoothHello || !bluetoothSessionCurrent()) return;
#endif
  JsonDocument document;
  document["v"] = 1;
  document["type"] = "telemetry";
  document["uptime_ms"] = now;
  document["state"] = basu::stateName(controller.state());
  if (controller.state() == basu::State::ManualValves && lastManualValvesReceiptId != 0)
    document["manual_valves_receipt_id"] = lastManualValvesReceiptId;
  document["valve_control_ready"] = hardware.valveControlReady();
  document["step_index"] = controller.stepIndex();
  document["cycle"] = controller.cycle();
  document["remaining_s"] = controller.remainingSeconds(now);
  JsonArray valves = document["valves"].to<JsonArray>();
  for (bool state : controller.outputs().valves) valves.add(state);
  document["pump_percent"] = controller.outputs().pumpPercent;
  if (hardware.pumpContactCommandAvailable())
    document["pump_run_contact_commanded"] = hardware.pumpRunContactCommanded();
  if (const char* status = hardware.pumpTachStatus(now)) {
    document["pump_tach_status"] = status;
    double rpm;
    if (hardware.readPumpRpm(now, rpm)) document["pump_rpm"] = rpm;
  }
  auto addReading = [&](const char* name, const basu::Reading& reading) {
    if (reading.fresh(now, controller.sensorMaxAgeMs())) document[name] = reading.value;
    else document[name] = nullptr;
  };
  addReading("pressure_psi", controller.measurements().pressure);
  if (const char* startup = controller.manualPressureStartupStatus(now)) document["pressure_startup"] = startup;
  if (controller.manualPressureStartupMs() || hardware.pressureMonitoringOnly()) {
    if (const auto millivolts = hardware.pressureAdcMillivolts(now)) document["pressure_adc_mv"] = *millivolts;
  }
  addReading("flow_ml_min", controller.measurements().flow);
  addReading("pump_feedback_v", controller.measurements().pumpFeedback);
  basu::SensorTestMillivolts rawInputs;
  if (!hardware.readSensorTestInputs(kFactoryProfile, controller.state(), rawInputs,
                                    basu::SensorTestScope::IdleOrManualValves))
    addAdcPinMillivolts(document, rawInputs);
  JsonObject sensorStatus = document["sensor_status"].to<JsonObject>();
  sensorStatus["pressure"] = hardware.sensorStatus(0, now);
  sensorStatus["flow"] = hardware.sensorStatus(1, now);
  sensorStatus["pump_feedback"] = hardware.sensorStatus(2, now);
  if (controller.fault().empty()) document["fault"] = nullptr;
  else document["fault"] = controller.fault();
  document["hardware_verified"] = controller.hardwareVerified();
  document["simulation"] = kSimulation;
  writeDocument(document, true);
}
}  // namespace

void setup() {
  Serial.begin(115200);
#ifdef BASU_BLUETOOTH_PHYSICAL
  pairingOnlyBoot = esp_reset_reason() == ESP_RST_SW &&
      pairingBootMarker == kPairingBootMarker && pairingBootCheck == ~kPairingBootMarker;
  pairingBootMarker = pairingBootCheck = 0;
#endif
  const bool initialized = hardware.begin();
  controller.setHardwareReady(initialized && !kSimulation);
#ifdef BASU_BLUETOOTH_PHYSICAL
  // A working full profile has already applied its configured safe outputs.
  // The manual relay fallback is only needed during pairing on a factory rig.
  if (!pairingOnlyBoot || !initialized)
#endif
    hardware.beginManualValves(basu::confirmedRigManualValves());
  controller.setValveControlReady(hardware.valveControlReady());
  // Pump/sensor setup remains separate from the confirmed six-valve capability.
  if (!initialized && board.verifiedBoardConfig && !hardware.pressureMonitoringOnly()) controller.latchFault(hardware.error());
#ifdef BASU_BLUETOOTH_DRY_RUN
  bluetoothInput = xQueueCreate(basu::kMaxLineBytes + 1, sizeof(uint8_t));
  if (bluetoothInput == nullptr) {
    Serial.println("Bluetooth dry run: could not allocate receive queue");
    return;
  }
  // Consume data in the event callback so the default untagged 512-byte queue
  // cannot mix input from different connection handles.
  bluetooth.onData([](const uint8_t*, std::size_t) {});
  bluetooth.onAuthComplete([](bool success) {
    if (success) reportBenchBondCount();
    else Serial.println("Bluetooth bench pairing failed");
  });
  bluetooth.register_callback(bluetoothEvent);
  if (!bluetooth.begin("MembraneControl-Bench")) Serial.println("Bluetooth dry run: failed to start");
  else reportBenchBondCount();
#endif
#ifdef BASU_BLUETOOTH_PHYSICAL
  if (pairingOnlyBoot) hardware.safeStop();
  if (const char* error = basu::protectedSpp::begin(pairingOnlyBoot)) {
    Serial.println(error);
    if (pairingOnlyBoot) restartAfterPairingMessage("Bluetooth: pairing failed; physical control locked");
  }
  pairingStartedMs = millis();
#endif
}

void loop() {
#ifdef BASU_BLUETOOTH_PHYSICAL
  if (pairingOnlyBoot) {
    serviceUsbPairing();
    readUsbPairingCommands();
    delay(10);
    return;
  }
  syncBluetoothSession();
  readUsbPairingCommands();
#endif
  uint32_t now = millis();
  updateMeasurements(now);
  controller.tick(now);
  if (!kSimulation && controller.state() == basu::State::Fault) hardware.safeStop();
  readSerial(now);
#ifdef BASU_BLUETOOTH_PHYSICAL
  syncBluetoothSession();
#endif
  now = millis();
  controller.tick(now);
  const bool valveOnly = controller.state() == basu::State::ManualValves;
  const bool applied = valveOnly ? hardware.applyManualValves(controller.outputs().valves) :
      (hardware.ready() ? hardware.apply(controller.outputs(), now, true) : true);
  if (applied && hardware.pumpRunContactCommanded()) controller.notePumpRunCommanded(millis());
  if (!applied && controller.active()) {
    controller.setHardwareReady(false);
    controller.latchFault(valveOnly ? hardware.valveError() : hardware.error());
    hardware.safeStop();
  }
  if (static_cast<uint32_t>(now - lastTelemetryMs) >= basu::kTelemetryIntervalMs) {
    lastTelemetryMs = now;
    writeTelemetry(now);
  }
  yield();
}
