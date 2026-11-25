"""Differential pairs through gen/router.py: the pair is routed as one centreline as wide as both traces and their
gap, then split into its two traces with gen/pairs.py's offset. Where the centreline changes layer, the pair
changes layer through two vias side by side (the search keeps room for both). Fan-in from each pad to its trace
is a short straight segment."""
import math

import pcbnew

from pairs import length, offset


def _simplify(pts):
    out = [pts[0]]
    for k in range(1, len(pts) - 1):
        a, b, c = out[-1], pts[k], pts[k + 1]
        if abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) > 1e-9:
            out.append(b)
    if len(pts) > 1:
        out.append(pts[-1])
    out = [q for k, q in enumerate(out) if k == 0 or math.dist(q, out[k - 1]) > 1e-6]
    changed = True          # no doubling back (grid snapping at the ends)
    while changed and len(out) > 2:
        changed = False
        for k in range(1, len(out) - 1):
            a, b, c = out[k - 1], out[k], out[k + 1]
            if (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1]) < -1e-9:
                del out[k]
                changed = True
                break
    return out


def _left_normal(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    return dy / n, -dx / n


def route_pair(R, board, O, p_pads, n_pads, starts, width, gap, layers=(pcbnew.F_Cu,), window=8.0,
               max_expand=3000000, anchors=None, via=(0.45, 0.25), via_pitch=0.75, greed=2.0, **kw):
    """p_pads, n_pads: (start pad, end pad) of each net. starts: (start point, end point) of the routed part of
    the centreline, just outside each end's pads, in board mm. anchors: optional (start, end) points the
    centreline begins and ends with, between each end's two pads, so the pair meets its pads square on.
    Returns (P length, N length, crossed) or None if no path."""
    half = (width + gap) / 2           # centreline to trace centre
    fat = half + width / 2             # half the width of the pair as a whole
    layers = list(layers)
    # the wide centreline keeps clear of its own pads too (it may only touch them through the anchors and fan-in)
    path = R.search((-1,), fat, layers, R.cells(starts[0], layers), R.cells(starts[1], layers), window=window,
                    max_expand=max_expand, greed=greed, via=(via[0] + via_pitch, via[1]), **kw)
    if path is None:
        return None

    def xy(item):
        v = item.GetPosition()
        return pcbnew.ToMM(v.x) - O[0], pcbnew.ToMM(v.y) - O[1]

    # split the path into runs on one layer; consecutive runs meet at a via cell
    runs = [[path[0]]]
    for c in path[1:]:
        if c[0] != runs[-1][-1][0]:
            runs.append([c])
        else:
            runs[-1].append(c)
    cpts = [[(R.x0 + i * R.res, R.y0 + j * R.res) for _, j, i in run] for run in runs]
    cpts[0] = [starts[0]] + cpts[0]
    cpts[-1] = cpts[-1] + [starts[1]]
    if anchors:
        cpts[0] = [anchors[0]] + cpts[0]
        cpts[-1] = cpts[-1] + [anchors[1]]
    cpts = [_simplify(c) for c in cpts]

    # traces: left and right offsets per run, joined through a via pair at each layer change
    left_tr, right_tr = [], []         # lists of (layer, polyline)
    vias = []                          # (left via point, right via point)
    for k, (run, pts) in enumerate(zip(runs, cpts)):
        layer = layers[run[0][0]]
        if len(pts) < 2:               # a run of a single cell between two layer changes: nothing to draw
            pts = pts + [pts[-1]]
        lp, rp = (offset(pts, -half), offset(pts, half)) if math.dist(pts[0], pts[-1]) > 1e-6 else (pts, pts)
        if k > 0:                      # start at the vias left by the previous run
            lv, rv = vias[-1]
            lp, rp = [lv] + lp, [rv] + rp
        if k < len(runs) - 1:          # end at a via pair across the direction of travel
            c = pts[-1]
            # across the mean of the incoming and outgoing directions, so through a turn each trace keeps to
            # its own side (across the incoming one only, the two jogs would cross)
            din = (pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]) if len(pts) > 1 else (0, 0)
            nxt = cpts[k + 1]
            dout = (nxt[1][0] - nxt[0][0], nxt[1][1] - nxt[0][1]) if len(nxt) > 1 else (0, 0)
            li, lo = math.hypot(*din), math.hypot(*dout)
            dsum = ((din[0] / li if li > 1e-6 else 0) + (dout[0] / lo if lo > 1e-6 else 0),
                    (din[1] / li if li > 1e-6 else 0) + (dout[1] / lo if lo > 1e-6 else 0))
            nx, ny = _left_normal((0, 0), dsum) if math.hypot(*dsum) > 1e-6 else (0, 1)
            lv = (c[0] + nx * via_pitch / 2, c[1] + ny * via_pitch / 2)
            rv = (c[0] - nx * via_pitch / 2, c[1] - ny * via_pitch / 2)
            lp, rp = lp + [lv], rp + [rv]
            vias.append((lv, rv))
        left_tr.append((layer, lp))
        right_tr.append((layer, rp))

    # P is whichever side starts nearer the P pad; the far end must agree, or the pair would have to cross
    p0, n0 = xy(p_pads[0]), xy(n_pads[0])
    swap = math.dist(left_tr[0][1][0], p0) + math.dist(right_tr[0][1][0], n0) > \
        math.dist(left_tr[0][1][0], n0) + math.dist(right_tr[0][1][0], p0)
    p_tr, n_tr = (right_tr, left_tr) if swap else (left_tr, right_tr)
    p1, n1 = xy(p_pads[1]), xy(n_pads[1])
    crossed = math.dist(p_tr[-1][1][-1], p1) + math.dist(n_tr[-1][1][-1], n1) > \
        math.dist(p_tr[-1][1][-1], n1) + math.dist(n_tr[-1][1][-1], p1)
    p_tr[0] = (p_tr[0][0], [p0] + p_tr[0][1]); p_tr[-1] = (p_tr[-1][0], p_tr[-1][1] + [p1])
    n_tr[0] = (n_tr[0][0], [n0] + n_tr[0][1]); n_tr[-1] = (n_tr[-1][0], n_tr[-1][1] + [n1])

    def mm(q):
        return pcbnew.VECTOR2I_MM(float(O[0] + q[0]), float(O[1] + q[1]))
    lengths = []
    for pad, trs, side in ((p_pads[0], p_tr, 0 if not swap else 1), (n_pads[0], n_tr, 1 if not swap else 0)):
        ni = pad.GetNet()
        total = 0.0
        for layer, pts_ in trs:
            total += length(pts_)
            for a, b in zip(pts_, pts_[1:]):
                if math.dist(a, b) < 1e-4:
                    continue
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(mm(a)); t.SetEnd(mm(b)); t.SetWidth(pcbnew.FromMM(width)); t.SetLayer(layer)
                t.SetNet(ni)
                board.Add(t)
                R.log.append(t)
        for v_pair in vias:
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(mm(v_pair[side])); v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetWidth(pcbnew.FromMM(via[0])); v.SetDrill(pcbnew.FromMM(via[1])); v.SetNet(ni)
            board.Add(v)
            R.log.append(v)
        lengths.append(total)
    R.changed()
    return lengths[0], lengths[1], crossed
