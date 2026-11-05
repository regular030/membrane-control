# Procurement baseline

Reuse the ESP32 relay board, USB-UART adapter, computer and balance cable.
The current pump uses the Garosa 3.3P-10V and the installed Masterflex
75211-70 DB25 cable. See the [wiring handoff](pump-interface.md).

## Order for the selected pump interface

| Qty | Item | Link / specification | Check before ordering |
| --- | --- | --- | --- |
| 1, if a replacement is needed | Garosa **3.3P-10V**, B07WZNV1V2 | [Exact Amazon Canada listing](https://www.amazon.ca/Voltage-Module-Voltage-Converter-Digital-Analog/dp/B07WZNV1V2) | Verify 3.3 V PWM input and the 0-10 V output version |
| 1, if needed | Regulated 24 V DC converter supply | Separate supply meeting the Garosa seller range of 15-30 V DC | Verify polarity, current rating and actual output. Keep separate from the 12 V sensors |
| Only if the onboard spare is unsuitable | Isolated pump contact interface | 3.3 V-compatible input, independent dry NO contact | Alternative GPIO26 control. Pump-side contacts connect across DB25 15/17 |
| As needed | Divider and input protection | HiLetgo B01HTC4XKY dividers are already selected | Verify scaling, filtering, input protection and grounding. Use an isolated feedback interface if required |
| As needed | DB25 connector, terminals and strain relief | Match the actual pump and cable | Trace all six assigned conductors and any DB25-to-DB15 adapter |

The onboard relay plan requires one independently wired spare channel with a
verified bit and fail-stop behavior. The [Garosa bench steps](pump-interface.md#garosa-converter-wiring)
cover output, zero and settling measurements before connection.

## Existing setup and optional replacements

| Item | Existing choice / reference | Reuse or replacement check |
| --- | --- | --- |
| Computer | [Lenovo ThinkCentre M720q, Amazon Canada](https://www.amazon.ca/dp/B08G1XKHPB), i5-8500T, 16 GB RAM, 256 GB SSD, Windows 11 Pro listing | Reuse a suitable lab computer first. For a replacement confirm power adapter, monitor cable, SSD condition and return coverage; current price unverified |
| Relay controller | [Srliya 16-channel ESP32-WROOM board](https://www.amazon.ca/dp/B0DKC2L2NH) | Verify the received ESP32_Relay_X16_V1.2 input rating, pin/bit map, startup/OE defaults and suitability for actual inductive valve loads |
| USB-UART | [DAOKAI CP2102 adapter](https://www.amazon.ca/dp/B0BCKBHQ8Y) | Verified 3.3 V TTL TX/RX; adapter power pins disconnected when board externally powered |
| DC supply | Existing believed 12 V supply; [previous SANSUN 12 V 2 A candidate](https://www.amazon.ca/dp/B01AZLA9XQ) | Verify its output and the board input rating. The Garosa has a separate 24 V supply |
| Balance cable | Current USB-A to USB-B data cable; [replacement reference](https://www.amazon.ca/dp/B00NH13DV2) | Reuse the current USB-B I/O path; the green USB-RS232 adapter is not needed for that path |
| DC connector | Matching female jack/pigtail, securely mounted | Confirm actual plug dimensions and polarity; 5.5 x 2.1 mm and 5.5 x 2.5 mm are not interchangeable assumptions |
| Enclosure and wiring | Rated terminals, glands, wire, ferrules, fuses, labels and mounting | Size after electrical/layout review, keeping mains valve conductors and low-voltage pump/sensor circuits separated |

The computer, balance, pump motor and 110-120 VAC valve coils retain their
appropriate supplies. The pump relay contact pair must stay separate from
the mains valve distribution.

## Computer offered for comparison

The [HP ProDesk 600 G1 listing](https://www.amazon.ca/dp/B085RY6Z1C) was observed at CAD 199.99 and advertises i5-4570T, 16 GB RAM, 256 GB SSD and Windows 11 Pro. It explicitly warns that it has TPM 1.2. The generic summary table also conflicts with the storage description. Prefer the newer M720q configuration for the Windows application.

See [Microsoft Windows 11 specifications](https://www.microsoft.com/en-us/windows/windows-11-specifications) for TPM 2.0 requirements and [supported Intel processors](https://learn.microsoft.com/en-us/windows-hardware/design/minimum/supported/windows-11-supported-intel-processors).
