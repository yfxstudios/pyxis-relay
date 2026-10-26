# Rev A: independent final pre-fab review, third pass (Fable, 2026-10-26, commit d32a7c2, branch hardware/hdmi-relay-design)

## Scope and what was run

Everything in the project at HEAD d32a7c2, checked against the datasheets in `../datasheets/` and the raw files
(netlist, board, Gerbers, CPL), not the generator comments. Findings were formed before any earlier review was read;
every item of `REVIEW_FINAL_2.md` (and, through its tables, the older reports) was then re-checked. Nothing in the
project was modified except adding this file. Scripts and outputs: `/private/tmp/claude-501/fable-review-3/`
(netparse.py → comps.txt/nets.txt, pcbscan.py, pairgap.py, cplcheck.py, pin1geo.py, fab_bbox.py, erc.json, drc.json,
gerb/ (fresh export), ds/ (pdftotext of every datasheet), img/ (rendered CM3 schematic pages), bsp/ (Radxa BSP dts +
dt-bindings + drivers/mfd/rk628.c, downloaded as data), case/ (copy of case.py run with `--check`)).

| Area | What I did |
|---|---|
| Schematic | `kicad-cli sch export netlist`, parsed to a per-part pin table; every CM3 pin (300) against `gen/cm3_pinout.json`, datasheet appendix C, the V1.3→V1.32 change sheet (xlsx parsed) and the CM3 V1.322 schematic (bank pages rendered as images, not just text); all 144 RK628D balls against datasheet table 2-1/2-2; every regulator, the PD sink, load switch, ESD arrays, FETs, connectors against their datasheets; DshanPi p.31/32 reference values. |
| Rules | `kicad-cli sch erc --severity-all`: 0. `kicad-cli pcb drc --schematic-parity --severity-all`: 0 / 0 unconnected / 0 parity (KiCad 10.0.7). `relay.kicad_pro`: no exclusions; one custom rule (J301 silk overhang). |
| PCB | pcbnew scan: zones, per-net lengths/widths/layers/vias for every high-speed net, P/N skew, a length-weighted P-to-N gap histogram per pair, polarised-part pin-1 geometry, courtyard overlaps, holes, via-in-pad; project checks `b2bfit.py`, `iolevels.py`, `returnpath.py`, `irdrop.py`, `gen/csimatch.py report` (KiCad Python) and `zsolve.py` (cqenv Python, scipy). ESD pass-through pad pairs traced in copper. |
| Fab | Fresh Gerber + drill export diffed against `fab/gerbers/` and `relay-gerbers.zip` (only date headers differ; zip = directory). Job-file stackup read. CPL compared row by row with the board (positions, sides, KiCad rotation + `JLC_ROT`, `JLC_OFFSET`, re-centred CM3 receptacles). BOM LCSC numbers resolved through `gen/lcsc-mpn.json`. |
| Device tree | Downloaded `rk3566-radxa-cm3-io.dts` and its whole include chain (rkr4.1), built the base with clang -E + dtc -@, compiled the overlay, applied it with `fdtoverlay` (clean), checked every carrier GPIO/pinmux against the base and the rk628 MFD driver's property names. |
| Case | `case.py --check` on a copy (PASS; STEP is newer than the last board save). Every opening/light-pipe/pinhole/hole coordinate against the board. |
| Docs | REV_A_SPEC.md, PRODUCTION.md, kicad/README.md, case/README.md, orders/. |

**Coordinates below are board mm: origin at the board's top-left corner (KiCad page (30, 30)), x right, y down;
y = 0 is the HDMI front edge, y = 100 the rear edge.**

## Verdict

**No blocker in the design. Paying is safe only after three things are confirmed on the order itself, and one
document error must be fixed before anyone connects a serial adapter:**

1. **The cart line must be the upload built from HEAD's `kicad/fab/`.** `orders/2026-10-25-jlcpcb-5-assembled-quote.md`
   still says the cart holds `relay-gerbers_Y6` (uploaded 16:45) and that it is superseded; two commits (6535945 PCIe
   PET/PER swap, d32a7c2 J101 CPL offset) changed the Gerbers and CPL after Y6. `fab/` at HEAD is correct and
   matches the board exactly; a Y6 order would have no Wi-Fi (M1).
2. **The 20 `JLC_ROT` corrections and the J101 `JLC_OFFSET` cannot be verified offline.** They are internally
   consistent with the board, but whether JLCPCB's models line up with the pads is only visible in their placement
   viewer. The owner says this was done on Y6; repeat it on the final upload for every polarised part (M2).
3. **Keep the quote's options:** JLC04161H-3313, ENIG, 0.15 mm vias epoxy-filled and capped (110 vias sit in SMD
   pads), two-sided assembly, X-ray (m12).

And: **the debug UART is 3.3 V, not 1.8 V** (M3). On the V1.322 module PMUIO2 is fed from GPIO_VREF, which this
carrier ties to +3V3. REV_A_SPEC, PRODUCTION, the J601 value "DEBUG UART 1V8", README and the overlay comment all
say 1.8 V and tell the builder to use a 1.8 V adapter; with one, console input will not be recognised. No board
change; fix the text and value (regenerate) before bring-up.

Accepted risks that stay open (owner decisions, documented): U104 thermal above 2 A sustained; PCIe TX routed
entirely uncoupled with REFCLK only partly coupled and no return vias at the module end; USB_BT uncoupled; the
100 Ω class solving to 92.6 Ω; CSI data-to-clock residual 6.3 mm; M.2 2230 standoff position unverified.

**Counts: 0 Blocker, 5 Major, 17 Minor, 11 Note.**

## Findings

| ID | Sev. | Area | Finding | Evidence | Fix for rev A | Rev B |
|---|---|---|---|---|---|---|
| M1 | Major | Ordering | **The project's own order notes say the cart holds a stale upload (Y6, PCIe pairs swapped at the M.2).** HEAD's `fab/` is right: J501 35/37 (PETp0/n0) = M2_PET_P/N ← C501/C502 (0 Ω) ← PCIE_TX_P/N (J702 pads 22/24 = Radxa 122/124); J501 41/43 = PCIE_RX_P/N (pads 16/18). Fresh Gerber/drill export is identical to `fab/gerbers/` and to the zip apart from `TF.CreationDate`; the CPL carries d32a7c2's J101 offset. | `orders/…quote.md` lines 76–95; `git log` (6535945 21:58, d32a7c2 23:07 vs Y6 16:45); my diff of gerb/ vs fab/gerbers/. | Before paying, open the cart line and check its upload time/file is after 23:07 Oct 25 (or re-upload `fab/relay-gerbers.zip` + `relay-bom.csv` + `relay-cpl.csv` as a new line, same options, delete Y6). Update the order note. | Put the git hash in the zip name. |
| M2 | Major | CPL | **CPL rotations/offsets are unverifiable offline.** `relay-cpl.csv` equals the board for all 175 rows (positions to 0.001 mm, sides, rotation = KiCad + `JLC_ROT`); J701–J703 re-centred on their pad arrays (DF40C receptacles are 180°-symmetric bodies, so their 0/0/90° rotations only need the long side right, which they are). But the correctness of the 20 `JLC_ROT` entries (U201 −90, U102/U101/U401 −90, U103–U106 180, Q101–Q203 180, six RClamps −90, J201/J401 90, J101 180) and of `JLC_OFFSET["J101"] = (2.3, 2.75)` (empirical, from the viewer; the target (44.3, 88.3) is the pad-array centre, not the F.Fab body centre (42.0, 92.0)) rests entirely on the owner's viewer check of Oct 25, done on Y6. Note the same KiCad package gets different corrections (U101 SOT-23-6 −90 vs U105/U106 SOT-23-6 180): JLCPCB's models are per LCSC part, so each must be seen. A 180° error on U102, U103–U106 or U201 destroys the board at first power; on C102 (not corrected) it vents. | `gen/fab.py` JLC_ROT/JLC_OFFSET and comments; cplcheck.py (0 differences); pin1geo.py (U201 A1 at (47.6, 24.6), U102 pin 1 at (22.6, 88.0), Q101 pin 1 (25.1, 84.6), C102 + at (64.8, 89.0), D101 cathode (49.5, 93.9)). | Repeat the viewer pass on the final upload with a screenshot per part: U201 ball-A1 corner (toward (47.6, 24.6), the south-east corner of the 8 mm body at (44.0, 21.0)), U102 pin 1 west-north, U103/U104 pin 1 west-north, U105 pin 1 east-south, U106 pin 1 west-south, Q101/Q201 pins 1/2 west, C102 + west, D101–D103 cathode (D101 north, D102 west, D103 east), D204/D205, LEDs, J201/J401 shells, J101 mouth to y = 100. | Key JLC_ROT by LCSC number; keep the screenshots in `orders/`. |
| M3 | Major | Docs / I/O levels | **PMUIO2 is 3.3 V on this carrier, not 1.8 V, so the debug UART header J601 is 3.3 V.** CM3 V1.322 schematic p.7: pin 1N15 PMUIO2 = net VCCA1V8_PMU_1; VCCA1V8_PMU_1 is selected by R11 (NC, to VCCA1V8_PMU), **R12 (0 R, to 1V8_3.3V)**, R13 (NC, to VCC_3V3); p.11: 1V8_3.3V = GPIO_VREF through R24 (0 R). This carrier ties GPIO_VREF to +3V3 (J69 78/84/86), so GPIO0_B0–D2 run at 3.3 V (the base DT's `pmuio2-supply = <&vcc_3v3>` agrees; the IO board puts UART2/I2C2_M0 straight on its 3.3 V 40-pin header). The datasheet's "1.8 V" for I2C1/I2C2_M0 describes the R11 build. Consequences: a 1.8 V adapter's TX (1.8 V) is below the CM3 RX threshold (≈ 2.3 V at 3.3 V) → no console input; its RX sees 3.3 V. Nothing else on the carrier is hurt: GPIO0_C4 (RK628D_PWR_EN) drives an NPN base through 1 kΩ (2.6 mA at 3.3 V, fine); the module's I2C2_M0/I2C0 2.2 kΩ pull-ups (R7–R10) are also on VCCA1V8_PMU_1 and unused here. `checks/iolevels.py` maps PMUIO2 to 1.8 V: conservative, so no pin was placed wrongly. Module revisions with R11 fitted would be 1.8 V: measure J601 pin 1 idle level on the first board. | Rendered crops: `img/c_pmuio2-07.png`, `img/c_r12-07.png`, `img/c_vref-11.png`, `img/c_i2c0-07.png`; REV_A_SPEC lines 217–220, 240, 254; PRODUCTION station 4; `gen/board_io_sheets.py` line 93; kicad/README.md 458–514; `dt/…dtso` line 41; CM3 datasheet I2C table. | Change the text to "3.3 V with GPIO_VREF = 3.3 V (V1.322 module; measure TX idle before connecting an adapter)"; J601 value "DEBUG UART 3V3"; fix `iolevels.py`'s PMUIO2 entry to "= GPIO_VREF". No copper change. | Silk "3V3" at J601. |
| M4 | Major (accepted) | PCIe layout | **PCIE_TX is not routed as a coupled pair anywhere**: 0 % of its 59.8 mm has N within 0.16 mm edge gap (gap histogram: 16.0 mm at 0.26, 10.6 at 0.21, 10.9 at 0.64, 7.8 at 2.41 mm); far stretches at B.Cu (54.8, 26.3)→(44.9, 26.3) 0.40 mm, (39.1, 28.2)→(33.3, 34.0) 0.78 mm, F.Cu (25.6, 29.9)→(20.1, 24.4) 2.55 mm. TX_N has 6 vias, TX_P 4. REFCLK is 38 % coupled. The four layer-change vias beside J702 have no GND via within 4.1–5.0 mm (TX_P (57.9, 25.5) 4.50 mm; TX_N (58.9, 25.8) 4.14; RX_N (56.82, 25.18) 4.96; RX_P (56.18, 25.82) 4.56; REFCLK_P (56.35, 27.4) 3.08). Uncoupled 0.14 mm microstrip is 52.6 Ω single-ended → ≈ 105 Ω "differential" against 85 Ω. PCIE_RX is fine (94 % coupled, 82.4 Ω). | pairgap.py; `checks/returnpath.py`; `checks/zsolve.py` (cqenv). | Accepted by the owner (Gen1 fallback, `max-link-speed` commented in the overlay). If copper is touched at all before upload: a GND via within 1 mm of each of the five vias near J702 (room at x 55–60, y 24–28). Read `lspci -vv` LnkSta and AER counters at bring-up. | Route TX/RX/REFCLK as 0.14/0.10 coupled pairs, ≤ 2 vias each, return via beside every one. |
| M5 | Major (accepted) | Power / thermal | **U104 (SY8303, 5V_SOM) runs hot if the module draws its rated 3 A**: TSOT23-8, θJA 60.2 °C/W, PD 2 W; 1.3–1.7 W loss at 12–17 V in → 80–105 °C rise in free air; the six 0.6/0.3 mm GND vias at U103/U104 and the roof vent help but are unquantified. Documented cap of 1.5–2 A sustained; thermocouple test planned. | SY8303 datasheet p.2–3; REV_A_SPEC §3; PRODUCTION step 9; pcbscan (vias). | Accepted. Measure U104 in the closed case under encode + Wi-Fi. | Exposed-pad 5 V buck. |
| m1 | Minor | CSI layout | **CSI_D3 has a 6.7 mm stretch where N sits 0.36 mm from P (centre) on F.Cu (50.8, 25.6)→(50.8, 32.3)** (only 58 % of D3 is at the 0.10 mm gap); CLK has 5.6 mm at 0.40 mm (64.3, 39.9)→(64.3, 34.3) and D0 1.8 mm. Those stretches are ≈ 115 Ω instead of 92.6 Ω. Short (≤ 0.05 UI at 1.2 Gb/s), not fatal. | pairgap.py far-segment list. | None. | Keep D3/CLK coupled through the fan-in. |
| m2 | Minor | USB layout | **USB_BT (J1 63/65 → M.2 3/5) is essentially two single-ended traces**: 57 mm on F.Cu (29.2, 45.5)→(86.2, 45.5) with DM 1.65 mm away, 20 mm with DM 5.55 mm away; DM 6 vias, DP 0. USB_OTG runs 63 mm on B.Cu at a constant 0.37 mm gap (≈ 105 Ω vs 90). Lengths matched (93.47/93.47, 73.53/73.63 mm). HS USB tolerates it; EMI/CM rejection worse. | pairgap.py; pcbscan. | Test Bluetooth and the OTG gadget at bring-up. | Coupled 0.12/0.10 pairs, symmetric vias. |
| m3 | Minor | Impedance | **The 100 Ω class (0.10/0.10 mm) solves to 92.6 Ω, USB 87.1 Ω, PCIe 82.4 Ω** on the 3313 stack (project solver, re-run). Within TMDS/D-PHY/1000BASE-T windows after JLCPCB's ±10 %, but at the low edge for HDMI; JLCPCB's engineers may propose a width change. | zsolve run (this review). | In the order remark: "build to the drawn geometry; 100/90/85 Ω nominal; no width change" (or accept theirs). | 0.09/0.15 or 0.10/0.18 for the 100 Ω class. |
| m4 | Minor | CSI skew | **Data-to-clock mismatch counting the module's lengths: D3 +6.32, D2 −6.32, D0 +3.54, D1 0 mm** (carrier CLK 51.30/51.48, D0 29.38, D1 51.46/51.64, D2 40.87, D3 29.16; module 35.5/61.1/35.3/39.7/64.1 mm). The CM3's "< 36 mil" rule is broken by the module itself (CLK is its shortest lane); 6.3 mm ≈ 40 ps = 0.05 UI at 1.2 Gb/s. Intra-pair ≤ 0.19 mm. | `gen/csimatch.py report`; CM3 datasheet §3.5.3. | Accepted. Lane rate ≤ 1.2 Gb/s; watch CSI CRC/ECC counters. | Route D2 outside the bundle; match totals < 1 mm. |
| m5 | Minor | Pair skew | **Intra-pair skew above the 12 mil rule**: MDI0–3 0.64–0.68 mm (25–27 mil, ≈ 4 ps); PCIE_REFCLK 0.78 mm (31 mil); PCIE_RX 0.33 mm; M2_PET stubs 0.57 mm. Electrically harmless at 125 MBd / 100 MHz. | pcbscan skew table. | None. | Tune. |
| m6 | Minor | M.2 mechanics | **H501 (16.0, 55.0) is 28.0 mm behind J501's origin; not verified against the M.2 Type 2230 module drawing.** J501's land pattern itself matches TE 114-115006 (previous review). If the notch is 1–2 mm off, the M2 screw will not reach it; the card still works. | pcbscan holes; `gen/board_io_sheets.py` m2(). | Fit a card on the first board and measure; a longer standoff with a bracket or a tie through H501 if needed. | Confirm from the M.2 spec drawing; or a 2.2 × 4 mm slot. |
| m7 | Minor | Power layout | **Thin spots**: 3V3_IO reaches J501 pins 2/4/72/74 through 0.10 mm B.Cu stubs at 0.3 A (86 A/mm², ≈ 4 °C); 1V1_628 has 0.127 mm B.Cu segments at 0.45 A (101 A/mm²); 5V_SYS trunk 0.4/0.6 mm, 70–86 mV at 1 A; LX_5V/LX_SOM 0.3 mm × 2.1 mm necks; SW_IO through 3 vias; VIN 0.8 mm at 2.8 A (100 A/mm², 21 °C if long). 5V_SOM itself is good (1.2 mm, 8 mV at 3 A). | `checks/irdrop.py` output; pcbscan widths. | Measure 3V3_IO at J501 under Wi-Fi TX. | Power islands on In2 or ≥ 0.8 mm trunks. |
| m8 | Minor | Reference planes | **Stretches without solid GND within 0.3 mm on the reference layer**: PCIE_TX_P 12.8 mm, USB_BT_DM 11.6, PCIE_RX_N 9.2, PCIE_TX_N 9.0, MDI3_P 9.1, MDI0_P 7.7, CSI_D2 6.5–6.7, CSI_D0_N 5.9 mm. All four zones are GND, filled (8.8–11.2 k mm²); these are via anti-pad fields under J702 and the magjack holes, not splits. | `checks/returnpath.py` (14 of 50 nets clean). | None. | Keep via fields out of pair corridors. |
| m9 | Minor | Fab options | **110 vias inside SMD pads** (R102, C116, U104 pad 8, J501 pads, RK628D C3/J9 with a 0.3 mm via in a 0.275 mm pad, …); 382 vias at 0.15/0.30 mm (0.075 mm ring); min track/clearance 0.09 mm; hole-to-hole 0.25 mm. Acceptable only with epoxy-filled-and-capped vias and the 0.15 mm option, which the quote carries. | pcbscan via-in-pad; `relay.kicad_pro` rules; quote lines 12–13. | Keep both options on the order. | Fan out beside pads; 0.2 mm drills. |
| m10 | Minor | Input at low battery | At 6 V and full load (≈ 15 W) input current is 2.5–3 A: F101 holds 3 A, J102 (JST PH) 2 A/contact, each SS54 drops ≈ 0.4 V. EN divider 100k/39k turns the SY8303s on above 5.35 V (VENH ≤ 1.5 V), off only at UVLO (≤ 4.35 V); software must shut down at 6.0 V. | BOM; SY8303 EN/UVLO table. | Keep battery loads realistic. | 4–5 A fuse, XT30, ideal-diode OR. |
| m11 | Minor | HDMI out 5 V | AP22804AW5-7 limits at 2.7–3.3 A (0.45 A short), not the ≤ 0.5 A a source should supply; a faulty sink loads 5V_SYS. Pinout (OUT/GND/FLG/EN/IN = 1–5) and EN = IN are right. | AP22804 datasheet pin table, ILIMIT. | None. | 0.5 A switch or polyfuse. |
| m12 | Minor | ADC | VIN_SENSE (100k/10k) has no clamp: 1.55 V at 17 V, full scale at 19.8 V, up to 2.9 V during an SMBJ20CA clamp (32.4 V); 9 kΩ source limits it to ~0.1 mA. | `gen/power.py`; SMBJ20CA Vc. | None. | BAT54 to SOM_1V8. |
| m13 | Minor | USB-C | No ESD on CC1/CC2 (into the CH224A directly), no TVS on VBUS_C (SMBJ20CA is after D103); USBLC6 pin 5 open is right at a 9 V contract. CH224A: VHV/VBUS 32 V, PG 32 V, CFG1 3.8 V (6.8 kΩ to GND). | CH224 manual §4.1, §8.1.1. | None. | 5 V ESD on CC; 20–24 V TVS on VBUS_C. |
| m14 | Minor | RK628D off state | While RK628D_3V3 is off: I2C2 and CEC pull-ups hang on it (R207/R208/R214), the CM3 can drive RESET_N (GPIO3_C2, 3.3 V push-pull) into the unpowered chip, a camera's 5 V reaches RX_SCL/SDA through 47 kΩ + 22 Ω. Sub-mA; same structure as DshanPi; the overlay's `enable-gpios`/`reset-gpios` give the rk628 driver the sequence (enable → 10 ms → reset pulse). | `gen/hdmi_in.py`; `bsp/drivers/mfd/rk628.c` lines 393–414. | Raise RK628D_PWR_EN early in boot, keep it on while a camera is attached. | I2C2 pull-ups from 3V3_IO. |
| m15 | Minor | Device tree | The overlay's `rk628@50` node has no child nodes (`rockchip,rk628-hdmirx`, `-csi`, `-combrxphy`, `-combtxphy`, `-cru`, …): the BSP rk628 MFD only registers cells whose compatibles exist in the DT, so this overlay alone brings up the chip (GPIOs, I2C, reset sequence) but not the HDMI-RX → CSI pipeline or the `rkcif`/`rkisp` link. The overlay says property names are the vendor driver's; `enable`/`reset` GPIO names match `rk628.c`, `plugin-det-gpios` is for the hdmirx child. | `bsp/drivers/mfd/rk628.c` lines 70–145, 393–414. | Software: add the child nodes and the CSI port graph from a DshanPi/RK3576 rk628 dts at bring-up. | — |
| m16 | Minor | Docs | Stale or misleading text beyond M3: `gen/hdmi_in.py` Note on J201 "LCSC C2902698" (BOM is Molex C916313); `orders/…quote.md` cart section (M1); `kicad/README.md` 458–514 and REV_A_SPEC 217–220 explain pin moves with "PMUIO2 is 1.8 V" (true only for R11 modules); no board name/revision on the silk (no board-level text at all). | files named; pcbscan "silk text: none". | Fix with M3. | "HDMI relay rev A" silk. |
| m17 | Minor | Courtyards | J101's courtyard overlaps D101's (1.09 × 7.09 mm) and C105's; bodies do not touch (J101 F.Fab x 37.5–46.6, D101 48.0–51.1) and DRC passes, but the jack's pad 3 (switch, unconnected) sits 0.15 mm from D101's courtyard. FB201/FB202/C234 courtyards touch (0.06–0.08 mm). | fab_bbox.py; pcbscan courtyard list. | None. | Give the jack 1 mm more. |
| n1 | Note | CM3 connectors | Radxa's IO board decal for J68/J69 (`DF40C-200DS-D4-OK`, 204 terminals) has four GND pads 201–204 that `relay:Radxa_CM3_J68` lacks; the 300 signal pads coincide to 0.0000 mm (b2bfit: rotation 90°, rms 0; mirror rejected at 19.7 mm). Mechanical only; the module is screwed down. | `checks/b2bfit.py`. | None. | Add them if the receptacle has fittings. |
| n2 | Note | Device tree base | The base already has `vccio_acodec` 3.3 V always-on and `vccio1-supply`; the overlay repeats it (harmless). Base claims on reused pins are all disabled in the merged tree (sdmmc0, vcc_sd GPIO0_A5, vcc5v0_usb30 GPIO3_C2, tf_det GPIO0_D4 → hog, ch482d GPIO3_C6/C7, pi/pwr LEDs GPIO4_A4/B7, hym8563 at 0x51). The module's own Wi-Fi/BT nodes (sdio_pwrseq GPIO2_B7, bt GPIO2_B1/B2/C0, uart8) stay enabled: their pins are not on the carrier (W0 module), so no conflict. `pcie2x1` keeps `vpcie3v3-supply = <&vcc3v3_sys>` from the base (no GPIO). `reset-gpios` ACTIVE_HIGH matches the base's convention; the rk628 `reset-gpios` ACTIVE_LOW matches the driver's set(1)=assert sequence. | `bsp/merged.dts`; base dts lines 30–60, 117–135, 205–235. | Boot it. | — |
| n3 | Note | CH224A | Pin 1 = VHV on VBUS_C (32 V rated; a CH224K would die at 9 V: the BOM says C42459160 = CH224A), pin 8 VBUS shorted to VHV as the manual requires, CFG1 6.8 kΩ = 9 V, PG open-drain into Q101's gate with 100 kΩ to VBUS_C, AO3401A VGS −9 V within ±12 V, body diode blocks VBUS_C → VBUS_SW, D103 blocks back-feed. A 5 V-only source leaves Q101 off, as intended. | CH224 manual §3, §4.1, §5.2.1, §7.1, §8.1.1; `lcsc-mpn.json`. | — | — |
| n4 | Note | ERC strength | ERC 0 is weak: generated symbols declare nearly every pin `passive` (CM3, RK628D, regulators, ESD arrays), so power/output conflicts cannot be caught. The netlist checks here stand in. | `gen/sch.py`, `gen/module.py` `_symbol()`. | — | Real pin types. |
| n5 | Note | Crystal | C70590 = YXC X322524MOB4SI, 24 MHz, **12 pF** (lcsc-mpn.json), with 2 × 18 pF: CL ≈ 9 + 3 pF stray = 12 pF. OK. | `gen/lcsc-mpn.json`. | — | — |
| n6 | Note | Panel / edges | HDMI shells overhang the front by 1.02 mm (F.Fab y −1.02), magjack the rear by 5.25 mm, USB-C face at y 99.55, DC jack mouth at y 99.35 (0.65 mm inside). JLCPCB adds rails on the short edges by default. | fab_bbox.py. | Ask for rails on the 120 mm edges in the order remark. | Line up the rear connectors. |
| n7 | Note | CM3 power pins | +5V_INPUT is six DF40 contacts at 0.3 A each (1.8 A sustained): Radxa's design, documented. USB_5V_IN (J1 94/96/98) must stay open when +5V_INPUT is used: it is. VCC_BAT±/TS open (no battery). PWRON_KEY open: the RK817 auto-powers on +5V_INPUT (datasheet §3.1.2). | CM3 datasheet §3.1.1–3.1.3; netlist. | — | — |
| n8 | Note | Case | `case.py --check`: PASS (board STEP x 0..120, y −1.0..105.5, z 3.7..22.6; roof underside 24.4; STEP 21:42 is newer than the board save 21:35). Openings vs board: HDMI c = 24/79 (J201/J401 x 24.0/79.0), USB-C c = 16 (J103 x 16.0), DC c = 42 (J101 axis x 42.0), Ethernet c = 99 (J301 body centre 98.9), light pipes = D601/D602/D603 within 0.05 mm, pinholes = SW601/SW602, M3 holes = H601/H603/H602/H604 at (4,4)/(4,96)/(116,36)/(116,68), battery hole x 58 = J102. Module, heatsink, Wi-Fi card, USB-C and M.2 sockets are stand-in blocks. | case run; pcbscan. | Fit-check the first board. | — |
| n9 | Note | Stock | Not re-checked online. Earlier: RK628D 27 pcs, magjack 0 (hand-fit), SRN6045TA-6R8M low. | — | Order promptly. | Second-source the RK628D. |
| n10 | Note | PERST#/W_DISABLE at boot | R501/R502/R503/R505 DNP (not in BOM/CPL); R504 (WIFI_DISABLE#, PMUIO1) fitted. PERST#/CLKREQ#/WAKE#/BT_DISABLE# are defined by the card's pull-ups until the kernel configures pulls; harmless. | BOM; netlist. | — | — |
| n11 | Note | Recovery / VBUSDET | RECOVERY: SARADC_VIN0 (J69-93, V1.32) with 10 kΩ to SOM_1V8 + 1 nF; RESET: PMIC_RESET_KEY to GND; VBUSDET held at 3.3 V through 10 kΩ (top of the 2.7–3.3 V window); USB_OTG0_ID open = device mode. Matches datasheet §3.2.1 and §3.10. | netlist; CM3 datasheet lines 640–666, 1870–1904. | — | — |

## What I verified as correct

**CM3 pin map (all 300 pins, from the netlist).** Every assignment lands on the intended function with the V1.32
moves applied (J69-37 = GPIO4_C5/UART9_TX_M1, J69-93 = SARADC_VIN0, J1-14 = SARADC_VIN3, J1-26 NC, J1-34 unused).
MDI0–3 J69 12/10, 4/6, 11/9, 3/5; CSI D0/D1/CLK0/D2/D3 J68 117/115, 123/121, 129/127, 130/128, 136/134; PCIe TX/RX/REFCLK
122/124, 116/118, 110/112; CLKREQn/PERSTn/WAKEn all `_M2` (J68-102, J68-109, J1-38); USB_OTG0 105/103; USB2 HOST2 J1
63/65; HDMI TX 170/172, 176/178, 182/184, 188/190, HPD 153, DDC 199/200, CEC GPIO4_D1 (151); I2C2_M1 35/36; I2C4_M0
38/44; UART2_M0 51/55; UART9_M1 J69-37/J1-36; CIF D0–D15/HREF/VSYNC/CLKIN; PMIC_RESET_KEY 100; VBUSDET J1-97; 5V_SOM × 6;
+3V3 × 2 + GPIO_VREF tied; +1V8 × 2. All 76 GND pins on GND. `b2bfit.py`: 300/300 pads at 0.0000 mm against Radxa's
IO board, mirror rejected. The three receptacle footprints are geometrically Radxa's (J703's odd/even sense is the
IO board's J24 decal, which mates with the module).

**I/O banks (from the V1.322 schematic images).** PMUIO1 = VCC3V3 ("3.3 V only"); OSC domain GPIO0_D3–D6 "1.8 V
only"; **PMUIO2 = VCCA1V8_PMU_1 = 1V8_3.3V = GPIO_VREF (R12/R24 0 Ω) = 3.3 V here** (M3); VCCIO1 = VCCIO_ACODEC (RK817
LDO4); VCCIO5 = VCC_3V3 (R43); VCCIO6 = GPIO_VREF; VCCIO7 = VCC_3V3. Every 3.3 V signal is therefore on a 3.3 V
bank: RESET_N GPIO3_C2, INT GPIO3_C3, I2C2 GPIO4_B4/B5, LED_STATUS GPIO4_B1, LED_WIFI GPIO0_A5, PLUGIN_DET GPIO0_A4,
WIFI_DISABLE GPIO0_A0, CEC GPIO4_D1, SDI UART GPIO4_C5/C6, DVP/SDI GPIOs on VCCIO5/6, PWR_EN GPIO0_C4. Module-side
circuits on reused pins: Q4/R170 100 Ω/R171 1 kΩ (TF_DET → SDMMC0_DET_L; the DT hog covers it), C54/C55 100 nF on
PCIE20_TXP/N (so C501/C502 = 0 Ω is right), HDMI HPD 100 kΩ pull-down + 1 kΩ series and DDC/CEC level shifters on the
module, VBUSDET straight to the SoC.

**RK628D.** All 144 balls match datasheet table 2-1/2-2 (power groups: DVDD D8/E9; VCCIO1 H5; VCCIO2 E8/F8; PLL_AVDD
M10 3.3 V; PLL_AVDD_1V1 J7; EFUSE J8; MIPI PLL C3; MIPI AVDD_3V3 D5/E4; MIPI AVDD_1V1 C5/D4/E3/F3; HDMITX DVDD J4–J6,
AVDD K4; HDMIRX DVDD H9/J9, AVDD J10; 29 VSS). MIPI lane order TX0/1/2/3/4 = D0/D1/CLK/D2/D3 as DshanPi p.31 (G2/F2/E2/
D2/C2 → CSI0 D0P/D1P/CLKP/D2P/D3P), P to P into J68. Straps: I2C_ADDR 10 kΩ to GND (+ internal pull-down) → 0x50 = the
DT; TEST to GND; RESETN internal pull-up + 100 nF; INT/SPIBOOT on a reset-pull-down CM3 pin. MIPI_REXT 4.02 kΩ 1 %,
RX/TX EXTR 2 kΩ 1 %, EFUSE_VDD_2V5 100 Ω + 100 nF to GND as DshanPi. Power gate AO3401A/MMBT3904 10k/1k/1k/100k, 1V1
enable from RK628D_3V3 through 10k/100n, ferrite-split AVDD rails, decoupling at the balls on the back. BGA 12 × 12 at
0.65 mm, 0.275 mm pads, 0.15/0.3 mm dogbone vias.

**HDMI IN / OUT.** Connector pins 1–19 standard into the Molex 208658-1001 footprint (BOM C916313 = 2086581001);
RCLAMP0524P (Tech Public, pins 1/2/4/5 I/O, 3/8 GND, 6/7/9/10 NC per its datasheet page 1): **every pass-through pad pair
on all six arrays is joined by board copper** (traced through F.Cu segments: D201/D202/D401/D402 straight through,
D203/D403 by links). HPD from K8 through 22 Ω; CEC 27 kΩ via MBR0530 + 22 Ω; DDC 47 kΩ to the source's 5 V via MBR0530 +
22 Ω; plug detect 2k/10k MMBT3904 into GPIO0_A4 with 10 kΩ to 3V3_IO; 100 nF on HDMIRX_5V. HDMI OUT: HPD straight to
J68-153; DDC 2.2 kΩ to HDMITX_5V; 5 V from U401 (EN = IN), 1 µF each side; three arrays. TMDS carrier 22.65–23.02 mm,
P/N 0.00; clock-to-data counting the module (CLK 36.0, D0 33.2, D1 30.2, D2 28.5 mm) ≤ 7.9 mm = 311 mil < 480 mil.

**Power tree (datasheets).** SY8303 pins FB/FS/GND/GND/IN/LX/BS/EN = 1–8; VOUT = 0.6 × (1 + 110/15) = 5.00 V; RFS 200 kΩ
= 0.5 MHz; BS 10 nF; EN 0.28 VIN (on above 5.35 V; abs max 40 V); 2 × 4.7 µF/50 V in + 47 µF/35 V bulk; 2 × 22 µF/25 V
out; 6.8 µH (ripple ≈ 1 A, peak 3.5 A vs 3.6 A rms). TPS563201 pins GND/SW/VIN/VFB/EN/VBST = 1–6; VFB 0.768 V → 3.30 V
and 1.10 V; EN internal 225–900 kΩ pull-down so 100k/100n from 5V_SYS settles ≥ 3.4 V and 10k/100n from RK628D_3V3 at
3.2 V; EN abs max 19 V; 0.1 µF VBST; 2.2/1.5 µH (4.6/4.95 A parts); 10 µF + 100 nF in, 2 × 22 µF out. Inputs: SS54 × 3
OR-ing, reversed DC blocked, SMBJ20CA (standoff 20 V ≥ 17 V, clamp 32 V < 40 V parts), 3 A/30 V PTC, VIN_SENSE =
VIN/11. All MLCC ratings above their rails (22 µF parts are 25 V). C102 + on VIN. U401 AP22804AW5 pins match SOT25.
Q101/Q201 G/S/D = 1/2/3; Q202/Q203 B/E/C = 1/2/3; D204/D205 anodes on RK628D_3V3/HDMIRX_5V; USBLC6 1→6, 3→4, pin 2 GND.

**Ethernet.** MDI0–3 → J301 MX1–MX4 (pads 11/10, 4/5, 3/2, 8/9); centre taps 12/6/1/7 through 1 µF to GND (voltage-mode
RTL8211F, datasheet §3.4). Pairs 53–70 mm, 98 % coupled at 0.10 mm, all F.Cu.

**M.2 E-key (netlist).** GND 1/7/18/33/39/45/51/57/63/69/75; 3.3 V 2/4/72/74 (2 × 22 µF + 2 × 100 nF); USB 3/5;
PETp0/n0 35/37 ← host TX via 0 Ω; PERp0/n0 41/43 → host RX; REFCLK 47/49; PERST# 52; CLKREQ# 53; W_DISABLE2# 54 =
BT_DISABLE_N; PEWAKE# 55; W_DISABLE1# 56 = WIFI_DISABLE_N; key 24–31 absent. USB-C: CC1/CC2 to the CH224A only, D+/D−
both rows through USBLC6, SBU open, shell GND. DC jack: pads match PJ-002A (1 = centre, 2 = sleeve, 3 = switch),
mouth toward y = 100.

**Layout / fab.** DRC + parity 0/0/0, ERC 0. Board 120 × 100 mm, four filled GND zones, 1043 vias (614 × 0.25/0.45,
382 × 0.15/0.3, 47 × 0.3/0.6). CSI/HDMI on F.Cu over In1 (CSI D2/D3 hop to B.Cu with GND vias 0.7–1.0 mm away).
Gerbers/drill/zip identical to a fresh export; job file 0.0994 / 1.265 / 0.0994 mm 3313, Er 4.1, ENIG,
ImpedanceControlled; `fab.py` refuses any other stack. BOM 59 lines, every LCSC number resolving to the intended
MPN/package; 7 DNP parts (R202, R216, R501–R503, R505, J602) in neither BOM nor CPL; J301 in `relay-bom-handfit.csv`
only; CPL 175 rows = BOM references; 62 bottom-side parts, all two-terminal passives.

**Device tree and case:** n2, n8. **Docs:** REV_A_SPEC §6 board size, stackup, two-sided assembly, electrolytic, DC jack
and crystal notes, README opening and PRODUCTION "5, not ordered" are fixed since REVIEW_FINAL_2 (its m18); spacers
documented (m17); J301 out of BOM/CPL (m16).

## Earlier reviews: every claimed status re-checked

**REVIEW_FINAL_2.md (commit 6535945)** — all re-measured on HEAD:

| Item | Claimed | Found at d32a7c2 |
|---|---|---|
| M1 cart holds stale Y6 | open | **Still open as a document fact** (M1 here): the order note was not updated after e7f753b/d32a7c2; `fab/` is correct. |
| M2 U104 thermal | accepted | Confirmed, accepted (M5). |
| m1 PCIe TX 43 % coupled, REFCLK 67 %, no return vias | accepted | Confirmed; by a 0.16 mm edge-gap criterion TX is 0 % coupled, REFCLK 38 % (M4). |
| m2 USB_BT/OTG uncoupled | accepted | Confirmed (m2). |
| m3 100 Ω class = 92.6 Ω | accepted | Confirmed by re-running zsolve (m3). |
| m4 CSI skew +6.5/−6.2 | accepted | Confirmed: +6.32/−6.32 (m4). |
| m5 MDI/REFCLK intra-pair | accepted | Confirmed (m5). |
| m6 H501 unverified | open | Still open (m6). |
| m7 J68 pads 201–204 | open | Still open (n1). |
| m8 reference-plane gaps | accepted | Confirmed (m8). |
| m9 thin power spots | accepted | Confirmed (m7). |
| m10 fuse/JST at 6 V | accepted | Confirmed (m10). |
| m11 AP22804 limit | accepted | Confirmed (m11). |
| m12 VIN_SENSE clamp | accepted | Confirmed (m12). |
| m13 CC ESD / VBUS TVS | accepted | Confirmed (m13). |
| m14 RK628D off-state | software | Confirmed; driver sequence checked in `rk628.c` (m14). |
| m15 via-in-pad / options | accepted | Confirmed, 110 vias (m9). |
| m16 J301 in BOM/CPL | open | **Fixed** (e7f753b): hand-fit file only; CPL 175 rows. |
| m17 M2.5 spacers undocumented | open | **Fixed**: PRODUCTION station 3 and orders/dev-parts.md list 4 × M2.5 × 1.5 mm. |
| m18 docs | open | **Mostly fixed** (e7f753b); remaining: `hdmi_in.py` Note C2902698, no silk name, and the new M3/m16 items. |
| n1 DT applies; vccio_acodec already in base | note | Confirmed; plus m15 (no rk628 child nodes). |
| n2–n11 | notes | All confirmed (n3 CH224A, n4 ERC, n7/n6 panel, n8 case, n10 DNP pull-ups, n11 recovery). |
| "I/O banks: PMUIO2 = VCCA1V8_PMU (1.8 V)" in its verified section | verified | **Disagree**: PMUIO2 = VCCA1V8_PMU_1 = GPIO_VREF via R12/R24 = 3.3 V here (M3). Same error in TEST_REPORT.md, REVIEW_INDEPENDENT (its bank map), REV_A_SPEC and README. The pin moves it motivated are still fine. |

**Older reports (REVIEW_FINAL, REVIEW_FABLE/_2/_3, REVIEW_INDEPENDENT, TEST_REPORT)** through REVIEW_FINAL_2's table:
the 1.8 V-pin moves (INT GPIO3_C3, RESET_N GPIO3_C2, LEDs GPIO4_B1/GPIO0_A5, BT_DISABLE GPIO1_A4, PD_PG_N off the
module), the ESD pass-through links, C501/C502 = 0 Ω, CSI matching, stackup in the files, DC-jack direction, case
labels, RFS 200 kΩ, inductor substitutions, thermal vias at U103/U104, 12 V + USB flashing, the TF_DET hog, and the
PCIe PET/PER swap are all **confirmed in the HEAD netlist/board/files**. REVIEW_FABLE_2 M4 / FABLE_3 M1 ("all
polarised parts checked in the viewer") is the one item nothing offline can confirm (M2 here).

## Software and device-tree requirements the hardware imposes

vccio_acodec 3.3 V boot-on (base does it) with SoC pull-ups on GPIO1_B0/B1; PERST# GPIO1_B2; BT enable GPIO1_A4
high; Wi-Fi enable GPIO0_A0 high; GPIO0_D4 held low; sdmmc0 and the IO board's regulators/LEDs/RTC off (overlay does
all of this); RK628D on i2c2m1 at 0x50 with reset GPIO3_C2 (active low), interrupt GPIO3_C3, power GPIO0_C4 raised early
and kept on while a camera is attached, plug detect GPIO0_A4 (active low); rk628 child nodes + CSI port graph still to
write; CSI 4-lane on CLK0 at ≤ 1.2 Gb/s; pcie2x1 with `max-link-speed = <1>` in reserve; **UART2_M0 console at 3.3 V
(GPIO_VREF)**; USB OTG0 peripheral; SARADC_VIN0 recovery; SARADC_VIN3 = VIN/11 (full scale 19.8 V); shut down below
6.0 V on battery; flash with 12 V on the DC jack plus USB-C for data.
