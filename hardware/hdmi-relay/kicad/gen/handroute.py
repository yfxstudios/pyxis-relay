"""Hand-drawn routes on the routed checkpoint (../routed.kicad_pcb), checked against every item on the board first.

  .../bin/python3 gen/handroute.py NET 'L:x,y x,y ...' ['V:x,y' ...] [--commit]

Each argument is a run of track on layer L (F, 1, 2 or B: F.Cu, In1, In2, B.Cu; width after a slash, e.g. 1/0.09)
or a via (0.3 mm, 0.15 mm drill; another size as V/0.6/0.3:x,y). Without --commit it only prints what would be too close: copper within 0.1 mm,
a drilled hole within 0.2 mm of copper, holes within 0.25 mm of each other.
"""
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from finish import ROUTED  # noqa: E402
from pcb import O  # noqa: E402

LAYERS = {"F": pcbnew.F_Cu, "1": pcbnew.In1_Cu, "2": pcbnew.In2_Cu, "B": pcbnew.B_Cu}
CL, HOLE_CL, HOLE_HOLE = 0.1, 0.2, 0.25


def seg_dist(a, b, c, d):
    """Distance between segments ab and cd (points as (x, y))."""
    def pt(p, q, r):
        dx, dy = r[0] - q[0], r[1] - q[1]
        L = dx * dx + dy * dy
        t = 0 if L == 0 else max(0, min(1, ((p[0] - q[0]) * dx + (p[1] - q[1]) * dy) / L))
        return math.hypot(p[0] - q[0] - t * dx, p[1] - q[1] - t * dy)

    def cross(p, q, r, s):
        def o(a_, b_, c_):
            return (b_[0] - a_[0]) * (c_[1] - a_[1]) - (b_[1] - a_[1]) * (c_[0] - a_[0])
        return o(p, q, r) * o(p, q, s) < 0 and o(r, s, p) * o(r, s, q) < 0
    if cross(a, b, c, d):
        return 0.0
    return min(pt(a, c, d), pt(b, c, d), pt(c, a, b), pt(d, a, b))


def parse(specs):
    new = []           # (layer or None for a via, a, b, half width, drill radius)
    for s in specs:
        kind, rest = s.split(":", 1)
        pts = [tuple(float(v) for v in p.split(",")) for p in rest.split()]
        if kind.startswith("V"):
            size = [float(v) for v in kind.split("/")[1:]] or [0.3, 0.15]
            new.append((None, pts[0], pts[0], size[0] / 2, size[1] / 2))
        else:
            ly, _, w = kind.partition("/")
            for a, b in zip(pts, pts[1:]):
                new.append((LAYERS[ly], a, b, float(w or 0.1) / 2, 0))
    return new


def obstacles(board, nc):
    def mm(v):
        return pcbnew.ToMM(v.x) - O[0], pcbnew.ToMM(v.y) - O[1]
    others = []        # (layers or None for all, a, b, half width, drill radius, description)
    for t in board.GetTracks():
        if t.GetNetCode() == nc:
            continue
        n = t.GetNetname().split("/")[-1]
        if t.GetClass() == "PCB_VIA":
            p = mm(t.GetPosition())
            others.append((None, p, p, pcbnew.ToMM(t.GetWidth()) / 2, pcbnew.ToMM(t.GetDrill()) / 2, f"via {n}"))
        else:
            others.append(({t.GetLayer()}, mm(t.GetStart()), mm(t.GetEnd()), pcbnew.ToMM(t.GetWidth()) / 2, 0,
                           f"track {n} {t.GetLayerName()}"))
    for f in board.GetFootprints():
        for p in f.Pads():
            if p.GetNetCode() == nc and nc:
                continue
            bb = p.GetBoundingBox()
            c = mm(p.GetPosition())
            r = min(pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())) / 2
            L = max(pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())) / 2 - r
            try:
                shape = p.GetShape(pcbnew.F_Cu)
            except TypeError:
                shape = p.GetShape()
            if shape not in (pcbnew.PAD_SHAPE_CIRCLE, pcbnew.PAD_SHAPE_OVAL):
                r *= 1.42          # a capsule round a rectangle's long axis misses its corners: grow it to cover them
            if bb.GetWidth() >= bb.GetHeight():
                a, b = (c[0] - L, c[1]), (c[0] + L, c[1])
            else:
                a, b = (c[0], c[1] - L), (c[0], c[1] + L)
            lys = {l for l in LAYERS.values() if p.IsOnLayer(l)}
            drill = pcbnew.ToMM(p.GetDrillSize().x) / 2 if p.HasHole() else 0
            others.append((lys, a, b, r, drill, f"pad {f.GetReference()}.{p.GetNumber()} "
                                                f"{p.GetNetname().split('/')[-1]}"))
    return others


def problems(new, others, quiet=False):
    bad = 0
    for ly, a, b, h, dr in new:
        for oly, oa, ob, oh, odr, desc in others:
            same = ly is None or oly is None or ly in oly
            d = seg_dist(a, b, oa, ob)
            need = []
            if same and d < h + oh + CL - 1e-4:
                need.append(f"copper {d - h - oh:.3f}")
            if dr and d - dr - oh < HOLE_CL - 1e-4 and (oly is None or True):
                need.append(f"hole-copper {d - dr - oh:.3f}")
            if odr and d - odr - h < HOLE_CL - 1e-4 and same:
                need.append(f"copper-hole {d - odr - h:.3f}")
            if dr and odr and d - dr - odr < HOLE_HOLE - 1e-4:
                need.append(f"hole-hole {d - dr - odr:.3f}")
            if need:
                bad += 1
                if not quiet:
                    print(f"{'via' if ly is None else pcbnew.LayerName(ly)} {a}-{b}: {desc}: {', '.join(need)}")
    return bad


def main():
    net, specs = sys.argv[1], [a for a in sys.argv[2:] if a != "--commit"]
    board = pcbnew.LoadBoard(ROUTED)
    ni = [v for k, v in board.GetNetsByName().items() if str(k).split("/")[-1] == net][0]
    nc = ni.GetNetCode()
    new = parse(specs)
    others = obstacles(board, nc)
    bad = problems(new, others)
    print(f"{bad} problems")
    if "--commit" in sys.argv and not bad:
        for ly, a, b, h, dr in new:
            if ly is None:
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I_MM(O[0] + a[0], O[1] + a[1])); v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetWidth(pcbnew.FromMM(2 * h)); v.SetDrill(pcbnew.FromMM(2 * dr))
                v.SetNet(ni)
                board.Add(v)
            else:
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I_MM(O[0] + a[0], O[1] + a[1]))
                t.SetEnd(pcbnew.VECTOR2I_MM(O[0] + b[0], O[1] + b[1]))
                t.SetWidth(pcbnew.FromMM(2 * h)); t.SetLayer(ly); t.SetNet(ni)
                board.Add(t)
        pcbnew.SaveBoard(ROUTED, board)
        print("committed")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
