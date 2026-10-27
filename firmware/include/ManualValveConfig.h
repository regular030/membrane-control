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
  // User-confirmed labels V1,V2,V3,V4,V5,V7 map to bits0,1,2,3,5,6.
  // There is no V6. All LOW is off; bit4 and bits7..15 stay LOW.
  ManualValveConfig config;
  config.confirmed = true;
  config.bits = {{0, 1, 2, 3, 5, 6}};
  return config;
}

}  // namespace basu
