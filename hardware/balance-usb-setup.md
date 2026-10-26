# Connect the Adam Nimbus balance

The latest photos show the existing **USB-to-RS232 adapter connected to the
balance's DB9 RS-232 port**. Reuse that connection first. It is independent of
the ESP32's USB-to-UART connection; select a different COM port for each device.

## Choose one connection path

| Path | Cable and driver |
| --- | --- |
| Existing, preferred | Balance DB9 RS-232 → existing green USB-to-RS232 adapter → computer USB. Use the driver for the adapter's actual chipset if Windows needs one. Its chipset cannot be identified from the photos alone. |
| Alternative | Balance USB-B **I/O** → USB data cable → computer USB. Use [Adam's Nimbus driver](https://adamequipment.com/support/software-downloads.html) if required. |

Use one path at a time. The balance's USB-A **Display** socket is for the remote
display, not the computer. The balance retains its own power supply. The
ESP32's 3.3 V TTL UART adapter is not a substitute for an RS-232 interface.

## Set up serial output

1. In Windows **Device Manager → Ports (COM & LPT)**, identify the balance
   connection by unplugging and reconnecting its USB adapter or cable. Do not
   assume a COM number from the photo or select the ESP32's port.
2. On the balance, enable its serial interface. Use **9600 baud, NONE parity**
   for the current app's **8 data bits, no parity, 1 stop bit (8N1)** connection.
   These are recommended matching settings, not settings confirmed by a photo.
3. Select grams and continuous single-line output, with stable-only filtering
   off while collecting liquid. The documented format is `123.4 g` followed by
   carriage return and line feed. Restart the balance after changing its serial
   settings, as required by the [Nimbus manual, sections 11 and 13.3](https://adamequipment.com.cn/media/docs/manuals/NBLe_i_UM_EN.pdf).
4. Stop any app run, uncheck **Simulation mode**, and open **Connections and
   settings**. Refresh the ports, select the balance's COM port and **9600** in
   the **Balance** section, then click **Connect**. Close other programs using
   that port first.

## Confirm readings

The app waits for incoming weights; it does not configure the balance or send
print/poll commands. A detected USB adapter alone does not confirm balance data.
Confirm that a known change on the pan changes the displayed mass.

Without a valid weight for more than **3 seconds**, the app marks weight data
stale. Stable-only output, manual-print mode or a long periodic-output interval
can cause this even when the cable is connected. Use continuous output for the
current app. Its baud selection must match the balance; the app's serial format
is fixed at 8N1. The documented simple mass stream has no per-reading stability flag.
