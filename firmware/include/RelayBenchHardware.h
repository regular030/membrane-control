#pragma once

#include <Arduino.h>
#include "RelayBenchCore.h"

namespace basu {

// Candidate wiring from the seller's ESP32_X16_TEST sample, for unloaded bench
// identification only. GPIO4/SRCLR is deliberately untouched. OE disabled means
// high impedance at the 595, not verified relay-contact or coil feedback.
class RelayBenchHardware final : public RelayBenchIo {
 public:
  static constexpr int kDataPin = 14;
  static constexpr int kClockPin = 13;
  static constexpr int kLatchPin = 12;
  static constexpr int kOePin = 5;

  void begin() {
    // Set the inactive latch value BEFORE making OE an output.
    digitalWrite(kOePin, HIGH);
    pinMode(kOePin, OUTPUT);
    for (int pin : {kDataPin, kClockPin, kLatchPin}) {
      digitalWrite(pin, LOW);
      pinMode(pin, OUTPUT);
    }
    initialized_ = true;
    writeDisabledWord(0);
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

  void enableOutputs() override {
    if (initialized_) digitalWrite(kOePin, LOW);
  }

 private:
  bool initialized_ = false;
};

}  // namespace basu
