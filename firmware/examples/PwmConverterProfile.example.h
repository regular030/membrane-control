#pragma once
#include "BoardConfig.h"

// UNVERIFIED TEMPLATE. GPIO25/26/34 and the 1 kHz/12-bit settings are candidates,
// not a completed rig profile. Never approve these fields without measurements.
namespace basu {
inline BoardConfig compiledBoardConfig() {
  BoardConfig config;
  config.verifiedBoardConfig = false;
  config.safeProfileVerified = false;
  config.pumpCommandSource = PumpCommandSource::PwmConverter;
  config.pwmConverterInterfaceVerified = false;
  config.pumpPwmPin = 25;
  config.pumpPwmChannel = 0;
  config.pumpPwmFrequencyHz = 1000;
  config.pumpPwmResolutionBits = 12;
  config.pwmSettleMs = 0;  // Placeholder: measure and review a delay in 10-5000 ms.
  config.pumpContactPin = 26;  // Separate reviewed, isolated START/STOP contact.
  config.pumpContactActiveHigh = true;
  config.shiftDataPin = 14;
  config.shiftClockPin = 13;
  config.shiftLatchPin = 12;
  config.shiftOePin = 5;
  config.valveBits = {{-1, -1, -1, -1, -1, -1, -1}};
  // Safe valve states, unused levels and active polarity remain UNVERIFIED.
  config.pressure.source = AnalogSource::NativeAdc1;
  config.pressure.pin = 34;  // Requires a separately protected/scaled input.
  config.pressure.calibrationVerified = false;
  config.pressureLimitPsi = NAN;
  // Native ADC needs no I2C. If using ADS1115 instead, configure SDA/SCL and
  // reviewed input channels/calibrations; the PWM backend does not require a DAC.
  return config;
}
}  // namespace basu
