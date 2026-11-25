# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = ["cadquery==2.5.2"]
# ///
"""3D-printable enclosure for the NIBE ESP32 Gateway board.

Two parts, no supports needed:
  base.stl  - floor, walls, four PCB standoffs, keyhole slots for wall mounting,
              a tongue with zip-tie slots that holds the heat pump cable
  lid.stl   - flat lid with four posts that clamp the board, light holes for the
              three LEDs and pin holes for the RESET and BOOT buttons

Four M3x16 screws go through the lid, the board and into the base.

Coordinates follow the board STEP export: x to the right, y up (board y is
negated), z up from the bottom of the base. Run with:  uv run enclosure.py
"""
import os
import sys

import cadquery as cq

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "hardware", "generator"))
import circuit as C  # noqa: E402  (board size, part positions)

# ----------------------------------------------------------------------------- dimensions
BW, BH, BR = C.BOARD_W, C.BOARD_H, 2.5      # board width, height, corner radius
PCB_T = 1.6
WALL, FLOOR, LID_T = 2.0, 2.0, 2.0
GAP = 0.4                                   # board to wall clearance
STANDOFF = 3.5                              # floor to board bottom (THT pins stick out 1.8 mm)
J2_H = 7.6                                  # terminal height above the board (from the STEP model)
HEAD_ROOM = 1.3                             # clearance above the terminal
Z_PCB = FLOOR + STANDOFF                    # board bottom
Z_TOP = Z_PCB + PCB_T                       # board top
Z_LID = round(Z_TOP + J2_H + HEAD_ROOM, 1)  # lid underside = top of the walls
SCREW_PILOT = 2.5                           # M3 self-tapping into PLA/PETG
SCREW_CLEAR = 3.4
POST_D = 6.4


def by(y_board):
    """Board y (down) to model y (up)."""
    return -y_board


HOLES = [(C.PARTS["H%d" % i]["pcb"][0], by(C.PARTS["H%d" % i]["pcb"][1])) for i in range(1, 5)]
X0, X1 = -GAP, BW + GAP
Y0, Y1 = by(BH) - GAP, GAP
OX0, OX1, OY0, OY1 = X0 - WALL, X1 + WALL, Y0 - WALL, Y1 + WALL
CX, CY = (OX0 + OX1) / 2, (OY0 + OY1) / 2

# connector openings
J2X, J2Y, _ = C.PARTS["J2"]["pcb"]
J2_X0, J2_X1 = J2X - 2.45 - 0.6, J2X + 12.95 + 0.6     # header body plus clearance
J1X, J1Y, _ = C.PARTS["J1"]["pcb"]
USB_W, USB_H = 12.6, 6.8                                # room for a USB-C plug overmould
USB_Z = Z_TOP + 1.63


def rounded_box(x0, x1, y0, y1, z0, z1, r):
    return (cq.Workplane("XY").workplane(offset=z0).center((x0 + x1) / 2, (y0 + y1) / 2)
            .rect(x1 - x0, y1 - y0).extrude(z1 - z0).edges("|Z").fillet(r))


def base():
    body = rounded_box(OX0, OX1, OY0, OY1, 0, Z_LID, BR + WALL)
    cavity = rounded_box(X0, X1, Y0, Y1, FLOOR, Z_LID + 1, BR + GAP)
    b = body.cut(cavity)
    # outer bottom edge softened
    b = b.faces("<Z").edges().chamfer(0.6)
    # standoffs with pilot holes
    for (x, y) in HOLES:
        post = cq.Workplane("XY").workplane(offset=FLOOR - 0.01).center(x, y).circle(POST_D / 2).extrude(STANDOFF + 0.01)
        b = b.union(post)
        b = b.cut(cq.Workplane("XY").workplane(offset=0.5).center(x, y).circle(SCREW_PILOT / 2).extrude(Z_PCB))
    # NIBE terminal opening in the bottom wall (open towards the lid would weaken the wall, so keep a bridge)
    j2 = cq.Workplane("XY").box(J2_X1 - J2_X0, WALL + GAP + 2, (Z_TOP + J2_H + 0.4) - (Z_TOP - 0.3),
                                centered=(False, False, False)).translate((J2_X0, OY0 - 1, Z_TOP - 0.3))
    b = b.cut(j2)
    # USB-C opening in the left wall
    usb = (cq.Workplane("YZ").workplane(offset=OX0 - 1).center(by(J1Y), USB_Z)
           .rect(USB_W, USB_H).extrude(WALL + GAP + 2).edges("|X").fillet(1.6))
    b = b.cut(usb)
    # tongue with two zip-tie slots below the terminal opening
    tx0, tx1 = J2_X0 - 4, J2_X1 + 4
    tongue = (cq.Workplane("XY").center((tx0 + tx1) / 2, OY0 - 7).rect(tx1 - tx0, 14.4).extrude(FLOOR)
              .edges("|Z").fillet(2.0))
    b = b.union(tongue)
    for dx in (-9.0, 9.0):
        slot = cq.Workplane("XY").center((J2_X0 + J2_X1) / 2 + dx, OY0 - 8).rect(2.2, 4.8).extrude(FLOOR + 1)
        b = b.cut(slot.translate((0, 0, -0.5)))
    # keyhole slots for two wall screws (head under the board, away from pins and antenna)
    for ky in (by(16.0), by(38.0)):
        kx = BW / 2 - 6
        head = cq.Workplane("XY").center(kx, ky).circle(4.2).extrude(FLOOR + 1).translate((0, 0, -0.5))
        slot = cq.Workplane("XY").center(kx, ky + 4.5).rect(4.2, 9.0).extrude(FLOOR + 1).translate((0, 0, -0.5))
        slot = slot.union(cq.Workplane("XY").center(kx, ky + 9.0).circle(2.1).extrude(FLOOR + 1).translate((0, 0, -0.5)))
        b = b.cut(head).cut(slot)
    return b


def lid():
    plate = rounded_box(OX0, OX1, OY0, OY1, Z_LID, Z_LID + LID_T, BR + WALL)
    plate = plate.faces(">Z").edges().chamfer(0.6)
    # locating rim that drops inside the walls, cut where the terminal sits
    rim_out = rounded_box(X0 + 0.25, X1 - 0.25, Y0 + 0.25, Y1 - 0.25, Z_LID - 2.0, Z_LID + 0.01, BR + GAP - 0.25)
    rim_in = rounded_box(X0 + 1.45, X1 - 1.45, Y0 + 1.45, Y1 - 1.45, Z_LID - 2.1, Z_LID + 0.1, max(BR + GAP - 1.45, 0.5))
    rim = rim_out.cut(rim_in)
    rim = rim.cut(cq.Workplane("XY").box(J2_X1 - J2_X0 + 2, 6, 3, centered=(False, False, False))
                  .translate((J2_X0 - 1, Y0 - 1, Z_LID - 2.5)))
    l = plate.union(rim)
    # posts that clamp the board, with screw clearance and a counterbore for the head
    for (x, y) in HOLES:
        post = cq.Workplane("XY").workplane(offset=Z_TOP + 0.05).center(x, y).circle(POST_D / 2).extrude(Z_LID - Z_TOP)
        l = l.union(post)
        l = l.cut(cq.Workplane("XY").workplane(offset=Z_TOP - 1).center(x, y).circle(SCREW_CLEAR / 2).extrude(30))
        l = l.cut(cq.Workplane("XY").workplane(offset=Z_LID + LID_T - 1.2).center(x, y).circle(3.1).extrude(5))
    # light holes over the LEDs and pin holes over the buttons
    for ref in ("D5", "D6", "D7"):
        x, y, _ = C.PARTS[ref]["pcb"]
        l = l.cut(cq.Workplane("XY").workplane(offset=Z_LID - 3).center(x, by(y)).circle(1.2).extrude(10))
    for ref in ("SW1", "SW2"):
        x, y, _ = C.PARTS[ref]["pcb"]
        l = l.cut(cq.Workplane("XY").workplane(offset=Z_LID - 3).center(x, by(y)).circle(1.6).extrude(10))
    # labels engraved in the top
    top = Z_LID + LID_T

    def engrave(txt, x, y, size, kind="regular", angle=0):
        wp = cq.Workplane("XY").workplane(offset=top - 0.5)
        t = wp.text(txt, size, 1.0, kind=kind)
        if angle:
            t = t.rotate((0, 0, 0), (0, 0, 1), angle)
        return t.translate((x, y, 0))

    labels = [("NIBE ESP32 Gateway", 27.0, by(26), 3.0, "bold", 0),
              ("MODBUS 40 port", 25.0, by(31), 2.2, "regular", 0)]
    for ref, txt in (("D5", "PWR"), ("D6", "STAT"), ("D7", "BUS")):
        x, y, _ = C.PARTS[ref]["pcb"]
        labels.append((txt, x, by(y - 4.6), 1.8, "regular", 90))
    x, y, _ = C.PARTS["SW1"]["pcb"]
    labels.append(("RESET", x, by(y + 3.6), 2.0, "regular", 0))
    x, y, _ = C.PARTS["SW2"]["pcb"]
    labels.append(("BOOT", x, by(y + 3.6), 2.0, "regular", 0))
    for i, txt in enumerate(["12V", "A", "B", "GND"]):
        labels.append((txt, J2X + 3.5 * i, by(BH - 3.0), 1.6, "bold", 0))
    x, y, _ = C.PARTS["J1"]["pcb"]
    labels.append(("USB", 6.5, by(y), 2.2, "bold", 0))
    for txt, x, y, size, kind, ang in labels:
        l = l.cut(engrave(txt, x, y, size, kind, ang))
    return l


def board():
    step = os.path.join(HERE, "..", "hardware", "production", "nibe-esp32-gateway.step")
    if not os.path.exists(step):
        return None
    return cq.importers.importStep(step).translate((0, 0, Z_PCB))


def fit_check(b, l, pcb):
    if pcb is None:
        print("fit check skipped: run hardware/build.sh fab first")
        return True
    ok = True
    for name, part in (("base", b), ("lid", l)):
        vol = 0.0
        for s in pcb.solids().vals():
            bb = s.BoundingBox()
            if bb.zmax - bb.zmin < 0.01:
                continue
            try:
                inter = part.val().intersect(s)
                vol += inter.Volume()
            except Exception:
                pass
        # the screws holes pass through the board holes, so any overlap is a real clash
        print("fit check: board vs %s overlap = %.3f mm3" % (name, vol))
        ok &= vol < 0.05
    return ok


def _polydata(shape, tmpdir):
    import vtkmodules.all as vtk
    tmp = os.path.join(tmpdir, "render-%d.stl" % id(shape))
    cq.exporters.export(shape, tmp, tolerance=0.03, angularTolerance=0.15)
    r = vtk.vtkSTLReader()
    r.SetFileName(tmp)
    r.Update()
    os.remove(tmp)
    return r.GetOutput()


def render(parts, path, elev=30, azim=-35, size=(1600, 1200), zoom=1.0):
    """Offscreen VTK render. parts: list of (shape, '#rrggbb', opacity)."""
    import tempfile
    import vtkmodules.all as vtk
    ren = vtk.vtkRenderer()
    ren.SetBackground(1, 1, 1)
    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.SetSize(*size)
    win.SetMultiSamples(8)
    win.AddRenderer(ren)
    tmpdir = tempfile.mkdtemp()
    for shape, color, opacity in parts:
        pd = _polydata(shape, tmpdir)
        normals = vtk.vtkPolyDataNormals()
        normals.SetInputData(pd)
        normals.SetFeatureAngle(35)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(normals.GetOutputPort())
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        c = tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
        actor.GetProperty().SetColor(*c)
        actor.GetProperty().SetOpacity(opacity)
        actor.GetProperty().SetSpecular(0.15)
        ren.AddActor(actor)
    cam = ren.GetActiveCamera()
    cam.SetViewUp(0, 0, 1)
    cam.SetPosition(0, -1, 0)
    cam.SetFocalPoint(0, 0, 0)
    cam.Elevation(elev)
    cam.Azimuth(azim)
    ren.ResetCamera()
    cam.Zoom(zoom)
    light = vtk.vtkLight()
    light.SetLightTypeToCameraLight()
    light.SetPosition(0.3, 0.6, 1)
    ren.AddLight(light)
    win.Render()
    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(win)
    w2i.Update()
    wr = vtk.vtkPNGWriter()
    wr.SetFileName(path)
    wr.SetInputConnection(w2i.GetOutputPort())
    wr.Write()


def board_parts(pcb, dz=0.0):
    """Split the board STEP into PCB, connector and other parts for colouring."""
    out = []
    j3x, j3y, _ = C.PARTS["J3"]["pcb"]
    for s in pcb.solids().vals():
        bb = s.BoundingBox()
        if abs(bb.center.x - j3x) < 2 and by(j3y + 13) < bb.center.y < by(j3y - 2):
            continue  # J3 is not fitted

        wp = cq.Workplane().add(s).translate((0, 0, dz))
        if bb.xlen > 40 and bb.ylen > 40:
            out.append((wp, "#1f6b3a", 1.0))
        elif bb.zmax - Z_PCB > 6.5 and bb.ylen < 12:
            out.append((wp, "#5fbf6a", 1.0))
        else:
            out.append((wp, "#303030", 1.0))
    return out


def main():
    out = HERE
    b, l = base(), lid()
    cq.exporters.export(b, os.path.join(out, "base.stl"), tolerance=0.02, angularTolerance=0.1)
    cq.exporters.export(b, os.path.join(out, "base.step"))
    # export the lid upside down, ready to print with the text facing the bed
    l_print = l.rotate((0, 0, 0), (1, 0, 0), 180).translate((0, 0, Z_LID + LID_T))
    cq.exporters.export(l_print, os.path.join(out, "lid.stl"), tolerance=0.02, angularTolerance=0.1)
    cq.exporters.export(l, os.path.join(out, "lid.step"))
    pcb = board()
    ok = fit_check(b, l, pcb)
    bb = b.val().BoundingBox()
    print("base outside: %.1f x %.1f x %.1f mm (with cable tongue)" % (bb.xlen, bb.ylen, bb.zlen))
    print("closed height: %.1f mm, lid underside at %.1f mm, board top at %.1f mm" % (Z_LID + LID_T, Z_LID, Z_TOP))
    img = os.path.join(HERE, "..", "docs", "images")
    os.makedirs(img, exist_ok=True)
    grey, white = "#c8ccd0", "#eef0f2"
    render([(b, grey, 1.0), (l, white, 1.0)], os.path.join(img, "enclosure-closed.png"), elev=32, azim=-30)
    if pcb is not None:
        render([(b, grey, 1.0)] + board_parts(pcb), os.path.join(img, "enclosure-open.png"), elev=45, azim=-25)
        render([(b, grey, 1.0)] + board_parts(pcb, 14) + [(l.translate((0, 0, 34)), white, 1.0)],
               os.path.join(img, "enclosure-exploded.png"), elev=18, azim=-30, size=(1400, 1600))
    if not ok:
        raise SystemExit("enclosure clashes with the board")


if __name__ == "__main__":
    main()
