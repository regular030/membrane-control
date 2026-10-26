# Procurement baseline

Updated 25 October 2026. Listings, prices and sellers can change. Quantities below support the initial bench prototype, not a complete commissioned mains assembly. Reuse existing suitable items.

## Initial purchases

| Qty | Item | Link | Purchase condition |
| --- | --- | --- | --- |
| 1 | Lenovo ThinkCentre M720q, i5-8500T, 16 GB RAM, 256 GB SSD, Windows 11 Pro | [Amazon Canada](https://www.amazon.ca/dp/B08G1XKHPB) | Include matching power adapter and confirm monitor cable/return coverage; current price unverified |
| 1 | Srliya 16-channel ESP32-WROOM relay board | [Amazon Canada](https://www.amazon.ca/dp/B0DKC2L2NH) | Selected candidate; verify exact revision, 74HC595 pin/bit mapping, OE defaults, supply input and valve-load suitability before physical use |
| 1 | DAOKAI CP2102 USB-to-UART adapter | [Amazon Canada](https://www.amazon.ca/dp/B0BCKBHQ8Y) | Use verified 3.3 V TTL TX/RX; leave adapter power pins disconnected when board externally powered |
| 1 only if verified compatible | SANSUN 12 V 2 A DC supply | [Amazon Canada](https://www.amazon.ca/dp/B01AZLA9XQ) | Do not apply 12 V until the actual board input rating and polarity are verified; seller documents conflict. Check supply label, connector and board/interface demand; reuse an existing suitable supply; current price unverified |
| Optional alternative only | USB-A to USB-B data cable for balance | [Amazon Canada](https://www.amazon.ca/dp/B00NH13DV2) | Existing green USB-to-RS232 adapter is already available and should be tried first; this cable is needed only if choosing the scale's alternative USB-B I/O path |

The controller needs an external supply matching the actual PCB input rating.
The seller's DC 5-12 V listing conflicts with its 5 V input diagram; the 5 V relay
coil markings do not establish the input rating. The installed board is marked
ESP32_Relay_X16_V1.2. Keep the proposed 12 V input disconnected until that revision
and terminal polarity are verified. The controller supply does not power the
computer, balance, pumps or 110-120 VAC valve coils. Those loads retain their
appropriate supplies and switching protection.

Confirm the SANSUN adapter's exact output plug and polarity on the ordered unit, then use a matching female jack/pigtail with strain relief to the controller input. If it is the advertised 5.5 x 2.1 mm centre-positive connector, use that mating size; do not assume 5.5 x 2.5 mm is equivalent. The pictured 16-channel board advertises a DC 5-12 V input range, but its exact revision and terminal polarity must still be verified. Never apply 12 V to a terminal documented only for 5 V. A supply's 2 A maximum rating is provisional until the complete board and interface demand is checked.

The selected board has more channels than the seven valve outputs required. Unused channels must remain in their reviewed inactive states. Its presence does not make the pump an ordinary relay-driven motor: pump speed uses a separate 0-10 V interface and remote start/stop. The firmware represents this candidate as a 16-bit shift-register board with unassigned hardware mappings; the product photograph does not establish a usable pin map or mains-load rating.

## Parts requiring final interface selection

| Item | Candidate or specification | Remaining check |
| --- | --- | --- |
| Pump command DAC | [DFRobot DFR0971](https://www.dfrobot.com/product-2613.html), [DigiKey Canada](https://www.digikey.ca/en/products/detail/dfrobot/DFR0971/18069239) | Exact module not found on Amazon.ca; confirm model-specific pump input/returns and output startup |
| Sensor ADC and conditioning | ADS1115-based acquisition or equivalent protected interface | Define 0-5 V and 0-10 V scaling, protection, grounding and calibration |
| Pump start/stop contact | Separate isolated signal contact/interface | Verify pump input and contact suitability |
| DB15 harness | Two-row 15-pin connector matching installed pump | Verify gender and pinout; do not substitute a three-row VGA connector |
| DC barrel adapter | Female 5.5 x 2.1 mm to secured pigtail or terminal | Check connector dimensions and mounting |
| Enclosure and wiring | Rated terminals, glands, wire, ferrules, labels, fuses and mounting | Size after layout and electrical review |

## Computer offered for comparison

The [HP ProDesk 600 G1 listing](https://www.amazon.ca/dp/B085RY6Z1C) was observed at CAD 199.99 and advertises i5-4570T, 16 GB RAM, 256 GB SSD and Windows 11 Pro. It explicitly warns that it has TPM 1.2. The generic summary table also conflicts with the storage description. Prefer the newer M720q configuration for the Windows application.

See [Microsoft Windows 11 specifications](https://www.microsoft.com/en-us/windows/windows-11-specifications) for TPM 2.0 requirements and [supported Intel processors](https://learn.microsoft.com/en-us/windows-hardware/design/minimum/supported/windows-11-supported-intel-processors).
