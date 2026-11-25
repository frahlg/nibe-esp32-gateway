"""Helpers that build a KiCad 9 board with the pcbnew Python API."""
import math

import pcbnew

from router import Router, Shape

FP_ROOT = "/usr/share/kicad/footprints"
MM = pcbnew.FromMM


def V(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))


def to_mm(v):
    return pcbnew.ToMM(v)


class Pcb:
    def __init__(self, path, width, height, corner_r=2.0):
        self.path = path
        self.board = pcbnew.NewBoard(path)
        self.W, self.H, self.cr = width, height, corner_r
        self.nets = {}
        self.fps = {}
        ds = self.board.GetDesignSettings()
        ds.SetCopperLayerCount(2)
        ds.m_MinClearance = MM(0.15)
        ds.m_TrackMinWidth = MM(0.15)
        ds.m_ViasMinSize = MM(0.5)
        ds.m_MinThroughDrill = MM(0.3)
        ds.m_HoleClearance = MM(0.25)
        ds.m_HoleToHoleMin = MM(0.25)
        ds.m_CopperEdgeClearance = MM(0.3)
        nc = ds.m_NetSettings.GetDefaultNetclass()
        nc.SetClearance(MM(0.2))
        nc.SetTrackWidth(MM(0.25))
        nc.SetViaDiameter(MM(0.6))
        nc.SetViaDrill(MM(0.3))

    # ------------------------------------------------------------ nets
    def net(self, name):
        if name not in self.nets:
            ni = pcbnew.NETINFO_ITEM(self.board, name)
            self.board.Add(ni)
            self.nets[name] = ni
        return self.nets[name]

    # ------------------------------------------------------------ outline
    def outline(self):
        W, H, r = self.W, self.H, self.cr
        lay = pcbnew.Edge_Cuts

        def seg(x1, y1, x2, y2):
            s = pcbnew.PCB_SHAPE(self.board, pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(V(x1, y1)); s.SetEnd(V(x2, y2)); s.SetLayer(lay); s.SetWidth(MM(0.1))
            self.board.Add(s)

        def arc(cx, cy, a0):
            s = pcbnew.PCB_SHAPE(self.board, pcbnew.SHAPE_T_ARC)
            a1, am = math.radians(a0), math.radians(a0 + 45)
            a2 = math.radians(a0 + 90)
            s.SetArcGeometry(V(cx + r * math.cos(a1), cy + r * math.sin(a1)),
                             V(cx + r * math.cos(am), cy + r * math.sin(am)),
                             V(cx + r * math.cos(a2), cy + r * math.sin(a2)))
            s.SetLayer(lay); s.SetWidth(MM(0.1))
            self.board.Add(s)

        seg(r, 0, W - r, 0); seg(W, r, W, H - r); seg(W - r, H, r, H); seg(0, H - r, 0, r)
        arc(W - r, r, 270); arc(W - r, H - r, 0); arc(r, H - r, 90); arc(r, r, 180)

    def inside(self, X, Y, margin):
        W, H, r = self.W, self.H, self.cr
        ok = (X >= margin) & (X <= W - margin) & (Y >= margin) & (Y <= H - margin)
        for cx, cy in ((r, r), (W - r, r), (r, H - r), (W - r, H - r)):
            corner = ((X < r) if cx == r else (X > W - r)) & ((Y < r) if cy == r else (Y > H - r))
            ok &= ~corner | (((X - cx) ** 2 + (Y - cy) ** 2) <= (r - margin) ** 2)
        return ok

    # ------------------------------------------------------------ footprints
    def place(self, ref, fpid, value, x, y, rot=0, bottom=False, path=None, fields=None, dnp=False,
              exclude_pos=False, exclude_bom=False, ref_size=0.8, hide_ref=False, ref_offset=None):
        lib, name = fpid.split(":")
        fp = pcbnew.FootprintLoad("%s/%s.pretty" % (FP_ROOT, lib), name)
        if fp is None:
            raise RuntimeError("footprint not found: " + fpid)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetReference(ref)
        fp.SetValue(value)
        fp.SetPosition(V(x, y))
        fp.SetOrientationDegrees(rot)
        if bottom:
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
        if path:
            fp.SetPath(pcbnew.KIID_PATH("/" + path))
            fp.SetSheetname("/")
            fp.SetSheetfile(self.sheetfile)
        for k, v in (fields or {}).items():
            fp.SetField(k, v)
            f = fp.GetFieldByName(k)
            if f:
                f.SetVisible(False)
        attrs = fp.GetAttributes()
        if dnp:
            attrs |= pcbnew.FP_DNP
        if exclude_pos:
            attrs |= pcbnew.FP_EXCLUDE_FROM_POS_FILES
        if exclude_bom:
            attrs |= pcbnew.FP_EXCLUDE_FROM_BOM
        fp.SetAttributes(attrs)
        rf = fp.Reference()
        rf.SetTextSize(V(ref_size, ref_size))
        rf.SetTextThickness(MM(ref_size * 0.15))
        if ref_offset is not None:
            rf.SetPosition(V(x + ref_offset[0], y + ref_offset[1]))
            rf.SetTextAngleDegrees(0)
        rf.SetVisible(not hide_ref)
        fp.Value().SetVisible(False)
        self.board.Add(fp)
        self.fps[ref] = fp
        return fp

    def pad_xy(self, ref, num):
        for p in self.fps[ref].Pads():
            if p.GetNumber() == str(num):
                return to_mm(p.GetPosition().x), to_mm(p.GetPosition().y)
        raise KeyError((ref, num))

    def assign_nets(self, pin_nets):
        """pin_nets: {(ref, pin): netname}."""
        for (ref, pin), name in pin_nets.items():
            if ref not in self.fps:
                continue
            for p in self.fps[ref].Pads():
                if p.GetNumber() == pin:
                    p.SetNet(self.net(name))

    # ------------------------------------------------------------ routing glue
    def make_router(self, clearance, edge_clearance, via_d, res=0.1):
        rt = Router(0, 0, self.W, self.H, res=res, clearance=clearance, edge_clearance=edge_clearance, via_d=via_d)
        rt.set_outline(lambda X, Y: self.inside(X, Y, edge_clearance))
        self.pad_shapes = {}
        for fp in self.board.GetFootprints():
            for p in fp.Pads():
                net = p.GetNetname() or ("__pad_%s_%s" % (fp.GetReference(), p.GetNumber()))
                pos = p.GetPosition()
                cx, cy = to_mm(pos.x), to_mm(pos.y)
                layers = tuple(l for l, kl in ((0, pcbnew.F_Cu), (1, pcbnew.B_Cu)) if p.IsOnLayer(kl))
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    d = to_mm(p.GetDrillSize().x)
                    rt.add(Shape("circle", "__npth", (0, 1), cx=cx, cy=cy, r=d / 2 + 0.05))
                    continue
                if not layers:
                    continue
                bb = p.GetBoundingBox()
                hw = to_mm(bb.GetWidth()) / 2
                hh = to_mm(bb.GetHeight()) / 2
                if p.GetShape() == pcbnew.PAD_SHAPE_CIRCLE:
                    shp = Shape("circle", net, layers, cx=cx, cy=cy, r=hw)
                else:
                    shp = Shape("rect", net, layers, cx=cx, cy=cy, hw=hw, hh=hh)
                rt.add(shp)
                self.pad_shapes[(fp.GetReference(), p.GetNumber(), round(cx, 3), round(cy, 3))] = [shp]
                if p.GetDrillSize().x > 0 and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                    pass
        self.router = rt
        return rt

    def emit_routes(self, via_d=0.6, via_drill=0.3):
        rt = self.router
        for (net, l, x1, y1, x2, y2, w) in rt.tracks:
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(V(x1, y1)); t.SetEnd(V(x2, y2)); t.SetWidth(MM(w))
            t.SetLayer(pcbnew.F_Cu if l == 0 else pcbnew.B_Cu)
            t.SetNet(self.net(net))
            self.board.Add(t)
        for (net, x, y) in rt.vias:
            self.via(net, x, y, via_d, via_drill)

    def via(self, net, x, y, d=0.6, drill=0.3):
        v = pcbnew.PCB_VIA(self.board)
        v.SetPosition(V(x, y))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetWidth(MM(d))
        v.SetDrill(MM(drill))
        v.SetNet(self.net(net))
        self.board.Add(v)
        return v

    def track(self, net, pts, width, layer=0):
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(V(x1, y1)); t.SetEnd(V(x2, y2)); t.SetWidth(MM(width))
            t.SetLayer(pcbnew.F_Cu if layer == 0 else pcbnew.B_Cu)
            t.SetNet(self.net(net))
            self.board.Add(t)
            if hasattr(self, "router"):
                self.router.tracks.append((net, layer, x1, y1, x2, y2, width))
                self.router.add(Shape("seg", net, (layer,), x1=x1, y1=y1, x2=x2, y2=y2, r=width / 2))

    # ------------------------------------------------------------ zones
    def zone(self, net, layer, pts, clearance=0.25, min_w=0.2, priority=0, thermal_gap=0.3, spoke=0.4,
             solid=False):
        z = pcbnew.ZONE(self.board)
        z.SetLayer(layer)
        z.SetNet(self.net(net))
        ol = z.Outline()
        ol.NewOutline()
        for x, y in pts:
            ol.Append(MM(x), MM(y))
        z.SetLocalClearance(MM(clearance))
        z.SetMinThickness(MM(min_w))
        z.SetThermalReliefGap(MM(thermal_gap))
        z.SetThermalReliefSpokeWidth(MM(spoke))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if solid else pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetAssignedPriority(priority)
        self.board.Add(z)
        return z

    def keepout(self, pts, layers=(pcbnew.F_Cu, pcbnew.B_Cu), name="keepout"):
        z = pcbnew.ZONE(self.board)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowCopperPour(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        ls = pcbnew.LSET()
        for l in layers:
            ls.AddLayer(l)
        z.SetLayerSet(ls)
        z.SetZoneName(name)
        ol = z.Outline()
        ol.NewOutline()
        for x, y in pts:
            ol.Append(MM(x), MM(y))
        self.board.Add(z)
        return z

    def fill(self):
        filler = pcbnew.ZONE_FILLER(self.board)
        filler.Fill(self.board.Zones())

    # ------------------------------------------------------------ graphics
    def text(self, s, x, y, size=1.0, layer=pcbnew.F_SilkS, bold=False, rot=0, justify=None):
        t = pcbnew.PCB_TEXT(self.board)
        t.SetText(s)
        t.SetPosition(V(x, y))
        t.SetLayer(layer)
        t.SetTextSize(V(size, size))
        t.SetTextThickness(MM(size * (0.2 if bold else 0.15)))
        t.SetTextAngleDegrees(rot)
        if layer == pcbnew.B_SilkS:
            t.SetMirrored(True)
        if justify == "left":
            t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
        elif justify == "right":
            t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
        self.board.Add(t)
        return t

    def line(self, x1, y1, x2, y2, layer=pcbnew.F_SilkS, w=0.15):
        s = pcbnew.PCB_SHAPE(self.board, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(V(x1, y1)); s.SetEnd(V(x2, y2)); s.SetLayer(layer); s.SetWidth(MM(w))
        self.board.Add(s)

    def rect(self, x1, y1, x2, y2, layer=pcbnew.F_SilkS, w=0.15, filled=False):
        s = pcbnew.PCB_SHAPE(self.board, pcbnew.SHAPE_T_RECT)
        s.SetStart(V(x1, y1)); s.SetEnd(V(x2, y2)); s.SetLayer(layer); s.SetWidth(MM(w))
        s.SetFilled(filled)
        self.board.Add(s)

    def save(self):
        pcbnew.SaveBoard(self.path, self.board)
