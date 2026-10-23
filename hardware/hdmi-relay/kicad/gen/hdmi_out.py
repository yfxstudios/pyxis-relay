"""HDMI OUT: the module's HDMI TX (J68, J702) to the HDMI connector J401, with its ESD, 5 V switch and DDC pull-ups.

Runs on the routed checkpoint in seconds, then gen/finish.py's steps:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 gen/hdmi_out.py

gen/route.py calls build() too, so a full regeneration includes it.

The four TMDS pairs leave J68's north pad row northwards (P west, 1.2 mm apart), step east on one 45-degree leg to
the connector's spacing (1.5 mm), and pass straight through two flow-through ESD parts just behind J401, as on
HDMI IN. Everything on L1 over the L2 GND plane.
"""
import math
import os
import shutil
import sys

import numpy as np
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from pairs import length, offset, tune  # noqa: E402
from pcb import NETCLASSES, O, W, H, netlist  # noqa: E402
from router import Router  # noqa: E402

PAIR_W = NETCLASSES["DIFF_100R"][4]
HALF = (NETCLASSES["DIFF_100R"][4] + NETCLASSES["DIFF_100R"][5]) / 2

# Placement (x, y, rotation), board mm. The ESD parts line up with the connector pins (see the pin check below);
# the 5 V switch, its capacitors and the DDC pull-ups sit east of the TMDS corridor (x 72-80).
PLACE = {
    "D401": (75.75, 13.0, 90), "D402": (78.75, 13.0, 90), "D403": (82.5, 13.0, 90),
    "U401": (87.5, 16.5, 0), "C401": (87.5, 19.0, 0), "C402": (84.6, 17.2, 90),
    "R401": (85.2, 13.6, 90), "R402": (86.4, 13.6, 90),
}
LANES = [  # name, J401 P, N pins, ESD part, J702 P, N pads
    ("D2", "1", "3", "D401", "70", "72"), ("D1", "4", "6", "D401", "76", "78"),
    ("D0", "7", "9", "D402", "82", "84"), ("CLK", "10", "12", "D402", "88", "90"),
]
Y_ESD_OUT = 14.0      # south of the ESD parts, where pairs settle to 0.2 mm centres
Y_DIAG = 24.0         # where each pair starts its 45-degree step east


def build(board, log=print):
    def mm(x, y):
        return pcbnew.VECTOR2I_MM(float(O[0] + x), float(O[1] + y))

    def xy(item):
        v = item.GetPosition()
        return pcbnew.ToMM(v.x) - O[0], pcbnew.ToMM(v.y) - O[1]

    def pad(ref, num):
        return xy(board.FindFootprintByReference(ref).FindPadByNumber(num))

    def net(short):
        for n, item in board.GetNetsByName().items():
            if str(n) == short or str(n).endswith("/" + short):
                return item
        raise SystemExit(f"no net {short}")

    def track(netname, layer, pts, width):
        for a, b in zip(pts, pts[1:]):
            if math.dist(a, b) < 1e-4:
                continue
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(mm(*a)); t.SetEnd(mm(*b)); t.SetWidth(pcbnew.FromMM(width))
            t.SetLayer(layer); t.SetNet(net(netname))
            board.Add(t)

    # ---- pad nets from the schematic (the ESD lines were reordered there) and placement
    _, nets = netlist()
    for ref in PLACE:
        for p in board.FindFootprintByReference(ref).Pads():
            name = nets.get((ref, p.GetNumber()))
            if name and p.GetNetname() != name:
                p.SetNet(board.FindNet(name))
    for ref, (x, y, rot) in PLACE.items():
        fp = board.FindFootprintByReference(ref)
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(mm(x, y))

    # ---- TMDS pairs: from the connector southwards, N east of P (left of travel)
    lengths = []
    for lane, pp, pn, esd, jp, jn in LANES:
        cp, cn = pad("J401", pp), pad("J401", pn)
        io = {"D401": ("1", "2", "4", "5"), "D402": ("1", "2", "4", "5")}[esd]
        k = 0 if lane in ("D2", "D0") else 2
        ep, en = pad(esd, io[k]), pad(esd, io[k + 1])
        ep2 = pad(esd, {"1": "10", "4": "7"}[io[k]])
        assert abs(ep[0] - ep2[0]) < 1e-3 and ep[0] < en[0] and abs((ep[0] + en[0]) / 2 - (cp[0] + cn[0]) / 2) < 1e-3, \
            (lane, ep, en, cp, cn)
        xc = (ep[0] + en[0]) / 2
        mp, mn = pad("J702", jp), pad("J702", jn)
        x0 = (mp[0] + mn[0]) / 2
        d = xc - x0
        top_j702 = mp[1] - 0.57 - 0.25        # just north of the pad row
        centre = [(xc, Y_ESD_OUT + 0.15), (xc, Y_DIAG - d), (x0, Y_DIAG), (x0, top_j702)]
        left, right = offset(centre, -HALF), offset(centre, HALF)     # heading south: left is east (N)
        top = min(ep[1], ep2[1]) - 0.4
        n = [cn, (cn[0], top - abs(cn[0] - en[0])), (en[0], top), (en[0], Y_ESD_OUT)] + left
        p = [cp, (cp[0], top - abs(cp[0] - ep[0])), (ep[0], top), (ep[0], Y_ESD_OUT)] + right
        n += [(mn[0], top_j702 + 0.1), (mn[0], mn[1])]
        p += [(mp[0], top_j702 + 0.1), (mp[0], mp[1])]
        ln, lp = length(n), length(p)
        if abs(ln - lp) > 0.005:          # bumps on the shorter trace's long straight, away from its partner
            if ln < lp:
                n = tune(n, 4, lp - ln, -1)
            else:
                p = tune(p, 4, ln - lp, 1)
        track(f"HDMITX_{lane}_N", pcbnew.F_Cu, n, PAIR_W)
        track(f"HDMITX_{lane}_P", pcbnew.F_Cu, p, PAIR_W)
        lengths.append((lane, length(n), length(p)))

    # ---- DDC, HPD and the 5 V switch: grid router; HPD crosses the pairs on the back. The 5 V line through D403
    # is drawn straight (connector pin 18 through ESD pins 7 and 4), 0.225 mm from the neighbouring pins.
    c5 = pad("J401", "18")
    assert abs(pad("D403", "4")[0] - c5[0]) < 1e-3 and abs(pad("D403", "7")[0] - c5[0]) < 1e-3
    track("HDMITX_5V", pcbnew.F_Cu, [c5, pad("D403", "4")], 0.25)
    R = Router(board, O, (W, H), (55.0, 0.0, 100.0, 40.0), clearance=0.13)

    def pads_of(netname, refs=None):
        return [p for fp in board.GetFootprints() for p in fp.Pads()
                if p.GetNetname().split("/")[-1] == netname and (refs is None or fp.GetReference() in refs)]
    left = []
    for netname, width, refs in (("HDMITX_SCL", 0.127, None), ("HDMITX_SDA", 0.127, None),
                                 ("HDMITX_HPD", 0.127, None),
                                 ("HDMITX_5V", 0.25, None),   # 0.25 mm fits the ESD and connector pins (0.5 mm pitch); 55 mA+
                                 ("5V_SYS", 0.4, ("U401", "C401"))):   # the 5V_SYS trunk comes with the power
        left += [(netname, t) for t in R.connect(net(netname).GetNetname(), pads_of(netname, refs), width,
                                                 window=6.0, max_expand=2000000)]

    # ---- a GND via beside every GND pad of these parts (the pours can't reach between the ESD lines)
    gc = net("GND").GetNetCode()
    vias_now = [xy(t) for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    added = 0
    for ref in PLACE:
        for p in board.FindFootprintByReference(ref).Pads():
            if p.GetNetCode() != gc:
                continue
            vb = R.blocked(gc, 0.225, [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]).any(axis=0)
            tb = R.blocked(gc, 0.125, [pcbnew.F_Cu])[0]
            x, y = xy(p)
            done = False
            for rad in np.arange(0.5, 1.6, 0.1):
                for a in range(0, 360, 15):
                    vx, vy = x + rad * math.cos(math.radians(a)), y + rad * math.sin(math.radians(a))
                    i, j = int(round((vx - R.x0) / R.res)), int(round((vy - R.y0) / R.res))
                    if not (0 <= i < R.nx and 0 <= j < R.ny) or vb[j, i]:
                        continue
                    if any(math.dist((vx, vy), v) < 0.65 for v in vias_now):
                        continue
                    steps = max(2, int(rad / R.res))
                    if all(not tb[int(round((y + (vy - y) * s / steps - R.y0) / R.res)),
                                   int(round((x + (vx - x) * s / steps - R.x0) / R.res))]
                           or math.dist((x + (vx - x) * s / steps, y + (vy - y) * s / steps), (x, y)) < 0.35
                           for s in range(steps + 1)):
                        v = pcbnew.PCB_VIA(board)
                        v.SetPosition(mm(vx, vy)); v.SetViaType(pcbnew.VIATYPE_THROUGH)
                        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                        v.SetDrill(pcbnew.FromMM(0.25)); v.SetWidth(pcbnew.FromMM(0.45)); v.SetNet(net("GND"))
                        board.Add(v)
                        track("GND", pcbnew.F_Cu, [(x, y), (vx, vy)], 0.25)
                        vias_now.append((vx, vy))
                        R.changed()
                        added += 1
                        done = True
                        break
                if done:
                    break
            if not done:
                left.append(("GND", p))

    log("HDMI OUT pairs (mm): " + ", ".join(f"{l} N {a:.2f} P {b:.2f}" for l, a, b in lengths))
    log(f"HDMI OUT: {added} GND vias; not connected: " +
        (", ".join(f"{n} at {t.GetParentFootprint().GetReference()}.{t.GetNumber()}" if hasattr(t, "GetNumber")
                   else n for n, t in left) or "none"))


if __name__ == "__main__":
    from finish import ROUTED, OUT, finish
    shutil.copy(os.path.join(ROOT, "relay.kicad_pro"), ROUTED.replace(".kicad_pcb", ".kicad_pro"))
    board = pcbnew.LoadBoard(ROUTED)
    # start clean: take out whatever an earlier run of this script drew
    for t in list(board.GetTracks()):
        if t.GetNetname().split("/")[-1].startswith("HDMITX_"):
            board.Remove(t)
    build(board)
    pcbnew.SaveBoard(ROUTED, board)
    finish(board)
    pcbnew.SaveBoard(OUT, board)
