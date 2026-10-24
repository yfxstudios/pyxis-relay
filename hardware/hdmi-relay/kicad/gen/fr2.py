"""Freerouting on the whole board, for the connections gen/autoroute.py could not close (Oct 23).

  .../bin/python3 gen/fr2.py export     # writes freerouting/fr2.dsn
  java -jar freerouting.jar -de freerouting/fr2.dsn -do freerouting/fr2.ses -mp 30 --gui.enabled=false
  .../bin/python3 gen/fr2.py import     # merges freerouting/fr2.ses into routed.kicad_pcb

Unlike gen/freeroute.py, the low-speed traces are left free, so Freerouting's push-and-shove can move them aside.
Locked (exported as protected): GND, the power rails, the high-speed pairs and the RK628D's ball dogbones. GND is
split into single-pin nets (the pours connect it, not traces). A net Freerouting puts on L2 (the GND plane) is
not taken. On import, every net whose routing Freerouting changed is replaced by its
session copy, wholesale.
"""
import os
import re
import shutil
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import autoroute as A  # noqa: E402
from sexpr import find, find_all, parse  # noqa: E402

WORK = os.path.join(ROOT, "freerouting")
DSN, SES = os.path.join(WORK, "fr2.dsn"), os.path.join(WORK, "fr2.ses")
LAYERS = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu, "In1.Cu": pcbnew.In1_Cu, "In2.Cu": pcbnew.In2_Cu}


def load():
    shutil.copy(os.path.join(ROOT, "relay.kicad_pro"), A.ROUTED.replace(".kicad_pcb", ".kicad_pro"))
    return pcbnew.LoadBoard(A.ROUTED)


def export():
    os.makedirs(WORK, exist_ok=True)
    b = load()
    soft = A.soft_nets(b, u201_too=True)
    pins = A._dogbones(b)
    locked = 0
    for t in b.GetTracks():
        if t.GetNetCode() not in soft or t.m_Uuid.AsString() in pins:
            t.SetLocked(True)
            locked += 1
    # (the inner layers stay signal layers here: L3 carries some low-speed segments, which must count as routed)
    if not pcbnew.ExportSpecctraDSN(b, DSN):
        raise SystemExit("DSN export failed")
    text = open(DSN).read()

    def split(m):                    # GND: single-pin nets (obstacles with a clearance, nothing to connect)
        name, pp = m.group(1), m.group(2).split()
        if name.strip('"') != "GND":
            return m.group(0)
        out = f'(net {name}\n      (pins {pp[0]})\n    )'
        for k, pin in enumerate(pp[1:], 2):
            out += f'\n    (net "GND__{k}"\n      (pins {pin})\n    )'
        return out
    text = re.sub(r'\(net ("[^"]*"|\S+)\n\s+\(pins ([^)]*)\)\n\s+\)', split, text)
    open(DSN, "w").write(text)
    print(f"wrote {DSN}: {locked} of {len(b.GetTracks())} tracks and vias locked")


def pos(x, y):   # session units 0.1 um, y up; board nm, y down
    return pcbnew.VECTOR2I(int(float(x) * 100), -int(float(y) * 100))


def do_import():
    b = load()
    tree = parse(open(SES).read())
    lib = find(find(tree, "routes"), "library_out")
    vsize = {}
    for ps in find_all(lib, "padstack") if lib else []:
        m = re.search(r"(\d+):(\d+)_um", ps[1])
        if m:
            vsize[ps[1]] = (int(m.group(1)) * 1000, int(m.group(2)) * 1000)
    changed = 0
    keep_alive = []
    for n in find_all(find(find(tree, "routes"), "network_out"), "net"):
        name = n[1].strip('"') if isinstance(n[1], str) else n[1]
        if name.startswith("GND"):
            continue
        ni = b.FindNet(name)
        if not ni:
            continue
        nc = ni.GetNetCode()
        wires, vias = [], []
        for w in find_all(n, "wire"):
            path = find(w, "path")
            layer, width, xy = LAYERS[path[1]], int(float(path[2]) * 100), path[3:]
            p = [pos(xy[k], xy[k + 1]) for k in range(0, len(xy) - 1, 2)]
            wires += [(layer, width, (a.x, a.y), (c.x, c.y)) for a, c in zip(p, p[1:]) if (a.x, a.y) != (c.x, c.y)]
        for v in find_all(n, "via"):
            at = pos(v[2], v[3])
            vias.append((v[1], (at.x, at.y)))
        old_w = {(t.GetLayer(), (t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y))
                 for t in b.GetTracks() if t.GetNetCode() == nc and t.GetClass() != "PCB_VIA"}
        new_w = {(l, s, e) for l, _, s, e in wires}
        new_w2 = {(l, e, s) for l, s, e in new_w}

        def close(a, c):
            return abs(a[0] - c[0]) + abs(a[1] - c[1]) < 2000
        if any(l == pcbnew.In1_Cu for l, _, _, _ in wires) and not any(
                t.GetLayer() == pcbnew.In1_Cu for t in b.GetTracks() if t.GetNetCode() == nc and t.GetClass() != "PCB_VIA"):
            print(f"  {A.short(name)}: new copper on L2 (the GND plane), not taken")
            continue
        same = len(old_w) == len(new_w) and all(
            any(o[0] == w[0] and close(o[1], w[1]) and close(o[2], w[2]) for w in new_w | new_w2) for o in old_w)
        if same:
            continue
        doomed = [t for t in b.GetTracks() if t.GetNetCode() == nc]
        for t in doomed:
            b.Remove(t)
        keep_alive.extend(doomed)
        for layer, width, s, e in wires:
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(pcbnew.VECTOR2I(*s)); t.SetEnd(pcbnew.VECTOR2I(*e)); t.SetWidth(width); t.SetLayer(layer)
            t.SetNet(ni)
            b.Add(t)
        for ps, at in vias:
            d, dr = vsize.get(ps, (450000, 250000))
            v = pcbnew.PCB_VIA(b)
            v.SetPosition(pcbnew.VECTOR2I(*at)); v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetWidth(d); v.SetDrill(dr); v.SetNet(ni)
            b.Add(v)
        changed += 1
        print(f"  {A.short(name)}: {len(doomed)} items out, {len(wires)} wires + {len(vias)} vias in")
    pcbnew.SaveBoard(A.ROUTED, b)
    shutil.copy(os.path.join(ROOT, "relay.kicad_pro"), A.ROUTED.replace(".kicad_pcb", ".kicad_pro"))
    print(f"imported: {changed} nets changed")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    export() if sys.argv[1] == "export" else do_import()
