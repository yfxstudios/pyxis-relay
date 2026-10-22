#!/bin/sh
# Turns a NanoPi R5C running FriendlyWrt (OpenWrt) into the PYXIS stream router + relay:
#   - LAN bridge (Ethernet LAN port + Wi-Fi AP) at ROUTER_IP/24 with DHCP
#     (FriendlyWrt on the R5C: WAN = eth0, LAN = eth1 inside bridge br-lan; the port
#     assignment is left exactly as the firmware set it up)
#   - static DHCP lease for the camera
#   - Wi-Fi access point for viewers (all other Wi-Fi networks on the box are disabled)
#   - MediaMTX relay as a procd service
#   - mDNS advert (_pyxisrelay._tcp) so PYXIS Viewer finds the relay
#
# Run on the NanoPi from the folder deploy.sh copied (it holds this script, config.env,
# the router/ files and the MediaMTX tarball):   sh setup.sh
# Safe to run again after editing config.env.

set -eu

MTX_VERSION="v1.21.2"
MTX_TARBALL="mediamtx_${MTX_VERSION}_linux_arm64.tar.gz"
MTX_SHA256="180a235374a548d9133cdd5e20f5dbd8b01317be1c86e0d7e66df585dc42ed6f"
MTX_URL="https://github.com/bluenviron/mediamtx/releases/download/${MTX_VERSION}/${MTX_TARBALL}"

HERE=$(cd "$(dirname "$0")" && pwd)

say()  { printf '\n==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- config + checks

[ -f "$HERE/config.env" ] || die "config.env not found next to setup.sh"
# shellcheck source=/dev/null
. "$HERE/config.env"

: "${ROUTER_IP:?}" "${ROUTER_HOSTNAME:?}" "${DHCP_START:?}" "${DHCP_LIMIT:?}" "${CAMERA_IP:?}"
: "${WIFI_SSID:?}" "${WIFI_KEY:?}" "${WIFI_COUNTRY:?}" "${WIFI_BAND:?}" "${WIFI_CHANNEL:?}"
CAMERA_MAC="${CAMERA_MAC:-}"
WIFI_ENCRYPTION="${WIFI_ENCRYPTION:-auto}"

is_uint() { case "$1" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }

valid_ip() {
	old_ifs=$IFS; IFS=.
	# shellcheck disable=SC2086  # split on dots on purpose
	set -- $1
	IFS=$old_ifs
	[ $# -eq 4 ] || return 1
	for o in "$@"; do
		is_uint "$o" && [ "$o" -le 255 ] || return 1
	done
}

prefix_of() { echo "${1%.*}"; }
host_of()   { echo "${1##*.}"; }

valid_ip "$ROUTER_IP" || die "ROUTER_IP is not an IPv4 address: $ROUTER_IP"
valid_ip "$CAMERA_IP" || die "CAMERA_IP is not an IPv4 address: $CAMERA_IP"
[ "$(prefix_of "$CAMERA_IP")" = "$(prefix_of "$ROUTER_IP")" ] \
	|| die "CAMERA_IP must be in the router's /24 network ($(prefix_of "$ROUTER_IP").x)"
if ! is_uint "$DHCP_START" || ! is_uint "$DHCP_LIMIT"; then
	die "DHCP_START and DHCP_LIMIT must be numbers"
fi

router_host=$(host_of "$ROUTER_IP")
camera_host=$(host_of "$CAMERA_IP")
pool_end=$((DHCP_START + DHCP_LIMIT - 1))
[ "$router_host" -ge 1 ] && [ "$router_host" -le 254 ] || die "ROUTER_IP must end in 1-254"
[ "$camera_host" -ge 2 ] && [ "$camera_host" -le 254 ] || die "CAMERA_IP must end in 2-254"
[ "$camera_host" -ne "$router_host" ] || die "CAMERA_IP can't equal ROUTER_IP"
[ "$DHCP_START" -ge 2 ] && [ "$DHCP_LIMIT" -ge 1 ] && [ "$pool_end" -le 254 ] \
	|| die "DHCP pool .$DHCP_START-.$pool_end must fit within .2-.254"
if [ "$camera_host" -ge "$DHCP_START" ] && [ "$camera_host" -le "$pool_end" ]; then
	die "CAMERA_IP (.$camera_host) is inside the DHCP pool (.$DHCP_START-.$pool_end); move it outside"
fi
if [ "$router_host" -ge "$DHCP_START" ] && [ "$router_host" -le "$pool_end" ]; then
	die "ROUTER_IP (.$router_host) is inside the DHCP pool (.$DHCP_START-.$pool_end)"
fi

if [ -n "$CAMERA_MAC" ]; then
	echo "$CAMERA_MAC" | grep -Eq '^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$' \
		|| die "CAMERA_MAC must look like AA:BB:CC:DD:EE:FF"
fi

case "$ROUTER_HOSTNAME" in
	''|-*|*[!A-Za-z0-9-]*) die "ROUTER_HOSTNAME may only contain letters, digits and '-'" ;;
esac

[ "$WIFI_SSID" != "CHANGE-ME" ] || die "Set WIFI_SSID in config.env"
[ "$WIFI_KEY" != "CHANGE-ME" ] || die "Set WIFI_KEY in config.env"
ssid_len=$(printf '%s' "$WIFI_SSID" | wc -c)
key_len=$(printf '%s' "$WIFI_KEY" | wc -c)
[ "$ssid_len" -ge 1 ] && [ "$ssid_len" -le 32 ] || die "WIFI_SSID must be 1-32 bytes"
[ "$key_len" -ge 8 ] && [ "$key_len" -le 63 ] || die "WIFI_KEY must be 8-63 characters"
case "$WIFI_BAND" in 2g|5g) ;; *) die "WIFI_BAND must be 2g or 5g" ;; esac
case "$WIFI_COUNTRY" in [A-Z][A-Z]) ;; *) die "WIFI_COUNTRY must be a two-letter code like US" ;; esac
case "$WIFI_CHANNEL" in
	default) if [ "$WIFI_BAND" = "5g" ]; then WIFI_CHANNEL=36; else WIFI_CHANNEL=6; fi ;;
	auto) ;;
	*) is_uint "$WIFI_CHANNEL" || die "WIFI_CHANNEL must be default, auto or a number" ;;
esac
case "$WIFI_ENCRYPTION" in auto|sae-mixed|psk2|sae) ;; *) die "WIFI_ENCRYPTION must be auto, sae-mixed, psk2 or sae" ;; esac

[ "$(uname -m)" = "aarch64" ] || die "This must run on the NanoPi (aarch64), not on $(uname -m)"
command -v uci >/dev/null || die "uci not found: this doesn't look like FriendlyWrt/OpenWrt"

board=$(cat /tmp/sysinfo/board_name 2>/dev/null || echo unknown)
case "$board" in
	*nanopi-r5c*) ;;
	*) warn "This is built for the NanoPi R5C; this board reports \"$board\". Continuing." ;;
esac

# The Wi-Fi network joins the LAN, which only works if the LAN is a bridge. FriendlyWrt
# and OpenWrt always create one (br-lan); refuse to continue if it was changed.
lan_dev=$(uci -q get network.lan.device || true)
lan_ports=""
for s in $(uci -q show network | sed -n 's/^network\.\([^.=]*\)=device$/\1/p'); do
	if [ "$(uci -q get "network.$s.name")" = "$lan_dev" ] && [ "$(uci -q get "network.$s.type")" = "bridge" ]; then
		lan_ports=$(uci -q get "network.$s.ports" || true)
	fi
done
[ -n "$lan_ports" ] || die "The LAN (device '${lan_dev:-none}') isn't a bridge with ports, so Wi-Fi can't join it. Reset the network settings to FriendlyWrt's defaults and try again."
wan_dev=$(uci -q get network.wan.device || echo none)

# ---------------------------------------------------------------- MediaMTX

install_mediamtx() {
	say "Installing MediaMTX $MTX_VERSION"
	tarball="$HERE/$MTX_TARBALL"
	if [ ! -f "$tarball" ]; then
		echo "Tarball not found next to setup.sh; downloading it (needs internet on the WAN port)."
		if command -v uclient-fetch >/dev/null; then
			uclient-fetch -q -O "$tarball" "$MTX_URL" || die "Download failed. Run deploy.sh from the Mac instead."
		else
			wget -q -O "$tarball" "$MTX_URL" || die "Download failed. Run deploy.sh from the Mac instead."
		fi
	fi
	echo "$MTX_SHA256  $tarball" | sha256sum -c - >/dev/null 2>&1 \
		|| die "Checksum mismatch for $MTX_TARBALL; refusing to install it"
	echo "Checksum OK ($MTX_SHA256)"

	tmp=$(mktemp -d)
	tar -xzf "$tarball" -C "$tmp" mediamtx || die "Could not unpack $MTX_TARBALL"
	if [ -f /usr/bin/mediamtx ] && cmp -s "$tmp/mediamtx" /usr/bin/mediamtx; then
		echo "Same MediaMTX binary already installed"
	else
		# The binary is ~64 MB; an old copy being replaced frees its space.
		need_kb=$(( $(wc -c < "$tmp/mediamtx") / 1024 + 1024 ))
		old_kb=0
		[ -f /usr/bin/mediamtx ] && old_kb=$(( $(wc -c < /usr/bin/mediamtx) / 1024 ))
		free_kb=$(df -k /usr/bin | awk 'NR==2 {print $4}')
		[ $((free_kb + old_kb)) -ge "$need_kb" ] \
			|| die "Not enough space in /usr/bin: need ${need_kb} KB, have $((free_kb + old_kb)) KB"

		if [ -x /etc/init.d/mediamtx ]; then /etc/init.d/mediamtx stop >/dev/null 2>&1 || true; fi
		rm -f /usr/bin/mediamtx
		cp "$tmp/mediamtx" /usr/bin/mediamtx || die "Copying MediaMTX to /usr/bin failed"
		chmod 755 /usr/bin/mediamtx
	fi
	rm -rf "$tmp"

	mkdir -p /etc/mediamtx
	cp "$HERE/router/mediamtx.yml" /etc/mediamtx/mediamtx.yml
	cp "$HERE/router/mediamtx.init" /etc/init.d/mediamtx
	chmod 755 /etc/init.d/mediamtx
	cp "$HERE/router/status.sh" /usr/bin/pyxis-relay-status
	chmod 755 /usr/bin/pyxis-relay-status
	# Keep the relay files across FriendlyWrt/OpenWrt sysupgrades.
	for f in /usr/bin/mediamtx /etc/mediamtx/ /etc/init.d/mediamtx /usr/bin/pyxis-relay-status; do
		grep -qxF "$f" /etc/sysupgrade.conf 2>/dev/null || echo "$f" >> /etc/sysupgrade.conf
	done
	/etc/init.d/mediamtx enable
	echo "Installed $(/usr/bin/mediamtx --version 2>/dev/null || echo "$MTX_VERSION")"
}

# ---------------------------------------------------------------- network + DHCP

configure_network() {
	say "LAN: $ROUTER_IP/24, DHCP .$DHCP_START-.$pool_end, hostname $ROUTER_HOSTNAME"
	echo "Ports: LAN (camera) = $lan_ports in $lan_dev, WAN (optional upstream) = $wan_dev"
	uci set system.@system[0].hostname="$ROUTER_HOSTNAME"

	uci set network.lan.proto='static'
	uci -q delete network.lan.ipaddr || true
	uci set network.lan.ipaddr="$ROUTER_IP"
	uci set network.lan.netmask='255.255.255.0'

	uci set dhcp.lan.start="$DHCP_START"
	uci set dhcp.lan.limit="$DHCP_LIMIT"
	uci set dhcp.lan.leasetime='12h'

	uci -q delete dhcp.pyxis_camera || true
	if [ -n "$CAMERA_MAC" ]; then
		uci set dhcp.pyxis_camera='host'
		uci set dhcp.pyxis_camera.name='pyxis-camera'
		uci set dhcp.pyxis_camera.mac="$CAMERA_MAC"
		uci set dhcp.pyxis_camera.ip="$CAMERA_IP"
		echo "Camera $CAMERA_MAC always gets $CAMERA_IP"
	else
		warn "CAMERA_MAC is empty: no static lease. The camera gets an address from the pool."
	fi
}

# ---------------------------------------------------------------- Wi-Fi AP

radio_band() {
	b=$(uci -q get "wireless.$1.band" || true)
	if [ -z "$b" ]; then
		case "$(uci -q get "wireless.$1.hwmode" || true)" in
			11a) b=5g ;;
			11b|11g) b=2g ;;
		esac
	fi
	echo "$b"
}

supports_sae() {
	for bin in /usr/sbin/hostapd /usr/sbin/wpad; do
		[ -x "$bin" ] && "$bin" -vsae >/dev/null 2>&1 && return 0
	done
	return 1
}

configure_wifi() {
	say "Wi-Fi access point \"$WIFI_SSID\" ($WIFI_BAND)"
	radios=$(uci -q show wireless | sed -n 's/^wireless\.\([^.=]*\)=wifi-device$/\1/p' || true)
	if [ -z "$radios" ]; then
		wifi config >/dev/null 2>&1 || true
		radios=$(uci -q show wireless | sed -n 's/^wireless\.\([^.=]*\)=wifi-device$/\1/p' || true)
	fi
	if [ -z "$radios" ]; then
		warn "No Wi-Fi radio found. Fit the M.2 RTL8822CE module (or a supported USB Wi-Fi dongle),"
		warn "reboot, and run setup.sh again. Skipping Wi-Fi; the relay still works over Ethernet."
		WIFI_DONE=no
		return 0
	fi

	# Prefer a radio already set to the requested band. OpenWrt labels a multi-band radio
	# with its highest band, so a Wi-Fi 6E/7 adapter shows up as "6g"; those all do 5g
	# and 2g too, so such a radio is switched to the requested band.
	radio=""
	for r in $radios; do
		[ "$(radio_band "$r")" = "$WIFI_BAND" ] && { radio=$r; break; }
	done
	if [ -z "$radio" ]; then
		radio=$(echo "$radios" | head -n 1)
		current=$(radio_band "$radio")
		if [ "$current" = "6g" ] || { [ "$current" = "5g" ] && [ "$WIFI_BAND" = "2g" ]; }; then
			echo "Switching $radio from $current to $WIFI_BAND"
			uci set "wireless.$radio.band=$WIFI_BAND"
			ht=$(uci -q get "wireless.$radio.htmode" || true)
			case "$WIFI_BAND:$ht" in
				5g:*320|5g:*160) uci set "wireless.$radio.htmode=${ht%???}80" ;;
				2g:HE*)  uci set "wireless.$radio.htmode=HE20" ;;
				2g:EHT*) uci set "wireless.$radio.htmode=EHT20" ;;
				2g:*)    uci set "wireless.$radio.htmode=HT20" ;;
			esac
		else
			warn "No $WIFI_BAND radio found; using $radio on ${current:-its own band}. Set WIFI_BAND to match your adapter."
		fi
	fi

	if ! [ -x /usr/sbin/hostapd ] && ! [ -x /usr/sbin/wpad ]; then
		warn "hostapd/wpad is not installed, so the access point can't start. Install a wpad package first."
	fi
	enc=$WIFI_ENCRYPTION
	if [ "$enc" = "auto" ]; then
		if supports_sae; then enc='sae-mixed'; else enc='psk2'; fi
	fi
	if [ "$(radio_band "$radio")" = "6g" ] && [ "$enc" != "sae" ]; then
		warn "6 GHz only allows WPA3; using encryption sae instead of $enc."
		enc='sae'
	fi

	uci set "wireless.$radio.disabled=0"
	uci set "wireless.$radio.channel=$WIFI_CHANNEL"
	# The country is system-wide: OpenWrt hands hostapd the country of the *last* radio,
	# so a second radio left at the default "00" breaks the AP. Set it on every radio.
	for r in $radios; do
		uci set "wireless.$r.country=$WIFI_COUNTRY"
	done

	# Only our network: turn off every other Wi-Fi network on the box (e.g. a default
	# open or default-password one) so nothing else gives access to the camera LAN.
	for s in $(uci -q show wireless | sed -n 's/^wireless\.\([^.=]*\)=wifi-iface$/\1/p'); do
		[ "$s" = "pyxis_ap" ] || uci set "wireless.$s.disabled=1"
	done

	uci -q delete wireless.pyxis_ap || true
	uci set wireless.pyxis_ap='wifi-iface'
	uci set wireless.pyxis_ap.device="$radio"
	uci set wireless.pyxis_ap.network='lan'
	uci set wireless.pyxis_ap.mode='ap'
	uci set wireless.pyxis_ap.ssid="$WIFI_SSID"
	uci set wireless.pyxis_ap.encryption="$enc"
	uci set wireless.pyxis_ap.key="$WIFI_KEY"
	uci set wireless.pyxis_ap.disabled='0'
	echo "Radio $radio, encryption $enc, channel $WIFI_CHANNEL, country $WIFI_COUNTRY"
	WIFI_DONE=yes
}

# ---------------------------------------------------------------- mDNS

pkg_install() {
	if command -v apk >/dev/null; then
		apk update >/dev/null 2>&1 && apk add "$1" >/dev/null 2>&1
	elif command -v opkg >/dev/null; then
		opkg update >/dev/null 2>&1 && opkg install "$1" >/dev/null 2>&1
	else
		return 1
	fi
}

configure_mdns() {
	say "mDNS advert _pyxisrelay._tcp (port 8889)"
	if ! [ -x /etc/init.d/umdns ] && ! [ -x /etc/init.d/avahi-daemon ]; then
		echo "No mDNS responder installed; installing umdns (needs internet on the WAN port)."
		pkg_install umdns || true
	fi
	if [ -x /etc/init.d/umdns ]; then
		# The advert itself is registered by /etc/init.d/mediamtx (procd_add_mdns).
		/etc/init.d/umdns enable
		MDNS=umdns
	elif [ -x /etc/init.d/avahi-daemon ]; then
		mkdir -p /etc/avahi/services
		cp "$HERE/router/pyxisrelay.avahi.service" /etc/avahi/services/pyxisrelay.service
		/etc/init.d/avahi-daemon enable
		MDNS=avahi
	else
		warn "Couldn't install umdns. PYXIS Viewer won't find the relay by itself;"
		warn "type $ROUTER_IP into its \"Relay IP or hostname\" field instead."
		MDNS=none
	fi
	echo "Using: $MDNS"
}

# ---------------------------------------------------------------- settings page

install_webui() {
	say "Settings page: http://$ROUTER_IP/"
	web="$HERE/router/web"
	[ -d /usr/share/rpcd/ucode ] \
		|| { warn "rpcd's ucode plugin support (rpcd-mod-ucode) is missing; skipping the settings page."; return 0; }
	mkdir -p /www/pyxis
	cp "$web/index.html" "$web/qrcode.js" /www/pyxis/
	cp "$web/pyxis.uc" /usr/share/rpcd/ucode/pyxis.uc
	cp "$web/pyxis-acl.json" /usr/share/rpcd/acl.d/pyxis.json
	# Settings the page owns (quality presets). Keep existing ones on re-runs.
	[ -f /etc/config/pyxis ] || : > /etc/config/pyxis
	# The router's front page now opens the settings page; LuCI stays at /cgi-bin/luci/.
	if [ -f /www/index.html ] && ! grep -q '/pyxis/' /www/index.html; then
		cp /www/index.html /www/index.luci.html
	fi
	cp "$web/root-index.html" /www/index.html
	# Read-only camera address for viewer apps (camera control); see router/camera.cgi.
	mkdir -p /www/cgi-bin
	cp "$HERE/router/camera.cgi" /www/cgi-bin/pyxis-camera
	chmod 755 /www/cgi-bin/pyxis-camera
	for f in /www/pyxis/ /www/index.html /www/cgi-bin/pyxis-camera /usr/share/rpcd/ucode/pyxis.uc /usr/share/rpcd/acl.d/pyxis.json /etc/config/pyxis; do
		grep -qxF "$f" /etc/sysupgrade.conf 2>/dev/null || echo "$f" >> /etc/sysupgrade.conf
	done
	# Load the plugin. This also signs out any open LuCI or settings-page session.
	/etc/init.d/rpcd restart
	echo "Sign in with the router's admin (root) password."
}

# ---------------------------------------------------------------- HDMI output

install_hdmi() {
	say "HDMI output (hardware-decoded live stream on the HDMI port)"
	if [ ! -f "$HERE/router/pyxis-hdmi" ]; then
		warn "The pyxis-hdmi player isn't in this kit (build it with hdmi/build.sh); skipping HDMI output."
		return 0
	fi
	if [ ! -e /dev/mpp_service ] || [ ! -e /dev/dri/card0 ]; then
		warn "No Rockchip video decoder (/dev/mpp_service) or display (/dev/dri/card0); skipping HDMI output."
		return 0
	fi
	if [ -x /etc/init.d/pyxis-hdmi ]; then /etc/init.d/pyxis-hdmi stop >/dev/null 2>&1 || true; fi
	# Copy then rename: replacing a running binary in place fails ("Text file busy").
	cp "$HERE/router/pyxis-hdmi" /usr/bin/pyxis-hdmi.new
	chmod 755 /usr/bin/pyxis-hdmi.new
	mv -f /usr/bin/pyxis-hdmi.new /usr/bin/pyxis-hdmi
	cp "$HERE/router/pyxis-hdmi.init" /etc/init.d/pyxis-hdmi
	chmod 755 /etc/init.d/pyxis-hdmi
	# Licences of the libraries built into the player (Apache-2.0 / MIT).
	if [ -f "$HERE/router/pyxis-hdmi-LICENSES.txt" ]; then
		mkdir -p /usr/share/doc/pyxis-hdmi
		cp "$HERE/router/pyxis-hdmi-LICENSES.txt" /usr/share/doc/pyxis-hdmi/THIRD_PARTY_LICENSES.txt
	fi
	[ -f /etc/config/pyxis ] || : > /etc/config/pyxis
	# Defaults on the first install only; the settings page owns these afterwards.
	if ! uci -q get pyxis.hdmi >/dev/null; then
		uci set pyxis.hdmi='hdmi'
		uci set pyxis.hdmi.enabled='1'
		uci set pyxis.hdmi.match_rate='1'
		uci set pyxis.hdmi.low_latency='0'
		uci commit pyxis
	fi
	for f in /usr/bin/pyxis-hdmi /etc/init.d/pyxis-hdmi /usr/share/doc/pyxis-hdmi/; do
		grep -qxF "$f" /etc/sysupgrade.conf 2>/dev/null || echo "$f" >> /etc/sysupgrade.conf
	done
	/etc/init.d/pyxis-hdmi enable
	/etc/init.d/pyxis-hdmi stop >/dev/null 2>&1 || true  # quiet when it isn't running yet
	/etc/init.d/pyxis-hdmi start
	echo "HDMI output $( [ "$(uci -q get pyxis.hdmi.enabled)" = 0 ] && echo "installed (turned off in settings)" || echo "on")"
}

# ---------------------------------------------------------------- camera auto-start

install_autostart() {
	say "Camera auto-start (off until turned on in the settings page)"
	command -v curl >/dev/null || pkg_install curl || warn "curl is missing; auto-start can't reach the camera."
	if [ -x /etc/init.d/pyxis-autostart ]; then /etc/init.d/pyxis-autostart stop >/dev/null 2>&1 || true; fi
	cp "$HERE/router/autostart.sh" /usr/bin/pyxis-autostart.new
	chmod 755 /usr/bin/pyxis-autostart.new
	mv -f /usr/bin/pyxis-autostart.new /usr/bin/pyxis-autostart
	cp "$HERE/router/pyxis-autostart.init" /etc/init.d/pyxis-autostart
	chmod 755 /etc/init.d/pyxis-autostart
	mkdir -p /etc/pyxis
	chmod 700 /etc/pyxis
	[ -f /etc/config/pyxis ] || : > /etc/config/pyxis
	# Default on the first install only; the settings page owns it afterwards.
	if ! uci -q get pyxis.autostart >/dev/null; then
		uci set pyxis.autostart='autostart'
		uci set pyxis.autostart.enabled='0'
		uci commit pyxis
	fi
	for f in /usr/bin/pyxis-autostart /etc/init.d/pyxis-autostart /etc/pyxis/; do
		grep -qxF "$f" /etc/sysupgrade.conf 2>/dev/null || echo "$f" >> /etc/sysupgrade.conf
	done
	/etc/init.d/pyxis-autostart enable
	/etc/init.d/pyxis-autostart start
	echo "Auto-start $( [ "$(uci -q get pyxis.autostart.enabled)" = 1 ] && echo on || echo "installed (turn it on in the settings page)")"
}

# ---------------------------------------------------------------- run

WIFI_DONE=no
MDNS=none
install_mediamtx
install_webui
install_hdmi
install_autostart
configure_network
configure_wifi
configure_mdns

say "Saving settings"
uci commit system
uci commit network
uci commit dhcp
# /etc/config/wireless doesn't exist on a box without a radio, and committing it then fails.
[ "$WIFI_DONE" = yes ] && uci commit wireless

if /etc/init.d/mediamtx running >/dev/null 2>&1; then
	/etc/init.d/mediamtx restart
else
	/etc/init.d/mediamtx start
fi
[ "$MDNS" = "umdns" ] && /etc/init.d/umdns restart
[ "$MDNS" = "avahi" ] && /etc/init.d/avahi-daemon restart

# Flush everything to storage now: unplugging right after setup otherwise leaves the
# files written last (the relay's config and service script) empty after power-up.
sync

cat <<EOF

Done. Applying network changes in a few seconds; if you're connected over SSH, that
connection will drop when the address changes.

  Router / relay:   $ROUTER_IP   ($ROUTER_HOSTNAME.local)
  Ports:            camera on LAN = $lan_ports, upstream on WAN = $wan_dev
  Camera:           $CAMERA_IP $( [ -n "$CAMERA_MAC" ] && echo "(static lease for $CAMERA_MAC)" || echo "(no static lease)")
  Wi-Fi:            $( [ "$WIFI_DONE" = yes ] && echo "\"$WIFI_SSID\"" || echo "not set up (no radio found)")
  mDNS:             $MDNS

  Camera pushes to: rtmp://$ROUTER_IP:1935/live   (key: pyxis)
  Watch (browser):  http://$ROUTER_IP:8889/live/pyxis/
  Watch (HLS):      http://$ROUTER_IP:8888/live/pyxis/index.m3u8
  Watch (VLC/OBS):  rtsp://$ROUTER_IP:8554/live/pyxis
  Relay log:        logread -e mediamtx
  Settings page:    http://$ROUTER_IP/   (sign in with the admin password)
  Health check:     pyxis-relay-status   (run it once you've reconnected)
EOF

# Reload networking last, in its own session, so this script's output reaches an SSH
# client first and the reload survives the SSH session closing. Tested on OpenWrt 25.12:
# a plain `nohup ... &` job is killed when the session ends, and
# `start-stop-daemon -x /bin/sh` refuses to start while this script's own shell runs.
# A full `wifi` (not `wifi reload`) also retries a radio whose earlier start failed.
reload_cmd='sleep 3; logger -t pyxis-relay "applying network changes"; /etc/init.d/system reload; /etc/init.d/network reload; wifi; /etc/init.d/dnsmasq restart; logger -t pyxis-relay "network changes applied"'
if command -v setsid >/dev/null 2>&1; then
	setsid sh -c "$reload_cmd" </dev/null >/dev/null 2>&1 &
elif [ -x /sbin/start-stop-daemon ]; then
	rm -f /var/run/pyxis-relay-reload.pid
	/sbin/start-stop-daemon -S -b -m -p /var/run/pyxis-relay-reload.pid -x /bin/sh -- -c "$reload_cmd" \
		|| warn "Couldn't schedule the network reload: reboot the NanoPi to apply the changes."
else
	warn "Couldn't schedule the network reload: reboot the NanoPi to apply the changes."
fi
