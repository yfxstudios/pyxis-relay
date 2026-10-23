"""A small grid maze router for the scripted layout (no autorouter is installed on this machine).

It rasterises the board's copper at 0.05 mm, blocks every cell closer than clearance + half the trace width to
copper of another net, and finds paths with A* in eight directions (so every segment is 0, 45 or 90 degrees), with
a cost for bends and for vias. Zones are ignored: they are refilled around the result. Trace centres sit on cell
centres; the blocked distance includes half a cell diagonal, so the copper between two cell centres keeps the
clearance too.

Used from gen/route.py for the low-speed and power connections; the high-speed pairs there are drawn by hand.
"""
import heapq
import math

import numpy as np
import pcbnew

CU = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
HOLE_CL = 0.2
HOLE_HOLE = 0.26     # drill edge to drill edge (JLCPCB 0.25 mm)


class Router:
    def __init__(self, board, origin, board_size, box, res=0.05, clearance=0.13, edge=0.3):
        self.board = board
        self.board_size = board_size
        self.O = origin
        self.x0, self.y0, self.x1, self.y1 = box
        self.res = res
        self.cl = clearance
        self.edge = edge
        self.nx = int(round((self.x1 - self.x0) / res)) + 1
        self.ny = int(round((self.y1 - self.y0) / res)) + 1
        self.cache = {}
        self.shapes = None
        self.peers = []
        self.log = []          # every item commit() adds, so a caller can take a trial route back out
        self.allow = {}        # layer -> (x0, y0, x1, y1): that layer may only be used inside the rectangle
        self.extra = []        # (x, y, r): temporary keep-out discs on every layer (call changed() after editing)
        self.pinned = set()    # uuids of tracks and vias a rip-up never moves (they stay hard when their net is soft)
        self.net_cl = {}       # netcode -> clearance its copper needs from others, where more than `clearance`
        self.shadow = {}       # layer -> (other layer, netcodes, margin): those nets' tracks on the other layer
        #                        also block this one (a plane layer kept whole under high-speed traces)

    # ------------------------------------------------------------------ geometry
    def _mm(self, v):
        return pcbnew.ToMM(v.x) - self.O[0], pcbnew.ToMM(v.y) - self.O[1]

    def _collect(self):
        """Every copper shape: (layers, netcode, kind, params). kind: 'c' circle (x, y, r), 'r' rect
        (cx, cy, hw, hh), 's' segment (x0, y0, x1, y1, half width)."""
        shapes = []
        self.track_idx = set()     # shapes that are tracks or vias (not pads): the ones a rip-up may move
        for fp in self.board.GetFootprints():
            for p in fp.Pads():
                layers = [l for l in CU if p.IsOnLayer(l)]
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    layers = CU
                cx, cy = self._mm(p.GetPosition())
                try:
                    circ = p.GetShape(pcbnew.F_Cu) == pcbnew.PAD_SHAPE_CIRCLE
                except TypeError:
                    circ = p.GetShape() == pcbnew.PAD_SHAPE_CIRCLE
                bb = p.GetBoundingBox()
                hw, hh = pcbnew.ToMM(bb.GetWidth()) / 2, pcbnew.ToMM(bb.GetHeight()) / 2
                if p.HasHole():
                    d = pcbnew.ToMM(p.GetDrillSize().x) / 2
                    shapes.append((CU, p.GetNetCode() if layers else 0, "h", (cx, cy, d)))
                if not layers:
                    continue
                if circ:
                    shapes.append((layers, p.GetNetCode(), "c", (cx, cy, hw)))
                else:
                    shapes.append((layers, p.GetNetCode(), "r", (cx, cy, hw, hh)))
        for t in self.board.GetTracks():
            if not self.pinned or t.m_Uuid.AsString() not in self.pinned:
                self.track_idx.update((len(shapes), len(shapes) + 1))
            if t.GetClass() == "PCB_VIA":
                x, y = self._mm(t.GetPosition())
                shapes.append((CU, t.GetNetCode(), "c", (x, y, pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2)))
                shapes.append((CU, t.GetNetCode(), "h", (x, y, pcbnew.ToMM(t.GetDrillValue()) / 2)))
            else:
                x0, y0 = self._mm(t.GetStart())
                x1, y1 = self._mm(t.GetEnd())
                shapes.append(([t.GetLayer()], t.GetNetCode(), "s", (x0, y0, x1, y1, pcbnew.ToMM(t.GetWidth()) / 2)))
        self.shapes = shapes

    def _dist(self, kind, prm, X, Y):
        if kind in "ch":
            return np.hypot(X - prm[0], Y - prm[1]) - prm[2]
        if kind == "r":
            return np.hypot(np.maximum(np.abs(X - prm[0]) - prm[2], 0), np.maximum(np.abs(Y - prm[1]) - prm[3], 0))
        x0, y0, x1, y1, h = prm
        dx, dy = x1 - x0, y1 - y0
        L = dx * dx + dy * dy
        t = np.zeros_like(X) if L == 0 else np.clip(((X - x0) * dx + (Y - y0) * dy) / L, 0, 1)
        return np.hypot(X - x0 - t * dx, Y - y0 - t * dy) - h

    def _extent(self, kind, prm):
        if kind in "ch":
            return prm[0] - prm[2], prm[1] - prm[2], prm[0] + prm[2], prm[1] + prm[2]
        if kind == "r":
            return prm[0] - prm[2], prm[1] - prm[3], prm[0] + prm[2], prm[1] + prm[3]
        return min(prm[0], prm[2]) - prm[4], min(prm[1], prm[3]) - prm[4], max(prm[0], prm[2]) + prm[4], \
            max(prm[1], prm[3]) + prm[4]

    def _paint(self, grid, kind, prm, margin, value=True):
        ex = self._extent(kind, prm)
        i0 = max(0, int(math.floor((ex[0] - margin - self.x0) / self.res)))
        i1 = min(self.nx, int(math.ceil((ex[2] + margin - self.x0) / self.res)) + 1)
        j0 = max(0, int(math.floor((ex[1] - margin - self.y0) / self.res)))
        j1 = min(self.ny, int(math.ceil((ex[3] + margin - self.y0) / self.res)) + 1)
        if i0 >= i1 or j0 >= j1:
            return
        X, Y = np.meshgrid(self.x0 + np.arange(i0, i1) * self.res, self.y0 + np.arange(j0, j1) * self.res)
        grid[j0:j1, i0:i1] |= self._dist(kind, prm, X, Y) < margin

    def blocked(self, netcode, half, layers, cl=None, soft=frozenset()):
        """Bool array [layer, y, x]: cells a centreline of half-width `half` on `netcode` may not use. `netcode`
        may be a tuple: a differential pair routed as one wide centreline may cross both its nets' copper.
        Tracks and vias of the nets in `soft` are left out (a rip-up may take them away)."""
        cl = self.cl if cl is None else cl
        own = netcode if isinstance(netcode, tuple) else (netcode,)
        key = (netcode, round(half, 4), tuple(layers), cl, soft)
        if key in self.cache:
            return self.cache[key]
        if self.shapes is None:
            self._collect()
        margin = cl + half + self.res * 0.71
        g = np.zeros((len(layers), self.ny, self.nx), bool)
        for li, layer in enumerate(layers):
            for k, (lys, nc, kind, prm) in enumerate(self.shapes):
                if soft and nc in soft and k in self.track_idx:
                    continue
                if layer in lys and (nc not in own or nc == 0):
                    # drilled holes keep HOLE_CL to other nets' copper (JLCPCB: 0.2 mm via hole to track)
                    m = margin if nc not in self.net_cl else max(cl, self.net_cl[nc]) + half + self.res * 0.71
                    self._paint(g[li], kind, prm, m if kind != "h" else HOLE_CL + half + self.res * 0.71)
            if layer in self.shadow:
                src, codes, extra = self.shadow[layer]
                for k, (lys, nc, kind, prm) in enumerate(self.shapes):
                    if kind == "s" and src in lys and nc in codes and nc not in own:
                        self._paint(g[li], kind, prm, margin + extra)
            for (ex, ey, er) in self.extra:
                self._paint(g[li], "c", (ex, ey, er), margin)
            if layer in self.allow:
                ax0, ay0, ax1, ay1 = self.allow[layer]
                keep = np.zeros_like(g[li])
                keep[max(0, int((ay0 - self.y0) / self.res)):int((ay1 - self.y0) / self.res) + 1,
                     max(0, int((ax0 - self.x0) / self.res)):int((ax1 - self.x0) / self.res) + 1] = True
                g[li] |= ~keep
            e = int(math.ceil((self.edge + half) / self.res))
            bx0 = int(round((0 - self.x0) / self.res)); by0 = int(round((0 - self.y0) / self.res))
            g[li, :, :max(0, bx0 + e)] = True
            g[li, :max(0, by0 + e), :] = True
            W, H = self.board_size
            bx1 = int(round((W - self.x0) / self.res)); by1 = int(round((H - self.y0) / self.res))
            g[li, :, max(0, bx1 - e + 1):] = True
            g[li, max(0, by1 - e + 1):, :] = True
        self.cache[key] = g
        return g

    def changed(self):
        """The board changed: forget the rasters, here and in routers sharing the board."""
        for r in [self] + self.peers:
            r.cache = {}
            r.shapes = None

    # ------------------------------------------------------------------ terminals
    def cells(self, item, layers, shrink=0.0):
        """Cells inside a pad, via or track of the net, as a set of (layer index, j, i)."""
        out = set()
        if isinstance(item, tuple):          # a bare point (x, y) on every layer given
            i = int(round((item[0] - self.x0) / self.res)); j = int(round((item[1] - self.y0) / self.res))
            return {(li, j, i) for li in range(len(layers))}
        if item.GetClass() == "PCB_VIA":
            x, y = self._mm(item.GetPosition())
            kind, prm, lys = "c", (x, y, pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)) / 2), CU
        elif item.GetClass() == "PCB_TRACK":
            x0, y0 = self._mm(item.GetStart()); x1, y1 = self._mm(item.GetEnd())
            kind, prm, lys = "s", (x0, y0, x1, y1, pcbnew.ToMM(item.GetWidth()) / 2), [item.GetLayer()]
        else:
            cx, cy = self._mm(item.GetPosition())
            bb = item.GetBoundingBox()
            hw, hh = pcbnew.ToMM(bb.GetWidth()) / 2, pcbnew.ToMM(bb.GetHeight()) / 2
            try:
                circ = item.GetShape(pcbnew.F_Cu) == pcbnew.PAD_SHAPE_CIRCLE
            except TypeError:
                circ = item.GetShape() == pcbnew.PAD_SHAPE_CIRCLE
            k = min(0.1, 0.4 * min(hw, hh))   # stay off rounded corners: end inside the copper
            kind, prm = ("c", (cx, cy, hw - k)) if circ else ("r", (cx, cy, hw - k, hh - k))
            lys = [l for l in CU if item.IsOnLayer(l)]
        tmp = np.zeros((self.ny, self.nx), bool)
        self._paint(tmp, kind, prm, -shrink if shrink else 1e-6)
        js, is_ = np.nonzero(tmp)
        for li, layer in enumerate(layers):
            if layer in lys:
                out |= {(li, int(j), int(i)) for j, i in zip(js, is_)}
        return out

    # ------------------------------------------------------------------ search
    def search(self, netcode, half, layers, sources, targets, via=(0.45, 0.25), via_cost=40, bend=3,
               window=4.0, max_expand=600000, cl=None, greed=1.0, soft=frozenset(), soft_cost=60,
               soft_hi=frozenset(), soft_hi_cost=400):
        """soft: nets whose tracks this path may cross at soft_cost per cell (the caller rips them up); soft_hi:
        the same at soft_hi_cost (nets ripped often already)."""
        allsoft = frozenset(soft) | frozenset(soft_hi)
        blk = self.blocked(netcode, half, layers, cl, allsoft)
        pen = (self.blocked(netcode, half, layers, cl) & ~blk) if allsoft else None
        pen_hi = (self.blocked(netcode, half, layers, cl, frozenset(soft)) & ~blk) if soft_hi else None
        # a through via touches every copper layer, not only the ones this route may use
        vr = max(via[0] / 2, via[1] / 2 + HOLE_CL - (self.cl if cl is None else cl))
        vblk = self.blocked(netcode, vr, CU, cl, allsoft).any(axis=0) if len(layers) > 1 else None
        if vblk is not None:          # nor next to this net's own holes (drill to drill spacing)
            own = netcode if isinstance(netcode, tuple) else (netcode,)
            vblk = vblk.copy()
            for lys, nc, kind, prm in self.shapes:
                if kind == "h" and nc in own and nc != 0:
                    self._paint(vblk, "c", prm, HOLE_HOLE + via[1] / 2 + self.res * 0.71)
        vpen = (self.blocked(netcode, vr, CU, cl).any(axis=0) & ~vblk) if allsoft and vblk is not None else None
        allc = list(sources) + list(targets)
        js = [c[1] for c in allc]; is_ = [c[2] for c in allc]
        w = int(window / self.res)
        jlo, jhi = max(0, min(js) - w), min(self.ny - 1, max(js) + w)
        ilo, ihi = max(0, min(is_) - w), min(self.nx - 1, max(is_) + w)
        tgt = set(targets)
        tj0, tj1 = min(c[1] for c in targets), max(c[1] for c in targets)
        ti0, ti1 = min(c[2] for c in targets), max(c[2] for c in targets)

        def h(j, i):   # octile distance to the target's box; greed > 1 trades path length for search time
            dj = max(tj0 - j, 0, j - tj1); di = max(ti0 - i, 0, i - ti1)
            return greed * (max(dj, di) + 0.414 * min(dj, di))

        dirs = [(0, 1, 1.0), (1, 1, 1.414), (1, 0, 1.0), (1, -1, 1.414), (0, -1, 1.0), (-1, -1, 1.414),
                (-1, 0, 1.0), (-1, 1, 1.414)]
        g = {}
        prev = {}
        heap = []
        for s in sources:
            st = (s[0], s[1], s[2], -1)
            g[st] = 0.0
            heapq.heappush(heap, (h(s[1], s[2]), 0.0, st))
        n = 0
        while heap:
            f, gc, st = heapq.heappop(heap)
            if gc > g.get(st, 1e18):
                continue
            l, j, i, d = st
            if (l, j, i) in tgt:
                path = [st]
                while path[-1] in prev:
                    path.append(prev[path[-1]])
                return [(p[0], p[1], p[2]) for p in reversed(path)]
            n += 1
            if n > max_expand:
                return None
            for k, (dj, di, c) in enumerate(dirs):
                jj, ii = j + dj, i + di
                if not (jlo <= jj <= jhi and ilo <= ii <= ihi) or blk[l, jj, ii]:
                    continue
                if dj and di and (blk[l, j, ii] and blk[l, jj, i]):
                    continue
                turn = 0 if d < 0 else (k - d) % 8
                if turn in (3, 4, 5):         # no turns sharper than 90 degrees
                    continue
                cost = gc + c + {0: 0, 1: bend, 7: bend, 2: 3 * bend, 6: 3 * bend}[turn]
                if pen is not None and pen[l, jj, ii]:
                    cost += (soft_hi_cost if pen_hi is not None and pen_hi[l, jj, ii] else soft_cost) * c
                ns = (l, jj, ii, k)
                if cost < g.get(ns, 1e18):
                    g[ns] = cost
                    prev[ns] = st
                    heapq.heappush(heap, (cost + h(jj, ii), cost, ns))
            if vblk is not None and not vblk[j, i]:
                for l2 in range(len(layers)):
                    if l2 != l and not blk[l2, j, i]:
                        ns = (l2, j, i, -1)
                        cost = gc + via_cost + (soft_cost * 3 if vpen is not None and vpen[j, i] else 0)
                        if cost < g.get(ns, 1e18):
                            g[ns] = cost
                            prev[ns] = st
                            heapq.heappush(heap, (cost + h(j, i), cost, ns))
        return None

    def commit(self, netname, path, half, layers, via=(0.45, 0.25)):
        """Turns a cell path into tracks and vias on the board. Returns the new items."""
        ni = self.board.FindNet(netname)
        items = []

        def pt(j, i):
            return self.x0 + i * self.res, self.y0 + j * self.res

        def add_run(layer, cells):
            pts = [pt(j, i) for j, i in cells]
            simp = [pts[0]]
            for k in range(1, len(pts) - 1):
                a, b, c = simp[-1], pts[k], pts[k + 1]
                if abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) > 1e-9:
                    simp.append(b)
            if len(pts) > 1:
                simp.append(pts[-1])
            for a, b in zip(simp, simp[1:]):
                t = pcbnew.PCB_TRACK(self.board)
                t.SetStart(pcbnew.VECTOR2I_MM(float(self.O[0] + a[0]), float(self.O[1] + a[1])))
                t.SetEnd(pcbnew.VECTOR2I_MM(float(self.O[0] + b[0]), float(self.O[1] + b[1])))
                t.SetWidth(pcbnew.FromMM(half * 2))
                t.SetLayer(layer)
                t.SetNet(ni)
                self.board.Add(t)
                items.append(t)
                self.log.append(t)

        run = [(path[0][1], path[0][2])]
        layer = path[0][0]
        for l, j, i in path[1:]:
            if l != layer:
                add_run(layers[layer], run)
                v = pcbnew.PCB_VIA(self.board)
                x, y = pt(j, i)
                v.SetPosition(pcbnew.VECTOR2I_MM(float(self.O[0] + x), float(self.O[1] + y)))
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                v.SetDrill(pcbnew.FromMM(via[1]))
                v.SetWidth(pcbnew.FromMM(via[0]))
                v.SetNet(ni)
                self.board.Add(v)
                items.append(v)
                self.log.append(v)
                layer, run = l, [(j, i)]
            else:
                run.append((j, i))
        add_run(layers[layer], run)
        self.changed()
        return items

    def connect(self, netname, terminals, width, layers=(pcbnew.F_Cu, pcbnew.B_Cu), via=(0.45, 0.25), **kw):
        """Joins all terminals (pads, vias, tracks or (x, y) points) of one net into a tree, nearest first.
        Returns the list of terminals it could not reach."""
        layers = list(layers)
        netcode = self.board.FindNet(netname).GetNetCode()
        half = width / 2
        def cells_of(t):  # a terminal may be a list of items: reaching any of them is enough
            return set().union(*[self.cells(x, layers) for x in t]) if isinstance(t, list) else self.cells(t, layers)
        terms = [(t, cells_of(t)) for t in terminals]
        terms = [(t, c) for t, c in terms if c]
        if not terms:
            return list(terminals)
        # grow the tree from the terminal nearest all the others, so one far terminal can't strand a local cluster
        centre = [np.mean([[c[1], c[2]] for c in cs], axis=0) for _, cs in terms]
        k0 = min(range(len(terms)), key=lambda k: sum(np.abs(centre[k] - c).sum() for c in centre))
        terms.insert(0, terms.pop(k0))
        tree = set(terms[0][1])
        rest = terms[1:]
        failed = []
        retried = False
        while rest or (failed and not retried):
            if not rest:                      # one more try for the misses, now that the tree has grown
                rest, failed, retried = [(t, self.cells(t, layers) if not isinstance(t, list) else
                                          set().union(*[self.cells(x, layers) for x in t])) for t in failed], [], True
            tc = np.array([(c[1], c[2]) for c in tree])
            best = min(rest, key=lambda tc_: min(np.abs(tc - np.array(next(iter(tc_[1]))[1:])).sum(axis=1)))
            rest.remove(best)
            if tree & best[1]:
                tree |= best[1]
                continue
            path = self.search(netcode, half, layers, tree, best[1], via=via, **kw)
            if path is None and len(best[1]) < len(tree) * 4:
                # from the other end: a terminal walled in close by is found far sooner from inside its wall
                path = self.search(netcode, half, layers, best[1], tree, via=via, **kw)
                path = path[::-1] if path else None
            if path is None:
                failed.append(best[0])
                continue
            self.commit(netname, path, half, layers, via)
            tree |= set(path) | best[1]
        return failed
