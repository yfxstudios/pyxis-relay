# SDI add-on board: design (draft 4, Oct 28, 2026)

A small daughterboard that adds a 3G/HD/SD-SDI input to the HDMI-in relay. It plugs into the relay's J602 header
and delivers BT.1120 video to the CM3's parallel camera input (DVP), alongside the RK628D's HDMI input on CSI.
**Status:** schematic drawn (generated, `kicad/gen/`), ERC 0. REVIEW_1's three blockers are settled below
(stackup, BNC position and wall bay, lid sub-assembly), and its majors and minors are
answered in the schematic or below (draft 4); no layout yet. Part numbers for the passives are still open. Receiver facts below are from the GS2971A datasheet Rev. 3 (`datasheets/GS2971A_Datasheet_Rev3.pdf`);
items still marked **verify** are not covered by it.

## Decisions (Oct 27)

- **Connector:** full-size 75 Ω right-angle BNC, **Samtec BNC7T-J-P-HN-RA-BH1** (true 75 Ω, 12G, bulkhead: the
  thread passes through a wall up to 4 mm thick with nut and lock washer; DigiKey; hand-fitted like the relay's
  magjack). Footprint `sdi:BNC_Samtec_BNC7T-J-P-xx-RA-BH1_Horizontal` drawn from Samtec's print rev J
  ([suddendocs.samtec.com/prints/bnc7t-j-p-xx-ra-bh1-mkt.pdf](https://suddendocs.samtec.com/prints/bnc7t-j-p-xx-ra-bh1-mkt.pdf);
  proprietary, so not copied into the repo). Amphenol's site refused the 031-70535-12G drawing. KiCad has no single
  75 Ω right-angle BNC footprint (its 031-6575 is a dual isolated BNC).
- **Case:** an SDI variant with a taller lid and a local outward bay for the BNC (see "Mechanics").
- **Stackup (REVIEW_1 B1):** JLC04161H-7628 for the add-on, not the relay's 3313 (see "Layout rules").
- **Mounting (REVIEW_1 B3):** the add-on is a lid sub-assembly: BNC nut on the lid's boss plus two M3 × 6 mm
  male-female standoffs into the lid posts; the lid and add-on go on and come off as one part.
- **J301:** SMD 2 × 20 2.00 mm socket on the bottom side (not through-hole), so the SDI input never crosses a pin
  field and the receiver can sit over the socket.
- **Receiver:** GS2971A (LCSC C512366: 168 in stock at $16.86 on Oct 27; JLCPCB can place it).

## GS2971A facts used (datasheet Rev. 3)

| Item | Value | Section |
|---|---|---|
| Equalizer | Integrated adaptive EQ: 150 m Belden 1694A at 3G, 250 m HD, 480 m SD; about 195 mW | 4.3.1 |
| Supplies | CORE_VDD and PLL_VDD 1.2 V (±5 %); A_VDD, EQ_VDD, BUFF_VDD 3.3 V; IO_VDD 1.8 or 3.3 V | 2.2 |
| Current (20-bit 3G) | 1.2 V: 210 mA typ, 265 mA max; 3.3 V: 115–130 mA; total 620–760 mW at IO 3.3 V | 2.3 |
| VCO supply | 1.2 V analog through 105 Ω 1 % with 33 µF (VCO_VDD about 0.7 V) | 1.2, fig. 5-1 |
| Reference | 27 MHz crystal, ESR ≤ 50 Ω, ±100 ppm total, 16 pF total per side | 4.6 |
| Output clock | 3G 20-bit: 148.5 MHz; HD 20-bit: 74.25 MHz; SD 20-bit: 13.5 MHz | 1.2 (PCLK) |
| Output bus | 20-bit: DOUT19–10 luma (stream 1), DOUT9–0 chroma (stream 2) | 1.2 |
| Timing outputs | STAT0 H, STAT1 V, STAT2 F, STAT3 LOCKED, STAT5 data error (defaults, reprogrammable) | 1.2 |
| Host | GSPI (SCLK, SDIN, SDOUT, CS active low); JTAG/HOST low selects GSPI | 4.20 |
| Power-up | Any order; hold RESET_TRST low ≥ 1 ms after the supplies are stable | 4.23–4.24 |
| Input network | BNC → 6.2 nH ∥ 75 Ω → 75 Ω to ground, 1 µF into SDI; SDI-bar 1 µF to 37.4 Ω | fig. 5-1 |
| Loop bandwidth | LB_CONT floating = nominal (3 MHz at 3G) | 4.5.1 |
| Package | 11 × 11 mm LBGA-100, 1.0 mm pitch, 0.5 mm balls | 7.1 |

## Schematic (rev A, generated)

`kicad/gen/build.py` writes `kicad/sdi.kicad_sch` (3 sheets, 101 parts, ERC 0):
- **Receiver:**
  - U101 GS2971A with the input network, AGC (2 × 470 nF), VBG 1 µF, LF 47 nF and the VCO filter.
  - **27 MHz crystal:** CL 8 pF with 12 pF caps. `XTAL_CL` in `sheets.py` sets the caps to 2 × CL − 4 pF, so a
    12 pF crystal gets 20 pF (REVIEW_1 m10).
  - **Strap resistors:** 20-bit HIGH; IOPROC HIGH; **audio LOW** (no I2S route on rev A, which saves 36 PCLK of
    latency and about 40 mW; m1); TIM_861 LOW (H:V:F); SW_EN, STANDBY, SDO_EN, RC_BYP and JTAG/HOST LOW.
  - **Control pins:** CS pulled up; RESET pulled down, so the receiver stays in reset until the relay releases it.
  - **Status:** a green LOCK LED on STAT3. Audio, F, STAT4/5, SMPTE_BYPASS and DVB_ASI go to test pads, with
    unfitted 10k pull-up/pull-down footprints on the last two for manual mode (m2).
  - **XTAL_OUT** is left open, so there is no toggling 27 MHz stub; probe at XTAL2 (m9).
  - **Unused:** no loop-out (SDO open, SDO_EN low).
  - **Decoupling:** 10 nF at every supply group.
- **Power:** U201 SY8089 buck (LCSC C78988; pinout and Vout = 0.6 V × (1 + R1/R2) checked against its datasheet),
  5V_SYS → 1.2 V: 22 µF in, 2.2 µH (NR3015 class, Isat ≥ 1.5 A so a short on 1.2 V doesn't drive it into hard
  saturation; m11), 2 × 22 µF out, 100k/100k with 22 pF feed-forward (the datasheet's typical
  circuit); 1V2_A, 3V3 and 3V3_A through 0R (or ferrites) from 1.2 V and the relay's 3V3_IO.
- **Interface:**
  - J301, a 2 × 20 2.00 mm SMD socket (bottom side), to the relay's J602.
  - **33 Ω series resistors** (`SERIES_R`; M3, m8) on DOUT19–12 → DVP_D15–8, DOUT9–2 → DVP_D7–0, PCLK,
    STAT0 → HSYNC and STAT1 → VSYNC.
  - **Control:** GSPI on SDI_GPIO3–6, RESET on SDI_GPIO7, LOCKED on SDI_GPIO1.
  - **ID EEPROM:** 24C02 on SDI_I2C, write-protected through 10k to 3.3 V; close solder jumper JP301 to write it
    (m7).

## Requirements

| | Target | Why |
|---|---|---|
| Input | One SDI input, 75 Ω, SMPTE 259M (SD), 292M (HD), 424M (3G Level A; Level B-DL through the receiver's B→A converter) | Broadcast and cinema cameras |
| Formats | 1080i50/59.94, 1080p23.98–30, 720p50/60 guaranteed; 1080p50/60 is "test and tune" at the DVP's limit (below) | Common camera outputs |
| Cable reach | Belden 1694A: about 100 m at 3G, 200 m at HD | Integrated adaptive equalizer |
| Loop-out | Optional reclocked SDI out | Nice to have; adds a second connector |
| Audio | Embedded audio de-embedded to I2S (up to 8 ch) | See "Audio" below: no free I2S on the CM3 yet |
| Power | From J602 (5V_SYS, 3V3_IO), under 1 W | The relay's 5 V budget has headroom |
| Fit | Inside the existing case, or a taller lid for a full-size BNC | See "Mechanics" |

## The relay side: what J602 gives us (fixed by rev A)

J602 is a 2 × 20, 2.00 mm header (not fitted on rev A; solder one in), at board coordinates x 104–106 mm,
y 31–69 mm (board origin top-left, 120 × 100 mm board), pin 1 at (104, 31). Pins
(`hardware/hdmi-relay/kicad/gen/board_io_sheets.py`):

| Pins | Signal | CM3 side |
|---|---|---|
| 1–2 | 5V_SYS | 5 V buck, shared with the relay |
| 3–4 | 3V3_IO | 3.3 V buck, shared |
| 5–6, 24, 39–40 | GND | |
| 7–22 | DVP_D0–D15 | 16-bit DVP input, 3.3 V banks |
| 23, 25, 26 | DVP_PCLK, DVP_HSYNC, DVP_VSYNC | |
| 27–28 | SDI_I2C_SCL / SDA | I2C4_M0 |
| 29–30 | SDI_UART_TX / RX | UART9_M1 |
| 31, 33–37 | SDI_GPIO1, SDI_GPIO3–7 | 3.3 V GPIOs |
| 32, 38 | not connected | Their CM3 pins went to LED_STATUS and RK628D reset |

The relay's DVP traces are 14–68 mm long and not length-matched: about 0.35 ns of skew, 5 % of a 148.5 MHz period.
Keep the add-on's own traces short (under 25 mm) and source-terminate them (33 Ω at the receiver's outputs).

## The CM3's DVP input (RK3566 VICAP)

From the RK3568 datasheet §1.2.11: DVP 8/10/12/16-bit, **up to 150 MHz**; BT.1120 YCbCr 4:2:2 8/10/12/16-bit,
single or dual-edge sampling; DVP and MIPI CSI can run at the same time.

What that means for SDI:
- **16 bits at 74.25 MHz** (8-bit Y + 8-bit C, BT.1120 SDR): 1080i, 1080p25/30, 720p. Comfortable.
- **16 bits at 148.5 MHz:** 1080p50/60 (3G). Right at the 150 MHz limit, so it is not a guaranteed format
  (REVIEW_1 M1):
  - **Receiver timing:** output delay ≤ 3.7 ns and hold ≥ 1.0 ns after the PCLK rising edge (table 2-4). That leaves
    3.0 ns of setup and 1.0 ns of hold for rising-edge capture, before the relay's 0.35 ns of DVP skew.
  - **Unknown:** the RK3566's DVP setup and hold are only in the TRM. Get them before bring-up.
  - **Tuning:** register 06Ch moves PCLK 0–90° plus 0–1.2 ns in 40 ps steps, and the CIF can sample on either edge.
    Bring-up sweeps 06Ch at 1080p60 and keeps the centre of the passing window.
  - **Layout:** PCLK and all 18 data and sync lines to the same length (±2 mm), each under 25 mm.
  - **Lower rates:** 74.25 MHz and below have more than 9 ns of margin.
- **3G Level B (M2):** in 20-bit mode a Level B signal arrives as two multiplexed 10-bit streams, not Y and C.
  - **Level B-DL (1080p50/60):** needs the receiver's Level B→A converter, enabled over GSPI (it is off by default),
    with the 05Eh reset sequence. GSPI is therefore **required** for the 1080p50/60 claim, not optional.
  - **H/V/F in B→A mode:** not usable, which is one more reason to use embedded sync.
  - **Level B-DS (two 1080i streams):** not supported as two streams; at most one stream as 8-bit BT.656 on
    DVP_D15–8.
- **10-bit video is truncated to 8 bits per component** (the top 8 of each 10-bit bus): 16 pins are all J602
  carries. Fine for streaming (the encoder is 8-bit anyway).
- **Sync: embedded EAV/SAV (BT.1120 with embedded sync) is the designed mode** (REVIEW_1 M4).
  - **Why not the H/V pins:** as strapped (TIM_861 LOW), STAT0 and STAT1 are H and V *blanking*. CIF_HREF expects a
    data-enable, which is H inverted. F isn't on J602 at all, so interlaced external-sync capture isn't possible.
  - **Fallback:** the STAT0/1 wires stay as a fallback. Use the CIF's HREF polarity flip, or reprogram STAT0 to DE
    and set TIM_861 over GSPI (it is read live).

## Receiver choice

| Part | What it is | Package | Price / stock (summaries) | Notes |
|---|---|---|---|---|
| **Semtech GS2971A (pick)** | 3G/HD/SD receiver with integrated adaptive cable EQ, reclocker, audio de-embedder; 20/10-bit parallel out | 11 × 11 mm LBGA-100, 1.0 mm | LCSC C512366: 168 in stock, $16.86 (Oct 27) | The common choice; JLCPCB can place it. Semtech lists the GS2971A and GS3471 for new designs; **verify** lifecycle with Semtech |
| Semtech GS3471 | Newer receiver with integrated adaptive EQ, retimer, 8-ch audio; 20/10-bit, SDR or DDR | 9 × 9 mm 100-ball BGA, 0.8 mm | Mouser stocks the GS347x family; not found at LCSC or DigiKey in a quick search | The likely long-term part; JLCPCB would need it consigned |
| Semtech GS2961A | 3G receiver with EQ, no audio | BGA | DigiKey about $45–54 | Dearer, no audio |
| TI LMH0341 | 3G deserializer, LVDS output | QFN | Farnell | No parallel BT.1120: would need an LVDS-to-parallel stage. Rejected |

**Plan:** draw the board around the GS2971A (cheap, JLCPCB-placeable) and check the GS3471's pinout for a rev B
drop-in. Read both full datasheets before the schematic: supplies, strap pins, host interface, output timing.

## Control

The Semtech receivers are configured over Semtech's SPI host interface (GSPI: SCLK, SDIN, SDOUT, CS active low;
datasheet 4.20), not I2C. Most of what we need also works stand-alone from strap pins (auto-detect the standard, 20-bit output,
embedded timing codes), so control is for status and tuning:

| Function | J602 pin |
|---|---|
| GSPI SCLK / SDIN / SDOUT / CS | SDI_GPIO3–6, bit-banged: kernel `spi-gpio` + `spidev`, mode 0, 16-bit words MSB first, ≥ 37.1 ns between words |
| RESET_N | SDI_GPIO7 |
| LOCKED / carrier detect (to an interrupt) | SDI_GPIO1 |
| Board ID EEPROM (24C02, identifies the add-on) | SDI_I2C_SCL / SDA |
| Not used | SDI_UART_TX / RX (the relay's UART9, driven by the CM3: leave unconnected) |

**Hardware SPI option (REVIEW_1 m6), not taken:** the CM3's SPI3_M0 is on J602 too, at pins 27, 28, 34 and 33.
Re-pinning the receiver there would give a kernel SPI bus, but it costs the I2C ID EEPROM, and GSPI traffic is a few
register writes at start-up. Kept bit-banged with the EEPROM. If a driver ever needs fast GSPI, swap the four nets in
`sheets.py` and drop the EEPROM; the receiver's own registers can identify the board instead.

## Audio

The receiver de-embeds audio to I2S, but rev A has no free I2S into the CM3: I2S1_M1 shares pins with the DVP
input, which is why the RK628D's HDMI audio also stops at test pads. Options:
1. Rev A + add-on: bring the receiver's I2S to test pads too (video only for now), with AUDIO_EN strapped LOW;
   software can enable audio over GSPI to probe the pads.
2. Rev B of the relay: route an I2S port (shared by HDMI and SDI audio, selected by software) to the CM3.
3. A small I2S-to-USB bridge on the add-on into a free USB port: not available on J602 today.

Recommend 1 now and 2 for rev B.

## Power

- **Supplies:** 1.2 V core/PLL (up to 265 mA) from a 2 A buck on 5V_SYS (an LDO from 3.3 V would burn 0.55 W);
  3.3 V analog (EQ, A_VDD, buffer) and 3.3 V I/O from the relay's 3V3_IO, the analog branch through a 0R/ferrite
  filter. I/O at 3.3 V matches the CM3's DVP banks.
- **Budget:** 0.62–0.76 W for the receiver (datasheet 2.3), about 0.85 W with the buck's losses.

## Mechanics

The add-on sits over the empty area east of the CM3, on a 2.00 mm socket mating J602. What is under it on the relay
(from `relay.kicad_pcb`, board coordinates): J602 (courtyard x 102.5–107.6, y 29.5–70.6), the lid-post holes H602
(116, 36) and H604 (116, 68) with 7 mm keep-outs, the CM3 module's east edge (x 93.6, 4.5 mm tall), and the magjack
J301 from y 71.6 south **but only west of x 108.9** (15.1 mm tall). Nothing else.

### Stack height

- **Standoffs set the gap:** two M3 × 6.0 mm male-female hex standoffs (5.5 mm AF) at H602/H604 between the relay
  and the add-on. Add-on bottom 6.0 mm, top 7.6 mm above the relay board top.
- **The connector must be no taller than the standoffs:** mated height (header insulator + socket body) 5.6–6.0 mm,
  so the socket stops just short of bottoming instead of being crushed. A 1.5 mm-insulator header on the relay
  plus a 4.3 mm SMD socket gives 5.8 mm. A 2.0 mm insulator (6.3 mm) does **not** fit. Measure the chosen pair.
- **Heights above the relay board top:** BNC axis 18.9 mm, BNC body top 25.6 mm, BNC leg tips 3.0 mm.
- **Over the CM3 module (x < 94.1):** 1.5 mm gap above the module, so bottom-side parts there are ≤ 1.0 mm and
  nothing through-hole.

### Placement (from the BNC drawing)

BNC7T-J-P-xx-RA-BH1: 4 × Ø2.90 legs on a 9.70 mm square around the centre pin; body 11.60 mm square; axis 11.30 mm
and body top 18.0 mm above the board; shoulder 8.85 mm in front of the centre pin; legs 3.00 mm below the board.

- **Centre pin at board (116.6, 50.0).** Two limits fix it:
  - **Rear legs (x 111.75):** pads Ø3.8 (footprint), pad edge 109.85, 0.35 mm from the SMD socket's bottom pads
    (≤ 109.5); hole edge 110.3, 3.3 mm from the socket body.
  - **No room inside the wall:** from a pin x of 113.7 east, the front leg pads already lie past the lid's inner
    wall face (120.4). Here they are at x 121.45, hole edge 122.9. REVIEW_1 B2's x ≥ 114.5 has the same problem.
    So the board goes through the wall into a bay (below).
- **Board edge:** the add-on reaches x 123.7 locally (a tab, y 42.5–57.5), 0.35 mm beyond the front leg pads
  (`BNC_EDGE` = 7.1 mm in the footprint, where the courtyard is clipped).
- **Positions on the add-on:**

  | Part | x | y |
  |---|---|---|
  | BNC body | 110.8–122.4 | 44.2–55.8 |
  | BNC flange | 122.4–125.45 | 43.05–56.95 |
  | Shoulder | 125.45 | |
- **SDI input path:** from the centre pin west between the rear legs (5.5 mm gap) to the input network at about
  x 104.5–110.5, then the 1 µF coupling to the receiver.
- **Receiver:** the GS2971A, body about x 93–104, y 44.5–55.5, with balls C1/D1 facing east. It sits on the top
  side, directly over the SMD socket. The DVP vias drop between the socket pads.
- **Rejected:** a front-wall BNC (the board would cover the roof light pipes, pinholes and J601), a south position
  (magjack), and a through-hole J301. Its two pin columns at x 104/106 run y 31–69, so the 75 Ω trace would have to
  squeeze between DVP pins.

### Board outline

| Region | x | y | Why |
|---|---|---|---|
| Main | 88.0–120.2 | 29.0–70.5 | 7 mm clear of the CM3 heatsink (x 81); 1.1 mm clear of the magjack (y 71.6) |
| SE tab | 110.0–120.2 | 70.5–72.0 | Material round the H604 hole; the magjack ends at x 108.9 |
| East tab | 120.2–123.7 | 42.5–57.5 | Carries the BNC's front legs into the wall bay |

- **Mounting holes:**
  - Ø3.4 (0.3 mm float, so the BNC nut sets x and the standoffs only clamp) at (116, 36) and (116, 68).
  - Ø7.0 copper keep-out on both sides: the lid post bears on the top, the standoff hex on the bottom.
- **Top-side keep-out bands, y 32.4–39.6 and 64.4–71.6, full width:** the add-on slides 18–19 mm east across the
  post ends during assembly (below). Top-side parts in these bands would hit the posts. The bottom side is free
  there except the hole keep-outs.
- **Bottom side:** 6.0 mm of height everywhere except over the CM3 module (≤ 1.0 mm) and the socket.

### SDI case variant (`case/case.py --sdi`)

- **Lid height:** `OVER` 16.8 → **27.0 mm** (body top 25.6 + 1.4 mm). The standard case stays as it is.
- **Lid posts at (116, 36) and (116, 68):** they end at the add-on top (7.6 mm above the relay board top), not at the
  board. Each keeps its M3 insert at the bottom. Posts at (4, 4) and (4, 96) are unchanged.
- **BNC bay (east wall), y 41.5–58.5:**
  - **Pocket:** x 120.0–125.45, from 2.0 mm above the relay board top (below the leg tips at 3.0) up to the roof.
    It takes the add-on's east tab, the BNC's front legs and its 13.9 mm flange.
  - **Outward boss:** x 122.6–128.45, y 39.5–60.5, full lid height. Its last 3.0 mm (x 125.45–128.45) is the panel
    that the shoulder seats on (Samtec allows 4.0 mm max).
  - **D-hole:** Ø12.89 with flats 11.30 apart, **flats top and bottom**, centred at y 50, 18.9 mm above the relay
    board top. The nut (Ø14.3) and lock washer sit on the boss face.
- **Assembly** (REVIEW_1 B3, option a):
  1. Fit the M3 heat-set inserts in the lid posts, as today.
  2. Turn the lid upside down. Lay the add-on in, components towards the roof, BNC thread aimed at the D-hole.
     Slide it east 18–19 mm, across the post ends, until the shoulder seats and the holes line up with the posts.
  3. Lock washer and nut on the BNC; tighten.
  4. Screw the two M3 × 6 male-female standoffs, stud up, through the add-on into the post inserts. The 1.6 mm
     board leaves 4.4 mm of stud in the insert.
  5. Lower the lid with the add-on onto the base: J301 onto J602, guided by the lid walls. The standoffs land on
     H602/H604.
  6. Screw in from under the base:
     - M3 × 10 into the lid inserts at (4, 4) and (4, 96), as today.
     - **M3 × 8** into the standoffs at (116, 36) and (116, 68): 3.6 mm of thread, short of the standoff's
       female depth.
  - **Opening:** lifting the lid pulls the add-on straight off J602, guided by the posts. J602 is never levered.
- **Fit check (`--sdi --check`):** the add-on outline, the BNC body, flange, thread, nut and leg tips, and the
  standoffs are checked against the lid, the base and the relay's STEP model. It also checks the slide path (BNC body
  and flange swept 18.1 mm) and a 15 mm BNC plug probe, and that both posts bear fully on the add-on.

## Layout rules

- 75 Ω single-ended (or 100 Ω differential, per the receiver's input) from the connector through the termination
  and AC coupling into the receiver, as short as possible, with the return-loss network from the datasheet, solid
  ground under it and no vias in the SDI path.
- **Stackup: JLC04161H-7628** (REVIEW_1 B1). The add-on does not need the relay's stackup, and nothing else on it
  is impedance-controlled.
  - **L1 to L2:** 0.2104 mm 7628 prepreg, εr about 4.4, 1 oz outer copper.
  - **75 Ω microstrip:** about 0.14 mm uncoated (Hammerstad; 50 Ω would be 0.36 mm). Solder mask brings it nearer
    0.13. Take the final width from JLCPCB's impedance calculator before routing. JLCPCB's minimum is 0.09 mm.
  - **Why not 3313:** a 75 Ω trace there would be about 0.06 mm, which can't be made.
  - BGA escape still needs 4 layers.
- **Planes under the SDI path:**
  - Cut L2 under the 0402 pads of the input network (6.2 nH, 75 Ω, 75 Ω, 1 µF, and the 1 µF/37.4 Ω on SDI-bar),
    so the 0.5 mm pads see L3 and stay near 75 Ω (GS2971A 5.2).
  - The BNC footprint has a Ø4.0 rule area on In1/In2/B.Cu round the centre pin.
  - Keep the analog corner (balls A1–G2, VBG/LF, AGC) over an unbroken L2 region with no digital return under it.
- **Parallel outputs:**
  - Series resistors at the receiver; PCLK with ground on both sides.
  - Match all 19 lines to ±2 mm, each under 25 mm (M1).
- **Signal return (M3):** J602 has a single ground pin (24) inside the DVP group.
  - Use the lowest output drive that passes (register 06Dh) with the 33 Ω series resistors.
  - Pour ground on the add-on's bottom layer, facing the relay's top-layer ground: the 6 mm gap between them is the
    only other return.
  - Leave J602 pins 29, 30, 32 and 38 unconnected.
  - Relay rev B: make 32 and 38 GND and move UART9 off 29/30.
- **Ground:** one GND net (REVIEW_1 m3). Keep the analog corner (balls A1–A4, B1–B4, C1–D3, E1–E3, F1–G2), the
  VBG/LF and AGC caps and the input network over plane with no digital return current under it.
- **BGA:** 0.45 mm NSMD pads with a 0.55 mm mask opening (m4). Confirm JLCPCB's BGA rules at quote time.
- **ESD (m13):** none on the input, matching Semtech's reference design; the input is 2 kV HBM and AC-coupled. If
  field units show input damage, the only option that keeps the return loss is a < 0.3 pF diode at the BNC pad.

## Software

- **Device tree:**
  - Enable `rkcif_dvp` (and its `sditf` node) with pinctrl `cif_dvp_clk` + `cif_dvp_bus16`.
  - BT.1120 16-bit with embedded sync (M4); PCLK edge and the Y/C order as found at bring-up.
  - `&i2c4` (i2c4m0_xfer) with `eeprom@50` (atmel,24c02).
  - `spi-gpio` on GPIO4_A6/B0/B2/B3 (SDI_GPIO3–6) for GSPI.
  - Take GPIO4_A6/A7/B0, GPIO3_A1/B4/C1 and the I2C4_M0 pins back from the Radxa base tree in
    `rk3566-relay-carrier.dtso`, and confirm nothing else claims GPIO4_C1 (CIF_CLKIN).
  - Leave UART9 disabled.
- **Reset contract (M6):** the receiver must stay in reset ≥ 1 ms after **all** supplies are stable.
  - **Supplies:** 1.2 V comes from the add-on's buck. 3V3_IO rises about 10 ms after 5V_SYS.
  - **At boot:** the 10k pull-down holds RESET low while GPIO3_C1 is still an input.
  - **Release:** the driver (`reset-gpios = <&gpio3 RK_PC1 GPIO_ACTIVE_LOW>`) or a hog keeps it low ≥ 20 ms after
    power, then ≥ 1 ms more, then releases it.
  - **Re-assert** after a hot re-seat of the add-on or a power cut to it.
  - **Mode changes after power-up:** register overrides only (the straps are read live, not latched).
- **GSPI tasks:**
  - standard detect (VD_STD);
  - Level B→A conversion and its 05Eh reset sequence (M2);
  - STAT mux and H_CONFIG (M4);
  - drive strength 06Dh (M3);
  - PCLK delay sweep 06Ch (M1);
  - audio enable.
- **LOCKED:** GPIO4_A7 as an interrupt to start and stop streaming; the LED mirrors it.
- A V4L2 subdevice driver for the receiver (none exists for the GS2971A in the BSP; **verify**): enough to report the
  detected standard and lock status. A first version can be user-space (GSPI from GPIOs) with the CIF driver in
  plain BT.1120 mode.
- The relay software picks HDMI or SDI as its source; with both present, either can stream.

## Open decisions

1. Connector: decided Oct 27 (full-size 75 Ω BNC, SDI case variant). Stackup, BNC position and mounting: decided
   Oct 27 (REVIEW_1 B1–B3, above).
2. Formats: decided Oct 28. 1080p30 and below are guaranteed; 1080p50/60 is designed for (matched lengths, GSPI,
   B→A conversion) but proven only at bring-up (REVIEW_1 M1, M2).
3. Receiver: GS2971A now (LCSC) or GS3471 (newer, consigned).
4. Loop-out: yes or no.
5. Audio: test pads now (AUDIO_EN LOW, enabled over GSPI when needed) and an I2S route on relay rev B.
6. Sync: decided Oct 28, embedded (M4). Series resistors 33 Ω (M3, m8). GSPI bit-banged, EEPROM kept (m6, m7).

## Next steps

1. **Parts (REVIEW_1 M7), with LCSC numbers in the generator** (`LCSC=` as the relay does):
   - the J602 header (1.5 mm insulator), the J301 SMD socket (4.3 mm) and the 6.0 mm M3 male-female standoffs;
     measure the mated stack;
   - a 27 MHz 3225 crystal, CL 8 pF (or change `XTAL_CL`), ESR ≤ 50 Ω, ±30 ppm;
   - a wire-wound 0402 6.2 nH ±5 % (high Q);
   - a 33 µF 6.3 V X5R 0805;
   - the 105 Ω and 37.4 Ω 1 % 0402 resistors;
   - a 2.2 µH NR3015 inductor with Isat ≥ 1.5 A;
   - confirm BNC7T-J-P-HN-RA-BH1 stock and quantity at Samtec or DigiKey.

   The jlcsearch API was refused again for scripted requests on Oct 28, so look these up by hand.
2. Print the `case.py --sdi` lid and check the bay, panel and slide-in assembly before the layout is final.
3. Board outline and placement as above, 4-layer layout on 7628 with the 75 Ω input and matched DVP lines, DRC.
4. Get the RK3566 VICAP DVP setup/hold from the TRM (M1).

## Sources

- RK3568 datasheet Rev 2.3, §1.2.11 (in `hardware/hdmi-relay/datasheets/`).
- [Semtech GS3471 product page](https://www.semtech.com/products/broadcast-video/receivers-deserializers/gs3471),
  [Mouser: GS347x receivers](https://www.mouser.com/new/semtech/semtech-gs3471-eval-kit/).
- [LCSC: GS2971AIBE3 (C512366)](https://www.lcsc.com/product-image/C512366.html),
  [element14: EBK-GS2971A-00 eval board](https://tw.element14.com/en-TW/semtech/ebk-gs2971a-00/gs2971a-3g-rx-eq-audio-eval-board/dp/4243068).
- [TI E2E: LMH0341 is LVDS only](https://e2e.ti.com/support/interface-group/interface/f/interface-forum/712852/ccs-lmh0341-lmh0340).
