"""CSI length matching (REVIEW_FABLE_2.md M1), on the routed checkpoint (../routed.kicad_pcb).

  .../bin/python3 gen/csimatch.py clear     remove what is in the way and the old CLK/D1 tails and D2's B run
  .../bin/python3 gen/csimatch.py add       draw the meandered CLK, D1 (F.Cu) and D2 (B.Cu), lengths solved
  .../bin/python3 gen/csimatch.py tidy      after the re-routes: move one 5V_SYS via off the CLK lane
  .../bin/python3 gen/csimatch.py report    carrier and total (carrier + module) length of every lane

The CM3 routes D0 and D3 about 25 mm longer inside the module than CLK, D1 and D2 (CM3 datasheet 3.5.3), and its rule
is data-to-clock mismatch < 36 mil counting both. D2 sits between D3 and CLK and only has room for two bumps (about
+16 mm), so the lanes are matched to a window instead: CLK at the midpoint of D2 and D3, D1 on CLK, D0 left alone.
The worst data-to-clock skew drops from 27 mm to about 6 mm.

Between the steps: gen/localroute.py re-routes 5V_SYS (to U401/J602, now 0.6 mm all the way), PCIE_PERST_N and
PCIE_CLKREQ_N, which "clear" lifted out of the meander areas (README, "CSI length matching").
"""
import io
import contextlib
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import handroute as H  # noqa: E402
from finish import GRAVEYARD, ROUTED  # noqa: E402
from pcb import O  # noqa: E402

# module-internal lengths, mean of P and N (CM3 datasheet 3.5.3, mil -> mm)
MODULE = {"CLK": 1398.1 * 0.0254, "D0": 2403.85 * 0.0254, "D1": 1391.75 * 0.0254, "D2": 1563.5 * 0.0254,
          "D3": 2522.0 * 0.0254}
W, HW, HW_PAD = 0.1, 0.1, 0.2        # trace width; half pair pitch in the run; half pitch at J702's 0.4 mm pads
LEG = 0.7                             # meander leg pitch: 0.4 mm between neighbouring legs of a pair
CH = 0.2                              # 45-degree corner chamfer
CUT_Y = 33.0                          # CLK and D1 are replaced from here down to J702


def net(board, short):
    return next(v for k, v in board.GetNetsByName().items() if str(k).split("/")[-1] == short)


def mm(p):
    return round(pcbnew.ToMM(p.x) - O[0], 3), round(pcbnew.ToMM(p.y) - O[1], 3)


def vec(x, y):
    return pcbnew.VECTOR2I_MM(x + O[0], y + O[1])


def remove(board, items):
    for t in items:
        board.Remove(t)
    GRAVEYARD.extend(items)


# ---- geometry -------------------------------------------------------------------------------------------------
def chamfer(pts, c=CH):
    """Cut every corner of an orthogonal/45-degree polyline by c along both legs."""
    out = [pts[0]]
    for a, b, n in zip(pts, pts[1:], pts[2:]):
        la, lb = math.dist(a, b), math.dist(b, n)
        if la < 1e-9 or lb < 1e-9:
            continue
        ua = ((b[0] - a[0]) / la, (b[1] - a[1]) / la)
        ub = ((n[0] - b[0]) / lb, (n[1] - b[1]) / lb)
        if abs(ua[0] * ub[1] - ua[1] * ub[0]) < 1e-9:      # straight on
            out.append(b)
            continue
        k = min(c, la / 2, lb / 2)
        out += [(b[0] - ua[0] * k, b[1] - ua[1] * k), (b[0] + ub[0] * k, b[1] + ub[1] * k)]
    out.append(pts[-1])
    return out


def offset(pts, hws, side):
    """Offset a polyline sideways (side +1 = right of travel, y down), with a half-width per segment (mitred)."""
    lines = []
    for (a, b), hw in zip(zip(pts, pts[1:]), hws):
        L = math.dist(a, b)
        d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        n = (-d[1], d[0])
        o = (a[0] + side * hw * n[0], a[1] + side * hw * n[1])
        lines.append((o, d, (b[0] + side * hw * n[0], b[1] + side * hw * n[1])))
    out = [lines[0][0]]
    for (o1, d1, _), (o2, d2, _) in zip(lines, lines[1:]):
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-12:
            out.append(o2)
            continue
        t = ((o2[0] - o1[0]) * d2[1] - (o2[1] - o1[1]) * d2[0]) / den
        out.append((o1[0] + t * d1[0], o1[1] + t * d1[1]))
    out.append(lines[-1][2])
    return [(round(x, 4), round(y, 4)) for x, y in out]


def plen(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def bumps(x0, y0, legs, heights, s):
    """Accordion along a baseline going east: for each bump, out-and-back legs at x, x + LEG, height h, toward s
    (+1 down, -1 up). Returns the baseline-and-bump points (corners not yet chamfered)."""
    pts = []
    for x, h in zip(legs, heights):
        pts += [(x, y0), (x, y0 + s * h), (x + LEG, y0 + s * h), (x + LEG, y0)]
    return pts


# ---- the three lanes -------------------------------------------------------------------------------------------
def lane(name, heights):
    """Centreline points and per-segment half-widths for the new part of a lane."""
    if name == "CLK":        # F.Cu: down x 53.5, baseline y 40.2, bumps down, up to J702 27/29 at x 64.08
        x0, yb, xe, s = 53.5, 40.2, 64.08, +1
        legs = [54.6 + i * 2 * LEG for i in range(len(heights))]
    elif name == "D1":       # F.Cu: down x 54.5, baseline y 39.4, bumps up toward D0, up to J702 21/23 at x 62.88
        x0, yb, xe, s = 54.5, 39.4, 62.88, -1
        legs = [55.9 + i * 2 * LEG for i in range(len(heights))]
    else:                    # D2, B.Cu, between its via pairs: baseline y 32.15 from x 53.1 to 55.8, bumps up
        pts = [(53.1, 32.15)] + bumps(0, 32.15, [53.45, 54.85][:len(heights)], heights, -1) + [(55.8, 32.15)]
        pts = chamfer(pts)
        return pts, [HW] * (len(pts) - 1)
    pts = [(x0, CUT_Y), (x0, yb)] + bumps(0, yb, legs, heights, s) + [(xe, yb), (xe, 34.32)]
    pts = chamfer(pts)
    hws = [HW] * (len(pts) - 1)
    hws[-1] = HW_PAD                  # the last leg runs at J702's 0.4 mm pad pitch
    return pts, hws


def solve(name, target_new):
    """Bump heights that make the new centreline (P/N mean) target_new long: whole bumps at the cap, the rest in
    the last one."""
    cap = {"CLK": 4.0, "D1": 2.45, "D2": 3.9}[name]
    nmax = {"CLK": 5, "D1": 4, "D2": 2}[name]
    for n in range(0, nmax + 1):
        base, _ = lane(name, [cap] * n)
        if n and mean_len(name, [cap] * n) >= target_new:
            lo, hi = 0.3, cap
            for _ in range(60):
                mid = (lo + hi) / 2
                if mean_len(name, [cap] * (n - 1) + [mid]) < target_new:
                    lo = mid
                else:
                    hi = mid
            return [cap] * (n - 1) + [round(hi, 4)]
    return [cap] * nmax                                      # cannot reach: as long as it goes


def mean_len(name, heights):
    pts, hws = lane(name, heights)
    return (plen(offset(pts, hws, +1)) + plen(offset(pts, hws, -1))) / 2


# ---- steps -----------------------------------------------------------------------------------------------------
GONE_SEGS = {   # (net, layer, a, b): copper "clear" lifts, re-routed afterwards with gen/localroute.py
    "5V_SYS": [("F", (50.15, 33.95), (49.5, 33.3)), ("F", (49.5, 33.3), (49.5, 29.0)),
               ("F", (50.3, 34.2), (51.4, 34.2)), ("F", (51.4, 34.2), (55.8, 38.6)),
               ("F", (55.8, 38.6), (64.9, 38.6)), ("B", (64.9, 38.6), (66.9, 36.6)),
               ("B", (66.9, 36.6), (67.3, 36.6))],
    "PCIE_PERST_N": [("F", (50.6, 44.5), (55.7, 39.4)), ("F", (55.7, 39.4), (56.6, 39.4)),
                     ("B", (56.6, 39.4), (60.3, 35.7))],
    "PCIE_CLKREQ_N": [("B", (52.1, 30.45), (53.05, 31.4)), ("B", (53.6, 30.9), (53.1, 31.4)),
                      ("B", (53.6, 30.9), (57.3, 30.9)), ("B", (57.3, 30.9), (58.3, 31.9))],
}
GONE_VIAS = {"5V_SYS": [(64.9, 38.6)], "PCIE_PERST_N": [(56.6, 39.4)],
             "GND": [(58.0, 42.0), (62.0, 42.0), (63.3, 37.18), (52.96, 30.68)]}
LAYER = {"F": pcbnew.F_Cu, "B": pcbnew.B_Cu}
# the F.Cu strip between D1's and CLK's legs into J702 holds a J702 GND pad; it reached the plane through the via
# at (63.3, 37.18), which the new D1 leg passes: two vias in the strip instead
NEW_GND_VIAS = [(63.48, 36.2), (63.48, 38.0)]


def clear(board):
    gone = []
    for n, segs in GONE_SEGS.items():
        nc = net(board, n).GetNetCode()
        for ly, a, b in segs:
            hit = [t for t in board.GetTracks() if t.GetNetCode() == nc and t.GetClass() == "PCB_TRACK"
                   and t.GetLayer() == LAYER[ly] and {mm(t.GetStart())[:2], mm(t.GetEnd())[:2]} ==
                   {(round(a[0], 3), round(a[1], 3)), (round(b[0], 3), round(b[1], 3))}]
            assert len(hit) == 1, (n, ly, a, b, len(hit))
            gone += hit
    for n, vias in GONE_VIAS.items():
        nc = net(board, n).GetNetCode()
        for c in vias:
            hit = [t for t in board.GetTracks() if t.GetNetCode() == nc and t.GetClass() == "PCB_VIA"
                   and math.dist(mm(t.GetPosition()), c) < 0.01]
            assert len(hit) == 1, (n, c, len(hit))
            gone += hit
    # CLK and D1: everything below CUT_Y goes; the verticals crossing it are cut back to it
    for n in ("CSI_CLK_P", "CSI_CLK_N", "CSI_D1_P", "CSI_D1_N"):
        nc = net(board, n).GetNetCode()
        for t in [t for t in board.GetTracks() if t.GetNetCode() == nc and t.GetClass() == "PCB_TRACK"]:
            a, b = mm(t.GetStart()), mm(t.GetEnd())
            if min(a[1], b[1]) >= CUT_Y - 1e-6:
                gone.append(t)
            elif max(a[1], b[1]) > CUT_Y:
                assert abs(a[0] - b[0]) < 1e-6, (n, a, b)          # only straight verticals cross the cut
                lo = a if a[1] < b[1] else b
                t.SetStart(vec(*lo))
                t.SetEnd(vec(lo[0], CUT_Y))
    # D2's straight B.Cu run between its vias
    for n, seg in (("CSI_D2_P", ((52.7, 32.25), (55.8, 32.25))), ("CSI_D2_N", ((53.1, 32.05), (56.2, 32.05)))):
        nc = net(board, n).GetNetCode()
        hit = [t for t in board.GetTracks() if t.GetNetCode() == nc and t.GetClass() == "PCB_TRACK"
               and {mm(t.GetStart()), mm(t.GetEnd())} == set(seg)]
        assert len(hit) == 1, (n, len(hit))
        gone += hit
    remove(board, gone)
    print(f"clear: {len(gone)} items removed, CLK/D1 cut back to y {CUT_Y}")


def carrier(board, short):
    nc = net(board, short).GetNetCode()
    return sum(pcbnew.ToMM(t.GetLength()) for t in board.GetTracks()
               if t.GetNetCode() == nc and t.GetClass() == "PCB_TRACK")


def add(board, commit):
    have = {k: (carrier(board, f"CSI_{k}_P") + carrier(board, f"CSI_{k}_N")) / 2 for k in MODULE}
    plan = {}
    d2 = solve("D2", 99.0)                                    # D2 as long as its pocket allows
    d2_new = mean_len("D2", d2) + 0.4                         # plus its 0.4 mm connector (one per polarity)
    total = {"D0": have["D0"] + MODULE["D0"], "D3": have["D3"] + MODULE["D3"],
             "D2": have["D2"] + d2_new + MODULE["D2"]}
    target = (min(total.values()) + max(total.values())) / 2  # CLK (and D1) at the middle of the data lanes
    plan["D2"] = d2
    for k in ("CLK", "D1"):
        plan[k] = solve(k, target - MODULE[k] - have[k])
    adds = []
    for k, heights in plan.items():
        pts, hws = lane(k, heights)
        layer = pcbnew.B_Cu if k == "D2" else pcbnew.F_Cu
        for side, pol in ((+1, "P"), (-1, "N")):
            line = offset(pts, hws, side)
            segs = list(zip(line, line[1:]))
            if k == "D2":
                segs += [((52.7, 32.25), (53.1, 32.25))] if pol == "P" else [((55.8, 32.05), (56.2, 32.05))]
            adds.append((k, pol, layer, segs))
        print(f"{k}: bumps {heights}, new centreline {mean_len(k, heights):.2f} mm")
    # clearance check against everything except the lane's own two nets
    bad = 0
    for k, pol, layer, segs in adds:
        own = {f"CSI_{k}_P", f"CSI_{k}_N"}
        others = [o for o in H.obstacles(board, net(board, f"CSI_{k}_{pol}").GetNetCode())
                  if not own & set(o[5].split())]
        ly = layer
        new = [(ly, a, b, W / 2, 0) for a, b in segs]
        with contextlib.redirect_stdout(io.StringIO()) as f:
            n = H.problems(new, others)
        if n:
            bad += n
            print(f"  {k}_{pol}:", f.getvalue().strip().replace("\n", "\n    "))
    # P against N of the same lane: 0.1 mm gap in the run, 0.3 mm at the pads
    for k in plan:
        P = next(s for kk, pol, _, s in adds if kk == k and pol == "P")
        N = next(s for kk, pol, _, s in adds if kk == k and pol == "N")
        g = min(H.seg_dist(a, b, c, d) for a, b in P for c, d in N) - W
        if g < 0.099:
            bad += 1
            print(f"  {k}: P-N gap {g:.3f} mm")
    print(f"{bad} problems")
    if commit and not bad:
        gnd = net(board, "GND")
        for c in NEW_GND_VIAS:
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(vec(*c))
            v.SetWidth(pcbnew.FromMM(0.3))
            v.SetDrill(pcbnew.FromMM(0.15))
            v.SetNet(gnd)
            board.Add(v)
        for k, pol, layer, segs in adds:
            ni = net(board, f"CSI_{k}_{pol}")
            for a, b in segs:
                t = pcbnew.PCB_TRACK(board)
                t.SetLayer(layer)
                t.SetStart(vec(*a))
                t.SetEnd(vec(*b))
                t.SetWidth(pcbnew.FromMM(W))
                t.SetNet(ni)
                board.Add(t)
        return True
    return False


def tidy(board):
    """After the re-routes: the router dropped 5V_SYS to B.Cu through a via at (52.85, 35.8), whose In1 clearance hole
    reached under CLK_P (checks/returnpath.py). The via moves 0.95 mm west, clear of the lane."""
    ni = net(board, "5V_SYS")
    nc = ni.GetNetCode()
    seg = [t for t in board.GetTracks() if t.GetNetCode() == nc and t.GetClass() == "PCB_TRACK"
           and t.GetLayer() == pcbnew.F_Cu and {mm(t.GetStart()), mm(t.GetEnd())} == {(52.0, 35.8), (52.85, 35.8)}]
    via = [t for t in board.GetTracks() if t.GetNetCode() == nc and t.GetClass() == "PCB_VIA"
           and math.dist(mm(t.GetPosition()), (52.85, 35.8)) < 0.01]
    assert len(seg) == 1 and len(via) == 1, (len(seg), len(via))
    remove(board, seg + via)
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(vec(51.9, 35.7))
    v.SetWidth(pcbnew.FromMM(0.6))
    v.SetDrill(pcbnew.FromMM(0.3))
    v.SetNet(ni)
    board.Add(v)
    t = pcbnew.PCB_TRACK(board)
    t.SetLayer(pcbnew.B_Cu)
    t.SetStart(vec(51.9, 35.7))
    t.SetEnd(vec(52.85, 35.8))
    t.SetWidth(pcbnew.FromMM(0.6))
    t.SetNet(ni)
    board.Add(t)
    print("tidy: 5V_SYS via moved to (51.9, 35.7)")


def report(board):
    tot = {}
    for k in MODULE:
        p, n = carrier(board, f"CSI_{k}_P"), carrier(board, f"CSI_{k}_N")
        tot[k] = (p + n) / 2 + MODULE[k]
        print(f"{k:3s} carrier P {p:6.2f} N {n:6.2f} (P-N {p - n:+.2f})   module {MODULE[k]:5.2f}   "
              f"total {tot[k]:6.2f}")
    print("data-to-clock:", "  ".join(f"{k} {tot[k] - tot['CLK']:+.2f}" for k in ("D0", "D1", "D2", "D3")),
          f"  worst {max(abs(tot[k] - tot['CLK']) for k in ('D0', 'D1', 'D2', 'D3')):.2f} mm")


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    board = pcbnew.LoadBoard(ROUTED)
    if step == "clear":
        clear(board)
        pcbnew.SaveBoard(ROUTED, board)
    elif step == "add":
        if add(board, "--commit" in sys.argv):
            pcbnew.SaveBoard(ROUTED, board)
            print("saved")
    elif step == "tidy":
        tidy(board)
        pcbnew.SaveBoard(ROUTED, board)
    elif step == "report":
        report(board)
    else:
        sys.exit(__doc__)
