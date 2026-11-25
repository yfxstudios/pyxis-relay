"""Project symbols (library "relay") and the footprints/LCSC numbers used for common parts.

Pinouts come from the datasheets in ../../datasheets/.
"""
from sch import box_symbol

# footprints
R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
LED0603 = "LED_SMD:LED_0603_1608Metric"

# SY8303AIC: 40 V, 3 A synchronous buck, TSOT23-8 (SY8303AIC.pdf, page 2)
SY8303 = "relay:" + box_symbol(
    "SY8303AIC",
    left=[("5", "IN", "power_in"), ("8", "EN", "input"), ("2", "FS", "passive")],
    right=[("7", "BS", "passive"), ("6", "LX", "power_out"), ("1", "FB", "input")],
    bottom=[None, (["3", "4"], "GND", "power_in")],
    footprint="Package_TO_SOT_SMD:TSOT-23-8",
    description="Silergy 4.5-40 V 3 A synchronous step-down regulator. LCSC C97054",
)

# TPS563201: 4.5-17 V, 3 A synchronous buck, SOT-23-6 (TPS563201.pdf, page 3). VFB reference 0.768 V.
TPS563201 = "relay:" + box_symbol(
    "TPS563201",
    left=[("3", "VIN", "power_in"), ("5", "EN", "input")],
    right=[("6", "VBST", "passive"), ("2", "SW", "power_out"), ("4", "VFB", "input")],
    bottom=[None, ("1", "GND", "power_in")],
    footprint="Package_TO_SOT_SMD:SOT-23-6",
    description="TI 4.5-17 V 3 A synchronous step-down regulator, VFB 0.768 V. LCSC C116592",
)


def resistor(sheet, at, a, b, value, **kw):
    return sheet.add("Device:R", at, {"1": a, "2": b}, value=value, footprint=kw.pop("footprint", R0402), **kw)


def cap(sheet, at, a, b, value, footprint=C0402, **kw):
    return sheet.add("Device:C", at, {"1": a, "2": b}, value=value, footprint=footprint, **kw)
