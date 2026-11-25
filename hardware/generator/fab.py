"""Fabrication outputs: Gerbers, drill, JLCPCB BOM and CPL, PDFs, STEP."""
import csv
import glob
import os
import re
import shutil
import subprocess
import zipfile

# Corrections between KiCad's footprint origin/zero rotation and the JLCPCB
# parts library. Each entry was checked against the JLCPCB placement viewer on
# 2026-11-25 for the exact LCSC part on this board. The community table in
# JLCKicadTools had USB-C and SOT-23 (3-pin) wrong for these parts.
# Still check the placement preview on jlcpcb.com before you pay.
JLC_ROTATIONS = [
    (r"^SOT-23-6", -90),                            # U1 USBLC6-2SC6
    (r"^SOT-23$", 180),                             # D4 PSM712
    (r"^SOT-583", 180),                             # U4 TPS62933
    (r"^SOIC-", 270),                               # U2 THVD1450
    (r"^USB_C_Receptacle_HRO_TYPE-C-31-M-12", 0),   # J1
]
# Where JLCPCB's footprint origin differs from KiCad's (mm, KiCad footprint frame, y down).
# U3 and J1 come from JLCPCB's own footprints for C2913204 and C165948, checked in the preview.
JLC_OFFSETS = [
    (r"^PhoenixContact_MC_1,5_4-G-3.5", (5.25, 0.0)),        # J2: centre of the four pins, not pin 1
    (r"^ESP32-S3-WROOM-1$", (0.0, 3.635)),                    # U3: centre of the pad field, not of the body
    (r"^USB_C_Receptacle_HRO_TYPE-C-31-M-12", (0.0, -1.424)),  # J1: 1.42 mm further from the board edge
]


def run(cmd):
    print("+", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        raise SystemExit("command failed: %s" % cmd[0:3])
    return r.stdout


def gerbers(pcb, outdir, name):
    gdir = os.path.join(outdir, "gerber")
    shutil.rmtree(gdir, ignore_errors=True)
    os.makedirs(gdir)
    run(["kicad-cli", "pcb", "export", "gerbers", "--output", gdir + "/",
         "--layers", "F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts",
         "--subtract-soldermask", "--no-x2", "--no-netlist", "--use-drill-file-origin", pcb])
    run(["kicad-cli", "pcb", "export", "drill", "--output", gdir + "/", "--format", "excellon",
         "--drill-origin", "absolute", "--excellon-units", "mm", "--excellon-zeros-format", "decimal", pcb])
    zpath = os.path.join(outdir, "%s-gerbers.zip" % name)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(glob.glob(gdir + "/*")):
            z.write(f, os.path.basename(f))
    shutil.rmtree(gdir)
    return zpath


def jlc_bom_cpl(board, outdir, name):
    """Write JLCPCB BOM and CPL straight from the board object."""
    import pcbnew
    rows = {}
    cpl = []
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        attrs = fp.GetAttributes()
        if ref.startswith("#") or attrs & pcbnew.FP_DNP or attrs & pcbnew.FP_EXCLUDE_FROM_BOM:
            continue
        lcsc = fp.GetFieldText("LCSC") if fp.HasFieldByName("LCSC") else ""
        if not lcsc:
            continue
        fpname = fp.GetFPID().GetLibItemName().wx_str() if hasattr(fp.GetFPID().GetLibItemName(), "wx_str") else str(fp.GetFPID().GetLibItemName())
        key = (fp.GetValue(), fpname, lcsc)
        rows.setdefault(key, []).append(ref)
        if attrs & pcbnew.FP_EXCLUDE_FROM_POS_FILES:
            continue
        pos = fp.GetPosition()
        x = pcbnew.ToMM(pos.x)
        y = -pcbnew.ToMM(pos.y)
        rot = fp.GetOrientationDegrees()
        for pat, (dx, dy) in JLC_OFFSETS:
            if re.search(pat, fpname):
                import math
                a = math.radians(rot)  # KiCad rotates counter-clockwise on screen (y down)
                x += dx * math.cos(a) + dy * math.sin(a)
                y -= -dx * math.sin(a) + dy * math.cos(a)
                break
        for pat, corr in JLC_ROTATIONS:
            if re.search(pat, fpname):
                rot += corr
                break
        rot %= 360
        side = "Bottom" if fp.IsFlipped() else "Top"
        cpl.append((ref, "%.4fmm" % x, "%.4fmm" % y, side, "%g" % rot))
    bom_path = os.path.join(outdir, "%s-bom-jlcpcb.csv" % name)
    with open(bom_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (val, fpn, lcsc), refs in sorted(rows.items(), key=lambda kv: natural(kv[1][0])):
            w.writerow([val, ",".join(sorted(refs, key=natural)), fpn, lcsc])
    cpl_path = os.path.join(outdir, "%s-cpl-jlcpcb.csv" % name)
    with open(cpl_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in sorted(cpl, key=lambda r: natural(r[0])):
            w.writerow(r)
    return bom_path, cpl_path


def natural(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]
