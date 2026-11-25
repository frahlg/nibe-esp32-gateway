"""Fabrication outputs: Gerbers, drill, JLCPCB BOM and CPL, PDFs, STEP."""
import csv
import glob
import os
import re
import shutil
import subprocess
import zipfile

# Rotation corrections between KiCad footprint zero orientation and the
# JLCPCB parts library, from the community table used by JLCKicadTools
# (github.com/matthewlai/JLCKicadTools, cpl_rotations_db.csv). Always check the
# placement preview on jlcpcb.com before you pay.
JLC_ROTATIONS = [
    (r"^SOT-23", -90),
    (r"^TSOT-23", 180),
    (r"^SOIC-", 270),
    (r"^USB_C_Receptacle_HRO_TYPE-C-31-M-12", 180),
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
