"""2-D quasi-TEM field solver for (edge-coupled) microstrip on JLCPCB's JLC04161H-3313 stackup.

Finite-difference Laplace solve of the cross-section; capacitance per unit length from the stored energy, once with
the real dielectrics and once in air; Z = 1 / (c * sqrt(C * C_air)). Odd mode gives Zdiff = 2 * Zodd, even mode
Zcommon = Zeven / 2.

  python checks/zsolve.py
"""
import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import spsolve

C0 = 299792458.0
EPS0 = 8.854187817e-12
H, T = 0.0994, 0.035            # mm: 3313 prepreg to the plane, 1 oz finished copper
ER_PP, ER_SM, T_SM = 4.1, 3.8, 0.015
DX = 0.0025                     # grid, mm
W_DOM, H_DOM = 2.4, 0.9


def solve(widths, gap, mode, er_on=True, mask=True):
    nx, ny = int(W_DOM / DX) + 1, int(H_DOM / DX) + 1
    x = np.arange(nx) * DX - W_DOM / 2
    y = np.arange(ny) * DX
    X, Y = np.meshgrid(x, y, indexing="ij")
    eps = np.ones((nx, ny))
    if er_on:
        eps[Y < H] = ER_PP
        if mask:
            eps[(Y >= H) & (Y < H + T + T_SM)] = ER_SM
    # conductors
    fixed = np.zeros((nx, ny), bool)
    V = np.zeros((nx, ny))
    fixed[:, 0] = True                                   # plane
    fixed[0, :] = fixed[-1, :] = fixed[:, -1] = True     # far walls at 0 V
    if len(widths) == 1:
        lines = [(-widths[0] / 2, widths[0] / 2, 1.0)]
    else:
        w1, w2 = widths
        v2 = -1.0 if mode == "odd" else 1.0
        lines = [(-gap / 2 - w1, -gap / 2, 1.0), (gap / 2, gap / 2 + w2, v2)]
    for a, b, v in lines:
        m = (X >= a - 1e-9) & (X <= b + 1e-9) & (Y >= H - 1e-9) & (Y <= H + T + 1e-9)
        fixed |= m
        V[m] = v
        eps[m] = 1.0
    idx = -np.ones((nx, ny), int)
    free = ~fixed
    idx[free] = np.arange(free.sum())
    n = free.sum()
    A = lil_matrix((n, n))
    rhs = np.zeros(n)
    fi, fj = np.nonzero(free)
    for i, j in zip(fi, fj):
        k = idx[i, j]
        diag = 0.0
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ii, jj = i + di, j + dj
            e = 2 * eps[i, j] * eps[ii, jj] / (eps[i, j] + eps[ii, jj])
            diag += e
            if fixed[ii, jj]:
                rhs[k] += e * V[ii, jj]
            else:
                A[k, idx[ii, jj]] = -e
        A[k, k] = diag
    V[free] = spsolve(A.tocsr(), rhs)
    # energy per unit length: 1/2 eps0 sum eps |grad V|^2 dA (on cell faces)
    ex = np.diff(V, axis=0) / (DX * 1e-3)
    ey = np.diff(V, axis=1) / (DX * 1e-3)
    epx = 2 * eps[1:, :] * eps[:-1, :] / (eps[1:, :] + eps[:-1, :])
    epy = 2 * eps[:, 1:] * eps[:, :-1] / (eps[:, 1:] + eps[:, :-1])
    W = 0.5 * EPS0 * ((epx * ex ** 2).sum() + (epy * ey ** 2).sum()) * (DX * 1e-3) ** 2
    # single line: W = C/2; odd/even pair: W = C (per line, V = +-1)
    return 2 * W if len(widths) == 1 else W


def z(widths, gap=0.0, mode="single", mask=True):
    c = solve(widths, gap, mode, True, mask)
    ca = solve(widths, gap, mode, False)
    return 1 / (C0 * np.sqrt(c * ca)), c / ca


if __name__ == "__main__":
    print("single-ended microstrip (with mask / bare):")
    for w in (0.10, 0.12, 0.14, 0.15, 0.20):
        zm, ee = z([w])
        zb, _ = z([w], mask=False)
        print(f"  w {w:.2f} mm: Z0 {zm:5.1f} / {zb:5.1f} ohm, eps_eff {ee:.2f}")
    print("edge-coupled pairs (with mask):")
    for name, w, s, tgt in (("DIFF_100R (HDMI, CSI, Ethernet)", 0.10, 0.10, 100), ("USB_90R", 0.12, 0.10, 90),
                            ("PCIE_85R", 0.14, 0.10, 85)):
        zo, _ = z([w, w], s, "odd")
        ze, _ = z([w, w], s, "even")
        print(f"  {name}: w {w} s {s}: Zdiff {2 * zo:5.1f} ohm (target {tgt}, {(2 * zo / tgt - 1) * 100:+.0f} %), "
              f"Zcommon {ze / 2:4.1f} ohm")
