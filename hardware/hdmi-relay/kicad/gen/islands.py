"""Prints (as JSON) the GND pour islands on the outer layers of the finished board (relay.kicad_pcb) that hold no
GND via, each as a list of candidate points inside it (board mm). Run by gen/autoroute.py's gndfix stage."""
import json
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
b = pcbnew.LoadBoard(os.path.join(os.path.dirname(HERE), "relay.kicad_pcb"))
gnd = b.FindNet("GND").GetNetCode()
vias = [t.GetPosition() for t in b.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetCode() == gnd]
out = []
for z in b.Zones():
    if z.GetNetCode() != gnd:
        continue
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        if not z.IsOnLayer(layer):
            continue
        polys = z.GetFilledPolysList(layer)
        for k in range(polys.OutlineCount()):
            one = pcbnew.SHAPE_POLY_SET()
            one.AddOutline(polys.Outline(k))
            for h in range(polys.HoleCount(k)):
                one.AddHole(polys.Hole(k, h))
            if any(one.Contains(v) for v in vias):
                continue
            bb = one.BBox()
            pts = []
            step = pcbnew.FromMM(0.25)
            y = bb.GetTop() + step // 2
            while y < bb.GetBottom():
                x = bb.GetLeft() + step // 2
                while x < bb.GetRight():
                    p = pcbnew.VECTOR2I(int(x), int(y))
                    if one.Contains(p) and one.Outline(0).PointInside(p, pcbnew.FromMM(0.35)):
                        pts.append((pcbnew.ToMM(x), pcbnew.ToMM(y)))
                    x += step
                y += step
            pads = [(f.GetReference(), q.GetNumber()) for f in b.GetFootprints() for q in f.Pads()
                    if q.GetNetCode() == gnd and q.IsOnLayer(layer) and one.Contains(q.GetPosition())]
            out.append({"pts": pts, "pads": pads})
print(json.dumps(out))
sys.stdout.flush()
os._exit(0)
