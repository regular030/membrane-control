#pragma once

#include <array>
#include <cstdint>
#include <string>

namespace basu {

// Approval is specific to seven single-coil solenoids, not motorized/reversing
// actuators or a production process. No runtime command can edit this profile.
struct ValveTestConfig {
  std::string profileId = "UNVERIFIED";
  bool reviewed = false;
  bool mappingVerified = false;
  bool restWordVerified = false;
  bool resetOeSafeVerified = false;
  bool solenoidLoadsVerified = false;
  bool pumpExcludedVerified = false;
  std::array<int, 7> valveBits{{-1, -1, -1, -1, -1, -1, -1}};
  uint32_t restWord = 0;
};

inline const char* validateValveTestConfig(const ValveTestConfig& config) {
  if (!config.reviewed || !config.mappingVerified || !config.restWordVerified ||
      !config.resetOeSafeVerified || !config.solenoidLoadsVerified || !config.pumpExcludedVerified)
    return "valve profile requires reviewed mapping, rest word, reset/OE safety, solenoids and pump exclusion";
  if (config.profileId.empty() || config.profileId.size() > 64 || config.profileId == "UNVERIFIED")
    return "reviewed valve profile requires a unique 1-64 character id";
  for (char ch : config.profileId) {
    if (!((ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') ||
          (ch >= '0' && ch <= '9') || ch == '-' || ch == '_' || ch == '.'))
      return "valve profile id accepts letters, digits, dash, underscore and dot only";
  }
  if (config.restWord > 65535) return "valve rest word must contain exactly sixteen bits";
  std::array<bool, 16> mapped{};
  for (int bit : config.valveBits) {
    if (bit < 0 || bit > 15 || mapped[bit]) return "seven unique reviewed valve bits 0-15 are required";
    mapped[bit] = true;
  }
  return nullptr;
}

}  // namespace basu
