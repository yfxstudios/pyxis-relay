"""
NanoPi R5C enclosure — parametric build script for Blender (tested on 5.2).

    /Applications/Blender.app/Contents/MacOS/Blender -b -P build_case.py -- [--render]

Builds the hood (top shell) and tray (bottom shell), a simplified R5C board model for
fit checks, exports print-oriented STLs, and saves R5C_case.blend next to this file.

Coordinates are millimetres in the board's own frame, taken from FriendlyElec's
NanoPi_R5C_2209.dxf: the PCB spans x 0..58, y 0..58, its top surface is z = 0.
The port edge is x = 58 (USB-C, LAN, WAN, HDMI); the USB-A / LED edge is x = 0.

Values marked VERIFY are not in FriendlyElec's 2D drawing (component heights). They
were estimated from FriendlyElec's photos; measure your board with calipers and
adjust before a production run (see README.md).
"""
import bpy, bmesh, math, sys, os
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
TRACE = "--trace" in (sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

# --------------------------------------------------------------------------------------
# Parameters
# --------------------------------------------------------------------------------------
PCB_T = 1.6
WALL = 2.0
CLR = 0.35                 # clearance around each connector in the port openings
# Interior cavity (board frame). Bands around the board leave room for antenna cables.
IN_X0, IN_X1 = -1.0, 58.2  # back (USB-A/LED edge) .. front (inner face of port wall)
IN_Y0, IN_Y1 = -2.7, 61.0  # 61.0 clears the microSD slot, which sticks out to y = 60.49
IN_TOP = 16.6              # interior ceiling above PCB top
FLOOR_TOP = -10.1          # below-board cavity for the M.2 Wi-Fi card and its cables
FLOOR_T = 2.0
R_OUT = 5.0                # vertical corner radius, outside
TOP_CHAMFER = 1.2
BOTTOM_CHAMFER = 1.0
# Seam: hood skirt (outer half of wall) overlaps a tongue on the tray (inner half).
SEAM_STEP = -1.5           # tray outer wall top
TONGUE_TOP = -0.2          # tray inner-half tongue top
HOOD_INNER_BOTTOM = 0.2    # hood inner-half bottom (0.4 mm over the tongue)
SKIRT_BOTTOM = -1.1        # hood outer-half bottom (0.4 mm reveal line above the step)

# Mounting holes from the DXF (pads r = 2.0). The third hole (34.32, 56.04) is covered
# underneath by the M.2 Wi-Fi card, so only two take screws (M2 x 18 countersunk, from
# below). The hood presses on all three; a plain post supports the board near the third.
HOLES = [(2.50, 17.01), (34.32, 2.00), (34.32, 56.04)]
SCREW_HOLES = HOLES[:2]
SUPPORT_POST = (53.75, 56.30)   # 2.08 mm from any bottom-side part in the DXF
SUPPORT_R = 1.6
PILLAR_R = 1.95            # limited by parts 2.08 mm from the hole centres (DXF)
PILOT_R = 0.8              # 1.6 mm pilot for M2 thread-forming into plastic
PILOT_DEPTH = 8.0
STANDOFF_R = 2.2           # limited by bottom-side parts 2.32 mm away (DXF)
SCREW_CLEAR_R = 1.2
CSK_R = 2.0                # M2 countersunk head 3.8 mm

# Port openings on the x = 58 wall: (name, y0, y1, z0, z1, corner radius)
RJ45_H = 13.8              # VERIFY: RJ45 height above PCB (photos suggest ~13.4; 13.8 covers 13.3-13.9 parts)
HDMI_H = 15.4              # VERIFY: vertical HDMI height above PCB (photos suggest ~15.0)
USBC_H = 3.26              # VERIFY: top-mount USB-C body height
PORTS = [
    # USB-C body y 1.83..10.77 (pads centre y 6.30); opening sized for cable overmolds
    ("USB-C", 0.8, 11.4, USBC_H / 2 - 3.3, USBC_H / 2 + 3.3, 2.4),
    ("LAN",  12.75 - CLR, 28.65 + CLR, -CLR, RJ45_H + CLR, 0.8),
    ("WAN",  30.81 - CLR, 46.71 + CLR, -CLR, RJ45_H + CLR, 0.8),
    ("HDMI", 48.80 - CLR, 56.50 + CLR, -CLR, HDMI_H + CLR, 0.8),
]
LABELS = [("5V", 6.1), ("LAN", 20.7), ("WAN", 38.76), ("HDMI", 52.65)]

# Status LEDs (DXF pads, x ~1.0): WiFi, LAN, WAN, SYS. Light pipes: 2 mm clear rod.
LEDS = [(1.0, 20.6), (1.0, 26.2), (1.0, 31.8), (1.0, 37.4)]
LIGHTPIPE_R = 1.05
# RP-SMA bulkheads on both side walls (1/4"-36 thread): 6.5 mm hole, flats 5.9 mm apart
ANT_X, ANT_Z = 16.0, 9.0
ANT_R, ANT_FLAT = 3.25, 2.95

OUT_X0, OUT_X1 = IN_X0 - WALL, IN_X1 + WALL
OUT_Y0, OUT_Y1 = IN_Y0 - WALL, IN_Y1 + WALL
OUT_TOP = IN_TOP + 2.0
OUT_BOTTOM = FLOOR_TOP - FLOOR_T

# --------------------------------------------------------------------------------------
# Mesh helpers (bmesh, no operators)
# --------------------------------------------------------------------------------------
def rrect_pts(x0, x1, y0, y1, r, seg=20):
    r = max(0.01, min(r, (x1 - x0) / 2 - 1e-4, (y1 - y0) / 2 - 1e-4))
    cs = [(x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180), (x1 - r, y0 + r, 270)]
    pts = []
    for cx, cy, a0 in cs:
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts

def loft(name, rings):
    """rings: list of (z, [(u, v), ...]) with identical point counts, bottom to top."""
    bm = bmesh.new()
    vrings = [[bm.verts.new((u, v, z)) for (u, v) in pts] for z, pts in rings]
    n = len(vrings[0])
    for a, b in zip(vrings, vrings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.faces.new(list(reversed(vrings[0])))
    bm.faces.new(vrings[-1])
    return finish(name, bm)

def rbox(name, x0, x1, y0, y1, z0, z1, r, chamfer_top=0.0, chamfer_bottom=0.0, seg=20):
    rings = []
    if chamfer_bottom:
        c = chamfer_bottom
        rings += [(z0, rrect_pts(x0 + c, x1 - c, y0 + c, y1 - c, r - c, seg)),
                  (z0 + c, rrect_pts(x0, x1, y0, y1, r, seg))]
    else:
        rings += [(z0, rrect_pts(x0, x1, y0, y1, r, seg))]
    if chamfer_top:
        c = chamfer_top
        rings += [(z1 - c, rrect_pts(x0, x1, y0, y1, r, seg)),
                  (z1, rrect_pts(x0 + c, x1 - c, y0 + c, y1 - c, r - c, seg))]
    else:
        rings += [(z1, rrect_pts(x0, x1, y0, y1, r, seg))]
    return loft(name, rings)

def prism(name, pts2d, axis, w0, w1):
    """Extrude a 2D outline along an axis. axis 'x': pts are (y, z); 'y': (x, z); 'z': (x, y)."""
    bm = bmesh.new()
    def P(u, v, w):
        return {"x": (w, u, v), "y": (u, w, v), "z": (u, v, w)}[axis]
    a = [bm.verts.new(P(u, v, w0)) for u, v in pts2d]
    b = [bm.verts.new(P(u, v, w1)) for u, v in pts2d]
    n = len(a)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.faces.new(list(reversed(a)))
    bm.faces.new(b)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish(name, bm)

def cyl(name, x, y, z0, z1, r, seg=48, r_top=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r,
                          radius2=r if r_top is None else r_top, depth=z1 - z0,
                          matrix=Matrix.Translation((x, y, (z0 + z1) / 2)))
    return finish(name, bm)

def finish(name, bm):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob

def join(name, obs):
    bm = bmesh.new()
    for ob in obs:
        bm.from_mesh(ob.data)
        bpy.data.objects.remove(ob)
    return finish(name, bm)

def boolean(target, tool, op):
    m = target.modifiers.new("b", "BOOLEAN")
    m.operation = op
    m.solver = "EXACT"
    m.use_self = True           # joined cutters overlap each other
    m.use_hole_tolerant = True
    m.object = tool
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(target.evaluated_get(dg))
    target.modifiers.clear()
    old = target.data
    target.data = me
    bpy.data.meshes.remove(old)
    bpy.data.objects.remove(tool)
    if TRACE:
        print(f"    bool {op:10} -> {target.name}: {len(me.polygons)} faces, {mesh_volume(target)/1000:.2f} cm3, non-manifold {non_manifold(target)}")
    return target

def text_solid(name, body, size, depth):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.size = size
    cu.extrude = depth / 2
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.resolution_u = 6
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    bm = bmesh.new()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    return finish(name, bm)

def slot2d(u0, u1, v0, v1):
    """Stadium (rounded slot) outline."""
    return rrect_pts(u0, u1, v0, v1, min(u1 - u0, v1 - v0) / 2, 12)

def dhole2d(cu, cv, r, flat):
    a = math.asin(flat / r)
    pts = []
    for k in range(17):  # right arc
        t = -a + 2 * a * k / 16
        pts.append((cu + r * math.cos(t), cv + r * math.sin(t)))
    for k in range(17):  # left arc
        t = math.pi - a + 2 * a * k / 16
        pts.append((cu + r * math.cos(t), cv + r * math.sin(t)))
    return pts

# --------------------------------------------------------------------------------------
# Hood (top shell)
# --------------------------------------------------------------------------------------
def build_hood():
    hood = rbox("hood", OUT_X0, OUT_X1, OUT_Y0, OUT_Y1, SKIRT_BOTTOM, OUT_TOP, R_OUT,
                chamfer_top=TOP_CHAMFER)
    cut = []
    # interior cavity, and the inner half of the wall below the seam
    cut.append(rbox("cav", IN_X0, IN_X1, IN_Y0, IN_Y1, SKIRT_BOTTOM - 1, IN_TOP, R_OUT - WALL))
    cut.append(rbox("skirt", IN_X0 - WALL / 2, IN_X1 + WALL / 2, IN_Y0 - WALL / 2, IN_Y1 + WALL / 2,
                    SKIRT_BOTTOM - 1, HOOD_INNER_BOTTOM, R_OUT - WALL / 2))
    hood = boolean(hood, join("hood_cav_tmp", cut), "DIFFERENCE")
    # re-add pillars inside the cavity (the cavity cut removed their lower part)
    pil = [cyl(f"pillarB{i}", x, y, 0.0, IN_TOP + 0.5, PILLAR_R) for i, (x, y) in enumerate(HOLES)]
    pil += [cyl(f"collarB{i}", x, y, IN_TOP - 4.0, IN_TOP + 0.5, LIGHTPIPE_R + 0.8) for i, (x, y) in enumerate(LEDS)]
    hood = boolean(hood, join("hood_pil_tmp", pil), "UNION")

    cut = []
    for i, (x, y) in enumerate(SCREW_HOLES):
        cut.append(cyl(f"pilot{i}", x, y, -1.0, PILOT_DEPTH, PILOT_R, seg=24))
    for i, (x, y) in enumerate(LEDS):
        cut.append(cyl(f"lp{i}", x, y, IN_TOP - 5.0, OUT_TOP + 1, LIGHTPIPE_R, seg=32))
    for name, y0, y1, z0, z1, r in PORTS:
        # notch open at the bottom edge so the hood slides straight down over the ports
        pts = rrect_pts(y0, y1, z0, z1, r)
        pts = [(u, v) for (u, v) in pts]
        cut.append(prism(f"port_{name}", pts, "x", IN_X1 - 1.0, OUT_X1 + 1.0))
        cut.append(prism(f"portslot_{name}", [(y0, SKIRT_BOTTOM - 1), (y1, SKIRT_BOTTOM - 1), (y1, (z0 + z1) / 2), (y0, (z0 + z1) / 2)],
                         "x", IN_X1 - 1.0, OUT_X1 + 1.0))
    # top grille: recessed panel with slots over the SoC/heatsink
    cx, cy = (OUT_X0 + OUT_X1) / 2, (OUT_Y0 + OUT_Y1) / 2
    gx0, gx1, gy0, gy1 = cx - 23.6, cx + 23.6, cy - 20.0, cy + 20.0
    # Engraved frame around the grille (0.8 wide, 0.4 deep). A recessed panel would be an
    # unsupported 47 x 40 mm ceiling when the hood prints top-down; a groove bridges 0.8 mm.
    frame = rbox("frame_o", gx0, gx1, gy0, gy1, OUT_TOP - 0.4, OUT_TOP + 1, 3.0)
    frame = boolean(frame, rbox("frame_i", gx0 + 0.8, gx1 - 0.8, gy0 + 0.8, gy1 - 0.8, OUT_TOP - 1, OUT_TOP + 2, 2.2), "DIFFERENCE")
    cut.append(frame)
    n = 12
    pitch = (gx1 - gx0 - 4.0) / (n - 1)
    for k in range(n):
        u = gx0 + 2.0 + k * pitch
        cut.append(prism(f"gslot{k}", slot2d(u - 0.9, u + 0.9, gy0 + 2.5, gy1 - 2.5), "z", IN_TOP - 1, OUT_TOP + 1))
    # side intake vents (vertical slots, front half of both side walls)
    for side, (w0, w1) in (("s0", (OUT_Y0 - 1, IN_Y0 + 1)), ("s1", (IN_Y1 - 1, OUT_Y1 + 1))):
        for k in range(7):
            u = 30.0 + k * 3.6
            cut.append(prism(f"vent_{side}{k}", slot2d(u - 0.9, u + 0.9, 3.0, 11.0), "y", w0, w1))
        cut.append(prism(f"ant_{side}", dhole2d(ANT_X, ANT_Z, ANT_R, ANT_FLAT), "y", w0, w1))
    hood = boolean(hood, join("hood_cut_tmp", cut), "DIFFERENCE")
    return hood

# --------------------------------------------------------------------------------------
# Tray (bottom shell)
# --------------------------------------------------------------------------------------
def build_tray():
    tray = rbox("tray", OUT_X0, OUT_X1, OUT_Y0, OUT_Y1, OUT_BOTTOM, SEAM_STEP, R_OUT,
                chamfer_bottom=BOTTOM_CHAMFER)
    tongue = rbox("tongue", IN_X0 - WALL / 2, IN_X1 + WALL / 2, IN_Y0 - WALL / 2, IN_Y1 + WALL / 2,
                  SEAM_STEP - 0.5, TONGUE_TOP, R_OUT - WALL / 2)
    tray = boolean(tray, tongue, "UNION")
    tray = boolean(tray, rbox("tcav", IN_X0, IN_X1, IN_Y0, IN_Y1, FLOOR_TOP, TONGUE_TOP + 5, R_OUT - WALL), "DIFFERENCE")
    stand = [cyl(f"stand{i}", x, y, FLOOR_TOP - 0.5, -PCB_T, STANDOFF_R) for i, (x, y) in enumerate(SCREW_HOLES)]
    stand.append(cyl("support", *SUPPORT_POST, FLOOR_TOP - 0.5, -PCB_T, SUPPORT_R))
    tray = boolean(tray, join("stand_tmp", stand), "UNION")

    cut = []
    for i, (x, y) in enumerate(SCREW_HOLES):
        cut.append(cyl(f"clr{i}", x, y, OUT_BOTTOM - 1, 0, SCREW_CLEAR_R, seg=32))
        # 90-degree countersink for an M2 flat head, flush with the bottom
        cut.append(cyl(f"csk{i}", x, y, OUT_BOTTOM - 0.01, OUT_BOTTOM + (CSK_R - SCREW_CLEAR_R), CSK_R, seg=32, r_top=SCREW_CLEAR_R))
        cut.append(cyl(f"cskb{i}", x, y, OUT_BOTTOM - 1, OUT_BOTTOM + 0.0, CSK_R, seg=32))
    for name, y0, y1, z0, z1, r in PORTS:
        if z0 < TONGUE_TOP:
            cut.append(prism(f"tport_{name}", rrect_pts(y0, y1, z0, z1, r), "x", IN_X1 - 1.0, OUT_X1 + 1.0))
    # floor vents under the M.2 Wi-Fi card area and towards the front
    for k in range(9):
        v = 12.0 + k * 4.5
        cut.append(prism(f"fvent{k}", slot2d(8.0, 30.0, v - 0.9, v + 0.9), "z", OUT_BOTTOM - 1, FLOOR_TOP + 1))
    # recesses for 10 mm rubber feet
    fi = 7.5
    for i, (x, y) in enumerate([(OUT_X0 + fi, OUT_Y0 + fi), (OUT_X1 - fi, OUT_Y0 + fi),
                                (OUT_X0 + fi, OUT_Y1 - fi), (OUT_X1 - fi, OUT_Y1 - fi)]):
        cut.append(cyl(f"foot{i}", x, y, OUT_BOTTOM - 1, OUT_BOTTOM + 1.0, 5.2))
    # engraved port labels on the front face, under each port
    for txt, y in LABELS:
        t = text_solid(f"lbl_{txt}", txt, 3.0, 1.2)
        t.data.transform(Matrix.Rotation(math.radians(90), 4, "X"))
        t.data.transform(Matrix.Rotation(math.radians(90), 4, "Z"))
        t.data.transform(Matrix.Translation((OUT_X1, y, (OUT_BOTTOM + SEAM_STEP) / 2 - 0.3)))
        cut.append(t)
    tray = boolean(tray, join("tray_cut_tmp", cut), "DIFFERENCE")
    return tray

# --------------------------------------------------------------------------------------
# Simplified board model for fit checks (not printed)
# --------------------------------------------------------------------------------------
BOARD_OUTLINE = [(2.032, 0), (15.977, 0), (15.977, 2.083), (25.044, 2.083), (27.686, 3.886),
                 (29.616, 3.886), (32.156, 1.346), (32.156, 0), (55.968, 0), (58, 2.032),
                 (58, 56.49), (56.312, 58.014), (2.032, 58), (0, 55.968), (0, 2.032)]

def build_board():
    parts = {}
    parts["pcb"] = prism("pcb", BOARD_OUTLINE, "z", -PCB_T, 0)
    box = lambda n, x0, x1, y0, y1, z0, z1: rbox(n, x0, x1, y0, y1, z0, z1, 0.3, seg=2)
    parts["rj45_lan"] = box("rj45_lan", 38.84, 60.15, 12.75, 28.65, 0, RJ45_H)
    parts["rj45_wan"] = box("rj45_wan", 38.84, 60.15, 30.81, 46.71, 0, RJ45_H)
    parts["hdmi"] = box("hdmi", 36.79, 60.19, 48.80, 56.50, 0, HDMI_H)
    parts["usbc"] = box("usbc", 51.0, 58.4, 1.83, 10.77, 0, USBC_H)
    parts["usba_1"] = box("usba_1", 0.04, 14.0, 1.73, 14.93, 0, 7.0)
    parts["usba_2"] = box("usba_2", 0.04, 14.0, 43.06, 56.26, 0, 7.0)
    parts["microsd"] = box("microsd", 19.38, 30.38, 44.8, 60.49, 0, 1.9)
    parts["heatsink"] = box("heatsink", 8.5, 27.5, 20.9, 39.9, 0, 11.5)
    # Bottom-side parts and THT legs as a 2.6 mm slab, minus the clear zones the DXF shows
    # around the screw holes (2.32 mm) and the support-post spot (2.08 mm).
    slab = prism("bottom_parts", BOARD_OUTLINE, "z", -PCB_T - 2.6, -PCB_T)
    keep = [cyl(f"kz{i}", x, y, -PCB_T - 3, -PCB_T + 0.1, 2.3) for i, (x, y) in enumerate(SCREW_HOLES)]
    keep.append(cyl("kzp", *SUPPORT_POST, -PCB_T - 3, -PCB_T + 0.1, 2.05))
    parts["bottom_parts"] = boolean(slab, join("keep_tmp", keep), "DIFFERENCE")
    # M.2 2230 card: connector near x 5, retaining screw/standoff at (35.38, 45.57)
    parts["m2_card"] = box("m2_card", 5.0, 37.2, 34.57, 56.57, -PCB_T - 5.0, -PCB_T - 2.6)
    parts["m2_screw"] = cyl("m2_screw", 35.38, 45.57, -PCB_T - 6.5, -PCB_T, 3.1)
    # RP-SMA bulkhead hardware inside each side wall: hex nut + jack body + cable bend
    for s, (y_in, d) in (("0", (IN_Y0, 1)), ("1", (IN_Y1, -1))):
        y0, y1 = sorted((y_in, y_in + d * 3.0))
        parts[f"ant_nut{s}"] = prism(f"ant_nut{s}", [(ANT_X + 4.6 * math.cos(math.radians(30 + 60 * k)),
                                                       ANT_Z + 4.6 * math.sin(math.radians(30 + 60 * k))) for k in range(6)], "y", y0, y1)
        y0, y1 = sorted((y_in, y_in + d * 9.0))
        parts[f"ant_body{s}"] = prism(f"ant_body{s}", rrect_pts(ANT_X - 3.2, ANT_X + 3.2, ANT_Z - 3.2, ANT_Z + 3.2, 3.19, 8), "y", y0, y1)
    for i, (x, y) in enumerate(LEDS):
        parts[f"led{i}"] = box(f"led{i}", x - 0.4, x + 0.4, y - 0.8, y + 0.8, 0, 0.6)
    return parts

# --------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------
def mesh_volume(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    v = bm.calc_volume(signed=False)
    bm.free()
    return v

def non_manifold(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    n = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return n

def copy_ob(ob, name):
    c = ob.copy()
    c.data = ob.data.copy()
    c.name = name
    bpy.context.scene.collection.objects.link(c)
    return c

def interference(case_ob, part_ob):
    a = copy_ob(case_ob, "chk_a")
    b = copy_ob(part_ob, "chk_b")
    a = boolean(a, b, "INTERSECT")
    v = mesh_volume(a) if len(a.data.polygons) else 0.0
    bpy.data.objects.remove(a)
    return v

# --------------------------------------------------------------------------------------
def main():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    hood = build_hood()
    tray = build_tray()
    board = build_board()

    print("\n=== CHECKS ===")
    for ob in (hood, tray):
        print(f"{ob.name}: {len(ob.data.polygons)} faces, volume {mesh_volume(ob)/1000:.1f} cm3, non-manifold edges {non_manifold(ob)}")
    bad = 0
    for pname, p in board.items():
        for ob in (hood, tray):
            v = interference(ob, p)
            if v > 0.01:
                bad += 1
                print(f"  INTERFERENCE {ob.name} x {pname}: {v:.2f} mm3")
    hc = copy_ob(hood, "hc")
    v = interference(hc, tray)
    bpy.data.objects.remove(hc)
    print(f"  hood x tray overlap: {v:.3f} mm3")
    if v > 0.01:
        bad += 1
    print(f"interference problems: {bad}")
    print(f"outer size: {OUT_X1-OUT_X0:.1f} x {OUT_Y1-OUT_Y0:.1f} x {OUT_TOP-OUT_BOTTOM:.1f} mm")

    # Export print-oriented STLs
    os.makedirs(os.path.join(HERE, "stl"), exist_ok=True)
    def export(ob, path, flip):
        c = copy_ob(ob, ob.name + "_print")
        if flip:
            c.data.transform(Matrix.Rotation(math.pi, 4, "X"))
        zmin = min(v.co.z for v in c.data.vertices)  # bound_box is stale after transform()
        c.data.transform(Matrix.Translation((0, 0, -zmin)))
        for o in bpy.context.scene.objects:
            o.select_set(False)
        c.select_set(True)
        bpy.context.view_layer.objects.active = c
        bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, apply_modifiers=True)
        bpy.data.objects.remove(c)
    export(hood, os.path.join(HERE, "stl", "R5C_case_hood.stl"), flip=True)   # print top-down
    export(tray, os.path.join(HERE, "stl", "R5C_case_tray.stl"), flip=False)

    # One print plate with both parts side by side (hood top-down, tray upright, 10 mm gap)
    h = copy_ob(hood, "plate_hood")
    h.data.transform(Matrix.Rotation(math.pi, 4, "X"))
    t = copy_ob(tray, "plate_tray")
    for ob, dx in ((h, -(OUT_X1 - OUT_X0) / 2 - 5.0), (t, (OUT_X1 - OUT_X0) / 2 + 5.0)):
        vs = ob.data.vertices
        cx = (min(v.co.x for v in vs) + max(v.co.x for v in vs)) / 2
        cy = (min(v.co.y for v in vs) + max(v.co.y for v in vs)) / 2
        ob.data.transform(Matrix.Translation((dx - cx, -cy, -min(v.co.z for v in vs))))
    export(join("R5C_case_plate", [h, t]), os.path.join(HERE, "stl", "R5C_case_plate.stl"), flip=False)

    # Fit-test slice: the front 9 mm of both parts, to check ports before a full print
    for ob, fname, flip in ((hood, "fit_test_front_hood.stl", True), (tray, "fit_test_front_tray.stl", False)):
        c = copy_ob(ob, ob.name + "_slice")
        c = boolean(c, rbox("slicebox", OUT_X1 - 9.0, OUT_X1 + 1, OUT_Y0 - 1, OUT_Y1 + 1, OUT_BOTTOM - 1, OUT_TOP + 1, 0.1, seg=2), "INTERSECT")
        export(c, os.path.join(HERE, "stl", fname), flip)
        bpy.data.objects.remove(c)

    # Scene setup for the .blend: board parts in their own collection, hidden by default
    col = bpy.data.collections.new("R5C board (reference)")
    bpy.context.scene.collection.children.link(col)
    for p in board.values():
        bpy.context.scene.collection.objects.unlink(p)
        col.objects.link(p)
    style(hood, tray, board)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "R5C_case.blend"))
    if "--render" in ARGS:
        render_all(hood, tray, board)

def mat(name, rgb, rough=0.55, metal=0.0):
    m = bpy.data.materials.new(name)
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m

def style(hood, tray, board):
    shell = mat("Shell (matte graphite)", (0.045, 0.047, 0.05), 0.62)
    for ob in (hood, tray):
        ob.data.materials.clear()      # booleans leave an empty slot 0 behind
        ob.data.materials.append(shell)
    for ob in (hood, tray):
        for p in ob.data.polygons:
            p.use_smooth = False
    pcb = mat("PCB", (0.02, 0.18, 0.55), 0.4)
    steel = mat("Steel", (0.75, 0.75, 0.75), 0.25, 1.0)
    alu = mat("Heatsink", (0.15, 0.15, 0.17), 0.35, 1.0)
    gold = mat("Brass", (0.8, 0.6, 0.25), 0.3, 1.0)
    for n, p in board.items():
        p.data.materials.clear()
        m = pcb if n in ("pcb", "bottom_parts", "m2_card") else alu if n == "heatsink" else gold if n.startswith("ant") else steel
        p.data.materials.append(m)

def render_all(hood, tray, board):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 96
    sc.cycles.use_denoising = True
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        sc.cycles.device = "GPU"
    except Exception as e:
        print("GPU not available, using CPU:", e)
    sc.render.resolution_x, sc.render.resolution_y = 1600, 1200
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    world = bpy.data.worlds.new("studio")
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.92, 0.92, 0.93, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
    # ground plane
    g = rbox("ground", -400, 400, -400, 400, OUT_BOTTOM - 0.5, OUT_BOTTOM, 1, seg=2)
    g.data.materials.append(mat("Ground", (0.85, 0.85, 0.86), 0.8))
    # lights
    def light(name, kind, loc, energy, size):
        L = bpy.data.lights.new(name, kind)
        L.energy = energy
        if kind == "AREA":
            L.size = size
        o = bpy.data.objects.new(name, L)
        o.location = loc
        o.rotation_euler = (Vector((27, 31, 0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        sc.collection.objects.link(o)
    light("key", "AREA", (180, 120, 200), 90000, 140)
    light("fill", "AREA", (-160, 60, 90), 25000, 160)
    light("rim", "AREA", (-60, -200, 120), 30000, 120)
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 70
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    center = Vector(((OUT_X0 + OUT_X1) / 2, (OUT_Y0 + OUT_Y1) / 2, (OUT_BOTTOM + OUT_TOP) / 2))
    os.makedirs(os.path.join(HERE, "renders"), exist_ok=True)
    def shot(fname, loc, show_board=False, explode=0.0, hide_hood=False):
        for p in board.values():
            p.hide_render = not show_board
        hood.location = (0, 0, explode)
        hood.hide_render = hide_hood
        cam.location = center + Vector(loc)
        cam.rotation_euler = (center + Vector((0, 0, explode / 3)) - cam.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = os.path.join(HERE, "renders", fname)
        bpy.ops.render.render(write_still=True)
    shot("01_front_three_quarter.png", (190, -120, 95))
    shot("02_back_three_quarter.png", (-170, 140, 110))
    shot("03_ports_front.png", (230, 0, 18))
    shot("04_exploded_with_board.png", (200, -150, 150), show_board=True, explode=45.0)
    hood.location = (0, 0, 0)

main()
