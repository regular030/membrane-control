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

These traces already exist. Do not connect sensors or new jumper wires to these GPIOs. The repository's shift-register driver supports these four functions, but the factory profile remains unassigned. Relay bit order, channel polarity and safe states must be measured before making a verified profile. Do not assume physical relay 1 equals bit 0 or physical relay 8 equals bit 7.

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
| ADC and pump DAC SDA | IO21 / GPIO21 | Shared I2C data |
| ADC and pump DAC SCL | IO22 / GPIO22 | Shared I2C clock |
| ADS1115 and DFR0971/GP8403 module power | 3V3 and GND | Applies to these specified 3.3 V-capable modules; pull-ups must be to 3.3 V |
| Adam Nimbus balance | Current: balance USB-B I/O directly to computer USB | No ESP32 pins; separate COM port from the controller; see [balance USB setup](balance-usb-setup.md) |

With the relay board externally powered, leave the USB-UART adapter's 3.3 V and 5 V power outputs disconnected. The seller's four-wire table describes a power arrangement; it is not a reason to tie two powered regulator outputs together. Check the adapter's actual TX logic level, not only its VCC selector label.

### Analog measurements and pump command

The pump's VOUT is feedback **from** the pump. It belongs on a protected ADC
input. The DAC output drives the opposite direction, into the pump's VIN/speed
command input, only after its model-specific range is confirmed. See
[pump interface](pump-interface.md).

This is the preferred external-ADC plan already supported by the firmware:

| Signal | Destination |
| --- | --- |
| Pressure sensor 0-5 V output | Scaling/protection interface, then ADS1115 A0 |
| Flow sensor 0-5 V analog output | Scaling/protection interface, then ADS1115 A1 |
| Pump speed feedback; actual range unverified, tag says 0-10 V | Range-matched scaling/protection interface, then ADS1115 A2 |
| Pump speed command | GP8403 VOUT0 to the verified pump speed-input terminal |

Use the flow sensor's analog output for this plan. Its pulse output is a different interface. For a 3.3 V-powered ADS1115, keep normal analog pin voltage within 0-3.3 V; selecting a larger ADC gain range does not make it 5 V or 10 V tolerant. Connect each pump signal's specified return according to the exact drive manual. Do not assume every cable tag called GROUND is the right analog return.

If using the ESP32's native ADC instead, reserve GPIO34 for conditioned pressure, GPIO35 for conditioned flow and GPIO36/SENSOR_VP for conditioned pump feedback. This is an alternative to the ADS1115, not extra duplicate wiring. It still requires scaling, protection and calibration. The firmware supports ADC1, but the installed board must expose those GPIOs.

### Pump remote start/stop

Prefer a spare onboard relay, provisionally physical channel 8, as the pump's remote dry contact, if its contact characteristics suit the pump's remote input. Its COM and NO contacts connect only to the pump's verified remote-start pair. Do not apply the board's supply voltage to that pair. Keep this signal-contact circuit separated from mains valve contacts.

**Version 0.1.0 limitation:** the physical driver currently expects a separate `pumpContactPin`, such as a reviewed GPIO26-driven isolated contact stage. It does not yet pack pump RUN into a spare 74HC595 relay bit. Using onboard relay 8 requires a driver change, validation of the physical relay-to-bit mapping and tests of STOP-before-DAC/valve changes. It is not enabled by this document. Avoid adding a separate contact stage merely to finalize wiring before that choice is settled.

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
- [DFRobot DFR0971 supply and output specification](https://wiki.dfrobot.com/dfr0971)
