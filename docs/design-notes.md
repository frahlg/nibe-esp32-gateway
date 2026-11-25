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
  LM2596 module on the pump's supply. FB1 is a 3 A bead (TDK MPZ2012S221A):
  on USB alone the buck draws up to about 0.5 A in Wi-Fi bursts, the full
  rating of a common 600 Ω bead.
- **U4 TPS62933** takes 3.8–30 V, so the same part runs from 12 V and from USB
  (about 4.3 V after the diode). It has spread-spectrum switching for low EMI
  and runs at 500 kHz with RT open. That is the frequency TI pairs with the
  4.7 µH inductor for a 3.3 V output (datasheet SLUSEA4, table 10-2); at
  1.2 MHz TI asks for 2.2 µH, and on USB the off-time would come close to the
  140 ns minimum. It starts on its own (EN floats, which the datasheet allows;
  EN is only rated to 6 V, so it must not see VSYS).
  Output: 0.8 V × (1 + 47 k/15 k) = 3.31 V. It can give 3 A, far more than the
  ESP32-S3 needs (about 0.35 A peak), so it runs cool.
- **Buck layout** follows the datasheet's layout section: C4 (100 nF) sits
  next to the VIN and GND pins, so the input loop is about 1 × 1.3 mm; VBUCK
  and SW are copper areas, not thin tracks; the FB divider sits on the side
  away from SW, 1.3 mm from the FB pin; the bottom ground plane under the
  regulator is unbroken.

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
drawings apply as they are. The fitted header (Dorabo DB2ERC-3.5-4P) has
0.8 mm square pins, 1.13 mm across the corners, so its holes are 1.4 mm as
Dorabo's drawing asks, not the 1.2 mm of KiCad's Phoenix footprint.

## Board

- 2 layers, 50 × 58 mm, ground pour on both layers with stitching vias.
- No via sits in or next to an SMD pad: an open via drains solder paste from
  the pad and can leave a starved joint or tombstone a small part. The router
  keeps every via at least 0.15 mm (copper to copper) from any SMD pad, and the
  build counts any that break the rule. Every ground pad has its own via just
  outside it.
- The module's ground pad keeps 4 of the footprint's 12 vias, covered by
  solder mask on the bottom, for the same reason.
- All passives 0603/0805 so they can be reworked by hand.
- LEDs: red PWR with 1 kΩ, green STAT and white BUS with 100 Ω. The green and
  white LEDs drop 2.6–3.1 V, so from a 3.3 V pin they need a small resistor to
  light at a few mA.
- Generated from Python ([hardware/generator](../hardware/generator)) and
  checked by KiCad's ERC, DRC and schematic-parity checks on every build.

## Known gaps

These are open until the first boards are built and tested:

- Current draw from X4:12 is estimated, not measured. NIBE does not publish
  how much X4:12 can give.
- Whether the pump already terminates or biases the bus is unknown. JP1 makes
  the terminator easy to remove.
- The firmware compiles and passes the bench tester's own tests, but has not
  run on a board yet (see [firmware](../firmware)).

## Reviews

Two independent reviews (electrical and layout) ran before the first order on
2026-11-25. They found no wrong pin or polarity. Fixed before ordering:

- U3 and J1 were placed by KiCad's footprint origin; JLCPCB uses its own.
  The CPL now carries both offsets (`JLC_OFFSETS` in `fab.py`), checked in
  JLCPCB's placement preview.
- J2's holes were too small for the fitted header (see Terminal).
- 40 vias sat in SMD pads, among them every ground pad (see Board).
- The buck switched at 1.2 MHz with an inductor sized for 500 kHz, and its
  layout had a long input loop and a long FB track near SW (see Power).
- FB1 ran at its current rating on USB; the green and white LEDs were dim.

## Ideas for a later revision

- THVD1410 in place of THVD1450: same pins, slew-rate limited, a better match
  for 9600 baud on a long cable.
- Ethernet (W5500) for sites with poor Wi-Fi.
- A divider on the 12 V input to an ADC pin, to report the pump's supply.
- A connector for a second bus (for example a P1 meter or an EV charger).
