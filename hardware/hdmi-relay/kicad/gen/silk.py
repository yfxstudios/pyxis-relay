"""Reference designators on the routed checkpoint (../routed.kicad_pcb), placed clear of pads, other silkscreen and
the board edge.

  .../bin/python3 gen/silk.py

Every reference becomes 0.8 mm text (0.15 mm stroke, JLCPCB's minimum legible size). Each is tried above, below,
left and right of its part's pads, then rotated a quarter turn, then a little farther out; the first spot that
keeps 0.1 mm from exposed pads on its side, from the other parts' outlines and references, and 0.3 mm inside the
board edge wins. A reference with no such spot is hidden: the part is still in the BOM and the CPL, and the
assembly drawing (F.Fab) keeps every reference.
"""
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from finish import ROUTED  # noqa: E402
from pcb import O, W, H  # noqa: E402

SIZE, STROKE = 0.8, 0.15
GAP = 0.1          # silk to pads and to other silk
EDGE = 0.3         # silk to the board edge


def box(item):
    bb = item.GetBoundingBox()
    return (pcbnew.ToMM(bb.GetLeft()) - O[0], pcbnew.ToMM(bb.GetTop()) - O[1],
            pcbnew.ToMM(bb.GetRight()) - O[0], pcbnew.ToMM(bb.GetBottom()) - O[1])


def overlap(a, b, gap):
    return a[0] < b[2] + gap and b[0] < a[2] + gap and a[1] < b[3] + gap and b[1] < a[3] + gap


def seg_hits_box(p, q, w, r, gap):
    """Whether segment pq (stroke w) comes within gap of box r."""
    g = gap + w / 2
    n = max(2, int(math.dist(p, q) / 0.05))
    for k in range(n + 1):
        x, y = p[0] + (q[0] - p[0]) * k / n, p[1] + (q[1] - p[1]) * k / n
        if r[0] - g < x < r[2] + g and r[1] - g < y < r[3] + g:
            return True
    return False


def outline_segments(fp, layer):
    """A footprint's silkscreen graphics on one layer, as (start, end, width) segments (others as their box)."""
    out = []
    for g in fp.GraphicalItems():
        if g.GetLayer() != layer or g.GetClass() not in ("PCB_SHAPE",):
            continue
        w = pcbnew.ToMM(g.GetWidth())
        s = g.GetShape()
        if s == pcbnew.SHAPE_T_SEGMENT:
            a, b = g.GetStart(), g.GetEnd()
            out.append(((pcbnew.ToMM(a.x) - O[0], pcbnew.ToMM(a.y) - O[1]),
                        (pcbnew.ToMM(b.x) - O[0], pcbnew.ToMM(b.y) - O[1]), w))
        else:
            x0, y0, x1, y1 = box(g)
            if s == pcbnew.SHAPE_T_RECT:
                for p, q in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
                    out.append((p, q, 0.0))
            else:
                out.append(("box", (x0, y0, x1, y1), w))
    return out


def main():
    board = pcbnew.LoadBoard(ROUTED)
    fps = list(board.GetFootprints())
    side = {f.GetReference(): pcbnew.B_SilkS if f.IsFlipped() else pcbnew.F_SilkS for f in fps}
    pads = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
    for f in fps:
        for p in f.Pads():
            for cu, sk in ((pcbnew.F_Cu, pcbnew.F_SilkS), (pcbnew.B_Cu, pcbnew.B_SilkS)):
                if p.IsOnLayer(cu):
                    pads[sk].append(box(p))
    lines = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
    for f in fps:
        for sk in lines:
            lines[sk] += [(f.GetReference(), s) for s in outline_segments(f, sk)]
    placed = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
    # other silk text that stays where it is (values and user text on silk)
    for f in fps:
        for t in f.GraphicalItems():
            if t.GetClass() == "PCB_TEXT" and t.GetLayer() in placed and t.IsVisible():
                placed[t.GetLayer()].append(box(t))
        v = f.Value()
        if v.IsVisible() and v.GetLayer() in placed:
            placed[v.GetLayer()].append(box(v))

    def clear(ref, sk, r):
        if r[0] < EDGE or r[1] < EDGE or r[2] > W - EDGE or r[3] > H - EDGE:
            return False
        if any(overlap(r, p, GAP) for p in pads[sk]):
            return False
        if any(overlap(r, p, GAP) for p in placed[sk]):
            return False
        for owner, s in lines[sk]:
            if s[0] == "box":
                if overlap(r, s[1], GAP + s[2] / 2):
                    return False
            elif seg_hits_box(s[0], s[1], s[2], r, GAP):
                return False
        return True

    # mounting holes need no reference (J301's outline, which hangs over the edge with the jack, is allowed by
    # relay.kicad_dru)
    for f in fps:
        if f.GetReference().startswith("H"):
            f.Reference().SetVisible(False)

    # crowded parts first: most pads nearby, fewest places to go
    order = sorted(fps, key=lambda f: -sum(overlap(box(f), p, 1.0) for p in pads[side[f.GetReference()]]))
    moved = hidden = 0
    for f in order:
        ref, t = f.GetReference(), f.Reference()
        if not t.IsVisible() or ref.startswith(("H", "MOUNT")):
            continue
        sk = side[ref]
        t.SetLayer(sk)
        t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(SIZE), pcbnew.FromMM(SIZE)))
        t.SetTextThickness(pcbnew.FromMM(STROKE))
        t.SetKeepUpright(True)
        pb = [box(p) for p in f.Pads()] or [box(f)]
        x0, y0 = min(b[0] for b in pb), min(b[1] for b in pb)
        x1, y1 = max(b[2] for b in pb), max(b[3] for b in pb)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        spot = None
        for extra in (0.0, 0.4, 0.9, 1.5):
            for ang in (0, 90):
                t.SetTextAngle(pcbnew.EDA_ANGLE(ang, pcbnew.DEGREES_T))
                t.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(cx + O[0]), pcbnew.FromMM(cy + O[1])))
                tb = box(t)
                hw, hh = (tb[2] - tb[0]) / 2, (tb[3] - tb[1]) / 2
                d = GAP + 0.05 + extra
                for px, py in ((cx, y0 - d - hh), (cx, y1 + d + hh), (x0 - d - hw, cy), (x1 + d + hw, cy)):
                    r = (px - hw, py - hh, px + hw, py + hh)
                    if clear(ref, sk, r):
                        spot = (px, py, r)
                        break
                if spot:
                    break
            if spot:
                break
        if spot:
            t.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(spot[0] + O[0]), pcbnew.FromMM(spot[1] + O[1])))
            placed[sk].append(box(t))
            moved += 1
        else:
            t.SetVisible(False)
            hidden += 1
    pcbnew.SaveBoard(ROUTED, board)
    print(f"silk: {moved} references placed, {hidden} hidden (no clear spot)")


if __name__ == "__main__":
    main()
