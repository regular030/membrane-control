#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <string>

namespace basu {

constexpr std::size_t kValveCount = 7;
constexpr std::size_t kMaxSteps = 32;
constexpr std::size_t kMaxLineBytes = 8192;
constexpr uint32_t kHeartbeatTimeoutMs = 3000;
constexpr uint32_t kTelemetryIntervalMs = 250;
constexpr double kMaxTotalSeconds = 604800.0;

struct Outputs {
  std::array<bool, kValveCount> valves{};
  double pumpPercent = 0;
  bool operator==(const Outputs& other) const {
    return valves == other.valves && pumpPercent == other.pumpPercent;
  }
  bool operator!=(const Outputs& other) const { return !(*this == other); }
};

struct Step {
  std::string name;
  double durationSeconds = 0;
  Outputs outputs;
};

struct Recipe {
  uint32_t schemaVersion = 1;
  std::string name;
  std::string description;
  bool hardwareApproved = false;
  uint16_t repeat = 1;
  double sampleIntervalSeconds = 1;
  bool requireBalance = false;
  std::array<Step, kMaxSteps> steps;
  std::size_t stepCount = 0;
};

inline bool validOutputs(const Outputs& outputs) {
  return std::isfinite(outputs.pumpPercent) && outputs.pumpPercent >= 0 &&
         outputs.pumpPercent <= 100;
}

inline const char* validateRecipe(const Recipe& recipe) {
  if (recipe.schemaVersion != 1) return "unsupported recipe schema_version";
  if (recipe.name.empty() || recipe.name.size() > 80) return "recipe name must contain 1-80 bytes";
  if (recipe.description.size() > 1000) return "recipe description exceeds 1000 bytes";
  if (recipe.stepCount == 0 || recipe.stepCount > kMaxSteps) return "recipe must contain 1-32 steps";
  if (recipe.repeat < 1 || recipe.repeat > 100) return "repeat must be 1-100";
  if (!std::isfinite(recipe.sampleIntervalSeconds) || recipe.sampleIntervalSeconds < 0.1 ||
      recipe.sampleIntervalSeconds > 3600) return "sample_interval_s must be 0.1-3600";
  double total = 0;
  for (std::size_t i = 0; i < recipe.stepCount; ++i) {
    const auto& step = recipe.steps[i];
    if (step.name.empty() || step.name.size() > 80) return "step name must contain 1-80 bytes";
    if (!std::isfinite(step.durationSeconds) || step.durationSeconds < 0.1 ||
        step.durationSeconds > 86400) return "duration_s must be 0.1-86400";
    if (!validOutputs(step.outputs)) return "pump_percent must be finite and 0-100";
    total += step.durationSeconds;
  }
  if (!std::isfinite(total) || total * recipe.repeat > kMaxTotalSeconds)
    return "repeated recipe exceeds 604800 seconds";
  return nullptr;
}

struct Reading {
  double value = 0;
  bool valid = false;
  uint32_t acquiredMs = 0;
  bool fresh(uint32_t now, uint32_t maxAge) const {
    return valid && std::isfinite(value) && static_cast<uint32_t>(now - acquiredMs) <= maxAge;
  }
};

struct Measurements {
  Reading pressure;
  Reading flow;
  Reading pumpFeedback;
};

struct SafetyConfig {
  bool simulation = true;
  bool hardwareReady = false;
  bool safeProfileVerified = false;
  double pressureLimitPsi = NAN;
  uint32_t sensorMaxAgeMs = 1000;
  std::array<bool, kValveCount> safeValves{};
};

enum class State { Idle, Running, Manual, Fault };

inline const char* stateName(State state) {
  switch (state) {
    case State::Running: return "running";
    case State::Manual: return "manual";
    case State::Fault: return "fault";
    default: return "idle";
  }
}

// Portable state machine. GPIO, serial and clock sources are deliberately outside it.
class Controller {
 public:
  explicit Controller(SafetyConfig safety = {}) : safety_(safety) { resetOutputs(); }

  const char* load(const Recipe& candidate) {
    if (state_ != State::Idle) return "recipe can only be replaced while idle";
    if (const char* error = validateRecipe(candidate)) return error;
    recipe_ = candidate;  // Commit only after every field/step has passed validation.
    loaded_ = true;
    return nullptr;
  }

  const char* start(uint32_t now) {
    if (state_ != State::Idle) return "start requires idle state";
    if (!loaded_) return "no recipe loaded";
    if (!safety_.simulation && !recipe_.hardwareApproved) return "recipe is not hardware approved";
    if (const char* error = readiness(now)) return error;
    state_ = State::Running;
    stepIndex_ = 0;
    cycle_ = 1;
    stepStartedMs_ = now;
    lastHeartbeatMs_ = now;
    outputs_ = recipe_.steps[0].outputs;
    return nullptr;
  }

  const char* manual(const Outputs& requested, uint32_t now) {
    if (state_ != State::Idle && state_ != State::Manual)
      return "manual control requires idle or manual state";
    if (!validOutputs(requested)) return "pump_percent must be finite and 0-100";
    if (const char* error = readiness(now)) return error;
    if (state_ == State::Idle) lastHeartbeatMs_ = now;
    state_ = State::Manual;
    stepIndex_ = -1;
    cycle_ = 0;
    outputs_ = requested;
    return nullptr;
  }

  // A stop never clears a latched fault and is valid in every state.
  void stop() {
    resetOutputs();
    stepIndex_ = -1;
    if (state_ != State::Fault) state_ = State::Idle;
  }

  void latchFault(const std::string& reason) {
    if (fault_.empty()) fault_ = reason;
    state_ = State::Fault;
    resetOutputs();
    stepIndex_ = -1;
  }

  const char* clearFault() {
    if (active()) return "stop before clearing a fault";
    fault_.clear();
    state_ = State::Idle;
    stepIndex_ = -1;
    resetOutputs();
    return nullptr;
  }

  void heartbeat(uint32_t now) { lastHeartbeatMs_ = now; }
  void setMeasurements(const Measurements& readings) { measurements_ = readings; }
  void setHardwareReady(bool ready) { safety_.hardwareReady = ready; }

  void tick(uint32_t now) {
    if (!active()) return;
    // Unsigned differences remain correct across millis() rollover.
    if (static_cast<uint32_t>(now - lastHeartbeatMs_) >= kHeartbeatTimeoutMs) {
      latchFault("heartbeat_timeout");
      return;
    }
    if (!safety_.simulation) {
      if (const char* error = readiness(now)) {
        latchFault(error);
        return;
      }
    }
    if (state_ != State::Running) return;
    // Bound loop by recipe limits; no blocking delay() or desktop-timed sequencing.
    while (state_ == State::Running) {
      const uint32_t durationMs = stepDurationMs(stepIndex_);
      if (static_cast<uint32_t>(now - stepStartedMs_) < durationMs) break;
      stepStartedMs_ += durationMs;
      ++stepIndex_;
      if (stepIndex_ >= static_cast<int>(recipe_.stepCount)) {
        if (cycle_ >= recipe_.repeat) {
          stop();
          break;
        }
        ++cycle_;
        stepIndex_ = 0;
      }
      outputs_ = recipe_.steps[stepIndex_].outputs;
    }
  }

  bool active() const { return state_ == State::Running || state_ == State::Manual; }
  State state() const { return state_; }
  const Outputs& outputs() const { return outputs_; }
  const Measurements& measurements() const { return measurements_; }
  const std::string& fault() const { return fault_; }
  const Recipe& recipe() const { return recipe_; }
  bool recipeLoaded() const { return loaded_; }
  bool simulation() const { return safety_.simulation; }
  bool hardwareVerified() const { return !safety_.simulation && safety_.hardwareReady && safety_.safeProfileVerified; }
  int stepIndex() const { return stepIndex_; }
  uint16_t cycle() const { return cycle_; }
  uint32_t sensorMaxAgeMs() const { return safety_.sensorMaxAgeMs; }
  double remainingSeconds(uint32_t now) const {
    if (state_ != State::Running || stepIndex_ < 0) return 0;
    const uint32_t duration = stepDurationMs(stepIndex_);
    const uint32_t elapsed = now - stepStartedMs_;
    return elapsed >= duration ? 0 : static_cast<double>(duration - elapsed) / 1000.0;
  }

 private:
  const char* readiness(uint32_t now) const {
    if (safety_.simulation) return nullptr;
    if (!safety_.hardwareReady) return "hardware_not_verified";
    if (!safety_.safeProfileVerified || !std::isfinite(safety_.pressureLimitPsi) ||
        safety_.pressureLimitPsi <= 0 || safety_.sensorMaxAgeMs == 0)
      return "safe_profile_not_verified";
    if (!measurements_.pressure.fresh(now, safety_.sensorMaxAgeMs)) return "pressure_invalid_or_stale";
    if (measurements_.pressure.value > safety_.pressureLimitPsi) return "pressure_limit_exceeded";
    return nullptr;
  }
  uint32_t stepDurationMs(int index) const {
    // Round configured durations upward to the millisecond clock resolution.
    return std::max<uint32_t>(1, static_cast<uint32_t>(std::ceil(recipe_.steps[index].durationSeconds * 1000.0)));
  }
  void resetOutputs() { outputs_.valves = safety_.safeValves; outputs_.pumpPercent = 0; }

  SafetyConfig safety_;
  State state_ = State::Idle;
  Outputs outputs_;
  Measurements measurements_;
  Recipe recipe_;
  bool loaded_ = false;
  int stepIndex_ = -1;
  uint16_t cycle_ = 0;
  uint32_t stepStartedMs_ = 0;
  uint32_t lastHeartbeatMs_ = 0;
  std::string fault_;
};

}  // namespace basu
