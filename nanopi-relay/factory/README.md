# Relay factory image

This turns the relay into an appliance. Flash a microSD card, power on, and about two minutes later it's a
working relay with its own Wi-Fi name and passwords. No Mac, SSH or `config.env` needed.

```
build-image.sh   FriendlyElec's FriendlyWrt for the R5C  +  relay installer  +  first-boot service
                 -> dist/relay-factory-<date>.img.gz     (no passwords in it)
provision.sh     factory image  +  one unit's Wi-Fi name, Wi-Fi password, admin password
                 -> dist/units/<code>/relay-<code>.img.gz, label.html, unit.txt
```

Both run on the Mac and need Docker Desktop. The image work happens in a small Debian container
(`Dockerfile`), natively on arm64.

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
