#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

constexpr int LOW = 0;
constexpr int HIGH = 1;
constexpr int INPUT = 0;
constexpr int OUTPUT = 1;
constexpr int ADC_11db = 3;
namespace fake {
struct GpioEvent { bool write; int pin; int value; unsigned sequence; };
struct LedcEvent { const char* operation; int channel; int pin; uint32_t value; unsigned sequence; };
inline std::array<int, 40> levels{};
inline unsigned gpioCalls = 0;
inline std::vector<GpioEvent> gpioEvents;
inline unsigned operationSequence = 0;
inline unsigned ledcCalls = 0;
inline bool ledcSetupSucceeds = true;
inline uint32_t ledcActualFrequency = 0;
inline bool ledcAttachFails = false;
inline bool ledcSetFails = false;
inline bool ledcUpdateFails = false;
inline bool ledcStopFails = false;
inline std::array<uint32_t, 16> ledcDuties{};
inline std::array<int, 16> ledcPins{};
inline std::vector<LedcEvent> ledcEvents;
inline void resetGpio() { levels.fill(0); gpioCalls = 0; gpioEvents.clear(); operationSequence = 0; }
inline void resetLedc() {
  ledcCalls = 0; ledcSetupSucceeds = true; ledcActualFrequency = 0;
  ledcAttachFails = ledcSetFails = ledcUpdateFails = ledcStopFails = false;
  ledcDuties.fill(0); ledcPins.fill(-1); ledcEvents.clear();
}
inline void recordLedc(const char* operation, int channel, int pin, uint32_t value) {
  ++ledcCalls;
  ledcEvents.push_back({operation, channel, pin, value, ++operationSequence});
}
}
inline void digitalWrite(int pin, int level) {
  ++fake::gpioCalls; fake::levels.at(pin) = level;
  fake::gpioEvents.push_back({true, pin, level, ++fake::operationSequence});
}
inline void pinMode(int pin, int mode) {
  ++fake::gpioCalls; fake::gpioEvents.push_back({false, pin, mode, ++fake::operationSequence});
}
inline void analogSetPinAttenuation(int, int) { ++fake::gpioCalls; }
inline uint32_t analogReadMilliVolts(int) { ++fake::gpioCalls; return 1000; }
inline uint32_t ledcSetup(uint8_t channel, uint32_t frequency, uint8_t resolution) {
  fake::recordLedc("setup", channel, -1, resolution);
  return fake::ledcSetupSucceeds ? (fake::ledcActualFrequency ? fake::ledcActualFrequency : frequency) : 0;
}
