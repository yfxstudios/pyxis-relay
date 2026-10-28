"""Sheets of the SDI add-on: the receiver, power, and the J602 interface (../../DESIGN.md).

Circuit values follow the GS2971A datasheet Rev. 3, figure 5-1 (typical application circuit).
"""
from parts import (C0603, C0805, GS2971A, L0402, LED0603, R0402, SY8089, cap, resistor, testpoint)

# receiver outputs that leave the board (through 22R at the receiver) -> J602 net
# 20-bit mode: DOUT19:10 = luma (data stream 1), DOUT9:0 = chroma (data stream 2). The DVP takes 16 bits: the top
# 8 of each (BT.1120 16-bit, 8-bit Y + 8-bit C).
TO_DVP = {f"DOUT{19 - i}": f"DVP_D{15 - i}" for i in range(8)}
TO_DVP.update({f"DOUT{9 - i}": f"DVP_D{7 - i}" for i in range(8)})
TO_DVP.update({"PCLK": "DVP_PCLK", "STAT0": "DVP_HSYNC", "STAT1": "DVP_VSYNC"})


def receiver(project):
    from sch import Sheet
    s = Sheet(project, "receiver", "SDI input and GS2971A receiver", 100, paper="A2")
    s.text("SDI IN (75 ohm BNC) -> return-loss network -> GS2971A (integrated adaptive equalizer, reclocker,\n"
           "SMPTE processing) -> 20-bit parallel video.  Values from the GS2971A datasheet figure 5-1.\n"
           "Layout: 75 ohm trace from the BNC, ground removed under the input parts, no vias in the SDI path.", (20, 15), 2)

    conn = {
        "C1": "SDI_P", "D1": "SDI_N", "F1": "AGCP", "G1": "AGCN",
        "A1": "VBG", "A2": "LF", "A3": "LB_CONT", "A4": "VCO_VDD",
        "K6": "XTAL1", "J6": "XTAL2", "H6": "XTAL_OUT",
        "C7": "GS_RESET_N", "D8": "GS_JTAG_HOST", "F7": "GSPI_CS_N", "F8": "GSPI_SCLK", "E8": "GSPI_SDIN",
        "E7": "GSPI_SDOUT",
        "H7": "GS_20BIT", "H8": "GS_IOPROC", "H3": "GS_AUDIO_EN", "H5": "GS_TIM_861", "D7": "GS_SW_EN",
        "K2": "GS_STANDBY", "J2": "GS_SDO_EN", "G3": "GS_RC_BYP", "G7": "SMPTE_BYPASS", "G8": "DVB_ASI",
        "J1": None, "K1": None, "B3": None, "F2": None,                 # no loop-out; RSV pins unconnected
        "A8": "GS_PCLK",
        "A5": "GS_STAT0", "A6": "GS_STAT1", "B5": "GS_STAT2", "B6": "SDI_LOCKED", "C5": "GS_STAT4", "C6": "GS_STAT5",
        "J3": "AOUT_1_2", "K3": "AOUT_3_4", "J5": "AOUT_5_6", "K5": "AOUT_7_8", "J4": "ACLK", "H4": "WCLK", "K4": "AMCLK",
        "D6": "1V2", "B2": "1V2_A", "B1": "3V3_A", "E1": "3V3_A", "H1": "3V3_A", "A7": "3V3",
        "B4": "GND", "C2": "GND", "D4": "GND", "D5": "GND", "B7": "GND", "E2": "GND", "H2": "GND",
    }
    dout = {"B8": 19, "A9": 18, "A10": 17, "B9": 16, "B10": 15, "C9": 14, "C10": 13, "C8": 12, "E10": 11, "E9": 10,
            "F10": 9, "F9": 8, "H10": 7, "H9": 6, "J10": 5, "J9": 4, "K10": 3, "K9": 2, "J8": 1, "K8": 0}
    for ball, i in dout.items():
        conn[ball] = f"GS_DOUT{i}" if f"DOUT{i}" in TO_DVP else None    # DOUT11, 10, 1, 0: unused (the DVP has 16 bits)
    s.add(GS2971A, (200, 170), conn, ref="U")

    # SDI input: BNC -> 6.2 nH || 75R -> 75R termination, 1 uF into SDI; SDI-bar 1 uF to 37.4R (figure 5-1)
    s.add("Connector:Conn_Coaxial", (40, 100), {"1": "SDI_BNC", "2": "GND"}, value="SDI IN", ref="J",
          footprint="sdi:BNC_Samtec_BNC7T-J-P-xx-RA-BH1_Horizontal",
          Note="Samtec BNC7T-J-P-HN-RA-BH1: true 75 ohm, 12G, right-angle bulkhead PCB jack (DigiKey; hand-fitted). "
               "The thread passes through the case wall (4 mm max) with nut and lock washer")
    s.add("Device:L", (60, 90), {"1": "SDI_BNC", "2": "SDI_TERM"}, value="6.2nH", footprint=L0402,
          Note="Return-loss compensation, high-Q 0402 RF inductor")
    resistor(s, (60, 110), "SDI_BNC", "SDI_TERM", "75R 1%")
    resistor(s, (80, 120), "SDI_TERM", "GND", "75R 1%")
    cap(s, (100, 100), "SDI_TERM", "SDI_P", "1uF", Note="0402 X7R, as small a pad as the trace width allows")
    cap(s, (100, 130), "SDI_REF", "SDI_N", "1uF")
    resistor(s, (100, 150), "SDI_REF", "GND", "37.4R 1%")
    # equalizer AGC: 470 nF across AGCP/AGCN and 470 nF from AGCN to ground
    cap(s, (120, 60), "AGCP", "AGCN", "470nF")
    cap(s, (120, 75), "AGCN", "GND", "470nF")
    # reclocker: band gap and loop filter caps; LB_CONT floating (nominal loop bandwidth), options to tie it
    cap(s, (60, 175), "VBG", "GND", "1uF")
    cap(s, (75, 175), "LF", "GND", "47nF", Note="C0G/NP0")
    resistor(s, (60, 195), "LB_CONT", "GND", "0R", dnp=True, Note="Fit to double the PLL bandwidth")
    resistor(s, (75, 195), "3V3_A", "LB_CONT", "0R", dnp=True, Note="Fit to halve the PLL bandwidth")
    # VCO supply: 1.2 V analog through 105R 1% with 33 uF at the ball (VCO_VDD is about 0.7 V)
    resistor(s, (60, 215), "1V2_A", "VCO_VDD", "105R 1%")
    cap(s, (75, 215), "VCO_VDD", "GND", "33uF", footprint=C0805, Note="Tantalum or MLCC, place at ball A4")
    s.flag("VCO_VDD", (90, 215))
    # 27 MHz reference: crystal, ESR 50R max, +-100 ppm total; 16 pF total per side including the board
    s.add("Device:Crystal_GND24", (60, 245), {"1": "XTAL1", "3": "XTAL2", "2": "GND", "4": "GND"}, value="27MHz",
          ref="Y", footprint="Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
          Note="27 MHz, ESR <= 50 ohm, +-100 ppm total (GS2971A 4.6); CL about 8-10 pF")
    cap(s, (45, 260), "XTAL1", "GND", "15pF", Note="C0G; 16 pF total with the board")
    cap(s, (75, 260), "XTAL2", "GND", "15pF", Note="C0G; 16 pF total with the board")
    testpoint(s, (90, 245), "XTAL_OUT")

    # strap pins (all have a GSPI override): 20-bit bus, processing on, audio on, H:V:F timing, normal operation
    straps = [("GS_20BIT", "3V3"), ("GS_IOPROC", "3V3"), ("GS_AUDIO_EN", "3V3"), ("GS_TIM_861", "GND"),
              ("GS_SW_EN", "GND"), ("GS_STANDBY", "GND"), ("GS_SDO_EN", "GND"), ("GS_RC_BYP", "GND"),
              ("GS_JTAG_HOST", "GND")]
    for i, (net, to) in enumerate(straps):
        a, b = (to, net) if to == "3V3" else (net, to)
        resistor(s, (330 + 15 * (i % 5), 60 + 20 * (i // 5)), a, b, "10k")
    resistor(s, (330, 110), "3V3", "GSPI_CS_N", "10k", Note="GSPI deselected until the host drives it")
    resistor(s, (345, 110), "GS_RESET_N", "GND", "10k", Note="Receiver held in reset until the host releases it")
    # status and audio to test pads (no free I2S on the relay, DESIGN.md "Audio")
    for i, net in enumerate(["SMPTE_BYPASS", "DVB_ASI", "GS_STAT2", "GS_STAT4", "GS_STAT5", "AOUT_1_2", "AOUT_3_4",
                             "AOUT_5_6", "AOUT_7_8", "ACLK", "WCLK", "AMCLK"]):
        testpoint(s, (330 + 15 * (i % 6), 140 + 15 * (i // 6)), net)
    # lock LED (STAT3 = LOCKED by default, 8 mA drive)
    resistor(s, (330, 185), "SDI_LOCKED", "LED_LOCK_A", "1k")
    s.add("Device:LED", (345, 185), {"A": "LED_LOCK_A", "K": "GND"}, value="green LOCK", footprint=LED0603)

    # decoupling at the balls (figure 5-1: 10 nF per supply ball group)
    for i, (net, n) in enumerate([("1V2", 4), ("1V2_A", 3), ("3V3_A", 3), ("3V3", 4)]):
        for k in range(n):
            cap(s, (60 + 15 * k, 290 + 15 * i), net, "GND", "10nF")
    return s


def power(project):
    from sch import Sheet
    s = Sheet(project, "power", "Power", 200)
    s.text("1.2 V core from 5V_SYS through a 2 A buck; 1.2 V analog and 3.3 V analog through 0R (or ferrite)\n"
           "filters as in GS2971A figure 5-1.  3.3 V I/O and analog from the relay's 3V3_IO.  About 0.8 W.", (20, 15), 2)
    cap(s, (40, 60), "5V_SYS", "GND", "22uF", footprint=C0805, Note="CIN: SY8089 datasheet")
    s.add(SY8089, (80, 60), {"4": "5V_SYS", "1": "5V_SYS", "3": "SW_1V2", "5": "FB_1V2", "2": "GND"}, ref="U")
    s.add("Device:L", (120, 50), {"1": "SW_1V2", "2": "1V2"}, value="2.2uH", ref="L",
          footprint="Inductor_SMD:L_Taiyo-Yuden_NR-30xx", Note="2.2 uH, Isat >= 1 A")
    resistor(s, (140, 60), "1V2", "FB_1V2", "100k 1%", Note="Vout = 0.6 V x (1 + 100k/100k) = 1.2 V (SY8089 pin table)")
    cap(s, (125, 70), "1V2", "FB_1V2", "22pF", Note="Feed-forward across R1, as in the SY8089 typical circuit")
    resistor(s, (140, 80), "FB_1V2", "GND", "100k 1%")
    cap(s, (155, 60), "1V2", "GND", "22uF", footprint=C0805, Note="COUT 2 x 22 uF: SY8089 datasheet")
    cap(s, (165, 80), "1V2", "GND", "22uF", footprint=C0805)
    cap(s, (170, 60), "1V2", "GND", "1uF")
    # analog 1.2 V
    resistor(s, (60, 120), "1V2", "1V2_A", "0R", Note="Or a 0402 ferrite (600R at 100 MHz)")
    cap(s, (80, 120), "1V2_A", "GND", "1uF")
    # 3.3 V: digital I/O straight from 3V3_IO; analog (EQ, A_VDD, buffer) through 0R
    resistor(s, (60, 150), "3V3_IO", "3V3", "0R")
    resistor(s, (60, 170), "3V3_IO", "3V3_A", "0R", Note="Or a 0402 ferrite (600R at 100 MHz)")
    cap(s, (40, 150), "3V3_IO", "GND", "10uF", footprint=C0805)
    cap(s, (80, 150), "3V3", "GND", "1uF")
    cap(s, (80, 170), "3V3_A", "GND", "1uF")
    cap(s, (95, 170), "3V3_A", "GND", "10uF", footprint=C0805)
    s.flag("5V_SYS", (40, 40))
    s.flag("3V3_IO", (40, 130))
    s.flag("GND", (40, 200))
    for i, net in enumerate(["1V2", "1V2_A", "3V3", "3V3_A"]):     # fed through the inductor and the 0R filters
        s.flag(net, (130 + 15 * i, 130))
    return s


def interface(project):
    from sch import Sheet
    s = Sheet(project, "interface", "Relay interface (J602)", 300)
    s.text("2 x 20, 2.00 mm socket on the underside, mating the relay's J602 (pin numbers as on the relay).\n"
           "22R series resistors at the receiver on every output that leaves the board.  GSPI is bit-banged on\n"
           "SDI_GPIO3-6; RESET on SDI_GPIO7; LOCKED to SDI_GPIO1.  The relay has 2.2k pull-ups on SDI_I2C.", (20, 15), 2)
    pins = ["5V_SYS", "5V_SYS", "3V3_IO", "3V3_IO", "GND", "GND"]
    pins += [f"DVP_D{i}" for i in range(16)] + ["DVP_PCLK", "GND", "DVP_HSYNC", "DVP_VSYNC"]
    pins += ["SDI_I2C_SCL", "SDI_I2C_SDA", None, None] + ["SDI_LOCKED", None, "GSPI_SCLK", "GSPI_SDIN", "GSPI_SDOUT",
                                                          "GSPI_CS_N", "GS_RESET_N", None]
    pins += ["GND", "GND"]
    assert len(pins) == 40
    s.add("Connector_Generic:Conn_02x20_Odd_Even", (220, 140), {str(i + 1): n for i, n in enumerate(pins)},
          value="To relay J602", ref="J", footprint="Connector_PinSocket_2.00mm:PinSocket_2x20_P2.00mm_Vertical",
          Note="Fit on the bottom side; mates the relay's 2 x 20 2.00 mm header J602")
    # series terminations, at the receiver
    for i, (src, dst) in enumerate(TO_DVP.items()):
        resistor(s, (80 + 20 * (i // 10), 60 + 15 * (i % 10)), "GS_" + src if src.startswith("DOUT") else
                 {"PCLK": "GS_PCLK", "STAT0": "GS_STAT0", "STAT1": "GS_STAT1"}[src], dst, "22R")
    # ID EEPROM: identifies the add-on to the relay software (address 0x50 on I2C4)
    s.add("Memory_EEPROM:24LC02", (330, 70), {"1": "GND", "2": "GND", "3": "GND", "4": "GND", "5": "SDI_I2C_SDA",
                                              "6": "SDI_I2C_SCL", "7": "GND", "8": "3V3"},
          ref="U", footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", Note="24C02 (any maker), board ID")
    cap(s, (350, 70), "3V3", "GND", "100nF")
    return s
