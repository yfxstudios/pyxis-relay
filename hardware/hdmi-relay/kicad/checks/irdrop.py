"""DC voltage drop on the power nets of ../relay.kicad_pcb: each net's copper (tracks, vias, pads) as a resistor
network, the regulator output as the source, the expected load currents drawn at the load pads; solved by nodal
analysis. Also reports each track's current density.

  .../bin/python3 checks/irdrop.py

Copper: JLCPCB 4-layer default, 1 oz (35 um) outer, 0.5 oz (17.5 um) inner; via barrel 20 um plating.
"""
import math
import sys
from collections import defaultdict

import numpy as np
import pcbnew

RHO = 1.72e-8                       # copper, ohm m (20 C)
T = {pcbnew.F_Cu: 35e-6, pcbnew.B_Cu: 35e-6, pcbnew.In1_Cu: 17.5e-6, pcbnew.In2_Cu: 17.5e-6}
BOARD_T, PLATE = 1.6e-3, 20e-6
O = (30, 30)

# net: (source pads, {load "REF" or "REF.pad": amps}); a REF alone spreads its current over its pads on the net
CASES = {
    "5V_SOM": (["L102.2"], {"J701": 3.0}),
    "5V_SYS": (["L101.2"], {"U105.3": 1.0, "U106.3": 0.35, "U401": 0.1, "C401.1": 0.0}),
    "3V3_IO": (["L103.2"], {"J501": 0.6, "Q201.2": 0.2, "J602": 0.05}),
    "RK628D_3V3": (["Q201.3"], {"U201": 0.05, "FB201.1": 0.1}),
    "AVDD_3V3_628": (["FB201.2"], {"U201": 0.1}),
    "1V1_628": (["L104.2"], {"U201": 0.45, "FB202.1": 0.15}),
    "AVDD_1V1_628": (["FB202.2"], {"U201": 0.15}),
    "VIN": (["F101.2"], {"U103.5": 1.4, "U104.5": 2.8}),     # 6 V battery: 5 V x 3 A and 5 V x 1.5 A at ~90 %
}


def mm(p):
    return (pcbnew.ToMM(p.x) - O[0], pcbnew.ToMM(p.y) - O[1])


def seg_proj(p, a, c):
    dx, dy = c[0] - a[0], c[1] - a[1]
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return t, math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def solve(b, net, sources, loads):
    ni = b.FindNet(net)
    if ni is None:
        names = [str(k) for k in b.GetNetsByName().keys() if str(k).split("/")[-1] == net]
        ni = b.FindNet(names[0])
    nc = ni.GetNetCode()
    segs = [t for t in b.GetTracks() if t.GetNetCode() == nc and t.GetClass() != "PCB_VIA"]
    vias = [t for t in b.GetTracks() if t.GetNetCode() == nc and t.GetClass() == "PCB_VIA"]
    pads = [(f.GetReference(), p) for f in b.GetFootprints() for p in f.Pads() if p.GetNetCode() == nc]
    nodes, edges = {}, []                     # node key -> index; edges (a, b, R, info)

    def node(k):
        if k not in nodes:
            nodes[k] = len(nodes)
        return nodes[k]

    def pad_layers(p):
        return [L for L in T if p.IsOnLayer(L)]

    # attachment points of everything on each segment (endpoints of others, vias, pads)
    cuts = defaultdict(set)
    sg = [(s, mm(s.GetStart()), mm(s.GetEnd()), pcbnew.ToMM(s.GetWidth()) / 2, s.GetLayer()) for s in segs]
    probes = []
    for s, a, c, hw, L in sg:
        probes += [(a, L, hw), (c, L, hw)]
    for v in vias:
        probes += [(mm(v.GetPosition()), None, pcbnew.ToMM(v.GetWidth(pcbnew.F_Cu)) / 2)]
    for i, (s, a, c, hw, L) in enumerate(sg):
        cuts[i] |= {0.0, 1.0}
        for P, PL, phw in probes:
            if PL is not None and PL != L:
                continue
            t, d = seg_proj(P, a, c)
            if d <= hw + phw + 1e-4 and 0 < t < 1:
                cuts[i].add(round(t, 6))
    # tracks that run across a pad (rather than ending on it) get a node inside the pad
    for ref, p in pads:
        bb = p.GetBoundingBox()
        x0, y0 = pcbnew.ToMM(bb.GetLeft()) - O[0], pcbnew.ToMM(bb.GetTop()) - O[1]
        x1, y1 = pcbnew.ToMM(bb.GetRight()) - O[0], pcbnew.ToMM(bb.GetBottom()) - O[1]
        for i, (s, a, c, hw, L) in enumerate(sg):
            if not p.IsOnLayer(L):
                continue
            n = max(2, int(math.dist(a, c) / 0.02))
            for k in range(1, n):
                x, y = a[0] + (c[0] - a[0]) * k / n, a[1] + (c[1] - a[1]) * k / n
                if x0 <= x <= x1 and y0 <= y <= y1:
                    cuts[i].add(round(k / n, 6))
                    break
    # points -> nodes: same layer, within 1 um share a node
    def pkey(P, L):
        return (round(P[0], 3), round(P[1], 3), L)

    nhw = defaultdict(float)
    for i, (s, a, c, hw, L) in enumerate(sg):
        ts = sorted(cuts[i])
        w = 2 * hw * 1e-3
        for t0, t1 in zip(ts, ts[1:]):
            p0 = (a[0] + (c[0] - a[0]) * t0, a[1] + (c[1] - a[1]) * t0)
            p1 = (a[0] + (c[0] - a[0]) * t1, a[1] + (c[1] - a[1]) * t1)
            ln = math.dist(p0, p1) * 1e-3
            n0, n1 = node(pkey(p0, L)), node(pkey(p1, L))
            nhw[n0] = max(nhw[n0], hw); nhw[n1] = max(nhw[n1], hw)
            edges.append((n0, n1, RHO * ln / (w * T[L]) + 1e-9,
                          ("seg", L, w, p0, p1)))
    # join co-located nodes on a layer that lie within each other's copper (overlapping ends)
    keys = list(nodes)
    for v in vias:
        P, r = mm(v.GetPosition()), pcbnew.ToMM(v.GetWidth(pcbnew.F_Cu)) / 2
        vn = node(("via", round(P[0], 3), round(P[1], 3)))
        rv = RHO * BOARD_T / (math.pi * pcbnew.ToMM(v.GetDrill()) * 1e-3 * PLATE) / 2
        for k in keys:
            if k[0] != "via" and len(k) == 3 and math.dist((k[0], k[1]), P) <= r + nhw[nodes[k]] + 0.005:
                edges.append((vn, nodes[k], rv, ("via",)))
    for ref, p in pads:
        pn = node(("pad", ref, p.GetNumber()))
        bb = p.GetBoundingBox()
        x0, y0 = pcbnew.ToMM(bb.GetLeft()) - O[0] - 0.02, pcbnew.ToMM(bb.GetTop()) - O[1] - 0.02
        x1, y1 = pcbnew.ToMM(bb.GetRight()) - O[0] + 0.02, pcbnew.ToMM(bb.GetBottom()) - O[1] + 0.02
        inside = lambda x, y, m=0: x0 - m <= x <= x1 + m and y0 - m <= y <= y1 + m
        for k in list(nodes):
            if k[0] in ("via", "pad"):
                continue
            if k[2] in pad_layers(p) and inside(k[0], k[1], nhw[nodes[k]]):
                edges.append((pn, nodes[k], 1e-5, ("pad",)))
        for k in list(nodes):
            if k[0] == "via" and inside(k[1], k[2]):
                edges.append((pn, nodes[k], 1e-5, ("pad",)))
    # segment ends overlapping other segments' ends within copper (not caught as T): link nodes on one layer
    pts = defaultdict(list)
    for k, i in nodes.items():
        if len(k) == 3 and k[0] not in ("via", "pad"):
            pts[k[2]].append((k, i))
    for L, lst in pts.items():
        for x in range(len(lst)):
            for y in range(x + 1, len(lst)):
                (ka, ia), (kb, ib) = lst[x], lst[y]
                if math.dist(ka[:2], kb[:2]) <= nhw[ia] + nhw[ib] - 0.01:
                    edges.append((ia, ib, 1e-5, ("join",)))
    n = len(nodes)
    G = np.zeros((n, n))
    for a, c, R, _ in edges:
        g = 1 / R
        G[a, a] += g; G[c, c] += g; G[a, c] -= g; G[c, a] -= g
    I = np.zeros(n)
    load_nodes = {}
    for spec, amps in loads.items():
        if "." in spec:
            ref, num = spec.split(".")
            sel = [("pad", ref, num)]
        else:
            sel = [("pad", r, p.GetNumber()) for r, p in pads if r == spec]
        sel = [k for k in sel if k in nodes]
        for k in sel:
            I[nodes[k]] -= amps / len(sel)
            load_nodes.setdefault(spec, []).append(nodes[k])
    src = [nodes[("pad",) + tuple(s.split("."))] for s in sources if ("pad",) + tuple(s.split(".")) in nodes]
    if not src:
        return None
    # only the copper joined to the source takes part; loads elsewhere are reported as not reached
    adj = defaultdict(list)
    for a, c, R, _ in edges:
        adj[a].append(c); adj[c].append(a)
    seen, stack = set(src), list(src)
    while stack:
        x = stack.pop()
        for y in adj[x]:
            if y not in seen:
                seen.add(y); stack.append(y)
    keep = [i for i in range(n) if i in seen and i not in src]
    Gr, Ir = G[np.ix_(keep, keep)], I[keep]
    V = np.full(n, np.nan)
    V[src] = 0
    V[keep] = np.linalg.solve(Gr, Ir)
    out = {}
    for spec, ids in load_nodes.items():
        got = [V[i] for i in ids if not np.isnan(V[i])]
        out[spec] = (min(got) if got else float("nan"), loads[spec], len(ids) - len(got))
    # the most loaded tracks (current density), merged per original track
    hot = {}
    for a, c, R, info in edges:
        if info[0] == "seg" and not (np.isnan(V[a]) or np.isnan(V[c])):
            i_ = abs(V[a] - V[c]) / R
            area = info[2] * T[info[1]]
            j = i_ / area / 1e6               # A/mm^2
            k = (info[1], round(info[2] * 1e3, 3))
            key = (b.GetLayerName(info[1]), round(info[2] * 1e3, 3), round(info[3][0], 1), round(info[3][1], 1))
            ln = math.dist(info[3], info[4])
            if key not in hot or hot[key][0] < j:
                hot[key] = (j, i_, ln)
    top = sorted(hot.items(), key=lambda kv: -kv[1][0])[:5]
    return out, top


def main():
    b = pcbnew.LoadBoard(sys.argv[1] if len(sys.argv) > 1 else "relay.kicad_pcb")
    for net, (src, loads) in CASES.items():
        r = solve(b, net, src, loads)
        if r is None:
            print(f"{net}: source not found")
            continue
        out, top = r
        drops = ", ".join(f"{k} {-v * 1e3:.1f} mV @ {a:g} A" + (f" ({miss} pads NOT REACHED)" if miss else "")
                          for k, (v, a, miss) in out.items() if a)
        print(f"{net}: {drops}")
        for (lay, w, x, y), (j, i_, ln) in top:
            # IPC-2221 external/internal: I = k * dT^0.44 * A^0.725 (A in mil^2) -> dT for this current
            area_mil2 = (w / 0.0254) * (35 if lay in ("F.Cu", "B.Cu") else 17.5) / 25.4
            kk = 0.048 if lay in ("F.Cu", "B.Cu") else 0.024
            dT = (i_ / (kk * area_mil2 ** 0.725)) ** (1 / 0.44)
            print(f"    {j:6.1f} A/mm^2  {i_:.2f} A in {w} mm {lay} at ({x},{y}), segment {ln:.2f} mm, IPC-2221 rise if long: {dT:.0f} C")


if __name__ == "__main__":
    main()
