#!/bin/sh
# Renders the camera's streaming XML profile for a relay address.
#   ./make-profile.sh 192.168.50.1            -> nanopi-relay/PYXIS-LAN-192.168.50.1.xml
#   ./make-profile.sh 192.168.50.1 out.xml    -> out.xml
# Load the file on the camera: copy to a CFexpress card or USB-C drive, then
# Setup -> page 11 -> Import Stream Settings.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
TEMPLATE="$HERE/../profiles/PYXIS-LAN-Template.xml"

[ $# -ge 1 ] || { echo "usage: $0 <relay-ip> [output.xml]" >&2; exit 2; }
ip=$1
out=${2:-"$HERE/PYXIS-LAN-$ip.xml"}

echo "$ip" | grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}$' || { echo "Not an IPv4 address: $ip" >&2; exit 2; }
[ -f "$TEMPLATE" ] || { echo "Template not found: $TEMPLATE" >&2; exit 1; }

sed "s/__RELAY_IP__/$ip/g" "$TEMPLATE" > "$out"
if grep -q "__RELAY_IP__" "$out"; then
	echo "Placeholder left in $out" >&2
	exit 1
fi
if command -v xmllint >/dev/null 2>&1; then
	xmllint --noout "$out"
fi
echo "$out"
