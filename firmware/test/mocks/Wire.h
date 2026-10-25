#pragma once
#include <cstddef>
#include <cstdint>

struct FakeWire {
  unsigned beginCount = 0;
  unsigned transactionCount = 0;
  bool failNext = false;
  void reset() { beginCount = 0; transactionCount = 0; failNext = false; }
  bool begin(int, int, uint32_t) { ++beginCount; return true; }
  void setTimeOut(int) {}
  void beginTransmission(uint8_t) { ++transactionCount; }
  std::size_t write(uint8_t) { return 1; }
  std::size_t write(const uint8_t*, std::size_t count) { return count; }
  uint8_t endTransmission(bool = true) {
    if (failNext) { failNext = false; return 2; }
    return 0;
  }
  uint8_t requestFrom(uint8_t, uint8_t) { return 2; }
  int read() { return 0; }
};
inline FakeWire Wire;
