#pragma once
#include "driver/adc.h"

using gpio_num_t = int;

namespace fake {
inline bool adc2PulldownFails = false;
inline std::array<bool, 40> adc2PulldownEnabled{};
}

inline esp_err_t rtc_gpio_pulldown_en(gpio_num_t pin) {
  if (fake::adc2PulldownFails || fake::adcAttenuation.at(pin) < 0) return ESP_FAIL;
  fake::adc2PulldownEnabled.at(pin) = true;
  return ESP_OK;
}
