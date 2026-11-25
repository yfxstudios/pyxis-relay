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
    (r"^5V_SYS$", 0.6), (r"^3V3_IO$", 0.5), (r"^(HDMITX_5V|HDMIRX_5V|1V1_628)$", 0.4), (r"^RK628D_3V3$", 0.2),   # RK628D I/O: tens of mA
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
                or re.match(r"(FB|BS|BST|FS|CT)\d*(_|$)|AVDD|RK628D_3V3|1V1_628|XIN_628|XOUT_628", name)   # regulators, rails
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


def _ball_has_copper(board, ball):
    """True if a track of the ball's net starts or ends on the ball (the net may have copper elsewhere)."""
    bx, by = pcbnew.ToMM(ball.GetPosition().x), pcbnew.ToMM(ball.GetPosition().y)
    for t in board.GetTracks():
        if t.GetNetCode() != ball.GetNetCode() or t.GetClass() == "PCB_VIA":
            continue
        g = _geom(t)
        if math.hypot(g[0] - bx, g[1] - by) < 0.16 or math.hypot(g[2] - bx, g[3] - by) < 0.16:
            return True
    return False


def dogbone(board, R, n, soft):
    """An RK628D ball of net n with no copper: a 0.3 mm via on one of the four diagonal sites beside it and a
    stub to it. If every site is taken by low-speed traces, those come out. Returns the nets ripped."""
    nc = board.FindNet(n).GetNetCode()
    balls = [p for p in board.FindFootprintByReference("U201").Pads() if p.GetNetCode() == nc]
    if not balls or _ball_has_copper(board, balls[0]):
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
    # the ring just outside the RK628D's footprint, on the side facing those pads: the box router only has to get
    # out of the ball grid; the open board beyond is the board-wide router's
    cb = board.FindFootprintByReference("U201").GetCourtyard(pcbnew.F_CrtYd).BBox()
    x0, y0 = pcbnew.ToMM(cb.GetLeft()) - O[0] - 1.0, pcbnew.ToMM(cb.GetTop()) - O[1] - 1.0
    x1, y1 = pcbnew.ToMM(cb.GetRight()) - O[0] + 1.0, pcbnew.ToMM(cb.GetBottom()) - O[1] + 1.0
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = cx - mx, cy - my
    if abs(dx) * (y1 - y0) > abs(dy) * (x1 - x0):          # leaves through the east or west edge
        x = x1 if dx > 0 else x0
        edge = [(x, y0 + k * 0.25) for k in range(int((y1 - y0) / 0.25) + 1)]
    else:
        y = y1 if dy > 0 else y0
        edge = [(x0 + k * 0.25, y) for k in range(int((x1 - x0) / 0.25) + 1)]
    return [t for t in terms if not (t.GetClass() == "PAD" and (pcbnew.ToMM(t.GetPosition().x) - O[0],
                                                                pcbnew.ToMM(t.GetPosition().y) - O[1]) in out)] + [edge]


def dogbone_local(board, R, n):
    """dogbone(), but a site covered by other nets' traces is cleared locally: only the pieces on the site come out
    (never a dogbone, a pad, GND, a high-speed pair or a main power rail), the via goes in, and each cut net is
    joined up again close by. Returns the cut nets that did not join up again."""
    nc = board.FindNet(n).GetNetCode()
    ball = [p for p in board.FindFootprintByReference("U201").Pads() if p.GetNetCode() == nc][0]
    if _ball_has_copper(board, ball):
        return []
    if not RF:
        _configs(board, n, 0.1)
    r = RF[0]
    _pin(board)
    pin = r.pinned
    gnd = board.FindNet("GND").GetNetCode()
    big = {board.FindNet(x).GetNetCode() for x in [str(k) for k in board.GetNetsByName().keys()]
           if short(x) in POWER_ORDER and short(x) not in ("RK628D_3V3", "1V1_628")}
    bx, by = pcbnew.ToMM(ball.GetPosition().x), pcbnew.ToMM(ball.GetPosition().y)
    pads = [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y),
             pcbnew.ToMM(p.GetBoundingBox().GetWidth()) / 2, pcbnew.ToMM(p.GetBoundingBox().GetHeight()) / 2)
            for f in board.GetFootprints() if f.GetReference() != "U201" for p in f.Pads()
            if abs(pcbnew.ToMM(p.GetPosition().x) - bx) < 2 and abs(pcbnew.ToMM(p.GetPosition().y) - by) < 2]
    best = None
    for dx in (-0.325, 0.325):
        for dy in (-0.325, 0.325):
            sx, sy = bx + dx, by + dy
            if any(abs(px - sx) < hw + 0.15 + 0.12 and abs(py - sy) < hh + 0.15 + 0.12 for px, py, hw, hh in pads):
                continue
            via = (sx, sy, sx, sy, 0.15, None)
            stub = (bx, by, sx, sy, 0.05, pcbnew.F_Cu)
            hit, stuck = [], False
            for t in board.GetTracks():
                if t.GetNetCode() == nc:
                    continue
                g = _geom(t)
                near = _seg_dist(via, g) < 0.15 + g[4] + (0.2 if g[5] is not None else 0.25) + 0.01 or \
                    ((g[5] is None or g[5] == pcbnew.F_Cu) and _seg_dist(stub, g) < 0.05 + g[4] + 0.1 + 0.01)
                if not near:
                    continue
                name = short(board.FindNet(t.GetNetCode()).GetNetname())
                if (t.m_Uuid.AsString() in pin or t.GetNetCode() in (gnd,) or t.GetNetCode() in big or
                        any(re.search(c[-1], name) for k, c in NETCLASSES.items() if k != "POWER")):
                    stuck = True
                    break
                hit.append(t)
            if not stuck and (best is None or len(hit) < len(best[2])):
                best = (sx, sy, hit)
    if best is None:
        log(f"dogbone {short(n)}: every site holds something fixed")
        return []
    sx, sy, hit = best
    cut = {t.GetNetCode() for t in hit}
    for t in hit:
        board.Remove(t)
    GRAVE.extend(hit)
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I_MM(sx, sy)); v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetWidth(pcbnew.FromMM(0.3)); v.SetDrill(pcbnew.FromMM(0.15))
    v.SetNet(ball.GetNet())
    board.Add(v)
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(ball.GetPosition()); t.SetEnd(pcbnew.VECTOR2I_MM(sx, sy)); t.SetWidth(pcbnew.FromMM(0.1))
    t.SetLayer(pcbnew.F_Cu); t.SetNet(ball.GetNet())
    board.Add(t)
    R.changed()
    _pin(board)
    failed = []
    for c in cut:
        cn = board.FindNet(c).GetNetname()
        left = r.connect(cn, net_terms(board, c), 0.1, layers=[pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu],
                         via=(0.3, 0.15), window=4.0, max_expand=2000000, greed=1.5)
        if left:
            failed.append(cn)
    log(f"dogbone {short(n)}: site cleared locally ({len(hit)} pieces of "
        f"{sorted(short(board.FindNet(c).GetNetname()) for c in cut)}); not rejoined: {[short(x) for x in failed]}")
    return failed


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
                local = {board.FindNet(x).GetNetCode() for x in [str(k) for k in board.GetNetsByName().keys()]
                         if short(x) in os.environ.get("LOCAL", "").split(",") and x}
                if clash - soft - hi - local:
                    for t in new_items:
                        board.Remove(t)
                    GRAVE.extend(new_items)
                    R.changed()
                    continue
                # rails allowed to give way locally: only their pieces under the new route come out, and they are
                # joined up again around it
                cut = [t for t in board.GetTracks() if t.GetNetCode() in (clash & local) and
                       t.m_Uuid.AsString() not in RS.pinned and any(
                           (a[5] is None or _geom(t)[5] is None or a[5] == _geom(t)[5]) and
                           _seg_dist(a, _geom(t)) < a[4] + _geom(t)[4] + 0.1 + 0.01 for a in new)]
                if cut:
                    rejoin = {t.GetNetCode() for t in cut}
                    for t in cut:
                        board.Remove(t)
                    GRAVE.extend(cut)
                    R.changed()
                    for c in rejoin:
                        cn = board.FindNet(c).GetNetname()
                        ok = not RS.connect(cn, net_terms(board, c), 0.1,
                                            layers=[pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu], via=(0.3, 0.15),
                                            window=4.0, max_expand=2000000, greed=1.5)
                        log(f"{label}   {short(cn)}: {len(cut)} pieces cut, rejoined: {'yes' if ok else 'NO'}")
                victims |= clash - local
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


def share_vias(board, R, near_balls, radius=1.4):
    """Frees fanout-via sites around these balls: where two orthogonal neighbour balls are on the same GND or power
    net and both have a dogbone, the one nearer a stuck ball gives its via up and joins its neighbour's ball with a
    straight top-layer stub (0.65 mm, between the two balls only). Returns how many vias were freed."""
    u = board.FindFootprintByReference("U201")
    balls = {p.GetNumber(): (pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y), p.GetNetCode(), p)
             for p in u.Pads()}
    shared = {board.FindNet(n).GetNetCode() for n in ["GND", "RK628D_3V3", "1V1_628", "/HDMI in (RK628D)/AVDD_3V3_628",
                                                      "/HDMI in (RK628D)/AVDD_1V1_628"] if board.FindNet(n)}
    centres = [(balls[b][0], balls[b][1]) for b in near_balls]
    items = [(t, _geom(t)) for t in board.GetTracks()]

    def dogbone_of(bx, by, nc):
        stub = via = None
        for t, g in items:
            if t.GetNetCode() != nc or t in GRAVE:
                continue
            if g[5] is not None:
                for ex, ey, ox, oy in ((g[0], g[1], g[2], g[3]), (g[2], g[3], g[0], g[1])):
                    if math.hypot(ex - bx, ey - by) < 0.01 and math.hypot(ox - bx, oy - by) < 0.5:
                        for v, gv in items:
                            if gv[5] is None and v.GetNetCode() == nc and math.hypot(gv[0] - ox, gv[1] - oy) < 0.01:
                                stub, via = t, v
        return stub, via
    freed = 0
    done = set()
    for k, (bx, by, nc, pad) in sorted(balls.items(), key=lambda kv: min(math.hypot(kv[1][0] - cx, kv[1][1] - cy)
                                                                       for cx, cy in centres)):
        if nc not in shared or k in done or min(math.hypot(bx - cx, by - cy) for cx, cy in centres) > radius:
            continue
        stub, via = dogbone_of(bx, by, nc)
        if not via:
            continue
        # a same-net neighbour that keeps its via
        for k2, (x2, y2, n2, p2) in balls.items():
            if k2 == k or n2 != nc or abs(math.hypot(x2 - bx, y2 - by) - 0.65) > 0.02 or k2 in done:
                continue
            s2, v2 = dogbone_of(x2, y2, nc)
            if not v2:
                continue
            # the straight stub must not touch other copper on the top layer
            seg = (bx, by, x2, y2, 0.075, pcbnew.F_Cu)
            if any(g[5] in (None, pcbnew.F_Cu) and t.GetNetCode() != nc and t not in GRAVE and
                   _seg_dist(seg, g) < 0.075 + g[4] + 0.1 for t, g in items):
                continue
            board.Remove(stub); board.Remove(via)
            GRAVE.extend([stub, via])
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pad.GetPosition()); t.SetEnd(p2.GetPosition()); t.SetWidth(pcbnew.FromMM(0.15))
            t.SetLayer(pcbnew.F_Cu); t.SetNet(pad.GetNet())
            board.Add(t)
            done.update({k, k2})
            freed += 1
            break
    R.changed()
    return freed


def stage_cluster(board, B, R):
    """The east-side control lines as one group, hardest first: INT and I2C_628_SCL have no free fanout site and no
    top-layer exit (the CSI pairs take those), and their sites were taken by I2C_628_SDA and RESET_N, routed earlier.
    The group comes out (dogbones stay), goes back in this order, and every other RK628D net stays as it is; the
    analog rails may give way locally (LOCAL)."""
    group = ["RK628D_INT", "I2C_628_SCL", "/HDMI in (RK628D)/RX_SCL", "RK628D_RESET_N", "I2C_628_SDA"]
    codes = {board.FindNet(n).GetNetCode() for n in group}
    doomed = [t for t in board.GetTracks() if t.GetNetCode() in codes]   # dogbones too: their sites are shared
    for t in doomed:
        board.Remove(t)
    GRAVE.extend(doomed)
    R.changed()
    near = [p.GetNumber() for p in board.FindFootprintByReference("U201").Pads() if p.GetNetCode() in codes]
    log(f"cluster: {share_vias(board, R, near)} GND/power vias shared with a neighbour ball, freeing their sites")
    broken = []
    for n in group:                      # fanout vias again, in this order, before any route takes a site
        nm = board.FindNet(n).GetNetname()
        dogbone(board, R, nm, frozenset())
        if not any(t.GetNetCode() == board.FindNet(n).GetNetCode() for t in board.GetTracks()):
            broken += dogbone_local(board, R, nm)
        log(f"cluster: {short(n)} dogbone " + ("placed" if any(
            t.GetNetCode() == board.FindNet(n).GetNetCode() for t in board.GetTracks()) else "none"))
    pcbnew.SaveBoard(ROUTED, board)
    u = {p.GetNetCode() for p in board.FindFootprintByReference("U201").Pads()}
    fixed = {c for c in u if c not in codes and board.FindNet(c) and short(board.FindNet(c).GetNetname()) != "GND"}
    log(f"cluster: {[short(n) for n in group]} out; {len(fixed)} other RK628D nets fixed")
    fixed -= {board.FindNet(x).GetNetCode() for x in broken}
    _ripup(board, R, [board.FindNet(n).GetNetname() for n in group] + broken, "cluster", u201_too=True, fixed=fixed)


def stage_c219(board, B, R):
    """C219 (AVDD_1V1 decoupling, on the back under the ball grid) sat on RESET_N's two free fanout-via sites. It
    moves to the nearest legal spot clear of them, its AVDD_1V1 side is joined up again and its GND pad gets a via;
    then RESET_N gets its via, and every net still open is routed with the rest of the RK628D's nets fixed."""
    u = board.FindFootprintByReference("U201")
    ball = [p for p in u.Pads() if short(p.GetNetname()) == "RK628D_RESET_N"][0]
    bx, by = pcbnew.ToMM(ball.GetPosition().x) - O[0], pcbnew.ToMM(ball.GetPosition().y) - O[1]
    c = board.FindFootprintByReference("C219")
    pads = [(pcbnew.ToMM(q.GetPosition().x), pcbnew.ToMM(q.GetPosition().y)) for q in c.Pads()]
    moved = abs(pcbnew.ToMM(c.GetPosition().x) - O[0] - 45.275) > 0.1
    stubs = [t for t in board.GetTracks() if t.GetNetCode() in {q.GetNetCode() for q in c.Pads()} and
             t.GetNetCode() != 0 and any(math.hypot(_geom(t)[k] - px, _geom(t)[k + 1] - py) < 0.35
                                         for px, py in pads for k in (0, 2))]
    stubs = [t for t in stubs if t.m_Uuid.AsString() not in _dogbones(board)] if not moved else []
    for t in stubs:
        board.Remove(t)
    GRAVE.extend(stubs)
    R.changed()
    keep = [(bx - 0.325 - 0.45, by + dy - 0.45, bx - 0.325 + 0.45, by + dy + 0.45) for dy in (-0.325, 0.325)]
    target = (pads[0][0] - O[0], pads[0][1] - O[1])
    if not moved:
        best = place_near(B, R, "C219", {"AVDD_1V1_628": target}, back=True, span=2.5, step=0.05, keepout=keep)
        log(f"c219: {len(stubs)} stubs off, moved to ({best[1]:.2f}, {best[2]:.2f}), {best[3]} deg")
    if not RF:
        _configs(board, "RK628D_RESET_N", 0.1)
    _pin(board)
    av = board.FindNet("/HDMI in (RK628D)/AVDD_1V1_628")
    left = RF[0].connect(av.GetNetname(), net_terms(board, av.GetNetCode()), 0.15,
                         layers=[pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu], via=(0.3, 0.15), window=4.0,
                         max_expand=2000000, greed=1.5)
    miss = B.gnd_vias(R, ["C219"], size=(0.3, 0.15))
    log(f"c219: AVDD_1V1_628 joined: {'yes' if not left else 'NO'}; GND via: {'yes' if not miss else 'NO'}")
    broken = dogbone_local(board, R, ball.GetNetname())
    pcbnew.SaveBoard(ROUTED, board)
    nets, _ = open_nets(board)
    queue = [n for n in nets if short(n) != "GND"]
    rk = ["RK628D_RESET_N", "I2C_628_SDA", "XOUT_628", "RX_HPD"]
    queue.sort(key=lambda n: (short(n) not in rk, rk.index(short(n)) if short(n) in rk else 0))
    codes = {p.GetNetCode() for p in u.Pads()}
    fixed = {cc for cc in codes if board.FindNet(cc) and board.FindNet(cc).GetNetname() not in queue and
             short(board.FindNet(cc).GetNetname()) != "GND"}
    log(f"c219: open now {[short(n) for n in queue]}")
    _ripup(board, R, queue, "c219", u201_too=True, fixed=fixed)


def _via_near(board, r, nc, x, y, reach=1.6):
    """A free spot for a 0.3 mm via of net nc within reach of (x, y) board mm, nearest first, or None."""
    vb = r.blocked(nc, max(0.15, 0.075 + 0.2 - r.cl), [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]).any(axis=0)
    own = [(_geom(t)[0], _geom(t)[1]) for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetCode() == nc]
    best = None
    k = int(reach / r.res)
    i0, j0 = int(round((x - O[0] - r.x0) / r.res)), int(round((y - O[1] - r.y0) / r.res))
    for dj in range(-k, k + 1):
        for di in range(-k, k + 1):
            j, i = j0 + dj, i0 + di
            if not (0 <= j < r.ny and 0 <= i < r.nx) or vb[j, i]:
                continue
            d = math.hypot(di, dj) * r.res
            if d > reach or (best and d >= best[0]):
                continue
            px, py = r.x0 + i * r.res + O[0], r.y0 + j * r.res + O[1]
            if any(math.hypot(px - ox, py - oy) < 0.55 for ox, oy in own):
                continue
            best = (d, px, py)
    return best[1:] if best else None


def stage_in2bridge(board, B, R):
    """Each connection still open (KiCad's list, GND aside) gets a 0.3 mm via beside each end, a short stub to it,
    and between the two vias a route on L3 (the back layer too, if L3 alone can't), where the board is nearly empty:
    the outer layers are full where these long control lines have to go (J701's pin rows, the pair bundles)."""
    if not FINE:
        FINE.append(make_router(board, 0.05))
    r = FINE[0]
    _, bad = open_nets(board)
    pairs = []
    for u in LAST_DRC[0]["unconnected_items"]:
        it = u["items"]
        m = re.search(r"\[([^\]]+)\]", it[0]["description"])
        if not m or m.group(1) == "GND" or len(it) < 2:
            continue
        pairs.append((m.group(1), (it[0]["pos"]["x"], it[0]["pos"]["y"]), (it[1]["pos"]["x"], it[1]["pos"]["y"])))
    log(f"in2bridge: {len(pairs)} open connections")
    for name, a, c in pairs:
        ni = board.FindNet(name)
        nc = ni.GetNetCode()
        ends = []
        for (x, y) in (a, c):
            own_via = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetCode() == nc and
                       math.hypot(_geom(t)[0] - x, _geom(t)[1] - y) < 0.05]
            if own_via:
                ends.append(own_via[0])
                continue
            spot = _via_near(board, r, nc, x, y, reach=3.0)
            if not spot:
                break
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I_MM(*spot)); v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetWidth(pcbnew.FromMM(0.3)); v.SetDrill(pcbnew.FromMM(0.15))
            v.SetNet(ni)
            board.Add(v)
            R.changed()
            # the stub from the end (the pad or track DRC names there) to its via, on any outer layer
            item = None
            for f in board.GetFootprints():
                for q in f.Pads():
                    if q.GetNetCode() == nc and math.hypot(pcbnew.ToMM(q.GetPosition().x) - x,
                                                           pcbnew.ToMM(q.GetPosition().y) - y) < 0.05:
                        item = q
            if item is None:
                tr = [t for t in board.GetTracks() if t.GetNetCode() == nc and t.GetClass() != "PCB_VIA"]
                tr.sort(key=lambda t: _seg_dist((x, y, x, y, 0, None), _geom(t)))
                item = tr[0] if tr else (x - O[0], y - O[1])
            left = r.connect(name, [item, v], 0.12, layers=[pcbnew.F_Cu, pcbnew.B_Cu], via=(0.3, 0.15),
                             window=3.0, max_expand=1500000, greed=1.5)
            if left:
                board.Remove(v); GRAVE.append(v); R.changed()
                break
            ends.append(v)
        if len(ends) < 2:
            log(f"in2bridge {short(name)}: no via beside one end")
            continue
        ok = False
        for layers in ([pcbnew.In2_Cu], [pcbnew.In2_Cu, pcbnew.B_Cu]):
            left = r.connect(name, ends, 0.12, layers=layers, via=(0.3, 0.15), window=40.0, max_expand=12000000,
                             greed=1.3)
            if not left:
                ok = True
                break
        prune_dead_ends(board, nc, _dogbones(board, {nc}))
        R.changed()
        pcbnew.SaveBoard(ROUTED, board)
        log(f"in2bridge {short(name)}: " + ("bridged" if ok else "no way through on L3"))


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

def stage_rebuild(board, B, R):
    """After gen/respace.py (small parts re-spaced, low-speed copper ripped): GND vias at the moved parts, then the
    power rails, then the RK628D's nets (fewest pieces first, rip-up allowed among themselves), then the other
    signals (a plain pass, then rip-up on what is left)."""
    nets, bad = open_nets(board)
    log(f"rebuild: {sum(nets.values())} unconnected on {len(nets)} nets, {len(bad)} DRC errors")
    refs = set()
    for u in LAST_DRC[0]["unconnected_items"]:
        for it in u["items"]:
            m = re.match(r"Pad (\S+) \[GND\] of (\S+)", it["description"])
            if m:
                refs.add(m.group(2))
    miss = B.gnd_vias(R, sorted(refs), only_unconnected=True)
    pcbnew.SaveBoard(ROUTED, board)
    log(f"rebuild gnd: {len(refs)} parts with GND pads apart; no room for a via at {miss}")
    names = {short(n): n for n in nets}
    for nm in POWER_ORDER:
        if nm in names:
            left = route_net(R, board, names[nm], window=10.0)
            pcbnew.SaveBoard(ROUTED, board)
            log(f"rebuild power {nm}: " + ("done" if not left else f"{len(left)} pieces still apart"))
    stage_rebuild_rk(board, B, R)


def stage_reserve(board, B, R):
    """Every RK628D ball still without copper gets its dogbone (fanout via and stub) now, before any more routing
    takes the via sites; a site taken by low-speed routes is cleared (they are routed again later)."""
    nets, _ = open_nets(board)
    soft = soft_nets(board, u201_too=True)
    codes = {p.GetNetCode() for p in board.FindFootprintByReference("U201").Pads()}
    ripped = set()
    for n in nets:
        nc = board.FindNet(n).GetNetCode()
        if short(n) == "GND" or nc not in codes:
            continue
        ripped |= set(dogbone(board, R, n, soft - {nc}))
    for n in ripped:
        prune_dead_ends(board, board.FindNet(n).GetNetCode(), _dogbones(board))
    R.changed()
    log(f"reserve: dogbones placed; ripped for room: {sorted(short(n) for n in ripped)}")


def stage_rebuild_rk(board, B, R):
    """stage_rebuild from the RK628D nets on."""
    nets, _ = open_nets(board)
    codes = {p.GetNetCode() for p in board.FindFootprintByReference("U201").Pads()}
    soft = soft_nets(board, u201_too=True)
    # the chip's rails first (nothing may rip them later), then its signals; fewest pieces first in each
    rk = sorted((n for n in nets if short(n) != "GND" and board.FindNet(n).GetNetCode() in codes),
                key=lambda n: (short(n) in os.environ.get("LAST", "").split(","),
                               board.FindNet(n).GetNetCode() in soft, nets[n]))
    _ripup(board, R, rk, "rebuild-rk", u201_too=True)
    nets, _ = open_nets(board)
    rest = sorted((n for n in nets if short(n) != "GND" and board.FindNet(n).GetNetCode() not in codes),
                  key=nets.get)
    fails = []
    for k, n in enumerate(rest):
        left = route_net(R, board, n, window=8.0)
        pcbnew.SaveBoard(ROUTED, board)
        log(f"rebuild signal {k + 1}/{len(rest)} {short(n)}: " + ("done" if not left else "open"))
        if left:
            fails.append(n)
    _ripup(board, R, fails, "rebuild-ripup")
    nets, _ = open_nets(board)
    left = [n for n in nets if short(n) != "GND"]
    if left:
        _ripup(board, R, left, "rebuild-last", u201_too=True)


def stage_clfix(board, B, R):
    """Clearance errors on power-class tracks (routed before the router kept the POWER class's 0.127 mm from
    their own side): the offending pieces come out and the net is joined up again."""
    _, bad = open_nets(board)
    pw = NETCLASSES["POWER"][-1]
    doomed, nets = [], set()
    for v in bad:
        if v["type"] != "clearance":
            continue
        for it in v["items"]:
            m = re.match(r"(Track|Via) \[([^\]]+)\]", it["description"])
            if not m or not re.search(pw, short(m.group(2))):
                continue
            x, y = it["pos"]["x"], it["pos"]["y"]
            for t in board.GetTracks():
                if t.GetNetname() == m.group(2) and t.HitTest(pcbnew.VECTOR2I_MM(x, y)) and t not in doomed:
                    doomed.append(t)
                    nets.add(m.group(2))
    for t in doomed:
        board.Remove(t)
    GRAVE.extend(doomed)
    R.changed()
    for n in nets:
        left = route_net(R, board, n, window=10.0)
        pcbnew.SaveBoard(ROUTED, board)
        log(f"clfix {short(n)}: " + ("rejoined" if not left else f"{len(left)} pieces apart"))


def stage_neck(board, B, R):
    """Power-class tracks too close to a neighbouring pad (a wide trace leaving a fine-pitch connector pin):
    the offending pieces get narrower, just enough to keep the clearance (not below 0.2 mm)."""
    for rnd in range(3):
        _, bad = open_nets(board)
        n = 0
        for v in bad:
            m = re.search(r"clearance ([0-9.]+) mm; actual ([0-9.]+) mm", v.get("description", ""))
            if v["type"] != "clearance" or not m:
                continue
            short_by = float(m.group(1)) - float(m.group(2))
            for it in v["items"]:
                mt = re.match(r"Track \[([^\]]+)\]", it["description"])
                if not mt:
                    continue
                at = pcbnew.VECTOR2I_MM(it["pos"]["x"], it["pos"]["y"])
                for t in board.GetTracks():
                    if t.GetClass() != "PCB_VIA" and t.GetNetname() == mt.group(1) and t.HitTest(at):
                        w = pcbnew.ToMM(t.GetWidth())
                        nw = max(0.2, math.floor((w - 2 * short_by - 0.01) * 100) / 100)
                        if nw < w:
                            t.SetWidth(pcbnew.FromMM(nw))
                            n += 1
                            log(f"neck {short(mt.group(1))}: {w:.2f} -> {nw:.2f} mm at "
                                f"({it['pos']['x'] - O[0]:.2f}, {it['pos']['y'] - O[1]:.2f})")
        R.changed()
        if not n:
            break
        pcbnew.SaveBoard(ROUTED, board)


def stage_one(board, B, R):
    """Rip-up routing of the nets in $NETS (comma-separated short names) only: for testing one net at a time."""
    want = os.environ["NETS"].split(",")
    queue = [str(k) for k in board.GetNetsByName().keys() if short(str(k)) in want]
    _ripup(board, R, queue, "one", u201_too=True)


def draw_xtal(board, B, names):
    """The crystal lines as stage_north draws them (both on the top layer, no via)."""
    for n in ("XIN_628", "XOUT_628"):
        nc = board.FindNet(names[n]).GetNetCode()
        old = [t for t in board.GetTracks() if t.GetNetCode() == nc]
        for t in old:
            board.Remove(t)
        GRAVE.extend(old)

    def draw(net, pts, w=0.1):
        ni = board.FindNet(names[net])
        for a, b_ in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(B.mm(*a)); t.SetEnd(B.mm(*b_)); t.SetWidth(pcbnew.FromMM(w))
            t.SetLayer(pcbnew.F_Cu); t.SetNet(ni)
            board.Add(t)
    draw("XOUT_628", [(42.375, 18.075), (42.70, 17.75), (42.70, 13.25), (43.30, 12.65)])
    draw("XOUT_628", [(43.77, 12.3), (44.80, 12.3), (45.20, 12.09), (46.19, 12.09)])
    draw("XIN_628", [(42.375, 17.425), (42.375, 16.85), (41.57, 16.05), (41.57, 14.0)])
    draw("XIN_628", [(41.57, 14.0), (40.70, 13.13), (40.70, 10.6), (41.15, 10.15), (41.15, 9.91)])


def stage_xtal_draw(board, B, R):
    draw_xtal(board, B, {short(str(k)): str(k) for k in board.GetNetsByName().keys()})
    R.changed()
    pcbnew.SaveBoard(ROUTED, board)


def stage_north(board, B, R):
    """The crystal lines, drawn: both on the top layer with no via. XOUT leaves ball L9 through the row channel to
    the gap between balls M9 and M8 and runs north between the crystal's pads 1 and 2 to pad 3; XIN goes straight
    north from M9 (outer ring) to pad 1 and round pad 4's west side to C203; XOUT on to C204. What sat in their
    way (the DDC lines' fanout, and pieces of 1V1_628 and 3V3_IO north of the chip) comes out and is routed
    again around them."""
    names = {short(str(k)): str(k) for k in board.GetNetsByName().keys()}
    whole = [board.FindNet(names[n]).GetNetCode() for n in ("XIN_628", "XOUT_628", "RX_SDA", "RX_SCL")]
    box = (40.3, 9.3, 46.0, 18.5)
    rails = [board.FindNet(names[n]).GetNetCode() for n in ("1V1_628", "3V3_IO")]
    doomed = []
    for t in board.GetTracks():
        g = _geom(t)
        if t.GetNetCode() in whole:
            doomed.append(t)
        elif t.GetNetCode() in rails and (t.GetClass() == "PCB_VIA" or t.GetLayer() == pcbnew.F_Cu) and any(
                box[0] <= x - O[0] <= box[2] and box[1] <= y - O[1] <= box[3] for x, y in ((g[0], g[1]), (g[2], g[3]))):
            doomed.append(t)
    for t in doomed:
        board.Remove(t)
    GRAVE.extend(doomed)
    for nc in rails:
        prune_dead_ends(board, nc, _dogbones(board))

    draw_xtal(board, B, names)
    R.changed()
    pcbnew.SaveBoard(ROUTED, board)
    log(f"north: crystal lines drawn; {len(doomed)} items out")
    for n in ("1V1_628", "3V3_IO"):
        left = route_net(R, board, names[n], window=10.0)
        pcbnew.SaveBoard(ROUTED, board)
        log(f"north {n}: " + ("rejoined" if not left else f"{len(left)} pieces apart"))
    _ripup(board, R, [names["RX_SCL"], names["RX_SDA"]], "north", u201_too=True,
           fixed={board.FindNet(names[n]).GetNetCode() for n in ("XIN_628", "XOUT_628")})


COMMITTED = os.path.join(ROOT, "freerouting", "committed_routed.kicad_pcb")   # the rev A board before respace.py


def stage_restore_rails(board, B, R):
    """The low-speed RK628D signals routed since the re-spacing come out first (their dogbones stay): they took
    the room the rails had. The RK628D's analog and I/O rails under the chip: their copper from the board before the re-spacing comes
    back, item by item, wherever it still keeps its clearance from everything now on the board (respace.py's
    dead-end pruning took most of it out)."""
    u201 = {p.GetNetCode() for p in board.FindFootprintByReference("U201").Pads()}
    sig = soft_nets(board, u201_too=True) & u201 - {board.FindNet(n).GetNetCode() for n in
                                                    ("/HDMI in (RK628D)/XIN_628", "/HDMI in (RK628D)/XOUT_628")}
    _rip(board, R, sig)
    log(f"restore: ripped {sorted(short(board.FindNet(c).GetNetname()) for c in sig)}")
    old = pcbnew.LoadBoard(COMMITTED)
    rf = Router(board, O, (W, H), RK_BOX, res=0.025, clearance=0.1)
    layers = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
    for name in ("RK628D_3V3", "AVDD_3V3_628", "AVDD_1V1_628"):
        ni = [v for k, v in board.GetNetsByName().items() if short(str(k)) == name][0]
        nc = ni.GetNetCode()
        cand = [t for t in old.GetTracks() if short(t.GetNetname()) == name]
        have = {(round(_geom(t)[0], 3), round(_geom(t)[1], 3), round(_geom(t)[2], 3), round(_geom(t)[3], 3),
                 t.GetLayer() if t.GetClass() != "PCB_VIA" else -1) for t in board.GetTracks() if t.GetNetCode() == nc}
        grids = {}

        def free(x, y, half, lys):
            key = (round(half, 3), tuple(lys))
            if key not in grids:
                grids[key] = rf.blocked(nc, half, lys).any(axis=0)
            g = grids[key]
            i, j = int(round((x - O[0] - rf.x0) / rf.res)), int(round((y - O[1] - rf.y0) / rf.res))
            return 0 <= i < rf.nx and 0 <= j < rf.ny and not g[j, i]
        added = 0
        for t in cand:
            g = _geom(t)
            via = t.GetClass() == "PCB_VIA"
            k = (round(g[0], 3), round(g[1], 3), round(g[2], 3), round(g[3], 3), -1 if via else t.GetLayer())
            if k in have:
                continue
            if via:
                ok = free(g[0], g[1], pcbnew.ToMM(t.GetWidth()) / 2, layers)
            else:
                half = pcbnew.ToMM(t.GetWidth()) / 2
                n = max(2, int(math.hypot(g[2] - g[0], g[3] - g[1]) / 0.0125))
                ok = all(free(g[0] + (g[2] - g[0]) * s / n, g[1] + (g[3] - g[1]) * s / n, half, [t.GetLayer()])
                         for s in range(n + 1))
            if not ok:
                continue
            if via:
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(t.GetPosition()); v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetWidth(t.GetWidth()); v.SetDrill(t.GetDrill())
                v.SetNet(ni)
                board.Add(v)
            else:
                n_ = pcbnew.PCB_TRACK(board)
                n_.SetStart(t.GetStart()); n_.SetEnd(t.GetEnd()); n_.SetWidth(t.GetWidth())
                n_.SetLayer(t.GetLayer()); n_.SetNet(ni)
                board.Add(n_)
            added += 1
        rf.changed()
        R.changed()
        log(f"restore {name}: {added} of {len(cand)} old items back")
    pcbnew.SaveBoard(ROUTED, board)


def stage_rail_last(board, B, R):
    """RK628D_3V3's copper outside the chip's courtyard comes out (its dogbones and the copper under the chip
    stay); it is routed again after the chip's signals, 0.2 mm wide (stage rebuild_rk with LAST=RK628D_3V3)."""
    nc = board.FindNet("RK628D_3V3").GetNetCode()
    c = board.FindFootprintByReference("U201").GetCourtyard(pcbnew.F_CrtYd).BBox()
    box = (pcbnew.ToMM(c.GetLeft()), pcbnew.ToMM(c.GetTop()), pcbnew.ToMM(c.GetRight()), pcbnew.ToMM(c.GetBottom()))
    dog = _dogbones(board, {nc})
    doomed = [t for t in board.GetTracks() if t.GetNetCode() == nc and t.m_Uuid.AsString() not in dog and not all(
        box[0] <= x <= box[2] and box[1] <= y <= box[3] for x, y in ((_geom(t)[0], _geom(t)[1]), (_geom(t)[2], _geom(t)[3])))]
    for t in doomed:
        board.Remove(t)
    GRAVE.extend(doomed)
    prune_dead_ends(board, nc, dog)
    R.changed()
    pcbnew.SaveBoard(ROUTED, board)
    log(f"rail_last: {len(doomed)} RK628D_3V3 items out")
    os.environ["LAST"] = "RK628D_3V3"
    stage_rebuild_rk(board, B, R)


def stage_resetfix(board, B, R):
    """RK628D_RESET_N (ball H4) is walled in on the top layer by GND and AVDD_1V1_628 fanout vias. Drawn: a via on
    its free diagonal site, a hop on In1 (the GND plane, under the ball field only) along the row line between the
    via rows to a via beyond ball H1, and the top layer from there to its route east. RK628D_INT's back-layer trace
    sat on the new via's site; it is routed again."""
    names = {short(str(k)): str(k) for k in board.GetNetsByName().keys()}
    rst = board.FindNet(names["RK628D_RESET_N"])
    intc = board.FindNet(names["RK628D_INT"]).GetNetCode()
    _rip(board, R, {intc})

    def via(x, y):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(B.mm(x, y)); v.SetViaType(pcbnew.VIATYPE_THROUGH); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetWidth(pcbnew.FromMM(0.3)); v.SetDrill(pcbnew.FromMM(0.15)); v.SetNet(rst)
        board.Add(v)

    def track(layer, pts, w):
        for a, b_ in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(B.mm(*a)); t.SetEnd(B.mm(*b_)); t.SetWidth(pcbnew.FromMM(w)); t.SetLayer(layer)
            t.SetNet(rst)
            board.Add(t)
    via(45.95, 19.70)
    track(pcbnew.In1_Cu, [(45.95, 19.70), (46.275, 20.025), (47.575, 20.025), (47.90, 20.35)], 0.09)
    via(47.90, 20.35)
    track(pcbnew.F_Cu, [(47.90, 20.35), (48.15, 20.35)], 0.1)
    prune_dead_ends(board, rst.GetNetCode(), _dogbones(board))
    R.changed()
    pcbnew.SaveBoard(ROUTED, board)
    log("resetfix: RESET_N drawn through In1; RK628D_INT out")
    _ripup(board, R, [names["RK628D_INT"]], "resetfix", u201_too=True, fixed={rst.GetNetCode()})


def stage_resetfix2(board, B, R):
    """After resetfix: the AVDD_3V3_628 piece on In2 and the I2S_628_SCLK piece on the back that come too close to
    RESET_N's new vias come out; AVDD_3V3_628 is joined again (fine grid, small vias), then I2S_628_SCLK and
    RK628D_INT are routed again."""
    names = {short(str(k)): str(k) for k in board.GetNetsByName().keys()}
    rst = board.FindNet(names["RK628D_RESET_N"]).GetNetCode()
    vias = [_geom(t) for t in board.GetTracks() if t.GetNetCode() == rst and t.GetClass() == "PCB_VIA"]
    avdd = board.FindNet(names["AVDD_3V3_628"]).GetNetCode()
    sclk = board.FindNet(names["I2S_628_SCLK"]).GetNetCode()
    doomed = [t for t in board.GetTracks() if t.GetNetCode() == avdd and t.GetClass() != "PCB_VIA" and
              any(_seg_dist(v, _geom(t)) < 0.075 + _geom(t)[4] + 0.2 for v in vias)]
    for t in doomed:
        board.Remove(t)
    GRAVE.extend(doomed)
    _rip(board, R, {sclk})
    R.changed()
    if not RF:
        _configs(board, names["AVDD_3V3_628"], 0.1)
    left = RF[0].connect(names["AVDD_3V3_628"], net_terms(board, avdd), 0.1,
                         layers=[pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu], via=(0.3, 0.15), window=4.0,
                         max_expand=3000000, greed=1.5)
    pcbnew.SaveBoard(ROUTED, board)
    log(f"resetfix2: {len(doomed)} AVDD_3V3_628 pieces out, rejoined: {'yes' if not left else 'NO'}")
    _ripup(board, R, [names["I2S_628_SCLK"], names["RK628D_INT"]], "resetfix2", u201_too=True, fixed={rst, avdd})


def _drc_item(board, nc, it):
    """The board item a DRC report entry names (a pad, track or via of net nc at the reported spot)."""
    at = pcbnew.VECTOR2I_MM(it["pos"]["x"], it["pos"]["y"])
    m = re.match(r"Pad (\S+) \[[^\]]+\] of (\S+)", it["description"])
    if m:
        return board.FindFootprintByReference(m.group(2)).FindPadByNumber(m.group(1))
    for t in board.GetTracks():
        if t.GetNetCode() == nc and t.HitTest(at):
            return t
    return None


def stage_gaps(board, B, R):
    """Each unconnected pair DRC reports on the nets in $NETS, joined one pair at a time with a small search
    window: the RK628D-area router first (0.025 mm, small vias), then the 0.05 mm board router."""
    want = os.environ["NETS"].split(",")
    w = float(os.environ.get("WIDTH", "0.15"))
    _, _ = open_nets(board)
    if not RF:
        _configs(board, "/HDMI in (RK628D)/AVDD_3V3_628", 0.1)       # (makes the RK628D-area router)
    u201 = {p.GetNetCode() for p in board.FindFootprintByReference("U201").Pads()}
    if not FINE:
        FINE.append(make_router(board, 0.05))
    pairs = []
    for u in LAST_DRC[0]["unconnected_items"]:
        m = re.search(r"\[([^\]]+)\]", u["items"][0]["description"])
        if m and short(m.group(1)) in want:
            pairs.append((m.group(1), u["items"]))
    for name, items in pairs:
        nc = board.FindNet(name).GetNetCode()
        a, b_ = (_drc_item(board, nc, it) for it in items)
        if a is None or b_ is None:
            log(f"gaps {short(name)}: item not found")
            continue
        board.BuildConnectivity()
        if board.GetConnectivity().GetConnectedItems(a, False) and \
                b_ in list(board.GetConnectivity().GetConnectedItems(a, False)):
            continue                                   # joined already by an earlier pair's route
        def group(x):
            """x and everything copper-joined to it on its net (found geometrically: the connectivity API's
            connected items include the other islands)."""
            items = [p for f in board.GetFootprints() for p in f.Pads() if p.GetNetCode() == nc] + \
                [t for t in board.GetTracks() if t.GetNetCode() == nc]

            def pts(t):
                if t.GetClass() == "PCB_TRACK":
                    return [t.GetStart(), t.GetEnd()]
                return [t.GetPosition()]

            def lays(t):
                if t.GetClass() == "PCB_TRACK":
                    return {t.GetLayer()}
                return {l for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu) if t.IsOnLayer(l)}
            parent = list(range(len(items)))

            def find(i):
                while parent[i] != i:
                    parent[i] = parent[parent[i]]
                    i = parent[i]
                return i
            for i, u in enumerate(items):
                for j in range(i + 1, len(items)):
                    v = items[j]
                    if not (lays(u) & lays(v)):
                        continue
                    if any(v.HitTest(q) for q in pts(u)) or any(u.HitTest(q) for q in pts(v)):
                        parent[find(i)] = find(j)
            k = next(i for i, u in enumerate(items) if u.m_Uuid.AsString() == x.m_Uuid.AsString())
            return [u for i, u in enumerate(items) if find(i) == find(k)]
        ga, gb = (group(a), group(b_)) if os.environ.get("GROUPS") else ([a], [b_])
        ok = False
        tries = ((RF[0], w, 3.0), (RF[0], 0.1, 5.0)) if nc in u201 or name.endswith("RK628D_3V3") else ()
        for r, ww, win in tries + ((FINE[0], w, 6.0), (FINE[0], 0.1, 10.0)):
            lys = [pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu] + ([pcbnew.In1_Cu] if r is RF[0] and os.environ.get("IN1")
                                                                 else [])
            left = r.connect(name, [ga, gb], ww, layers=lys,
                             via=(0.3, 0.15), window=win, max_expand=int(os.environ.get("MAXEXP", "800000")), greed=1.5)
            # (a box router drops terminals outside its box and reports success: check the two really met)
            if not left and any(u.m_Uuid.AsString() == b_.m_Uuid.AsString() for u in group(a)):
                ok = True
                break
        R.changed()
        pcbnew.SaveBoard(ROUTED, board)
        log(f"gaps {short(name)}: {items[0]['description'][:30]} .. {items[1]['description'][:30]}: "
            + ("joined" if ok else "OPEN"))


def stage_dejunk(board, B, R):
    """Copper left over from failed tries: on every low-speed signal net, each track or via whose removal leaves
    the net exactly as connected (part of a loop or a spur) comes out, then dead ends are pruned. RK628D dogbones,
    the crystal lines and the power, regulator and high-speed nets are left alone."""
    soft = soft_nets(board, u201_too=True)
    dog = _dogbones(board)
    out = 0
    for nc in sorted(soft):
        items = [t for t in board.GetTracks() if t.GetNetCode() == nc and t.m_Uuid.AsString() not in dog]
        if not items:
            continue
        board.BuildConnectivity()
        base = board.GetConnectivity().GetUnconnectedCount(False)
        for t in sorted(items, key=lambda t: t.GetClass() != "PCB_VIA"):   # vias first: their loops are the cost
            board.Remove(t)
            board.BuildConnectivity()
            if board.GetConnectivity().GetUnconnectedCount(False) > base:
                board.Add(t)
            else:
                GRAVE.append(t)
                out += 1
        prune_dead_ends(board, nc, dog)
    R.changed()
    pcbnew.SaveBoard(ROUTED, board)
    log(f"dejunk: {out} redundant items out")


def _restore(board, names, res=0.05, source=None):
    """Copper of these nets from the board before the re-spacing, item by item, wherever it still keeps its
    clearance from everything now on the board. Returns {name: (items back, items before)}."""
    old = pcbnew.LoadBoard(source or COMMITTED)
    r = Router(board, O, (W, H), (0.0, 0.0, W, H), res=res, clearance=0.1)
    pw = NETCLASSES["POWER"][-1]
    for nm, ni in board.GetNetsByName().items():
        if re.search(pw, short(str(nm))):
            r.net_cl[ni.GetNetCode()] = 0.127
    layers = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
    by = {}
    for t in old.GetTracks():
        by.setdefault(short(t.GetNetname()), []).append(t)
    out = {}
    for name in names:
        ni = [v for k, v in board.GetNetsByName().items() if short(str(k)) == name][0]
        nc = ni.GetNetCode()
        grids = {}
        have = {(round(_geom(t)[0], 3), round(_geom(t)[1], 3), round(_geom(t)[2], 3), round(_geom(t)[3], 3),
                 _geom(t)[5]) for t in board.GetTracks() if t.GetNetCode() == nc}

        def free(x, y, half, lys):
            key = (round(half, 3), tuple(lys))
            if key not in grids:
                grids[key] = r.blocked(nc, half, lys).any(axis=0)
            g = grids[key]
            i, j = int(round((x - O[0] - r.x0) / r.res)), int(round((y - O[1] - r.y0) / r.res))
            return 0 <= i < r.nx and 0 <= j < r.ny and not g[j, i]
        added = 0
        for t in by.get(name, []):
            g = _geom(t)
            if t.GetClass() == "PCB_VIA":
                ok = free(g[0], g[1], pcbnew.ToMM(t.GetWidth()) / 2, layers)
            else:
                half = pcbnew.ToMM(t.GetWidth()) / 2
                n = max(2, int(math.hypot(g[2] - g[0], g[3] - g[1]) / (r.res / 2)))
                ok = all(free(g[0] + (g[2] - g[0]) * s_ / n, g[1] + (g[3] - g[1]) * s_ / n, half, [t.GetLayer()])
                         for s_ in range(n + 1))
            if not ok or (k_ := (round(g[0], 3), round(g[1], 3), round(g[2], 3), round(g[3], 3), g[5])) in have:
                continue
            have.add(k_)
            if t.GetClass() == "PCB_VIA":
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(t.GetPosition()); v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetWidth(t.GetWidth()); v.SetDrill(t.GetDrill())
            else:
                v = pcbnew.PCB_TRACK(board)
                v.SetStart(t.GetStart()); v.SetEnd(t.GetEnd()); v.SetWidth(t.GetWidth()); v.SetLayer(t.GetLayer())
            v.SetNet(ni)
            board.Add(v)
            added += 1
        r.changed()
        out[name] = (added, len(by.get(name, [])))
    R_ = ROUTERS[0] if ROUTERS else None
    if R_:
        R_.changed()
    return out


def stage_restore_signals(board, B, R):
    """The low-speed signals away from the RK628D: what this rebuild routed of them comes out, and their routes
    from the board before the re-spacing come back wherever they still fit (their connectors did not move); dead
    ends are pruned. What is left open is routed afterwards (stage rebuild_rk)."""
    u201 = {p.GetNetCode() for p in board.FindFootprintByReference("U201").Pads()}
    codes = soft_nets(board, u201_too=True) - u201
    names = sorted(short(board.FindNet(c).GetNetname()) for c in codes)
    old = pcbnew.LoadBoard(COMMITTED)
    oldnames = {short(t.GetNetname()) for t in old.GetTracks()}
    allsig = [short(str(k)) for k, v in board.GetNetsByName().items() if v.GetNetCode() not in u201 and
              short(str(k)) in oldnames and not any(re.search(c[-1], short(str(k))) for c in NETCLASSES.values())
              and short(str(k)) not in POWER_ORDER and short(str(k)) != "GND" and
              not re.match(r"(FB|BS|BST|FS|CT)\d*(_|$)|AVDD|RK628D_3V3|1V1_628|XIN_628|XOUT_628", short(str(k)))]
    _rip(board, R, codes)
    log(f"restore_signals: ripped {len(codes)} nets")
    got = _restore(board, allsig)              # no pruning: a route missing a piece keeps both halves for stage gaps
    R.changed()
    pcbnew.SaveBoard(ROUTED, board)
    log("restore_signals: " + ", ".join(f"{n} {a}/{b}" for n, (a, b) in sorted(got.items())))
    nets, _ = open_nets(board)
    os.environ["NETS"] = ",".join(short(n) for n in nets if short(n) in allsig)
    os.environ["GROUPS"] = "1"
    stage_gaps(board, B, R)


def stage_restore_from(board, B, R):
    """$NETS' copper from the checkpoint $FROM, wherever it fits (items already here are skipped)."""
    got = _restore(board, os.environ["NETS"].split(","), source=os.environ["FROM"])
    R.changed()
    pcbnew.SaveBoard(ROUTED, board)
    log("restore_from: " + ", ".join(f"{n} {a}/{b}" for n, (a, b) in sorted(got.items())))


def stage_restore_open(board, B, R):
    """Every low-speed signal net still open (not the RK628D's) gets its route from the board before the
    re-spacing back wherever it fits, with no pruning: a route with one piece that no longer fits stays as two
    pieces with a short gap, which stage gaps then closes."""
    nets, _ = open_nets(board)
    u201 = {p.GetNetCode() for p in board.FindFootprintByReference("U201").Pads()}
    names = [short(n) for n in nets if short(n) != "GND" and board.FindNet(n).GetNetCode() not in u201]
    got = _restore(board, names)
    R.changed()
    pcbnew.SaveBoard(ROUTED, board)
    log("restore_open: " + ", ".join(f"{n} {a}/{b}" for n, (a, b) in sorted(got.items())))
    os.environ["NETS"] = ",".join(names)
    os.environ["GROUPS"] = "1"
    stage_gaps(board, B, R)


def stage_revert_parts(board, B, R):
    """Small parts gen/respace.py moved that sit on a net still open: each goes back to its place on the board before
    the re-spacing (side, position, rotation) when that spot is free of every other part's courtyard now, and
    its nets' copper comes out, to be restored from that board and gap-filled (stage restore_signals)."""
    nets, _ = open_nets(board)
    openc = {board.FindNet(n).GetNetCode() for n in nets if short(n) != "GND"}
    old = pcbnew.LoadBoard(COMMITTED)

    def court(f):
        side = pcbnew.B_CrtYd if f.IsFlipped() else pcbnew.F_CrtYd
        c = f.GetCourtyard(side)
        bb = c.BBox() if c.OutlineCount() else f.GetBoundingBox(False)
        return (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())
    moved = []
    group = set(os.environ.get("GROUP", "").split(",")) - {""}     # these go back together, whatever their nets
    for f in board.GetFootprints():
        g = old.FindFootprintByReference(f.GetReference())
        if g is None or (not any(p.GetNetCode() in openc for p in f.Pads()) and f.GetReference() not in group):
            continue
        if f.GetPosition() == g.GetPosition() and f.IsFlipped() == g.IsFlipped():
            continue
        oc = court(g)
        clash = [h.GetReference() for h in board.GetFootprints() if h.GetReference() != f.GetReference()
                 and h.GetReference() not in group and h.IsFlipped() == g.IsFlipped() and not (court(h)[2] <= oc[0] or court(h)[0] >= oc[2] or
                                                             court(h)[3] <= oc[1] or court(h)[1] >= oc[3])]
        if clash:
            log(f"revert {f.GetReference()}: old spot taken by {clash}")
            continue
        moved.append(f.GetReference())
        if f.IsFlipped() != g.IsFlipped():
            f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        f.SetPosition(g.GetPosition())
        f.SetOrientation(g.GetOrientation())
    codes = {p.GetNetCode() for r in moved for p in board.FindFootprintByReference(r).Pads()} - \
        {board.FindNet("GND").GetNetCode()}
    codes = {c for c in codes if c in soft_nets(board, u201_too=True) or c in openc}
    _rip(board, R, codes)
    R.changed()
    pcbnew.SaveBoard(ROUTED, board)
    log(f"revert: {moved} back in place; ripped {sorted(short(board.FindNet(c).GetNetname()) for c in codes)}")


def stage_repin(board, B, R):
    """RK628D_INT and RK628D_PWR_EN move from J69 (J701) pins 46 and 24 to J1 (J703) pins 93 and 95 (gen/module.py):
    the pads change nets, the two nets' copper outside the RK628D corner comes out (the corner's escape stays),
    and stage gaps joins them to the new pins."""
    moves = {("J701", "46"): None, ("J701", "24"): None, ("J703", "93"): "RK628D_INT", ("J703", "95"): "RK628D_PWR_EN"}
    for (ref, num), net in moves.items():
        pad = board.FindFootprintByReference(ref).FindPadByNumber(num)
        if net is None:
            pad.SetNetCode(0)
        else:
            pad.SetNet(board.FindNet(net))
    codes = {board.FindNet(n).GetNetCode() for n in ("RK628D_INT", "RK628D_PWR_EN")}
    box = (12.0, 2.0, 54.0, 32.0)
    doomed = [t for t in board.GetTracks() if t.GetNetCode() in codes and not all(
        box[0] <= x - O[0] <= box[2] and box[1] <= y - O[1] <= box[3]
        for x, y in ((_geom(t)[0], _geom(t)[1]), (_geom(t)[2], _geom(t)[3])))]
    for t in doomed:
        board.Remove(t)
    GRAVE.extend(doomed)
    for c in codes:
        prune_dead_ends(board, c, _dogbones(board))
    R.changed()
    pcbnew.SaveBoard(ROUTED, board)
    log(f"repin: pads moved, {len(doomed)} items out")
    os.environ["NETS"] = "RK628D_INT,RK628D_PWR_EN"
    os.environ["GROUPS"] = "1"
    stage_gaps(board, B, R)


def stage_escape(board, B, R):
    """$NET's RK628D ball out of the ball field: the 0.025 mm RK628D-area router (In1 allowed under the chip) from
    the net's copper there to the first of the points $TO ('x,y x,y ...', board mm) it can reach."""
    name = [str(k) for k in board.GetNetsByName().keys() if short(str(k)) == os.environ["NET"]][0]
    nc = board.FindNet(name).GetNetCode()
    if not RF:
        _configs(board, "/HDMI in (RK628D)/AVDD_3V3_628", 0.1)
    _pin(board)
    mine = [t for t in board.GetTracks() if t.GetNetCode() == nc] + \
        [p for p in board.FindFootprintByReference("U201").Pads() if p.GetNetCode() == nc]
    for pt in os.environ["TO"].split():
        x, y = (float(v) for v in pt.split(","))
        left = RF[0].connect(name, [mine, (x, y)], 0.1,
                             layers=[pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu, pcbnew.In1_Cu], via=(0.3, 0.15),
                             window=4.0, max_expand=4000000, greed=1.5)
        log(f"escape {short(name)} to ({x}, {y}): " + ("out" if not left else "no"))
        if not left:
            break
    R.changed()
    pcbnew.SaveBoard(ROUTED, board)


# placement fixes after the review of Oct 24: (ref, side "F"/"B", x, y, rotation) or a rotation alone ("+180")
PLACEFIX = [
    ("L103", "+180"),                    # its switch pad faced away from U105's SW pin (7.4 mm): now 3 mm
    ("L104", "+180"),                    # the same at U106 (7.5 mm)
    ("C121", "F", 28.45, 29.6, 270),     # U106's bootstrap cap beside pins 6 (BST) and 2 (SW), west of the IC
    ("C203", "F", 39.85, 14.0, 180),     # crystal load caps against the crystal's pads (were 4 mm out)
    ("C204", "F", 45.55, 12.3, 0),
    ("D101", "+180"),                    # VIN_RAW toward the fuse, VDC toward the jack
    ("D103", "+180"),                    # VBUS_SW toward the USB-C switch, VIN_RAW toward the fuse
]
PLACEFIX_INT = [("C207", "B", 49.05, 18.22, 90)]    # 1 mm east: frees a via site at the ball field's east edge


def stage_intfix(board, B, R):
    """RK628D_INT out of the ball field: C207 (a 100 nF on RK628D_3V3, on the back at the east edge) moves 1 mm
    east, then the RK628D-area router (In1 allowed under the chip) takes INT from its fanout via to the edge,
    stage gaps joins it to J703 pin 93, and C207 is joined again."""
    global PLACEFIX
    keep, PLACEFIX = PLACEFIX, PLACEFIX_INT
    f = board.FindFootprintByReference("C207")
    nets = {p.GetNetCode() for p in f.Pads()}
    doomed = [t for t in board.GetTracks() if t.GetNetCode() in nets and any(
        (p.HitTest(t.GetPosition()) if t.GetClass() == "PCB_VIA" else (p.HitTest(t.GetStart()) or p.HitTest(t.GetEnd())))
        for p in f.Pads() if p.GetNetCode() == t.GetNetCode())]
    for t in doomed:
        board.Remove(t)
    GRAVE.extend(doomed)
    prune_dead_ends(board, board.FindNet("RK628D_3V3").GetNetCode(), _dogbones(board))
    _, side, x, y, rot = PLACEFIX_INT[0]
    f.SetPosition(B.mm(x, y)); f.SetOrientationDegrees(rot)
    PLACEFIX = keep
    R.changed()
    pcbnew.SaveBoard(ROUTED, board)
    log(f"intfix: C207 moved, {len(doomed)} items out")
    os.environ["NET"] = "RK628D_INT"
    os.environ.setdefault("TO", "49.3,18.7 49.3,19.4 49.3,20.1 49.3,18.0 49.6,19.0")
    stage_escape(board, B, R)
    os.environ["NETS"] = "RK628D_INT,RK628D_3V3"
    os.environ["GROUPS"] = "1"
    stage_gaps(board, B, R)
    B.gnd_vias(R, ["C207"], only_unconnected=True)
    R.changed()


def stage_placefix(board, B, R):
    """Moves the parts in PLACEFIX (and C702/C703 next to the CM3's SOM_3V3/SOM_1V8 pins, on the back), with
    the copper that touched their pads taken out first; their nets are joined again afterwards (stage
    gaps/route_net) and GND pads get vias."""
    moved = [m[0] for m in PLACEFIX] + ["C702", "C703"]
    nets = set()
    doomed = []
    for ref in moved:
        f = board.FindFootprintByReference(ref)
        for p in f.Pads():
            if p.GetNetCode() == 0:
                continue
            nets.add(p.GetNetCode())
            for t in board.GetTracks():
                if t.GetNetCode() != p.GetNetCode() or t in doomed:
                    continue
                if t.GetClass() == "PCB_VIA":
                    hit = p.HitTest(t.GetPosition())
                else:
                    hit = p.HitTest(t.GetStart()) or p.HitTest(t.GetEnd())
                if hit:
                    doomed.append(t)
    for t in doomed:
        board.Remove(t)
    GRAVE.extend(doomed)
    gnd = board.FindNet("GND").GetNetCode()
    for nc in nets - {gnd}:
        prune_dead_ends(board, nc, _dogbones(board))
    for m in PLACEFIX:
        f = board.FindFootprintByReference(m[0])
        if len(m) == 2:
            f.SetOrientationDegrees((f.GetOrientationDegrees() + 180) % 360)
        else:
            _, side, x, y, rot = m
            if f.IsFlipped() != (side == "B"):
                f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
            f.SetOrientationDegrees(rot)
            f.SetPosition(B.mm(x, y))
    R.changed()
    # C702/C703: on the back, as near the SOM_3V3 / SOM_1V8 pins' vias as there is room
    for ref, net in (("C702", "SOM_3V3"), ("C703", "SOM_1V8")):
        pins = [p for p in board.FindFootprintByReference("J701").Pads() if short(p.GetNetname()) == net]
        tx = sum(B.xy(p)[0] for p in pins) / len(pins)
        best = place_near(B, R, ref, {net: (tx, 64.6), "GND": (tx, 64.6)}, back=True, span=3.0, step=0.1, keepout=[])
        log(f"placefix {ref}: back at ({best[1]:.2f}, {best[2]:.2f}), {best[3]} deg")
    pcbnew.SaveBoard(ROUTED, board)
    log(f"placefix: {len(doomed)} items out on {len(nets)} nets; moved {moved}")


def stage_placefix2(board, B, R):
    """Second round of stage placefix: the crystal's load caps and C702/C703 found spots free of other copper
    (place_near), and the 1V1_628 copper left beside L104's turned switch pad comes out."""
    y = board.FindFootprintByReference("Y201")
    yp = {p.GetNumber(): B.xy(p) for p in y.Pads()}
    for ref, net, pin, gnd in (("C203", "XIN_628", "1", "4"), ("C204", "XOUT_628", "3", "2")):
        f = board.FindFootprintByReference(ref)
        f.SetPosition(B.mm(200, 200))              # off the board while its spot is chosen
        R.changed()
        best = None
        for back in (False, True):
            try:
                b_ = place_near(B, R, ref, {net: yp[pin], "GND": yp[gnd]}, back=back, span=3.0, step=0.05, keepout=[])
            except SystemExit:
                continue
            if best is None or b_[0] < best[0] - 1.0:      # the back only if clearly better
                best = b_ + (back,)
        _, x, y_, rot, back = best
        if f.IsFlipped() != back:
            f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        f.SetOrientationDegrees(rot); f.SetPosition(B.mm(x, y_))
        R.changed()
        log(f"placefix2 {ref}: {'back' if back else 'top'} at ({x:.2f}, {y_:.2f}), {rot} deg")
    for ref, net in (("C702", "SOM_3V3"), ("C703", "SOM_1V8")):
        f = board.FindFootprintByReference(ref)
        f.SetPosition(B.mm(200, 200))
        R.changed()
        pins = [p for p in board.FindFootprintByReference("J701").Pads() if short(p.GetNetname()) == net]
        tx = sum(B.xy(p)[0] for p in pins) / len(pins)
        best = place_near(B, R, ref, {net: (tx, 63.2), "GND": (tx, 63.2)}, back=True, span=4.0, step=0.1,
                          keepout=[(55.0, 63.4, 90.0, 72.0)])
        log(f"placefix2 {ref}: back at ({best[1]:.2f}, {best[2]:.2f}), {best[3]} deg")
    l = board.FindFootprintByReference("L104")
    sw = [B.xy(p) for p in l.Pads() if short(p.GetNetname()) == "SW_628"][0]
    nc = board.FindNet("1V1_628").GetNetCode()
    doomed = [t for t in board.GetTracks() if t.GetNetCode() == nc and
              min(math.hypot(_geom(t)[0] - O[0] - sw[0], _geom(t)[1] - O[1] - sw[1]),
                  math.hypot(_geom(t)[2] - O[0] - sw[0], _geom(t)[3] - O[1] - sw[1])) < 2.6]
    for t in doomed:
        board.Remove(t)
    GRAVE.extend(doomed)
    prune_dead_ends(board, nc, _dogbones(board))
    R.changed()
    pcbnew.SaveBoard(ROUTED, board)
    log(f"placefix2: {len(doomed)} 1V1_628 items beside L104 out")


def stage_placefix_route(board, B, R):
    """After placefix/placefix2: GND vias at the moved parts' GND pads, then their power nets joined again (switch
    nodes first, wide where there is room), then the crystal and the other signals by stage gaps."""
    miss = B.gnd_vias(R, ["C121", "C203", "C204", "C702", "C703"], only_unconnected=True)
    log(f"placefix_route: GND vias placed; no room at {miss}")
    names = {short(str(k)): str(k) for k in board.GetNetsByName().keys()}
    for n in ("SW_IO", "SW_628", "BST_628", "BST_IO", "3V3_IO", "1V1_628", "VIN_RAW", "VDC", "VBUS_SW", "SOM_3V3",
              "SOM_1V8"):
        left = route_net(R, board, names[n], window=10.0)
        pcbnew.SaveBoard(ROUTED, board)
        log(f"placefix_route {n}: " + ("joined" if not left else f"{len(left)} pieces apart"))
    nets, _ = open_nets(board)
    os.environ["NETS"] = ",".join(short(n) for n in nets if short(n) not in ("GND", "RK628D_INT"))
    os.environ["GROUPS"] = "1"
    stage_gaps(board, B, R)


def stage_c207(board, B, R):
    """C207 (100 nF on RK628D_3V3, on the back) had no way left to its rail at the chip's east edge (INT and SCL
    now leave there): it goes, still on the back, next to one of the rail's vias north of the chip, is joined to
    it and gets a GND via."""
    f = board.FindFootprintByReference("C207")
    nc = board.FindNet("RK628D_3V3").GetNetCode()
    doomed = [t for t in board.GetTracks() if t.GetNetCode() == nc and any(
        (p.HitTest(t.GetPosition()) if t.GetClass() == "PCB_VIA" else (p.HitTest(t.GetStart()) or p.HitTest(t.GetEnd())))
        for p in f.Pads())]
    for t in doomed:
        board.Remove(t)
    GRAVE.extend(doomed)
    f.SetPosition(B.mm(200, 200))
    R.changed()
    best = place_near(B, R, "C207", {"RK628D_3V3": (44.85, 14.15), "GND": (44.85, 14.15)}, back=True, span=3.0,
                      step=0.05, keepout=[])
    log(f"c207: back at ({best[1]:.2f}, {best[2]:.2f}), {best[3]} deg")
    pcbnew.SaveBoard(ROUTED, board)
    os.environ["NETS"] = "RK628D_3V3"
    os.environ["GROUPS"] = "1"
    stage_gaps(board, B, R)
    B.gnd_vias(R, ["C207"], only_unconnected=True)
    R.changed()


def stage_gndpads(board, B, R):
    """GND pads still cut off from the planes (islands.py: mostly connector pins between other nets' traces): each
    gets a small via (0.3/0.15 mm) to the inner GND planes, reached by a straight trace from the pad on its own layer
    (0.15 mm, or 0.1 mm), at the nearest spot where both keep their clearances. Every candidate is checked against
    everything on the board (gen/handroute.py's rules) before it is added."""
    import handroute as H
    gnd = board.FindNet("GND")
    gc = gnd.GetNetCode()
    subprocess.run([KP, os.path.join(HERE, "finish.py")], capture_output=True)
    r = subprocess.run([KP, os.path.join(HERE, "islands.py")], capture_output=True, text=True)
    isl = json.loads([l for l in r.stdout.splitlines() if l.startswith("[")][-1])
    others = H.obstacles(board, gc)
    done, failed = 0, []
    for il in isl:
        ok = False
        for ref, num in il["pads"]:
            f = board.FindFootprintByReference(ref)
            p = f.FindPadByNumber(num)
            x, y = B.xy(p)
            lay = "B" if f.IsFlipped() and not p.HasHole() else "F"
            near = [o for o in others if min(math.dist(o[1], (x, y)), math.dist(o[2], (x, y))) < 4 or
                    H.seg_dist(o[1], o[2], (x - 3, y - 3), (x + 3, y + 3)) < 3]
            cands = []
            for rad in [0.45 + 0.05 * k for k in range(42)]:
                for a in range(0, 360, 10):
                    vx, vy = round(x + rad * math.cos(math.radians(a)), 3), round(y + rad * math.sin(math.radians(a)), 3)
                    cands.append((rad, vx, vy))
            # also: out along the pad's long axis first (between a connector's neighbouring pins), then to the via
            bb = p.GetBoundingBox()
            ax = (1, 0) if bb.GetWidth() >= bb.GetHeight() else (0, 1)
            half = max(pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())) / 2
            paths = [[(x, y), (vx, vy)] for _, vx, vy in cands]
            for sgn in (1, -1):
                for ext in [half + 0.2 + 0.1 * k for k in range(16)]:
                    ex, ey = round(x + sgn * ax[0] * ext, 3), round(y + sgn * ax[1] * ext, 3)
                    for rad in (0.0, 0.35, 0.5, 0.7):
                        for a in range(0, 360, 30 if rad else 360):
                            vx, vy = round(ex + rad * math.cos(math.radians(a)), 3), round(ey + rad * math.sin(math.radians(a)), 3)
                            paths.append([(x, y), (ex, ey), (vx, vy)] if rad else [(x, y), (ex, ey)])
            paths.sort(key=lambda pp: sum(math.dist(a_, b_) for a_, b_ in zip(pp, pp[1:])))
            # first choice: a trace to a GND via already there (it reaches the planes); straight or one bend
            gv = [B.xy(t) for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetCode() == gc
                  and math.dist(B.xy(t), (x, y)) < 3.0]
            joins = []
            for vx, vy in gv:
                joins += [[(x, y), (vx, vy)], [(x, y), (vx, y), (vx, vy)], [(x, y), (x, vy), (vx, vy)]]
            joins.sort(key=lambda pp: sum(math.dist(a_, b_) for a_, b_ in zip(pp, pp[1:])))
            for pp in joins:
                for w in (0.2, 0.15, 0.1):
                    new = H.parse([f"{lay}/{w}:" + " ".join(f"{a_},{b_}" for a_, b_ in pp)])
                    if H.problems(new, near, quiet=True) == 0:
                        for ly, a_, b_, h, dr in new:
                            t = pcbnew.PCB_TRACK(board)
                            t.SetStart(B.mm(*a_)); t.SetEnd(B.mm(*b_)); t.SetWidth(pcbnew.FromMM(2 * h))
                            t.SetLayer(ly); t.SetNet(gnd)
                            board.Add(t)
                        ok = True
                        break
                if ok:
                    break
            if ok:
                break
            mine = [(round(g[0], 3), round(g[1], 3)) for g in (B.xy(t) for t in board.GetTracks()
                                                             if t.GetClass() == "PCB_VIA" and t.GetNetCode() == gc)]
            for pp in paths:
                vx, vy = pp[-1]
                if any(math.dist((vx, vy), m) < 0.15 + 0.075 + 0.25 + 0.075 - 0.15 + 0.4 for m in mine):
                    continue                                     # own-net hole spacing (0.25 mm hole to hole)
                for w in (0.15, 0.1):
                    new = H.parse([f"{lay}/{w}:" + " ".join(f"{a_},{b_}" for a_, b_ in pp), f"V:{vx},{vy}"])
                    if H.problems(new, near, quiet=True) == 0:
                        for ly, a_, b_, h, dr in new:
                            if ly is None:
                                v = pcbnew.PCB_VIA(board)
                                v.SetPosition(B.mm(*a_)); v.SetViaType(pcbnew.VIATYPE_THROUGH)
                                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                                v.SetWidth(pcbnew.FromMM(0.3)); v.SetDrill(pcbnew.FromMM(0.15)); v.SetNet(gnd)
                                board.Add(v)
                                others.append((None, a_, a_, 0.15, 0.075, "via GND"))
                            else:
                                t = pcbnew.PCB_TRACK(board)
                                t.SetStart(B.mm(*a_)); t.SetEnd(B.mm(*b_)); t.SetWidth(pcbnew.FromMM(2 * h))
                                t.SetLayer(ly); t.SetNet(gnd)
                                board.Add(t)
                        ok = True
                        break
                if ok:
                    break
            if ok:
                break
        if ok:
            done += 1
        else:
            failed.append(il["pads"])
    R.changed()
    pcbnew.SaveBoard(ROUTED, board)
    log(f"gndpads: {done} of {len(isl)} islands joined to the planes; no room at {failed}")


GNDFORCE = [   # (pad, GND path in gen/handroute.py's notation): low-speed signals in the way are ripped and rerouted
    ("C207.2", ["B/0.2:50.23,14.95 50.23,16.04 49.11,16.04"]),
    ("C218.2", ["B/0.2:48.35,22.95 47.15,22.95 47.15,22.55"]),
]
GNDFORCE_D203 = [("D203.3/8", ["F/0.2:31.07,13.09 31.07,13.86", "V:31.07,13.475"])]   # after R217 moved off


def stage_gndforce(board, B, R):
    """Decoupling caps whose GND pad could not reach the planes: a short GND trace to the nearest GND via or pad,
    with the low-speed signal traces in its way taken out first and routed again afterwards (stage gaps)."""
    import handroute as H
    gnd = board.FindNet("GND")
    gc = gnd.GetNetCode()
    soft = soft_nets(board, u201_too=True)
    ripped = set()
    todo = GNDFORCE_D203 if os.environ.get("D203") else GNDFORCE
    if os.environ.get("AUTO"):
        # every GND pad still cut off: out along the pad's axis to a via, the candidate whose only conflicts are
        # low-speed signal tracks (fewest first), those tracks cut and joined again afterwards
        subprocess.run([KP, os.path.join(HERE, "finish.py")], capture_output=True)
        r = subprocess.run([KP, os.path.join(HERE, "islands.py")], capture_output=True, text=True)
        isl = json.loads([l for l in r.stdout.splitlines() if l.startswith("[")][-1])
        softn = {short(board.FindNet(c).GetNetname()) for c in soft}
        allob = H.obstacles(board, gc)
        mine = [B.xy(t) for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetCode() == gc]
        todo = []
        skip = set(os.environ.get("SKIP", "").split(","))
        for il in isl:
            ref, num = il["pads"][0]
            if f"{ref}.{num}" in skip:
                continue
            f = board.FindFootprintByReference(ref)
            p = f.FindPadByNumber(num)
            x, y = B.xy(p)
            lay = "B" if f.IsFlipped() and not p.HasHole() else "F"
            bb = p.GetBoundingBox()
            ax = (1, 0) if bb.GetWidth() >= bb.GetHeight() else (0, 1)
            half = max(pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())) / 2
            near = [o for o in allob if min(math.dist(o[1], (x, y)), math.dist(o[2], (x, y))) < 4 or
                    H.seg_dist(o[1], o[2], (x - 3, y - 3), (x + 3, y + 3)) < 3]
            best = None
            for sgn in (1, -1):
                for ext in [half + 0.25 + 0.1 * k for k in range(12)]:
                    vx, vy = round(x + sgn * ax[0] * ext, 3), round(y + sgn * ax[1] * ext, 3)
                    if any(math.dist((vx, vy), m) < 0.45 for m in mine):
                        continue
                    specs = [f"{lay}/0.15:{x},{y} {vx},{vy}", f"V:{vx},{vy}"]
                    new = H.parse(specs)
                    hits, hard = set(), False
                    for ly, a, b_, h, dr in new:
                        for oly, oa, ob, oh, odr, desc in near:
                            same = ly is None or oly is None or ly in oly
                            d = H.seg_dist(a, b_, oa, ob)
                            bad = (same and d < h + oh + 0.1) or (dr and d - dr - oh < 0.2) or \
                                (odr and same and d - odr - h < 0.2) or (dr and odr and d - dr - odr < 0.25)
                            if bad:
                                if desc.startswith("track ") and desc.split()[1] in softn:
                                    hits.add(desc.split()[1])
                                else:
                                    hard = True
                    if not hard and (best is None or len(hits) < best[0]):
                        best = (len(hits), specs)
            if best:
                todo.append((f"{ref}.{num}", best[1]))
                mine.append(tuple(float(v) for v in best[1][1][2:].split(",")))
            else:
                log(f"gndforce {ref}.{num}: no candidate free of fixed copper")
    for pad, specs in todo:
        new = H.parse(specs)
        others = H.obstacles(board, gc)
        hit = set()
        for ly, a, b_, h, dr in new:
            for oly, oa, ob, oh, odr, desc in others:
                same = ly is None or oly is None or ly in oly
                if same and H.seg_dist(a, b_, oa, ob) < h + oh + 0.1 + 0.01 and desc.startswith("track "):
                    hit.add(desc.split()[1])
        codes = {c for c in soft if short(board.FindNet(c).GetNetname()) in hit}
        if hit - {short(board.FindNet(c).GetNetname()) for c in codes}:
            log(f"gndforce {pad}: blocked by fixed nets {sorted(hit)}; skipped")
            continue
        # only the pieces in the way come out (a whole long route would be hard to get back)
        cut = []
        for t in board.GetTracks():
            if t.GetNetCode() not in codes or t.GetClass() == "PCB_VIA":
                continue
            g = ((pcbnew.ToMM(t.GetStart().x) - O[0], pcbnew.ToMM(t.GetStart().y) - O[1]),
                 (pcbnew.ToMM(t.GetEnd().x) - O[0], pcbnew.ToMM(t.GetEnd().y) - O[1]))
            for ly, a, b_, h, dr in new:
                if (ly is None or ly == t.GetLayer()) and \
                        H.seg_dist(a, b_, g[0], g[1]) < h + pcbnew.ToMM(t.GetWidth()) / 2 + 0.1 + 0.01:
                    cut.append(t)
                    break
        for t in cut:
            board.Remove(t)
        GRAVE.extend(cut)
        ripped |= codes
        if H.problems(new, H.obstacles(board, gc), quiet=True):
            log(f"gndforce {pad}: still blocked after ripping {sorted(hit)}; skipped")
            continue
        for ly, a, b_, h, dr in new:
            if ly is None:
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(B.mm(*a)); v.SetViaType(pcbnew.VIATYPE_THROUGH); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                v.SetWidth(pcbnew.FromMM(0.3)); v.SetDrill(pcbnew.FromMM(0.15)); v.SetNet(gnd)
                board.Add(v)
                continue
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(B.mm(*a)); t.SetEnd(B.mm(*b_)); t.SetWidth(pcbnew.FromMM(2 * h)); t.SetLayer(ly); t.SetNet(gnd)
            board.Add(t)
        log(f"gndforce {pad}: joined; ripped {sorted(hit)}")
    R.changed()
    pcbnew.SaveBoard(ROUTED, board)
    if ripped:
        os.environ["NETS"] = ",".join(short(board.FindNet(c).GetNetname()) for c in ripped)
        os.environ["GROUPS"] = "1"
        stage_gaps(board, B, R)


def stage_moveto(board, B, R):
    """$REF (a small cap on the back) goes to the free spot nearest a via of its rail ($NET, near $AT 'x,y') where
    its pads clear everything; its rail pad is joined (stage gaps) and its GND pad gets a via (stage gndpads)."""
    ref, net = os.environ["REF"], os.environ["NET"]
    at = tuple(float(v) for v in os.environ["AT"].split(","))
    f = board.FindFootprintByReference(ref)
    codes = {p.GetNetCode() for p in f.Pads()}
    doomed = [t for t in board.GetTracks() if t.GetNetCode() in codes and any(
        (p.HitTest(t.GetPosition()) if t.GetClass() == "PCB_VIA" else (p.HitTest(t.GetStart()) or p.HitTest(t.GetEnd())))
        for p in f.Pads())]
    for t in doomed:
        board.Remove(t)
    GRAVE.extend(doomed)
    f.SetPosition(B.mm(200, 200))
    R.changed()
    best = place_near(B, R, ref, {net: at, "GND": at}, back=f.IsFlipped(), span=3.0, step=0.05, keepout=[])
    log(f"moveto {ref}: at ({best[1]:.2f}, {best[2]:.2f}), {best[3]} deg")
    pcbnew.SaveBoard(ROUTED, board)
    os.environ["NETS"] = net
    os.environ["GROUPS"] = "1"
    stage_gaps(board, B, R)
    stage_gndpads(board, B, R)


STAGES = {"moveto": stage_moveto, "gndforce": stage_gndforce, "gndpads": stage_gndpads, "c207": stage_c207, "intfix": stage_intfix, "placefix_route": stage_placefix_route, "placefix2": stage_placefix2, "placefix": stage_placefix, "escape": stage_escape, "repin": stage_repin, "revert_parts": stage_revert_parts, "restore_open": stage_restore_open, "restore_from": stage_restore_from, "restore_signals": stage_restore_signals, "dejunk": stage_dejunk, "gaps": stage_gaps, "resetfix2": stage_resetfix2, "resetfix": stage_resetfix, "rail_last": stage_rail_last, "xtal_draw": stage_xtal_draw, "restore_rails": stage_restore_rails, "north": stage_north, "one": stage_one, "neck": stage_neck, "clfix": stage_clfix, "reserve": stage_reserve, "rebuild_rk": stage_rebuild_rk, "rebuild": stage_rebuild, "in2bridge": stage_in2bridge, "c219": stage_c219, "cluster": stage_cluster, "gndfix": stage_gndfix, "clean": stage_clean, "harvest": stage_harvest, "corner": stage_corner, "xtal": stage_xtal, "localfix": stage_localfix, "sequence": stage_sequence, "tpmove": stage_tpmove, "replan": stage_replan, "rkplace": stage_rkplace, "tune": stage_tune, "pcie": stage_pcie, "rxpair": stage_rxpair, "shadow": stage_shadow, "pairs_again": stage_pairs_again, "pairfix": stage_pairfix, "repair": stage_repair, "ripup": stage_ripup, "rkrip": stage_rkrip, "holes": stage_holes, "rip_j69": stage_rip_j69, "j69": stage_j69, "pairs": stage_pairs, "power": stage_power, "signals": stage_signals, "rk628": stage_rk628,
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
