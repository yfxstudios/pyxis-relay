"""Moves nets to new CM3 pins on the routed checkpoint (../routed.kicad_pcb), after gen/module.py has changed.

  .../bin/python3 gen/pinmove.py pads      reassign the pads and cut each net's stub to its old pad
  .../bin/python3 gen/pinmove.py tidy      after routing: LED_WIFI's tail and DVP_D6 re-drawn (TIDY)
  .../bin/python3 gen/pinmove.py prune     last: remove copper left dangling on these nets

Between the two steps, gen/handroute.py draws each net's short tail to its new pad (README, "Oct 25 pin fixes").
Then gen/sync.py gives the freed pads their unconnected-(...) nets. Oct 25: the 1.8 V pin fixes from
REVIEW_INDEPENDENT.md (M1, M2, M3, M5, M8).
"""
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from finish import GRAVEYARD, ROUTED  # noqa: E402
from pcb import O  # noqa: E402

# net: old pad, new pad (None: the net just leaves the module)
MOVES = {
    "RK628D_INT": (("J703", "18"), ("J703", "12")),
    "RK628D_RESET_N": (("J703", "20"), ("J703", "10")),
    "BT_DISABLE_N": (("J703", "34"), ("J703", "40")),
    "LED_STATUS": (("J701", "30"), ("J701", "34")),
    "LED_WIFI": (("J701", "56"), ("J701", "75")),
    "PD_PG_N": (("J701", "58"), None),
}
DROP = {"SDI_GPIO8": ("J602", "38"), "SDI_GPIO2": ("J602", "32")}     # nets that no longer exist: all copper removed, the header pin left unused
# the last stub into each old pad, (layer, start, end) in board mm
CUT = {
    "RK628D_INT": [("F", (91.33, 56.7), (90.42, 56.7))],
    "RK628D_RESET_N": [("F", (90.35, 56.2), (90.75, 56.2)), ("F", (90.75, 56.2), (90.8, 56.25))],
    "BT_DISABLE_N": [("F", (92.25, 51.9), (92.25, 53.15)), ("F", (92.25, 53.15), (91.85, 53.55))],
    "LED_STATUS": [("F", (63.4, 64.05), (63.7, 64.35)), ("F", (63.7, 64.35), (64.05, 64.35)),
                   ("F", (64.05, 64.35), (64.35, 64.65)), ("F", (64.35, 64.65), (64.35, 65.15)),
                   ("F", (64.35, 65.15), (64.3, 65.2))],
    "LED_WIFI": [("F", (69.5, 65.0), (69.5, 65.2))],
    # PD_PG_N's whole branch from the tee by Q101 to J701 pin 58 (the net now stays by the CH224A)
    "PD_PG_N": [("B", (26.6, 85.45), (27.4, 84.65)), ("B", (27.4, 84.65), (30.4, 84.65)),
                ("B", (30.4, 84.65), (48.25, 66.8)), ("F", (48.25, 66.8), (56.6, 58.45)),
                ("F", (56.6, 58.45), (67.75, 58.45)), ("F", (67.75, 58.45), (69.1, 57.1)),
                ("B", (69.1, 57.1), (71.15, 57.1)), ("B", (71.15, 57.1), (71.25, 57.2)),
                ("F", (71.25, 57.2), (69.9, 58.55)), ("B", (69.9, 58.55), (69.9, 64.0)),
                ("F", (69.9, 64.0), (69.9, 65.2))],
}
CUT_VIAS = {"PD_PG_N": [(48.25, 66.8), (69.1, 57.1), (71.25, 57.2), (69.9, 58.55), (69.9, 64.0)],
            "LED_WIFI": [(69.5, 65.0)]}      # 0.73 mm from pad 56, which is no longer LED_WIFI's
LAYER = {"F": pcbnew.F_Cu, "B": pcbnew.B_Cu, "1": pcbnew.In1_Cu, "2": pcbnew.In2_Cu}


def pad(board, ref, num):
    f = next(f for f in board.GetFootprints() if f.GetReference() == ref)
    return next(p for p in f.Pads() if p.GetNumber() == num)


def mm(p):
    return round(pcbnew.ToMM(p.x) - O[0], 2), round(pcbnew.ToMM(p.y) - O[1], 2)


def remove(board, t):
    board.Remove(t)
    GRAVEYARD.append(t)      # a removed item that Python frees breaks pcbnew's SWIG types


def pads(board):
    for name, ref_pin in DROP.items():
        ni = board.FindNet(name)
        for t in [t for t in board.GetTracks() if ni and t.GetNetCode() == ni.GetNetCode()]:
            remove(board, t)
        pad(board, *ref_pin).SetNetCode(0)
    for name, (old, new) in MOVES.items():          # free every old pad first: two nets may swap pads
        pad(board, *old).SetNetCode(0)
    for name, (old, new) in MOVES.items():
        ni = board.FindNet(name)
        if new:
            p = pad(board, *new)
            if p.GetNetCode() and not p.GetNetname().startswith("unconnected") and p.GetNetname() not in DROP:
                raise RuntimeError(f"{new} is on {p.GetNetname()}")
            p.SetNet(ni)
        for layer, a, b in CUT.get(name, []):
            hit = [t for t in board.GetTracks() if t.GetNetCode() == ni.GetNetCode() and t.GetClass() != "PCB_VIA"
                   and t.GetLayer() == LAYER[layer] and {mm(t.GetStart()), mm(t.GetEnd())} == {a, b}]
            if len(hit) != 1:
                raise RuntimeError(f"{name}: stub {a}-{b} on {layer}: found {len(hit)}")
            remove(board, hit[0])
        for c in CUT_VIAS.get(name, []):
            hit = [t for t in board.GetTracks() if t.GetNetCode() == ni.GetNetCode() and t.GetClass() == "PCB_VIA"
                   and mm(t.GetPosition()) == c]
            if len(hit) != 1:
                raise RuntimeError(f"{name}: via {c}: found {len(hit)}")
            remove(board, hit[0])
        print(f"{name}: {old[0]}.{old[1]} -> " + (f"{new[0]}.{new[1]}" if new else "off the module") +
              f", {len(CUT.get(name, []))} segments and {len(CUT_VIAS.get(name, []))} vias cut")


def _seg_point(p, a, b):
    """Distance from p to segment ab, and the parameter t of the nearest point."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy), t


def prune_geometric(board, nc):
    """Removes this net's copper that leads nowhere, by geometry and same-net contacts only (a pad of another net
    or of no net is not a contact). A dead-ended track that something else touches part-way along is shortened to
    that point instead of removed, so a new route teed into an old one survives (finish.prune_dead_ends would take
    the whole track, and the new route with it). Returns (removed, shortened)."""
    eps = 0.005
    removed = shortened = 0
    while True:
        segs = [t for t in board.GetTracks() if t.GetNetCode() == nc and t.GetClass() != "PCB_VIA"]
        vias = [t for t in board.GetTracks() if t.GetNetCode() == nc and t.GetClass() == "PCB_VIA"]
        pads_ = []
        for f in board.GetFootprints():
            for p in f.Pads():
                if p.GetNetCode() == nc:
                    bb = p.GetBoundingBox()
                    pads_.append((p, (pcbnew.ToMM(bb.GetLeft()) - O[0], pcbnew.ToMM(bb.GetTop()) - O[1],
                                      pcbnew.ToMM(bb.GetRight()) - O[0], pcbnew.ToMM(bb.GetBottom()) - O[1])))
        geo = {id(t): (mm(t.GetStart()), mm(t.GetEnd()), pcbnew.ToMM(t.GetWidth()) / 2, t.GetLayer()) for t in segs}
        vgeo = {id(v): (mm(v.GetPosition()), pcbnew.ToMM(v.GetWidth(pcbnew.F_Cu)) / 2) for v in vias}

        def contact(pt, layer, skip, own=0.0):
            """Is the end at pt (half width own) on `layer` overlapped by same-net copper other than `skip`?"""
            for t in segs:
                a, b, hw, ly = geo[id(t)]
                if t is not skip and ly == layer and _seg_point(pt, a, b)[0] <= hw + own - eps:
                    return True
            for v in vias:
                c, r = vgeo[id(v)]
                if v is not skip and math.dist(pt, c) <= r + own - eps:
                    return True
            for p, (x0, y0, x1, y1) in pads_:
                if p.IsOnLayer(layer) and x0 - eps <= pt[0] <= x1 + eps and y0 - eps <= pt[1] <= y1 + eps:
                    return True
            return False

        dead, short = [], []
        for v in vias:
            c, r = vgeo[id(v)]
            touching = [t for t in segs if _seg_point(c, geo[id(t)][0], geo[id(t)][1])[0] <= r + geo[id(t)][2] - eps]
            layers = {geo[id(t)][3] for t in touching}
            layers |= {l for p, (x0, y0, x1, y1) in pads_ for l in LAYER.values()
                       if p.IsOnLayer(l) and x0 <= c[0] <= x1 and y0 <= c[1] <= y1}
            if len(layers) > 1:
                continue
            dead.append(v)
            if len(touching) >= 2:
                # a via that only joins tracks on one layer (its other layers' copper was cut): the tracks meet
                # at its centre instead
                for t in touching:
                    a, b = geo[id(t)][:2]
                    end = "start" if math.dist(a, c) <= math.dist(b, c) else "end"
                    if min(math.dist(a, c), math.dist(b, c)) > r + geo[id(t)][2]:
                        continue                               # passes the via part-way: already joined
                    pt = pcbnew.VECTOR2I_MM(c[0] + O[0], c[1] + O[1])
                    (t.SetStart if end == "start" else t.SetEnd)(pt)
                break                                          # geometry changed: measure again
        if dead:                                               # vias first, then measure the tracks again
            for v in dead:
                remove(board, v)
            removed += len(dead)
            continue
        for t in segs:
            a, b, hw, ly = geo[id(t)]
            free_a, free_b = not contact(a, ly, t, hw), not contact(b, ly, t, hw)
            if not (free_a or free_b):
                continue
            # contacts part-way along this track: other tracks' ends, vias, pads
            ts = []
            for o in segs:
                if o is t or geo[id(o)][3] != ly:
                    continue
                for q in geo[id(o)][:2]:
                    d, tt = _seg_point(q, a, b)
                    if d <= hw + geo[id(o)][2] - eps and 0 < tt < 1:
                        ts.append(tt)
            for v in vias:
                d, tt = _seg_point(vgeo[id(v)][0], a, b)
                if d <= vgeo[id(v)][1] + hw - eps and 0 < tt < 1:
                    ts.append(tt)
            if free_a and free_b and len(ts) < 2 or not ts:
                dead.append(t)
                continue
            lo, hi = min(ts), max(ts)
            na = a if not free_a else (a[0] + lo * (b[0] - a[0]), a[1] + lo * (b[1] - a[1]))
            nb = b if not free_b else (a[0] + hi * (b[0] - a[0]), a[1] + hi * (b[1] - a[1]))
            if math.dist(na, nb) < 0.01:
                dead.append(t)
            else:
                short.append((t, na, nb))
        if not dead and not short:
            return removed, shortened
        for t in dead:
            remove(board, t)
        for t, na, nb in short:
            t.SetStart(pcbnew.VECTOR2I_MM(na[0] + O[0], na[1] + O[1]))
            t.SetEnd(pcbnew.VECTOR2I_MM(nb[0] + O[0], nb[1] + O[1]))
        removed += len(dead)
        shortened += len(short)


# after routing. LED_WIFI's tail to pad 75 has to cross the gap between J701's rows, and every via spot right of
# pad 71 is taken by back-layer tracks, so a tail along the gap cut pad 71 (GND) off from the ground fill. The tail
# now drops from a via at DVP_D6's old place in the gap, and DVP_D6 is re-routed on In2 under the pads
# (gen/localroute.py), which leaves the fill a 0.4 mm strip along the pad tops. net: (removed, added); each item is
# (layer, start, end) or ("V", centre), in board mm.
TIDY = {
    "LED_WIFI": ([("F", (72.3, 67.45), (72.45, 67.6)), ("F", (72.45, 67.6), (73.25, 67.6)),
                  ("F", (73.25, 67.6), (73.5, 67.85)), ("F", (73.5, 67.85), (73.5, 67.9)),
                  ("2", (73.5, 66.8), (72.85, 67.45)), ("2", (72.85, 67.45), (72.3, 67.45)), ("V", (72.3, 67.45))],
                 [("2", (73.5, 66.8), (73.5, 67.05)), ("2", (73.5, 67.05), (72.65, 67.05)), ("V", (72.65, 67.05)),
                  ("F", (72.65, 67.05), (73.25, 67.05)), ("F", (73.25, 67.05), (73.48, 67.28)),
                  ("F", (73.48, 67.28), (73.48, 67.9))]),
    "DVP_D6": ([("F", (75.35, 67.05), (68.0, 67.05)), ("F", (75.45, 67.15), (75.35, 67.05)),
                ("F", (76.1, 67.15), (75.45, 67.15)), ("B", (76.1, 67.1), (76.1, 67.15)), ("V", (76.1, 67.15))], []),
}


def tidy(board):
    for name, (cut, add) in TIDY.items():
        ni = board.FindNet(name)
        for item in cut:
            if item[0] == "V":
                hit = [t for t in board.GetTracks() if t.GetNetCode() == ni.GetNetCode()
                       and t.GetClass() == "PCB_VIA" and mm(t.GetPosition()) == item[1]]
            else:
                hit = [t for t in board.GetTracks() if t.GetNetCode() == ni.GetNetCode()
                       and t.GetClass() != "PCB_VIA" and t.GetLayer() == LAYER[item[0]]
                       and {mm(t.GetStart()), mm(t.GetEnd())} == {item[1], item[2]}]
            if len(hit) != 1:
                raise RuntimeError(f"{name}: {item}: found {len(hit)}")
            remove(board, hit[0])
        for item in add:
            if item[0] == "V":
                t = pcbnew.PCB_VIA(board)
                t.SetPosition(pcbnew.VECTOR2I_MM(item[1][0] + O[0], item[1][1] + O[1]))
                t.SetWidth(pcbnew.FromMM(0.3))
                t.SetDrill(pcbnew.FromMM(0.15))
            else:
                t = pcbnew.PCB_TRACK(board)
                t.SetLayer(LAYER[item[0]])
                t.SetStart(pcbnew.VECTOR2I_MM(item[1][0] + O[0], item[1][1] + O[1]))
                t.SetEnd(pcbnew.VECTOR2I_MM(item[2][0] + O[0], item[2][1] + O[1]))
                t.SetWidth(pcbnew.FromMM(0.1))
            t.SetNet(ni)
            board.Add(t)
        print(f"{name}: {len(cut)} items cut, {len(add)} added")


def prune(board):
    for name in list(MOVES) + list(DROP) + list(TIDY):
        ni = board.FindNet(name)
        if ni is None:
            continue
        r, s = prune_geometric(board, ni.GetNetCode())
        print(f"{name}: {r} dead-end items removed, {s} tracks shortened")


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    if step not in ("pads", "tidy", "prune"):
        sys.exit(__doc__)
    board = pcbnew.LoadBoard(ROUTED)
    {"pads": pads, "tidy": tidy, "prune": prune}[step](board)
    pcbnew.SaveBoard(ROUTED, board)
