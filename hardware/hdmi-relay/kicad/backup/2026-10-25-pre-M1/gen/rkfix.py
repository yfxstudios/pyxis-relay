"""One-off board edits for the RK628D's west corner (Oct 23), on routed.kicad_pcb. Its own process: removing a
footprint leaves pcbnew's Python layer unusable for the rest of a run.

- EFUSE (ball J8): its fanout via was closed in by the GND vias around it (0.2 mm drill to copper leaves no room
  between them on any layer). GND ball G8 gives up its via and joins its neighbour G7 on the top layer instead,
  which opens a way out.
- MCLK (ball H7): no way out at all, and it only went to a test pad (HDMI audio is not used: the CM3's I2S pins
  are shared with the DVP input). TP204 comes off the board (and the schematic, gen/hdmi_in.py), and the ball's
  stub and via go.
"""
import math
import os
import shutil
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ROUTED = os.path.join(ROOT, "routed.kicad_pcb")
shutil.copy(os.path.join(ROOT, "relay.kicad_pro"), ROUTED.replace(".kicad_pcb", ".kicad_pro"))
b = pcbnew.LoadBoard(ROUTED)
u = b.FindFootprintByReference("U201")
pad = {p.GetNumber(): p for p in u.Pads()}


def mm(v):
    return pcbnew.ToMM(v.x), pcbnew.ToMM(v.y)


g8, g7, h7 = mm(pad["G8"].GetPosition()), mm(pad["G7"].GetPosition()), mm(pad["H7"].GetPosition())
mclk = pad["H7"].GetNetCode()
gnd = b.FindNet("GND")
doomed = []
for t in b.GetTracks():
    if t.GetClass() == "PCB_VIA":
        p = mm(t.GetPosition())
        if t.GetNetCode() == gnd.GetNetCode() and math.hypot(p[0] - g8[0] + 0.325, p[1] - g8[1] + 0.325) < 0.01:
            doomed.append(t)
        elif t.GetNetCode() == mclk:
            doomed.append(t)
    else:
        a, e = mm(t.GetStart()), mm(t.GetEnd())
        if t.GetNetCode() == mclk:
            doomed.append(t)
        elif t.GetNetCode() == gnd.GetNetCode() and any(math.hypot(q[0] - g8[0], q[1] - g8[1]) < 0.01 for q in (a, e)) \
                and any(math.hypot(q[0] - g8[0] + 0.325, q[1] - g8[1] + 0.325) < 0.01 for q in (a, e)):
            doomed.append(t)
print(f"removing {len(doomed)} items (G8's dogbone, MCLK's copper)")
for t in doomed:
    b.Remove(t)
t = pcbnew.PCB_TRACK(b)
t.SetStart(pcbnew.VECTOR2I_MM(*g8)); t.SetEnd(pcbnew.VECTOR2I_MM(*g7))
t.SetWidth(pcbnew.FromMM(0.15)); t.SetLayer(pcbnew.F_Cu); t.SetNet(gnd)
b.Add(t)
pad["H7"].SetNetCode(0)
tp = b.FindFootprintByReference("TP204")
b.Remove(tp)
pcbnew.SaveBoard(ROUTED, b)
shutil.copy(os.path.join(ROOT, "relay.kicad_pro"), ROUTED.replace(".kicad_pcb", ".kicad_pro"))
print("saved")
sys.stdout.flush()
os._exit(0)
