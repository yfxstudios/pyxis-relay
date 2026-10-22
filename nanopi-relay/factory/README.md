# Relay factory image

This turns the relay into an appliance. Flash a microSD card, power on, and about two minutes later it's a
working relay with its own Wi-Fi name and passwords. No Mac, SSH or `config.env` needed.

```
build-image.sh   FriendlyElec's FriendlyWrt for the R5C  +  relay installer  +  first-boot service
                 -> dist/relay-factory-<date>.img.gz     (no passwords in it)
provision.sh     factory image  +  one unit's Wi-Fi name, Wi-Fi password, admin password
                 -> dist/units/<code>/relay-<code>.img.gz, label.html, unit.txt
```

Both run on the Mac. The image work happens in a small Debian container (`Dockerfile`), natively on arm64.

**What a fresh clone needs:**
- **Docker Desktop**, running.
- **`brew install zig cmake meson ninja`**, to build the HDMI player from source (`../hdmi/build.sh`).
  Or run with `NO_HDMI=1` for an image without HDMI output.
- **Internet on the first build.** It downloads, and checks against pinned SHA-256 checksums, the
  FriendlyWrt base image (about 207 MB), MediaMTX, and the HDMI player's two libraries (Rockchip MPP,
  libdrm).

Everything else is in this repository. A build from a clean clone was checked: the image holds the same
21 relay files with the same permissions as one built from the working folder. Only the freshly compiled
HDMI player differed, by its embedded build path, and it runs on the R5C.

## Build and provision

```bash
./build-image.sh
./provision.sh --country US
```

- `--count N` makes several units at once.
- `--ssh` leaves SSH on, for development units.
- The product name, Wi-Fi name prefix, hostname and app link all come from `brand.env`. Change them
  there and rebuild.

## Flash and first boot

**The R5C boots from the microSD card only when its built-in eMMC has no system on it.** A wiped or new
R5C with an empty eMMC is fine. One already running FriendlyWrt from eMMC ignores the card until its eMMC
is cleared. The card image is self-contained: it has the Rockchip loader, U-Boot, kernel and system.

You'll need an R5C with the RTL8822CE M.2 Wi-Fi module and its antennas, a 5 V USB-C power supply, and a
microSD card.

1. Write `relay-<code>.img.gz` to a microSD card (8 GB or larger) with balenaEtcher or Raspberry Pi Imager.
   Both accept the `.gz` directly.
2. Put the card in the R5C, connect the camera to **LAN**, and power on.
3. On first boot, the `relay-firstboot` service:
   - waits for the network to come up
   - applies the unit's settings
   - runs the same installer `deploy.sh` runs (`setup.sh`)
   - sets the admin password
   - turns camera auto-start on
   - switches off FriendlyWrt extras a relay doesn't need (web terminal, file sharing, UPnP, ad blocking
     and similar), and SSH unless `--ssh` was used
   - deletes the settings file and reboots

   This takes about 2 minutes. If anything fails, it tries again on the next boot. Log:
   `/etc/relay/firstboot.log`.
4. Join the Wi-Fi on the label (or scan its QR) and open the app.

## What's in a unit

- **Image:** no plaintext admin password. Only its SHA-512 hash, plus the Wi-Fi password, which the
  Wi-Fi itself needs. The settings file is deleted on first boot.
- **`label.html`:** a 4 × 3 in label. The big QR joins the Wi-Fi and opens the app. The small QR is a
  standard Wi-Fi QR for phones without the app. Also the Wi-Fi name and password, and the admin password.
- **`unit.txt`:** the passwords in plain text, for your records. Keep it safe or delete it.

## Base image

FriendlyWrt 25.12 for the R5S/R5C, release `FriendlyWrt-2026-10-13` from FriendlyElec's
[Actions-FriendlyWrt](https://github.com/friendlyarm/Actions-FriendlyWrt/releases) builds. It's pinned by
SHA-256 in `build-image.sh`. To move to a newer release, change `BASE_TAG` and `BASE_SHA256` and rebuild.

## Not done yet

- **Tested on a real R5C:** not yet. It's been built and checked inside the image (settings file,
  permissions, password hash, scripts parse in the box's shell), but a full first boot on hardware is the
  next step.
- **Install to eMMC:** the unit runs from the microSD card. Copying to the built-in eMMC still uses
  FriendlyElec's method.
- **Updates, factory reset, diagnostics bundle and setup wizard:** the next items in phase 1 of
  `PRODUCTION_PLAN.md`.
