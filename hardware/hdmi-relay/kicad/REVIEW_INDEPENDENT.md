# Rev A: independent engineering review (Oct 25, 2026)

Scope: schematic (netlist exported from `relay.kicad_sch`), `relay.kicad_pcb`, the fab outputs in `fab/`, and the
generators in `gen/`, checked against the datasheets in `../datasheets/`. `TEST_REPORT.md` was read only after the
findings below were formed. No design, generator or fab file was changed.

**Status (Oct 25, later):**
- **Fixed:** M1, M2, M3, M5 and M8, by pin moves. Also M4 (in PRODUCTION.md), R501 from M12, and N1 (in the docs).
- **Accepted for rev A:** the rest. See TEST_REPORT.md, "Fixed on Oct 25".

## Verdict

The board is close, and most of it checks out against primary sources: the CM3 pinout (V1.32), the B2B footprints,
the RK628D ball map and its copy of the DshanPi reference, the CSI lane order and polarity, the regulators' dividers,
and the Ethernet, M.2, USB-C and HDMI pinouts. **It is not clean, though, and the earlier report's "I/O level audit:
clean" is wrong.** The RK3566 pins GPIO0_D3–D6 are in the oscillator domain (PMUIO0), which runs at **1.8 V only**.
The audit treated them as 3.3 V. Four carrier signals use 1.8 V-only pins against 3.3 V parts or pull-ups:
- RK628D_INT and RK628D_RESET_N;
- BT_DISABLE_N;
- the two status LEDs and PD_PG_N, on the 1.8 V PMUIO2 bank.

None of this stops the board powering up, booting or capturing (except the INT line, if software enables it). But:
- the STATUS and WIFI LEDs can never light;
- the USB-C "only pass VBUS after 9 V is agreed" gate can't turn off;
- RK628D_INT can drive 3.3 V into a 1.8 V PLL supply domain;
- the production flashing step (USB-C from a PC, no other supply) depends on undefined regulator behaviour.

**Recommendation:** if the order isn't in production yet, rev A is worth a re-spin of those nets. They are small
moves, plus one level shifter. If it is already in production, the board can be brought up with the workarounds
below. Every one of these must be fixed in rev B.

**Counts:** 0 Blocker, 5 Major, 8 Minor, 7 Note.

## Findings (most severe first)

| ID | Severity | Area | What's wrong | Evidence | Rev A bodge / workaround | Rev B fix |
|---|---|---|---|---|---|---|
| M1 | **Major** | CM3 ↔ RK628D | **RK628D_INT is wired straight to GPIO0_D5, a 1.8 V-only pin.** The RK628D drives INT at 3.3 V. Whenever INT is a push-pull output and high, it forces current through the RK3566 pad's clamp into PMUPLL_AVDD_1V8, the PMU PLL's analogue supply: over the absolute maximum, with a risk of upsetting or damaging the PLL domain. | CM3 V1.322 schematic p.7 (RK3566_G): the OSC box holding GPIO0_D3_d…D6_d is labelled "Operating Voltage = 1.8V Only (PMUPLL_AVDD_1V8)". The RK3568 datasheet pin table lists GPIO0_D3–D6 as **PMUIO0**. RK628D datasheet tables 2-2 and 3-2: VCCIO1 is 3.135–3.465 V only. DshanPi p.31 marks INT as "3.3V". Netlist: `RK628D_INT` = J703.18 ↔ U201.J3, with nothing in between. | Leave INT unused in software: keep GPIO0_D5 an input and never set the RK628D's INT as an output (poll its status over I2C). INT resets as an input with pull-down, so the SPIBOOT strap stays low. For a hardware bodge, cut the trace at J703.18 and fit a 10 kΩ in series: injection under 0.15 mA. That's still outside the spec but not destructive. | Move INT (and RESET, M8) to a 3.3 V CM3 pin: PMUIO1 GPIO0_A*, or a VCCIO6/7 GPIO_VREF pin. Or add a 1.8↔3.3 V translator (for example 74LVC2T45 or a TXS-type part). |
| M2 | **Major** | LEDs | **The STATUS (white) and WIFI (blue) LEDs can never light.** Both are driven by 1.8 V GPIOs through 1 kΩ, and the LEDs need about 2.6–3.1 V. Step 2 of the PRODUCTION.md test script will fail. | LED_STATUS = J701.30 = GPIO0_C5; LED_WIFI = J701.56 = GPIO0_B5. Both are PMUIO2, supplied from VCCA1V8_PMU_1 (CM3 schematic p.7, pin 1N15). LCSC C2290 KT-0603W: Vf 2.6–3.1 V. C2288 KT-0603B: Vf 3.1 V. GPIO0_B5 also carries the module's own 2.2 kΩ pull-up to 1.8 V (R9/R10, I2C2_M0). | No clean bodge. Either accept dark LEDs on rev A (the PWR LED works), or dead-bug an NPN per LED: base from the GPIO through 4.7 kΩ, LED from 3V3_IO through about 220 Ω to the collector. | Drive each LED with a low-side NPN or N-FET from 3V3_IO, or sink the LED into a 3.3 V-domain GPIO. |
| M3 | **Major** | Power, USB-C | **The USB-C VBUS gate (Q101) can't turn off.** PD_PG_N goes to GPIO0_B6, which has a 2.2 kΩ pull-up to 1.8 V on the module. When the CH224A's PG is released (no 9 V contract), Q101's gate isn't pulled to VBUS by R102 (100 kΩ). Instead it sits at about 1.96 V with the module powered, or near 0 V with the module unpowered. So V<sub>GS</sub> is about −3 to −5 V, Q101 stays on, and a 5 V-only source or a PC port feeds VIN. That contradicts REV_A_SPEC §3 ("passes VBUS … only once 9 V is agreed"). The pull-up also pushes 70–90 µA from VBUS into the module's 1.8 V PMU rail, including while the module is off. | CM3 schematic p.7: R9/R10 2.2 kΩ to VCCA1V8_PMU_1 on I2C2_SCL_M0/I2C2_SDA_M0. CM3 datasheet §3.9 item 3 ("pull-ups are already present"). Netlist: PD_PG_N = U102.10 (PG, open drain) + Q101.1 (gate) + R102 to VBUS_C + J701.58. | Cut the PD_PG_N trace into J701.58 (the CM3 side), so Q101 gates correctly. Software loses PD status. If it's needed, read it through a 100 kΩ/22 kΩ divider dead-bugged to the pad. | Keep PG → Q101 only. Report PD status to the SoC through a small N-FET or NPN (open drain into a 1.8 V GPIO), or read it from the CH224A over I2C (CFG2/CFG3 are SCL/SDA in single-resistor mode). |
| M4 | **Major** | Power, production | **Flashing over USB-C from a PC alone isn't a supported power case.** PRODUCTION.md station 4 says "Hold RECOVERY, plug USB-C" with no other supply. On 5 V (and with M3, Q101 conducts), VIN is about 4.5 V: 5 V minus the SS54 drop. At that VIN the SY8303 EN divider gives 4.5 × 39/139 = 1.27 V, under the 1.5 V guaranteed-high threshold. Both bucks run in dropout (about 4.3–4.4 V), and 5V_SYS is under the TPS563201's 4.5 V minimum. It may boot the CM3 or it may not, unit to unit. | SY8303 datasheet: V<sub>ENH</sub> max 1.5 V, UVLO max 4.35 V. TPS563201 datasheet: VIN 4.5–17 V. R111/R112 = 100k/39k. REV_A_SPEC §3 itself says 5 V sources aren't supported. | Flash with 12 V on the DC jack **and** USB-C to the PC (data only). Update station 4 and the bring-up checklist. | If flashing from USB power alone is wanted, OR VBUS (5 V) into 5V_SOM through an ideal-diode or load-switch path. Otherwise just document it. |
| M5 | **Major** | M.2, CM3 | **BT_DISABLE_N is on GPIO0_D3 (1.8 V only) with R505 (10 kΩ) pulled up to 3V3_IO.** Whenever the pin isn't driving low, about 0.1 mA flows through the pad clamp into PMUPLL_AVDD_1V8. A 1.8 V high is also below the usual 3.3 V-logic V<sub>IH</sub> for W_DISABLE2#, so Bluetooth may read as disabled. | Same evidence as M1 (OSC/PMUIO0, 1.8 V only). Netlist: BT_DISABLE_N = J703.34 (GPIO0_D3) + J501.54 + R505 to 3V3_IO. | Remove R505 (0402). Drive GPIO0_D3 low only to disable; otherwise leave it as an input. If BT then stays disabled, the card has no pull-up of its own: tie J501.54 high through 10 kΩ to 3V3_IO and give up software control. | Move W_DISABLE2# to a 3.3 V GPIO, or use an open-drain N-FET with the pull-up on the 3.3 V side. |
| M6 | Minor | CSI | **CSI lane-to-clock skew, counting the module's internal lengths, is about 24 mm (about 950 mil).** The CM3's rule is under 36 mil, and the carrier alone is already 7.35 mm (289 mil). Total lengths (carrier + module): CLK0 69.0, D0 90.4, D1 66.8, D2 65.8, D3 93.2 mm. At 1080p60 YUV422 (about 0.6–0.75 Gb/s per lane) that is about 0.1 UI, and about 0.19 UI at 1.2 Gb/s. | CM3 datasheet §3.6 (lines 1068–1096: "Data to clock mismatch <36mil", module lengths CLK0 about 1398 mil, D0 about 2404, D1 about 1392, D2 about 1563, D3 about 2522). Carrier lengths measured from the board: CLK 33.50, D0 29.38, D1 31.44, D2 26.15, D3 29.16 mm. | Run the RK628D's CSI at the lowest lane rate that carries the format. Check for CRC/ECC errors at bring-up. | Length-match the **totals** (carrier + module), not just the carrier: lengthen CLK0, D1 and D2, or shorten D0 and D3 where possible. |
| M7 | Minor | HDMI out | **The AP22804's current limit is 2.7–3.3 A** (short-circuit 0.45 A), not the "55 mA" the spec implies. A faulty cable or sink can pull close to 3 A from 5V_SYS, which also feeds the 3V3_IO and 1V1_628 bucks. HDMI asks the source to limit +5 V to 0.5 A. | AP22804 datasheet: I<sub>LIMIT</sub> 2.7–3.0–3.3 A, I<sub>SHORT</sub> 0.45 A. The LCSC C3001659 listing also says 2.5 A. | None needed for bring-up. | A switch in the 0.5 A class (for example AP2151/AP2171-type), or a 0.5 A polyfuse in series. |
| M8 | Minor | CM3 ↔ RK628D | **RK628D_RESET_N is on GPIO0_D6 (1.8 V only), not "PMUIO1, 3.3 V" as REV_A_SPEC §7 and TEST_REPORT fix 1 say.** A 1.8 V high is under the RK628D's V<sub>IH</sub> min of 2.0 V, though above its typical Schmitt threshold (V<sub>tr+</sub> max 1.34 V), so reset should release. The RK628D's internal pull-up to 3.3 V (26–71 kΩ) feeds about 20–60 µA into the 1.8 V-only pad whenever the SoC isn't driving low. | CM3 schematic p.7 (as M1). RK628D datasheet table 2-3 (RESETN: pull-up) and table 3-3 (V<sub>IH</sub> 2.0 V; threshold 1.0–1.34 V). Netlist: RK628D_RESET_N = J703.20 + U201.H4 + C202. | Works as is. Verify release at bring-up. | Same move or translator as M1. |
| M9 | Minor | Power layout | **The SY8303 switch nodes LX_5V and LX_SOM are 0.3 mm tracks (about 2.1 mm long) carrying up to 3 A plus ripple.** TPS563201 SW_IO goes through 3 vias, which spreads the switching node across layers (EMI). | pcbnew query: LX_5V and LX_SOM widths {0.3 mm}, 2.1 mm. SW_IO 0.8 mm with 3 vias. | None (short neck, a modest temperature rise). | Pour LX as a short, wide copper area on F.Cu only. |
| M10 | Minor | Input power | **F101 (3 A hold) is below the worst-case VIN current, and the NP-F input connector J102 (JST PH, 2 A) is under-rated.** `checks/irdrop.py` itself models VIN = 4.2 A at 6 V with full load. A PH contact is rated 2 A. | `fab/relay-bom.csv`: F101 C48985875 (1812L300/30GR, 3 A hold); J102 C131337 B2B-PH-K-S (2 A per LCSC). `irdrop.py` CASES["VIN"]. | Keep the module load realistic (about 7 W total is about 1.2 A at 6 V). | A 4–5 A-hold fuse and a battery connector rated over 5 A (for example XT30 or a JST VH). |
| M11 | Minor | High-speed layout | **The PCIe TX, USB-OTG and USB-BT pairs aren't coupled** (104–112 Ω), as the earlier report found. In addition: USB_BT_DM has 6 vias and USB_BT_DP none; PCIe TX_N has 6 vias and TX_P has 4; M2_PER_P/N change layer differently. Several of these pair vias have no GND return via within 2 mm. | pcbnew: per-net via counts (USB_BT_DM 6 / DP 0; PCIE_TX_N 6 / P 4); gap histogram USB_BT 1.53 mm and 5.4 mm; `checks/returnpath.py` return-via list. | None (USB2 for BT is likely full-speed; PCIe Gen2 margin is fine per the earlier simulation). | Route each as a coupled pair with symmetric vias and a GND via beside each pair via. |
| M12 | Minor | PCIe sideband, CM3 | **PERST#, CLKREQ# and WAKE# (GPIO1_B2/B0/B1) are in VCCIO1 = VCCIO_ACODEC.** That rail is off at power-up and set to 1.8 or 3.3 V by software through the RK817. R501–R503 pull these pins to 3V3_IO (on whenever 5V_SYS is), back-powering VCCIO1 through the pad clamps until the LDO is enabled. R501 also holds PERST# **de-asserted** while the SoC boots. | CM3 datasheet §3.1.2 ("VCCIO_ACODEC … off by default … activated later … by software"), §3.9 item 5 (VCCIO_ACODEC 1.8 or 3.3 V). CM3 schematic, sheet "RK3566_H (VCCIO1 Domain)": VCCIO1 = VCCIO_ACODEC. Radxa's own IO board uses the same pins with no carrier pull-ups. | Device tree: VCCIO_ACODEC (RK817 LDO4) at 3.3 V, always-on, and pmu-io-domains vccio1 = 3.3 V. Optionally remove R501 so PERST# stays asserted (internal pull-down) until the driver releases it. | Pull PERST# **down**. Take CLKREQ#/WAKE# pull-ups from a rail that follows VCCIO1, or rely on the card's own. |
| M13 | Minor | DT/software | **The module also drives the PLUGIN_DET pin.** GPIO0_A4 (J69-76, SDMMC0_DET_L) has an on-module MMBT3904 (Q4, through 100 Ω) that pulls it low whenever GPIO0_D4 (TF_DET) is driven high. | CM3 schematic p.7, bottom left: R170 100 Ω, Q4, R171 1 kΩ from TF_DET. | Keep GPIO0_D4 low or unused in the device tree. | Same. |
| N1 | Note | Debug | **The debug UART (J601) is 1.8 V** (GPIO0_D0/D1, PMUIO2), not 3.3 V. A 3.3 V USB-UART adapter's TX overdrives the pin. | CM3 schematic p.7 (UART2_RX/TX_M0 in PMUIO2 = VCCA1V8_PMU_1). | Use a 1.8 V adapter. Label the header. | Add "1V8" silk. |
| N2 | Note | CM3 power | **The DF40 contacts are rated 0.3 A each, so the six +5V_INPUT pins carry about 1.8 A, not the 3 A REV_A_SPEC budgets.** This is the module's design, not ours. | LCSC C597931: "300mA". CM3 datasheet §3.1.1 (6 pins, 3 A). | Keep CM3 sustained draw under about 1.8 A. | — |
| N3 | Note | Supply | **RK628D (C2843533) showed only 27 in stock at LCSC (Oct 25),** and the magjack (C3179417) has none. | jlcsearch query. | Already planned (hand-fit J301). | Second source for the RK628D before the pilot. |
| N4 | Note | SDI header (DNP) | **Radxa's datasheet contradicts itself on I2C4_SDA_M0:** the §3.9 table says J69_40, the appendix and xlsx say J69_44 (GPIO4_B2). We use 44, which matches the pin mux. | CM3 datasheet lines 1589 vs 2447. | — | Confirm on an IO board before the SDI add-on. |
| N5 | Note | Docs | Out-of-date documentation: <ul><li>REV_A_SPEC §7 says GPIO0_D6 is 3.3 V and lists INT on "the same PMUIO2 bank" next to a rule forbidding it.</li><li>The HDMI part number is given as C2902698; the BOM uses C916313 (Molex 2086581001, which matches the footprint).</li><li>The outline is 120 × 100 mm, not about 90 × 65.</li><li>C102 is an aluminium electrolytic (RVT), not polymer.</li><li>"All SMD on top", but 63 parts are on the bottom.</li><li>"HDMITX_5V 55 mA" (see M7).</li></ul> | | | |
| N6 | Note | USBLC6 | U101 pin 5 (VBUS) is unconnected. This is acceptable: it's the part's floating-rail mode, and the earlier report rightly moved it off the 9 V VBUS. | Netlist. | — | Tie to a 5 V or 3.3 V rail for the best clamping. |
| N7 | Note | Dev order | The dev modules in `orders/` are RM116-D2E16**W2** (with Wi-Fi). Nothing on the carrier conflicts with the W2's on-module Wi-Fi. J69-89/91 (WL_NDIS/BT_NDIS names) only reach the unfitted SDI header. | `orders/2026-10-25-dev-parts.md`. | — | — |

## What I verified and found correct

- **CM3 pin map:** every assigned pin in `gen/module.py` against the V1.32 change table (xlsx: J69-37/93, J1-14/26/34, CSI D2/D3 at J68 128/130/134/136). All functions match. The supply and ground pins match the IO board (`checks/b2bfit.py` re-run: 300/300 pins, 0.0000 mm, mirror rejected).
- **Module mounting:** the four 2.6 mm holes are at 47.95 × 33.0 mm, which matches the datasheet's "3.5 mm inset" on 55 × 40. No top-side part sits under the module outline (only C702/C703 on the bottom). CPL centres for J701–J703 equal the pad-bounding-box centres.
- **I/O banks that are right:**
  - I2C2_M1 (GPIO4_B4/B5, VCCIO6 = GPIO_VREF = 3.3 V, 4.7 kΩ to RK628D_3V3);
  - PLUGIN_DET (GPIO0_A4, PMUIO1 3.3 V, 10 kΩ to 3V3_IO);
  - WIFI_DISABLE_N (GPIO0_A0, PMUIO1);
  - PWR_EN (GPIO0_C4, 1.8 V) into an NPN base through 1 kΩ, which is fine;
  - RECOVERY (10 kΩ to SOM_1V8, 1 nF);
  - VBUSDET (10 kΩ to SOM_3V3);
  - VIN_SENSE: 100k/10k, 17 V → 1.55 V.
- **RK628D:**
  - every connected ball against datasheet table 2-1/2-2, including TEST to GND, EFUSE 100 Ω + 100 nF, MIPI_REXT 4.02 kΩ, HDMIRX/TX_EXTR 2 kΩ;
  - supplies and ferrite split identical to DshanPi p.31;
  - I2C_ADDR: R201 fitted, R202 DNP, so 0x50;
  - 24 MHz crystal is DshanPi's "Selection 1", valid without HDMI_TX/GVI;
  - HDMI RX DDC (47 kΩ to 5 V through MBR0530, 22 Ω), CEC (27 kΩ through a diode, 22 Ω), HPD (22 Ω), 5 V detect (2k/10k NPN) identical to DshanPi p.32;
  - CSI TX0→D0, TX1→D1, TX2→CLK, TX3→D2, TX4→D3, P to P, matching DshanPi p.32 and the CM3 pins.
- **Power:**
  - SY8303 0.6 × (1 + 110/15) = 5.0 V, Fsw = 105/210 kΩ = 500 kHz, BS 10 nF, 40 V input (TVS clamp fine), EN on at 5.35 V max;
  - TPS563201 3.30 V / 1.10 V with L within datasheet table 2;
  - CH224A pinout (VHV pin 1 on VBUS, 1 µF), 6.8 kΩ = 9 V;
  - AO3401A and MMBT3904 pinouts;
  - AP22804AW5 pinout and active-high EN;
  - SS54 OR-ing; SMBJ20CA vs 17 V.
- **Ethernet:** MDI0–3 → JK0654219 MX1–MX4, which reach RJ45 pins 1/2, 3/6, 4/5, 7/8 with the right polarity (datasheet p.4). Centre taps through 1 µF to GND.
- **M.2 E-key:** pins 2/4/72/74 3.3 V; USB 3/5; PET 35/37 to the SoC's RX; PER 41/43 through 100 nF from the SoC's TX; REFCLK 47/49; PERST 52, CLKREQ 53, W_DISABLE2 54, PEWAKE 55, W_DISABLE1 56; key gap 24–31 absent in the footprint.
- **USB-C** (CC to the CH224A, D+/D− both rows, USBLC6) and the **HDMI A footprints** (standard 1–19 numbering, LCSC C916313 = Molex 2086581001).
- **DC jack:** the footprint matches the PJ-002A layout (1 = centre, 2 = sleeve, 3 = switch, unused).
- **Impedance:** 0.10/0.10 mm on 3313 prepreg is about 100 Ω; PCIe RX 0.14/0.11 is about 85 Ω.
- **Rule checks:** KiCad DRC with schematic parity re-run: 0/0/0. ERC: 0.

## What I could not verify (and how to close it)

- **Crystal Y201 (C70590, X322524MOB4SI) load capacitance.** With 18 pF caps and about 3–4 pF stray, the board
  presents about 12–13 pF. The part must be a 12 pF CL part; LCSC lookup failed. Check the YXC datasheet.
- **L101/L102 (C2041457, Bourns SRN6045TA-6R8M) saturation current.** The schematic value says "5A". At 3 A out and
  17 V in, the peak is about 3.5 A, so I<sub>sat</sub> must be at least 3.6 A. Check the Bourns table. If it's
  about 3 A, use a 6.8 µH part rated over 4 A.
- **JLCPCB rotations.**
  - U401 (SOT-25) is the only SOT-23-family part with no `JLC_ROT` entry, while every other one needed +180 or −90.
    If its model needs +180, IN and OUT swap.
  - The LEDs, diodes and all 63 bottom-side parts weren't checked either.
  - **Close it:** check each in JLCPCB's DFM placement viewer before paying.
- **M.2 standoff H501, 28 mm from J501:** needs the TE 2199230-4 drawing (datum to card-stop).
- **RK628D power-up order (3.3 V before 1.1 V through the RC on EN):** the datasheet has no sequencing section, and
  the Rockchip hardware design guide isn't in the repo. The scheme matches DshanPi.
- **D-PHY skew budget of the RK3566 receiver (M6):** Rockchip's PHY spec isn't available.
- **Reference-plane gaps:** `checks/returnpath.py` flags 0.4–11 mm per net. Those I inspected were via-antipad
  clearances at the CM3 and M.2 fields, not plane splits, but I didn't inspect every sample.
- **Thermal of the RK628D and CM3 in the case, and connector overhang against the case:** no case model was checked.

## Agreement and disagreement with TEST_REPORT.md

- **Disagree: "I/O level audit: clean" and fix 1.**
  - `checks/iolevels.py`'s `bank()` maps GPIO0 index ≥ 27 (GPIO0_D3–D7) to "PMUIO1/OSC, 3.3 V". Both the CM3
    schematic (OSC box: 1.8 V only) and the RK3568 datasheet (PMUIO0) say otherwise.
  - So the "fixed" RESET_N (GPIO0_D6) is still on a 1.8 V pin (M8), and INT (GPIO0_D5) was never flagged (M1).
  - The audit also skips nets with no pull-up to a listed rail. That's how it missed the LEDs (M2), PD_PG_N, whose
    pull-up goes to VBUS_C, not a listed rail (M3), and BT_DISABLE_N (M5).
- **Disagree, by omission:**
  - the PD gate (M3) and the USB-only flashing case (M4) aren't covered;
  - the AP22804's 3 A limit (M7);
  - F101 against its own 4.2 A VIN case, and J102's 2 A rating (M10).
- **Partly disagree: CSI skew.** The report quotes 7.35 mm, carrier only. The CM3 datasheet gives the module's
  internal lengths, and the total spread is about 24 mm (M6).
- **Agree:**
  - B2B footprint fit;
  - RK628D ball map and DshanPi copy;
  - regulator dividers and Fsw;
  - CH224A config;
  - magjack and DC-jack pinouts;
  - USBLC6 VBUS change;
  - impedance numbers;
  - uncoupled PCIe TX and USB pairs (M11);
  - the U106 input-cap note;
  - the via-in-pad note (COST.md says filled and capped vias are ordered, which covers it);
  - DRC/ERC/parity clean.
