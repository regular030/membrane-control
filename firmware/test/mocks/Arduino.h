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
struct GpioEvent { bool write; int pin; int value; };
inline std::array<int, 40> levels{};
inline unsigned gpioCalls = 0;
inline std::vector<GpioEvent> gpioEvents;
inline void resetGpio() { levels.fill(0); gpioCalls = 0; gpioEvents.clear(); }
}
inline void digitalWrite(int pin, int level) {
  ++fake::gpioCalls; fake::levels.at(pin) = level; fake::gpioEvents.push_back({true, pin, level});
}
inline void pinMode(int pin, int mode) { ++fake::gpioCalls; fake::gpioEvents.push_back({false, pin, mode}); }
inline void analogSetPinAttenuation(int, int) { ++fake::gpioCalls; }
inline uint32_t analogReadMilliVolts(int) { ++fake::gpioCalls; return 1000; }
