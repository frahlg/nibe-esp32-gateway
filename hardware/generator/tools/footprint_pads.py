"""Print pad positions and courtyard of library footprints.

Usage (inside the KiCad image): python3 tools/footprint_pads.py "Lib:Footprint" ...
"""
import sys, pcbnew
for spec in sys.argv[1:]:
    lib, name = spec.split(":")
    fp = pcbnew.FootprintLoad("/usr/share/kicad/footprints/%s.pretty" % lib, name)
    bb = fp.GetBoundingBox(False)
    cy = fp.GetCourtyard(pcbnew.F_CrtYd).BBox() if fp.GetCourtyard(pcbnew.F_CrtYd).OutlineCount() else None
    print("##", spec, "bbox %.2f x %.2f" % (pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())),
          "court x[%.2f,%.2f] y[%.2f,%.2f]" % (pcbnew.ToMM(cy.GetLeft()), pcbnew.ToMM(cy.GetRight()), pcbnew.ToMM(cy.GetTop()), pcbnew.ToMM(cy.GetBottom())) if cy else "")
    seen = {}
    for p in fp.Pads():
        k = p.GetNumber()
        s = p.GetSize()
        print("  %-4s (%7.3f,%7.3f) %5.2fx%-5.2f %s drill=%.2f" % (k, pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y), pcbnew.ToMM(s.x), pcbnew.ToMM(s.y), p.GetAttribute(), pcbnew.ToMM(p.GetDrillSize().x)))

