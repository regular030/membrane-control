# Procurement baseline

Updated 26 October 2026. Listings, prices and sellers can change. Quantities below support the initial bench prototype, not a complete commissioned mains assembly. Reuse existing suitable items.

## Initial purchases

| Qty | Item | Link | Purchase condition |
| --- | --- | --- | --- |
| 1 | Lenovo ThinkCentre M720q, i5-8500T, 16 GB RAM, 256 GB SSD, Windows 11 Pro | [Amazon Canada](https://www.amazon.ca/dp/B08G1XKHPB) | Include matching power adapter and confirm monitor cable/return coverage; current price unverified |
| 1 | Srliya 16-channel ESP32-WROOM relay board | [Amazon Canada](https://www.amazon.ca/dp/B0DKC2L2NH) | Selected candidate; verify exact revision, 74HC595 pin/bit mapping, OE defaults, supply input and valve-load suitability before physical use |
| 1 | DAOKAI CP2102 USB-to-UART adapter | [Amazon Canada](https://www.amazon.ca/dp/B0BCKBHQ8Y) | Use verified 3.3 V TTL TX/RX; leave adapter power pins disconnected when board externally powered |
| 1 only if verified compatible | SANSUN 12 V 2 A DC supply | [Amazon Canada](https://www.amazon.ca/dp/B01AZLA9XQ) | Do not apply 12 V until the actual board input rating and polarity are verified; seller documents conflict. Check supply label, connector and board/interface demand; reuse an existing suitable supply; current price unverified |
| Reuse the current cable | USB-A to USB-B data cable for balance | [Amazon Canada](https://www.amazon.ca/dp/B00NH13DV2) | The user now uses the scale's USB-B I/O connection. Reuse the working data cable; the green RS232 adapter is no longer the selected path |

The controller needs an external supply matching the actual PCB input rating.
The seller's DC 5-12 V listing conflicts with its 5 V input diagram; the 5 V relay
coil markings do not establish the input rating. The installed board is marked
ESP32_Relay_X16_V1.2. Keep the proposed 12 V input disconnected until that revision
and terminal polarity are verified. The controller supply does not power the
computer, balance, pumps or 110-120 VAC valve coils. Those loads retain their
appropriate supplies and switching protection.

Confirm the SANSUN adapter's exact output plug and polarity on the ordered unit, then use a matching female jack/pigtail with strain relief to the controller input. If it is the advertised 5.5 x 2.1 mm centre-positive connector, use that mating size; do not assume 5.5 x 2.5 mm is equivalent. The pictured 16-channel board advertises a DC 5-12 V input range, but its exact revision and terminal polarity must still be verified. Never apply 12 V to a terminal documented only for 5 V. A supply's 2 A maximum rating is provisional until the complete board and interface demand is checked.

The selected board has more channels than the seven valve outputs required.
Unused channels must remain in their reviewed inactive states. Pump speed and
remote start/stop use separate control interfaces. The identified 75211-30
manual confirms 0-10 V voltage command and feedback, with separate documented
return pins. Verify its actual mode, harness and references before selecting
the interface modules. The firmware represents this candidate
as a 16-bit shift-register board with unassigned hardware mappings; the product
photograph does not establish a usable pin map or mains-load rating.

## Parts requiring final interface selection

| Item | Candidate or specification | Remaining check |
| --- | --- | --- |
| 1 pump command DAC | **DFRobot Gravity DFR0971 / GP8403, two-channel I2C 0-10 V**: [DigiKey Canada, part 1738-DFR0971-ND](https://www.digikey.ca/en/products/detail/dfrobot/DFR0971/18069239); [exact manufacturer product](https://www.dfrobot.com/product-2613.html) | Preferred purchase: matches the current GP8403 driver. Verify the received DFR0971, 3.3 V supply, 0-10 V output, V mode, DB15 1/3 reference, grounding and safe startup before connection |
| Sensor ADC and conditioning | ADS1115-based acquisition or equivalent protected interface | Define sensor scaling and the separately verified pump-feedback range, protection, grounding and calibration |
| Pump start/stop contact | Separate isolated signal contact/interface | Verify contact behavior/suitability across 75211-30 DB15 pins 10/12 |
| DB15 harness | Two-row 15-pin connector matching installed pump | Verify gender and pinout; do not substitute a three-row VGA connector |
| DC barrel adapter | Female 5.5 x 2.1 mm to secured pigtail or terminal | Check connector dimensions and mounting |
| Enclosure and wiring | Rated terminals, glands, wire, ferrules, labels, fuses and mounting | Size after layout and electrical review |

The exact DFR0971 manufacturer's specifications were checked on 26 October
2026. An exact Amazon.ca product/ASIN could not be verified: Amazon search
pages were inaccessible to the research tool and indexed results did not
identify a matching Canadian listing. The Amazon link above is a **search**,
not a verified ready-to-order product. Match the manufacturer/model, supply,
I2C interface and output range; a generic PWM converter or ordinary 0-VCC DAC
is a different part. Amazon price, stock, seller and delivery are unverified.

**Canadian purchase links checked on 26 October 2026:** DigiKey Canada lists
the exact DFR0971 at **CAD 14.83**, with 773 shown in stock. Confirm shipping,
tax and fulfillment at checkout. This is the preferred way to retain the
current driver and existing pump handoff without changing converter models.

A different hardware option is the **DFRobot DFR1073 / GP8413**, listed at
**CAD 21.29** with two units shown by
[RobotShop Canada](https://ca.robotshop.com/products/gravity-gp8413-2-channel-15-bit-i2c-to-0-5v-10v-dac-module).
The [manufacturer specification](https://wiki.dfrobot.com/dfr1073/) confirms
3.3-5 V supply, I2C and selectable 0-5/0-10 V outputs. It uses a 15-bit GP8413,
so it is **not a drop-in replacement in release 0.1.12**: its output encoding,
scale and initialization must be implemented and tested before pump operation.
Neither part has been bench-tested on this rig. Prices and stock can change;
do not buy both modules for one pump command.

For Raj: the DAC adds only the speed-command path. It does not include the
isolated start/stop contact, protected feedback ADC or a corrected DB15
harness. Follow [the pump wiring handoff](pump-interface.md#handoff-connecting-the-dfr0971-when-it-arrives)
for proposed GPIO21 SDA / GPIO22 SCL connections and the unpowered continuity
checks required before connecting any pump wires. The physical firmware stays
unverified until the complete interface is commissioned.

## Computer offered for comparison

The [HP ProDesk 600 G1 listing](https://www.amazon.ca/dp/B085RY6Z1C) was observed at CAD 199.99 and advertises i5-4570T, 16 GB RAM, 256 GB SSD and Windows 11 Pro. It explicitly warns that it has TPM 1.2. The generic summary table also conflicts with the storage description. Prefer the newer M720q configuration for the Windows application.

See [Microsoft Windows 11 specifications](https://www.microsoft.com/en-us/windows/windows-11-specifications) for TPM 2.0 requirements and [supported Intel processors](https://learn.microsoft.com/en-us/windows-hardware/design/minimum/supported/windows-11-supported-intel-processors).
