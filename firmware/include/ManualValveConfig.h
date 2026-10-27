#pragma once
#include "ControlCore.h"

namespace basu {

struct ManualValveConfig {
  bool confirmed = false;
  std::array<int, kManualValveCount> bits{{-1, -1, -1, -1, -1, -1}};
};

inline const char* validateManualValveConfig(const ManualValveConfig& config) {
  if (!config.confirmed) return "manual valve mapping is not confirmed";
  std::array<bool, 16> used{};
  for (int bit : config.bits) {
    if (bit < 0 || bit > 15 || used[bit]) return "six unique manual valve bits 0-15 are required";
    used[bit] = true;
  }
  return nullptr;
}

inline ManualValveConfig confirmedRigManualValves() {
  // User-confirmed rig: SIX physical valves, V1..V6 = bits0..5.
  // All LOW is off, all HIGH energized. Bits6..15 remain LOW in this mode.
  ManualValveConfig config;
  config.confirmed = true;
  config.bits = {{0, 1, 2, 3, 4, 5}};
  return config;
}

}  // namespace basu
