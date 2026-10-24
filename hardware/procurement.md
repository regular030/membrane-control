# Procurement baseline

Checked 24 October 2026. Listings, prices and sellers can change. Quantities below support the initial bench prototype, not a complete commissioned mains assembly. Reuse existing suitable items.

## Initial purchases

| Qty | Item | Link | Purchase condition |
| --- | --- | --- | --- |
| 1 | Lenovo ThinkCentre M720q, i5-8500T, 16 GB RAM, 256 GB SSD, Windows 11 Pro | [Amazon Canada](https://www.amazon.ca/dp/B08G1XKHPB) | Include matching power adapter and confirm monitor cable/return coverage; current price unverified |
| 1 | DORHEA 8-channel ESP32 relay board | [Amazon Canada](https://www.amazon.ca/dp/B0H6JRXPHD) | Low-voltage bench prototype only until schematic, startup behavior and valve-load suitability verified |
| 1 | DAOKAI CP2102 USB-to-UART adapter | [Amazon Canada](https://www.amazon.ca/dp/B0BCKBHQ8Y) | Use verified 3.3 V TTL TX/RX; leave adapter power pins disconnected when board externally powered |
| 1 if needed | StarTech SVA12M2NEUA 12 V 2 A supply | [Amazon Canada](https://www.amazon.ca/dp/B01N5HCQNS) | Observed CAD 24.16; check total demand, polarity and board input; reuse existing supply if suitable |
| 1 if needed | USB-A to USB-B data cable for balance | [Amazon Canada](https://www.amazon.ca/dp/B00NH13DV2) | Reuse existing suitable data cable; check required cable length |

The [StarTech manufacturer datasheet](https://media.startech.com/cms/pdfs/sva12m2neua_datasheet.pdf) identifies 12 V DC, 2 A, positive centre and 5.5 x 2.1 mm connector dimensions. Connect through a matching female jack/pigtail with strain relief to the board's documented 12 V-compatible input. Do not feed the board's 5 V terminal with 12 V.

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
