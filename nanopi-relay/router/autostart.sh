#!/bin/sh
# pyxis-autostart: keeps the camera (the PYXIS, or another Blackmagic camera) streaming to the relay.
# Installed as /usr/bin/pyxis-autostart and run by /etc/init.d/pyxis-autostart.
#
# The streaming XML can't make the camera stream at power-on, so the relay does it over
# the camera's REST API (Web media manager, https://<camera>/control/api/v1):
#   - whenever the camera is on the network and its stream is idle (just switched on, or the
#     stream stopped for any reason), and the relay's profile is the active platform, it starts it;
#   - if the camera's stream is in any other state (Streaming, Connecting, Interrupted...) but
#     nothing has reached the relay for STUCK seconds (e.g. after a Wi-Fi drop), it stops the
#     stream and starts it again;
#   - it never streams anywhere else: if another platform is selected on the camera it does
#     nothing and says so on the settings page.
#
# Settings (uci, also on the settings page):
#   pyxis.autostart.enabled=0|1
#   pyxis.autostart.host       camera address; empty = found: the first that answers the camera
#                              API among the last one found, the fixed address, Blackmagic
#                              devices, then any other DHCP client (see find_host)
#   pyxis.autostart.stream_lut=0|1  (default 1) turn on the display LUT for the camera's Stream
#                              output before starting, so the stream is Rec.709, not flat log
#                              (PYXIS Viewer's monitor LUTs go on top of that)
# Secure Login, when the camera uses one: /etc/pyxis/camera.curl (mode 600, curl config:
#   user = "name:password"). Written by the settings page; never in /etc/config.

PLATFORM="PYXIS LAN Relay (RTMP)"
LOGIN=/etc/pyxis/camera.curl
STATUS=/tmp/pyxis-autostart.json
FOUND=/tmp/pyxis-camera.found   # the camera in use, for the viewer apps (camera.cgi)
BODY=/tmp/pyxis-autostart.body
JSON=""
MTX=http://127.0.0.1:9997/v3
STUCK=30         # seconds a non-idle stream on the camera may go without reaching the relay

host=""          # camera address in use
found=""         # address found among the DHCP clients (tried first next time)
scheme=""        # https or http, once known
online=0         # camera answered last time
was_live=0       # the relay was receiving the stream last time
stuck_since=0    # when the camera started claiming a stream the relay isn't getting
last_try=0
state="starting" # for the settings page
message=""

log() { echo "$*"; }

json_esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }

write_status() {
	printf '{"time":%s,"camera":"%s","state":"%s","message":"%s"}\n' \
		"$(date +%s)" "$(json_esc "$host")" "$state" "$(json_esc "$message")" > "$STATUS.tmp" \
		&& mv "$STATUS.tmp" "$STATUS"
}

set_state() {  # state message
	if [ "$1" != "$state" ] || [ "$2" != "$message" ]; then
		state=$1; message=$2
		log "$state${message:+: $message}"
	fi
	write_status
}

# cam METHOD PATH [SCHEME] [nologin]: response body in $BODY, HTTP code in $code (000 = no answer).
# Set JSON='{...}' before calling to send a JSON request body (cleared afterwards).
# -k: the camera's certificate is self-signed. --anyauth: Basic or Digest, whichever it asks for.
# The login is only sent over HTTPS, and never while searching for the camera.
cam() {
	s=${3:-$scheme}
	url="$s://$host/control/api/v1$2"
	method=$1
	nologin=${4:-}
	set -- -s -k -m 4 --connect-timeout 2 -X "$method" -o "$BODY" -w '%{http_code}'
	if [ -s "$LOGIN" ] && [ "$s" = https ] && [ "$nologin" != nologin ]; then set -- "$@" --anyauth -K "$LOGIN"; fi
	if [ -n "${JSON:-}" ]; then set -- "$@" -H 'Content-Type: application/json' --data "$JSON"; fi
	code=$(curl "$@" "$url" 2>/dev/null)
	[ -n "$code" ] || code=000
	JSON=""
}

# Is the relay receiving the camera's stream?
relay_live() {
	curl -s -m 2 "$MTX/paths/list?itemsPerPage=100" 2>/dev/null \
		| jsonfilter -e "@.items[@.name='live/pyxis'].ready" 2>/dev/null | grep -q true
}

# Camera address: the setting if there is one. Otherwise the first device that answers the
# camera's REST API (with or without a login prompt), trying in order: the camera found last time,
# the fixed address (DHCP reservation), Blackmagic devices (MAC prefix 7C:2E:0D), then any other
# DHCP client: a camera on a USB-C Ethernet adapter has the adapter's MAC, not Blackmagic's.
find_host() {
	h=$(uci -q get pyxis.autostart.host)
	if [ -n "$h" ]; then host=$h; return 0; fi
	l=/tmp/dhcp.leases
	seen=" "
	for ip in $found $(uci -q get dhcp.pyxis_camera.ip) \
			$(awk 'tolower($2) ~ /^7c:2e:0d:/ {print $3}' $l 2>/dev/null) $(awk '{print $3}' $l 2>/dev/null); do
		case "$seen" in *" $ip "*) continue ;; esac
		seen="$seen$ip "
		host=$ip
		for s in https http; do
			cam GET /livestreams/0 "$s" nologin
			case $code in 200|401|403)
				[ "$found" = "$ip" ] || log "found a camera at $ip"
				found=$ip
				echo "$ip" > "$FOUND"
				return 0 ;;
			esac
		done
	done
	host=""
	found=""
	rm -f "$FOUND"
	return 1
}

# Reachable over the API? Sets scheme. With a login, HTTPS only.
probe() {
	for s in https http; do
		[ "$s" = http ] && [ -s "$LOGIN" ] && break
		cam GET /livestreams/0 "$s"
		case $code in 200|401|403) scheme=$s; return 0 ;; esac
	done
	[ "$host" = "$found" ] && found=""
	return 1
}

tick() {
	if ! find_host; then
		[ "$online" = 1 ] && log "the camera went offline"
		online=0
		was_live=0; stuck_since=0
		set_state waiting "No camera answering on the relay's network (off, starting up, or Web media manager is off)"
		return
	fi
	if ! probe; then
		[ "$online" = 1 ] && log "camera at $host went offline"
		online=0
		was_live=0; stuck_since=0
		set_state waiting "Camera at $host isn't answering (off, starting up, or Web media manager is off)"
		return
	fi
	if [ "$online" = 0 ]; then
		log "camera at $host is online ($scheme)"
		online=1
	fi
	case $code in
		401|403)
			if [ -s "$LOGIN" ]; then
				set_state error "The camera rejected the login. Check the Secure Login username and password."
			else
				set_state error "The camera needs its Secure Login (set in Blackmagic Camera Setup > Network Access)."
			fi
			return ;;
	esac

	cstatus=$(jsonfilter -i "$BODY" -e '@.status' 2>/dev/null)
	now=$(date +%s)
	if relay_live; then
		was_live=1; stuck_since=0
		set_state streaming "Camera is streaming to the relay"
		return
	fi
	if [ -n "$cstatus" ] && [ "$cstatus" != "Idle" ]; then
		[ "$stuck_since" = 0 ] && stuck_since=$now
		if [ $((now - stuck_since)) -lt "$STUCK" ]; then
			set_state starting "Camera stream is $cstatus, waiting for it to reach the relay"
			return
		fi
		log "camera says $cstatus but nothing has reached the relay for ${STUCK}s: restarting its stream"
		cam PUT /livestreams/0/stop
		stuck_since=0; was_live=0; last_try=0
		set_state starting "Restarting the camera's stream (it wasn't reaching the relay)"
		return
	fi
	stuck_since=0
	if [ "$was_live" = 1 ]; then
		log "the stream stopped: starting it again"
		was_live=0
	fi

	cam GET /livestreams/0/activePlatform
	platform=$(jsonfilter -i "$BODY" -e '@.platform' 2>/dev/null)
	if [ "$code" = 200 ] && [ "$platform" != "$PLATFORM" ]; then
		set_state error "The camera's streaming platform is \"${platform:-none}\", not \"$PLATFORM\". Load and select the relay's profile on the camera; auto-start won't stream anywhere else."
		return
	fi

	[ $((now - last_try)) -ge 10 ] || return
	last_try=$now
	if [ "$(uci -q get pyxis.autostart.stream_lut)" != "0" ]; then
		JSON='{"enabled":true}'
		cam PUT /monitoring/Stream/displayLUT
		case $code in
			200|204) log "display LUT on for the stream" ;;
			404) ;;  # no separate Stream output on this camera
			*) log "couldn't turn on the stream's display LUT (HTTP $code); starting anyway" ;;
		esac
	fi
	cam PUT /livestreams/0/start
	case $code in
		200|204) log "asked the camera to start streaming"; set_state starting "Asked the camera to start streaming" ;;
		*) set_state waiting "The camera didn't start streaming yet (HTTP $code); retrying" ;;
	esac
}

trap 'rm -f "$STATUS" "$BODY" "$FOUND"; exit 0' INT TERM
log "pyxis-autostart: running"
while :; do
	tick
	sleep 5
done
