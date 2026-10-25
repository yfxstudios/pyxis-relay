"""I/O level audit: every signal net on the CM3 connectors (J701 = J69, J702 = J68, J703 = J1), the RK3566 GPIO behind
each pin (Radxa CM3 v1.3 pinout) and its I/O bank voltage, against the voltage this board puts on the net (pull-up
rails, and the I/O supply of other ICs on the net)."""
import json, re, sys, openpyxl
d = json.load(open(sys.argv[1]))
wb = openpyxl.load_workbook(sys.argv[2], read_only=True, data_only=True)
conn, pins = None, {}
for r in wb.worksheets[0].iter_rows(values_only=True):
    if r[0] and isinstance(r[0], str) and "Connector" in r[0]:
        conn = re.search(r"\((J\d+)\)", r[0]).group(1); continue
    if isinstance(r[0], (int, float)) and conn:
        pins[(conn, int(r[0]))] = [str(x) for x in r[1:] if x]
REF = {"J701": "J69", "J702": "J68", "J703": "J1"}
# RK3566 banks on the CM3 (RK3568 datasheet table 2.8; CM3 datasheet 3.1/3.9; CM3 schematic)
def bank(g):
    m = re.match(r"GPIO(\d)_([A-D])(\d)", g); b, l, n = int(m.group(1)), m.group(2), int(m.group(3))
    i = "ABCD".index(l) * 8 + n
    if b == 1 and i < 12:
        return ("VCCIO1=ACODEC", 3.3)        # CM3 datasheet: the PCIe M2 group (GPIO1_B0-B2) runs at 3.3 V
    if b == 0:
        return ("PMUIO1", 3.3) if i < 8 else (("PMUIO2", 1.8) if i < 27 else ("PMUIO1/OSC", 3.3))
    if b == 4 and i >= 18:
        return ("VCCIO7", 3.3)
    if (b == 4) or (b == 3 and i >= 18):
        return ("VCCIO6=GPIO_VREF", 3.3)
    return (f"GPIO{b} bank", None)
RAIL = {"3V3_IO": 3.3, "SOM_3V3": 3.3, "RK628D_3V3": 3.3, "SOM_1V8": 1.8, "5V_SYS": 5.0, "HDMIRX_5V": 5.0, "HDMITX_5V": 5.0}
val = {c["reference"]: c["value"] for c in d["components"]}
rnets = {}
for n, v in d["nets"].items():
    for p in v["pins"]:
        rnets.setdefault(p["component"], {})[p["pin_number"]] = n.split("/")[-1]
bad = []
for n, v in d["nets"].items():
    nm = n.split("/")[-1]
    if nm in RAIL or nm == "GND" or nm.startswith(("unconnected", "SOM_", "5V", "USB_", "PCIE_TX", "PCIE_RX", "PCIE_REFCLK", "CSI_", "MDI", "HDMITX_D", "HDMITX_CLK")):
        continue
    for j in [p for p in v["pins"] if p["component"] in REF]:
        pn = int(j["pin_number"]) + (100 if j["component"] == "J702" and int(j["pin_number"]) <= 100 else 0)  # J68 is 101-200
        f = pins.get((REF[j["component"]], pn), [])
        g = next((x for x in f if re.match(r"GPIO\d_[A-D]\d", x)), None)
        if not g:
            continue
        bk, bv = bank(g)
        if j["component"] == "J702" and pn in (199, 200):
            bk, bv = "HDMITX DDC (5 V tolerant, CM3 datasheet 3.9)", 5.0
        # what this board puts on the net: pull-up resistors to a rail
        ups = []
        for p in v["pins"]:
            if p["component"].startswith("R"):
                other = [x for k, x in rnets[p["component"]].items() if k != p["pin_number"]]
                if other and other[0] in RAIL:
                    ups.append((p["component"], val[p["component"]], other[0]))
        drv = sorted({p["component"] for p in v["pins"] if p["component"].startswith(("U", "Q", "D")) and p["component"] not in REF})
        hi = max([RAIL[u[2]] for u in ups] + ([3.3] if "U201" in drv else []), default=None)
        flag = "OVERVOLTAGE" if (bv and hi and hi > bv + 0.3) else ""
        row = (nm, f"{j['component']}.{j['pin_number']}", g, bk, bv, ups, drv, flag)
        if flag or bv is None:
            bad.append(row)
        print(("!! " if flag else "   ") + f"{nm:22s} {row[1]:9s} {g:9s} {bk:17s} {str(bv):4s} pull-ups {ups} parts {drv}")
