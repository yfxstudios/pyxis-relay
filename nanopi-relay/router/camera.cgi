#!/bin/sh
# /www/cgi-bin/pyxis-camera: tells viewer apps where the camera is, so they can reach its
# control API (https://<camera>/control/api/v1) without the user typing an address.
# Read-only, no login, only reachable on the relay's own network. Answers:
#   {"cameras":["192.168.50.183"]}
# In order: the camera the relay's auto-start found (it searches every device, so a camera on a
# USB-C Ethernet adapter is included), the fixed address (if set), then DHCP clients with
# Blackmagic Design's MAC prefix (7C:2E:0D). The apps use the first that answers.
echo "Content-Type: application/json"
echo "Cache-Control: no-store"
echo ""
list=""
add() {
	case " $list " in *" $1 "*) ;; *) list="${list:+$list }$1" ;; esac
}
# the camera the relay's auto-start is using (it searches the whole network), if it's running
[ -r /tmp/pyxis-camera.found ] && add "$(cat /tmp/pyxis-camera.found)"
fixed=$(uci -q get dhcp.pyxis_camera.ip)
[ -n "$fixed" ] && add "$fixed"
if [ -r /tmp/dhcp.leases ]; then
	# shellcheck disable=SC2013  # one address per line, no spaces
	for ip in $(awk 'tolower($2) ~ /^7c:2e:0d:/ {print $3}' /tmp/dhcp.leases); do add "$ip"; done
fi
printf '{"cameras":['
sep=""
for ip in $list; do
	case $ip in *[!0-9.]*) continue ;; esac  # IPv4 addresses only
	printf '%s"%s"' "$sep" "$ip"
	sep=","
done
printf ']}\n'
