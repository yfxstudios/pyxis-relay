# App Store submission: PYXIS Viewer (iPhone/iPad)

## Where it stands (Oct 21, 2026)

Released to **TestFlight internal testing**:
- App Store Connect app record: **PYXIS Viewer** (iOS, bundle ID `com.matthewyak.pyxisviewer`, SKU
  `pyxisviewer-ios`, Apple ID 6825654335).
- Build **1.0 (1)** was uploaded and processed. It expires in 90 days.
- TestFlight group **Internal** has matt.yakligian@gmail.com as its tester. Automatic distribution is on,
  so every new build uploaded from Xcode goes to the group without any extra step.
- The app has an App Store privacy manifest (`PyxisViewer/PrivacyInfo.xcprivacy`: no tracking, no
  data collection, UserDefaults for its own settings) and `ITSAppUsesNonExemptEncryption = false`.

**New builds:** raise `CURRENT_PROJECT_VERSION` in the project, archive, then export with
`ExportOptions.plist` with `destination` set to `upload`. The archive for 1.0 (1) is in Xcode's Organizer.

**To add testers:** they must be users on the App Store Connect team (Users and Access). Then add them
to the Internal group. For people outside the team, make an external group (Beta App Review) with a
public link.

**Before any App Store release:** the Account Holder must accept the updated Paid Applications
Schedule (App Store Connect shows a banner). Also see the name, screenshots, privacy policy and review
notes below.

## Choose how to release it

The app only works with a PYXIS camera **and** this project's relay. That matters for App Review and for who
can use it:

| Option | Review | Who can install |
|---|---|---|
| **TestFlight, internal testing** | None | Up to 100 people you add as users in App Store Connect. Builds last 90 days. |
| **TestFlight, external (public link)** | Light Beta App Review on the first build | Anyone with the link, up to 10,000. Builds last 90 days. |
| **Unlisted App Store app** | Full App Review, plus an Apple request form | Anyone with the direct link; not searchable. |
| **Public App Store** | Full App Review | Everyone. Reviewers need a demo video, since they don't have the hardware. |

For your own crew, **TestFlight internal** is quickest: no review, available within minutes of upload.

## 1. Create the app record (you)

App Store Connect → Apps → **+** → New App:
- Platforms: **iOS**. Add macOS later; see "Mac" below.
- Name: see "Name" below. It must be unique on the App Store.
- Primary language: English (U.S.).
- Bundle ID: **com.matthewyak.pyxisviewer**. It's already registered and appears in the list.
- SKU: `pyxisviewer-ios` (anything you like; never shown).
- User access: Full access.

### Name

"PYXIS" is Blackmagic Design's product name. App Review rejects names that suggest a company made or
endorsed an app when it didn't (guidelines 4.1 and 5.2). Safer choices:
- **Relay Viewer for PYXIS 12K**: names the camera descriptively, "for" style.
- **Rig Monitor – Live Camera Feed**: no trademark in the name; mention the PYXIS in the description.

The name under the icon (`CFBundleDisplayName`, now "PYXIS Viewer") can stay or change to match. Tell me
and I'll update it.

## 2. Upload the build (me, on your go-ahead)

```bash
xcodebuild -exportArchive -archivePath <archive> -exportOptionsPlist ExportOptions.plist -allowProvisioningUpdates
```

That's the same export as before, with `destination` set to `upload`. It uses the Apple account already signed in to
Xcode on this Mac. No password is typed. For each new build, raise `CURRENT_PROJECT_VERSION`.

## 3. Store listing drafts

**Subtitle** (30 characters): `Live view & control for PYXIS`

**Promotional text** (170): `Watch your PYXIS 12K live on iPhone with a single QR scan, and control it like the camera's own touchscreen.`

**Description:**

> A live monitor and remote control for the Blackmagic PYXIS 12K, through the PYXIS relay.
>
> • One scan: the relay's QR code joins its Wi-Fi and opens the live picture.
> • Low delay: hardware decoding, every frame shown the moment it arrives.
> • Camera control laid out like the camera's touchscreen: frame rate, shutter, iris, ISO (with base ISO marked), white balance, tint, record, media, power, and the full camera menu.
> • Tap to focus, with single, continuous, face and object autofocus (with a supported lens).
> • Monitor LUTs: built-in film looks and your own .cube files, applied in the app only. The camera isn't changed.
> • Clean feed: swipe the controls away.
> • Capture on your phone: grab a full-resolution frame, or record what you see.
>
> Requires a Blackmagic PYXIS camera streaming to a PYXIS relay on the same network. Not affiliated with or endorsed by Blackmagic Design.

**Keywords** (100): `blackmagic,camera,monitor,cinema,remote,control,live,stream,LUT,focus,filmmaking,video,assist`

**Category:** Photo & Video. **Age rating:** answer "None" throughout, which gives 4+.

**Support URL / Marketing URL:** a page you control. The support URL is required.

## 4. App Privacy (App Store Connect → App Privacy)

- Data collection: **"No, we do not collect data from this app."** The app only talks to the relay and
  camera on the local network. Frames and recordings stay on the device or in your Photos.
- **Privacy policy URL** (required). It has to be a public web page. Draft text:

> PYXIS Viewer doesn't collect, store or share any personal data. It connects only to the camera relay and
> camera on your local network. Wi-Fi details from the relay's QR code are used only to join that network.
> A camera login, if you enter one, is kept in your device's Keychain and sent only to your camera over
> HTTPS. Frames and recordings you capture are saved only to your device's Photos. There are no accounts,
> analytics, advertising or third-party services. Contact: <your email>.

## 5. Screenshots

Required:
- **iPhone 6.9"**: 1320 × 2868 (or 1290 × 2796), at least one, up to 10.
- **iPad 13"**: 2064 × 2752, only while the app supports iPad. It does now. To skip iPad, make it
  iPhone-only; iPads would still run it in iPhone mode.

Good shots: the live view with controls, the ISO picker, the WB picker, Monitor LUTs, tap-to-focus,
and the welcome screen. Take them with no one in frame. I can take them in the Simulator against the live
relay.

## 6. Review notes (App Review Information)

> This app is a monitor/remote for the Blackmagic PYXIS 12K camera and works only with that camera and a
> PYXIS relay (a small router running MediaMTX) on the same network, so it can't be fully tested without
> the hardware. A demo video showing setup and every feature is at: <link>.
> No sign-in is required. The app asks to join the relay's Wi-Fi (NEHotspotConfiguration) when a relay QR
> code is scanned, and for Local Network access to reach the relay and camera.

A demo video (screen recording of the app with the camera) is effectively required for full App Review.
TestFlight internal testing doesn't need it.

## Mac

The Mac build isn't ready for the Mac App Store or Mac TestFlight. Both require the App Sandbox, and with
the sandbox on, the app couldn't reach the relay. Options:
- **Fix the sandboxed build** (likely local-network permission or entitlement details), then add macOS to
  the same App Store record.
- **Distribute it directly** (Developer ID signing + notarization): no sandbox needed, shared as a download.

## Android

Google Play is a separate process: a Play developer account, a signed release bundle (`.aab`) with an
upload key, store listing, Data safety form, and closed testing before production.
