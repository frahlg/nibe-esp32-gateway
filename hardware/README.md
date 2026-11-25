# Hardware

The board is described in Python and turned into a normal KiCad 9 project. You
can open `kicad/nibe-esp32-gateway.kicad_pro` in KiCad and look at or edit
everything, but the next build overwrites hand edits. Change the Python, not the
KiCad files.

```
hardware/
├── build.sh                 build everything inside the official KiCad 9 Docker image
├── fetch-3d-models.sh       download KiCad 3D models (only for renders and STEP)
├── generator/
│   ├── circuit.py           THE CIRCUIT: parts, nets, schematic and board positions
│   ├── parts.py             part catalogue: symbol, footprint, LCSC number
│   ├── build.py             schematic, netlist check, ERC
│   ├── build_pcb.py         placement, routing, ground pours, silkscreen, DRC
│   ├── build_fab.py         Gerbers, drill, BOM, CPL, PDFs, STEP, renders
│   ├── schgen.py            writes .kicad_sch files
│   ├── pcbgen.py            pcbnew helpers
│   ├── router.py            small A* router (two layers, 45°, vias)
│   ├── fab.py               JLCPCB BOM/CPL and rotation corrections
│   ├── sexp.py              S-expression reader/writer
│   └── tools/               pins.py, footprint_pads.py, check_stock.py
├── kicad/                   generated KiCad project (schematic, board, project)
└── production/              generated files to order the board
```

## Build

You need Docker. Nothing else is installed on your machine.

```bash
cd hardware
./fetch-3d-models.sh   # optional, once: 3D models for renders and the STEP file
./build.sh             # schematic + board + production files
```

`./build.sh sch`, `./build.sh pcb` and `./build.sh fab` run one step each.

## What a build checks

Each step stops or reports when something is wrong:

1. **Netlist check.** The schematic is exported to a netlist with `kicad-cli`
   and compared pin by pin with `circuit.py`. Any difference stops the build.
2. **ERC** on the schematic (must report 0 issues).
3. **Routing.** Every net must route; failures are listed.
4. **DRC with schematic parity** on the board: clearances, unconnected items,
   and that the board matches the schematic. The build prints `DRC summary:
   clean` when all is well.

The enclosure has its own fit check against the board's STEP file (see
[../enclosure](../enclosure)).

## How the board is made

- **Schematic.** Every pin gets a short wire and a net label or power symbol.
  That keeps the generated drawing readable and easy to check.
- **Placement** is hand-written in `circuit.py`, in millimetres from the top-left
  corner of the board.
- **Routing.** A small grid router (`router.py`) routes one net at a time on a
  0.1 mm grid, or 0.05 mm next to 0.5 mm pitch pins. Power nets get wider
  tracks. Ground is not routed: both layers have a ground pour, each ground pad
  gets its own via, and stitching vias tie the pours together.
- **Design rules** follow JLCPCB's standard 2-layer process: 0.2 mm clearance,
  0.25 mm signal tracks, 0.4–0.6 mm power tracks, 0.3/0.6 mm vias.

## Changing the circuit

1. Edit `circuit.py` (and `parts.py` for a new part).
2. `./build.sh` and read the output: netlist, ERC, routing, DRC.
3. Look at `docs/images/pcb-top.png` and `production/*.pdf`.
4. `python3 generator/tools/check_stock.py` before you order.
