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
| 23 | **US import duty** | | **$0–17?** | **Not known.** Duties on Chinese electronics have changed often. At 25% of about $68 customs value it adds about $17 per unit. Ask a customs broker for the rate on this product's tariff code. |
| | **Landed unit cost, with 25% duty** | | **about $91** | |

## Where the $299 goes (direct sales from our own web shop)

| | Per unit | Source |
|---|---|---|
| Price | $299.00 | |
| Card payment fee | −$9.00 | Assumption: about 2.9% + $0.30, typical for Stripe or Shopify Payments |
| Shipping to the customer (free shipping) | −$10.00 | Assumption: US ground, small box |
| Warranty and returns reserve, 3% | −$9.00 | Assumption |
| **Net revenue** | **$271** | |
| Landed unit cost | −$74 to −$91 | Table above |
| **Gross profit per unit** | **$180–197** | Before one-time costs, support time and marketing |

**Through a dealer** such as B&H: dealers usually take 25–40% of the price. We'd receive about $180–225 a unit,
and gross profit drops to about $88–150. That's an assumption: get the actual terms from dealers.

The "about $90 target" in DESIGN.md is roughly a third of the price. It's a rule of thumb that leaves room for
dealer discounts later. Without duty this design meets it; with a 25% duty it's about $1 over.

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

## To replace the assumptions

1. **Quotes:** Radxa (or Arace / RS) for RM116-D2E16W0 at 5, 100, 500 and 1,000. MYIR as a fallback.
2. **Wi-Fi card quote:** Seeed or a Realtek card maker, at 500 units.
3. **Customs broker:** the duty rate for this product.
4. **JLCPCB quote** once a first BOM exists: upload the files at quantity 500.
5. **Test lab quotes** for FCC and CE/RED.
