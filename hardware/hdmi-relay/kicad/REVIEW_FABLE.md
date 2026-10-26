# Rev A: pre-fab review (Fable, Oct 25, 2026)

Scope: `relay.kicad_sch` and its sheets (netlist exported with kicad-cli), `relay.kicad_pcb`, the fab outputs in
`fab/`, the generators in `gen/`, the case model in `../case/`, against the datasheets in `../datasheets/` and the
LCSC/JLCPCB listings of the BOM parts. KiCad DRC (`--schematic-parity --severity-all`) and ERC were re-run; the board
was dumped with pcbnew and analysed with scripts kept outside the project
(`/private/tmp/claude-501/fable-review/`). `REVIEW_INDEPENDENT.md` and `TEST_REPORT.md` were read only after the
findings were formed. Nothing in the project was changed except adding this file.

**Status (Oct 25, later):**
- **Fixed B1:** 0.2 mm F.Cu links now join every pass-through pad pair of D203 and D403 (D203 1–10, 2–9, 4–7, 5–6;
  D403 1–10, 2–9, 5–6). D403 7 (5 V) is NC and left bare; pad 4 clamps the rail. The four TMDS arrays already had
  copper across every pair.
- **Fixed M1:** C501/C502 are now fitted as 0 Ω (C17168) on their 0402 capacitor pads.
- **Re-run:** DRC with parity 0/0/0, ERC 0, I/O audit 0 flagged, fab outputs regenerated.
- **M3 (rev A part):** 6 GND thermal vias at U103/U104.
- **M4:** stackup written into the board and job file; `gen/fab.py` checks it.
- **Still open:**
  - M2: lane-rate cap on rev A, serpentines in rev B.
  - M3's rev B part: an exposed-pad buck.
  - The Minors and Notes.

## Verdict

**Do not order as is.** One blocker: the HDMI DDC lines on both ports, and the HDMI IN SDA line, go *through* the ESD
arrays by entering one pad and leaving from the pad opposite. That works with the Semtech RClamp0524P, whose pins
are internally paired. The BOM part is the Tech Public RCLAMP0524P (LCSC C907837), and its datasheet marks pins 6,
7, 9 and 10 **NC**. If they are, the HDMI OUT EDID bus and the HDMI IN SDA line are open circuits and neither port
works. It is a 20-minute copper fix (short bridges between the pad pairs) and a DRC re-run.

Beyond that, the board is in good shape: the CM3 pin map, the I/O bank voltages after the Oct 25 moves, the RK628D
ball map and straps, the regulators' dividers and thresholds, the connector pinouts, the connector footprints
against Radxa's IO board, and the BOM/CPL consistency all check out against primary sources. The four Majors are
real but survivable for a rev A bring-up with the workarounds listed.

**Counts: 1 Blocker, 4 Major, 11 Minor, 11 Note.**

## Findings

| ID | Sev. | Area | What's wrong | Evidence | Rev A workaround | Rev B fix |
|---|---|---|---|---|---|---|
| B1 | **Blocker** | HDMI ESD | **HDMI OUT SCL and SDA (D403 pads 1↔10, 2↔9) and HDMI IN SDA (D203 pads 5↔6) have no copper between the two pads of each line: the signal enters on one pad and leaves on the other, relying on the ESD part's internal pin-to-pin link.** The BOM part (Tech Public RCLAMP0524P, C907837) draws pins 10/9/7/6 as "NC" with only pins 1/2/4/5 tied to the diodes. HDMI IN SCL reaches only pad 7 (an NC pin), so it is connected but unprotected. All 16 TMDS lines and HDMI OUT 5 V/HPD, HDMI IN HPD/CEC are fine: copper runs under both pads. Without DDC a source cannot read the RK628D's EDID (HDMI IN dead) and the CM3 cannot read the monitor's EDID (HDMI OUT dead or default-mode only). | `datasheets/RCLAMP0524P.pdf` p.1 "Dimensions and Pin Configuration" (pins 6, 7, 9, 10 labelled NC, no diode drawn to them). pcbnew connectivity with D203/D403 removed from the board: D403 HDMITX_SCL 1/10 and HDMITX_SDA 2/9 "open without the part", D203 PORT_SDA 5/6 "open without the part", D203 PORT_SCL pad 4 no copper. KiCad DRC passes because it treats same-net pads of one footprint as connected. | Before ordering: draw a 0.15 mm F.Cu bridge between pads 1–10, 2–9, 4–7 and 5–6 on D203 and D403 (and, for uniformity, on D201/D202/D401/D402 where the pass-through trace already does it). Re-run DRC. If the boards are already made: solder-bridge the pad pairs, or fit genuine Semtech RClamp0524P parts. | Use a part whose datasheet states flow-through pins, or route every line explicitly through copper and treat the array as a stub. |
| M1 | Major | PCIe | **Two AC-coupling capacitors in series on the PCIe TX lanes.** The CM3 already has C54/C55 (100 nF, 0201) on PCIE20_TXP/N before the connector; the carrier adds C501/C502 (100 nF) between PCIE_TX and M2_PER. Net 50 nF, under the PCIe CEM minimum of 75 nF. (The RX side has the same problem, module C57/C58 plus the card's own capacitors, but that is Radxa's design and the IO board ships that way.) | CM3 V1.322 schematic, sheet "MULTI PHY P_S": "AA37 C54 100nF C0201 X5R 10V PCIE20_TXP / AA38 C55 … PCIE20_TXN" (text lines 808–809); `gen/board_io_sheets.py` m2(): `cap(... "PCIE_TX_P", "M2_PER_P", "100nF")`. | Fit 0 Ω 0402 in place of C501/C502 (BOM change only). Links with 50 nF usually still train at Gen1, so it is not a bring-up stopper. | Delete C501/C502 and route PCIE_TX straight to J501 pins 41/43. |
| M2 | Major | CSI | **Data-to-clock mismatch including the module's internal lengths is +21.4 mm (D0) and +24.2 mm (D3) against the CM3 rule of <36 mil (0.9 mm).** Totals: CLK 33.50+35.51 = 69.0 mm, D0 29.38+61.06 = 90.4, D1 31.44+35.35 = 66.8, D2 26.15+39.71 = 65.9, D3 29.16+64.06 = 93.2. Carrier-only the spread is 7.35 mm (CLK longest), which does not compensate the module; it adds to D1/D2 and only partly cancels D0/D3. At 1.2 Gb/s per lane 24 mm is about 160 ps = 0.19 UI, the whole interconnect skew budget of a D-PHY receiver without deskew (RK3566 has none below 1.5 Gb/s). At the rate 1080p60 YUV422 actually needs (about 0.5–0.6 Gb/s per lane) it is about 0.08 UI and will work. | CM3 datasheet "MIPI Layout Requirements": "Data to clock mismatch <36mil", module lengths table (CLK0P 1395.6 mil … D3N 2546.4 mil). Carrier lengths from `relay.kicad_pcb` (pcbnew). | Configure the RK628D CSI TX for the lowest lane rate that carries the format (4 lanes, ≤600 Mb/s). Check CSI CRC/ECC counters at bring-up. | Match the totals: add about 21 mm to CLK, 24 mm to D1 and D2 (serpentines fit between the RK628D and J702), or shorten D0/D3. |
| M3 | Major | Power, thermal | **U104 (SY8303, 5V_SOM) runs at or above its rated junction temperature at the module's 3 A maximum.** θJA is 60.2 °C/W in TSOT23-8; at 12–17 V in, 5 V/3 A out, losses are about 1.3–1.7 W (TEST_REPORT's own figure is 116–124 °C at 40 °C ambient). Inside the printed case ambient is higher, and the package has no thermal pad, only two GND pins. | SY8303 datasheet p.2 "θJA 60.2 °C/W", RDS(on) 110/70 mΩ; CM3 datasheet §3.1.1 (+5V input up to 3 A); TEST_REPORT thermal section. | Keep sustained module current under about 1.5–2 A (realistic for RK3566 + 2 GB), put a thermocouple on U104 during the soak test, add copper under its GND pins if the fill allows. | A 5 V buck with an exposed pad (QFN or SOT-583 class), or a lower switching loss part; both U103 and U104 would benefit. |
| M4 | Major | Stackup, ordering | **The impedance targets exist only in the net classes; the board file carries no stackup and the Gerber job file says 0.48 mm dielectrics (KiCad's default).** 0.10/0.10 mm (100 Ω), 0.14/0.10 (85 Ω) and 0.12/0.10 (90 Ω) are right only on JLC04161H-3313 (0.0994 mm prepreg). On JLCPCB's default 7628 stack (0.21 mm) the same geometry is about 120 Ω differential (IPC-2141 estimate: Z0 single 86 Ω). COST.md names 3313 but no fab file does. | `relay.kicad_pcb` has no `(stackup …)` block; `fab/gerbers/relay-job.gbrjob`: "Dielectric Thickness 0.48". `relay.kicad_pro` net classes. IPC-2141 edge-coupled microstrip, Er 4.05/4.4. | Order with "impedance control: JLC04161H-3313" selected and state the three pair geometries in the order notes. | Define the stackup in Board Setup (so DRC, the job file and the drawings agree) and add an impedance table to a fab drawing layer. |
| m1 | Minor | High-speed | PCIe TX is coupled over only 16 % of its length (max gap 3.6 mm), REFCLK 54 %; USB_OTG and USB_BT are single traces; USB_BT_DM has 6 vias and DP 0; PCIE_TX_N 6 vias and TX_P 4. Uncoupled 0.14/0.12 mm traces on 3313 are about 104–112 Ω differential. The RTL8822CE is a Gen1 card and USB for BT is low-rate, so this is margin, not function. | pcbnew: per-pair coupling and via counts. | None. | Route as coupled pairs with symmetric vias and a GND via beside every pair via. |
| m2 | Minor | Power | **3V3_IO reaches the M.2 socket (pins 72/74) through 0.36–0.43 mm traces, and 5V_SYS is a 0.6 mm trace about 160 mm long.** An RTL8822CE card pulls 1–1.5 A peaks on 3.3 V; 5V_SYS carries about 1–1.5 A over about 0.13 Ω (0.15–0.2 V drop), which also lowers HDMITX_5V (HDMI asks for 4.8–5.3 V at the connector). There are no power pours: In2 is a GND pour plus signals. | pcbnew: 3V3_IO segments at J501 pads 72/74 widths 0.36/0.43; 5V_SYS widths {0.6 mm: 51 segments}, 179.6 mm total. | Measure 3V3_IO at J501 and HDMITX_5V at J401 under Wi-Fi load. | Widen to ≥0.8 mm or pour 3V3_IO/5V_SYS islands on In2. |
| m3 | Minor | USB-C | **No ESD protection on CC1/CC2 or VBUS_C.** USBLC6 covers D+/D− only; the SMBJ20CA sits after the OR diode. CC pins go straight into the CH224A. | Netlist: CC1/CC2 = J103 ↔ U102 only. | None. | ESD array on CC1/CC2 (5 V class) and a 20–24 V TVS on VBUS_C. |
| m4 | Minor | HDMI out | **AP22804 current limit is 2.7–3.3 A (0.45 A into a dead short), not an HDMI-grade 0.5 A limit.** A faulty cable loads 5V_SYS, which also feeds 3V3_IO and 1V1_628. | AP22804 datasheet ILIMIT 2.7/3.0/3.3 A. | None. | A 0.5 A-class switch or a 0.5 A polyfuse in series. |
| m5 | Minor | Input | **F101 (3 A hold, 5 A trip) and J102 (JST PH, 2 A/contact) are below the worst-case 6 V input current (about 4 A at full load).** Typical load (about 7 W) is about 1.2 A. | LCSC C48985875 (1812L300/30GR), C131337 (B2B-PH-K-S). | Keep the load realistic on battery. | 4–5 A fuse; XT30 or JST VH for the battery. |
| m6 | Minor | Power layout | **SW_IO (U105 switch node) changes layer through three 0.3 mm vias; SW_628 has a 0.13 mm neck; LX_5V/LX_SOM are 0.3 mm × 2 mm necks for 3 A.** EMI and local heating, not function. | pcbnew: SW_IO B.Cu 5.0 mm with 3 vias; SW_628 widths {0.127…0.8}; LX_* 0.3 mm. | None. | Keep each switch node a short F.Cu copper area; move L104 1 mm so U106's input cap fits. |
| m7 | Minor | CEC option | **R202 (0 Ω, DNP) would tie the 3.3 V CEC bus to J68-151, which on the module is the 5 V side of a UM3204H level shifter (10 kΩ pull-ups to VCC5V_MIDU).** Fitting it lifts PORT_CEC toward 5 V against the RK628D's 3.465 V recommended max (3.8 V absolute) and the CEC spec's 3.63 V. | CM3 V1.322 schematic, HDMI sheet: U7 UM3204H, VCCB = VCC5V_MIDU, B4/D1 = HDMI_TX_CEC_PORT. | Leave R202 unfitted. If CEC bit-banging is needed, use a 3.3 V GPIO instead. | Route CEC_GPIO to a plain VCCIO7/PMUIO1 GPIO, or add a 3.3 V clamp. |
| m8 | Minor | Fab | **101 vias sit inside SMD pads on 65 parts (two in RK628D pads), and the small vias are 0.3/0.15 mm.** Fine only with the filled-and-capped via option COST.md plans; without it expect solder wicking and tombstoned 0402s. | pcbnew via-in-pad count; drill file T1 0.150. | Order "via filling: epoxy filled and capped" and the 0.15 mm drill option. | Fan out beside pads; 0.2 mm drills. |
| m9 | Minor | Fab | **The Gerber job file describes a stackup that is not the one ordered** (see M4), and the CPL rotation corrections (`gen/fab.py` JLC_ROT) cover 13 parts only; U401 (SOT-25), the SMA/SOD diodes, LEDs, the electrolytic C102 and all bottom parts are uncorrected. KiCad and JLCPCB zero orientations differ for several of these. | `fab.py` lines 162–172; CPL rotations. | Check every polarised part in JLCPCB's placement preview before paying (as the README already says). | Keep a verified rotation table per footprint, not per reference. |
| m10 | Minor | HDMI in | **HDMI IN SCL is protected only if the ESD array's pin 7 is a live pin.** With the Tech Public part it is NC, so SCL has no ESD clamp (see B1). | pcbnew: D203 PORT_SCL copper on pad 7 only. | Covered by the B1 bridges (then pad 4 clamps it). | As B1. |
| m11 | Minor | ADC | **VIN_SENSE has no clamp.** The 100k/10k divider gives 1.55 V at 17 V, but a TVS clamp event (SMBJ20CA, 32 V) puts 2.9 V on SARADC_VIN3 (1.8 V input). | `gen/power.py`; SMBJ20CA Vc 32.4 V. | None. | Add a BAT54 to SOM_1V8 or a 1.8 V zener at the ADC pin. |
| n1 | Note | CSI/HDMI | The module's own pairs are not intra-pair matched: CSI D3 1.24 mm, D1 1.01 mm, HDMI TX D1 1.57 mm, PCIe RX 0.79 mm (all >12 mil). Rev B could compensate on the carrier by making P/N deliberately unequal. | CM3 datasheet length tables. | — | Compensate P/N on the carrier. |
| n2 | Note | CM3 power | DF40 contacts are rated 0.3 A; six +5V pins give 1.8 A sustained, not 3 A. Radxa's design. | LCSC C597931 "300mA". | Keep sustained draw under about 1.8 A. | — |
| n3 | Note | DT | **Device tree work the hardware forces:** vccio_acodec (RK817) 3.3 V always-on and pmu-io-domains vccio1 = 3.3 V (BT_DISABLE#, PERST#, CLKREQ#, WAKE#); disable `sdmmc0` or drop its `cd-gpios`/`vmmc` GPIOs, because GPIO0_A4 is now PLUGIN_DET and GPIO0_A5 is LED_WIFI; keep GPIO0_D4 (TF_DET) low (it pulls PLUGIN_DET low through the module's Q4); RK628D on i2c2 (i2c2m1), reset GPIO3_C2, int GPIO3_C3, power-enable GPIO0_C4; CSI 4-lane on CLK0; PCIe PERST GPIO1_B2, CLKREQ/WAKE M2 group. | CM3 schematic p.7 (Q4/R170/R171), connector pages; `gen/module.py`. | — | — |
| n4 | Note | Wi-Fi | GPIO0_A0 (WIFI_DISABLE_N here) is WIFI_PWREN on the module: on the W2 dev modules it also switches the on-module Wi-Fi supply. Harmless on the W0 production SKU. | CM3 schematic connector page "WIFI_PWREN / 3V3_PWR_EN". | — | — |
| n5 | Note | M.2 | H501 (standoff) is 28.0 mm from J501's footprint origin. The TE 2199230 drawing was not available in text form; the application spec (114-115006) has no standoff dimension. Needs a check against the TE customer drawing or an M.2 2230 card on a printout. | `relay.kicad_pcb`. | Check before ordering. | — |
| n6 | Note | ESD parts | Tech Public RCLAMP0524P: 0.6–0.8 pF line-to-ground, Vbr 6.8–9.5 V. Fine for 1080p60 (1.5 Gb/s); marginal for HDMI 2.0 6 Gb/s. Unidirectional, 5 V VRWM: fine for HDMITX_5V on D403. | `RCLAMP0524P.pdf` p.2. | — | ≤0.3 pF part if 4K input is ever wanted. |
| n7 | Note | Case | The 2D positions match the board: four M3 holes (4,4), (4,96), (116,36), (116,68); light pipes over D601/D602/D603; pinholes over SW601/602; HDMI, USB-C, DC and RJ45 openings centred on the connectors; the CM3 keep-out block (38.4–93.6 × 29.9–70.1) matches the module outline derived from its mounting holes (38.6–93.5 × 30.1–70.0). The 3D clash check (`case.py --check`) was not re-run here (needs CadQuery). The magjack protrudes 2.9 mm (documented). The tripod bosses at (30,70) and (85,85) clear every through-hole pin by more than 7.5 mm. | `case/case.py`, pcbnew. | — | Line the RJ45 up with the rear wall. |
| n8 | Note | U106 | U106's nearest input capacitor is 3.1 mm from pin 3 (C119); U105's are 1.7/1.9 mm. Known, accepted. | pcbnew. | — | Move L104 1 mm. |
| n9 | Note | Supply | Stock could not be read from LCSC/JLCPCB pages (no stock field served; JLCPCB rate-limited). RK628D is "Extended"; the magjack is the Pulse part itself (C3179417 = JK0654219NL, pinout verified) but PRODUCTION.md says it is out of stock. The two Sunlord inductors (C83455, C98203) return "Part not found" on LCSC's product pages though JLCPCB still lists them: confirm before the order. | WebFetch of the listings. | Hand-fit J301; confirm L103/L104 availability. | Second-source the RK628D and choose a stocked jack. |
| n10 | Note | Docs | REV_A_SPEC still says 90 × 65 mm (board is 120.1 × 100.1), "47 µF aluminium polymer" (BOM is a JIERR electrolytic), HDMI connector C2902698 (BOM is Molex C916313, which matches the footprint), "all SMD on top" (62 parts on the bottom), and "L3 power" (In2 is a GND pour with low-speed signals). | Files named. | Update. | — |
| n11 | Note | RK628D sequencing | 3.3 V first, 1.1 V about 1 ms later (RC on U106 EN from RK628D_3V3), copied from DshanPi. The RK628D datasheet has no sequencing section and the Rockchip design guide is not in the repo. | `gen/power.py`, DshanPi p.31. | Confirm at bring-up. | — |

## What was verified as correct, and how

**CM3 pin map (every assigned pin).** `gen/cm3_pinout.json` was checked against the datasheet appendix C tables
(V1.3) with the V1.31/V1.32 changes from `radxa_cm3_v1300_to_1320_pinout.xlsx` applied: J69-37 → GPIO4_C5
(UART9_TX_M1), J69-93 → SARADC_VIN0, J1-14 → SARADC_VIN3, J1-26 → NC, J1-34 → GPIO0_D3. All 54 assignments in
`gen/module.py` land on the right function: MDI0–3, CSI D0–D3/CLK0 (4-lane), I2C2_M1 on 35/36, UART2_M0 on 51/55,
UART9_M1 on J69-37/J1-36, I2C4_M0 on 38/44, CIF D0–D15/HREF/VSYNC/CLKIN, PCIE20 TX/RX/REFCLK, CLKREQn/PERSTn/WAKEn
all in the M2 group (J68-102, J68-109, J1-38), USB_OTG0 D+/D−, USB2_HOST2, HDMI TX pairs/HPD/DDC, CEC on GPIO4_D1,
PMIC_RESET_KEY, VBUSDET, 5V ×6, +3V3 ×2 + GPIO_VREF, +1V8 ×2. No pin is used twice; the generator asserts it.

**I/O bank map, derived independently.** From the RK3568 datasheet pin table (domain labels per group) and the CM3
V1.322 schematic: PMUIO0 = GPIO0_D3–D6 (1.8 V only), PMUIO1 = GPIO0_A0–A7 (3.3 V only per RK3568 table "PMUIO1
2.97–3.63 V"), PMUIO2 = GPIO0_B0–D2 (VCCA1V8_PMU, 1.8 V), VCCIO1 = GPIO1_A0–B3 (= VCCIO_ACODEC, software-set),
VCCIO5 = GPIO2_D0–GPIO3_C5 (R43 0 Ω to VCC_3V3), VCCIO6 = GPIO3_C6–GPIO4_C1 (= GPIO_VREF via R24, tied to +3V3 here),
VCCIO7 = GPIO4_C2–D1 (VCC_3V3). Against that map every 3.3 V signal is on a 3.3 V bank: I2C2 (GPIO4_B4/B5, VCCIO6),
RESET_N/INT (GPIO3_C2/C3, VCCIO5), PLUGIN_DET/LED_WIFI/WIFI_DISABLE (GPIO0_A4/A5/A0, PMUIO1), LED_STATUS (GPIO4_B1,
VCCIO6), CEC_GPIO (GPIO4_D1, VCCIO7), SDI GPIO/UART/I2C (VCCIO5/6/7), BT_DISABLE/PERST/CLKREQ/WAKE (VCCIO1, needs the
DT setting). The two 1.8 V uses are intentional: PWR_EN into an NPN base, the 1.8 V debug UART. `checks/iolevels.py`
now has the same map. The J701 pads 30–90 and J703 10/12/40 moves: DRC with `--severity-all` reports no dangling
track or via, and the nets reach the new pads (parity 0).

**Module on the carrier.** `checks/b2bfit.py` re-run: all 300 pins coincide with Radxa's IO-board placement to
0.0000 mm, mirror rejected (19.7 mm rms). Mounting holes MH1–4 (2.6 mm) are 47.95 × 33.0 mm apart = 55 × 40 minus
2 × 3.5 mm. No top-side part inside the module outline (bottom: C702/C703 only). GPIO_VREF tied to +3V3.

**RK628D.** All 144 balls in `gen/hdmi_in.py` match datasheet tables 2-1/2-2 (script comparison; only naming
differences). INT is also SPIBOOT with an internal pull-down, and GPIO3_C3 defaults to pull-down, so normal boot.
RESETN internal pull-up, TEST pull-down tied to GND, I2C_ADDR low (0x50), I2C pins pulled up 4.7 kΩ to RK628D_3V3.
Supplies: 1.1 V and 3.3 V only, EFUSE_VDD_2V5 held low through 100 Ω (as DshanPi), ferrite-split analog rails,
2 kΩ EXTR, 4.02 kΩ MIPI_REXT. Crystal C70590 is a 12 pF CL part; 18 pF load capacitors give 9 pF + stray ≈ 12 pF.
CSI lane map TX0/1/2/3/4 = D0/D1/CLK/D2/D3 as on DshanPi p.31, P to P into J68 117/123/129/130/136.

**Power tree.** SY8303: Vout 0.6 × (1+110/15) = 5.00 V; Fsw 105/210k = 500 kHz; EN divider 100k/39k turns on at
≤5.35 V VIN (VENH ≤1.5 V), EN abs max 40 V; UVLO 4.35 V; input 2 × 4.7 µF/50 V (datasheet asks ≥4.7 µF); inductor
SRN6045TA-6R8M Isat 5.7 A, Irms 3.6 A against 3.5 A peak; min off-time 120 ns allows 94 % duty, so 5 V holds down to
about 5.6 V in (6.0 V battery). TPS563201: 0.768 × (1+33/10) = 3.30 V and 0.768 × (1+10/23.2) = 1.10 V; 2.2 µH and
1.5 µH per its table; EN through 100k/100n from 5V_SYS and 10k/100n from RK628D_3V3 (REN 225–900 kΩ keeps EN >1.6 V);
UVLO 3.6 V; 5V_SYS ≥4.5 V. Output 22 µF/10 V 0805 ×2 derate to about 25–35 µF effective. CH224A: pin 1 VHV and pin 8
VBUS on VBUS_C (VBUS "must be shorted to VHV" for the A), 1 µF/50 V, CFG1 6.8 kΩ = 9 V, PG open-drain into Q101's gate
with 100 kΩ to VBUS_C; AO3401A VGS −9 V within ±12 V; body diode cannot back-feed the port because D103 is in
series. AP22804AW5: pin 1 OUT, 2 GND, 3 FLG, 4 EN (active high, tied to IN), 5 IN. USBLC6 pin 5 left floating is
correct at a 9 V contract.

**Connectors.** HDMI: J201/J401 pins 1–19 in standard order; D2/D1 and D0/CLK pairs flow through D201/D202 and
D401/D402 with copper under both pads; HPD on the IN side driven by the RK628D through 22 Ω (as DshanPi), on the
OUT side straight to J68-153 where the module has 1 kΩ series and 100 kΩ pull-down; DDC pull-ups 2.2 kΩ to
HDMITX_5V (the module's UM3204H 5 V side); CEC 27 kΩ. The BOM HDMI socket is Molex 2086581001 (C916313), which is the
part the KiCad footprint is drawn for. Ethernet: J301 pin map matches the JK0654219 schematic (MX1± 11/10, CT1 12;
MX2± 4/5, CT2 6; MX3± 3/2, CT3 1; MX4± 8/9, CT4 7) and the cable side lands MDI0–3 on RJ45 1/2, 3/6, 4/5, 7/8;
C3179417 is that exact Pulse part; centre taps 1 µF to GND. M.2 E-key: 1/7/18/33/39/45/51/57/63/69/75 GND,
2/4/72/74 3.3 V, 3/5 USB, 35/37 PETp/n → PCIE_RX, 41/43 PERp/n ← PCIE_TX, 47/49 REFCLK, 52 PERST#, 53 CLKREQ#, 54
W_DISABLE2#, 55 PEWAKE#, 56 W_DISABLE1#; socket C2977809 = TE 2199230-4 (E key, 4.2 mm) matching the footprint
family. USB-C: HRO TYPE-C-31-M-12 (C165948) with the matching footprint, CC1/CC2 to the CH224A (Rd inside), D+/D−
through USBLC6 to USB_OTG0. DC jack PJ-002AH (C2961147, 2.0 mm pin, 5 A), same footprint as PJ-002A.

**Layout.** DRC `--schematic-parity --severity-all`: 0 violations, 0 unconnected, 0 parity; ERC 0. 4 layers, 1.6 mm,
120.1 × 100.1 mm. Zones: GND on all four layers (In1 solid under every F.Cu pair; no inner-layer track found within
0.25 mm under any F.Cu or B.Cu high-speed segment, including DVP_D6's In2 run under J701). Pairs: CSI, HDMI IN/OUT
P/N matched to 0.00–0.02 mm, 80–88 % coupled, all on F.Cu over In1; CSI D2/D3 use two vias each; HDMI
clock-to-data including the module's lengths stays within 480 mil (worst 7.9 mm); Ethernet pairs 98 % coupled, P/N
within 0.69 mm (acceptable at 125 MBd); PCIe RX 98 % coupled, 0.33 mm. Decoupling: U105 input caps 1.7/1.9 mm, U103/U104
2.05 mm, RK628D 22 capacitors within 6 mm plus 49 fanout vias, crystal 8 mm from the chip with load caps beside it,
CM3 5 V caps 4–5 mm from the pins. ESD arrays 6–7 mm from their connectors. Copper-to-edge and hole clearances pass
DRC (0.3 mm edge rule). Six fiducials, out of BOM/CPL.

**Fab files.** Gerbers: 4 copper, mask, paste, silk, edge, PTH/NPTH drills, all in page coordinates; the CPL uses the
same coordinates (C120 at 64.9 mm = board 34.95 mm), so they align. BOM and CPL list the same 179 references; DNP parts
(R202, R216, R501, J602) are in neither; every BOM line has an LCSC number; 117 top / 62 bottom. Part identities
confirmed on LCSC: CH224A C42459160, RK628D C2843533 (Extended), DF40C-100DS-0.4V(51) C597931, SY8303AIC C97054,
TPS563201 C116592, AP22804AW5-7 C3001659, RCLAMP0524P C907837, SRN6045TA-6R8M C2041457, SWPA6045S2R2MT C83455,
SWPA6045S1R5MT C98203, 1812L300/30GR C48985875, X322524MOB4SI C70590, PJ-002AH C2961147, Molex 2086581001 C916313,
JK0654219NL C3179417, TE 2199230-4 C2977809.

## What could not be verified

- **Whether the Tech Public RCLAMP0524P's NC pins are bonded through.** The datasheet says NC; treat as open (B1).
- **Part stock and lifecycle.** LCSC's pages serve no stock figure to a fetch and JLCPCB rate-limited the lookups.
- **The M.2 standoff distance** (n5).
- **The RK3566 D-PHY receiver skew budget and the RK628D's minimum CSI lane rate** (M2): Rockchip documents not in
  the repo.
- **RK628D 1.1 V current and power sequencing** (n11): no design guide.
- **JLCPCB's zero orientation for the uncorrected CPL parts** (m9): only their preview shows it.
- **The case in 3D** (n7): the CadQuery clash check was not re-run; only 2D positions were compared.
- **Impedance with a field solver**: IPC-2141 closed form only; the project's `checks/zsolve.py` figure (92.6 Ω) is
  plausible but not independently reproduced.

## Comparison with the earlier reports

**REVIEW_INDEPENDENT.md (Oct 25).**
- Confirmed: the PMUIO0 1.8 V-only finding and the five pin moves it caused (M1, M2, M3, M5, M8 there) are now
  correctly fixed; the bank map in `checks/iolevels.py` matches my independent derivation. Also confirmed: M4
  (USB-only flashing), M7 (AP22804 limit, my m4), M9 (switch-node necks, my m6), M10 (fuse/JST, my m5), M11
  (uncoupled pairs, my m1), M12/M13 (VCCIO_ACODEC and TF_DET, my n3), N1 (1.8 V UART), N2 (DF40 current, my n2),
  N4–N7.
- Disputed: it lists "PER 41/43 through 100 nF from the SoC's TX" as verified correct. The module already has those
  capacitors (my M1). Its M6 (CSI skew) is rated Minor; the numbers agree with mine but a 25× violation of the
  datasheet rule with no receiver deskew is a Major with a software mitigation.
- Missed: B1 (ESD pass-through on NC pins), M4 (stackup not captured in any fab file), m2 (3V3_IO/5V_SYS trace
  widths), m3 (CC ESD), m7 (CEC option into a 5 V node), m11 (ADC clamp).
- Still open from it: M6/M7/M9/M10/M11/M12 by the project's own choice; N3 (stock) unresolved.

**TEST_REPORT.md (Oct 24/25).**
- Disputed: "RClamp0524P … Match. All six run each line straight across its column (1↔10, 2↔9, 4↔7, 5↔6)". That is
  the intent, but D203 and D403 do not carry copper across for SDA/SCL (B1), and the datasheet it cites shows those
  columns ending in NC pins. "Magjack … Match" and "CM3 connectors … exact" are confirmed. The 3 A thermal figure it
  computes (116–124 °C) supports my M3 rather than the "ready to order" verdict.
- Confirmed: DRC/ERC/parity clean; regulator outputs and Fsw; CH224A configuration; USBLC6 pin 5; fiducials; the
  VIN neck fix (VIN is now 0.8–1.6 mm); impedance numbers for the coupled pairs; the uncoupled-pair eye estimate is
  consistent with my Minor rating.
- Open: "two things to settle" (magjack stock, DC plug 2.0 vs 2.1 mm) remain open; the via-in-pad count (101 by my
  count, 110 by its) is covered only if the filled-via option is actually ordered.
