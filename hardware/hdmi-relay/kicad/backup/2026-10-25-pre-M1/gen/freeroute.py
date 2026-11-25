"""Finishes chosen nets on the routed board with Freerouting, then runs gen/finish.py's steps.

  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 gen/freeroute.py

Needs Java 21+ and the Freerouting jar (FREEROUTING below; Freerouting 2.5.0 from its GitHub releases).

Freerouting can't be told to route only some nets, so the export hides the others: every existing track and via is
locked (exported as protected, so Freerouting leaves them alone), every net not in TARGET is split into single-pin
nets (still obstacles, nothing to route), and the inner planes are exported as power layers. Only Freerouting's new
copper on the TARGET nets is added to the board, on the outer layers.
"""
import os
import shutil
import subprocess
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from finish import ROUTED, OUT, finish  # noqa: E402

JAVA = "/opt/homebrew/opt/openjdk/bin/java"
FREEROUTING = os.path.expanduser("~/tools/freerouting/freerouting-2.5.0.jar")
WORK = os.path.join(ROOT, "freerouting")
# the RK628D connections gen/route.py's own router leaves open
TARGET = {"XOUT_628", "RX_SDA", "RX_CEC", "EFUSE_628", "I2S_628_MCLK", "I2C_628_SCL", "I2C_628_SDA", "CEC_GPIO",
          "RK628D_PWR_EN", "1V1_628", "AVDD_3V3_628", "AVDD_1V1_628"}


def short(name):
    return name.split("/")[-1]


def key(t):
    s, e = t.GetStart(), t.GetEnd()
    return (t.GetClass(), t.GetLayer(), t.GetNetCode(), s.x, s.y, e.x, e.y)


def load():
    # the board takes its net classes and rules from the project file beside it
    shutil.copy(os.path.join(ROOT, "relay.kicad_pro"), ROUTED.replace(".kicad_pcb", ".kicad_pro"))
    return pcbnew.LoadBoard(ROUTED)


os.makedirs(WORK, exist_ok=True)
dsn, ses = os.path.join(WORK, "relay.dsn"), os.path.join(WORK, "relay.ses")

board = load()
before = {key(t) for t in board.GetTracks()}
for t in board.GetTracks():
    t.SetLocked(True)
for layer in (pcbnew.In1_Cu, pcbnew.In2_Cu):
    board.SetLayerType(layer, pcbnew.LT_POWER)
if not pcbnew.ExportSpecctraDSN(board, dsn):
    raise SystemExit("DSN export failed")

# Only the target nets are left for Freerouting to route: every other net is split into single-pin nets in the
# export, so its pads and tracks stay obstacles with a net and a clearance, but it has nothing to connect. (Routing
# all 250 open connections took Freerouting over 20 minutes; moving the other nets to "no net" instead made
# Freerouting ignore them as obstacles.)
import re  # noqa: E402
text = open(dsn).read()


def split(m):
    name, pins = m.group(1), m.group(2).split()
    if short(name.strip('"')) in TARGET or len(pins) < 2:
        return m.group(0)
    base = name.strip('"')
    out = f'(net {name}\n      (pins {pins[0]})\n    )'
    for k, pin in enumerate(pins[1:], 2):
        out += f'\n    (net "{base}__{k}"\n      (pins {pin})\n    )'
    return out


text = re.sub(r'\(net ("[^"]*"|\S+)\n\s+\(pins ([^)]*)\)\n\s+\)', split, text)
open(dsn, "w").write(text)

if os.path.exists(ses):
    os.remove(ses)
log = os.path.join(WORK, "freerouting.log")   # follow progress with: tail -f freerouting/freerouting.log
with open(log, "w") as f:
    subprocess.run([JAVA, "-jar", FREEROUTING, "-de", dsn, "-do", ses, "-mp", "8", "--gui.enabled=false"],
                   stdout=f, stderr=subprocess.STDOUT, timeout=1200)
if not os.path.exists(ses):
    raise SystemExit(f"Freerouting wrote no session; see {log}")

# Bring back only Freerouting's new copper on the target nets. (KiCad's own session import replaces every track on
# the board, and with the other nets hidden in the export their routing would come back without nets.)
from sexpr import find, find_all, parse  # noqa: E402
board = load()
existing = [t for t in board.GetTracks()]
LAYERS = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu, "In1.Cu": pcbnew.In1_Cu, "In2.Cu": pcbnew.In2_Cu}


def pos(x, y):   # session units are 0.1 um, y up; the board's are nm, y down
    return pcbnew.VECTOR2I(int(x) * 100, -int(y) * 100)


def have_track(layer, nc, a, b):
    for t in existing:
        if t.GetClass() == "PCB_TRACK" and t.GetLayer() == layer and t.GetNetCode() == nc:
            s_, e_ = t.GetStart(), t.GetEnd()
            if ((abs(s_.x - a.x) + abs(s_.y - a.y) < 2000 and abs(e_.x - b.x) + abs(e_.y - b.y) < 2000) or
                    (abs(s_.x - b.x) + abs(s_.y - b.y) < 2000 and abs(e_.x - a.x) + abs(e_.y - a.y) < 2000)):
                return True
    return False


def have_via(nc, at):
    return any(t.GetClass() == "PCB_VIA" and t.GetNetCode() == nc and
               abs(t.GetPosition().x - at.x) + abs(t.GetPosition().y - at.y) < 2000 for t in existing)


tree = parse(open(ses).read())
added = skipped_inner = 0
for n in find_all(find(find(tree, "routes"), "network_out"), "net"):
    name = n[1]
    if short(name) not in TARGET:
        continue
    ni = board.FindNet(name)
    nc = ni.GetNetCode()
    for w in find_all(n, "wire"):
        path = find(w, "path")
        layer, width, xy = LAYERS[path[1]], int(path[2]) * 100, path[3:]
        pts = [pos(xy[k], xy[k + 1]) for k in range(0, len(xy) - 1, 2)]
        for a, b in zip(pts, pts[1:]):
            if have_track(layer, nc, a, b):
                continue
            if layer in (pcbnew.In1_Cu, pcbnew.In2_Cu):   # the inner layers stay planes
                skipped_inner += 1
                continue
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(a); t.SetEnd(b); t.SetWidth(width); t.SetLayer(layer); t.SetNet(ni)
            board.Add(t)
            added += 1
    for v in find_all(n, "via"):
        at = pos(v[2], v[3])
        if have_via(nc, at):
            continue
        d, drill = (int(x) for x in v[1].split("_")[1].split(":"))   # "Via[0-3]_450:250_um"
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(at); via.SetViaType(pcbnew.VIATYPE_THROUGH); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetWidth(d * 1000); via.SetDrill(drill * 1000); via.SetNet(ni)
        board.Add(via)
        added += 1
print(f"Freerouting: added {added} new tracks and vias on the target nets ({skipped_inner} inner-layer segments "
      f"left out)")
pcbnew.SaveBoard(ROUTED, board)
finish(board)
pcbnew.SaveBoard(OUT, board)
