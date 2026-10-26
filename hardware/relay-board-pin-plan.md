# Srliya 16-channel board: proposed wiring

Source: the user's screenshots and the [Amazon B0DKC2L2NH listing](https://www.amazon.ca/dp/B0DKC2L2NH), inspected 25 October 2026. These are seller-documented GPIO assignments and proposed peripheral connections. They are not a verified schematic or a commissioned physical profile.

## Relay control already on the PCB

The seller's `ESP32_X16_TEST.ino` screenshot defines:

| Signal | ESP32 GPIO | Meaning |
| --- | --- | --- |
| `HC595_SI_PIN` | 14 | Serial data into the 74HC595 chain |
| `HC595_SCK_PIN` | 13 | Shift clock |
| `HC595_RCK_PIN` | 12 | Storage-register latch clock |
| `HC595_G_PIN` | 5 | Output-enable control |

These traces already exist. Do not connect sensors or new jumper wires to these GPIOs. The repository's shift-register driver supports these four functions, but the factory profile remains unassigned. The user has observed LOW = relay off and HIGH = relay on; record that result without treating it as proof of bit order, reset/OE defaults or safe valve states. Do not assume physical relay 1 equals bit 0 or physical relay 8 equals bit 7.

The separate [real relay board test](../docs/relay-board-test.md) firmware now uses
these candidate pins to pulse unloaded outputs and establish their mapping.
Its identity and commands are separate from the experiment controller, and it
never marks the production hardware profile verified.

TI specifies OE HIGH as high impedance, not a guaranteed relay-OFF state. The relay driver circuit and its default bias determine what happens during reset. GPIO12 and GPIO5 also have ESP32 boot-strapping roles. Leave their onboard bias circuits intact.

Reserve GPIO4 until the board's shift-register clear/reset wiring has been traced; a clear connection on a similar board is not proof for this revision.

## Recommended peripheral wiring

Solder the supplied headers into the labelled I/O breakout pads beside the ESP32. Use a small terminal/interface board for field wires and strain relief. GPIO numbers below are signal names, not positions along a header. The listing does not establish an unambiguous hole-by-hole header layout; confirm the silkscreen or continuity with power removed before soldering.

| Component connection | Board connection | Notes |
| --- | --- | --- |
| USB-UART TX | RX / RXD0 / GPIO3 | Adapter must use 3.3 V TTL logic |
| USB-UART RX | TX / TXD0 / GPIO1 | Cross TX and RX |
| USB-UART GND | GND | Common UART reference |
| Selected EC Buying converter PWM | IO25 / GPIO25, proposed | 3.3 V PWM, proposed 1 kHz; confirm exposed pad and reviewed profile |
| Selected converter VIN | Verified regulated supply within its stated 3.3-12 V range | Existing nominal 12 V is at its maximum; verify actual tolerance/startup |
| Selected converter GND | Reviewed common low-voltage reference | Nonisolated power/PWM/output reference; resolve pump and ESP32/USB grounding first |
| Pump contact-interface control | IO26 / GPIO26, proposed | To a verified 3.3 V-compatible isolated contact interface, never directly to pump pins |
| Optional external ADC SDA | IO21 / GPIO21 | I2C only if ADS1115 acquisition is selected; the PWM converter does not use it |
| Optional external ADC SCL | IO22 / GPIO22 | Same acquisition choice |
| ADS1115 power, if selected | 3V3 and GND | Verify module and pull-ups support 3.3 V; condition all analog inputs |
| Adam Nimbus balance | Current: balance USB-B I/O directly to computer USB | No ESP32 pins; separate COM port from the controller; see [balance USB setup](balance-usb-setup.md) |

With the relay board externally powered, leave the USB-UART adapter's 3.3 V and 5 V power outputs disconnected. The seller's four-wire table describes a power arrangement; it is not a reason to tie two powered regulator outputs together. Check the adapter's actual TX logic level, not only its VCC selector label.

### Analog measurements and pump command

The pump's VOUT is feedback **from** the pump. It belongs on a protected ADC
input. The selected PWM converter's OUT drives the opposite direction, into
the pump's VIN/speed-command input. The identified 75211-30 manual documents a 0-10 V command at
DB15 1(+)/3(-) and feedback at 9(+)/5(-). The actual harness and references must
still be checked. See
[pump interface](pump-interface.md).

The [selected EC Buying module](https://www.amazon.ca/EC-Buying-Converter-Adjustable-Conversion/dp/B0CPJGFCGR)
converts ESP32 PWM to a DC analog command. Its output is not isolated; do not
join the pump's signal returns by assumption. See the
[pump wiring handoff](pump-interface.md#connecting-the-ec-buying-converter-when-it-arrives)
for the terminal table and unloaded output/stop/reset tests. No extra GP8403
DAC is required for this selected path.

This is one external-ADC acquisition plan supported by the firmware:

| Signal | Destination |
| --- | --- |
| Pressure sensor 0-5 V output | Scaling/protection interface, then ADS1115 A0 |
| Flow sensor 0-5 V analog output | Scaling/protection interface, then ADS1115 A1 |
| Pump speed feedback, documented 0-10 V on DB15 9(+)/5(-) | Range-matched scaling/protection interface, then ADS1115 A2; use the specified return |
| Pump speed command | EC Buying converter OUT to DB15 1(+), reviewed output reference to 3(-); first test with pump disconnected |

Use the flow sensor's analog output for this plan. Its pulse output is a different interface. For a 3.3 V-powered ADS1115, keep normal analog pin voltage within 0-3.3 V; selecting a larger ADC gain range does not make it 5 V or 10 V tolerant. Connect each pump signal's specified return according to the exact drive manual. Do not assume every cable tag called GROUND is the right analog return.

If using the ESP32's native ADC instead, reserve GPIO34 for conditioned pressure, GPIO35 for conditioned flow and GPIO36/SENSOR_VP for conditioned pump feedback. This is an alternative to the ADS1115, not extra duplicate wiring. It still requires scaling, protection and calibration. The firmware supports ADC1, but the installed board must expose those GPIOs.

### Pump remote start/stop

Use a separately reviewed isolated dry-contact interface, provisionally driven
by **GPIO26**, matching the current `pumpContactPin` driver. Its control input
must support 3.3 V ESP32 logic. Its isolated contact side connects only across
the pump's **DB15 pins 10 and 12**, with no external voltage applied. This
signal-contact circuit must remain separate from the 110-120 VAC valve COM bus.
Never copy the old Arduino VIN connection to the pump's start/stop wire.

The driver does not pack pump RUN into a spare 74HC595 relay bit. An onboard
relay is not a substitute without a reviewed driver/mapping and an electrical
separation design. Verify STOP, reset and interface power loss with the pump
disconnected before connecting its harness.

### Recorded old analog channels

The user-confirmed Mega wiring was pump feedback **A8**, pressure **A10** and
flow **A12**, with pump command on PWM-capable **D3**. Those three A-numbered
channels are analog inputs, not I2C. The new acquisition may use ADS1115 inputs
or conditioned ESP32 ADC1 pins; it does not copy Mega channel numbers onto the
ESP32. Every 0-5 V sensor and the separate 0-10 V feedback path still needs
scaling, protection, reference verification and calibration.

## Programming

The onboard ESP32 remains on the board; no programming jig is needed. Use its UART header and the IO0 and EN buttons. For manual download mode, hold IO0, press and release EN, then release IO0 and start the PlatformIO upload. Reset with IO0 released after flashing. Close the desktop app's serial connection before upload. The first upload should be the factory dry-run environment, with loads disconnected.

## Power discrepancy to resolve

The listing text says DC 5-12 V, but its annotated photo calls the input "5V Power Supply" and the relays are marked SRD-05VDC. A 5 V coil does not establish the board input rating. Confirm the actual board revision, terminal labels and regulator input rating before applying 12 V. If it is a 5 V-only input, retain the 12 V supply through a correctly sized 12-to-5 V converter. Never feed 12 V into a 3V3, UART or GPIO pad. Valve and pump load power remain separate from controller power.

## Primary references

- [Espressif I2C pins and pull-ups](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/i2c.html)
- [ESP32-WROOM-32E pin definitions](https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf)
- [Espressif boot mode selection](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html)
- [TI SN74HC595 OE behavior](https://www.ti.com/product/SN74HC595)
- [TI ADS1115 input limits](https://www.ti.com/lit/ds/symlink/ads1115.pdf)
- [Selected EC Buying PWM converter specification](https://www.amazon.ca/EC-Buying-Converter-Adjustable-Conversion/dp/B0CPJGFCGR)
- [Arduino Mega 2560 resources and pinout](https://docs.arduino.cc/hardware/mega-2560/)
