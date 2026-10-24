"""Merges the re-spaced, re-routed RK628D corner into the rev A board as it was before the re-spacing, and writes
the result to ../routed.kicad_pcb.

  .../bin/python3 gen/hybrid.py BEFORE.kicad_pcb RK.kicad_pcb

BEFORE is the board before gen/respace.py (everything routed except five RK628D nets), RK is a later checkpoint in
which the corner around the RK628D was re-spaced and routed again. Outside the corner's box nothing changes from
BEFORE (placement and copper), except that the RK628D's own nets (and its rails) come from RK wherever they fit;
inside the box everything comes from RK. Differential pairs are the same on both and stay as they are. The
connections that cross the box edge are joined afterwards by gen/autoroute.py stage gaps.
"""
import math
import os
import re
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from finish import ROUTED  # noqa: E402
from pcb import NETCLASSES, O, W, H  # noqa: E402
from router import Router  # noqa: E402

BOX = (12.0, 2.0, 54.0, 32.0)          # the RK628D corner, board mm
PAIR = re.compile("|".join(c[-1] for k, c in NETCLASSES.items() if k != "POWER"))
RAILS = re.compile(r"^(RK628D_3V3|1V1_628|AVDD_.*_628|HDMIRX_5V|XIN_628|XOUT_628)$")
GRAVE = []


def short(n):
    return n.split("/")[-1]


def mm(v):
    return pcbnew.ToMM(v.x) - O[0], pcbnew.ToMM(v.y) - O[1]


def ends(t):
    return (mm(t.GetPosition()),) if t.GetClass() == "PCB_VIA" else (mm(t.GetStart()), mm(t.GetEnd()))


def inside(p):
    return BOX[0] <= p[0] <= BOX[2] and BOX[1] <= p[1] <= BOX[3]


def main():
    board = pcbnew.LoadBoard(sys.argv[1])
    src = pcbnew.LoadBoard(sys.argv[2])
    rk = {p.GetNetCode() for p in board.FindFootprintByReference("U201").Pads()}
    rk |= {ni.GetNetCode() for nm, ni in board.GetNetsByName().items() if RAILS.match(short(str(nm)))}
    rkn = {short(board.FindNet(c).GetNetname()) for c in rk if c}

    # the CM3's CEC GPIO moved from J69 (J701) pin 28 to J68 (J702) pin 151 (gen/module.py)
    cec = board.FindNet("CEC_GPIO")
    old = board.FindFootprintByReference("J701").FindPadByNumber("28")
    if old.GetNetCode() == cec.GetNetCode():
        old.SetNetCode(0)
        board.FindFootprintByReference("J702").FindPadByNumber("51").SetNet(cec)
        doomed = [t for t in board.GetTracks() if t.GetNetCode() == cec.GetNetCode()]
        for t in doomed:
            board.Remove(t)
        GRAVE.extend(doomed)

    # out: the RK628D's nets everywhere, and everything but the pairs inside the box
    doomed = [t for t in board.GetTracks() if not PAIR.search(short(t.GetNetname())) and
              (t.GetNetCode() in rk or any(inside(p) for p in ends(t)))]
    for t in doomed:
        board.Remove(t)
    GRAVE.extend(doomed)
    print(f"{len(doomed)} items out")

    # the parts inside the box as they are in RK
    moved = 0
    for g in src.GetFootprints():
        if not inside(mm(g.GetPosition())):
            continue
        f = board.FindFootprintByReference(g.GetReference())
        if f.IsFlipped() != g.IsFlipped():
            f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        if f.GetPosition() != g.GetPosition() or f.GetOrientation() != g.GetOrientation():
            moved += 1
        f.SetPosition(g.GetPosition())
        f.SetOrientation(g.GetOrientation())
    print(f"{moved} parts placed as in RK")

    def copy(t):
        ni = board.FindNet(t.GetNetname())
        if t.GetClass() == "PCB_VIA":
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(t.GetPosition()); v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetWidth(t.GetWidth(pcbnew.F_Cu)); v.SetDrill(t.GetDrill())
        else:
            v = pcbnew.PCB_TRACK(board)
            v.SetStart(t.GetStart()); v.SetEnd(t.GetEnd()); v.SetWidth(t.GetWidth()); v.SetLayer(t.GetLayer())
        v.SetNet(ni)
        board.Add(v)

    # in: everything inside the box but the pairs (nothing else of BEFORE is left there)
    later = []
    n_in = 0
    for t in src.GetTracks():
        if PAIR.search(short(t.GetNetname())):
            continue
        if all(inside(p) for p in ends(t)):
            copy(t)
            n_in += 1
        elif short(t.GetNetname()) in rkn:
            later.append(t)
    print(f"{n_in} items copied inside the box")

    # in, where they fit: the RK628D's nets outside the box
    r = Router(board, O, (W, H), (0.0, 0.0, W, H), res=0.05, clearance=0.1)
    pw = NETCLASSES["POWER"][-1]
    for nm, ni in board.GetNetsByName().items():
        if re.search(pw, short(str(nm))):
            r.net_cl[ni.GetNetCode()] = 0.127
    layers = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
    grids = {}

    def free(nc, x, y, half, lys):
        key = (nc, round(half, 3), tuple(lys))
        if key not in grids:
            grids[key] = r.blocked(nc, half, lys).any(axis=0)
        i, j = int(round((x - r.x0) / r.res)), int(round((y - r.y0) / r.res))
        return 0 <= i < r.nx and 0 <= j < r.ny and not grids[key][j, i]
    n_out = skipped = 0
    for t in later:
        nc = board.FindNet(t.GetNetname()).GetNetCode()
        if t.GetClass() == "PCB_VIA":
            p = mm(t.GetPosition())
            ok = free(nc, p[0], p[1], pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2, layers)
        else:
            (x0, y0), (x1, y1) = ends(t)
            half = pcbnew.ToMM(t.GetWidth()) / 2
            n = max(2, int(math.hypot(x1 - x0, y1 - y0) / 0.025))
            ok = all(free(nc, x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n, half, [t.GetLayer()])
                     for k in range(n + 1))
        if ok:
            copy(t)
            n_out += 1
        else:
            skipped += 1
    print(f"RK628D nets outside the box: {n_out} items copied, {skipped} did not fit")
    pcbnew.SaveBoard(ROUTED, board)
    print("saved", ROUTED)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
