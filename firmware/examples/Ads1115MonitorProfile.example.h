#pragma once
#include "BoardConfig.h"

namespace basu {
inline BoardConfig compiledBoardConfig() {
  BoardConfig config;
  config.verifiedBoardConfig = true;
  config.safeProfileVerified = true;  // Confirmed manual relay setup, all valves off at Stop.
  config.pumpCommandSource = PumpCommandSource::PwmConverter;
  config.pumpPwmPin = 25;
  config.pumpContactBit = 15;
  config.i2cSdaPin = 33;
  config.i2cSclPin = 27;
  config.ads1115Address = 0x48;

  config.pressure.source = AnalogSource::Ads1115;
  config.pressure.adsChannel = 0;
  config.pressure.calibrationVerified = false;  // Keep pump locked until pressure is checked against the gauge.
  config.pressureLimitPsi = 80;

  config.flow.source = AnalogSource::Ads1115;
  config.flow.adsChannel = 1;
  config.flow.calibrationVerified = true;
  // Certificate nominal slope through the 5:1 divider: 100 mL/min at 1 V.
  config.flow.unitsPerVolt = 100;
  config.flow.minPinVolts = 0.130;
  config.flow.maxPinVolts = 1.000;
  config.flow.minValue = 13;
  config.flow.maxValue = 100;

  config.pumpFeedback.source = AnalogSource::Ads1115;
  config.pumpFeedback.adsChannel = 2;
  return config;
}
}  // namespace basu
