#pragma once

#include "ControlCore.h"

namespace basu {

enum class RelayKind { DirectGpio, ShiftRegister595 };
enum class AnalogSource { Disabled, NativeAdc1, Ads1115 };
enum class PumpCommandSource { Gp8403, PwmConverter };

struct AnalogConfig {
  AnalogSource source = AnalogSource::Disabled;
  int pin = -1;
  int adsChannel = -1;
  bool calibrationVerified = false;
  double unitsPerVolt = 1;
  double offset = 0;
  double minPinVolts = 0;
  double maxPinVolts = 3.0;
  double minValue = -1000000;
  double maxValue = 1000000;
  bool rejectRails = true;
};

struct BoardConfig {
  // Default is the user's 16-channel candidate's DRIVER TYPE, not its unknown pin map.
  bool verifiedBoardConfig = false;
  bool safeProfileVerified = false;
  RelayKind relayKind = RelayKind::ShiftRegister595;
  std::array<int, kValveCount> valvePins{{-1, -1, -1, -1, -1, -1, -1}};
  std::array<int, kValveCount> valveBits{{-1, -1, -1, -1, -1, -1, -1}};
  std::array<bool, kValveCount> valveActiveHigh{{true, true, true, true, true, true, true}};
  std::array<bool, kValveCount> safeValves{};
  int shiftDataPin = -1;
  int shiftClockPin = -1;
  int shiftLatchPin = -1;
  int shiftOePin = -1;
  bool shiftOeActiveLow = true;
  uint8_t shiftBitCount = 16;
  bool shiftMsbFirst = true;
  uint16_t shiftUnusedLevels = 0;
  int pumpContactPin = -1;
  bool pumpContactActiveHigh = true;
  int i2cSdaPin = -1;
  int i2cSclPin = -1;
  uint8_t gp8403Address = 0x58;
  uint8_t gp8403Channel = 0;
  bool gp8403InterfaceVerified = false;
  PumpCommandSource pumpCommandSource = PumpCommandSource::Gp8403;
  bool pwmConverterInterfaceVerified = false;
  int pumpPwmPin = -1;
  int pumpPwmChannel = 0;
  uint32_t pumpPwmFrequencyHz = 1000;
  int pumpPwmResolutionBits = 12;
  uint32_t pwmSettleMs = 0;  // No reviewed settling time is supplied by default.
  uint8_t ads1115Address = 0x48;
  AnalogConfig pressure;
  AnalogConfig flow;
  AnalogConfig pumpFeedback;
  double pressureLimitPsi = NAN;
  uint32_t sensorMaxAgeMs = 1000;
};

inline bool outputCapablePin(int pin) {
  // Classic ESP32 only. Flash pins and UART0 pins are unavailable to this profile.
  return pin >= 0 && pin <= 33 && !(pin >= 6 && pin <= 11) && pin != 1 && pin != 3 &&
         pin != 20 && pin != 24 && !(pin >= 28 && pin <= 31);
}

inline bool calibrationValid(const AnalogConfig& input) {
  return input.calibrationVerified && std::isfinite(input.unitsPerVolt) && input.unitsPerVolt != 0 &&
         std::isfinite(input.offset) && std::isfinite(input.minPinVolts) &&
         std::isfinite(input.maxPinVolts) && input.minPinVolts >= 0 &&
         input.maxPinVolts <= 3.3 && input.maxPinVolts > input.minPinVolts &&
         std::isfinite(input.minValue) && std::isfinite(input.maxValue) &&
         input.maxValue > input.minValue;
}

inline bool boardUsesAds(const BoardConfig& config) {
  return config.pressure.source == AnalogSource::Ads1115 || config.flow.source == AnalogSource::Ads1115 ||
         config.pumpFeedback.source == AnalogSource::Ads1115;
}

inline bool boardUsesI2c(const BoardConfig& config) {
  return config.pumpCommandSource == PumpCommandSource::Gp8403 || boardUsesAds(config);
}

inline const char* pumpCommandSourceName(PumpCommandSource source) {
  switch (source) {
    case PumpCommandSource::Gp8403: return "gp8403";
    case PumpCommandSource::PwmConverter: return "pwm_converter";
    default: return "invalid";
  }
}

inline bool encodePumpPwmDuty(double percent, int resolutionBits, uint32_t& duty) {
  if (!std::isfinite(percent) || percent < 0 || percent > 100 || resolutionBits < 8 || resolutionBits > 16)
    return false;
  // ESP-IDF accepts 2^resolution for constant HIGH at these 8-16 bit widths,
  // matching Arduino-ESP32's special handling of a full-scale analogWrite.
  const uint32_t maximum = 1U << resolutionBits;
  // Round to nearest code and saturate the register value to its configured width.
  duty = std::min(maximum, static_cast<uint32_t>(std::lround(percent * maximum / 100.0)));
  return true;
}

inline const char* validateBoardConfig(const BoardConfig& config) {
  if (!config.verifiedBoardConfig) return "board profile has not been verified";
  if (!config.safeProfileVerified || !std::isfinite(config.pressureLimitPsi) ||
      config.pressureLimitPsi <= 0 || config.sensorMaxAgeMs < 100 || config.sensorMaxAgeMs > 3000)
    return "verified safe states, positive pressure limit and sensor age are required";
  if (config.pumpCommandSource == PumpCommandSource::Gp8403) {
    if (!config.gp8403InterfaceVerified || config.gp8403Address < 0x58 ||
        config.gp8403Address > 0x5f || config.gp8403Channel > 1)
      return "GP8403 interface is not verified";
  } else if (config.pumpCommandSource == PumpCommandSource::PwmConverter) {
    if (!config.pwmConverterInterfaceVerified || config.pumpPwmChannel < 0 || config.pumpPwmChannel > 15 ||
        config.pumpPwmFrequencyHz < 22 || config.pumpPwmFrequencyHz > 20000 ||
        config.pumpPwmResolutionBits < 8 || config.pumpPwmResolutionBits > 16 ||
        config.pwmSettleMs < 10 || config.pwmSettleMs > 5000)
      return "PWM converter interface, channel, frequency or resolution is not verified";
  } else return "unknown pump command source";
  if (config.pressure.source == AnalogSource::Disabled) return "physical operation requires pressure input";
  std::array<bool, 40> used{};
  // On the selected X16 PCB GPIO4 may serve the shift-register clear input.
  // New PWM profiles must leave it alone; legacy GP8403 profiles are unchanged.
  if (config.pumpCommandSource == PumpCommandSource::PwmConverter) used[4] = true;
  auto reserve = [&used](int pin) {
    if (!outputCapablePin(pin) || used[pin]) return false;
    used[pin] = true;
    return true;
  };
  if (!reserve(config.pumpContactPin)) return "pump contact pin invalid, reserved or conflicting";
  if (boardUsesI2c(config) || config.i2cSdaPin != -1 || config.i2cSclPin != -1) {
    if (!reserve(config.i2cSdaPin) || !reserve(config.i2cSclPin))
      return "I2C pins invalid or conflicting";
  }
  if (config.pumpCommandSource == PumpCommandSource::PwmConverter) {
    if (config.pumpPwmPin == 5 || config.pumpPwmPin == 12 || config.pumpPwmPin == 13 ||
        config.pumpPwmPin == 14 || !reserve(config.pumpPwmPin))
      return "PWM output pin invalid, reserved or conflicting";
  }
  if (config.relayKind == RelayKind::DirectGpio) {
    for (int pin : config.valvePins) if (!reserve(pin)) return "valve GPIO invalid or conflicting";
  } else if (config.relayKind == RelayKind::ShiftRegister595) {
    if (config.shiftBitCount != 8 && config.shiftBitCount != 16)
      return "74HC595 driver supports an explicit 8 or 16 bit chain";
    if (!reserve(config.shiftDataPin) || !reserve(config.shiftClockPin) ||
        !reserve(config.shiftLatchPin) || !reserve(config.shiftOePin))
      return "74HC595 pins invalid or conflicting";
    std::array<bool, 16> mapped{};
    for (int bit : config.valveBits) {
      if (bit < 0 || bit >= config.shiftBitCount || mapped[bit]) return "74HC595 valve bits invalid or duplicated";
      mapped[bit] = true;
    }
  } else return "unknown relay interface";
  bool usesAds = false;
  std::array<bool, 4> adsChannels{};
  for (const AnalogConfig* input : {&config.pressure, &config.flow, &config.pumpFeedback}) {
    if (input->source == AnalogSource::Disabled) continue;
    if (!calibrationValid(*input)) return "sensor calibration or protected pin voltage range invalid";
    if (input->source == AnalogSource::NativeAdc1) {
      if (input->pin < 32 || input->pin > 39 || used[input->pin]) return "ADC1 pin invalid or conflicting";
      used[input->pin] = true;
    } else if (input->source == AnalogSource::Ads1115) {
      usesAds = true;
      if (input->adsChannel < 0 || input->adsChannel > 3 || adsChannels[input->adsChannel])
        return "ADS1115 channel invalid or duplicated";
      adsChannels[input->adsChannel] = true;
    } else return "unknown analog input source";
  }
  if (usesAds && (config.ads1115Address < 0x48 || config.ads1115Address > 0x4b))
    return "ADS1115 address must be 0x48-0x4b";
  return nullptr;
}

inline uint16_t shiftLevels(const BoardConfig& config, const Outputs& outputs) {
  uint16_t levels = config.shiftUnusedLevels;
  for (std::size_t i = 0; i < kValveCount; ++i) {
    const bool high = outputs.valves[i] == config.valveActiveHigh[i];
    const uint16_t bit = static_cast<uint16_t>(1U << config.valveBits[i]);
    levels = high ? (levels | bit) : (levels & ~bit);
  }
  return levels;
}

inline Reading calibratedReading(const AnalogConfig& config, double pinVolts, uint32_t now) {
  Reading reading;
  reading.acquiredMs = now;
  reading.value = pinVolts * config.unitsPerVolt + config.offset;
  reading.valid = calibrationValid(config) && std::isfinite(pinVolts) &&
                  pinVolts >= config.minPinVolts && pinVolts <= config.maxPinVolts &&
                  reading.value >= config.minValue && reading.value <= config.maxValue;
  if (config.rejectRails && (pinVolts <= 0.001 || pinVolts >= 3.299)) reading.valid = false;
  return reading;
}

}  // namespace basu
