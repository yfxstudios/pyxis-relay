"""Turns the DC jack J101 to face the board edge (REVIEW_FABLE_2.md B1), on the routed checkpoint.

  .../bin/python3 gen/jackfix.py          turn J101 and clear the copper under its new pads
  .../bin/python3 gen/jackfix.py --via    after routing: VIN_RAW's second via at the east layer change

It was placed with its centre-pin terminal (the jack's rear) at the edge and the plug opening facing inward. Now
rotated 180 deg about the same axis line, pin 1 at (42.0, 85.55): the opening is 0.7 mm inside the edge. Removes the
copper the new pads land on: the VDC stub to the old pin 1, the VIN_RAW run across the jack, and GND stitching vias
under the new pads. Then gen/localroute.py re-routes VDC and VIN_RAW (README, "DC jack (Oct 25)").
"""
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from finish import GRAVEYARD, ROUTED  # noqa: E402
from pcb import O  # noqa: E402

PIN1 = (42.0, 85.55)
CUT = {"VDC": [((43.6, 96.8), (48.7, 96.8))],
       "VIN_RAW": [((42.1, 84.2), (34.7, 84.2)), ((48.9, 91.0), (42.1, 84.2))]}


def mm(p):
    return round(pcbnew.ToMM(p.x) - O[0], 2), round(pcbnew.ToMM(p.y) - O[1], 2)


def main():
    board = pcbnew.LoadBoard(ROUTED)
    f = board.FindFootprintByReference("J101")
    f.SetOrientationDegrees(90)
    f.SetPosition(pcbnew.VECTOR2I_MM(PIN1[0] + O[0], PIN1[1] + O[1]))
    pads = list(f.Pads())
    print("J101 pads:", [(p.GetNumber(), mm(p.GetPosition())) for p in pads])
    gone = []
    for net, segs in CUT.items():
        nc = next(v for k, v in board.GetNetsByName().items() if str(k).split("/")[-1] == net).GetNetCode()
        for a, b in segs:
            hit = [t for t in board.GetTracks() if t.GetNetCode() == nc and t.GetClass() == "PCB_TRACK"
                   and {mm(t.GetStart()), mm(t.GetEnd())} == {a, b}]
            assert len(hit) == 1, (net, a, b, len(hit))
            gone += hit
    # stitching vias the new pads (with 0.2 mm hole clearance) now cover
    for v in [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]:
        for p in pads:
            bb = p.GetBoundingBox()
            bb.Inflate(pcbnew.FromMM(0.2) + v.GetWidth(pcbnew.F_Cu) // 2)
            if bb.Contains(v.GetPosition()):
                gone.append(v)
                break
    for t in gone:
        board.Remove(t)
    GRAVEYARD.extend(gone)
    print(f"removed {len(gone)} items:", [(t.GetNetname().split('/')[-1], mm(t.GetStart())) for t in gone])
    nudge_fuse(board)
    pcbnew.SaveBoard(ROUTED, board)


def nudge_fuse(board):
    """J101's pin-3 courtyard now reaches F101's: F101 moves 0.4 mm east and its reference off J101's pin 3."""
    f = board.FindFootprintByReference("F101")
    f.Move(pcbnew.VECTOR2I_MM(0.4, 0))
    f.Reference().SetPosition(pcbnew.VECTOR2I_MM(53.4 + O[0], 93.0 + O[1]))
    ni = next(v for k, v in board.GetNetsByName().items() if str(k).split("/")[-1] == "VIN_RAW")
    for a, b in (((48.55, 91.75), (49.7, 91.6)), ((48.9, 91.9), (49.7, 91.6))):   # re-reach pad 1
        t = pcbnew.PCB_TRACK(board)
        t.SetLayer(pcbnew.F_Cu)
        t.SetStart(pcbnew.VECTOR2I_MM(a[0] + O[0], a[1] + O[1]))
        t.SetEnd(pcbnew.VECTOR2I_MM(b[0] + O[0], b[1] + O[1]))
        t.SetWidth(pcbnew.FromMM(0.8))
        t.SetNet(ni)
        board.Add(t)


def second_via():
    """VIN_RAW's east layer change gets a second via (USB-C current, up to 3 A). Drawn here rather than with
    gen/handroute.py, whose round-pad model of J101's slotted pin 3 is too conservative; KiCad DRC checks it."""
    board = pcbnew.LoadBoard(ROUTED)
    ni = next(v for k, v in board.GetNetsByName().items() if str(k).split("/")[-1] == "VIN_RAW")
    a, b = (45.35, 90.9), (45.35, 91.75)
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        t = pcbnew.PCB_TRACK(board)
        t.SetLayer(layer)
        t.SetStart(pcbnew.VECTOR2I_MM(a[0] + O[0], a[1] + O[1]))
        t.SetEnd(pcbnew.VECTOR2I_MM(b[0] + O[0], b[1] + O[1]))
        t.SetWidth(pcbnew.FromMM(0.8))
        t.SetNet(ni)
        board.Add(t)
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I_MM(b[0] + O[0], b[1] + O[1]))
    v.SetWidth(pcbnew.FromMM(0.6))
    v.SetDrill(pcbnew.FromMM(0.3))
    v.SetNet(ni)
    board.Add(v)
    pcbnew.SaveBoard(ROUTED, board)
    print("VIN_RAW: second via at", b)


if __name__ == "__main__":
    second_via() if "--via" in sys.argv else main()
