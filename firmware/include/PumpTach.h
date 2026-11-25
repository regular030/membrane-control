#pragma once

#include <driver/pcnt.h>
#include "ControlCore.h"

namespace basu {

// Diagnostic only. The hardware counter runs continuously between samples, so
// reading it never pauses counting and no per-edge interrupt is needed.
class PumpTach {
 public:
  PumpTach(int pin, uint16_t pulsesPerRevolution)
      : pin_(pin), pulsesPerRevolution_(pulsesPerRevolution) {}

  void begin() {
    if (pin_ < 0) return;
    pcnt_config_t config{};
    config.pulse_gpio_num = pin_;
    config.ctrl_gpio_num = PCNT_PIN_NOT_USED;
    config.lctrl_mode = PCNT_MODE_KEEP;
    config.hctrl_mode = PCNT_MODE_KEEP;
    config.pos_mode = PCNT_COUNT_INC;
    config.neg_mode = PCNT_COUNT_DIS;
    config.counter_h_lim = kCounterLimit;
    config.counter_l_lim = -1;
    config.unit = kUnit;
    config.channel = PCNT_CHANNEL_0;
    initialized_ = pcnt_unit_config(&config) == ESP_OK &&
                   pcnt_intr_disable(kUnit) == ESP_OK &&
                   pcnt_event_enable(kUnit, PCNT_EVT_H_LIM) == ESP_OK &&
                   pcnt_set_filter_value(kUnit, 80) == ESP_OK &&  // 1 us at 80 MHz APB.
                   pcnt_filter_enable(kUnit) == ESP_OK;
  }

  void sample(uint32_t now) {
    const uint32_t elapsed = now - lastSampleMs_;
    if (!initialized_ || (sampleAttempted_ && elapsed < kWindowMs)) return;
    lastSampleMs_ = now;
    sampleAttempted_ = true;

    int16_t count = 0;
    if (pcnt_get_counter_value(kUnit, &count) != ESP_OK || count < 0 || count >= kCounterLimit) {
      reading_.valid = false;
      haveBaseline_ = false;
      unavailable_ = true;
      return;
    }
    unavailable_ = haveBaseline_ && elapsed > kMaximumWindowMs;
    if (haveBaseline_ && !unavailable_) {
      int pulses = count - previousCount_;
      if (pulses < 0) pulses += kCounterLimit;  // PCNT resets to zero at the high limit.
      reading_ = {60000.0 * pulses / (elapsed * static_cast<double>(pulsesPerRevolution_)), true, now};
    } else {
      reading_.valid = false;
    }
    previousCount_ = count;
    haveBaseline_ = true;
  }

  const char* status(uint32_t now) const {
    if (pin_ < 0) return nullptr;
    if (!initialized_ || unavailable_) return "unavailable";
    if (!reading_.valid) return "waiting";
    if (!reading_.fresh(now, kMaximumWindowMs)) return "unavailable";
    return reading_.value == 0 ? "no_pulses" : "reading_received";
  }

  bool readRpm(uint32_t now, double& rpm) const {
    if (!reading_.fresh(now, kMaximumWindowMs)) return false;
    rpm = reading_.value;
    return true;
  }

 private:
  static constexpr pcnt_unit_t kUnit = PCNT_UNIT_0;
  static constexpr int16_t kCounterLimit = 32767;
  static constexpr uint32_t kWindowMs = 500;
  // The Masterflex's 6 kHz maximum gives at most 6000 pulses in a valid
  // window. Reject longer intervals rather than guessing at the count.
  static constexpr uint32_t kMaximumWindowMs = 1000;

  int pin_;
  uint16_t pulsesPerRevolution_;
  bool initialized_ = false;
  bool sampleAttempted_ = false;
  bool haveBaseline_ = false;
  bool unavailable_ = false;
  int16_t previousCount_ = 0;
  uint32_t lastSampleMs_ = 0;
  Reading reading_;
};

}  // namespace basu
