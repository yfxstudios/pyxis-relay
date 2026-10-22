#!/bin/sh
# pyxis-relay-status: health check for the NanoPi PYXIS router + relay.
# Installed as /usr/bin/pyxis-relay-status by setup.sh. Run:  ssh root@<router> pyxis-relay-status

ok()   { printf '  [ok]   %s\n' "$*"; }
bad()  { printf '  [!!]   %s\n' "$*"; }
info() { printf '  [--]   %s\n' "$*"; }

echo "PYXIS relay status ($(uci -q get system.@system[0].hostname), $(uci -q get network.lan.ipaddr))"

# Which jack is which: link state of the LAN and WAN ports.
lan_dev=$(uci -q get network.lan.device)
for s in $(uci -q show network | sed -n 's/^network\.\([^.=]*\)=device$/\1/p'); do
	[ "$(uci -q get "network.$s.name")" = "$lan_dev" ] && lan_ports=$(uci -q get "network.$s.ports")
done
for p in ${lan_ports:-} $(uci -q get network.wan.device); do
	role=LAN; [ "$p" = "$(uci -q get network.wan.device)" ] && role=WAN
	if [ "$(cat "/sys/class/net/$p/carrier" 2>/dev/null)" = "1" ]; then
		ok "$role port $p: cable connected"
	else
		info "$role port $p: no cable"
	fi
done

if pidof mediamtx >/dev/null; then ok "Relay (MediaMTX) running"; else bad "Relay not running: /etc/init.d/mediamtx start; logread -e mediamtx"; fi

code=$(uclient-fetch -q -O /dev/null "http://127.0.0.1:8888/live/pyxis/index.m3u8" 2>&1 && echo 200 || echo none)
if [ "$code" = "200" ]; then ok "Camera is streaming to the relay"; else info "Camera is not streaming right now"; fi

if command -v ubus >/dev/null && ubus call network.wireless status >/dev/null 2>&1; then
	status=$(ubus call network.wireless status)
	if echo "$status" | jsonfilter -e '@.*.up' 2>/dev/null | grep -q true; then
		ifname=$(echo "$status" | jsonfilter -e '@.*.interfaces[@.section="pyxis_ap"].ifname' 2>/dev/null | head -n 1)
		# The radio can be "up" while hostapd failed; ask hostapd itself.
		ap=$( [ -n "$ifname" ] && ubus call "hostapd.$ifname" get_status 2>/dev/null)
		ap_state=$(echo "$ap" | jsonfilter -e '@.status' 2>/dev/null)
		if [ "$ap_state" = "ENABLED" ]; then
			clients=$(iwinfo "$ifname" assoclist 2>/dev/null | grep -c '^[0-9A-F][0-9A-F]:')
			ok "Wi-Fi \"$(echo "$ap" | jsonfilter -e '@.ssid')\" broadcasting on channel $(echo "$ap" | jsonfilter -e '@.channel') ($(uci -q get wireless.pyxis_ap.encryption)), $clients client(s)"
		elif [ -n "$ap_state" ]; then
			info "Wi-Fi access point starting (hostapd: $ap_state)"
		else
			# hostapd has no status object until the AP is enabled; its log says why.
			last=$( [ -n "$ifname" ] && logread 2>/dev/null | grep "hostapd: $ifname: " | tail -n 1)
			case "$last" in
				*DFS-CAC-START*|*"->DFS"*) info "Wi-Fi access point waiting out the 60 s radar check on a DFS channel" ;;
				*ACS-STARTED*|*"->ACS"*)   info "Wi-Fi access point is choosing a channel (~15 s)" ;;
				*) bad "Wi-Fi access point isn't running: check logread | grep hostapd" ;;
			esac
		fi
	else
		bad "Wi-Fi access point is down: check logread | grep -iE 'hostapd|netifd'"
	fi
else
	info "No Wi-Fi configured"
fi

cam_ip=$(uci -q get dhcp.pyxis_camera.ip)
if [ -n "$cam_ip" ]; then
	if grep -q " $cam_ip " /tmp/dhcp.leases 2>/dev/null; then ok "Camera has its lease ($cam_ip)"; else info "Camera hasn't taken its lease ($cam_ip) yet"; fi
fi

if pidof umdns >/dev/null; then ok "mDNS (umdns) running: PYXIS Viewer can find the relay"
elif pidof avahi-daemon >/dev/null; then ok "mDNS (avahi) running: PYXIS Viewer can find the relay"
else info "No mDNS responder: type the router IP into PYXIS Viewer"; fi
