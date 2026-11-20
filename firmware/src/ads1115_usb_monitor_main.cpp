#include <Arduino.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <cstring>

// A separate USB sensor board. Only UART0 and this I2C pair are initialized.
namespace {
constexpr int kSdaPin = 22;
constexpr int kSclPin = 21;
constexpr uint32_t kI2cHz = 25000;
constexpr uint8_t kAddress = 0x48;
constexpr uint32_t kSampleIntervalMs = 200;
constexpr uint32_t kHeartbeatIntervalMs = 1000;
const char* const kChannelNames[] = {"A0", "A1", "A2"};
const char* const kSignalNames[] = {"pressure", "flow", "pump_feedback"};

struct Sample {
  bool valid = false;
  int16_t raw = 0;
  uint32_t sampledMs = 0;
  const char* status = "waiting";
};
Sample samples[3];
bool busReady = false;
bool adcAck = false;
uint32_t sequence = 0;
uint32_t lastSampleMs = 0;
uint32_t lastHeartbeatMs = 0;
char command[32];
size_t commandLength = 0;
bool discardingCommand = false;

void send(JsonDocument& message) {
  message["v"] = 1;
  message["device"] = "membrane-ads1115-monitor";
  message["uptime_ms"] = millis();
  serializeJson(message, Serial);
  Serial.println();
}

bool readRegister(uint8_t reg, uint16_t& value) {
  Wire.beginTransmission(kAddress);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0 ||
      Wire.requestFrom(kAddress, static_cast<uint8_t>(2)) != 2) return false;
  const int high = Wire.read();
  const int low = Wire.read();
  if (high < 0 || low < 0) return false;
  value = static_cast<uint16_t>((high << 8) | low);
  return true;
}

Sample readChannel(uint8_t channel) {
  Sample result;
  result.status = "i2c_error";
  // Single-ended AINx, +/-4.096 V PGA, single-shot, 128 SPS, comparator off.
  // The physical input range remains bounded by the module's supply rails.
  const uint16_t config = static_cast<uint16_t>(0x8383U | ((4U + channel) << 12));
  Wire.beginTransmission(kAddress);
  Wire.write(static_cast<uint8_t>(1));
  Wire.write(static_cast<uint8_t>(config >> 8));
  Wire.write(static_cast<uint8_t>(config));
  if (Wire.endTransmission() != 0) return result;

  const uint32_t started = millis();
  delay(9);
  while (static_cast<uint32_t>(millis() - started) <= 30) {
    uint16_t readback = 0;
    if (!readRegister(1, readback)) return result;
    if ((readback & 0x7fffU) != (config & 0x7fffU)) {
      result.status = "config_mismatch";
      return result;
    }
    if (readback & 0x8000U) {
      uint16_t raw = 0;
      if (!readRegister(0, raw)) return result;
      result.valid = true;
      result.raw = static_cast<int16_t>(raw);
      result.sampledMs = millis();
      result.status = "reading_received";
      return result;
    }
    delay(1);
  }
  result.status = "conversion_timeout";
  return result;
}

void sendHello() {
  JsonDocument message;
  message["type"] = "hello";
  message["firmware"] = "0.1.28-ads1115-usb";
  message["sda_pin"] = kSdaPin;
  message["scl_pin"] = kSclPin;
  message["i2c_hz"] = kI2cHz;
  message["adc_address"] = kAddress;
  message["bus_ready"] = busReady;
  message["divider_ratio"] = 5;
  message["volts_per_count"] = 0.000125;
  send(message);
}

void sendReadings(const char* type) {
  JsonDocument message;
  message["type"] = type;
  message["sequence"] = sequence;
  message["adc_ack"] = adcAck;
  for (uint8_t channel = 0; channel < 3; ++channel) {
    auto reading = message["channels"][kChannelNames[channel]].to<JsonObject>();
    const auto& sample = samples[channel];
    reading["signal"] = kSignalNames[channel];
    reading["status"] = sample.status;
    if (sample.valid) {
      reading["raw"] = sample.raw;
      reading["volts"] = sample.raw * 0.000125;
      reading["sample_uptime_ms"] = sample.sampledMs;
    } else {
      reading["raw"] = nullptr;
      reading["volts"] = nullptr;
      reading["sample_uptime_ms"] = nullptr;
    }
  }
  send(message);
}

void scan() {
  JsonDocument message;
  message["type"] = "i2c_scan";
  message["sda_pin"] = kSdaPin;
  message["scl_pin"] = kSclPin;
  message["i2c_hz"] = kI2cHz;
  auto addresses = message["addresses"].to<JsonArray>();
  unsigned errors = 0;
  if (busReady) {
    for (uint8_t address = 0x08; address <= 0x77; ++address) {
      Wire.beginTransmission(address);
      const uint8_t status = Wire.endTransmission();
      if (status == 0) addresses.add(address);
      else if (status != 2) ++errors;
      delay(1);
    }
  }
  message["bus_ready"] = busReady;
  message["errors"] = errors;
  send(message);
}

void readCommands() {
  // Bound work and discard a whole overlong line rather than its suffix.
  for (unsigned count = 0; count < 64 && Serial.available(); ++count) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\r') continue;
    if (c == '\n') {
      command[commandLength] = '\0';
      if (!discardingCommand) {
        if (std::strcmp(command, "I2CSCAN") == 0) scan();
        else if (std::strcmp(command, "HELLO") == 0) sendHello();
        else if (std::strcmp(command, "PING") == 0 || std::strcmp(command, "STATUS") == 0)
          sendReadings("heartbeat");
      }
      commandLength = 0;
      discardingCommand = false;
    } else if (!discardingCommand) {
      if (commandLength < sizeof(command) - 1) command[commandLength++] = c;
      else { commandLength = 0; discardingCommand = true; }
    }
  }
}
}  // namespace

void setup() {
  Serial.begin(115200);
  busReady = Wire.begin(kSdaPin, kSclPin, kI2cHz);
  Wire.setTimeOut(20);
  sendHello();
  scan();
  lastSampleMs = millis() - kSampleIntervalMs;
}

void loop() {
  readCommands();
  uint32_t now = millis();
  if (static_cast<uint32_t>(now - lastSampleMs) >= kSampleIntervalMs) {
    lastSampleMs = now;
    adcAck = false;
    if (busReady) {
      Wire.beginTransmission(kAddress);
      adcAck = Wire.endTransmission() == 0;
    }
    for (uint8_t channel = 0; channel < 3; ++channel) {
      samples[channel] = Sample{};
      samples[channel].status = busReady ? "adc_not_responding" : "i2c_initialization_failed";
      if (adcAck) samples[channel] = readChannel(channel);
    }
    ++sequence;
    sendReadings("telemetry");
  }
  now = millis();
  if (static_cast<uint32_t>(now - lastHeartbeatMs) >= kHeartbeatIntervalMs) {
    lastHeartbeatMs = now;
    sendReadings("heartbeat");
  }
  delay(1);
}
