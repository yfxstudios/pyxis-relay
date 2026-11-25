"""Global fiducials for assembly on the routed checkpoint (../routed.kicad_pcb): three on each assembled side.

  .../bin/python3 gen/fiducials.py

KiCad's Fiducial_1mm_Mask2mm (1 mm copper dot, 2 mm mask opening), placed at the free spot nearest three of the
board's corners, at least 3.5 mm from the edge (JLCPCB's guidance is 3 mm or more), with 1.5 mm from the dot's
centre to any other copper on its side and no courtyard overlap. The dot keeps 0.5 mm from the GND pour. Fiducials
are board-only (no schematic symbol) and stay out of the BOM and the position file. Running it again replaces
them.
"""
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from finish import ROUTED  # noqa: E402
from pcb import O, W, H  # noqa: E402

LIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/Fiducial.pretty"
EDGE, CLEAR, STEP = 3.5, 1.5, 0.25


def mm(p):
    return pcbnew.ToMM(p.x) - O[0], pcbnew.ToMM(p.y) - O[1]


def seg_dist(p, a, c):
    dx, dy = c[0] - a[0], c[1] - a[1]
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def main():
    board = pcbnew.LoadBoard(ROUTED)
    for f in [f for f in board.GetFootprints() if f.GetReference().startswith("FID")]:
        board.Remove(f)
    placed = []
    for back in (False, True):
        cu = pcbnew.B_Cu if back else pcbnew.F_Cu
        crt = pcbnew.B_CrtYd if back else pcbnew.F_CrtYd
        copper = []                                  # (a, b, half-width) of other copper on this side
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA":
                p = mm(t.GetPosition())
                copper.append((p, p, pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2))
            elif t.GetLayer() == cu:
                copper.append((mm(t.GetStart()), mm(t.GetEnd()), pcbnew.ToMM(t.GetWidth()) / 2))
        boxes = []
        for f in board.GetFootprints():
            for p in f.Pads():
                if p.IsOnLayer(cu):
                    bb = p.GetBoundingBox()
                    boxes.append((pcbnew.ToMM(bb.GetLeft()) - O[0], pcbnew.ToMM(bb.GetTop()) - O[1],
                                  pcbnew.ToMM(bb.GetRight()) - O[0], pcbnew.ToMM(bb.GetBottom()) - O[1]))
            c = f.GetCourtyard(crt)
            if c.OutlineCount():
                bb = c.BBox()
                boxes.append((pcbnew.ToMM(bb.GetLeft()) - O[0], pcbnew.ToMM(bb.GetTop()) - O[1],
                              pcbnew.ToMM(bb.GetRight()) - O[0], pcbnew.ToMM(bb.GetBottom()) - O[1]))

        def free(x, y):
            if any(seg_dist((x, y), a, b) < CLEAR + hw - 0.5 for a, b, hw in copper):
                return False
            # pads and courtyards: keep the 2 mm mask opening (plus 0.25 mm) clear of them
            r = 1.25
            return not any(x + r > b[0] and x - r < b[2] and y + r > b[1] and y - r < b[3] for b in boxes)
        spots = [(EDGE + i * STEP, EDGE + j * STEP) for i in range(int((W - 2 * EDGE) / STEP) + 1)
                 for j in range(int((H - 2 * EDGE) / STEP) + 1)]
        spots = [s for s in spots if free(*s)]
        corners = [(0, 0), (W, 0), (0, H)] if not back else [(W, 0), (0, H), (W, H)]
        for k, cx in enumerate(corners):
            x, y = min(spots, key=lambda s: math.dist(s, cx))
            ref = f"FID{len(placed) + 1}"
            fp = pcbnew.FootprintLoad(LIB, "Fiducial_1mm_Mask2mm")
            fp.SetReference(ref)
            fp.Reference().SetVisible(False)
            fp.Value().SetVisible(False)
            fp.SetPosition(pcbnew.VECTOR2I_MM(x + O[0], y + O[1]))
            fp.SetAttributes(pcbnew.FP_SMD | pcbnew.FP_BOARD_ONLY | pcbnew.FP_EXCLUDE_FROM_BOM |
                             pcbnew.FP_EXCLUDE_FROM_POS_FILES)
            for p in fp.Pads():
                p.SetLocalClearance(pcbnew.FromMM(0.5))
            board.Add(fp)
            if back:
                fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
            placed.append((ref, "B" if back else "F", round(x, 2), round(y, 2)))
            spots = [s for s in spots if math.dist(s, (x, y)) > 10]
    pcbnew.SaveBoard(ROUTED, board)
    print("fiducials:", placed)


if __name__ == "__main__":
    main()
