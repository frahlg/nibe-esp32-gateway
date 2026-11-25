"""Write the files you upload to JLCPCB, plus PDFs, STEP and images."""
import os
import shutil

import pcbnew

import fab
from build import KDIR, PROD, NAME, PCB, SCH, run

DOCS_IMG = os.path.normpath(os.path.join(KDIR, "..", "..", "docs", "images"))


def main():
    os.makedirs(PROD, exist_ok=True)
    os.makedirs(DOCS_IMG, exist_ok=True)
    board = pcbnew.LoadBoard(PCB)
    z = fab.gerbers(PCB, PROD, NAME)
    bom, cpl = fab.jlc_bom_cpl(board, PROD, NAME)
    print("wrote", z, bom, cpl)

    run(["kicad-cli", "sch", "export", "pdf", "-o", os.path.join(PROD, NAME + "-schematic.pdf"), SCH])
    run(["kicad-cli", "pcb", "export", "pdf", "--layers", "F.Fab,Edge.Cuts", "--mode-single",
         "--include-border-title", "-o", os.path.join(PROD, NAME + "-assembly-top.pdf"), PCB])
    run(["kicad-cli", "pcb", "export", "pdf", "--layers", "F.Cu,F.Silkscreen,Edge.Cuts", "--mode-single",
         "-o", os.path.join(PROD, NAME + "-top-copper.pdf"), PCB])
    run(["kicad-cli", "pcb", "export", "pdf", "--layers", "B.Cu,B.Silkscreen,Edge.Cuts", "--mode-single",
         "--mirror", "-o", os.path.join(PROD, NAME + "-bottom-copper.pdf"), PCB])
    run(["kicad-cli", "pcb", "export", "step", "--subst-models", "--force", "-o",
         os.path.join(PROD, NAME + ".step"), PCB])
    for side in ("top", "bottom"):
        run(["kicad-cli", "pcb", "render", "--side", side, "--width", "1400", "--height", "1600",
             "--quality", "high", "-o", os.path.join(DOCS_IMG, "pcb-%s.png" % side), PCB])
    run(["kicad-cli", "pcb", "render", "--side", "top", "--rotate", "-40,0,-25", "--perspective",
         "--zoom", "0.85", "--width", "1600", "--height", "1200", "--quality", "high",
         "-o", os.path.join(DOCS_IMG, "pcb-3d.png"), PCB])
    shutil.copy(os.path.join(PROD, NAME + "-schematic.pdf"), os.path.join(KDIR, "..", "..", "docs", "schematic.pdf"))
