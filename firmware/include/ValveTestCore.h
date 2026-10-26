#pragma once

#include <cstring>
#include <string>
#include "JsonRecipe.h"
#include "ValveTestConfig.h"

namespace basu {

class ValveTestIo {
 public:
  virtual ~ValveTestIo() = default;
  virtual bool begin(const ValveTestConfig& config) = 0;
  virtual void writeDisabledWord(uint16_t word) = 0;
  virtual void enableOutputs() = 0;
};

enum class ValveTestState { Locked, Disarmed, Ready, Pulsing, Fault };

inline const char* valveTestStateName(ValveTestState state) {
  switch (state) {
    case ValveTestState::Disarmed: return "disarmed";
    case ValveTestState::Ready: return "ready";
    case ValveTestState::Pulsing: return "pulsing";
    case ValveTestState::Fault: return "fault";
    default: return "locked";
  }
}

class ValveTestCore {
 public:
  static constexpr uint32_t kHeartbeatTimeoutMs = 1000;
  static constexpr uint32_t kDefaultDurationMs = 500;
  static constexpr uint32_t kMinimumDurationMs = 100;
  static constexpr uint32_t kMaximumDurationMs = 2000;

  ValveTestCore(ValveTestConfig config, ValveTestIo& io) : config_(config), io_(io) {}

  void begin() {
    // Invalid/missing approval must not perform even one GPIO operation.
    if (const char* error = validateValveTestConfig(config_)) { fault_ = error; return; }
    if (!io_.begin(config_)) { fault_ = "valve relay initialization failed"; return; }
    profileVerified_ = true;
    state_ = ValveTestState::Disarmed;
    fault_.clear();
  }

  void resetSession() { stop(); }

  void heartbeat(uint32_t now) {
    tick(now);  // A late heartbeat cannot erase an already expired lease.
    lastHeartbeatMs_ = now;
    heartbeatSeen_ = true;
  }

  void stop() {
    if (profileVerified_) io_.writeDisabledWord(static_cast<uint16_t>(config_.restWord));
    activeValve_ = 0;
    durationMs_ = 0;
    heartbeatSeen_ = false;
    state_ = profileVerified_ ? ValveTestState::Disarmed : ValveTestState::Locked;
    if (profileVerified_) fault_.clear();
  }

  const char* arm(const std::string& profileId, bool wiringChecked, bool pumpIsolated,
                  bool testAreaReady, uint32_t now) {
    tick(now);
    if (!profileVerified_) return "valve profile is locked; a reviewed compiled profile is required";
    if (state_ != ValveTestState::Disarmed) return "stop before arming a valve test";
    if (profileId != config_.profileId) return "valve profile id does not match this firmware";
    if (!wiringChecked || !pumpIsolated || !testAreaReady)
      return "wiring_checked, pump_isolated and test_area_ready must all be true";
    if (!freshHeartbeat(now)) return "fresh heartbeat required before arming";
    state_ = ValveTestState::Ready;
    return nullptr;
  }

  const char* pulse(uint32_t valve, uint32_t duration, uint32_t now) {
    tick(now);
    if (!profileVerified_ || state_ != ValveTestState::Ready)
      return "arm the reviewed valve profile before one valve pulse";
    if (valve < 1 || valve > 7) return "valve must be an integer 1-7";
    if (duration < kMinimumDurationMs || duration > kMaximumDurationMs)
      return "duration_ms must be an integer 100-2000";
    if (!freshHeartbeat(now)) return "fresh heartbeat required before valve testing";
    const uint16_t word = static_cast<uint16_t>(config_.restWord ^ (1U << config_.valveBits[valve - 1]));
    io_.writeDisabledWord(word);
    operationStartedMs_ = now;
    durationMs_ = duration;
    activeValve_ = static_cast<int>(valve);
    state_ = ValveTestState::Pulsing;
    io_.enableOutputs();
    return nullptr;
  }

  void tick(uint32_t now) {
    if ((state_ == ValveTestState::Ready || state_ == ValveTestState::Pulsing) && !freshHeartbeat(now)) {
      io_.writeDisabledWord(static_cast<uint16_t>(config_.restWord));
      activeValve_ = 0;
      durationMs_ = 0;
      state_ = ValveTestState::Fault;
      fault_ = "heartbeat_timeout";
      return;
    }
    if (state_ != ValveTestState::Pulsing || static_cast<uint32_t>(now - operationStartedMs_) < durationMs_) return;
    io_.writeDisabledWord(static_cast<uint16_t>(config_.restWord));
    activeValve_ = 0;
    durationMs_ = 0;
    state_ = ValveTestState::Ready;
  }

  ValveTestState state() const { return state_; }
  bool profileVerified() const { return profileVerified_; }
  const std::string& profileId() const { return config_.profileId; }
  bool outputsEnabled() const { return state_ == ValveTestState::Pulsing; }
  int activeValve() const { return activeValve_; }
  const std::string& fault() const { return fault_; }
  uint32_t remainingMs(uint32_t now) const {
    if (state_ != ValveTestState::Pulsing) return 0;
    const uint32_t elapsed = now - operationStartedMs_;
    return elapsed >= durationMs_ ? 0 : durationMs_ - elapsed;
  }

 private:
  bool freshHeartbeat(uint32_t now) const {
    return heartbeatSeen_ && static_cast<uint32_t>(now - lastHeartbeatMs_) < kHeartbeatTimeoutMs;
  }
  const ValveTestConfig config_;
  ValveTestIo& io_;
  bool profileVerified_ = false;
  bool heartbeatSeen_ = false;
  uint32_t lastHeartbeatMs_ = 0;
  uint32_t operationStartedMs_ = 0;
  uint32_t durationMs_ = 0;
  int activeValve_ = 0;
  ValveTestState state_ = ValveTestState::Locked;
  std::string fault_;
};

struct ValveTestReply {
  uint32_t id = 0;
  bool hello = false;
  const char* error = nullptr;
};

inline bool valveTestInteger(JsonVariantConst value) {
  return !value.is<bool>() && value.is<uint32_t>();
}

inline bool valveTestFields(JsonVariantConst request, const std::string& command) {
  for (JsonPairConst field : request.as<JsonObjectConst>()) {
    const char* key = field.key().c_str();
    if (!std::strcmp(key, "v") || !std::strcmp(key, "id") || !std::strcmp(key, "cmd")) continue;
    if (command == "valve_arm" && (!std::strcmp(key, "profile_id") || !std::strcmp(key, "wiring_checked") ||
        !std::strcmp(key, "pump_isolated") || !std::strcmp(key, "test_area_ready"))) continue;
    if (command == "valve_pulse" && (!std::strcmp(key, "valve") || !std::strcmp(key, "duration_ms"))) continue;
    return false;
  }
  return true;
}

inline ValveTestReply handleValveTestRequest(ValveTestCore& core, JsonVariantConst request, uint32_t now) {
  core.tick(now);
  ValveTestReply reply;
  std::string command;
  reply.error = parseEnvelope(request, reply.id, command);
  if (reply.error) return reply;
  if (!valveTestFields(request, command)) { reply.error = "unexpected valve-test field"; return reply; }
  if (command == "hello") {
    core.resetSession();
    reply.hello = true;
  } else if (command == "heartbeat") {
    core.heartbeat(now);
  } else if (command == "stop") {
    core.stop();
  } else if (command == "valve_arm") {
    if (!request["profile_id"].is<const char*>() || !request["wiring_checked"].is<bool>() ||
        !request["pump_isolated"].is<bool>() || !request["test_area_ready"].is<bool>())
      reply.error = "invalid valve_arm field types";
    else reply.error = core.arm(request["profile_id"].as<const char*>(), request["wiring_checked"].as<bool>(),
                               request["pump_isolated"].as<bool>(), request["test_area_ready"].as<bool>(), now);
  } else if (command == "valve_pulse") {
    if (!valveTestInteger(request["valve"]) || !valveTestInteger(request["duration_ms"]))
      reply.error = "invalid valve_pulse field types";
    else reply.error = core.pulse(request["valve"].as<uint32_t>(), request["duration_ms"].as<uint32_t>(), now);
  } else reply.error = "valve test accepts only hello, heartbeat, stop, valve_arm and valve_pulse";
  return reply;
}

}  // namespace basu
