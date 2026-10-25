# HDMI-in relay: production plan (draft 1, Oct 24, 2026)

How units get built after rev A: what JLCPCB does in China, what our team does in California, the 50-unit pilot,
and the case. Costs come from [COST.md](COST.md); the board from [kicad/](kicad/README.md); the case from
[case/](case/README.md).

## Who does what

**JLCPCB (Shenzhen)** makes and assembles the carrier board: both sides of SMT, X-ray of the RK628D, and the
through-hole parts they stock (DC jack, JST battery connector, debug header). Boards ship to us by UPS with duty
paid (DDP).

**Our team (California)** turns boards into finished units:

| Station | Work | Time per unit (est.) |
|---|---|---|
| 1. Incoming check | Count boards, look for damage and missing parts (photo on a light box), log the JLCPCB lot | 1 min |
| 2. Hand soldering | Fit the parts JLCPCB can't: the Pulse magjack J301 on rev A (out of stock at JLCPCB). Rev B moves to a stocked jack JLCPCB can fit. | 3 min (rev A only) |
| 3. Module and Wi-Fi | Thermal pad and heatsink on the CM3, press the CM3 onto J701–J703, four M2.5 screws; Wi-Fi card into J501 with an M2 screw; two antenna leads onto the card | 4 min |
| 4. Flash | 12 V on the DC jack, then hold RECOVERY and plug USB-C to the PC (data only: the board does not run reliably from a PC port's 5 V). Run the flashing script (writes the image, sets the serial number, records the MACs). Several units can flash at once. The debug header J601 is 1.8 V: use a 1.8 V USB-UART adapter. | 1 min attended, 3 min machine |
| 5. Test | Run the test script (below); print the label only on PASS | 5 min, partly machine time |
| 6. Case and box | Board into the printed base, four screws, antennas into the bulkheads, light pipes, lid, label, box with the quick-start card | 4 min |

That's about **18 minutes of hands-on time a unit** (about $8–9 at $28 an hour, loaded), which replaces the $2.80
of "fit module, X-ray, test" in COST.md item 17.

**Why California assembly helps with duty.** JLCPCB's checkout charged 35% on the boards. Duty is paid on what
crosses the border from China, so anything we make or buy in the US doesn't carry it:
- the printed case, packaging and labels (made here: no duty);
- parts bought from US distributor stock (the distributor has already imported them).

The board, the module and the Wi-Fi card still come from China one way or another. On COST.md's numbers that cuts
the dutiable value from about $77 to about $68 a unit, so the duty from about $27 to about $24. A customs broker
should confirm the rate and the HS code for each item before the pilot. Don't mark units "Made in USA": the main
parts come from China; "Assembled in USA" is the accurate label.

## Stages

1. **Rev A bring-up (3 assembled prototypes, ordered Oct 24).** The [DESIGN.md bring-up
   checklist](DESIGN.md#prototype-plan): power rails, boot, Ethernet, Wi-Fi AP, HDMI in, HDMI out, Bluetooth,
   CEC, and thermals in the printed case. Fit-check the case on a real board.
2. **Rev B board.** Fixes from bring-up, plus the cost changes in [COST.md](COST.md#how-to-bring-it-down):
   stocked magjack (JLCPCB can fit it), LCSC HDMI sockets, generic M.2 socket and buttons, and, if layout allows,
   no via-in-pad. Also for the case: line the RJ45 front up with the USB-C and DC jack fronts (today it sticks out
   5.5 mm further).
3. **Pilot: 50 units on rev B.** Built with the stations above. Units go to friendly crews and to the emissions
   pre-scan.
4. **Production: 500.** Same flow, with an injection-moulded or extruded case if the printed one becomes the
   bottleneck.

## Pilot (50 units): what to buy

| Item | Qty | Where | Note |
|---|---|---|---|
| Carrier boards, assembled | 55 | JLCPCB | 10% spare for bring-up failures. Get the quote with rev B files. |
| Radxa CM3 RM116-D2E16W0 (2 GB / 16 GB, no Wi-Fi) | 52 | Radxa / Arace / Allnet | Check every module is board revision V1.32 or later. |
| RTL8822CE M.2 2230 card | 52 | Seeed or a US distributor | Buy from US stock to avoid paying the duty ourselves |
| Antennas: 2 × dual-band RP-SMA dipoles + 2 × IPEX MHF4/U.FL to RP-SMA bulkhead pigtails, 100 mm | 52 sets | Amazon / DigiKey | Match the card's connector (most RTL8822CE cards are MHF4) |
| Heatsink 30 × 30 × 6 mm (aluminium) + 1 mm thermal pad for the RK3566 | 52 | Amazon / DigiKey | Lid is vented above it |
| Pulse JK0654219NL magjack | 55 | DigiKey / Mouser | Rev A only |
| Screws and inserts: M3 × 6 (case), M2.5 × 4 (module), M2 × 3 + M2 standoff (Wi-Fi card), M3 heat-set inserts, ¼"-20 heat-set inserts | per the [case parts list](case/README.md) | McMaster / Amazon | |
| Light pipes, 3 mm round, for the PWR / STATUS / WIFI LEDs | 3 per unit | DigiKey | Lid has the holes |
| Filament (PETG or ASA) | about 6 kg | | About 100 g a case |
| Boxes, inserts, labels, quick-start cards | 55 | | |
| USB-C PD charger, 20 W, 9 V | 50 | | Optional in the box (COST.md says $3) |

### Pilot unit cost (estimate)

Not quoted yet: the board line scales the Oct 24 JLCPCB quotes (5 and 500 boards) to 55, and the rest are small-lot
prices. Expect the pilot to cost well over the 500-unit figure.

| Per unit | Estimate | Basis |
|---|---|---|
| Board from JLCPCB, landed with 35% duty | about $47 | About $1,800 for 55 boards (board, assembly and parts at small-lot prices), plus UPS and duty |
| Radxa CM3 | $40–49 | $49 at Keyestudio today; ask Radxa for 52 |
| Wi-Fi card | $15 | US distributor stock |
| Antennas and pigtails | $6 | |
| Heatsink and pad | $2 | |
| Magjack (rev A only) | $9 | DigiKey, small lot |
| Case: filament, inserts, screws, feet, light pipes | $5 | |
| Box, insert, label, card | $2 | |
| Our team's time, about 18 minutes | $9 | |
| **Pilot unit** | **about $135–145** | Against about $112 at 500 units (COST.md) |

## Station equipment

- **Soldering:** temperature-controlled iron, flux, fume extractor, ESD mat and wrist straps (stations 2–3).
- **Flashing:** a powered USB hub and a laptop running `rkdeveloptool` with the factory image and script.
- **Test bench:** 12 V DC supply and a 9 V USB-C PD supply; an HDMI source that outputs 1080p60 (a camera or a
  cheap HDMI pattern generator); an HDMI monitor; a gigabit switch; a laptop with Wi-Fi for the AP and stream test.
- **Printing:** two printers (Bambu P1S class) print a case set in about 4 hours each, so about 25 cases a week
  on two printers.
- **Labels:** a thermal label printer for the serial / MAC / QR label.

## Test script (station 5)

Runs on the unit over SSH from the bench laptop, prints PASS or FAIL per line, and stores the log under the serial
number:

1. Power: boots from 12 V DC, then again from 9 V USB-C PD. `VIN_SENSE` reads within 5% of the supply. From a
   5 V-only USB-C source, VIN stays off (the PD gate, Q101).
2. LEDs: PWR on; STATUS and WIFI blink on command (the operator confirms).
3. Ethernet: gigabit link; 100 MB transfer with no errors.
4. HDMI in: the RK628D reports 1080p60 from the pattern generator; 30 s capture, no dropped frames.
5. HDMI out: the captured frames appear on the monitor (the operator confirms).
6. Wi-Fi: the AP comes up on 2.4 and 5 GHz; the laptop joins and pulls the stream for 30 s.
7. Bluetooth: the controller is up and scans.
8. Buttons: RESET reboots; RECOVERY reads low when pressed.
9. Thermal: after 10 minutes of capture and encode in the closed case, SoC under 85 °C.

## Open

- Pilot quote from JLCPCB at 55 boards, once rev B is out.
- Customs broker: the duty rate and HS code for the boards, the module and the Wi-Fi card.
- Module supply: a Radxa quote at 50 and 500, and lead time.
- The factory image and flashing script (software side).
