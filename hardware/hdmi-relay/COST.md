# HDMI-in relay: unit cost breakdown (Oct 22, 2026)

How the unit cost estimate in [DESIGN.md](DESIGN.md) is built: one line per part, with where each price comes
from.

## Ground rules

- **Quantity: 500 units.** Prices use each listing's tier closest to 500–1,000.
- **"Listing"** means a distributor page I found; prices are snapshots and change. **"Assumption"** means I
  found no listing at volume and estimated; each says why.
- **Design:** the rev A carrier in [REV_A_SPEC.md](REV_A_SPEC.md): Radxa CM3 module (since Oct 22; it was the MYIR
  RK3568), an M.2 Wi-Fi card, assembled at JLCPCB in China and shipped to the US.
- **Not included:** sales tax, our own time, and one-time costs. The one-time costs are
  [listed separately](#one-time-costs), because they shrink per unit as volume grows.

## Per unit

| # | Item | Part | Unit price | Source |
|---|---|---|---|---|
| 1 | Processor module (RK3566, 2 GB RAM, 16 GB eMMC, power IC, Ethernet PHY) | Radxa CM3 RM116-D2E16W0 | **$35.00** | Assumption built on a listing: the version without eMMC (RM116-D2E0W0S) is £23.07 each in a box of 500 at [RS](https://uk.rs-online.com/web/p/rock-sbc-boards/2600891), about $30; 16 GB eMMC assumed +$5. Needs a quote. (Was MYIR MYC-LR3568 at $43 list.) |
| 2 | HDMI-to-camera-input bridge | Rockchip RK628D | $2.34 | Listing: LCSC C2843533, 990+ ([datasheet page](https://datasheet.lcsc.com/lcsc/2401261533_Rockchip-RK628D_C2843533.pdf)) |
| 3 | RK628D support parts: two regulators and a crystal | | $0.50 | Assumption: three common parts at $0.10–0.20 each |
| 4 | Wi-Fi 5 + Bluetooth 5 card (today's chip) | RTL8822CE M.2 2230 | **$8.00** | Assumption. Retail listings are $15–28 ([Pakronics](https://www.pakronics.com.au/products/rtl8822ce-wireless-nic-2-4g-5ghz-dual-band-wifi-5-bluetooth-5-0-compatible-with-jetson-orin-ss114993556), [EmbeddedWorks](https://embeddedworks.net/product/wlan800)), and used cards sell for about $8 ([eBay](https://www.ebay.de/itm/285904698085)). Seeed offers volume quotes. Needs a quote. |
| 5 | M.2 E-key socket | | $0.30 | Assumption |
| 6 | Two dual-band antennas with cables | RP-SMA dipole + IPEX pigtail | $2.50 | Assumption. Retail pairs are $6–13 ([Newegg](https://www.newegg.com/p/0EP-00DR-00003), [Mini-Box](https://www.mini-box.com/Wireless-antennas-and-accessories)); factory price for a pair is typically a third of that. |
| 7 | Three module connectors (carrier side) | Hirose DF40C-100DS-0.4V(51) × 3 | $1.90 | Listing: [LCSC C597931](https://www.lcsc.com/product-image/C597931.html), $0.53–0.72 at 1,000+ (two snapshots), × 3. The Ethernet chip ($0.85) is now on the module. |
| 8 | Ethernet jack with magnetics, **gigabit** (4 pairs) | to choose | $1.80 | Assumption. Correction: the HR911105A first listed here ($0.89, [LCSC C12074](https://www.lcsc.com/product-image/C12074.html)) is 10/100 only. Gigabit magjacks cost roughly double. |
| 9 | Two full-size HDMI sockets (in, out) | Ckmtw D-HDMIM19P-F000 | $0.42 | Listing: [LCSC C2902698](https://www.lcsc.com/product-detail/C2902698.html), $0.21 at 1,400+, × 2 |
| 10 | HDMI static protection, 4 chips | RCLAMP0524P | $0.08 | Listing: [LCSC C907837](https://lcsc.com/product-detail/TVS_TECH-PUBLIC-RCLAMP0524P_C907837.html), about $0.019 at 3,000+, × 4 |
| 11 | Plug-detect and power-switch transistors, small protection parts | MMBT3904, AO3401A, TVS | $0.10 | Assumption. No EDID memory: the RK628D has it on chip. |
| 12 | USB-C fast-charge (PD) power request | WCH CH224A (CH224K successor, same pinout) | $0.26 | Listing for the CH224K: [LCSC C970725](https://www.lcsc.com/product-image/C970725.html?whichImg=0), 1,000+. Check the CH224A price. |
| 13 | Two 6–17 V to 5 V, 3 A converters (module and everything else) | Silergy SY8303AIC × 2 | $0.66 | Listing: [LCSC C97054](https://www.lcsc.com/product-detail/C97054.html), $0.30–0.36 at 1,000+, × 2 |
| 14 | USB-C socket, locking DC socket, two inductors, input protection | | $1.05 | Assumption |
| 15 | Resistors, capacitors, LEDs, button (about 150 parts) | | $1.00 | Assumption: about $0.005 each, LCSC's typical price for small passives |
| 16 | Circuit board, 4 layers, about 80 × 80 mm | | $1.00 | Listing: JLCPCB priced 500 boards of 100 × 100 mm, 4 layers, at $353, so $0.71 each ([JLCPCB](https://jlcpcb.com/news/discount-on-quality-4-layer-pcbs), March 2024) |
| 17 | Assembly and test | | **$4.50** | Assumption, built on a listing. JLCPCB charges $0.0017 per solder joint plus an $8 setup and a $1.50 stencil ([JLCPCB](https://jlcpcb.com/help/article/pcb-assembly-price)). About 1,000 joints gives $1.70. Add hand soldering of the jacks, X-ray inspection of the RK628D, fees for less common parts, fitting the module, and a power-on test: about $4.50. |
| 18 | Case | Aluminium extrusion with end plates | **$5.00** | Assumption. Off-the-shelf extruded cases are $6–12 at US distributors ([Jameco Hammond 1455D802](https://www.jameco.com/z/1455D802-Hammond-Manufacturing-Extruded-Aluminum-Enclosure-with-Plastic-End-Panels-80x45x25mm_2404167.html), $6.15 at 250+; [DigiKey Hammond 1455CS802](https://azcus.digikey.com/en/products/detail/hammond-manufacturing/1455CS802/21844204), $11.58 at 25). A custom profile from a Chinese extruder would cost less. |
| 19 | Box, insert, label with QR, quick-start card | | $1.50 | Assumption |
| 20 | USB-C power supply in the box | 20 W PD charger | $3.00 | Assumption. Optional: leaving it out saves $3. |
| 21 | Shipping China → US warehouse | | $1.00 | Assumption: a sea or air consolidated shipment of about 0.4 kg per unit |
| | **Subtotal** | | **$71.90** | |
| 22 | Scrap and failed units, 3% | | $2.15 | Assumption |
| | **Landed unit cost, before import duty** | | **about $74** | |
| 23 | **US import duty** | | **$0–17?** | **Update Oct 24: JLCPCB's checkout charged 35% on the board order (HS 847330); see [shipping and duties](#shipping-and-us-duties-from-jlcpcbs-checkout-oct-24-2026).** Originally: **Not known.** Duties on Chinese electronics have changed often. At 25% of about $68 customs value it adds about $17 per unit. Ask a customs broker for the rate on this product's tariff code. |
| | **Landed unit cost, with 25% duty** | | **about $91** | |

## JLCPCB quote for the rev A board, 500 units (Oct 24, 2026)

An instant quote on JLCPCB's site for the finished rev A files (`kicad/fab/`), replacing the estimates for the
circuit board, its parts and its assembly (items 2, 3, 5, 7–16 and the JLCPCB part of item 17 above). Not
ordered. The quote file is saved in the JLCPCB account as "relay-gerbers".

**Order set up as:** 500 boards as 125 panels of 2 × 2 (JLCPCB's suggestion for volume), 4 layers, 120 × 100 mm,
1.6 mm, FR4 TG155, ENIG, JLC04161H-3313 stackup, 0.15 mm vias epoxy-filled and capped, standard assembly on both
sides, parts from JLCPCB/LCSC stock, 5–6 day build.

| | Order total | Per board | Notes |
|---|---|---|---|
| Circuit boards | $1,560.94 | $3.12 | $672 of it ($1.34 a board) is what the 0.15 mm filled vias force: the via size ($345.71), epoxy filling ($172.86), a four-wire Kelvin test ($99.91), TG155 ($34.57) and the plating method ($18.94). ENIG is $162.50 ($0.33). |
| Assembly fees | $765.58 | $1.53 | Setup $51.50, stencil $16.54, feeder loading $75.95, SMT $508.20, hand soldering $3.61, manual assembly $66.13, fixture $41.35, packaging $2.30. |
| Parts in stock (52 lines) | $4,921.84 | $9.84 | JLCPCB's own prices, including their spares. |
| Parts short at 500 (6 lines) | $3,804.35 | $7.61 | Priced from the same page but not in the total, as JLCPCB doesn't have enough stock: magjack J301 ($3.42 a board), RK628D ($2.36; 27 in stock), two buttons ($1.09), four inductors ($0.74). These need JLCPCB's pre-order or global sourcing, or a stocked substitute. |
| Fitting the short parts | — | ~$0.20 | Assumption: they're left out of the assembly fees above. |
| **Board, assembled** | **≈ $11,050** | **≈ $22.30** | Before shipping (65.6 kg for the order). |

### Shipping and US duties, from JLCPCB's checkout (Oct 24, 2026)

The 500-board order was saved to the cart and taken to the shipping step of checkout (not submitted), shipping to
the US with duties paid by JLCPCB (DDP). Declared as "Development Board", HS code 847330.

| Shipping method (DDP) | Shipping | Duties and taxes | Disbursement fee | Order total |
|---|---|---|---|---|
| UPS Express Saver, 2–4 days | **$758.54** | $2,536.93 | $63.42 | **$10,607.25** |
| FedEx Express, 2–5 days | $884.89 | $2,536.93 | $63.42 | $10,733.60 |
| DHL Express, 2–4 days | $947.83 | $2,536.93 | $50.74 | $10,783.86 |

**The duty is exactly 35% of the goods value** ($2,536.93 on $7,248.36), whatever the shipping method, plus a
fee of 2.5% of the duty (UPS, FedEx). The order weighs 65.6 kg.

Those totals leave out the six short part lines ($3,804.35), so the whole board order, with them added at the same
35% duty, is:

| Per board | |
|---|---|
| Board, assembled (all parts) | $22.31 |
| Shipping, UPS DDP | $1.52 |
| US duty, 35% | $7.74 |
| Duty disbursement fee | $0.19 |
| **Board, landed in the US** | **≈ $31.75** |

That's $15,776 for the 500 boards.

**What 35% does to the unit cost.** The per-unit table assumed 25% on the whole product. If everything from China
(module, Wi-Fi card, antennas, case, box, charger) also pays 35%, the duty is about $27 a unit (about $8 on the
board, about $19 on the rest), and:

| | Before duty | With duty |
|---|---|---|
| Rev A as quoted, 35% duty | about $85 | **about $112** |
| Rev B parts changes, 35% duty | about $78 | about $103 |

So with today's 35% rate, $90 isn't reachable by board changes alone: the duty is now larger than the whole
carrier board. The levers are the module price, which product pays which rate (ask a customs broker whether a
different HS code fits, and whether the module, made by Radxa, is cheaper to import separately), and assembling
the final product somewhere other than China.

**Against the estimate:** the same items were estimated at $13.11 a board ($11.41 of parts and board, plus $1.70
of JLCPCB assembly), so the quote is **about $9.20 a board higher**. Replacing them in the per-unit table:

| | Estimate (Oct 22) | With the quote |
|---|---|---|
| Subtotal | $71.90 | **$81.09** |
| Scrap and failed units, 3% | $2.15 | $2.43 |
| **Landed unit cost, before import duty** | about $74 | **about $83.50** |
| US import duty at 25% of customs value | about $17 | about $19.50 |
| **Landed unit cost, with 25% duty** | about $91 | **about $103** |

**Where the extra $9.20 comes from** (quote against estimate, per board): the magjack (+$1.62), the Molex HDMI
sockets (+$1.56), the TE M.2 socket (+$0.79), the two E-Switch buttons (+$1.05; generic 5.2 mm buttons are about
$0.02), the bigger board with filled 0.15 mm vias (+$2.12), the ten 22 µF capacitors ($1.36 at JLCPCB's price,
+$1.2 over the passives estimate), and the second-tier regulators and USB power switch (AP22804, 2 × TPS563201,
about +$0.6). The RK628D ($2.36), module connectors ($1.83) and DC socket ($0.62) came in as estimated.

## Where the $299 goes (direct sales from our own web shop)

| | Per unit | Source |
|---|---|---|
| Price | $299.00 | |
| Card payment fee | −$9.00 | Assumption: about 2.9% + $0.30, typical for Stripe or Shopify Payments |
| Shipping to the customer (free shipping) | −$10.00 | Assumption: US ground, small box |
| Warranty and returns reserve, 3% | −$9.00 | Assumption |
| **Net revenue** | **$271** | |
| Landed unit cost | −$84 to −$112 | Rev A as quoted (Oct 24), from no duty to the 35% charged at checkout; the estimate was $74–91 |
| **Gross profit per unit** | **$159–187** | Before one-time costs, support time and marketing |

**Through a dealer** such as B&H: dealers usually take 25–40% of the price. We'd receive about $180–225 a unit,
and gross profit drops to about $88–150. That's an assumption: get the actual terms from dealers.

The "about $90 target" in DESIGN.md is roughly a third of the price. It's a rule of thumb that leaves room for
dealer discounts later. Rev A as quoted meets it without duty (about $83.50) but not with duty: about $103 at 25%,
and about $112 at the 35% JLCPCB's checkout charged. Board changes alone can't close that gap; see
[shipping and duties](#shipping-and-us-duties-from-jlcpcbs-checkout-oct-24-2026).

## One-time costs

| Item | Cost | Source |
|---|---|---|
| Stage A development kits | $115–255 plus shipping | [DESIGN.md](DESIGN.md#prototype-plan) |
| Carrier board design tools, 2 rounds of 5–10 prototypes | $2–5k | Assumption: KiCad is free; prototype boards with the module and assembly cost $150–300 each |
| Emissions pre-scan | $2–5k | Assumption |
| FCC (US) and CE/RED (EU) testing and filing | $10–20k | Assumption: typical quotes for a Wi-Fi product using a pre-certified radio card. Get lab quotes. |
| Case: custom extrusion die and end-plate tooling | $1–3k | Assumption: an extrusion die costs far less than an injection mould ($5–15k) |
| **Total** | **about $15–33k** | |

Spread over the first 500 units, that's $30–66 a unit; over 1,000 units, $15–33. It's paid once and isn't part of
the per-unit cost above.

## How to bring it down

| Change | Saves per unit | Confidence |
|---|---|---|
| Module volume price from Radxa directly | $2–5 | Needs a quote |
| ~~RK3566 module instead of RK3568~~ | Done: the Radxa CM3 | Saved about $8 against the MYIR list price, plus the Ethernet chip and a regulator |
| Leave the USB-C charger out of the box | $3 | Our choice |
| Wi-Fi card bought at factory price | $2–4 | Needs a quote |
| Processor directly on our board, at 1,000+ units | $15–25 | Adds a $20–40k+ one-time design cost |
| **Rev B parts**, all from the Oct 24 quote: a stocked LCSC gigabit magjack such as HanRun HR911130A (C54408) instead of the Pulse ($3.42 → about $1.80); LCSC HDMI sockets instead of Molex ($1.98 → $0.42); a generic M.2 E-key socket ($1.09 → $0.30); basic-library 5.2 mm buttons ($1.09 → $0.04) | about $5.00 | High: quoted prices. The magjack and HDMI swaps need new footprints. |
| **Rev B board:** 0.2 mm vias and no via-in-pad where the layout allows, which drops the filled vias, Kelvin test and TG155 surcharge | up to $1.34 | Medium: depends on whether the RK628D and module connectors can be fanned out without via-in-pad |
| Cheaper 22 µF capacitors (ten per board at $0.11 each from JLCPCB) | about $0.80 | Medium: check other LCSC basic parts |

With the rev B changes (about $6–7 a board), rev A's $83.50 drops to about **$77 before duty and about $95 with
25% duty**. Reaching $90 with a 25% duty also needs one of: no charger in the box ($3), a direct Radxa module
price ($2–5), or a factory-price Wi-Fi card ($2–4).

## To replace the assumptions

1. **Quotes:** Radxa (or Arace / RS) for RM116-D2E16W0 at 5, 100, 500 and 1,000. MYIR as a fallback.
2. **Wi-Fi card quote:** Seeed or a Realtek card maker, at 500 units.
3. **Customs broker:** the duty rate for this product.
4. ~~**JLCPCB quote** once a first BOM exists: upload the files at quantity 500.~~ Done Oct 24: see
   [the quote](#jlcpcb-quote-for-the-rev-a-board-500-units-oct-24-2026). Still open: prices for the six lines
   JLCPCB is short of at 500 (pre-order or global sourcing).
5. **Test lab quotes** for FCC and CE/RED.
