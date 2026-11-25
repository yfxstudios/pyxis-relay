# Rev A: second pre-fab review (Fable, Oct 25, 2026, after the pin moves, ESD links, thermal vias and stackup)

Scope: `relay.kicad_sch` and its sheets (netlist exported with kicad-cli), `relay.kicad_pcb` and `routed.kicad_pcb`,
the fab outputs in `fab/` (Gerbers, drills, job file, BOM, CPL, FAB_NOTES), the generators in `gen/`, the checks in
`checks/`, the case in `../case/`, against the datasheets in `../datasheets/`, the LCSC/JLCPCB listings (fetched today)
and the JLCPCB order notes in `../orders/`. ERC, DRC (`--schematic-parity --severity-all`), the Gerber/drill export and
`checks/irdrop.py`, `returnpath.py`, `b2bfit.py` were re-run. The board was dumped with pcbnew and analysed with scripts
kept in `/private/tmp/claude-501/fable-review-2/`. `REVIEW_INDEPENDENT.md`, `REVIEW_FABLE.md` and `TEST_REPORT.md` were
read only after the findings were formed. Nothing in the project was changed except adding this file.

**Status (Oct 25, later):**
- **Fixed:** B1 (jack turned) and M4 (two rotation fixes after a part-by-part viewer check).
- **Rev A part done:**
  - M2: case vent; thermal vias were added earlier.
  - M3: R502/R503/R505 not fitted; device tree note.
  - M5: L103/L104 swapped to stocked parts.
- **M1 mostly fixed:** worst data-to-clock skew is 6.3 mm, from 24 mm (`gen/csimatch.py`). D2 can't go further
  without leaving the bundle.
- See TEST_REPORT.md, "Fixed on Oct 25, third pass".

## Verdict

**Do not order as is.** One blocker that none of the three earlier reports or the fab files caught:

- **The DC jack J101 faces the wrong way.** Its plug opening points into the board (toward F101) and its back wall,
  with the centre-pin boss, sits 1.25 mm from the rear edge, in the case's "DC IN" opening. Nothing can be plugged
  into it. Everything else about the DC input (footprint, pin numbers, part) is right; the footprint is simply
  placed 180° out and 12 mm too far back. This is a 15-minute fix in KiCad (rotate, move 12 mm inboard, re-route
  two short tracks) and a DRC + `gen/fab.py` re-run. If the boards are ordered as they are, the DC input is lost:
  the unit runs from USB-C PD or the NP-F lead only, or a panel-mount jack is wired to J101's pads.

Everything that was changed by script today checks out against the files that will be manufactured: the six pin
moves land on 3.3 V banks (bank map re-derived from the CM3 V1.322 schematic), the DVP_D6 re-route on In2 is under
no high-speed trace, the RClamp pass-through links and the six thermal vias are in the Gerbers and drill file, the
C501/C502 0 Ω links are in the BOM, and the stackup block in the job file is JLC04161H-3313. The Gerbers in `fab/`
are byte-identical (timestamps aside) to a fresh export of `relay.kicad_pcb`.

The Majors below are survivable for a rev A bring-up with the listed workarounds; all need a rev B change.

**Counts: 1 Blocker, 5 Major, 14 Minor, 12 Note.**

## Findings

Coordinates are KiCad board coordinates (mm); board coordinates = KiCad minus (30, 30).

| ID | Sev. | Area | What's wrong | Evidence | Rev A workaround | Rev B fix |
|---|---|---|---|---|---|---|
| B1 | **Blocker** | DC input, mechanical | **J101 (PJ-002AH) is placed with its mouth toward the board interior.** The footprint's pin 2 (sleeve) is 6 mm *toward the plug opening* from pin 1 (centre pin, at the rear of the jack); the body runs 13.8 mm from pin 1 toward pin 2. On the board pin 1 is at (72.0, 127.9) and pin 2 at (72.0, 121.9), so the body spans y 114.15–128.75: the opening is at y ≈ 114 (facing F101/D103) and the rear face at 128.75, 1.25 mm from the edge at y = 130. The case's DC opening (`case/case.py` line 49, "its face is 2.1 mm inside the board edge") was measured to the rear boss. The README ("DC jack: its mouth now sits at the board edge") describes the move that put the back of the jack at the edge. | pcbnew: J101 pads 1 (72.0,127.9) VDC, 2 (72.0,121.9) GND, 3 (67.3,124.9) NC; F.Fab outline y 114.15–128.75 with the chamfered rear corner at (75.7–76.55, 127.85–128.75). KiCad `BarrelJack_Horizontal`: pads (0,0), (−6,0), (−3,4.7), body x −13.8…+0.9, STEP bore at x −13.7…−2.0. CUI PJ-002A drawing p.2: centre-pin terminal 0.7 mm from the rear, 13.7 mm from the front. `renders/rev_a_3d_top.png`: open face toward F101, round boss at the edge. `case/out/view-rear.png`: boss visible in the DC opening. | **Fix before ordering:** rotate J101 to +90°, place pin 1 at about (72.0, 116.5) so the opening is 0.5–1 mm inside the edge (body x 67.5–76.5 stays clear of F101 at x 78.5 and D103), re-route VDC and GND (2 tracks), DRC, `gen/fab.py`. The case opening then fits (11.4 × 11.6 mm, axis 6.5 mm above the board). If ordered as is: delete J101 from the BOM/CPL and wire a panel-mount 5.5/2.0 mm jack to pads 1/2; USB-C PD and the NP-F lead still work. | Same, plus a mouth-at-edge note in `gen/`. |
| M1 | Major | CSI, length | **CSI data-to-clock mismatch, counting the module's internal lengths, is up to 27 mm against the CM3 rule of < 36 mil (0.9 mm).** Totals carrier + module (mm): CLK 33.50 + 35.5 = 69.0; D0 29.38 + 61.1 = 90.5; D1 31.44 + 35.3 = 66.8; D2 26.15 + 39.7 = 65.9; D3 29.16 + 64.1 = 93.2. Spread 27.3 mm ≈ 180 ps. At 1.2 Gb/s per lane that is 0.22 UI, more than the D-PHY receiver's skew budget (the RK3566 has no deskew below 1.5 Gb/s). The carrier alone is already 7.35 mm and in the wrong direction for D1/D2. | CM3 datasheet §3.5.3 (text lines 1068–1096): "Data to clock mismatch <36mil", module lengths CLK0 1395.6/1400.5, D0 2394.8/2412.9, D1 1371.8/1411.7, D2 1565.5/1561.5, D3 2497.6/2546.4 mil; §3.5.4: "equal-length design … by controlling the total wiring length between the compute module and the baseboard". Carrier lengths from pcbnew (track only; P = N to 0.00 mm). | Run the RK628D CSI TX at the lowest lane rate that carries the format: 1080p60 YUV422 on 4 lanes needs about 0.6 Gb/s per lane, where the mismatch is 0.1 UI. Watch the CSI CRC/ECC counters at bring-up. | Match the totals: about +24 mm on CLK, +26 on D1, +27 on D2, +3 on D0 (serpentines between U201 and J702). |
| M2 | Major | Power, thermal | **U104 (SY8303, 5V_SOM) exceeds its thermal budget at the module's rated 3 A.** TSOT23-8, θJA 60.2 °C/W, no exposed pad. At 12–17 V in and 5 V/3 A out the loss is about 1.3–1.7 W: 80–100 °C rise before the thermal vias, roughly 60–75 °C after them. In the closed case (no thermal path to the case, intakes below the board) ambient will be well above 25 °C. The 1.5 mm stack also puts the module's six 0.3 A DF40 contacts at 1.8 A, so 3 A is not reachable anyway, but 1.5–2 A sustained is. | SY8303 datasheet p.2 "θJA 60.2 °C/W", RDS(on); CM3 datasheet §3.1.1 (3 A); `checks/irdrop.py` VIN case 2.8 A into U104; six 0.6/0.3 mm GND vias confirmed in `relay-PTH.drl` (T3 0.300 at X96.76Y−107.75 etc.). Case: no lid boss to the module heatsink, side vents at z 3.5–5.5 mm (below the board). | Keep the module's sustained draw under about 1.5 A; thermocouple on U104 and the CM3 during the closed-case soak (PRODUCTION.md test 9). | A 5 V buck with an exposed pad (QFN/SOT-583 class) for both U103 and U104, and a lid boss with a thermal pad onto the module. |
| M3 | Major | PCIe/BT sideband, CM3 | **PERST# (GPIO1_B2), CLKREQ# (GPIO1_B0), WAKE# (GPIO1_B1) and BT_DISABLE# (GPIO1_A4) sit in VCCIO1 = VCCIO_ACODEC, which is RK817 LDO4 ("Codec vddio", 400 mA), off at power-up and set by software.** Until the device tree turns it on, those pads are unpowered while R502/R503/R505 (10 kΩ to 3V3_IO) back-feed them through the pad clamps, and the SoC cannot drive PERST#/W_DISABLE2#: no Wi-Fi/BT until the DT is right. With R501 DNP, PERST# rests on GPIO1_B2's reset pull-down, so the card stays in reset, which is the correct default. | CM3 V1.322 schematic p.20 (RK817 LDO4 → VCCIO_ACODEC, 4.7 µF), p.14 VCCIO1 domain; CM3 datasheet §3.1.2 ("VCCIO_ACODEC … typically off by default … activated later … from software"); netlist: BT_DISABLE_N = J703.40 + J501.54 + R505; PCIE_WAKE_N = J703.38 + R503; PCIE_CLKREQ_N = J702.2 + R502; PCIE_PERST_N = J702.9 + R501 (DNP). RK3568 datasheet §2.8: GPIO1_A0–B? under VCCIO1. | Device tree: `vccio_acodec` (LDO4) 3.3 V, always-on, boot-on; `pmu_io_domains` vccio1-supply = vccio_acodec; verify with a meter on J501 pin 54 (should read 3.3 V from R505 regardless, and GPIO1_A4 should toggle it). Keep R501 DNP. | Put W_DISABLE2#, PERST#, CLKREQ#, WAKE# on VCCIO5/6/7 or PMUIO1 pins (the hardware CLKREQ/WAKE functions are not needed for the RTL8822CE; GPIO works), or take the pull-ups from a rail that follows VCCIO1. |
| M4 | Major | Assembly, CPL | **Rotation of polarised parts in the CPL is unverified for everything outside `JLC_ROT`.** `gen/fab.py` corrects 13 references found in JLCPCB's viewer (Q101/Q201/Q202/Q203, U101–U106, U201, J201/J401). Not corrected and not checked: D101–D104 (SMA/SMB), D204/D205 (SOD-123), D601–D603 (LEDs), C102 (electrolytic), U401 (SOT-25: IN and OUT swap if its model needs +180° like the other SOT-23s did), Y201, J103, J101, J501, J301, and every bottom-side part. A wrong Schottky or TVS orientation on VIN is a dead or shorted input; a reversed U401 puts 5V_SYS on the wrong pin. The CPL was regenerated today after the pin moves, so any earlier preview check is void. | `gen/fab.py` JLC_ROT (lines 162–172 of the current file); `fab/relay-cpl.csv` (180 rows, Y negative = KiCad Y-up coordinates); JLCPCB's SMA diode and SOT-23-5 zero orientations differ from KiCad's for several library parts (known issue, cannot be checked offline). | Before paying: open the JLCPCB placement preview for order Y5 and check every polarised part's pin 1/cathode against the silkscreen. Fix any wrong one in `JLC_ROT` and re-upload. | Keep a verified rotation table per footprint (not per reference), stored with the generator. |
| M5 | Major | Supply | **Parts availability.** J301 Pulse JK0654219NL (C3179417): 0 at JLCPCB and LCSC, "PreSale" (already planned as hand-fit). L103 SWPA6045S2R2MT (C83455) and L104 SWPA6045S1R5MT (C98203): LCSC product pages return "Page Not Found" (delisted), JLCPCB has 93 and 83 pcs. U201 RK628D (C2843533): 27 pcs. L101/L102 SRN6045TA-6R8M (C2041457): 146 pcs, 2 per board. Enough for 5 boards, no reorder path for the pilot. | JLCPCB parts API and LCSC pages fetched Oct 25 (raw dumps in `/private/tmp/claude-501/fable-review-2/agent-parts/`). | Order now, before the quantities move; keep the Mouser/DigiKey magjack plan. | Second-source the RK628D; pick stocked 6045 inductors (Bourns SRN6045TA-2R2Y/-1R5Y class) and a stocked magjack. |
| m1 | Minor | PCIe layout | **PCIe TX and REFCLK are uncoupled (0 % of their length within 0.13 mm gap; gaps 0.2–0.7 mm), TX_N has 6 vias and TX_P 4, and the layer-change vias near J702 have no GND return via within 4–5 mm.** Uncoupled 0.14 mm traces on this stack are about 104 Ω differential against 85 Ω. TX_N also passes within 0.5 mm of L104 pin 1 (SW_628, the 1.1 V switch node) and vias beside U106. The RTL8822CE is a Gen1 (2.5 GT/s) card, so this is margin, not function. | pcbnew coupling histogram (section F of `board2.py`): PCIE_TX 0 %, PCIE_REFCLK 0 %, PCIE_RX 94 %; via lists; `checks/returnpath.py`: PCIE_TX/RX/REFCLK vias at (56–59, 25–28) board coords with nearest GND via 2.4–5.0 mm. | Force Gen1 in the device tree (`max-link-speed = <1>`) if the link is unstable at Gen2; check `lspci -vv` LnkSta and AER counters. | Route TX and REFCLK as coupled 85 Ω pairs, symmetric vias, a GND via beside each pair via; keep the lane 2 mm from L104. |
| m2 | Minor | USB layout | **USB_BT_DM has 6 vias and 19.5 mm on B.Cu; USB_BT_DP has none and is all on F.Cu.** Lengths match (93.47/93.47 mm) but the pair is uncoupled and asymmetric; mid-route vias at (74.4, 77.15) and (62.45, 70.65) are 3–4 mm from the nearest GND via. USB_OTG pairs: uncoupled but symmetric. The CM3 datasheet also asks for a common-mode choke and 2.2 Ω series on OTG; neither is fitted. | pcbnew via list; `returnpath.py` USB_BT_DM entries; CM3 datasheet §3.2.1. | None; Bluetooth over USB runs at full/high speed with margin to spare over 10 cm. | Route coupled, symmetric; add 0 Ω/CMC pads on OTG. |
| m3 | Minor | Input power | **F101 (3 A hold, 5 A trip, derating to about 2.3 A hold at 60 °C) and J102 (JST PH, 2 A per contact) are below the worst-case input current at 6 V (about 4 A).** Typical 7 W is about 1.3 A. | LCSC C48985875 (1812L300/30GR), C131337; `checks/irdrop.py` VIN case. | Keep the battery load realistic; the fuse trips, it doesn't fail. | 4–5 A hold fuse; XT30 or JST VH for the battery lead. |
| m4 | Minor | HDMI out 5 V | **AP22804AW5 limits at 2.7–3.3 A (0.45 A only into a hard short).** HDMI asks the source to limit +5 V to 0.5 A. A faulty sink drags 5V_SYS, which also feeds 3V3_IO and 1V1_628. HDMITX_5V reaches the connector through 0.25 mm traces and 5V_SYS through about 160 mm of 0.6 mm; at 1–1.5 A on 5V_SYS the connector sees about 4.8 V, the HDMI minimum. | AP22804 datasheet (ILIMIT 2.7/3.0/3.3 A, ISHORT 0.45 A); pcbnew widths (HDMITX_5V 0.25 mm; 5V_SYS 0.6 mm). | Measure HDMITX_5V at J401 pin 18 under load. | 0.5 A-class switch or a 0.5 A polyfuse; wider 5V_SYS. |
| m5 | Minor | Power layout | **5V_SYS reaches U106's input (the 1.1 V buck) through 8 mm of 0.127 mm trace** ((79.5, 63.3)→(79.5, 59.0) and (64.5, 62.8)→U106.3). About 0.25 A average, 30 mΩ, so function is fine, but the high-frequency input loop then depends entirely on C119/C120 (3.4 and 2.3 mm from pin 3). SW_628 keeps its 0.127 mm neck; SW_IO still changes layer through three vias; LX_5V/LX_SOM are 0.3 mm × 2 mm necks for 3 A. | pcbnew section H/`board3.py`; README "Known compromises". | None. | 0.5 mm feed to U106 pin 3 and a 100 nF at the pin (move L104 1 mm); switch nodes as short F.Cu copper areas. |
| m6 | Minor | 3V3_IO distribution | **A 29 mm run of 0.127 mm 3V3_IO along y = 39.1 (x 70→99) and 0.1 mm segments feed the pull-ups, LEDs and the Q203 collector pull-up; the M.2 3.3 V pins 2/4/72/74 are fed through 0.6/0.3 mm vias into 0.5 mm B.Cu copper.** `irdrop.py`: 42 mV at J501 at 0.6 A, 0.1 mm segments at 0.3 A (4 °C). Acceptable; no 3V3_IO or 5V_SYS pour exists (In2 is a GND pour with signals). | `checks/irdrop.py` output; pcbnew widths. | Measure 3V3_IO at J501 under Wi-Fi TX. | 3V3_IO island on In2 or ≥0.8 mm trunks. |
| m7 | Minor | USB-C | **No ESD on CC1/CC2 and no TVS on VBUS_C**; USBLC6 covers D+/D− only (pin 5 correctly left floating at a 9 V contract), SMBJ20CA sits after D103. CFG1 of the CH224A is rated 3.8 V and CC pins go straight to the chip. | Netlist; CH224 manual §7.1. | None. | 5 V ESD array on CC1/CC2; 20–24 V TVS on VBUS_C. |
| m8 | Minor | ADC | **VIN_SENSE has no clamp:** 100k/10k gives 1.55 V at 17 V, 1.8 V (full scale) at 19.8 V and 2.9 V during an SMBJ20CA clamp event (32 V). | `gen/power.py`; SMBJ20CA Vc 32.4 V. | None. | BAT54 to SOM_1V8 at the ADC pin. |
| m9 | Minor | CEC option | **R216 (0 Ω, DNP) would tie the 3.3 V CEC bus to J68-151, the 5 V side of the module's UM3204H level shifter (10 kΩ to VCC5V_MIDU).** | CM3 schematic HDMI sheet (U7 UM3204H, HDMI_TX_CEC_PORT). | Leave R216 unfitted. | Route CEC_GPIO to a plain 3.3 V GPIO. |
| m10 | Minor | HDMI in HPD | **HPD to the camera is driven at 3.3 V through 22 Ω from the RK628D (ball K8).** HDMI 1.4 requires HPD high ≥ 2.4 V at the source, so it is in spec, and it copies DshanPi p.32, but some sources detect HPD with a comparator near 2 V with a 10 kΩ pull-down, leaving 1.3 V margin. | `gen/hdmi_in.py` R213; RK628D ball table (K8 GPIO1_B0/HDMIRX_HPD_M0); DshanPi p.32. | Test with the target cameras (Blackmagic, Sony). | Transistor pulling HPD to HDMIRX_5V through 1 kΩ, as many sinks do. |
| m11 | Minor | ESD arrays | **D403 pad 7 (HDMITX_5V) has no copper; pad 4 carries the rail.** Harmless (one diode per line), but the pad-pair convention now differs between D203 (all four pairs linked) and D403 (three), and the link traces (0.2 mm, 0.77 mm long) run between pad rows under the body of a part whose datasheet land pattern is 0.2 × 0.675 mm pads 0.875 mm apart, versus KiCad's 0.3 × 0.55 at 0.77 mm. Fits the 0.38 mm leads; less toe than recommended. | `board2.py` section A; RCLAMP0524P datasheet p.5 land pattern; KiCad USON-10 pads. | None. | Footprint drawn to the vendor land pattern with the four links built in. |
| m12 | Minor | HDMI ESD parts | **Tech Public RCLAMP0524P: 0.6–0.8 pF line-to-ground, Vbr 6.8–9.5 V, ±15 kV contact (not Semtech's 0.3 pF).** Fine for 1080p60 (1.5 Gb/s); marginal for HDMI 2.0 rates. Unidirectional, VRWM 5 V: correct for 5 V lines; two of the parts (D403 pad 4) sit on the 5 V rail itself. | RCLAMP0524P datasheet p.2. | None. | ≤0.3 pF part if 4K input is ever wanted. |
| m13 | Minor | HDMI in DDC/CEC pull-ups | **CEC pull-up (27 kΩ) comes from RK628D_3V3 through D204 and DDC pull-ups (47 kΩ) from the source's 5 V through D205 (MBR0530, ~0.3 V drop): correct, as DshanPi.** But RK628D_3V3 is off until software raises PWR_EN, so with the RK628D unpowered the CEC line has no pull-up and the RX_CEC/RX_SCL/RX_SDA pads see the camera's 5 V-domain DDC pull-ups through 22 Ω into an unpowered chip (back-powering through the RK628D's clamps at < 0.2 mA). The I2C2 bus to the CM3 also loses its pull-ups when RK628D_3V3 is off. | `gen/hdmi_in.py`; netlist. | Software: raise RK628D_PWR_EN early in boot and keep it on while a camera is attached. | 3V3_IO-referenced pull-ups for I2C2; DDC/CEC clamps that tolerate the unpowered state. |
| m14 | Minor | Mechanical (case) | **Case details that will bite at assembly** (from the case review, `case/case.py`): the USB-C opening is cut in the lid only and the base wall is solid to the board plane, so a plug overmould stops 3 mm short of J103; the HDMI pockets likewise stop at the board plane; the ¼"-20 insert holes (6.6 mm deep) run through their 5 mm bosses into the board; the M3 posts have a 0.3 mm wall around the counterbore; no M2.5 × 1.5 mm standoffs are listed for the module's 1.5 mm stack; the lid has no boss/thermal pad to the module (REV_A_SPEC §6 calls for one); README says M3 × 10, PRODUCTION M3 × 6 (10 is needed). | `case/case.py` lines 19–33, 49, 66, 69–70, 96, 101–105, 127–136; Radxa CM3 datasheet §2.7; PRODUCTION.md line 61; case/README.md line 81. | File/notch the printed base at the USB-C and HDMI openings; blind the ¼"-20 holes; add 1.5 mm M2.5 spacers to the module kit. | Re-cut the openings into the base wall, 5 mm floor under the inserts, thicker posts, lid boss with pad. |
| n1 | Note | Gerbers / fab files | Verified: every file in `fab/gerbers/` equals a fresh `kicad-cli` export of `relay.kicad_pcb` except the date lines; the zip holds the same 16 files; the four ESD links are in `relay-F_Cu.gtl` at X60.57/X60.07/X111.5/X112.0 (D02/D01 pairs); the six thermal vias are in `relay-PTH.drl` under T3 (0.300 mm); the job file states 0.0994/1.265/0.0994 mm dielectrics, ENIG, ImpedanceControlled true; `gen/fab.py` refuses any other stackup. | Re-export diff in `/private/tmp/claude-501/fable-review-2/regerb/`. | — | — |
| n2 | Note | CM3 connectors | The DF40 pads of J701–J703 match Radxa's IO board to 0.0000 mm on all 300 pins (`checks/b2bfit.py`), mirror rejected. Radxa's J68 has four extra GND pads (201–204) that this footprint lacks; the DF40C-100DS-0.4V(51) receptacle has no tabs needing pads on J69/J1 either, so they are presumed board-specific. | `checks/b2bfit.py` output. | — | Check what Radxa's pads 201–204 are. |
| n3 | Note | Module keep-out | The module outline (x 68.5–123.5, y 60–100, from the 47.95 × 33 mm hole pattern) has no top-side part inside it; the nearest are R701–R704/C701/C704–C707 at y 101.2–103.6 and R205 at y 57.4. Under the module on the back: C702, C703, C232. | pcbnew footprint positions. | — | — |
| n4 | Note | PCIe AC coupling | With C501/C502 at 0 Ω the TX path has the module's C54/C55 (100 nF) only: correct. The RX path has the module's C57/C58 plus the card's own capacitors in series (≈50 nF, below the 75 nF CEM minimum). That is Radxa's design and Radxa's IO board ships that way. | CM3 schematic p.9 (MULTI PHY P_S); CM3 datasheet (CTX 75–200 nF). | None. | — |
| n5 | Note | Via-in-pad | 101 vias lie inside SMD pads (J501 pins 39/41/45/47/52/53, U102's exposed pad, many 0402 GND pads), drills 0.15–0.3 mm, all tented in the board file. Acceptable only with the "epoxy filled & capped" option the Y5 cart carries; JLCPCB's fill process is specified for 0.15–0.5 mm drills (the 0.6/0.3 vias in C117, J501.2, Q201.2 etc. qualify). Confirm the option survives any re-quote. | `board2.py` section C; `orders/2026-10-25-jlcpcb-5-assembled-quote.md`. | Keep the via option selected. | Fan out beside the pads. |
| n6 | Note | JLCPCB rules | Min track/clearance 0.09/0.1 mm, inner tracks 0.09 mm (RK628D_3V3 on In1 and AVDD on In2), 0.15 mm drills, 0.3 mm vias, hole-to-hole 0.25 mm: all at JLCPCB's 4-layer limits but inside them. Copper to edge ≥ 0.3 mm (J101 pad 1 at 0.35 mm). DRC `missing_courtyard` is set to ignore; MOUNT_CM3 is the only footprint without one. | `relay.kicad_pro` rules; DRC. | — | — |
| n7 | Note | USB OTG / recovery | VBUSDET is tied to SOM_3V3 through 10 kΩ: the module routes the pin straight to the SoC (T38) with only 100 nF, so the pin sees 3.3 V, the top of the 2.7–3.3 V window. RECOVERY: 10 kΩ to SOM_1V8 + 1 nF, button to GND, per §3.11. USB_OTG0_ID left open (device mode). USB_5V_IN correctly unconnected (datasheet warns against powering it with +5V_INPUT). | CM3 schematic p.9; CM3 datasheet §3.2.1, §3.1.1 warning. | — | — |
| n8 | Note | Module pull-ups touched by the carrier | GPIO0_A4 (PLUGIN_DET) has the module's Q4 (TF_DET → 100 Ω) and an internal pull-up; GPIO0_A5 (LED_WIFI) is SDMMC0_PWREN; I2C2_M0 (J69 56/58) keeps its 2.2 kΩ 1.8 V pull-ups unused. WIFI_PWREN (GPIO0_A0) is the on-module Wi-Fi enable on W2 modules. All handled in software (see DT list). | CM3 schematic p.7. | — | — |
| n9 | Note | Debug UART | J601 is 1.8 V (GPIO0_D0/D1, PMUIO2 = VCCA1V8_PMU, 100 Ω series on the module). Value field says "1V8"; no silkscreen. | CM3 schematic p.7. | 1.8 V adapter. | "1V8" silk. |
| n10 | Note | Crystal / RK628D straps | Y201 X322524MOB4SI is a 12 pF CL part; 18 pF + 18 pF with ~3 pF stray gives 12 pF. I2C_ADDR low (0x50), TEST to GND (internal pull-down), RESETN has an internal pull-up (reset state "Up") with C202 100 nF 6.8 mm away (RC only), INT/SPIBOOT internal pull-down onto GPIO3_C3 (reset pull-down): normal boot. EFUSE_VDD_2V5 held at 0 V through 100 Ω: per datasheet, 2.5 V is only needed for programming. | RK628D datasheet tables 2-3/2-4 (lines 545–596); `gen/hdmi_in.py`. | — | — |
| n11 | Note | Regulators | SY8303: 0.6 × (1 + 110/15) = 5.00 V, Fsw 105/210k = 500 kHz, BS 10 nF (datasheet value), EN 100k/39k on at ≤ 5.35 V (VENH ≤ 1.5 V), UVLO ≤ 4.35 V, 2 × 4.7 µF/50 V in (≥ 4.7 µF required), 2 × 22 µF/25 V out (≥ 22 µF after bias: about 25 µF). TPS563201: 3.30/1.10 V, EN has an internal 400 kΩ to GND so 100k/100n from 5V_SYS settles at 4.0 V (8 ms) and 10k/100n from RK628D_3V3 at 3.2 V (1 ms): 3.3 V before 1.1 V as DshanPi; VIN ≥ 4.5 V met by 5V_SYS. CH224A: VHV pin 1 and VBUS pin 8 both on VBUS_C (manual: "VBUS must be shorted to VHV"), 1 µF, CFG1 6.8 kΩ = 9 V with CFG2/3 floating (allowed, internal pull-ups), PG open-drain to Q101 with 100 kΩ to VBUS_C; AO3401A VGS −9 V within ±12 V; D103 blocks back-feed. AP22804A: 1 OUT, 2 GND, 3 FLG, 4 EN (active high), 5 IN. | Datasheets as cited; netlist. | — | — |
| n12 | Note | Docs | REV_A_SPEC still says 90 × 65 mm, "all SMD on top", "L3 power", 47 µF polymer, HDMI C2902698, and "6.8uH 5A" (Bourns rates it 3.6 A rms / 5.7 A sat). | Files named; Bourns SRN6045TA table. | Update. | — |

## What was verified as correct, and how

**Pin map and I/O banks.** Every assigned CM3 pin in `gen/module.py` was listed with its Radxa name and RK3566
function from `gen/cm3_pinout.json` (V1.32: J69-37 UART9_TX_M1, J69-93 SARADC_VIN0, J1-14 SARADC_VIN3) and the bank
of each GPIO was taken from the CM3 V1.322 schematic read as images: p.7 PMUIO1 = GPIO0_A0–A7 (VCC3V3_PMU, "3.3V
Only"), PMUIO2 = GPIO0_B0–D2 (VCCA1V8_PMU), OSC = GPIO0_D3–D6 ("1.8V Only"); p.14 VCCIO1 = VCCIO_ACODEC
(GPIO1_A0–B?); p.13/12 VCCIO5 = VCC_3V3; p.11 VCCIO6 = GPIO_VREF (tied to +3V3 here); p.10 VCCIO7 = VCC_3V3. The
RK3568 datasheet §2.8 group labels agree. Result for today's moves: RK628D_INT GPIO3_C3 and RESET_N GPIO3_C2 (VCCIO5,
3.3 V), LED_STATUS GPIO4_B1 (VCCIO6), LED_WIFI GPIO0_A5 (PMUIO1), BT_DISABLE_N GPIO1_A4 (VCCIO1, see M3), PD_PG_N no
longer on the module (netlist: `/Power/PD_PG_N` = U102.10, Q101.1, R102 only). I2C2_M1 on GPIO4_B4/B5 (VCCIO6),
PLUGIN_DET GPIO0_A4, WIFI_DISABLE_N GPIO0_A0 (PMUIO1), PWR_EN GPIO0_C4 (1.8 V into an NPN base through 1 kΩ: fine),
CEC_GPIO GPIO4_D1 (VCCIO7), DVP/SDI pins on VCCIO6/7. `checks/iolevels.py` encodes the same map. No pin is used twice
(the generator asserts it). `checks/b2bfit.py`: 300/300 pins at 0.0000 mm against Radxa's IO board.

**RK628D.** All 144 balls in `gen/hdmi_in.py` against datasheet table 2-1/2-2 (the HDMIRX HPD/SCL/SDA/CEC on K8/L8/M8/K9
are the GPIO1_B0–B3 M0 functions, L10/M11 are VSS, as DshanPi p.31 wires them); supplies (1.1 V and 3.3 V only,
ferrite-split analog rails, EFUSE low), straps, crystal, CSI lane order TX0/1/2/3/4 = D0/D1/CLK/D2/D3 P-to-P into J68
117/123/129/130/136 (4-lane mode on CLK0). Decoupling: 22 capacitors within 6 mm on the back, 49 fanout vias, crystal
load caps 1.6–1.75 mm from Y201.

**Power tree.** As in n11; input OR-ing with three SS54 (40 V/5 A), SMBJ20CA (Vbr ≥ 24.5 V) on VIN, VIN_SENSE 1.55 V
at 17 V. `checks/irdrop.py`: VIN 23 mV at 2.8 A into U104 on 0.8–1.6 mm copper; 5V_SOM 8 mV at 3 A. Regulator loops:
VIN→Cin 2.05 mm (U103/U104), SW→L 2.7–3.4 mm, L→Cout 2.6–3.6 mm; U105 Cin 1.5/1.9 mm.

**Connectors and ESD.** HDMI J201/J401: pins 1–19 standard; TMDS pairs flow through D201/D202/D401/D402 with the
trace crossing both pads; D203/D403 pad pairs now linked by copper (Gerber-verified); shells to GND. Ethernet:
MDI0–3 → JK0654219 MX1–MX4 → RJ45 1/2, 3/6, 4/5, 7/8, centre taps 1 µF to GND; pad pitch 2.032 mm, holes 0.89/1.02/
3.2 mm. M.2 E-key pin map (GND 1/7/18/…/75, 3.3 V 2/4/72/74, USB 3/5, PET 35/37 → PCIE_RX, PER 41/43 ← PCIE_TX
through the 0 Ω links, REFCLK 47/49, PERST 52, CLKREQ 53, W_DISABLE2 54, PEWAKE 55, W_DISABLE1 56); TE 2199230-4
footprint (pads 0.3 × 1.55, pegs 1.1/1.8 mm). USB-C HRO TYPE-C-31-M-12: CC1/CC2 to the CH224A, D+/D− both rows through
USBLC6, mouth 0.5 mm inside the edge. DC jack footprint vs PJ-002AH drawing: pin positions match exactly (pin-1 slot
3.0 vs 3.5 mm recommended) but see B1 for orientation.

**Layout.** DRC `--schematic-parity --severity-all`: 0/0/0; ERC 0. GND zones on all four layers (In1 11216 mm² of
12000, 17 mm of In1 track all under U201). Pairs on F.Cu reference In1 with no other-net track within 0.4 mm under any
CSI/HDMI/MDI/USB/PCIe segment; plane "gaps" are via antipads only. CSI, HDMI IN/OUT: P = N to 0.00 mm, 71–81 %
coupled at 0.1 mm gap; MDI 98 % coupled, P/N within 0.7 mm; PCIe RX 94 %. HDMI OUT clock-to-data including the module:
worst 7.9 mm (< 480 mil). HDMI IN pairs 23.8–30.2 mm. DVP_D6 on In2 under J701 pads with no high-speed trace above it.

**Fab outputs.** BOM 59 lines, every line with an LCSC number that resolves to the intended MPN (60 numbers checked
today: no wrong part, no wrong package); BOM and CPL list the same 180 references; DNP (R202, R216, R501, J602) and
fiducials/test points/mounting holes in neither; 118 top / 62 bottom. CPL coordinates equal the Gerber coordinates
(page origin, Y up). FAB_NOTES states the stackup and the three pair geometries.

## What could not be verified

- **JLCPCB's zero orientation for the uncorrected CPL parts (M4):** only their preview shows it.
- **The RK3566 D-PHY receiver's skew tolerance and the RK628D's minimum CSI lane rate (M1):** Rockchip documents
  are not in the repo.
- **Whether the stock Radxa CM3 device tree already enables VCCIO_ACODEC at 3.3 V (M3):** not checkable offline.
- **Impedance with a 2-D solver:** `checks/zsolve.py` (92.6 Ω for 0.10/0.10 on 3313) was not re-run; the closed-form
  estimate agrees within 10 %.
- **RK628D 1.1 V current and power sequencing:** no Rockchip design guide; the scheme copies DshanPi.
- **The M.2 2230 standoff spacing (H501 at 28.0 mm from J501):** the TE 2199230 drawing is not in text form.
- **The DF40 pads 201–204 on Radxa's J68 (n2).**
- **Real heights of the module heatsink, Wi-Fi shield and switch actuators in the case (m14).**

## Software / device-tree requirements the hardware imposes

- `vccio_acodec` (RK817 LDO4) 3.3 V, boot-on, always-on; `pmu_io_domains` vccio1-supply = vccio_acodec (BT_DISABLE#,
  PERST#, CLKREQ#, WAKE#).
- Disable `sdmmc0`, or remove its `cd-gpios` (GPIO0_A4 = PLUGIN_DET) and `vmmc`/`pwren` (GPIO0_A5 = LED_WIFI).
- Keep GPIO0_D4 (TF_DET) low or unused; it pulls PLUGIN_DET low through the module's Q4.
- RK628D on `i2c2` with `i2c2m1_xfer`; reset GPIO3_C2 (active low), interrupt GPIO3_C3, power-enable GPIO0_C4 (raise
  early, keep on while a camera is attached, see m13), plug-detect GPIO0_A4 active low; CSI 4-lane on CLK0 at the
  lowest lane rate that carries the format (M1).
- PCIe: PERST GPIO1_B2, CLKREQ/WAKE as GPIO1_B0/B1 (M2 group); `max-link-speed = <1>` if Gen2 is unstable (m1).
- UART2_M0 console at 1.8 V; USB OTG0 peripheral mode (VBUSDET tied high); SARADC_VIN0 recovery, SARADC_VIN3 =
  VIN/11.
- LEDs: GPIO4_B1 (STATUS), GPIO0_A5 (WIFI), active high; WIFI_DISABLE GPIO0_A0, BT_DISABLE GPIO1_A4 active low.
- PD status is no longer readable by the SoC (PG drives Q101 only); use `VIN_SENSE` to tell 9 V from battery.

## Comparison with the earlier reports

**REVIEW_INDEPENDENT.md (Oct 25).**
- Confirmed, and the fixes are correct and complete: M1/M8 (INT and RESET_N now on GPIO3_C3/C2, VCCIO5), M2 (LEDs on
  GPIO4_B1/GPIO0_A5 with 150 Ω: 1–3 mA at 3.3 V), M3 (PD_PG_N off the module; `sync.py` renamed it to a sheet-local
  net), M5 (BT_DISABLE_N on GPIO1_A4, with the VCCIO1 caveat now in M3 here), M4 (PRODUCTION station 4 reworded),
  N1 (J601 value). Its bank derivation matches mine.
- Confirmed and still open: M6 (CSI skew, my M1, same numbers), M7 (AP22804, my m4), M9 (switch-node necks, my m5),
  M10 (fuse/JST, my m3), M11 (uncoupled pairs, my m1/m2), M12 (VCCIO1, my M3), M13 (TF_DET, DT list), N2–N7.
- Disputed: "DC jack: the footprint matches the PJ-002A layout" is true for the pads and wrong in effect, because the
  footprint is placed facing inward (my B1). "No top-side part sits under the module outline" is confirmed.

**REVIEW_FABLE.md (Oct 25).**
- B1 (ESD pass-through on NC pins): confirmed from the datasheet image (p.1: pins 6/7/9/10 NC); the fix is complete.
  All four pairs of D203 and three of D403 are linked in `relay-F_Cu.gtl`; D403 pad 7 is correctly left bare; the TMDS
  arrays carry their traces across both pads.
- M1 (double TX AC coupling): confirmed from the CM3 schematic p.9 (C54/C55); the 0 Ω fix is right. The RX path's
  double capacitors (C57/C58 plus the card's) remain Radxa's design (my n4).
- M2 (CSI skew): confirmed, still open (my M1). M3 (U104 thermal): confirmed; the six vias are in the drill file;
  still a Major (my M2). M4 (stackup): fixed; job file and board carry 3313 and `fab.py` enforces it (my n1).
- m1–m11, n1–n11: confirmed; m2 and m8 slightly re-measured here (m6, n5). Its n7 ("case openings centred on the
  connectors") is confirmed in x and y, but it did not check which way the DC jack faces (my B1) or the base-wall
  cuts (my m14).

**TEST_REPORT.md (Oct 24/25).**
- Confirmed: DRC/ERC/parity clean; regulator values, Fsw and EN thresholds; the VIN neck fix; CH224A configuration;
  USBLC6 pin 5; fiducials; "CM3 connectors: exact"; "Magjack: match"; the RClamp correction; the Oct 25 fix table.
- Disputed: "DC jack J101 … footprint and pins match" (orientation not checked, my B1); the thermal estimate
  "about 40–45 °C/W" after the vias is unmeasured and still leaves U104 near 100 °C at 3 A in the case (my M2); the
  "CSI lane-to-clock spread 7.35 mm" figure omits the module (its own later section accepts M6).
- Open from it: the magjack stock (now also the two Sunlord inductors and the RK628D count, my M5) and the 2.0 mm
  plug note.

**Net result of the day's script changes:** everything claimed fixed is fixed and present in the files that will be
manufactured. The one thing that stops the order is older than today's work and outside what any of the three reviews
looked at: the DC jack's direction.
