# Rev A: third pre-fab review (Fable, Oct 25, 2026, after the jack turn, CSI matching, DNP and CPL changes)

Scope: `relay.kicad_sch` and its sheets (netlist re-exported with kicad-cli), `relay.kicad_pcb` and `routed.kicad_pcb`,
the fab outputs in `fab/` (Gerbers, drills, job file, BOM, CPL, FAB_NOTES), the generators in `gen/`, the checks in
`checks/`, the case in `../case/`, the order notes in `../orders/`, against the datasheets in `../datasheets/` (read as
text, and as images where the text layer is empty: RCLAMP0524P, PJ-002A p.2, JK0654219NL p.2/p.4). ERC, DRC
(`--schematic-parity --severity-all`), `checks/b2bfit.py`, `returnpath.py`, `iolevels.py`, `irdrop.py`, `tline.py` were
re-run. The board was dumped with pcbnew and analysed with scripts kept in `/private/tmp/claude-501/fable-review-3/`,
including an independent impedance estimate (closed-form Kirschning–Jansen and a numpy finite-difference solve). The
backup in `backup/2026-10-25-pre-M1/` was used only for before/after comparison. The four earlier reports were read only
after the findings below were formed. Nothing in the project was changed except adding this file.

**Status (Oct 25, later):**
- **Fixed:** m11 (case light-pipe labels) and m12 (RFS 200k, inductor value says 3.6 A).
- **M1 closed.** Every polarised part was checked in JLCPCB's viewer against KiCad's pin 1, on an upload of the
  current files:
  - diodes, LEDs and C102;
  - Y201;
  - U101, U102–U106, U201, U401 and the RClamps;
  - Q101, Q201–Q203;
  - J103, J201, J401 and J501.

  The U101 −90° against U105/U106 180° difference is real: they use different JLCPCB models (USBLC6 against
  TPS563201) on the same KiCad footprint, and both land right.
- **M2 handled for rev A** (owner's decision: keep the SY8303). REV_A_SPEC.md states a 1.5–2 A sustained limit on
  5V_SOM, and PRODUCTION.md step 9 logs the current alongside the U104 thermocouple. Rev B moves to an exposed-pad
  buck.
- **M3 handled in software** (owner's decision): `../dt/rk3566-relay-carrier.dtso`. It sets VCCIO_ACODEC to 3.3 V
  always-on and vccio1 in the IO domains, the SoC pull-ups on CLKREQ#/WAKE#, PERST# as reset-gpios, rfkill for
  W_DISABLE1#/2#, the LEDs, TF_DET held low, and the RK628D at 0x50 with its four control lines. It is not compiled
  here (no dtc), so check the labels and the vendor RK628 binding against the BSP.
- **m2:** put the pair geometries from `fab/FAB_NOTES.txt` in the order remark on the next upload.

Coordinates are KiCad board coordinates (mm); board coordinates = KiCad minus (30, 30).

## Verdict

**Order, with the listed workarounds, after one more look at JLCPCB's placement preview (M1).** I found no blocker.
Everything changed by script today is correct and is in the files that will be manufactured:

- **DC jack J101:** pads 1/2/3 at (72.0, 115.55)/(72.0, 121.55)/(76.7, 118.55), footprint rotation 90°. In KiCad's
  `BarrelJack_Horizontal` the body runs 13.7–14 mm from pin 1 toward pin 2 (pin 2 is on the plug side, PJ-002A p.2),
  so the opening is at y ≈ 129.3–129.6, 0.5–0.8 mm inside the rear edge (130.05), facing out. The three pad flashes
  and the three 1 × 3 mm slots are in `relay-F_Cu.gtl` / `relay-PTH.drl` at those positions. F101 at (80.9, 119.3),
  no courtyard overlap (DRC). VDC 0.8 mm, VIN_RAW 0.8 mm with four 0.3 mm vias.
- **CSI matching:** carrier lengths now CLK 51.30/51.48, D0 29.38, D1 51.46/51.64, D2 40.87 (F+B, 2 vias), D3 29.16
  (2 vias). With the module's lengths (CM3 datasheet §3.5.3) the totals are CLK 86.9, D0 90.5, D1 86.9, D2 80.6,
  D3 93.2 mm: data-to-clock +3.6 / 0 / −6.3 / +6.3 mm (was up to 27 mm). P/N within 0.19 mm. The meanders are in the
  Gerbers (88 0.1 mm segments in the CLK/D1 window on F.Cu, 26 in the D2 window on B.Cu). Bump geometry: 0.7 mm leg
  pitch gives 0.4 mm (4 W) between neighbouring legs; each bump has two left and two right turns, so P and N gain the
  same length. CSI via return: every CSI layer-change via has a GND via within 0.7–1.0 mm.
- **R502/R503/R505 not fitted:** DNP in the schematic, absent from BOM and CPL. R504 (WIFI_DISABLE#) still fitted.
- **L103/L104:** C36500 (SWPA6045S2R2NT, 4.6 A) and C96956 (SWPA6045S1R5NT, 4.95 A) on the 6 × 6 mm pads.
- **CPL:** 176 rows = the 176 BOM references; DNP parts in neither; U401 and the six RClamps carry the −90° correction.
- **Gerber job file:** 0.0994 / 1.265 / 0.0994 mm dielectrics, 3313, ENIG, ImpedanceControlled; `gen/fab.py` enforces it.
- **DRC with parity and ERC:** 0 / 0 / 0, with every rule at its highest severity.
- **Case:** the DC opening (c = 42, 11.4 × 11.6 mm) sits over the jack (board x 42) and the new roof vent is over
  U103/U104.

**Counts: 0 Blocker, 3 Major, 14 Minor, 12 Note.**

## Findings

| ID | Sev. | Area | What's wrong | Evidence | Rev A workaround | Rev B fix |
|---|---|---|---|---|---|---|
| M1 | Major | Assembly, CPL | **The JLCPCB rotation corrections cannot be verified offline, and the table is not self-consistent.** `JLC_ROT` turns U101 (SOT-23-6) by −90° but U105/U106 (also SOT-23-6) by +180°, and SOT-23 (Q10x/Q20x) by +180° while SOT-23-5 (U401) gets −90°. Different LCSC parts can have different model zero orientations, so this may well be right, but it means the correction depends on each part's JLCPCB model and only their viewer shows it. A wrong U103–U106 or U401 orientation shorts a supply; a wrong RClamp orientation only loses protection. The CPL was regenerated after the last viewer check (jack turn, CSI pass), so the check must be done on the Y6 upload. | `gen/fab.py` JLC_ROT; `fab/relay-cpl.csv`. The claim of a part-by-part viewer check is in REVIEW_FABLE_2 and TEST_REPORT, not reproducible here. | Open order Y6's placement preview and check pin 1 / cathode / A1 of U101–U106, U201, U401, Q101–Q203, D101–D104, D204/D205, D601–D603, D201–D203, D401–D403, J201/J401, J103, J501, C102 against the silkscreen. Fix any wrong entry and re-upload. | Rotation table keyed by LCSC number, kept with the generator, with a screenshot per part. |
| M2 | Major | Power, thermal | **U104 (SY8303, 5V_SOM) is at its thermal limit if the module ever draws its rated 3 A.** TSOT23-8, θJA 60.2 °C/W, no exposed pad; at 12–17 V in and 5 V/3 A out the loss is about 1.3–1.7 W. Six 0.6/0.3 mm GND vias help (estimate, not measured). In the closed printed case the air around it is well above 25 °C. The six DF40 +5 V contacts (0.3 A each) cap the sustained module current near 1.8 A anyway, where U104 is fine. | SY8303 datasheet: θJA 60.2 °C/W, PD 2 W at 25 °C; CM3 datasheet §3.1.1; drill file T3 vias at U103/U104; `case/case.py` VENTS. | Keep the module's sustained draw ≤ 1.5–2 A (realistic for RK3566 + 2 GB); thermocouple on U104 during the closed-case soak (PRODUCTION.md test 9). | Exposed-pad 5 V buck for U103/U104 and a lid boss with a thermal pad to the module. |
| M3 | Major | PCIe/BT sideband, DT | **Wi-Fi and Bluetooth work only if the device tree is right.** PERST# (GPIO1_B2), CLKREQ# (GPIO1_B0), WAKE# (GPIO1_B1) and BT_DISABLE# (GPIO1_A4) are in VCCIO1 = VCCIO_ACODEC (RK817 LDO4, "typically off by default … activated later … from software"). With R501–R503/R505 not fitted there are no board pull-ups at all: CLKREQ# and WAKE# (open-drain from the card) need the SoC's own pull-ups, PERST# must be driven high by the driver, and W_DISABLE2# (pin 54) floats until GPIO1_A4 drives it. The M.2 card's own pull-ups on W_DISABLE# still back-feed the unpowered bank a little until LDO4 is on (card-dependent, < 0.3 mA). | CM3 datasheet §3.1.2; CM3 V1.322 schematic p.14 (VCCIO1 = VCCIO_ACODEC) and p.20 (LDO4); netlist: J501.52/53/54/55 reach J702.9, J702.2, J703.40, J703.38 with nothing else. | DT: `vccio_acodec` 3.3 V boot-on/always-on, `pmu_io_domains` vccio1-supply = vccio_acodec, pinctrl pull-up on GPIO1_B0/B1, drive GPIO1_A4 high for BT. Verify 3.3 V on J501 pins 52–56 with the driver loaded. | Sideband on VCCIO5/6/7 or PMUIO1 pins; CLKREQ#/WAKE# pull-ups from a rail that follows the bank. |
| m1 | Minor | CSI | **Data-to-clock mismatch is still 6.3 mm (D2, D3) against the CM3 rule of < 36 mil (0.9 mm) counting the module's lengths.** At 1.2 Gb/s that is about 40 ps = 0.05 UI, inside a D-PHY receiver's budget; at the 0.6 Gb/s that 1080p60 YUV422 needs it is 0.025 UI. The tight serpentines (0.4 mm between legs) couple a little, so the delivered compensation is probably 10–20 % less than the geometric length: budget 7–8 mm. D2 vs D3 lane-to-lane is 12.6 mm, which the CSI-2 lane aligner absorbs. | `gen/csimatch.py report` figures reproduced from pcbnew; CM3 datasheet §3.5.3. | Run the RK628D CSI at ≤ 1.2 Gb/s per lane (the format needs about half that); watch the CSI CRC/ECC counters at bring-up. | Route D2 outside the bundle and match all five totals to < 1 mm. |
| m2 | Minor | Impedance | **The 100 Ω pairs (0.10/0.10 mm) land between 95 and 105 Ω depending on how the solder mask is modelled; PCIe 0.14/0.10 at 85–92 Ω, USB 0.12/0.10 at 90–99 Ω.** My finite-difference solve with a 20 µm mask gives 95.4 / 89.7 / 84.7 Ω; the closed form without mask gives 113 / 105 / 97 Ω. All inside ±10 % only if JLCPCB's mask is as modelled; they are not "impedance controlled" unless the order says so. | `/private/tmp/claude-501/fable-review-3/fd.py`, `zcalc.py`; `checks/zsolve.py` (not re-runnable here: no scipy) reports 92.6 Ω. | Keep JLC04161H-3313 selected; add "100 Ω diff 0.10/0.10, 90 Ω 0.12/0.10, 85 Ω 0.14/0.10 on L1/L4" to the order remarks so JLCPCB flags a mismatch. | Ask JLCPCB's calculator for the exact widths and route to them. |
| m3 | Minor | PCIe / USB layout | **PCIe TX and REFCLK are not coupled (gaps 0.2–0.7 mm), TX_N has 6 vias and TX_P 4, RX has 2 + 2 and 0.33 mm P/N skew (> 12 mil), REFCLK 54 mm on B.Cu; the layer-change vias near J702 have no GND via within 2.4–5 mm.** USB_BT_DM has 6 vias and DP none. Gen1 Wi-Fi card and USB for BT: margin, not function. | pcbnew per-net lengths/vias; `checks/returnpath.py` (25 vias over 1 mm from a GND via). | `max-link-speed = <1>` if the link is unstable; check `lspci` LnkSta / AER. | Coupled pairs, symmetric vias, a GND via per pair via, ≤ 2 vias each. |
| m4 | Minor | Ethernet layout | **MDI pairs have 0.64–0.68 mm intra-pair skew (25–27 mil) against the CM3 rule of < 12 mil.** At 125 MBd this is about 4 ps, harmless, but it is the one high-speed rule the Ethernet routing breaks. | pcbnew: MDI0 53.41/54.05, MDI1 59.86/59.22, MDI2 68.75/69.44, MDI3 69.73/69.05 mm. | None. | Tune the four pairs. |
| m5 | Minor | HDMI out 5 V | **AP22804AW5 limits at 2.7–3.3 A (0.45 A into a dead short), not an HDMI-class 0.5 A.** A faulty sink loads 5V_SYS, which also feeds 3V3_IO and 1V1_628; HDMITX_5V runs on 0.25 mm traces. | AP22804 datasheet: ILIMIT 2.7/3.0/3.3 A, ISHORT 0.45 A. | None for bring-up. | 0.5 A-class switch or polyfuse. |
| m6 | Minor | Input power | **F101 (3 A hold, 30 V) and J102 (JST PH, 2 A/contact) are below the worst-case input current at 6 V (about 4 A at full load).** Typical 7 W is 1.2–1.3 A. | BOM: C48985875, C131337; `checks/irdrop.py` VIN case. | Keep the battery load realistic; the fuse trips, it doesn't fail. | 4–5 A fuse; XT30 / JST VH. |
| m7 | Minor | Power layout | **Switch nodes and feeds:** LX_5V/LX_SOM 0.3 mm × 2 mm necks for 3 A; SW_IO changes layer through three vias; 1V1_628 has 0.127 mm segments at 0.45 A (101 A/mm²); U106's nearest input capacitor is 3.1 mm from pin 3. | `checks/irdrop.py`; pcbnew widths. | None. | Switch nodes as short F.Cu copper areas; 0.5 mm 1V1 trunk; 100 nF at U106 pin 3. |
| m8 | Minor | USB-C | **No ESD on CC1/CC2 and no TVS on VBUS_C**; USBLC6 covers D+/D− only, SMBJ20CA sits after D103. | Netlist. | None. | 5 V ESD array on CC1/CC2, 20–24 V TVS on VBUS_C. |
| m9 | Minor | ADC | **VIN_SENSE has no clamp:** 1.55 V at 17 V, 1.8 V (full scale) at 19.8 V, 2.9 V during an SMBJ20CA clamp (32 V). | `gen/power.py`; SMBJ20CA Vc. | None. | BAT54 to SOM_1V8. |
| m10 | Minor | CEC option | **R216 (0 Ω, DNP) would tie the 3.3 V CEC bus to J68-151, the 5 V side of the module's level shifter.** | CM3 schematic HDMI sheet. | Leave R216 unfitted. | CEC_GPIO on a plain 3.3 V GPIO. |
| m11 | Minor | Case | **The roof labels are on the wrong light pipes.** `case.py` LIGHTPIPES puts "PWR" at (97.72, 18.47) = D601, "STATUS" at (101.18, 18.47) = D602, "WIFI" at (115.70, 11.98) = D603. On the board D601 is the white STATUS LED, D602 the blue WIFI LED and D603 the red PWR LED (`gen/board_io_sheets.py` order; BOM: D601 white, D602 blue, D603 "red PWR"; R603 2.2 kΩ from 3V3_IO is on D603). | `case/case.py` line 58; `fab/relay-bom.csv`; pcbnew D601–D603 positions. | Swap the engraved labels in `case.py` before printing (PWR ↔ WIFI, STATUS stays wrong as written: order should be STATUS, WIFI, PWR). | Same. |
| m12 | Minor | SY8303 timing | **RFS = 210 kΩ programs 500 kHz by the formula (105/RFS), the bottom of the part's 500 kHz–2.5 MHz range; with the ±15 % oscillator tolerance it runs down to 425 kHz.** The datasheet's own example uses 200 kΩ. The 6.8 µH inductor is sized for 500 kHz; at lower frequency ripple rises to 1.2 A pp against the SRN6045TA-6R8M's 3.6 A rms rating (BOM comment says "5A"). | SY8303 datasheet p.2 features, pin table (Fsw = 105/RFS), electrical table (RFS = 200k → 0.5 MHz, ±15 %); LCSC C2041457 description "3.6A". | None; measure Fsw at bring-up. | 180–200 kΩ; a 6.8 µH part rated ≥ 4 A. |
| m13 | Minor | HDMI in | **HPD to the camera is driven at 3.3 V through 22 Ω from the RK628D**, in spec (≥ 2.4 V) and as DshanPi, but with less margin than a 5 V-derived HPD against sources that detect near 2 V with a 10 kΩ load. | `gen/hdmi_in.py` R213; RK628D K8. | Test with the target cameras. | Transistor pulling HPD to HDMIRX_5V. |
| m14 | Minor | Supply | **RK628D (C2843533) shows 27 pcs at JLCPCB; the magjack is hand-fitted; most other BOM numbers could not be looked up today** (the community API returned nothing for 20 of 30 numbers tried). | jlcsearch queries Oct 25. | Order now; keep the DigiKey/Mouser magjack plan. | Second source for the RK628D; a stocked jack. |
| n1 | Note | Gerbers / fab files | The Gerbers reflect the current board: jack pads and slots at the new positions, the CSI meanders on F.Cu and B.Cu, the 3313 job stackup, outline 120 × 100 mm (edge extents 30–150 / −130–−30), 16 drill tools from 0.15 mm, 15 slots (USB-C, HDMI shells, jack). Against the pre-M1 backup only the four copper layers and the PTH drill differ; mask, paste, silk and outline files are the same size. | `/private/tmp/claude-501/fable-review-3/` Gerber parse. | — | — |
| n2 | Note | Via-in-pad | 119 vias lie inside SMD pads (0.15–0.3 mm drills, including U102's exposed pad, Q201, J501 pins, many 0402s). Fine only with the "epoxy filled and capped" option the Y6 cart carries. | pcbnew; `orders/…quote.md`. | Keep the option on any re-quote. | Fan out beside pads. |
| n3 | Note | JLCPCB rules | 0.09 mm tracks and clearances (In1 RK628D_3V3, I2C_628_SCL), 0.15 mm drills, 0.3 mm vias, 0.3 mm copper-to-edge, closest hole-edge-to-hole-edge 0.278 mm (two 0.15 mm vias at (99.08, 97.57)/(99.5, 97.65) under J701): all at JLCPCB's 4-layer limits. Confirm the hole-to-hole figure against their current capability page. | `relay.kicad_pro` rules; pcbnew hole scan. | — | 0.1 mm / 0.3 mm margins. |
| n4 | Note | CM3 connectors | J701–J703 pads coincide with Radxa's IO board on all 300 pins (`b2bfit.py` 0.0000 mm, mirror rejected). The CPL rotation for them is derived from the pad-row aspect (0° / 90°); if JLCPCB's DF40C-100DS model zero differs by 180° the receptacle is still right, because the DF40 receptacle is 180° symmetric and the contact positions, not the part's pin labels, carry the signals. Radxa's J68 has four extra GND pads (201–204) that this footprint lacks: still unexplained. | `checks/b2bfit.py`; `gen/fab.py _centre_cm3`. | — | Find out what pads 201–204 are. |
| n5 | Note | Module keep-out | No top-side part inside the module outline (x 68.5–123.5, y 60–100) except the MOUNT_CM3 holes; two bottom parts under it. 1.5 mm stack: Radxa allows no components under the module, satisfied. 2.6 mm holes on 47.95 × 33.0 mm for M2.5 standoffs. | pcbnew. | 1.5 mm M2.5 standoffs in the kit. | — |
| n6 | Note | Magjack mechanics | JK0654219NL p.2: shield tabs (Ø1.57) 18.42 mm in front of pin row 1, pegs (Ø3.20) 3.18 mm behind the tabs, front face about 7.2 mm in front of the tabs (scaled from the side view). KiCad's footprint has the same pins/pegs/tabs and a front face 7.7 mm beyond the tabs, so the jack face is 4.6–5.1 mm past the board edge; the case wall ends 2.6 mm past the edge, so the face protrudes 2–2.5 mm (README says 2.9 mm). Pin map MX1–4/CT1–4 and the internal Bob Smith network verified on p.4. | Datasheet images; KiCad `RJ45_Pulse_JK0654219NL_Horizontal`. | — | Line the jack up with the wall. |
| n7 | Note | USB OTG | VBUSDET is tied permanently high (10 kΩ to SOM_3V3): the module always believes a USB host is attached, which is what flashing and the gadget need, but it is a deviation from the datasheet's divider. The datasheet's 2.2 Ω series and common-mode choke on OTG are not fitted. USB_OTG0_ID open, USB_5V_IN open: correct. | CM3 datasheet §3.2.1, §3.1.1; netlist. | — | 0 Ω/CMC pads; VBUSDET from VBUS_C through a divider. |
| n8 | Note | RK628D straps | I2C_ADDR 10 kΩ to GND (0x50; internal pull-down too), TEST to GND, INT/SPIBOOT (J3) internal pull-down with no board pull → normal boot; RESETN internal pull-up, 100 nF, driven by GPIO3_C2 (VCCIO5, 3.3 V); EFUSE_VDD_2V5 held at 0 V through 100 Ω (datasheet: only needed for programming). Power table: VCCIO1/2 3.3 V, DVDD 1.1 V, matched. | RK628D datasheet tables 2-1/2-2/2-3. | — | — |
| n9 | Note | SPI/BOM labels | Harmless BOM/CPL cosmetics: the three CM3 receptacles are listed under footprint "Radxa_CM3_J69" and value "CM3 J69" (one LCSC number, so JLCPCB does not care); SW602 is listed under "RESET"; "6.8uH 5A" for a 3.6 A rms part; "22uF" vs "22uF/10V" grouped by value. | `fab/relay-bom.csv`. | — | Tidy the Comment column. |
| n10 | Note | Docs | REV_A_SPEC still says 90 × 65 mm, "all SMD on top", "L3 power", 47 µF polymer, HDMI C2902698 (the BOM and footprint are Molex 2086581001, C916313, and the only HDMI drawing in `datasheets/` is the Kmtw part, not the Molex one). | Files named. | Update. | — |
| n11 | Note | ESD arrays | Tech Public RCLAMP0524P p.1: pins 6/7/9/10 NC, diodes on 1/2/4/5. Every line crosses both pads of its column in copper (TMDS by the trace, D203/D403 by the 0.2 mm links), so the NC pins carry nothing. 0.35 pF I/O-to-I/O; fine at 1080p60. | Datasheet image; pcbnew. | — | Footprint with the links built in. |
| n12 | Note | Impedance tooling | `checks/zsolve.py` and `tline.py` need scipy/ngspice; neither Python here has scipy, so the project's 92.6 Ω figure was not reproduced. My own two estimates bracket it (m2). | — | — | Pin the Python environment for `checks/`. |

## What was verified as correct, and how

**CM3 pin map.** Every net on J701/J702/J703 was listed from the fresh netlist against `gen/cm3_pinout.json` (V1.32:
J69-37 UART9_TX_M1, J69-93 SARADC_VIN0, J1-14 SARADC_VIN3, J1-26 NC, J1-34 GPIO0_D3). All assignments land on the
intended functions: MDI0–3 (J69 12/10, 4/6, 11/9, 3/5), CSI D0–D3/CLK0 (J68 117/115, 123/121, 130/128, 136/134,
129/127), PCIe TX/RX/REFCLK (122/124, 116/118, 110/112), CLKREQn/PERSTn/WAKEn all `_M2` (J68-102, J68-109, J1-38),
USB_OTG0 (105/103), USB2_HOST2 (J1 63/65), HDMI TX pairs/HPD/DDC/CEC, I2C2_M1 (35/36), I2C4_M0 (38/44), UART2_M0
(51/55), UART9_M1 (J69-37/J1-36), CIF D0–D15/HREF/VSYNC/CLKIN, PMIC_RESET_KEY, VBUSDET, 5 V ×6, +3V3 ×2 + GPIO_VREF,
+1V8 ×2. Unused: PWRON_KEY (RK817 pulls it up itself), USB_OTG0_ID, USB_5V_IN, VCC_BAT, TS, CLK1, DSI, eDP, USB3,
HOST1/3, audio, SARADC 1/2: all allowed open.

**I/O bank map, derived from the CM3 V1.322 schematic by page:** PMUIO1 = GPIO0_A0–A7 (VCC3V3_PMU, 3.3 V); PMUIO2 =
GPIO0_B0–D1 (1.8 V); OSC = GPIO0_D3–D6 (1.8 V only); VCCIO1 = GPIO1_A0–B3 (VCCIO_ACODEC, software); VCCIO2 =
GPIO1_B4–D4 (VCCIO_FLASH 1.8 V); VCCIO3 = GPIO1_D5–GPIO2_A2 (VCCIO_SD); VCCIO4 = GPIO2_A3–C6 (VCCIO_WL = 1.8 V);
VCCIO5 = GPIO3_A1–C5 (R43 0 Ω to VCC_3V3, R42 NC); VCCIO6 = GPIO3_C6–GPIO4_C1 (GPIO_VREF through R24, tied to +3V3
here); VCCIO7 = GPIO4_C2–D1 (VCC_3V3). Against that map: INT GPIO3_C3 and RESET_N GPIO3_C2 (VCCIO5), I2C2 GPIO4_B4/B5
and LED_STATUS GPIO4_B1 (VCCIO6), LED_WIFI GPIO0_A5, PLUGIN_DET GPIO0_A4 and WIFI_DISABLE GPIO0_A0 (PMUIO1), CEC_GPIO
GPIO4_D1 and SDI UART GPIO4_C5/C6 (VCCIO7), DVP/SDI GPIO3_C6–GPIO4_C1 (VCCIO6), SDI GPIO5–7 GPIO3_A1/B4/C1 (VCCIO5);
1.8 V by design: PWR_EN GPIO0_C4 into an NPN base through 1 kΩ (1.1 mA, saturates the 0.3 mA collector load), debug
UART GPIO0_D0/D1. VCCIO1 holds the four sideband lines (M3). `checks/iolevels.py` flags 0 and agrees with the map.

**RK628D.** All 144 balls in `gen/hdmi_in.py` against datasheet tables 2-1/2-2 (checked by name for every connected
ball: HDMIRX pairs L12/L11…H12/H11, HPD K8, SCL L8, SDA M8, CEC K9, EXTR G9/M3, REXT B1, OSC M9/L9, RESETN H4,
TEST D7, I2C_ADDR C7, I2C L3/K3, INT J3, CSI TX0–TX4 on G/F/E/D/C 1–2, supplies as table 2-2). Straps as n8.
Supplies: 1.1 V and 3.3 V only, ferrite-split analog rails, 4.02 kΩ MIPI_REXT, 2 kΩ EXTRs. Crystal X322524MOB4SI is a
12 pF CL part; 18 pF + 18 pF with ~3 pF stray ≈ 12 pF. CSI lane order TX0/1/2/3/4 = D0/D1/CLK/D2/D3, P to P into J68.
Decoupling: 22 capacitors on the back under the BGA with 0.15 mm vias in pads. Power gate: AO3401A gate pulled to
3V3_IO by 10 kΩ, NPN pulls it to −3 V (RDS(on) < 85 mΩ at −2.5 V); 1V1 enable follows RK628D_3V3 with 10k/100n.

**Power tree.** SY8303: 0.6 × (1 + 110/15) = 5.00 V; EN 100k/39k turns on at VIN ≤ 5.35 V (VENH ≤ 1.5 V; at a 6.0 V
battery VIN ≈ 5.6 V); EN/FS/FB absolute max 40 V; UVLO 4.35 V; BS 10 nF (datasheet value); 2 × 4.7 µF/50 V in + 47 µF
bulk; 2 × 22 µF/25 V out (≈ 25–30 µF after bias). Dropout: 94 % duty keeps 5 V down to ≈ 5.6 V in. TPS563201:
0.768 × 4.3 = 3.30 V, 0.768 × 1.431 = 1.10 V; EN 1.6 V threshold with 225–900 kΩ internal pull-down, so 100k/100n from
5V_SYS (≈ 4 V, ~8 ms) and 10k/100n from RK628D_3V3 (3.2 V, ~1 ms); VIN 4.5–17 V met by 5V_SYS; EN abs max 19 V;
2.2 µH / 1.5 µH per the datasheet table; current limit 3.3–5.1 A above the inductors' 4.6/4.95 A ratings only in a
fault. CH224A: VHV (pin 1) and VBUS (pin 8) both on VBUS_C ("VBUS must be shorted to VHV" for the A), 1 µF/50 V,
CFG1 6.8 kΩ = 9 V, PG open-drain active low into Q101's gate with 100 kΩ to VBUS_C; AO3401A VGS −9 V within ±12 V; the
body diode cannot back-feed a PC port because D103 is in series; with a 5 V-only source PG stays high, Q101 off, as
the spec intends. AP22804AW5-7: active-high EN tied to IN, 2.7–5.5 V in. SMBJ20CA (standoff 20 V) on VIN ≤ 17 V.
VIN_SENSE 100k/10k: 1.55 V at 17 V. `irdrop.py`: VIN 23 mV at 2.8 A, 5V_SOM 8 mV at 3 A, 3V3_IO 42 mV at 0.6 A at the
M.2 socket (fed by 0.5 mm F/B copper into pins 2/4/72/74).

**Connectors and ESD.** HDMI J201/J401: pins 1–19 in standard order, shells to GND, slots 14.5 × 5.96 mm match the
Molex/Kmtw pattern; TMDS pairs flow straight through D201/D202/D401/D402; DDC/HPD/CEC through D203/D403 with the copper
links (n11); HDMI OUT HPD straight to J68-153 (module: 1 kΩ series, 100 kΩ pull-down), DDC 2.2 kΩ to HDMITX_5V (module
level-shifts); HDMI IN DDC 47 kΩ to the source's 5 V via MBR0530, CEC 27 kΩ via MBR0530, 22 Ω series, HPD 22 Ω, plug
detect 2k/10k NPN into GPIO0_A4 with 10 kΩ to 3V3_IO (the module's Q4 on GPIO0_D4 also reaches that pin: keep TF_DET
low). Ethernet: J301 pads 11/10/12, 4/5/6, 3/2/1, 8/9/7 = MX1±/CT1 … MX4±/CT4 per the JK0654219 schematic (p.4), cable
side RJ45 1/2, 3/6, 4/5, 7/8, 75 Ω + 1 nF Bob Smith inside the jack, centre taps 1 µF to GND; pad grid 2.03/2.54 mm,
0.89/1.02/1.57/3.2 mm holes per p.2. M.2 E-key: 2/4/72/74 3.3 V, 3/5 USB, 35/37 PETp/n → PCIE_RX, 41/43 PERp/n ←
PCIE_TX through C501/C502 (0 Ω; the module's C54/C55 are the TX AC caps), 47/49 REFCLK, 52 PERST#, 53 CLKREQ#,
54 W_DISABLE2#, 55 PEWAKE#, 56 W_DISABLE1#, 2 × 22 µF + 2 × 100 nF at the socket; TE 2199230-4 footprint. USB-C:
TYPE-C-31-M-12, CC1/CC2 to the CH224A only (Rd inside), D+/D− both rows through USBLC6 (pin 5 floating, correct at
9 V). DC jack: PJ-002AH pads 1 = centre (VDC), 2 = sleeve (GND), 3 = switch (open), slots 1 × 3 mm, orientation as in
the verdict; 2.0 mm centre pin (use 5.5 × 2.0 mm plugs). Debug header TX/RX/GND, RESET to PMIC_RESET_KEY (module has
22 Ω + ESD), RECOVERY 10 kΩ to SOM_1V8 + 1 nF.

**Layout.** 120 × 100 mm, GND zones on all four layers (In1 11 211 mm², In2 10 886 mm²); In1 carries only 22 short
segments, all under U201 (RK628D_3V3, RESET_N, INT, SCL, AVDD_1V1, RX_SDA), none under a CSI/HDMI/PCIe/USB/MDI
trace. HDMI OUT clock-to-data with the module's lengths < 480 mil. CSI, HDMI IN/OUT P/N ≤ 0.19 mm, all on F.Cu over In1;
D2/D3 B.Cu stretches over In2 (GND) with GND vias 0.7–1.0 mm from each signal via. 1047 vias (614 × 0.25/0.45,
386 × 0.15/0.3, 47 × 0.3/0.6). Copper-to-edge ≥ 0.3 mm; J301's intentional overhang is the only silk-edge exception
(`relay.kicad_dru`). Courtyards: 0 overlaps. Fiducials 3 + 3, out of BOM/CPL.

**Fab files.** BOM 59 lines, every line with an LCSC number; `gen/lcsc-mpn.json` resolves each to the intended MPN and
package (DF40C-100DS-0.4V(51), RK628D WBBGA-144, CH224A ESSOP-10, SY8303AIC TSOT-23-8, TPS563201DDCR, AP22804AW5-7,
RCLAMP0524P DFN2510-10, Molex 2086581001, TE 2199230-4, PJ-002AH, JK0654219NL, TYPE-C-31-M-12, X322524MOB4SI 12 pF,
1812L300/30GR, TL3342F160QG, SS54, SMBJ20CA, MBR0530T1G, SRN6045TA-6R8M, SWPA6045S2R2NT/1R5NT). Schematic ↔ BOM ↔ CPL:
191 components, 176 placed in both files, the 7 DNP (R202, R216, R501–R503, R505, J602) in neither, fiducials/test
points/holes excluded. CPL coordinates are the Gerber coordinates (KiCad page origin, Y up); J701–J703 centred on
their pad fields.

**Case (2D).** Openings at board x 24/79 (HDMI), 16 (USB-C), 42 (DC), 99 (RJ45 body centre 98.9); M3 holes (4,4),
(4,96), (116,36), (116,68); pinholes over SW601/SW602; light pipes over D601–D603 (labels wrong, m11); roof vents over
the module (x 38.5–93.5, y 30–70) and U103/U104.

## What could not be verified

- **JLCPCB's model orientation for every polarised part (M1):** only their viewer shows it.
- **Impedance with the project's own solver (n12):** no scipy in either Python; two independent estimates bracket it.
- **The M.2 2230 standoff H501 (28.0 mm from J501's origin, 24.2 mm from the pad rows):** no TE drawing or M.2 module
  drawing in the repo. Check with a card on a 1:1 print, or the PCI-SIG M.2 Figure for Type 2230.
- **The Molex 2086581001 face position** (README: 1.0 mm past the edge): the only HDMI drawing in `datasheets/` is the
  Kmtw D-HDMIM19P-F000; its slot pattern matches, its face position was not compared.
- **The RK3566 D-PHY skew budget and the RK628D's lane-rate options (m1):** Rockchip documents not in the repo.
- **Whether Radxa's stock device tree already powers VCCIO_ACODEC at 3.3 V (M3).**
- **Part stock for most of the BOM (m14):** the community API served only 10 of 30 numbers.
- **The DF40 pads 201–204 on Radxa's J68 (n4).**
- **Real heights in the case (module heatsink, Wi-Fi shield, switch actuators) and the 3D clash check:** CadQuery not run.
- **RK628D 1.1 V current and sequencing:** no design guide; the scheme copies DshanPi (3.3 V first, 1.1 V ~1 ms later).
- **JLCPCB's current hole-to-hole minimum (n3).**

## Software / device-tree requirements the hardware imposes

- `vccio_acodec` (RK817 LDO4) 3.3 V, boot-on, always-on; `pmu_io_domains` vccio1-supply = vccio_acodec; pinctrl
  pull-ups on GPIO1_B0 (CLKREQ#) and GPIO1_B1 (WAKE#); PERST# = GPIO1_B2 active low; BT enable = GPIO1_A4 high,
  Wi-Fi enable = GPIO0_A0 high.
- Disable `sdmmc0` or drop its `cd-gpios` (GPIO0_A4 = PLUGIN_DET, active low) and `pwren` (GPIO0_A5 = LED_WIFI);
  keep GPIO0_D4 (TF_DET) low or unused.
- RK628D on `i2c2` (`i2c2m1_xfer`), address 0x50, reset GPIO3_C2 (active low), interrupt GPIO3_C3, power enable
  GPIO0_C4 (raise early; the I2C and CEC pull-ups hang on RK628D_3V3), plug detect GPIO0_A4; CSI 4-lane on CLK0,
  ≤ 1.2 Gb/s per lane; check CRC/ECC counters.
- PCIe: `max-link-speed = <1>` if Gen2 is unstable (m3).
- UART2_M0 console at 1.8 V (1.5 Mb/s); USB OTG0 peripheral (VBUSDET tied high); SARADC_VIN0 recovery; SARADC_VIN3 =
  VIN/11 (full scale 19.8 V).
- LEDs: STATUS GPIO4_B1, WIFI GPIO0_A5, active high. PD status is not readable by the SoC; use VIN_SENSE (≈ 8.6 V on a
  9 V contract) to tell USB-C from battery.
- Flash with 12 V on the DC jack plus USB-C for data (a 5 V-only source does not pass Q101).

## Comparison with the four earlier reports

**TEST_REPORT.md.** Confirmed: DRC/ERC/parity clean; regulator values, Fsw, EN thresholds; CH224A configuration; USBLC6
pin 5; fiducials; the VIN neck fix (0.8–1.6 mm); "CM3 connectors exact"; "magjack match" (re-verified from the
datasheet images); the DC-jack pin match and the 2.0 mm plug note; the Oct 25 pin-fix table; the CSI table after
`csimatch.py` (my numbers are identical). Disputed: the thermal estimate after the vias is still an estimate (M2);
"Ready to order" on Oct 24 preceded the ESD-link, jack and CSI fixes, all of which were needed. Its U106 input-cap
compromise stands (m7).

**REVIEW_INDEPENDENT.md.** M1/M2/M3/M5/M8 (1.8 V pins): confirmed fixed and complete; my bank derivation matches. M4
(USB-only flashing): confirmed, documented. M6 (CSI skew): now reduced from 24 to 6.3 mm; I rate the remainder Minor
(m1). M7 (AP22804), M9 (switch nodes), M10 (fuse/JST), M11 (uncoupled pairs), M12 (VCCIO1), M13 (TF_DET), N1–N7:
confirmed, still open as the project accepted. Its "DC jack footprint matches" was right about pads and silent on
direction; now both are right.

**REVIEW_FABLE.md.** B1 (ESD pass-through on NC pins): confirmed from the datasheet image; the links are in the Gerbers;
fix complete. M1 (double TX AC coupling): confirmed from the CM3 schematic (C54/C55); 0 Ω fix correct. M2 (CSI):
mostly fixed (m1). M3 (U104 thermal): confirmed, vias present, still Major (M2). M4 (stackup): fixed and enforced.
m1–m11: confirmed; m2 (3V3_IO at the M.2) is 0.5 mm copper now and acceptable; m8/m9 (via-in-pad, rotations) remain
as n2/M1. Its n7 ("case openings centred") is confirmed in position; it did not check the roof labels (m11).

**REVIEW_FABLE_2.md.** B1 (jack backwards): confirmed fixed and complete (verdict section). M1 (CSI): fixed to 6.3 mm as
it predicted; the claim "D2 can't go further without leaving the bundle" is consistent with the layout. M2 (thermal):
vent added, still Major (M2). M3 (VCCIO1 sideband): R502/R503/R505 now DNP as proposed; the DT dependency remains
(M3). M4 (CPL rotations): two corrections added; the viewer check is claimed but not reproducible, and the CPL has been
regenerated since (M1). M5 (parts): L103/L104 now on stocked NT parts (confirmed in BOM); RK628D still 27 pcs (m14).
m1–m14 and n1–n12: confirmed; m6 (3V3_IO feeds) and m11 (ESD land pattern) unchanged and accepted; m14 (case details)
not re-examined in 3D. New since that review: m11 (roof labels), m12 (RFS at the bottom of the range), m4 (MDI skew),
n6 (magjack geometry verified from the drawing), and the Gerber/backup comparison (n1).

**Net result of today's script changes:** the jack turn, the CSI meanders, the three DNPs, the inductor swap and the
rotation corrections are all present and correct in the manufactured files. What remains is a last look at JLCPCB's
placement preview on the Y6 upload, the device tree work, and the thermal measurement in the case.
