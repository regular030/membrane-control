#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <vector>

struct FakeWire {
  unsigned beginCount = 0;
  unsigned transactionCount = 0;
  bool failNext = false;
  bool beginSucceeds = true;
  int failingAddress = -1;
  int adsAddress = -1;
  int adsFailedChannel = -1;
  std::array<std::optional<int16_t>, 4> adsConversions{};
  std::vector<uint8_t> addresses;
  std::vector<std::vector<uint8_t>> writes;
  void reset() {
    beginCount = 0; transactionCount = 0; failNext = false; beginSucceeds = true;
    failingAddress = -1; addresses.clear(); writes.clear();
    adsAddress = -1; adsFailedChannel = -1; adsConversions.fill(std::nullopt);
    adsChannel = -1; response = 0; responseOffset = 0;
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
    if (!addresses.empty() && addresses.back() == adsAddress) {
      const auto& bytes = writes.back();
      if (bytes.size() == 3 && bytes[0] == 1) adsChannel = ((bytes[1] >> 4) & 7) - 4;
    }
    return 0;
  }
  uint8_t requestFrom(uint8_t address, uint8_t) {
    response = 0;
    responseOffset = 0;
    if (address != adsAddress || adsChannel < 0 || !adsConversions[adsChannel] || writes.back().empty()) return 2;
    if (writes.back().front() == 1) {
      response = 0x8000;
    } else if (writes.back().front() == 0) {
      if (adsChannel == adsFailedChannel) return 0;
      response = static_cast<uint16_t>(*adsConversions[adsChannel]);
    }
    return 2;
  }
  int read() { return responseOffset++ == 0 ? response >> 8 : response & 0xff; }

 private:
  int adsChannel = -1;
  uint16_t response = 0;
  int responseOffset = 0;
};
inline FakeWire Wire;
