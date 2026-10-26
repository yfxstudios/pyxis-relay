"""JLCPCB fabrication and assembly outputs from relay.kicad_pcb, into ../fab/.

  .../bin/python3 gen/fab.py

  fab/gerbers/           Gerbers (4 copper layers, masks, paste, silk, outline) and Excellon drill files
  fab/relay-gerbers.zip  the same, zipped for upload
  fab/relay-bom.csv      BOM in JLCPCB's columns (Comment, Designator, Footprint, LCSC Part #), DNP parts left out
  fab/relay-cpl.csv      pick-and-place in JLCPCB's columns (Designator, Mid X, Mid Y, Layer, Rotation)
  fab/relay-bom-handfit.csv  parts fitted by hand after assembly (HAND_FIT), in the BOM's columns, kept out of the
                         JLCPCB BOM and CPL

JLCPCB's assembly preview should be checked for part rotations: their library's zero orientation differs from
KiCad's for some packages.
"""
import csv
import json
import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KC = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
BOARD = os.path.join(ROOT, "relay.kicad_pcb")
SCH = os.path.join(ROOT, "relay.kicad_sch")
FAB = os.path.join(ROOT, "fab")
LAYERS = "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts"


# LCSC numbers for parts whose schematic symbol has none, by (value, footprint). Resistors and capacitors are
# JLCPCB basic parts where one exists (1 % resistors; capacitors rated at least the schematic voltage), picked with
# the jlcsearch API; the rest from JLCPCB's parts search (Oct 23).
LCSC_BY = {
    ("100R", "R_0402_1005Metric"): "C25076",           # 0402WGF1000TCE
    ("100k", "R_0402_1005Metric"): "C25741",           # 0402WGF1003TCE
    ("100nF", "C_0402_1005Metric"): "C307331",         # CL05B104KB54PNC
    ("10k", "R_0402_1005Metric"): "C25744",            # 0402WGF1002TCE
    ("10nF", "C_0402_1005Metric"): "C15195",           # CL05B103KB5NNNC
    ("10uF", "C_0805_2012Metric"): "C15850",           # CL21A106KAYNNNE
    ("10uF/10V", "C_0805_2012Metric"): "C15850",       # CL21A106KAYNNNE
    ("110k", "R_0402_1005Metric"): "C25745",           # 0402WGF1103TCE
    ("15k", "R_0402_1005Metric"): "C25756",            # 0402WGF1502TCE
    ("150R", "R_0402_1005Metric"): "C25082",           # 0402WGF1500TCE
    ("200k", "R_0402_1005Metric"): "C25764",           # 0402WGF2003TCE (SY8303 RFS)
    ("0R", "C_0402_1005Metric"): "C17168",             # 0402WGF0000TCE, 0R link on a capacitor footprint (C501/C502)
    ("18pF", "C_0402_1005Metric"): "C1549",            # 0402CG180J500NT
    ("1k", "R_0402_1005Metric"): "C11702",             # 0402WGF1001TCE
    ("1nF", "C_0402_1005Metric"): "C1523",             # 0402B102K500NT
    ("1uF", "C_0402_1005Metric"): "C52923",            # CL05A105KA5NQNC
    ("1uF/50V", "C_0805_2012Metric"): "C28323",        # CL21B105KBFNNNE
    ("2.2k", "R_0402_1005Metric"): "C25879",           # 0402WGF2201TCE
    ("210k", "R_0402_1005Metric"): "C58827",           # 0402WGF2103TCE
    ("22R", "R_0402_1005Metric"): "C25092",            # 0402WGF220JTCE
    ("22uF", "C_0805_2012Metric"): "C45783",           # CL21A226MAQNNNE
    ("22uF/10V", "C_0805_2012Metric"): "C45783",       # CL21A226MAQNNNE
    ("23.2k", "R_0402_1005Metric"): "C25873",          # 0402WGF2322TCE
    ("27k", "R_0402_1005Metric"): "C25771",            # 0402WGF2702TCE
    ("2k", "R_0402_1005Metric"): "C4109",              # 0402WGF2001TCE
    ("2k 1%", "R_0402_1005Metric"): "C4109",           # 0402WGF2001TCE
    ("33k", "R_0402_1005Metric"): "C25779",            # 0402WGF3302TCE
    ("39k", "R_0402_1005Metric"): "C25783",            # 0402WGF3902TCE
    ("4.02k 1%", "R_0402_1005Metric"): "C43251",       # 0402WGF4021TCE
    ("4.7k", "R_0402_1005Metric"): "C25900",           # 0402WGF4701TCE
    ("4.7uF/50V", "C_1206_3216Metric"): "C29823",      # 1206B475K500NT
    ("47k", "R_0402_1005Metric"): "C25792",            # 0402WGF4702TCE
    ("6.8k", "R_0402_1005Metric"): "C25917",           # 0402WGF6801TCE
    ("47uF/35V", "CP_Elec_6.3x7.7"): "C47023116",          # RVT35V47M6X8, 6.3 x 7.7 mm
    ("SS54", "D_SMA"): "C22452",                           # basic part
    ("SMBJ20CA", "D_SMB"): "C113992",
    ("MBR0530", "D_SOD-123"): "C82046",                    # MBR0530T1G
    ("white", "LED_0603_1608Metric"): "C2290",             # KT-0603W, basic
    ("blue", "LED_0603_1608Metric"): "C2288",              # KT-0603B
    ("red PWR", "LED_0603_1608Metric"): "C2286",           # KT-0603R, basic
    ("3A hold", "Fuse_1812_4532Metric"): "C48985875",      # 1812L300/30GR: 3 A hold, 30 V
    ("330R@100MHz", "L_0603_1608Metric"): "C275487",       # TDK MPZ1608S331ATA00
    ("MMBT3904", "SOT-23"): "C20526",                      # basic part
    ("USBLC6-2SC6", "SOT-23-6"): "C2687116",
    ("CH224A", "SSOP-10-1EP_3.9x4.9mm_P1mm_EP2.1x3.3mm"): "C42459160",
    ("AP22804AW5", "SOT-23-5"): "C3001659",                # AP22804AW5-7
    ("24MHz", "Crystal_SMD_3225-4Pin_3.2x2.5mm"): "C70590",  # X322524MOB4SI, 12 pF load (18 pF caps)
    ("6.8uH 3.6A", "L_Bourns_SRN6045TA"): "C2041457",      # Bourns SRN6045TA-6R8M, 3.6 A rms (low stock: check)
    ("2.2uH", "L_Bourns_SRN6045TA"): "C36500",             # Sunlord SWPA6045S2R2NT, same 6 x 6 mm pads (the
                                                            # MT version C83455 is delisted at LCSC)
    ("1.5uH", "L_Bourns_SRN6045TA"): "C96956",             # Sunlord SWPA6045S1R5NT, same 6 x 6 mm pads (MT
                                                            # version C98203 delisted)
    ("NP-F plate", "JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical"): "C131337",
    ("HDMI IN", "HDMI_A_Molex_208658-1001_Horizontal"): "C916313",   # Molex 2086581001
    ("HDMI OUT", "HDMI_A_Molex_208658-1001_Horizontal"): "C916313",
    ("M.2 E-key 2230", "TE_M.2_E_2x38-1MP_P0.5mm"): "C2977809",      # TE 2199230-4
    ("DEBUG UART 3V3", "PinHeader_1x03_P2.54mm_Vertical"): "C2937625",   # PZ254V-11-03P
    ("RESET", "SW_SPST_TL3342"): "C2886898",               # TL3342F160QG
    ("RECOVERY", "SW_SPST_TL3342"): "C2886898",
    ("DC 6-17V", "BarrelJack_Horizontal"): "C2961147",     # CUI PJ-002AH: 5 A (PJ-002A is 2.5 A), same layout; 2.0 mm pin
    ("RJ45 1000BASE-T magjack", "RJ45_Pulse_JK0654219NL_Horizontal"): "C3179417",  # Pulse JK0654219NL (no stock)
}
# not placed by the assembler: bare pads
NOT_PLACED = ("MountingHole", "TestPoint")
# fitted by hand after assembly (PRODUCTION.md): J301, the magjack, has no JLCPCB/LCSC stock (DigiKey/Mouser instead)
HAND_FIT = {"J301"}


NOTES = """Rev A fab notes (also in kicad/README.md)
- 4 layers, 1.6 mm, stackup JLCPCB JLC04161H-3313 (0.0994 mm 3313 prepreg under L1 and L4). Select it at ordering:
  the trace widths below are designed for it, and on the default 7628 stack the 100 ohm pairs come out at ~120 ohm.
- Differential pairs on L1/L4 (width/gap, mm): 100 ohm 0.10/0.10 (HDMI, CSI, Ethernet), 90 ohm 0.12/0.10 (USB),
  85 ohm 0.14/0.10 (PCIe).
- ENIG. Vias 0.15 mm drill minimum, epoxy-filled and capped (via-in-pad on several parts).
"""


def _check_stackup(gerb):
    """The Gerber job file must carry the 3313 stackup (gen/finish.py STACKUP), not KiCad's default 0.48 mm."""
    job = json.load(open(next(os.path.join(gerb, f) for f in os.listdir(gerb) if f.endswith(".gbrjob"))))
    diel = [round(m["Thickness"], 4) for m in job["MaterialStackup"] if m["Type"] == "Dielectric"]
    if diel != [0.0994, 1.265, 0.0994]:
        sys.exit(f"fab: the board's stackup is not JLC04161H-3313 (dielectrics {diel}): run gen/finish.py")
    open(os.path.join(FAB, "FAB_NOTES.txt"), "w").write(NOTES)


def run(*args):
    r = subprocess.run([KC, *args], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"kicad-cli {' '.join(args[:3])} failed:\n{r.stdout}\n{r.stderr}")


def main():
    gerb = os.path.join(FAB, "gerbers")
    shutil.rmtree(FAB, ignore_errors=True)
    os.makedirs(gerb)
    run("pcb", "export", "gerbers", "--layers", LAYERS, "--subtract-soldermask", "--check-zones", "-o", gerb + "/",
        BOARD)
    run("pcb", "export", "drill", "--format", "excellon", "--excellon-separate-th", "--generate-map", "--map-format",
        "pdf", "-o", gerb + "/", BOARD)
    _check_stackup(gerb)
    with zipfile.ZipFile(os.path.join(FAB, "relay-gerbers.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(gerb)):
            z.write(os.path.join(gerb, f), f)

    # BOM from the schematic (it carries the LCSC numbers), grouped, DNP left out
    raw = os.path.join(FAB, "bom-raw.csv")
    run("sch", "export", "bom", "--fields", "Value,Reference,Footprint,LCSC,${QUANTITY}",
        "--labels", "Comment,Designator,Footprint,LCSC Part #,Qty", "--group-by", "Value,Footprint,LCSC",
        "--ref-range-delimiter", "", "--exclude-dnp", "-o", raw, SCH)
    # one line per LCSC number: JLCPCB unselects every line of a part that appears on two lines (e.g. "22uF" and
    # "22uF/10V"), which would leave those parts unplaced
    lines, hand = {}, []
    with open(raw) as f:
        for row in csv.DictReader(f):
            fp = row["Footprint"].split(":")[-1]
            if fp.startswith(NOT_PLACED):
                continue
            lcsc = row["LCSC Part #"] or LCSC_BY.get((row["Comment"], fp), "")
            refs = row["Designator"].split(",")
            if set(refs) & HAND_FIT:
                hand.append([row["Comment"], ",".join(r for r in refs if r in HAND_FIT), fp, lcsc])
                row["Designator"] = ",".join(r for r in refs if r not in HAND_FIT)
                if not row["Designator"]:
                    continue
            key = lcsc or (row["Comment"], fp)
            if key in lines:
                lines[key][1] += "," + row["Designator"]
            else:
                lines[key] = [row["Comment"], row["Designator"], fp, lcsc]
    os.remove(raw)
    with open(os.path.join(FAB, "relay-bom.csv"), "w", newline="") as g:
        w = csv.writer(g)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for line in lines.values():
            line[1] = ",".join(sorted(line[1].split(","), key=lambda r: (r.rstrip("0123456789"), int(r[len(r.rstrip("0123456789")):] or 0))))
            w.writerow(line)
        missing = sum(not line[3] for line in lines.values())
    with open(os.path.join(FAB, "relay-bom-handfit.csv"), "w", newline="") as g:
        w = csv.writer(g)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        w.writerows(hand)

    # pick-and-place from the board
    pos = os.path.join(FAB, "pos-raw.csv")
    run("pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both", "--exclude-dnp", "-o", pos,
        BOARD)
    with open(pos) as f, open(os.path.join(FAB, "relay-cpl.csv"), "w", newline="") as g:
        w = csv.writer(g)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        n = 0
        for row in csv.DictReader(f):
            if row["Ref"].startswith(("H", "MOUNT", "TP")) or row["Ref"] in HAND_FIT:
                continue
            w.writerow([row["Ref"], f"{float(row['PosX']):.3f}mm", f"{float(row['PosY']):.3f}mm",
                        "Top" if row["Side"] == "top" else "Bottom", f"{float(row['Rot']):.1f}"])
            n += 1
    os.remove(pos)
    _centre_cm3(os.path.join(FAB, "relay-cpl.csv"))
    _offset_for_jlc(os.path.join(FAB, "relay-cpl.csv"))
    _rotate_for_jlc(os.path.join(FAB, "relay-cpl.csv"))
    print(f"fab/: gerbers + drill ({len(os.listdir(gerb))} files, zipped), BOM ({missing} lines without an LCSC "
          f"number), CPL ({n} parts); hand-fitted, not in either: {', '.join(sorted(HAND_FIT))}")


# Degrees (counter-clockwise, seen from the top) added to KiCad's rotation so JLCPCB's model of the part lines up
# with its footprint, found in JLCPCB's placement viewer: lead pattern against pads, and the model's pin-1 mark
# against the footprint's pin 1. Their models don't share KiCad's zero orientation.
JLC_ROT = {
    "Q101": 180, "Q201": 180, "Q202": 180, "Q203": 180,     # SOT-23: the model's two-lead side was on the 1-pad side
    "U101": -90, "U102": -90,                               # model leads crossed the pad rows
    "U103": 180, "U104": 180, "U105": 180, "U106": 180,     # pin 1 at the opposite corner
    "U201": -90,                                            # RK628D: ball A1 one corner round
    "J201": 90, "J401": 90,                                 # HDMI: model body turned across the shell tabs
    # Oct 25, checked part by part in JLCPCB's viewer (REVIEW_FABLE_2.md M4): the SOT-23-5 and USON-10 models sit
    # 90 deg across their pads. Diodes, LEDs, C102, Y201, J103 and J501 match as exported.
    "U401": -90,
    "D201": -90, "D202": -90, "D203": -90, "D401": -90, "D402": -90, "D403": -90,
    # Oct 25, viewer: the DC jack's model faced into the board (mouth away from the edge)
    "J101": 180,
}
# Board-mm offsets (x right, y down, from the footprint origin) to where JLCPCB's model must sit, measured in its
# viewer: their models' origins aren't KiCad's. J101 (origin at pin 1): the model sat 6.5 mm into the board at the
# origin and 4.8 mm off the edge, 3.2 mm west, at the F.Fab body centre.
JLC_OFFSET = {"J101": (2.3, 2.75)}


def _rotate_for_jlc(cpl):
    with open(cpl) as f:
        rows = list(csv.reader(f))
    for row in rows[1:]:
        if row[0] in JLC_ROT:
            rot = (float(row[4]) + JLC_ROT[row[0]]) % 360
            row[4] = f"{rot - 360 if rot > 180 else rot:.1f}"
    with open(cpl, "w", newline="") as f:
        csv.writer(f).writerows(rows)


def _centre_cm3(cpl):
    """The three CM3 receptacle footprints share the module's origin (its centre), so the position file would put
    all three in the same spot. JLCPCB places at the part's centre: use each one's pad centre, and turn the
    rotation so the part's long side follows its pad row (0 = long side along X)."""
    import pcbnew
    board = pcbnew.LoadBoard(BOARD)
    fix = {}
    for f in board.GetFootprints():
        if not str(f.GetFPID().GetLibItemName()).startswith("Radxa_CM3_"):
            continue
        bb = None
        for p in f.Pads():
            pb = p.GetBoundingBox()
            if bb is None:
                bb = pb
            else:
                bb.Merge(pb)
        c, o = bb.GetCenter(), f.GetPosition()
        fix[f.GetReference()] = (pcbnew.ToMM(c.x - o.x), pcbnew.ToMM(c.y - o.y),
                                 0.0 if bb.GetWidth() > bb.GetHeight() else 90.0)
    with open(cpl) as f:
        rows = list(csv.reader(f))
    for row in rows[1:]:
        if row[0] in fix:
            dx, dy, rot = fix[row[0]]
            row[1] = f"{float(row[1][:-2]) + dx:.3f}mm"
            row[2] = f"{float(row[2][:-2]) - dy:.3f}mm"          # the position file's Y points up
            row[4] = f"{rot:.1f}"
    with open(cpl, "w", newline="") as f:
        csv.writer(f).writerows(rows)


def _offset_for_jlc(cpl):
    """Moves the JLC_OFFSET parts by their offsets (the position file's Y points up)."""
    with open(cpl) as f:
        rows = list(csv.reader(f))
    for row in rows[1:]:
        if row[0] in JLC_OFFSET:
            dx, dy = JLC_OFFSET[row[0]]
            row[1] = f"{float(row[1][:-2]) + dx:.3f}mm"
            row[2] = f"{float(row[2][:-2]) - dy:.3f}mm"
    with open(cpl, "w", newline="") as f:
        csv.writer(f).writerows(rows)

if __name__ == "__main__":
    main()
