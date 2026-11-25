"""Print the pins of library symbols (number, name, type, position).

Usage (inside the KiCad image): python3 tools/pins.py Lib:Symbol ...
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import schgen
for spec in sys.argv[1:]:
    lib, name = spec.split(":")
    s = schgen.flat_symbol(lib, name)
    pins = schgen.symbol_pins(s)
    print("##", spec, "bbox", schgen.symbol_bbox(s))
    print("   " + "  ".join("%s:%s(%s)@%g,%g/%d" % (p["number"], p["name"], p["type"][:3], p["x"], p["y"], p["angle"]) for p in pins))
