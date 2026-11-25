# Rev A: final pre-fab review (Fable, Oct 25, 2026, commit d5c0b40)

Scope: `relay.kicad_sch` and its sheets (netlist re-exported with kicad-cli), `relay.kicad_pcb` and `routed.kicad_pcb`,
the fab outputs in `fab/`, the generators in `gen/`, the checks in `checks/`, `../dt/rk3566-relay-carrier.dtso`,
`../case/case.py`, `../REV_A_SPEC.md`, `../PRODUCTION.md` and `../orders/`, against the datasheets in `../datasheets/`
(CM3 datasheet and V1.322 schematic, V1.3→V1.32 pinout history, CM3 IO board V1.35 schematic, RK628D, RK3568, DshanPi-A1,
SY8303, TPS563201, CH224, AP22804, PJ-002A, JK0654219NL). ERC, DRC (`--schematic-parity --severity-all`) and
`checks/b2bfit.py`, `iolevels.py`, `returnpath.py`, `irdrop.py`, `tline.py` were re-run; the board was dumped with pcbnew
and analysed with scripts kept in `/private/tmp/claude-501/fable-review-final/`. The five earlier reports were read only
after the findings below were formed. Nothing in the project was changed except adding this file.

## Status after fixes (Oct 25, later the same day)

- **B1 fixed.** `gen/board_io_sheets.py`: PETp0/PETn0 (35/37) now carry the host TX through C501/C502 (0 Ω), as
  `M2_PET_P/N`; PERp0/PERn0 (41/43) carry PCIE_RX_P/N. Copper: PCIE_RX ends 1.5 mm further east, at 41/43, in the same
  shape as before; C501/C502 pad 2 run on F.Cu to 35/37 through the band north of the pads; REFCLK_N, which used that
  band, now drops through a via in pad 49 and runs on B.Cu under the pad row to its old path; PCIE_TX_P's B.Cu run
  moved 0.1 mm east to clear that via. DRC with parity 0/0/0, ERC 0. Lengths: TX+PET 62.89 / 63.38 mm (0.49 mm
  skew), RX 53.74 / 54.07, REFCLK 59.63 / 58.85. The new PET stubs have no vias. `fab/` regenerated: copper and drill
  only, BOM and CPL unchanged. A new JLCPCB upload is still needed (M4).
- **M1 fixed.** The overlay targets Radxa's BSP base (radxa/kernel linux-5.10-gen-rkr4.1, rk3566-radxa-cm3-io.dts)
  and turns off sdmmc0, `vcc_sd` (GPIO0_A5), `tf_det` (GPIO0_D4, replaced by the hog), and three more conflicts that
  base has: `vcc5v0_usb30` drives GPIO3_C2 (RK628D_RESET_N) high, always on; `vcc_ch482d1/2` drive GPIO3_C6/C7
  (DVP_D0/D1) and the pi/pwr LEDs drive GPIO4_A4/B7 (DVP_D14/VSYNC); the hym8563 at 0x51 on i2c2 is off. The USB2
  host phy moves to `vcc5v0_sys`. GPIO0_A0 and GPIO0_D3 are not claimed by that base. The overlay compiles with
  dtc 1.8.1 and applies with fdtoverlay to a base built from those sources (statuses checked in the merged tree).
- **M2 fixed.** USB-C opening now 8.8 mm tall from 2.4 mm below the board top, cut in the base wall as well as the
  lid. Tripod bosses rise to 0.2 mm under the board; insert holes 5.0 mm deep for a ¼"-20 × 0.2" insert, leaving a
  0.8 mm solid stop. `case.py --check` now also probes a 12 × 6.5 mm plug overmould and the stop above each insert:
  PASS.


**Not ready to order.** One blocker, which none of the five earlier reports caught because all of them took the M.2
pin names the wrong way round:

- **The PCIe lane to the M.2 Wi-Fi socket is reversed.** The CM3's receiver (PCIE20_RXP/N, J68 116/118) is wired to
  J501 pins 35/37 (PETp0/PETn0) and the CM3's transmitter (PCIE20_TXP/N, J68 122/124, through the C501/C502 0 Ω
  links) to pins 41/43 (PERp0/PERn0). In the M.2 and PCIe CEM conventions PET is the *host's* transmit pair and PER
  the host's receive pair: the DshanPi-A1 wires its SoC's PCIE_SOC_TXP through 0.1 µF into M.2 pin 35 "PETP0"
  (schematic p.36), and Radxa's CM3 IO board wires PCIE20_TXP to its slot's HSOp(0). As built, the card's transmitter
  meets the CM3's transmitter and the two receivers meet each other: the link never trains, so there is no Wi-Fi.
  Bluetooth (USB) still works. It is a schematic swap of two pin pairs and a few millimetres of re-routing at J501,
  then DRC, `gen/fab.py`, a new JLCPCB upload and a repeat of the placement-viewer check.

Everything else that the earlier reviews reported fixed is fixed and is in the manufactured files: the pin moves, the
ESD pass-through links (confirmed by connectivity with the arrays replaced by bare pads), the C501/C502 links, the
thermal vias, the stackup in the job file, the DC jack direction, the CSI matching, the DNP resistors, the inductor swap
and the case labels. The remaining Majors are the known thermal limit (accepted with a documented current cap), the
case (two mechanical faults that stop the USB-C plug and put a tripod insert into the board) and the device-tree
overlay (it does not disable the module's SD-card nodes that own the two GPIOs it reuses).

**Counts: 1 Blocker, 4 Major, 14 Minor, 10 Note.**

Coordinates below are board coordinates in mm (KiCad coordinates minus (30, 30)).

## Findings

| ID | Sev. | Area | What's wrong | Evidence | Rev A action | Rev B fix |
|---|---|---|---|---|---|---|
| B1 | **Blocker** | M.2 PCIe | **Host TX and RX are swapped at the M.2 socket.** J501.35 (PETp0) and .37 (PETn0) carry PCIE_RX_P/N from J702.16/18 (116 PCIE20_RXP, 118 PCIE20_RXN). J501.41 (PERp0) and .43 (PERn0) carry M2_PER_P/N, which are PCIE_TX_P/N from J702.22/24 (122 PCIE20_TXP, 124 PCIE20_TXN) through C501/C502 (0 Ω). PET/PER are named from the host: PET = host transmit → module receive, PER = module transmit → host receive. The schematic comment in `gen/board_io_sheets.py` m() ("PETp0: card transmits → host receives") has it backwards, and every earlier report copied that reading. | Netlist: `PCIE_RX_P: J501.35(PETp0), J702.16(116_PCIE20_RXP)`; `M2_PER_P: C501.2, J501.41(PERp0)`; `PCIE_TX_P: C501.1, J702.22(122_PCIE20_TXP)`. `datasheets/DshanPi-A1-RK3576-SCH_V1.1.pdf` p.36 "M.2 KEY E": `[15] PCIE_SOC_TXP → C452 0.1uF → pin 35 AP_PETP0`, `PCIE_SOC_TXN → C453 → 37 AP_PETN0`, `PCIE_SOC_RXP → C454 → 41 AP_PERP0`, `PCIE_SOC_RXN → C455 → 43 AP_PERN0`; p.15 shows PCIE_SOC_TXP is the RK3576 PCIe0 root-complex TXP. `datasheets/SCH_CM3_IO_V1.35.pdf`: `PCIE20_TXP_1 → HSOp(0)`, `PCIE20_RXP_1 → HSIp(0)` on the PCIe x1 slot (HSO = host output). CM3 datasheet appendix C: 116/118 = PCIE20_RXP/N, 122/124 = PCIE20_TXP/N. | **Fix before ordering.** `gen/board_io_sheets.py` m(): PETp0/PETn0 ← the host TX path (M2_PER_P/N, i.e. through C501/C502 from PCIE_TX), PERp0/PERn0 ← PCIE_RX_P/N; rename the nets. Board: pads 35/37 are at x 15.25/15.75 and 41/43 at 16.75/17.25, all at y 23.23; C501/C502 sit at (16.75/17.85, 20.45–21.41). Cross the two pairs in the 3 mm north of the pads (one pair on B.Cu with a GND via beside each signal via, or move C501/C502 west). Keep C501/C502 at 0 Ω: the module's C54/C55 are the TX capacitors. Re-run DRC with parity, `gen/sync.py`, `gen/fab.py`, upload as a new JLCPCB order and repeat the viewer check (M4). Update REV_A_SPEC §7 and `kicad/README.md`. If boards are already built: cut the four tracks at J501 and cross-wire with 0.1 mm wire (PCIe Gen1 may survive 3 mm of wire), or ship without Wi-Fi. | Same mapping, routed as coupled 85 Ω pairs with symmetric vias. |
| M1 | Major | Device tree | **The overlay does not take GPIO0_A4 and GPIO0_A5 away from the module's SD-card nodes.** On the Radxa CM3 IO device tree GPIO0_A4 (SDMMC0_DET_L) is sdmmc0's card detect and GPIO0_A5 (SDMMC_PWREN) is the SD supply enable. Here they are RK628D_PLUGIN_DET and LED_WIFI. With sdmmc0 left enabled the mmc core sees a "card" whenever a camera is plugged in, requests GPIO0_A4 before the rk628 driver can, and drives GPIO0_A5 (the Wi-Fi LED) as a regulator. The same applies to GPIO0_A0 (WIFI_PWREN on the IO board, a regulator enable there) and GPIO0_D3 (PCIE_PWREN_H on the IO board) if the base tree uses them. The overlay has not been compiled (no dtc) and the rk628 binding is the vendor's, so property names are unverified. | `dt/rk3566-relay-carrier.dtso` (no `&sdmmc0`, `&vcc_sd`/`vcc3v3_sd` or Wi-Fi-regulator overrides); CM3 datasheet appendix C pins 75/76; CM3 IO schematic "SD_PWR_ON", "3V3_PWR_EN". | Add `&sdmmc0 { status = "disabled"; };` and disable (or re-GPIO) the base tree's regulators that use GPIO0_A5, GPIO0_A0 and GPIO0_D3; compile the overlay with `dtc` against the BSP tree before bring-up; keep `max-link-speed = <1>` ready for pcie2x1. The pin/bank/polarity content of the overlay is otherwise right (see "Verified"). | Same. |
| M2 | Major | Case | **Two mechanical faults in `case/case.py`.** (a) The USB-C opening is cut in the lid only (`lid()` REAR cut, z0 = Z_BT − 0.6, but the lid solid starts at Z_BT) and the base wall is solid up to the board plane. The J103 face is 0.5 mm inside the board edge, so the receptacle sits 0.5 + 0.4 + 2.2 = 3.1 mm behind the outer wall face; a USB-C plug's overmould (about 6.5 mm tall, centred 1.6 mm above the board) cannot enter, and its 6.5 mm shell reaches only about 3.4 mm into the socket: it will not mate. (b) The two ¼"-20 insert holes are 6.6 mm deep from z = 0 while the board underside is at Z_BB = 6.0 mm and the bosses stop at 5.0 mm: the hole breaks through the boss and a ¼" insert, or any screw run in past it, bears on the PCB. The `--check` intersection test cannot see either (a hole is not a solid). REVIEW_FABLE_2 m14 raised both; neither was changed. | `case/case.py`: `UNDER = 4.0`, `FLOOR = 2.0`, `Z_BB = 6.0`; `TRIPOD_INSERT = dict(d=8.0, depth=6.6)`; `boss … extrude(UNDER - 1.0)`; `base()` cuts only the Ethernet relief; `REAR` USB-C `z=-0.6`. J103 F.Fab extent y 92.10..99.50 (pcbnew). | Before printing: notch the base wall under the USB-C opening down to about 2 mm below the board top (and extend the lid cut to meet it); make the tripod bosses full height (UNDER) and the insert holes at most 5.5 mm deep, or move them under a bare patch and add a stop. Re-run `--check` and a 1:1 print fit with a USB-C cable and a ¼"-20 screw. | Same, plus the lid boss and thermal pad to the module that REV_A_SPEC §6 calls for. |
| M3 | Major | Power, thermal | **U104 (SY8303, 5V_SOM) is at its thermal limit at the module's rated 3 A** (TSOT23-8, θJA 60 °C/W, no pad; about 1.3–1.7 W from 12–17 V). Six 0.6/0.3 mm GND vias are in place (board (49.76..68.96, 77.75..79.1)); the case has a roof vent over it. Accepted by the owner with a documented 1.5–2 A sustained cap and a thermocouple test. The DF40 contacts (0.3 A × 6) cap the module near 1.8 A anyway. | SY8303 datasheet p.2; REV_A_SPEC §3 "5V_SOM thermal limit"; PRODUCTION step 9; pcbnew via list. | Accepted: keep the limit, measure U104 in the closed case. | Exposed-pad 5 V buck for U103/U104. |
| M4 | Major | Assembly, CPL | **The CPL rotation table cannot be verified offline, and B1 forces a new upload.** `JLC_ROT` corrects 20 references; the earlier viewer check (REVIEW_FABLE_3 M1) was done by eye on the Y6 upload. Once B1 regenerates the CPL, that check is void and must be repeated, particularly for U103–U106 (a 180° error shorts a rail), U201 (ball A1), U401, U102, the SS54/SMBJ diodes on VIN, and the three DF40 receptacles. | `gen/fab.py` JLC_ROT; `fab/relay-cpl.csv`. | Repeat the part-by-part placement-viewer check on the post-B1 upload before paying. | Rotation table keyed by LCSC number with a screenshot per part. |
| m1 | Minor | CSI | **Data-to-clock mismatch including the module's lengths is 6.3 mm (D2 −6.32, D3 +6.32, D0 +3.5 mm) against the CM3 rule of < 36 mil.** Carrier: CLK 51.30/51.48, D0 29.38, D1 51.46/51.64, D2 40.87 (2 vias), D3 29.16 (2 vias); module (CM3 datasheet §3.5.3): CLK0 35.5, D0 61.1, D1 35.3, D2 39.7, D3 64.1 mm. 6.3 mm is about 40 ps, 0.05 UI at 1.2 Gb/s. Intra-pair ≤ 0.18 mm. | pcbnew lengths; CM3 datasheet lines 1068–1096. | Accepted: run ≤ 1.2 Gb/s per lane, watch CSI CRC/ECC counters. | Route D2 outside the bundle; match all five totals to < 1 mm. |
| m2 | Minor | PCIe / USB layout | **PCIe TX and REFCLK are uncoupled single traces (about 104 Ω instead of 85 Ω), TX_N has 6 vias and TX_P 4, REFCLK and TX run 42–54 mm on B.Cu; 25 high-speed signal vias have no GND return via within 1 mm (PCIe TX/RX/REFCLK near J702 at 2.4–5.0 mm). USB_BT_DM has 6 vias and 19.5 mm on B.Cu, USB_BT_DP none.** Function at Gen1 and USB HS is not in doubt; margin is. | pcbnew per-net layer/via table; `checks/returnpath.py` (re-run, 25 entries over 1 mm); `checks/tline.py` eye estimate 2 % closure. | `max-link-speed = <1>` if Gen2 is unstable; check `lspci` LnkSta/AER. | Coupled pairs, ≤ 2 vias each, a GND via beside every signal via. |
| m3 | Minor | Pair skew | **MDI intra-pair skew 0.64–0.69 mm (25–27 mil) and PCIe RX 0.33 mm (13 mil) against the CM3 rule of < 12 mil.** The module adds up to 28 mil on MDI1 of its own. Electrically harmless at 125 MBd and 5 GT/s respectively. | pcbnew: MDI0 53.41/54.05, MDI1 59.86/59.22, MDI2 68.75/69.44, MDI3 69.73/69.05; PCIE_RX 55.24/55.57; CM3 datasheet MDI table. | None. | Tune the pairs. |
| m4 | Minor | HDMI out 5 V | **AP22804AW5 limits at 2.7–3.3 A (0.45 A only into a dead short), not the 0.5 A HDMI expects of a source.** A faulty sink loads 5V_SYS, which also feeds 3V3_IO and 1V1_628. | AP22804 datasheet (ILIMIT 2.7/3.0/3.3 A, ISHORT 0.45 A). | None for bring-up. | 0.5 A-class switch or polyfuse. |
| m5 | Minor | Input at low battery | **At a 6 V battery and full load (about 15 W in) the input current is 2.5–3 A: F101 holds 3 A (less when warm), J102's JST PH contacts are rated 2 A, and the SS54 OR diode in SMA dissipates about 1.1 W.** At the typical 7 W (1.2 A) all three are fine. | BOM C48985875, C131337, C22452; `checks/irdrop.py` VIN case. | Keep the battery load realistic; the fuse trips, it does not fail. | 4–5 A fuse, XT30/JST VH, ideal-diode OR-ing. |
| m6 | Minor | ADC | **VIN_SENSE has no clamp:** 1.55 V at 17 V, full scale (1.8 V) at 19.8 V, 2.9 V during an SMBJ20CA clamp event (32 V). | `gen/power.py` R103/R104; SMBJ20CA Vc 32.4 V. | None. | BAT54 to SOM_1V8. |
| m7 | Minor | USB-C | **No ESD on CC1/CC2 and no TVS on VBUS_C**; USBLC6 covers D+/D− only (pin 5 correctly floating at 9 V), the SMBJ20CA sits after D103. | Netlist. | None. | 5 V ESD array on CC, 20–24 V TVS on VBUS_C. |
| m8 | Minor | CEC option | **R216 (0 Ω, DNP) would tie the 3.3 V CEC bus to J68-151, the 5 V side of the module's HDMI level shifter.** | CM3 schematic HDMI sheet; `gen/hdmi_in.py`. | Leave R216 unfitted. | CEC_GPIO on a plain 3.3 V GPIO. |
| m9 | Minor | Power layout | **Switch nodes and feeds:** LX_5V/LX_SOM are 0.3 mm × 2.1 mm necks for 3 A; SW_IO changes layer through 3 vias (5 mm on B.Cu); SW_628 has a 0.127 mm neck; 1V1_628 has 0.127 mm B.Cu segments at 0.45 A (101 A/mm²); U106's nearest input capacitor is 3.1 mm from pin 3. | pcbnew widths; `checks/irdrop.py`. | None. | Switch nodes as short F.Cu areas; 0.5 mm 1V1 trunk; 100 nF at U106 pin 3 (move L104 1 mm). |
| m10 | Minor | Fab, via-in-pad | **112 vias sit inside SMD pads on about 70 parts, including two RK628D balls (C3 and J9: a 0.3 mm via in a 0.275 mm pad) and U102's exposed pad.** Acceptable only with the "epoxy filled and capped" option the quote carries; without it expect wicking, thin joints and tombstoned 0402s. `kicad/README.md` "Known compromises" mentions only J501 pins 39/41. | pcbnew pad hit test; `orders/2026-10-25-jlcpcb-5-assembled-quote.md`. | Keep the via option on every re-quote (including the post-B1 one); say so in README. | Fan out beside pads; 0.2 mm drills. |
| m11 | Minor | Power distribution | **5V_SYS is a 0.6 mm trunk about 140 mm long (70–90 mV at 1 A to U105/U106/U401), HDMITX_5V runs on 0.25 mm, and the M.2 3.3 V pins are fed through 0.5 mm copper with 0.1 mm stubs at 0.3 A.** No power pours exist; In2 is a GND pour with signals. | `checks/irdrop.py` (5V_SYS 70–86 mV, 3V3_IO 42 mV at J501); pcbnew widths. | Measure 3V3_IO at J501 under Wi-Fi TX and HDMITX_5V at J401 under load. | 3V3_IO/5V_SYS islands on In2 or ≥ 0.8 mm trunks. |
| m12 | Minor | RK628D off-state | **While RK628D_3V3 is off, the I2C2 bus and CEC have no pull-up (R207/R208/R214 hang on RK628D_3V3), the CM3 can drive RESET_N (GPIO3_C2) high into the unpowered chip, and a connected camera's DDC pull-ups reach RX_SCL/RX_SDA through 22 Ω.** All sub-mA back-feeds, but the sequencing lives in software. | `gen/hdmi_in.py`; netlist. | Raise RK628D_PWR_EN early in boot, keep RESET_N low until then, keep PWR_EN on while a camera is attached. | I2C2 pull-ups from 3V3_IO; DDC/CEC clamps that tolerate the off state. |
| m13 | Minor | Module mechanics | **The 1.5 mm M2.5 spacers that the 1.5 mm DF40 stack needs are in no parts list** (PRODUCTION station 3, `orders/2026-10-25-dev-parts.md`); screwing the module down without them crushes the connectors. The dev order has 14 × 14 × 7 mm heatsinks while the case model and PRODUCTION assume 30 × 30 × 6 mm. H501 is 28.0 mm from J501's centre (24.2 mm from the pad rows), which fits a 2230 card if its notch is centred on the far edge, but the TE 2199230-4 hold-down dimension was not available to confirm it. | CM3 datasheet §2.7 ("standoffs must match the connector height"); `case/case.py` extra[] block; `orders/…dev-parts.md`; pcbnew. | Add four 1.5 mm M2.5 spacers to the kit; check H501 with a card on a 1:1 print. | Document in PRODUCTION; confirm H501 from the TE drawing. |
| m14 | Minor | Docs | **Stale or inconsistent text:** REV_A_SPEC §6 "about 90 × 65 mm" (120 × 100), "L3 power" (In2 is GND plus signals), "all SMD on the top side" (62 bottom parts), §3 "47 µF aluminium polymer" (RVT35V47M6X8 is a plain electrolytic), §4 HDMI "LCSC C2902698" (BOM is Molex C916313), §3/§7 "locking DC jack" (PJ-002AH is not locking); PRODUCTION "3 assembled prototypes, ordered Oct 24" against the order note "not ordered, 5 all assembled"; the Mouser CSV orders a 5.5 × 2.1 mm supply plug for a 2.0 mm-pin jack (the dev-parts note itself says it fits loosely); BOM comments list J702/J703 under "CM3 J69"/`Radxa_CM3_J69`, SW602 under "RESET", J401 under "HDMI IN" (harmless to JLCPCB). | Files named. | Update before the pilot. | — |
| n1 | Note | Impedance | My closed-form estimate on the 3313 stack (h 0.0994 mm, Er 4.1, 35 µm copper, mask): 0.10/0.10 → 100–105 Ω, 0.12/0.10 → 93–97 Ω, 0.14/0.10 → 87–90 Ω. Within ±10 % of target. `checks/zsolve.py` cannot run here (no scipy). Put the three geometries in the order remark so JLCPCB flags a mismatch. | Hammerstad/Jansen; `fab/FAB_NOTES.txt`. | — | Route to JLCPCB's calculator widths. |
| n2 | Note | CM3 power | DF40 contacts are 0.3 A each: six +5V pins give 1.8 A sustained, not 3 A. Radxa's design; REV_A_SPEC says so. | LCSC C597931. | Keep sustained draw ≤ 1.8 A. | — |
| n3 | Note | JLCPCB limits | 0.09 mm inner tracks (RK628D_3V3, RX_CEC), 0.1 mm outer tracks/clearance, 0.15 mm drills, 0.3 mm vias (0.075 mm ring), 0.3 mm copper-to-edge; closest different-net hole edges 0.278 mm (GND via vs DEBUG_TX via at (69.08, 67.57)); 71 same-net and 136 different-net hole pairs closer than 0.5 mm. All inside JLCPCB's published 4-layer numbers but with no margin. | pcbnew hole scan; `relay.kicad_pro`. | — | 0.1 mm / 0.3 mm margins. |
| n4 | Note | Panel | JLCPCB adds its 5 mm rails on the 100 mm edges (panel 120 × 110), which are the edges where the HDMI shells overhang by 1.07 mm (board y −1.07) and the hand-fitted magjack will later overhang by 5.2 mm. The HDMI lip resting on the rail is harmless, but ask for rails on the 120 mm edges if they offer the choice. | pcbnew J201/J401 F.Fab extents; order note. | Order remark. | — |
| n5 | Note | RK628D footprint | Generated BGA pads are 0.275 mm round for a 0.65 mm pitch, below the usual 0.3 mm NSMD but above JLCPCB's 0.25 mm minimum; 49 dogbone vias plus the two in-pad vias (m10). | `relay.pretty/BGA-144…kicad_mod`. | — | 0.30 mm pads. |
| n6 | Note | PCIe AC coupling | After B1 is fixed the host TX path has only the module's C54/C55 (C501/C502 are 0 Ω): correct. The host RX path has the module's C57/C58 in series with the card's own capacitors (about 50 nF): Radxa's design, as on their IO board. | CM3 V1.322 schematic lines 808–813. | None. | — |
| n7 | Note | USB OTG | VBUSDET tied high (10 kΩ to SOM_3V3): the module always sees a host, which is what flashing and the gadget need. No common-mode choke or 2.2 Ω series parts on OTG (CM3 datasheet §3.2.1). USB_OTG0_ID and USB_5V_IN correctly open. | Netlist; CM3 datasheet. | — | 0 Ω/CMC pads. |
| n8 | Note | Supply | Stock was not re-checked here (no network use). Earlier reports: RK628D 27 pcs at JLCPCB, magjack none (hand-fit from Mouser), L101/L102 146 pcs. | REVIEW_FABLE_2/3. | Order promptly after B1. | Second-source the RK628D. |
| n9 | Note | CM3 connectors | Radxa's J68 has four extra GND pads (201–204) that `Radxa_CM3_J68` lacks; the DF40C-100DS-0.4V(51) receptacle has no fitting nails, so they are presumed board-specific. Still unexplained. | `checks/b2bfit.py`. | — | Find out what they are. |
| n10 | Note | CH224A PG | R102 pulls the CH224A's PG to VBUS_C (up to 9 V) when released. PG is a high-voltage open drain rated 32 V on the CH224A (it would be VDD+0.5 V on a CH224K): correct for the A, and the BOM part is the A. | CH224 manual §8.1.1 "VIOHV (PG, VBUS) 32 V"; lcsc-mpn.json C42459160 = CH224A. | — | — |

## What was verified as correct, and how

**CM3 pin map (every pin).** `gen/cm3_pinout.json` was compared line by line with the datasheet appendix C tables and the
V1.31/V1.32 change history (xlsx): J69-37 → 4G_DISABLE (GPIO4_C5, UART9_TX_M1), J69-93 → SARADC_VIN0, J1-14 → SARADC_VIN3,
J1-26 → NC, J1-34 → PCIE_PWREN_H (GPIO0_D3); CSI D2/D3 on 128/130/134/136. All 54 assignments in `gen/module.py` land
on the intended functions: MDI0–3 (J69 12/10, 4/6, 11/9, 3/5), CSI D0–D3 and CLK0 (J68 117/115, 123/121, 130/128,
136/134, 129/127), PCIe TX/RX/REFCLK (122/124, 116/118, 110/112), CLKREQn/PERSTn/WAKEn all in the M2 group (J68-102,
J68-109, J1-38), USB_OTG0 (105/103), USB2_HOST2 (J1 63/65), HDMI TX pairs (170/172, 176/178, 182/184, 188/190),
HPD 153, DDC 199/200, CEC on GPIO4_D1 (151), I2C2_M1 (35/36), I2C4_M0 (38/44), UART2_M0 (51/55), UART9_M1
(J69-37/J1-36), CIF D0–D15/HREF/VSYNC/CLKIN, PMIC_RESET_KEY 100, VBUSDET J1-97, 5 V × 6, +3V3 × 2 + GPIO_VREF, +1V8 × 2.
The generator asserts no pin is used twice; the remaining pins are GND or no-connect, all allowed open (PWRON_KEY:
the RK817 auto-powers on +5V_INPUT, datasheet §3.1.2; USB_5V_IN must not be driven with +5V_INPUT, §3.1.1 warning).
`checks/b2bfit.py` re-run: 300/300 pins coincide with Radxa's IO board at 0.0000 mm, mirror rejected.

**I/O bank map, derived from the CM3 V1.322 schematic p.7 and the per-domain pages:** PMUIO1 = GPIO0_A0–A7 (VCC3V3_PMU,
"3.3V Only"), PMUIO2 = GPIO0_B0–D2 (VCCA1V8_PMU), OSC = GPIO0_D3–D6 ("1.8V Only"), VCCIO1 = GPIO1_A0–B3 (VCCIO_ACODEC,
software), VCCIO5 = GPIO3_A1–C5 (R43 0 Ω to VCC_3V3), VCCIO6 = GPIO3_C6–GPIO4_C1 (GPIO_VREF via R24, tied to +3V3 here),
VCCIO7 = GPIO4_C2–D1 (VCC_3V3). Against it: INT GPIO3_C3 and RESET_N GPIO3_C2 (VCCIO5), I2C2 GPIO4_B4/B5 and LED_STATUS
GPIO4_B1 (VCCIO6), LED_WIFI GPIO0_A5, PLUGIN_DET GPIO0_A4 and WIFI_DISABLE GPIO0_A0 (PMUIO1), CEC_GPIO GPIO4_D1 and
SDI UART GPIO4_C5/C6 (VCCIO7), DVP/SDI GPIO3_C6–GPIO4_C1 (VCCIO6), SDI GPIO5–7 GPIO3_A1/B4/C1 (VCCIO5); 1.8 V by design:
PWR_EN GPIO0_C4 into an NPN base through 1 kΩ, the debug UART GPIO0_D0/D1. BT_DISABLE/PERST/CLKREQ/WAKE are in VCCIO1
(needs the DT). `checks/iolevels.py` re-run: 0 flagged, and its `bank()` agrees with this derivation. The module-side
circuits that touch our nets were read from the schematic: Q4/R170/R171 (TF_DET → SDMMC0_DET_L), R9/R10 2.2 kΩ to 1.8 V
on GPIO0_B5/B6 (unused here), WIFI_PWREN GPIO0_A0 default pull-down.

**RK628D.** All 144 balls in `gen/hdmi_in.py` against datasheet table 2-1 (every connected ball by name: HDMIRX pairs
L12/L11, K12/K11, J12/J11, H12/H11; HPD K8, SCL L8, SDA M8, CEC K9; EXTR G9/M3; REXT B1; OSC M9/L9; RESETN H4; TEST D7;
I2C_ADDR C7; I2C L3/K3; INT J3; CSI TX0–TX4 on G/F/E/D/C 1–2; supplies as table 2-2). Straps (table 2-3): I2C_ADDR
10 kΩ to GND plus internal pull-down → 0x50 (the DT uses 0x50); TEST to GND; INT/SPIBOOT internal pull-down onto a CM3
pin that resets pulled down → normal boot; RESETN internal pull-up with C202; EFUSE_VDD_2V5 held at 0 V through 100 Ω
as in DshanPi p.31. Supplies 1.1 V and 3.3 V only with ferrite-split analog rails, 4.02 kΩ MIPI_REXT and 2 kΩ EXTRs as
DshanPi (R233 4.02K, R236/R243 2K). Crystal X322524MOB4SI (C70590) is a 12 pF part; 18 pF + 18 pF with about 3 pF
stray gives 12 pF. CSI lane order TX0/1/2/3/4 = D0/D1/CLK/D2/D3, P to P into J68 117/123/129/130/136. Decoupling:
AVDD_1V1 9 × 100 nF + 2 × 1 µF + 10 µF, AVDD_3V3 6 × 100 nF + 1 µF + 10 µF, DVDD 2 × 100 nF + 10 µF, VCCIO 3 × 100 nF +
1 µF + 10 µF, on the back under the chip with fanout vias. Power gate: AO3401A with 10 kΩ gate pull-up, NPN from
GPIO0_C4 through 1 kΩ with 100 kΩ pull-down (off at boot); 1V1 enable follows RK628D_3V3 through 10 kΩ/100 nF.

**Power tree.** SY8303: 0.6 × (1 + 110/15) = 5.00 V; RFS 200 kΩ = 0.5 MHz (datasheet table); BS 10 nF (datasheet
value); EN 100k/39k turns on at VIN ≤ 5.35 V (VENH ≤ 1.5 V), EN/FS/FB abs max 40 V, UVLO 4.35 V; 2 × 4.7 µF/50 V in plus
47 µF/35 V bulk; 2 × 22 µF/25 V out (about 25–35 µF after bias, above the 22 µF minimum); 6.8 µH at 500 kHz gives
about 1 A pk-pk ripple at 17 V, peak 3.5 A against the SRN6045TA-6R8M's 3.6 A rating at the 3 A corner (fine at the
documented 2 A). TPS563201: 0.768 × 4.3 = 3.30 V and 0.768 × 1.431 = 1.10 V; EN threshold 1.6 V max with the internal
225–900 kΩ pull-down, so 100k/100n from 5V_SYS settles at ≥ 3.4 V and 10k/100n from RK628D_3V3 at 3.2 V; VIN 4.5–17 V
met by 5V_SYS; 2.2 µH / 1.5 µH per the datasheet table, 10 µF + 100 nF in, 2 × 22 µF out; inductors 4.6/4.95 A.
CH224A: VHV (pin 1) and VBUS (pin 8) both on VBUS_C (manual: VBUS shorted to VHV on the A), 1 µF/50 V, CFG1 6.8 kΩ =
9 V, PG open-drain (32 V rated) into Q101's gate with 100 kΩ to VBUS_C; AO3401A VGS −9 V within ±12 V; D103 blocks any
back-feed into the port; a 5 V-only source leaves Q101 off, as the spec intends. AP22804AW5-7: active-high EN tied to
IN. Input: SS54 × 3 OR-ing (40 V/5 A), SMBJ20CA on VIN (17 V max), 3 A PTC (30 V), VIN_SENSE 100k/10k = VIN/11.
`checks/irdrop.py` re-run: 5V_SOM 8 mV at 3 A on 1.2 mm copper; VIN 23 mV at 2.8 A on 0.8–1.6 mm; 5V_SYS 70–86 mV at
1 A; 3V3_IO 42 mV at 0.6 A at the M.2. Every MLCC voltage rating is above its rail (25 V parts on 5 V, 50 V on 9 V and
VIN).

**Connectors and ESD.** HDMI J201/J401: pins 1–19 in standard order into the Molex 208658-1001 footprint, which is the
BOM part (C916313); D2/D1 and D0/CLK pairs flow through D201/D202 and D401/D402; DDC/HPD/CEC through D203/D403.
**Pass-through links re-verified independently:** with all six RClamp footprints removed and each pad replaced by a
bare copper patch of its own size, `kicad-cli pcb drc` reports 0 unconnected items, so every HDMI line is continuous
through board copper and never depends on the clone's NC pins. HDMI IN: HPD from the RK628D through 22 Ω, DDC 47 kΩ to
the source's 5 V through MBR0530, CEC 27 kΩ through MBR0530, 22 Ω series, 5 V detect 2k/10k NPN into GPIO0_A4 with
10 kΩ to 3V3_IO, all as DshanPi p.32. HDMI OUT: HPD straight to J68-153, DDC 2.2 kΩ to HDMITX_5V (the module
level-shifts both), 5 V from U401. Ethernet: MDI0–3 → J301 MX1–MX4 (pads 11/10, 4/5, 3/2, 8/9; centre taps 12, 6, 1, 7
through 1 µF to GND, as the CM3 datasheet §3.4 requires for the voltage-mode RTL8211F) → RJ45 1/2, 3/6, 4/5, 7/8;
C3179417 is the Pulse part the footprint is drawn for. M.2 E-key: GND 1/7/18/33/39/45/51/57/63/69/75, 3.3 V 2/4/72/74,
USB 3/5 (D+ → HOST2_DP, D− → HOST2_DM), REFCLK 47/49, PERST# 52, CLKREQ# 53, W_DISABLE2# 54, PEWAKE# 55, W_DISABLE1# 56,
TE 2199230-4 footprint (C2977809), 2 × 22 µF + 2 × 100 nF at the socket; only the PET/PER pairs are wrong (B1). USB-C:
HRO TYPE-C-31-M-12 with its own footprint, CC1/CC2 to the CH224A only, D+/D− both rows through USBLC6 (1→6, 3→4) to
USB_OTG0, SBU open, shell to GND. DC jack: KiCad `BarrelJack_Horizontal` pads (0,0)/(−6,0)/(−3,4.7) match the PJ-002A
layout (1 = centre pin, 2 = sleeve, 3 = switch, open); placed at 90° with pin 1 at (42.0, 85.55), body to y 99.30,
so the mouth is 0.7 mm inside the rear edge, facing out, under the case's DC opening at x 42. Buttons: RESET to
PMIC_RESET_KEY, RECOVERY to SARADC_VIN0 (J69-93 on V1.32) with 10 kΩ to SOM_1V8 and 1 nF. Debug header TX/RX/GND at
1.8 V (value says so). LEDs 150 Ω from 3.3 V banks (about 3–4 mA), PWR 2.2 kΩ from 3V3_IO.

**Device tree overlay against the schematic.** Every GPIO in the overlay matches `gen/module.py` and the bank map:
PERST# GPIO1_B2, CLKREQ# GPIO1_B0 and WAKE# GPIO1_B1 as function 4 (PCIE20_*_M2 per the CM3 appendix C columns),
BT_DISABLE# GPIO1_A4, WIFI_DISABLE# GPIO0_A0, RESET_N GPIO3_C2 active low, INT GPIO3_C3 (reset-state pull-down kept, so
the SPIBOOT strap stays low), PWR_EN GPIO0_C4 active high, PLUGIN_DET GPIO0_A4 active low, LEDs GPIO4_B1/GPIO0_A5 active
high, I2C2 on `i2c2m1_xfer` at 0x50, vccio1 = vccio_acodec at 3.3 V always-on, TF_DET (GPIO0_D4) hogged low, rfkill
`shutdown-gpios` active low (W_DISABLE# low = off), pcie2x1 `reset-gpios` active high in the upstream sense. What is
missing is in M1.

**Layout.** DRC `--schematic-parity --severity-all`: 0 violations, 0 unconnected, 0 parity (no exclusions; the five
ignored checks are footprint-library cosmetics, missing_courtyard, track_not_centered_on_via and tuning profiles).
ERC 0. `routed.kicad_pcb` holds exactly the same 4414 tracks and vias and the same footprint placement as
`relay.kicad_pcb`; only the four GND zones differ, as intended. 120.1 × 100.1 mm, 4 layers, GND zones on all four.
1047 vias (614 × 0.25/0.45, 386 × 0.15/0.3, 47 × 0.3/0.6), matching the PTH drill tools T1–T3 hit for hit. No
top-side part inside the module outline (x 38.45–93.55, y 29.95–70.05); the 1.5 mm stack allows none. CSI, HDMI IN
and HDMI OUT pairs are on F.Cu over the solid In1 (In1 carries only short segments under U201); HDMI IN pair-to-pair
spread 6.45 mm and HDMI OUT clock-to-data with the module's lengths about 8 mm, both under 480 mil; P/N matched to
0.00–0.18 mm. CSI D2/D3 B.Cu stretches have a GND via within 0.7–1.0 mm of each signal via. The six U103/U104
thermal vias, the C501/C502 0 Ω links, the ESD links, the jack move and the CSI meanders are all present in the board
and in the Gerbers. RK628D decoupling and fanout as described above. Courtyards: 0 overlaps; silk: 0 overlaps and
0 silk-over-copper at warning severity.

**Fab files.** BOM 59 lines, every line with an LCSC number, each resolved by `gen/lcsc-mpn.json` to the intended MPN
and package (DF40C-100DS-0.4V(51), RK628D WBBGA-144, CH224A ESSOP-10, SY8303AIC TSOT-23-8, TPS563201DDCR, AP22804AW5-7,
RCLAMP0524P DFN2510-10, Molex 2086581001, TE 2199230-4, PJ-002AH, JK0654219NL, TYPE-C-31-M-12, X322524MOB4SI 12 pF,
1812L300/30GR, TL3342F160QG, SS54, SMBJ20CA, MBR0530T1G, SRN6045TA-6R8M, SWPA6045S2R2NT/1R5NT). Schematic ↔ BOM ↔ CPL:
191 components; 176 in both BOM and CPL; the 7 DNP parts (R202, R216, R501–R503, R505, J602) in neither; the 15 others
are mounting holes, test points and fiducials. CPL positions equal the board positions for every part (J701–J703
re-centred on their pad fields, 0°/0°/90°), layers agree, Y is page-up as the Gerbers are. Gerber zip: 16 files, 4 copper,
mask, paste, silk, outline (closed, 120 × 100 mm), PTH/NPTH drills. Drill tools account for every hole: 0.15/0.25/0.3
vias, 0.4 and 0.5 mounting-hole vias, 0.65 USB-C pegs, 0.75 J102, 0.8 × 40 J602, 0.89 × 12 and 1.025 × 4 and 1.57 × 2
and 3.2 × 2 J301, 1.0 J101/J601, 2.2 H501, 2.6 × 4 CM3, 3.2 × 4 M3. Job file: 0.0994 / 1.265 / 0.0994 mm dielectrics,
3313, ENIG, ImpedanceControlled; `gen/fab.py` refuses any other stackup. PCBWay BOM carries the same 60 lines with MPNs.

**Case (2D).** Openings at board x 24 and 79 (HDMI, faces 1.07 mm past the front edge), 16 (USB-C, face 0.5 mm inside),
42 (DC, mouth 0.7 mm inside), 99 (RJ45 body centre 98.9, face 5.2 mm past the edge); M3 holes (4,4), (4,96), (116,36),
(116,68) = H601/H603/H602/H604; light pipes over D601 (97.72, 18.47) STATUS, D602 (101.18, 18.47) WIFI, D603
(115.70, 11.98) PWR in the right order; pinholes over SW601/SW602; roof vents over the module and over U103/U104;
battery-lead hole at x 58 over J102. The faults are in M2 and m13.

## What could not be verified

- **JLCPCB's model orientation for every polarised part (M4):** only their placement viewer shows it, and the CPL
  will be regenerated after B1.
- **The 2-D impedance solve (`checks/zsolve.py`)**: no scipy in either Python here; my closed-form figures (n1) are
  within 10 % of the project's 92.6 Ω.
- **The M.2 2230 hold-down position (H501 at 28.0 mm from J501's centre)** against the TE 2199230-4 drawing (m13).
- **The RK3566 D-PHY receiver's skew tolerance and the RK628D's lane-rate options (m1); the RK628D 1.1 V current and
  power-up order** (no Rockchip design guide in the repo; the scheme copies DshanPi).
- **Whether Radxa's stock device tree already powers VCCIO_ACODEC at 3.3 V and which nodes own GPIO0_A0/A4/A5/D3**
  (M1): the BSP tree is not in the repo and the overlay was not compiled.
- **Part stock and lifecycle** (no network lookups made here).
- **Real heights in the case** (module plus heatsink, Wi-Fi card shield, USB-C and M.2 sockets are blocks) and the
  CadQuery clash check (not re-run).
- **The DF40 pads 201–204 on Radxa's J68** (n9).

## Status of every finding in the five earlier reports

Legend: **fixed** = fixed and confirmed correct in the current files; **accepted** = not changed, documented workaround
or owner decision; **open** = not fixed and not explicitly accepted; **disputed** = the earlier finding or its
verification is wrong.

**TEST_REPORT.md (Oct 24/25)**

| Item | Status |
|---|---|
| Fix 1: RK628D lines off 1.8 V pins (SCL → J69-35, RESET_N, PLUGIN_DET → J69-76) | fixed (RESET_N completed by the Oct 25 move to GPIO3_C2) |
| Fix 2: VIN neck into U104 | fixed (0.8–1.6 mm, `irdrop.py` 23 mV at 2.8 A) |
| Fix 3: fiducials | fixed (3 + 3, out of BOM/CPL) |
| "I/O level audit: clean" (Oct 24) | disputed by REVIEW_INDEPENDENT, since corrected; `iolevels.py` now 0 flagged with the right bank map |
| Magjack stock | accepted (hand-fit from Mouser) |
| DC plug 2.0 vs 2.1 mm | open: the Mouser CSV still orders a 2.1 mm-plug supply (m14) |
| Item 4: U106 input cap | accepted (m9) |
| Item 5: via-in-pad | accepted via the filled-and-capped order option (m10; README understates the count) |
| Item 6: uncoupled PCIe TX / USB | accepted (m2) |
| "Ready to order" (Oct 24) | disputed then and now; see B1 |
| M.2 pin-level check listed as "not done" | correct: it was never done, and the pin map is wrong (B1) |

**REVIEW_INDEPENDENT.md (Oct 25)**

| ID | Status |
|---|---|
| M1 RK628D_INT on 1.8 V pin | fixed (GPIO3_C3, VCCIO5) |
| M2 LEDs on 1.8 V pins | fixed (GPIO4_B1 / GPIO0_A5, 150 Ω) |
| M3 PD_PG_N held Q101 on | fixed (PG drives Q101 only; net is sheet-local) |
| M4 USB-only flashing | accepted (PRODUCTION station 4: 12 V plus USB-C) |
| M5 BT_DISABLE_N on 1.8 V pin | fixed (GPIO1_A4; R505 DNP; DT dependency in M1 here) |
| M6 CSI skew incl. module | mostly fixed (24 → 6.3 mm), residual accepted (m1) |
| M7 AP22804 limit | accepted (m4) |
| M8 RESET_N on 1.8 V pin | fixed (GPIO3_C2) |
| M9 LX necks / SW_IO vias | accepted (m9) |
| M10 F101 / J102 ratings | accepted (m5) |
| M11 uncoupled pairs, asymmetric vias | accepted (m2) |
| M12 VCCIO1 pull-ups / PERST# | fixed for the pull-ups (R501–R503, R505 DNP) with the DT part written; DT incomplete (M1) |
| M13 TF_DET drives PLUGIN_DET | fixed in the DT (gpio-hog) |
| N1 1.8 V debug UART | accepted (value and docs; no silk) |
| N2 DF40 1.8 A | accepted (n2) |
| N3 stock | open (n8) |
| N4 I2C4_SDA pin ambiguity | open note (we use J69-44, which matches the mux) |
| N5 docs | open: most items still in REV_A_SPEC (m14) |
| N6 USBLC6 pin 5 | accepted |
| N7 W2 dev modules | note, no action |
| "Verified: PET 35/37 to the SoC's RX; PER 41/43 from the SoC's TX" | **disputed: that is the swap (B1)** |

**REVIEW_FABLE.md (Oct 25)**

| ID | Status |
|---|---|
| B1 DDC through NC pins | fixed; re-verified by connectivity with the arrays replaced by bare pads |
| M1 double PCIe TX AC caps | fixed (C501/C502 0 Ω); the pair they sit in is on the wrong pins (B1) |
| M2 CSI skew | mostly fixed, residual accepted (m1) |
| M3 U104 thermal | accepted with thermal vias and a current cap (M3) |
| M4 stackup absent from fab files | fixed (board stackup, job file, `fab.py` guard, FAB_NOTES) |
| m1 uncoupled pairs | accepted (m2) |
| m2 3V3_IO / 5V_SYS widths | accepted (m11; M.2 feed now 0.5 mm) |
| m3 CC ESD / VBUS TVS | accepted (m7) |
| m4 AP22804 | accepted (m4) |
| m5 fuse / JST | accepted (m5) |
| m6 switch nodes | accepted (m9) |
| m7 CEC option into 5 V node | accepted (m8, R216 DNP) |
| m8 via-in-pad | accepted via order option (m10) |
| m9 CPL rotations / job stackup | stackup fixed; rotations checked by eye, must be repeated (M4) |
| m10 HDMI IN SCL unprotected | fixed by the links |
| m11 VIN_SENSE clamp | accepted (m6) |
| n1 module pairs unmatched internally | note |
| n2 DF40 current | note (n2) |
| n3 DT list | partly done: overlay exists but sdmmc0/regulators not disabled (M1) |
| n4 GPIO0_A0 = WIFI_PWREN on W2 modules | note (also M1) |
| n5 M.2 standoff | open (m13) |
| n6 clone ESD capacitance | note |
| n7 case 2D positions | confirmed; its 3D faults are M2 |
| n8 U106 input cap | accepted (m9) |
| n9 stock | open (n8) |
| n10 docs | open (m14) |
| n11 RK628D sequencing | unverifiable, copies DshanPi |
| "Verified: PET 35/37 → PCIE_RX, PER 41/43 ← PCIE_TX" | **disputed (B1)** |

**REVIEW_FABLE_2.md (Oct 25)**

| ID | Status |
|---|---|
| B1 DC jack facing inward | fixed (mouth at y 99.30, facing the rear edge, under the case opening) |
| M1 CSI skew | fixed to 6.3 mm (m1) |
| M2 U104 thermal | accepted (M3); case vent present |
| M3 VCCIO1 sideband | fixed for the pull-ups; DT written but incomplete (M1) |
| M4 CPL rotations | checked by eye (claimed); must be repeated after B1 (M4) |
| M5 parts availability | L103/L104 fixed (NT parts in BOM); RK628D/magjack open (n8) |
| m1 PCIe TX/REFCLK uncoupled, return vias | accepted (m2) |
| m2 USB_BT asymmetry | accepted (m2) |
| m3 fuse / JST | accepted (m5) |
| m4 AP22804, HDMITX_5V width | accepted (m4, m11) |
| m5 5V_SYS feed to U106 | fixed in part (5V_SYS to U401/J602 now 0.6 mm); U106 cap accepted (m9) |
| m6 3V3_IO distribution | accepted (m11) |
| m7 CC ESD | accepted (m7) |
| m8 VIN_SENSE clamp | accepted (m6) |
| m9 CEC option | accepted (m8) |
| m10 HPD at 3.3 V | accepted (test with target cameras) |
| m11 ESD land pattern / D403 pad 7 | accepted |
| m12 clone ESD rating | note |
| m13 pull-ups off with RK628D off | open, software (m12) |
| m14 case details (USB-C notch, ¼"-20 depth, spacers, posts, lid boss, screw length) | **open: USB-C notch and insert depth confirmed (M2); spacers (m13); README says M3 × 10 and PRODUCTION M3 × 6 (m14)** |
| n1 Gerbers equal a fresh export | confirmed again (drill tools and via counts match) |
| n2 J68 pads 201–204 | open (n9) |
| n3 module keep-out | confirmed |
| n4 RX double AC caps | note (n6) |
| n5 via-in-pad | accepted (m10) |
| n6 JLCPCB limits | confirmed (n3) |
| n7 VBUSDET / OTG | note (n7) |
| n8 module pull-ups | handled in the DT except the sdmmc0 ownership (M1) |
| n9 UART silk | open, cosmetic |
| n10 crystal / straps | confirmed |
| n11 regulators | confirmed |
| n12 docs | open (m14) |
| "Verified: PET 35/37 → PCIE_RX, PER 41/43 ← PCIE_TX" | **disputed (B1)** |

**REVIEW_FABLE_3.md (Oct 25)**

| ID | Status |
|---|---|
| M1 CPL rotations not self-consistent | closed by a viewer check on Y6; void after B1, repeat (M4) |
| M2 U104 thermal | accepted with the 1.5–2 A cap and current log (M3) |
| M3 DT dependency | overlay written; incomplete (M1) |
| m1 CSI residual 6.3 mm | accepted (m1) |
| m2 impedance depends on mask model / order remark | accepted; my estimate agrees (n1) |
| m3 PCIe/USB layout | accepted (m2) |
| m4 MDI intra-pair skew | accepted (m3) |
| m5 AP22804 | accepted (m4) |
| m6 fuse / JST | accepted (m5) |
| m7 switch nodes / 1V1 segments / U106 cap | accepted (m9) |
| m8 CC ESD | accepted (m7) |
| m9 VIN_SENSE clamp | accepted (m6) |
| m10 CEC option | accepted (m8) |
| m11 roof labels swapped | fixed (LIGHTPIPES order STATUS, WIFI, PWR = D601, D602, D603) |
| m12 RFS 210k / inductor value | fixed (R105/R108 200k, C25764; value "6.8uH 3.6A") |
| m13 HPD at 3.3 V | accepted |
| m14 stock | open (n8) |
| n1 Gerbers current | confirmed |
| n2 via-in-pad count | confirmed (112 by my count) (m10) |
| n3 hole-to-hole 0.278 mm | confirmed (n3) |
| n4 CM3 connector CPL symmetry | accepted; still in the viewer check (M4) |
| n5 1.5 mm standoffs "in the kit" | open: not in any parts list (m13) |
| n6 magjack geometry | confirmed from the footprint |
| n7 VBUSDET | note (n7) |
| n8 RK628D straps | confirmed |
| n9 BOM comment cosmetics | open, harmless (m14) |
| n10 docs | open (m14) |
| n11 ESD links | confirmed (connectivity test) |
| n12 scipy for zsolve | still missing |
| "Verified: PET 35/37 → PCIE_RX, PER 41/43 ← PCIE_TX" | **disputed (B1)** |

## Software and device-tree requirements the hardware imposes (unchanged list, with M1 added)

- `vccio_acodec` 3.3 V boot-on/always-on, `pmu_io_domains` vccio1-supply; pinctrl pull-ups on GPIO1_B0/B1; PERST#
  GPIO1_B2; BT enable GPIO1_A4 high; Wi-Fi enable GPIO0_A0 high (overlay has these).
- Disable `sdmmc0` and the base-tree nodes that drive GPIO0_A5, GPIO0_D4, GPIO3_C2, GPIO3_C6/C7, GPIO4_A4/B7 (done,
  see the status above).
- Keep GPIO0_D4 low (overlay has the hog).
- RK628D on i2c2 (`i2c2m1_xfer`) at 0x50; reset GPIO3_C2, interrupt GPIO3_C3, power enable GPIO0_C4 raised early and
  kept on while a camera is attached, plug detect GPIO0_A4; CSI 4-lane on CLK0 at ≤ 1.2 Gb/s.
- PCIe: after B1, pcie2x1 with `max-link-speed = <1>` in reserve.
- UART2_M0 console at 1.8 V; USB OTG0 peripheral; SARADC_VIN0 recovery; SARADC_VIN3 = VIN/11 (full scale 19.8 V).
- Flash with 12 V on the DC jack plus USB-C for data.
