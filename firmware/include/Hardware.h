#pragma once

#include <Arduino.h>
#include <Wire.h>
#include "BoardConfig.h"

namespace basu {

// This entire adapter is dormant in the default simulation build. There are no
// GPIO/I2C accesses before validateBoardConfig() and the compiled approval gate.
class Hardware {
 public:
  Hardware(BoardConfig config, bool simulation) : config_(config), simulation_(simulation) {}

  bool begin() {
    if (simulation_) return true;
    if (const char* error = validateBoardConfig(config_)) { error_ = error; return false; }
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
    for (const AnalogConfig* input : inputs()) {
      if (input->source == AnalogSource::NativeAdc1) {
        pinMode(input->pin, INPUT);
        analogSetPinAttenuation(input->pin, ADC_11db);
      }
    }
    if (!Wire.begin(config_.i2cSdaPin, config_.i2cSclPin, 100000)) return fail("i2c_initialization_failed");
    Wire.setTimeOut(20);
    i2cInitialized_ = true;
    // Manufacturer GP8403 register mapping: range register 0x01 (0x11=10 V),
    // channel registers 0x02/0x04, left-aligned 12-bit little-endian output.
    // Zero BOTH channels before range change; never call EEPROM store().
    const uint8_t zeroBoth[] = {0, 0, 0, 0};
    const uint8_t range10V[] = {0x11};
    if (!writeRegister(config_.gp8403Address, 0x02, zeroBoth, sizeof(zeroBoth)) ||
        !writeRegister(config_.gp8403Address, 0x01, range10V, sizeof(range10V)) ||
        !writePumpVoltage(0)) return fail("gp8403_initialization_failed");
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

  bool apply(const Outputs& requested) {
    if (simulation_) return true;
    if (!ready_) return false;
    if (requested == applied_) return true;
    // Disable pump while changing valves/speed; recipe must still include any
    // required hydraulic settling delays as explicit steps.
    digitalWrite(config_.pumpContactPin, !config_.pumpContactActiveHigh);
    safeStopIssued_ = false;
    writeValves(requested);
    if (!writePumpVoltage(requested.pumpPercent)) return fail("gp8403_write_failed");
    if (requested.pumpPercent > 0) digitalWrite(config_.pumpContactPin, config_.pumpContactActiveHigh);
    applied_ = requested;
    safeStopIssued_ = requested == safeOutputs();
    return true;
  }

  // Best-effort physical stop: contact STOP precedes I2C, so a stuck bus cannot
  // prevent the software issuing STOP. Hardware must independently fail safe.
  void safeStop() {
    if (simulation_ || !ioInitialized_) return;
    digitalWrite(config_.pumpContactPin, !config_.pumpContactActiveHigh);
    if (safeStopIssued_) return;
    safeStopIssued_ = true;
    writeValves(safeOutputs());
    if (i2cInitialized_) writePumpVoltage(0);
    applied_ = safeOutputs();
  }

  void sample(uint32_t now) {
    if (simulation_ || !ready_) return;
    if (static_cast<uint32_t>(now - lastHealthMs_) >= 1000) {
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
        }
      }
    }
    sampleAds(now);
  }

  bool ready() const { return ready_; }
  const char* error() const { return error_; }
  const Measurements& measurements() const { return measurements_; }

 private:
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
  bool writePumpVoltage(double percent) {
    if (!i2cInitialized_ || !validOutputs(Outputs{{}, percent})) return false;
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
        adsPending_ = false;
        return;
      }
      if (!(conversionConfig & 0x8000)) {
        if (static_cast<uint32_t>(now - adsStartedMs_) > 30) {
          destinations[adsInputIndex_]->valid = false;
          adsPending_ = false;
        }
        return;
      }
      if (readRegister16(config_.ads1115Address, 0x00, raw)) {
        const double volts = static_cast<int16_t>(raw) * (4.096 / 32768.0);
        *destinations[adsInputIndex_] = calibratedReading(*configurations[adsInputIndex_], volts, now);
      } else destinations[adsInputIndex_]->valid = false;
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
        } else destinations[adsInputIndex_]->valid = false;
        break;
      }
      adsInputIndex_ = (adsInputIndex_ + 1) % configurations.size();
    }
  }

  BoardConfig config_;
  bool simulation_;
  bool ioInitialized_ = false;
  bool i2cInitialized_ = false;
  bool ready_ = false;
  bool safeStopIssued_ = false;
  const char* error_ = "hardware_not_initialized";
  Outputs applied_;
  Measurements measurements_;
  uint32_t lastNativeSampleMs_ = 0;
  uint32_t lastHealthMs_ = 0;
  uint32_t adsStartedMs_ = 0;
  std::size_t adsInputIndex_ = 0;
  bool adsPending_ = false;
};

}  // namespace basu
