#pragma once

// TEMPLATE ONLY: not a real mapping or a reviewed 120 VAC wiring design.
// A knowledgeable reviewer must establish the actual seven SINGLE-COIL
// SOLENOID channels, contacts, rest polarity, unused outputs, isolated pump,
// and safe OE/reset/power-loss response before approving a separate copy.
// Do not use this target for motorized/reversing/latching actuators.
namespace basu {
inline ValveTestConfig compiledValveTestConfig() {
  ValveTestConfig config;
  config.profileId = "UNVERIFIED";
  config.reviewed = false;
  config.mappingVerified = false;
  config.restWordVerified = false;
  config.resetOeSafeVerified = false;
  config.solenoidLoadsVerified = false;
  config.pumpExcludedVerified = false;
  config.valveBits = {{-1, -1, -1, -1, -1, -1, -1}};
  config.restWord = 0;  // Placeholder, NOT an established all-relays-off word.
  return config;
}
}  // namespace basu
