"""Geometry for hand-drawn differential pairs: parallel offsets of a centreline and length-matching bumps.
Shared by gen/route.py and gen/hdmi_out.py."""
import math


def offset(pts, d):
    """The polyline moved sideways by d (positive = to the right of the direction of travel, y pointing down),
    with mitred corners, so parallel lanes keep their spacing through 45 degree bends."""
    def normal(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy)
        return -dy / n, dx / n
    ns = [normal(a, b) for a, b in zip(pts, pts[1:])]
    out = [(pts[0][0] + d * ns[0][0], pts[0][1] + d * ns[0][1])]
    for p, na, nb in zip(pts[1:-1], ns, ns[1:]):
        k = 1 + na[0] * nb[0] + na[1] * nb[1]
        out.append((p[0] + d * (na[0] + nb[0]) / k, p[1] + d * (na[1] + nb[1]) / k))
    out.append((pts[-1][0] + d * ns[-1][0], pts[-1][1] + d * ns[-1][1]))
    return out



def length(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))



def tune(pts, seg, extra, side, start=0.8, h_max=0.45, top=0.35, gap=0.35):
    """Adds `extra` mm to a trace with 45-degree-chamfered bumps on straight segment `seg`, on one side
    (+1 right of travel, -1 left), starting `start` mm along it. Bumps go on the side away from the partner trace."""
    a, b = pts[seg], pts[seg + 1]
    L = math.dist(a, b)
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    nv = (-u[1] * side, u[0] * side)
    c = 0.1
    n = max(1, math.ceil(extra / (2 * h_max - 2.343 * c)))
    h = (extra / n + 2.343 * c) / 2
    if h < 2 * c:                 # small corrections: shallower bumps, chamfer half the height
        h = extra / (n * 0.828)
        c = h / 2
    pitch = 4 * c + top + gap
    assert start + n * pitch - gap < L - 0.3, f"segment {seg} too short for {n} bumps"
    out = list(pts[:seg + 1])
    for i in range(n):
        s = start + i * pitch

        def at(along, out_):
            return (a[0] + u[0] * (s + along) + nv[0] * out_, a[1] + u[1] * (s + along) + nv[1] * out_)
        out += [at(0, 0), at(c, c), at(c, h - c), at(2 * c, h), at(2 * c + top, h), at(3 * c + top, h - c),
                at(3 * c + top, c), at(4 * c + top, 0)]
    return out + list(pts[seg + 1:])
