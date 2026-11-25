"""Adds the planes and the scripted high-speed routes to ../relay.kicad_pcb (run gen/pcb.py first).

Run with KiCad's bundled Python:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 gen/route.py

It removes every track, via and zone first, so it can be run again after any placement change. It saves the
routed board as ../routed.kicad_pcb, then runs gen/finish.py's steps (pours, fill) to write ../relay.kicad_pcb; for a
small change, script it against routed.kicad_pcb and run gen/finish.py alone. Routes are written as
centrelines in board millimetres (origin at the board's top-left corner, as in gen/pcb.py) and offset into the two
traces of each pair, so every coordinate below is one decision that can be checked against the pads.

Stackup: L1 signals, L2 (In1) GND, L3 (In2) GND for now (power islands come with the power routing), L4 signals.
All pairs here are on L1 over the L2 plane except two short CSI hops on L4 over L3.
"""
import math
import os
import sys

import numpy as np
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from pcb import NETCLASSES, O, W, H  # noqa: E402  (pcb.py only builds the board when run directly)
from pairs import length, offset, tune  # noqa: E402

BOARD = os.path.join(ROOT, "relay.kicad_pcb")
PAIR_W = NETCLASSES["DIFF_100R"][4]           # 0.10 mm traces
PAIR_HALF = (NETCLASSES["DIFF_100R"][4] + NETCLASSES["DIFF_100R"][5]) / 2  # centreline to trace: 0.10 mm
VIA_D, VIA_DRILL = 0.45, 0.25

board = pcbnew.LoadBoard(BOARD)


def mm(x, y):
    return pcbnew.VECTOR2I_MM(float(O[0] + x), float(O[1] + y))


def pad(ref, num):
    p = board.FindFootprintByReference(ref).FindPadByNumber(num)
    v = p.GetPosition()
    return pcbnew.ToMM(v.x) - O[0], pcbnew.ToMM(v.y) - O[1]


def net(name):
    """Nets by full name or by the last path element (sheet-local nets are '/Sheet name/NET')."""
    for n, item in board.GetNetsByName().items():
        n = str(n)
        if n == name or n.endswith("/" + name):
            return item
    raise SystemExit(f"no net {name}")


def track(netname, layer, pts, width=PAIR_W):
    ni = net(netname)
    out = []
    for a, b in zip(pts, pts[1:]):
        if math.dist(a, b) < 1e-4:
            continue
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(mm(*a)); t.SetEnd(mm(*b))
        t.SetWidth(pcbnew.FromMM(width))
        t.SetLayer(layer)
        t.SetNet(ni)
        board.Add(t)
        out.append(t)
    return out


def via(netname, at, size=(VIA_D, VIA_DRILL)):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(mm(*at))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetDrill(pcbnew.FromMM(size[1]))
    v.SetWidth(pcbnew.FromMM(size[0]))
    v.SetNet(net(netname))
    board.Add(v)
    return v



def pair(centre):
    """(left, right) trace polylines of a pair along a centreline. Every pair here runs with N on the left."""
    return offset(centre, -PAIR_HALF), offset(centre, PAIR_HALF)


LENGTHS = []


def routed(name, n_pts, p_pts):
    """Record one pair's two trace lengths (all segments, all layers) for the report."""
    LENGTHS.append((name, length(n_pts), length(p_pts)))


# ------------------------------------------------------------------ clear the previous run
for item in list(board.GetTracks()):
    board.Remove(item)
for z in list(board.Zones()):
    board.Remove(z)


# ------------------------------------------------------------------ length tuning
def match(n_pieces, p_pieces, seg):
    """Lengthens the shorter trace of a pair (on piece 0, segment `seg`) so N and P match. N is always on the left
    of travel, so its bumps go left and P's go right."""
    ln = sum(length(p) for p, _ in n_pieces)
    lp = sum(length(p) for p, _ in p_pieces)
    if abs(ln - lp) > 0.005:
        pieces, side = (n_pieces, -1) if ln < lp else (p_pieces, 1)
        pieces[0] = (tune(pieces[0][0], seg, abs(ln - lp), side), pieces[0][1])
    return n_pieces, p_pieces


def emit(name, n_net, p_net, n_pieces, p_pieces):
    for pts, layer in n_pieces:
        track(n_net, layer, pts)
    for pts, layer in p_pieces:
        track(p_net, layer, pts)
    routed(name, [q for p, _ in n_pieces for q in p], [q for p, _ in p_pieces for q in p])


# ------------------------------------------------------------------ CSI-2: RK628D (U201) to the CM3's J68 (J702)
# U201 is turned 180 degrees, so ball column 1 is the outer column on the right and rows run G (top) to C. Each lane
# has N on column 1 (straight out) and P on column 2, which leaves through the gap below its row's column-1 ball:
# 0.325 mm from both neighbours' centres, 0.1375 mm copper to copper with 0.1 mm traces.
#
# J702 (J68) has two pad rows 2.64 mm apart. D0, D1 and CLK land on the south row; they leave the RK628D eastwards,
# turn south past the connector's west end and come up into their pads from the south (the "wrap"). D2 and D3 land
# on the north row and are reached from between the rows (the gap under the connector body), so that P and N meet
# their pads without crossing: they hop under the wrap on L4 (two vias at each end).
#
# Every leg is horizontal, vertical or 45 degrees. A 45-degree leg is x - y = k; neighbouring pairs keep 0.65 mm
# between centrelines on those legs (k differs by 0.65 * sqrt 2) and spread to 1.0 mm on the runs south, which
# leaves room for the length-matching bumps.
CSI = [  # lane, ball row, J702 N pad, P pad
    ("D0", "G", "15", "17"), ("D1", "F", "21", "23"), ("CLK", "E", "27", "29"),
    ("D2", "D", "28", "30"), ("D3", "C", "34", "36"),
]
x1 = pad("U201", "G1")[0]        # column 1 (N)
x2 = pad("U201", "G2")[0]        # column 2 (P)
rows = {r: pad("U201", r + "1")[1] for _, r, *_ in CSI}
pitch = rows["F"] - rows["G"]
assert abs(pitch - 0.65) < 1e-3 and x1 > x2, (pitch, x1, x2)
X_E = x1 + 0.6                   # end of the straight N stub, clear of the ball
X_S = X_E + 0.0625               # where the pair settles to 0.2 mm centres
cG = rows["G"] + 0.1625          # D0's centreline (half way between its N stub and its P stub)
R2 = math.sqrt(2)
K0 = 51.0 - cG                   # D0's diagonal leg: x - y = K0, starting at x = 51
X_V = 55.5                       # D0's run south, west of the connector; D1 and CLK 1.0 mm further west
LANE0 = 36.3                     # D0's run east, below the south pad row (the USB/PERST vias fit above it)
M0 = X_V - (LANE0 - 0.8)         # D0's corner from south to east: x - y = M0


def exit_stubs(row):
    """Ball-to-pair stubs: N straight out of column 1, P through the gap below the column-1 ball."""
    y = rows[row]
    n = [pad("U201", row + "1"), (X_E, y), (X_S, y + 0.0625)]
    p = [pad("U201", row + "2"), (x2 + 0.325, y + 0.325), (X_E, y + 0.325), (X_S, y + 0.2625)]
    return n, p


for i, (lane, row, npad, ppad) in enumerate(CSI[:3]):
    c = cG + 0.65 * i
    k = K0 - 0.65 * i * R2
    xv = X_V - 1.0 * i
    m = M0 - 0.65 * i * R2
    ln = LANE0 + 0.8 * i
    centre = [(X_S, c), (k + c, c), (xv, xv - k), (xv, xv - m), (ln + m, ln), (70.0, ln)]
    left, right = pair(centre)
    xn, yn = pad("J702", npad)
    xp, yp = pad("J702", ppad)
    # into the pads from the south: N (left, north side of the lane) turns up first, at the western pad
    left = left[:-1] + [(xn - 0.3, left[-1][1]), (xn, left[-1][1] - 0.3), (xn, yn)]
    right = right[:-1] + [(xp - 0.3, right[-1][1]), (xp, right[-1][1] - 0.3), (xp, yp)]
    sn, sp = exit_stubs(row)
    n_pieces, p_pieces = match([(sn + left[1:], pcbnew.F_Cu)], [(sp + right[1:], pcbnew.F_Cu)], seg=4)
    emit(f"CSI_{lane}", f"CSI_{lane}_N", f"CSI_{lane}_P", n_pieces, p_pieces)

# D2 and D3: their diagonal legs sit 1.3 and 2.1 mm outside CLK's, and their runs south end in a pair of vias side by
# side (N east, P west, 0.6 mm apart); on L4 they run east under the wrap to a second pair of vias, one above the
# other, at the channel entrance; then on L1 between J702's pad rows to the north-row pads' south ends.
HOPS = {
    #      diag offset  run-south x  vias y (west)  L4 N lane y  channel vias x  L1 channel lanes (N, P)
    "D2": (2.6, 52.4, 31.65, 32.05, 56.2, (32.45, 32.65)),
    "D3": (3.4, 50.9, 32.70, 33.10, 56.9, (33.10, 33.30)),
}
for lane, row, npad, ppad in CSI[3:]:
    off, xv, yv, lane_n, xc, (fn, fp) = HOPS[lane]
    c = rows[row] + 0.1625
    k = K0 - off * R2
    assert k + c > X_S + 0.2, lane
    left, right = pair([(X_S, c), (k + c, c), (xv, xv - k), (xv, yv - 0.4)])
    sn, sp = exit_stubs(row)
    nf = sn + left[1:] + [(xv + 0.3, yv - 0.2), (xv + 0.3, yv)]
    pf = sp + right[1:] + [(xv - 0.3, yv - 0.2), (xv - 0.3, yv)]
    nb = [(xv + 0.3, yv), (xv + 0.3 + (lane_n - yv), lane_n), (xc, lane_n)]
    pb = [(xv - 0.3, yv), (xv - 0.3 + (lane_n + 0.2 - yv), lane_n + 0.2), (xc - 0.4, lane_n + 0.2), (xc, lane_n + 0.6)]
    xn, yn = pad("J702", npad)
    xp, yp = pad("J702", ppad)
    nc = [(xc, lane_n)] + ([(xc + fn - lane_n, fn)] if fn != lane_n else []) + [(xn, fn), (xn, yn)]
    pc = [(xc, lane_n + 0.6), (xc + (lane_n + 0.6 - fp), fp), (xp, fp), (xp, yp)]
    for v in ((xv + 0.3, yv), (xc, lane_n)):
        via(f"CSI_{lane}_N", v)
    for v in ((xv - 0.3, yv), (xc, lane_n + 0.6)):
        via(f"CSI_{lane}_P", v)
    n_pieces, p_pieces = match([(nf, pcbnew.F_Cu), (nb, pcbnew.B_Cu), (nc, pcbnew.F_Cu)],
                               [(pf, pcbnew.F_Cu), (pb, pcbnew.B_Cu), (pc, pcbnew.F_Cu)], seg=4)
    emit(f"CSI_{lane}", f"CSI_{lane}_N", f"CSI_{lane}_P", n_pieces, p_pieces)

# MIPI_REXT (ball B1, column 1 under D3): straight out, then south to R205
bx, by = pad("U201", "B1")
r205 = [p for p in board.FindFootprintByReference("R205").Pads() if "MIPI_REXT" in p.GetNetname()][0]
rx, ry = pcbnew.ToMM(r205.GetPosition().x) - O[0], pcbnew.ToMM(r205.GetPosition().y) - O[1]
track("MIPI_REXT", pcbnew.F_Cu, [(bx, by), (rx, by), (rx, ry)], 0.127)


# ------------------------------------------------------------------ HDMI IN: J201 through D201/D202 to U201
# The connector's pairs leave southwards 1.5 mm apart (P west), pass straight through the flow-through ESD parts
# (lines 0.5 mm apart there), turn east and meet the RK628D's left side. There P is on column 12 (outer, straight
# in) and N on column 11, reached through the gap above its row's column-12 ball.
HDMI = [  # lane, P pin, N pin, ESD part, ESD P pin, ESD N pin, ball row
    ("D2", "1", "3", "D201", "1", "2", "H"), ("D1", "4", "6", "D201", "4", "5", "J"),
    ("D0", "7", "9", "D202", "1", "2", "K"), ("CLK", "10", "12", "D202", "4", "5", "L"),
]
c12 = pad("U201", "L12")[0]
c11 = pad("U201", "L11")[0]
assert c12 < c11
X_F = c12 - 0.8                   # where each pair splits for the balls
Y_ESD_OUT = 14.0                  # below the ESD parts, where pairs settle to 0.2 mm centres
for lane, pp, pn, esd, ep, en, row in HDMI:
    jp, jn = pad("J201", pp), pad("J201", pn)
    ep1, en1 = pad(esd, ep), pad(esd, en)
    ep2 = pad(esd, {"1": "10", "4": "7"}[ep])          # the other end of each flow-through line
    en2 = pad(esd, {"2": "9", "5": "6"}[en])
    assert abs(ep1[0] - ep2[0]) < 1e-3 and abs(en1[0] - en2[0]) < 1e-3 and ep1[0] < en1[0], (lane, ep1, en1)
    xc = (ep1[0] + en1[0]) / 2
    yr = pad("U201", row + "12")[1]
    yc = yr - 0.1625
    d = 1.0
    left, right = pair([(xc, Y_ESD_OUT + 0.15), (xc, yc - d), (xc + d, yc), (X_F, yc)])  # heading south, N east
    top = min(ep1[1], ep2[1]) - 0.4
    n_pts = [jn, (jn[0], top - abs(jn[0] - en1[0])), (en1[0], top), (en1[0], Y_ESD_OUT)] + left
    p_pts = [jp, (jp[0], top - abs(jp[0] - ep1[0])), (ep1[0], top), (ep1[0], Y_ESD_OUT)] + right
    n_pts += [(X_F + 0.0625, yr - 0.325), (c11 - 0.325, yr - 0.325), pad("U201", row + "11")]
    p_pts += [(X_F + 0.0625, yr), pad("U201", row + "12")]
    n_pieces, p_pieces = match([(n_pts, pcbnew.F_Cu)], [(p_pts, pcbnew.F_Cu)], seg=4)
    emit(f"HDMIRX_{lane}", f"HDMIRX_{lane}_N", f"HDMIRX_{lane}_P", n_pieces, p_pieces)


# ------------------------------------------------------------------ RK628D: fanout, decoupling and power
# The ball grid has 0.65 mm pitch. A 0.3 mm via (0.15 mm drill) fits at the centre of four balls with 0.17 mm to
# each and leaves 0.35 mm between neighbouring vias for a 0.1 mm trace, so every power and GND ball gets a "dogbone": a 0.15 mm stub on L1 to its own via. Inner signal balls get a
# site reserved for their via (they are routed later). The decoupling capacitors and the two ferrites go on the
# back, under and around the chip, and gen/router.py joins each rail's vias, capacitors and feeds.
from router import Router  # noqa: E402

POWER = ("AVDD_1V1_628", "AVDD_3V3_628", "RK628D_3V3", "1V1_628")
FAN_VIA = (0.30, 0.15)
ROWS = "ABCDEFGHJKLM"
u201 = board.FindFootprintByReference("U201")
balls = {p.GetNumber(): p for p in u201.Pads()}
bpos = {n: pad("U201", n) for n in balls}


def short(name):
    return name.split("/")[-1]


def ring(num):
    r, c = ROWS.index(num[0]), int(num[1:]) - 1
    return min(r, 11 - r, c, 11 - c)


bx_min = min(p[0] for p in bpos.values()); bx_max = max(p[0] for p in bpos.values())
by_min = min(p[1] for p in bpos.values()); by_max = max(p[1] for p in bpos.values())
BGA_C = ((bx_min + bx_max) / 2, (by_min + by_max) / 2)
existing = [(pcbnew.ToMM(t.GetStart().x) - O[0], pcbnew.ToMM(t.GetStart().y) - O[1],
             pcbnew.ToMM(t.GetEnd().x) - O[0], pcbnew.ToMM(t.GetEnd().y) - O[1], pcbnew.ToMM(t.GetWidth()))
            for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]


def seg_dist(px, py, x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    L = dx * dx + dy * dy
    f = 0 if L == 0 else max(0, min(1, ((px - x0) * dx + (py - y0) * dy) / L))
    return math.hypot(px - x0 - f * dx, py - y0 - f * dy)


def site_free(x, y):
    """A fanout via fits here: inside the ball field and clear of the escape traces already drawn."""
    if not (bx_min < x < bx_max and by_min < y < by_max):
        return False
    return all(seg_dist(x, y, *s[:4]) >= FAN_VIA[0] / 2 + s[4] / 2 + 0.1 for s in existing)


need = {}  # ball -> kind
for n, p in balls.items():
    net_ = short(p.GetNetname())
    if net_.startswith("unconnected") or n == "B1":
        continue
    if net_ in POWER:
        need[n] = "power"
    elif net_ == "GND":
        need[n] = "gnd"
    elif ring(n) >= 2:
        need[n] = "signal"


def candidates(n):
    x, y = bpos[n]
    out = [(round(x + dx, 4), round(y + dy, 4)) for dx in (-0.325, 0.325) for dy in (-0.325, 0.325)]
    out = [s for s in out if site_free(*s)]
    if need[n] == "signal":   # signals: the site on the outside, towards the edge they will leave by
        out.sort(key=lambda s: -math.dist(s, BGA_C))
    return out


taken = {}
order = sorted(need, key=lambda n: (len(candidates(n)), {"signal": 0, "power": 1, "gnd": 2}[need[n]]))
for n in order:
    free = [s for s in candidates(n) if s not in taken]
    if free:
        taken[free[0]] = n


# Under the field, a trace on the back or L3 can only travel diagonally: site to the spot under a ball and on to
# another of that ball's four sites (between two vias in a row there is no room for 0.2 mm hole clearance). So a
# power via whose eight neighbouring sites all hold other nets' vias is walled in. Move GND vias out of the way
# until every power via has a free path to the edge of the field.
def neighbours(s):
    return [(round(s[0] + dx, 4), round(s[1] + dy, 4)) for dx in (-0.65, 0, 0.65) for dy in (-0.65, 0, 0.65)
            if dx or dy]


def all_sites():
    return {(round(bpos[n][0] + dx, 4), round(bpos[n][1] + dy, 4)) for n in bpos
            for dx in (-0.325, 0.325) for dy in (-0.325, 0.325) if bx_min < bpos[n][0] + dx < bx_max
            and by_min < bpos[n][1] + dy < by_max}


SITES = all_sites()


def escapes(start, netname):
    seen, todo = {start}, [start]
    while todo:
        s = todo.pop()
        for t in neighbours(s):
            if t not in SITES:
                return True                       # off the field: free copper outside
            if t in seen:
                continue
            owner = taken.get(t)
            if owner is None or short(balls[owner].GetNetname()) == netname:
                seen.add(t)
                todo.append(t)
    return False


for _ in range(40):
    walled = [s for s, n in taken.items() if need[n] == "power" and not escapes(s, short(balls[n].GetNetname()))]
    if not walled:
        break
    s0 = walled[0]
    moved = False
    for t in neighbours(s0):
        n = taken.get(t)
        if n is None or need[n] != "gnd":
            continue
        for alt in candidates(n):
            if alt in taken:
                continue
            del taken[t]
            taken[alt] = n
            if escapes(s0, short(balls[taken[s0]].GetNetname())):
                moved = True
                break
            del taken[alt]
            taken[t] = n
        if moved:
            break
    if not moved:   # no other site for any neighbouring GND ball: give one up (its neighbours carry it on L1)
        t = next(t for t in neighbours(s0) if taken.get(t) and need[taken[t]] == "gnd")
        del taken[t]
site_of = {n: s for s, n in taken.items()}
RESERVED_SIGNAL_SITES = {n: s for n, s in site_of.items() if need[n] == "signal"}

fan_vias = {}
signal_vias = {}
for n, site in RESERVED_SIGNAL_SITES.items():
    nm = short(balls[n].GetNetname())
    signal_vias[nm] = via(nm, site, FAN_VIA)
    track(nm, pcbnew.F_Cu, [bpos[n], site], 0.1)
for n, s in site_of.items():
    if need[n] == "signal":
        continue
    netname = short(balls[n].GetNetname())
    fan_vias.setdefault(netname, []).append(via(netname, s, FAN_VIA))
    track(netname, pcbnew.F_Cu, [bpos[n], s], 0.15)
# Neighbouring balls on the same rail (J4-J7, J9-H9, F3-E3, F8-E8) are also tied on L1 along the row line, 0.09 mm
# wide: 0.13 mm from the vias either side and 0.205 mm from their holes. Fewer separate pieces for the back and L3
# to join.
for n, p in balls.items():
    if need.get(n) != "power":
        continue
    r, c = ROWS.index(n[0]), int(n[1:])
    for rr, cc in ((r, c + 1), (r + 1, c)):
        m = f"{ROWS[rr]}{cc}" if rr < 12 and cc <= 12 else None
        if m in balls and short(balls[m].GetNetname()) == short(p.GetNetname()):
            track(short(p.GetNetname()), pcbnew.F_Cu, [bpos[n], bpos[m]], 0.09)
# GND balls left without a site: tie on L1 to a neighbouring GND ball that has one (0.1 mm, on the row line, so it
# keeps 0.1 mm from the vias either side)
no_site = [n for n in need if n not in site_of and need[n] != "signal"]
for n in list(no_site):
    r, c = ROWS.index(n[0]), int(n[1:])
    for rr, cc in ((r, c - 1), (r, c + 1), (r - 1, c), (r + 1, c)):
        if 0 <= rr < 12 and 1 <= cc <= 12:
            m = f"{ROWS[rr]}{cc}"
            if m in site_of and short(balls[m].GetNetname()) == short(balls[n].GetNetname()):
                track(short(balls[n].GetNetname()), pcbnew.F_Cu, [bpos[n], bpos[m]], 0.1)
                no_site.remove(n)
                break

# ---- capacitors and ferrites to the back
R = Router(board, O, (W, H), (14.0, 0.0, 66.0, 45.0), clearance=0.13)
RF = Router(board, O, (W, H), (35.0, 11.0, 55.0, 30.0), res=0.025, clearance=0.1)
R.peers, RF.peers = [RF], [R]


def two_pad(fp):
    return len(fp.Pads()) == 2


caps = {nm: [] for nm in POWER}
for fp in board.GetFootprints():
    ref = fp.GetReference()
    nets_ = {short(p.GetNetname()) for p in fp.Pads()}
    if ref.startswith("C2") and len(nets_) == 2 and "GND" in nets_ and (nets_ - {"GND"}) <= set(POWER):
        caps[(nets_ - {"GND"}).pop()].append(fp)
ferrites = [board.FindFootprintByReference(r) for r in ("FB201", "FB202")]


def value_rank(fp):
    v = fp.GetValue()
    return 0 if v.startswith("100n") else 1 if v.startswith("1u") else 2


back = []  # (x0, y0, x1, y1) courtyards already on the back
for fp in [f for nm in POWER for f in caps[nm]] + ferrites:
    if not fp.IsFlipped():
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)


def via_xy(v):
    return pcbnew.ToMM(v.GetPosition().x) - O[0], pcbnew.ToMM(v.GetPosition().y) - O[1]


def local_pads(fp):
    """Pad offsets (dx, dy, half w, half h, net) at orientation 0."""
    fp.SetOrientationDegrees(0)
    c = fp.GetPosition()
    out = []
    for p in fp.Pads():
        q = p.GetPosition()
        bb = p.GetBoundingBox()
        out.append((pcbnew.ToMM(q.x - c.x), pcbnew.ToMM(q.y - c.y), pcbnew.ToMM(bb.GetWidth()) / 2,
                    pcbnew.ToMM(bb.GetHeight()) / 2, short(p.GetNetname())))
    return out


def integral(a):
    s = np.zeros((a.shape[0] + 1, a.shape[1] + 1), np.int32)
    s[1:, 1:] = np.cumsum(np.cumsum(a, 0), 1)
    return s


def rect_clear(S, x0, y0, x1, y1):
    i0 = int(math.floor((x0 - R.x0) / R.res)); i1 = int(math.ceil((x1 - R.x0) / R.res))
    j0 = int(math.floor((y0 - R.y0) / R.res)); j1 = int(math.ceil((y1 - R.y0) / R.res))
    if i0 < 0 or j0 < 0 or i1 >= R.nx or j1 >= R.ny:
        return False
    return S[j1 + 1, i1 + 1] - S[j0, i1 + 1] - S[j1 + 1, i0] + S[j0, i0] == 0


# ---- the RK628D's support parts on the front, each next to what it connects to
# gen/pcb.py packs them by size only; here they are re-placed one by one, each as close as possible to the copper
# it connects to (a ball, a connector pin or a part placed before it), in an order that starts at the chip.
SUPPORT_ORDER = [
    # on a ball: crystal, DDC/CEC/HPD series resistors, EXTR and EFUSE resistors, I2C address and pull-ups,
    # reset capacitor, I2S test points
    "Y201", "R219", "R220", "R215", "R213", "R204", "R203", "R206", "C201", "R201", "R202", "R207", "R208",
    "C202", "TP201", "TP202", "TP203", "TP204",
    # one step further: crystal load caps, DDC/CEC pull-ups and their diodes, HDMI port ESD and 5 V detect,
    # the RK628D power switch
    "C203", "C204", "R217", "R218", "D205", "R214", "D204", "R216", "D203", "C235", "R221", "R222", "Q203", "R223",
    "Q201", "R209", "R210", "Q202", "R211", "R212", "C205",
]
OVERRIDE = {  # parts that belong at the connector rather than half way to the chip
    "D203": {"PORT_HPD": "J201.19", "PORT_CEC": "J201.13", "PORT_SCL": "J201.15", "PORT_SDA": "J201.16"},
    "C235": {"HDMIRX_5V": "J201.18"},
    "C205": {"3V3_IO": "Q201.2"},     # the P-FET's input capacitor, at its source
}
KEEPOUT = [(35.4, 29.7, 96.6, 70.3),   # under the Radxa CM3 (1.5 mm stack height): nothing on the front
           (38.0, 15.0, 50.0, 27.0)]   # a 1.5 mm ring around the RK628D, left free for the balls' escape traces
LIFT = (200.0, 200.0)
for r in SUPPORT_ORDER:
    board.FindFootprintByReference(r).SetPosition(mm(*LIFT))
R.changed()


def front_rects(skip=None):
    out = list(KEEPOUT)
    for fp in board.GetFootprints():
        if fp.GetReference() == skip or fp.IsFlipped():
            continue
        x, y = via_xy(fp)
        if x > 150:
            continue
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        if cy.OutlineCount():
            bb = cy.BBox()
            out.append((pcbnew.ToMM(bb.GetLeft()) - O[0], pcbnew.ToMM(bb.GetTop()) - O[1],
                        pcbnew.ToMM(bb.GetRight()) - O[0], pcbnew.ToMM(bb.GetBottom()) - O[1]))
    return out


def net_target(nm, skip):
    """Centre of the net's pads on parts already in place. The module connectors don't count: those nets run off
    to the CM3 anyway, and the part belongs with the chip."""
    pts = [via_xy(p) for fp in board.GetFootprints() if fp.GetReference() != skip and not fp.IsFlipped()
           and not fp.GetReference().startswith("J70") and via_xy(fp)[0] < 150
           for p in fp.Pads() if short(p.GetNetname()) == nm]
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)) if pts else None


def place_front(fp, span=4.0):
    ref = fp.GetReference()
    lp = local_pads(fp)
    targets = {}
    for *_, nm in lp:
        if ref in OVERRIDE and nm in OVERRIDE[ref]:
            r_, n_ = OVERRIDE[ref][nm].split(".")
            targets[nm] = pad(r_, n_)
        elif nm in ("GND", "", "3V3_IO") or nm.startswith("unconnected"):
            continue
        else:
            t = net_target(nm, ref)
            if t:
                targets[nm] = t
    if not targets:
        targets = {"": BGA_C}
    cx0 = sum(t[0] for t in targets.values()) / len(targets)
    cy0 = sum(t[1] for t in targets.values()) / len(targets)
    sums = {}
    for *_, nm in lp:
        if nm not in sums:
            sums[nm] = integral(R.blocked(net(nm).GetNetCode() if nm else 0, 0.0, [pcbnew.F_Cu])[0])
    rects = front_rects(skip=ref)
    best = None
    for rot in (0, 90, 180, 270):
        fp.SetPosition(mm(0, 0))
        fp.SetOrientationDegrees(rot)
        cy = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        cbox = (pcbnew.ToMM(cy.GetLeft()) - O[0], pcbnew.ToMM(cy.GetTop()) - O[1],
                pcbnew.ToMM(cy.GetRight()) - O[0], pcbnew.ToMM(cy.GetBottom()) - O[1])
        cs, sn = round(math.cos(math.radians(rot))), round(math.sin(math.radians(rot)))
        pads_r = [(dx * cs + dy * sn, -dx * sn + dy * cs, (hw if rot in (0, 180) else hh),
                   (hh if rot in (0, 180) else hw), nm) for dx, dy, hw, hh, nm in lp]
        for gy in np.arange(-span, span + 0.01, 0.1):
            for gx in np.arange(-span, span + 0.01, 0.1):
                x, y = round(cx0 + gx, 2), round(cy0 + gy, 2)
                cost = sum(math.dist((x + p[0], y + p[1]), targets[p[4]]) for p in pads_r if p[4] in targets)
                if best and cost >= best[0]:
                    continue
                c = (x + cbox[0], y + cbox[1], x + cbox[2], y + cbox[3])
                if c[0] < 0.5 or c[1] < 0.5 or c[2] > W - 0.5 or c[3] > H - 0.5:
                    continue
                if any(not (c[2] <= b[0] or c[0] >= b[2] or c[3] <= b[1] or c[1] >= b[3]) for b in rects):
                    continue
                if all(rect_clear(sums[p[4]], x + p[0] - p[2], y + p[1] - p[3], x + p[0] + p[2], y + p[1] + p[3])
                       for p in pads_r):
                    best = (cost, x, y, rot)
    if best is None:
        fp.SetPosition(mm(*LIFT))
        if span < 12:
            return place_front(fp, span + 4)
        raise SystemExit(f"no room on the front for {ref}")
    fp.SetOrientationDegrees(best[3])
    fp.SetPosition(mm(best[1], best[2]))
    R.changed()
    if os.environ.get("ROUTE_STOP"):
        print(ref, "targets", {k: (round(v[0], 1), round(v[1], 1)) for k, v in targets.items()}, "->", best, span)


for r in SUPPORT_ORDER:
    place_front(board.FindFootprintByReference(r))
if os.environ.get("ROUTE_STOP") == "front":   # quick look at the placement without the slow routing
    pcbnew.SaveBoard(BOARD, board)
    raise SystemExit("stopped after front placement")


def place_back(fp, targets, accept, span=3.0):
    """Puts a two-pad part on the back where its pads are clear of other nets' copper and its courtyard clear of
    the parts already there, as close as possible to targets[net] for each pad's net, at the first such spot where
    accept(fp) (a trial routing) succeeds."""
    lp = local_pads(fp)
    sums = {}
    for _, _, _, _, nm in lp:
        if nm not in sums:
            sums[nm] = integral(R.blocked(net(nm).GetNetCode(), 0.0, [pcbnew.B_Cu])[0])
    tx = [targets[nm] for *_, nm in lp if nm in targets]
    cx0 = sum(t[0] for t in tx) / len(tx); cy0 = sum(t[1] for t in tx) / len(tx)
    spots = []
    for rot in (0, 90, 180, 270):
        cs, sn = round(math.cos(math.radians(rot))), round(math.sin(math.radians(rot)))
        pads_r = [(dx * cs + dy * sn, -dx * sn + dy * cs, (hw if rot in (0, 180) else hh),
                   (hh if rot in (0, 180) else hw), nm) for dx, dy, hw, hh, nm in lp]
        ext_x = max(abs(p[0]) + p[2] for p in pads_r) + 0.25
        ext_y = max(abs(p[1]) + p[3] for p in pads_r) + 0.25
        for gy in np.arange(-span, span + 0.01, 0.1):
            for gx in np.arange(-span, span + 0.01, 0.1):
                x, y = cx0 + gx, cy0 + gy
                if any(not (x + ext_x <= b[0] or x - ext_x >= b[2] or y + ext_y <= b[1] or y - ext_y >= b[3])
                       for b in back):
                    continue
                if all(rect_clear(sums[p[4]], x + p[0] - p[2], y + p[1] - p[3], x + p[0] + p[2], y + p[1] + p[3])
                       for p in pads_r):
                    cost = sum(math.dist((x + p[0], y + p[1]), targets[p[4]]) * (1.0 if p[4] != "GND" else 0.3)
                               for p in pads_r if p[4] in targets)
                    spots.append((cost, x, y, rot, ext_x, ext_y))
    spots.sort()
    if not spots and span < 8:
        return place_back(fp, targets, accept, span + 2.5)
    if not spots:
        raise SystemExit(f"no room on the back for {fp.GetReference()}")
    tried = []
    for cost, x, y, rot, ex_, ey_ in spots:
        if any(math.dist((x, y), t) < 0.4 for t in tried):
            continue
        tried.append((x, y))
        if len(tried) > 12:
            break
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(mm(x, y))
        R.changed()
        if accept(fp):
            back.append((x - ex_, y - ey_, x + ex_, y + ey_))
            return True
    # no trial routing worked: take the best spot and leave its pads to the final rail pass (reported if open)
    cost, x, y, rot, ex_, ey_ = spots[0]
    fp.SetOrientationDegrees(rot)
    fp.SetPosition(mm(x, y))
    back.append((x - ex_, y - ey_, x + ex_, y + ey_))
    R.changed()
    print(f"  {fp.GetReference()}: placed, but its trial routing failed")
    return False


def gnd_via_near(p, max_r=1.6):
    """A GND via beside a GND pad, joined to it by a short trace on the pad's layer. Returns the new items."""
    x, y = pcbnew.ToMM(p.GetPosition().x) - O[0], pcbnew.ToMM(p.GetPosition().y) - O[1]
    layer = pcbnew.B_Cu if p.IsOnLayer(pcbnew.B_Cu) and not p.IsOnLayer(pcbnew.F_Cu) else pcbnew.F_Cu
    gc = net("GND").GetNetCode()
    vb = R.blocked(gc, 0.225, [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]).any(axis=0)
    tb = R.blocked(gc, 0.125, [layer])[0]
    vias_now = [via_xy(v) for v in board.GetTracks() if v.GetClass() == "PCB_VIA"]
    for rad in np.arange(0.5, max_r, 0.1):
        for a in range(0, 360, 15):
            vx, vy = x + rad * math.cos(math.radians(a)), y + rad * math.sin(math.radians(a))
            i, j = int(round((vx - R.x0) / R.res)), int(round((vy - R.y0) / R.res))
            if not (0 <= i < R.nx and 0 <= j < R.ny) or vb[j, i]:
                continue
            if any(math.dist((vx, vy), v) < 0.65 for v in vias_now):
                continue   # hole to hole
            steps = max(2, int(rad / R.res))
            if all(not tb[int(round((y + (vy - y) * t / steps - R.y0) / R.res)),
                           int(round((x + (vx - x) * t / steps - R.x0) / R.res))]
                   or math.dist((x + (vx - x) * t / steps, y + (vy - y) * t / steps), (x, y)) < 0.35
                   for t in range(steps + 1)):
                items = [via("GND", (vx, vy))] + track("GND", layer, [(x, y), (vx, vy)], 0.25)
                R.changed()
                return items
    return None


def undo(items):
    for it in items:
        board.Remove(it)
    R.changed()


def net_items(netname):
    nc = net(netname).GetNetCode()
    return [t for t in board.GetTracks() if t.GetNetCode() == nc]


def join_part(fp, gnd_ok=True):
    """Trial routing for a part on the back: each non-GND pad to its rail's copper (back or L3), the GND pad to a
    GND fanout via on the back or a GND via of its own. Keeps the routes if all succeed, else removes them."""
    made = []
    start = (len(RF.log), len(R.log))
    ok = True
    for p in fp.Pads():
        nm = short(p.GetNetname())
        if nm == "GND":
            left = RF.connect(net("GND").GetNetname(), [p, list(fan_vias.get("GND", []))], 0.15,
                              layers=[pcbnew.B_Cu], window=1.5, max_expand=60000)
            if left:
                extra = gnd_via_near(p)
                if extra is None:
                    ok = False
                    break
                made += extra
        else:
            copper = net_items(nm)
            if not copper:
                continue      # the first part of a rail with no copper yet: the rail routing joins it
            if RF.connect(net(nm).GetNetname(), [p, copper], 0.1, layers=[pcbnew.B_Cu, pcbnew.In2_Cu],
                          via=FAN_VIA, window=2.5, max_expand=150000):
                ok = False
                break
    if not ok:
        undo(made + RF.log[start[0]:] + R.log[start[1]:])
        del RF.log[start[0]:], R.log[start[1]:]
    return ok


# ---- rails first, while the back and L3 are still empty: each rail's fanout vias joined (0.1 mm, diagonally
# between the vias) and led out to an exit via just outside the ball field, on the side its feed comes from. The
# capacitors and feeds then join a rail at any of its copper, and no rail can be walled in by the others.
def free_via_spot(netname, near, size=(VIA_D, VIA_DRILL)):
    nc = net(netname).GetNetCode()
    vb = R.blocked(nc, max(size[0] / 2, size[1] / 2 + 0.07), [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu,
                                                            pcbnew.B_Cu]).any(axis=0)
    vias_now = [via_xy(v) for v in board.GetTracks() if v.GetClass() == "PCB_VIA"]
    for rad in np.arange(0, 2.0, 0.05):
        for a in range(0, 360, 10):
            x, y = near[0] + rad * math.cos(math.radians(a)), near[1] + rad * math.sin(math.radians(a))
            i, j = int(round((x - R.x0) / R.res)), int(round((y - R.y0) / R.res))
            if 0 <= i < R.nx and 0 <= j < R.ny and not vb[j, i] and \
                    all(math.dist((x, y), v) >= size[1] + 0.25 for v in vias_now):
                return x, y
    raise SystemExit(f"no exit via spot for {netname} near {near}")


unrouted = []
RAIL_ORDER = ("RK628D_3V3", "AVDD_3V3_628", "1V1_628", "AVDD_1V1_628")
EXITS = {  # north edge for the rails fed from the ferrites and the P-FET above; south-west for the 1V1 converter
    "AVDD_1V1_628": (41.0, by_min - 1.0), "RK628D_3V3": (43.2, by_min - 1.0),
    "AVDD_3V3_628": (45.4, by_min - 1.0), "1V1_628": (41.5, by_max + 1.3),
}
exit_vias = {}
for nm in RAIL_ORDER:
    exit_vias[nm] = via(nm, free_via_spot(nm, EXITS[nm]))
    R.changed()
    unrouted += [(nm, t) for t in RF.connect(net(nm).GetNetname(), list(fan_vias.get(nm, [])) + [exit_vias[nm]],
                                             0.1, layers=[pcbnew.In2_Cu, pcbnew.B_Cu], via=FAN_VIA)]

# ---- the RK628D's low-speed signals, before the capacitors take the back: ball (or its via) to its parts, parts
# to the CM3's J69 (J701)
# Short nets near the chip on the 0.05 mm grid; the ones that run down to the module connector on a board-wide one.
RL = Router(board, O, (W, H), (12.0, 0.0, 100.0, 75.0), clearance=0.13)
R.peers, RF.peers, RL.peers = [RF, RL], [R, RL], [R, RF]
SIGNALS = [
    # at the chip
    "XIN_628", "XOUT_628", "RX_SCL", "RX_SDA", "RX_CEC", "RX_HPD", "TX_EXTR", "RX_EXTR", "EFUSE_628",
    "RK628D_I2C_ADDR", "I2S_628_SCLK", "I2S_628_LRCK", "I2S_628_SDO", "I2S_628_MCLK",
    # between the parts and the HDMI port
    "PORT_SCL", "PORT_SDA", "PORT_CEC", "PORT_HPD", "DDC_PU", "CEC_PU", "DET_B", "PFET_G_628", "NPN_C_628",
    "NPN_B_628",
    # to the module
    "I2C_628_SCL", "I2C_628_SDA", "RK628D_INT", "RK628D_RESET_N", "CEC_GPIO", "RK628D_PWR_EN",
    "RK628D_PLUGIN_DET",
]
WIDE = {"HDMIRX_5V": 0.3, "3V3_IO": 0.4}


def signal_terms(nm):
    terms = [p for fp in board.GetFootprints() for p in fp.Pads() if short(p.GetNetname()) == nm
             and via_xy(fp)[0] < 150]
    if nm in signal_vias:     # inner balls: start from their via, the ball is already joined to it
        terms = [signal_vias[nm]] + [p for p in terms if p.GetParentFootprint().GetReference() != "U201"]
    if nm == "3V3_IO":        # only the RK628D end here; the trunk from the 3.3 V converter comes with the power
        terms = [p for p in terms if p.GetParentFootprint().GetReference() in ("Q201", "C205", "R209", "R223")]
    return terms


def is_far(t):
    return hasattr(t, "GetNumber") and t.GetParentFootprint().GetReference().startswith("J70")


def route_local(nm):
    """Everything of a signal net except its run to the module connector. Returns what it couldn't reach."""
    terms = [t for t in signal_terms(nm) if not is_far(t)]
    failed = []
    # the chip end first, on the 0.025 mm grid, where the gaps between balls and between vias fall on cell
    # centres (0.1 mm traces: 0.1375 mm to the balls either side)
    if any(not hasattr(t, "GetNumber") or t.GetParentFootprint().GetReference() == "U201" for t in terms):
        def inside(t):
            x, y = via_xy(t)
            return RF.x0 + 0.5 < x < RF.x1 - 0.5 and RF.y0 + 0.5 < y < RF.y1 - 0.5
        failed += RF.connect(net(nm).GetNetname(), [t for t in terms if inside(t)], 0.1,
                             layers=[pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu], via=FAN_VIA, window=4.0)
        rest = [t for t in terms if not inside(t)]
        terms = ([net_items(nm)] + rest) if net_items(nm) and rest else rest
    if len(terms) > 1:
        failed += R.connect(net(nm).GetNetname(), terms, WIDE.get(nm, 0.127), window=6.0)
    return failed


# Local legs first, with rip-up: when a net fails, every local signal route is taken out and the failed nets go
# first on the next pass (a net routed early can wall in one routed later). The best pass is kept.
def signal_pass(order):
    fails = {nm: route_local(nm) for nm in order}
    return {nm: f for nm, f in fails.items() if f}


order = SIGNALS + list(WIDE)
best = None
for attempt in range(4):
    mark = (len(R.log), len(RF.log))
    fails = signal_pass(order)
    print(f"  signal pass {attempt + 1}: {len(fails)} nets incomplete {sorted(fails) if fails else ''}")
    if best is None or len(fails) < len(best[0]):
        best = (fails, list(order))
    if not fails or attempt == 3:
        break
    undo(R.log[mark[0]:] + RF.log[mark[1]:])
    del R.log[mark[0]:], RF.log[mark[1]:]
    order = [nm for nm in order if nm in fails] + [nm for nm in order if nm not in fails]
if len(fails) > len(best[0]):   # the last pass did worse than the best one: take it out, redo the best order
    undo(R.log[mark[0]:] + RF.log[mark[1]:])
    del R.log[mark[0]:], RF.log[mark[1]:]
    fails = signal_pass(best[1])
unrouted += [(nm, t) for nm, f in fails.items() for t in f]

# then the long legs to the CM3's J69, on the board-wide grid
for nm in SIGNALS:
    far = [t for t in signal_terms(nm) if is_far(t)]
    if far and net_items(nm):
        left = RL.connect(net(nm).GetNetname(), [net_items(nm)] + far, 0.127, window=8.0, max_expand=3000000,
                          greed=1.3)
        unrouted += [(nm, t) for t in left]


# ---- capacitors: each tried at its best spots until its pads can be joined
gnd_xy = [via_xy(v) for v in fan_vias.get("GND", [])]
placed_caps = {}
for nm in POWER:
    vias_ = fan_vias.get(nm, [])
    for k, fp in enumerate(sorted(caps[nm], key=value_rank)):
        if value_rank(fp) == 0 and vias_:
            tgt = via_xy(vias_[k % len(vias_)])
        else:  # bulk capacitors: at the edge of the ball field nearest the rail's vias
            cxs = [via_xy(v) for v in vias_] or [BGA_C]
            mx, my = sum(c[0] for c in cxs) / len(cxs), sum(c[1] for c in cxs) / len(cxs)
            tgt = (mx, by_max + 1.6) if my > BGA_C[1] else (mx, by_min - 1.6)
        gnear = min(gnd_xy, key=lambda g: math.dist(g, tgt)) if gnd_xy else tgt
        place_back(fp, {nm: tgt, "GND": gnear}, join_part, span=3.0 if value_rank(fp) == 0 else 6.0)
        placed_caps.setdefault(nm, []).append(fp)


# ferrites: between their two rails, at the ball field's north edge
def centroid(nm):
    cxs = [via_xy(v) for v in fan_vias.get(nm, [])] or [BGA_C]
    return sum(c[0] for c in cxs) / len(cxs), sum(c[1] for c in cxs) / len(cxs)


for fb, (a, b) in zip(ferrites, (("RK628D_3V3", "AVDD_3V3_628"), ("1V1_628", "AVDD_1V1_628"))):
    ta, tb = centroid(a), centroid(b)
    place_back(fb, {a: (ta[0], by_min - 2.0), b: (tb[0], by_min - 1.2)}, join_part, span=6.0)

# anything of a rail still apart: join it on the back and L3, and as a last resort on L2 inside the ball field away
# from the escape traces at its edges (a few short cuts in the GND plane right under the chip, where no high-speed
# trace runs above)
RF.allow = {pcbnew.In1_Cu: (bx_min + 1.2, by_min + 0.3, bx_max - 1.2, by_max - 0.3)}
for nm in RAIL_ORDER:
    terms = [net_items(nm)] + [p for fp in placed_caps.get(nm, []) + ferrites for p in fp.Pads()
                               if short(p.GetNetname()) == nm]
    left = RF.connect(net(nm).GetNetname(), terms, 0.1, layers=[pcbnew.B_Cu, pcbnew.In2_Cu], via=FAN_VIA)
    if left:
        terms = [net_items(nm)] + left
        left = RF.connect(net(nm).GetNetname(), terms, 0.1, layers=[pcbnew.B_Cu, pcbnew.In2_Cu, pcbnew.In1_Cu],
                          via=FAN_VIA)
    unrouted += [(nm, t) for t in left]

# ---- the 1V1_628 converter (U106) beside the chip, and the feeds into the rails
BUCK = ["U106", "C119", "C120", "C121", "C122", "C123", "L104", "R115", "R116", "R118", "C125"]


def pads_on(netname, refs):
    return [p for r in refs for p in board.FindFootprintByReference(r).Pads() if short(p.GetNetname()) == netname]


for nm, w in (("SW_628", 0.5), ("5V_SYS", 0.5), ("BST_628", 0.25), ("FB_628", 0.2), ("EN_628", 0.2)):
    unrouted += [(nm, t) for t in R.connect(net(nm).GetNetname(), pads_on(nm, BUCK), w, window=3.0)]
for r in BUCK:
    for p in board.FindFootprintByReference(r).Pads():
        if short(p.GetNetname()) == "GND" and gnd_via_near(p) is None:
            unrouted.append(("GND", p))


FEEDS = {
    # rail: (other parts' pads on it, width)
    "1V1_628": (["U106", "L104", "C122", "C123", "R115", "FB202"], 0.4),
    "RK628D_3V3": (["Q201", "FB201", "R118", "R202", "R207", "R208", "D204"], 0.3),
}
for nm, (refs, w) in FEEDS.items():
    terms = [net_items(nm)] + pads_on(nm, refs)
    unrouted += [(nm, t) for t in R.connect(net(nm).GetNetname(), terms, w, window=6.0)]



def prune(netname):
    """Removes dead ends on a net, as KiCad's own connectivity sees them: tracks with a free end and vias joined on
    one layer or none (left by routes that a later, shorter connection made unnecessary). A via joining tracks on
    one layer only is replaced by a bridge on that layer."""
    nc = net(netname).GetNetCode()
    layers4 = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
    while True:
        board.BuildConnectivity()
        conn = board.GetConnectivity()
        items = [t for t in board.GetTracks() if t.GetNetCode() == nc]
        dead = []
        for t in items:
            if t.GetClass() == "PCB_VIA":
                on = [l for l in layers4 if conn.IsConnectedOnLayer(t, l)]
                if len(on) <= 1:
                    if on:
                        c = via_xy(t)
                        vr = pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2
                        for o in items:
                            if o.GetClass() == "PCB_TRACK" and o.GetLayer() == on[0]:
                                for e in (o.GetStart(), o.GetEnd()):
                                    q = (pcbnew.ToMM(e.x) - O[0], pcbnew.ToMM(e.y) - O[1])
                                    if math.dist(q, c) <= vr + 0.01:
                                        track(netname, on[0], [c, q], pcbnew.ToMM(o.GetWidth()))
                    dead.append(t)
            elif conn.TestTrackEndpointDangling(t, False):
                dead.append(t)
        if not dead:
            return
        for t in dead:
            board.Remove(t)

if os.environ.get("ROUTE_STOP") == "prune":
    pcbnew.SaveBoard(BOARD, board)
    raise SystemExit("stopped before pruning")
for nm in POWER + tuple(SIGNALS) + tuple(WIDE):
    prune(nm)
R.changed()
board.BuildConnectivity()
conn = board.GetConnectivity()
RK_NETS = POWER + ("SW_628", "5V_SYS", "BST_628", "FB_628", "EN_628")
for nm, t in unrouted:
    where = (t.GetParentFootprint().GetReference() + "." + t.GetNumber()) if hasattr(t, "GetNumber") else "via/track"
    print(f"  router gave up: {nm} at {where}")
print(f"RK628D: {len(fan_vias.get('GND', []))} GND and {sum(len(fan_vias.get(n, [])) for n in POWER)} power "
      f"fanout vias, {len(RESERVED_SIGNAL_SITES)} signal sites reserved, GND balls without a via: {no_site or 'none'}")


# ------------------------------------------------------------------ ground return vias
# Where a pair changes layer (L1 over L2 to L4 over L3), its return current changes plane too: a GND via within
# about 1 mm of each signal via carries it. The full stitching grid comes after the rest of the routing, so it
# doesn't block it.
def clear_at(x, y, keep=0.15):
    r = VIA_D / 2 + keep
    for fp in board.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            if (pcbnew.ToMM(bb.GetLeft()) - O[0] - r <= x <= pcbnew.ToMM(bb.GetRight()) - O[0] + r and
                    pcbnew.ToMM(bb.GetTop()) - O[1] - r <= y <= pcbnew.ToMM(bb.GetBottom()) - O[1] + r):
                return False
    for t in board.GetTracks():
        x0, y0 = pcbnew.ToMM(t.GetStart().x) - O[0], pcbnew.ToMM(t.GetStart().y) - O[1]
        x1_, y1_ = pcbnew.ToMM(t.GetEnd().x) - O[0], pcbnew.ToMM(t.GetEnd().y) - O[1]
        w = VIA_D if t.GetClass() == "PCB_VIA" else pcbnew.ToMM(t.GetWidth())
        dx, dy = x1_ - x0, y1_ - y0
        L2 = dx * dx + dy * dy
        f = 0 if L2 == 0 else max(0, min(1, ((x - x0) * dx + (y - y0) * dy) / L2))
        if math.hypot(x - x0 - f * dx, y - y0 - f * dy) < r + w / 2:
            return False
    return True


def return_vias():
    signal = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname().startswith("CSI_")]
    added = 0
    for v in signal:
        vx, vy = pcbnew.ToMM(v.GetPosition().x) - O[0], pcbnew.ToMM(v.GetPosition().y) - O[1]
        for rad in (0.7, 0.85, 1.0, 1.2, 1.5):
            spot = next(((vx + rad * math.cos(a / 12 * math.pi), vy + rad * math.sin(a / 12 * math.pi))
                         for a in range(24) if clear_at(vx + rad * math.cos(a / 12 * math.pi),
                                                        vy + rad * math.sin(a / 12 * math.pi))), None)
            if spot:
                via("GND", spot)
                added += 1
                break
    return added


n_return = return_vias()

# HDMI OUT (gen/hdmi_out.py, also runnable on its own against the checkpoint)
from hdmi_out import build as hdmi_out  # noqa: E402
hdmi_out(board)

# checkpoint without pours, then the quick finishing steps (gen/finish.py, also runnable on its own)
pcbnew.SaveBoard(os.path.join(ROOT, "routed.kicad_pcb"), board)
from finish import finish  # noqa: E402
finish(board)
pcbnew.SaveBoard(BOARD, board)

print(f"routed {len(LENGTHS)} pairs, {n_return} GND return vias; trace lengths (mm):")
for name, ln, lp in LENGTHS:
    print(f"  {name:12s} N {ln:6.2f}  P {lp:6.2f}  skew {abs(ln - lp):.2f}")
