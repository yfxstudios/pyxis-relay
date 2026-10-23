"""JLCPCB fabrication and assembly outputs from relay.kicad_pcb, into ../fab/.

  .../bin/python3 gen/fab.py

  fab/gerbers/           Gerbers (4 copper layers, masks, paste, silk, outline) and Excellon drill files
  fab/relay-gerbers.zip  the same, zipped for upload
  fab/relay-bom.csv      BOM in JLCPCB's columns (Comment, Designator, Footprint, LCSC Part #), DNP parts left out
  fab/relay-cpl.csv      pick-and-place in JLCPCB's columns (Designator, Mid X, Mid Y, Layer, Rotation)

JLCPCB's assembly preview should be checked for part rotations: their library's zero orientation differs from
KiCad's for some packages.
"""
import csv
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
    with zipfile.ZipFile(os.path.join(FAB, "relay-gerbers.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(gerb)):
            z.write(os.path.join(gerb, f), f)

    # BOM from the schematic (it carries the LCSC numbers), grouped, DNP left out
    raw = os.path.join(FAB, "bom-raw.csv")
    run("sch", "export", "bom", "--fields", "Value,Reference,Footprint,LCSC,${QUANTITY}",
        "--labels", "Comment,Designator,Footprint,LCSC Part #,Qty", "--group-by", "Value,Footprint,LCSC",
        "--ref-range-delimiter", "", "--exclude-dnp", "-o", raw, SCH)
    with open(raw) as f, open(os.path.join(FAB, "relay-bom.csv"), "w", newline="") as g:
        w = csv.writer(g)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        missing = 0
        for row in csv.DictReader(f):
            fp = row["Footprint"].split(":")[-1]
            w.writerow([row["Comment"], row["Designator"], fp, row["LCSC Part #"]])
            missing += not row["LCSC Part #"]
    os.remove(raw)

    # pick-and-place from the board
    pos = os.path.join(FAB, "pos-raw.csv")
    run("pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both", "--exclude-dnp", "-o", pos,
        BOARD)
    with open(pos) as f, open(os.path.join(FAB, "relay-cpl.csv"), "w", newline="") as g:
        w = csv.writer(g)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        n = 0
        for row in csv.DictReader(f):
            if row["Ref"].startswith(("H", "MOUNT")):
                continue
            w.writerow([row["Ref"], f"{float(row['PosX']):.3f}mm", f"{float(row['PosY']):.3f}mm",
                        "Top" if row["Side"] == "top" else "Bottom", f"{float(row['Rot']):.1f}"])
            n += 1
    os.remove(pos)
    print(f"fab/: gerbers + drill ({len(os.listdir(gerb))} files, zipped), BOM ({missing} lines without an LCSC "
          f"number), CPL ({n} parts)")


if __name__ == "__main__":
    main()
