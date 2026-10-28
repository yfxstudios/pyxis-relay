# SDI add-on board: design (draft 2, Oct 27, 2026)

A small daughterboard that adds a 3G/HD/SD-SDI input to the HDMI-in relay. It plugs into the relay's J602 header
and delivers BT.1120 video to the CM3's parallel camera input (DVP), alongside the RK628D's HDMI input on CSI.
**Status:** schematic drawn (generated, `kicad/gen/`), ERC clean apart from the BNC footprint still to draw. No
layout yet. Receiver facts below are from the GS2971A datasheet Rev. 3 (`datasheets/GS2971A_Datasheet_Rev3.pdf`);
items still marked **verify** are not covered by it.

## Decisions (Oct 27)

- **Connector:** full-size 75 Ω right-angle BNC, **Samtec BNC7T-J-P-HN-RA-BH1** (true 75 Ω, 12G, bulkhead: the
  thread passes through a wall up to 4 mm thick with nut and lock washer; DigiKey; hand-fitted like the relay's
  magjack). Footprint `sdi:BNC_Samtec_BNC7T-J-P-xx-RA-BH1_Horizontal` drawn from Samtec's print rev J
  ([suddendocs.samtec.com/prints/bnc7t-j-p-xx-ra-bh1-mkt.pdf](https://suddendocs.samtec.com/prints/bnc7t-j-p-xx-ra-bh1-mkt.pdf);
  proprietary, so not copied into the repo). Amphenol's site refused the 031-70535-12G drawing. KiCad has no single
  75 Ω right-angle BNC footprint (its 031-6575 is a dual isolated BNC).
- **Case:** an SDI variant with a taller lid (see "Mechanics").
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

`kicad/gen/build.py` writes `kicad/sdi.kicad_sch` (3 sheets, 96 parts, ERC 0 apart from the missing BNC footprint):
- **Receiver:** U101 GS2971A; the input network, AGC (2 × 470 nF), VBG 1 µF, LF 47 nF, VCO filter, 27 MHz crystal
  with 15 pF; strap resistors: 20-bit HIGH, IOPROC HIGH, audio HIGH, TIM_861 LOW (H:V:F), SW_EN, STANDBY, SDO_EN,
  RC_BYP and JTAG/HOST LOW; CS pulled up, RESET pulled down (held in reset until the relay releases it); a green
  LOCK LED on STAT3; audio, F, STAT4/5, SMPTE_BYPASS, DVB_ASI and XTAL_OUT on test pads; no loop-out (SDO open,
  SDO_EN low); 10 nF at every supply group.
- **Power:** U201 SY8089 buck (LCSC C78988; pinout and Vout = 0.6 V × (1 + R1/R2) checked against its datasheet),
  5V_SYS → 1.2 V: 22 µF in, 2.2 µH, 2 × 22 µF out, 100k/100k with 22 pF feed-forward (the datasheet's typical
  circuit); 1V2_A, 3V3 and 3V3_A through 0R (or ferrites) from 1.2 V and the relay's 3V3_IO.
- **Interface:** J301 2 × 20 2.00 mm socket (bottom side) to the relay's J602; 22 Ω series resistors on DOUT19–12
  → DVP_D15–8, DOUT9–2 → DVP_D7–0, PCLK, STAT0 → HSYNC, STAT1 → VSYNC; GSPI on SDI_GPIO3–6, RESET on SDI_GPIO7,
  LOCKED on SDI_GPIO1; 24C02 ID EEPROM on SDI_I2C.

## Requirements

| | Target | Why |
|---|---|---|
| Input | One SDI input, 75 Ω, SMPTE 259M (SD), 292M (HD), 424M (3G level A/B) | Broadcast and cinema cameras |
| Formats | 1080i50/59.94, 1080p23.98–30, 720p50/60; 1080p50/60 at the DVP's limit (below) | Common camera outputs |
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
Keep the add-on's own traces short (under 25 mm) and source-terminate them (22–33 Ω at the receiver's outputs).

## The CM3's DVP input (RK3566 VICAP)

From the RK3568 datasheet §1.2.11: DVP 8/10/12/16-bit, **up to 150 MHz**; BT.1120 YCbCr 4:2:2 8/10/12/16-bit,
single or dual-edge sampling; DVP and MIPI CSI can run at the same time.

What that means for SDI:
- **16 bits at 74.25 MHz** (8-bit Y + 8-bit C, BT.1120 SDR): 1080i, 1080p25/30, 720p. Comfortable.
- **16 bits at 148.5 MHz:** 1080p50/60 (3G level A). Right at the 150 MHz limit: may work, needs testing.
- **10-bit video is truncated to 8 bits per component** (the top 8 of each 10-bit bus): 16 pins are all J602
  carries. Fine for streaming (the encoder is 8-bit anyway).
- **Sync:** use embedded EAV/SAV timing codes (BT.1120 with embedded sync) or the receiver's H/V outputs on DVP_HSYNC
  and DVP_VSYNC. Both are supported; embedded sync is the simpler, more robust choice.

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
| GSPI SCLK / SDIN / SDOUT / CS | SDI_GPIO3–6 (bit-banged; the CM3 has no SPI on these pins) |
| RESET_N | SDI_GPIO7 |
| LOCKED / carrier detect (to an interrupt) | SDI_GPIO1 |
| Board ID EEPROM (24C02, identifies the add-on) | SDI_I2C_SCL / SDA |
| Spare | SDI_UART_TX / RX |

## Audio

The receiver de-embeds audio to I2S, but rev A has no free I2S into the CM3: I2S1_M1 shares pins with the DVP
input, which is why the RK628D's HDMI audio also stops at test pads. Options:
1. Rev A + add-on: bring the receiver's I2S to test pads too (video only for now).
2. Rev B of the relay: route an I2S port (shared by HDMI and SDI audio, selected by software) to the CM3.
3. A small I2S-to-USB bridge on the add-on into a free USB port: not available on J602 today.

Recommend 1 now and 2 for rev B.

## Power

- **Supplies:** 1.2 V core/PLL (up to 265 mA) from a 2 A buck on 5V_SYS (an LDO from 3.3 V would burn 0.55 W);
  3.3 V analog (EQ, A_VDD, buffer) and 3.3 V I/O from the relay's 3V3_IO, the analog branch through a 0R/ferrite
  filter. I/O at 3.3 V matches the CM3's DVP banks.
- **Budget:** 0.62–0.76 W for the receiver (datasheet 2.3), about 0.85 W with the buck's losses.

## Mechanics

The add-on sits over the empty area east of the CM3 (board x 95–120 mm, y 25–75 mm), on a 2.00 mm socket mating
J602. Two things shape it:
- **The case's lid posts** at board (116, 36) and (116, 68) run from the roof to the relay board, 6.8 mm diameter.
  The add-on needs clearance cut-outs for both (or uses them as its own mounting, with spacers).
- **Height:** the lid gives 16.8 mm above the relay board. With a 2.00 mm socket and header the add-on's top sits
  about 7–9 mm up, leaving 8–10 mm. A full-size right-angle BNC is about 14 mm tall: it **does not fit** this lid.

### Placement (from the BNC drawing)

BNC7T-J-P-xx-RA-BH1: 4 × 2.90 mm legs on a 9.70 mm square around the centre pin; body 11.60 mm square, axis
11.30 mm and body top 18.0 mm above the board, nut Ø14.3 mm; shoulder 8.85 mm in front of the centre pin.

- **Conflict:** with the shoulder against the inner face of the east wall (board x 120.4), the centre pin sits at
  x 111.55 and the rear legs at x 106.7, on top of the J602 socket body (x 103–107), which hangs under the add-on.
- **Fix:** centre pin at about x 113.4, y 50 (rear legs at x 108.5, clear of the socket; body y 44.2–55.8 and nut
  y 42.9–57.1, clear of the lid posts at y 36 and 68). The shoulder then lands 1.8 mm into the 2.2 mm wall: give the
  east wall a local outward boss (about 4.0 mm thick, the BNC's panel maximum) with a Ø15 × 1.8 mm counterbore on
  the inside for the shoulder.
- **Rejected:** a front-wall BNC (the board would cover the roof light pipes, pinholes and J601) and a south
  position (the magjack is 15 mm tall there).
- **Board outline:** about x 94–120, y 29–71 (board coordinates), over the CM3 module's east edge (4.5 mm tall, under
  the add-on's 6.3 mm stack) and away from its heatsink (x 51–81); notches for the lid posts at (116, 36) and
  (116, 68); the GS2971A west or north of the BNC.

### SDI case variant (plan)

- **Lid:** `OVER` from 16.8 to about 27 mm (lid about 10 mm taller), as a `--sdi` option in `case/case.py` so the
  standard case stays as it is: relay board top + 6.3 mm stack (2.00 mm header + 4.3 mm socket) + 1.6 mm add-on
  + 18.0 mm BNC body + 1 mm.
- **East wall:** Samtec's D-shaped panel hole (12.89 × 11.30 mm) at the BNC axis, about 19.2 mm above the relay
  board top, through the local boss and counterbore described above. Entirely in the lid.
- **Lid posts:** both posts at board (116, 36) and (116, 68) stay; the add-on has clearance cut-outs for them.
- **Fit check:** add the add-on's outline and the BNC body to `--check`, with a BNC plug probe like the HDMI ones.

Connector choice (decide first):
| Option | Fits today's lid | Notes |
|---|---|---|
| Full-size BNC, right angle, 75 Ω | No: needs a lid about 8 mm taller (SDI variant of the case) | What every SDI camera cable has |
| HD-BNC or DIN 1.0/2.3, right angle | Yes | Compact broadcast connectors; needs an adapter cable to BNC |
| Full-size BNC on a short 75 Ω pigtail to a bulkhead in the east wall | Yes, if the bulkhead sits below the lid line | One extra cable; easy |

The east (right) wall is free for the connector: antennas are on the west wall, Ethernet and power at the rear.

## Layout rules

- 75 Ω single-ended (or 100 Ω differential, per the receiver's input) from the connector through the termination
  and AC coupling into the receiver, as short as possible, with the return-loss network from the datasheet, solid
  ground under it and no vias in the SDI path.
- 4 layers to match the relay (JLC04161H-3313), so the 75 Ω geometry comes from the same stackup; BGA escape needs
  them anyway.
- Parallel outputs: series resistors at the receiver, short traces to the socket, PCLK routed with ground on both
  sides.

## Software

- Device tree: enable the CIF's DVP path (`rkcif_dvp`) with a BT.1120 endpoint (16-bit, embedded sync, pixel clock
  polarity from the receiver), and an I2C node for the ID EEPROM. GPIO hogs or a small driver for RESET_N and the
  GSPI bit-bang.
- A V4L2 subdevice driver for the receiver (none exists for the GS2971A in the BSP; **verify**): enough to report the
  detected standard and lock status. A first version can be user-space (GSPI from GPIOs) with the CIF driver in
  plain BT.1120 mode.
- The relay software picks HDMI or SDI as its source; with both present, either can stream.

## Open decisions

1. Connector: decided Oct 27 (full-size 75 Ω BNC, SDI case variant).
2. Formats: 1080p30 and below guaranteed, or design and test for 1080p60 at the DVP's 150 MHz limit.
3. Receiver: GS2971A now (LCSC) or GS3471 (newer, consigned).
4. Loop-out: yes or no.
5. Audio: test pads now and an I2S route on relay rev B?

## Next steps

1. LCSC parts for the passives, crystal and 6.2 nH RF inductor (the jlcsearch API refused requests on Oct 27; use
   the relay's `gen/fab.py` map for the common values).
2. Check the stack height with the actual 2.00 mm header and socket parts.
3. Settle open decisions 2–5.
4. Board outline and placement (over the relay's x 95–120, y 25–75 mm, with the lid-post cut-outs), 4-layer layout
   with the 75 Ω input, DRC, then the SDI case variant.

## Sources

- RK3568 datasheet Rev 2.3, §1.2.11 (in `hardware/hdmi-relay/datasheets/`).
- [Semtech GS3471 product page](https://www.semtech.com/products/broadcast-video/receivers-deserializers/gs3471),
  [Mouser: GS347x receivers](https://www.mouser.com/new/semtech/semtech-gs3471-eval-kit/).
- [LCSC: GS2971AIBE3 (C512366)](https://www.lcsc.com/product-image/C512366.html),
  [element14: EBK-GS2971A-00 eval board](https://tw.element14.com/en-TW/semtech/ebk-gs2971a-00/gs2971a-3g-rx-eq-audio-eval-board/dp/4243068).
- [TI E2E: LMH0341 is LVDS only](https://e2e.ti.com/support/interface-group/interface/f/interface-forum/712852/ccs-lmh0341-lmh0340).
