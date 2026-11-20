#pragma once
#include "BoardConfig.h"

// Current lab rig: the replacement ESP32 owns the relays, pump and ADS1115.
// Valve path, RUN contact, 50% command and Stop state were confirmed in the lab.
namespace basu {
inline BoardConfig compiledBoardConfig() {
  BoardConfig config;
  config.verifiedBoardConfig = true;
  config.safeProfileVerified = true;
  config.shiftDataPin = 14;
  config.shiftClockPin = 13;
  config.shiftLatchPin = 12;
  config.shiftOePin = 5;
  config.valveBits = {{0, 1, 2, 3, 5, -1, 6}};
  config.pumpCommandSource = PumpCommandSource::PwmConverter;
  config.pwmConverterInterfaceVerified = true;
  config.pumpPwmPin = 33;
  config.pwmSettleMs = 1500;
  config.pumpContactBit = 15;
  config.pumpLimits.maxPercent = 50;
  config.pumpLimits.requiredValves = std::array<bool, kValveCount>{{true, false, true, false, false, false, false}};
  config.i2cSdaPin = 22;
  config.i2cSclPin = 21;
  config.i2cClockHz = 25000;
  config.ads1115Address = 0x48;
  config.pressureLimitPsi = 80;

  config.pressure.source = AnalogSource::Ads1115;
  config.pressure.adsChannel = 3;
  config.pressure.calibrationVerified = true;
  // Certificate: 0 psi at 0.005 V and 100 psi at 5.004 V, before 5:1 division.
  config.pressure.unitsPerVolt = 500.0 / (5.004 - 0.005);
  config.pressure.offset = -0.001 * config.pressure.unitsPerVolt;
  config.pressure.minPinVolts = 0;
  config.pressure.maxPinVolts = 1.05;
  config.pressure.minValue = 0;
  config.pressure.maxValue = 105;
  config.pressure.rejectRails = false;
  config.pressure.adsZeroToleranceVolts = 0.002;

  config.flow.source = AnalogSource::Ads1115;
  config.flow.adsChannel = 1;
  config.flow.calibrationVerified = true;
  config.flow.unitsPerVolt = 100;
  config.flow.minPinVolts = 0;
  config.flow.maxPinVolts = 1.05;
  config.flow.minValue = 0;
  config.flow.maxValue = 105;
  config.flow.rejectRails = false;
  config.flow.adsZeroToleranceVolts = 0.002;

  config.pumpFeedback.source = AnalogSource::Ads1115;
  config.pumpFeedback.adsChannel = 2;
  config.pumpFeedback.calibrationVerified = true;
  config.pumpFeedback.unitsPerVolt = 5;
  config.pumpFeedback.minPinVolts = 0;
  config.pumpFeedback.maxPinVolts = 2.1;
  config.pumpFeedback.minValue = 0;
  config.pumpFeedback.maxValue = 10.5;
  config.pumpFeedback.rejectRails = false;
  config.pumpFeedback.adsZeroToleranceVolts = 0.001;
  return config;
}
}  // namespace basu
