#!/bin/sh
# Builds the relay factory image (run on the Mac; needs Docker):
#   FriendlyElec's official FriendlyWrt image for the NanoPi R5C (pinned by checksum)
#   + the relay installer (the same setup.sh and files deploy.sh sends, plus MediaMTX and the
#     HDMI player) in /usr/share/relay/installer
#   + the one-time first-boot setup (files/etc/init.d/relay-firstboot).
# The result has no Wi-Fi or admin passwords in it: provision.sh adds each unit's own.
#
# usage: ./build-image.sh            -> dist/relay-factory-<date>.img.gz
#        NO_HDMI=1 ./build-image.sh  -> without the HDMI player (skips building it)
#
# Everything comes from this repository or is downloaded and checked against pinned checksums.
# Building the HDMI player needs zig, cmake, meson and ninja (brew install zig cmake meson ninja).
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
RELAY=$(cd "$HERE/.." && pwd)

# FriendlyWrt 25.12 for the R5S/R5C, from FriendlyElec's own release builds.
BASE_TAG="FriendlyWrt-2026-10-13"
BASE_FILE="R5S-R5C-Series-FriendlyWrt-25.12.img.gz"
BASE_SHA256="aac1054ee2be228f44bf608c828777992a95fd3a371476fa0f26635f0ce61d66"
BASE_URL="https://github.com/friendlyarm/Actions-FriendlyWrt/releases/download/$BASE_TAG/$BASE_FILE"
BASE="$HERE/.cache/R5S-R5C-Series-FriendlyWrt-25.12-${BASE_TAG#FriendlyWrt-}.img.gz"

# MediaMTX, the same pinned release deploy.sh and setup.sh use
MTX_VERSION="v1.21.2"
MTX_TARBALL="mediamtx_${MTX_VERSION}_linux_arm64.tar.gz"
MTX_SHA256="180a235374a548d9133cdd5e20f5dbd8b01317be1c86e0d7e66df585dc42ed6f"
MTX_URL="https://github.com/bluenviron/mediamtx/releases/download/${MTX_VERSION}/${MTX_TARBALL}"

VERSION=${RELAY_VERSION:-$(date +%Y%m%d)}
OUT="$HERE/dist/relay-factory-$VERSION.img.gz"

command -v docker >/dev/null && docker info >/dev/null 2>&1 || { echo "Docker isn't running." >&2; exit 1; }

# 1. base image, verified
mkdir -p "$HERE/.cache" "$HERE/dist"
if [ ! -f "$BASE" ]; then
	echo "Downloading $BASE_FILE ($BASE_TAG)..."
	curl -fSL --progress-bar -o "$BASE.part" "$BASE_URL"
	mv "$BASE.part" "$BASE"
fi
echo "$BASE_SHA256  $BASE" | shasum -a 256 -c - >/dev/null || { echo "Base image checksum mismatch: delete $BASE and run again." >&2; exit 1; }
echo "Base image OK ($BASE_TAG)"

# 2. MediaMTX, verified
mkdir -p "$RELAY/.cache"
if [ ! -f "$RELAY/.cache/$MTX_TARBALL" ]; then
	echo "Downloading MediaMTX $MTX_VERSION (linux arm64)..."
	curl -fSL --progress-bar -o "$RELAY/.cache/$MTX_TARBALL.part" "$MTX_URL"
	mv "$RELAY/.cache/$MTX_TARBALL.part" "$RELAY/.cache/$MTX_TARBALL"
fi
echo "$MTX_SHA256  $RELAY/.cache/$MTX_TARBALL" | shasum -a 256 -c - >/dev/null \
	|| { rm -f "$RELAY/.cache/$MTX_TARBALL"; echo "MediaMTX checksum mismatch: deleted the download. Run again." >&2; exit 1; }
echo "MediaMTX OK ($MTX_VERSION)"

# 3. the HDMI player, built from source (hdmi/build.sh) unless it's already built or NO_HDMI=1
if [ "${NO_HDMI:-0}" != 1 ] && [ ! -f "$RELAY/hdmi/pyxis-hdmi" ]; then
	for t in zig cmake meson ninja; do
		command -v $t >/dev/null || { echo "Building the HDMI player needs $t (brew install zig cmake meson ninja), or run with NO_HDMI=1." >&2; exit 1; }
	done
	echo "Building the HDMI player (hdmi/build.sh)..."
	"$RELAY/hdmi/build.sh" >/dev/null || { echo "HDMI player build failed (run ../hdmi/build.sh to see why), or run with NO_HDMI=1." >&2; exit 1; }
fi
if [ "${NO_HDMI:-0}" = 1 ] || [ ! -f "$RELAY/hdmi/pyxis-hdmi" ]; then
	echo "Note: no HDMI player in this image."
fi

# 4. what goes into the image
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
inst="$stage/usr/share/relay/installer"
mkdir -p "$inst/router" "$stage/etc/relay"
cp "$RELAY/router/setup.sh" "$inst/setup.sh"
cp "$RELAY/.cache/$MTX_TARBALL" "$inst/"
for f in mediamtx.yml mediamtx.init pyxisrelay.avahi.service status.sh pyxis-hdmi.init autostart.sh pyxis-autostart.init camera.cgi; do
	cp "$RELAY/router/$f" "$inst/router/"
done
cp -R "$RELAY/router/web" "$inst/router/web"
if [ "${NO_HDMI:-0}" != 1 ] && [ -f "$RELAY/hdmi/pyxis-hdmi" ]; then
	cp "$RELAY/hdmi/pyxis-hdmi" "$inst/router/pyxis-hdmi"
	cp "$RELAY/hdmi/THIRD_PARTY_LICENSES.txt" "$inst/router/pyxis-hdmi-LICENSES.txt"
fi
cp -R "$HERE/files/." "$stage/"
cp "$HERE/brand.env" "$stage/etc/relay/brand.env"
echo "RELAY_VERSION=$VERSION" > "$stage/etc/relay/version"
echo "BASE=$BASE_TAG/$BASE_FILE" >> "$stage/etc/relay/version"

# 5. put it into the image's root filesystem (in a Linux container: loop-mount the ext4 partition)
docker build -q -t relay-factory-tools "$HERE" >/dev/null
docker run --rm --privileged \
	-v "$BASE:/in/base.img.gz:ro" -v "$stage:/stage:ro" -v "$HERE/dist:/out" \
	-e OUTNAME="$(basename "$OUT")" relay-factory-tools sh -eu -c '
		gunzip -c /in/base.img.gz > /tmp/image.img
		# the "rootfs" partition: start and size in 512-byte sectors
		set -- $(sfdisk -J /tmp/image.img | python3 -c "import json,sys; p=[x for x in json.load(sys.stdin)[\"partitiontable\"][\"partitions\"] if x.get(\"name\")==\"rootfs\"][0]; print(p[\"start\"], p[\"size\"])")
		start=$1; size=$2
		dd if=/tmp/image.img of=/tmp/rootfs.ext4 bs=512 skip=$start count=$size status=none
		mkdir -p /mnt/root
		mount -o loop /tmp/rootfs.ext4 /mnt/root
		cp -R /stage/. /mnt/root/
		chown -R 0:0 /mnt/root/usr/share/relay /mnt/root/etc/relay /mnt/root/etc/init.d/relay-firstboot /mnt/root/etc/uci-defaults/zz-relay-firstboot
		chmod 755 /mnt/root/etc/init.d/relay-firstboot /mnt/root/usr/share/relay/installer/setup.sh
		chmod 700 /mnt/root/etc/relay
		# Enable the first-boot service in the image itself. Enabling it from uci-defaults is too
		# late: procd has already listed the services to start, so it would only run on the
		# boot after (found on a real R5C).
		ln -sf ../init.d/relay-firstboot /mnt/root/etc/rc.d/S99relay-firstboot
		umount /mnt/root
		e2fsck -fy /tmp/rootfs.ext4 >/dev/null || [ $? -le 1 ]
		dd if=/tmp/rootfs.ext4 of=/tmp/image.img bs=512 seek=$start conv=notrunc status=none
		gzip -6 -c /tmp/image.img > "/out/$OUTNAME.part"
		mv "/out/$OUTNAME.part" "/out/$OUTNAME"
	'
(cd "$HERE/dist" && shasum -a 256 "$(basename "$OUT")" > "$(basename "$OUT").sha256")
echo "Factory image: $OUT"
echo "Next: ./provision.sh to make a unit's image and label."
