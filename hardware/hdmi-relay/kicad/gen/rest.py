"""The rest of the board, section by section, on the routed checkpoint (../routed.kicad_pcb), then gen/finish.py.

  .../bin/python3 gen/rest.py ethernet [m2 io sdi power]

Each section can be re-run on its own: it first takes out whatever it drew before (by net), then draws again.
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
from pcb import NETCLASSES, O, W, H  # noqa: E402
from router import Router  # noqa: E402


class Board:
    """Small helpers in board millimetres (origin at the board's top-left corner)."""

    def __init__(self, board):
        self.b = board

    def mm(self, x, y):
        return pcbnew.VECTOR2I_MM(float(O[0] + x), float(O[1] + y))

    def xy(self, item):
        v = item.GetPosition()
        return pcbnew.ToMM(v.x) - O[0], pcbnew.ToMM(v.y) - O[1]

    def fp(self, ref):
        return self.b.FindFootprintByReference(ref)

    def pad(self, ref, num):
        return self.fp(ref).FindPadByNumber(num)

    def net(self, short):
        for n, item in self.b.GetNetsByName().items():
            if str(n) == short or str(n).endswith("/" + short):
                return item
        raise SystemExit(f"no net {short}")

    def place(self, ref, x, y, rot=0, back=False):
        f = self.fp(ref)
        if f.IsFlipped() != back:
            f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        f.SetOrientationDegrees(rot)
        f.SetPosition(self.mm(x, y))

    def clear_nets(self, names):
        for t in list(self.b.GetTracks()):
            if t.GetNetname().split("/")[-1] in names:
                self.b.Remove(t)

    def gnd_vias(self, R, refs, size=(0.45, 0.25), only_unconnected=False):
        """A GND via beside each GND pad of these parts, joined by a short trace on the pad's layer. With
        only_unconnected, pads that already have GND copper on them (a track or via) are skipped."""
        gnd = self.net("GND")
        gc = gnd.GetNetCode()
        missing = []
        mine = [t for t in self.b.GetTracks() if t.GetNetCode() == gc] if only_unconnected else []
        for ref in refs:
            for p in self.fp(ref).Pads():
                if p.GetNetCode() != gc or p.HasHole():
                    continue
                if only_unconnected and any(p.HitTest(t.GetPosition() if t.GetClass() == "PCB_VIA" else t.GetStart())
                                            or (t.GetClass() != "PCB_VIA" and p.HitTest(t.GetEnd())) for t in mine):
                    continue
                layer = pcbnew.B_Cu if self.fp(ref).IsFlipped() else pcbnew.F_Cu
                vb = R.blocked(gc, size[0] / 2, [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]).any(axis=0)
                tb = R.blocked(gc, 0.125, [layer])[0]
                vias = [self.xy(t) for t in self.b.GetTracks() if t.GetClass() == "PCB_VIA"]
                x, y = self.xy(p)
                spot = None
                for rad in np.arange(0.5, 1.8, 0.1):
                    for a in range(0, 360, 15):
                        vx, vy = x + rad * math.cos(math.radians(a)), y + rad * math.sin(math.radians(a))
                        i, j = int(round((vx - R.x0) / R.res)), int(round((vy - R.y0) / R.res))
                        if not (0 <= i < R.nx and 0 <= j < R.ny) or vb[j, i]:
                            continue
                        if any(math.dist((vx, vy), v) < size[1] + 0.45 for v in vias):
                            continue
                        steps = max(2, int(rad / R.res))
                        if all(not tb[int(round((y + (vy - y) * s / steps - R.y0) / R.res)),
                                       int(round((x + (vx - x) * s / steps - R.x0) / R.res))]
                               or math.dist((x + (vx - x) * s / steps, y + (vy - y) * s / steps), (x, y)) < 0.4
                               for s in range(steps + 1)):
                            spot = (vx, vy)
                            break
                    if spot:
                        break
                if not spot:
                    missing.append(f"{ref}.{p.GetNumber()}")
                    continue
                v = pcbnew.PCB_VIA(self.b)
                v.SetPosition(self.mm(*spot)); v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                v.SetWidth(pcbnew.FromMM(size[0])); v.SetDrill(pcbnew.FromMM(size[1])); v.SetNet(gnd)
                self.b.Add(v)
                t = pcbnew.PCB_TRACK(self.b)
                t.SetStart(self.mm(x, y)); t.SetEnd(self.mm(*spot)); t.SetWidth(pcbnew.FromMM(0.25))
                t.SetLayer(layer); t.SetNet(gnd)
                self.b.Add(t)
                R.changed()
        return missing


# ------------------------------------------------------------------ Ethernet
# The CM3's PHY pairs come out at the west end of J69 (J701): MDI0 and MDI1 on the north pad row, MDI2 and MDI3 on
# the south row. All four run on L1 (over the L2 plane), drawn by hand like the CSI lanes:
#   - MDI0 and MDI1 leave northwards; MDI2 and MDI3 go up into the gap between J69's pad rows, west out of it and
#     north round the connector's end.
#   - Four lanes run east under the module, between J1's bottom pins and the CM3's mounting hole (MDI3 north,
#     MDI0 south), turn south past the hole and come down into the magjack J301 through the gap in its LED row.
#   - MDI0 and MDI3 turn into the jack's first pin row from the strip between it and the LED row, MDI1 and MDI2
#     into the second row from the strip between the two rows. That way each pair meets its pins with P and N on
#     the right sides (no crossing), and no pair passes another's pins.
MDI_W, MDI_GAP = NETCLASSES["DIFF_100R"][4], NETCLASSES["DIFF_100R"][5]


def chamfer(pts, d=0.6):
    """45-degree corners: each corner point replaced by two points d mm back along its segments."""
    out = [pts[0]]
    for a, b_, c in zip(pts, pts[1:], pts[2:]):
        la, lc = math.dist(a, b_), math.dist(b_, c)
        k1, k2 = min(d, la / 2) / la, min(d, lc / 2) / lc
        out += [(b_[0] + (a[0] - b_[0]) * k1, b_[1] + (a[1] - b_[1]) * k1),
                (b_[0] + (c[0] - b_[0]) * k2, b_[1] + (c[1] - b_[1]) * k2)]
    return out + [pts[-1]]


def draw_pair(B, centre, start_pads, end_pads, width, gap):
    """Two traces along a centreline (offset half the pitch each way), each joined to its pads at both ends.
    start_pads/end_pads: (P pad, N pad). The side P is on is taken from the start and must hold at the end."""
    from pairs import length, offset
    half = (width + gap) / 2
    left, right = offset(centre, -half), offset(centre, half)
    p0, n0 = B.xy(start_pads[0]), B.xy(start_pads[1])
    if math.dist(left[0], p0) > math.dist(left[0], n0):
        left, right = right, left
    p1, n1 = B.xy(end_pads[0]), B.xy(end_pads[1])
    assert math.dist(left[-1], p1) < math.dist(left[-1], n1), "pair would cross"
    for pad_s, pts, pad_e in ((start_pads[0], left, end_pads[0]), (start_pads[1], right, end_pads[1])):
        full = [B.xy(pad_s)] + pts + [B.xy(pad_e)]
        ni = pad_s.GetNet()
        for a, b_ in zip(full, full[1:]):
            if math.dist(a, b_) < 1e-4:
                continue
            t = pcbnew.PCB_TRACK(B.b)
            t.SetStart(B.mm(*a)); t.SetEnd(B.mm(*b_)); t.SetWidth(pcbnew.FromMM(width))
            t.SetLayer(pcbnew.F_Cu); t.SetNet(ni)
            B.b.Add(t)
        yield length(full)


def rejoin_ball(B, ball):
    """An RK628D inner ball whose via went with a pruned route: a new via at a free site beside it (0.3 mm, as in
    gen/route.py's fanout) and a way out of the ball field on the back or L3. Returns the net's copper."""
    b = B.b
    bx, by = B.xy(ball)
    nc = ball.GetNetCode()
    RF = Router(b, O, (W, H), (35.0, 11.0, 55.0, 30.0), res=0.025, clearance=0.1)
    vb = RF.blocked(nc, 0.175, [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]).any(axis=0)
    sites = [(bx + dx, by + dy) for dx in (-0.325, 0.325) for dy in (-0.325, 0.325)
             if not vb[int(round((by + dy - RF.y0) / RF.res)), int(round((bx + dx - RF.x0) / RF.res))]]
    if not sites:
        return []
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(B.mm(*sites[0])); v.SetViaType(pcbnew.VIATYPE_THROUGH); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetWidth(pcbnew.FromMM(0.3)); v.SetDrill(pcbnew.FromMM(0.15)); v.SetNet(ball.GetNet())
    b.Add(v)
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(B.mm(bx, by)); t.SetEnd(B.mm(*sites[0])); t.SetWidth(pcbnew.FromMM(0.1))
    t.SetLayer(pcbnew.F_Cu); t.SetNet(ball.GetNet())
    b.Add(t)
    RF.changed()
    RF.connect(ball.GetNetname(), [v, (bx + 6.5, by + 2.0)], 0.1, layers=[pcbnew.B_Cu, pcbnew.In2_Cu],
               via=(0.3, 0.15), window=4.0)
    return [x for x in b.GetTracks() if x.GetNetCode() == nc]


def ethernet(B, log):
    b = B.b
    B.clear_nets({"MDI0_P", "MDI0_N", "MDI1_P", "MDI1_N", "MDI2_P", "MDI2_N", "MDI3_P", "MDI3_N",
                  "CT1", "CT2", "CT3", "CT4"})
    # centre-tap capacitors on the back, each beside its jack pin
    B.place("C301", 90.9, 76.46, 90, back=True)    # CT1, pin 12
    B.place("C302", 93.84, 80.9, 0, back=True)     # CT2, pin 6
    B.place("C303", 104.0, 80.9, 0, back=True)     # CT3, pin 1
    B.place("C304", 106.95, 76.46, 90, back=True)  # CT4, pin 7
    jp = lambda n: B.xy(B.pad("J301", n))     # noqa: E731
    jm = lambda n: B.xy(B.pad("J701", n))     # noqa: E731
    row1, row2, led = jp("8")[1], jp("2")[1], jp("13")[1]
    strip1 = (led + row1) / 2 + 0.05           # between the LED row and the first pin row
    strip2 = (row1 + row2) / 2                 # between the two pin rows
    # east lanes (y) between J1's bottom pins and the CM3's mounting hole MH4, and where each pair turns south (x)
    lane = {"MDI3": 61.15, "MDI2": 61.85, "MDI1": 62.55, "MDI0": 63.2}
    down = {"MDI0": 97.4, "MDI1": 98.3, "MDI2": 99.2, "MDI3": 100.1}
    chan = {"MDI3": jm("3")[1] - 1.04, "MDI2": jm("3")[1] - 1.64}   # lanes in the gap between J69's pad rows
    west = {"MDI3": 56.6, "MDI2": 57.4}                               # runs north round J69's west end
    pairs = [  # pair, J701 P/N pads, J301 P/N pins, strip the pair turns into its pins from
        ("MDI0", "12", "10", "11", "10", strip1),
        ("MDI1", "4", "6", "4", "5", strip2),
        ("MDI2", "11", "9", "3", "2", strip2),
        ("MDI3", "3", "5", "8", "9", strip1),
    ]
    out = []
    for name, sp, sn, ep, en, strip in pairs:
        x0 = (jm(sp)[0] + jm(sn)[0]) / 2
        y0 = jm(sp)[1]
        x1 = (jp(ep)[0] + jp(en)[0]) / 2
        y_pins = jp(ep)[1]
        if name in ("MDI0", "MDI1"):                       # north pad row: straight up to the lane
            path = [(x0, y0), (x0, lane[name])]
        else:                                              # south row: up into the gap, west, then north
            path = [(x0, y0), (x0, chan[name]), (west[name], chan[name]), (west[name], lane[name])]
        path += [(down[name], lane[name]), (down[name], strip), (x1, strip),
                 (x1, strip + (0.45 if y_pins > strip else -0.45))]
        # a tight first corner (it is right beside J69's pads), 0.6 mm ones elsewhere
        centre = chamfer(path[:3], 0.25)[:-1] + chamfer(path[1:], 0.6)[1:] if len(path) > 3 else chamfer(path)
        centre[0], centre[-1] = path[0], path[-1]
        lp, ln = draw_pair(B, centre, (B.pad("J701", sp), B.pad("J701", sn)), (B.pad("J301", ep), B.pad("J301", en)),
                           MDI_W, MDI_GAP)
        out.append(f"{name} P {lp:.1f} N {ln:.1f} mm")
    R = Router(b, O, (W, H), (40.0, 40.0, 115.0, 99.0), clearance=0.13)
    # The RK628D's lines to J69 were routed before these lanes: take out their copper near J69 (and whatever dead
    # end that leaves), then join each one to its pin again around the lanes.
    to_j69 = ["RK628D_INT", "RK628D_PLUGIN_DET", "RK628D_RESET_N", "I2C_628_SCL", "I2C_628_SDA", "CEC_GPIO",
              "RK628D_PWR_EN"]
    lane_box = (55.0, 58.0, 102.0, 70.0)
    for t in list(b.GetTracks()):
        if t.GetNetname().split("/")[-1] in to_j69:
            pts = [B.xy(t)] if t.GetClass() == "PCB_VIA" else [
                (pcbnew.ToMM(t.GetStart().x) - O[0], pcbnew.ToMM(t.GetStart().y) - O[1]),
                (pcbnew.ToMM(t.GetEnd().x) - O[0], pcbnew.ToMM(t.GetEnd().y) - O[1])]
            if any(lane_box[0] < x < lane_box[2] and lane_box[1] < y < lane_box[3] for x, y in pts):
                b.Remove(t)
    from finish import prune_dead_ends
    for nm in to_j69:
        prune_dead_ends(b, B.net(nm).GetNetCode())
    R.changed()
    RL = Router(b, O, (W, H), (12.0, 0.0, 115.0, 99.0), clearance=0.13)    # these run up to the RK628D
    for nm in to_j69:
        items = [t for t in b.GetTracks() if t.GetNetCode() == B.net(nm).GetNetCode()]
        pads = [p for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetCode() == B.net(nm).GetNetCode()]
        j69 = [p for p in pads if p.GetParentFootprint().GetReference() == "J701"]
        rest = [p for p in pads if p not in j69]
        if not items and any(p.GetParentFootprint().GetReference() == "U201" for p in rest):
            items = rejoin_ball(B, [p for p in rest if p.GetParentFootprint().GetReference() == "U201"][0])
        left = RL.connect(B.net(nm).GetNetname(), [items + rest] + j69, 0.127, window=8.0, max_expand=4000000,
                          greed=1.3)
        if left:
            out.append(f"{nm} not rejoined to J69")
        prune_dead_ends(b, B.net(nm).GetNetCode())
    for ref, pin in (("C301", "12"), ("C302", "6"), ("C303", "1"), ("C304", "7")):
        nm = B.pad("J301", pin).GetNetname()
        R.connect(nm, [B.pad("J301", pin)] + [p for p in B.fp(ref).Pads() if p.GetNetname() == nm], 0.25,
                  layers=[pcbnew.B_Cu])
    miss = B.gnd_vias(R, ["C301", "C302", "C303", "C304"])
    log("Ethernet: " + "; ".join(out) + (f"; no GND via at {', '.join(miss)}" if miss else ""))


# ------------------------------------------------------------------ M.2 Wi-Fi + Bluetooth
M2 = (16.0, 27.0, 0)            # socket centre; odd pins (PCIe, USB) on the north row, the 2230 card lies south
M2_STANDOFF = (16.0, 55.0)      # card hold-down, ~30 mm along the card: check against the socket's card stop line


def sync_footprints(B, wanted):
    """Puts the footprints the schematic now names on the board (replacing old ones or adding them), with their
    pad nets from the netlist. wanted: {ref: (lib_id, (x, y, rotation))}. Every new footprint is loaded before
    anything is removed: once a footprint has been removed from the board, pcbnew's loader returns unusable
    objects for the rest of the process."""
    from pcb import load_fp, netlist
    b = B.b
    comps, nets = netlist()
    new, olds, keep = {}, {}, {}
    for ref, (lib_id, at) in wanted.items():
        old = B.fp(ref)
        if old is None or str(old.GetFPID().GetUniStringLibId()) != lib_id:
            new[ref] = load_fp(lib_id)
            olds[ref] = old
        else:
            keep[ref] = old
    # (lookups after a footprint is removed return unusable objects too: everything is fetched before)
    for ref, old in olds.items():
        if old is not None:
            b.Remove(old)
    for ref, (lib_id, at) in wanted.items():
        fp = keep.get(ref)
        if ref in new:
            fp = new[ref]
            fp.SetReference(ref)
            fp.SetValue(comps[ref]["value"])
            b.Add(fp)
        fp.SetOrientationDegrees(at[2])
        fp.SetPosition(B.mm(at[0], at[1]))
        for p in fp.Pads():
            name = nets.get((ref, p.GetNumber()))
            if name:
                ni = b.FindNet(name)
                if ni is None:
                    ni = pcbnew.NETINFO_ITEM(b, name)
                    b.Add(ni)
                p.SetNet(ni)


def m2_parts(B, log):
    """Footprint swap only, and it ends the run (see sync_footprints): run it on its own, then the next sections."""
    from finish import ROUTED
    sync_footprints(B, {"J501": ("Connector_PCBEdge:TE_M.2_E_2x38-1MP_P0.5mm", M2),
                        "H501": ("MountingHole:MountingHole_2.2mm_M2_Pad_Via", M2_STANDOFF + (0,))})
    pcbnew.SaveBoard(ROUTED, B.b)
    log("M.2: TE socket and card standoff placed; saved (run the next sections in a new run)")
    os._exit(0)


def m2(B, log):
    """PCIe x1 and USB 2.0 to the M.2 socket, its control lines, 3.3 V decoupling and AC coupling. The PCIe and USB
    pairs go through the grid router as pairs (two vias side by side where they change layer)."""
    from pairroute import route_pair
    b = B.b
    nets = {"PCIE_REFCLK_P", "PCIE_REFCLK_N", "PCIE_RX_P", "PCIE_RX_N", "PCIE_TX_P", "PCIE_TX_N", "M2_PER_P",
            "M2_PER_N", "USB_BT_DP", "USB_BT_DM", "PCIE_PERST_N", "PCIE_CLKREQ_N", "PCIE_WAKE_N", "WIFI_DISABLE_N",
            "BT_DISABLE_N"}
    B.clear_nets(nets)
    # AC coupling on the host's transmit pair, just north of the card's PER pins (41, 43), host side to the north
    B.place("C501", 16.55, 20.3, 90)
    B.place("C502", 17.45, 20.3, 90)
    for ref in ("C501", "C502"):           # turn each so its M2_PER pad faces the socket (south)
        f = B.fp(ref)
        per = [p for p in f.Pads() if "M2_PER" in p.GetNetname()][0]
        if B.xy(per)[1] < B.xy(f)[1]:
            f.SetOrientationDegrees(270)
    # 3.3 V decoupling at the socket's supply pins (2, 4 and 72, 74) and the control-line pull-ups, on the back
    # under the socket (the card covers the front)
    for ref, x, y in (("C503", 7.25, 33.2), ("C505", 9.6, 33.2), ("C504", 24.75, 33.2), ("C506", 22.4, 33.2)):
        B.place(ref, x, y, 0, back=True)
    for k, ref in enumerate(("R501", "R502", "R503", "R504", "R505")):
        B.place(ref, 15.0 + 1.4 * k, 35.0, 90, back=True)
    R = Router(b, O, (W, H), (0.0, 0.0, 100.0, 75.0), clearance=0.13)
    jp = lambda n: B.xy(B.pad("J702", n))    # noqa: E731
    mp = lambda n: B.xy(B.pad("J501", n))    # noqa: E731
    north_m2 = mp("35")[1] - 0.775 - 0.6
    pcie_w, pcie_gap = NETCLASSES["PCIE_85R"][4], NETCLASSES["PCIE_85R"][5]
    usb_w, usb_gap = NETCLASSES["USB_90R"][4], NETCLASSES["USB_90R"][5]
    tx_p = [p for p in B.fp("C501").Pads() if "PCIE_TX" in p.GetNetname()][0]
    tx_n = [p for p in B.fp("C502").Pads() if "PCIE_TX" in p.GetNetname()][0]
    jobs = [  # name, start P/N pads, end P/N pads, start, end, anchors, width, gap
        ("REFCLK", B.pad("J702", "10"), B.pad("J702", "12"), B.pad("J501", "47"), B.pad("J501", "49"),
         pcie_w, pcie_gap, "north"),
        ("PCIe RX", B.pad("J702", "16"), B.pad("J702", "18"), B.pad("J501", "35"), B.pad("J501", "37"),
         pcie_w, pcie_gap, "north"),
        ("PCIe TX", B.pad("J702", "22"), B.pad("J702", "24"), tx_p, tx_n, pcie_w, pcie_gap, "north"),
        ("USB BT", B.pad("J703", "63"), B.pad("J703", "65"), B.pad("J501", "3"), B.pad("J501", "5"),
         usb_w, usb_gap, "west"),
    ]
    out = []
    for name, sp, sn, ep, en, w, g, side in jobs:
        a0 = ((B.xy(sp)[0] + B.xy(sn)[0]) / 2, (B.xy(sp)[1] + B.xy(sn)[1]) / 2)
        start = (a0[0], a0[1] - 1.2) if side == "north" else (a0[0] - 1.2, a0[1])
        a1 = ((B.xy(ep)[0] + B.xy(en)[0]) / 2, (B.xy(ep)[1] + B.xy(en)[1]) / 2)
        end = (a1[0], a1[1] - 1.3)
        r = route_pair(R, b, O, (sp, ep), (sn, en), (start, end), w, g, layers=(pcbnew.F_Cu, pcbnew.B_Cu),
                       window=10.0, max_expand=4000000, anchors=(a0, a1))
        out.append(f"{name}: " + ("NO PATH" if r is None else
                                  f"P {r[0]:.1f} N {r[1]:.1f} mm" + (" CROSSED" if r[2] else "")))
    left = []
    for nm in ("M2_PER_P", "M2_PER_N"):
        left += R.connect(B.net(nm).GetNetname(), [p for fp in b.GetFootprints() for p in fp.Pads()
                                                   if p.GetNetname().split("/")[-1] == nm], 0.14, window=3.0)
    for nm in ("PCIE_PERST_N", "PCIE_CLKREQ_N", "PCIE_WAKE_N", "WIFI_DISABLE_N", "BT_DISABLE_N"):
        pads = [p for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname().split("/")[-1] == nm]
        left += R.connect(B.net(nm).GetNetname(), pads, 0.127, window=8.0, max_expand=4000000, greed=1.3)
    # 3.3 V: the socket pins, their capacitors and the pull-ups (the trunk from the converter comes with the power)
    v33 = [p for ref in ("J501", "C503", "C504", "C505", "C506", "R501", "R502", "R503", "R504", "R505")
           for p in B.fp(ref).Pads() if p.GetNetname().split("/")[-1] == "3V3_IO"]
    left += R.connect(B.net("3V3_IO").GetNetname(), v33, 0.3, window=6.0)
    miss = B.gnd_vias(R, ["C503", "C504", "C505", "C506"])
    gnd_pins = [p for p in B.fp("J501").Pads() if p.GetNetname() == "GND"]
    log("M.2: " + "; ".join(out) + f"; not connected: {len(left)}" + (f"; no GND via at {miss}" if miss else ""))


# ------------------------------------------------------------------ placement: M.2 area and power section
# Placement only: the routing of these areas is done by hand in KiCad. Parts that move lose their old traces
# (anything with an end on them is taken out, then dead ends), so nothing is left pointing at an old spot.

GRAVEYARD = []


def rip_around(B, refs, keep_nets=("GND",)):
    """Takes out tracks and vias with an end on these parts' pads, then the dead ends that leaves."""
    from finish import prune_dead_ends
    b = B.b
    pads = [p for r in refs for p in B.fp(r).Pads() if p.GetNetname() not in keep_nets]
    hit_nets, doomed = set(), []
    for t in b.GetTracks():
        if t.GetNetname() in keep_nets:
            continue
        # plain coordinates, not pcbnew vectors: removing an item while vectors of it are still referenced
        # corrupts pcbnew's Python layer
        ends = [(t.GetPosition().x, t.GetPosition().y)] if t.GetClass() == "PCB_VIA" else \
            [(t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)]
        if any(p.GetNetCode() == t.GetNetCode() and p.HitTest(pcbnew.VECTOR2I(int(x), int(y)))
               for p in pads for x, y in ends):
            hit_nets.add(t.GetNetCode())
            doomed.append(t)
    for t in doomed:
        b.Remove(t)
    GRAVEYARD.extend(doomed)          # kept alive until the run ends
    for nc in hit_nets:
        prune_dead_ends(b, nc)
    return hit_nets


def rip_crossing(B, refs):
    """Takes out tracks of other nets that come too close to these parts' pads (and the dead ends left)."""
    from finish import prune_dead_ends
    b = B.b
    pads = [(B.xy(p), pcbnew.ToMM(p.GetBoundingBox().GetWidth()) / 2, pcbnew.ToMM(p.GetBoundingBox().GetHeight()) / 2,
             p.GetNetCode(), p.IsOnLayer(pcbnew.F_Cu), p.IsOnLayer(pcbnew.B_Cu)) for r in refs for p in B.fp(r).Pads()]
    doomed, nets_hit = [], set()
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            segs = [((pcbnew.ToMM(t.GetPosition().x) - O[0], pcbnew.ToMM(t.GetPosition().y) - O[1]),) * 2]
            w, on = pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2, (True, True)
        else:
            segs = [((pcbnew.ToMM(t.GetStart().x) - O[0], pcbnew.ToMM(t.GetStart().y) - O[1]),
                     (pcbnew.ToMM(t.GetEnd().x) - O[0], pcbnew.ToMM(t.GetEnd().y) - O[1]))]
            w, on = pcbnew.ToMM(t.GetWidth()) / 2, (t.GetLayer() == pcbnew.F_Cu, t.GetLayer() == pcbnew.B_Cu)
        nc = t.GetNetCode()
        for (cx, cy), hw, hh, pnc, pf, pb in pads:
            if pnc == nc or not ((on[0] and pf) or (on[1] and pb)):
                continue
            (x0, y0), (x1, y1) = segs[0]
            # sample the segment: close enough to the pad rectangle (with 0.13 mm clearance) means it crosses
            n = max(2, int(math.dist((x0, y0), (x1, y1)) / 0.05))
            if any(abs(x0 + (x1 - x0) * k / n - cx) < hw + w + 0.13 and abs(y0 + (y1 - y0) * k / n - cy) < hh + w + 0.13
                   for k in range(n + 1)):
                doomed.append(t)
                nets_hit.add(nc)
                break
    for t in doomed:
        b.Remove(t)
    GRAVEYARD.extend(doomed)
    for nc in nets_hit:
        prune_dead_ends(b, nc)
    return nets_hit


def courtyard(B, fp):
    side = pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd
    c = fp.GetCourtyard(side)
    bb = c.BBox() if c.OutlineCount() else fp.GetBoundingBox()
    return (pcbnew.ToMM(bb.GetLeft()) - O[0], pcbnew.ToMM(bb.GetTop()) - O[1],
            pcbnew.ToMM(bb.GetRight()) - O[0], pcbnew.ToMM(bb.GetBottom()) - O[1])


# places the front must keep clear of: under the CM3, under the M.2 card (2230: 22 x 30 mm, south of the socket)
FRONT_KEEPOUT = [(35.4, 29.7, 96.6, 70.3), (4.5, 32.0, 27.5, 58.5)]


def place_near(B, R, ref, targets, back=False, span=6.0, step=0.1, rots=(0, 90, 180, 270), keepout=None):
    """Puts a part where its pads are clear of other nets' copper and its courtyard clear of the other parts on
    its side, as close as possible to targets {net: (x, y)} (or to a point given as targets['*'])."""
    b = B.b
    fp = B.fp(ref)
    if fp.IsFlipped() != back:
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    keepout = (FRONT_KEEPOUT if not back else []) if keepout is None else keepout
    layer = pcbnew.B_Cu if back else pcbnew.F_Cu
    others = [courtyard(B, f) for f in b.GetFootprints() if f.GetReference() != ref and f.IsFlipped() == back
              and courtyard(B, f)[0] < 150]
    pads0 = []
    fp.SetOrientationDegrees(0)
    fp.SetPosition(B.mm(0, 0))
    for p in fp.Pads():
        q = B.xy(p)
        bb = p.GetBoundingBox()
        pads0.append((q[0], q[1], pcbnew.ToMM(bb.GetWidth()) / 2, pcbnew.ToMM(bb.GetHeight()) / 2,
                      p.GetNetname().split("/")[-1], p.GetNetCode(), p.HasHole()))
    sums = {}
    best = None
    tx = [t for t in targets.values()]
    cx0 = sum(t[0] for t in tx) / len(tx); cy0 = sum(t[1] for t in tx) / len(tx)
    for rot in rots:
        fp.SetOrientationDegrees(rot)
        cb = courtyard(B, fp)
        cs, sn = round(math.cos(math.radians(rot))), round(math.sin(math.radians(rot)))
        sx = -1 if back else 1      # a flipped footprint's local x is mirrored
        pr = [(sx * dx * cs + dy * sn, -sx * dx * sn + dy * cs, hw if rot in (0, 180) else hh,
               hh if rot in (0, 180) else hw, nm, nc) for dx, dy, hw, hh, nm, nc, _ in pads0]
        for gy in np.arange(-span, span + 1e-6, step):
            for gx in np.arange(-span, span + 1e-6, step):
                x, y = cx0 + gx, cy0 + gy
                cost = sum(math.dist((x + q[0], y + q[1]), targets[q[4]]) for q in pr if q[4] in targets) or \
                    math.dist((x, y), targets.get("*", (x, y)))
                if best and cost >= best[0]:
                    continue
                c = (x + cb[0], y + cb[1], x + cb[2], y + cb[3])
                if c[0] < 0.5 or c[1] < 0.5 or c[2] > W - 0.5 or c[3] > H - 0.5:
                    continue
                if any(not (c[2] <= k[0] or c[0] >= k[2] or c[3] <= k[1] or c[1] >= k[3]) for k in others + keepout):
                    continue
                ok = True
                for q in pr:
                    if q[5] not in sums:
                        from router import Router as _R  # noqa: F401
                        a = R.blocked(q[5], 0.0, [layer])[0]
                        S_ = np.zeros((a.shape[0] + 1, a.shape[1] + 1), np.int32)
                        S_[1:, 1:] = np.cumsum(np.cumsum(a, 0), 1)
                        sums[q[5]] = S_
                    S_ = sums[q[5]]
                    i0 = int(math.floor((x + q[0] - q[2] - R.x0) / R.res)); i1 = int(math.ceil((x + q[0] + q[2] - R.x0) / R.res))
                    j0 = int(math.floor((y + q[1] - q[3] - R.y0) / R.res)); j1 = int(math.ceil((y + q[1] + q[3] - R.y0) / R.res))
                    if i0 < 0 or j0 < 0 or i1 >= R.nx or j1 >= R.ny or \
                            S_[j1 + 1, i1 + 1] - S_[j0, i1 + 1] - S_[j1 + 1, i0] + S_[j0, i0]:
                        ok = False
                        break
                if ok:
                    best = (cost, x, y, rot)
    if best is None:
        if span < 20:
            return place_near(B, R, ref, targets, back, span * 2, step * 2, rots, keepout)
        raise SystemExit(f"no room for {ref}")
    fp.SetOrientationDegrees(best[3])
    fp.SetPosition(B.mm(best[1], best[2]))
    R.changed()
    return best


def pin_xy(B, ref, num):
    return B.xy(B.pad(ref, num))


def placement(B, log):
    """The M.2 socket's neighbours, the M.2 support parts, and the power section laid out converter by converter."""
    b = B.b
    R = Router(b, O, (W, H), (0.0, 0.0, W, H), clearance=0.13)
    # ---- what moves: everything in the power section, the M.2 support parts, and the RK628D power switch's
    # parts that the real (wider) socket now covers. Their old traces go first.
    power = [f.GetReference() for f in b.GetFootprints() if f.GetReference()[:2] in ("C1", "R1", "D1", "F1", "L1",
             "Q1", "U1") and f.GetReference() not in ("C119", "C120", "C121", "C122", "C123", "C125", "R115", "R116",
             "R118", "L104", "U106")]
    m2 = ["C501", "C502", "C503", "C504", "C505", "C506", "R501", "R502", "R503", "R504", "R505"]
    covered = [r for r in ("Q202", "R211", "R212", "C205", "R209", "R210")
               if not (courtyard(B, B.fp(r))[0] >= courtyard(B, B.fp("J501"))[2] or
                       courtyard(B, B.fp(r))[3] <= courtyard(B, B.fp("J501"))[1])]
    movers = power + m2 + covered + ["J101", "J103"]
    ripped = rip_around(B, movers)
    for r in movers:                                  # off the board while the others are placed
        B.fp(r).SetPosition(B.mm(200, 200))
    # also clear any old trace that the real socket's pads now sit on
    rip_around(B, ["J501"])
    R.changed()

    # ---- back-panel connectors: mouths flush with the board edge (USB-C was turned the wrong way)
    B.place("J103", 16.0, 95.8, 0)
    B.place("J101", 42.0, 97.9, -90)
    R.changed()

    # ---- M.2: AC coupling caps just north of the PER pins; 3.3 V decoupling and pull-ups on the back under the
    # socket (the card covers the front)
    per_p, per_n = pin_xy(B, "J501", "41"), pin_xy(B, "J501", "43")
    for ref, pin in (("C501", per_p), ("C502", per_n)):
        place_near(B, R, ref, {next(p.GetNetname().split("/")[-1] for p in B.fp(ref).Pads()
                                    if "M2_PER" in p.GetNetname()): (pin[0], pin[1] - 1.2)}, span=2.5,
                   rots=(90, 270))
    for ref, pins in (("C503", ("2", "4")), ("C505", ("2", "4")), ("C504", ("72", "74")), ("C506", ("72", "74"))):
        pts = [pin_xy(B, "J501", n) for n in pins]
        place_near(B, R, ref, {"3V3_IO": ((pts[0][0] + pts[1][0]) / 2, pts[0][1] + 1.5)}, back=True, span=4)
    for ref in ("R501", "R502", "R503", "R504", "R505"):
        sig = [p.GetNetname().split("/")[-1] for p in B.fp(ref).Pads() if "3V3" not in p.GetNetname()][0]
        pin = [p for p in B.fp("J501").Pads() if p.GetNetname().split("/")[-1] == sig][0]
        place_near(B, R, ref, {sig: (B.xy(pin)[0], B.xy(pin)[1] + 1.5)}, back=True, span=5)
    # the RK628D power switch's covered parts: as near as they fit to what they connect to
    for ref in covered:
        tg = {}
        for p in B.fp(ref).Pads():
            nm = p.GetNetname().split("/")[-1]
            pts = [B.xy(q) for f in b.GetFootprints() if f.GetReference() != ref and courtyard(B, f)[0] < 150
                   for q in f.Pads() if q.GetNetname().split("/")[-1] == nm and nm not in ("GND", "3V3_IO")]
            if pts:
                tg[nm] = (sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts))
        place_near(B, R, ref, tg or {"*": (30.0, 20.5)}, span=4)

    # ---- power: each converter laid out around its IC (positions by hand, the small parts placed next to
    # the pins they serve)
    #   input stage, near the back-panel inputs: OR diodes, fuse, TVS, bulk capacitor, the USB-C PD sink
    fixed = {
        "D101": (49.5, 96.0, 90),       # DC jack -> VIN_RAW
        "D102": (58.5, 89.4, 0),        # NP-F -> VIN_RAW
        "D103": (32.5, 85.0, 0),        # USB-C VBUS (after the P-FET) -> VIN_RAW
        "F101": (50.5, 89.6, 90),       # VIN_RAW -> VIN, polyfuse
        "D104": (55.4, 84.6, 0),        # VIN TVS
        "C102": (67.5, 89.0, 0),        # VIN bulk 47 uF
        "U101": (16.0, 88.3, 90),       # USB data ESD at the connector
        "U102": (25.0, 90.0, 0),        # CH224A PD sink
        "Q101": (29.0, 86.0, 0),        # VBUS switch
        # 5V_SYS converter (SY8303): IC, input caps under it (VIN pin 5 right, GND pins left), inductor east
        "U103": (52.0, 77.5, 0), "C104": (52.0, 80.1, 0), "C105": (52.0, 82.6, 0), "L101": (57.7, 77.8, 0),
        "C107": (61.4, 76.5, 90), "C108": (63.6, 76.5, 90),
        # 5V_SOM converter (SY8303) east of it, output caps toward J69's 5 V pins (south row, x 74-76)
        "U104": (69.0, 77.5, 0), "C109": (69.0, 80.1, 0), "C110": (69.0, 82.6, 0), "L102": (74.7, 77.8, 0),
        "C112": (78.4, 76.5, 90), "C113": (80.6, 76.5, 90),
        # 3V3_IO converter (TPS563201) in the strip between the M.2 card and the module, close to its main load
        "U105": (31.2, 49.5, 180), "C114": (33.4, 47.0, 0), "L103": (32.0, 54.6, 90),
        "C117": (30.4, 59.6, 0), "C118": (33.8, 59.6, 0),
    }
    # in this order, each slid to the nearest free spot (so a loop stays as tight as the parts allow)
    for ref, (x, y, rot) in fixed.items():
        place_near(B, R, ref, {"*": (x, y)}, rots=(rot,), span=4.0)
    #   satellites: next to the pin they connect to
    sat = {
        # 5V_SYS: bootstrap, feedback, frequency set, the shared enable divider
        "C106": ("U103", ("7", "6")), "R106": ("U103", ("1",)), "R107": ("U103", ("1",)), "R105": ("U103", ("2",)),
        "R111": ("U103", ("8",)), "R112": ("U103", ("8",)),
        # 5V_SOM
        "C111": ("U104", ("7", "6")), "R109": ("U104", ("1",)), "R110": ("U104", ("1",)), "R108": ("U104", ("2",)),
        # 3V3_IO: input 100 nF, bootstrap, feedback, enable RC
        "C115": ("U105", ("3",)), "C116": ("U105", ("6", "2")), "R113": ("U105", ("4",)), "R114": ("U105", ("4",)),
        "R117": ("U105", ("5",)), "C124": ("U105", ("5",)),
        # PD sink: CFG resistor, VBUS cap, PG pull-up
        "R101": ("U102", ("9",)), "C101": ("U102", ("1",)), "R102": ("U102", ("10",)),
        # VIN sense divider and filter, near the VIN bus
        "R103": ("C102", ("1",)), "R104": ("C102", ("1",)), "C103": ("C102", ("1",)),
    }
    for ref, (ic, pins) in sat.items():
        pts = [pin_xy(B, ic, n) for n in pins]
        place_near(B, R, ref, {"*": (sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts))},
                   span=3.0)
    #   module 5 V / 3.3 V / 1.8 V decoupling right at J69's pins (south row), and its pull-ups
    j5 = [pin_xy(B, "J701", n) for n in ("77", "79", "81", "83", "85", "87")]
    jx = sum(q[0] for q in j5) / len(j5)
    for k, ref in enumerate(("C704", "C705", "C706", "C707")):
        place_near(B, R, ref, {"*": (jx - 1.5 + 1.0 * k, 72.0)}, span=3.0)
    # old traces of other nets that now run across a newly placed part's pads (or the new socket's) go too
    crossed = rip_crossing(B, movers + ["J501"] + covered)
    log(f"placement: {len(movers)} parts placed; old traces taken out on {len(ripped | crossed)} nets")


SECTIONS = {"ethernet": ethernet, "m2_parts": m2_parts, "m2": m2, "placement": placement}

if __name__ == "__main__":
    from finish import ROUTED, OUT, finish
    shutil.copy(os.path.join(ROOT, "relay.kicad_pro"), ROUTED.replace(".kicad_pcb", ".kicad_pro"))
    board = pcbnew.LoadBoard(ROUTED)
    B = Board(board)
    for name in sys.argv[1:]:
        SECTIONS[name](B, print)
    pcbnew.SaveBoard(ROUTED, board)
    finish(board)
    pcbnew.SaveBoard(OUT, board)
