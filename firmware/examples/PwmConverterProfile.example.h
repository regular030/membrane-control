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
  // Lab-confirmed 595 bit 15 is LOW for STOP and HIGH for RUN. For the
  // separate isolated contact interface, set the bit to -1 and use GPIO26.
  config.pumpContactBit = 15;
  config.pumpContactPin = -1;
  config.pumpContactActiveHigh = true;
  config.shiftDataPin = 14;
  config.shiftClockPin = 13;
  config.shiftLatchPin = 12;
  config.shiftOePin = 5;
  // Installed V1-V5 and V7. Slot 5 is the absent V6 and stays false on the wire.
  config.valveBits = {{0, 1, 2, 3, 5, -1, 6}};
  // Lab Stop leaves all installed valves off. Confirm the rest of the
  // output configuration on the actual rig before enabling the profile.
  // Assign a verified pressure input before enabling physical operation.
  // GPIO34 is now pump feedback and GPIO39 is flow on the lab rig.
  config.pressure.calibrationVerified = false;
  // Certificate endpoints: 0 psi at 0.005 V, 100 psi at 5.004 V.
  // Candidate coefficients assume the documented 5:1 input divider.
  config.pressure.unitsPerVolt = 100.0 * 5.0 / (5.004 - 0.005);
  config.pressure.offset = -0.005 * config.pressure.unitsPerVolt / 5.0;
  config.pressure.minPinVolts = 0.150;  // Lower end of the production 11 dB ADC range.
  config.pressure.maxPinVolts = 5.004 / 5.0;
  config.pressure.minValue = 0;
  config.pressure.maxValue = 100;
  config.flow.source = AnalogSource::NativeAdc1;
  config.flow.pin = 39;  // SVN, through its own conditioned analog input.
  config.flow.calibrationVerified = false;
  // Certificate: 20 mL/min at 1.00 V, 50 at 2.50 V, 100 at 5.00 V.
  // The 5:1 divider puts these points at 0.20, 0.50 and 1.00 V at the ADC input.
  config.flow.unitsPerVolt = 100.0;
  config.flow.minPinVolts = 0.150;  // 13 mL/min is below the production ADC range.
  config.flow.maxPinVolts = 1.000;
  config.flow.minValue = 13;
  config.flow.maxValue = 100;
  config.pumpFeedback.source = AnalogSource::NativeAdc1;
  config.pumpFeedback.pin = 34;  // IO34, through its own conditioned analog input.
  config.pumpFeedback.calibrationVerified = false;
  config.pressureLimitPsi = 80;  // Lab-confirmed cutoff for the CWF rig.
  // Native ADC needs no I2C. If using ADS1115 instead, configure SDA/SCL and
  // reviewed input channels/calibrations; the PWM backend does not require a DAC.
  return config;
}
}  // namespace basu
