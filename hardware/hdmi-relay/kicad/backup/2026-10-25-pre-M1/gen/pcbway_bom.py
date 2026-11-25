"""PCBWay turnkey BOM from the JLCPCB BOM (run gen/fab.py first):

  python3 gen/pcbway_bom.py

PCBWay sources parts by manufacturer part number, so each line's LCSC number is looked up in gen/lcsc-mpn.json
(MPN and maker, taken from LCSC's part pages). The LCSC number stays in its own column as a cross-reference.
Writes fab/relay-bom-pcbway.csv; the position file (fab/relay-cpl.csv) is shared with JLCPCB.
"""
import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAB = os.path.join(ROOT, "fab")
THT = ("BarrelJack", "JST_PH", "RJ45", "PinHeader")


def main():
    mpn = json.load(open(os.path.join(ROOT, "gen", "lcsc-mpn.json")))      # not in fab/: gen/fab.py clears that
    with open(os.path.join(FAB, "relay-bom.csv")) as f, \
            open(os.path.join(FAB, "relay-bom-pcbway.csv"), "w", newline="") as g:
        w = csv.writer(g)
        w.writerow(["Line#", "Qty", "Designator", "MPN", "Manufacturer", "Description", "Package", "Type", "LCSC"])
        for n, row in enumerate(csv.DictReader(f), 1):
            refs = row["Designator"].split(",")
            part = mpn[row["LCSC Part #"]]
            w.writerow([n, len(refs), ",".join(refs), part["mpn"], part["manufacturer"],
                        f"{row['Comment']}: {part['description']}", row["Footprint"],
                        "THT" if row["Footprint"].startswith(THT) else "SMD", row["LCSC Part #"]])
    print(f"fab/relay-bom-pcbway.csv: {n} lines")


if __name__ == "__main__":
    main()
