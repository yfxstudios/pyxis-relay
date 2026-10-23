"""Finishing steps on the routed board, in seconds: run this after a small change instead of gen/route.py.

  gen/route.py   placement and routing (about 10 minutes), saves ../routed.kicad_pcb (no copper pours)
  gen/finish.py  duplicate vias out, GND pours on all four layers, fill; saves ../relay.kicad_pcb

Small fixes to the routing itself can be scripted against routed.kicad_pcb and finished with this.
"""
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from pcb import O, W, H  # noqa: E402

ROUTED = os.path.join(ROOT, "routed.kicad_pcb")
OUT = os.path.join(ROOT, "relay.kicad_pcb")


def mm(x, y):
    return pcbnew.VECTOR2I_MM(float(O[0] + x), float(O[1] + y))


def prune_dead_ends(board, netcode, keep=frozenset()):
    """Removes tracks with a free end and vias joined on one layer or none, on one net, until none are left.
    Items whose uuid is in keep stay (an RK628D ball's dogbone waiting for its route)."""
    layers = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
    while True:
        board.BuildConnectivity()
        conn = board.GetConnectivity()
        dead = [t for t in board.GetTracks() if t.GetNetCode() == netcode and t.m_Uuid.AsString() not in keep and (
            (t.GetClass() == "PCB_VIA" and sum(conn.IsConnectedOnLayer(t, l) for l in layers) <= 1) or
            (t.GetClass() != "PCB_VIA" and conn.TestTrackEndpointDangling(t, False)))]
        if not dead:
            return
        for t in dead:
            board.Remove(t)
        GRAVEYARD.extend(dead)    # removed items stay referenced until the run ends (pcbnew's Python layer
        #                           breaks if they are freed while other proxies of them exist)


GRAVEYARD = []


def finish(board):
    # two routes can each drop a via on the same spot of the same net: keep one
    # (positions read as plain numbers first: removing an item while a proxy of its position is alive breaks
    # pcbnew's Python layer)
    seen, doomed = set(), []
    for v in [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]:
        key = (v.GetNetCode(), round(pcbnew.ToMM(v.GetPosition().x), 2), round(pcbnew.ToMM(v.GetPosition().y), 2))
        if key in seen:
            doomed.append(v)
        else:
            seen.add(key)
    for v in doomed:
        board.Remove(v)
    GRAVEYARD.extend(doomed)
    dupes = len(doomed)
    # planes: L2 and L3 solid GND (L3 gets power islands with the power routing), GND pours on L1 and L4
    for z in list(board.Zones()):
        board.Remove(z)
    gnd = board.FindNet("GND")
    for layer in (pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(gnd)
        ol = z.Outline()
        ol.NewOutline()
        for x, y in ((0, 0), (W, 0), (W, H), (0, H)):
            p = mm(x, y)
            ol.Append(p.x, p.y)
        z.SetLocalClearance(pcbnew.FromMM(0.2))
        z.SetMinThickness(pcbnew.FromMM(0.2))
        z.SetThermalReliefGap(pcbnew.FromMM(0.25))
        z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.3))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)  # SMD pads solid, through-hole pads with spokes
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        board.Add(z)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    return dupes


if __name__ == "__main__":
    # KiCad keeps the net classes and design rules in the project file next to the board, and SaveBoard rewrites
    # it from what the board was loaded with: give the checkpoint the real project rules first
    import shutil
    shutil.copy(os.path.join(ROOT, "relay.kicad_pro"), ROUTED.replace(".kicad_pcb", ".kicad_pro"))
    b = pcbnew.LoadBoard(ROUTED)
    n = finish(b)
    pcbnew.SaveBoard(OUT, b)
    print(f"wrote {OUT}: {n} duplicate vias removed, pours filled")
