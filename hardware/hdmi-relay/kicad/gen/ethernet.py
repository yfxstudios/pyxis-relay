"""Sheet: Gigabit Ethernet jack. The PHY (RTL8211F) is on the Radxa CM3; its four MDI pairs come out on J69.

Radxa CM3 datasheet 3.4: voltage-mode PHY, so each transformer centre tap goes to ground through 1 uF (no bias).
The module already has common-mode chokes on the MDI pairs.
"""
from parts import cap


def build(project):
    from sch import Sheet
    s = Sheet(project, "ethernet", "Ethernet", 300)
    s.text("Gigabit Ethernet: the PHY is on the Radxa CM3.  MDI pairs 100 ohm differential, matched within each pair.\n"
           "Centre taps to GND through 1 uF each (voltage-mode PHY, Radxa CM3 datasheet 3.4).  Jack LEDs unused in rev A.",
           (20, 15), 2)
    s.add("Connector:RJ45_JK0654219", (150, 120),
          {"MX1+": "MDI0_P", "MX1-": "MDI0_N", "MX2+": "MDI1_P", "MX2-": "MDI1_N", "MX3+": "MDI2_P",
           "MX3-": "MDI2_N", "MX4+": "MDI3_P", "MX4-": "MDI3_N", "MXCT1": "CT1", "MXCT2": "CT2", "MXCT3": "CT3",
           "MXCT4": "CT4", "LED1+": None, "LED1-": None, "LED2+": None, "LED2-": None, "SH": "GND"},
          value="RJ45 1000BASE-T magjack", footprint="Connector_RJ:RJ45_Pulse_JK0654219NL_Horizontal",
          Note="Pick an LCSC gigabit magjack with this pinout, or redo the footprint")
    for i in range(4):
        cap(s, (90 + 10 * i, 200), f"CT{i + 1}", "GND", "1uF")
    return s
