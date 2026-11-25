# Ordering the board and printing the box

Everything you upload is in [`hardware/production/`](../hardware/production):

| File | What it is |
|---|---|
| `nibe-esp32-gateway-gerbers.zip` | Gerber and drill files |
| `nibe-esp32-gateway-bom-jlcpcb.csv` | Bill of materials with LCSC part numbers |
| `nibe-esp32-gateway-cpl-jlcpcb.csv` | Pick-and-place (component positions) |
| `nibe-esp32-gateway-schematic.pdf` | Schematic |
| `nibe-esp32-gateway-assembly-top.pdf` | Assembly drawing with all references |
| `nibe-esp32-gateway.step` | 3D model of the assembled board |

The files are made for [JLCPCB](https://jlcpcb.com). Any maker that takes Gerbers
works for the bare board; for assembly you then need to map the parts yourself.

## Before you order

Check that the parts are still in stock. Stock changes every day.

```bash
python3 hardware/generator/tools/check_stock.py
```

It lists stock, price and basic/extended status for every part and fails if a
part is short. On 2026-11-25 every part was in stock and the parts cost about
**USD 8 per board**. Ten parts are "extended" at JLCPCB, which adds a one-off
loading fee per part type to each order.

If a part is gone, pick an equal part in the JLCPCB library and change its
number in [`hardware/generator/parts.py`](../hardware/generator/parts.py), then
rebuild (see [hardware/README.md](../hardware/README.md)).

## Order at JLCPCB

1. Upload `nibe-esp32-gateway-gerbers.zip`.
2. Board settings: 2 layers, 1.6 mm, any colour, HASL lead-free or ENIG,
   1 oz copper. The defaults are fine; the board uses 0.2 mm clearance,
   0.25 mm tracks and 0.3 mm vias.
3. Turn on **PCB Assembly**, top side, **Standard**. JLCPCB only places the
   ESP32 module with Standard assembly, and Standard also places the
   through-hole terminal J2. Tick **Confirm Parts Placement** so an engineer
   checks the placement before the build.
4. Upload the BOM and the CPL file.
5. **Check the placement preview.** JLCPCB and KiCad do not always agree on the
   zero rotation or origin of a part. The CPL carries rotation corrections for
   U1, U2, U4, D4 and J1, and position offsets for U3, J1 and J2; each was
   checked in the preview on 2026-11-25 (see `JLC_ROTATIONS` and `JLC_OFFSETS`
   in `hardware/generator/fab.py`). Still look at every part with a pin-1 mark:
   U1 (USB ESD), U2 (RS-485), U3 (ESP32 module), U4 (regulator), D1–D3, D4 and
   the LEDs. In the preview a pink dot marks pin 1 of JLCPCB's part; it must sit
   on the pin-1 pad. Rotate any part where it does not. Check too that the
   module's pads sit on the board's pads (its antenna must not stick out past
   the top edge), that the USB-C socket's pins sit on their pads and that J2's
   four pins sit in their holes.
6. J3 (expansion header) and JP1 are not fitted. JP1 is a solder jumper that is
   closed by a copper bridge on the board.

## Loose parts

Order these from [LCSC](https://www.lcsc.com) (you can ship them with the
JLCPCB order):

| Qty | Part | LCSC |
|---|---|---|
| 1 | 4-pin 3.5 mm pluggable terminal plug, screw type | C5188251 |
| 4 | M3×16 pan-head screw (self-tapping for plastic, or machine screw with heat-set inserts) | – |

## Print the box

The box is in [`enclosure/`](../enclosure): `base.stl` and `lid.stl` (STEP files
too). Both print without supports, the lid with its top face on the bed.

| Setting | Value |
|---|---|
| Material | PETG (best near a heat pump) or PLA |
| Layer height | 0.2 mm |
| Walls | 3 perimeters |
| Infill | 25 % |
| Supports | none |

The text on the lid is engraved 0.5 mm deep. A colour change at the first
layers makes it stand out.

## Assembly

1. Fit the board onto the four posts in the base, terminal towards the opening
   with the tongue.
2. Put the lid on, posts down, and fasten it with the four M3×16 screws. The
   screws go through the lid and the board into the base and clamp the board.
3. Press RESET or BOOT through the small holes with a paper clip.

## Variant: external antenna

If Wi-Fi is weak where the box hangs, order the board with
**ESP32-S3-WROOM-1U-N8R2** (LCSC C3013944) in place of the WROOM-1. It has the
same pads and a U.FL socket for an external antenna, but its body is 6.3 mm
shorter. Keep the CPL as it is and check in the placement preview that the
module's pads sit on the board's pads; if they do not, move U3 along Y in the
preview until they do. Drill a 6.5 mm hole in the top wall of the base for an
SMA bulkhead and use a U.FL-to-SMA pigtail.
