"""Place, route and check the board."""
import json
import os
import subprocess
import time

import pcbnew

import circuit as C
from router import Shape
import schgen
from build import KDIR, NAME, PCB, PRO, write_project, run
from pcbgen import Pcb, MM

W, H = C.BOARD_W, C.BOARD_H
CLR = 0.2          # copper clearance used by the router (DRC rule is 0.15)
EDGE_CLR = 0.4

# routing order and track width per net (mm); GND is handled by pours and vias
ROUTES = [
    ("USB_DP", 0.25), ("USB_DN", 0.25),
    ("RS485_TX", 0.25), ("RS485_DE", 0.25), ("RS485_RX", 0.25),
    ("BST", 0.25), ("SS", 0.25), ("FB", 0.25),   # SW and VBUCK are copper zones (C.BUCK_ZONES)
    ("12V_IN", 0.6), ("VIN", 0.6), ("VSYS", 0.6), ("VBUS", 0.5),
    ("+3V3", 0.5),
    ("BUS_A", 0.3), ("BUS_B", 0.3), ("TERM", 0.25),
    ("CC1", 0.25), ("CC2", 0.25), ("EN", 0.25), ("BOOT", 0.25),
    ("LED_STAT", 0.25), ("LED_BUS", 0.25), ("LED_PWR", 0.25), ("LED_STAT_A", 0.25), ("LED_BUS_A", 0.25),
    ("EXP_IO1", 0.25), ("EXP_IO2", 0.25), ("TXD0", 0.25), ("RXD0", 0.25),
]

# nets next to 0.5 mm pitch pins (USB-C, TPS62933) are routed on a 0.05 mm grid
FINE_NETS = {"USB_DP", "USB_DN", "CC1", "CC2", "BST", "SS", "FB", "SW", "VBUCK", "VBUS"}

# Ground vias placed before any routing, where the signal tracks would otherwise
# box a ground pad in (U1 pin 2 sits between the two USB lines).
PRE_VIAS = {("U1", "2"): (16.1, 23.4)}

# preferred first pad of each net (routing starts there and grows a tree)
HUB = {"+3V3": ("L1", "2"), "VSYS": ("C2", "1"), "VBUS": ("U1", "5"), "VIN": ("C1", "1"),
       "RS485_DE": ("U3", "18"), "BUS_A": ("U2", "6"), "BUS_B": ("U2", "7")}


def board_net(name):
    """Netlist net name as KiCad names it on the board."""
    return name


def load_pin_nets():
    raw = json.load(open(os.path.join(KDIR, ".pin_nets.json")))
    return {tuple(k.split("|")): v for k, v in raw.items()}


def place_all(pcb):
    for ref, p in C.PARTS.items():
        sym, fp, value, lcsc, mpn = p["part"]
        x, y, r = p["pcb"]
        fields = {}
        if lcsc:
            fields["LCSC"] = lcsc
        if mpn:
            fields["MPN"] = mpn
        is_hole = ref.startswith("H")
        pcb.place(ref, fp, value, x, y, rot=r, path=schgen.uid(C.PROJECT, "sym", ref), fields=fields,
                  dnp=p.get("dnp", False), exclude_pos=is_hole or p.get("dnp", False),
                  exclude_bom=is_hole or p.get("nobom", False), ref_size=0.8, hide_ref=is_hole)
    # The fitted terminal (Dorabo DB2ERC, 0.8 mm square pins, 1.13 mm across the
    # corners) wants a 1.4 mm hole; the Phoenix footprint has 1.2 mm.
    j2 = pcb.fps["J2"]
    for p in j2.Pads():
        p.SetDrillSize(pcbnew.VECTOR2I(MM(1.4), MM(1.4)))
        p.SetSize(pcbnew.VECTOR2I(MM(2.0), MM(3.6)))
    # footprint silkscreen that now touches the wider pads goes to the fab layer
    for g in j2.GraphicalItems():
        if g.GetLayer() != pcbnew.F_SilkS:
            continue
        gb = g.GetBoundingBox()
        gb.Inflate(MM(0.2))
        if any(gb.Intersects(p.GetBoundingBox()) for p in j2.Pads()):
            g.SetLayer(pcbnew.F_Fab)


def solid_gnd(pcb):
    """Buck-loop ground pads join the pour with full copper, not thermal spokes."""
    for ref, num in C.SOLID_GND:
        for p in pcb.fps[ref].Pads():
            if p.GetNumber() == num:
                p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)


def buck_zones(pcb, routers):
    """Top-layer copper areas for SW and VBUCK; the routers treat them as copper of that net."""
    from router import Shape
    for name, pts in C.BUCK_ZONES.items():
        net = next(n for n in pcb.nets if n.lstrip("/") == name)
        pcb.zone(net, pcbnew.F_Cu, pts, clearance=0.25, min_w=0.2, priority=1, solid=True)
        # cover the polygon with rectangles for the routers (horizontal bands between its y values)
        ys = sorted(set(y for _, y in pts))
        for y0, y1 in zip(ys, ys[1:]):
            ym = (y0 + y1) / 2
            xs = []
            for (xa, ya), (xb, yb) in zip(pts, pts[1:] + pts[:1]):
                if xa == xb and min(ya, yb) <= ym <= max(ya, yb):
                    xs.append(xa)
            xs.sort()
            for xl, xr in zip(xs[0::2], xs[1::2]):
                shp = Shape("rect", net, (0,), cx=(xl + xr) / 2, cy=ym, hw=(xr - xl) / 2, hh=(y1 - y0) / 2)
                for rt in routers:
                    if shp not in rt.shapes:
                        rt.add(shp)


def pads_of(pcb, net):
    out = []
    for ref, fp in pcb.fps.items():
        for p in fp.Pads():
            if p.GetNetname() == net:
                pos = p.GetPosition()
                layers = tuple(l for l, kl in ((0, pcbnew.F_Cu), (1, pcbnew.B_Cu)) if p.IsOnLayer(kl))
                out.append((ref, p.GetNumber(), pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y), layers))
    return out


def route_net(pcb, rt, net, width, log):
    pads = pads_of(pcb, net)
    # merge pads at the same spot (stacked pads)
    uniq = []
    for p in pads:
        if not any(abs(p[2] - q[2]) < 1e-3 and abs(p[3] - q[3]) < 1e-3 for q in uniq):
            uniq.append(p)
    if len(uniq) < 2:
        return True
    hub = HUB.get(net.lstrip("/"))
    start = next((p for p in uniq if hub and (p[0], p[1]) == hub), uniq[0])
    connected = [start]
    tree = list(pcb.pad_shapes[(start[0], start[1], round(start[2], 3), round(start[3], 3))])
    todo = [p for p in uniq if p is not start]
    ok = True
    while todo:
        # nearest unconnected pad to the tree
        todo.sort(key=lambda p: min((p[2] - q[2]) ** 2 + (p[3] - q[3]) ** 2 for q in connected))
        p = todo.pop(0)
        goals = [(q[2], q[3], q[4]) for q in connected]
        t0 = time.time()
        path = rt.route(net, (p[2], p[3], p[4]), goals, width, goal_shapes=tree)
        if path is None:
            log.append("FAILED %s: %s.%s" % (net, p[0], p[1]))
            ok = False
            continue
        end_xy = None
        for q in connected:
            ix, iy = rt.idx(q[2], q[3])
            if (path[-1][1], path[-1][2]) == (ix, iy):
                end_xy = (q[2], q[3])
        n0 = len(rt.shapes)
        rt.commit(net, path, width, start_xy=(p[2], p[3]), end_xy=end_xy)
        tree += rt.shapes[n0:] + pcb.pad_shapes[(p[0], p[1], round(p[2], 3), round(p[3], 3))]
        connected.append(p)
        log.append("routed %s %s.%s (%d cells, %.1fs)" % (net, p[0], p[1], len(path), time.time() - t0))
    return ok


# Module ground-pad vias that stay (footprint coordinates). The footprint has 12;
# each open hole drains paste from the pad, so keep the four around the centre.
EPAD_KEEP = {(-2.2, 2.46), (-1.5, 1.76), (-1.5, 3.16), (-0.8, 2.46)}


def epad_vias(pcb):
    """Keep four of the module's thermal vias, opened up to 0.3 mm (the JLCPCB 2-layer
    minimum) and covered by solder mask on the bottom; turn the rest into plain top copper."""
    fp = pcb.fps["U3"]
    top = pcbnew.LSET()
    top.AddLayer(pcbnew.F_Cu)
    both = pcbnew.LSET()
    both.AddLayer(pcbnew.F_Cu)
    both.AddLayer(pcbnew.B_Cu)
    for p in fp.Pads():
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and p.GetDrillSize().x < MM(0.25):
            rel = p.GetFPRelativePosition()
            key = (round(pcbnew.ToMM(rel.x), 2), round(pcbnew.ToMM(rel.y), 2))
            if key in EPAD_KEEP:
                p.SetDrillSize(pcbnew.VECTOR2I(MM(0.3), MM(0.3)))
                p.SetSize(pcbnew.VECTOR2I(MM(0.6), MM(0.6)))
                p.SetLayerSet(both)
            else:
                p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
                p.SetDrillSize(pcbnew.VECTOR2I(0, 0))
                p.SetLayerSet(top)
    return []


def gnd_vias(pcb, rt, log):
    """Give every SMD ground pad its own via to the bottom ground plane."""
    for ref, num, x, y, layers in pads_of(pcb, "GND"):
        if layers != (0,):
            continue
        if ref == "U3" and num == "41":
            continue  # module pad has its own via array
        if (ref, num) in PRE_VIAS:
            continue
        path = rt.route("GND", (x, y, (0,)), [], 0.3, goal_any_via=True, max_expand=400000, own_targets=False)
        if path is None:
            log.append("no GND via for %s.%s" % (ref, num))
            continue
        # cut the path after the first cell on the bottom layer
        cut = next((i for i, c in enumerate(path) if c[0] == 1), None)
        if cut is None:
            log.append("no GND via for %s.%s" % (ref, num))
            continue
        rt.commit("GND", path[:cut + 1], 0.3, start_xy=(x, y))


def stitch(pcb, rt, pitch=4.0):
    """Ground stitching vias on a grid wherever there is room."""
    import numpy as np
    vb = [rt.blocked("__stitch__", l, rt.via_r + 0.15) for l in range(2)]
    ok = ~vb[0] & ~vb[1]
    n = 0
    y = 2.0
    while y < H - 1:
        x = 2.0
        while x < W - 1:
            ix, iy = rt.idx(x, y)
            if ok[iy, ix]:
                rt.vias.append(("GND", x, y))
                from router import Shape
                rt.add(Shape("circle", "GND", (0, 1), cx=x, cy=y, r=rt.via_r))
                n += 1
            x += pitch
        y += pitch
    return n


def silkscreen(pcb):
    F, B = pcbnew.F_SilkS, pcbnew.B_SilkS
    j2 = C.PARTS["J2"]["pcb"]
    for i, lab in enumerate(["12V", "A", "B", "GND"]):
        pcb.text(lab, j2[0] + 3.5 * i, j2[1] - 3.6, size=1.0, bold=True)
    for ref in ("D5", "D6", "D7"):
        x, y, _ = C.PARTS[ref]["pcb"]
        pcb.text(C.PARTS[ref]["label"], x, y + 2.6, size=0.8)
    for ref, dy in (("SW1", -3.6), ("SW2", 3.6)):
        x, y, _ = C.PARTS[ref]["pcb"]
        pcb.text(C.PARTS[ref]["label"], x, y + dy, size=0.8)
        pcb.fps[ref].Reference().SetVisible(False)
    x, y, _ = C.PARTS["JP1"]["pcb"]
    pcb.text("TERM", x + 1.6, y, size=0.8, rot=90)
    x, y, _ = C.PARTS["J3"]["pcb"]
    for i, lab in enumerate(["G", "1", "2", "TX", "RX", "3V3"]):
        pcb.text(lab, x - 2.3, y + 2.54 * i, size=0.8, justify="right")
    pcb.text("USB", 2.2, 16.6, size=0.8)
    pcb.text("NIBE ESP32 GW v%s" % C.REV, 40.6, 51.0, size=0.9, bold=True)
    # bottom side
    pcb.text("NIBE ESP32 Gateway rev %s" % C.REV, W / 2, 20, size=1.2, layer=B, bold=True)
    pcb.text("ESP32-S3 + RS-485 for the NIBE MODBUS 40 port", W / 2, 22.5, size=0.8, layer=B)
    pcb.text("Wire to AA3-X4: 12=12V 11=A 10=B 9=GND", W / 2, 25.0, size=0.8, layer=B)
    pcb.text("AA3-X4", j2[0] + 5.25, j2[1] - 5.0, size=0.8, layer=B, bold=True)
    for i, lab in enumerate(["12", "11", "10", "9"]):
        pcb.text(lab, j2[0] + 3.5 * i, j2[1] - 3.4, size=1.0, layer=B, bold=True)
    pcb.text("Open hardware CERN-OHL-P-2.0  %s" % C.DATE, W / 2, 27.5, size=0.8, layer=B)
    pcb.text("github.com/frahlg/nibe-esp32-gateway", W / 2, 30.0, size=0.8, layer=B)


def place_refs(pcb):
    """Move each reference designator next to its part where it hits nothing; hide it otherwise."""
    board = pcb.board
    obstacles = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            obstacles.append(("pad", fp.GetReference(), bb))
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        if cy.OutlineCount() and fp.GetReference() not in ("U3",):
            obstacles.append(("crt", fp.GetReference(), cy.BBox()))
    for d in board.GetDrawings():
        if isinstance(d, pcbnew.PCB_TEXT) and d.GetLayer() == pcbnew.F_SilkS:
            obstacles.append(("txt", "", d.GetBoundingBox()))
    m = MM(0.15)

    def hits(bb, ref):
        if bb.GetLeft() < MM(0.6) or bb.GetTop() < MM(0.6) or bb.GetRight() > MM(W - 0.6) or bb.GetBottom() > MM(H - 0.6):
            return True
        for kind, owner, ob in obstacles:
            if kind == "crt" and owner == ref:
                continue
            if (bb.GetLeft() - m < ob.GetRight() and bb.GetRight() + m > ob.GetLeft() and
                    bb.GetTop() - m < ob.GetBottom() and bb.GetBottom() + m > ob.GetTop()):
                return True
        return False

    hidden = []
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        rf = fp.Reference()
        if ref.startswith("H") or ref == "U3" or not rf.IsVisible():
            continue
        cy = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        cx, cyy = cy.GetCenter().x, cy.GetCenter().y
        rf.SetTextAngleDegrees(0)
        cands = []
        for ang in (0, 90):
            rf.SetTextAngleDegrees(ang)
            tb = rf.GetBoundingBox()
            tw, th = tb.GetWidth(), tb.GetHeight()
            cands += [
                (ang, cx, cy.GetTop() - th // 2 - MM(0.2)),
                (ang, cx, cy.GetBottom() + th // 2 + MM(0.2)),
                (ang, cy.GetRight() + tw // 2 + MM(0.2), cyy),
                (ang, cy.GetLeft() - tw // 2 - MM(0.2), cyy),
            ]
        placed = False
        for ang, x, y in cands:
            rf.SetTextAngleDegrees(ang)
            rf.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
            bb = rf.GetBoundingBox()
            if not hits(bb, ref):
                obstacles.append(("txt", "", bb))
                placed = True
                break
        if not placed:
            rf.SetVisible(False)
            hidden.append(ref)
    return hidden


def via_in_pad(board, gap=0.15):
    """Vias (board vias and footprint via pads) whose copper comes within gap of an SMD pad."""
    import math
    holes = []
    for v in board.GetTracks():
        if v.Type() == pcbnew.PCB_VIA_T:
            p = v.GetPosition()
            holes.append(("via %s" % v.GetNetname(), pcbnew.ToMM(p.x), pcbnew.ToMM(p.y), 0.3))
    smd = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            pos = p.GetPosition()
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and p.GetDrillSize().x < MM(0.5):
                holes.append(("%s.%s" % (fp.GetReference(), p.GetNumber()), pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y),
                              pcbnew.ToMM(p.GetSize().x) / 2))
            elif p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                bb = p.GetBoundingBox()
                smd.append(("%s.%s" % (fp.GetReference(), p.GetNumber()), pcbnew.ToMM(bb.GetLeft()),
                            pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))
    bad = []
    for name, x, y, r in holes:
        for pname, x0, y0, x1, y1 in smd:
            if name.split(".")[0] == pname.split(".")[0] == "U3":
                continue  # the module's own ground-pad vias (see epad_vias)
            dx = max(x0 - x, 0, x - x1)
            dy = max(y0 - y, 0, y - y1)
            if math.hypot(dx, dy) < r + gap - 1e-6:
                bad.append("%s at (%.2f, %.2f) -> %s" % (name, x, y, pname))
    return bad


def drc(refill=True):
    out = os.path.join(KDIR, "drc.json")
    run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all", "--schematic-parity",
         "-o", out, PCB], check=False)
    data = json.load(open(out))
    os.remove(out)
    res = []
    for key in ("violations", "unconnected_items", "schematic_parity"):
        for v in data.get(key, []):
            items = "; ".join(i.get("description", "") for i in v.get("items", []))
            res.append((key, v.get("severity"), v.get("type"), v.get("description"), items))
    return res


def main():
    pin_nets = load_pin_nets()
    pcb = Pcb(PCB, W, H, corner_r=2.5)
    pcb.sheetfile = NAME + ".kicad_sch"
    place_all(pcb)
    pcb.assign_nets(pin_nets)
    solid_gnd(pcb)
    pcb.outline()

    # antenna keep-out: no copper on any layer along the top edge
    ko = [(0, 0), (W, 0), (W, 6.4), (0, 6.4)]
    pcb.keepout(ko, name="antenna")

    if os.environ.get("NOROUTE"):
        pcb.save()
        write_project()
        for key, sev, typ, desc, items in drc():
            if typ in ("courtyards_overlap", "pth_inside_courtyard", "npth_inside_courtyard", "copper_edge_clearance"):
                print("  DRC", typ, items[:150])
        return
    evias = epad_vias(pcb)
    rt = pcb.make_router(CLR, EDGE_CLR, 0.6)
    rt.add_keepout(None, 0, 0, W, 6.4 + 0.3)
    fine = pcb.make_router(CLR, EDGE_CLR, 0.6, res=0.05)
    fine.add_keepout(None, 0, 0, W, 6.4 + 0.3)
    fine.shapes, fine.tracks, fine.vias = rt.shapes, rt.tracks, rt.vias  # share copper
    buck_zones(pcb, [rt])
    for (ref, num), (vx, vy) in PRE_VIAS.items():
        px, py = pcb.pad_xy(ref, num)
        rt.tracks.append(("GND", 0, px, py, vx, vy, 0.3))
        rt.add(Shape("seg", "GND", (0,), x1=px, y1=py, x2=vx, y2=vy, r=0.15))
        rt.vias.append(("GND", vx, vy))
        rt.add(Shape("circle", "GND", (0, 1), cx=vx, cy=vy, r=rt.via_r))
    for (x, y) in evias:
        rt.vias.append(("GND", x, y))
        rt.add(Shape("circle", "GND", (0, 1), cx=x, cy=y, r=rt.via_r))
    log = []
    t0 = time.time()
    failed = []
    for net, w in ROUTES:
        bn = next((n for n in pcb.nets if n.lstrip("/") == net), None)
        if bn is None:
            log.append("net %s not on board" % net)
            continue
        if not route_net(pcb, fine if net in FINE_NETS else rt, bn, w, log):
            failed.append(net)
    gnd_vias(pcb, fine, log)
    nst = stitch(pcb, rt)
    pcb.emit_routes()
    for line in log:
        if not line.startswith("routed"):
            print(" ", line)
    print("routing done in %.0fs, %d tracks, %d vias (%d stitching), failed: %s"
          % (time.time() - t0, len(rt.tracks), len(rt.vias), nst, failed or "none"))

    # ground pours on both layers
    outline = [(0, 0), (W, 0), (W, H), (0, H)]
    pcb.zone("GND", pcbnew.F_Cu, outline, clearance=0.25, min_w=0.2)
    pcb.zone("GND", pcbnew.B_Cu, outline, clearance=0.25, min_w=0.2)
    silkscreen(pcb)
    hidden = place_refs(pcb)
    print("references without room on the silkscreen (shown on the assembly drawing):", ", ".join(hidden) or "none")
    pcb.save()
    write_project()
    # reload so the fill runs with the project's design rules (hole clearance etc.)
    board = pcbnew.LoadBoard(PCB)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(PCB, board)
    write_project()
    bad = via_in_pad(board)
    for line in bad:
        print("  VIA IN PAD", line)
    print("via-in-pad check: %d vias within 0.15 mm of an SMD pad" % len(bad))
    issues = drc()
    counts = {}
    for key, sev, typ, desc, items in issues:
        counts[(key, sev)] = counts.get((key, sev), 0) + 1
        print("  DRC %s/%s %s: %s | %s" % (key, sev, typ, desc, items[:150]))
    print("DRC summary:", counts or "clean")
