"""Brings the routed checkpoint (../routed.kicad_pcb) in line with the schematic, as KiCad's "Update PCB from
Schematic" would, without touching placement or copper.

  .../bin/python3 gen/sync.py

From the schematic's netlist: each footprint's value and fields (Datasheet, Note, LCSC, ...), its do-not-populate
and exclude-from-BOM flags, the single-pin "unconnected-(...)" nets KiCad gives unused pins, and net names (a net
that became local to one sheet gets the sheet path; its copper goes with it). MOUNT_CM3 (the CM3's
mounting outline, placed by gen/pcb.py) has no symbol: it is marked board-only.
"""
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from fab import KC, SCH  # noqa: E402
from finish import ROUTED  # noqa: E402

SKIP = {"Reference", "Value", "Footprint", "Description", "Sheetname", "Sheetfile"}


def main():
    xml = os.path.join(tempfile.mkdtemp(), "net.xml")
    subprocess.run([KC, "sch", "export", "netlist", "--format", "kicadxml", "-o", xml, SCH], check=True,
                   capture_output=True)
    root = ET.parse(xml).getroot()
    board = pcbnew.LoadBoard(ROUTED)
    fields = flags = nets = values = renamed = 0
    for c in root.iter("comp"):
        f = board.FindFootprintByReference(c.get("ref"))
        if f is None:
            continue
        props = {p.get("name"): p.get("value") for p in c.findall("property")}
        if f.GetValue() != c.findtext("value"):
            f.SetValue(c.findtext("value"))
            values += 1
        for fl in c.iter("field"):
            name, text = fl.get("name"), fl.text or ""
            if name in SKIP:
                continue
            if f.HasField(name) and f.GetFieldText(name) == text:
                continue
            new = not f.HasField(name)
            f.SetField(name, text)
            if new:
                f.GetField(name).SetVisible(False)
            fields += 1
        dnp, nobom = "dnp" in props, "exclude_from_bom" in props
        if f.IsDNP() != dnp or f.IsExcludedFromBOM() != nobom:
            f.SetDNP(dnp)
            f.SetExcludedFromBOM(nobom)
            flags += 1
    for n in root.iter("net"):
        name = n.get("name")
        if name.startswith("unconnected-("):
            continue
        pads = [board.FindFootprintByReference(x.get("ref")) for x in n.findall("node")]
        pads = [f.FindPadByNumber(x.get("pin")) for f, x in zip(pads, n.findall("node")) if f]
        old = {p.GetNetname() for p in pads if p is not None and p.GetNetCode() != 0}
        if len(old) != 1 or name in old or board.FindNet(name) is not None:
            continue
        oi = board.FindNet(old.pop())
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        for item in list(board.GetTracks()) + list(board.Zones()) + [p for f in board.GetFootprints() for p in f.Pads()]:
            if item.GetNetCode() == oi.GetNetCode():
                item.SetNet(ni)
        renamed += 1
    for n in root.iter("net"):
        name = n.get("name").replace("/", "{slash}")     # KiCad's escape in net names
        if not name.startswith("unconnected-("):
            continue
        for node in n.findall("node"):
            f = board.FindFootprintByReference(node.get("ref"))
            p = f.FindPadByNumber(node.get("pin")) if f else None
            if p is None or p.GetNetCode() != 0:
                continue
            ni = board.FindNet(name)
            if ni is None:
                ni = pcbnew.NETINFO_ITEM(board, name)
                board.Add(ni)
            p.SetNet(ni)
            nets += 1
    board.FindFootprintByReference("MOUNT_CM3").SetBoardOnly(True)
    pcbnew.SaveBoard(ROUTED, board)
    print(f"sync: {values} values, {fields} fields, {flags} DNP/BOM flags, {renamed} nets renamed, "
          f"{nets} unused pins given their unconnected-(...) nets")


if __name__ == "__main__":
    main()
