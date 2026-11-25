# CLAUDE.md

Open-hardware ESP32-S3 gateway for the NIBE F-series accessory bus (MODBUS 40
port). Hardware rev 1.0 is designed and reviewed; the ESPHome firmware is in
`firmware/`. Neither has run on a real board yet.

## Ground rules

- `hardware/generator/circuit.py` is the single source of truth for the board.
  Never hand-edit `hardware/kicad/*` or `hardware/production/*`: the build
  overwrites them.
- Part numbers live in `hardware/generator/parts.py`. Check stock with
  `python3 hardware/generator/tools/check_stock.py` after a build.
- The terminal order (12V, A, B, GND = NIBE AA3-X4:12, 11, 10, 9) and the GPIO map
  (GPIO9 TX, GPIO12 RX, GPIO10 DE) are interfaces. If you change them, update
  `firmware/README.md`, `firmware/nibe-gateway.yaml`, the silkscreen, the lid
  labels and `docs/installation.md` in the same change.
- Protocol facts in `docs/protocol.md` carry sources. Mark anything you cannot
  confirm as not confirmed.

## Build and check (the feedback loop)

```bash
cd hardware && ./build.sh          # Docker, KiCad 9 image; sch + pcb + fab
cd enclosure && uv run enclosure.py
```

A good hardware build prints all of:

- `netlist: 32 nets` and no `NETLIST ERROR` lines
- `ERC: 0 issues (0 errors)`
- `routing done ... failed: none`
- `via-in-pad check: 0 vias within 0.15 mm of an SMD pad`
- `DRC summary: clean` (includes schematic parity and silkscreen checks)

A good enclosure run prints `overlap = 0.000 mm3` for base and lid.

Then look at `docs/images/pcb-top.png` and `docs/images/enclosure-*.png`.

Single steps: `./build.sh sch`, `./build.sh pcb`, `./build.sh fab`.
`NOROUTE=1 ./build.sh pcb` places parts without routing (fast placement checks).

## Layout notes

- Board coordinates are mm from the top-left corner, y down. The antenna is at
  the top edge (y < 6.4 is a copper keep-out on both layers); mounting holes stay
  below y = 6.5.
- The router uses a 0.05 mm grid for nets on 0.5 mm pitch pins (`FINE_NETS` in
  `build_pcb.py`) and 0.1 mm for the rest.
- Ground is never routed: pours on both layers, one via next to (never in) each
  ground pad, stitching vias. `PRE_VIAS` in `build_pcb.py` places a ground via
  before routing where signal tracks would box a pad in.
- No via in or within 0.15 mm of an SMD pad (`Router.no_via`). The buck's SW and
  VBUCK are top-layer copper areas (`BUCK_ZONES` in `circuit.py`); keep C4 at the
  VIN/GND pins and the FB divider on the side away from SW.
- JLCPCB places parts by its own footprint origin and rotation. New parts may
  need entries in `JLC_ROTATIONS`/`JLC_OFFSETS` in `fab.py`; check every one in
  the JLCPCB placement preview.
