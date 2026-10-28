"""Project footprints (library "sdi", in ../sdi.pretty)."""
import math
import os

from sexpr import dump, parse, q


def bga(name, rows, cols, pitch, body, pad, descr):
    """Ball grid: rows lettered A.. (no I, O, Q, S, X, Z), columns numbered from 1; A1 top-left."""
    letters = [c for c in "ABCDEFGHJKLMNPRTUVWY"][:rows]
    off_x, off_y = (cols - 1) * pitch / 2, (rows - 1) * pitch / 2
    h = body / 2
    items = [f'(footprint {q(name)} (version 20241229) (generator "sdi_gen") (layer "F.Cu") (descr {q(descr)}) '
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



# Add-on placement (DESIGN.md "Placement"): centre pin at board (116.6, 50.0), board edge 7.1 mm in front of it.
BNC_EDGE = 7.1


def _circle(r, n=16):
    return " ".join(f"(xy {round(r * math.cos(2 * math.pi * i / n), 3)} {round(r * math.sin(2 * math.pi * i / n), 3)})"
                    for i in range(n))


def bnc_samtec_bh1():
    """Samtec BNC7T-J-P-xx-RA-BH1 (true 75 ohm right-angle bulkhead jack), from Samtec's print rev J
    (suddendocs.samtec.com/prints/bnc7t-j-p-xx-ra-bh1-mkt.pdf): 4 x 2.90 mm holes on a 9.70 mm square, 1.30 mm centre
    pin hole in the middle; body 11.60 mm square, axis 11.30 mm above the board, shoulder 8.85 mm in front of the pin
    centre, tip 26.95 mm. Origin = centre pin, +X = mating direction (towards the case wall). Leg pads 3.8 mm (0.45 mm
    ring) so the rear pads clear the J301 socket's bottom-side pads; the board edge is BNC_EDGE in front of the pin, so
    the courtyard stops there; a 4 mm anti-pad keeps the inner planes and B.Cu away from the centre pin."""
    name = "BNC_Samtec_BNC7T-J-P-xx-RA-BH1_Horizontal"
    e = BNC_EDGE
    items = [f'(footprint {q(name)} (version 20241229) (generator "sdi_gen") (layer "F.Cu") '
             f'(descr "Samtec BNC7T-J-P-xx-RA-BH1, 75 ohm right-angle bulkhead PCB jack (print rev J)") (attr through_hole)',
             '(property "Reference" "REF**" (at 0 -8.5 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',
             f'(property "Value" {q(name)} (at 10 8.5 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))',
             '(fp_rect (start -5.8 -5.8) (end 5.8 5.8) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))',
             '(fp_rect (start 5.8 -6.95) (end 8.85 6.95) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))',
             '(fp_rect (start 8.85 -4.83) (end 26.95 4.83) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))',
             '(fp_line (start 8.85 -7.6) (end 8.85 7.6) (stroke (width 0.1) (type dash)) (layer "F.Fab"))',
             '(fp_text user "shoulder: seats on the lid boss panel" (at 9.6 -7.9 90) (layer "F.Fab") '
             '(effects (font (size 0.6 0.6) (thickness 0.08)) (justify left)))',
             f'(fp_line (start {e} -7.6) (end {e} 7.6) (stroke (width 0.1) (type dash)) (layer "F.Fab"))',
             f'(fp_text user "board edge" (at {e - 0.6} -7.9 90) (layer "F.Fab") '
             '(effects (font (size 0.6 0.6) (thickness 0.08)) (justify left)))',
             '(fp_line (start -5.92 -5.92) (end 5.92 -5.92) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))',
             '(fp_line (start -5.92 5.92) (end 5.92 5.92) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))',
             '(fp_line (start -5.92 -5.92) (end -5.92 5.92) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))',
             f'(fp_rect (start -6.3 -7.45) (end {e} 7.45) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))',
             '(pad "1" thru_hole circle (at 0 0) (size 2.0 2.0) (drill 1.3) (layers "*.Cu" "*.Mask"))']
    for x, y in ((-4.85, -4.85), (4.85, -4.85), (-4.85, 4.85), (4.85, 4.85)):
        items.append(f'(pad "2" thru_hole circle (at {x} {y}) (size 3.8 3.8) (drill 2.9) (layers "*.Cu" "*.Mask"))')
    items.append('(zone (net 0) (net_name "") (layers "In1.Cu" "In2.Cu" "B.Cu") (name "SDI pin anti-pad") '
                 '(hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) '
                 '(keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) '
                 '(footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) '
                 f'(polygon (pts {_circle(2.0)})))')
    items.append(")")
    return name, dump(parse(" ".join(items))) + "\n"


def write(outdir):
    lib = os.path.join(outdir, "sdi.pretty")
    os.makedirs(lib, exist_ok=True)
    name = "BGA-100_11.0x11.0mm_Layout10x10_P1.0mm"
    open(os.path.join(lib, name + ".kicad_mod"), "w").write(bga(
        name, 10, 10, 1.0, 11.0, 0.45,
        "Semtech GS2971A LBGA-100, 11 x 11 mm, 1.0 mm pitch, 0.5 mm balls (GS2971A datasheet 7.1). NSMD 0.45 mm "
        "pads: check against Semtech's land-pattern recommendation and JLCPCB's BGA rules."))
    name, text = bnc_samtec_bh1()
    open(os.path.join(lib, name + ".kicad_mod"), "w").write(text)
    open(os.path.join(outdir, "fp-lib-table"), "w").write(
        '(fp_lib_table\n\t(version 7)\n\t(lib (name "sdi")(type "KiCad")(uri "${KIPRJMOD}/sdi.pretty")'
        '(options "")(descr "Project footprints"))\n)\n')
