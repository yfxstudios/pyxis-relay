"""Re-places the small parts with a routing gap between courtyards, on the routed checkpoint (../routed.kicad_pcb),
and takes out the low-speed routing so gen/autoroute.py can route it again from a clean slate.

  .../bin/python3 gen/respace.py [gap_mm]        (default 0.8)

The first placement packed the 0402s courtyard to courtyard, which left no channels between them. This keeps:
  - the differential pairs and the parts on them (AC caps, ESD arrays), as routed and placed
  - the RK628D's back-side decoupling under the ball field, and its dogbones, B-side and inner-layer copper there
  - the ICs, inductors, connectors, fuses and switches where they are
  - every GND via (stitching)
and rips every other track and via. Each remaining small part then goes, largest first, to the spot nearest its
connections (the pads it joins on parts already placed) where its courtyard keeps the gap from every other part and
its pads keep the clearance from the copper that stays.
"""
import math
import os
import re
import sys

import numpy as np
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from finish import ROUTED, prune_dead_ends  # noqa: E402
from pcb import NETCLASSES, O, W, H  # noqa: E402
from rest import FRONT_KEEPOUT  # noqa: E402
from router import Router  # noqa: E402
from autoroute import _dogbones, _geom  # noqa: E402

GAP = float(sys.argv[1]) if len(sys.argv) > 1 else 0.8
TIGHT_GAP = 0.3               # for the switching-loop and bulk parts, which must stay close to their IC
RES = 0.05
PAIR = re.compile("|".join(c[-1] for k, c in NETCLASSES.items() if k != "POWER"))
FIXED_PREFIX = ("U", "L", "J", "H", "SW", "F", "MOUNT")
FLIP = 2.0                     # cost of changing side, in mm of connection length
SMALL = 4.0                    # courtyard's longer side, mm
GRAVE = []


def short(n):
    return n.split("/")[-1]


def mmxy(v):
    return pcbnew.ToMM(v.x) - O[0], pcbnew.ToMM(v.y) - O[1]


def court(fp):
    side = pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd
    c = fp.GetCourtyard(side)
    bb = c.BBox() if c.OutlineCount() else fp.GetBoundingBox(False)
    return (pcbnew.ToMM(bb.GetLeft()) - O[0], pcbnew.ToMM(bb.GetTop()) - O[1],
            pcbnew.ToMM(bb.GetRight()) - O[0], pcbnew.ToMM(bb.GetBottom()) - O[1])


def main():
    board = pcbnew.LoadBoard(ROUTED)
    u201 = board.FindFootprintByReference("U201")
    uc = court(u201)

    # the CM3's CEC GPIO moved from J69 (J701) pin 28 to J68 (J702) pin 151 (gen/module.py)
    cec = board.FindNet("CEC_GPIO")
    old = board.FindFootprintByReference("J701").FindPadByNumber("28")
    if old.GetNetCode() == cec.GetNetCode():
        old.SetNetCode(0)
        board.FindFootprintByReference("J702").FindPadByNumber("51").SetNet(cec)

    # which parts move
    fps = list(board.GetFootprints())
    locked_b = [f for f in fps if f.IsFlipped()]
    moving = []
    for f in fps:
        ref = f.GetReference()
        c = court(f)
        small = max(c[2] - c[0], c[3] - c[1]) <= SMALL
        on_pair = any(PAIR.search(short(p.GetNetname())) for p in f.Pads())
        under_bga = f.IsFlipped() and c[0] < uc[2] + 2 and c[2] > uc[0] - 2 and c[1] < uc[3] + 2 and c[3] > uc[1] - 5
        if small and not on_pair and not under_bga and not ref.startswith(FIXED_PREFIX):
            moving.append(f)
    print(f"{len(moving)} parts to re-place: " + " ".join(sorted(f.GetReference() for f in moving)))
    # the decoupling area under the ball field, whose B-side and inner copper stays
    kb = [court(f) for f in locked_b if court(f)[0] < uc[2] + 2 and court(f)[2] > uc[0] - 2
          and court(f)[1] < uc[3] + 2 and court(f)[3] > uc[1] - 5] + [uc]
    keep_box = (min(k[0] for k in kb) - 0.3, min(k[1] for k in kb) - 0.3, max(k[2] for k in kb) + 0.3,
                max(k[3] for k in kb) + 0.3)
    print("kept decoupling box", [round(v, 1) for v in keep_box])

    # rip
    dog = _dogbones(board)
    gnd = board.FindNet("GND").GetNetCode()

    def inside(g):
        return all(keep_box[0] <= x <= keep_box[2] and keep_box[1] <= y <= keep_box[3]
                   for x, y in ((g[0], g[1]), (g[2], g[3])))
    doomed = []
    for t in board.GetTracks():
        g = _geom(t)
        via = t.GetClass() == "PCB_VIA"
        if PAIR.search(short(t.GetNetname())) or t.m_Uuid.AsString() in dog or (via and t.GetNetCode() == gnd):
            continue
        if inside(g) and (via or t.GetLayer() != pcbnew.F_Cu):
            continue
        doomed.append(t)
    nets = {t.GetNetCode() for t in doomed}
    for t in doomed:
        board.Remove(t)
    GRAVE.extend(doomed)
    for nc in nets:
        if nc != gnd:
            prune_dead_ends(board, nc, keep=dog)
    print(f"ripped {len(doomed)} tracks and vias on {len(nets)} nets")

    # the moving parts go off the board while the obstacle maps are made
    home = {}
    for f in moving:
        home[f.GetReference()] = (mmxy(f.GetPosition()), f.GetOrientationDegrees(), court(f))
        f.SetPosition(pcbnew.VECTOR2I_MM(O[0] + 400, O[1] + 400))
    R = Router(board, O, (W, H), (0.0, 0.0, W, H), res=0.1, clearance=0.10)

    nx, ny = int(W / RES) + 1, int(H / RES) + 1
    # (side, firm): obstacles grown by the gap, or by the smaller gap a switching-loop part may keep
    occ = {(b, t): np.zeros((ny, nx), bool) for b in (False, True) for t in (False, True)}

    def paint(side, r, m):
        for t in (False, True):
            g = min(m, TIGHT_GAP) if t else m
            i0 = max(0, int(math.floor((r[0] - g) / RES))); i1 = min(nx, int(math.ceil((r[2] + g) / RES)) + 1)
            j0 = max(0, int(math.floor((r[1] - g) / RES))); j1 = min(ny, int(math.ceil((r[3] + g) / RES)) + 1)
            occ[(side, t)][j0:j1, i0:i1] = True
    moving_ids = {f.GetReference() for f in moving}
    for f in fps:
        if f.GetReference() in moving_ids:
            continue
        paint(f.IsFlipped(), court(f), GAP)
        for p in f.Pads():          # through-hole pins block the other side too
            if p.HasHole():
                bb = p.GetBoundingBox()
                paint(not f.IsFlipped(), (pcbnew.ToMM(bb.GetLeft()) - O[0], pcbnew.ToMM(bb.GetTop()) - O[1],
                                          pcbnew.ToMM(bb.GetRight()) - O[0], pcbnew.ToMM(bb.GetBottom()) - O[1]),
                      GAP / 2)
    for k in FRONT_KEEPOUT:
        paint(False, k, 0)
    edge = 0.5
    for side in occ:
        o = occ[side]
        e = int(edge / RES)
        o[:e, :] = o[-e:, :] = o[:, :e] = o[:, -e:] = True

    def sat(a):
        s = np.zeros((a.shape[0] + 1, a.shape[1] + 1), np.int32)
        s[1:, 1:] = np.cumsum(np.cumsum(a, 0), 1)
        return s

    def rect_hits(s, res, x0, y0, X, Y, r):
        """For candidate centres (X, Y) (arrays), whether rectangle r (relative to the centre) hits s's cells."""
        i0 = np.floor((X + r[0] - x0) / res).astype(int); i1 = np.ceil((X + r[2] - x0) / res).astype(int)
        j0 = np.floor((Y + r[1] - y0) / res).astype(int); j1 = np.ceil((Y + r[3] - y0) / res).astype(int)
        h, w = s.shape[0] - 1, s.shape[1] - 1
        out = (i0 < 0) | (j0 < 0) | (i1 >= w) | (j1 >= h)
        i0, i1, j0, j1 = (np.clip(v, 0, m - 1) for v, m in ((i0, w), (i1, w), (j0, h), (j1, h)))
        n = s[j1 + 1, i1 + 1] - s[j0, i1 + 1] - s[j1 + 1, i0] + s[j0, i0]
        return out | (n > 0)

    sat_occ = {side: sat(occ[side]) for side in occ}
    sums = {}

    def net_sat(nc, layer):
        if (nc, layer) not in sums:
            sums[(nc, layer)] = sat(R.blocked(nc, 0.0, [layer])[0])
        return sums[(nc, layer)]

    placed = {f.GetReference() for f in fps} - moving_ids
    def tight(f):
        """Parts of a converter's switching loop or a supply's bulk decoupling, and the ESD arrays: they stay on
        their side and move as little as they can, before everything else."""
        return f.GetReference().startswith(("D", "Q1")) or "uF" in f.GetValue() or \
            any(re.match(r"(LX_|SW_|BS|BST)", short(p.GetNetname())) for p in f.Pads())

    def area(f):
        c = home[f.GetReference()][2]
        return (c[2] - c[0]) * (c[3] - c[1])
    order = sorted(moving, key=lambda f: (not tight(f), -area(f)))
    moves = []
    flips = 0
    for f in order:
        ref = f.GetReference()
        (hx, hy), rot0, _ = home[ref]
        # targets: each non-GND pad's nearest same-net pad on a placed part
        tgt = {}
        for p in f.Pads():
            nc = p.GetNetCode()
            if nc in (0, gnd):
                continue
            pts = [mmxy(q.GetPosition()) for g in fps if g.GetReference() in placed for q in g.Pads()
                   if q.GetNetCode() == nc]
            if pts:
                tgt[p.GetNumber()] = pts
        best = None
        back0 = f.IsFlipped()
        firm = tight(f)
        for back in ((back0,) if firm else (back0, not back0)):          # the other side when it is much better: costs a via or two
            if f.IsFlipped() != back:
                f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
            layer = pcbnew.B_Cu if back else pcbnew.F_Cu
            for drot in (0, 90, 180, 270):
                rot = (rot0 + drot) % 360
                f.SetOrientationDegrees(rot)
                f.SetPosition(pcbnew.VECTOR2I_MM(O[0], O[1]))
                cr = court(f)
                pads = []
                for p in f.Pads():
                    bb = p.GetBoundingBox()
                    px, py = mmxy(p.GetPosition())
                    pads.append((p.GetNumber(), p.GetNetCode(), px, py,
                                 (pcbnew.ToMM(bb.GetLeft()) - O[0], pcbnew.ToMM(bb.GetTop()) - O[1],
                                  pcbnew.ToMM(bb.GetRight()) - O[0], pcbnew.ToMM(bb.GetBottom()) - O[1])))
                for span, step in ((6.0, 0.1), (14.0, 0.2)):
                    g = np.arange(-span, span + 1e-9, step)
                    X, Y = np.meshgrid(hx + g, hy + g)
                    ok = ~rect_hits(sat_occ[(back, firm)], RES, 0.0, 0.0, X, Y, cr)
                    for num, nc, px, py, pr in pads:
                        if not ok.any():
                            break
                        ok &= ~rect_hits(net_sat(nc, layer), R.res, R.x0, R.y0, X, Y, pr)
                    if not ok.any():
                        continue
                    cost = (1.0 if firm else 0.3) * np.hypot(X - hx, Y - hy) + (0.4 if drot else 0.0) + (FLIP if back != back0 else 0.0)
                    for num, nc, px, py, pr in pads:
                        if num in tgt:
                            cost = cost + np.min([np.hypot(X + px - tx, Y + py - ty) for tx, ty in tgt[num]], axis=0)
                    cost = np.where(ok, cost, np.inf)
                    k = np.unravel_index(np.argmin(cost), cost.shape)
                    if best is None or cost[k] < best[0]:
                        best = (cost[k], X[k], Y[k], rot, cr, back)
                    break
        if best is None:
            raise SystemExit(f"no room for {ref}")
        _, x, y, rot, cr, back = best
        x, y = float(x), float(y)
        if f.IsFlipped() != back:
            f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        f.SetOrientationDegrees(rot)
        f.SetPosition(pcbnew.VECTOR2I_MM(O[0] + x, O[1] + y))
        paint(back, (x + cr[0], y + cr[1], x + cr[2], y + cr[3]), GAP)
        for t in (False, True):
            sat_occ[(back, t)] = sat(occ[(back, t)])
        placed.add(ref)
        flips += back != back0
        moves.append((math.hypot(x - hx, y - hy), ref))
        print(f"{ref}: moved {math.hypot(x - hx, y - hy):.2f} mm, rot {rot0:.0f} -> {rot:.0f}"
              + (" (other side)" if back != back0 else ""), flush=True)

    moves.sort(reverse=True)
    print(f"{flips} parts changed side")
    print("largest moves:", ", ".join(f"{r} {d:.1f}" for d, r in moves[:15]))
    pcbnew.SaveBoard(ROUTED, board)
    print("saved", ROUTED)
    sys.stdout.flush()
    os._exit(0)



if __name__ == "__main__":
    main()
