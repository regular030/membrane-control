#pragma once

#include <cstddef>
#include <cstdint>
#include "BluetoothControlSession.h"

namespace basu::protectedSpp {

constexpr std::size_t kFrameBytes = 1024;
enum class PairingStatus { Waiting, Ready, Failed };
const char* begin(bool pairingOnly = false);
bool requestPairing();
bool takePairingCode(uint32_t& code);
bool confirmPairing(uint32_t code);
PairingStatus pairingStatus();
bool savePairing();
BluetoothLinkToken current();
bool read(BluetoothLinkToken token, uint8_t& byte);
void send(BluetoothLinkToken token, const char* data, std::size_t length, bool telemetry);

}  // namespace basu::protectedSpp
