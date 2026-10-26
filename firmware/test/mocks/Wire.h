#pragma once
#include <cstddef>
#include <cstdint>
#include <vector>

struct FakeWire {
  unsigned beginCount = 0;
  unsigned transactionCount = 0;
  bool failNext = false;
  bool beginSucceeds = true;
  int failingAddress = -1;
  std::vector<uint8_t> addresses;
  std::vector<std::vector<uint8_t>> writes;
  void reset() {
    beginCount = 0; transactionCount = 0; failNext = false; beginSucceeds = true;
    failingAddress = -1; addresses.clear(); writes.clear();
  }
  bool begin(int, int, uint32_t) { ++beginCount; return beginSucceeds; }
  void setTimeOut(int) {}
  void beginTransmission(uint8_t address) { ++transactionCount; addresses.push_back(address); writes.emplace_back(); }
  std::size_t write(uint8_t value) { writes.back().push_back(value); return 1; }
  std::size_t write(const uint8_t* data, std::size_t count) {
    writes.back().insert(writes.back().end(), data, data + count); return count;
  }
  uint8_t endTransmission(bool = true) {
    if (failNext) { failNext = false; return 2; }
    if (!addresses.empty() && addresses.back() == failingAddress) return 2;
    return 0;
  }
  uint8_t requestFrom(uint8_t, uint8_t) { return 2; }
  int read() { return 0; }
};
inline FakeWire Wire;
