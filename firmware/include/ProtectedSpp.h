#pragma once

#include <cstddef>
#include <cstdint>
#include "BluetoothControlSession.h"

namespace basu::protectedSpp {

constexpr std::size_t kFrameBytes = 1024;
const char* begin();
BluetoothLinkToken current();
bool read(BluetoothLinkToken token, uint8_t& byte);
void send(BluetoothLinkToken token, const char* data, std::size_t length, bool telemetry);

}  // namespace basu::protectedSpp
