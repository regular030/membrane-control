#pragma once

#include <Arduino.h>
#include <Wire.h>
#include <driver/ledc.h>
#include "BoardConfig.h"
#include "ManualValveConfig.h"

namespace basu {

enum class SensorReadState { Never, Reading, OutOfRange, Unavailable };

inline const char* analogSourceName(AnalogSource source) {
  switch (source) {
    case AnalogSource::NativeAdc1: return "native_adc1";
    case AnalogSource::Ads1115: return "ads1115";
    default: return "disabled";
  }
}

// Diagnostics describe configured acquisition, not electrical connectivity.
// The classifier is read-only and cannot initialize a sensor or unlock outputs.
inline const char* classifySensorStatus(const BoardConfig& board, const AnalogConfig& input,
    const Reading& reading, SensorReadState acquisition, bool profileValidated, bool hardwareReady,
    bool simulation, uint32_t now) {
  if (simulation) return "simulated";
  if (input.source == AnalogSource::Disabled) return "not_configured";
  if (!board.verifiedBoardConfig || !board.safeProfileVerified) return "profile_locked";
  if (!calibrationValid(input)) return "uncalibrated";
  if (!profileValidated) return "profile_locked";
  if (!hardwareReady || acquisition == SensorReadState::Unavailable) return "hardware_unavailable";
  if (acquisition == SensorReadState::Never) return "stale";
  if (acquisition == SensorReadState::OutOfRange || !reading.valid) return "out_of_range";
  return reading.fresh(now, board.sensorMaxAgeMs) ? "reading_received" : "stale";
}

// Simulation never accesses I/O. Full pump/sensor I/O requires BoardConfig;
// the independent confirmed manual mapping initializes only the 595 relay pins.
class Hardware {
 public:
  Hardware(BoardConfig config, bool simulation) : config_(config), simulation_(simulation) {}

  bool begin() {
    if (simulation_) return true;
    if (const char* error = validateBoardConfig(config_)) { error_ = error; return false; }
    profileValidated_ = true;
    // Establish the pump's STOP contact before other outputs or I2C operations.
    digitalWrite(config_.pumpContactPin, !config_.pumpContactActiveHigh);
    pinMode(config_.pumpContactPin, OUTPUT);
    ioInitialized_ = true;
    if (config_.relayKind == RelayKind::ShiftRegister595) {
      setOe(false);
      pinMode(config_.shiftOePin, OUTPUT);
      for (int pin : {config_.shiftDataPin, config_.shiftClockPin, config_.shiftLatchPin}) {
        digitalWrite(pin, LOW);
        pinMode(pin, OUTPUT);
      }
    } else {
      for (std::size_t i = 0; i < kValveCount; ++i) {
        digitalWrite(config_.valvePins[i], config_.safeValves[i] == config_.valveActiveHigh[i]);
        pinMode(config_.valvePins[i], OUTPUT);
      }
    }
    writeValves(safeOutputs());
    if (config_.pumpCommandSource == PumpCommandSource::PwmConverter && !beginPumpPwm())
      return fail("pwm_initialization_failed");
    for (const AnalogConfig* input : inputs()) {
      if (input->source == AnalogSource::NativeAdc1) {
        pinMode(input->pin, INPUT);
        analogSetPinAttenuation(input->pin, ADC_11db);
      }
    }
    if (boardUsesI2c(config_)) {
      if (!Wire.begin(config_.i2cSdaPin, config_.i2cSclPin, 100000)) return fail("i2c_initialization_failed");
      Wire.setTimeOut(20);
      i2cInitialized_ = true;
    }
    if (config_.pumpCommandSource == PumpCommandSource::Gp8403) {
      // GP8403: zero BOTH channels before range change; never store to EEPROM.
      const uint8_t zeroBoth[] = {0, 0, 0, 0};
      const uint8_t range10V[] = {0x11};
      if (!writeRegister(config_.gp8403Address, 0x02, zeroBoth, sizeof(zeroBoth)) ||
          !writeRegister(config_.gp8403Address, 0x01, range10V, sizeof(range10V)) ||
          !writePumpCommand(0)) return fail("gp8403_initialization_failed");
    }
    for (const AnalogConfig* input : inputs()) {
      if (input->source == AnalogSource::Ads1115 && !probe(config_.ads1115Address))
        return fail("ads1115_not_responding");
    }
    ready_ = true;
    if (config_.relayKind == RelayKind::ShiftRegister595) setOe(true);
    applied_ = safeOutputs();
    safeStopIssued_ = true;
    return true;
  }

  bool beginManualValves(const ManualValveConfig& config) {
    if (const char* error = validateManualValveConfig(config)) { valveError_ = error; return false; }
    // If a full driver already owns GPIO, reuse it only when its relay interface
    // agrees with the confirmed rig. Never initialize a second competing driver.
    if (!simulation_ && ioInitialized_ && !manualInterfaceCompatible(config)) {
      valveError_ = "full relay interface differs from confirmed manual mapping";
      return false;
    }
    manualConfig_ = config;
    if (!simulation_) {
      if (!ioInitialized_) {
        digitalWrite(kManualOePin, HIGH);
        pinMode(kManualOePin, OUTPUT);
        for (int pin : {kManualDataPin, kManualClockPin, kManualLatchPin}) {
          digitalWrite(pin, LOW);
          pinMode(pin, OUTPUT);
        }
      }
      manualRelayInitialized_ = true;
      writeManualWord(0);
    }
    manualValvesReady_ = true;
    valveError_ = nullptr;
    return true;
  }

  bool applyManualValves(const std::array<bool, kValveCount>& valves) {
    if (!manualValvesReady_) return false;
    for (std::size_t index = kManualValveCount; index < kValveCount; ++index)
      if (valves[index]) { valveError_ = "unused valve slot must remain false"; return false; }
    if (simulation_) return true;
    // Normally the core requires Stop before changing modes. Also handle the
    // narrow case of a just-completed recipe whose last output is not applied yet.
    if (ioInitialized_ && (applied_.pumpPercent > 0 || pumpRunPending_)) safeStop();
    if (ioInitialized_) digitalWrite(config_.pumpContactPin, !config_.pumpContactActiveHigh);
    pumpRunPending_ = false;
    uint16_t word = 0;
    for (std::size_t index = 0; index < kManualValveCount; ++index)
      if (valves[index]) word |= static_cast<uint16_t>(1U << manualConfig_.bits[index]);
    if (!manualWordKnown_ || word != manualWord_) writeManualWord(word);
    manualModeActive_ = true;
    applied_.valves = valves;
    applied_.pumpPercent = 0;
    safeStopIssued_ = word == 0;
    return true;
  }

  bool apply(const Outputs& requested, uint32_t now = 0, bool allowPumpRun = false) {
    if (simulation_) return true;
    if (!ready_) return false;
    if (!validOutputs(requested)) return fail("invalid_outputs");
    if (requested == applied_) {
      // Only the main loop passes allowPumpRun, after the current safety tick.
      // Sensor acquisition and serial ACK paths never release this contact.
      if (pumpRunPending_ && allowPumpRun &&
          static_cast<uint32_t>(now - pumpCommandChangedMs_) >= config_.pwmSettleMs) {
        pumpRunPending_ = false;
        digitalWrite(config_.pumpContactPin, config_.pumpContactActiveHigh);
      }
      return true;
    }
    // Disable pump while changing valves/speed; recipe must still include any
    // required hydraulic settling delays as explicit steps.
    digitalWrite(config_.pumpContactPin, !config_.pumpContactActiveHigh);
    pumpRunPending_ = false;
    manualModeActive_ = false;
    manualWordKnown_ = false;
    safeStopIssued_ = false;
    writeValves(requested);
    if (!writePumpCommand(requested.pumpPercent))
      return fail(config_.pumpCommandSource == PumpCommandSource::Gp8403 ? "gp8403_write_failed" : "pwm_write_failed");
    if (requested.pumpPercent > 0) {
      if (config_.pumpCommandSource == PumpCommandSource::PwmConverter) {
        pumpCommandChangedMs_ = now;
        pumpRunPending_ = true;
      } else digitalWrite(config_.pumpContactPin, config_.pumpContactActiveHigh);
    }
    applied_ = requested;
    safeStopIssued_ = requested == safeOutputs();
    return true;
  }

  // Contact STOP precedes PWM zero, valve changes or I2C, so a stuck bus cannot
  // prevent the software issuing STOP. Hardware must independently fail safe.
  void safeStop() {
    pumpRunPending_ = false;
    if (simulation_ || (!ioInitialized_ && !manualRelayInitialized_)) return;
    if (ioInitialized_) digitalWrite(config_.pumpContactPin, !config_.pumpContactActiveHigh);
    if (pwmInitialized_ && !writePumpPwmDuty(0) && ready_) {
      ready_ = false;
      error_ = "pwm_stop_failed";
    }
    if (manualRelayInitialized_ && (!ioInitialized_ || manualModeActive_)) {
      if (!manualWordKnown_ || manualWord_ != 0) writeManualWord(0);
      manualModeActive_ = false;
      safeStopIssued_ = true;
      applied_ = Outputs{};  // Manual rest is all LOW, independent of the full process profile.
      return;
    }
    if (safeStopIssued_) return;
    safeStopIssued_ = true;
    writeValves(safeOutputs());
    manualWordKnown_ = false;
    if (config_.pumpCommandSource == PumpCommandSource::Gp8403 && i2cInitialized_) writePumpCommand(0);
    applied_ = safeOutputs();
  }

  void sample(uint32_t now, bool valveOnly = false) {
    if (simulation_ || !ready_) return;
    if (!valveOnly && config_.pumpCommandSource == PumpCommandSource::Gp8403 &&
        static_cast<uint32_t>(now - lastHealthMs_) >= 1000) {
      lastHealthMs_ = now;
      if (!probe(config_.gp8403Address)) { fail("gp8403_disconnected"); return; }
    }
    if (static_cast<uint32_t>(now - lastNativeSampleMs_) >= 100) {
      lastNativeSampleMs_ = now;
      auto configurations = inputs();
      auto destinations = readings();
      for (std::size_t i = 0; i < configurations.size(); ++i) {
        if (configurations[i]->source == AnalogSource::NativeAdc1) {
          *destinations[i] = calibratedReading(*configurations[i], analogReadMilliVolts(configurations[i]->pin) / 1000.0, now);
          sensorReadState_[i] = destinations[i]->valid ? SensorReadState::Reading : SensorReadState::OutOfRange;
        }
      }
    }
    sampleAds(now);
  }

  bool ready() const { return ready_; }
  bool valveControlReady() const { return manualValvesReady_; }
  const std::array<int, kManualValveCount>& manualValveBits() const { return manualConfig_.bits; }
  const char* valveError() const { return valveError_ ? valveError_ : "valve_control_not_ready"; }
  const char* error() const { return error_; }
  const Measurements& measurements() const { return measurements_; }
  const char* sensorStatus(std::size_t index, uint32_t now) const {
    const auto configured = inputs();
    const std::array<const Reading*, 3> measured{{&measurements_.pressure, &measurements_.flow, &measurements_.pumpFeedback}};
    if (index >= configured.size()) return "not_configured";
    return classifySensorStatus(config_, *configured[index], *measured[index], sensorReadState_[index],
                                profileValidated_, ready_, simulation_, now);
  }

 private:
  static constexpr int kManualDataPin = 14;
  static constexpr int kManualClockPin = 13;
  static constexpr int kManualLatchPin = 12;
  static constexpr int kManualOePin = 5;
  bool manualInterfaceCompatible(const ManualValveConfig& manual) const {
    if (config_.relayKind != RelayKind::ShiftRegister595 || config_.shiftBitCount != 16 ||
        config_.shiftDataPin != kManualDataPin || config_.shiftClockPin != kManualClockPin ||
        config_.shiftLatchPin != kManualLatchPin || config_.shiftOePin != kManualOePin ||
        !config_.shiftOeActiveLow || !config_.shiftMsbFirst || config_.shiftUnusedLevels != 0) return false;
    for (std::size_t index = 0; index < kValveCount; ++index) {
      if (config_.safeValves[index] || !config_.valveActiveHigh[index]) return false;
      if (index < kManualValveCount && config_.valveBits[index] != manual.bits[index]) return false;
    }
    return true;
  }
  void writeManualWord(uint16_t word) {
    digitalWrite(kManualOePin, HIGH);
    digitalWrite(kManualLatchPin, LOW);
    for (int bit = 15; bit >= 0; --bit) {
      digitalWrite(kManualClockPin, LOW);
      digitalWrite(kManualDataPin, (word >> bit) & 1U);
      digitalWrite(kManualClockPin, HIGH);
    }
    digitalWrite(kManualLatchPin, HIGH);
    digitalWrite(kManualOePin, LOW);  // Hold the commanded levels, including all-off LOW.
    manualWord_ = word;
    manualWordKnown_ = true;
  }
  std::array<const AnalogConfig*, 3> inputs() const {
    return {{&config_.pressure, &config_.flow, &config_.pumpFeedback}};
  }
  std::array<Reading*, 3> readings() {
    return {{&measurements_.pressure, &measurements_.flow, &measurements_.pumpFeedback}};
  }
  Outputs safeOutputs() const { Outputs safe; safe.valves = config_.safeValves; return safe; }
  bool fail(const char* reason) {
    error_ = reason;
    ready_ = false;
    safeStop();
    return false;
  }
  void setOe(bool enabled) {
    digitalWrite(config_.shiftOePin, config_.shiftOeActiveLow ? !enabled : enabled);
  }
  void writeValves(const Outputs& outputs) {
    if (config_.relayKind == RelayKind::DirectGpio) {
      for (std::size_t i = 0; i < kValveCount; ++i)
        digitalWrite(config_.valvePins[i], outputs.valves[i] == config_.valveActiveHigh[i]);
      return;
    }
    const uint16_t levels = shiftLevels(config_, outputs);
    digitalWrite(config_.shiftLatchPin, LOW);
    for (int serialIndex = 0; serialIndex < config_.shiftBitCount; ++serialIndex) {
      const int bit = config_.shiftMsbFirst ? config_.shiftBitCount - 1 - serialIndex : serialIndex;
      digitalWrite(config_.shiftClockPin, LOW);
      digitalWrite(config_.shiftDataPin, (levels >> bit) & 1U);
      digitalWrite(config_.shiftClockPin, HIGH);
    }
    digitalWrite(config_.shiftLatchPin, HIGH);
  }
  bool probe(uint8_t address) {
    Wire.beginTransmission(address);
    return Wire.endTransmission() == 0;
  }
  bool writeRegister(uint8_t address, uint8_t reg, const uint8_t* bytes, std::size_t count) {
    Wire.beginTransmission(address);
    Wire.write(reg);
    Wire.write(bytes, count);
    return Wire.endTransmission() == 0;
  }
  bool readRegister16(uint8_t address, uint8_t reg, uint16_t& value) {
    Wire.beginTransmission(address);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0 || Wire.requestFrom(address, static_cast<uint8_t>(2)) != 2) return false;
    value = static_cast<uint16_t>((Wire.read() << 8) | Wire.read());
    return true;
  }
  bool beginPumpPwm() {
    // Hold LOW as GPIO before attaching the peripheral. Preload zero duty on
    // the dedicated channel, which may have retained a previous timer value.
    digitalWrite(config_.pumpPwmPin, LOW);
    pinMode(config_.pumpPwmPin, OUTPUT);
    const double actualHz = ledcSetup(config_.pumpPwmChannel, config_.pumpPwmFrequencyHz,
                                      config_.pumpPwmResolutionBits);
    if (!std::isfinite(actualHz) || actualHz < 22 || actualHz > 20000) return false;
    // Arduino's ledcAttachPin/ledcWrite are void and discard driver errors.
    // Use its documented channel/timer mapping with checked ESP-IDF calls.
    ledc_channel_config_t channel{};
    channel.gpio_num = config_.pumpPwmPin;
    channel.speed_mode = pwmMode();
    channel.channel = pwmChannel();
    channel.intr_type = LEDC_INTR_DISABLE;
    channel.timer_sel = static_cast<ledc_timer_t>((config_.pumpPwmChannel / 2) % 4);
    channel.duty = 0;  // Explicit zero, never attach a stale global duty value.
    channel.hpoint = 0;
    if (ledc_channel_config(&channel) != ESP_OK) {
      ledc_stop(pwmMode(), pwmChannel(), 0);
      return false;
    }
    pwmInitialized_ = true;
    return true;
  }
  ledc_mode_t pwmMode() const { return static_cast<ledc_mode_t>(config_.pumpPwmChannel / 8); }
  ledc_channel_t pwmChannel() const { return static_cast<ledc_channel_t>(config_.pumpPwmChannel % 8); }
  bool writePumpPwmDuty(uint32_t duty) {
    if (ledc_set_duty(pwmMode(), pwmChannel(), duty) != ESP_OK ||
        ledc_update_duty(pwmMode(), pwmChannel()) != ESP_OK) {
      ledc_stop(pwmMode(), pwmChannel(), 0);  // Best effort; STOP contact stays independent.
      return false;
    }
    return true;
  }
  bool writePumpCommand(double percent) {
    if (!validOutputs(Outputs{{}, percent})) return false;
    if (config_.pumpCommandSource == PumpCommandSource::PwmConverter) {
      uint32_t duty = 0;
      if (!pwmInitialized_ || !encodePumpPwmDuty(percent, config_.pumpPwmResolutionBits, duty)) return false;
      return writePumpPwmDuty(duty);  // Register success is not measured converter feedback.
    }
    if (!i2cInitialized_) return false;
    const uint32_t millivolts = static_cast<uint32_t>(std::lround(percent * 100.0));
    const uint16_t code = static_cast<uint16_t>((millivolts * 4095U / 10000U) << 4);
    const uint8_t bytes[] = {static_cast<uint8_t>(code), static_cast<uint8_t>(code >> 8)};
    return writeRegister(config_.gp8403Address, config_.gp8403Channel == 0 ? 0x02 : 0x04, bytes, sizeof(bytes));
  }
  void sampleAds(uint32_t now) {
    auto configurations = inputs();
    auto destinations = readings();
    if (adsPending_) {
      if (static_cast<uint32_t>(now - adsStartedMs_) < 9) return;
      uint16_t conversionConfig = 0;
      uint16_t raw = 0;
      if (!readRegister16(config_.ads1115Address, 0x01, conversionConfig)) {
        destinations[adsInputIndex_]->valid = false;
        sensorReadState_[adsInputIndex_] = SensorReadState::Unavailable;
        adsPending_ = false;
        return;
      }
      if (!(conversionConfig & 0x8000)) {
        if (static_cast<uint32_t>(now - adsStartedMs_) > 30) {
          destinations[adsInputIndex_]->valid = false;
          sensorReadState_[adsInputIndex_] = SensorReadState::Unavailable;
          adsPending_ = false;
        }
        return;
      }
      if (readRegister16(config_.ads1115Address, 0x00, raw)) {
        const double volts = static_cast<int16_t>(raw) * (4.096 / 32768.0);
        *destinations[adsInputIndex_] = calibratedReading(*configurations[adsInputIndex_], volts, now);
        sensorReadState_[adsInputIndex_] = destinations[adsInputIndex_]->valid ?
            SensorReadState::Reading : SensorReadState::OutOfRange;
      } else {
        destinations[adsInputIndex_]->valid = false;
        sensorReadState_[adsInputIndex_] = SensorReadState::Unavailable;
      }
      adsPending_ = false;
      adsInputIndex_ = (adsInputIndex_ + 1) % configurations.size();
    }
    for (std::size_t attempts = 0; attempts < configurations.size(); ++attempts) {
      const auto& input = *configurations[adsInputIndex_];
      if (input.source == AnalogSource::Ads1115) {
        // TI ADS1115: OS=start, MUX=single-ended AINx, PGA=+/-4.096 V,
        // MODE=single-shot, DR=128 SPS, comparator disabled. Inputs still must
        // remain inside the actual 3.3 V supply rails; PGA range is not tolerance.
        const uint16_t configWord = static_cast<uint16_t>(0x8383U | ((4U + input.adsChannel) << 12));
        const uint8_t bytes[] = {static_cast<uint8_t>(configWord >> 8), static_cast<uint8_t>(configWord)};
        if (writeRegister(config_.ads1115Address, 0x01, bytes, sizeof(bytes))) {
          adsStartedMs_ = now;
          adsPending_ = true;
        } else {
          destinations[adsInputIndex_]->valid = false;
          sensorReadState_[adsInputIndex_] = SensorReadState::Unavailable;
        }
        break;
      }
      adsInputIndex_ = (adsInputIndex_ + 1) % configurations.size();
    }
  }

  BoardConfig config_;
  bool simulation_;
  ManualValveConfig manualConfig_;
  bool manualValvesReady_ = false;
  bool manualRelayInitialized_ = false;
  bool manualModeActive_ = false;
  bool manualWordKnown_ = false;
  uint16_t manualWord_ = 0;
  const char* valveError_ = "valve_control_not_ready";
  bool profileValidated_ = false;
  bool ioInitialized_ = false;
  bool i2cInitialized_ = false;
  bool pwmInitialized_ = false;
  bool pumpRunPending_ = false;
  uint32_t pumpCommandChangedMs_ = 0;
  bool ready_ = false;
  bool safeStopIssued_ = false;
  const char* error_ = "hardware_not_initialized";
  Outputs applied_;
  Measurements measurements_;
  std::array<SensorReadState, 3> sensorReadState_{{SensorReadState::Never, SensorReadState::Never, SensorReadState::Never}};
  uint32_t lastNativeSampleMs_ = 0;
  uint32_t lastHealthMs_ = 0;
  uint32_t adsStartedMs_ = 0;
  std::size_t adsInputIndex_ = 0;
  bool adsPending_ = false;
};

}  // namespace basu
