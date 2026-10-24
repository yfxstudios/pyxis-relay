"""Sheet: Radxa CM3 (RK3566) on three Hirose DF40 100-pin receptacles.

Pin names come from the Radxa CM3 datasheet rev 1.2, Appendix C (gen/cm3_pinout.json, extracted from
datasheets/Radxa_CM3_Datasheet.pdf), updated to module revision V1.32+ from Radxa's pinout change history
(datasheets/radxa_cm3_v1300_to_1320_pinout.xlsx). Older modules (V1.3, V1.31) differ on five pins. Radxa numbers J68's pins 101-200; on the receptacle footprint they are pads 1-100.
Every pin is either assigned below or marked unused (no-connect); the build fails on any pin left out.
"""
import json
import os

from parts import C0402, cap, resistor
from sch import box_symbol

PINOUT = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cm3_pinout.json")))
GND = "GND"

# (connector, Radxa pin number) -> carrier net. Choices are explained in REV_A_SPEC.md section 7.
ASSIGN = {
    "J69": {
        3: "MDI3_P", 5: "MDI3_N", 4: "MDI1_P", 6: "MDI1_N", 11: "MDI2_P", 9: "MDI2_N", 12: "MDI0_P", 10: "MDI0_N",
        48: "RK628D_RESET_N", 50: "RK628D_PLUGIN_DET",
        28: "I2C_628_SCL", 36: "I2C_628_SDA",                       # GPIO0_C6, GPIO4_B4: i2c-gpio (pin 35 had no room)
        37: "SDI_UART_TX",                                           # GPIO4_C5 = UART9_TX_M1 (V1.32: was SARADC)
        93: "RECOVERY_ADC",                                          # SARADC_VIN0: low at boot = Rockusb recovery
        30: "LED_STATUS", 56: "LED_WIFI", 58: "PD_PG_N",
        51: "DEBUG_RX", 55: "DEBUG_TX",                              # UART2_M0, the boot console
        100: "SOM_RESET_N",                                          # PMIC_RESET_KEY
        77: "5V_SOM", 79: "5V_SOM", 81: "5V_SOM", 83: "5V_SOM", 85: "5V_SOM", 87: "5V_SOM",
        78: "SOM_3V3", 84: "SOM_3V3", 86: "SOM_3V3",                # GPIO_VREF must tie to the module's +3V3
        88: "SOM_1V8", 90: "SOM_1V8",
        # DVP (CIF) for the SDI add-on header
        41: "DVP_D0", 49: "DVP_D1", 26: "DVP_D2", 25: "DVP_D3", 27: "DVP_D4", 45: "DVP_D5", 47: "DVP_D6",
        54: "DVP_D7", 21: "DVP_D14", 91: "DVP_D15", 89: "DVP_HSYNC", 95: "DVP_VSYNC", 97: "DVP_PCLK",
        38: "SDI_I2C_SCL", 44: "SDI_I2C_SDA",                       # I2C4_M0
        29: "SDI_GPIO1", 34: "SDI_GPIO2", 39: "SDI_GPIO3", 40: "SDI_GPIO4",
    },
    "J68": {
        103: "USB_OTG_DM", 105: "USB_OTG_DP",
        102: "PCIE_CLKREQ_N", 109: "PCIE_PERST_N",                  # PCIE20_*_M2 group (WAKE is J1 pin 38)
        110: "PCIE_REFCLK_P", 112: "PCIE_REFCLK_N", 116: "PCIE_RX_P", 118: "PCIE_RX_N",
        122: "PCIE_TX_P", 124: "PCIE_TX_N",
        117: "CSI_D0_P", 115: "CSI_D0_N", 123: "CSI_D1_P", 121: "CSI_D1_N", 129: "CSI_CLK_P", 127: "CSI_CLK_N",
        130: "CSI_D2_P", 128: "CSI_D2_N", 136: "CSI_D3_P", 134: "CSI_D3_N",
        170: "HDMITX_D2_P", 172: "HDMITX_D2_N", 176: "HDMITX_D1_P", 178: "HDMITX_D1_N",
        182: "HDMITX_D0_P", 184: "HDMITX_D0_N", 188: "HDMITX_CLK_P", 190: "HDMITX_CLK_N",
        153: "HDMITX_HPD", 199: "HDMITX_SDA", 200: "HDMITX_SCL",     # level-shifted on the module
        151: "CEC_GPIO",                                             # GPIO4_D1 (VCCIO7, 3.3 V): next to the RK628D
    },
    "J1": {
        34: "BT_DISABLE_N", 74: "WIFI_DISABLE_N", 38: "PCIE_WAKE_N",
        14: "VIN_SENSE",                                             # SARADC_VIN3, 0-1.8 V
        63: "USB_BT_DP", 65: "USB_BT_DM",                            # USB2 HOST2
        97: "OTG_VBUSDET",
        75: "DVP_D8", 77: "DVP_D9", 79: "DVP_D10", 81: "DVP_D11", 83: "DVP_D12", 85: "DVP_D13",
        36: "SDI_UART_RX",                                           # UART9_RX_M1 (TX is J69 pin 37)
        4: "SDI_GPIO5", 6: "SDI_GPIO6", 8: "SDI_GPIO7", 10: "SDI_GPIO8",
        18: "RK628D_INT", 95: "RK628D_PWR_EN",                       # GPIO0_D5, GPIO0_C4: J69's middle is full
    },
}
OFFSET = {"J69": 0, "J68": 100, "J1": 0}


def _symbol(conn):
    pins = PINOUT[conn]
    rows = []
    for pad in range(1, 101):
        n = pad + OFFSET[conn]
        name = pins[str(n)]["name"] or "NC"
        ptype = "power_in" if name in ("+5V_INPUT", "GND") else "passive"
        rows.append((str(pad), f"{n} {name}" if OFFSET[conn] else name, ptype))
    return "relay:" + box_symbol(
        f"Radxa_CM3_{conn}", rows[0::2], rows[1::2], ref="J",
        footprint=f"relay:Radxa_CM3_{conn}", width=55.88,
        description=f"Radxa CM3 connector {conn} (carrier receptacle Hirose DF40C-100DS-0.4V(51), 1.5 mm stack). "
                    + ("Radxa pin = pad + 100." if OFFSET[conn] else "Radxa pin = pad."))


def build(project):
    from sch import Sheet
    s = Sheet(project, "module", "Module: Radxa CM3", 700, paper="A2")
    s.text("Radxa CM3 (RK3566, RM116-D2E16W0: 2 GB, 16 GB eMMC, no Wi-Fi) on three DF40C-100DS-0.4V(51) receptacles.\n"
           "Pinout for module revision V1.32 or later (shipping V1.322).  Power: 5V_SOM, 3.8-5.2 V, up to 3 A.\n"
           "GPIO_VREF tied to the module's +3V3 (3.3 V I/O, as the datasheet requires).  Unused pins are no-connect.\n"
           "The module has its own Ethernet PHY (RTL8211F) and level-shifts HDMI DDC/CEC/HPD.", (20, 15), 2)
    for i, conn in enumerate(("J69", "J68", "J1")):
        sym = _symbol(conn)
        assign = ASSIGN[conn]
        conns = {}
        for pad in range(1, 101):
            n = pad + OFFSET[conn]
            name = PINOUT[conn][str(n)]["name"]
            if n in assign:
                conns[str(pad)] = assign[n]
            elif name == "GND":
                conns[str(pad)] = GND
            else:
                conns[str(pad)] = None
        bad = set(assign) - {pad + OFFSET[conn] for pad in range(1, 101)}
        assert not bad, (conn, bad)
        s.add(sym, (110 + 170 * i, 200), conns, value=f"CM3 {conn}", ref="J",
              LCSC="C597931", Note="Hirose DF40C-100DS-0.4V(51) receptacle")

    # module support parts (datasheet sections 3.1, 3.2.1, 3.11)
    resistor(s, (60, 60), "SOM_1V8", "RECOVERY_ADC", "10k", Note="SARADC_VIN0 pull-up to 1.8 V (datasheet: keep it)")
    cap(s, (70, 60), "RECOVERY_ADC", "GND", "1nF")
    resistor(s, (85, 60), "SOM_3V3", "OTG_VBUSDET", "10k",
             Note="VBUSDET must be high (2.7-3.3 V) for USB device mode: held high so flashing always works")
    cap(s, (100, 60), "SOM_3V3", "GND", "100nF")
    cap(s, (110, 60), "SOM_1V8", "GND", "100nF")
    resistor(s, (150, 60), "SOM_3V3", "SDI_I2C_SCL", "2.2k")
    resistor(s, (160, 60), "SOM_3V3", "SDI_I2C_SDA", "2.2k")
    for i in range(4):
        cap(s, (180 + 10 * i, 60), "5V_SOM", "GND", "22uF/10V" if i < 2 else "100nF",
            footprint="Capacitor_SMD:C_0805_2012Metric" if i < 2 else C0402)
    s.flag("SOM_3V3", (240, 45))
    s.flag("SOM_1V8", (255, 45))
    return s
