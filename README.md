# PYXIS 12K → live view

## How it works

```
PYXIS 12K ──RTMP──▶  NanoPi R5C relay "pyxis-relay"  ──▶  PYXIS Viewer (iPhone, iPad, Mac, Android)
 (Ethernet)          Wi-Fi AP PYXIS-Stream, 192.168.50.1     RTSP    rtsp://pyxis-relay.local:8554/live/pyxis
                     MediaMTX, HDMI output, settings page    WebRTC  http://192.168.50.1:8889/live/pyxis/
                                                             HLS     http://192.168.50.1:8888/live/pyxis/index.m3u8
                                                             HDMI    straight from the relay
```

The PYXIS streaming engine can only **send** a stream (it's an RTMP caller), so it can't host one for others
to open. The camera streams to the relay, which re-shares it on its own Wi-Fi network and on HDMI. The relay
also starts the camera's stream when the camera comes on, and restarts it whenever it stops.

## Files

| File | What it is |
|---|---|
| `nanopi-relay/` | NanoPi R5C router + relay: MediaMTX, Wi-Fi AP, HDMI output, stream auto-start, settings page (see its README) |
| `PyxisViewer-iOS/` | iPhone, iPad and Mac app: live picture, camera control, monitor LUTs, autofocus; one QR scan joins the relay's Wi-Fi on iPhone (see its README) |
| `PyxisViewer-Android/` | Android app: the same viewer, camera control, monitor LUTs and autofocus; the same QR (see its README) |
| `profiles/PYXIS-LAN-Template.xml` | Blackmagic Streaming XML profile with a `__RELAY_IP__` placeholder (`nanopi-relay/make-profile.sh` fills it in) |
| `profiles/PYXIS-LAN-192.168.68.40.xml` | The profile for the earlier setup, where a Mac on the home network was the relay. Not used with the R5C. |
| `case/` | Enclosure design |

The profile defines one service, **PYXIS LAN Relay (RTMP)**, with three quality levels: LAN High, LAN Medium
and LAN Low (Wi-Fi). Each covers 1080p30/60 and 2160p30/60 in H.264.

## Watching

- **iPhone or Android:** scan the QR code from the relay's settings page (`http://pyxis-relay.local/`). The
  app joins PYXIS-Stream and plays. Already on PYXIS-Stream? Just open the app.
- **Mac:** join PYXIS-Stream from the Wi-Fi menu and open PYXIS Viewer. It finds the relay by itself.
- **Monitor or TV:** the relay's HDMI output.
- **Any browser:** `http://192.168.50.1:8889/live/pyxis/` (under a second behind, video only), or HLS with
  sound in Safari (about 4–8 s behind).
- **VLC or OBS:** `rtsp://pyxis-relay.local:8554/live/pyxis`.

Setup, the camera profile, auto-start, the HDMI output and measurements are in `nanopi-relay/README.md`.

## Notes / limits

- Anyone on the PYXIS-Stream Wi-Fi can watch: the Wi-Fi password is the only lock. Nothing is reachable from
  outside the relay's network.
- Streaming is H.264. That works on every device, but the camera's maximum streaming resolution and bitrate may be lower
  than the 2160p entries in the profile. If so, the camera uses whichever entry matches its streaming format.
- The camera's stream is separate from what it records internally. You can record 12K BRAW and stream at the same time.
