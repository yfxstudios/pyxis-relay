"""Project footprints (library "sdi", in ../sdi.pretty)."""
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



def write(outdir):
    lib = os.path.join(outdir, "sdi.pretty")
    os.makedirs(lib, exist_ok=True)
    name = "BGA-100_11.0x11.0mm_Layout10x10_P1.0mm"
    open(os.path.join(lib, name + ".kicad_mod"), "w").write(bga(
        name, 10, 10, 1.0, 11.0, 0.45,
        "Semtech GS2971A LBGA-100, 11 x 11 mm, 1.0 mm pitch, 0.5 mm balls (GS2971A datasheet 7.1). NSMD 0.45 mm "
        "pads: check against Semtech's land-pattern recommendation and JLCPCB's BGA rules."))
    open(os.path.join(outdir, "fp-lib-table"), "w").write(
        '(fp_lib_table\n\t(version 7)\n\t(lib (name "sdi")(type "KiCad")(uri "${KIPRJMOD}/sdi.pretty")'
        '(options "")(descr "Project footprints"))\n)\n')
