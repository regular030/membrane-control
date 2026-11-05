# Srliya 16-channel board: proposed wiring

Use the [current wiring guide](../docs/ordered-parts-wiring.md) for the
Masterflex 75211-70 DB25, Garosa 3.3P-10V and HiLetgo dividers. It identifies
the GPIO34/36/39 measurement pins and the spare onboard pump relay plan.

**Current installed valve map, version 0.1.16:** V1, V2, V3, V4, V5 and V7
use bits 0, 1, 2, 3, 5 and 6. There is no V6. Bit 4 has no valve assignment. The
[normal valve guide](../docs/normal-valves.md) describes the current controls;
the peripheral wiring below remains a planning reference.

Source: the user's screenshots and the [Amazon B0DKC2L2NH listing](https://www.amazon.ca/dp/B0DKC2L2NH), inspected 25 October 2026. These are seller-documented GPIO assignments and proposed peripheral connections. They are not a verified schematic or a commissioned physical profile.

## Relay control already on the PCB

The seller's `ESP32_X16_TEST.ino` screenshot defines:

| Signal | ESP32 GPIO | Meaning |
| --- | --- | --- |
| `HC595_SI_PIN` | 14 | Serial data into the 74HC595 chain |
| `HC595_SCK_PIN` | 13 | Shift clock |
| `HC595_RCK_PIN` | 12 | Storage-register latch clock |
| `HC595_G_PIN` | 5 | Output-enable control |

These traces already exist. Do not connect sensors or new jumper wires to these
GPIOs. The normal manual-valve driver already uses them with the confirmed
six-valve mapping above. The lab also confirmed pump bit 15. The factory
controller still keeps full pump operation disabled. The confirmed polarity and valve bits do not establish
reset/OE defaults or the process's fault-state valve routing. Do not infer
additional physical relay mappings from the confirmed six alone.

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
| Garosa **PWM+** | IO25 / GPIO25 | 3.3 V PWM at 1 kHz |
| Garosa **PWM-** | ESP32 GND | PWM signal return |
| Garosa **Supply+ / Supply-** | Separate regulated 24 V DC supply pair | Seller range 15-30 V DC and board mark 12-30 V |
| Pump start/stop | 74HC595 raw bit 15 | Physical COM and NO across DB25 15/17. LOW stops, HIGH runs |
| Optional external contact-driver control | IO26 / GPIO26 | Reserved for a 3.3 V-compatible external isolated driver, if used instead |
| Optional external ADC SDA | IO21 / GPIO21 | I2C only if ADS1115 acquisition is selected; the PWM converter does not use it |
| Optional external ADC SCL | IO22 / GPIO22 | Same acquisition choice |
| ADS1115 power, if selected | 3V3 and GND | Verify module and pull-ups support 3.3 V; condition all analog inputs |
| Adam Nimbus balance | Current: balance USB-B I/O directly to computer USB | No ESP32 pins; separate COM port from the controller; see [balance USB setup](balance-usb-setup.md) |

With the relay board externally powered, leave the USB-UART adapter's 3.3 V and 5 V power outputs disconnected. The seller's four-wire table describes a power arrangement; it is not a reason to tie two powered regulator outputs together. Check the adapter's actual TX logic level, not only its VCC selector label.

### Analog measurements and pump command

The [Garosa 3.3P-10V](https://www.amazon.ca/Voltage-Module-Voltage-Converter-Digital-Analog/dp/B07WZNV1V2) drives the 75211-70 pump's 0-10 V
command at DB25 **1 (+)/3 (-)**. The running command output is DB25
**14 (+)/5 (-)**. For the terminal table and unloaded measurements, see the
[pump interface](pump-interface.md#garosa-converter-wiring).

| Signal | Selected native ADC1 input | Optional ADS1115 input |
| --- | --- | --- |
| Pressure 0-5 V through scaling/protection | **GPIO34** | A0 |
| Flow 0-5 V through scaling/protection | **GPIO36 / SVP** | A1 |
| Pump running command output 0-10 V through scaling/protection | **GPIO39 / SVN**, after reference review | A2, after reference review |

Keep GPIO35 unused following the reported possible overvoltage. Use the flow
sensor's analog output. On an ADS1115 powered at 3.3 V, the analog inputs still
need scaling to stay within 0-3.3 V at the pins. Check the actual divider and
pump reference paths before adding pump measurement. The direct divider joins
its input return to the ESP32 ADC ground.

### Pump remote start/stop

Use a tested spare onboard relay with independent contacts. Its **COM** goes
to DB25 **15** and **NO** to **17**. Both contacts must be separate from the
110-120 VAC valve distribution. The lab reported that raw bit 15 is LOW
for STOP and HIGH for RUN. An external
isolated contact driver on **GPIO26** is an alternative. GPIO26 goes to that
driver's control input.

On the 75211-70, use **Voltage Input** and **Continuous Pump Mode** with
**START/STOP required ON** and **AUTO START OFF**. Verify the contact's open
state inhibits the pump before live use. See the
[drive settings and wiring](pump-interface.md#spare-onboard-relay-for-startstop).

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
- [Garosa 3.3P-10V PWM converter listing](https://www.amazon.ca/Voltage-Module-Voltage-Converter-Digital-Analog/dp/B07WZNV1V2)
- [Arduino Mega 2560 resources and pinout](https://docs.arduino.cc/hardware/mega-2560/)
