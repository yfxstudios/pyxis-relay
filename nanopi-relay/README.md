# NanoPi R5C router + relay for the PYXIS 12K

This replaces the Mac's relay with a FriendlyElec **NanoPi R5C** running FriendlyWrt. The R5C is the
router for its own little network: the camera plugs into its LAN port, viewers join its Wi-Fi hotspot,
and MediaMTX on the R5C re-shares the camera's stream to every viewer. It doesn't play video itself
(no HDMI output is used).

```
                         ┌──────────────── NanoPi R5C (FriendlyWrt) ─────────────────┐
PYXIS 12K ──Ethernet──▶  │ LAN 2.5GbE (eth1) ─┐                                       │
                         │                    ├─ br-lan 192.168.50.1/24 ── MediaMTX   │
phones, Macs  ◀─Wi-Fi──▶ │ M.2 Wi-Fi AP ──────┘   DHCP .100-.199, camera = .10 (fixed)│
                         │ WAN 2.5GbE (eth0) ──▶ (optional) home router, for internet │
                         └───────────────────────────────────────────────────────────┘
```

The camera's link to the relay is a short Ethernet cable. On the Mac, the camera reached the relay over
weak Wi-Fi, and that caused the stutter.

## Files

| File | Runs on | What it does |
|---|---|---|
| `config.env.example` | — | Settings to fill in: Wi-Fi name and password, addresses, camera MAC. Copy it to `config.env`. |
| `deploy.sh` | Mac | Downloads MediaMTX v1.21.2 and checks its SHA-256, writes the camera profile, copies everything to the NanoPi over SSH and runs `setup.sh` there. You type the password once. |
| `make-profile.sh` | Mac | Writes the camera's XML profile for a relay address. |
| `PYXIS-LAN-192.168.50.1.xml` | Camera | Profile for the default router address. |
| `router/setup.sh` | NanoPi | Sets up the LAN, DHCP, the camera's fixed lease, the Wi-Fi access point, MediaMTX as a service and the mDNS advert. It checks `config.env` first and changes nothing if anything is wrong. It leaves the port assignment as FriendlyWrt set it and refuses to run if the LAN isn't a bridge. Safe to run again. |
| `router/mediamtx.yml` | NanoPi | Relay config. Same as the first (Mac-hosted) relay's tested config (RTMP 1935, RTSP 8554, fMP4 HLS 8888, WebRTC 8889, `readTimeout: 30s`, SRT off). Logs go to the system log. |
| `router/mediamtx.init` | NanoPi | Service script (`/etc/init.d/mediamtx`). Starts at boot, restarts on crash, and advertises `_pyxisrelay._tcp` while the relay runs. |
| `router/status.sh` | NanoPi | Installed as `pyxis-relay-status`. Shows which ports have a cable, whether the relay runs, the camera is streaming, the access point is broadcasting (with client count), the camera has its lease, and mDNS is up. |
| `router/pyxisrelay.avahi.service` | NanoPi | mDNS advert. Only used if the image runs avahi instead of umdns. |
| `router/web/index.html`, `qrcode.js` | NanoPi | The settings page, at `http://192.168.50.1/`. A single self-contained file plus the QR library (qrcode-generator 1.4.4, MIT). Works offline. |
| `router/web/pyxis.uc` | NanoPi | The page's backend: an rpcd plugin (`/usr/share/rpcd/ucode/pyxis.uc`) reached through `/ubus`, the same endpoint and login LuCI uses. |
| `router/web/pyxis-acl.json` | NanoPi | Says which page actions need a signed-in admin. |
| `router/web/root-index.html` | NanoPi | Makes `http://192.168.50.1/` open the settings page. LuCI stays at `/cgi-bin/luci/`. |
| `hdmi/pyxis-hdmi` | NanoPi | The HDMI player: a static aarch64 binary, installed as `/usr/bin/pyxis-hdmi`. |
| `hdmi/pyxis-hdmi.c`, `hdmi/build.sh` | Mac | The player's source, and the script that rebuilds it (Zig cross-compiler, Rockchip MPP 1.1.0, libdrm 2.4.123, checksum-verified). |
| `hdmi/THIRD_PARTY_LICENSES.txt` | NanoPi | Licences of the libraries built into the player (Apache-2.0 / MIT). Installed in `/usr/share/doc/pyxis-hdmi/`. **Ship it with the product.** |
| `router/camera.cgi` | NanoPi | Installed as `/www/cgi-bin/pyxis-camera`. Tells viewer apps where the camera is (the camera auto-start found, its fixed address, or DHCP clients with Blackmagic's MAC prefix), for camera control. Read-only, no login, camera network only. |
| `router/autostart.sh`, `router/pyxis-autostart.init` | NanoPi | Camera auto-start (`/usr/bin/pyxis-autostart`, `/etc/init.d/pyxis-autostart`). Off until turned on in the settings page. See "Starting the stream automatically". |
| `router/pyxis-hdmi.init` | NanoPi | Service script (`/etc/init.d/pyxis-hdmi`). Starts at boot and restarts on crash. Reads `pyxis.hdmi.enabled` and `pyxis.hdmi.match_rate`. |

## Hardware

**NanoPi R5C** with FriendlyElec's **M.2 E-key Wi-Fi module (Realtek RTL8822CE, Wi-Fi 5, PCIe)** and its
antennas.

### Can the RTL8822CE be a hotspot? Yes: documented by FriendlyElec, and confirmed on a real R5C

FriendlyElec's [NanoPi R5C wiki](https://wiki.friendlyelec.com/wiki/index.php/NanoPi_R5C) covers this:
- Section 5.14, "How to use M.2 PCI-E WiFi", lists the RTL8822CE as the supported M.2 module.
- Section 5.14.1, "AP Mode", says FriendlyWrt's wireless is off by default. Turning it on under
  Network → Wireless gives a hotspot named like `FriendlyWrt-xx:yy:zz` with the password `password`.
- The changelog also lists Wi-Fi Direct and repeater support for the RTL8822CE.

So **access-point mode is FriendlyElec's documented, supported configuration** for this module, and it
works on a real R5C: the PYXIS-Stream hotspot ran on it at 5 GHz with WPA2/WPA3 (see the end of this file).

Setup turns off that default `FriendlyWrt-…` hotspot, which has a publicly known password, and creates
your own.

### Fallbacks if the M.2 module won't host the hotspot

1. **USB Wi-Fi dongle from FriendlyElec's tested list.** The R5C wiki's section 6.4.1.2 lists these, and
   section 5.15.2 shows "Configure a USB WiFi Device as AP":
   - **MediaTek MT7662**, test sample COMFAST CF-WU782AC V2 (USB `0E8D:7612`). Prefer this one: it uses
     OpenWrt's well-supported MediaTek `mt76` driver. Some MT7662 dongles first need `usb_modeswitch` to
     switch out of their "driver CD" mode.
   - Realtek RTL8812AU (USB `0BDA:8812`).
   - Realtek RTL8821CU, test sample TP-Link TL-WDN5200H (USB `0BDA:C811`).

   The wiki says devices with these USB IDs "would most likely work". It doesn't say which support
   access-point mode, so the MediaTek one is the safest bet. Plug it into a USB 3 port, reboot, and run
   setup again. It picks up the new radio.
2. **A separate Wi-Fi access point on the LAN.** Use any home access point or router set to
   *access point / bridge mode* with its own DHCP **off**. The R5C has only **one** LAN port and the camera
   uses it, so put a small gigabit switch on the LAN port, then connect the camera and the access point
   to the switch. Viewers on that access point land on the same network (`192.168.50.x`) and get addresses
   from the R5C. You can leave the M.2 module out entirely. Setup warns that no radio was found and skips
   Wi-Fi.

### Ports: which is WAN and which is LAN

The R5C has two 2.5GbE ports. Confirmed from FriendlyWrt's own board network script
(`target/linux/rockchip/armv8/base-files/etc/board.d/02_network`, branch `master-v25.12`, entry
`friendlyelec,nanopi-r5c`):

| Port | Interface | Role |
|---|---|---|
| WAN | `eth0` | Optional upstream. Gets an address from your home router by DHCP. |
| LAN | `eth1` | The camera. Bridged into `br-lan` together with the Wi-Fi hotspot. |

This matches the wiki's FriendlyCore notes (`eth0` = WAN LED, `eth1` = LAN at 192.168.2.1). OpenWrt
always makes the LAN a bridge (`br-lan`) so Wi-Fi can join it. FriendlyWrt's network generator keeps
that behavior.

Plain upstream OpenWrt (not FriendlyWrt) assigns the R5C's ports the **other way round** (`eth0` LAN,
`eth1` WAN). Setup never changes the port assignment; it uses whatever the firmware set up. It prints
which interface is LAN and WAN, and `pyxis-relay-status` shows which port has a cable plugged in. If
the camera doesn't show up, check those rather than trusting the labels on the case.

## 1. Flash FriendlyWrt

1. Fit the M.2 Wi-Fi module and its antennas, with the power off.
2. Download the **NanoPi R5C** FriendlyWrt image from the
   [R5C wiki](https://wiki.friendlyelec.com/wiki/index.php/NanoPi_R5C). Current images are based on
   OpenWrt 25.12 (kernel 6.1) and install packages with `apk`. Older ones use `opkg`. Setup handles both.
3. Write it to a microSD card (balenaEtcher, or `dd`) and boot the R5C from it. To install to the eMMC,
   follow the wiki's eMMC steps.
4. Connect the Mac to the R5C's **LAN** port (`eth1`) with a cable. Optionally connect **WAN** (`eth0`) to
   your home router, which gives the R5C internet so setup can install `umdns` if the image lacks it.
   The camera takes over the LAN port later.
5. Check that you can reach it: <http://192.168.2.1> (FriendlyWrt's default). Its default password is
   `password`, or empty on some versions. **Set a real root password** (`passwd` over SSH, or in the web UI)
   before giving anyone the Wi-Fi password.

## 2. Configure and deploy (from the Mac)

```bash
cd nanopi-relay
cp config.env.example config.env
open -e config.env
```

Set at least `WIFI_SSID`, `WIFI_KEY` and `WIFI_COUNTRY`. The defaults put the router at `192.168.50.1`,
viewers at `.100`–`.199` and the camera at `.10`. Leave `CAMERA_MAC` empty for now. Then:

```bash
./deploy.sh 192.168.2.1
```

At the end the R5C moves to `192.168.50.1`, so the SSH connection drops. Unplug and replug the Mac's
cable so it gets a new address, or move the Mac to the new Wi-Fi network, then check:

```bash
ssh root@192.168.50.1 pyxis-relay-status
```

The access point broadcasts within a few seconds on channel 36 (5 GHz) or 6 (2.4 GHz). If you set
`WIFI_CHANNEL="auto"`, it can pick a radar-protected (DFS) 5 GHz channel. Then it listens for radar for
60 s before it broadcasts, and must move or go quiet if radar shows up later.

To change settings later, edit `config.env` and run `./deploy.sh 192.168.50.1` again.

## 3. Camera

1. Move the Mac to the new Wi-Fi network. On the camera, set the network to **Ethernet, DHCP**, then
   plug it into the R5C's **LAN** port (the one the Mac was on).
2. Optional, so the camera always has `192.168.50.10` (handy for PYXIS Viewer's camera controls): find its
   MAC address with `ssh root@192.168.50.1 cat /tmp/dhcp.leases`, put it in `CAMERA_MAC`, then run
   `./deploy.sh 192.168.50.1` again.
3. Copy `PYXIS-LAN-192.168.50.1.xml` to a CFexpress card or USB-C drive. If you changed `ROUTER_IP`, run
   `./make-profile.sh <ip>` first, or use the copy `deploy.sh` made. On the camera, go to Setup → page 11 →
   **Import Stream Settings**, choose **PYXIS LAN Relay (RTMP)** and turn **Stream** on.

### Starting the stream automatically

The streaming XML can't make the camera start streaming at power-on (the format only describes services,
servers and quality profiles). The relay does it instead, over the camera's REST API:

1. On a computer with **Blackmagic Camera Setup**, open the camera's **Network Access** settings and turn
   **Web media manager** on. If you pick "Enabled with security only", note the Secure Login username and
   password.
2. Load the relay's profile on the camera (step 3 above) and keep **PYXIS LAN Relay (RTMP)** selected.
3. On the settings page, open **Camera & stream → Start streaming automatically**, tick the box, enter the
   Secure Login if the camera uses one, and save. Leave the camera address empty to have the relay find it.

What it does:
- **Finding the camera** (camera address left empty). It tries, in order: the camera it found last, the fixed
  address, Blackmagic devices on the relay's network (MAC prefix 7C:2E:0D), then every other device. That
  last step covers a camera on a USB-C Ethernet adapter, which has the adapter's MAC. It uses the first one
  that answers the camera's API, so any Blackmagic camera with Web media manager on works, not just the
  PYXIS. The viewer apps are told the same camera.
- Each time the camera comes online, it waits until the camera's stream is idle, then asks it to start.
  It retries every 10 s while the camera is still starting up.
- If the stream stops for any reason (including being stopped on the camera), the relay starts it again
  within about 10 s. To stop streaming for good, turn auto-start off on the settings page.
- If the camera says it's streaming or connecting but nothing reaches the relay for 30 s (for example
  after a Wi-Fi drop), the relay stops the camera's stream and starts it again.
- Just before starting, it turns on the display LUT for the camera's **Stream** output, so a camera set to
  Film dynamic range streams a normal Rec.709 picture instead of flat log footage, in every viewer. PYXIS
  Viewer's monitor LUTs go on top of that. Untick "Turn on the display LUT for the stream" on the settings
  page to leave it alone. Recorded clips aren't affected. Tested against a simulated camera, not yet live.
- It only starts the stream when **PYXIS LAN Relay (RTMP)** is the camera's selected platform, so it never
  streams anywhere else. Otherwise the settings page says which platform is selected.
- The Secure Login is stored in `/etc/pyxis/camera.curl`, readable only by root, and sent to the camera
  over HTTPS only. The settings page never shows the password again. While searching for the camera
  (no address set), the relay doesn't send the login.
- Its log: `logread -e pyxis-autostart`.

## 4. Watching

**iPhone, one scan:** with the **PYXIS Viewer** iPhone app installed (`../PyxisViewer-iOS`), scan the QR code
on the settings page (Watch card; **Print QR card** prints it) with the Camera app. The app joins the
R5C's Wi-Fi and starts the picture. The code contains the Wi-Fi password.

Or join the R5C's Wi-Fi, then use any of these:

| Viewer | Address |
|---|---|
| Phone or browser, low delay (<1 s, video only) | `http://192.168.50.1:8889/live/pyxis/` |
| Phone or Safari with sound (HLS, about 4–8 s delay) | `http://192.168.50.1:8888/live/pyxis/index.m3u8` |
| VLC or OBS | `rtsp://192.168.50.1:8554/live/pyxis` |
| PYXIS Viewer (iPhone, iPad, Mac, Android) | Finds the relay at `pyxis-relay.local` by itself; on a phone, scan the QR code to join the Wi-Fi first. |

The camera profile uses the relay's address, `192.168.50.1`: the camera may not resolve `pyxis-relay.local`.
Use the XML file `deploy.sh` made, or `./make-profile.sh 192.168.50.1`.

## How many viewers can the Wi-Fi handle?

Every viewer gets its own copy of the stream, so the Wi-Fi has to carry *(stream bitrate) × (viewers)*.
Viewers far from the NanoPi use more airtime and slow everyone down.

Stream bitrates from the profile at 1080p30 are LAN Low 3.5, LAN Medium 6 and LAN High 12 Mbps. 1080p60
and 2160p are higher (up to 40 Mbps).

**These are estimates, not measurements.** They assume about half of a single client's measured speed is
usable across many clients, with headroom left over:

| Wi-Fi | Plan for about | LAN Low (3.5 Mbps) | LAN Medium (6) | LAN High (12) |
|---|---|---|---|---|
| R5C + RTL8822CE, 5 GHz (a review measured 276 Mbps down / 156 Mbps up for one client) | 70 Mbps total | ~15–20 viewers | ~10 | ~5 |
| R5C + RTL8822CE, 2.4 GHz (`WIFI_BAND="2g"`) | 25–30 Mbps | ~6–8 | ~4 | ~2 |
| Fallback: MT7662 USB dongle, 5 GHz | 50–70 Mbps | ~12–20 | ~8–10 | ~4–5 |

For more viewers:
- Use **LAN Low**.
- Put viewers on cables: add a small switch to the LAN port, with the camera and wired viewers on it.
- Or connect a proper Wi-Fi access point through that switch (fallback 2 above), instead of or alongside
  the R5C's radio.

## HDMI output

A screen plugged into the R5C's HDMI port shows the live stream, from your camera through the relay.

```
camera -> relay (MediaMTX) -> RTSP over localhost -> RTP unpacking -> Rockchip hardware decoder (MPP)
       -> decoded frame handed straight to a display plane (no copy, hardware scaling) -> HDMI
```

- **Two playback modes** (settings page → HDMI output → Playback):
  - **Smooth motion** (default): frames are shown on the stream's own timeline, not the moment they arrive.
    The PYXIS sends its frames in uneven bursts (arrival times wander by 30–60 ms); the player measures that
    over the last 3 s and holds each frame just long enough to absorb it, so every frame stays up equally
    long. With refresh matching on, 24p plays at 24 Hz (measured: every frame held exactly one refresh).
  - **Lowest latency**: each frame goes up at the screen's very next refresh after it's decoded, with no
    smoothing buffer, and the refresh rate never drops below 48 Hz (24p plays at 60 Hz). Motion can be a
    little uneven when the camera's delivery is bursty.
- **Delay** (from a frame reaching the relay to the refresh that shows it, measured with the PYXIS stream
  at 1080p24; the settings page shows the live figure):

  | Mode | Refresh | Delay | Then drawing to mid-screen |
  |---|---|---|---|
  | Smooth motion | 24 Hz | 64–67 ms | ~21 ms |
  | Lowest latency | 60 Hz | 21–22 ms | ~8 ms |

  So Lowest latency puts the picture on screen about 55–60 ms sooner. Hardware decode is about 10 ms of
  either figure. The camera's own encoding and buffering come before all of this, and are the same for
  every viewer: turn the camera's **Low Latency** setting on.
- **Frame rate:** it decodes and shows every frame. With the PYXIS stream it showed 24.0 of 24.0 frames/s,
  with no lost frames or decode errors. After a (re)start the first picture appears at the camera's next
  keyframe (within about 2 s), so you never see a damaged picture.
- **Colour:** HD streams are converted with the BT.709 colour matrix (SD with BT.601), as the camera and
  other players expect.
- **Formats:** H.264 and H.265, up to 4K. Tested at 720p30, 1080p24/60 and 2160p24/30 at up to 30 Mbps,
  all decoded in real time with 2–7 % CPU.
- **Refresh rate:** the screen keeps its preferred resolution, at a refresh rate that's an exact multiple of
  the stream's frame rate, so every frame is shown for the same time. It prefers 48 Hz or more (25p → 50 Hz,
  30p → 60 Hz, 60p → 60 Hz, 24p → 48 or 120 Hz); failing that it uses the stream's own rate (24p → 24 Hz).
  On 60 Hz, 24p frames alternate between 3 and 2 refreshes, a steady stutter that was clearly visible on the
  test monitor next to a Mac showing the same stream evenly. 24 Hz removes it (measured: every frame held
  exactly one refresh) for about 25 ms more delay. Frames are paced to the stream's timestamps, so clock
  drift costs at most a rare single repeated or skipped frame. With refresh matching off, the screen stays at
  its normal rate (usually 60 Hz) for the lowest delay.
- **Hotplug:** plug in or unplug a screen at any time. With no stream, the screen goes black after 2 s. The
  kernel's text console is kept off the HDMI screen, so a screen without video shows black, never console
  text.
- **Settings:** on the settings page (HDMI output: on/off, playback mode, refresh matching), or with
  `uci set pyxis.hdmi.enabled=0|1` / `pyxis.hdmi.low_latency=0|1` / `pyxis.hdmi.match_rate=0|1`, then
  `/etc/init.d/pyxis-hdmi restart`.
- **Troubleshooting:**
  - `logread -e pyxis-hdmi` shows the player's log (a stats line every minute).
  - `pyxis-hdmi -l` lists the screen's modes.
  - `/tmp/pyxis-hdmi.json` holds the live status.
- **No audio** over HDMI yet: video only.
- **Rebuilding:** run `hdmi/build.sh` on the Mac (needs `zig`, `cmake`, `meson`, `ninja`).

## Settings page

Open **http://192.168.50.1/** (or `http://pyxis-relay.local/`) from any device on PYXIS-Stream and sign in
with the router's admin password.

| Section | What it does |
|---|---|
| Status | Live/offline, camera's address, bitrate in, resolution and codec, viewer sessions, Wi-Fi clients, LAN/WAN cables, chip temperature, uptime. Refreshes every 2 s. |
| Watch | A built-in low-latency preview (video only, off until you press the button), the viewer links, and a QR code for phones. |
| Wi-Fi hotspot | Name, password (leave empty to keep it), 2.4/5 GHz, channel (non-radar channels only). Saving restarts the hotspot. |
| Camera & stream | Where the camera sends to, **Download camera profile** (generated on the box for its current address), quality presets (12 bitrates and the preset picked after import), and the camera's fixed address (pick it from the device list). |
| Admin | Change the admin password, restart the relay, reboot, view the relay log, open LuCI. |

Things to know:
- **The settings page and `deploy.sh` both set Wi-Fi and the camera's fixed address.** Running `deploy.sh`
  again resets those to `config.env`, which makes it the factory reset. Quality presets live in
  `/etc/config/pyxis` and survive a re-run.
- The stream key (`pyxis`) and path (`live/pyxis`) are fixed, because PYXIS Viewer expects them.
- The page's backend validates every setting before saving (password length, channel allowed on the
  band, fixed address outside the automatic range, bitrates 0.5–100 Mbps), so a bad value can't break the
  router.
- **Browser support:** the preview uses WebRTC to port 8889, a separate origin from the page. Standard
  browsers (Chrome, Safari, Firefox) allow it because the relay sends the right CORS headers. The Claude
  desktop app's built-in browser pane blocks it, so the preview stays on "retrying" there; the rest of the
  page works.

## Security

- The relay is open to everyone on the NanoPi's network. The Wi-Fi password is the access control.
- OpenWrt's firewall blocks everything coming in on the WAN port, so nothing is reachable from your home
  network or the internet. Don't open ports there.
- Every other Wi-Fi network on the NanoPi (for example a default open or default-password one) is turned
  off by setup.
- Set a root password on the NanoPi (see step 1). It's also the settings page's login, and its sessions
  expire after an hour without use.
- The camera's Secure Login (only if you use auto-start) is kept in `/etc/pyxis/camera.curl`, readable by
  root only, and only ever sent to the camera over HTTPS.
- The settings page and MediaMTX's API are only reachable from the NanoPi's own network. MediaMTX's API
  listens on 127.0.0.1 only.

## Troubleshooting

- `pyxis-relay-status` gives a summary. `logread -e mediamtx` shows the relay log, and
  `logread | grep hostapd` shows the access point log.
- **No Wi-Fi:** "No Wi-Fi radio found" means the M.2 module isn't detected. Check it's seated and screwed
  down, reboot and run setup again. hostapd errors usually mean the band or channel doesn't suit the
  module. Try `WIFI_BAND="2g"`, or use a fallback (see Hardware).
- **Camera not on the network:** run `pyxis-relay-status` and check that the LAN port shows
  "cable connected". Setup's summary prints which interface is LAN.
- **No addresses handed out on the LAN:** `logread` says `found already running DHCP-server … refusing to
  start` when the LAN port connects to a network that already has a DHCP server, such as your home router.
  OpenWrt then stops handing out addresses there on purpose. Plug only the camera (and a switch for wired
  viewers) into the LAN port. Your home router belongs on WAN.
- **Upgrading FriendlyWrt:** the relay files are listed in `/etc/sysupgrade.conf` so a firmware upgrade
  keeps them. Run `deploy.sh` again if something's missing.
- **Updating MediaMTX:** change `MTX_VERSION` and `MTX_SHA256` in both `deploy.sh` and `router/setup.sh`.
  Take the checksum from the release's `checksums.sha256`.

## What was tested, and what wasn't

### On a real NanoPi R5C (FriendlyWrt, OpenWrt 25.12.2, RTL8822CE)

- `deploy.sh` installed everything, then ran again cleanly. The RTL8822CE hosts the **PYXIS-Stream**
  hotspot (5 GHz, channel 36, WPA2/WPA3), and a Mac and a phone joined it.
- Relay: a 1080p24, 3.5 Mbps test feed arrived at a steady 24.07 fps, longest gap 80 ms, no pauses. A
  1280×720 webcam stream also went through, to PYXIS Viewer and the settings page.
- Auto-discovery: PYXIS Viewer found "PYXIS Relay on FriendlyWrt" over mDNS.
- Settings page:
  - Sign-in through LuCI's login: a wrong password is refused, and calls without a session are refused.
  - Each action is permission-checked: a session limited to read-only actions was denied `set_wifi`.
  - Status, config, profile and log, through rpcd in 0.14 s.
  - The generated camera profile is identical (servers, presets, all 12 bitrates) to the Mac kit's.
  - Quality presets, the camera's fixed address (set and removed) and relay restart were tested.
  - Validation was checked for every form (13 bad inputs, each refused with a message).
  - **Password change:** the exact mechanism was tested on a temporary account, not root. It set a
    SHA-256 password hash, refused mismatched entries and left the old password, and the account files
    were then restored byte for byte.
  - **Preview:** in a standard Chromium (Playwright), the built-in player played the webcam at 1280×720,
    30 fps (150 frames in 5 s), and reconnected by itself after the stream went offline and came back.
- HDMI output (see "HDMI output" above for the measured numbers):
  - Played the PYXIS 12K stream on a real computer monitor (EDID read, 1080p, 4K-capable).
  - Motion: a moving bar was played and the display hardware's own output was captured in bursts
    (writeback, `PYXIS_HDMI_CAPTURES=N`). This found the cause of the stutter and moving tear line seen on
    the monitor: the player cached its display framebuffers by the decoder's buffer index, which this MPP
    build reports as -1 for every buffer, so every frame went to the first framebuffer and the screen only
    changed when the decoder reused that buffer, sometimes mid-scan. After the fix (cached by the buffer
    itself), every capture is a whole frame and the bar advances steadily between captures, at 24 Hz and
    60 Hz. Flip timing (`PYXIS_HDMI_DEBUG=1`) with the camera at 24 Hz: every frame held exactly one refresh,
    with a rare 2.
  - Before the monitor was available, the display path was tested with the HDMI port forced "connected".
    Frames captured from the display hardware's own output (writeback) showed the decoded video with correct
    colours, and a 4K stream scaled to the screen.
  - Stream stop/restart, screen unplug/replug and turning HDMI off/on from the settings page were all
    checked against the kernel's display state.
  - Shutdown releases every buffer.
- Camera auto-start, on the R5C with the real PYXIS (Web media manager on, no Secure Login): with no
  address set it found the camera among the DHCP clients (192.168.50.183, HTTPS). A stream stopped through
  the camera's API stayed stopped; a fresh start of the service (the same state as a camera that's just
  been switched on) started the stream within 6 s, and the relay received it. The settings API saved a
  login with quotes, backslashes and colons in it, which curl read back exactly (file mode 600), and
  rejected bad addresses and line breaks. Earlier, on the Mac against a simulated camera: it starts again
  after the camera disappears and comes back, and won't start while another platform is selected.
  Not yet tested: an actual camera power cycle, and a camera with Secure Login over HTTPS.
- **Not exercised live** (each would cut the stream or the Wi-Fi during testing):
  - Saving Wi-Fi. It writes the same settings `setup.sh` writes and restarts the hotspot with the same
    `wifi` command, both proven above.
  - Reboot.
  - Changing the real admin password.

### Earlier, before the board arrived

No R5C was available, so the router side was tested on the official **OpenWrt 25.12.4 arm64** image (the
release current FriendlyWrt for the R5C is based on) in a QEMU VM, using the real `deploy.sh`.

**Tested and working:**
- `deploy.sh` → `setup.sh` end to end:
  - MediaMTX download and checksum check.
  - LAN moved to 192.168.50.1/24, the DHCP pool set, and the camera's fixed lease written into dnsmasq.
  - Settings kept after both a normal reboot and a simulated power cut.
  - Running it again works, including the "same binary already installed" path.
- Bad settings are rejected before any change. Nine cases were tried (placeholder Wi-Fi name, short key,
  camera inside the pool or on another network, bad IP, MAC, band or hostname, pool past .254), with zero
  pending changes afterwards.
- The relay on OpenWrt arm64:
  - It starts at boot, including after a power cut.
  - RTMP ingest works.
  - The RTSP check PYXIS Viewer uses for "is it live?" returns 200.
  - fMP4 HLS played in AVPlayer with the app's settings (0 s frozen in 20 s).
  - The WebRTC page loads.
- The mDNS advert: a separate client's `_pyxisrelay._tcp` query was answered with
  `pyxis-relay._pyxisrelay._tcp → pyxis-relay.local:8889`, also after a reboot.
- The Wi-Fi access point, on a simulated `mac80211_hwsim` radio with OpenWrt's `wpad-basic-mbedtls`,
  starting from OpenWrt's defaults:
  - Setup moved the radio from 6 GHz to 5 GHz and set the country.
  - The AP came up on channel 36 with WPA2/WPA3.
  - A simulated client joined with **WPA2** and with **WPA3**.
  - The client got a lease from the router's DHCP (`192.168.50.161`, from 192.168.50.1) and reached the relay.
    QEMU runs its own DHCP server on the VM's LAN, so OpenWrt correctly refused to serve DHCP there
    (see Troubleshooting). For this one check the VM's link to QEMU was detached and `dhcp.lan.force`
    was set temporarily, then removed. The shipped setup leaves OpenWrt's safety check on.
  - `pyxis-relay-status` reported the AP and the client count correctly.
- `shellcheck` passes on every script. The relay config also ran on the Mac's MediaMTX v1.21.2 with no
  warnings.
- The R5C-specific checks were added after the VM was shut down: the board-name warning, the "LAN must be
  a bridge" check and the port printout. Their parsing was tested against a `uci` stand-in that replays
  the VM's real output format, using three layouts:
  - FriendlyWrt's R5C default: `br-lan` with port `eth1`, WAN `eth0`. Accepted.
  - LAN as a plain `eth1`: stopped with an explanation.
  - A two-port bridge: accepted.

  These checks haven't run on OpenWrt itself.

**Bugs the VM testing found and fixed:**
- Saving Wi-Fi settings on a box with no radio stopped setup.
- A second run thought there wasn't enough space.
- Files written last were empty after a power cut. Setup now flushes to disk with `sync`.
- The JSON advert in `/etc/umdns/` was never served. The service script registers the advert now.
- The network reload at the end was killed when the SSH session closed, so changes only applied after a
  reboot.
- A second radio's default country `00` overrode the access point's country.
- `wifi reload` didn't retry a radio that had failed earlier.
- `auto` channel landed on radar channels with a 60 s wait.
- The status check said "up" when the access point had actually failed.

**Not tested (needs the real hardware):**
- FriendlyWrt on a real R5C, as opposed to stock OpenWrt 25.12.4. The port mapping comes from
  FriendlyWrt's source code, not from a running board.
- The RTL8822CE module as a hotspot (documented by FriendlyElec, see Hardware), its range and real
  throughput. The viewer counts above are estimates. The fallback dongles are untested too.
- The `opkg` path (FriendlyWrt images older than OpenWrt 25.12), and the avahi path.
- WebRTC video reaching a Wi-Fi client. The VM's networking can't carry WebRTC's UDP media, so only the
  WebRTC page and signaling were checked.
- The PYXIS camera streaming to the NanoPi, and getting its fixed lease. A test stream and a fake MAC
  stood in for it.
