#pragma once

namespace basu {
template<int DefaultPin>
constexpr int pumpPwmPin() {
#ifdef BASU_PUMP_PWM_PIN
  constexpr int pin = BASU_PUMP_PWM_PIN;
#else
  constexpr int pin = DefaultPin;
#endif
  static_assert(pin == 23 || pin == 25 || pin == 26 || pin == 27,
                "Pump PWM must use IO23, IO25, IO26, or IO27");
  return pin;
}
}  // namespace basu
