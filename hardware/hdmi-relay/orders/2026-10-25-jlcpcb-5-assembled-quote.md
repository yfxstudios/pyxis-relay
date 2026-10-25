# JLCPCB quote: 5 rev A boards, all 5 assembled (Oct 25, 2026)

Live instant quote from JLCPCB for the corrected rev A files (`kicad/fab/`, after the Oct 25 pin fixes). Not
ordered and not in the cart. JLCPCB auto-saved it in the account as the project "relay-gerbers".

## Order set-up

**Board:**
- 5 boards, 4 layers, 120 × 100 mm, 1.6 mm thick.
- FR4 TG155, ENIG finish.
- Stackup JLC04161H-3313: the impedances are designed for it. Select it again on any re-quote.
- 0.15 mm vias, epoxy-filled and capped, with horizontal electroless plating.
- 4-wire Kelvin test (JLCPCB adds it automatically for 0.15 mm vias).

**Assembly:**
- Standard PCBA, both sides, on all 5 boards.
- JLCPCB adds 5 mm edge rails, so the panel is 120 × 110 mm.

**Parts:**
- 58 of 59 BOM lines are placed by JLCPCB, from JLCPCB/LCSC stock.
- J301, the magjack, isn't placed: it's out of stock at JLCPCB, and it's hand-soldered in California
  (JK0654219NL from DigiKey or Mouser).

## Price

| Item | Cost |
|---|---|
| **Boards (5)** | **$130.36** |
| Engineering fee | $25.00 |
| Via covering (epoxy fill and cap) | $18.18 |
| ENIG | $18.10 |
| Board | $8.20 |
| TG155 material | $3.64 |
| Via plating method | $3.47 |
| 4-wire Kelvin test | $17.41 |
| 0.15 mm minimum via | $36.36 |
| **Assembly (5)** | **$308.46** |
| Setup fee (two sides) | $51.50 |
| Stencil | $16.54 |
| Components (58 lines, JLCPCB prices with spares) | $115.02 |
| Feeder loading (extended parts) | $85.25 |
| SMT assembly | $10.44 |
| Hand-soldering labour | $3.61 |
| Manual assembly | $0.79 |
| Assembly fixture | $16.54 |
| X-ray inspection (RK628D BGA) | $8.25 |
| Packaging | $0.52 |
| **JLCPCB total** | **$438.82** |

**Build time:**
- Boards: 3–4 days.
- Assembly: 5–6 days, included in the price. Faster costs extra: 4–5 days +$49.63, 3–4 days +$99.25.
- Shipping weight: 1.09 kg.

## Landed cost (estimate)

| Item | Cost | Basis |
|---|---|---|
| JLCPCB total | $438.82 | Quote above |
| Shipping, DHL Express DDP | about $45 | The open 3-assembled order shows $41.79; this one is heavier |
| US duties and taxes, 35% | about $153.59 | Same rate JLCPCB's checkout charges on the open order (HS 847330) |
| Duty disbursement fee | about $8 | $7.52 on the open order |
| **Landed** | **about $645** | **About $129 a board** |

**Compared with the order in your checkout** (5 boards, 3 assembled, old pre-fix files):
- That order: $396.26 merchandise, $584.27 landed.
- All 5 assembled: about $43 more before duty, about $61 more landed. That's about $30 each for the 2 extra
  assembled boards.
- Most of the assembly cost is fixed (setup, stencil, feeder loading, fixture), so the extra boards are cheap.

**Not included:**
- the CM3 modules, Wi-Fi cards, antennas and heatsinks (see `2026-10-25-dev-parts.md`);
- the magjacks;
- hand assembly in California.

## Before ordering

- **In the cart (Oct 25, 14:24): relay-gerbers_Y4, $440.34**, from the files in commit 2a6e6a4: the pin fixes, the
  ESD links (review B1) and C501/C502 as 0 Ω (M1).
  - It's $1.52 more than the quote above: one more feeder for the 0 Ω part.
  - Product description is Development Board (HS 847330); J301 is not placed.
- **The old 3-assembled order (Y3, pre-fix files) was deleted from the cart.** Check out from the cart with only Y4
  selected. The cart also holds the 500-unit quote (P2); leave it unselected.
