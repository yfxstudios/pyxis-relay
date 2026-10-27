"""Sheet: power inputs and regulators (REV_A_SPEC.md section 3)."""
from parts import C0402, C0805, C1206, R0402, SY8303, TPS563201, cap, resistor


def build(project):
    from sch import Sheet
    s = Sheet(project, "power", "Power", 100)
    s.text("Power: DC 6-17 V / NP-F / USB-C PD 9 V  ->  5V_SOM and 5V_SYS (2x SY8303)  ->  3V3_IO, 1V1_628 (TPS563201)\n"
           "Inputs are OR-ed with Schottky diodes: no back-feed between them, and reversed DC is blocked.\n"
           "See REV_A_SPEC.md section 3.", (20, 15), 2)

    # ---- inputs
    s.add("Connector:Barrel_Jack", (30, 50), {"1": "VDC", "2": "GND"}, value="DC 6-17V",
          footprint="Connector_BarrelJack:BarrelJack_Horizontal", Note="CUI PJ-002AH, 5.5 x 2.0 mm, 5 A (LCSC C2961147); not a locking type")
    s.add("Connector_Generic:Conn_01x02", (30, 75), {"1": "VNPF", "2": "GND"}, value="NP-F plate", ref="J",
          footprint="Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical")
    s.add("Device:D_Schottky", (60, 50), {"K": "VIN_RAW", "A": "VDC"}, value="SS54",
          footprint="Diode_SMD:D_SMA")
    s.add("Device:D_Schottky", (60, 75), {"K": "VIN_RAW", "A": "VNPF"}, value="SS54",
          footprint="Diode_SMD:D_SMA")

    # USB-C: PD sink asks for 9 V; a P-FET passes VBUS only once PD is good (PG low)
    s.add("Connector:USB_C_Receptacle_USB2.0_16P", (35, 140),
          {"VBUS": "VBUS_C", "CC1": "CC1", "CC2": "CC2", "D+": "USB_OTG_DP_C", "D-": "USB_OTG_DM_C",
           "SBU1": None, "SBU2": None, "GND": "GND", "SHIELD": "GND"},
          footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", LCSC="C165948")
    s.add("Power_Protection:USBLC6-2SC6", (80, 175),
          {"1": "USB_OTG_DP_C", "6": "USB_OTG_DP", "3": "USB_OTG_DM_C", "4": "USB_OTG_DM", "2": "GND",
           # pin 5 floats: tied to VBUS_C its 6-9 V clamp would conduct at the 9 V PD contract. The data-line
           # clamps still work through the internal Zener.
           "5": None}, footprint="Package_TO_SOT_SMD:SOT-23-6")
    s.add("Interface_USB:CH224K", (95, 130),
          {"VDD": "VBUS_C", "VBUS": "VBUS_C", "CC1": "CC1", "CC2": "CC2", "DP": None, "DM": None,
           "CFG1": "PD_CFG1", "CFG2": None, "CFG3": None, "PG": "PD_PG_N", "GND": "GND"},
          value="CH224A", footprint="Package_SO:SSOP-10-1EP_3.9x4.9mm_P1mm_EP2.1x3.3mm",
          Note="CH224A (pin-compatible CH224K successor, VBUS rated 32 V). Pin 1 = VHV.")
    cap(s, (115, 105), "VBUS_C", "GND", "1uF/50V", footprint=C0805)
    resistor(s, (125, 145), "PD_CFG1", "GND", "6.8k", Note="CH224A single-resistor config: 6.8k = 9 V")
    # PG (open drain) pulls the P-FET gate low once a 9 V contract is up
    resistor(s, (140, 105), "VBUS_C", "PD_PG_N", "100k")
    s.add("Transistor_FET:AO3401A", (160, 120), {"G": "PD_PG_N", "S": "VBUS_C", "D": "VBUS_SW"},
          footprint="Package_TO_SOT_SMD:SOT-23", LCSC="C15127", Note="AO3401A: 30 V P-FET, VGS max 12 V: OK at 9 V")
    s.add("Device:D_Schottky", (180, 140), {"K": "VIN_RAW", "A": "VBUS_SW"}, value="SS54",
          footprint="Diode_SMD:D_SMA")

    # ---- protection, bulk capacitance, battery sense
    s.add("Device:Polyfuse", (90, 60), {"1": "VIN_RAW", "2": "VIN"}, value="3A hold", footprint="Fuse:Fuse_1812_4532Metric")
    s.add("Device:D_TVS", (110, 75), {"A1": "VIN", "A2": "GND"}, value="SMBJ20CA", footprint="Diode_SMD:D_SMB")
    s.add("Device:C_Polarized", (125, 60), {"1": "VIN", "2": "GND"}, value="47uF/35V",
          footprint="Capacitor_SMD:CP_Elec_6.3x7.7", ref="C")
    resistor(s, (140, 50), "VIN", "VIN_SENSE", "100k")
    resistor(s, (140, 72), "VIN_SENSE", "GND", "10k", Note="VIN/11 to a 1.8 V SARADC input: 17 V -> 1.55 V")
    cap(s, (150, 72), "VIN_SENSE", "GND", "100nF")
    s.flag("VIN", (100, 40))
    s.flag("GND", (110, 40))
    s.flag("VBUS_C", (120, 40))

    # ---- two SY8303 5 V converters, 500 kHz (lowest frequency = highest duty cycle, for low NP-F voltage):
    #      5V_SOM feeds only the Radxa CM3 (up to 3 A), 5V_SYS everything else
    def five_volt(x, y, net, tag, note):
        s.add(SY8303, (x, y), {"IN": "VIN", "EN": "EN_5V", "FS": f"FS_{tag}", "BS": f"BS_{tag}", "LX": f"LX_{tag}",
                               "FB": f"FB_{tag}", "GND": "GND"}, value="SY8303AIC", ref="U", LCSC="C97054", Note=note)
        cap(s, (x - 40, y - 15), "VIN", "GND", "4.7uF/50V", footprint=C1206)
        cap(s, (x - 32, y - 15), "VIN", "GND", "4.7uF/50V", footprint=C1206)
        resistor(s, (x - 24, y + 25), f"FS_{tag}", "GND", "200k",
                 Note="RFS 200k = 0.5 MHz in the datasheet's table (105/RFS gives 525 kHz), the low end of 0.5-2.5 MHz")
        cap(s, (x + 30, y - 25), f"BS_{tag}", f"LX_{tag}", "10nF")
        s.add("Device:L", (x + 45, y - 10), {"1": f"LX_{tag}", "2": net}, value="6.8uH 3.6A",
              footprint="Inductor_SMD:L_Bourns_SRN6045TA")
        resistor(s, (x + 60, y + 5), net, f"FB_{tag}", "110k", Note="VOUT = 0.6 (1 + 110k/15k) = 5.0 V")
        resistor(s, (x + 60, y + 27), f"FB_{tag}", "GND", "15k")
        cap(s, (x + 72, y + 5), net, "GND", "22uF/10V", footprint=C0805)
        cap(s, (x + 80, y + 5), net, "GND", "22uF/10V", footprint=C0805)
        s.flag(net, (x + 90, y - 10))

    five_volt(230, 60, "5V_SYS", "5V", "5V_SYS: 3V3_IO, 1V1_628, HDMI out 5 V")
    five_volt(230, 140, "5V_SOM", "SOM", "5V_SOM: Radxa CM3 only (3.8-5.2 V, up to 3 A)")
    resistor(s, (180, 110), "VIN", "EN_5V", "100k", Note="EN divider (both converters): on above about 5.4 V VIN")
    resistor(s, (190, 110), "EN_5V", "GND", "39k")

    # ---- three TPS563201 rails from 5V_SYS
    def rail(x, y, net, tag, r_top, r_bot, l, en, note):
        s.add(TPS563201, (x, y), {"VIN": "5V_SYS", "EN": en, "VBST": f"BST_{tag}", "SW": f"SW_{tag}",
                                  "VFB": f"FB_{tag}", "GND": "GND"}, value="TPS563201", ref="U", LCSC="C116592")
        cap(s, (x - 35, y - 15), "5V_SYS", "GND", "10uF/10V", footprint=C0805)
        cap(s, (x - 27, y - 15), "5V_SYS", "GND", "100nF")
        cap(s, (x + 25, y - 25), f"BST_{tag}", f"SW_{tag}", "100nF")
        s.add("Device:L", (x + 40, y - 10), {"1": f"SW_{tag}", "2": net}, value=l,
              footprint="Inductor_SMD:L_Bourns_SRN6045TA")
        resistor(s, (x + 55, y + 5), net, f"FB_{tag}", r_top, Note=note)
        resistor(s, (x + 55, y + 27), f"FB_{tag}", "GND", r_bot)
        cap(s, (x + 67, y + 5), net, "GND", "22uF/10V", footprint=C0805)
        cap(s, (x + 75, y + 5), net, "GND", "22uF/10V", footprint=C0805)
        s.flag(net, (x + 85, y - 10))

    rail(60, 230, "3V3_IO", "IO", "33k", "10k", "2.2uH", "EN_3V3", "VOUT = 0.768 (1 + 33k/10k) = 3.30 V: M.2, RK628D I/O")
    rail(200, 230, "1V1_628", "628", "10k", "23.2k", "1.5uH", "EN_628",
         "VOUT = 0.768 (1 + 10k/23.2k) = 1.10 V; RK628D core and PHY")
    # 3.3 V rails come up about 10 ms after 5V_SYS (RC on EN); option to drive from the module instead
    resistor(s, (60, 185), "5V_SYS", "EN_3V3", "100k", Note="3V3_IO about 10 ms after 5V_SYS")
    cap(s, (70, 205), "EN_3V3", "GND", "100nF")
    # 1V1_628 follows the switched RK628D_3V3 (hdmi_in sheet), as in the DshanPi reference: 3.3 V first
    resistor(s, (200, 185), "RK628D_3V3", "EN_628", "10k")
    cap(s, (210, 205), "EN_628", "GND", "100nF")
    return s
