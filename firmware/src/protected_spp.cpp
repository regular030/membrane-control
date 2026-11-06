#include "ProtectedSpp.h"

#include <algorithm>
#include <array>
#include <cstring>
#include <esp_bt.h>
#include <esp_bt_device.h>
#include <esp_bt_main.h>
#include <esp_gap_bt_api.h>
#include <esp_spp_api.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>

// The pinned Arduino core otherwise releases Bluetooth memory during startup.
extern "C" bool btInUse() { return true; }

namespace basu::protectedSpp {
namespace {
constexpr char kName[] = "MembraneControl";
constexpr TickType_t kWriteTimeout = pdMS_TO_TICKS(1000);

struct Frame {
  BluetoothLinkToken token;
  std::size_t length;
  std::array<uint8_t, kFrameBytes> bytes;
};

portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
BluetoothLink link;
esp_bd_addr_t enrolledPeer{};
QueueHandle_t outgoing = nullptr;
std::array<uint8_t, kMaxLineBytes + 1> incoming{};
std::size_t head = 0;
std::size_t used = 0;
uint32_t pendingDisconnect = 0;
bool callingSdk = false;
bool writing = false;
bool congested = false;
std::size_t writingLength = 0;

void invalidateLocked(BluetoothLinkToken token) {
  if (!link.invalidate(token)) return;
  head = used = 0;
  pendingDisconnect = token.handle;
}

void invalidate(BluetoothLinkToken token) {
  portENTER_CRITICAL(&lock);
  invalidateLocked(token);
  portEXIT_CRITICAL(&lock);
}

// The pinned IDF may wait while posting an SPP write. Keep all such writes
// outside the controller loop so radio congestion cannot stall the watchdog.
void transmit(void*) {
  Frame frame{};
  for (;;) {
    portENTER_CRITICAL(&lock);
    const uint32_t disconnect = pendingDisconnect;
    pendingDisconnect = 0;
    callingSdk = disconnect != 0;
    portEXIT_CRITICAL(&lock);
    if (disconnect) {
      esp_spp_disconnect(disconnect);
      portENTER_CRITICAL(&lock);
      callingSdk = false;
      portEXIT_CRITICAL(&lock);
    }
    if (xQueueReceive(outgoing, &frame, pdMS_TO_TICKS(10)) != pdTRUE) continue;

    const TickType_t started = xTaskGetTickCount();
    for (;;) {
      portENTER_CRITICAL(&lock);
      const bool sessionCurrent = link.current(frame.token);
      const bool ready = sessionCurrent && !writing && !congested;
      if (ready) {
        callingSdk = writing = true;
        writingLength = frame.length;
      }
      portEXIT_CRITICAL(&lock);
      if (!sessionCurrent) break;
      if (ready) {
        const esp_err_t result = esp_spp_write(frame.token.handle, frame.length, frame.bytes.data());
        portENTER_CRITICAL(&lock);
        callingSdk = false;
        if (result != ESP_OK) invalidateLocked(frame.token);
        portEXIT_CRITICAL(&lock);
        break;
      }
      if (xTaskGetTickCount() - started >= kWriteTimeout) {
        invalidate(frame.token);
        break;
      }
      vTaskDelay(1);
    }
  }
}

void onGap(esp_bt_gap_cb_event_t event, esp_bt_gap_cb_param_t* data) {
  // Enrollment happens on the unloaded bench image. Physical firmware never
  // grants a new bond through PIN or numeric confirmation prompts.
  if (event == ESP_BT_GAP_PIN_REQ_EVT) {
    esp_bt_pin_code_t empty{};
    esp_bt_gap_pin_reply(data->pin_req.bda, false, 0, empty);
  } else if (event == ESP_BT_GAP_CFM_REQ_EVT) {
    esp_bt_gap_ssp_confirm_reply(data->cfm_req.bda, false);
  } else if (event == ESP_BT_GAP_KEY_REQ_EVT) {
    esp_bt_gap_ssp_passkey_reply(data->key_req.bda, false, 0);
  }
}

void onSpp(esp_spp_cb_event_t event, esp_spp_cb_param_t* data) {
  if (event == ESP_SPP_INIT_EVT && data->init.status == ESP_SPP_SUCCESS) {
    constexpr esp_spp_sec_t security = ESP_SPP_SEC_AUTHENTICATE | ESP_SPP_SEC_ENCRYPT;
    esp_spp_start_srv(security, ESP_SPP_ROLE_SLAVE, 0, kName);
    return;
  }
  if (event == ESP_SPP_START_EVT && data->start.status == ESP_SPP_SUCCESS) {
    esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_GENERAL_DISCOVERABLE);
    return;
  }
  if (event == ESP_SPP_SRV_OPEN_EVT && data->srv_open.status == ESP_SPP_SUCCESS) {
    const auto handle = data->srv_open.handle;
    const bool enrolled = std::memcmp(enrolledPeer, data->srv_open.rem_bda, sizeof(enrolledPeer)) == 0;
    portENTER_CRITICAL(&lock);
    const bool accepted = !callingSdk && link.open(handle, enrolled);
    if (accepted) {
      head = used = 0;
      writing = congested = false;
    }
    portEXIT_CRITICAL(&lock);
    if (!accepted) esp_spp_disconnect(handle);
    return;
  }

  portENTER_CRITICAL(&lock);
  const auto token = link.token();
  if (event == ESP_SPP_CLOSE_EVT && link.close(data->close.handle)) {
    head = used = 0;
    writing = congested = false;
    if (pendingDisconnect == data->close.handle) pendingDisconnect = 0;
  } else if (token.handle && event == ESP_SPP_DATA_IND_EVT && data->data_ind.handle == token.handle) {
    const std::size_t length = data->data_ind.len;
    if (length > incoming.size() - used) {
      invalidateLocked(token);
    } else if (length) {
      const std::size_t tail = (head + used) % incoming.size();
      const std::size_t first = std::min(length, incoming.size() - tail);
      std::memcpy(incoming.data() + tail, data->data_ind.data, first);
      std::memcpy(incoming.data(), data->data_ind.data + first, length - first);
      used += length;
    }
  } else if (token.handle && event == ESP_SPP_WRITE_EVT && data->write.handle == token.handle) {
    if (writing && (data->write.status != ESP_SPP_SUCCESS || data->write.len != static_cast<int>(writingLength)))
      invalidateLocked(token);
    writing = false;
    congested = data->write.cong;
  } else if (token.handle && event == ESP_SPP_CONG_EVT && data->cong.handle == token.handle) {
    congested = data->cong.cong;
  }
  portEXIT_CRITICAL(&lock);
}
}  // namespace

const char* begin() {
  esp_bt_controller_config_t config = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
  if (esp_bt_controller_init(&config) != ESP_OK || esp_bt_controller_enable(ESP_BT_MODE_BTDM) != ESP_OK ||
      esp_bluedroid_init() != ESP_OK || esp_bluedroid_enable() != ESP_OK)
    return "Bluetooth initialization failed";
  int bonds = esp_bt_gap_get_bond_device_num();
  if (bonds == 0) return "Bluetooth physical control locked: no enrolled bench bond";
  if (bonds > 1) return "Bluetooth physical control locked: multiple enrolled bench bonds";
  esp_bd_addr_t saved[1]{};
  if (bonds != 1 || esp_bt_gap_get_bond_device_list(&bonds, saved) != ESP_OK || bonds != 1)
    return "Bluetooth physical control locked: could not read the enrolled bench bond";
  std::memcpy(enrolledPeer, saved[0], sizeof(enrolledPeer));

  outgoing = xQueueCreate(4, sizeof(Frame));
  if (!outgoing || xTaskCreate(transmit, "protected_spp_tx", 4096, nullptr, 1, nullptr) != pdPASS)
    return "Bluetooth transmit initialization failed";
  uint8_t ioCapability = ESP_BT_IO_CAP_IO;
  if (esp_bt_gap_register_callback(onGap) != ESP_OK ||
      esp_bt_gap_set_security_param(ESP_BT_SP_IOCAP_MODE, &ioCapability, sizeof(ioCapability)) != ESP_OK ||
      esp_bt_dev_set_device_name(kName) != ESP_OK || esp_spp_register_callback(onSpp) != ESP_OK ||
      esp_spp_init(ESP_SPP_MODE_CB) != ESP_OK)
    return "Bluetooth protected serial service could not start";
  return nullptr;
}

BluetoothLinkToken current() {
  portENTER_CRITICAL(&lock);
  const auto token = link.token();
  portEXIT_CRITICAL(&lock);
  return token;
}

bool read(BluetoothLinkToken token, uint8_t& byte) {
  portENTER_CRITICAL(&lock);
  const bool ready = used && link.current(token);
  if (ready) {
    byte = incoming[head];
    head = (head + 1) % incoming.size();
    --used;
  }
  portEXIT_CRITICAL(&lock);
  return ready;
}

void send(BluetoothLinkToken token, const char* data, std::size_t length, bool telemetry) {
  if (!token.handle || !(token == current())) return;
  if (length > kFrameBytes) { invalidate(token); return; }
  Frame frame{};
  frame.token = token;
  frame.length = length;
  std::memcpy(frame.bytes.data(), data, length);
  if (xQueueSend(outgoing, &frame, 0) != pdTRUE && !telemetry) invalidate(token);
}

}  // namespace basu::protectedSpp
