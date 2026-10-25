"""I/O level audit: every signal net on the CM3 connectors (J701 = J69, J702 = J68, J703 = J1), the RK3566 GPIO behind
each pin (gen/cm3_pinout.json, module revision V1.32) and its I/O bank voltage, against what this board puts on the
net.

  python3 checks/iolevels.py            (from kicad/; exports the netlist with kicad-cli)

Flags, per CM3 pin:
- OVERVOLTAGE: a pull-up, or a part whose I/O runs at a higher voltage than the pin's bank (RK628D, M.2 card).
- LED NEEDS MORE: the pin drives an LED through a resistor, and the bank voltage is below the LED's forward voltage.
- MODULE PULL-UP: the pin has a pull-up on the module (CM3 schematic p.7) and the board also uses the net for
  something that pull-up would upset (anything but an I2C bus).
- UNKNOWN BANK: no bank voltage known for the pin (it has to be checked by hand).
Exit status 1 if anything is flagged.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KC = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
PINOUT = json.load(open(os.path.join(ROOT, "gen", "cm3_pinout.json")))
REF = {"J701": ("J69", 0), "J702": ("J68", 100), "J703": ("J1", 0)}


def bank(g):
    """RK3566 I/O domain of a GPIO on the CM3 (Radxa CM3 V1.322 schematic pp.7-13, RK3568 datasheet table 2-8)."""
    m = re.match(r"GPIO(\d)_([A-D])(\d)", g)
    b, i = int(m.group(1)), "ABCD".index(m.group(2)) * 8 + int(m.group(3))
    if b == 0:
        if i < 8:
            return "PMUIO1", 3.3                 # p.7: "Operating Voltage=3.3V Only"
        if i < 27:
            return "PMUIO2", 1.8                 # p.7: supplied from VCCA1V8_PMU
        return "OSC (PMUIO0)", 1.8               # p.7: GPIO0_D3-D6, "1.8V Only"
    if b == 1 and i < 12:
        return "VCCIO1 = ACODEC (DT: 3.3 V)", 3.3   # off until software sets it; this board needs 3.3 V
    if b == 3 and i < 22:
        return "VCCIO5", 3.3                     # p.12: GPIO3_A1-C5, R43 0R to VCC_3V3
    if (b == 3) or (b == 4 and i < 18):
        return "VCCIO6 = GPIO_VREF", 3.3         # p.10: GPIO3_C6-D7, GPIO4_A0-C1; GPIO_VREF tied to SOM_3V3 here
    if b == 4:
        return "VCCIO7", 3.3                     # p.9: VCC_3V3
    return f"GPIO{b} (VCCIO2-4)", None


# pull-up rails and their highest voltage on this board
RAIL = {"3V3_IO": 3.3, "SOM_3V3": 3.3, "RK628D_3V3": 3.3, "SOM_1V8": 1.8, "5V_SYS": 5.0, "HDMIRX_5V": 5.0,
        "HDMITX_5V": 5.0, "VBUS_C": 9.0, "VBUS_SW": 9.0, "VIN": 17.0}
# other parts' logic level on the nets they share with the CM3
PART_V = {"U201": 3.3, "J501": 3.3}          # RK628D I/O (VCCIO1/2 = 3.3 V); M.2 card sideband (3.3 V)
MODULE_PULLUP = {"GPIO0_B5", "GPIO0_B6"}     # I2C2_M0: 2.2k to VCCA1V8_PMU on the module (p.7, R9/R10)
LED_VF = {"white": 2.6, "blue": 2.7, "red": 1.8, "green": 2.0}   # lowest forward voltage at about 1 mA
SKIP = ("unconnected", "SOM_", "5V", "USB_", "PCIE_TX", "PCIE_RX", "PCIE_REFCLK", "CSI_", "MDI", "HDMITX_D",
        "HDMITX_CLK", "GND")


def netlist():
    path = os.path.join(tempfile.mkdtemp(), "net.xml")
    subprocess.run([KC, "sch", "export", "netlist", "--format", "kicadxml", "-o", path,
                    os.path.join(ROOT, "relay.kicad_sch")], check=True, capture_output=True)
    root = ET.parse(path).getroot()
    value = {c.get("ref"): c.findtext("value") for c in root.iter("comp")}
    nets = {}
    for n in root.iter("net"):
        nets[n.get("name").split("/")[-1]] = [(x.get("ref"), x.get("pin")) for x in n.findall("node")]
    pin_net = {(r, p): nm for nm, nodes in nets.items() for r, p in nodes}
    return value, nets, pin_net


def main():
    value, nets, pin_net = netlist()
    flagged = 0
    for nm, nodes in sorted(nets.items()):
        if nm in RAIL or nm.startswith(SKIP):
            continue
        for ref, pin in [n for n in nodes if n[0] in REF]:
            conn, off = REF[ref]
            info = PINOUT[conn].get(str(int(pin) + off), {})
            g = re.search(r"GPIO\d_[A-D]\d", info.get("alt") or "")
            if not g:
                continue
            g = g.group(0)
            bk, bv = bank(g)
            if ref == "J702" and int(pin) + off in (199, 200):
                bk, bv = "HDMI TX DDC (5 V tolerant, CM3 datasheet 3.9)", 5.0
            flags, notes = [], []
            for r, p in nodes:
                if not r.startswith("R"):
                    continue
                other = pin_net.get((r, "2" if p == "1" else "1"))
                if other in RAIL:
                    notes.append(f"{r} {value[r]} to {other}")
                    if bv and RAIL[other] > bv + 0.3:
                        flags.append(f"OVERVOLTAGE (pull-up to {other})")
                # resistor into an LED anode
                for lr, lp in nets.get(other, []):
                    if lr.startswith("D") and lp in ("A", "2") and any(c in (value[lr] or "").lower() for c in LED_VF):
                        vf = next(v for c, v in LED_VF.items() if c in value[lr].lower())
                        notes.append(f"{r} into LED {lr} ({value[lr]})")
                        if bv and bv < vf + 0.3:
                            flags.append(f"LED NEEDS MORE ({lr} {value[lr]} needs about {vf} V)")
            for r, _ in nodes:
                if r in PART_V:
                    notes.append(f"{r} at {PART_V[r]} V")
                    if bv and PART_V[r] > bv + 0.3:
                        flags.append(f"OVERVOLTAGE ({r} drives {PART_V[r]} V)")
            if g in MODULE_PULLUP and not nm.startswith("I2C"):
                flags.append("MODULE PULL-UP (2.2k to 1.8 V on the CM3)")
            if bv is None:
                flags.append("UNKNOWN BANK")
            flagged += bool(flags)
            print(f"{'!!' if flags else '  '} {nm:20s} {ref}.{pin:3s} {g:8s} {bk:28s} {str(bv):4s} "
                  f"{'; '.join(notes)}{'   <<< ' + ', '.join(flags) if flags else ''}")
    print(f"\n{flagged} CM3 pins flagged")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
