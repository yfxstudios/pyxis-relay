"""Compares the CM3 board-to-board connector footprints (J701 = J69, J702 = J68, J703 = J1) against Radxa's own CM3
IO board (datasheets/radxa_cm3_io_board_b2b_connector_20230718.asc, PADS ASCII): every pin's position by Radxa pin
number, fitted with one rigid transform (rotation + offset) over all three connectors, then again allowing a mirror.
A clean fit means the footprints, the pin numbering and the spacing between the connectors all match the module.

  .../bin/python3 checks/b2bfit.py
"""
import math, re, sys
import numpy as np
import pcbnew

ASC = "../datasheets/radxa_cm3_io_board_b2b_connector_20230718.asc"
BU = 1.5e6                                   # PADS basic units per mm (38100 per mil)
lines = open(ASC, errors="replace").read().splitlines()
decals, parts = {}, {}
i = lines.index(next(l for l in lines if l.startswith("*PARTDECAL*")))
while i < len(lines) and not lines[i].startswith("*PARTTYPE*"):
    m = re.match(r"^(DF40\S+)\s+M\s", lines[i])
    if m:
        name, terms = m.group(1), []
        i += 1
        while i < len(lines) and not re.match(r"^(DF40\S+)\s+M\s|^\*", lines[i]):
            t = re.match(r"^T(-?\d+)\s+(-?\d+)", lines[i])
            if t:
                terms.append((int(t.group(1)) / BU, int(t.group(2)) / BU))
            i += 1
        decals[name] = terms
        continue
    i += 1
for l in lines:
    m = re.match(r"^(U33|J24)\s+(DF40\S+)\s+(-?\d+)\s+(-?\d+)\s+([\d.]+)\s+\S+\s+(\S)", l)
    if m:
        parts[m.group(1)] = (m.group(2), int(m.group(3)) / BU, int(m.group(4)) / BU, float(m.group(5)), m.group(6))
io = {}
for ref, (dec, x, y, ori, mir) in parts.items():
    a = math.radians(ori)
    for k, (tx, ty) in enumerate(decals[dec], 1):
        if mir == "Y":
            tx = -tx
        px, py = x + tx * math.cos(a) - ty * math.sin(a), y + tx * math.sin(a) + ty * math.cos(a)
        con, pin = ("J1", k) if ref == "J24" else (("J69", k) if k <= 100 else ("J68", k))
        if k <= (100 if ref == "J24" else 200):
            io[(con, pin)] = (px, -py)                  # PADS is y-up; KiCad y-down
b = pcbnew.LoadBoard("relay.kicad_pcb")
ours = {}
for ref, con, off in (("J701", "J69", 0), ("J702", "J68", 100), ("J703", "J1", 0)):
    for p in b.FindFootprintByReference(ref).Pads():
        if p.GetNumber().isdigit():
            ours[(con, int(p.GetNumber()) + off)] = (pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y))
keys = sorted(set(io) & set(ours))
P = np.array([io[k] for k in keys]); Q = np.array([ours[k] for k in keys])
print(f"pins compared: {len(keys)} (IO board {len(io)}, ours {len(ours)})")
for mirror in (False, True):
    A = P * np.array([-1, 1]) if mirror else P
    ca, cb = A.mean(0), Q.mean(0)
    U, S, Vt = np.linalg.svd((A - ca).T @ (Q - cb))
    R = (U @ Vt).T
    if np.linalg.det(R) < 0:
        Vt[-1] *= -1; R = (U @ Vt).T
    res = np.linalg.norm((A - ca) @ R.T + cb - Q, axis=1)
    ang = math.degrees(math.atan2(R[1, 0], R[0, 0]))
    print(f"{'mirrored' if mirror else 'as is   '}: rotation {ang:7.2f} deg, rms {res.mean():.4f} mm, max {res.max():.4f} mm "
          f"at {keys[int(res.argmax())]}")
    if not mirror:
        for con in ("J69", "J68", "J1"):
            r = [res[j] for j, k in enumerate(keys) if k[0] == con]
            print(f"   {con}: max {max(r):.4f} mm")

# second check: the IO board's ground and supply pins against ours
sig, cur = {}, None
for l in lines:
    m = re.match(r"^\*SIGNAL\*\s+(\S+)", l)
    if m:
        cur = m.group(1); continue
    if l.startswith("*") and not l.startswith("*SIGNAL*"):
        cur = None if l.startswith(("*MISC*", "*END*")) else cur
    if cur:
        for ref, pin in re.findall(r"\b(U33|J24)\.(\d+)", l):
            k = int(pin)
            key = ("J1", k) if ref == "J24" else (("J69", k) if k <= 100 else ("J68", k))
            sig.setdefault(cur, set()).add(key)
ournet = {}
for ref, con, off in (("J701", "J69", 0), ("J702", "J68", 100), ("J703", "J1", 0)):
    for p in b.FindFootprintByReference(ref).Pads():
        if p.GetNumber().isdigit():
            ournet[(con, int(p.GetNumber()) + off)] = p.GetNetname().split("/")[-1]
print("IO-board supply/ground nets vs ours:")
for s in sorted(sig):
    if re.search(r"GND|V\d|5V|3V3|1V8|VREF|BAT", s):
        mine = sorted({ournet.get(k, "?") for k in sig[s]})
        print(f"   {s:14s} {len(sig[s]):3d} pins -> ours: {mine}")
odd = sorted(k for k in sig.get("GND", ()) if ournet.get(k) != "GND")
print("IO-board GND pins that are not GND here:", odd)
