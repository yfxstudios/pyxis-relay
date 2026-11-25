# Production-readiness plan

Turning the PYXIS relay and viewer apps from a working one-off rig into a product other people can buy, set up
alone, and get help with.

## Where it stands

What works today:
- **Relay.** A NanoPi R5C running FriendlyWrt and MediaMTX. It has its own Wi-Fi network, a QR code to join it,
  HDMI output, a settings page, and keeps the camera streaming.
- **Apps.** iPhone/iPad, Mac and Android, with live view, camera control, monitor LUTs, autofocus, frame
  grabs and local recording.
- **TestFlight.** The iOS app is in internal testing.

What makes it a prototype rather than a product:

| Area | Today | A buyer needs |
|---|---|---|
| Relay setup | Flash FriendlyWrt by hand, edit `config.env` on a Mac, run `deploy.sh` over SSH, set the root password with `passwd` | Plug in the box, scan a QR code, done |
| Credentials | Default root password, one shared Wi-Fi password in a config file | Unique credentials per unit, set on first boot |
| Updates | Re-run `deploy.sh` from a Mac | Updates from the settings page or the app |
| Camera setup | Load the XML profile, turn on Web media manager, all from READMEs | A step-by-step guide in the app, per camera model |
| Docs | Long technical READMEs | Quick-start card, website, troubleshooting, videos |
| Testing | One camera (PYXIS 12K), one iPhone, one Android emulator | A camera and phone matrix, soak tests, beta users |
| Name | "PYXIS" (Blackmagic's trademark) everywhere | A product name you can sell under |

## Decided (Oct 22, 2026)

- **Name:** a plain "what it does" name (in the style of RigLink, SetLink, CamRelay), used for the box, the
  apps and the Wi-Fi name. To do: shortlist candidates, then check trademarks (USPTO), App Store and Play
  names, and domains. Describe compatibility as "for Blackmagic cameras", with a "not affiliated with
  Blackmagic Design" line.
- **What we sell:** option (c). First a DIY beta (free relay image plus guide, free apps) for 10–20 testers
  across camera models; then assembled relay units once certification and sourcing are lined up. Ask a test
  lab early whether reselling the FriendlyElec board with our software needs its own certification.
- **Pricing:** free apps; revenue from the relay. The assembled unit is targeted at about $299 (parts about
  $100–110), to be confirmed with beta testers and after measuring latency against wireless video kits. A
  "Pro" upgrade stays a later option, once there's multi-camera support.

### Name shortlist, round 2: the whole crew connected (screened Oct 22, 2026)

The "Rig" names below didn't fit: the product is about everyone on set being connected, not just one rig.
Round 2 screened set-wide and crew-wide names. Same caveat: a basic screen, not legal clearance.

| Name | App Store | Google Play | .com | .app | Other domains | USPTO |
|---|---|---|---|---|---|---|
| **SetWide** | clear | clear | taken | **free** | .io / .co / .video free | clear |
| **OnSetLink** | clear | clear | taken | **free** | – | clear |
| **VillageView** | clear | near-misses ("Village Vü", "Villaview") | taken | **free** | – | clear |
| **Video Village** | clear | clear | taken | **free** | – | only dead marks; but it's everyday film-set language, so it would be hard to register and protect |

Ruled out:
- **SetView:** an app already uses the name on Google Play.
- **SetCast, SetShare, CrewLive:** .com and .app both taken.
- **CrewView, SetSync, CrewSync, SetHub, CrewHub, AllSet, CrewCast, SetLive:** apps already use these names on
  the App Store.

### Name shortlist, round 1: "Rig" names (screened Oct 22, 2026; superseded)

This is a basic availability screen, not legal clearance. Before committing, have a trademark attorney do a
full search, including the EU and UK if you'll sell there.

| Name | App Store | Google Play | .com | .app | Other domains | USPTO |
|---|---|---|---|---|---|---|
| **RigLink** | clear | clear | taken | taken | riglink.io / .co / .video, riglinkapp.com free | only a cancelled oil-and-gas mark |
| **RigFeed** | clear | clear | taken | **free** | rigfeed.io / .co / .video, getrigfeed.com free | clear |
| RigRelay | clear | clear | taken | taken | – | clear |
| SetRelay | clear | clear | taken | taken (registered Oct 21, 2026) | – | clear |
| CrewFeed | clear | clear | taken | taken | – | clear |
| CamFeed | clear | clear | taken | taken | – | clear |
| RigMonitor | clear | clear | taken | taken | – | clear |
| SetMonitor | clear | clear | taken | **free** | – | clear |

Ruled out because the App Store already has an app with that name: SetLink, CamRelay, CamTether, CrewLink,
RigCast, RigHub, SetFeed, and RigView (too close to "RigViewer").

## Decisions to make first

These shape everything after them:

1. **Product name and brand.** "PYXIS" is Blackmagic Design's trademark, and App Review and marketplaces reject
   names that suggest endorsement. Pick a name you own, describe compatibility as "for Blackmagic cameras",
   and say "not affiliated with Blackmagic Design". Check trademark availability and the domain.
2. **What you sell:**
   - **(a) Assembled relay units.** Pre-flashed, in the case. Simplest for buyers, but brings hardware sourcing,
     stock, returns and radio certification.
   - **(b) A software image plus a parts list.** For a DIY audience: flash an SD card, follow the guide.
   - **(c) Both.** Often (b) first for early adopters, then (a).
3. **Business model.** Free apps with paid hardware is simplest. A paid app or subscription needs Apple's
   Paid Applications agreement, banking and tax setup, and it raises support expectations.
4. **Seller entity.** Enroll the Apple and Google developer accounts as an **organization** (an LLC with a
   D-U-N-S number), so the store listing shows the company rather than your personal name. Also covers
   liability and insurance if you sell hardware.
5. **Launch camera list.** Cameras on both Blackmagic lists (streaming plus REST control) are: the PYXIS and
   URSA Cine families, Cinema Camera 6K, URSA Broadcast G2, and the Studio Cameras. Launch only with what you've
   tested; add more as testers confirm them.

## Workstreams

### 1. Relay: from scripts to an appliance (largest)

- **Factory image.** A single flashable image (FriendlyWrt plus MediaMTX plus our services) built
  reproducibly by a script or CI, replacing the hand-run `deploy.sh`. Version-stamped.
- **First-boot setup:**
  - Each unit generates its own Wi-Fi password and settings-page password on first boot, printed on a
    label or QR sticker (or shown once on the HDMI output).
  - No shared default credentials.
  - SSH off by default.
- **Setup wizard** on the settings page, reachable from the app after the first QR scan:
  1. Name the network.
  2. Set the country (Wi-Fi regulatory domain).
  3. Pick the camera.
  4. Download the camera profile.
  5. Check that the camera answers and is streaming.
- **Updates.** Signed update packages: check, download and apply from the settings page or the app, with
  rollback to the previous version if a new one fails to boot.
- **Factory reset.** A button-hold or settings-page option that restores the first-boot state.
- **Diagnostics:**
  - One-tap "Send diagnostics" that bundles logs and status into a file the user can email.
  - The settings page shows relay version, camera found, stream status and Wi-Fi channel.
- **Security review:**
  - Settings page over HTTPS or a local-only token, and no open endpoints beyond what the apps need.
  - Rate-limit login.
  - Camera Secure Login stored only on the relay.
- **Reliability:**
  - Multi-hour soak tests with several viewers.
  - Thermal testing in the case.
  - Power-loss tests (pull the plug mid-write; settings must survive).
- **Multiple cameras (later).** Today it's one camera per relay with a fixed stream key. Decide whether
  version 1 is single-camera; multi-camera means per-camera stream keys and a camera picker in the apps.

### 2. Hardware (only for option a or c)

- **Bill of materials and sourcing.** NanoPi R5C, Wi-Fi module (RTL8822CE, which is confirmed as a hotspot),
  antennas, SD card or eMMC, power supply, case. Lead times, a second source, cost per unit.
- **Case.** Move from 3D printing to small-batch production (printing service or injection mould), with labels
  for ports and the QR sticker.
- **Certification.**
  - A box with a Wi-Fi radio sold in the US needs FCC authorization, and the EU needs a CE/RED declaration.
  - The board and module certifications may not cover the finished product.
  - Get quotes from a test lab early: this is a major cost and timeline item.
- **Open-source compliance.** OpenWrt/FriendlyWrt (GPL) requires a written offer of source code, and MediaMTX
  (MIT) needs its license notice. Ship a licenses page and a source-code download.
- **Packaging.** Box, quick-start card, QR sticker, power supply, warranty card.

### 3. Apps: polish and onboarding

- **Rename and rebrand** across apps, store listings, Wi-Fi name, relay hostname, QR scheme and file names.
  Keep the old QR scheme working so existing relays still open the apps.
- **First-run onboarding in the app:**
  1. A welcome with what you need (camera, relay, the app).
  2. Scan the relay QR.
  3. A short explanation before each system permission (Wi-Fi join, local network, Photos).
  4. A **camera setup checklist** for the connected model: turn on Web media manager, load the profile,
     select the platform. The app shows a live check mark as each step is detected (it can see the camera
     API and the stream).
- **In-app help:**
  - A Help screen with gestures (swipe for clean feed, swipe for the AF rail, hold LUT).
  - A troubleshooting tree ("No picture" → is the relay reachable? is the camera found? is it streaming?),
    using the same states the app already knows.
  - Links to the website and support.
- **Error states.** Every failure says what happened and what to do; no raw HTTP codes.
- **Accessibility.** VoiceOver/TalkBack labels (mostly there), Dynamic Type in menus, contrast check.
- **iPad layout and Mac sandbox:**
  - Test and polish the iPad layout, or ship iPhone-only at first.
  - The Mac App Store needs the App Sandbox working; alternatively distribute the Mac app as a notarized
    download.
- **Android:** a real-device test pass (recording frame rate, `.local` name resolution, Wi-Fi join on
  several makers' phones), Play signing, target SDK, Data safety form.
- **Privacy and telemetry.** Decide whether to add crash reporting (for example, opt-in Sentry). If so, update
  the privacy manifest, Play Data safety and the privacy policy.
- **Automated tests:**
  - Unit tests for the depacketizer, timecode, base ISO, LUT parsing and JSON handling.
  - A fake camera and relay server for UI tests, so features can be tested without hardware.
- **CI and release:** builds and tests on every change, then TestFlight / Play internal uploads with version
  numbers set automatically.

### 4. Documentation and online presence

- **Website**, with your own domain:
  - Landing page: what it is, who it's for, the compatibility list.
  - Quick start.
  - Per-camera setup guides with screenshots.
  - Troubleshooting and FAQ.
  - Privacy policy, terms, and support contact.
  - The App Store and Play require a support URL and a privacy policy.
- **Quick-start card in the box:** four steps with pictures, and a QR to the online guide.
- **Videos:** a 2-minute setup video and a 1-minute feature tour. This is also the demo video App Review asks
  for, since reviewers won't have the hardware.
- **User manual:** convert the technical READMEs into a user manual (the website) and a separate developer and
  maintenance guide (in the repository).
- **Support:**
  - An email address or help desk.
  - Canned answers for the common issues.
  - A template asking for diagnostics, camera model, firmware and phone.

### 5. Testing and beta

- **Compatibility matrix:** camera models × firmware versions × phones (iPhone, iPad, Mac, two or three
  Android brands). Track results in a table on the website.
- **Field conditions:**
  - Wi-Fi range.
  - Interference (RF-busy locations).
  - Many viewers. The relay README has the bitrate math; confirm it in real use.
  - Battery-powered relay.
  - Hours-long shoots.
- **Beta program:**
  - TestFlight external group (public link, light review) and Play closed testing.
  - 10–20 users across camera models.
  - A feedback form.
- **Release criteria:**
  - No crashes in the beta's last two weeks.
  - Setup completed unaided by every beta tester.
  - Each launch camera verified.

### 6. Business and launch

- Company, bank and tax, and the developer accounts enrolled as an organization.
- The Paid Applications agreement accepted (App Store Connect is already asking).
- Pricing, sales channel (for example Shopify), shipping, returns and warranty terms.
- App Store and Play listings: screenshots (no people in frame), description, keywords, review notes with the
  demo video.
- Launch: announce to Blackmagic user communities, forums and YouTube reviewers, with demo units for two
  or three reviewers.

### 7. HDMI input: the next relay hardware (researched Oct 22, 2026)

> **Updated for cost:** the design now uses an RK3568 (today's processor) with an RK628D HDMI bridge and a
> 1080p60 stream, instead of the RK3588 below. It also covers camera control over Bluetooth, HDMI (CEC) and SDI.
> See [hardware/hdmi-relay/DESIGN.md](hardware/hdmi-relay/DESIGN.md).

**Why.** Today only Blackmagic cameras that stream over Ethernet work. An HDMI input lets any camera with HDMI
feed the relay: Sony, Canon, Panasonic, and Blackmagic Pocket cameras. It should also cut latency, because the
relay encodes the picture itself, tuned for speed, instead of relaying the camera's RTMP stream.

**What changes in the product:**
- **Viewing works with any HDMI camera.** Camera control stays Blackmagic-only and still needs Ethernet. For
  other cameras, the apps hide the control menus and keep the picture, LUTs and local capture.
- **The apps don't change for video.** The relay publishes HDMI to the same RTSP path
  (`live/pyxis`), so the apps see one stream whatever the source.
- **The relay picks the source:** HDMI when a signal is present, the camera's stream otherwise.
- **HDMI loop-through out** gives an on-set monitor the picture with no delay. It replaces decoding the stream
  for the HDMI output.

**Chip choice.** The R5C's RK3568 has no HDMI input and the board has no camera port, so the platform changes.

| Chip | How HDMI gets in | Notes |
|---|---|---|
| **RK3588** (full chip) | Built-in HDMI 2.0 receiver, up to 4K60 | Hardware H.264/H.265 encoder up to 8K30. Appears in Linux as a normal video capture device. |
| **RK3588S** (used in most modules, e.g. Radxa CM5) | No built-in receiver | Needs a bridge chip, like the RK3576. |
| **RK3576** | Rockchip **RK628D** bridge, HDMI 2.0 to the camera port, up to 4K60 | Cheaper and lower power; one more part and driver. |

The Lontium LT6911UXC is another HDMI-to-camera-port bridge. Users report 4K60 needs 8 lanes and it usually runs
4K30 in practice. On a Rockchip chip, Rockchip's own RK628D is the safer choice.

**Prototype: FriendlyElec NanoPC-T6** (full RK3588; about $150–200).
- Full-size HDMI 2.0 in, two 2.5GbE ports, two HDMI out, M.2 for the Wi-Fi module.
- Same vendor as the R5C, with the same FriendlyWrt and Rockchip MPP stack. The factory image, first boot and
  HDMI player carry over with the least rework.
- Alternatives: Orange Pi 5 Plus (full-size HDMI in; different vendor's software). Radxa ROCK 5B has only
  micro-HDMI in, which is too fragile on a camera rig.
- No off-the-shelf board is close enough to ship as-is. They're desktop-shaped, run on USB-C or 12 V rather than
  camera batteries, and have no SDI input.

**Production: our own carrier board around a bought module.** The module carries the processor, memory and
storage, the expensive and risky part to design. The carrier has:
- HDMI in and HDMI loop-through out.
- Ethernet, for Blackmagic camera control.
- A pre-certified Wi-Fi 6 module, to reduce radio certification.
- 7–17 V input for D-tap, V-mount or NP-F batteries, on a locking connector.
- A 1/4-20 mount and fanless cooling.
- **SDI in, as phase 2.** Most cinema cameras (ARRI, RED, URSA) output SDI rather than HDMI. A 3G-SDI receiver
  plus a bridge is enough for 1080p60 monitoring.

Module options: a full-RK3588 module such as FriendlyElec's CM3588 uses the built-in receiver. Check whether the
CM3588 brings the HDMI input out to its connector; not yet verified. An RK3588S module (Radxa CM5, about
$80–130) or an RK3576 module needs the RK628D. Rough cost: low tens of thousands of dollars for a 4–6 layer
carrier, prototypes and emissions testing. A fully custom board costs several times that and only pays off at
thousands of units.

**Latency target.** Hollyland's Mars 4K was measured at about 66 ms over HDMI and up to 83 ms in its phone app.
No published end-to-end figure exists for RK3588 capture, encode and stream. Around 100 ms looks realistic with:
- no B-frames
- intra-refresh instead of large keyframes
- RTSP over UDP
- a small buffer in the apps

Measure it on the prototype; today's latency through the camera's stream hasn't been measured either.

**Risks:**
- Rockchip's HDMI input is mature only in its vendor kernel, not mainline Linux. FriendlyWrt uses the vendor
  kernel.
- The encoder needs a larger reserved memory pool (CMA) to run stably.
- Some cameras send 4:4:4 or 10-bit over HDMI, which may need converting before encoding.

**Steps:**
1. Measure today's glass-to-glass latency through the camera's stream, as a baseline.
2. Buy a NanoPC-T6.
3. Get HDMI capture and hardware encode feeding MediaMTX on the same path, then measure latency with a running
   clock on screen.
4. Add source selection to the relay and a video-only mode to the apps.
5. Test with two or three non-Blackmagic cameras.
6. Choose the module, then design the carrier board (SDI later).

## Phases

| Phase | Goal | Main work | Done when |
|---|---|---|---|
| **0. Decide** (1–2 weeks) | Know what you're selling | Name and trademark check, hardware vs. image, pricing, company | Name and model chosen; accounts in the company's name |
| **1. Appliance** | Relay that sets itself up | Factory image, first boot with unique credentials, setup wizard, updates, factory reset, diagnostics, security review | A new unit goes from power-on to streaming using only the phone |
| **2. Onboarding and polish** | Apps a stranger can use | Rebrand, first-run flow, camera checklist, help and troubleshooting, error states, tests, CI | A first-time user finishes setup without help (watch 3–5 people try it) |
| **3. Docs and web** | Answers outside the app | Website, quick-start card, videos, privacy policy, support inbox | Every in-app help link resolves; store requirements met |
| **4. Beta** | Proof on real shoots | TestFlight external and Play closed testing, compatibility matrix, soak and field tests | Release criteria met |
| **5. Hardware readiness** (for a or c, in parallel from phase 1) | Sellable box | Sourcing, case production, certification, packaging, licenses | Certified units in stock |
| **6. Launch** | Available to buy | Store submissions, shop live, announcements | Apps approved, first orders shipped |

Phases 1–3 can overlap. Phase 5 has the longest lead time (certification), so start it early if you'll sell
hardware.

## Biggest risks

1. **Trademark.** Selling under "PYXIS" invites rejection or a takedown. Rename before any public listing.
2. **Radio certification** for a sold Wi-Fi device: cost and time. Option (b) avoids it at first.
3. **Security.** Shared default passwords in a product that's widely sold is the most likely real-world
   problem. Unique per-unit credentials are a must.
4. **Blackmagic firmware changes** can break the API or streaming. Track firmware releases and keep the
   fallbacks; the record fallback is one.
5. **Support load.** Networking problems are hard to debug remotely, so the diagnostics bundle and the
   in-app checks pay for themselves.
6. **Single-board supply.** The NanoPi R5C or its Wi-Fi module could go out of stock. Keep the image portable
   to a second board.
7. **HDMI-in platform change.** Moving to an RK3588 board or module (workstream 7) means a new image and
   driver stack. Prove it on the NanoPC-T6 before committing to a carrier board.

## Suggested next steps

1. Decide the name, what you sell (a/b/c) and pricing.
2. Start phase 1: the factory image and first-boot credentials.
3. In parallel, make the app's first-run onboarding and camera checklist (phase 2). It's useful for TestFlight
   testers right away.
