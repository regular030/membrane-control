#pragma once
#include "driver/ledc.h"

enum adc2_channel_t { ADC2_CHANNEL_7 = 7, ADC2_CHANNEL_9 = 9 };
enum adc_atten_t { ADC_ATTEN_DB_2_5 = ADC_2_5db, ADC_ATTEN_DB_12 = ADC_11db };
enum adc_bits_width_t { ADC_WIDTH_BIT_12 };
enum adc_unit_t { ADC_UNIT_2 };

namespace fake {
inline bool adc2ReadFails = false;
inline bool adc2SetupFails = false;
}

inline int adc2Pin(adc2_channel_t channel) { return channel == ADC2_CHANNEL_7 ? 27 : 26; }

inline esp_err_t adc2_config_channel_atten(adc2_channel_t channel, adc_atten_t attenuation) {
  if (fake::adc2SetupFails) return ESP_FAIL;
  analogSetPinAttenuation(adc2Pin(channel), attenuation);
  return ESP_OK;
}

inline esp_err_t adc2_get_raw(adc2_channel_t channel, adc_bits_width_t, int* raw) {
  if (fake::adc2ReadFails) return ESP_FAIL;
  *raw = analogReadMilliVolts(adc2Pin(channel));
  return ESP_OK;
}
