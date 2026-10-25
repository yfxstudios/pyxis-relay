# HDMI-in relay: design (rev 0, Oct 22, 2026)

The next relay: it takes HDMI from **any** camera, encodes it with low latency and serves it to the apps on the
same RTSP path as today. It also controls Blackmagic cameras over every channel they offer. The priority is a
**low unit cost**.

Status: architecture and part selection. No schematic yet. Prices marked *est.* are estimates to replace with
quotes; the rest come from a distributor listing, linked.

## Decisions in this revision

> **Update (Oct 22):** the module changed to the Radxa CM3 (RK3566); the RK628D bridge and 1080p60 stay.
> Landed unit cost now about $83.50 before import duty for rev A as quoted by JLCPCB at 500 units (Oct 24),
> about $77 with the planned rev B part changes. JLCPCB's checkout charged 35% US duty on the board order, which
> would put the landed cost at about $112 (rev B about $103) ([COST.md](COST.md)).

1. **RK3568 + RK628D bridge, not RK3588.** This is the same processor as today's R5C, so FriendlyWrt, MPP, the
   factory image, first boot and the HDMI player carry over. Rockchip's own **RK628D** bridge converts HDMI to the
   camera port. It costs [$2.34 at 1,000](https://datasheet.lcsc.com/lcsc/2401261533_Rockchip-RK628D_C2843533.pdf), against about
   $20–40 more per unit for an RK3588 module.
2. **1080p60 output stream** (confirmed Oct 22). The RK3568 encodes H.264/H.265 at 1080p60. That's plenty for monitoring on phones
   and tablets. The RK628D accepts up to 4K60 and can scale down in hardware
   ([CNX](https://www.cnx-software.com/2020/12/21/rk628d-adds-hdmi-input-extra-video-outputs-to-rockchip-processors/)),
   so a camera sending 4K still works. Its scaler limits are 1/4 bilinear and 1/6 averaging; confirm against the
   datasheet.
3. **A bought module on our carrier board for the first runs. Processor directly on our board only at volume.**
   Routing DDR memory is where custom boards fail and where the design cost goes. See [Cost](#cost).
4. **SDI goes on an optional add-on board.** The base unit stays cheap. A board-to-board header reserves the
   signals.
5. **The previous NanoPC-T6 (RK3588) prototype is superseded** on cost. Return to RK3588 only if a 4K stream to
   viewers becomes a requirement.

## Block diagram

```
                    HDMI in (full size, locking)                      HDMI out (full size)
                          │   CEC ─────────────┐                          ▲  ~1–2 frames, no encode
                          ▼                    │                          │
  camera ──HDMI──►  ┌──────────┐  MIPI CSI-2  ┌─┴──────────────────────────┴─┐  PCIe 2.0  ┌──────────────┐
                    │  RK628D  │──4 lanes────►│     RK3568 module            │──────────►│ RTL8822CE     │
                    │ HDMI→CSI │  YUV422      │ VICAP → MPP H.264/H.265 enc  │            │ Wi-Fi 5 AP +  │──► 2 antennas
                    │ + scaler │◄──I2C────────│ MediaMTX → RTSP over Wi-Fi   │   UART     │ Bluetooth 5   │
                    └──────────┘  EDID/ctrl   │ FriendlyWrt (as today)       │◄──────────►│ (BLE control) │
                                              └─┬─────────────┬──────────────┘            └──────────────┘
                                                │ RGMII       │ board-to-board header (optional SDI board)
                                          ┌─────▼─────┐   ┌───▼─────────────────────────────┐
  camera ──Ethernet (REST control)───────►│ GbE PHY   │   │ SDI board (phase 2): 3G-SDI in  │
                                          │ + magjack │   │ for video, SDI out for control  │
                                          └───────────┘   └─────────────────────────────────┘
  Power: USB-C PD (CH224K, 9/12 V) or 7–17 V locking DC (D-tap / V-mount / NP-F)
         → protection → wide-input buck → 5 V → module PMIC and 3.3/1.8/1.2 V rails
```

## Camera control: Ethernet, Bluetooth, HDMI and SDI

The apps' camera control is built on the REST API today. Blackmagic cameras have four control channels, and the
relay can carry each of them. The apps would talk to the relay, and the relay would pick whichever channel the
connected camera supports.

| Channel | Cameras | How documented | Extra hardware | Plan |
|---|---|---|---|---|
| **Ethernet (REST)** | Newer cameras: PYXIS, URSA Cine, Cinema Camera 6K, Studio, URSA Broadcast G2 | Official | None (today's) | v1, as now |
| **Bluetooth LE** | Pocket cameras, URSA Mini Pro, and others; build the model list in testing | Official ([Blackmagic developer docs](https://www.blackmagicdesign.com/developer/products/camera/sdk-and-software)); same parameter set as the SDI protocol | **None:** the RTL8822CE already has Bluetooth 5 | **v1** |
| **HDMI (CEC)**, as the ATEM Mini does | Pocket 4K / 6K family | **Not documented.** Partly reverse-engineered ([part 1](https://blog.brixit.nl/reverse-engineering-the-bmd-camera-hdmi-control/), [part 2](https://blog.brixit.nl/reverse-engineering-the-bmd-camera-hdmi-control-part-2/)) | About $0.10: route the CEC pin to a GPIO, and make the EDID programmable | Wire it in rev A; ship as experimental |
| **SDI** (return feed), as ATEM SDI switchers do | Cameras with an SDI **input**: URSA Broadcast, Studio cameras, URSA Mini Pro, URSA Cine | Official: SDI Camera Control Protocol, ancillary packets DID/SDID 0x51/0x53 on VANC line 16 ([ATEM manual](https://www.manualslib.com/manual/1876502/Atem-Constellation-8k.html?page=192)) | SDI **output** into the camera, carrying a video frame with the packets: serializer + small FPGA, about $30–40 *est.* | Phase 2, on the SDI add-on board |

**HDMI control.** The ATEM Mini controls Pocket 4K/6K cameras over the HDMI cable's CEC wire, using Blackmagic's
own vendor messages (vendor ID `7C:2E:0D`). The camera only joins when the sink's EDID carries the right vendor
block and CEC physical address.

One person has decoded part of it with a Pi Pico on an HDMI breakout. They mapped 35 opcodes and changed gain;
tally (`0x02`) and record start/stop (`0x03`) were decoded earlier. Parts are still unknown, and the camera
dropped off CEC after some replies. It's cheap to wire in but risky to promise, and a firmware update could
change it.

**What it means for the board:**
- Route HDMI-in **CEC** to an SoC GPIO through an open-drain transistor, with the 27 kΩ pull-up the CEC spec
  sets.
- Make the **EDID** fully writable, either by the RK628D or by a small EEPROM on the HDMI DDC lines.
- Bring **HPD** under software control, so the relay can make the camera re-read the EDID.

**Bluetooth vs. HDMI.** Every camera with HDMI control (the Pocket family) also has Bluetooth control, and
Bluetooth is documented. **Bluetooth is the primary path for those cameras.** HDMI control is worth its 10 cents
for three things: it needs no pairing, it can't be disrupted by radio interference, and it carries tally.

**SDI.** The control signal travels into the camera's SDI **input**, embedded in a video frame (the ATEM's program
return), so the relay would have to *transmit* SDI.

Most cameras with an SDI input already have the REST API over Ethernet. SDI control mainly adds older URSA Mini
Pro models, plus installs that already run SDI. It belongs on the add-on board with SDI video input, not in the
base unit.

**App side:** Bluetooth and SDI use the same Blackmagic parameter format (group, parameter, type, value). One
encoder in the relay serves both. The apps keep sending the same commands they send today, and the relay
translates them.

## Video path and latency

`HDMI → RK628D (scale if needed) → CSI-2 4-lane YUV422 → RK3568 capture → MPP encoder → MediaMTX → RTSP → app decode`

**Encoder settings for low latency:**
- H.264 High, no B-frames.
- Intra-refresh, or a 1 s GOP, rather than large periodic keyframes.
- Slice output, if MPP sends slices before the frame is complete.
- Constant bitrate of about 8–12 Mb/s at 1080p60. The relay README has the Wi-Fi math for several viewers.

**Transport and apps:**
- RTSP over UDP on the Wi-Fi.
- The apps' decode buffer cut to one frame when the source is HDMI.

**Target:** under 100 ms glass to glass. For reference, Hollyland's Mars 4K measures about 66 ms over HDMI and up
to 83 ms in its app ([RedShark](https://www.redsharknews.com/hollyland-mars-4k-reviewed-for-when-wireless-hd-just-doesnt-cut-it)).
Measure it on the prototype first.

**HDMI out** shows the captured frames directly on the RK3568's display output (DRM), with no encode or decode in
between. That's about 1–2 frames of delay and no extra parts; it's cheaper than a splitter chip. The HDMI player
already drives DRM, and it can apply the monitor LUT there.

**Audio:** the RK628D brings HDMI audio out over I2S. Route it to the module now; the apps don't use audio yet.

## Main parts

| Function | Part | Unit cost | Notes |
|---|---|---|---|
| Processor | **RK3568 module**, 2 GB RAM, 16 GB eMMC | $43 list (MYIR) | See [Module shortlist](#module-shortlist). |
| HDMI → CSI | **Rockchip RK628D** | [$2.34 at 990+](https://datasheet.lcsc.com/lcsc/2401261533_Rockchip-RK628D_C2843533.pdf) | HDMI 2.0 in, 4K60 YUV420; CSI out 4 × 1.2 Gb/s; scaler. Supported in Rockchip's vendor kernel. |
| Wi-Fi + Bluetooth | **RTL8822CE** | $7–10 *est.* | Same chip as today: proven as an access point on FriendlyWrt. M.2 card for rev A; a pre-certified solder-down module for production. |
| Ethernet | GbE PHY (RTL8211F class) + integrated magnetics jack | $3–4 *est.* | |
| Connectors | 2 × full-size HDMI, RJ45, USB-C, locking DC, 2 × RP-SMA | $4–6 *est.* | |
| Power | CH224K PD sink, reverse/surge protection, 4.5–28 V input 5 V/3 A buck | $2–3 *est.* | Peak budget about 7 W: RK3568 3–5 W, RK628D under 1 W, Wi-Fi 1–2 W. |
| HDMI ESD, CEC transistor, EDID EEPROM | TPD12S016 class, small FET, 24C02 | $1 *est.* | |
| PCB, 4 layers, about 80 × 80 mm | | $3–5 *est.* | No DDR on our board, so 4 layers are enough. |
| Assembly and test | | $6–10 *est.* | |
| Case | Injection-moulded, or aluminium extrusion with end plates | $3–6 *est.* | Moulding tooling is a one-time $5–15k *est.*. An extrusion needs almost no tooling and conducts heat, so it lets us skip the fan. |

## Unit cost target

The line-by-line breakdown, with a source or an assumption for each price, is in [COST.md](COST.md).

**$299 retail → landed unit cost of about $90 or less**, about a third of the price. That leaves room for
packaging, shipping, payment fees, returns, support and margin. Today's estimate is $80–115, so the high end must
come down. In order of effect:

1. **RK3566 instead of RK3568.** It has the same 1080p60 encoder, 4-lane camera input, one Gigabit Ethernet and a
   PCIe 2.0 lane for Wi-Fi, which is all this product uses. It drops the RK3568's second Ethernet and extra PCIe
   and SATA, which we don't need. The chip and modules cost less; get quotes. One candidate:
   Geniatech SoM-3566-OSM, LGA, 2 GB / 8 GB, 4-lane CSI, PCIe 2.1
   ([spec](https://file.geniatech.com/thcdownloads/geniatech/specification/GTC(HF)-SPEC(EN)-SoM-3566-OSM-20220624-PDD01.pdf)).
2. **Volume quotes on the module.** MYIR's $43 is a list price and they offer bulk discounts.
3. **A solder-down Wi-Fi/Bluetooth module** instead of an M.2 card, with no M.2 socket.
4. **An aluminium-extrusion case:** almost no tooling, and no fan.
5. **The processor directly on our board** at about 1,000+ units: $65–85 by the estimate below.

## Module shortlist

> **Superseded (Oct 22):** the module is now the **Radxa CM3 (RK3566, RM116-D2E16W0)**. Its full pinout, power
> design and layout guide are public, it costs less, and it carries the Ethernet PHY. See
> [REV_A_SPEC.md](REV_A_SPEC.md#1-the-module-radxa-cm3) and [COST.md](COST.md). The table below is kept for the
> record; MYIR stays the fallback.

Every module must bring these out on its pins: 4-lane MIPI CSI, RGMII (one GbE), PCIe 2.0 x1 (Wi-Fi), HDMI TX,
I2C, I2S, UART and a few GPIOs. Check each against its pin list before choosing. For comparison, the bare RK3568
chip is about [$17 at LCSC](https://datasheet.lcsc.com/lcsc/2401261533_Rockchip-RK3568_C2938930.pdf).

| # | Module | Price | Form | Notes |
|---|---|---|---|---|
| **1 (pick)** | **MYIR MYC-LR3568B2**, 2 GB LPDDR4, 16 GB eMMC | **$43** list; RK3568J industrial version $65 ([MYIR](https://www.myirtech.com/news_list.asp?id=900)) | 381-pin LGA, 43 × 45 mm, PMIC and EEPROM on the module | Cheapest credible module. It solders straight down, so there's no connector cost. Sold through Mouser, so sourcing is easy. LGA needs X-ray inspection at assembly; JLCPCB and PCBWay do it. **We'd add the RK628D driver to our kernel** (it's in Rockchip's SDK). |
| 2 (fallback) | **Firefly Core-3568J**, 2 GB / 32 GB | $129 retail, in stock ([Firefly](https://www.firefly.store/products/core-3568j-ai-core-board-with-rockchip-64-bit-processor-rk3568)); ask for a volume price | Edge connector | **Same software as the Stage A board**, and Firefly's kernel already supports the RK628D. Lowest risk, highest price. |
| 3 (quote) | **Rongpin LGA-RK3568 / RP-RK3568** | from $21 on Alibaba (unverified) ([listing](https://www.alibaba.com/product-detail/Rockchip-RK3568-development-board-RK3568-core_1601022550076.html)) | LGA or castellated | Cheapest if real. Documentation and long-term supply are unknown: get a datasheet and a sample. |
| 4 (quote) | **EmbedFire LubanCat-2CF** | not published | Card edge | Good English documentation ([EmbedFire](https://doc.embedfire.com/linux/rk356x/quick_start/en/latest/quick_start/lubancat/lubancat2.html)). Ask for a price. |
| – (dropped) | Geniatech SOM-3568-SMARC | $128–248 ([Geniatech](https://shop.geniatech.com/product/smarc-module/)) | SMARC 2.1 | A standard form factor would allow second sources, but it's too expensive. |

**Plan:**
- Ask MYIR for a quote at 100 / 500 / 1,000 units, plus a supply-life commitment and the module's full pin list.
- Ask Firefly for a volume price on the Core-3568J.
- Ask Rongpin and EmbedFire for datasheets and prices.
- Draw the carrier for MYIR only after its pin list confirms 4-lane CSI, RGMII and PCIe.

## Cost

**Unit cost at about 500 units (all estimates):**

| | Module on carrier (rev A–B) | Processor on our board (rev C, at volume) |
|---|---|---|
| Processor, memory, storage | $43–65 (MYIR list; volume quote pending) | $28–35 (RK3568, 2 GB DDR4, 8 GB eMMC, RK809 PMIC) |
| Everything else above | $35–50 | $35–50 |
| **Unit total** | **about $80–115** | **about $65–85** |
| One-time cost | Carrier design and protos about $5–15k; emissions pre-scan $2–5k | Plus a 6–8 layer DDR layout and its verification: $20–40k+ |

At $299 retail, the module route leaves room for packaging, support and margin. Move the processor onto our own
board only once volume clearly pays back the extra one-time cost: roughly $20–30 saved per unit, so about 1,000+
units.

**Certification:** a pre-certified Wi-Fi module avoids a full radio test; the RTL8822CE M.2 card's own FCC ID
covers only a host it was certified with. The finished product still needs FCC Part 15B, CE and RED test reports.
Get quotes from a lab before rev B.

## Prototype plan

**Stage A: development kits (updated Oct 22 for the Radxa CM3; about $118 core plus shipping, $255 with the 4-lane check).**
One-time prototype costs, not unit costs. The core kit runs the production module on Radxa's own carrier, so the
software built here (OpenWrt or Radxa OS, device tree, RK628 driver, encoder, relay) carries straight onto our board.

**Shopping list for the dev unit (Oct 22): two orders.** No US retailer found stocks the Radxa parts: DigiKey, Amazon
US and Ameridroid have no CM3, CM3 IO board or HDMI adapter (Mouser's search didn't load, so it's unchecked). So the three Radxa parts come from Asia, and
everything else is one DigiKey order.

*Order 1: DigiKey (US), about $44*

| Item | DigiKey part | Price | Stock (Oct 22) |
|---|---|---|---|
| 12 V / 2 A wall supply, 5.5 × 2.1 mm, centre positive (for the IO board) | [179-SWI24-12-N-P5-ND](https://www.digikey.com/en/products/detail/bel-power-solutions/SWI24-12-N-P5/5415094) (Bel SWI24-12-N-P5) | $20.31 | 491 |
| HDMI-A to mini-HDMI cable, 6 ft (camera to the Radxa adapter) | [5600-FE-HHM14-06-ND](https://www.digikey.com/en/products/detail/my-cable-mart/FE-HHM14-06/24871529) | $9.51 | 82 |
| USB-serial adapter, 3.3 V (boot console) | [1528-5335-ND](https://www.digikey.com/en/products/result?keywords=1528-5335-ND) (Adafruit CP2102N Friend) | $5.95 | 827 |
| USB-A to micro-B cable, 3 ft (flashing through the IO board's OTG port) | [Q966-ND](https://www.digikey.com/en/products/result?keywords=3025030-03) (Qualtek 3025030-03) | $2.97 | 31,116 |
| Cat6 patch cable, 3 ft (IO board to today's relay) | [TL922-ND](https://www.digikey.com/en/products/detail/eaton-tripp-lite/N201-003-BL/1533238) (Tripp Lite N201-003-BL) | $5.60 | 4,317 |

*Order 2: Radxa parts from Asia, about $89 plus shipping (two stores)*

| Item | Store | Price |
|---|---|---|
| Radxa CM3, 2 GB / 16 GB, Wi-Fi | [Keyestudio](https://www.keyestudio.com/products/radxa-rock-3-compute-module-core-board-adapts-radxa-cm3-soc-rockchip-rk3566-2gb-16gb-wifi-bt) (ships from China) | $49 |
| Radxa CM3 IO Board | [Arace](https://arace.tech/products/radxa-cm3-io-board) (ships from Hong Kong) | $24.99 |
| Radxa 4K HDMI IN to MIPI CSI adapter (mini-HDMI input) | [Arace](https://arace.tech/products/radxa-4k-hdmi-in-to-mipi-csi-adapter), same order | $15 |

The IO board's DC jack is a DC-044A (schematic page 15), usually 5.5 × 2.0/2.1 mm. Check the board before plugging in
the supply. Ask Keyestudio for the CM3's board revision (V1.32+ matches our carrier; older still works for the dev
unit, with four signals on other pins).

**Core kit (details):**

| Item | Price | Notes |
|---|---|---|
| **Radxa CM3**, 2 GB / 16 GB eMMC, Wi-Fi | $49 at [Keyestudio](https://www.keyestudio.com/products/radxa-rock-3-compute-module-core-board-adapts-radxa-cm3-soc-rockchip-rk3566-2gb-16gb-wifi-bt) (in stock, ships from China); $76 [OZ Robotics](https://ozrobotics.com/shop/rock-3-compute-module-cm3-2gb-16gb-with-wifi-bt/); $99 [SB Components](https://shop.sb-components.co.uk/products/rockpi-cm3) (UK) | The production module; the Wi-Fi version is fine for development. Check the board revision is V1.32 or later, since our carrier follows that pinout. |
| **Radxa CM3 IO Board** | $24.99 at [Arace](https://arace.tech/products/radxa-cm3-io-board) (in stock) | Radxa's reference carrier. Its schematic is in `datasheets/SCH_CM3_IO_V1.35.pdf`. Two 15-pin, 1 mm camera connectors, **2 lanes each**; HDMI out, Gigabit Ethernet, PCIe x1, micro-USB OTG for flashing; 12 V DC in. |
| **12 V / 2 A DC supply**, 5.5 × 2.1 mm, centre positive | see Parts Express ([120-078](https://www.parts-express.com/12-VDC-2A-Switching-AC-Power-Adapter-with-2.1-x-5.5mm-Center-Plug-120-078)), about $10 *est.* | For the IO board; UL listed. |
| **Radxa 4K HDMI IN to MIPI CSI-2 adapter** (RK628H) | **$15 at [Arace](https://arace.tech/products/radxa-4k-hdmi-in-to-mipi-csi-adapter)** (in stock; same order as the IO board). $33–42 on AliExpress. | Radxa's own board ([docs](https://docs.radxa.com/en/accessories/display/hdmi-in-to-mipi-csi2)), the same RK628 family as our RK628D, with the same Rockchip driver. Includes a 15-pin 1 mm cable for 2-lane sockets like the IO board's. |
| Mini-HDMI plug to full-size HDMI socket adapter | $2.95, [Adafruit 2819](https://www.adafruit.com/product/2819) | The Radxa adapter's HDMI input is mini-HDMI; this gives it a full-size socket for normal camera cables. No full-size RK628 board fits the IO board's 15-pin camera socket directly (see below). |
| 3.3 V USB-serial adapter | about $11, [Adafruit CP2102N Friend (5335)](https://adafruit.com/product/5335) | Boot console (3.3 V logic). |
| Raspberry Pi Pico + 2 HDMI breakout boards | $4 Pico ([Adafruit 4864](https://www.adafruit.com/product/4864), out of stock there; any [Raspberry Pi reseller](https://www.raspberrypi.com/products/raspberry-pi-pico/)) + breakouts | Only for the HDMI camera-control (CEC) tests, which also need a Pocket 4K/6K. Buy later. |
| HDMI cables; an HDMI source that can do 1080p60 | on hand | |

**Full-size HDMI:** the only RK628 board found with a full-size socket is Firefly's (photo on
[Firefly's page](https://www.firefly.store/products/tf-hdmi-mipi-csi-drive-boardhdmi_mipi): Type A socket, RK628D, 30-pin
FPC). Its camera cable is Firefly's 30-pin type with no published pinout, so it doesn't plug into the CM3 IO board's
15-pin socket. It does pair natively with the Firefly ROC-RK3566-PC in the optional kit below. For the CM3 kit, the
Radxa adapter plus the $3 mini-to-full-size adapter is the practical route.

**Two catches with the core kit:**
- **2 lanes, not 4.** The IO board only brings out 2-lane camera sockets. Radxa rates the adapter at up to
  1440p30 on 2 lanes, so plan on **1080p30** for the core-kit tests. 1080p60 needs about 2.4 Gb/s, right at the
  2-lane limit. Everything else is proved: driver, encoder, latency path, relay software. Only the 4-lane wiring
  waits for our own board, which has it.
- **The CM3 isn't on the adapter's supported list.** Radxa supports it on the ROCK 3C, which uses the same RK3566
  chip and a 2-lane socket of the same kind, through a Radxa OS device-tree overlay. Porting that overlay to the
  CM3 IO board is our first software task. Check the 15-pin socket pinouts match before plugging in: the IO-board
  schematic, page 11, against the adapter's documentation.

**Optional 4-lane check (about $140), if you want 1080p60 proven before the carrier is built:**

| Item | Price | Notes |
|---|---|---|
| **Firefly ROC-RK3566-PC** | from $119 at [Firefly](https://www.firefly.store/products/roc-rk3566-pc-quad-core-64-bit-mini-computer-1) | Same RK3566 chip; Firefly lists it as supported by its RK628D board, with the driver in its images. |
| **Firefly HDMI to MIPI CSI board** (RK628D, the exact chip on our carrier) | $19 at [Firefly](https://www.firefly.store/products/tf-hdmi-mipi-csi-drive-boardhdmi_mipi) (71 in stock; includes 30-pin and 30-to-24-pin cables) | Firefly publishes no schematic: use it only with Firefly boards. |

**For the first tests, don't set up Wi-Fi.** Plug the IO board's Ethernet into today's R5C relay, so the proven
Wi-Fi access point and the apps stay as they are; only the video source changes.

**Bluetooth and HDMI control** need a Blackmagic Pocket 4K or 6K: borrow or rent one for a day.

- Prove, in order:
  1. Radxa's OpenWrt 25.12 build for the CM3 IO board boots ([Radxa downloads](https://docs.radxa.com/en/som/cm/cm3/download)).
     The RK628 driver and overlay are easier to start on Radxa OS, then move to OpenWrt.
  2. The RK628 driver and overlay on the CM3: 1080p30 capture on 2 lanes, and 4K→1080p scaling.
  3. Hardware encode feeding MediaMTX, with glass-to-glass latency measured using a running clock on screen.
  4. HDMI out showing the captured frames.
  5. With the optional Firefly kit: 1080p60 on 4 lanes.
- **Bluetooth control:** works on today's R5C. Its RTL8822CE has Bluetooth, so this is software only. It needs a
  camera with Bluetooth control to test.
- **HDMI (CEC) control:** a Pi Pico and an HDMI breakout, as in the reverse-engineering write-up. Needs a Pocket
  4K or 6K.
- Also measure today's camera-stream latency, as the baseline.

**Stage B: carrier rev A.**
- KiCad, 4 layers, using the chosen module.
- Everything in this document, including the CEC, EDID and HPD wiring and the SDI header (not populated).
- Quantity 5–10 assembled at JLCPCB or PCBWay.
- Bring-up checklist: power rails, boot, Ethernet, Wi-Fi AP, HDMI in, HDMI out, Bluetooth, CEC, thermals in the
  case.

**Stage C: rev B and production.**
- Fixes from rev A, and a pre-certified Wi-Fi module.
- Emissions pre-scan, the case, then the certification run.
- The factory image gains a board variant (device tree), and provisioning stays the same.

## Open questions

- **Which cameras can we test?**
  - Bluetooth and HDMI control need a Pocket 4K or 6K (or another Bluetooth model).
  - SDI control needs a camera with an SDI input.
  - The PYXIS uses Ethernet only.
- **Module vendor:** get quotes and long-term availability from two or three RK3568 module makers. The carrier
  should fit one module footprint, with a second source checked.
- **Is SDI video input needed in v1?** Many cinema cameras output SDI only. If early customers need it, the
  add-on board moves up.
- **Should the apps support video-only cameras?** For non-Blackmagic cameras, the apps need to hide the control
  menus and keep the picture, LUTs and capture.
