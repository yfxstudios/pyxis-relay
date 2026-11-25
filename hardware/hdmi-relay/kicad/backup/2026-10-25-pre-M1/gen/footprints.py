"""Project footprints (library "relay", in ../relay.pretty)."""
import json
import os

from sexpr import dump, parse, q


def bga(name, rows, cols, pitch, body, pad, descr):
    """Ball grid: rows lettered A.. (no I, O, Q, S, X, Z), columns numbered from 1; A1 top-left."""
    letters = [c for c in "ABCDEFGHJKLMNPRTUVWY"][:rows]
    off_x, off_y = (cols - 1) * pitch / 2, (rows - 1) * pitch / 2
    h = body / 2
    items = [f'(footprint {q(name)} (version 20241229) (generator "relay_gen") (layer "F.Cu") (descr {q(descr)}) '
             f'(attr smd)',
             f'(property "Reference" "REF**" (at 0 {-h - 1.2} 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',
             f'(property "Value" {q(name)} (at 0 {h + 1.2} 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))',
             f'(fp_rect (start {-h} {-h}) (end {h} {h}) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))',
             f'(fp_rect (start {-h - 0.11} {-h - 0.11}) (end {h + 0.11} {h + 0.11}) (stroke (width 0.12) (type solid)) (fill no) (layer "F.SilkS"))',
             f'(fp_circle (center {-h - 0.6} {-h - 0.6}) (end {-h - 0.45} {-h - 0.6}) (stroke (width 0.3) (type solid)) (fill yes) (layer "F.SilkS"))',
             f'(fp_rect (start {-h - 0.5} {-h - 0.5}) (end {h + 0.5} {h + 0.5}) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))']
    for r, letter in enumerate(letters):
        for c in range(cols):
            x, y = round(-off_x + c * pitch, 4), round(-off_y + r * pitch, 4)
            items.append(f'(pad {q(f"{letter}{c + 1}")} smd circle (at {x} {y}) (size {pad} {pad}) '
                         f'(layers "F.Cu" "F.Paste" "F.Mask"))')
    items.append(")")
    return dump(parse(" ".join(items))) + "\n"


def _fp(name, descr, items, attr="smd"):
    return dump(parse(f'(footprint {q(name)} (version 20241229) (generator "relay_gen") (layer "F.Cu") '
                      f'(descr {q(descr)}) (attr {attr}) ' + " ".join(items) + ")")) + "\n"


def _text(ref_y, value, val_y):
    return [f'(property "Reference" "REF**" (at 0 {ref_y} 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',
            f'(property "Value" {q(value)} (at 0 {val_y} 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))']


def cm3_footprints():
    """The three Radxa CM3 receptacles and the module's mounting holes, all in one module frame (origin = Radxa's
    U33 origin), copied from Radxa's own IO-board layout (cm3_footprint.json). Placing all four at the same board
    position and rotation reproduces Radxa's proven connector spacing exactly."""
    g = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cm3_footprint.json")))
    w, l = g["pad"]["w"], g["pad"]["l"]
    out = {}
    for conn in ("J69", "J68", "J1"):
        pads = g[conn]
        vertical = conn == "J1"          # J1 sits rotated 270 deg: its fingers run along y
        sx, sy = (w, l) if vertical else (l, w)
        items = _text(0, f"Radxa CM3 {conn}", 0)
        for n, (x, y) in sorted(pads.items(), key=lambda t: int(t[0])):
            items.append(f'(pad {q(n)} smd rect (at {x} {y}) (size {sx} {sy}) (layers "F.Cu" "F.Paste" "F.Mask"))')
        xs = [p[0] for p in pads.values()]
        ys = [p[1] for p in pads.values()]
        x0, x1 = min(xs) - (sx / 2 + 0.6), max(xs) + (sx / 2 + 0.6)
        y0, y1 = min(ys) - (sy / 2 + 0.6), max(ys) + (sy / 2 + 0.6)
        items.append(f'(fp_rect (start {x0:.3f} {y0:.3f}) (end {x1:.3f} {y1:.3f}) (stroke (width 0.12) (type solid)) (fill no) (layer "F.SilkS"))')
        items.append(f'(fp_rect (start {x0 - 0.2:.3f} {y0 - 0.2:.3f}) (end {x1 + 0.2:.3f} {y1 + 0.2:.3f}) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))')
        p1 = pads["1"]
        items.append(f'(fp_circle (center {p1[0] + (0 if vertical else 1.2)} {p1[1] + (1.2 if vertical else 0)}) (end {p1[0] + (0.15 if vertical else 1.35)} {p1[1] + (1.2 if vertical else 0)}) (stroke (width 0.3) (type solid)) (fill yes) (layer "F.SilkS"))')
        out[f"Radxa_CM3_{conn}"] = _fp(f"Radxa_CM3_{conn}",
            f"Radxa CM3 {conn}: Hirose DF40C-100DS-0.4V(51) receptacle, land pattern and position copied from Radxa's "
            f"CM3 IO board. Place at the same origin and rotation as the other Radxa_CM3_* footprints.", items)
    # module outline (40 x 55 mm) and the four M2.5 mounting holes (plated, 2.6 mm drill, 6 mm pad)
    items = _text(-29.5, "Radxa CM3 module", 29.5)
    for i, (x, y) in enumerate(g["holes"]):
        items.append(f'(pad "MH{i + 1}" thru_hole circle (at {x} {y}) (size {g["hole"]["pad"]} {g["hole"]["pad"]}) '
                     f'(drill {g["hole"]["drill"]}) (layers "*.Cu" "*.Mask"))')
    items.append('(fp_rect (start -20 -27.5) (end 20 27.5) (stroke (width 0.12) (type solid)) (fill no) (layer "F.SilkS"))')
    items.append('(fp_rect (start -20 -27.5) (end 20 27.5) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))')
    out["Radxa_CM3_Mount"] = _fp("Radxa_CM3_Mount",
        "Radxa CM3 module outline (40 x 55 mm) and its four M2.5 mounting holes, positions from Radxa's CM3 IO board.",
        items, attr="through_hole")
    return out


def m2_socket_placeholder():
    """PLACEHOLDER land pattern for an M.2 E-key socket: 75 positions at 0.5 mm per row, odd pins on one row and
    even on the other. Replace with the chosen socket's drawing (e.g. a 4.2 mm-high E-key part from LCSC) before
    any board is ordered."""
    items = _text(-4, "M.2 E-key (PLACEHOLDER pads)", 4)
    for n in range(1, 76):
        if 24 <= n <= 31:          # E key: no contacts
            continue
        x = round((n - 38) * 0.25, 3)
        y = -0.9 if n % 2 else 0.9
        items.append(f'(pad {q(str(n))} smd rect (at {x} {y}) (size 0.3 1.0) (layers "F.Cu" "F.Paste" "F.Mask"))')
    items.append('(fp_rect (start -11 -3) (end 11 3) (stroke (width 0.12) (type solid)) (fill no) (layer "F.SilkS"))')
    items.append('(fp_rect (start -11 -3) (end 11 34) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))')
    items.append('(fp_rect (start -11 3) (end 11 33) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))')
    items.append('(fp_text user "2230 card area" (at 0 18 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))')
    return {"M.2_E-key_Socket_PLACEHOLDER": _fp("M.2_E-key_Socket_PLACEHOLDER",
            "PLACEHOLDER M.2 E-key socket with a 22 x 30 mm card area. Not a real land pattern.", items)}


def write(outdir):
    lib = os.path.join(outdir, "relay.pretty")
    os.makedirs(lib, exist_ok=True)
    name = "BGA-144_8.0x8.0mm_Layout12x12_P0.65mm"
    open(os.path.join(lib, name + ".kicad_mod"), "w").write(bga(
        name, 12, 12, 0.65, 8.0, 0.275,
        "RK628D WBBGA-144, 8x8 mm, 0.65 mm pitch, 0.3 mm balls (RK628D datasheet 2.4). NSMD 0.275 mm pads: "
        "check against the datasheet land pattern and JLCPCB's BGA rules before ordering."))
    for name, text in {**cm3_footprints(), **m2_socket_placeholder()}.items():
        open(os.path.join(lib, name + ".kicad_mod"), "w").write(text)
    open(os.path.join(outdir, "fp-lib-table"), "w").write(
        '(fp_lib_table\n\t(version 7)\n\t(lib (name "relay")(type "KiCad")(uri "${KIPRJMOD}/relay.pretty")'
        '(options "")(descr "Project footprints"))\n)\n')
