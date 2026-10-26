#pragma once
#include "Arduino.h"

using esp_err_t = int;
constexpr esp_err_t ESP_OK = 0;
constexpr esp_err_t ESP_FAIL = -1;
enum ledc_mode_t { LEDC_HIGH_SPEED_MODE = 0, LEDC_LOW_SPEED_MODE = 1 };
enum ledc_channel_t { LEDC_CHANNEL_0 = 0, LEDC_CHANNEL_1, LEDC_CHANNEL_2, LEDC_CHANNEL_3,
                      LEDC_CHANNEL_4, LEDC_CHANNEL_5, LEDC_CHANNEL_6, LEDC_CHANNEL_7 };
enum ledc_timer_t { LEDC_TIMER_0 = 0, LEDC_TIMER_1, LEDC_TIMER_2, LEDC_TIMER_3 };
enum ledc_intr_type_t { LEDC_INTR_DISABLE = 0 };
struct ledc_channel_config_t {
  int gpio_num;
  ledc_mode_t speed_mode;
  ledc_channel_t channel;
  ledc_intr_type_t intr_type;
  ledc_timer_t timer_sel;
  uint32_t duty;
  int hpoint;
};
inline int fakeChannel(ledc_mode_t mode, ledc_channel_t channel) { return int(mode) * 8 + int(channel); }
inline esp_err_t ledc_channel_config(const ledc_channel_config_t* config) {
  const int channel = fakeChannel(config->speed_mode, config->channel);
  fake::recordLedc("attach", channel, config->gpio_num, config->duty);
  if (fake::ledcAttachFails) return ESP_FAIL;
  fake::ledcDuties.at(channel) = config->duty;
  fake::ledcPins.at(channel) = config->gpio_num;
  return ESP_OK;
}
inline esp_err_t ledc_set_duty(ledc_mode_t mode, ledc_channel_t channel, uint32_t duty) {
  const int index = fakeChannel(mode, channel);
  fake::recordLedc("set", index, -1, duty);
  if (fake::ledcSetFails) return ESP_FAIL;
  fake::ledcDuties.at(index) = duty;
  return ESP_OK;
}
inline esp_err_t ledc_update_duty(ledc_mode_t mode, ledc_channel_t channel) {
  fake::recordLedc("update", fakeChannel(mode, channel), -1, 0);
  return fake::ledcUpdateFails ? ESP_FAIL : ESP_OK;
}
inline esp_err_t ledc_stop(ledc_mode_t mode, ledc_channel_t channel, uint32_t idleLevel) {
  const int index = fakeChannel(mode, channel);
  fake::recordLedc("stop", index, -1, idleLevel);
  if (fake::ledcStopFails) return ESP_FAIL;
  fake::ledcDuties.at(index) = 0;
  return ESP_OK;
}
