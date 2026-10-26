# HDMI-in relay carrier board: rev A electrical spec (draft 2, Oct 22, 2026)

This is what the rev A schematic implements, block by block. Choices come from [DESIGN.md](DESIGN.md) and the costs
from [COST.md](COST.md). **The schematic is in [kicad/](kicad/README.md)**: ERC passes, every module pin assigned.

**Draft 2 (Oct 22): the module is now the Radxa CM3 (RK3566)**, replacing the MYIR MYC-LR3568, because its full
pinout, power design and layout guide are public. MYIR only gives its pinout on request. The MYIR email draft is
kept as a fallback.

## References used

| Document | Where | Used for |
|---|---|---|
| Radxa CM3 datasheet rev 1.2 | [`datasheets/Radxa_CM3_Datasheet.pdf`](datasheets/Radxa_CM3_Datasheet.pdf) ([Radxa](https://dl.radxa.com/cm3/docs/radxa_cm3_datasheet.pdf)) | Connector pinout (appendix C), power, USB, HDMI, PCIe, MIPI, recovery, layout rules |
| Radxa CM3 pinout change history V1.3 → V1.32 | [`datasheets/radxa_cm3_v1300_to_1320_pinout.xlsx`](datasheets/radxa_cm3_v1300_to_1320_pinout.xlsx) ([Radxa](https://dl.radxa.com/cm3/docs/radxa_cm3_v1300_to_1320_pinout.xlsx)) | **Five pins moved after the datasheet's V1.3 tables**; we follow V1.32+ |
| Radxa CM3 V1.322 schematic | [`datasheets/radxa_cm3_v1.322_schematic.pdf`](datasheets/radxa_cm3_v1.322_schematic.pdf) ([Radxa](https://dl.radxa.com/cm3/docs/v1.322/radxa_cm3_v1.322_schematic.pdf)) | What's already on the module |
| Radxa CM3 IO board B2B connector data | [`datasheets/radxa_cm3_io_board_b2b_connector_20230718.asc`](datasheets/radxa_cm3_io_board_b2b_connector_20230718.asc) ([Radxa](https://dl.radxa.com/cm3/io_board/radxa_cm3_io_board_b2b_connector_20230718.asc)) | Connector placement on a working carrier (to check against ours) |
| RK3568/RK3566 datasheet V2.3 | [`datasheets/RK3568_Datasheet.pdf`](datasheets/RK3568_Datasheet.pdf) ([rockchip.fr](https://rockchip.fr/RK3568%20datasheet%20V2.3.pdf)) | Pin muxing, I/O voltages, SARADC |
| RK628D datasheet V1.0 | [`datasheets/RK628D_Datasheet_V1.0.pdf`](datasheets/RK628D_Datasheet_V1.0.pdf) ([rockchip.fr](https://rockchip.fr/RK628D%20datasheet%20V1.0.pdf)) | Pins, rails, I2C address, package |
| DshanPi-A1 schematic V1.1 (RK3576 + RK628D, a shipping board) | [`datasheets/DshanPi-A1-RK3576-SCH_V1.1.pdf`](datasheets/DshanPi-A1-RK3576-SCH_V1.1.pdf) ([100ask](https://dl.100ask.net/Hardware/MPU/RK3576-DshanPi-A1/DshanPi-A1-RK3576-SCH_V1.1.pdf)), pages 31–32 | **Reference circuit for the RK628D and the HDMI input.** We copy it, not invent it. |
| CH224, SY8303, TPS563201, RCLAMP0524P, AO3401A datasheets | [`datasheets/`](datasheets/) | Power and protection parts |

**Still to get:** the Rockchip RK628D hardware design guide (through a Rockchip distributor), which would confirm
the 1.1 V current and trace-length rules.

## 1. The module: Radxa CM3

From the Radxa CM3 datasheet:
- **Part:** RM116-D2E16W0, with 2 GB RAM, 16 GB eMMC and no Wi-Fi. We use our own 2×2 RTL8822CE card, which is
  better as an access point than the module's 1×1 Wi-Fi. Radxa commits to production until at least September 2029.
- **Connectors:** three Hirose DF40 100-pin. On the carrier, three **DF40C-100DS-0.4V(51)** receptacles (1.5 mm stack,
  as on Radxa's own IO board). Four M2.5 mounting holes. Module 55 × 40 mm.
- **Power: one 5 V input**, 3.8–5.2 V, up to 3 A, on six pins. The module's RK817 power IC handles its own power-up
  order, and the carrier doesn't need to manage it (datasheet 3.1.2). The module outputs +3V3 and +1V8 (200 mA each)
  for references.
- **GPIO_VREF must be tied to the module's +3V3** (or +1V8). We use 3.3 V, matching the RK628D's I/O.
- **Already on the module:**
  - the Ethernet PHY (RTL8211F, with common-mode chokes)
  - HDMI DDC/CEC level shifting, and the HPD pull-down and series resistor
  - eMMC and the power IC
- **Recovery:** SARADC_VIN0 held low at power-up enters Rockusb recovery for flashing over USB OTG (datasheet 3.11).
  It needs a 10 kΩ pull-up to 1.8 V and 1 nF. USB_OTG0_VBUSDET must be high (2.7–3.3 V) for device mode.
- **Software:** Radxa Debian and Android images, and an **official OpenWrt build (25.12) for the Radxa CM3 IO
  board** ([Radxa downloads](https://docs.radxa.com/en/som/cm/cm3/download)). Our relay runs on OpenWrt-based
  FriendlyWrt today, so it moves to that OpenWrt target with a device tree for our carrier.
- **Module revision:** the datasheet's pin tables are for V1.3. Radxa's change history moves five pins in V1.31 and
  V1.32 (J69-37, J69-93, J1-14, J1-26, J1-34). **This carrier follows V1.32 and later.** Older modules would put
  VIN_SENSE, RECOVERY, the SDI UART TX and BT_DISABLE on the wrong pins.

## 2. Block diagram (carrier)

```
 VIN 6–17 V (DC, NP-F) ──┐
                          ├─► Schottky OR ───► protection ─┬─► SY8303 ─► 5V_SOM (3 A) ─► Radxa CM3
 USB-C (PD 9 V, CH224A) ──┘  (USB via P-FET)   (TVS, fuse)  └─► SY8303 ─► 5V_SYS (3 A) ─┬─► TPS563201 ─► 3V3_IO ─► M.2, RK628D I/O
   └─ USB 2.0 D+/D− ─► CM3 USB OTG (flashing, debug)                                     ├─► TPS563201 ─► 1V1_628 ─► RK628D core/PHY
                                                                                          └─► AP22804 ─► HDMI OUT pin 18

 HDMI IN ─► ESD ─► RK628D ──CSI-2 ×4──► CM3 CSI RX            CM3 HDMI TX ─► ESD ─► HDMI OUT
             │      ├─ I2C, RESET, INT, PWR_EN ◄─► CM3 GPIO
             │      ├─ I2S audio ─► test pads (CM3 I2S pins are shared with the DVP input)
             │      └─ CEC, DDC, HPD (handled by the RK628D; CEC also to a CM3 GPIO through a 0 Ω option)
 CM3 Ethernet PHY (on module) ─► MDI ×4 ─► RJ45 with magnetics
 CM3 PCIe 2.1 ×1 + USB 2.0 host ─► M.2 E-key 2230 (RTL8822CE: Wi-Fi on PCIe, Bluetooth on USB) ─► 2 × IPEX ─► RP-SMA
 CM3 DVP 16-bit + I2C + UART + 8 GPIO ─► 2 × 20 header for the SDI add-on board (not fitted)
 Debug: 3-pin UART header · buttons: RESET, RECOVERY · LEDs: PWR, STATUS, WIFI
```

## 3. Power

### Inputs

- **DC jack (5.5 × 2.0 mm, CUI PJ-002AH; not a locking type), 6–17 V.** Covers D-tap, V-mount, NP-F and 12 V supplies. Rated 3 A.
- **USB-C.** A CH224A asks the charger for **9 V** (6.8 kΩ on CFG1); WCH recommends it over the CH224K for new
  designs, same pinout, VBUS rated 32 V instead of 13.5 V. Its power-good pin goes to a module GPIO, and also turns
  on a P-FET that passes VBUS to the box only once 9 V is agreed. 9 V rather than 12 V because many chargers skip 12 V.
  **5 V-only chargers aren't supported:** the 5 V buck can't make 5 V from 5 V. A sensing pin tells the software,
  and the status LED blinks a "charger too weak" code. This saves a buck-boost converter, about $1.50 *est.*;
  every USB-C PD charger offers 9 V. The USB-C D+/D− also go to the module's USB OTG port for flashing.
- **Combining the inputs:** one SS54 Schottky diode per input (DC, NP-F, USB-C), so the higher voltage wins, no
  input back-feeds another, and a reversed DC lead is blocked. Cheaper than P-FET ideal diodes; costs about 0.35 V
  (0.35 W at 1 A).
- **Protection:**
  - SMBJ20CA TVS on VIN (D-tap batteries sit up to 16.8 V)
  - 3 A resettable fuse
  - input bulk capacitor: 47 µF / 35 V aluminium electrolytic (C102, Lelon RVT35V47M6X8, 6.3 × 7.7 mm)

### Rails

| Rail | Source | Load | Rated | Part (first choice) |
|---|---|---|---|---|
| VIN | DC jack, NP-F slot or USB-C | — | 6–17 V, 2 A typical | — |
| 5V_SOM | SY8303AIC buck, 500 kHz | Radxa CM3 only (3.8–5.2 V, up to 3 A) | **1.5–2 A sustained on rev A** (thermal, below); 3 A peaks | [LCSC C97054](https://www.lcsc.com/product-detail/C97054.html) |
| 5V_SYS | Second SY8303AIC, 500 kHz | 3V3_IO, 1V1_628, HDMI out 5 V | 3 A | Same part |
| 3V3_IO | TPS563201 buck from 5V_SYS | M.2 Wi-Fi (about 1 A peak), RK628D I/O and 3.3 V analog, LEDs | 3 A | [LCSC C116592](https://www.lcsc.com/product-detail/C116592.html) |
| RK628D_3V3 | P-FET switch from 3V3_IO, on when the module drives `RK628D_PWR_EN` | RK628D I/O and analog 3.3 V | — | AO3401A + MMBT3904, as in the DshanPi reference |
| 1V1_628 | TPS563201 buck from 5V_SYS, enabled about 1 ms after RK628D_3V3 (RC on EN) | RK628D core, PLL and PHY 1.1 V supplies | 3 A | Same part as 3V3_IO. The TPS563201 needs 4.5 V in, so it runs from 5V_SYS. |
| HDMITX_5V | AP22804 current-limited switch from 5V_SYS | HDMI OUT pin 18 | 55 mA (HDMI spec) | — |

**Notes:**
- The RK628D needs **only 1.1 V and 3.3 V** (datasheet table 2-2). Its 2.5 V eFuse supply must be low in normal
  use: tied to ground through 100 Ω with 100 nF, as in the reference.
- Its analog 3.3 V and 1.1 V supplies each get a ferrite bead and their own capacitors, copying the DshanPi page 31.
- **Peak budget:** about 7 W typical. The module gets its own 15 W converter, because its 3 A maximum would
  otherwise share one converter with everything else.
- **5V_SOM thermal limit (rev A, REVIEW_FABLE_3.md M2).** U104 (TSOT23-8, no exposed pad, θJA 60 °C/W on a
  low-K test board) loses about 1.4 W at 3 A from 12 V. Even with its four thermal vias into In1 and the roof vent
  over it, that's an estimated 100 °C or more in a 40 °C case. Its thermal shutdown is at 150 °C.
  - **Rated use:** the RK3566 module draws about 1.5–2 A sustained under encode plus Wi-Fi, about 64–80 °C.
  - **Check:** the pilot units' thermocouple test (PRODUCTION.md step 9) has to confirm it.
  - **Don't power USB loads from the module's 5 V.** The module's six DF40 contacts carry 1.8 A at 0.3 A each.
  - **Rev B:** a 5 V buck with an exposed pad (TPS56637 class) for both U103 and U104.
- **Power-up order:** the CM3 sequences itself from its single 5 V input (datasheet 3.1.2). 3V3_IO comes up about
  10 ms after 5V_SYS.

### Battery (Oct 22): an NP-F slot, not a built-in pack

**Decision for rev A: no lithium cells inside.** Instead:
- **An NP-F battery slot on the back of the case.** Sony NP-F batteries are already common on sets.
  - Parts: a plate with two spring contacts, wired to VIN. About $3 *est.*
  - Runtime at about 6 W: an NP-F570 (about 16 Wh) gives about 2.5 h; an NP-F970 (about 47 Wh) about 7 h.
- **A USB-C PD power bank** works already: anything offering 9 or 12 V.
- **D-tap and V-mount** work already, through the DC jack.
- **Swapping without a reboot:** the diode OR means a second source can be plugged in before the first is removed.

**Change this makes:** VIN minimum goes from 7 V to **6.0 V**, because NP-F cells end discharge around 6 V. The
SY8303 runs from 4.5 V, and 5 V out stays in regulation down to about 5.5 V at VIN (after the input diode), so
about 5.9 V at the battery. `VIN_SENSE` shows the battery
level in the apps, and the software shuts down cleanly below 6.0 V.

**Why not a built-in pack:**
- **Parts:** 2 × 18650 cells, a 2S charger, protection and balancing, and a temperature sensor add about $10–14
  *est.* per unit, plus a larger case.
- **Certification:** the pack needs UN38.3 transport testing and IEC 62133 safety testing. Buying an
  already-certified pack avoids repeating the tests, but costs more per pack.
- **Shipping:** lithium batteries in equipment ship under UN3481, with paperwork and air-freight limits.
- Revisit as a "Pro" version if customers ask for it.

## 4. HDMI input (RK628D)

This copies the DshanPi-A1 circuit (schematic pages 31–32), with our changes marked.

- **Connector:** full-size HDMI type A, SMD with through-hole shell legs (Molex 208658-1001, [LCSC C916313](https://www.lcsc.com/product-detail/C916313.html); same part for HDMI OUT).
  The case clamps the cable for strain relief; there's no locking connector at this price.
- **Static protection:**
  - each RCLAMP0524P line has copper straight across its pad pair (pins 6/7/9/10 are NC on this part)
  - two RCLAMP0524P on the four high-speed pairs ([LCSC C907837](https://lcsc.com/product-detail/TVS_TECH-PUBLIC-RCLAMP0524P_C907837.html))
  - a third RCLAMP0524P on HPD, CEC, SCL and SDA (one part number instead of the reference's WE05MFC)
- **Hot-plug detect:** the RK628D drives HPD to the camera directly, through 22 Ω. Camera-present detection: the
  connector's +5 V turns on an NPN (MMBT3904), which pulls `RK628D_PLUGIN_DET` low for a module GPIO. Software
  raises HPD only after writing the EDID, which is how the reference board works.
- **EDID:** in the RK628D's on-chip EDID memory, which software can read and write. **No EEPROM is needed.** That
  saves the 24C02 in COST.md, and still allows the Blackmagic vendor block that HDMI camera control needs.
- **DDC:** 22 Ω series resistors and diodes as in the reference, pulled up on the HDMI 5 V side.
- **CEC:** 27 kΩ pull-up to 3.3 V, into the RK628D's HDMI-receiver CEC pin.
  - **Our change:** a second path, through a 0 Ω resistor that isn't fitted, to a module GPIO. That way the module
    can bit-bang CEC if the RK628D driver doesn't expose Blackmagic's vendor messages.
- **Clock:** its own 24 MHz crystal. The reference (DshanPi p.31) allows the crystal when HDMI_TX and GVI_TX are
  unused, which is the case here (the SoC-clock option is the one it marks for all scenarios); the module's clock
  output isn't guaranteed to be on a pin.
- **I2C address:** I2C_ADDR strapped low, giving 7-bit 0x50 (0x51 with a strap, as in the reference). This shares
  nothing else on that I2C bus.
- **Control signals to the module:**
  - `RK628D_RESET`, `RK628D_INT`, `RK628D_PWR_EN`, `RK628D_PLUGIN_DET`
  - I2C SCL and SDA
- **Video out to the module:** MIPI CSI-2, 4 data lanes plus clock, on the RK628D's DSI0/CSI pins, routed as
  100 Ω differential pairs into the module's CSI receiver in 4-lane mode. 1080p60 YUV422 needs about 2.4 Gb/s with
  blanking; four lanes at 1.2 Gb/s give 4.8.
- **Audio out:** I2S (SCLK, LRCK, D0, MCLK) to a module I2S port.
- **Unused** (pads only, no connector): RK628D HDMI TX, LVDS/GVI, parallel RGB.

## 5. Other interfaces

| Block | Implementation | Notes |
|---|---|---|
| **HDMI OUT** | CM3 HDMI 2.0 TX → RCLAMP0524P ×3 → full-size HDMI A | 5 V on pin 18 from the current-limited switch. DDC and HPD go straight to the module, which level-shifts them (CM3 datasheet 3.5.1); 2.2 kΩ DDC pull-ups to the HDMI 5 V. CEC not connected. |
| **Ethernet** | PHY on the CM3 → 4 MDI pairs → gigabit jack with magnetics | Centre taps to ground through 1 µF each (voltage-mode PHY, CM3 datasheet 3.4). Jack LEDs unused in rev A. |
| **Wi-Fi + Bluetooth** | M.2 2230 E-key socket | **Wi-Fi uses the PCIe lane; Bluetooth on the RTL8822CE M.2 card uses USB 2.0.** So the socket gets PCIe ×1 (from the module's PCIe 2.1 combo lane), one module USB 2.0 host port, `PERST#`, `CLKREQ#`, `WAKE#`, `W_DISABLE1#/2#` to GPIOs, and 3V3_IO. Two IPEX leads to two RP-SMA bulkheads. |
| **USB-C data** | Module USB 2.0 OTG | For flashing (Rockchip's USB tool) and a USB network gadget for debugging. ESD on D+/D−. |
| **Debug** | 3-pin 2.54 mm header: TX, RX, GND | UART2_M0 on J69 pins 51/55, the boot console. 1.5 Mb/s, as on today's R5C. |
| **Buttons** | RESET (PMIC_RESET_KEY), RECOVERY (SARADC_VIN0 to ground) | Small tact switches, inside the case. No MASKROM button: an empty eMMC drops into maskrom by itself, and RECOVERY covers reflashing. |
| **LEDs** | PWR (from 5V_SYS), STATUS, WIFI (GPIO) | Behind light pipes, as on the R5C case. |
| **SDI add-on header** | 2 × 20 pin, 2.0 mm, not fitted | **Wired to the module's 16-bit DVP camera input**, plus pixel clock, HSYNC, VSYNC, I2C, UART, 8 GPIOs, 5V_SYS and 3V3_IO. An SDI receiver such as the GS2971A outputs a parallel BT.1120 bus, which is what a DVP input takes. So the SDI board needs no bridge chip, and the 4-lane camera input stays free for HDMI. On the CM3 the DVP pins are free: its own Ethernet uses GMAC1_M0, not the GMAC1_M1 pins the DVP shares. |

## 6. Board and layout rules

- **Outline: 120 × 100 mm**, four M3 holes, in the 3D-printed case (`case/`).
- **Front panel:** HDMI IN, HDMI OUT. **Rear panel:** USB-C, DC IN, battery lead, RJ45. **Left side:** 2 × RP-SMA.
  LEDs on top through light pipes.
- **Stackup:** 4 layers, JLCPCB's impedance-controlled 1.6 mm stack. L1 signals, L2 solid ground, L3 ground
  pour plus signals, L4 signals and power (JLC04161H-3313).
- **Impedances:**

  | Signals | Impedance |
  |---|---|
  | HDMI pairs, MIPI CSI pairs | 100 Ω differential |
  | PCIe | 85 Ω differential |
  | USB | 90 Ω differential |
  | Ethernet MDI pairs | 100 Ω differential |

- **Length matching:** follow the CM3 datasheet's limits, which also give each signal's length inside the module.
  Within each pair: under 12 mil. MIPI data to clock: under 36 mil. HDMI clock to data: under 480 mil. Carrier
  runs: under 6 inches. Tighten the CSI side if the RK628D design guide says so.
- **No signal crosses a split in the ground plane.** HDMI and CSI stay on L1 over L2 with one via pair at most.
- **The module sits in the middle of the board**, with the RK628D between the HDMI IN jack and the module's CSI
  pads, so the CSI run is under 30 mm.
- **Heat:** a thermal pad from the module's top to the extrusion wall, through a lid boss. Copper pour and vias
  under the RK628D and the bucks.
- **Assembly:** SMD on both sides (62 parts on the bottom; JLCPCB two-sided assembly). Through-hole: the DC jack
  and HDMI shell legs (JLCPCB), the RJ45 magjack J301 (hand-fitted: no JLCPCB stock). The CM3 plugs in after assembly; Radxa recommends a fixture for fitting and removing it.

## 7. Module signal map (Radxa CM3, module revision V1.32+)

All of it is in [`kicad/gen/module.py`](kicad/gen/module.py), which fails the build if a pin is assigned twice or
left out. Pins not listed are ground or no-connect.

**I/O voltage (Oct 25 fix; corrected Oct 26).** On the CM3, GPIO0_D3–D6 (the oscillator domain, PMUIO0) are 1.8 V
only (CM3 V1.322 schematic p.7). GPIO0_B0–D2 (PMUIO2) follow GPIO_VREF on the V1.322 module (VCCA1V8_PMU_1: R12 0 Ω to
1V8_3.3V, R24 0 Ω to GPIO_VREF; R11 to 1.8 V not fitted), so they are 3.3 V on this carrier; the Oct 25 fix treated
them as 1.8 V, which was conservative. Everything that meets a 3.3 V part, a 3.3 V pull-up or an LED uses
PMUIO1 (GPIO0_A*), VCCIO5, VCCIO6 (GPIO_VREF = 3.3 V here) or VCCIO7. `kicad/checks/iolevels.py` checks every CM3
pin against its bank. PD_PG_N no longer reaches the module: GPIO0_B6 has a 2.2 kΩ pull-up on the module,
which held the USB-C VBUS gate (Q101) on.

**Device tree requirements** (all of them in `dt/rk3566-relay-carrier.dtso`, an overlay on Radxa's BSP
rk3566-radxa-cm3-io.dtb that also turns off the IO board's sdmmc0, SD/USB/CH482D regulators, LEDs and RTC, whose
GPIOs this carrier reuses). VCCIO_ACODEC (RK817 LDO4) set to 3.3 V and always on, with pmu-io-domains vccio1 =
3.3 V: BT_DISABLE#, PERST#, CLKREQ# and WAKE# sit in that domain. Their board pull-ups are not fitted (they back-fed the
unpowered bank), so the pinctrl must enable the SoC's pull-ups on CLKREQ# (GPIO1_B0) and WAKE# (GPIO1_B1). CSI
data-to-clock skew, counting the module's own lengths, is now at most 6.3 mm, about 40 ps (REVIEW_FABLE_2.md M1;
`kicad/gen/csimatch.py`). That's under 0.05 UI at 1.2 Gb/s, so no lane-rate cap is needed. Still check the CSI
CRC/ECC counters at bring-up. Keep GPIO0_D4 (TF_DET) low or unused: driven high,
it makes the module pull RK628D PLUGIN_DET low. The RK628D is described for the BSP's HDMI-RX to CSI-2 V4L2 driver
(`rockchip,rk628-csi-v4l2`), with the capture graph RK628D → csi2_dphy0 (full mode, 4 lanes) → mipi_csi2 →
rkcif_mipi_lvds. W_DISABLE1#/2# (GPIO0_A0, GPIO1_A4) are held high (radios on) by GPIO hogs with SoC pull-ups;
rfkill-gpio is ACPI-only in that kernel.

| Function | CM3 pin(s) | RK3566 function |
|---|---|---|
| CSI-2 D0–D3, CLK (4-lane) | J68: D0 117/115, D1 123/121, CLK0 129/127, D2 130/128, D3 136/134 | MIPI_CSI_RX (4-lane mode uses CLK0) |
| RK628D I2C SCL / SDA | J69 35 / 36 | I2C2_M1 (GPIO4_B5 / GPIO4_B4), the hardware I2C2 controller. VCCIO6 = GPIO_VREF, tied to 3.3 V |
| RK628D RESET_N | J1 10 | GPIO3_C2 (VCCIO5, 3.3 V) |
| RK628D PLUGIN_DET | J69 76 | GPIO0_A4 (PMUIO1, 3.3 V), SDMMC0_DET by default, an input |
| RK628D INT | J1 12 | GPIO3_C3 (VCCIO5, 3.3 V) |
| RK628D PWR_EN | J1 95 | GPIO0_C4 (PMUIO2 = GPIO_VREF, 3.3 V): drives an NPN base through 1 kΩ |
| CEC_GPIO (0 Ω option) | J68 151 | GPIO4_D1 (HDMI_TX_CEC pad, VCCIO7 at 3.3 V; on J68 to keep the trace short) |
| HDMI TX D0–D2, CLK | J68 182/184, 176/178, 170/172, 188/190 | HDMI_TX |
| HDMI HPD, DDC SDA / SCL | J68 153, 199 / 200 | Level-shifted on the module |
| Ethernet MDI0–3 | J69 12/10, 4/6, 11/9, 3/5 | On-module RTL8211F |
| PCIe TX, RX, REFCLK | J68 122/124, 116/118, 110/112 | PCIE20 (multi-PHY2). At J501: TX → C501/C502 (0 Ω) → PETp0/n0 (35/37); PERp0/n0 (41/43) → RX. PET is the host's transmit pair |
| PCIe PERST#, CLKREQ#, WAKE# | J68 109, J68 102, J1 38 | PCIE20_*_M2 (CLKREQ and WAKE must share one mux group) |
| WIFI_DISABLE#, BT_DISABLE# | J1 74, J1 40 | GPIO0_A0 (PMUIO1, 3.3 V), GPIO1_A4 (VCCIO1 = VCCIO_ACODEC: set to 3.3 V in the device tree) |
| USB to M.2 (Bluetooth) | J1 63/65 | USB2 HOST2 |
| USB OTG to USB-C (flashing) | J68 105/103; VBUSDET J1 97 | USB_OTG0 |
| VIN_SENSE | J1 14 | SARADC_VIN3 (0–1.8 V) |
| RECOVERY button | J69 93 | SARADC_VIN0 |
| RESET button | J69 100 | PMIC_RESET_KEY |
| LED_STATUS, LED_WIFI | J69 34, 75 | GPIO4_B1 (VCCIO6, 3.3 V), GPIO0_A5 (PMUIO1, 3.3 V); each sources its LED through 150 Ω |
| Debug UART RX / TX | J69 51 / 55 | UART2_M0 (PMUIO2 = GPIO_VREF: **3.3 V levels**, use a 3.3 V USB-UART adapter; measure TX idle on the first board) |
| DVP D0–D7 | J69 41, 49, 26, 25, 27, 45, 47, 54 | CIF_D0–D7 |
| DVP D8–D13 | J1 75, 77, 79, 81, 83, 85 | CIF_D8–D13 |
| DVP D14, D15, HSYNC, VSYNC, PCLK | J69 21, 91, 89, 95, 97 | CIF_D14, CIF_D15, CIF_HREF, CIF_VSYNC, CIF_CLKIN |
| SDI I2C SCL / SDA | J69 38 / 44 | I2C4_M0 |
| SDI UART TX / RX | J69 37 / J1 36 | UART9_M1 |
| SDI GPIO1, 3–7 | J69 29, 39, 40; J1 4, 6, 8 | GPIO4_A7, GPIO4_A6, GPIO4_B0, GPIO3_A1, GPIO3_B4, GPIO3_C1. GPIO2 and GPIO8 (header pins 32, 38) are unused: their CM3 pins now drive LED_STATUS and RK628D_RESET_N |
| 5V_SOM | J69 77, 79, 81, 83, 85, 87 | Module supply |
| GPIO_VREF + module 3.3 V out | J69 78, 84, 86 | Tied together (3.3 V I/O) |
| Module 1.8 V out | J69 88, 90 | Pull-up for RECOVERY |

**Not connected:** the RK628D's I2S audio (to test pads). The CM3's usable I2S pins are the DVP pins, so HDMI audio
and the SDI input can't both use them. The apps don't use audio yet.

## Next steps

1. **Get a quote from Radxa** (or Arace / RS) for RM116-D2E16W0 at 5, 100 and 500 pieces.
2. **Check the receptacle footprints** against Radxa's IO-board connector placement data, which is in
   `datasheets/`: pin 1 orientation, the spacing between the three connectors, and mounting-hole positions.
3. **Bring up the relay software on Radxa's OpenWrt build**, on a CM3 IO board, before our carrier exists.
4. Footprints, values and layout: see [kicad/README.md](kicad/README.md).
