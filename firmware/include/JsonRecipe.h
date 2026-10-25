#pragma once
#include <ArduinoJson.h>
#include "ControlCore.h"

namespace basu {

class FrameReader {
 public:
  FrameReader(const char* bytes, std::size_t count) : bytes_(bytes), count_(count) {}
  int read() { return position_ < count_ ? static_cast<unsigned char>(bytes_[position_++]) : -1; }
  std::size_t readBytes(char* destination, std::size_t count) {
    std::size_t copied = 0;
    while (copied < count && position_ < count_) destination[copied++] = bytes_[position_++];
    return copied;
  }
  std::size_t position() const { return position_; }
 private:
  const char* bytes_;
  std::size_t count_;
  std::size_t position_ = 0;
};

inline const char* decodeObject(const char* bytes, std::size_t count, JsonDocument& document) {
  if (count > kMaxLineBytes) return "line exceeds 8192 bytes";
  for (std::size_t i = 0; i < count; ++i) if (bytes[i] == '\0') return "NUL byte in JSON frame";
  FrameReader reader(bytes, count);
  if (deserializeJson(document, reader, DeserializationOption::NestingLimit(8)) ||
      !document.is<JsonObject>()) return "invalid JSON object";
  for (std::size_t i = reader.position(); i < count; ++i) {
    if (bytes[i] != ' ' && bytes[i] != '\t' && bytes[i] != '\r' && bytes[i] != '\n')
      return "trailing data after JSON object";
  }
  return nullptr;
}

inline const char* parseEnvelope(JsonVariantConst request, uint32_t& id, std::string& command) {
  id = 0;
  if (!request.is<JsonObjectConst>()) return "invalid JSON object";
  if (request["id"].is<bool>() || !request["id"].is<uint32_t>() || request["id"].as<uint32_t>() == 0)
    return "id must be a positive 32-bit integer";
  id = request["id"].as<uint32_t>();
  if (request["v"].is<bool>() || !request["v"].is<uint32_t>() || request["v"].as<uint32_t>() != 1)
    return "unsupported protocol version";
  if (!request["cmd"].is<const char*>()) return "cmd must be a string";
  command = request["cmd"].as<const char*>();
  return nullptr;
}

inline bool finiteJsonNumber(JsonVariantConst value) {
  return !value.is<bool>() && value.is<double>() && std::isfinite(value.as<double>());
}

inline const char* parseOutputs(JsonVariantConst valves, JsonVariantConst pump, Outputs& destination) {
  if (!valves.is<JsonArrayConst>() || valves.size() != kValveCount)
    return "valves must contain exactly seven booleans";
  Outputs candidate;
  for (std::size_t i = 0; i < kValveCount; ++i) {
    if (!valves[i].is<bool>()) return "valve states must be booleans";
    candidate.valves[i] = valves[i].as<bool>();
  }
  if (!finiteJsonNumber(pump)) return "pump_percent must be a finite number";
  candidate.pumpPercent = pump.as<double>();
  if (!validOutputs(candidate)) return "pump_percent must be 0-100";
  destination = candidate;
  return nullptr;
}

// Strongly typed parse into a temporary. Failure never changes the destination.
inline const char* parseRecipe(JsonVariantConst value, Recipe& destination) {
  if (!value.is<JsonObjectConst>()) return "recipe must be an object";
  if (value["schema_version"].is<bool>() || !value["schema_version"].is<uint32_t>() || value["schema_version"].as<uint32_t>() != 1)
    return "unsupported recipe schema_version";
  if (!value["name"].is<const char*>() || !value["description"].is<const char*>())
    return "recipe name and description must be strings";
  if (!value["hardware_approved"].is<bool>() || !value["require_balance"].is<bool>())
    return "recipe approval and balance requirement must be booleans";
  if (value["repeat"].is<bool>() || !value["repeat"].is<uint32_t>() || value["repeat"].as<uint32_t>() < 1 ||
      value["repeat"].as<uint32_t>() > 100) return "repeat must be an integer 1-100";
  if (!finiteJsonNumber(value["sample_interval_s"])) return "sample_interval_s must be a finite number";
  if (!value["steps"].is<JsonArrayConst>() || value["steps"].size() == 0 ||
      value["steps"].size() > kMaxSteps) return "recipe must contain 1-32 steps";
  Recipe candidate;
  candidate.schemaVersion = 1;
  candidate.name = value["name"].as<const char*>();
  candidate.description = value["description"].as<const char*>();
  candidate.hardwareApproved = value["hardware_approved"].as<bool>();
  candidate.requireBalance = value["require_balance"].as<bool>();
  candidate.repeat = value["repeat"].as<uint16_t>();
  candidate.sampleIntervalSeconds = value["sample_interval_s"].as<double>();
  candidate.stepCount = value["steps"].size();
  for (std::size_t i = 0; i < candidate.stepCount; ++i) {
    JsonVariantConst step = value["steps"][i];
    if (!step.is<JsonObjectConst>() || !step["name"].is<const char*>()) return "step name must be a string";
    if (!finiteJsonNumber(step["duration_s"])) return "duration_s must be a finite number";
    candidate.steps[i].name = step["name"].as<const char*>();
    candidate.steps[i].durationSeconds = step["duration_s"].as<double>();
    if (const char* error = parseOutputs(step["valves"], step["pump_percent"], candidate.steps[i].outputs)) return error;
  }
  if (const char* error = validateRecipe(candidate)) return error;
  destination = candidate;
  return nullptr;
}

}  // namespace basu
