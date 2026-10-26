#pragma once

#include <Arduino.h>
#include "ValveTestCore.h"

namespace basu {

// Candidate board interface only. The compiled review must establish that its
// OE-disabled/high-impedance and reset states actually release every solenoid.
class ValveTestHardware final : public ValveTestIo {
 public:
  static constexpr int kDataPin = 14;
  static constexpr int kClockPin = 13;
  static constexpr int kLatchPin = 12;
  static constexpr int kOePin = 5;

  bool begin(const ValveTestConfig& config) override {
    if (validateValveTestConfig(config)) return false;
    digitalWrite(kOePin, HIGH);
    pinMode(kOePin, OUTPUT);
    for (int pin : {kDataPin, kClockPin, kLatchPin}) {
      digitalWrite(pin, LOW);
      pinMode(pin, OUTPUT);
    }
    initialized_ = true;
    writeDisabledWord(static_cast<uint16_t>(config.restWord));
    return true;
  }

  void writeDisabledWord(uint16_t word) override {
    if (!initialized_) return;
    digitalWrite(kOePin, HIGH);
    digitalWrite(kLatchPin, LOW);
    for (int bit = 15; bit >= 0; --bit) {
      digitalWrite(kClockPin, LOW);
      digitalWrite(kDataPin, (word >> bit) & 1U);
      digitalWrite(kClockPin, HIGH);
    }
    digitalWrite(kLatchPin, HIGH);
  }

  void enableOutputs() override { if (initialized_) digitalWrite(kOePin, LOW); }

 private:
  bool initialized_ = false;
};

}  // namespace basu
