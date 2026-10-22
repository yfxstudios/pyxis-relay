"""Sheets: HDMI out, M.2 Wi-Fi/Bluetooth, and board I/O (debug, buttons, LEDs, SDI header, mounting).
REV_A_SPEC.md section 5."""
from parts import C0402, C0805, LED0603, cap, resistor


def hdmi_out(project):
    from sch import Sheet
    s = Sheet(project, "hdmi_out", "HDMI out", 400)
    s.text("HDMI OUT from the module's HDMI 2.0 TX: the on-set monitor feed (captured frames, no encode).\n"
           "TMDS pairs 100 ohm differential.  5 V on pin 18 from a current-limited switch (HDMI requires >= 55 mA).\n"
           "DDC/HPD go straight to the module, which level-shifts them (Radxa CM3 datasheet 3.5.1).  CEC not used.",
           (20, 15), 2)
    s.add("Connector:HDMI_A", (300, 130),
          {"D2+": "HDMITX_D2_P", "D2-": "HDMITX_D2_N", "D1+": "HDMITX_D1_P", "D1-": "HDMITX_D1_N",
           "D0+": "HDMITX_D0_P", "D0-": "HDMITX_D0_N", "CK+": "HDMITX_CLK_P", "CK-": "HDMITX_CLK_N",
           "CEC": None, "UTILITY": None, "SCL": "HDMITX_SCL", "SDA": "HDMITX_SDA", "HPD": "HDMITX_HPD",
           "+5V": "HDMITX_5V", "D2S": "GND", "D1S": "GND", "D0S": "GND", "CKS": "GND", "GND": "GND", "SH": "GND"},
          value="HDMI OUT", footprint="Connector_Video:HDMI_A_Molex_208658-1001_Horizontal",
          Note="Same connector part as HDMI IN")
    from hdmi_in import _rclamp
    _rclamp(s, (230, 230), ("HDMITX_D2_P", "HDMITX_D2_N", "HDMITX_D0_P", "HDMITX_D0_N"))
    _rclamp(s, (260, 230), ("HDMITX_CLK_P", "HDMITX_CLK_N", "HDMITX_D1_P", "HDMITX_D1_N"))
    _rclamp(s, (290, 230), ("HDMITX_HPD", "HDMITX_SCL", "HDMITX_SDA", "HDMITX_5V"))
    # 5 V to the monitor
    s.add("Power_Management:AP22804AW5", (100, 60), {"IN": "5V_SYS", "EN": "5V_SYS", "OUT": "HDMITX_5V",
                                                     "~{FLG}": None, "GND": "GND"},
          footprint="Package_TO_SOT_SMD:SOT-23-5", Note="Current-limited load switch")
    cap(s, (75, 75), "5V_SYS", "GND", "1uF")
    cap(s, (125, 75), "HDMITX_5V", "GND", "1uF")
    # The Radxa CM3 level-shifts DDC and CEC and has HPD's pull-down and series resistor on the module
    # (CM3 datasheet 3.5.1): DDC and HPD go straight to the connector. DDC pull-ups to the monitor's 5 V.
    resistor(s, (100, 150), "HDMITX_5V", "HDMITX_SCL", "2.2k")
    resistor(s, (110, 150), "HDMITX_5V", "HDMITX_SDA", "2.2k")
    return s


def m2(project):
    from sch import Sheet
    s = Sheet(project, "m2_wifi", "M.2 Wi-Fi + Bluetooth", 500)
    s.text("M.2 2230 E-key socket for the RTL8822CE card: Wi-Fi on PCIe x1 (combo PHY in PCIe mode), Bluetooth on\n"
           "USB 2.0.  Host-side 100 nF AC coupling on the lanes the host transmits.  PCIe 85 ohm, USB 90 ohm.", (20, 15), 2)
    conn = {
        "PETp0": "PCIE_RX_P", "PETn0": "PCIE_RX_N",            # card transmits -> host receives
        "PERp0": "M2_PER_P", "PERn0": "M2_PER_N",              # host transmits through the AC caps below
        "REFCLKp0": "PCIE_REFCLK_P", "REFCLKn0": "PCIE_REFCLK_N",
        "~{PERST0}": "PCIE_PERST_N", "~{CLKREQ0}": "PCIE_CLKREQ_N", "~{PEWAKE0}": "PCIE_WAKE_N",
        "~{W_DISABLE1}": "WIFI_DISABLE_N", "~{W_DISABLE2}": "BT_DISABLE_N",
        "USB_D+": "USB_BT_DP", "USB_D-": "USB_BT_DM", "3.3V": "3V3_IO", "GND": "GND",
    }
    for name in ("~{LED_1}", "PCM_CLK/I2S_SCK", "SDIO_CLK", "PCM_SYNC/I2S_WS", "SDIO_CMD", "PCM_IN/I2S_SD_IN",
                 "SDIO_DATA0", "PCM_OUT/I2S_SD_OUT", "SDIO_DATA1", "~{LED_2}", "SDIO_DATA2", "SDIO_DATA3",
                 "~{UART_WAKE}", "~{SDIO_WAKE}", "UART_RXD", "~{SDIO_RESET}", "UART_TXD", "UART_CTS", "UART_RTS",
                 "VENDOR_DEFINED", "COEX3", "COEX2", "COEX1", "SUSCLK", "I2C_DATA", "RESERVED/PETp1", "I2C_CLK",
                 "RESERVED/PETn1", "~{ALERT}", "RESERVED", "RESERVED/PERp1", "UIM_SWP/~{PERST1}", "RESERVED/PERn1",
                 "UIM_POWER_SNK/~{CLKREQ1}", "UIM_POWER_SRC/GPIO1/~{PEWAKE1}", "RESERVED/REFCLKp1",
                 "RESERVED/REFCLKn1"):
        conn[name] = None
    s.add("Connector:Bus_M.2_Socket_E", (200, 140), conn, value="M.2 E-key 2230",
          footprint="relay:M.2_E-key_Socket_PLACEHOLDER", Note="Socket footprint to make for the chosen part")
    cap(s, (110, 90), "PCIE_TX_P", "M2_PER_P", "100nF")
    cap(s, (120, 90), "PCIE_TX_N", "M2_PER_N", "100nF")
    for i, net in enumerate(("PCIE_PERST_N", "PCIE_CLKREQ_N", "PCIE_WAKE_N", "WIFI_DISABLE_N", "BT_DISABLE_N")):
        resistor(s, (290 + 10 * i, 60), "3V3_IO", net, "10k")
    for i, v in enumerate(("22uF", "22uF", "100nF", "100nF")):
        cap(s, (290 + 10 * i, 230), "3V3_IO", "GND", v, footprint=C0805 if v == "22uF" else C0402)
    return s


def board_io(project):
    from sch import Sheet
    s = Sheet(project, "board_io", "Debug, buttons, LEDs, SDI header", 600)
    s.text("Debug UART (1.5 Mb/s), RESET and RECOVERY buttons, status LEDs, the SDI add-on header (not fitted)\n"
           "and mounting holes.  The SDI header carries the module's 16-bit DVP camera input (BT.1120 from an SDI\n"
           "receiver such as the GS2971A).  On the CM3 the DVP pins are free: its Ethernet uses GMAC1_M0.", (20, 15), 2)
    s.add("Connector_Generic:Conn_01x03", (40, 60), {"Pin_1": "DEBUG_TX", "Pin_2": "DEBUG_RX", "Pin_3": "GND"},
          value="DEBUG UART", ref="J", footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical")
    # buttons
    s.add("Switch:SW_Push", (100, 60), {"1": "SOM_RESET_N", "2": "GND"}, value="RESET",
          footprint="Button_Switch_SMD:SW_SPST_TL3342")
    s.add("Switch:SW_Push", (100, 90), {"1": "RECOVERY_ADC", "2": "GND"}, value="RECOVERY",
          footprint="Button_Switch_SMD:SW_SPST_TL3342",
          Note="Held at power-up: Rockusb recovery for flashing over USB-C (CM3 datasheet 3.11)")
    # LEDs: GPIO high = on
    for i, (net, col) in enumerate((("LED_STATUS", "white"), ("LED_WIFI", "blue"))):
        x = 180 + 30 * i
        resistor(s, (x, 60), net, f"{net}_A", "1k")
        s.add("Device:LED", (x + 12, 80), {"A": f"{net}_A", "K": "GND"}, value=col, footprint=LED0603)
    resistor(s, (250, 60), "3V3_IO", "LED_PWR_A", "2.2k")
    s.add("Device:LED", (262, 80), {"A": "LED_PWR_A", "K": "GND"}, value="red PWR", footprint=LED0603)
    # SDI add-on header
    pins = ["5V_SYS", "5V_SYS", "3V3_IO", "3V3_IO", "GND", "GND"]
    pins += [f"DVP_D{i}" for i in range(16)] + ["DVP_PCLK", "GND", "DVP_HSYNC", "DVP_VSYNC"]
    pins += ["SDI_I2C_SCL", "SDI_I2C_SDA", "SDI_UART_TX", "SDI_UART_RX"] + [f"SDI_GPIO{i}" for i in range(1, 9)]
    pins += ["GND", "GND"]
    assert len(pins) == 40
    s.add("Connector_Generic:Conn_02x20_Odd_Even", (330, 140), {str(i + 1): n for i, n in enumerate(pins)},
          value="SDI add-on (DNP)", ref="J", dnp=True,
          footprint="Connector_PinHeader_2.00mm:PinHeader_2x20_P2.00mm_Vertical")
    for i in range(4):
        s.add("Mechanical:MountingHole_Pad", (60 + 15 * i, 200), {"1": "GND"}, ref="H",
              footprint="MountingHole:MountingHole_3.2mm_M3_Pad_Via")
    return s
