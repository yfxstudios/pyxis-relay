#!/bin/sh
# /www/cgi-bin/pyxis-hdmi: the HDMI output's frame guide, for viewer apps (their menu sets it).
# No login, only reachable on the relay's own network, like camera control. Only these
# settings, and only these values, can be changed here; the settings page has the same ones.
#   GET                                   -> {"installed":true,"guide":"2.39","shade":60,"fill":false}
#   POST ?guide=2.39&shade=60&fill=1      (any of the three) -> the same, after the change
#     guide: off 2.39 2.00 1.85 16:9 4:3 1:1 4:5 9:16    shade: 0-100 (% dark outside)    fill: 0|1
# pyxis-hdmi reads them from /etc/config/pyxis within a second; it doesn't restart.
echo "Content-Type: application/json"
echo "Cache-Control: no-store"
echo ""

if [ "$REQUEST_METHOD" = POST ]; then
	# check every setting first: all or nothing
	sets=""
	IFS='&'
	for kv in $QUERY_STRING; do
		k=${kv%%=*}; v=$(printf '%s' "${kv#*=}" | sed 's/%3[Aa]/:/g')
		case "$k=$v" in
			guide=off|guide=2.39|guide=2.00|guide=1.85|guide=16:9|guide=4:3|guide=1:1|guide=4:5|guide=9:16) ;;
			shade=[0-9]|shade=[0-9][0-9]|shade=100) ;;
			fill=0|fill=1) ;;
			*) printf '{"ok":false,"error":"bad setting"}\n'; exit 0 ;;
		esac
		sets="$sets$k=$v&"
	done
	if [ -n "$sets" ]; then
		[ -f /etc/config/pyxis ] || : > /etc/config/pyxis
		uci -q get pyxis.hdmi >/dev/null || uci set pyxis.hdmi=hdmi
		for kv in $sets; do uci set "pyxis.hdmi.$kv"; done
		uci commit pyxis
	fi
	unset IFS
fi

guide=$(uci -q get pyxis.hdmi.guide); shade=$(uci -q get pyxis.hdmi.shade); fill=$(uci -q get pyxis.hdmi.fill)
installed=false; [ -x /usr/bin/pyxis-hdmi ] && installed=true
printf '{"ok":true,"installed":%s,"guide":"%s","shade":%s,"fill":%s}\n' "$installed" "${guide:-off}" "${shade:-60}" \
	"$([ "$fill" = 1 ] && echo true || echo false)"
