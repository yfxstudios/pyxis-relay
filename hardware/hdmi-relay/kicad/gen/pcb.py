"""Creates the rev A board (../relay.kicad_pcb) from the schematic netlist: outline, stackup, net classes and an
initial placement by floorplan. Routing is done afterwards in KiCad.

Run with KiCad's bundled Python (it has the pcbnew module):
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 gen/pcb.py

It rebuilds the board from scratch, so run it before routing starts; after that, use KiCad's "Update PCB from
schematic" instead.
"""
import os
import re
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from sexpr import find, find_all, parse  # noqa: E402

FP_LIBS = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
OUT = os.path.join(ROOT, "relay.kicad_pcb")

# Board: 120 x 100 mm, origin at the top-left corner; y = 0 is the front panel, y = 100 the back panel.
W, H = 120.0, 100.0
O = (30.0, 30.0)  # page offset so everything sits on the drawing sheet

# Net classes. Widths are first estimates for JLCPCB's JLC04161H-3313 stackup (L1 over L2, 0.0994 mm 3313 prepreg,
# Er 4.1), from the IPC-2141 microstrip formulas. Confirm each with JLCPCB's impedance calculator before ordering.
NETCLASSES = {
    #             track  clear  via_d  via_drill  dp_width  dp_gap   nets (regex)
    "DIFF_100R": (0.10, 0.10, 0.45, 0.25, 0.10, 0.10,
                  r"^(HDMIRX|HDMITX)_(D[0-2]|CLK)_[PN]$|^CSI_(D[0-3]|CLK)_[PN]$|^MDI[0-3]_[PN]$"),
    "USB_90R":   (0.12, 0.10, 0.45, 0.25, 0.12, 0.10, r"^USB_.*_D[PM](_C)?$"),
    "PCIE_85R":  (0.14, 0.10, 0.45, 0.25, 0.14, 0.10, r"^PCIE_(TX|RX|REFCLK)_[PN]$|^M2_PER_[PN]$"),
    "POWER":     (0.50, 0.127, 0.60, 0.30, 0.20, 0.20,
                  r"^(VIN|VIN_RAW|VDC|VNPF|VBUS_C|VBUS_SW|5V_SYS|5V_SOM|3V3_IO|1V1_628|RK628D_3V3|AVDD_.*|"
                  r"HDMITX_5V|HDMIRX_5V|SOM_3V3|SOM_1V8|1V0_PHY|LX_.*|SW_.*)$"),
}
DEFAULT = (0.127, 0.10, 0.45, 0.25)


def mm(x, y):
    return pcbnew.VECTOR2I_MM(O[0] + x, O[1] + y)


def netlist():
    t = parse(open(os.path.join(ROOT, "build.net")).read())
    comps = {}
    for c in find_all(find(t, "components"), "comp"):
        ref = find(c, "ref")[1]
        comps[ref] = dict(value=find(c, "value")[1], footprint=(find(c, "footprint") or [None, ""])[1])
    nets = {}
    for n in find_all(find(t, "nets"), "net"):
        name = find(n, "name")[1]
        for node in find_all(n, "node"):
            nets[(find(node, "ref")[1], find(node, "pin")[1])] = name
    return comps, nets


def load_fp(lib_id):
    lib, name = lib_id.split(":", 1)
    path = os.path.join(ROOT, "relay.pretty") if lib == "relay" else os.path.join(FP_LIBS, lib + ".pretty")
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        raise SystemExit(f"footprint not found: {lib_id}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


# ------------------------------------------------------------------ floorplan
# Fixed positions (x, y, rotation, back side?) for the parts that set the layout. Everything else is packed into its
# sheet's region, below. See ../REV_A_SPEC.md section 6 and the placement notes in ../kicad/README.md.
CM3 = (66.0, 50.0, -90)  # module frame origin; -90 puts J68 (CSI, HDMI TX, PCIe) toward the front
FIXED = {
    "J701": CM3, "J702": CM3, "J703": CM3, "MOUNT_CM3": CM3,
    "J201": (24.0, 7.0, 90),      # HDMI IN, front panel (opening toward y = 0)
    "J401": (79.0, 7.0, 90),      # HDMI OUT, front panel
    "U201": (44.0, 21.0, 0),      # RK628D, between HDMI IN and the CM3's CSI pins
    "J501": (16.0, 27.0, 0),      # M.2 socket; the 2230 card lies over x 5..27, y 30..61
    "J301": (104.0, 79.0, -90),   # RJ45, back panel (the MDI pins are on J69, toward the back)
    "J103": (16.0, 95.0, 180),    # USB-C, back panel
    "J101": (42.0, 92.0, -90),    # locking DC jack, back panel
    "J102": (58.0, 95.0, 0),      # NP-F plate lead
    "J602": (104.0, 31.0, 0),     # SDI add-on header (not fitted), right of the module
    "J601": (110.0, 4.0, 0),      # debug UART
    "H601": (4.0, 4.0, 0), "H602": (116.0, 36.0, 0), "H603": (4.0, 96.0, 0), "H604": (116.0, 68.0, 0),
}
# Regions (x0, y0, x1, y1) where each sheet's remaining parts are packed, keyed by the reference's hundreds digit.
# A sheet can have several rectangles; they fill in order.
REGIONS = {
    1: [(2.0, 63.0, 37.0, 86.0), (49.0, 73.0, 79.0, 81.0), (64.0, 86.0, 86.0, 98.0)],  # power
    2: [(33.0, 1.0, 62.0, 13.5), (49.0, 14.0, 62.0, 29.0), (33.0, 26.0, 49.0, 29.0)],  # around the RK628D
    3: [(90.0, 70.0, 118.0, 75.0)],                           # Ethernet centre-tap caps
    4: [(64.0, 17.5, 98.0, 28.0)],                            # HDMI out
    5: [(2.0, 14.0, 14.0, 23.0)],                             # M.2 support
    6: [(96.0, 11.0, 118.0, 30.0)],                           # buttons, LEDs
    7: [(40.0, 70.5, 92.0, 73.0), (95.0, 76.0, 100.0, 77.0)], # module support
}


def pack(board, fps, regions):
    """Place footprints left to right, top to bottom inside the regions, using each courtyard for spacing."""
    regions = list(regions)
    x0, y0, x1, y1 = regions.pop(0)
    x, y, row_h = x0, y0, 0.0
    for fp in fps:
        bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox() if fp.GetCourtyard(pcbnew.F_CrtYd).OutlineCount() else fp.GetBoundingBox()
        w = pcbnew.ToMM(bb.GetWidth()) + 0.4
        h = pcbnew.ToMM(bb.GetHeight()) + 0.4
        if x + w > x1 and x > x0:
            x, y, row_h = x0, y + row_h, 0.0
        if y + h > y1 and regions:
            x0, y0, x1, y1 = regions.pop(0)
            x, y, row_h = x0, y0, 0.0
        fp.SetPosition(mm(x + w / 2, y + h / 2))
        x += w
        row_h = max(row_h, h)
    return y + row_h <= y1  # False: region overflowed


def write_project_rules(netnames):
    """KiCad keeps net classes and board constraints in the project file: write them there."""
    import json
    pro_path = os.path.join(ROOT, "relay.kicad_pro")
    pro = json.load(open(pro_path)) if os.path.exists(pro_path) else {}
    pro.setdefault("meta", {"filename": "relay.kicad_pro", "version": 3})

    def cls(name, tw, cl, vd, vdr, dpw=0.2, dpg=0.2):
        return {"name": name, "track_width": tw, "clearance": cl, "via_diameter": vd, "via_drill": vdr,
                "diff_pair_width": dpw, "diff_pair_gap": dpg, "diff_pair_via_gap": 0.25,
                "microvia_diameter": 0.3, "microvia_drill": 0.1, "wire_width": 6, "bus_width": 12,
                "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)",
                "priority": 2147483647}
    classes = [cls("Default", *DEFAULT)]
    patterns = []
    for i, (name, (tw, cl, vd, vdr, dpw, dpg, pattern)) in enumerate(NETCLASSES.items()):
        c = cls(name, tw, cl, vd, vdr, dpw, dpg)
        c["priority"] = i
        classes.append(c)
        patterns += [{"netclass": name, "pattern": n} for n in netnames if re.search(pattern, n)]
    pro["net_settings"] = {"classes": classes, "meta": {"version": 4}, "netclass_assignments": None,
                           "netclass_patterns": patterns}
    # JLCPCB 4-layer capabilities (Oct 2026 public limits; confirm on their site before ordering)
    board = pro.setdefault("board", {})
    rules = board.setdefault("design_settings", {}).setdefault("rules", {})
    rules.update({"min_clearance": 0.09, "min_track_width": 0.09, "min_via_diameter": 0.3, "min_through_hole_diameter": 0.15,
                  "min_via_annular_width": 0.075, "min_copper_edge_clearance": 0.3, "min_hole_clearance": 0.2,
                  "min_hole_to_hole": 0.25, "min_silk_clearance": 0.0})
    json.dump(pro, open(pro_path, "w"), indent=2)


def main():
    comps, nets = netlist()
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(4)

    # net classes
    ns = ds.m_NetSettings
    d = ns.GetDefaultNetclass()
    d.SetTrackWidth(pcbnew.FromMM(DEFAULT[0])); d.SetClearance(pcbnew.FromMM(DEFAULT[1]))
    d.SetViaDiameter(pcbnew.FromMM(DEFAULT[2])); d.SetViaDrill(pcbnew.FromMM(DEFAULT[3]))
    ns.SetDefaultNetclass(d)
    for name, (tw, cl, vd, vdr, dpw, dpg, pattern) in NETCLASSES.items():
        nc = pcbnew.NETCLASS(name)
        nc.SetTrackWidth(pcbnew.FromMM(tw)); nc.SetClearance(pcbnew.FromMM(cl))
        nc.SetViaDiameter(pcbnew.FromMM(vd)); nc.SetViaDrill(pcbnew.FromMM(vdr))
        nc.SetDiffPairWidth(pcbnew.FromMM(dpw)); nc.SetDiffPairGap(pcbnew.FromMM(dpg))
        ns.SetNetclass(name, nc)

    # nets
    netinfo = {}
    for name in sorted(set(nets.values())):
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        netinfo[name] = ni
    for name, (*_, pattern) in NETCLASSES.items():
        for net in netinfo:
            if re.search(pattern, net):
                ns.SetNetclassPatternAssignment(net, name)

    # footprints
    placed = {}
    for ref, c in sorted(comps.items()):
        if not c["footprint"]:
            raise SystemExit(f"{ref} has no footprint")
        fp = load_fp(c["footprint"])
        fp.SetReference(ref)
        fp.SetValue(c["value"])
        for pad in fp.Pads():
            key = (ref, pad.GetNumber())
            if key in nets:
                pad.SetNet(netinfo[nets[key]])
        board.Add(fp)
        placed[ref] = fp
    mount = load_fp("relay:Radxa_CM3_Mount")
    mount.SetReference("MOUNT_CM3")
    mount.SetValue("Radxa CM3")
    for pad in mount.Pads():
        pad.SetNet(netinfo["GND"])
    board.Add(mount)
    placed["MOUNT_CM3"] = mount

    # board outline
    rect = pcbnew.PCB_SHAPE(board)
    rect.SetShape(pcbnew.SHAPE_T_RECT)
    rect.SetLayer(pcbnew.Edge_Cuts)
    rect.SetStart(mm(0, 0)); rect.SetEnd(mm(W, H))
    rect.SetWidth(pcbnew.FromMM(0.1))
    board.Add(rect)

    # placement
    for ref, (x, y, rot) in FIXED.items():
        if ref in placed:
            placed[ref].SetPosition(mm(x, y))
            placed[ref].SetOrientationDegrees(rot)
    groups = {}
    for ref, fp in placed.items():
        if ref in FIXED:
            continue
        num = re.search(r"\d+", ref)
        groups.setdefault(int(num.group()) // 100 if num else 0, []).append(fp)
    overflow = []
    for g, fps in sorted(groups.items()):
        # big parts first so the small ones fill the gaps after them
        fps.sort(key=lambda f: -f.GetBoundingBox().GetArea())
        if not pack(board, fps, REGIONS[g]):
            overflow.append(g)

    pcbnew.SaveBoard(OUT, board)
    write_project_rules(sorted(netinfo))
    print(f"wrote {OUT}: {len(placed)} footprints, {len(netinfo)} nets; regions overflowed: {overflow or 'none'}")


main()
