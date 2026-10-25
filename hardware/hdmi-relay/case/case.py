"""3D-printable case for the rev A carrier: a base tray and a lid, held together by the board's four M3 screws.

  python case/case.py            # writes case/out/base.stl, lid.stl, case.step
  python case/case.py --check    # also checks the case against the board's STEP model (case/ref/relay-board.step)

Needs CadQuery (pip install cadquery). Board coordinates are KiCad's, in mm, with (0, 0) at the board's top-left
corner and y pointing down; the case model uses X = x, Y = -y, Z up. All positions below come from
kicad/relay.kicad_pcb (see README.md for how they were read).
"""
import os
import sys

import cadquery as cq

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

# ---- board ---------------------------------------------------------------------------------------------------
BW, BH, BT = 120.0, 100.0, 1.6                 # board outline and thickness
HOLES = [(4, 4), (4, 96), (116, 36), (116, 68)]  # H601, H603, H602, H604: M3

# ---- case parameters ------------------------------------------------------------------------------------------
GAP = 0.4          # board edge to inner wall
WALL = 2.2
FLOOR = 2.0
ROOF = 2.0
UNDER = 4.0        # floor top to board bottom: through-hole pins stick out 2.0 mm, bottom-side parts 1.3 mm
OVER = 16.8        # board top to roof underside: magjack 15.1 mm (STEP model), CM3 + heatsink about 11 mm
R_OUT = 3.0        # outer corner radius

Z_BB = FLOOR + UNDER            # board bottom
Z_BT = Z_BB + BT                # board top: the base/lid split
Z_TOP = Z_BT + OVER + ROOF      # outside top

X0, X1 = -GAP - WALL, BW + GAP + WALL       # outer extents (board x)
Y0, Y1 = -GAP - WALL, BH + GAP + WALL       # outer extents (board y)

# ---- openings, in board coordinates: (centre x or y along the wall, width, bottom z above board top, height) ------
# Front wall (y = 0): the two HDMI sockets, 6.3 mm tall. Their faces sit 1.0 mm past the board edge; the wall's outer face
# is pocketed around each so the plug's overmould reaches the socket.
FRONT = [
    dict(name="HDMI IN", c=24.0, w=15.8, h=7.0, pocket=(22.0, 12.0)),
    dict(name="HDMI OUT", c=79.0, w=15.8, h=7.0, pocket=(22.0, 12.0)),
]
# Rear wall (y = 100): USB-C, DC jack (its face is 2.1 mm inside the board edge, so the opening fits the plug),
# magjack (15.1 mm tall; it sticks out 5.5 mm past the board edge, through the wall).
REAR = [
    dict(name="USB-C", c=16.0, w=12.6, h=7.0, z=-0.6, r=3.0),
    dict(name="DC IN", c=42.0, w=11.4, h=11.6),
    dict(name="ETHERNET", c=99.0, w=19.2, h=15.6),
]
BATT_WIRE = dict(x=58.0, z=9.0, d=5.0)        # NP-F plate lead from J102, through a grommet
# Left wall (x = 0): two RP-SMA bulkheads for the Wi-Fi antennas, near the M.2 card.
ANTENNAS = [45.0, 75.0]                       # board y
ANT_Z = 9.5                                   # centre above board top
ANT_D, ANT_FLAT = 6.6, 6.0                    # 1/4"-36 RP-SMA thread, D-flat
# Roof: light pipes over the LEDs, pinholes over the buttons, vents over the CM3.
LIGHTPIPES = [(97.72, 18.47, "PWR"), (101.18, 18.47, "STATUS"), (115.70, 11.98, "WIFI")]  # D601, D602, D603
LP_D = 3.1
PINHOLES = [(100.50, 14.24, "RST"), (109.49, 14.24, "REC")]                                # SW601, SW602
LABEL_H, LABEL_DEPTH = 2.4, 0.5               # engraved roof labels, read from the front (HDMI side)
PIN_D = 1.8
VENT = dict(x0=44, x1=88, y0=34, y1=66, slot=2.0, pitch=4.0)  # over the CM3 module (38-94 x 30-70)
# Base: two 1/4"-20 heat-set inserts underneath, clear of bottom-side parts.
TRIPOD = [(30.0, 70.0), (85.0, 85.0)]
TRIPOD_INSERT = dict(d=8.0, depth=6.6)        # 1/4"-20 x 0.25" heat-set insert hole
M3_INSERT = dict(d=4.0, depth=6.5)            # M3 heat-set insert hole (e.g. Ruthex M3 x 5.7); an M3 x 10
                                              # from the counterbore ends 5.6 mm above the board, inside it
M3_CLEAR, M3_HEAD = 3.4, 6.2                  # clearance hole, counterbore for an M3 socket head
POST_D = 6.8                                  # fits inside the holes' 7 mm keep-out


def P(x, y):
    """Board (x, y) to case model (X, Y)."""
    return (x, -y)


def outer_box(z0, z1):
    return (cq.Workplane("XY").workplane(offset=z0)
            .center((X0 + X1) / 2, -(Y0 + Y1) / 2)
            .rect(X1 - X0, Y1 - Y0).extrude(z1 - z0)
            .edges("|Z").fillet(R_OUT))


def inner_box(z0, z1):
    return (cq.Workplane("XY").workplane(offset=z0)
            .center(BW / 2, -BH / 2)
            .rect(BW + 2 * GAP, BH + 2 * GAP).extrude(z1 - z0))


def box(cx, cy, cz, sx, sy, sz):
    return cq.Workplane("XY").box(sx, sy, sz).translate((cx, cy, cz))


def base():
    b = outer_box(0, Z_BT).cut(inner_box(FLOOR, Z_BT + 1))
    for x, y in HOLES:                          # standoffs, with a through hole and a counterbore underneath
        post = cq.Workplane("XY").workplane(offset=FLOOR).center(*P(x, y)).circle(POST_D / 2).extrude(UNDER)
        b = b.union(post)
        b = b.cut(cq.Workplane("XY").center(*P(x, y)).circle(M3_CLEAR / 2).extrude(Z_BB))
        b = b.cut(cq.Workplane("XY").center(*P(x, y)).circle(M3_HEAD / 2).extrude(3.2))
    for x, y in TRIPOD:                         # 1/4"-20 inserts from below, in bosses
        boss = cq.Workplane("XY").workplane(offset=FLOOR).center(*P(x, y)).circle(6.5).extrude(UNDER - 1.0)
        b = b.union(boss)
        b = b.cut(cq.Workplane("XY").center(*P(x, y)).circle(TRIPOD_INSERT["d"] / 2)
                  .extrude(TRIPOD_INSERT["depth"]))
    for i in range(4):                          # low side vents, left and right walls
        y = 20 + i * 20
        for x in (X0, X1):
            b = b.cut(box(x, -y, FLOOR + 2.5, WALL * 3, 12, 2.0))
    # rubber feet recesses (10 mm bumpers)
    for x, y in [(12, 12), (108, 12), (12, 88), (108, 88)]:
        b = b.cut(cq.Workplane("XY").center(*P(x, y)).circle(5.3).extrude(0.6))
    return b


def lid():
    l = outer_box(Z_BT, Z_TOP).cut(inner_box(Z_BT - 1, Z_TOP - ROOF))
    for x, y in HOLES:                          # posts from the roof down to the board, insert at the bottom
        post = (cq.Workplane("XY").workplane(offset=Z_BT).center(*P(x, y))
                .circle(POST_D / 2).extrude(Z_TOP - ROOF - Z_BT))
        l = l.union(post)
        l = l.cut(cq.Workplane("XY").workplane(offset=Z_BT).center(*P(x, y))
                  .circle(M3_INSERT["d"] / 2).extrude(M3_INSERT["depth"]))
    # front wall: HDMI openings, pocketed outside so the face is flush with the socket
    for o in FRONT:
        l = l.cut(box(o["c"], -(Y0 + 1.0), Z_BT + o["h"] / 2 - 0.2, o["w"], WALL * 4, o["h"] + 0.4))
        pw, ph = o["pocket"]
        l = l.cut(box(o["c"], -(Y0 + 0.6), Z_BT + 3.1, pw, 1.2 * 2, ph))
    # rear wall
    for o in REAR:
        z0 = Z_BT + o.get("z", 0.0)
        cut = box(o["c"], -(Y1 - 1.0), z0 + o["h"] / 2, o["w"], WALL * 4, o["h"])
        if o.get("r"):
            cut = cut.edges("|Y").fillet(o["r"])
        l = l.cut(cut)
    l = l.cut(cq.Workplane("XZ", origin=(0, -Y1 + WALL + 1, 0)).center(BATT_WIRE["x"], Z_BT + BATT_WIRE["z"])
              .circle(BATT_WIRE["d"] / 2).extrude(WALL + 2))
    # left wall: RP-SMA bulkheads (D-flat holes)
    for y in ANTENNAS:
        d = (cq.Workplane("YZ", origin=(X0 - 1, 0, 0)).center(-y, Z_BT + ANT_Z)
             .circle(ANT_D / 2).extrude(WALL + 2))
        flat = box(X0 + WALL / 2, -y, Z_BT + ANT_Z + (ANT_FLAT - ANT_D / 2) + 2, WALL * 3, ANT_D + 1, 4)
        l = l.cut(d.cut(flat))
    # roof: light pipes, pinholes, vents, labels
    for x, y, _ in LIGHTPIPES:
        l = l.cut(cq.Workplane("XY").workplane(offset=Z_TOP - ROOF - 1).center(*P(x, y))
                  .circle(LP_D / 2).extrude(ROOF + 2))
    for x, y, _ in PINHOLES:
        l = l.cut(cq.Workplane("XY").workplane(offset=Z_TOP - ROOF - 1).center(*P(x, y))
                  .circle(PIN_D / 2).extrude(ROOF + 2))
    v = VENT
    x = v["x0"]
    while x + v["slot"] <= v["x1"]:
        l = l.cut(box(x + v["slot"] / 2, -(v["y0"] + v["y1"]) / 2, Z_TOP - ROOF / 2,
                      v["slot"], v["y1"] - v["y0"], ROOF + 2).edges("|Z").fillet(v["slot"] / 2 - 0.01))
        x += v["pitch"]
    # Engraved labels, readable standing at the front: the LEDs sit only 3.5 mm apart, so their labels run
    # vertically, starting just behind each light pipe; the button labels sit in front of the pinholes.
    def label(text, x, y, rot, halign):
        wp = (cq.Workplane("XY").workplane(offset=Z_TOP - LABEL_DEPTH).center(*P(x, y))
              .transformed(rotate=(0, 0, rot)))
        return wp.text(text, LABEL_H, LABEL_DEPTH + 1, kind="bold", halign=halign, valign="center")
    for x, y, text in LIGHTPIPES:
        l = l.cut(label(text, x, y + LP_D / 2 + 1.2, -90, "left"))
    for x, y, text in PINHOLES:
        l = l.cut(label(text, x, y - PIN_D / 2 - 2.6, 180, "center"))
    return l


def check(parts):
    """Intersect the case with the board model plus stand-ins for parts without a 3D model."""
    step = os.path.join(HERE, "ref", "relay-board.step")
    # KiCad exports in page coordinates (board top-left at (30, -30)) with the board's bottom at z = 0
    board = cq.importers.importStep(step).translate((-30.0, 30.0, Z_BB))
    # stand-ins, board coordinates: (x0, y0, x1, y1, height above board top)
    extra = [
        (10.5, 92.6, 21.5, 100.0, 3.3, "USB-C (no model)"),
        (4.5, 21.9, 27.5, 32.1, 4.2, "M.2 socket (no model)"),
        (5.0, 25.0, 27.0, 57.0, 4.6, "Wi-Fi card"),
        (38.4, 29.9, 93.6, 70.1, 4.5, "CM3 module on 1.5 mm stack"),
        (51.0, 35.0, 81.0, 65.0, 11.5, "CM3 heatsink 30 x 30 x 6 + pad"),
        (48.5, 86.3, 52.5, 92.3, 3.5, "fuse (no model)"),
    ]
    solids = [board]
    for x0, y0, x1, y1, h, _ in extra:
        solids.append(box((x0 + x1) / 2, -(y0 + y1) / 2, Z_BT + h / 2, x1 - x0, y1 - y0, h))
    ok = True
    for pname, p in parts.items():
        for s, label in zip(solids, ["board STEP"] + [e[5] for e in extra]):
            try:
                v = p.intersect(s).val().Volume()
            except Exception:
                v = 0.0
            if v > 0.5:
                ok = False
                print(f"  CLASH {pname} x {label}: {v:.1f} mm^3")
    tb = board.val().BoundingBox()
    print(f"  board model extents: x {tb.xmin:.1f}..{tb.xmax:.1f}, y {-tb.ymax:.1f}..{-tb.ymin:.1f}, "
          f"z {tb.zmin:.1f}..{tb.zmax:.1f} (board top at {Z_BT:.1f}, roof underside at {Z_TOP - ROOF:.1f})")
    print("  fit check:", "PASS" if ok else "FAIL")
    return ok


def main():
    os.makedirs(OUT, exist_ok=True)
    parts = {"base": base(), "lid": lid()}
    for name, p in parts.items():
        cq.exporters.export(p, os.path.join(OUT, f"{name}.stl"), tolerance=0.05, angularTolerance=0.1)
    asm = cq.Assembly().add(parts["base"], name="base").add(parts["lid"], name="lid")
    asm.save(os.path.join(OUT, "case.step"))
    print(f"case: {X1 - X0:.1f} x {Y1 - Y0:.1f} x {Z_TOP:.1f} mm outside; board on {UNDER} mm standoffs; "
          f"{OVER} mm above the board")
    if "--check" in sys.argv:
        sys.exit(0 if check(parts) else 1)


if __name__ == "__main__":
    main()
