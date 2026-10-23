"""Routes everything still open on the board, stage by stage, on the routed checkpoint (../routed.kicad_pcb).

  .../bin/python3 gen/autoroute.py [stage ...]     stages: pairs power signals rk628 gnd   (default: all)

Progress goes to ../autoroute.log. After each stage the checkpoint is saved and gen/finish.py's steps run, so
relay.kicad_pcb is always a finished board. What is open comes from KiCad's own DRC (unconnected items).
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from finish import OUT, ROUTED, prune_dead_ends  # noqa: E402
from pairroute import route_pair  # noqa: E402
from pcb import NETCLASSES, O, W, H  # noqa: E402
from rest import Board, place_near, rejoin_ball  # noqa: E402
from router import Router  # noqa: E402

KC = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
LOG = open(os.path.join(ROOT, "autoroute.log"), "a") if __name__ == "__main__" else sys.stdout
T0 = time.time()


def log(*a):
    msg = f"[{time.time() - T0:6.0f}s] " + " ".join(str(x) for x in a)
    print(msg, flush=True)
    LOG.write(msg + "\n")
    LOG.flush()


def short(n):
    return n.split("/")[-1]


# trace width and via by net (mm); everything else takes its net class width
WIDE = [
    (r"^5V_SOM$", 1.2), (r"^(VIN|VIN_RAW|VDC|VNPF|VBUS_C|VBUS_SW)$", 0.8), (r"^(LX_|SW_)", 0.8),
    (r"^5V_SYS$", 0.6), (r"^3V3_IO$", 0.5), (r"^(HDMITX_5V|HDMIRX_5V|1V1_628|RK628D_3V3)$", 0.4),
    (r"^(SOM_3V3|SOM_1V8)$", 0.3),
]


def width_for(name):
    for pat, w in WIDE:
        if re.search(pat, short(name)):
            return w
    for cls, (tw, *_rest, pattern) in NETCLASSES.items():
        if re.search(pattern, short(name)):
            return tw
    return 0.127


def via_for(w):
    return (0.6, 0.3) if w >= 0.5 else (0.45, 0.25)


KP = sys.executable
GRAVE = []
LAST_DRC = []      # the last DRC report (open_nets)


def open_nets(board):
    """Nets KiCad's DRC reports unconnected items on, on the finished board (pours filled). The working board
    never gets pours (removing them again breaks pcbnew's Python layer): it is saved, finished in another process
    and checked there."""
    pcbnew.SaveBoard(ROUTED, board)
    r = subprocess.run([KP, os.path.join(HERE, "finish.py")], capture_output=True, text=True)
    if "wrote " not in r.stdout:                               # a stale relay.kicad_pcb would give a stale report
        raise RuntimeError("finish.py failed:\n" + r.stdout[-2000:] + r.stderr[-2000:])
    rep = os.path.join(ROOT, "freerouting", "check.json")
    os.makedirs(os.path.dirname(rep), exist_ok=True)
    subprocess.run([KC, "pcb", "drc", "--format", "json", "--severity-all", "-o", rep, OUT], capture_output=True)
    d = json.load(open(rep))
    LAST_DRC[:] = [d]
    nets = {}
    for u in d["unconnected_items"]:
        m = re.search(r"\[([^\]]+)\]", u["items"][0]["description"])
        if m:
            nets[m.group(1)] = nets.get(m.group(1), 0) + 1
    bad = [v for v in d["violations"] if v["type"] not in ("silk_overlap", "silk_over_copper", "silk_edge_clearance")]
    return nets, bad


def net_terms(board, nc):
    pads = [p for f in board.GetFootprints() for p in f.Pads() if p.GetNetCode() == nc]
    copper = [t for t in board.GetTracks() if t.GetNetCode() == nc]
    return pads + copper


FINE = []    # the 0.05 mm router, made on first use


def make_router(board, res, box=None):
    """A router keeping the net classes' clearances: 0.10 mm, 0.127 mm next to POWER-class copper."""
    r = Router(board, O, (W, H), box or (0.0, 0.0, W, H), res=res, clearance=0.10)
    pw = NETCLASSES["POWER"][-1]
    for nm, ni in board.GetNetsByName().items():
        if re.search(pw, short(str(nm))):
            r.net_cl[ni.GetNetCode()] = 0.127
    for other in ([ROUTERS[0]] if ROUTERS else []) + (ROUTERS[0].peers if ROUTERS else []):
        r.peers.append(other); other.peers.append(r)
    if not ROUTERS:
        ROUTERS.append(r)
    # L3 is the plane under the back layer: no trace on it under a back-layer high-speed trace
    hs = {ni.GetNetCode() for nm, ni in board.GetNetsByName().items()
          if any(re.search(c[-1], short(str(nm))) for k, c in NETCLASSES.items() if k != "POWER")}
    r.shadow[pcbnew.In2_Cu] = (pcbnew.B_Cu, hs, 0.3)
    return r


ROUTERS = []


def route_net(R, board, name, width=None, layers=(pcbnew.F_Cu, pcbnew.B_Cu), **kw):
    """Joins every piece of a net (pads, existing tracks and vias): on the 0.1 mm grid with a greedy search
    first (fast), then the 0.05 mm grid, then narrower."""
    ni = board.FindNet(name)
    w = width or width_for(name)
    if not FINE:
        FINE.append(make_router(board, 0.05))
    left = None
    tries = [(R, w, via_for(w)), (FINE[0], w, via_for(w))] + \
        [(FINE[0], x, via_for(x)) for x in sorted({min(w, 0.3), 0.127}, reverse=True) if x < w]
    if w <= 0.2:
        tries.append((FINE[0], w, (0.3, 0.15)))             # small vias fit beside 0.4 mm-pitch connector pins
    for router, ww, vv in tries:
        terms = net_terms(board, ni.GetNetCode())
        left = router.connect(name, terms, ww, layers=list(layers), via=vv, window=kw.get("window", 6.0),
                              max_expand=kw.get("max_expand", 1500000), greed=2.0)
        if not left:
            return []
    return left


# ------------------------------------------------------------------ stages
TO_J69 = ["RK628D_INT", "RK628D_PLUGIN_DET", "RK628D_RESET_N", "I2C_628_SCL", "I2C_628_SDA", "CEC_GPIO",
          "RK628D_PWR_EN"]


def stage_rip_j69(board, B, R):
    """The RK628D's seven slow lines down to J69 were routed before the M.2 socket and the pairs had their places,
    straight through where the pairs must go. Their long legs come out (the chip-end escapes stay); they are
    routed again after the pairs (stage j69)."""
    codes = {board.FindNet(n).GetNetCode() if board.FindNet(n) else B.net(n).GetNetCode() for n in TO_J69}
    doomed = []
    for t in board.GetTracks():
        if t.GetNetCode() not in codes:
            continue
        pts = [(t.GetPosition().x, t.GetPosition().y)] if t.GetClass() == "PCB_VIA" else \
            [(t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)]
        if any(pcbnew.ToMM(y) - O[1] > 28.0 or pcbnew.ToMM(x) - O[0] > 52.0 for x, y in pts):
            doomed.append(t)
    for t in doomed:
        board.Remove(t)
    GRAVE.extend(doomed)
    for nc in codes:
        prune_dead_ends(board, nc)
    R.changed()
    log(f"rip_j69: {len(doomed)} track pieces and vias taken out")


def stage_j69(board, B, R):
    fails = []
    for n in TO_J69:
        left = route_net(R, board, B.net(n).GetNetname(), window=10.0)
        if left:
            fails.append(n)
    log(f"j69: rerouted, still open: {fails or 'none'}")


def stage_pairs(board, B, R):
    """PCIe and USB. Each pin gets a straight stub out of its pad row, side by side with its partner's; then the
    two nets are routed one after the other on the fast grid. If the second is walled in by the first, both come
    out (stubs kept) and they go in the other order."""
    pcie_w = NETCLASSES["PCIE_85R"][4]
    usb_w = NETCLASSES["USB_90R"][4]

    def capside(ref):
        return [p for p in B.fp(ref).Pads() if "PCIE_TX" in p.GetNetname()][0]
    jobs = [
        ("REFCLK", ("J702", "10"), ("J702", "12"), ("J501", "47"), ("J501", "49"), pcie_w),
        ("PCIe RX", ("J702", "16"), ("J702", "18"), ("J501", "35"), ("J501", "37"), pcie_w),
        ("PCIe TX", ("J702", "22"), ("J702", "24"), capside("C501"), capside("C502"), pcie_w),
        ("USB BT", ("J703", "63"), ("J703", "65"), ("J501", "3"), ("J501", "5"), usb_w),
        ("USB OTG", ("J702", "5"), ("J702", "3"), ("U101", "6"), ("U101", "4"), usb_w),
        ("USB-C", ("U101", "1"), ("U101", "3"), ("J103", "A6"), ("J103", "A7"), usb_w),
    ]

    def pad(x):
        return B.pad(*x) if isinstance(x, tuple) else x
    for name, sp, sn, ep, en, w in jobs:
        sp, sn, ep, en = pad(sp), pad(sn), pad(ep), pad(en)
        codes = (sp.GetNetCode(), sn.GetNetCode())
        if any(t.GetNetCode() in codes for t in board.GetTracks()):
            log(f"{name}: already has copper, skipped")
            continue
        for p in (sp, sn, ep, en):
            # stubs only on connector pins (rows of pads), and only where the stub keeps its clearance
            if not p.GetParentFootprint().GetReference().startswith("J"):
                continue
            bb = p.GetBoundingBox()
            x, y = B.xy(p)
            pts = [B.xy(q) for q in p.GetParentFootprint().Pads()]
            cx, cy = sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts)
            if bb.GetHeight() > bb.GetWidth():
                end = (x, y + (0.8 + pcbnew.ToMM(bb.GetHeight()) / 2) * (1 if y > cy else -1))
            else:
                end = (x + (0.8 + pcbnew.ToMM(bb.GetWidth()) / 2) * (1 if x > cx else -1), y)
            layer = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
            blk = R.blocked(p.GetNetCode(), w / 2, [layer])[0]
            n = max(2, int(math.dist((x, y), end) / R.res))
            if any(blk[int(round((y + (end[1] - y) * k / n - R.y0) / R.res)),
                       int(round((x + (end[0] - x) * k / n - R.x0) / R.res))] for k in range(n + 1)):
                continue
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(B.mm(x, y)); t.SetEnd(B.mm(*end)); t.SetWidth(pcbnew.FromMM(w))
            t.SetLayer(layer); t.SetNet(p.GetNet())
            board.Add(t)
            R.changed()
        stubs = {t.m_Uuid.AsString() for t in board.GetTracks() if t.GetNetCode() in codes}

        def quick(nm):
            return R.connect(nm, net_terms(board, board.FindNet(nm).GetNetCode()), w,
                             layers=[pcbnew.F_Cu, pcbnew.B_Cu], via=via_for(w), window=8.0, max_expand=1500000,
                             greed=2.0)
        left = []
        for first, second in ((sp, sn), (sn, sp)):
            left = quick(first.GetNetname()) + quick(second.GetNetname())
            if not left:
                break
            doomed = [t for t in board.GetTracks() if t.GetNetCode() in codes and t.m_Uuid.AsString() not in stubs]
            for t in doomed:
                board.Remove(t)
            GRAVE.extend(doomed)
            R.changed()
        for nc in codes:
            prune_dead_ends(board, nc)
        R.changed()
        log(f"{name}: " + ("routed" if not left else f"{len(left)} open"))


POWER_ORDER = ["5V_SOM", "VIN", "VIN_RAW", "VDC", "VNPF", "VBUS_C", "VBUS_SW", "LX_5V", "LX_SOM", "SW_IO", "5V_SYS",
               "3V3_IO", "HDMITX_5V", "HDMIRX_5V", "1V1_628", "RK628D_3V3", "SOM_3V3", "SOM_1V8"]


def stage_power(board, B, R):
    nets, _ = open_nets(board)
    names = {short(n): n for n in nets}
    rk_area = {"1V1_628", "RK628D_3V3", "HDMIRX_5V"}          # under/around the RK628D: stage rk628
    for nm in POWER_ORDER:
        if nm in names and nm not in rk_area:
            left = route_net(R, board, names[nm], window=10.0)
            pcbnew.SaveBoard(ROUTED, board)                    # every net kept as it finishes
            log(f"power {nm}: " + ("done" if not left else f"{len(left)} pieces still apart"))


def stage_signals(board, B, R):
    nets, _ = open_nets(board)
    rk = {"XOUT_628", "RX_SDA", "RX_CEC", "EFUSE_628", "I2S_628_MCLK", "I2C_628_SCL", "I2C_628_SDA", "AVDD_3V3_628",
          "AVDD_1V1_628", "1V1_628", "RK628D_3V3", "I2S_628_SCLK", "RK628D_INT", "RK628D_RESET_N", "HDMIRX_5V"}
    todo = [n for n in nets if short(n) != "GND" and short(n) not in rk and short(n) not in POWER_ORDER]
    # fewest pieces first: short local nets before long ones
    todo.sort(key=lambda n: nets[n])
    fails = []
    for k, n in enumerate(todo):
        left = route_net(R, board, n, window=8.0)
        pcbnew.SaveBoard(ROUTED, board)
        log(f"signal {k + 1}/{len(todo)} {short(n)}: " + ("done" if not left else "open"))
        if left:
            fails.append(short(n))
    log(f"signals: {len(todo)} nets, still open: {fails or 'none'}")


OLD = os.path.join(ROOT, "freerouting", "before_placement.kicad_pcb")   # the board before the power/M.2 placement


def restore_old(board, B, R, names):
    """Copies a net's traces back from the board before the placement changes, piece by piece, wherever a piece
    still keeps its clearance from everything now on the board. Returns how many pieces came back."""
    if not os.path.exists(OLD):
        return 0
    old = pcbnew.LoadBoard(OLD)
    n = 0
    for name in names:
        ni = board.FindNet(name)
        if ni is None:
            continue
        nc = ni.GetNetCode()
        oc = old.FindNet(name).GetNetCode()
        for t in old.GetTracks():
            if t.GetNetCode() != oc:
                continue
            if t.GetClass() == "PCB_VIA":
                x, y = pcbnew.ToMM(t.GetPosition().x) - O[0], pcbnew.ToMM(t.GetPosition().y) - O[1]
                blk = R.blocked(nc, pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2,
                                [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]).any(axis=0)
                if blk[int(round((y - R.y0) / R.res)), int(round((x - R.x0) / R.res))]:
                    continue
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(t.GetPosition()); v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                v.SetWidth(t.GetWidth(pcbnew.F_Cu)); v.SetDrill(t.GetDrillValue()); v.SetNet(ni)
                board.Add(v)
            else:
                layer = t.GetLayer()
                blk = R.blocked(nc, pcbnew.ToMM(t.GetWidth()) / 2, [layer])[0]
                x0, y0 = pcbnew.ToMM(t.GetStart().x) - O[0], pcbnew.ToMM(t.GetStart().y) - O[1]
                x1, y1 = pcbnew.ToMM(t.GetEnd().x) - O[0], pcbnew.ToMM(t.GetEnd().y) - O[1]
                k = max(2, int(math.dist((x0, y0), (x1, y1)) / R.res))
                if any(blk[int(round((y0 + (y1 - y0) * i / k - R.y0) / R.res)),
                           int(round((x0 + (x1 - x0) * i / k - R.x0) / R.res))] for i in range(k + 1)):
                    continue
                c = pcbnew.PCB_TRACK(board)
                c.SetStart(t.GetStart()); c.SetEnd(t.GetEnd()); c.SetWidth(t.GetWidth()); c.SetLayer(layer)
                c.SetNet(ni)
                board.Add(c)
            n += 1
        R.changed()
    return n


def stage_rk628(board, B, R):
    """The RK628D area's leftovers: first its old traces back where they still fit (option 2), then the fine grid
    under and around the chip with the back and L3 allowed (option 1), then the board-wide grid for anything
    further out."""
    nets, _ = open_nets(board)
    todo = [n for n in nets if short(n) != "GND"]
    back = restore_old(board, B, R, todo)
    for n in todo:
        prune_dead_ends(board, board.FindNet(n).GetNetCode())
    R.changed()
    log(f"rk628: {back} old track pieces restored")
    nets, _ = open_nets(board)
    RF = Router(board, O, (W, H), (30.0, 5.0, 60.0, 35.0), res=0.025, clearance=0.1)
    RF.peers = [R] + R.peers
    for r in R.peers:
        r.peers.append(RF)
    R.peers.append(RF)
    fails = []
    for n in [n for n in nets if short(n) != "GND"]:
        ni = board.FindNet(n)
        ball = [p for p in B.fp("U201").Pads() if p.GetNetCode() == ni.GetNetCode()]
        if ball and not [t for t in board.GetTracks() if t.GetNetCode() == ni.GetNetCode()]:
            rejoin_ball(B, ball[0])
        left = RF.connect(n, net_terms(board, ni.GetNetCode()), 0.1,
                          layers=[pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu], via=(0.3, 0.15), window=5.0,
                          max_expand=2500000)
        if left:
            left = route_net(R, board, n, window=10.0)
        prune_dead_ends(board, ni.GetNetCode())
        pcbnew.SaveBoard(ROUTED, board)
        log(f"rk628 {short(n)}: " + ("done" if not left else "open"))
        if left:
            fails.append(short(n))
    log(f"rk628 and leftovers: still open: {fails or 'none'}")


def stage_gnd(board, B, R):
    """A GND via beside every GND pad the pours don't reach, then a stitching grid tying the planes together."""
    for attempt in range(3):
        tmp_nets, _ = open_nets(board)
        if not any(short(n) == "GND" for n in tmp_nets):
            break
        # the GND pads DRC still finds apart (after the pours are filled): a via beside each
        refs = set()
        for u in LAST_DRC[0]["unconnected_items"]:
            for it in u["items"]:
                m = re.match(r"Pad (\S+) \[GND\] of (\S+)", it["description"])
                if m:
                    refs.add(m.group(2))
        miss = B.gnd_vias(R, sorted(refs), only_unconnected=True)
        log(f"gnd pass {attempt + 1}: {len(refs)} parts with GND pads apart; {len(miss)} without room for a via")
    # stitching: a via every 4 mm where nothing else is near
    gnd = board.FindNet("GND")
    vb = R.blocked(gnd.GetNetCode(), 0.45, [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]).any(axis=0)
    n = 0
    y = 2.0
    while y < H - 2:
        x = 2.0
        while x < W - 2:
            i, j = int(round((x - R.x0) / R.res)), int(round((y - R.y0) / R.res))
            if not vb[j, i]:
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(B.mm(x, y)); v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                v.SetWidth(pcbnew.FromMM(0.45)); v.SetDrill(pcbnew.FromMM(0.25)); v.SetNet(gnd)
                board.Add(v)
                n += 1
            x += 4.0
        y += 4.0
    R.changed()
    log(f"gnd: {n} stitching vias")


def stage_holes(board, B, R):
    """Two vias of one net closer than the drill rules allow (each route keeps its holes clear of other nets
    only): the second one goes, and the tracks that ended on it end on the first one instead."""
    _, bad = open_nets(board)
    pairs = [[(i["pos"]["x"], i["pos"]["y"]) for i in v["items"]] for v in bad if v["type"] == "hole_to_hole"
             and len({re.search(r"\[([^\]]+)\]", i["description"]).group(1) for i in v["items"]}) == 1]
    vias = [(t, pcbnew.ToMM(t.GetPosition().x), pcbnew.ToMM(t.GetPosition().y), t.GetNetCode())
            for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    tracks = [(t, pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y), pcbnew.ToMM(t.GetEnd().x),
               pcbnew.ToMM(t.GetEnd().y), t.GetNetCode()) for t in board.GetTracks() if t.GetClass() != "PCB_VIA"]

    def at(x, y):
        return min(vias, key=lambda v: math.hypot(v[1] - x, v[2] - y))
    doomed = []
    for a, b in pairs:
        keep, gone = at(*a), at(*b)
        if gone[0] in doomed or keep[0] in doomed:
            continue
        for t, sx, sy, ex, ey, nc in tracks:
            if nc != gone[3]:
                continue
            if math.hypot(sx - gone[1], sy - gone[2]) < 1e-3:
                t.SetStart(pcbnew.VECTOR2I_MM(keep[1], keep[2]))
            if math.hypot(ex - gone[1], ey - gone[2]) < 1e-3:
                t.SetEnd(pcbnew.VECTOR2I_MM(keep[1], keep[2]))
        doomed.append(gone[0])
    for v in doomed:
        board.Remove(v)
    GRAVE.extend(doomed)
    R.changed()
    log(f"holes: {len(doomed)} vias merged into their neighbours")


def _geom(t):
    """A track or via as plain numbers: (x0, y0, x1, y1, half width, layers or None for every layer)."""
    if t.GetClass() == "PCB_VIA":
        # radius: the copper, or as far as its drill's clearance reaches (0.2 mm drill to copper, less the 0.1 mm
        # copper clearance the callers add)
        x, y = pcbnew.ToMM(t.GetPosition().x), pcbnew.ToMM(t.GetPosition().y)
        return (x, y, x, y, max(pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2, pcbnew.ToMM(t.GetDrillValue()) / 2 + 0.1),
                None)
    return (pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y), pcbnew.ToMM(t.GetEnd().x),
            pcbnew.ToMM(t.GetEnd().y), pcbnew.ToMM(t.GetWidth()) / 2, t.GetLayer())


def _seg_dist(a, b):
    def pd(px, py, x0, y0, x1, y1):
        dx, dy = x1 - x0, y1 - y0
        L = dx * dx + dy * dy
        u = 0 if L == 0 else max(0, min(1, ((px - x0) * dx + (py - y0) * dy) / L))
        return math.hypot(px - x0 - u * dx, py - y0 - u * dy)
    def side(px, py, x0, y0, x1, y1):
        return (x1 - x0) * (py - y0) - (y1 - y0) * (px - x0)
    if (side(a[0], a[1], *b[:4]) * side(a[2], a[3], *b[:4]) < 0 and
            side(b[0], b[1], *a[:4]) * side(b[2], b[3], *a[:4]) < 0):
        return 0.0                                             # they cross
    return min(pd(a[0], a[1], *b[:4]), pd(a[2], a[3], *b[:4]), pd(b[0], b[1], *a[:4]), pd(b[2], b[3], *a[:4]))


def soft_nets(board, exhausted=(), u201_too=False):
    """Low-speed signal nets whose routes a rip-up may take out: Default class, not GND, not power or regulator
    loops, not nets ripped too often already, and (unless u201_too) not the RK628D's ball-grid nets."""
    u201 = {p.GetNetCode() for p in board.FindFootprintByReference("U201").Pads()}
    out = set()
    for nc in {t.GetNetCode() for t in board.GetTracks()}:
        name = short(board.FindNet(nc).GetNetname()) if board.FindNet(nc) else ""
        if (not name or name == "GND" or (nc in u201 and not u201_too) or name in exhausted or name in POWER_ORDER
                or re.match(r"(FB|BS|BST|FS|CT)\d*(_|$)|AVDD|RK628D_3V3|1V1_628", name)   # regulators, rails
                or any(re.search(c[-1], name) for c in NETCLASSES.values())):
            continue
        out.add(nc)
    return out


RK_BOX = (30.0, 5.0, 60.0, 35.0)       # around the RK628D: the 0.025 mm grid
RF = []


def _configs(board, n, w):
    """The routers a net is tried on: the 0.025 mm grid with L3 near the RK628D when the net has a pad there,
    and the 0.05 mm grid on the outer layers."""
    if not FINE:
        FINE.append(make_router(board, 0.05))
    sv = (0.3, 0.15) if w <= 0.2 else via_for(w)
    out = []
    nc = board.FindNet(n).GetNetCode()
    pads = [p for f in board.GetFootprints() for p in f.Pads() if p.GetNetCode() == nc]
    inside = [RK_BOX[0] + 0.5 < pcbnew.ToMM(p.GetPosition().x) - O[0] < RK_BOX[2] - 0.5 and
              RK_BOX[1] + 0.5 < pcbnew.ToMM(p.GetPosition().y) - O[1] < RK_BOX[3] - 0.5 for p in pads]
    if w <= 0.2 and any(inside):
        if not RF:
            r = make_router(board, 0.025, RK_BOX)
            # L2 only inside the ball grid's footprint (already holed by the fanout vias there), and never under a
            # top-layer high-speed trace
            cb = board.FindFootprintByReference("U201").GetCourtyard(pcbnew.F_CrtYd).BBox()
            r.allow[pcbnew.In1_Cu] = (pcbnew.ToMM(cb.GetLeft()) - O[0], pcbnew.ToMM(cb.GetTop()) - O[1],
                                      pcbnew.ToMM(cb.GetRight()) - O[0], pcbnew.ToMM(cb.GetBottom()) - O[1])
            r.shadow[pcbnew.In1_Cu] = (pcbnew.F_Cu, r.shadow[pcbnew.In2_Cu][1], 0.3)
            RF.append(r)
        # (the box router can't see terminals outside it: a net reaching out is finished by the next one)
        out.append((RF[0], [pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu], 0.1, (0.3, 0.15), 5.0, all(inside)))
        out.append((RF[0], [pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu, pcbnew.In1_Cu], 0.1, (0.3, 0.15), 5.0,
                    all(inside)))
    out.append((ROUTERS[0], [pcbnew.F_Cu, pcbnew.B_Cu], w, via_for(w), 10.0, True))   # 0.1 mm: long runs, fast
    out.append((FINE[0], [pcbnew.F_Cu, pcbnew.B_Cu], w, sv, 10.0, True))
    if w <= 0.2 and not any(re.search(c[-1], short(n)) for c in NETCLASSES.values()):
        # low-speed only: short hops on L3 (the GND pour flows round them)
        out.append((FINE[0], [pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu], w, sv, 10.0, True))
    return out


def _dogbones(board, codes=None):
    """The RK628D's dogbones (each ball's stub and fanout via), as a set of item ids, on these nets (or all)."""
    balls = [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y), p.GetNetCode())
             for p in board.FindFootprintByReference("U201").Pads() if codes is None or p.GetNetCode() in codes]
    bnets = {b[2] for b in balls}
    items = [(t, _geom(t), t.GetNetCode()) for t in board.GetTracks() if t.GetNetCode() in bnets]
    keep = set()
    for t, g, nc in items:
        if g[5] is None:
            continue
        for bx, by, bn in balls:
            if bn != nc:
                continue
            for ex, ey, ox, oy in ((g[0], g[1], g[2], g[3]), (g[2], g[3], g[0], g[1])):
                if math.hypot(ex - bx, ey - by) < 0.01 and math.hypot(ox - bx, oy - by) < 0.5:
                    keep.add(t.m_Uuid.AsString())
                    for v, gv, vn in items:
                        if gv[5] is None and vn == nc and math.hypot(gv[0] - ox, gv[1] - oy) < 0.01:
                            keep.add(v.m_Uuid.AsString())
    return keep


def _pin(board):
    """Dogbones stay hard in every router's soft searches (a rip-up keeps them)."""
    ids = _dogbones(board)
    for r in ROUTERS + ROUTERS[0].peers:
        r.pinned = ids
        r.cache = {}
        r.shapes = None


def _rip(board, R, codes):
    """Takes these nets' tracks and vias out, except an RK628D ball's dogbone (its fanout via and the stub from
    the ball to it), which is hard to find room for again inside the ball field."""
    balls = [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y), p.GetNetCode())
             for p in board.FindFootprintByReference("U201").Pads() if p.GetNetCode() in codes]
    items = [(t, _geom(t), t.GetNetCode()) for t in board.GetTracks() if t.GetNetCode() in codes]
    keep = set()
    for t, g, nc in items:
        if g[5] is None:
            continue
        for bx, by, bn in balls:
            if bn != nc:
                continue
            for ex, ey, ox, oy in ((g[0], g[1], g[2], g[3]), (g[2], g[3], g[0], g[1])):
                if math.hypot(ex - bx, ey - by) < 0.01 and math.hypot(ox - bx, oy - by) < 0.5:
                    keep.add(id(t))
                    for v, gv, vn in items:
                        if gv[5] is None and vn == nc and math.hypot(gv[0] - ox, gv[1] - oy) < 0.01:
                            keep.add(id(v))
    doomed = [t for t, g, nc in items if id(t) not in keep]
    for t in doomed:
        board.Remove(t)
    GRAVE.extend(doomed)
    R.changed()


def dogbone(board, R, n, soft):
    """An RK628D ball of net n with no copper: a 0.3 mm via on one of the four diagonal sites beside it and a
    stub to it. If every site is taken by low-speed traces, those come out. Returns the nets ripped."""
    nc = board.FindNet(n).GetNetCode()
    if any(t.GetNetCode() == nc for t in board.GetTracks()):
        return []
    balls = [p for p in board.FindFootprintByReference("U201").Pads() if p.GetNetCode() == nc]
    if not balls:
        return []
    ball = balls[0]
    # the outer ring of balls escapes on the top layer: no via needed (the second ring usually does too, but its
    # way out between the outer balls can be taken by other nets' fanout, so it gets a via when it has no copper)
    allb = [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y))
            for p in board.FindFootprintByReference("U201").Pads()]
    xs, ys = sorted({round(x, 2) for x, _ in allb}), sorted({round(y, 2) for _, y in allb})
    i = xs.index(round(pcbnew.ToMM(ball.GetPosition().x), 2))
    j = ys.index(round(pcbnew.ToMM(ball.GetPosition().y), 2))
    if min(i, j, len(xs) - 1 - i, len(ys) - 1 - j) < 1:
        return []
    if not RF:
        _configs(board, n, 0.1)                            # (makes the RK628D-area router)
    r = RF[0]
    _pin(board)
    bx, by = pcbnew.ToMM(ball.GetPosition().x) - O[0], pcbnew.ToMM(ball.GetPosition().y) - O[1]
    sites = [(bx + dx, by + dy) for dx in (-0.325, 0.325) for dy in (-0.325, 0.325)]
    vr = max(0.15, 0.075 + 0.2 - r.cl)
    ripped = []
    for attempt in range(2):
        vb = r.blocked(nc, vr, [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]).any(axis=0)
        free = [st for st in sites if not vb[int(round((st[1] - r.y0) / r.res)), int(round((st[0] - r.x0) / r.res))]]
        if free:
            st = free[0]
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I_MM(O[0] + st[0], O[1] + st[1])); v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetWidth(pcbnew.FromMM(0.3)); v.SetDrill(pcbnew.FromMM(0.15))
            v.SetNet(ball.GetNet())
            board.Add(v)
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(ball.GetPosition()); t.SetEnd(pcbnew.VECTOR2I_MM(O[0] + st[0], O[1] + st[1]))
            t.SetWidth(pcbnew.FromMM(0.1)); t.SetLayer(pcbnew.F_Cu); t.SetNet(ball.GetNet())
            board.Add(t)
            R.changed()
            return ripped
        if attempt:
            break
        # clear a site whose blockers may all move (a site with anything fixed on it would stay blocked), the one
        # with the fewest nets
        near, stuck = {}, set()
        pinned = r.pinned
        for t in board.GetTracks():
            if t.GetNetCode() == nc:
                continue
            g = _geom(t)
            for k, st in enumerate(sites):
                pt = (st[0] + O[0], st[1] + O[1], st[0] + O[0], st[1] + O[1], 0.15, None)
                if _seg_dist(pt, g) < 0.15 + g[4] + 0.2 + 0.01:
                    if t.GetNetCode() in soft and t.m_Uuid.AsString() not in pinned:
                        near.setdefault(k, set()).add(t.GetNetCode())
                    else:
                        stuck.add(k)
        near = {k: v for k, v in near.items() if k not in stuck}
        if not near:
            log(f"dogbone {short(n)}: no site can be cleared")
            break
        k = min(near, key=lambda k: len(near[k]))
        _rip(board, R, near[k])
        ripped = [board.FindNet(c).GetNetname() for c in near[k]]
        log(f"dogbone {short(n)}: site cleared, ripped {[short(x) for x in ripped]}")
    return ripped


def _terms(board, nc, whole):
    """A net's terminals for one router. For the RK628D box router when some pads are outside its box: a stand-in
    terminal, any point along the box edge facing those pads (the escape out of the ball grid ends there, and a
    board-wide router takes it on)."""
    terms = net_terms(board, nc)
    if whole:
        return terms
    out = [(pcbnew.ToMM(p.GetPosition().x) - O[0], pcbnew.ToMM(p.GetPosition().y) - O[1]) for p in terms
           if p.GetClass() == "PAD" and not (RK_BOX[0] + 0.5 < pcbnew.ToMM(p.GetPosition().x) - O[0] < RK_BOX[2] - 0.5
                                              and RK_BOX[1] + 0.5 < pcbnew.ToMM(p.GetPosition().y) - O[1] < RK_BOX[3] - 0.5)]
    if not out:
        return terms
    cx, cy = sum(q[0] for q in out) / len(out), sum(q[1] for q in out) / len(out)
    mx, my = (RK_BOX[0] + RK_BOX[2]) / 2, (RK_BOX[1] + RK_BOX[3]) / 2
    x0, y0, x1, y1 = RK_BOX[0] + 1.0, RK_BOX[1] + 1.0, RK_BOX[2] - 1.0, RK_BOX[3] - 1.0
    dx, dy = cx - mx, cy - my
    if abs(dx) * (y1 - y0) > abs(dy) * (x1 - x0):          # leaves through the east or west edge
        x = x1 if dx > 0 else x0
        edge = [(x, y0 + k * 0.25) for k in range(int((y1 - y0) / 0.25) + 1)]
    else:
        y = y1 if dy > 0 else y0
        edge = [(x0 + k * 0.25, y) for k in range(int((x1 - x0) / 0.25) + 1)]
    return [t for t in terms if not (t.GetClass() == "PAD" and (pcbnew.ToMM(t.GetPosition().x) - O[0],
                                                                pcbnew.ToMM(t.GetPosition().y) - O[1]) in out)] + [edge]


def _ripup(board, R, queue, label, u201_too=False, fixed=None):
    """fixed: a set of netcodes; with it, each net routed joins it and is never ripped again (so the queue, taken
    in order, ends)."""
    fixed = set() if fixed is None else fixed
    rips = {}
    tries = {}
    while queue:
        n = queue.pop(0)
        tries[n] = tries.get(n, 0) + 1
        if tries[n] > int(os.environ.get("TRIES", "10")):
            log(f"{label} {short(n)}: given up")
            continue
        nc = board.FindNet(n).GetNetCode()
        for v in dogbone(board, R, n, soft_nets(board, u201_too=True) - {nc} - fixed):
            if v not in queue:
                queue.append(v)
        prune_dead_ends(board, nc, _dogbones(board, {nc}))      # leftovers of earlier tries are not terminals
        R.changed()
        cfgs = _configs(board, n, min(width_for(n), 0.3))
        _pin(board)                                            # (after _configs: it may make a router)
        left = True
        for RS, layers, w, via, win, whole in cfgs:
            left = RS.connect(n, _terms(board, nc, whole), w, layers=layers, via=via, window=win,
                              max_expand=3000000 if RS is ROUTERS[0] else 1000000, greed=2.0)
            if not left and whole:
                break
            left = left or True
        if not left:
            fixed.add(nc)
            pcbnew.SaveBoard(ROUTED, board)
            log(f"{label} {short(n)}: routed")
            continue
        allsoft = soft_nets(board, {k for k, v in rips.items() if v >= 8}, u201_too) - {nc} - fixed
        hi = frozenset(c for c in allsoft if rips.get(short(board.FindNet(c).GetNetname()), 0) >= 2)
        soft = frozenset(allsoft) - hi
        victims = set()
        nopath = set()
        if left:
            # first: the grid's blocked cells keep a little more than the clearance (half a cell diagonal); a path
            # through any net's cells is kept if, measured exactly, it clears every net that may not move
            gnd = board.FindNet("GND").GetNetCode()
            everything = frozenset({t.GetNetCode() for t in board.GetTracks()} - {nc, gnd})
            for ci, (RS, layers, w, via, win, whole) in enumerate(cfgs):
                # (a box router that can't see every terminal still does the ball-grid end; a later one finishes)
                mark = len(RS.log)
                left2 = RS.connect(n, _terms(board, nc, whole), w, layers=layers, via=via, window=win,
                                   max_expand=3000000, greed=1.5, soft=everything, soft_cost=60)
                new_items = RS.log[mark:]
                if left2 and not new_items:
                    nopath.add(ci)                         # nothing found even here: nothing stricter will
                new = [_geom(t) for t in new_items]
                clash = set()
                for t in board.GetTracks():
                    tc = t.GetNetCode()
                    if tc not in everything or tc in clash:
                        continue
                    g = _geom(t)
                    cl = max(RS.cl, RS.net_cl.get(tc, 0))
                    for a in new:
                        if (a[5] is None or g[5] is None or a[5] == g[5]) and _seg_dist(a, g) < a[4] + g[4] + cl - 0.002:
                            clash.add(tc)
                            break
                if os.environ.get("DEBUG"):
                    log(f"  loose cfg {ci} res {RS.res}: left {len(left2)}, {len(new_items)} new, clash "
                        f"{sorted(short(board.FindNet(c).GetNetname()) for c in clash)}, hard "
                        f"{sorted(short(board.FindNet(c).GetNetname()) for c in clash - soft - hi)}")
                if clash - soft - hi:
                    for t in new_items:
                        board.Remove(t)
                    GRAVE.extend(new_items)
                    R.changed()
                    continue
                victims |= clash
                if not left2 and whole:
                    left = []
                    break
        if left:
            for ci, (RS, layers, w, via, win, whole) in enumerate(cfgs):
                if ci in nopath:
                    continue
                mark = len(RS.log)
                left = RS.connect(n, _terms(board, nc, whole), w, layers=layers, via=via, window=win, max_expand=1500000,
                                  greed=1.5, soft=soft, soft_cost=60, soft_hi=hi,
                                  soft_hi_cost=60 * (1 + max([rips.get(short(board.FindNet(c).GetNetname()), 0)
                                                              for c in hi] or [0])))
                new = [_geom(t) for t in RS.log[mark:]]
                for t in board.GetTracks():
                    tc = t.GetNetCode()
                    if (tc not in soft and tc not in hi) or tc in victims:
                        continue
                    g = _geom(t)
                    for a in new:
                        if a[5] is not None and g[5] is not None and a[5] != g[5]:
                            continue
                        if _seg_dist(a, g) < a[4] + g[4] + RS.cl - 0.005:
                            victims.add(tc)
                            break
                if not left and whole:
                    break
                left = left or True
        _rip(board, R, victims)
        prune_dead_ends(board, nc, _dogbones(board, {nc}))      # (a ball's dogbone stays, routed or not)
        R.changed()
        names = [board.FindNet(v).GetNetname() for v in victims]
        for v in names:
            rips[short(v)] = rips.get(short(v), 0) + 1
            if v not in queue:
                queue.append(v)
        if left:
            queue.append(n)
        else:
            fixed.add(nc)
        pcbnew.SaveBoard(ROUTED, board)
        log(f"{label} {short(n)}: " + ("routed" if not left else "still open") +
            (f", ripped {[short(v) for v in names]}" if names else ""))


def _open_queue(board, u201):
    nets, _ = open_nets(board)
    codes = {p.GetNetCode() for p in board.FindFootprintByReference("U201").Pads()}
    queue = [n for n in nets if short(n) != "GND" and (board.FindNet(n).GetNetCode() in codes) == u201]
    if os.environ.get("ONLY"):                                 # a test on a few nets first
        queue = [n for n in queue if short(n) in os.environ["ONLY"].split(",")]
    return queue


def stage_repair(board, B, R):
    """DRC clashes between two nets' tracks (a rip-up that missed a crossing): the low-speed net of the two comes
    out, and both groups go through rip-up again."""
    _, bad = open_nets(board)
    soft = soft_nets(board, u201_too=True)
    names = {}
    for v in bad:
        if v["type"] not in ("tracks_crossing", "clearance", "shorting_items", "hole_clearance", "hole_to_hole"):
            continue
        nets = [re.search(r"\[([^\]]+)\]", i["description"]) for i in v["items"]]
        nets = [board.FindNet(m.group(1)) for m in nets if m]
        cand = [n for n in nets if n and n.GetNetCode() in soft]
        if len(nets) == 2 and cand:
            for victim in cand:               # both, if both may move (a ball's dogbone stays either way)
                names[victim.GetNetname()] = victim.GetNetCode()
    _rip(board, R, set(names.values()))
    log(f"repair: ripped {sorted(short(n) for n in names)}")
    codes = {p.GetNetCode() for p in board.FindFootprintByReference("U201").Pads()}
    _ripup(board, R, [n for n, c in names.items() if c in codes], "repair-rk", u201_too=True)
    _ripup(board, R, [n for n, c in names.items() if c not in codes], "repair")


def stage_pairs_again(board, B, R):
    """Pairs with an open side: both sides out, then stage pairs again (stubs on both connector pins first, the
    two traces in either order)."""
    nets, _ = open_nets(board)
    swap = {"_N": "_P", "_P": "_N", "_DM": "_DP", "_DP": "_DM"}
    codes = set()
    for n in [n for n in nets if re.search(NETCLASSES["PCIE_85R"][-1] + "|" + NETCLASSES["USB_90R"][-1], short(n))]:
        m = re.search(r"(_N|_P|_DM|_DP)(_C)?$", n)
        pn = board.FindNet(n[:m.start(1)] + swap[m.group(1)] + (m.group(2) or ""))
        codes |= {board.FindNet(n).GetNetCode()} | ({pn.GetNetCode()} if pn else set())
    _rip(board, R, codes)
    log(f"pairs_again: {len(codes)} nets taken out")
    stage_pairs(board, B, R)


def _chain(board, nc, start_pad):
    """The tracks of one net as runs from start_pad: [(layer, [points])], one run per layer between vias. Board mm
    (no offset). Assumes a simple path (no branches)."""
    segs = [(t.GetLayer(), _geom(t)) for t in board.GetTracks() if t.GetNetCode() == nc and t.GetClass() != "PCB_VIA"]
    vias = [_geom(t)[:2] for t in board.GetTracks() if t.GetNetCode() == nc and t.GetClass() == "PCB_VIA"]

    def key(x, y):
        return (round(x, 3), round(y, 3))
    sx, sy = pcbnew.ToMM(start_pad.GetPosition().x), pcbnew.ToMM(start_pad.GetPosition().y)
    # the segment end inside the pad (or nearest it)
    best = min(((math.hypot(g[k] - sx, g[k + 1] - sy), i, k) for i, (l, g) in enumerate(segs) for k in (0, 2)))
    _, i, k = best
    layer, g = segs[i]
    used = {i}
    run = [(g[k], g[k + 1]), (g[2 - k], g[3 - k])]
    runs = []
    while True:
        end = key(*run[-1])
        nxt = [(j, kk) for j, (l, gg) in enumerate(segs) if j not in used and l == layer
               for kk in (0, 2) if key(gg[kk], gg[kk + 1]) == end]
        if nxt:
            j, kk = nxt[0]
            used.add(j)
            gg = segs[j][1]
            run.append((gg[2 - kk], gg[3 - kk]))
            continue
        if any(key(*v) == end for v in vias):
            other = [(j, kk) for j, (l, gg) in enumerate(segs) if j not in used and l != layer
                     for kk in (0, 2) if key(gg[kk], gg[kk + 1]) == end]
            if other:
                runs.append((layer, run))
                j, kk = other[0]
                used.add(j)
                layer, gg = segs[j]
                run = [(gg[kk], gg[kk + 1]), (gg[2 - kk], gg[3 - kk])]
                continue
        runs.append((layer, run))
        return runs


def _simplify(pts, min_len=0.12):
    out = list(pts)
    changed = True
    while changed and len(out) > 2:
        changed = False
        for k in range(1, len(out) - 1):
            a, b, c = out[k - 1], out[k], out[k + 1]
            col = abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) < 1e-6
            if col or math.dist(a, b) < min_len or math.dist(b, c) < min_len and k < len(out) - 2:
                del out[k]
                changed = True
                break
    return out


def stage_shadow(board, B, R):
    """PCIe RX: N walled in by P and the other pairs. N is drawn as P's partner, 0.25 mm beside it (0.14 mm
    traces, 0.11 mm gap), with its own via beside each of P's, and joined to its pads by the router. Low-speed
    nets in its way come out and are routed again."""
    from pairs import offset
    pn, nn = board.FindNet("PCIE_RX_P"), board.FindNet("PCIE_RX_N")
    _rip(board, R, {nn.GetNetCode()})
    p0 = [q for q in board.FindFootprintByReference("J501").Pads() if q.GetNumber() == "35"][0]
    n0 = [q for q in board.FindFootprintByReference("J501").Pads() if q.GetNumber() == "37"][0]
    runs = [(l, _simplify(pts)) for l, pts in _chain(board, pn.GetNetCode(), p0)]
    nx, ny = pcbnew.ToMM(n0.GetPosition().x), pcbnew.ToMM(n0.GetPosition().y)
    d = 0.25
    if math.dist(offset(runs[0][1], -d)[0], (nx, ny)) < math.dist(offset(runs[0][1], d)[0], (nx, ny)):
        d = -d
    lanes = [(l, offset(pts, d)) for l, pts in runs]
    # vias: beside each of P's, 0.65 mm off along the incoming run's normal
    for k in range(len(lanes) - 1):
        a, b = runs[k][1][-2], runs[k][1][-1]
        L = math.dist(a, b)
        nrm = (-(b[1] - a[1]) / L, (b[0] - a[0]) / L)
        v = (b[0] + math.copysign(0.65, d) * nrm[0], b[1] + math.copysign(0.65, d) * nrm[1])
        lanes[k] = (lanes[k][0], lanes[k][1][:-1] + [v])
        lanes[k + 1] = (lanes[k + 1][0], [v] + lanes[k + 1][1][1:])
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I_MM(*v)); via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetWidth(pcbnew.FromMM(0.45)); via.SetDrill(pcbnew.FromMM(0.25))
        via.SetNet(nn)
        board.Add(via)

    def trim(pts, cut):
        """The polyline without its first `cut` mm."""
        acc = 0.0
        for k in range(len(pts) - 1):
            seg = math.dist(pts[k], pts[k + 1])
            if acc + seg > cut:
                f = (cut - acc) / seg
                q = (pts[k][0] + f * (pts[k + 1][0] - pts[k][0]), pts[k][1] + f * (pts[k + 1][1] - pts[k][1]))
                return [q] + pts[k + 1:]
            acc += seg
        return pts[-1:]
    lanes[0] = (lanes[0][0], trim(lanes[0][1], 1.0))
    lanes[-1] = (lanes[-1][0], trim(lanes[-1][1][::-1], 0.8)[::-1])
    for layer, pts in lanes:
        for a, b in zip(pts, pts[1:]):
            if math.dist(a, b) < 1e-4:
                continue
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I_MM(*a)); t.SetEnd(pcbnew.VECTOR2I_MM(*b))
            t.SetWidth(pcbnew.FromMM(0.14)); t.SetLayer(layer); t.SetNet(nn)
            board.Add(t)
    R.changed()
    if not FINE:
        FINE.append(make_router(board, 0.05))
    left = FINE[0].connect(nn.GetNetname(), net_terms(board, nn.GetNetCode()), 0.14, layers=[pcbnew.F_Cu, pcbnew.B_Cu],
                           via=(0.45, 0.25), window=3.0, max_expand=500000, greed=1.5)
    pcbnew.SaveBoard(ROUTED, board)
    log(f"shadow: PCIE_RX_N drawn beside P ({sum(len(p) for _, p in lanes)} points), ends " +
        ("joined" if not left else f"{len(left)} open"))
    # what it hits
    _, bad = open_nets(board)
    hit = set()
    for v in bad:
        names = [re.search(r"\[([^\]]+)\]", i["description"]) for i in v["items"]]
        names = [m.group(1) for m in names if m]
        if "PCIE_RX_N" in names:
            hit |= {x for x in names if x != "PCIE_RX_N"}
            log(f"shadow: {v['type']}: " + " / ".join(i["description"][:50] for i in v["items"]))
    soft = soft_nets(board, u201_too=True)
    victims = {board.FindNet(x).GetNetCode() for x in hit if board.FindNet(x)} & soft
    if victims:
        _rip(board, R, victims)
        _ripup(board, R, [board.FindNet(c).GetNetname() for c in victims], "shadow")


def _coupled(board, R, label, sp, sn, ep, en, sdir, edir, soft):
    """One pair as a coupled pair (gen/pairroute.py): sdir/edir are the (dx, dy) directions the pins are left in.
    Low-speed nets crossed come out (returned)."""
    def mid(a, b, k, d):
        return ((pcbnew.ToMM(a.GetPosition().x) + pcbnew.ToMM(b.GetPosition().x)) / 2 - O[0] + d[0] * k,
                (pcbnew.ToMM(a.GetPosition().y) + pcbnew.ToMM(b.GetPosition().y)) / 2 - O[1] + d[1] * k)
    starts = (mid(sp, sn, sdir[2], sdir), mid(ep, en, edir[2], edir))
    anchors = (mid(sp, sn, sdir[2] - 0.25, sdir), mid(ep, en, edir[2] - 0.25, edir))
    if not FINE:
        FINE.append(make_router(board, 0.05))
    mark = len(FINE[0].log)
    res = route_pair(FINE[0], board, O, (sp, ep), (sn, en), starts, 0.14, 0.11, layers=(pcbnew.F_Cu, pcbnew.B_Cu),
                     window=8.0, max_expand=4000000, anchors=anchors, via=(0.45, 0.25), via_pitch=0.9, greed=1.5,
                     soft=soft, soft_cost=60)
    if res is None:
        log(f"pcie {label}: no coupled path")
        return None
    new = [_geom(t) for t in FINE[0].log[mark:]]
    victims = set()
    for t in board.GetTracks():
        tc = t.GetNetCode()
        if tc not in soft or tc in victims:
            continue
        g = _geom(t)
        for a in new:
            if (a[5] is None or g[5] is None or a[5] == g[5]) and _seg_dist(a, g) < a[4] + g[4] + 0.1 - 0.005:
                victims.add(tc)
                break
    _rip(board, R, victims)
    log(f"pcie {label}: P {res[0]:.1f} mm, N {res[1]:.1f} mm, crossed={res[2]}; ripped "
        f"{sorted(short(board.FindNet(c).GetNetname()) for c in victims)}")
    return victims


def stage_pcie(board, B, R):
    """The PCIe group again, as coupled pairs: RX (hardest, walled in by the others), REFCLK, TX to the AC caps,
    then the short cap-to-socket legs. Pairs that find no coupled path go to stage pairs' single traces."""
    names = ["PCIE_RX_P", "PCIE_RX_N", "PCIE_REFCLK_P", "PCIE_REFCLK_N", "PCIE_TX_P", "PCIE_TX_N",
             "/M.2 Wi-Fi + Bluetooth/M2_PER_P", "/M.2 Wi-Fi + Bluetooth/M2_PER_N"]
    _rip(board, R, {board.FindNet(n).GetNetCode() for n in names})
    pad = lambda ref, num: [q for q in board.FindFootprintByReference(ref).Pads() if q.GetNumber() == num][0]  # noqa
    soft = frozenset(soft_nets(board, u201_too=True))
    up, down = (0, -1, 1.0), (0, 1, 1.3)
    victims = set()
    for label, sp, sn, ep, en, sd, ed in [
            ("RX", pad("J702", "16"), pad("J702", "18"), pad("J501", "35"), pad("J501", "37"), up, down),
            ("REFCLK", pad("J702", "10"), pad("J702", "12"), pad("J501", "47"), pad("J501", "49"), up, down),
            ("TX", pad("J702", "22"), pad("J702", "24"), pad("C501", "1"), pad("C502", "1"), up, (0, -1, 0.85))]:
        if os.environ.get("ONLY") and label not in os.environ["ONLY"].split(","):
            continue
        v = _coupled(board, R, label, sp, sn, ep, en, sd, ed, soft)
        victims |= v or set()
        pcbnew.SaveBoard(ROUTED, board)
    for n in names[6:]:
        left = route_net(R, board, n, window=4.0)
        log(f"pcie {short(n)}: " + ("routed" if not left else "open"))
    stage_pairs(board, B, R)              # any pair still without copper: single traces with stubs
    pcbnew.SaveBoard(ROUTED, board)
    _ripup(board, R, [board.FindNet(c).GetNetname() for c in victims], "pcie")


def stage_rxpair(board, B, R):
    """PCIe RX as a coupled pair: both traces out, then one centreline as wide as the pair (gen/pairroute.py) from
    the module's pins to the M.2 pins, split into P and N. Low-speed nets in its way come out and are routed
    again."""
    pn, nn = board.FindNet("PCIE_RX_P"), board.FindNet("PCIE_RX_N")
    _rip(board, R, {pn.GetNetCode(), nn.GetNetCode()})
    pad = lambda ref, num: [q for q in board.FindFootprintByReference(ref).Pads() if q.GetNumber() == num][0]  # noqa
    sp, sn, ep, en = pad("J702", "16"), pad("J702", "18"), pad("J501", "35"), pad("J501", "37")

    def mid(a, b, dx, dy):
        return ((pcbnew.ToMM(a.GetPosition().x) + pcbnew.ToMM(b.GetPosition().x)) / 2 - O[0] + dx,
                (pcbnew.ToMM(a.GetPosition().y) + pcbnew.ToMM(b.GetPosition().y)) / 2 - O[1] + dy)
    starts = (mid(sp, sn, 0, -1.0), mid(ep, en, 0, 1.3))     # just outside each pin pair, away from the rows
    anchors = (mid(sp, sn, 0, -0.75), mid(ep, en, 0, 1.0))
    if not FINE:
        FINE.append(make_router(board, 0.05))
    soft = frozenset(soft_nets(board, u201_too=True))
    mark = len(FINE[0].log)
    res = route_pair(FINE[0], board, O, (sp, ep), (sn, en), starts, 0.14, 0.11, layers=(pcbnew.F_Cu, pcbnew.B_Cu),
                     window=8.0, max_expand=4000000, anchors=anchors, via=(0.45, 0.25), via_pitch=0.9, greed=1.5,
                     soft=soft, soft_cost=60)
    if res is None:
        log("rxpair: no path")
        return
    new = [_geom(t) for t in FINE[0].log[mark:]]
    victims = set()
    for t in board.GetTracks():
        tc = t.GetNetCode()
        if tc not in soft or tc in victims:
            continue
        g = _geom(t)
        for a in new:
            if (a[5] is None or g[5] is None or a[5] == g[5]) and _seg_dist(a, g) < a[4] + g[4] + 0.1 - 0.005:
                victims.add(tc)
                break
    log(f"rxpair: P {res[0]:.1f} mm, N {res[1]:.1f} mm, crossed={res[2]}; ripping "
        f"{sorted(short(board.FindNet(c).GetNetname()) for c in victims)}")
    _rip(board, R, victims)
    pcbnew.SaveBoard(ROUTED, board)
    _ripup(board, R, [board.FindNet(c).GetNetname() for c in victims], "rxpair")


def stage_rkplace(board, B, R):
    """EFUSE (R206, C201) and the MCLK test point (TP204) sat west of the crystal, so their lines had to cross the
    crystal's and the HDMI control lines' way out of the ball grid. They go to the back, beside their balls' fanout
    vias, where each needs only a stub."""
    moves = {"I2S_628_MCLK": ["TP204"], "EFUSE_628": ["R206", "C201"]}
    for n, refs in moves.items():
        ni = board.FindNet("/HDMI in (RK628D)/" + n) or board.FindNet(n)
        nc = ni.GetNetCode()
        ball = [p for p in board.FindFootprintByReference("U201").Pads() if p.GetNetCode() == nc][0]
        _rip(board, R, {nc})                               # (the dogbone stays)
        vias = [_geom(t) for t in board.GetTracks() if t.GetNetCode() == nc and t.GetClass() == "PCB_VIA"]
        bx, by = pcbnew.ToMM(ball.GetPosition().x), pcbnew.ToMM(ball.GetPosition().y)
        vx, vy = min(vias, key=lambda g: math.hypot(g[0] - bx, g[1] - by))[:2] if vias else (bx, by)
        for ref in refs:
            best = place_near(B, R, ref, {ni.GetNetname().split("/")[-1]: (vx - O[0], vy - O[1])}, back=True,
                              span=3.0, step=0.05)
            log(f"rkplace {ref}: to the back at ({best[1]:.2f}, {best[2]:.2f}), {best[3]} deg")
    pcbnew.SaveBoard(ROUTED, board)


def stage_tpmove(board, B, R):
    """TP204 (MCLK test point) to the back west of the RK628D: east of it the middle of the ball grid is a solid
    field of GND fanout vias with no room between them (0.2 mm drill to copper), west is free under the HDMI balls,
    which escape on the top layer."""
    best = place_near(B, R, "TP204", {"*": (38.0, 22.0)}, back=True, span=3.0, step=0.1)
    log(f"tpmove TP204: to ({best[1]:.2f}, {best[2]:.2f}) on the back")
    pcbnew.SaveBoard(ROUTED, board)


def stage_replan(board, B, R):
    """The RK628D's west corner: its analog rails (AVDD_3V3_628, AVDD_1V1_628) were routed early and wander
    through the only ways out for the crystal, EFUSE, MCLK and the HDMI control lines. The rails come out (their
    dogbones stay), the signals go in first, then the rails again."""
    rails = ["/HDMI in (RK628D)/AVDD_3V3_628", "/HDMI in (RK628D)/AVDD_1V1_628"]
    _rip(board, R, {board.FindNet(n).GetNetCode() for n in rails})
    log("replan: analog rails taken out")
    nets, _ = open_nets(board)
    codes = {p.GetNetCode() for p in board.FindFootprintByReference("U201").Pads()}
    sig = [n for n in nets if short(n) != "GND" and board.FindNet(n).GetNetCode() in codes and n not in rails]
    _ripup(board, R, sig, "replan", u201_too=True)
    _ripup(board, R, rails, "replan-rail", u201_too=True)


def stage_sequence(board, B, R):
    """The RK628D corner in a fixed order, hardest first: each net, once routed, is never ripped again, so the
    contest between neighbours (XOUT and RX_CEC, MCLK and EFUSE) ends. The analog rails go last."""
    order = ["EFUSE_628", "RK628D_RESET_N", "RX_EXTR", "I2C_628_SDA", "RK628D_I2C_ADDR", "RK628D_INT", "RX_CEC",
             "RX_HPD", "I2C_628_SCL", "I2S_628_SCLK", "I2S_628_SDO", "RX_SCL", "XOUT_628", "I2S_628_LRCK", "MIPI_REXT",
             "RX_SDA", "TX_EXTR", "XIN_628", "AVDD_1V1_628", "AVDD_3V3_628"]
    nets, _ = open_nets(board)
    codes = {p.GetNetCode() for p in board.FindFootprintByReference("U201").Pads()}
    opened = [n for n in nets if short(n) != "GND" and board.FindNet(n).GetNetCode() in codes]
    rank = {k: i for i, k in enumerate(order)}
    queue = sorted(opened, key=lambda n: rank.get(short(n), len(order)))
    log(f"sequence: {[short(n) for n in queue]}")
    # the chip's nets already routed stay as they are (a restart keeps what the last run settled)
    done = {board.FindNet(n).GetNetCode() for n in [str(k) for k in board.GetNetsByName().keys()]
            if board.FindNet(n).GetNetCode() in codes and n not in opened and short(n) != "GND"}
    _ripup(board, R, queue, "sequence", u201_too=True, fixed=done)
    nets, _ = open_nets(board)
    rest = [n for n in nets if short(n) != "GND"]
    log(f"sequence: still open {[short(n) for n in rest]}")
    if rest:
        _ripup(board, R, rest, "sequence-rest", u201_too=True, fixed=set())


def stage_localfix(board, B, R):
    """Balls whose four fanout-via sites are all under other nets' traces (RX_SCL on L8, I2C_628_SCL on L3): the
    trace pieces on the least crowded site come out (only those pieces, never another ball's dogbone), the ball gets
    its via there, the cut nets are joined up again on the fine grid, then the ball's own net is routed."""
    if not RF:
        _configs(board, "/HDMI in (RK628D)/RX_SCL", 0.1)
    r = RF[0]
    for nm in ["/HDMI in (RK628D)/RX_SCL", "I2C_628_SCL", "RK628D_INT", "RK628D_RESET_N"]:
        ni = board.FindNet(nm) or board.FindNet(nm.split("/")[-1])
        nc = ni.GetNetCode()
        ball = [p for p in board.FindFootprintByReference("U201").Pads() if p.GetNetCode() == nc][0]
        bx, by = pcbnew.ToMM(ball.GetPosition().x), pcbnew.ToMM(ball.GetPosition().y)
        pin = _dogbones(board)
        if any(t.m_Uuid.AsString() in pin for t in board.GetTracks() if t.GetNetCode() == nc):
            log(f"localfix {short(nm)}: has its via already")
            _ripup(board, R, [ni.GetNetname()], "localfix", u201_too=True,
                   fixed={p.GetNetCode() for p in board.FindFootprintByReference("U201").Pads()} - {nc})
            continue
        best = None
        for dx in (-0.325, 0.325):
            for dy in (-0.325, 0.325):
                sx, sy = bx + dx, by + dy
                via = (sx, sy, sx, sy, 0.175 + 0.075, None)          # 0.3 mm via, with its drill clearance
                stub = (bx, by, sx, sy, 0.05, pcbnew.F_Cu)
                hit = []
                for t in board.GetTracks():
                    if t.GetNetCode() == nc:
                        continue
                    g = _geom(t)
                    near = _seg_dist(via, g) < via[4] + g[4] + 0.1 or \
                        ((g[5] is None or g[5] == pcbnew.F_Cu) and _seg_dist(stub, g) < 0.05 + g[4] + 0.1)
                    if near:
                        hit.append(t)
                if any(t.m_Uuid.AsString() in pin or t.GetNetCode() == board.FindNet("GND").GetNetCode()
                       for t in hit):
                    continue
                if best is None or len(hit) < len(best[2]):
                    best = (sx, sy, hit)
        if best is None:
            log(f"localfix {short(nm)}: every site holds a dogbone")
            continue
        sx, sy, hit = best
        cut = {t.GetNetCode() for t in hit}
        for t in hit:
            board.Remove(t)
        GRAVE.extend(hit)
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I_MM(sx, sy)); v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetWidth(pcbnew.FromMM(0.3)); v.SetDrill(pcbnew.FromMM(0.15))
        v.SetNet(ni)
        board.Add(v)
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(ball.GetPosition()); t.SetEnd(pcbnew.VECTOR2I_MM(sx, sy)); t.SetWidth(pcbnew.FromMM(0.1))
        t.SetLayer(pcbnew.F_Cu); t.SetNet(ni)
        board.Add(t)
        R.changed()
        log(f"localfix {short(nm)}: via at ({sx - O[0]:.3f}, {sy - O[1]:.3f}); cut {len(hit)} pieces of "
            f"{sorted(short(board.FindNet(c).GetNetname()) for c in cut)}")
        _pin(board)
        for c in cut:                       # join the cut nets up again, close by
            cn = board.FindNet(c).GetNetname()
            left = r.connect(cn, net_terms(board, c), 0.1, layers=[pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu],
                             via=(0.3, 0.15), window=3.0, max_expand=1500000, greed=1.5)
            log(f"localfix   {short(cn)} rejoined: " + ("yes" if not left else f"{len(left)} pieces apart"))
        pcbnew.SaveBoard(ROUTED, board)
        _ripup(board, R, [ni.GetNetname()], "localfix", u201_too=True,
               fixed={p.GetNetCode() for p in board.FindFootprintByReference("U201").Pads()} - {nc})


def stage_xtal(board, B, R):
    """The crystal (Y201) and its load capacitors sat on the top layer between the ball grid's north-west corner and
    the HDMI control resistors, so every line from that corner had to cross its traces. They go to the back, under
    their balls' fanout vias (the crystal lines get shorter too), and the top layer north of the chip is left to the
    HDMI control lines."""
    xin, xout = board.FindNet("/HDMI in (RK628D)/XIN_628"), board.FindNet("/HDMI in (RK628D)/XOUT_628")
    _rip(board, R, {xin.GetNetCode(), xout.GetNetCode()})          # (their dogbones stay)

    def via_of(ni):
        vs = [_geom(t) for t in board.GetTracks() if t.GetNetCode() == ni.GetNetCode() and t.GetClass() == "PCB_VIA"]
        ball = [p for p in board.FindFootprintByReference("U201").Pads() if p.GetNetCode() == ni.GetNetCode()][0]
        bx, by = pcbnew.ToMM(ball.GetPosition().x), pcbnew.ToMM(ball.GetPosition().y)
        g = min(vs, key=lambda g: math.hypot(g[0] - bx, g[1] - by)) if vs else (bx, by)
        return g[0] - O[0], g[1] - O[1]
    tx, to = via_of(xin), via_of(xout)
    if not board.FindFootprintByReference("Y201").IsFlipped():
        pass
    if board.FindFootprintByReference("Y201").IsFlipped():
        best = None                                        # (already moved: a restart goes straight to routing)
    else:
        best = place_near(B, R, "Y201", {"XIN_628": tx, "XOUT_628": to}, back=True, span=4.0, step=0.05)
    y = board.FindFootprintByReference("Y201")
    pads = {p.GetNetname().split("/")[-1]: (pcbnew.ToMM(p.GetPosition().x) - O[0], pcbnew.ToMM(p.GetPosition().y) - O[1])
            for p in y.Pads()}
    for ref, net in (("C203", "XIN_628"), ("C204", "XOUT_628")) if best else ():
        best = place_near(B, R, ref, {net: pads[net]}, back=True, span=3.0, step=0.05)
        log(f"xtal {ref}: to the back at ({best[1]:.2f}, {best[2]:.2f}), {best[3]} deg")
    pcbnew.SaveBoard(ROUTED, board)
    nets, _ = open_nets(board)
    codes = {p.GetNetCode() for p in board.FindFootprintByReference("U201").Pads()}
    opened = [n for n in nets if short(n) != "GND" and board.FindNet(n).GetNetCode() in codes]
    first = [n for n in opened if short(n) in ("XIN_628", "XOUT_628")]
    queue = first + [n for n in opened if n not in first]
    log(f"xtal: then {[short(n) for n in queue]}")
    keep = {board.FindNet(n).GetNetCode() for n in [str(k) for k in board.GetNetsByName().keys()]
            if short(n) in ("AVDD_1V1_628", "AVDD_3V3_628", "EFUSE_628", "RX_CEC")}
    _ripup(board, R, queue, "xtal", u201_too=True, fixed=keep)


def stage_corner(board, B, R):
    """A clean slate for the RK628D's slow nets and analog rails: every one comes out (ball dogbones stay; the GND
    and main power fanout, RK628D_3V3, 1V1_628 and the high-speed pairs are not touched), then they go back one by
    one, inner balls first, then the second ring, then the outer ring, the analog rails last (they have the most
    ways round). Each net, once routed, stays, so the queue ends."""
    u = board.FindFootprintByReference("U201")
    allb = [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)) for p in u.Pads()]
    xs, ys = sorted({round(x, 2) for x, _ in allb}), sorted({round(y, 2) for _, y in allb})
    depth = {}
    for p in u.Pads():
        i = xs.index(round(pcbnew.ToMM(p.GetPosition().x), 2)); j = ys.index(round(pcbnew.ToMM(p.GetPosition().y), 2))
        d = min(i, j, len(xs) - 1 - i, len(ys) - 1 - j)
        depth[p.GetNetCode()] = max(depth.get(p.GetNetCode(), 0), d)
    rails = {"AVDD_3V3_628", "AVDD_1V1_628"}
    nets = []
    for nc in depth:
        ni = board.FindNet(nc) if nc else None
        if not ni:
            continue
        nm = short(ni.GetNetname())
        if (not nm or nm == "GND" or nm.startswith("unconnected") or nm in ("RK628D_3V3", "1V1_628")
                or any(re.search(c[-1], nm) for c in NETCLASSES.values())):
            continue
        nets.append(ni.GetNetname())
    _rip(board, R, {board.FindNet(n).GetNetCode() for n in nets})
    for n in nets:
        prune_dead_ends(board, board.FindNet(n).GetNetCode(), _dogbones(board, {board.FindNet(n).GetNetCode()}))
    R.changed()
    queue = sorted(nets, key=lambda n: (short(n) in rails, -depth[board.FindNet(n).GetNetCode()], short(n)))
    # every ball's fanout via first, before any route can take its site (inner balls first)
    for n in queue:
        if short(n) not in rails:
            dogbone(board, R, n, frozenset())
    pcbnew.SaveBoard(ROUTED, board)
    log(f"corner: {len(queue)} nets out, back in this order: {[short(n) for n in queue]}")
    _ripup(board, R, queue, "corner", u201_too=True, fixed=set())


def stage_harvest(board, B, R):
    """Open nets that were routed at some earlier checkpoint (just not all at the same time): each one's old route is
    copied back from the newest checkpoint where every piece still clears the board as it is now, and kept only if
    it closes the net (KiCad's own connectivity says so). Checkpoints: the .kicad_pcb files in $HARVEST_DIR."""
    folder = os.environ.get("HARVEST_DIR")
    files = sorted([os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".kicad_pcb")],
                   key=os.path.getmtime, reverse=True) if folder else []
    if not FINE:
        FINE.append(make_router(board, 0.05))
    if not RF:
        _configs(board, "RK628D_INT", 0.1)
    nets, _ = open_nets(board)
    todo = [n for n in nets if short(n) != "GND"]
    log(f"harvest: {len(todo)} open nets, {len(files)} checkpoints")

    def clear(nc, g, layer_list):
        x0, y0, x1, y1, half = g[0] - O[0], g[1] - O[1], g[2] - O[0], g[3] - O[1], g[4]
        inside = all(RK_BOX[0] + 0.3 < x < RK_BOX[2] - 0.3 and RK_BOX[1] + 0.3 < y < RK_BOX[3] - 0.3
                     for x, y in ((x0, y0), (x1, y1)))
        r = RF[0] if inside else FINE[0]
        blk = r.blocked(nc, half, layer_list).any(axis=0)
        k = max(2, int(math.dist((x0, y0), (x1, y1)) / r.res))
        for i in range(k + 1):
            x, y = x0 + (x1 - x0) * i / k, y0 + (y1 - y0) * i / k
            j, ii = int(round((y - r.y0) / r.res)), int(round((x - r.x0) / r.res))
            if not (0 <= j < r.ny and 0 <= ii < r.nx) or blk[j, ii]:
                return False
        return True

    def unconnected():
        board.BuildConnectivity()
        return board.GetConnectivity().GetUnconnectedCount(True)

    olds = {}
    for n in todo:
        ni = board.FindNet(n)
        nc = ni.GetNetCode()
        done = False
        for f in files:
            if f not in olds:
                olds[f] = pcbnew.LoadBoard(f)
            ob = olds[f]
            on = ob.FindNet(n)
            if not on:
                continue
            pieces = [(t.GetClass(), _geom(t), t.GetLayer() if t.GetClass() != "PCB_VIA" else None,
                       pcbnew.ToMM(t.GetDrillValue()) if t.GetClass() == "PCB_VIA" else 0)
                      for t in ob.GetTracks() if t.GetNetCode() == on.GetNetCode()]
            if not pieces:
                continue
            ok = all(clear(nc, g, [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu] if cls == "PCB_VIA" else [lay])
                     for cls, g, lay, _ in pieces)
            if not ok:
                continue
            before = unconnected()
            added = []
            for cls, g, lay, drill in pieces:
                if cls == "PCB_VIA":
                    v = pcbnew.PCB_VIA(board)
                    v.SetPosition(pcbnew.VECTOR2I_MM(g[0], g[1])); v.SetViaType(pcbnew.VIATYPE_THROUGH)
                    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                    v.SetWidth(pcbnew.FromMM(min(g[4] * 2, 0.45) if g[4] * 2 < 0.6 else g[4] * 2))
                    v.SetDrill(pcbnew.FromMM(drill)); v.SetNet(ni)
                    board.Add(v); added.append(v)
                else:
                    t = pcbnew.PCB_TRACK(board)
                    t.SetStart(pcbnew.VECTOR2I_MM(g[0], g[1])); t.SetEnd(pcbnew.VECTOR2I_MM(g[2], g[3]))
                    t.SetWidth(pcbnew.FromMM(g[4] * 2)); t.SetLayer(lay); t.SetNet(ni)
                    board.Add(t); added.append(t)
            after = unconnected()
            R.changed()
            if after < before:
                prune_dead_ends(board, nc, _dogbones(board, {nc}))
                R.changed()
                log(f"harvest {short(n)}: back from {os.path.basename(f)} ({len(added)} pieces)")
                pcbnew.SaveBoard(ROUTED, board)
                done = True
                break
            for t in added:
                board.Remove(t)
            GRAVE.extend(added)
            R.changed()
        if not done:
            log(f"harvest {short(n)}: no checkpoint's route fits")


def stage_clean(board, B, R):
    """The items DRC calls dangling (on the finished board, pours filled): a stub to nowhere, a fanout via its
    route abandoned. Only those items go (a GND via looks dangling on the working board, which has no pours)."""
    _, bad = open_nets(board)
    spots = [(v["type"], i["pos"]["x"], i["pos"]["y"], re.search(r"\[([^\]]+)\]", i["description"]).group(1))
             for v in bad if v["type"] in ("via_dangling", "track_dangling") for i in v["items"][:1]]
    doomed = []
    for kind, x, y, name in spots:
        nc = board.FindNet(name).GetNetCode()
        for t in board.GetTracks():
            if t.GetNetCode() != nc or t in doomed:
                continue
            g = _geom(t)
            if (kind == "via_dangling") == (g[5] is None) and _seg_dist((x, y, x, y, 0, None), g) < 0.02:
                doomed.append(t)
    for t in doomed:
        board.Remove(t)
    GRAVE.extend(doomed)
    R.changed()
    log(f"clean: {len(doomed)} dangling items removed ({len(spots)} reported)")


def stage_gndfix(board, B, R):
    """GND clean-up after the stitching grid: grid vias too near a hole or on no pour come out, then every outer-layer
    GND pour island without a via gets one (else it floats: DRC counts it unconnected)."""
    gnd = board.FindNet("GND")
    gc = gnd.GetNetCode()
    holes = [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y), pcbnew.ToMM(p.GetDrillSize().x) / 2)
             for f in board.GetFootprints() for p in f.Pads() if p.HasHole()]
    for rnd in range(3):
        _, bad = open_nets(board)
        spots = [(i["pos"]["x"], i["pos"]["y"]) for v in bad if v["type"] in ("hole_to_hole", "via_dangling")
                 for i in v["items"] if "Via [GND]" in i["description"]]
        doomed = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetCode() == gc and
                  any(math.hypot(_geom(t)[0] - x, _geom(t)[1] - y) < 0.01 for x, y in spots)]
        for t in doomed:
            board.Remove(t)
        GRAVE.extend(doomed)
        R.changed()
        pcbnew.SaveBoard(ROUTED, board)
        subprocess.run([KP, os.path.join(HERE, "finish.py")], capture_output=True)
        r = subprocess.run([KP, os.path.join(HERE, "islands.py")], capture_output=True, text=True)
        isl = json.loads([l for l in r.stdout.splitlines() if l.startswith("[")][-1])
        vb = (FINE[0] if FINE else make_router(board, 0.05))
        if not FINE:
            FINE.append(vb)
        blk = vb.blocked(gc, 0.225, [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]).any(axis=0)
        vias_now = [_geom(t) for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
        added = 0
        joined = 0
        blk_s = vb.blocked(gc, 0.175, [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]).any(axis=0)
        for il in isl:
            pts = il["pts"]
            placed = False
            for size, bk in (((0.45, 0.25), blk), ((0.3, 0.15), blk_s)):
                for x, y in pts:
                    j, i = int(round((y - O[1] - vb.y0) / vb.res)), int(round((x - O[0] - vb.x0) / vb.res))
                    if not (0 <= j < vb.ny and 0 <= i < vb.nx) or bk[j, i]:
                        continue
                    if any(math.hypot(hx - x, hy - y) < hr + size[1] / 2 + 0.3 for hx, hy, hr in holes):
                        continue
                    if any(math.hypot(g[0] - x, g[1] - y) < size[1] / 2 + 0.125 + 0.27 for g in vias_now):
                        continue
                    v = pcbnew.PCB_VIA(board)
                    v.SetPosition(pcbnew.VECTOR2I_MM(x, y)); v.SetViaType(pcbnew.VIATYPE_THROUGH)
                    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                    v.SetWidth(pcbnew.FromMM(size[0])); v.SetDrill(pcbnew.FromMM(size[1])); v.SetNet(gnd)
                    board.Add(v)
                    vias_now.append((x, y, x, y, size[0] / 2, None))
                    added += 1
                    placed = True
                    break
                if placed:
                    break
            if placed:
                continue
            if il["pads"]:                       # no room for a via: a short trace to the nearest GND via instead
                ref, num = il["pads"][0]
                pad = [q for q in board.FindFootprintByReference(ref).Pads() if q.GetNumber() == num][0]
                px, py = pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)
                near = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetCode() == gc and
                        math.hypot(_geom(t)[0] - px, _geom(t)[1] - py) < 6.0]
                if near:
                    r0 = RF[0] if (RF and RK_BOX[0] < px - O[0] < RK_BOX[2] and RK_BOX[1] < py - O[1] < RK_BOX[3]) \
                        else vb
                    left = r0.connect("GND", [pad, near], 0.12, layers=[pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu],
                                      via=(0.3, 0.15), window=4.0, max_expand=1500000, greed=1.5)
                    joined += 0 if left else 1
        R.changed()
        log(f"gndfix round {rnd + 1}: {len(doomed)} grid vias out, {added} island vias in, {joined} pads joined by a "
            f"trace ({len(isl)} islands)")
        if (not isl and not doomed) or (not added and not joined and not doomed):
            break
    pcbnew.SaveBoard(ROUTED, board)


def stage_tune(board, B, R):
    """Length matching: the shorter trace of a pair gets chamfered bumps (gen/pairs.py's tune) on its longest
    straight segments, on whichever side has room, until it is within 0.2 mm of its partner."""
    from pairs import tune
    if not FINE:
        FINE.append(make_router(board, 0.05))
    r = FINE[0]
    for pa, pb in [("PCIE_REFCLK_P", "PCIE_REFCLK_N"), ("PCIE_RX_P", "PCIE_RX_N"), ("PCIE_TX_P", "PCIE_TX_N"),
                   ("USB_OTG_DP", "USB_OTG_DM"), ("USB_BT_DP", "USB_BT_DM")]:
        na, nb = board.FindNet(pa), board.FindNet(pb)
        if not na or not nb:
            continue
        ln = {n.GetNetCode(): sum(pcbnew.ToMM(t.GetLength()) for t in board.GetTracks()
                                  if t.GetNetCode() == n.GetNetCode() and t.GetClass() != "PCB_VIA") for n in (na, nb)}
        short_n = min((na, nb), key=lambda n: ln[n.GetNetCode()])
        nc = short_n.GetNetCode()
        need = abs(ln[na.GetNetCode()] - ln[nb.GetNetCode()])
        added = 0.0
        segs = sorted([t for t in board.GetTracks() if t.GetNetCode() == nc and t.GetClass() != "PCB_VIA"],
                      key=lambda t: -t.GetLength())
        for t in segs:
            if need - added < 0.2:
                break
            g = _geom(t)
            a0, b0 = (g[0] - O[0], g[1] - O[1]), (g[2] - O[0], g[3] - O[1])
            L = math.dist(a0, b0)
            nb_max = int((L - 0.3 - 0.8 + 0.35) / 1.1)
            if nb_max < 1:
                continue
            extra = min(need - added, nb_max * 0.66)
            layer, w = t.GetLayer(), g[4] * 2
            blk = r.blocked(nc, w / 2, [layer])[0]
            for side in (1, -1):
                try:
                    pts = tune([a0, b0], 0, extra, side)
                except AssertionError:
                    break
                ok = True
                for p, q in zip(pts, pts[1:]):
                    k = max(2, int(math.dist(p, q) / r.res))
                    for i in range(k + 1):
                        x, y = p[0] + (q[0] - p[0]) * i / k, p[1] + (q[1] - p[1]) * i / k
                        jj, ii = int(round((y - r.y0) / r.res)), int(round((x - r.x0) / r.res))
                        # the original segment's own cells are fine (only its own net is there)
                        if blk[jj, ii]:
                            ok = False
                            break
                    if not ok:
                        break
                if not ok:
                    continue
                net = t.GetNet()
                board.Remove(t)
                GRAVE.append(t)
                for p, q in zip(pts, pts[1:]):
                    if math.dist(p, q) < 1e-4:
                        continue
                    nt = pcbnew.PCB_TRACK(board)
                    nt.SetStart(pcbnew.VECTOR2I_MM(O[0] + p[0], O[1] + p[1]))
                    nt.SetEnd(pcbnew.VECTOR2I_MM(O[0] + q[0], O[1] + q[1]))
                    nt.SetWidth(pcbnew.FromMM(w)); nt.SetLayer(layer); nt.SetNet(net)
                    board.Add(nt)
                R.changed()
                blk = None
                added += extra
                break
        log(f"tune {short(pa)[:-2]}: {short(short_n.GetNetname())} +{added:.2f} of {need:.2f} mm")
    pcbnew.SaveBoard(ROUTED, board)


def stage_pairfix(board, B, R):
    """A pair with one side routed and the other walled in by it: the routed side comes out, the open side goes
    first, then its partner (both through rip-up)."""
    nets, _ = open_nets(board)
    swap = {"_N": "_P", "_P": "_N", "_DM": "_DP", "_DP": "_DM"}
    for n in [n for n in nets if re.search(NETCLASSES["PCIE_85R"][-1] + "|" + NETCLASSES["USB_90R"][-1], short(n))]:
        m = re.search(r"(_N|_P|_DM|_DP)(_C)?$", n)
        partner = n[:m.start(1)] + swap[m.group(1)] + (m.group(2) or "")
        pn = board.FindNet(partner)
        if not pn:
            continue
        doomed = [t for t in board.GetTracks() if t.GetNetCode() == pn.GetNetCode()]
        for t in doomed:
            board.Remove(t)
        GRAVE.extend(doomed)
        R.changed()
        log(f"pairfix {short(n)}: {short(partner)} taken out ({len(doomed)} pieces)")
        _ripup(board, R, [n, partner], "pairfix")


def stage_ripup(board, B, R):
    """Rip-up and reroute for nets walled in by earlier routes: the net may cross other low-speed nets' traces
    (at a cost per cell); the nets it crosses come out and go back in the queue. A net ripped three times is
    no longer soft, so the loop ends. The RK628D's own nets are left to stage rkrip."""
    _ripup(board, R, _open_queue(board, False), "ripup")


def stage_rkrip(board, B, R):
    """The same for the RK628D's nets, on the 0.025 mm grid with L3, where its other low-speed nets may move."""
    _ripup(board, R, _open_queue(board, True), "rkrip", u201_too=True)

STAGES = {"gndfix": stage_gndfix, "clean": stage_clean, "harvest": stage_harvest, "corner": stage_corner, "xtal": stage_xtal, "localfix": stage_localfix, "sequence": stage_sequence, "tpmove": stage_tpmove, "replan": stage_replan, "rkplace": stage_rkplace, "tune": stage_tune, "pcie": stage_pcie, "rxpair": stage_rxpair, "shadow": stage_shadow, "pairs_again": stage_pairs_again, "pairfix": stage_pairfix, "repair": stage_repair, "ripup": stage_ripup, "rkrip": stage_rkrip, "holes": stage_holes, "rip_j69": stage_rip_j69, "j69": stage_j69, "pairs": stage_pairs, "power": stage_power, "signals": stage_signals, "rk628": stage_rk628,
          "gnd": stage_gnd}

if __name__ == "__main__":
    shutil.copy(os.path.join(ROOT, "relay.kicad_pro"), ROUTED.replace(".kicad_pcb", ".kicad_pro"))
    board = pcbnew.LoadBoard(ROUTED)      # the checkpoint has no pours
    B = Board(board)
    R = make_router(board, 0.1)
    stages = sys.argv[1:] or list(STAGES)
    log("start:", stages)
    for st in stages:
        STAGES[st](board, B, R)
        R.changed()
        pcbnew.SaveBoard(ROUTED, board)
        log(f"stage {st} done, checkpoint saved")
    nets, bad = open_nets(board)
    log(f"end: {sum(nets.values())} unconnected on {len(nets)} nets: {sorted(short(n) for n in nets)}")
    log(f"end: {len(bad)} DRC errors: " + "; ".join(f"{v['type']}: " + " / ".join(i['description'][:40]
                                                                                 for i in v['items'])
                                                      for v in bad[:30]))
