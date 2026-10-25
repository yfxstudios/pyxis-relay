# Rev A: design verification and simulation (Oct 24)

Board after the Oct 24 verification fixes (first pass ran on `7fbea6e`). Everything here is analysis and simulation; nothing was built.
Raw outputs are in `analysis/2026-10-24_1342/` (first pass) and `analysis/2026-10-24_fix/` (after the fixes), not committed; the helper scripts are in `checks/`.

## Verdict

**Ready to order, with the remaining items below accepted for rev A.** The first pass of this report found three
RK628D control lines on 1.8 V CM3 pins. Those are fixed, and so are the VIN neck and the missing fiducials. After
the fixes, every check below was run again:
- **KiCad DRC with schematic parity:** 0 violations, 0 unconnected, 0 parity issues.
- **ERC:** 0.
- **SPICE:** 39 pass, 0 fail.
- **I/O level audit:** clean.

## Fixed after the first pass

**1. I/O levels: 3.3 V RK628D lines were on 1.8 V CM3 pins.**

The RK628D runs its I/O at 3.3 V; the CM3's PMUIO2 bank (GPIO0_B0–C7) is 1.8 V. Evidence for 1.8 V:
- the CM3 schematic feeds PMUIO2 from VCCA1V8_PMU;
- the CM3 datasheet's I2C table lists GPIO0_B3–B6 as "1.8V";
- the bank boundaries come from the RK3568 datasheet, section 2.8.

| Net | Was | Now |
|---|---|---|
| I2C_628_SCL | J69 28, GPIO0_C6 (1.8 V), with a 3.3 V pull-up | **J69 35**, GPIO4_B5. Hardware I2C2_M1 with SDA on 36 (VCCIO6 = GPIO_VREF = 3.3 V), so i2c-gpio is no longer needed |
| RK628D_RESET_N | J69 48, GPIO0_B7 (1.8 V) | **J1 20**, GPIO0_D6 (oscillator/PMUIO1, 3.3 V), beside INT |
| RK628D_PLUGIN_DET | J69 50, GPIO0_C7 (1.8 V), with a 3.3 V pull-up | **J69 76**, GPIO0_A4 (PMUIO1, 3.3 V), SDMMC0_DET, an input |

Notes on the moves:
- **RESET_N:** went to J1 20 because J69 75 and J69 31 are boxed in on every layer.
- **SCL:** reaching pin 35 meant re-routing a short SDI_I2C_SDA link under J701.
- **Audit:** `checks/iolevels.py` now reports no 3.3 V source on any 1.8 V CM3 pin. The HDMI TX DDC
  pins (J68 199/200) are 5 V-tolerant per the CM3 datasheet.

**Device tree impact:**
- The RK628D now sits on `i2c2` with pinctrl `i2c2m1_xfer`.
- Its reset GPIO is GPIO0_D6, and plug-detect is GPIO0_A4 (active low, needs a pull-up).

**2. VIN neck into U104.**
- **Before:** a 0.3 mm × 1.8 mm neck at 267 A/mm² (6 V battery, CM3 at 3 A).
- **Now:** a 0.8 mm path from U104 pin 5 straight to C109, down the channel between pin 4 and C109's GND pad, at
  100 A/mm². The trunk from F101 is 1.6 mm, then 1.0 mm.
- **Drop:** VIN at U104 now drops 23 mV instead of 38 mV.

**3. Fiducials.** `gen/fiducials.py` places three on each side, at least 3.5 mm from the edge:
- **Footprint:** KiCad Fiducial_1mm_Mask2mm, 0.5 mm clear of the pour.
- **Attributes:** board-only, out of the BOM and CPL. BOM and CPL both still list 180 parts.

## Footprint and pin checks against datasheets (second pass)

| Part | What was checked | Result |
|---|---|---|
| CM3 connectors J701/J702/J703 | Every pin's position and number against Radxa's own CM3 IO board PCB (`datasheets/radxa_cm3_io_board_b2b_connector_20230718.asc`), one best fit over all 300 pins (`checks/b2bfit.py`). Ground and supply pins against the IO board's nets | **Exact**: 0.0000 mm on every pin. A mirrored footprint would miss by 19.7 mm on average. All 76 GND pins and the 5 V / 3.3 V / 1.8 V pins match |
| RK628D (U201) | All 144 balls' functions against datasheet section 2.4. Footprint grid, A1 position and orientation against Fig. 2-2 / 2-6 | **Match**. Ball J3 (INT) doubles as the SPIBOOT strap, reset-state pull-down. The CM3 pin on it also defaults to pull-down, so it boots in the normal mode |
| CH224A (U102) | Pin table and eSSOP10 package (WCH datasheet sections 4 and 9) | **Match** |
| USBLC6-2SC6 (U101) | Pinout and ratings (UMW datasheet: V_RWM 5 V, V_BR 6–9 V) | Pinout matches. **Fixed:** pin 5 (VBUS) was on VBUS_C, which carries 9 V once PD negotiates. That is above the clamp's breakdown voltage, so the part would have overheated. Pin 5 is now unconnected; the data-line clamps still work through the internal Zener |
| AP22804 (U401) | SOT25 pin table (Diodes datasheet, now in `datasheets/`) | **Match**: OUT, GND, FLG unused, EN tied high (active-high A version), IN with 1 µF |
| RClamp0524P (D201–D203, D401–D403) | Pin configuration (TechPublic datasheet) | **Match**. All six run each line straight across its column (1↔10, 2↔9, 4↔7, 5↔6), with GND on 3 and 8 |
| Magjack J301 (Pulse JK0654219NL) | JK0654219 schematic and recommended PCB layout | **Match**: pins, centre taps and every hole size and spacing |
| DC jack J101 | CUI PJ-002A drawing and recommended layout | Footprint and pins **match** (1 = centre/+, 2 = sleeve/GND). **Changed** to CUI PJ-002AH (C2961147): same layout, 5 A instead of 2.5 A |

**Two things to settle before ordering:**
- **Magjack stock:** JK0654219NL is out of stock at LCSC. JK0-0036NL is a drop-in replacement (same drawing and same PCB-side pins; only its unused LEDs differ), but LCSC doesn't stock it either. Use JLCPCB's global sourcing, or hand-solder one bought from DigiKey or Mouser (it's through-hole).
- **DC plug size:** the PJ-002A family has a **2.0 mm** centre pin. A 5.5 × 2.1 mm plug fits but can be loose. Use a 5.5 × 2.0 mm supply plug, or choose a 2.1 mm jack together with the case.

The 6.8 µH inductors (C2041457) show 141 in stock, which is enough.

## Still open, accepted for rev A

**4. U106 input cap (not fixed).** No top-side spot for a 100 nF improves U106's input loop:
- **Search:** every position within 3 mm of pins 1/3 lies inside U106, L104 or C119's courtyard.
- **Best legal spot:** a 9.4 mm loop, longer than C119's current 7.2 mm.
- **B.Cu underneath:** taken by R115/R116 and the 1V1 output.
- **Risk:** U106 is a 0.35 A buck with the solid GND plane 0.1 mm below, so low.
- **Rev B:** move L104 down about 1 mm and put a 100 nF next to pin 3.

U103/U104's input loops (3.3 + 3.7 mm) are unchanged.

**5. Untented vias in pads.** 110 vias on 72 parts, mostly 0402/0603 passives (`analyze_pcb.py` VP-001). Either
order JLCPCB's epoxy-filled, capped vias, or accept some risk of thin joints and tombstoning on those parts.

**6. Uncoupled PCIe TX and USB pairs.** They are 104–112 Ω against the 85/90 Ω targets, but the simulated eye
closure is only about 2 % (see below). Route them coupled in rev B.

## Simulation and calculation results

### Regulators: output voltage from the actual parts

| Rail | Divider | Nominal | Worst case (1 % R, datasheet Vref) | Load needs |
|---|---|---|---|---|
| 5V_SOM (U104) | 110k/15k, 0.6 V ±1.5 % | 5.000 V | 4.84–5.17 V | CM3 3.8–5.2 V: passes (35 mV top margin) |
| 5V_SYS (U103) | 110k/15k | 5.000 V | 4.84–5.17 V | |
| 3V3_IO (U105) | 33k/10k, 0.768 V ±2.5 % | 3.302 V | 3.17–3.44 V | RK628D 3.135–3.465 V (see below) |
| 1V1_628 (U106) | 10k/23.2k | 1.099 V | 1.065–1.133 V | RK628D 0.99–1.21 V: passes |

- **RK628D 3.3 V supply:** at the worst corner, 3V3_IO minus the drops below (about 70 mV at full M.2 load) can
  reach about 3.10 V at the RK628D, under its 3.135 V minimum. At nominal it gets about 3.23 V. Measure at
  bring-up.
- **ngspice:** 43 subcircuits simulated, 39 pass, 0 fail. The 4 "LC filter" warnings are the regulators'
  bootstrap capacitors next to their inductors, not filters.
- **Switching frequency:** SY8303 Fsw = 105/210k = 500 kHz.
- **SY8303 enable:** turns on above VIN 5.35 V.
- **CH224A:** R101 = 6.8 kΩ requests 9 V from a PD charger.
- **VIN_SENSE:** reads 1.55 V at 17 V input, reaching the ADC's 1.8 V full scale at 19.8 V.

### DC voltage drop, from the actual copper (`checks/irdrop.py`)

Every track, via and pad on each net becomes a resistor network (1 oz outer, 0.5 oz inner copper), solved with the
loads shown.

| Net | Load | Worst drop | Worst track |
|---|---|---|---|
| 5V_SOM | 3 A into the CM3 | 8 mV | 1.2 mm, 71 A/mm², about 12 °C if long |
| 5V_SYS | 1.45 A | 88 mV | 0.127 mm branch at 0.45 A, about 7 °C |
| 3V3_IO | 0.85 A | 58 mV | 0.1 mm at 0.3 A, about 4 °C |
| RK628D_3V3 / AVDD_3V3 | 0.15 A | 11 / 8 mV | |
| 1V1_628 / AVDD_1V1 | 0.6 A | 19 / 11 mV | |
| VIN (6 V battery, full load) | 4.2 A | 23 mV | 0.8 mm at 2.8 A, 100 A/mm² (was a 0.3 mm neck, 267 A/mm²) |

### Thermal: regulator junction temperature, 40 °C ambient

Losses are computed from the datasheet R_DS(on), scaled ×1.4 for hot silicon.
- **U104 at a sustained 3 A:** 116–124 °C, below its 150 °C thermal shutdown.
- **U104 at a realistic 1.5 A:** about 64 °C.
- **U103:** about 61 °C.
- **U105:** about 53 °C.

### Output capacitance after MLCC DC-bias derating

SY8303 needs more than 22 µF at its output.
- **5V_SYS:** about 27 µF effective.
- **5V_SOM:** about 35 µF effective.

### Impedance: 2-D field solver (`checks/zsolve.py`)

JLC04161H-3313 stackup: 0.0994 mm prepreg, Er 4.1, solder mask included. The solver agrees with Hammerstad's
closed-form result to 0.2 %.

| Pairs | Geometry | Zdiff | Spec |
|---|---|---|---|
| HDMI, CSI, Ethernet (coupled 75–98 %) | 0.10/0.10 | 92.6 Ω | 100 Ω: in (−7 %) |
| PCIe RX (coupled 94 %) | 0.14/0.10 | 82.4 Ω | 85 Ω ±15 %: in |
| PCIe REFCLK (0.35 mm centres) | 0.14 | 95.8 Ω | in |
| PCIe TX (uncoupled) | 0.14, 0.78 mm centres | 104 Ω | **out (max 98)** |
| USB OTG / BT (uncoupled) | 0.12 | 109 / 112 Ω | **out (max 103.5)** |

**Effect of the mismatch:** ngspice transient with a pseudo-random bit pattern over the routed length shows about
2 % eye closure: PCIe 391.6 vs 400 mV, USB 394–397 mV. That's acceptable for rev A. In rev B, route those pairs
coupled.

### Pair length matching

- **Matched to 0.000 mm:** all HDMI, CSI, PCIe TX and REFCLK pairs.
- **PCIe RX:** 0.33 mm, about 2 ps. Over the 0.13 mm guideline, harmless at 5 GT/s.
- **USB-C stub:** 4.3 mm, about 25 ps at USB 2.0. Fine.
- **CSI lane-to-clock spread:** 7.35 mm, about 44 ps = 0.05 UI at about 1.2 Gbps per lane. At the edge of a
  typical budget; re-check if lanes run faster.

### Return paths (`checks/returnpath.py`)

- **Reference planes:** In1 is solid except for via clearances and the short hops under the RK628D. Most "gaps"
  the test flags are via clearance holes beside the traces.
- **Return vias:** 25 high-speed signal vias have no GND via within 1 mm, mainly PCIe TX/RX near the CM3
  connector (4–5 mm) and USB_BT. Add a GND via beside each pair via if there is room.

### Other checks

- **Gerbers:** 4 copper layers, aligned, outline closed, 120 × 100 mm. BOM and CPL list the same 180 parts.
- **CC1/CC2 at J103:** no external 5.1 kΩ needed; the CH224A reference schematic has none.
- **RK628D RESETN:** has an internal pull-up (datasheet pad table).
- **EFUSE:** the 100 Ω pull-down is intentional, as in the DshanPi reference design.

## Analyzer findings judged false positives

- **Sourcing (MPN coverage):** every BOM line has an LCSC number; the analyzer counts only an MPN field.
- **"Plane splits" on 3V3_IO / 5V_SYS:** these nets have no planes; the analyzer counts each trace as an island.
- **EMC warnings:** "clock on outer layer" and "pair on outer layer" are unavoidable on 4 layers. "No filtering
  at J101/J301/J401" overlooks the TVS/fuse, the magjack's own magnetics and the RClamp ESD parts.
- **Connector overhang:** J201, J301 and J401 overhang the edge by design.
- **Thermal analyzer (0 findings):** it doesn't model switching regulators. The hand calculation above replaces it.

## Not performed

- **Lifecycle audit:** needs MPNs plus distributor API keys.
- **Pin-level datasheet check of every IC:** done for CH224A, the regulators, the RK628D resets and supplies, and
  the CM3 I/O banks. Not done for USBLC6, AP22804, RClamp or the magjack.
- **Regulator loop stability and load-step response:** needs vendor models.
- **Full-wave EMI simulation.**
- **Prior-review delta:** this is the first review.
