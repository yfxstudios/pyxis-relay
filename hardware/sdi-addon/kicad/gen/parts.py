"""Project symbols (library "sdi") and the footprints used for common parts.

Pinouts come from the datasheets in ../../datasheets/.
"""
from sch import box_symbol

# footprints
R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
L0402 = "Inductor_SMD:L_0402_1005Metric"
LED0603 = "LED_SMD:LED_0603_1608Metric"
TP = "TestPoint:TestPoint_Pad_D1.0mm"

P, I, O, B, PW = "passive", "input", "output", "bidirectional", "power_in"

# GS2971A, 11 x 11 mm 100-ball LBGA, 1.0 mm pitch (GS2971A datasheet Rev. 3, section 1.1 and table 1-1)
GS_LEFT = [
    ("C1", "SDI", I), ("D1", "~{SDI}", I), ("F1", "AGCP", P), ("G1", "AGCN", P),
    None,
    ("A1", "VBG", P), ("A2", "LF", P), ("A3", "LB_CONT", P), ("A4", "VCO_VDD", PW),
    None,
    ("K6", "XTAL1", I), ("J6", "XTAL2", P), ("H6", "XTAL_OUT", O),
    None,
    ("C7", "RESET_TRST", I), ("D8", "JTAG/~{HOST}", I), ("F7", "~{CS}_TMS", I), ("F8", "SCLK_TCK", I),
    ("E8", "SDIN_TDI", I), ("E7", "SDOUT_TDO", O),
    None,
    ("H7", "20bit/~{10bit}", I), ("H8", "IOPROC_EN/~{DIS}", I), ("H3", "AUDIO_EN/~{DIS}", I), ("H5", "TIM_861", I),
    ("D7", "SW_EN", I), ("K2", "STANDBY", I), ("J2", "SDO_EN/~{DIS}", I), ("G3", "RC_BYP", I),
    ("G7", "SMPTE_BYPASS", B), ("G8", "DVB_ASI", B),
    None,
    ("J1", "SDO", O), ("K1", "~{SDO}", O),
    None,
    ("B3", "RSV", P), ("F2", "RSV", P),
]
GS_RIGHT = [
    ("A8", "PCLK", O),
    None,
] + [(b, f"DOUT{i}", O) for i, b in [
    (19, "B8"), (18, "A9"), (17, "A10"), (16, "B9"), (15, "B10"), (14, "C9"), (13, "C10"), (12, "C8"), (11, "E10"),
    (10, "E9"), (9, "F10"), (8, "F9"), (7, "H10"), (6, "H9"), (5, "J10"), (4, "J9"), (3, "K10"), (2, "K9"),
    (1, "J8"), (0, "K8")]] + [
    None,
    ("A5", "STAT0", O), ("A6", "STAT1", O), ("B5", "STAT2", O), ("B6", "STAT3", O), ("C5", "STAT4", O),
    ("C6", "STAT5", O),
    None,
    ("J3", "AOUT_1/2", O), ("K3", "AOUT_3/4", O), ("J5", "AOUT_5/6", O), ("K5", "AOUT_7/8", O), ("J4", "ACLK", O),
    ("H4", "WCLK", O), ("K4", "AMCLK", O),
]
GS_POWER = [
    (["D6", "E6", "F6", "G6"], "CORE_VDD", PW), (["B2", "C3", "C4"], "PLL_VDD", PW), (["B1"], "A_VDD", PW),
    (["E1"], "EQ_VDD", PW), (["H1"], "BUFF_VDD", PW), (["A7", "D10", "G10", "K7"], "IO_VDD", PW),
    (["B4"], "VCO_GND", PW), (["C2", "D2", "D3", "E3", "F3", "G2"], "A_GND", PW), (["D4", "E4", "F4"], "PLL_GND", PW),
    (["D5", "E5", "F5", "G4", "G5"], "CORE_GND", PW), (["B7", "D9", "G9", "J7"], "IO_GND", PW), (["E2"], "EQ_GND", PW),
    (["H2"], "BUFF_GND", PW),
]


def _check():
    balls = [p[0] for p in GS_LEFT + GS_RIGHT if p] + [b for p in GS_POWER for b in p[0]]
    grid = {f"{r}{c}" for r in "ABCDEFGHJK" for c in range(1, 11)}
    assert len(balls) == 100 and set(balls) == grid, sorted(grid ^ set(balls))


_check()
GS2971A = "sdi:" + box_symbol(
    "GS2971A", GS_LEFT, GS_RIGHT + [None] * (len(GS_LEFT) - len(GS_RIGHT)), bottom=GS_POWER,
    footprint="sdi:BGA-100_11.0x11.0mm_Layout10x10_P1.0mm",
    description="Semtech 3G/HD/SD-SDI receiver with integrated adaptive cable equalizer, 11 x 11 mm LBGA-100. "
                "LCSC C512366",
    width=66.04)

# SY8089AAAC: 2.7-5.5 V, 2 A synchronous buck, SOT-23-5, FB 0.6 V. Pinout to check against the datasheet before
# layout (EN 1, GND 2, LX 3, IN 4, FB 5).
SY8089 = "sdi:" + box_symbol(
    "SY8089AAAC",
    left=[("4", "IN", PW), ("1", "EN", I)],
    right=[("3", "LX", "power_out"), ("5", "FB", I)],
    bottom=[None, ("2", "GND", PW)],
    footprint="Package_TO_SOT_SMD:SOT-23-5",
    description="Silergy 2.7-5.5 V 2 A synchronous step-down regulator, FB 0.6 V",
)


def resistor(sheet, at, a, b, value, **kw):
    return sheet.add("Device:R", at, {"1": a, "2": b}, value=value, footprint=kw.pop("footprint", R0402), **kw)


def cap(sheet, at, a, b, value, footprint=C0402, **kw):
    return sheet.add("Device:C", at, {"1": a, "2": b}, value=value, footprint=footprint, **kw)


def testpoint(sheet, at, net):
    return sheet.add("Connector:TestPoint", at, {"1": net}, value=net, ref="TP", footprint=TP)
