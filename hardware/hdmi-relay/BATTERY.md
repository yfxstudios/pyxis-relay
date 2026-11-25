# Battery power: plan (draft 1, Oct 27, 2026)

What it takes to run the rev A relay from a camera battery, and what is still missing. Nothing here is built or
ordered yet.

## What the board already has

- **Inputs:** NP-F plate on J102 (JST PH 2-pin, pin 1 = + `VNPF`), the 6–17 V DC jack J101 (D-tap or V-mount
  through a cable), and USB-C PD at 9 V. Each goes through its own SS54 into `VIN_RAW`, so the highest wins and a
  second source can be plugged in before the first is pulled (hot swap, no reboot).
- **Protection:** 3 A resettable fuse F101, SMBJ20CA TVS, 47 µF bulk on `VIN`.
- **Sensing:** `VIN_SENSE` = `VIN` / 11 (100k/10k, 100 nF) into SARADC_VIN3 (CM3 J1-14, 10-bit, 1.8 V full scale:
  19.8 V). It is measured **after** the diodes and fuse, so it reads the winning source minus about 0.4–0.5 V, and
  it cannot tell which source that is.
- **Low limit:** the 5 V bucks stay in regulation down to about 5.5 V at `VIN`, about 5.9–6.0 V at the battery
  (REV_A_SPEC §3). Below that nothing in hardware cuts off: the software has to shut down first.

## Missing pieces

### 1. Accessories (not in any parts list yet)

| Item | Qty / unit | Choose by | Check |
|---|---|---|---|
| NP-F battery plate with a 2-wire lead (or bare contacts we wire) | 1 | ¼"-20 mount to match the case insert; NP-F550–970 fit | Polarity of its lead; lead long enough to reach J102 through the grommet |
| JST PH 2-pin lead: PHR-2 housing + SPH-002T crimps, or a pre-crimped 22–24 AWG pigtail | 1 | PH contacts are about 2 A | Pin 1 = +. Keep it short (IR drop at 2–3 A) |
| Grommet, 5 mm hole | 1 | Already in the case parts list | — |
| D-tap → 5.5 mm barrel cable | 1 per kit | The jack has a 2.0 mm pin: 5.5 × 2.0 plug if available, 5.5 × 2.1 is loose | Centre positive; ≥ 1 A wire |
| Test batteries: NP-F570 and NP-F970 | 1 each (dev) | Genuine or reputable clones (protection circuit) | — |

Add the chosen parts to PRODUCTION.md and `orders/`.

### 2. Software (nothing exists for this board yet)

A small battery service on the relay:

- **Read:** `/sys/bus/iio/devices/iio:device0/in_voltage3_raw` (rockchip-saradc), `VIN = raw × 1.8 / 1023 × 11`,
  with a per-board calibration factor (see bring-up). Sample at 1 Hz, median of 5 to ride over load steps.
- **Battery estimate:** `V_batt ≈ VIN + 0.45 V` (SS54 drop at about 1 A; refine from the bring-up measurement).
- **States** (for a 2S NP-F; hysteresis 0.2 V on every threshold):

  | Battery | State | Action |
  |---|---|---|
  | above 7.4 V | OK | — |
  | 6.6–7.4 V | Low | Warning on the settings page and in the viewer apps; STATUS LED slow blink |
  | 6.2–6.6 V | Critical | Warning repeats; LED fast blink |
  | below 6.0 V for 10 s | Shut down | Stop the stream cleanly, sync, power off |

- **Source:** since the ADC can't tell sources apart, the user picks the battery type on the settings page:
  NP-F (2S), V-mount/D-tap (4S, thresholds × 2: shut down below 12.0 V), or mains/USB-C (no battery warnings).
  Readings above 9.5 V with "NP-F" selected mean a DC or USB-C source is winning: show "external power".
- **Percentage and runtime:** a 2S Li-ion voltage-to-charge table, and runtime from the measured board power
  (about 6 W while streaming: NP-F570 ≈ 2.5 h, NP-F970 ≈ 7 h, REV_A_SPEC §3). Only an estimate: no current sense.
- **Expose:** a status call in the settings page backend (as `nanopi-relay/router/web/pyxis.uc` does today), the
  battery line in the status command, and the level in the viewer apps' HUD.
- **Log:** voltage once a minute, for run-down tests and support.

### 3. Device tree

The base tree's `saradc` node must stay enabled with its `vref-supply` (it is in rk3566-radxa-cm3.dtsi); the
overlay disables only `rk817_sound`, which used channel 2. Nothing else needed for channel 3.

## Decision needed first: which OS

REV_A_SPEC §1 plans OpenWrt (Radxa's official CM3 build, mainline kernel). The HDMI capture driver
(`rockchip,rk628-csi-v4l2`) and the device-tree overlay exist only in Radxa's BSP 5.10 kernel. So either:
- **BSP Debian/Ubuntu** (5.10, capture works, overlay as written), with the relay software ported from FriendlyWrt
  (MediaMTX and the player run anywhere; the settings page backend is OpenWrt-specific), or
- **OpenWrt on the BSP kernel** (custom build), or
- **OpenWrt mainline** and port the RK628 capture driver (large).

The battery service itself is the same on any of them (sysfs + a small daemon).

## Bring-up tests (first board)

1. **Calibrate:** bench supply at 6.0, 7.4, 8.4, 12.0 and 16.8 V into the DC jack; record the ADC reading and the
   VIN at the fuse; fit the scale. Repeat with 0.5 A and 2 A load to measure the diode drop.
2. **Minimum voltage:** lower the supply until 5V_SYS / 5V_SOM leave regulation; confirm the 6.0 V shutdown fires first.
3. **Run-down:** NP-F570 and NP-F970 while streaming 1080p; log voltage and time; check the estimate.
4. **Hot swap:** plug DC in, pull the battery, and back, while streaming: no reboot, no stream drop.
5. **Current and heat at 6 V:** board current at full load (fuse, J102 and SS54 temperature), U104 with a thermocouple.

## Open questions

- Which NP-F plate (lead polarity and length, mounting).
- Whether to sell the plate and cables as a kit or list them as compatible accessories.
- Rev B: a sturdier battery connector than JST PH, a current-sense resistor for real runtime, and a hardware
  low-voltage cutoff.
