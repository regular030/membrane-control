#pragma once

#include <cstdint>
#include "ControlCore.h"

namespace basu {

struct BluetoothLinkToken {
  uint32_t generation = 0;
  uint32_t handle = 0;
  bool operator==(const BluetoothLinkToken& other) const {
    return generation == other.generation && handle == other.handle;
  }
};

// The transport synchronizes this object between its callback and worker tasks.
class BluetoothLink {
 public:
  bool open(uint32_t handle, bool authorized) {
    if (!authorized || !handle || handle_) return false;
    handle_ = handle;
    valid_ = true;
    ++generation_;
    return true;
  }

  bool close(uint32_t handle) {
    if (!handle || handle != handle_) return false;
    handle_ = 0;
    valid_ = false;
    ++generation_;
    return true;
  }

  bool invalidate(BluetoothLinkToken token) {
    if (!current(token)) return false;
    valid_ = false;
    ++generation_;
    return true;
  }

  BluetoothLinkToken token() const { return {generation_, valid_ ? handle_ : 0}; }
  bool current(BluetoothLinkToken candidate) const { return candidate.handle && candidate == token(); }

 private:
  uint32_t generation_ = 0;
  uint32_t handle_ = 0;
  bool valid_ = false;
};

// Loop-thread state only. A HELLO never inherits the preceding heartbeat.
class BluetoothCommandLease {
 public:
  void reset() { hello_ = false; heartbeat_ = false; }
  void hello() { reset(); hello_ = true; }
  bool identified() const { return hello_; }
  void heartbeat(uint32_t now) { heartbeat_ = hello_; lastHeartbeatMs_ = now; }
  bool mayActuate(uint32_t now) const {
    return heartbeat_ && static_cast<uint32_t>(now - lastHeartbeatMs_) < kHeartbeatTimeoutMs;
  }

 private:
  bool hello_ = false;
  bool heartbeat_ = false;
  uint32_t lastHeartbeatMs_ = 0;
};

}  // namespace basu
