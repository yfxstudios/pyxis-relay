#!/bin/sh
# Makes relay units from the factory image (run on the Mac; needs Docker). Each unit gets:
#   - its own Wi-Fi name (<SSID_PREFIX>-<unit code>) and Wi-Fi password,
#   - its own admin password (the settings page sign-in; only its hash goes into the image),
#   - a flashable image:   dist/units/<code>/relay-<code>.img.gz
#   - a printable label:   dist/units/<code>/label.html  (QR to join + open the app, Wi-Fi QR,
#                                                         passwords)
#   - a record for you:    dist/units/<code>/unit.txt    (the passwords: keep it safe)
#
# usage: ./provision.sh [--count N] [--country US] [--ssh] [image.img.gz]
#   --country  Wi-Fi regulatory country, two letters (default US). Must match where it's used.
#   --ssh      leave SSH on (for development units; off by default)
#   image      defaults to the newest dist/relay-factory-*.img.gz
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
COUNT=1
COUNTRY=US
SSH=0
IMAGE=""
while [ $# -gt 0 ]; do
	case $1 in
		--count) COUNT=$2; shift 2 ;;
		--country) COUNTRY=$2; shift 2 ;;
		--ssh) SSH=1; shift ;;
		-*) echo "unknown option $1" >&2; exit 1 ;;
		*) IMAGE=$1; shift ;;
	esac
done
case "$COUNTRY" in [A-Z][A-Z]) ;; *) echo "--country must be two capital letters, like US" >&2; exit 1 ;; esac
[ -n "$IMAGE" ] || IMAGE=$(ls -t "$HERE"/dist/relay-factory-*.img.gz 2>/dev/null | head -1)
[ -f "$IMAGE" ] || { echo "No factory image: run ./build-image.sh first." >&2; exit 1; }
command -v docker >/dev/null && docker info >/dev/null 2>&1 || { echo "Docker isn't running." >&2; exit 1; }

mkdir -p "$HERE/dist/units"
docker build -q -t relay-factory-tools "$HERE" >/dev/null
docker run --rm --privileged \
	-v "$IMAGE:/in/factory.img.gz:ro" -v "$HERE/brand.env:/in/brand.env:ro" -v "$HERE/dist/units:/out" \
	-v "$HERE/label.py:/in/label.py:ro" \
	-e COUNT="$COUNT" -e COUNTRY="$COUNTRY" -e SSH="$SSH" relay-factory-tools sh -eu -c '
		. /in/brand.env
		gunzip -c /in/factory.img.gz > /tmp/factory.img
		set -- $(sfdisk -J /tmp/factory.img | python3 -c "import json,sys; p=[x for x in json.load(sys.stdin)[\"partitiontable\"][\"partitions\"] if x.get(\"name\")==\"rootfs\"][0]; print(p[\"start\"], p[\"size\"])")
		start=$1; size=$2
		i=0
		while [ $i -lt "$COUNT" ]; do
			i=$((i + 1))
			# unit code and passwords: no look-alike characters (0/o, 1/l/i)
			code=$(python3 -c "import secrets; print(\"\".join(secrets.choice(\"ABCDEFGHJKMNPQRSTUVWXYZ23456789\") for _ in range(4)))")
			[ -e "/out/$code" ] && continue
			pw() { python3 -c "import secrets; a=\"abcdefghjkmnpqrstuvwxyz23456789\"; print(\"-\".join(\"\".join(secrets.choice(a) for _ in range(4)) for _ in range(3)))"; }
			wifi_key=$(pw); admin=$(pw)
			hash=$(openssl passwd -6 "$admin")
			ssid="$SSID_PREFIX-$code"
			mkdir -p "/out/$code"
			chmod 700 "/out/$code"

			cp /tmp/factory.img /tmp/unit.img
			dd if=/tmp/unit.img of=/tmp/rootfs.ext4 bs=512 skip=$start count=$size status=none
			mkdir -p /mnt/root
			mount -o loop /tmp/rootfs.ext4 /mnt/root
			umask 077
			cat > /mnt/root/etc/relay/provision.env <<ENV
UNIT_ID="$code"
WIFI_SSID="$ssid"
WIFI_KEY="$wifi_key"
WIFI_COUNTRY="$COUNTRY"
ADMIN_HASH='"'"'$hash'"'"'
RELAY_HOSTNAME="$RELAY_HOSTNAME"
SSH="$SSH"
ENV
			chown 0:0 /mnt/root/etc/relay/provision.env
			chmod 600 /mnt/root/etc/relay/provision.env
			umount /mnt/root
			umask 022
			dd if=/tmp/rootfs.ext4 of=/tmp/unit.img bs=512 seek=$start conv=notrunc status=none
			gzip -6 -c /tmp/unit.img > "/out/$code/relay-$code.img.gz"

			cat > "/out/$code/unit.txt" <<TXT
Unit $code
Wi-Fi network:   $ssid
Wi-Fi password:  $wifi_key
Admin password:  $admin   (settings page: http://$RELAY_HOSTNAME.local or http://192.168.50.1)
Wi-Fi country:   $COUNTRY
SSH:             $( [ "$SSH" = 1 ] && echo on || echo off )
Image:           relay-$code.img.gz
TXT
			chmod 600 "/out/$code/unit.txt"
			python3 /in/label.py "$code" "$ssid" "$wifi_key" "$admin" > "/out/$code/label.html"
			echo "Unit $code: Wi-Fi \"$ssid\""
		done
	'
echo "Units are in $HERE/dist/units/. Flash relay-<code>.img.gz to a microSD card and print label.html."
echo "unit.txt holds the passwords in plain text: store it safely or delete it after printing the label."
