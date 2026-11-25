# Design notes

Why the board looks the way it does. Read this before you change it.

## Goals

1. One cable to the heat pump, nothing else to plug in.
2. Survive wiring mistakes, surges on a long cable and a noisy utility room.
3. Order fully assembled from JLCPCB, with parts that are in stock.
4. Work with the firmware people already use (esphome-nibe, NibeGW, nibegw-esp).

## Power: from the heat pump

The F750 gives 12 V on AA3-X4:12, next to the bus, and NIBE's own MODBUS 40
runs from it (rated 45–80 mA). So the board takes its power there too, and one
4-core cable carries everything. USB-C is there for flashing and bench work.

```
X4:12 ─ F1 PTC 0.5 A ─┬─ D3 SMAJ18A ─ GND        (surge clamp, 29 V max)
                      ├─ C1 10 µF
                      └─ D2 B5819W ─┐
USB VBUS ─ D1 B5819W ───────────────┴─ VSYS ─ FB1 ferrite ─ VBUCK ─ U4 TPS62933 ─ 3.3 V
```

- **F1** (resettable fuse) protects the pump's 12 V if the board shorts. With
  reverse polarity D3 conducts and F1 trips.
- **D3** clamps surges from the cable. Its clamp voltage (29 V) is below the
  regulator's 32 V limit.
- **D1/D2** let USB and the pump feed the board at the same time without
  feeding each other.
- **FB1** with the capacitors on both sides keeps the regulator's switching
  noise off the pump's 12 V. One community report saw pump errors with a noisy
  LM2596 module on the pump's supply.
- **U4 TPS62933** takes 3.8–30 V, so the same part runs from 12 V and from USB
  (about 4.3 V after the diode). It has spread-spectrum switching for low EMI,
  runs at 1.2 MHz (RT to GND) and starts on its own (EN floats, which the
  datasheet allows; EN is only rated to 6 V, so it must not see VSYS).
  Output: 0.8 V × (1 + 47 k/15 k) = 3.31 V. It can give 3 A, far more than the
  ESP32-S3 needs (about 0.35 A peak), so it runs cool.

We estimate the board draws about 40 mA at 12 V on average and up to about
120 mA in Wi-Fi bursts. Not measured yet.

## RS-485

- **THVD1450** (TI): 3.3 V, ±18 kV IEC ESD on A/B, and a fail-safe receiver
  that reads an idle, open or shorted bus as "1". That keeps garbage out of the
  UART when nobody talks.
- **PSM712** TVS array on A/B, made for RS-485 (−7 V…+12 V working range).
- **DE and /RE on one GPIO** (GPIO10), with a 10 kΩ pull-down so the board only
  listens until the firmware runs. esphome-nibe (`dir_pin`) and nibegw-esp
  (UART RTS) both drive such a pin. One community report found that a module
  with automatic direction control failed with NIBE, while GPIO control worked.
- **RO pull-up** (10 kΩ) keeps the UART line high while the receiver is off
  during transmit.
- **Termination and bias**: 120 Ω across A/B through solder jumper JP1 (closed
  by default) and 4.7 kΩ bias resistors. This copies the LilyGo T-CAN485, the
  board most esphome-nibe users run. Cut JP1 if another device sits after the
  gateway on the bus.
- **Ground**: board ground ties straight to X4:9. Users who left the bus ground
  open saw garbage on the bus. Since the board runs from the pump, there is one
  ground and no ground loop. No galvanic isolation: it would add parts and
  cost and protect against a problem this wiring does not have. Plug a laptop
  into USB-C while the board is on the pump only for short service work.

## ESP32-S3-WROOM-1-N8R2

- Native USB on GPIO19/20, so no USB-serial chip and no auto-reset circuit.
- Two cores: Wi-Fi runs on one, the bus answers on time on the other.
- 8 MB flash and 2 MB PSRAM leave room for later firmware (OTA, local logic).
- The bus pins sit on the module's bottom row (GPIO9, 10, 12), straight above
  the transceiver, so the three signals run in short straight lines.
- Strapping pins GPIO0 (BOOT button), GPIO3, GPIO45 and GPIO46 are left alone.
- The antenna sits at the top edge with no copper on either layer under or
  beside it. The mounting holes are below the antenna zone.

## Terminal

A 3.5 mm pluggable terminal (Phoenix MC 1,5 style). You wire the plug at the
pump, then plug it in; you can take the gateway away without touching the pump.
The pin order is 12V, A, B, GND, the same as on MODBUS 40, so NIBE's wiring
drawings apply as they are.

## Board

- 2 layers, 50 × 58 mm, ground pour on both layers with stitching vias.
- All passives 0603/0805 so they can be reworked by hand.
- Generated from Python ([hardware/generator](../hardware/generator)) and
  checked by KiCad's ERC, DRC and schematic-parity checks on every build.

## Known gaps

These are open until the first boards are built and tested:

- Current draw from X4:12 is estimated, not measured. NIBE does not publish
  how much X4:12 can give.
- Whether the pump already terminates or biases the bus is unknown. JP1 makes
  the terminator easy to remove.
- JLCPCB rotation for U4 (SOT-583) and the module must be checked in the
  placement preview.
- The firmware is not written yet (see [firmware](../firmware)).

## Ideas for a later revision

- Ethernet (W5500) for sites with poor Wi-Fi.
- A divider on the 12 V input to an ADC pin, to report the pump's supply.
- A connector for a second bus (for example a P1 meter or an EV charger).
