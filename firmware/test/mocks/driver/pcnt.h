#pragma once

#include <cstdint>

enum pcnt_unit_t { PCNT_UNIT_0 };
enum pcnt_channel_t { PCNT_CHANNEL_0 };
enum pcnt_ctrl_mode_t { PCNT_MODE_KEEP };
enum pcnt_count_mode_t { PCNT_COUNT_DIS, PCNT_COUNT_INC };
enum pcnt_evt_type_t { PCNT_EVT_H_LIM };
constexpr int PCNT_PIN_NOT_USED = -1;

struct pcnt_config_t {
  int pulse_gpio_num;
  int ctrl_gpio_num;
  pcnt_ctrl_mode_t lctrl_mode;
  pcnt_ctrl_mode_t hctrl_mode;
  pcnt_count_mode_t pos_mode;
  pcnt_count_mode_t neg_mode;
  int16_t counter_h_lim;
  int16_t counter_l_lim;
  pcnt_unit_t unit;
  pcnt_channel_t channel;
};

namespace fake {
inline int pcntPin = -1;
inline int16_t pcntCount = 0;
inline bool pcntConfigFails = false;
inline bool pcntReadFails = false;

inline void resetPcnt() {
  pcntPin = -1;
  pcntCount = 0;
  pcntConfigFails = pcntReadFails = false;
}
}

inline int pcnt_unit_config(const pcnt_config_t* config) {
  if (fake::pcntConfigFails) return -1;
  fake::pcntPin = config->pulse_gpio_num;
  return 0;
}

inline int pcnt_set_filter_value(pcnt_unit_t, uint16_t) { return 0; }
inline int pcnt_filter_enable(pcnt_unit_t) { return 0; }
inline int pcnt_intr_disable(pcnt_unit_t) { return 0; }
inline int pcnt_event_enable(pcnt_unit_t, pcnt_evt_type_t) { return 0; }

inline int pcnt_get_counter_value(pcnt_unit_t, int16_t* count) {
  if (fake::pcntReadFails) return -1;
  *count = fake::pcntCount;
  return 0;
}
