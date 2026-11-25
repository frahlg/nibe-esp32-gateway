# Installing the gateway on a NIBE F750

> **Safety.** The heat pump has mains voltage inside. Switch it off at the
> isolator before you open it, and if you are not sure, let an electrician do
> the wiring. The gateway itself only touches the 12 V accessory bus.

## What you need

- The assembled board in its printed box (see [ordering.md](ordering.md)).
- 4 × M3×16 pan-head screws (self-tapping for plastic, or machine screws with
  M3 heat-set inserts).
- A 4-pin 3.5 mm pluggable terminal plug (LCSC C5188251 or any Phoenix
  MC 1,5/4-ST-3,5 compatible plug).
- Cable: 4 cores, at least 0.5 mm², shielded if you can (LiYCY), for example
  LiYY 4×0.5. NIBE allows up to 50 m. Keep it at least 20 cm from mains cables.
- A small flat screwdriver and a T30 Torx driver for the F750 front panel.

## 1. Wire the plug

Wire the board's plug to terminal block **AA3-X4** on the input board **AA3**.
The board's terminal uses the same order as NIBE's own MODBUS 40 terminal.

| Gateway terminal | Signal | F750 AA3-X4 |
|---|---|---|
| 1 (left, square pad) | 12V | 12 |
| 2 | A | 11 |
| 3 | B | 10 |
| 4 (right) | GND | 9 |

The labels are on the board, the lid and the back of the board. If the pump
already has an RMU 40 room unit on X4, read the MODBUS 40 manual first: only
two units may share the bus, and the second one is wired after the first.

## 2. Open the heat pump and connect

1. Switch the heat pump off.
2. Pull the upper front panel straight out. Remove the two T30 screws at the
   lower edge of the main front panel, lift it out at the bottom and then up.
3. The input board AA3 sits on the right, below the display. Open its cover
   with your hand: push the catch down and tilt the cover out.
4. Run the cable in through grommet UB1 or UB2 at the back of the pump, as for
   any other low-voltage cable.
5. Connect the four cores to AA3-X4:9–12. The terminals are spring clamps that
   you open with a small screwdriver.
6. Close AA3 and the front panels.

## 3. Mount the box

- Mount the box **outside** the cabinet. The steel cabinet blocks Wi-Fi, and
  users who put boards inside the pump report that they lose contact with the
  access point.
- Keep the top of the box (the antenna end, away from the cable) free of metal.
  A wall next to the pump works well. On the pump's side panel the steel can
  weaken the signal; test first.
- The base has two keyhole slots, 22 mm apart, one above the other. Put two
  screws into the wall (head up to 8 mm across and 2.5 mm high, shank up to
  4 mm). Leave about 2.5 mm between the wall and the underside of each head,
  hang the base on them and slide it down. Then fit the board and the lid.
- Fasten the cable to the tongue below the terminal with a zip tie.

## 4. Power on and check

1. Plug the cable into the board's terminal and switch the heat pump on.
2. The red **PWR** LED lights up as soon as the pump gives 12 V.
3. With firmware loaded (see [../firmware](../firmware)), the green **STAT** LED
   shows the Wi-Fi state and the white **BUS** LED can blink on bus traffic.

## 5. Enable MODBUS 40 in the pump

1. Hold **Back** for 7 seconds to open the service menu.
2. Open menu **5.2 System settings** (on some firmware versions **5.2.4
   Accessories**) and tick **MODBUS 40**.
3. The pump starts to send telegrams. The gateway must answer them within a
   short time, or the pump raises **alarm 251** after about 15 seconds.

Only tick MODBUS 40 when the gateway runs firmware that answers the pump. If you
remove the gateway later, untick MODBUS 40 first.

## 6. Optional: LOG.SET

The pump can push 20 chosen registers about twice a second. Pick them in a
LOG.SET file and load it from a USB stick through the display (menu USB →
logging). The gateway works without it. See [protocol.md](protocol.md#logset).

## Troubleshooting

| What you see | Check |
|---|---|
| PWR LED off | 12 V on X4:12 and GND on X4:9; the PTC fuse F1 resets itself after a short |
| Garbage on the bus in the logs | GND (X4:9) must be connected, not only A and B |
| No answer from the pump at all | Swap A and B; one user had to |
| Alarm 251 now and then | Lower the log level, set `power_save_mode: none`, check Wi-Fi strength |
| Bus errors with another accessory after the gateway | Cut jumper JP1 (TERM) so only the last device terminates the bus |
