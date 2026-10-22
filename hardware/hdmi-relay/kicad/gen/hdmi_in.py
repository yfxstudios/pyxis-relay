"""Sheet: HDMI input through the RK628D (REV_A_SPEC.md section 4).

Copied from the DshanPi-A1 V1.1 schematic, pages 31-32 (datasheets/DshanPi-A1-RK3576-SCH_V1.1.pdf), which ships an
RK628D feeding a Rockchip CSI receiver. Ball numbers come from the RK628D datasheet V1.0, tables 2-2 and 2-3.
"""
from parts import C0402, C0805, R0402, cap, resistor
from sch import box_symbol

P, I, O, B, PW = "passive", "input", "output", "bidirectional", "power_in"

GND_BALLS = ["A1", "A12", "C4", "C6", "D3", "D6", "E5", "E6", "E7", "F4", "F5", "F6", "F7", "G3", "G4", "G5", "G6",
             "G7", "G8", "H6", "H10", "K5", "K6", "K7", "K10", "M1", "M12", "L10", "M11"]

LEFT = [
    ("L12", "HDMIRX_CLKP", I), ("L11", "HDMIRX_CLKN", I), ("K12", "HDMIRX_D0P", I), ("K11", "HDMIRX_D0N", I),
    ("J12", "HDMIRX_D1P", I), ("J11", "HDMIRX_D1N", I), ("H12", "HDMIRX_D2P", I), ("H11", "HDMIRX_D2N", I),
    None,
    ("K8", "HDMIRX_HPD", O), ("L8", "HDMIRX_SCL", B), ("M8", "HDMIRX_SDA", B), ("K9", "HDMIRX_CEC", B),
    ("G9", "HDMIRX_EXTR", P),
    None,
    ("M9", "OSC_IN", I), ("L9", "OSC_OUT", O), ("H4", "RESETN", I), ("D7", "TEST", I),
    ("C7", "I2C_ADDR(GPIO3_B3)", I), ("L3", "I2C_SCL", B), ("K3", "I2C_SDA", B), ("J3", "INT(GPIO3_B4)", O),
    None,
    ("J2", "I2S_SCK", O), ("J1", "I2S_LRCK", O), ("K2", "I2S_D0", O), ("H3", "I2S_D1", O), ("H2", "I2S_D2", O),
    ("H1", "I2S_D3", O), ("H7", "TEST_CLKO/I2S_MCLK", O), ("H8", "GPIO1_A1", B),
    None,
    ("L2", "HDMITX_HPD", B), ("K1", "HDMITX_SDA", B), ("L1", "HDMITX_SCL", B), ("M2", "HDMITX_CEC", B),
    ("M4", "HDMITX_CLKP", O), ("L4", "HDMITX_CLKN", O), ("M5", "HDMITX_D0P", O), ("L5", "HDMITX_D0N", O),
    ("M6", "HDMITX_D1P", O), ("L6", "HDMITX_D1N", O), ("M7", "HDMITX_D2P", O), ("L7", "HDMITX_D2N", O),
    ("M3", "HDMITX_EXTR", P),
]
# Port0 of the TX block carries MIPI CSI-2 (DshanPi page 31 table): TX0=D0, TX1=D1, TX2=CLK, TX3=D2, TX4=D3
RIGHT = [
    ("G2", "TX0P/CSI_D0P", O), ("G1", "TX0N/CSI_D0N", O), ("F2", "TX1P/CSI_D1P", O), ("F1", "TX1N/CSI_D1N", O),
    ("E2", "TX2P/CSI_CLKP", O), ("E1", "TX2N/CSI_CLKN", O), ("D2", "TX3P/CSI_D2P", O), ("D1", "TX3N/CSI_D2N", O),
    ("C2", "TX4P/CSI_D3P", O), ("C1", "TX4N/CSI_D3N", O), ("B1", "MIPI_REXT", P),
    None,
    ("A2", "TX5P", O), ("B2", "TX5N", O), ("A3", "TX6P", O), ("B3", "TX6N", O), ("A4", "TX7P", O), ("B4", "TX7N", O),
    ("A5", "TX8P", O), ("B5", "TX8N", O), ("A6", "TX9P", O), ("B6", "TX9N", O), ("A7", "GVI_HPD", B),
    ("B7", "GVI_LOCK", B),
    None,
    ("A9", "VOP_DCLK", B), ("B9", "VOP_DEN", B), ("A8", "VOP_HSYNC", B), ("B8", "VOP_VSYNC", B),
] + [(b, f"VOP_D{i}", B) for i, b in enumerate(
    ["G10", "G11", "G12", "F9", "F12", "F11", "F10", "E10", "E12", "E11", "D10", "D11", "C11", "D12", "C12", "B12",
     "B11", "A11", "C10", "B10", "A10", "D9", "C9", "C8"])]
POWER = [
    (["D8", "E9"], "DVDD_1V1", PW), (["J7"], "PLL_AVDD_1V1", PW), (["H9", "J9"], "HDMIRX_DVDD_1V1", PW),
    (["C5", "D4", "E3", "F3"], "MIPI_AVDD_1V1", PW), (["J4", "J5", "J6"], "HDMITX_DVDD_1V1", PW),
    (["H5"], "VCCIO1", PW), (["E8", "F8"], "VCCIO2", PW), (["M10"], "PLL_AVDD_3V3", PW),
    (["J10"], "HDMIRX_AVDD_3V3", PW), (["C3"], "MIPI_PLL_AVDD_3V3", PW), (["D5", "E4"], "MIPI_AVDD_3V3", PW),
    (["K4"], "HDMITX_AVDD_3V3", PW), (["J8"], "EFUSE_VDD_2V5", PW), (GND_BALLS, "VSS", PW),
]


def _check():
    balls = [p[0] for p in LEFT + RIGHT if p] + [b for p in POWER for b in p[0]]
    assert len(balls) == 144 and len(set(balls)) == 144, (len(balls), len(set(balls)))
    grid = {f"{r}{c}" for r in "ABCDEFGHJKLM" for c in range(1, 13)}
    assert set(balls) == grid, sorted(grid ^ set(balls))


_check()
pad = [None] * 12  # room for the bottom pin names inside the box
RK628D = "relay:" + box_symbol(
    "RK628D", LEFT + pad, RIGHT + [None] * (len(LEFT) - len(RIGHT)) + pad, bottom=POWER,
    footprint="relay:BGA-144_8.0x8.0mm_Layout12x12_P0.65mm",
    description="Rockchip HDMI 2.0 RX to MIPI CSI-2 bridge, WBBGA-144 8x8 mm 0.65 mm pitch. LCSC C2843533",
    width=76.2)


def build(project):
    from sch import Sheet
    s = Sheet(project, "hdmi_in", "HDMI in (RK628D)", 200, paper="A2")
    s.text("HDMI IN -> RK628D -> MIPI CSI-2 x4 to the module.  Circuit copied from DshanPi-A1 V1.1 pages 31-32.\n"
           "Route HDMI and CSI pairs at 100 ohm differential.  Power filter capacitors go at the RK628D balls.", (20, 15), 2)

    # ---------------- RK628D
    csi = {"TX0P/CSI_D0P": "CSI_D0_P", "TX0N/CSI_D0N": "CSI_D0_N", "TX1P/CSI_D1P": "CSI_D1_P",
           "TX1N/CSI_D1N": "CSI_D1_N", "TX2P/CSI_CLKP": "CSI_CLK_P", "TX2N/CSI_CLKN": "CSI_CLK_N",
           "TX3P/CSI_D2P": "CSI_D2_P", "TX3N/CSI_D2N": "CSI_D2_N", "TX4P/CSI_D3P": "CSI_D3_P",
           "TX4N/CSI_D3N": "CSI_D3_N"}
    conn = {
        "HDMIRX_CLKP": "HDMIRX_CLK_P", "HDMIRX_CLKN": "HDMIRX_CLK_N", "HDMIRX_D0P": "HDMIRX_D0_P",
        "HDMIRX_D0N": "HDMIRX_D0_N", "HDMIRX_D1P": "HDMIRX_D1_P", "HDMIRX_D1N": "HDMIRX_D1_N",
        "HDMIRX_D2P": "HDMIRX_D2_P", "HDMIRX_D2N": "HDMIRX_D2_N",
        "HDMIRX_HPD": "RX_HPD", "HDMIRX_SCL": "RX_SCL", "HDMIRX_SDA": "RX_SDA", "HDMIRX_CEC": "RX_CEC",
        "HDMIRX_EXTR": "RX_EXTR", "OSC_IN": "XIN_628", "OSC_OUT": "XOUT_628", "RESETN": "RK628D_RESET_N",
        "TEST": "GND", "I2C_ADDR(GPIO3_B3)": "RK628D_I2C_ADDR", "I2C_SCL": "I2C_628_SCL", "I2C_SDA": "I2C_628_SDA",
        "INT(GPIO3_B4)": "RK628D_INT", "I2S_SCK": "I2S_628_SCLK", "I2S_LRCK": "I2S_628_LRCK", "I2S_D0": "I2S_628_SDO",
        "I2S_D1": None, "I2S_D2": None, "I2S_D3": None, "TEST_CLKO/I2S_MCLK": "I2S_628_MCLK", "GPIO1_A1": None,
        "MIPI_REXT": "MIPI_REXT", "HDMITX_EXTR": "TX_EXTR",
        "DVDD_1V1": "1V1_628", "PLL_AVDD_1V1": "AVDD_1V1_628", "HDMIRX_DVDD_1V1": "AVDD_1V1_628",
        "MIPI_AVDD_1V1": "AVDD_1V1_628", "HDMITX_DVDD_1V1": "AVDD_1V1_628",
        "VCCIO1": "RK628D_3V3", "VCCIO2": "RK628D_3V3", "PLL_AVDD_3V3": "AVDD_3V3_628",
        "HDMIRX_AVDD_3V3": "AVDD_3V3_628", "MIPI_PLL_AVDD_3V3": "AVDD_3V3_628", "MIPI_AVDD_3V3": "AVDD_3V3_628",
        "HDMITX_AVDD_3V3": "AVDD_3V3_628", "EFUSE_VDD_2V5": "EFUSE_628", "VSS": "GND",
    }
    conn.update(csi)
    unused = ["HDMITX_HPD", "HDMITX_SDA", "HDMITX_SCL", "HDMITX_CEC", "HDMITX_CLKP", "HDMITX_CLKN", "HDMITX_D0P",
              "HDMITX_D0N", "HDMITX_D1P", "HDMITX_D1N", "HDMITX_D2P", "HDMITX_D2N", "TX5P", "TX5N", "TX6P", "TX6N",
              "TX7P", "TX7N", "TX8P", "TX8N", "TX9P", "TX9N", "GVI_HPD", "GVI_LOCK", "VOP_DCLK", "VOP_DEN",
              "VOP_HSYNC", "VOP_VSYNC"] + [f"VOP_D{i}" for i in range(24)]
    conn.update({k: None for k in unused})
    s.add(RK628D, (200, 160), conn, value="RK628D", ref="U", LCSC="C2843533")

    # strap, reference resistors, eFuse, reset, clock (DshanPi page 31)
    resistor(s, (95, 95), "RK628D_I2C_ADDR", "GND", "10k", Note="ADDR low: 7-bit I2C address 0x50 (0x51 if pulled up)")
    resistor(s, (105, 95), "RK628D_3V3", "RK628D_I2C_ADDR", "10k", dnp=True)
    resistor(s, (115, 95), "RX_EXTR", "GND", "2k 1%")
    resistor(s, (125, 95), "TX_EXTR", "GND", "2k 1%", Note="HDMI TX unused but powered, as in the reference")
    resistor(s, (300, 60), "MIPI_REXT", "GND", "4.02k 1%")
    resistor(s, (135, 95), "EFUSE_628", "GND", "100R", Note="eFuse supply held low in normal use (datasheet)")
    cap(s, (145, 95), "EFUSE_628", "GND", "100nF")
    cap(s, (155, 95), "RK628D_RESET_N", "GND", "100nF")
    s.add("Device:Crystal_GND24", (110, 130), {"1": "XIN_628", "3": "XOUT_628", "G": "GND"}, value="24MHz",
          footprint="Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", Note="CL to match the load caps (12 pF part)")
    cap(s, (100, 145), "XIN_628", "GND", "18pF")
    cap(s, (120, 145), "XOUT_628", "GND", "18pF")
    resistor(s, (95, 70), "RK628D_3V3", "I2C_628_SCL", "4.7k")
    resistor(s, (105, 70), "RK628D_3V3", "I2C_628_SDA", "4.7k")

    # ---------------- RK628D power gating and filtering (DshanPi page 31 "RK628D POWER")
    # 3V3_IO -> P-FET (switched by RK628D_PWR_EN via an NPN) -> RK628D_3V3 -> ferrite -> AVDD_3V3_628
    s.add("Transistor_FET:AO3401A", (60, 250), {"S": "3V3_IO", "D": "RK628D_3V3", "G": "PFET_G_628"},
          footprint="Package_TO_SOT_SMD:SOT-23", LCSC="C15127")
    resistor(s, (45, 235), "3V3_IO", "PFET_G_628", "10k")
    resistor(s, (45, 265), "PFET_G_628", "NPN_C_628", "1k")
    s.add("Transistor_BJT:MMBT3904", (80, 285), {"B": "NPN_B_628", "C": "NPN_C_628", "E": "GND"})
    resistor(s, (60, 300), "RK628D_PWR_EN", "NPN_B_628", "1k")
    resistor(s, (95, 300), "NPN_B_628", "GND", "100k")
    cap(s, (35, 250), "3V3_IO", "GND", "10uF", footprint=C0805)
    cap(s, (100, 250), "RK628D_3V3", "GND", "10uF", footprint=C0805)
    cap(s, (110, 250), "RK628D_3V3", "GND", "100nF")
    s.add("Device:FerriteBead", (130, 250), {"1": "RK628D_3V3", "2": "AVDD_3V3_628"}, value="330R@100MHz",
          footprint="Inductor_SMD:L_0603_1608Metric", ref="FB")
    s.add("Device:FerriteBead", (150, 250), {"1": "1V1_628", "2": "AVDD_1V1_628"}, value="330R@100MHz",
          footprint="Inductor_SMD:L_0603_1608Metric", ref="FB")
    # decoupling at the balls: DVDD x2, PLL 1V1, HDMIRX 1V1, MIPI 1V1 x4, HDMITX 1V1 x3; VCCIO x3; 3V3 analog
    x = 175
    for net, vals in (("1V1_628", ["100nF", "100nF", "10uF"]),
                      ("AVDD_1V1_628", ["100nF"] * 9 + ["1uF", "1uF", "10uF"]),
                      ("RK628D_3V3", ["100nF", "100nF", "100nF", "1uF"]),
                      ("AVDD_3V3_628", ["100nF"] * 6 + ["1uF", "10uF"])):
        for v in vals:
            cap(s, (x, 300), net, "GND", v, footprint=C0805 if v == "10uF" else C0402)
            x += 8.89

    # ---------------- HDMI connector, protection, plug detect, DDC/CEC/HPD (DshanPi page 32)
    hdmi = {"D2+": "HDMIRX_D2_P", "D2-": "HDMIRX_D2_N", "D1+": "HDMIRX_D1_P", "D1-": "HDMIRX_D1_N",
            "D0+": "HDMIRX_D0_P", "D0-": "HDMIRX_D0_N", "CK+": "HDMIRX_CLK_P", "CK-": "HDMIRX_CLK_N",
            "CEC": "PORT_CEC", "UTILITY": None, "SCL": "PORT_SCL", "SDA": "PORT_SDA", "HPD": "PORT_HPD",
            "+5V": "HDMIRX_5V", "D2S": "GND", "D1S": "GND", "D0S": "GND", "CKS": "GND", "GND": "GND", "SH": "GND"}
    s.add("Connector:HDMI_A", (420, 150), hdmi, value="HDMI IN",
          footprint="Connector_Video:HDMI_A_Molex_208658-1001_Horizontal",
          Note="Footprint to match the bought part (LCSC C2902698)")
    cap(s, (440, 100), "HDMIRX_5V", "GND", "100nF")
    for i, pins in enumerate((("HDMIRX_D2_P", "HDMIRX_D2_N", "HDMIRX_D0_P", "HDMIRX_D0_N"),
                              ("HDMIRX_CLK_P", "HDMIRX_CLK_N", "HDMIRX_D1_P", "HDMIRX_D1_N"),
                              ("PORT_HPD", "PORT_CEC", "PORT_SCL", "PORT_SDA"))):
        _rclamp(s, (360 + 30 * i, 250), pins)
    resistor(s, (330, 140), "RX_HPD", "PORT_HPD", "22R")
    # CEC: 27k pull-up from RK628D_3V3 through a Schottky (no back-feed when off); 22R series
    s.add("Device:D_Schottky", (300, 175), {"A": "RK628D_3V3", "K": "CEC_PU"}, value="MBR0530",
          footprint="Diode_SMD:D_SOD-123")
    resistor(s, (315, 190), "CEC_PU", "PORT_CEC", "27k")
    resistor(s, (330, 190), "RX_CEC", "PORT_CEC", "22R")
    resistor(s, (345, 190), "CEC_GPIO", "PORT_CEC", "0R", dnp=True,
             Note="Option: module GPIO bit-bangs CEC if the RK628D driver can't send Blackmagic vendor messages")
    # DDC: 47k pull-ups to the source's +5V through a Schottky; 22R series to the RK628D
    s.add("Device:D_Schottky", (300, 215), {"A": "HDMIRX_5V", "K": "DDC_PU"}, value="MBR0530",
          footprint="Diode_SMD:D_SOD-123")
    resistor(s, (315, 230), "DDC_PU", "PORT_SCL", "47k")
    resistor(s, (325, 230), "DDC_PU", "PORT_SDA", "47k")
    resistor(s, (340, 230), "RX_SCL", "PORT_SCL", "22R")
    resistor(s, (350, 230), "RX_SDA", "PORT_SDA", "22R")
    # plug detect: the source's +5V turns on an NPN; RK628D_PLUGIN_DET goes low when a camera is connected
    resistor(s, (380, 60), "HDMIRX_5V", "DET_B", "2k")
    resistor(s, (395, 75), "DET_B", "GND", "10k")
    s.add("Transistor_BJT:MMBT3904", (410, 60), {"B": "DET_B", "C": "RK628D_PLUGIN_DET", "E": "GND"})
    resistor(s, (430, 45), "3V3_IO", "RK628D_PLUGIN_DET", "10k")
    # HDMI audio (RK628D I2S) to test pads only: on the CM3, I2S1_M1 shares pins with the DVP input for SDI.
    for i, net in enumerate(("I2S_628_SCLK", "I2S_628_LRCK", "I2S_628_SDO", "I2S_628_MCLK")):
        s.add("Connector:TestPoint", (40 + 12 * i, 330), {"1": net}, ref="TP", value=net,
              footprint="TestPoint:TestPoint_Pad_D1.0mm")
    for i, net in enumerate(("RK628D_3V3", "AVDD_3V3_628", "AVDD_1V1_628", "EFUSE_628", "HDMIRX_5V")):
        s.flag(net, (250 + 15 * i, 40))
    return s


def _rclamp(s, at, lines):
    """RCLAMP0524P (DFN2510-10): four lines flow through pins 1/10, 2/9, 4/7, 5/6; GND on 3 and 8."""
    s.add(RCLAMP, at, {"IO1": lines[0], "IO2": lines[1], "IO3": lines[2], "IO4": lines[3], "GND": "GND"},
          value="RCLAMP0524P", ref="D", LCSC="C907837")


# Flow-through part: IO1 pins 1 and 10, IO2 2 and 9, IO3 4 and 7, IO4 5 and 6 (RCLAMP0524P.pdf). The board routes
# each line straight through its pad pair, so the symbol shows one pin per line.
RCLAMP = "relay:" + box_symbol(
    "RCLAMP0524P",
    left=[(["1", "10"], "IO1", P), (["2", "9"], "IO2", P), (["4", "7"], "IO3", P), (["5", "6"], "IO4", P)],
    right=[], bottom=[None, (["3", "8"], "GND", P)],
    footprint="Package_SON:USON-10_2.5x1.0mm_P0.5mm",
    description="4-line ESD array, flow-through DFN2510-10. LCSC C907837", width=12.7)
