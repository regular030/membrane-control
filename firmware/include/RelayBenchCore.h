#pragma once

#include <cstdint>
#include <string>
#include "JsonRecipe.h"

namespace basu {

// This interface describes commanded register levels, not measured relay states.
// It is deliberately separate from the commissioned experiment controller.
class RelayBenchIo {
 public:
  virtual ~RelayBenchIo() = default;
  virtual void writeDisabledWord(uint16_t word) = 0;
  virtual void enableOutputs() = 0;
};

enum class RelayBenchState { Disarmed, Probing, Ready, Pulsing, Fault };

inline const char* relayBenchStateName(RelayBenchState state) {
  switch (state) {
    case RelayBenchState::Probing: return "probing";
    case RelayBenchState::Ready: return "ready";
    case RelayBenchState::Pulsing: return "pulsing";
    case RelayBenchState::Fault: return "fault";
    default: return "disarmed";
  }
}

class RelayBenchCore {
 public:
  static constexpr uint32_t kHeartbeatTimeoutMs = 1000;
  static constexpr uint32_t kMinimumDurationMs = 100;
  static constexpr uint32_t kMaximumDurationMs = 2000;

  explicit RelayBenchCore(RelayBenchIo& io) : io_(io) {}

  void resetSession() {
    stop();
    heartbeatSeen_ = false;
  }

  // A late heartbeat cannot erase an expired operation or confirmation lease.
  void heartbeat(uint32_t now) {
    tick(now);
    lastHeartbeatMs_ = now;
    heartbeatSeen_ = true;
  }

  void stop() {
    io_.writeDisabledWord(baselineWord_);
    clearConfirmation();
    pulseBit_ = -1;
    durationMs_ = 0;
    state_ = RelayBenchState::Disarmed;
    fault_.clear();
  }

  const char* probe(uint32_t requestId, uint32_t baseline, uint32_t duration,
                    bool loadsDisconnected, uint32_t now) {
    tick(now);
    if (active()) return "bench operation is active; stop before another probe";
    if (state_ == RelayBenchState::Fault) return "stop to clear the relay bench fault";
    if (!loadsDisconnected) return "probe requires loads_disconnected true";
    if (baseline != 0 && baseline != 65535) return "baseline_word must be 0 or 65535";
    if (!validDuration(duration)) return "duration_ms must be an integer 100-2000";
    if (requestId == 0) return "probe requires a positive request id";
    if (!freshHeartbeat(now)) return "fresh heartbeat required before relay testing";
    clearConfirmation();
    baselineWord_ = static_cast<uint16_t>(baseline);
    probeId_ = requestId;
    pulseBit_ = -1;
    beginOperation(RelayBenchState::Probing, baselineWord_, duration, now);
    return nullptr;
  }

  const char* confirm(uint32_t probeId, uint32_t baseline, bool loadsDisconnected,
                      bool allRelaysOff, uint32_t now) {
    tick(now);
    if (active()) return "wait for the baseline probe to finish";
    if (state_ == RelayBenchState::Fault) return "stop to clear the relay bench fault";
    if (!loadsDisconnected || !allRelaysOff)
      return "confirm requires loads_disconnected and all_relays_off true";
    if (!freshHeartbeat(now)) return "fresh heartbeat required before confirmation";
    if (!probeCompleted_ || probeId == 0 || probeId != probeId_ || baseline != baselineWord_)
      return "confirmation must match the most recently completed baseline probe";
    baselineConfirmed_ = true;
    state_ = RelayBenchState::Ready;
    return nullptr;
  }

  const char* pulse(uint32_t bit, uint32_t duration, uint32_t now) {
    tick(now);
    if (active()) return "bench operation is active; stop before another pulse";
    if (state_ != RelayBenchState::Ready || !baselineConfirmed_)
      return "complete and confirm an all-relays-off baseline first";
    if (bit > 15) return "bit must be an integer 0-15";
    if (!validDuration(duration)) return "duration_ms must be an integer 100-2000";
    if (!freshHeartbeat(now)) return "fresh heartbeat required before relay testing";
    pulseBit_ = static_cast<int>(bit);
    const uint16_t word = static_cast<uint16_t>(baselineWord_ ^ (1U << bit));
    beginOperation(RelayBenchState::Pulsing, word, duration, now);
    return nullptr;
  }

  void tick(uint32_t now) {
    // Keep the observed baseline local to a continuously responding host, even
    // while OE is disabled. A reconnect must never inherit a ready board.
    if ((active() || baselineConfirmed_ || probeCompleted_) && !freshHeartbeat(now)) {
      fail("heartbeat_timeout");
      return;
    }
    if (!active() || static_cast<uint32_t>(now - operationStartedMs_) < durationMs_) return;
    const bool wasProbe = state_ == RelayBenchState::Probing;
    io_.writeDisabledWord(baselineWord_);
    pulseBit_ = -1;
    durationMs_ = 0;
    if (wasProbe) {
      probeCompleted_ = true;
      state_ = RelayBenchState::Disarmed;
    } else {
      state_ = RelayBenchState::Ready;
    }
  }

  bool active() const {
    return state_ == RelayBenchState::Probing || state_ == RelayBenchState::Pulsing;
  }
  RelayBenchState state() const { return state_; }
  bool outputsEnabled() const { return active(); }
  bool baselineConfirmed() const { return baselineConfirmed_; }
  bool probeCompleted() const { return probeCompleted_; }
  uint16_t baselineWord() const { return baselineWord_; }
  uint32_t probeId() const { return probeId_; }
  int pulseBit() const { return pulseBit_; }
  const std::string& fault() const { return fault_; }
  uint32_t remainingMs(uint32_t now) const {
    if (!active()) return 0;
    const uint32_t elapsed = now - operationStartedMs_;
    return elapsed >= durationMs_ ? 0 : durationMs_ - elapsed;
  }

 private:
  static bool validDuration(uint32_t duration) {
    return duration >= kMinimumDurationMs && duration <= kMaximumDurationMs;
  }
  bool freshHeartbeat(uint32_t now) const {
    return heartbeatSeen_ && static_cast<uint32_t>(now - lastHeartbeatMs_) < kHeartbeatTimeoutMs;
  }
  void clearConfirmation() {
    baselineConfirmed_ = false;
    probeCompleted_ = false;
    probeId_ = 0;
  }
  void beginOperation(RelayBenchState state, uint16_t word, uint32_t duration, uint32_t now) {
    // The electrical adapter disables OE before changing the stored word.
    io_.writeDisabledWord(word);
    operationStartedMs_ = now;
    durationMs_ = duration;
    state_ = state;
    io_.enableOutputs();
  }
  void fail(const char* reason) {
    io_.writeDisabledWord(baselineWord_);
    clearConfirmation();
    pulseBit_ = -1;
    durationMs_ = 0;
    state_ = RelayBenchState::Fault;
    fault_ = reason;
  }

  RelayBenchIo& io_;
  RelayBenchState state_ = RelayBenchState::Disarmed;
  bool heartbeatSeen_ = false;
  uint32_t lastHeartbeatMs_ = 0;
  bool baselineConfirmed_ = false;
  bool probeCompleted_ = false;
  uint16_t baselineWord_ = 0;
  uint32_t probeId_ = 0;
  int pulseBit_ = -1;
  uint32_t operationStartedMs_ = 0;
  uint32_t durationMs_ = 0;
  std::string fault_;
};

struct RelayBenchReply {
  uint32_t id = 0;
  bool hello = false;
  const char* error = nullptr;
};

inline bool relayBenchInteger(JsonVariantConst value) {
  return !value.is<bool>() && value.is<uint32_t>();
}

// Strict envelope/type checks are shared with the experiment firmware, while
// the command vocabulary cannot load a recipe or actuate the pump.
inline RelayBenchReply handleRelayBenchRequest(RelayBenchCore& bench, JsonVariantConst request,
                                               uint32_t now) {
  bench.tick(now);
  RelayBenchReply reply;
  std::string command;
  reply.error = parseEnvelope(request, reply.id, command);
  if (reply.error) return reply;
  if (command == "hello") {
    bench.resetSession();
    reply.hello = true;
  } else if (command == "heartbeat") {
    bench.heartbeat(now);
  } else if (command == "stop") {
    bench.stop();
  } else if (command == "bench_probe") {
    if (!relayBenchInteger(request["baseline_word"]) || !relayBenchInteger(request["duration_ms"]) ||
        !request["loads_disconnected"].is<bool>()) reply.error = "invalid bench_probe field types";
    else reply.error = bench.probe(reply.id, request["baseline_word"].as<uint32_t>(),
                                  request["duration_ms"].as<uint32_t>(),
                                  request["loads_disconnected"].as<bool>(), now);
  } else if (command == "bench_confirm") {
    if (!relayBenchInteger(request["probe_id"]) || !relayBenchInteger(request["baseline_word"]) ||
        !request["loads_disconnected"].is<bool>() || !request["all_relays_off"].is<bool>())
      reply.error = "invalid bench_confirm field types";
    else reply.error = bench.confirm(request["probe_id"].as<uint32_t>(),
                                    request["baseline_word"].as<uint32_t>(),
                                    request["loads_disconnected"].as<bool>(),
                                    request["all_relays_off"].as<bool>(), now);
  } else if (command == "bench_pulse") {
    if (!relayBenchInteger(request["bit"]) || !relayBenchInteger(request["duration_ms"]))
      reply.error = "invalid bench_pulse field types";
    else reply.error = bench.pulse(request["bit"].as<uint32_t>(), request["duration_ms"].as<uint32_t>(), now);
  } else {
    reply.error = "relay bench accepts only hello, heartbeat, stop and bench commands";
  }
  return reply;
}

}  // namespace basu
