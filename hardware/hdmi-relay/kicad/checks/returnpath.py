"""Return-path checks for the high-speed nets of ../relay.kicad_pcb (pours filled):

1. reference plane under each track: sampled every 0.1 mm at the centreline and at both edges plus 3x the dielectric
   height (0.3 mm) either side; any sample without filled GND copper on the reference layer counts as a gap
   (F -> In1, B -> In2, In2 -> In1);
2. return vias: every signal via of a high-speed net should have a GND via within 1.0 mm (its return current
   changes planes there too).

  .../bin/python3 checks/returnpath.py
"""
import math
import re
from collections import defaultdict

import pcbnew

HS = re.compile(r"^(HDMIRX|HDMITX)_(D[0-2]|CLK)_[PN]$|^CSI_(D[0-3]|CLK)_[PN]$|^MDI[0-3]_[PN]$|^USB_.*_D[PM](_C)?$|"
                r"^PCIE_(TX|RX|REFCLK)_[PN]$|^M2_PET_[PN]$|^XIN_628$|^XOUT_628$")
REF = {pcbnew.F_Cu: pcbnew.In1_Cu, pcbnew.B_Cu: pcbnew.In2_Cu, pcbnew.In2_Cu: pcbnew.In1_Cu}
O = 30


def main():
    b = pcbnew.LoadBoard("relay.kicad_pcb")
    gnd = [z for z in b.Zones() if z.GetNetname() == "GND"]
    fill = {L: [z.GetFilledPolysList(L) for z in gnd if z.IsOnLayer(L)] for L in (pcbnew.In1_Cu, pcbnew.In2_Cu)}

    def has_gnd(L, x, y):
        p = pcbnew.VECTOR2I(pcbnew.FromMM(x + O), pcbnew.FromMM(y + O))
        return any(f.Contains(p) for f in fill[L])

    gaps = defaultdict(lambda: [0.0, 0.0, []])        # net -> [gap mm, total mm, where]
    for t in b.GetTracks():
        n = t.GetNetname().split("/")[-1]
        if t.GetClass() == "PCB_VIA" or not HS.match(n) or t.GetLayer() not in REF:
            continue
        L = REF[t.GetLayer()]
        a = (pcbnew.ToMM(t.GetStart().x) - O, pcbnew.ToMM(t.GetStart().y) - O)
        c = (pcbnew.ToMM(t.GetEnd().x) - O, pcbnew.ToMM(t.GetEnd().y) - O)
        ln = math.dist(a, c)
        if ln == 0:
            continue
        ux, uy = (c[0] - a[0]) / ln, (c[1] - a[1]) / ln
        side = pcbnew.ToMM(t.GetWidth()) / 2 + 0.3
        steps = max(1, int(ln / 0.1))
        for k in range(steps + 1):
            x, y = a[0] + ux * ln * k / steps, a[1] + uy * ln * k / steps
            ok = all(has_gnd(L, x - uy * s, y + ux * s) for s in (0, side, -side))
            if not ok:
                gaps[n][0] += ln / (steps + 1)
                if len(gaps[n][2]) < 3:
                    gaps[n][2].append((round(x, 2), round(y, 2), b.GetLayerName(t.GetLayer())))
        gaps[n][1] += ln
    print("Reference plane under high-speed tracks (gap = no GND within 0.3 mm of the trace on its reference layer):")
    for n in sorted(gaps):
        g, tot, where = gaps[n]
        if g > 0:
            print(f"  {n:16s} {g:5.2f} mm of {tot:6.2f} mm without solid reference  e.g. {where}")
    clean = [n for n in gaps if gaps[n][0] == 0]
    print(f"  clean: {len(clean)} of {len(gaps)} nets")

    gv = [(pcbnew.ToMM(t.GetPosition().x) - O, pcbnew.ToMM(t.GetPosition().y) - O)
          for t in b.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]
    gp = [(pcbnew.ToMM(p.GetPosition().x) - O, pcbnew.ToMM(p.GetPosition().y) - O)
          for f in b.GetFootprints() for p in f.Pads() if p.GetNetname() == "GND" and p.HasHole()]
    print("Return vias (nearest GND via or GND through-hole to each high-speed signal via):")
    far = []
    for t in b.GetTracks():
        n = t.GetNetname().split("/")[-1]
        if t.GetClass() != "PCB_VIA" or not HS.match(n):
            continue
        P = (pcbnew.ToMM(t.GetPosition().x) - O, pcbnew.ToMM(t.GetPosition().y) - O)
        d = min(math.dist(P, q) for q in gv + gp)
        far.append((d, n, tuple(round(v, 2) for v in P)))
    far.sort(reverse=True)
    for d, n, P in far:
        flag = "  <-- over 1 mm" if d > 1.0 else ""
        print(f"  {n:16s} via at {P}: nearest GND via {d:.2f} mm{flag}")


if __name__ == "__main__":
    main()
