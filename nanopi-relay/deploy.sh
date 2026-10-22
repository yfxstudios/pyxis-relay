#!/bin/sh
# Run on the Mac. Sets up a NanoPi R5C (FriendlyWrt) as the PYXIS router + relay:
#   1. downloads the pinned MediaMTX release and verifies its SHA-256
#   2. renders the camera XML profile for ROUTER_IP
#   3. copies everything to the NanoPi over SSH and runs router/setup.sh there
#
# usage: ./deploy.sh [current-router-address]
#   current-router-address: where the NanoPi is reachable now; FriendlyWrt's default
#   is 192.168.2.1. After setup it moves to ROUTER_IP from config.env.
# Optional environment: SSH_PORT (default 22), SSH_USER (default root),
#   SSH_OPTS (extra ssh options, e.g. for a test VM).
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
MTX_VERSION="v1.21.2"
MTX_TARBALL="mediamtx_${MTX_VERSION}_linux_arm64.tar.gz"
MTX_SHA256="180a235374a548d9133cdd5e20f5dbd8b01317be1c86e0d7e66df585dc42ed6f"
MTX_URL="https://github.com/bluenviron/mediamtx/releases/download/${MTX_VERSION}/${MTX_TARBALL}"

TARGET=${1:-192.168.2.1}
SSH_PORT=${SSH_PORT:-22}
SSH_USER=${SSH_USER:-root}
SSH_OPTS=${SSH_OPTS:-}

[ -f "$HERE/config.env" ] || { echo "Create config.env first:  cp config.env.example config.env  (then edit it)" >&2; exit 1; }
# shellcheck source=/dev/null
. "$HERE/config.env"
[ "${WIFI_SSID:-CHANGE-ME}" != "CHANGE-ME" ] && [ "${WIFI_KEY:-CHANGE-ME}" != "CHANGE-ME" ] \
	|| { echo "Set WIFI_SSID and WIFI_KEY in config.env first." >&2; exit 1; }

# 1. MediaMTX, verified
mkdir -p "$HERE/.cache"
tarball="$HERE/.cache/$MTX_TARBALL"
if [ ! -f "$tarball" ]; then
	echo "Downloading MediaMTX $MTX_VERSION (linux arm64)..."
	curl -fSL --progress-bar -o "$tarball.part" "$MTX_URL"
	mv "$tarball.part" "$tarball"
fi
echo "$MTX_SHA256  $tarball" | shasum -a 256 -c - >/dev/null \
	|| { rm -f "$tarball"; echo "Checksum mismatch: deleted the download. Run again." >&2; exit 1; }
echo "MediaMTX tarball checksum OK"

# 2. Camera profile
profile=$("$HERE/make-profile.sh" "$ROUTER_IP")
echo "Camera profile: $profile"

# 3. Copy and run, over one SSH connection (one password prompt).
# Short fixed path: a Unix socket path must stay under ~104 characters.
ctl="/tmp/pyxis-relay-ssh-%C"
# shellcheck disable=SC2086  # SSH_OPTS is a list of options on purpose
set -- -p "$SSH_PORT" -o ControlMaster=auto -o ControlPath="$ctl" -o ControlPersist=120 $SSH_OPTS "$SSH_USER@$TARGET"

echo "Connecting to $SSH_USER@$TARGET (FriendlyWrt's default password is 'password', or empty)..."
ssh "$@" 'rm -rf /tmp/pyxis-relay && mkdir -p /tmp/pyxis-relay/router'

stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/router"
cp "$HERE/config.env" "$tarball" "$stage/"
cp "$HERE/router/setup.sh" "$HERE/router/mediamtx.yml" "$HERE/router/mediamtx.init" \
	"$HERE/router/pyxisrelay.avahi.service" "$HERE/router/status.sh" "$stage/router/"
mv "$stage/router/setup.sh" "$stage/setup.sh"
cp -R "$HERE/router/web" "$stage/router/web"
cp "$HERE/router/pyxis-hdmi.init" "$HERE/router/autostart.sh" "$HERE/router/pyxis-autostart.init" "$HERE/router/camera.cgi" "$stage/router/"
# The HDMI player is optional: built separately with hdmi/build.sh.
if [ -f "$HERE/hdmi/pyxis-hdmi" ]; then
	cp "$HERE/hdmi/pyxis-hdmi" "$stage/router/pyxis-hdmi"
	cp "$HERE/hdmi/THIRD_PARTY_LICENSES.txt" "$stage/router/pyxis-hdmi-LICENSES.txt"
fi
# Plain ustar without macOS metadata, so BusyBox tar unpacks it cleanly.
(cd "$stage" && COPYFILE_DISABLE=1 tar --format ustar --no-xattrs --no-mac-metadata -cf - .) \
	| ssh "$@" 'tar -xf - -C /tmp/pyxis-relay'

ssh "$@" 'sh /tmp/pyxis-relay/setup.sh'
ssh -O exit "$@" 2>/dev/null || true

cat <<EOF

Next:
  1. Plug the camera into the NanoPi's LAN port. Join Wi-Fi "$WIFI_SSID" from this Mac.
  2. Load $profile on the camera (CFexpress card or USB-C drive:
     Setup -> page 11 -> Import Stream Settings), choose "PYXIS LAN Relay (RTMP)", start streaming.
  3. Watch: http://$ROUTER_IP:8889/live/pyxis/  or PYXIS Viewer -> "Another Mac / host".
  4. Check health any time:  ssh $SSH_USER@$ROUTER_IP pyxis-relay-status
EOF
