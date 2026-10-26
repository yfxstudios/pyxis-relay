# Rev A: independent final pre-fab review, second pass (Fable, 2026-10-25, commit 6535945, branch hardware/hdmi-relay-design)

## Scope and what was run

Everything in the project as of commit 6535945, against the datasheets in `../datasheets/` and raw files rather than
generator comments. Nothing in the project was modified except adding this file. Scripts and outputs are in
`/private/tmp/claude-501/fable-review-final-2/` (boarddump.py, coupling.py, farsegs.py, links.py/links2.py,
erc.json, drc.json, relay.net, gerb/, dt/, ds/ = pdftotext of every datasheet, case_copy/).

| Area | What I did |
|---|---|
| Schematic | Read `gen/module.py`, `power.py`, `hdmi_in.py`, `hdmi_out.py`, `board_io_sheets.py`, `ethernet.py`, `parts.py`; exported the netlist with `kicad-cli sch export netlist` and dumped every connector/polarised-part pin from it (not from the generators). Checked all 54 CM3 assignments against `cm3_pinout.json`, the datasheet appendix C, the V1.3→V1.32 change table (parsed the xlsx: J69-37/93, J1-14/26/34) and the CM3 V1.322 schematic bank pages (PMUIO1/2, OSC, VCCIO1/5/6/7 supplies, Q4/R170 on SDMMC0_DET_L, C54/C55, USB_OTG0_VBUSDET). All 144 RK628D balls against datasheet table 2-1 (parsed programmatically). DshanPi-A1 p.31/32 rendered and read (RK628D power, MIPI lane table, crystal note, HDMI-in connector page). CH224, SY8303, TPS563201, AP22804, AO3401A, RTL8211F, JK0654219NL, PJ-002A (drawing rendered), RCLAMP0524P/USBLC6 footprints. |
| Rules | `kicad-cli sch erc --severity-all`: 0. `kicad-cli pcb drc --schematic-parity --severity-all`: 0 violations / 0 unconnected / 0 parity. `relay.kicad_pro` has no ERC or DRC exclusions; the only custom rule ignores silk clearance on the overhanging J301. |
| PCB | pcbnew dump: every footprint position/rotation/courtyard, every hole, 1043 vias by size, per-net length per layer and via count for all 23 differential pairs and 45 single-ended nets, zones, via-in-pad hit test, a length-weighted coupling/gap histogram per pair, and the locations of the uncoupled segments. Re-ran the project's `checks/b2bfit.py`, `iolevels.py`, `returnpath.py`, `irdrop.py`, `tline.py` with KiCad's Python and `checks/zsolve.py` with the CadQuery Python (it has scipy 1.18, so the 2-D field solve actually ran this time). |
| Fab | Re-exported Gerbers, drills and the position file from `relay.kicad_pcb` and diffed them against `fab/` (only date headers differ). Compared `fab/relay-cpl.csv` row by row with the fresh position file (positions equal for all 176 parts; rotation deltas equal `JLC_ROT`). BOM lines resolved through `gen/lcsc-mpn.json`. Job file stackup read. `orders/2026-10-25-jlcpcb-5-assembled-quote.md` read. |
| Device tree | Sparse-cloned radxa/kernel `linux-5.10-gen-rkr4.1` (dts + dt-bindings), built `rk3566-radxa-cm3-io.dtb` with clang -E + dtc -@, compiled the overlay, applied it with `fdtoverlay` (applies cleanly), decompiled the merged tree and checked the rk628 node, hog, rfkill, LEDs, regulator statuses. Checked every carrier GPIO and pinmux group against what the base tree claims. |
| Case | Ran `case/case.py --check` with the CadQuery Python on a copy of `case/` (PASS); compared every opening/light-pipe/pinhole/hole coordinate with the board dump. |
| Docs | REV_A_SPEC.md, PRODUCTION.md, kicad/README.md, case/README.md, orders/. |
| Earlier reviews | Read only after the findings below were formed; every item in REVIEW_FINAL.md's status tables re-checked (last section). |

Coordinates in this report are **board coordinates in mm: origin at the board's top-left corner (KiCad page
(30, 30) mm), x to the right, y down; y = 0 is the front panel (HDMI), y = 100 the rear panel.**

## Verdict

**Ready to order, with two conditions and the accepted risks listed below. No blocker found.**

1. **Upload the current `fab/relay-gerbers.zip`; do not check out the order in the cart.** The cart holds
   `relay-gerbers_Y6` (uploaded 16:45), which predates the PCIe PET/PER swap fix (board saved 21:35, fab regenerated
   21:37, commit 21:58). `fab/` matches the board exactly (Gerber diff: date headers only), so the right files exist;
   they just have not been uploaded. The quote note already says so (lines 78–80), but it is the one thing that turns a
   working design into boards with no Wi-Fi.
2. **Repeat the placement-viewer rotation check on that upload.** BOM and CPL are unchanged from Y6, so the earlier
   check should still hold, but JLCPCB re-derives placement per upload and nothing offline can confirm the 20
   `JLC_ROT` corrections (U201 BGA −90°, U103–U106 180°, U102/U401/D20x/D40x −90°, Q10x/Q20x 180°, J201/J401 90°,
   J701–J703 re-centred).

Accepted risks that stay open (owner decisions, documented): U104 thermal at > 2 A sustained; PCIe TX/REFCLK and
both USB pairs routed loosely or uncoupled; 100 Ω class solving to 92.6 Ω; CSI residual skew 6.3 mm; the M.2
2230 standoff position unverified against a drawing.

**Counts: 0 Blocker, 2 Major, 18 Minor, 11 Note.**

## Findings

| ID | Sev. | Area | Finding | Evidence | Fix for rev A | Rev B |
|---|---|---|---|---|---|---|
| M1 | **Major** | Ordering / CPL | **The JLCPCB cart order (Y6) is stale: its Gerbers have the M.2 PCIe pairs swapped.** The files in `fab/` are correct and current (netlist: J501.35/37 = M2_PET_P/N ← C501/C502 ← PCIE_TX_P/N = J702 pads 22/24 (Radxa 122/124); J501.41/43 = PCIE_RX_P/N = J702 pads 16/18 (116/118)), but they have not been uploaded. The rotation table `gen/fab.py` JLC_ROT (20 refs) cannot be verified offline; the Oct 25 viewer check was on Y6. | `git log`: 6535945 at 21:58; `fab/relay-gerbers.zip` 21:37; `relay.kicad_pcb` 21:35; `orders/…quote.md` lines 78–95 ("In the cart (16:45): relay-gerbers_Y6", "Superseded by the B1 fix"); my Gerber/drill/pos diff against a fresh export: identical apart from `TF.CreationDate`. | Upload `fab/relay-gerbers.zip` + `relay-bom.csv` + `relay-cpl.csv` as a new order (same options: JLC04161H-3313, ENIG, 0.15 mm vias filled and capped, both sides), check every polarised part in the placement viewer (U201 ball A1 toward board (39.5, 16.5) corner side as in KiCad; U103–U106 pin 1; Q101/Q201 S/D; D101–D104 cathode; J201/J401 shells), delete Y6, then pay. | Key the rotation table by LCSC number with a screenshot per part. |
| M2 | **Major** | Power, thermal | **U104 (SY8303, 5V_SOM) exceeds a safe junction temperature if the module draws its rated 3 A.** TSOT23-8, PD 2 W at 25 °C on a JEDEC 51-3 board (≈ 62 °C/W), no exposed pad. At 12–17 V in and 5 V / 3 A out the loss is about 1.3–1.7 W: 80–105 °C rise. At the documented 1.5–2 A sustained it is 55–70 °C rise. Four GND vias within 1 mm of U104's body and two at U103 are present; the case has a roof vent above both. Accepted by the owner with a 1.5–2 A cap, a current log and a thermocouple test. | SY8303 datasheet p.2 (PD 2 W, θJA note); `checks/irdrop.py` VIN 2.8 A case; pcbnew: GND vias at (66.76, 77.75), (68.96, 77.85), (66.91, 79.1), (65.96, 78.05); REV_A_SPEC §3 "5V_SOM thermal limit"; PRODUCTION step 9. | Accepted. Measure U104 case temperature in the closed case under encode + Wi-Fi; log 5V_SOM current. | Exposed-pad 5 V buck (TPS56637 class) for U103 and U104, or one 3 A converter plus a load switch. |
| m1 | Minor | PCIe layout | **PCIe TX is coupled over only 43 % of its length; 31.9 mm of PCIE_TX_P runs with N more than 0.6 mm away** (B.Cu (39.1, 28.2)→(33.3, 34.0) gap 0.78 mm; F.Cu (25.6, 29.9)→(20.1, 24.4) gap 2.55 mm; B.Cu (28.2, 32.1)→(26.0, 29.9) 2.4 mm; (30.5, 32.1)→(28.2, 32.1) 1.59 mm), and the remaining coupled part sits at 0.21–0.26 mm gap, not 0.10. REFCLK is 67 % coupled (10.8 mm uncoupled). Uncoupled 0.14 mm microstrip is 52.6 Ω single-ended, so those stretches are ≈ 105 Ω differential against the 85 Ω target. TX_N has 6 vias, TX_P 4. **The four layer-change vias beside J702 have no GND return via within 4.1–5.0 mm** (PCIE_RX_N via (56.82, 25.18) 4.96 mm; RX_P (56.18, 25.82) 4.56 mm; TX_P (57.9, 25.5) 4.50 mm; TX_N (58.9, 25.8) 4.14 mm; REFCLK_P (56.35, 27.4) 3.08 mm). `checks/tline.py` (lossless, ideal line) estimates 2 % eye closure; a 32 mm / 105 Ω section is about one Gen2 UI long, so its reflections land in the next bit. Gen1 fallback exists. | coupling.py, farsegs.py; `checks/returnpath.py` return-via table; `checks/zsolve.py` single-ended 0.14 mm = 52.6 Ω. | Accepted for rev A. If any copper is touched before the upload, the cheapest gain is one GND via (0.45/0.25) within 1 mm of each of the five signal vias near J702 (there is room at x 55–60, y 24–28). Keep `max-link-speed = <1>` in reserve; read `lspci -vv` LnkSta and AER counters at bring-up. | Route TX/RX/REFCLK as coupled 0.14/0.10 pairs on one layer, ≤ 2 vias each with a return via beside every one. |
| m2 | Minor | USB layout | **USB_BT (CM3 J1 63/65 → M.2 3/5) is coupled over 11 % of 93.5 mm**: DP runs 57 mm on F.Cu (29.2, 45.5)→(86.2, 45.5) with DM 1.65 mm away and 20 mm (14.0, 31.6)→(28.2, 45.8) with DM 5.55 mm away; DM has 6 vias, DP none. **USB_OTG** runs 63 mm on B.Cu (59.6, 35.7)→(14.9, 80.4) at a constant 0.37 mm gap (≈ 105 Ω instead of 90). Lengths are matched (93.47/93.47, 73.53/73.63 mm). USB 2.0 HS tolerates this (`tline.py`: 1.5 % closure), but common-mode rejection and EMI are worse than a coupled pair. | coupling.py, farsegs.py. | None (test Bluetooth and the OTG gadget at bring-up). | Route both as 0.12/0.10 coupled pairs, symmetric vias. |
| m3 | Minor | Impedance | **The 100 Ω class (0.10/0.10 mm) solves to 92.6 Ω (−7 %) with the project's own 2-D field solver; USB 87.1 Ω (−3 %), PCIe 82.4 Ω (−3 %).** Single-ended 0.10 mm = 60.5 Ω. REVIEW_FINAL n1's closed-form 100–105 Ω is optimistic. With JLCPCB's ±10 % the 100 Ω pairs could land at 83–102 Ω: inside TMDS (100 ±15 %), D-PHY (80–125 Ω) and 1000BASE-T (100 ±15 %) limits, but at the low edge for HDMI. If JLCPCB's engineers are asked for 100 Ω on 0.10/0.10 they may widen the gap or stop the order with a question. | `checks/zsolve.py` run with scipy 1.18 (cqenv): output above; FAB_NOTES geometry. | In the order remark give the geometries and say "manufacture to the geometry; 100/90/85 Ω nominal, no width change needed", or accept their suggested width. | 0.09/0.15 mm or 0.10/0.18 mm for the 100 Ω class on 3313 (re-solve), or move to JLC's calculator widths. |
| m4 | Minor | CSI skew | **Data-to-clock mismatch counting the module's internal lengths is +6.5 mm (D3) and −6.2 mm (D2); D0 +3.7, D1 0.** Carrier (F/B, vias): CLK 51.30/51.48 (0), D0 29.38 (0), D1 51.46/51.64 (0), D2 40.87 = F 21.6 + B 19.2 (2 vias), D3 29.16 = F 22.5 + B 6.7 (2 vias). Module (CM3 datasheet §3.5.3, mil → mm): CLK0 35.5, D0 61.1, D1 35.3, D2 39.7, D3 64.1. 6.5 mm ≈ 42 ps = 0.05 UI at 1.2 Gb/s; the CM3's own "< 36 mil" rule is already broken 25 mm by the module itself. Intra-pair ≤ 0.19 mm. 97–99 % of each lane is coupled at 0.10 mm gap. | boarddump.py; `gen/csimatch.py` MODULE table; datasheet lines 1089–1096. | Accepted. Lane rate ≤ 1.2 Gb/s; watch `rkcif` CRC/ECC error counters. | Route D2 outside the bundle and match all five totals to < 1 mm. |
| m5 | Minor | Pair skew | **Intra-pair skew above the CM3's 12 mil rule:** MDI0 0.64, MDI1 0.64, MDI2 0.68, MDI3 0.68 mm (25–27 mil); PCIE_REFCLK 0.78 mm (31 mil, 5 ps); PCIE_RX 0.33 mm; M2_PET stubs 0.57 mm (TX+PET total 62.9/63.4). Electrically harmless at 125 MBd and 100 MHz; the PCIe data pair totals are within 0.5 mm. | boarddump.py. | None. | Tune. |
| m6 | Minor | M.2 mechanics | **The 2230 hold-down H501 at (16.0, 55.0) is 28.0 mm from J501's centre (24.2 mm behind the even-pin pad row at y 30.8) and is still unverified against a drawing.** TE's application spec 114-115006 (fetched) only gives the connector land pattern, which `TE_M.2_E_2x38-1MP_P0.5mm` matches (rows 7.55 mm apart, pegs Ø1.1/Ø1.8 at ±10 mm, 2.275 mm from the even row); it does not place the standoff. My reconstruction (card edge 1–3 mm inside the connector from the even row, 30 mm card, notch centre about 2 mm inside the far edge) puts the required standoff 1–2 mm further from the connector than 55.0, with ±1 mm uncertainty. Wrong by 2 mm, an M2 screw will not reach the notch; the card still works held by the socket. | pcbnew holes list (J501 pegs (6.0, 28.5) Ø1.1 and (26.0, 28.5) Ø1.8; H501 Ø2.2 PTH); TE 114-115006 Figure 2 (`/private/tmp/claude-501/fable-review-final-2/te/`). | Order as is; on the first board drop an RTL8822CE card in and measure. If short, a 2 mm-longer M2 standoff with a slotted bracket or a nylon cable tie through H501 holds it. | Confirm from the M.2 spec module drawing (Type 2230 notch position) and put H501 there; or a 2.2 × 4 mm slot. |
| m7 | Minor | CM3 connectors | **Radxa's IO board has four extra GND pads (201–204) on its J68 footprint (U33, decal `DF40C-200DS-D4-OK`) that `relay:Radxa_CM3_J68` does not have.** The 100 signal pads coincide to 0.0000 mm on all three connectors. The DF40C-100DS-0.4V(51) itself has no board-lock pads, so these are likely Radxa's own stiffening pads; unexplained. | `checks/b2bfit.py` ("IO-board GND pins that are not GND here: J68 201–204"); `.asc` line 75634. | None. | Ask Radxa, or add four GND pads at Radxa's coordinates if the receptacle used has metal fittings. |
| m8 | Minor | Reference planes | **`checks/returnpath.py` finds stretches without solid GND within 0.3 mm on the reference layer:** PCIE_TX_P 12.8 mm, USB_BT_DM 11.6, PCIE_RX_N 9.2, PCIE_TX_N 9.0, MDI3_P 9.1, MDI0_P 7.7, CSI_D2_P/N 6.5–6.7, CSI_D0_N 5.9 mm (the rest 0.4–4.8 mm). Spot checks are via anti-pad fields under J702 and the magjack hole field, not plane splits (all four zones are GND, filled, 8.8–11.2 k mm²). | returnpath.txt; boarddump zones. | None. | Keep via fields away from pair corridors; stitch. |
| m9 | Minor | Power layout | **Thin spots:** 5V_SYS is a 0.4/0.6 mm trunk 148 mm long (70–86 mV at 1 A to U105/U106/U401); 3V3_IO reaches J501 pins 2/4/72/74 through 0.1 mm stubs at 0.3 A (86 A/mm², 42 mV total at 0.6 A); 1V1_628 has 0.127 mm B.Cu segments at 0.45 A (101 A/mm²); LX_5V/LX_SOM are 0.3 mm × 2.1 mm necks at 3 A; SW_IO changes layer through 3 vias; SW_628 has a 0.127 mm neck; U106's nearest input capacitor is ~3 mm away. In2 is a GND pour with 30 signals on it (PCIE_WAKE_N 94 mm, RK628D_PWR_EN 83 mm, …), not a power layer. 5V_SOM itself is good: 8.4 mV at 3 A. | `checks/irdrop.py` (irdrop.txt); boarddump widths and In2 table. | Measure 3V3_IO at J501 under Wi-Fi TX and HDMITX_5V at J401. | Power islands on In2 or ≥ 0.8 mm trunks; switch nodes as short F.Cu polygons. |
| m10 | Minor | Input at low battery | **At 6 V in and full load (≈ 15 W) the input current is 2.5–3 A: F101 holds 3 A (less when warm), J102's JST PH is 2 A/contact, each SS54 drops ≈ 0.4 V (1.1 W in SMA).** At the typical 7 W it is 1.2 A and fine. EN divider 100k/39k turns the SY8303s on above 5.35 V (VENH ≤ 1.5 V) and they stay on down to UVLO (4.35 V max); software must shut down at 6.0 V as the spec says. | BOM C48985875 / C131337 / C22452; SY8303 datasheet EN/UVLO table. | Keep battery loads realistic; the fuse trips, it does not fail. | 4–5 A fuse, XT30 or JST VH, ideal-diode OR-ing. |
| m11 | Minor | HDMI out 5 V | **AP22804AW5-7 limits at 2.7–3.3 A (0.45 A into a dead short), not the ≤ 0.5 A HDMI expects of a source.** EN tied to IN (active high) is correct. A faulty sink loads 5V_SYS, which also feeds 3V3_IO and 1V1_628. | AP22804 datasheet ILIMIT/ISHORT table. | None. | 0.5 A load switch or a 0.5 A polyfuse. |
| m12 | Minor | ADC | **VIN_SENSE (100k/10k = VIN/11) has no clamp:** 1.55 V at 17 V, 1.8 V full scale at 19.8 V, 2.9 V on SARADC_VIN3 during an SMBJ20CA clamp (32.4 V). Source impedance 9 kΩ limits it to ~0.1 mA. | `gen/power.py`; SMBJ20CA Vc. | None. | BAT54 to SOM_1V8. |
| m13 | Minor | USB-C | **No ESD on CC1/CC2 (straight into the CH224A), no TVS on VBUS_C (the SMBJ20CA is after D103); USBLC6 covers D+/D− only** (pin 5 floating is correct at a 9 V contract). CH224A CFG1 is rated 3.8 V, CC/PG/VBUS 32 V. | Netlist; CH224 manual §8.1.1. | None. | 5 V ESD array on CC, 20–24 V TVS on VBUS_C. |
| m14 | Minor | RK628D off state | **While RK628D_3V3 is off: I2C2 (SCL/SDA) and CEC have no pull-up (R207/R208/R214 hang on RK628D_3V3); the CM3 can drive RESET_N (GPIO3_C2, push-pull 3.3 V) into the unpowered chip; a connected camera's 5 V reaches RX_SCL/RX_SDA through 47 kΩ + 22 Ω.** Sub-mA back-feeds; the sequencing is software's (the overlay's `reset-gpios` active-low and `enable-gpios` give the driver what it needs). The DshanPi reference has the same structure. | `gen/hdmi_in.py`; netlist; DshanPi p.31/32. | Raise RK628D_PWR_EN early in boot and keep it on while a camera is attached; keep RESET_N low until then. | I2C2 pull-ups from 3V3_IO; buffered DDC. |
| m15 | Minor | Fab options | **110 vias sit inside SMD pads (R102, C116, U104 pad 8, J501 pads 2/39/45/47/49/52/53, RK628D C3 and J9: a 0.3 mm via in a 0.275 mm pad, …).** Fine only with the epoxy-filled-and-capped option the quote carries ($18.18); without it expect wicking and tombstoned 0402s. 382 vias are 0.15/0.30 mm (0.075 mm ring), min track/clearance 0.09 mm, hole-to-hole 0.25 mm: inside JLCPCB's 4-layer limits with no margin. | boarddump via-in-pad hit test; `relay.kicad_pro` rules; quote lines 12–13, 30, 36. | Keep "via covering: epoxy filled & capped" and "0.15 mm min via" on the re-upload. | Fan out beside pads; 0.2 mm drills; 0.1 mm margins. |
| m16 | Minor | BOM for upload | **`fab/relay-bom.csv` carries J301 with LCSC C3179417 (Pulse magjack, 0 stock) and `relay-cpl.csv` places it.** PRODUCTION says it is hand-fitted; JLCPCB will stop or substitute. Also harmless cosmetics: J701–J703 grouped under "CM3 J69"/`Radxa_CM3_J69`, SW602 under "RESET", J401 under "HDMI IN". | `fab/relay-bom.csv` line "RJ45 1000BASE-T magjack"; CPL row J301. | Untick J301 in JLCPCB's BOM step (or delete the line from the uploaded copy). | A stocked gigabit magjack. |
| m17 | Minor | Module mechanics | **1.5 mm M2.5 spacers for the module are in no parts list.** The DF40C 1.5 mm stack needs standoffs of exactly that height under the four M2.5 holes (MOUNT_CM3 MH1–MH4 at (42.0, 66.5), (42.0, 33.5), (90.0, 33.5), (90.0, 66.5), 2.6 mm plated, 6 mm pads); screws without them bend the connectors. | CM3 datasheet §2.7; PRODUCTION station 3 ("four M2.5 screws"); `orders/2026-10-25-dev-parts.md`. | Add 4 × M2.5 × 1.5 mm spacers (or Radxa's) per unit. | Document in PRODUCTION. |
| m18 | Minor | Docs | **Text that would mislead a builder:** REV_A_SPEC §6 "about 90 × 65 mm" (board is 120 × 100), "L3 power" (In2 is GND + signals), "all SMD on the top side except…" (62 bottom-side parts; the quote is two-sided), §3 "47 µF aluminium polymer" (RVT35V47M6X8 is a plain electrolytic), §3/§7 "locking DC jack" (PJ-002AH is not locking), §4 HDMI "C2902698" (BOM is Molex C916313), §4 crystal "the reference marks this 'all application scenarios'" (DshanPi p.31 marks the *SoC clock* for all scenarios and the crystal for "without HDMI_TX and GVI_TX", which this board satisfies); kicad/README.md still opens with "schematic draft 1", "ERC passes with one warning: the M.2 socket footprint isn't made yet", "placeholder" lists; PRODUCTION "3 assembled prototypes, ordered Oct 24" against the order note (5, not yet ordered); README says M3 × 10 case screws, PRODUCTION M3 × 6; no board name/revision text on the silkscreen (board texts: none; 139 of 198 reference designators visible). | Files named; boarddump "board texts: []". | Fix before the pilot; add "HDMI relay rev A 2026-10" silk in rev B. | — |
| n1 | Note | Device tree | **The overlay compiles (dtc -@) and applies with fdtoverlay to a base built from radxa/kernel rkr4.1; every GPIO, bank and polarity matches `gen/module.py`.** The base already has `vccio_acodec` (RK817 LDO4) at 3.3 V always-on/boot-on and `vccio1-supply = <&vccio_acodec>` (rk3566-radxa-cm3.dtsi lines 125, 304–313), so that part of the overlay is belt-and-braces; the hardware fact remains that LDO4 is off until the kernel's regulator core runs (CM3 datasheet §3.1.2), so PERST#/CLKREQ#/WAKE#/BT_DISABLE# float for the first seconds (card pull-ups only). Pinmux collisions checked: base `i2s1_8ch` uses GPIO1_A3/A5/A7/B3 (not A4/B0/B1/B2); base `pcie20m2_pins` (B0/B2 fn4) is replaced by the overlay's pinctrl-0; `hdmitxm0_cec` claims GPIO4_D1, harmless with R216 unfitted; base nodes on GPIO3_C2 (vcc5v0_usb30), GPIO0_A5 (vcc_sd), GPIO0_D4 (tf_det), GPIO3_C6/C7 (ch482d), GPIO4_A4/B7 (LEDs), hym8563 at 0x51 are all disabled by the overlay (confirmed in the merged tree). `reset-gpios = <&gpio1 RK_PB2 GPIO_ACTIVE_HIGH>` matches the base's convention. The rk628 node's property names are the vendor driver's and were not checked against a driver source. | dt/merged.dts in the review directory. | Boot it. | — |
| n2 | Note | RK628D supplies | VCCIO1 (H5) and VCCIO2 (E8/F8) are both on RK628D_3V3; the DshanPi runs its VCCIO at 1.8 V from an SGM2028 (p.31 "VCCIO_1V8"). The datasheet allows 1.8 or 3.3 V on VCCIO2 (table: VCCIO2 1.62–1.98 or 3.135–3.465 V); the GPIO/VOP pins it feeds are unused here, and 3.3 V keeps I2C/INT at the CM3's 3.3 V banks. EFUSE_VDD_2V5 at 0 V through 100 Ω: "AVDD must be high during PGM mode" only. | RK628D datasheet lines 923–976; DshanPi p.31. | — | — |
| n3 | Note | CH224A | CH224A (C42459160) is pin-compatible with the CH224K symbol used: pin 1 = VHV straight on VBUS_C (32 V rated; a CH224K would need the series resistor), pin 8 VBUS "shorted to VHV", CFG1 6.8 kΩ = 9 V, PG open-drain rated 32 V into Q101's gate with 100 kΩ to VBUS_C, AO3401A VGS −9 V within ±12 V, body diode blocks VBUS_C → VBUS_SW, D103 blocks back-feed into the port. A 5 V-only source leaves Q101 off, as intended; flashing needs 12 V on the DC jack (PRODUCTION says so). | CH224 manual §4 pin tables, §7.1, §8.1.1; AO3401A datasheet. | — | — |
| n4 | Note | CM3 power | +5V_INPUT is six DF40 contacts at 0.3 A each: 1.8 A sustained, not 3 A. Radxa's design; REV_A_SPEC says so. USB_5V_IN (J1 94/96/98) must stay open when +5V_INPUT is used (datasheet §3.1.1): it is. VCC_BAT±/TS open: no battery. | CM3 datasheet lines 498–511; netlist. | — | — |
| n5 | Note | ERC strength | ERC = 0 is weak evidence: the generated symbols declare almost every pin `passive` (CM3, RK628D, regulators, ESD arrays) and the project's pin map is default, so power-vs-power and output-vs-output conflicts cannot be caught. The netlist-level checks in this review (and `iolevels.py`) stand in for it. | `gen/sch.py` box_symbol, `gen/module.py` `_symbol()`. | — | Give the custom symbols real pin types in rev B. |
| n6 | Note | Panel / edges | HDMI shells overhang the front edge by 1.07 mm (J201/J401 F.Fab to y −1.07; courtyard −1.6), the magjack will overhang the rear by 5.5 mm (its body (89..108.8, 71.6..105.7)); USB-C face flush at y 100; DC jack mouth at y ≈ 99.3. JLCPCB adds rails on the shorter edges unless told otherwise. | boarddump courtyards. | Ask for rails on the 120 mm edges in the order remark. | Line up the rear connectors. |
| n7 | Note | USB-C data | USB_OTG_DP_C/DM_C stubs (J103 → U101) are 2.60 / 6.95 mm, so the whole OTG pair is 76.1 / 80.6 mm (4.5 mm, ≈ 30 ps, inside USB 2.0's 100 ps). | boarddump. | — | — |
| n8 | Note | Case | `case.py --check` PASS (board STEP extents x 0..120, y −1.0..105.5, z 3.7..22.6; roof underside at 24.4). Openings vs board: HDMI c = 24/79 (J201/J401 at x 24/79), USB-C c = 16 (J103 x 16, notch to −2.4 mm), DC c = 42 (J101 pin 1 (42.0, 85.55), pin 2 (42.0, 91.55), pin 3 (46.7, 88.55); mouth at y ≈ 99.3 facing out), Ethernet c = 99 (J301 body centre 98.9), light pipes (97.72, 18.47)/(101.18, 18.47)/(115.70, 11.98) = D601 white/D602 blue/D603 red, pinholes (100.5, 14.24)/(109.49, 14.24) = SW601/SW602, M3 holes (4,4) (4,96) (116,36) (116,68) = H601/H603/H602/H604 (3.2 mm, 6.4 mm pads with 8 vias), tripod insert hole 5.0 mm deep under a boss ending 0.2 mm below the board (0.8 mm stop). Heights of the module + heatsink, Wi-Fi card, sockets are still stand-in blocks. | case_copy run; boarddump. | Fit-check the first board. | — |
| n9 | Note | Stock | Not re-checked (no part lookups made). Earlier: RK628D 27 pcs, magjack 0, SRN6045TA-6R8M low. | — | Order promptly. | Second-source the RK628D. |
| n10 | Note | PERST#/W_DISABLE at boot | R501/R502/R503/R505 are DNP (confirmed in BOM and CPL), so PERST#, CLKREQ#, WAKE# and BT_DISABLE# are defined only by the card's own pull-ups until the kernel powers VCCIO1 and configures pulls; R504 (WIFI_DISABLE#, PMUIO1) is fitted. Harmless: the PCIe driver asserts PERST# before training. | Netlist; `fab/relay-bom.csv`. | — | — |
| n11 | Note | Debug / recovery | J601 is 1.8 V (UART2_M0 in PMUIO2); the value says so, the silk does not. RECOVERY: SARADC_VIN0 (J69-93, V1.32) with 10 kΩ to SOM_1V8 + 1 nF on the carrier in parallel with the module's own pull-up (datasheet asks to keep it). VBUSDET held at 3.3 V through 10 kΩ (top of the 2.7–3.3 V window). | Netlist; CM3 datasheet lines 643–666, 1870–1904. | — | "1V8" on the silk. |

## What I verified as correct

**CM3 pin map (all 300 pins, from the netlist, not the generator).** Every assigned pin lands on the intended
function per appendix C with the V1.32 moves applied (J69-37 = 4G_DISABLE/GPIO4_C5/UART9_TX_M1, J69-93 =
SARADC_VIN0, J1-14 = SARADC_VIN3, J1-26 = NC, J1-34 = PCIE_PWREN_H unused). MDI0–3 on J69 12/10, 4/6, 11/9, 3/5;
CSI D0/D1/CLK0/D2/D3 on J68 117/115, 123/121, 129/127, 130/128, 136/134 (4-lane mode uses CLK0); PCIe TX/RX/REFCLK
122/124, 116/118, 110/112; CLKREQn/PERSTn/WAKEn all PCIE20_*_M2 (J68-102, J68-109, J1-38); USB_OTG0 105/103; USB2
HOST2 J1 63/65; HDMI TX pairs 170/172, 176/178, 182/184, 188/190; HPD 153; DDC 199/200; CEC GPIO4_D1 (151); I2C2_M1
35/36; I2C4_M0 38/44; UART2_M0 51/55; UART9_M1 J69-37/J1-36; CIF D0–D15/HREF/VSYNC/CLKIN; PMIC_RESET_KEY 100;
VBUSDET J1-97; 5V_SOM × 6 (77–87 odd); +3V3 × 2 + GPIO_VREF tied (78/84/86); +1V8 × 2 (88/90). GND: J701 21, J702 30,
J703 25 pins, all on GND; the remaining 125 pins unconnected and allowed open (PWRON_KEY auto-on, USB_5V_IN,
VCC_BAT, TS, USB3/HOST1/3, audio, eDP, DSI, SARADC 1/2). `b2bfit.py`: 300/300 pads at 0.0000 mm against Radxa's IO
board, mirror rejected. Module mounting holes 47.95 × 33.0 mm, 2.6 mm plated.

**I/O banks (from the V1.322 schematic, not the generator).** PMUIO1 = VCC3V3_PMU (GPIO0_A*), PMUIO2 = VCCA1V8_PMU
(GPIO0_B0–D2), OSC domain 1.8 V only (GPIO0_D3–D6), VCCIO1 = VCCIO_ACODEC (RK817 LDO4, off by default, datasheet
§3.1.2), VCCIO5 = VCC_3V3 (R43 0 Ω), VCCIO6 = GPIO_VREF (R24 0 Ω) = +3V3 here, VCCIO7 = VCC_3V3. Every 3.3 V
signal is on PMUIO1/VCCIO5/6/7: RESET_N GPIO3_C2, INT GPIO3_C3, I2C2 GPIO4_B4/B5, LED_STATUS GPIO4_B1, LED_WIFI
GPIO0_A5, PLUGIN_DET GPIO0_A4, WIFI_DISABLE GPIO0_A0, CEC GPIO4_D1, SDI UART GPIO4_C5/C6, DVP GPIO3_C6–GPIO4_C1, SDI
GPIO 3_A1/B4/C1. 1.8 V by design: PWR_EN GPIO0_C4 into an NPN base, the debug UART. `iolevels.py`: 0 flagged.
Module-side circuits on reused pins read from the schematic: Q4/R170 100 Ω/R171 1 kΩ (TF_DET → SDMMC0_DET_L: the hog
covers it), C54/C55 100 nF on PCIE20_TXP/N (so C501/C502 = 0 Ω is right; the RX path has the module's caps in series
with the card's, Radxa's own arrangement), HDMI HPD 100 kΩ pull-down + 1 kΩ series and DDC/CEC level shifters on the
module, VBUSDET straight to the SoC.

**RK628D.** All 144 balls match datasheet table 2-1 (the only name differences are the generator's shorter aliases for
the TX lanes, DVDD_2 and H7). MIPI lane order TX0/1/2/3/4 = D0/D1/CLK/D2/D3 exactly as the DshanPi p.31 "LVDS/MIPI/GVI
signal relationship" table (G2/F2/E2/D2/C2 → CSI0 D0P/D1P/CLKP/D2P/D3P), P to P into J68. Straps: I2C_ADDR 10 kΩ to
GND (+ internal pull-down) → 0x50 = the DT; TEST to GND; RESETN internal pull-up + 100 nF; INT on a CM3 pin with
reset pull-down (SPIBOOT strap low). References: MIPI_REXT 4.02 kΩ 1 % (DshanPi R233 4.02K), RX/TX EXTR 2 kΩ 1 %.
EFUSE_VDD_2V5 to GND through 100 Ω + 100 nF as DshanPi. Crystal X322524MOB4SI 12 pF with 2 × 18 pF (≈ 12 pF with
3 pF stray); DshanPi permits an independent crystal "without HDMI_TX and GVI_TX", which holds here. Power gate
AO3401A/MMBT3904 with 10k/1k/1k/100k identical to DshanPi (Q4/Q5/R239–R242); 1V1 enable from RK628D_3V3 through
10 kΩ/100 nF (DshanPi R245/C423); ferrite-split AVDD rails (FB15/FB16 equivalents); decoupling 2 × 100 nF + 10 µF on
DVDD, 9 × 100 nF + 2 × 1 µF + 10 µF on AVDD_1V1, 6 × 100 nF + 1 µF + 10 µF on AVDD_3V3, 3 × 100 nF + 1 µF + 10 µF on
VCCIO, on the back under the chip; BGA footprint 12 × 12 at 0.65 mm, 0.275 mm NSMD pads, 74 × 0.15/0.3 mm dogbone
vias (0.17 mm from pad edges, 0.14 mm beside 0.1 mm traces).

**HDMI IN (against DshanPi p.32, rendered).** Connector pins 1–19 standard into the Molex 208658-1001 footprint
(BOM C916313 = 2086581001); D2/D1 through D201, D0/CLK through D202, HPD/CEC/SCL/SDA through D203; every
pass-through pad pair has board copper (segment through both pads or an explicit link: D201/D202/D401/D402 all four
pairs straight through, D203 and D403 linked; D403 5 V enters pad 4 from pin 18). HPD from ball K8 through 22 Ω
(DshanPi R252); CEC 27 kΩ from RK628D_3V3 through MBR0530 + 22 Ω series (D14/R255/R257); DDC 47 kΩ to the source's
5 V through MBR0530 + 22 Ω series (D13/R253/R256/R254/R258); plug detect 2 kΩ/10 kΩ MMBT3904 into GPIO0_A4 with 10 kΩ
to 3V3_IO (R250/R251/Q6/R249); 100 nF on HDMIRX_5V (C430). **HDMI OUT:** HPD straight to J68-153, DDC 2.2 kΩ to
HDMITX_5V, 5 V from U401 (AP22804AW5-7, EN = IN), 1 µF each side, three RCLAMP0524P. TMDS pairs 22.65–23.02 mm, P/N
0.00 mm, all F.Cu, clock-to-data spread 0.4 mm.

**Power tree (datasheets).** SY8303: VOUT = 0.6 × (1 + 110/15) = 5.00 V; Fsw = 105/200 = 525 kHz (RFS 200 kΩ =
0.5 MHz in the table); BS 10 nF; EN 100k/39k = 0.28 VIN (on ≤ 5.35 V, abs max 40 V); UVLO ≤ 4.35 V; 2 × 4.7 µF/50 V
1206 in (≥ 4.7 µF required) + 47 µF/35 V bulk; 2 × 22 µF/25 V out; 6.8 µH (≈ 1 A pk-pk ripple at 17 V, peak 3.5 A vs
SRN6045TA-6R8M 3.6 A); soft start 1 ms. TPS563201: VFB 0.768 V → 0.768 × (1 + 33/10) = 3.30 V, 0.768 × (1 + 10/23.2)
= 1.10 V; EN has an internal 225–900 kΩ pull-down, so 100k/100n from 5V_SYS settles at ≥ 3.4 V (τ ≈ 8 ms) and
10k/100n from RK628D_3V3 at 3.2 V (τ ≈ 1 ms); EN abs max 17 V; VIN 4.5–17 V met; 0.1 µF VBST; 2.2 µH / 1.5 µH
(SWPA6045S2R2NT 4.6 A / S1R5NT 4.95 A); 10 µF + 100 nF in, 2 × 22 µF out; min on/off times satisfied (22 % and 66 %
duty at 580 kHz). Inputs: SS54 × 3 OR-ing (40 V/5 A), reversed DC blocked, SMBJ20CA on VIN (standoff 20 V ≥ 17 V,
clamp 32 V < 40 V parts), 3 A/30 V PTC, VIN_SENSE = VIN/11. Every MLCC rating above its rail. C102 polarity: pin 1 (+)
on VIN. `irdrop.py`: 5V_SOM 8 mV at 3 A, VIN 23 mV at 2.8 A.

**Ethernet.** MDI0–3 → J301 MX1–MX4 (pads 11/10, 4/5, 3/2, 8/9) → RJ45 1/2, 3/6, 4/5, 7/8; centre taps 12/6/1/7 through
1 µF to GND, which is what the CM3 datasheet §3.4 requires for the voltage-mode RTL8211F ("center tap of the transformer
should be connected to ground through a 1uF capacitor"); JK0654219NL is a 10/100/1000 part (Pulse J411.G); LEDs open.
Pairs 53–70 mm, 98–99 % coupled at 0.10 mm gap, all F.Cu.

**M.2 E-key (netlist).** GND 1/7/18/33/39/45/51/57/63/69/75; 3.3 V 2/4/72/74 (2 × 22 µF + 2 × 100 nF); USB D+ 3 →
HOST2_DP, D− 5 → HOST2_DM; PETp0/n0 35/37 ← M2_PET_P/N ← C501/C502 (0 Ω, C17168) ← PCIE_TX_P/N (host TX, correct
after the swap); PERp0/n0 41/43 → PCIE_RX_P/N; REFCLK 47/49; PERST# 52; CLKREQ# 53; W_DISABLE2# 54 = BT_DISABLE_N;
PEWAKE# 55; W_DISABLE1# 56 = WIFI_DISABLE_N; key gap 24–31 absent; TE 2199230-4 land pattern matches TE 114-115006
Figure 2 (rows 7.55 mm apart, pegs Ø1.1/Ø1.8 20 mm apart). USB-C: HRO TYPE-C-31-M-12 with its own footprint, CC1/CC2 to
the CH224A only, D+/D− both rows through USBLC6 (1→6, 3→4), SBU open, shell GND. DC jack: `BarrelJack_Horizontal`
pads (0,0)/(−6,0)/(−3,4.7), slots 1 × 3 mm, match the PJ-002A drawing (1 = centre pin, 2 = sleeve, 3 = switch); placed
at 90° so the mouth faces the rear edge (0.75 mm inside it). Buttons: RESET to PMIC_RESET_KEY, RECOVERY to
SARADC_VIN0. LEDs: anode to the 150 Ω/2.2 kΩ resistor, cathode to GND (KiCad LED pin 1 = K). Q101/Q201 AO3401A G/S/D
= 1/2/3; Q202/Q203 MMBT3904 E/B/C = 1/2/3; D204/D205 MBR0530 anodes on RK628D_3V3/HDMIRX_5V. Fiducials 3 + 3.

**Layout.** DRC with parity 0/0/0, ERC 0, no exclusions. Board 120 × 100 mm (Edge.Cuts bbox 0..120 × 0..100), four GND
zones filled (F 8848, B 9760, In1 11212, In2 10888 mm²), 1043 vias (614 × 0.25/0.45, 382 × 0.15/0.3, 47 × 0.3/0.6),
3423 tracks, min width 0.09 mm (inner). CSI/HDMI-IN/HDMI-OUT on F.Cu over In1 (only CSI D2/D3 hop to B.Cu, with GND
vias within 0.7–1.0 mm of each signal via). No top-side part under the module outline (38.4..93.6 × 29.9..70.1). HDMI
IN pairs 23.8–30.2 mm, P/N 0.00 mm, 82–86 % coupled (the rest is the fan-in at the ESD arrays and connector). Six
GND vias at U103/U104 present. Courtyards: 0 overlaps.

**Fab files.** Gerbers/drills/position identical to a fresh export from `relay.kicad_pcb`; job file 0.0994 / 1.265 /
0.0994 mm, 3313, Er 4.1, ENIG, ImpedanceControlled, and `gen/fab.py` refuses anything else. BOM 59 lines, every line
with an LCSC number resolving to the intended MPN/package in `lcsc-mpn.json`; the 7 DNP parts (R202, R216, R501–R503,
R505, J602) in neither BOM nor CPL; CPL 176 rows = BOM references; positions equal the board for every part, Y page-up
as the Gerbers; rotations = KiCad + JLC_ROT; 62 bottom-side parts, all two-terminal passives (rotation-insensitive).
FAB_NOTES and the quote carry the stackup, 0.15 mm vias, fill-and-cap, two-sided assembly, X-ray.

**Device tree and case:** see n1 and n8.

## Earlier reviews: every claimed status re-checked

REVIEW_FINAL.md (the latest) carries a status table for all five older reports; I re-checked that table against the
files rather than repeating it. Where I agree, I say so once; disagreements are called out.

**REVIEW_FINAL.md "Status after fixes"**

| Item | Claimed | Found |
|---|---|---|
| B1 PCIe PET/PER swapped | fixed | **Confirmed fixed** in schematic (netlist J501 35/37 = M2_PET from PCIE_TX via C501/C502; 41/43 = PCIE_RX), in copper (M2_PET stubs 3.09/3.66 mm on F.Cu, no vias) and in `fab/` (fresh export identical). **Not yet uploaded** (M1 here). |
| M1 DT does not disable sdmmc0 etc. | fixed | **Confirmed**: overlay compiles and applies against the real base; sdmmc0, vcc_sd, vcc5v0_usb30, tf_det, vcc_ch482d1/2, pi/pwr LEDs, hym8563 disabled in the merged tree; u2phy0_host on vcc5v0_sys; hog on GPIO0_D4 present. Base already had vccio_acodec at 3.3 V always-on (n1). |
| M2 case USB-C notch / tripod insert depth | fixed | **Confirmed** in `case.py` (USB-C z = −2.4 cut in base and lid; TRIPOD_INSERT depth 5.0, boss to UNDER − 0.2 = 3.8 → 0.8 mm stop) and by running `--check` (PASS, including the overmould and stop probes). |
| M3 U104 thermal | accepted | Still accepted (M2 here); vias present. |
| M4 CPL rotations, new upload needed | open | **Still open** (M1 here): Y6 in the cart is stale; CPL unchanged since the viewer check, but the check must be repeated on the new upload. |
| m1 CSI 6.3 mm | accepted | Confirmed: +6.5/−6.2 mm by my numbers (m4). |
| m2 PCIe/USB uncoupled, 25 vias without return | accepted | Confirmed and quantified (m1, m2): TX 43 % coupled, 31.9 mm far; USB_BT 11 %, USB_OTG 7 % (0.37 mm gap). |
| m3 MDI / RX intra-pair skew | accepted | Confirmed (m5). |
| m4 AP22804 | accepted | Confirmed (m11). |
| m5 fuse / JST / SS54 at 6 V | accepted | Confirmed (m10). |
| m6 VIN_SENSE clamp | accepted | Confirmed (m12). |
| m7 CC ESD / VBUS TVS | accepted | Confirmed (m13). |
| m8 R216 CEC option | accepted | Confirmed DNP (not in BOM/CPL). |
| m9 switch nodes / 1V1 segments / U106 cap | accepted | Confirmed (m9). |
| m10 via-in-pad 112 | accepted via option | Confirmed, 110 by my hit test; quote has the option (m15). |
| m11 5V_SYS / 3V3_IO / HDMITX_5V distribution | accepted | Confirmed (m9). |
| m12 RK628D off-state back-feeds | software | Confirmed (m14). |
| m13 M2.5 spacers; H501 unverified; heatsink size | open | **Still open** (m17, m6). H501 now bounded by the TE land pattern (connector side) but the module notch position is still not from a drawing. |
| m14 docs | open | **Still open**, plus the crystal-note misquote and the stale README opening (m18). |
| n1 impedance 100–105 Ω closed form | note | **Disagree**: the project's field solver (now run) gives 92.6 Ω for 0.10/0.10 (m3). |
| n2 DF40 1.8 A; n3 JLC limits; n4 rails; n5 BGA pads; n6 PCIe caps; n7 OTG; n8 stock; n9 J68 pads 201–204; n10 CH224A PG | notes | All confirmed (n4, m15, n6, m15, n3, n11, n9, m7, n3). |

**Older reports (REVIEW_INDEPENDENT, REVIEW_FABLE, REVIEW_FABLE_2, REVIEW_FABLE_3) through REVIEW_FINAL's table**

| Group | Found |
|---|---|
| 1.8 V-pin fixes (INDEPENDENT M1/M2/M3/M5/M8; FABLE_2 M3 pull-ups) | **Confirmed fixed** in the netlist: INT GPIO3_C3, LEDs GPIO4_B1/GPIO0_A5 with 150 Ω, PD_PG_N reaches only Q101's gate and R102, BT_DISABLE GPIO1_A4, RESET_N GPIO3_C2; R501/R502/R503/R505 DNP, R504 fitted. |
| ESD pass-through links (FABLE B1, m10; FABLE_2 m11) | **Confirmed**: every pad pair on all six arrays is joined by board copper (links.py/links2.py), so no line depends on the clone's NC pins; D403 pad 7 carries no copper (pad 4 does), as FABLE_2 m11 noted. |
| PCIe double AC caps (FABLE M1) | Confirmed: C501/C502 are 0 Ω (C17168) on the host TX path; module C54/C55 are the only series caps. |
| CSI matching (FABLE M2, FABLE_2 M1, INDEPENDENT M6) | Confirmed at 6.3–6.5 mm residual. |
| Stackup in fab files (FABLE M4, m9) | Confirmed (job file, board setup, `fab.py` guard, FAB_NOTES, quote). |
| DC jack direction (FABLE_2 B1) | Confirmed fixed: J101 at 90°, pin 2 (sleeve) at y 91.55 toward the rear, mouth at y ≈ 99.3 facing out (PJ-002A layout: the long housing lies on the pin-2 side). |
| Case roof labels (FABLE_3 m11) | Confirmed fixed (LIGHTPIPES order STATUS/WIFI/PWR = D601/D602/D603). |
| RFS 200 kΩ / inductor value (FABLE_3 m12) | Confirmed (R105/R108 = 200k C25764; L101/L102 "6.8uH 3.6A"). |
| Inductor substitutions (FABLE_2 M5) | Confirmed (C36500, C96956 in BOM). |
| Thermal vias at U103/U104 (FABLE M3) | Confirmed present (2 + 4 within 1 mm of the bodies). |
| USB-only flashing (INDEPENDENT M4) | Confirmed accepted in PRODUCTION station 4 (12 V + USB-C). |
| TF_DET drives PLUGIN_DET (INDEPENDENT M13) | Confirmed handled by the DT hog; module circuit confirmed from the schematic (Q4, R170 100 Ω, R171 1 kΩ). |
| "PET 35/37 to the SoC's RX" verifications in the four older reports | Disputed by REVIEW_FINAL, correctly; now fixed. |
| Open items carried: stock (n8), J68 pads (m7), spacers (m17), docs (m18), UART silk (n11) | Still open. |

## Software and device-tree requirements the hardware imposes (unchanged)

vccio_acodec 3.3 V boot-on (base already does it) and SoC pull-ups on GPIO1_B0/B1; PERST# GPIO1_B2; BT enable
GPIO1_A4 high; Wi-Fi enable GPIO0_A0 high; GPIO0_D4 held low; sdmmc0 and the IO board's regulators/LEDs/RTC off
(overlay does all of this); RK628D on i2c2m1 at 0x50 with reset GPIO3_C2, interrupt GPIO3_C3, power GPIO0_C4 raised
early and kept on while a camera is attached, plug detect GPIO0_A4; CSI 4-lane on CLK0 at ≤ 1.2 Gb/s; pcie2x1 with
`max-link-speed = <1>` in reserve; UART2_M0 console at 1.8 V; USB OTG0 peripheral; SARADC_VIN0 recovery; SARADC_VIN3
= VIN/11 (full scale 19.8 V); shut down below 6.0 V on battery; flash with 12 V on the DC jack plus USB-C for data.
