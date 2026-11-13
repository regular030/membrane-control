#include <Arduino.h>
#include <driver/adc.h>
#include <driver/rtc_io.h>
#include <esp_adc_cal.h>

namespace {
constexpr gpio_num_t kPressurePin = GPIO_NUM_26;
constexpr adc2_channel_t kPressureChannel = ADC2_CHANNEL_9;
constexpr auto kAttenuation = ADC_ATTEN_DB_2_5;
constexpr auto kWidth = ADC_WIDTH_BIT_12;
esp_adc_cal_characteristics_t calibration{};
bool ready = false;
bool pulldown = false;

void setPulldown(bool enabled) {
  const esp_err_t result = enabled ? rtc_gpio_pulldown_en(kPressurePin) : rtc_gpio_pulldown_dis(kPressurePin);
  if (result != ESP_OK) {
    Serial.printf("IO26 pull-down error: %s\n", esp_err_to_name(result));
    return;
  }
  pulldown = enabled;
  Serial.printf("IO26 pull-down %s\n", pulldown ? "on" : "off");
}
}  // namespace

void setup() {
  Serial.begin(115200);
  Serial.println("IO26 pressure input test. Send 0 to disable or 1 to enable the pull-down.");
  // Only the USB serial interface and IO26 are used in this build.
  pinMode(kPressurePin, INPUT);
  const esp_err_t result = adc2_config_channel_atten(kPressureChannel, kAttenuation);
  if (result != ESP_OK) {
    Serial.printf("IO26 setup error: %s\n", esp_err_to_name(result));
    return;
  }
  esp_adc_cal_characterize(ADC_UNIT_2, kAttenuation, kWidth, 1100, &calibration);
  ready = true;
  setPulldown(true);  // The ADC setup disables internal pulls, so set this afterward.
}

void loop() {
  if (ready) {
    while (Serial.available()) {
      const int command = Serial.read();
      if (command == '0' || command == '1') setPulldown(command == '1');
    }
    int raw = 0;
    const esp_err_t result = adc2_get_raw(kPressureChannel, kWidth, &raw);
    if (result == ESP_OK) {
      Serial.printf("IO26 pull-down %s: raw=%d, %lu mV\n", pulldown ? "on" : "off", raw,
                    static_cast<unsigned long>(esp_adc_cal_raw_to_voltage(raw, &calibration)));
    } else {
      Serial.printf("IO26 read error: %s\n", esp_err_to_name(result));
    }
  }
  delay(250);
}
