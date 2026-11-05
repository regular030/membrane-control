#pragma once
#include "BoardConfig.h"

// UNVERIFIED TEMPLATE. These are candidate pins and timer settings. The shipped
// profile remains locked until the lab confirms wiring, calibration and safety.
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
  // Assign the tested active-high spare 595 bit to pumpContactBit. For the
  // separate isolated contact interface, leave the bit at -1 and use GPIO26.
  config.pumpContactBit = -1;
  config.pumpContactPin = -1;
  config.pumpContactActiveHigh = true;
  config.shiftDataPin = 14;
  config.shiftClockPin = 13;
  config.shiftLatchPin = 12;
  config.shiftOePin = 5;
  // Installed V1-V5 and V7. Slot 5 is the absent V6 and stays false on the wire.
  config.valveBits = {{0, 1, 2, 3, 5, -1, 6}};
  // Safe valve states, unused levels and active polarity remain UNVERIFIED.
  config.pressure.source = AnalogSource::NativeAdc1;
  config.pressure.pin = 34;  // Requires a separately protected/scaled input.
  config.pressure.calibrationVerified = false;
  config.flow.source = AnalogSource::NativeAdc1;
  config.flow.pin = 36;  // SVP, through its own conditioned analog input.
  config.flow.calibrationVerified = false;
  config.pumpFeedback.source = AnalogSource::NativeAdc1;
  config.pumpFeedback.pin = 39;  // SVN, through its own conditioned analog input.
  config.pumpFeedback.calibrationVerified = false;
  config.pressureLimitPsi = NAN;
  // Native ADC needs no I2C. If using ADS1115 instead, configure SDA/SCL and
  // reviewed input channels/calibrations; the PWM backend does not require a DAC.
  return config;
}
}  // namespace basu
