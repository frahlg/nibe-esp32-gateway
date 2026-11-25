"""Generate a KiCad 9 schematic (.kicad_sch) from a Python circuit description.

Every symbol pin gets a short wire stub that ends in a net label, a power
symbol or a no-connect flag. That keeps the generated drawing readable and
makes the connectivity easy to check: `kicad-cli sch export netlist` must give
back exactly the nets that circuit.py asks for (build.py checks this).
"""
import copy
import math
import uuid

import sexp
from sexp import Sym

KICAD_SYMBOLS = "/usr/share/kicad/symbols"
POWER_SYMBOLS = {"GND", "+3V3"}
NS = uuid.UUID("6b1f0e0c-4f9e-4b8a-9d55-2a0f3c1e7a11")

_libs = {}


def uid(*parts):
    return str(uuid.uuid5(NS, "/".join(str(p) for p in parts)))


def _lib(name):
    if name not in _libs:
        root = sexp.parse(open("%s/%s.kicad_sym" % (KICAD_SYMBOLS, name)).read())
        _libs[name] = {s[1]: s for s in sexp.findall(root, "symbol")}
    return _libs[name]


def flat_symbol(lib, name):
    """Return a deep copy of a library symbol with `extends` resolved."""
    s = copy.deepcopy(_lib(lib)[name])
    ext = sexp.find(s, "extends")
    if not ext:
        return s
    parent = flat_symbol(lib, ext[1])
    pname = parent[1]
    out = [Sym("symbol"), name]
    child_props = {p[1]: p for p in sexp.findall(s, "property")}
    for item in parent[2:]:
        if isinstance(item, list) and item and item[0] == "property":
            out.append(child_props.pop(item[1], item))
        elif isinstance(item, list) and item and item[0] == "symbol":
            sub = copy.deepcopy(item)
            sub[1] = sub[1].replace(pname + "_", name + "_", 1)
            out.append(sub)
        else:
            out.append(item)
    # child-only properties go after the inherited ones
    insert_at = max(i for i, it in enumerate(out) if isinstance(it, list) and it and it[0] == "property") + 1
    for p in child_props.values():
        out.insert(insert_at, p)
        insert_at += 1
    return out


def symbol_pins(sym):
    """Pins of unit 1 / body style 1 as dicts in library coordinates (y up)."""
    pins = []
    name = sym[1].split(":")[-1]
    for sub in sexp.findall(sym, "symbol"):
        parts = sub[1][len(name) + 1:].split("_")
        unit, style = int(parts[0]), int(parts[1])
        if unit not in (0, 1) or style not in (0, 1):
            continue
        for p in sexp.findall(sub, "pin"):
            at = sexp.find(p, "at")
            hidden = any(isinstance(x, list) and x[0] == "hide" for x in p) or "hide" in p
            pins.append({
                "number": sexp.find(p, "number")[1],
                "name": sexp.find(p, "name")[1],
                "type": str(p[1]),
                "x": float(at[1]), "y": float(at[2]), "angle": float(at[3]),
                "length": float(sexp.find(p, "length")[1]),
                "hidden": hidden,
            })
    return pins


def symbol_bbox(sym):
    xs, ys = [], []
    name = sym[1].split(":")[-1]
    for sub in sexp.findall(sym, "symbol"):
        for item in sub:
            if not isinstance(item, list):
                continue
            if item[0] == "rectangle":
                for k in ("start", "end"):
                    v = sexp.find(item, k)
                    xs.append(float(v[1])); ys.append(float(v[2]))
            elif item[0] == "polyline":
                for xy in sexp.findall(sexp.find(item, "pts"), "xy"):
                    xs.append(float(xy[1])); ys.append(float(xy[2]))
            elif item[0] == "circle":
                c = sexp.find(item, "center"); r = float(sexp.find(item, "radius")[1])
                xs += [float(c[1]) - r, float(c[1]) + r]; ys += [float(c[2]) - r, float(c[2]) + r]
            elif item[0] == "pin":
                at = sexp.find(item, "at")
                xs.append(float(at[1])); ys.append(float(at[2]))
    if not xs:
        return (-2.54, -2.54, 2.54, 2.54)
    return (min(xs), min(ys), max(xs), max(ys))


def rot(vx, vy, r):
    """Rotate a screen vector (y down) counter-clockwise on screen by r degrees."""
    r %= 360
    if r == 0:
        return vx, vy
    if r == 90:
        return vy, -vx
    if r == 180:
        return -vx, -vy
    if r == 270:
        return -vy, vx
    raise ValueError(r)


def lib_to_screen(px, py, r):
    return rot(px, -py, r)


def snap(v, g=1.27):
    return round(round(v / g) * g, 4)


def eff(size=1.27, justify=None, hide=False, bold=False):
    font = [Sym("font"), [Sym("size"), size, size]]
    if bold:
        font.append([Sym("bold"), Sym("yes")])
    e = [Sym("effects"), font]
    if justify:
        e.append([Sym("justify")] + [Sym(j) for j in justify.split()])
    if hide:
        e.append([Sym("hide"), Sym("yes")])
    return e


class Schematic:
    def __init__(self, project, title, rev, date, company, paper="A3", comments=()):
        self.project = project
        self.root_uuid = uid(project, "root")
        self.items = []
        self.lib_symbols = {}
        self.pwr_count = 0
        self.title = [Sym("title_block"), [Sym("title"), title], [Sym("date"), date],
                      [Sym("rev"), rev], [Sym("company"), company]]
        for i, c in enumerate(comments, 1):
            self.title.append([Sym("comment"), i, c])
        self.paper = paper
        self.expected = {}  # (ref, pin) -> net, for verification

    # ------------------------------------------------------------------ helpers
    def _use_symbol(self, lib_id):
        if lib_id not in self.lib_symbols:
            lib, name = lib_id.split(":")
            s = flat_symbol(lib, name)
            s[1] = lib_id
            self.lib_symbols[lib_id] = s
        return self.lib_symbols[lib_id]

    def wire(self, x1, y1, x2, y2):
        self.items.append([Sym("wire"), [Sym("pts"), [Sym("xy"), x1, y1], [Sym("xy"), x2, y2]],
                           [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("default")]],
                           [Sym("uuid"), uid(self.project, "wire", x1, y1, x2, y2)]])

    def label(self, net, x, y, out):
        ang, just = {(1, 0): (0, "left bottom"), (-1, 0): (180, "right bottom"),
                     (0, -1): (90, "left bottom"), (0, 1): (270, "right bottom")}[out]
        self.items.append([Sym("label"), net, [Sym("at"), x, y, ang], [Sym("fields_autoplaced"), Sym("yes")],
                           eff(justify=just), [Sym("uuid"), uid(self.project, "label", net, x, y)]])

    def no_connect(self, x, y):
        self.items.append([Sym("no_connect"), [Sym("at"), x, y], [Sym("uuid"), uid(self.project, "nc", x, y)]])

    def text(self, s, x, y, size=2.0, bold=True):
        self.items.append([Sym("text"), s, [Sym("exclude_from_sim"), Sym("no")], [Sym("at"), x, y, 0],
                           eff(size=size, justify="left bottom", bold=bold), [Sym("uuid"), uid(self.project, "text", s, x, y)]])

    def box(self, x1, y1, x2, y2):
        self.items.append([Sym("rectangle"), [Sym("start"), x1, y1], [Sym("end"), x2, y2],
                           [Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("dash")]],
                           [Sym("fill"), [Sym("type"), Sym("none")]],
                           [Sym("uuid"), uid(self.project, "box", x1, y1, x2, y2)]])

    def _instance(self, lib_id, ref, value, x, y, r, props, in_bom=True, on_board=True, dnp=False,
                  ref_at=None, val_at=None, hide_ref=False, hide_val=False):
        sym = self._use_symbol(lib_id)
        su = uid(self.project, "sym", ref)
        node = [Sym("symbol"), [Sym("lib_id"), lib_id], [Sym("at"), x, y, r], [Sym("unit"), 1],
                [Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), in_bom], [Sym("on_board"), on_board],
                [Sym("dnp"), dnp], [Sym("uuid"), su]]
        bx0, by0, bx1, by1 = symbol_bbox(sym)
        # rotated body size on screen
        w, h = (bx1 - bx0, by1 - by0) if r in (0, 180) else (by1 - by0, bx1 - bx0)
        # property placement next to the body
        if ref_at is None or val_at is None:
            if w < 6 and h >= w:  # small vertical part: text to the right
                ref_at = ref_at or (x + w / 2 + 1.27, y - 1.27, "left")
                val_at = val_at or (x + w / 2 + 1.27, y + 1.27, "left")
            elif h < 6:  # small horizontal part: reference above, value below
                ref_at = ref_at or (x, y - h / 2 - 1.27, None)
                val_at = val_at or (x, y + h / 2 + 1.27, None)
            else:
                ref_at = ref_at or (x + bx0, y - by1 - 1.27, "left")
                val_at = val_at or (x + bx0, y - by0 + 2.54, "left")
        node.append([Sym("property"), "Reference", ref, [Sym("at"), ref_at[0], ref_at[1], 0],
                     eff(justify=ref_at[2], hide=hide_ref)])
        node.append([Sym("property"), "Value", value, [Sym("at"), val_at[0], val_at[1], 0],
                     eff(justify=val_at[2], hide=hide_val)])
        lib_props = {p[1]: p[2] for p in sexp.findall(sym, "property")}
        merged = {"Footprint": lib_props.get("Footprint", ""), "Datasheet": lib_props.get("Datasheet", "~"),
                  "Description": lib_props.get("Description", "")}
        merged.update(props)
        for k, v in merged.items():
            node.append([Sym("property"), k, v, [Sym("at"), x, y, 0], eff(hide=True)])
        for p in symbol_pins(sym):
            node.append([Sym("pin"), p["number"], [Sym("uuid"), uid(self.project, "pin", ref, p["number"])]])
        node.append([Sym("instances"), [Sym("project"), self.project,
                                        [Sym("path"), "/" + self.root_uuid, [Sym("reference"), ref], [Sym("unit"), 1]]]])
        self.items.append(node)
        return sym

    # ------------------------------------------------------------------ public
    def part(self, lib_id, ref, value, x, y, nets, r=0, props=None, stub=2.54, dnp=False,
             in_bom=True, ref_at=None, val_at=None, hide_val=False):
        """Place a symbol and connect each pin (by number) to a net.

        nets: {pin_number: net_name or None (= no connect)}. Net names starting
        with '+' or equal to 'GND' use KiCad power symbols, others local labels.
        Pins that are stacked on the same spot share one stub.
        """
        props = props or {}
        sym = self._instance(lib_id, ref, value, x, y, r, props, in_bom=in_bom, dnp=dnp,
                             ref_at=ref_at, val_at=val_at, hide_val=hide_val)
        pins = symbol_pins(sym)
        known = {p["number"] for p in pins}
        for k in nets:
            if k not in known:
                raise KeyError("%s has no pin %s (has %s)" % (ref, k, sorted(known)))
        by_pos = {}
        for p in pins:
            if p["type"] == "no_connect" and p["number"] not in nets:
                continue
            by_pos.setdefault((p["x"], p["y"]), []).append(p)
        for (px, py), group in by_pos.items():
            netset = {nets.get(p["number"], "__missing__") for p in group}
            if "__missing__" in netset:
                missing = [p["number"] for p in group if p["number"] not in nets]
                raise KeyError("%s: pins %s have no net assignment" % (ref, missing))
            if len(netset) != 1:
                raise ValueError("%s: stacked pins %s map to different nets %s" % (ref, [p["number"] for p in group], netset))
            net = netset.pop()
            sx, sy = lib_to_screen(px, py, r)
            ax, ay = snap(x + sx), snap(y + sy)
            a = math.radians(group[0]["angle"])
            ox, oy = lib_to_screen(-round(math.cos(a)), -round(math.sin(a)), r)
            out = (int(ox), int(oy))
            for p in group:
                self.expected[(ref, p["number"])] = net
            if net is None:
                self.no_connect(ax, ay)
                continue
            ex, ey = snap(ax + out[0] * stub), snap(ay + out[1] * stub)
            self.wire(ax, ay, ex, ey)
            if net in POWER_SYMBOLS:
                self.power(net, ex, ey, out)
            else:
                self.label(net, ex, ey, out)
        return pins

    def power(self, net, x, y, out):
        lib_id = "power:" + net
        sym = self._use_symbol(lib_id)
        # body direction of the power symbol at rotation 0 (screen coords)
        body = (0, 1) if net == "GND" else (0, -1)
        for r in (0, 90, 180, 270):
            if rot(body[0], body[1], r) == out:
                break
        self.pwr_count += 1
        ref = "#PWR%03d" % self.pwr_count
        tx, ty = rot(0, 3.81 if net == "GND" else -3.81, r)
        self._instance(lib_id, ref, net, x, y, r, {}, in_bom=False, on_board=True,
                       ref_at=(x, y, None), val_at=(snap(x + tx), snap(y + ty), None), hide_ref=True)

    def pwr_flag(self, net, x, y):
        """PWR_FLAG on a net (tells ERC the net is driven)."""
        lib_id = "power:PWR_FLAG"
        self._use_symbol(lib_id)
        self.pwr_count += 1
        ref = "#FLG%03d" % self.pwr_count
        self._instance(lib_id, ref, "PWR_FLAG", x, y, 0, {}, in_bom=False, on_board=True,
                       ref_at=(x, y - 5.08, None), val_at=(x, y - 3.81, None), hide_ref=True)
        self.wire(x, y, x, y + 2.54)
        if net in POWER_SYMBOLS:
            self.power(net, x, y + 2.54, (0, 1))
        else:
            self.label(net, x, y + 2.54, (0, 1))

    def write(self, path):
        doc = [Sym("kicad_sch"), [Sym("version"), 20250114], [Sym("generator"), "eeschema"],
               [Sym("generator_version"), "9.0"], [Sym("uuid"), self.root_uuid], [Sym("paper"), self.paper],
               self.title, [Sym("lib_symbols")] + list(self.lib_symbols.values())]
        doc += self.items
        doc.append([Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]])
        doc.append([Sym("embedded_fonts"), Sym("no")])
        with open(path, "w") as f:
            f.write(sexp.dump(doc) + "\n")
