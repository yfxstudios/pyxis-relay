#!/usr/bin/env ucode
// rpcd plugin behind the PYXIS relay settings page (/www/pyxis/).
// Installed as /usr/share/rpcd/ucode/pyxis.uc; access is granted by
// /usr/share/rpcd/acl.d/pyxis.json to sessions that logged in as root.
// The page calls it over uhttpd's /ubus JSON-RPC endpoint, like LuCI does.

'use strict';

import { readfile, writefile, popen, stat } from 'fs';
import { cursor } from 'uci';
import * as ubus from 'ubus';

const API = 'http://127.0.0.1:9997/v3';      // MediaMTX API, localhost only
const STREAM_PATH = 'live/pyxis';             // fixed: PYXIS Viewer expects it
const STREAM_KEY = 'pyxis';

const PRESETS = ['high', 'medium', 'low'];
const PRESET_NAMES = { high: 'LAN High', medium: 'LAN Medium', low: 'LAN Low (Wi-Fi)' };
const MODES = ['p1080_30', 'p1080_60', 'p2160_30', 'p2160_60'];
const MODE_ATTRS = {
	p1080_30: ['1080p', '30'], p1080_60: ['1080p', '60'],
	p2160_30: ['2160p', '30'], p2160_60: ['2160p', '60'],
};
// Mbps. Same numbers as profiles/PYXIS-LAN-Template.xml.
const DEFAULT_RATES = {
	high:   { p1080_30: 12,  p1080_60: 18, p2160_30: 30, p2160_60: 40 },
	medium: { p1080_30: 6,   p1080_60: 9,  p2160_30: 15, p2160_60: 20 },
	low:    { p1080_30: 3.5, p1080_60: 5,  p2160_30: 8,  p2160_60: 10 },
};
const CHANNELS = {
	'5g': ['auto', '36', '40', '44', '48', '149', '153', '157', '161'],
	'2g': ['auto', '1', '6', '11'],
};

// ------------------------------------------------------------------ helpers

function sh(cmd) {
	let p = popen(cmd, 'r');
	if (!p) return '';
	let out = p.read('all');
	p.close();
	return out ?? '';
}

function readnum(path) {
	let s = readfile(path);
	return s == null ? null : +trim(s);
}

function api(path) {
	let out = sh(`curl -s -m 2 '${API}${path}'`);
	try { return json(out); } catch (e) { return null; }
}

// Run a fixed command a moment later, detached, so the JSON-RPC reply goes out first.
// Only ever called with constant strings (never user input).
function later(cmd) {
	system(`setsid sh -c 'sleep 2; ${cmd}' </dev/null >/dev/null 2>&1 &`);
}

function fail(msg) { return { ok: false, error: msg }; }

function lan_info(c) {
	let ip = c.get('network', 'lan', 'ipaddr') ?? '';
	if (type(ip) == 'array') ip = ip[0];
	ip = split(ip, '/')[0];
	let dev = c.get('network', 'lan', 'device');
	let ports = [];
	c.foreach('network', 'device', (s) => {
		if (s.name == dev && s.type == 'bridge' && s.ports)
			ports = type(s.ports) == 'array' ? s.ports : split(s.ports, ' ');
	});
	return {
		ip: ip,
		prefix: join('.', slice(split(ip, '.'), 0, 3)),
		dev: dev,
		ports: ports,
		dhcp_start: +(c.get('dhcp', 'lan', 'start') ?? 100),
		dhcp_limit: +(c.get('dhcp', 'lan', 'limit') ?? 150),
		wan_dev: c.get('network', 'wan', 'device') ?? null,
	};
}

function hostname(c) {
	let h = null;
	c.foreach('system', 'system', (s) => { if (h == null) h = s.hostname; });
	return h;
}

function valid_ip(ip) {
	let m = match(ip, /^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$/);
	if (!m) return false;
	for (let i = 1; i <= 4; i++)
		if (+m[i] > 255) return false;
	return true;
}

function rates_from(c) {
	let r = {};
	for (let p in PRESETS) {
		r[p] = {};
		for (let m in MODES) {
			let v = c.get('pyxis', 'quality', `${p}_${m}`);
			r[p][m] = v != null ? +v : DEFAULT_RATES[p][m];
		}
	}
	return r;
}

function quality_default(c) {
	let d = c.get('pyxis', 'quality', 'default');
	return (d in PRESET_NAMES) ? d : 'high';
}

function wifi_iface(conn) {
	let st = conn.call('network.wireless', 'status', {}) ?? {};
	for (let radio in st)
		for (let i in (st[radio].interfaces ?? []))
			if (i.section == 'pyxis_ap')
				return { radio: radio, up: !!st[radio].up, ifname: i.ifname };
	return null;
}

// HDMI output: settings, whether the player runs, and its live status file.
function hdmi_info(c, conn) {
	let installed = !!stat('/usr/bin/pyxis-hdmi');
	let info = {
		installed: installed,
		enabled: c.get('pyxis', 'hdmi', 'enabled') != '0',
		match_rate: c.get('pyxis', 'hdmi', 'match_rate') != '0',
		low_latency: c.get('pyxis', 'hdmi', 'low_latency') == '1',
		running: false,
	};
	if (conn) {
		let svc = conn.call('service', 'list', { name: 'pyxis-hdmi' }) ?? {};
		for (let n, inst in (svc['pyxis-hdmi']?.instances ?? {}))
			if (inst.running) info.running = true;
	}
	let st = null;
	try { st = json(readfile('/tmp/pyxis-hdmi.json') ?? ''); } catch (e) { st = null; }
	if (info.running && st && time() - (st.time ?? 0) < 5) info.live = st;  // ignore a stale file
	return info;
}

// Camera auto-start: settings, the saved Secure Login's username (never the password) and
// the service's live status file.
const CAMERA_LOGIN = '/etc/pyxis/camera.curl';

function login_user() {
	let m = match(readfile(CAMERA_LOGIN) ?? '', /user = "((\\.|[^"\\])*)"/);
	if (!m) return null;
	let up = replace(m[1], /\\(.)/g, (all, ch) => ch);
	let i = index(up, ':');
	return i < 0 ? up : substr(up, 0, i);
}

function autostart_info(c, conn) {
	let info = {
		enabled: c.get('pyxis', 'autostart', 'enabled') == '1',
		host: c.get('pyxis', 'autostart', 'host') ?? '',
		stream_lut: c.get('pyxis', 'autostart', 'stream_lut') != '0',
		user: login_user(),
		running: false,
	};
	if (conn) {
		let svc = conn.call('service', 'list', { name: 'pyxis-autostart' }) ?? {};
		for (let n, inst in (svc['pyxis-autostart']?.instances ?? {}))
			if (inst.running) info.running = true;
	}
	let st = null;
	try { st = json(readfile('/tmp/pyxis-autostart.json') ?? ''); } catch (e) { st = null; }
	if (info.running && st && time() - (st.time ?? 0) < 20) info.live = st;
	return info;
}

function camera_profile_xml(ip, def, rates) {
	let x = '<?xml version="1.0" encoding="UTF-8"?>\n';
	x += `<!-- Blackmagic PYXIS 12K LAN streaming profile, generated by the PYXIS relay at ${ip}.\n`;
	x += '     Load it on the camera: Setup -> page 11 -> Import Stream Settings. -->\n';
	x += '<streaming>\n  <service>\n    <name>PYXIS LAN Relay (RTMP)</name>\n';
	x += `    <key>${STREAM_KEY}</key>\n    <servers>\n      <server group="Primary">\n`;
	x += `        <name>LAN Relay</name>\n        <url>rtmp://${ip}:1935/live</url>\n`;
	x += '      </server>\n    </servers>\n';
	x += `    <profiles default="${PRESET_NAMES[def]}">\n`;
	for (let p in PRESETS) {
		x += `      <profile>\n        <name>${PRESET_NAMES[p]}</name>\n`;
		for (let m in MODES) {
			let bps = int(rates[p][m] * 1000000 + 0.5);
			x += `        <config resolution="${MODE_ATTRS[m][0]}" fps="${MODE_ATTRS[m][1]}" codec="H264">`
			   + `<bitrate>${bps}</bitrate><audio-bitrate>128000</audio-bitrate></config>\n`;
		}
		x += '      </profile>\n';
	}
	x += '    </profiles>\n  </service>\n</streaming>\n';
	return x;
}

// ------------------------------------------------------------------ methods

const methods = {
	status: {
		call: function() {
			let c = cursor();
			let conn = ubus.connect();
			let lan = lan_info(c);

			// Relay process
			let svc = conn.call('service', 'list', { name: 'mediamtx' }) ?? {};
			let running = false;
			for (let n, inst in (svc.mediamtx?.instances ?? {}))
				if (inst.running) running = true;

			// Stream, from the MediaMTX API (paths/list never 404s, unlike paths/get)
			let stream = { live: false };
			let paths = running ? api('/paths/list?itemsPerPage=100') : null;
			for (let p in (paths?.items ?? [])) {
				if (p.name != STREAM_PATH) continue;
				let video = null, audio = null;
				for (let t in (p.tracks2 ?? [])) {
					let props = t.codecProps ?? {};
					if (props.width && !video)
						video = { codec: t.codec, width: props.width, height: props.height };
					else if (props.sampleRate && !audio)
						audio = { codec: t.codec, sample_rate: props.sampleRate, channels: props.channelCount };
				}
				stream = {
					live: !!p.ready,
					since: p.readyTime,
					video: video,
					audio: audio,
					bytes_in: p.inboundBytes ?? p.bytesReceived ?? 0,
					frames_in_error: p.inboundFramesInError ?? 0,
					readers: length(p.readers ?? []),
				};
				if (p.source?.type == 'rtmpConn') {
					let conns = api('/rtmpconns/list?itemsPerPage=100');
					for (let rc in (conns?.items ?? []))
						if (rc.id == p.source.id) {
							stream.source_addr = split(rc.remoteAddr, ':')[0];
							stream.source_agent = rc.userAgent;
						}
				}
			}

			// Wi-Fi access point
			let wifi = { configured: c.get('wireless', 'pyxis_ap') != null };
			let w = wifi_iface(conn);
			if (w) {
				wifi.up = w.up && !!w.ifname;
				wifi.ifname = w.ifname;
				wifi.ssid = c.get('wireless', 'pyxis_ap', 'ssid');
				// The iwinfo *CLI*, not ubus: the ubus "iwinfo" object lives inside rpcd
				// itself, and calling it from this rpcd plugin deadlocks until timeout.
				if (w.ifname && match(w.ifname, /^[A-Za-z0-9._-]+$/)) {
					let n = 0;
					for (let line in split(sh(`iwinfo ${w.ifname} assoclist 2>/dev/null`), '\n'))
						if (match(line, /^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\s/)) n++;
					wifi.clients = n;
				}
				wifi.band = c.get('wireless', w.radio, 'band');
				// This driver reports the live channel as "unknown"; show the configured one.
				wifi.channel = c.get('wireless', w.radio, 'channel');
			}

			// Ports
			let carrier = (dev) => dev ? readnum(`/sys/class/net/${dev}/carrier`) == 1 : false;
			let lan_link = false;
			for (let d in lan.ports) if (carrier(d)) lan_link = true;
			let wan_ip = null;
			let wan = conn.call('network.interface.wan', 'status', {});
			if (wan?.['ipv4-address']?.[0]) wan_ip = wan['ipv4-address'][0].address;

			// DHCP leases (devices on the camera network)
			let leases = [];
			for (let line in split(readfile('/tmp/dhcp.leases') ?? '', '\n')) {
				let f = split(trim(line), ' ');
				if (length(f) >= 4)
					push(leases, { expires: +f[0], mac: uc(f[1]), ip: f[2], name: f[3] == '*' ? '' : f[3] });
			}

			// System
			let mem = {};
			for (let line in split(readfile('/proc/meminfo') ?? '', '\n')) {
				let m = match(line, /^(MemTotal|MemAvailable):\s+([0-9]+)/);
				if (m) mem[m[1]] = +m[2];
			}
			let temp = readnum('/sys/class/thermal/thermal_zone0/temp');
			let hdmi = hdmi_info(c, conn);
			let autostart = autostart_info(c, conn);

			conn.disconnect();
			return {
				ok: true,
				relay: { running: running },
				stream: stream,
				wifi: wifi,
				ports: {
					lan: { devs: lan.ports, link: lan_link },
					wan: { dev: lan.wan_dev, link: carrier(lan.wan_dev), ip: wan_ip },
				},
				camera: {
					mac: c.get('dhcp', 'pyxis_camera', 'mac'),
					ip: c.get('dhcp', 'pyxis_camera', 'ip'),
				},
				leases: leases,
				hdmi: hdmi,
				autostart: autostart,
				system: {
					hostname: hostname(c),
					ip: lan.ip,
					uptime: +split(readfile('/proc/uptime') ?? '0', ' ')[0],
					load: slice(split(trim(readfile('/proc/loadavg') ?? ''), ' '), 0, 3),
					temp_c: temp != null ? temp / 1000 : null,
					mem_total_kb: mem.MemTotal,
					mem_avail_kb: mem.MemAvailable,
					time: time(),
				},
			};
		}
	},

	get_config: {
		call: function() {
			let c = cursor();
			let lan = lan_info(c);
			let radio = c.get('wireless', 'pyxis_ap', 'device');
			return {
				ok: true,
				hostname: hostname(c),
				lan: { ip: lan.ip, dhcp_start: lan.dhcp_start, dhcp_limit: lan.dhcp_limit },
				wifi: c.get('wireless', 'pyxis_ap') == null ? null : {
					ssid: c.get('wireless', 'pyxis_ap', 'ssid'),
					key: c.get('wireless', 'pyxis_ap', 'key'),
					encryption: c.get('wireless', 'pyxis_ap', 'encryption'),
					band: radio ? c.get('wireless', radio, 'band') : null,
					channel: radio ? c.get('wireless', radio, 'channel') : null,
					country: radio ? c.get('wireless', radio, 'country') : null,
					channels: CHANNELS,
				},
				camera: {
					mac: c.get('dhcp', 'pyxis_camera', 'mac'),
					ip: c.get('dhcp', 'pyxis_camera', 'ip') ?? `${lan.prefix}.10`,
				},
				quality: { default: quality_default(c), rates: rates_from(c), names: PRESET_NAMES },
				hdmi: hdmi_info(c, null),
				autostart: autostart_info(c, null),
				stream: {
					rtmp_url: `rtmp://${lan.ip}:1935/live`,
					key: STREAM_KEY,
					path: STREAM_PATH,
					webrtc: `http://${lan.ip}:8889/${STREAM_PATH}/`,
					hls: `http://${lan.ip}:8888/${STREAM_PATH}/index.m3u8`,
					rtsp: `rtsp://${lan.ip}:8554/${STREAM_PATH}`,
				},
			};
		}
	},

	set_wifi: {
		args: { ssid: 'ssid', key: 'key', band: 'band', channel: 'channel' },
		call: function(req) {
			let a = req.args ?? {};
			let c = cursor();
			if (c.get('wireless', 'pyxis_ap') == null)
				return fail('No Wi-Fi access point is set up on this relay.');
			let radio = c.get('wireless', 'pyxis_ap', 'device');
			let ssid = a.ssid ?? '', key = a.key ?? '', band = a.band ?? '', channel = a.channel ?? '';

			if (length(ssid) < 1 || length(ssid) > 32)
				return fail('The network name must be 1-32 characters.');
			if (key != '' && !match(key, /^[\x20-\x7e]{8,63}$/))
				return fail('The Wi-Fi password must be 8-63 characters (letters, digits, symbols, spaces).');
			if (!(band in CHANNELS))
				return fail('Band must be 2.4 GHz or 5 GHz.');
			if (index(CHANNELS[band], channel) < 0)
				return fail('That channel is not allowed on this band.');

			let old_band = c.get('wireless', radio, 'band');
			c.set('wireless', 'pyxis_ap', 'ssid', ssid);
			if (key != '') c.set('wireless', 'pyxis_ap', 'key', key);
			if (band != old_band) {
				c.set('wireless', radio, 'band', band);
				c.set('wireless', radio, 'htmode', band == '5g' ? 'VHT80' : 'HT20');
			}
			c.set('wireless', radio, 'channel', channel);
			c.commit('wireless');
			later('wifi');
			return { ok: true, message: 'Saved. The Wi-Fi network restarts in a few seconds.' };
		}
	},

	set_camera: {
		args: { mac: 'mac', ip: 'ip' },
		call: function(req) {
			let a = req.args ?? {};
			let c = cursor();
			let lan = lan_info(c);
			let mac = uc(trim(a.mac ?? '')), ip = trim(a.ip ?? '');
			if (mac == '') {
				c.delete('dhcp', 'pyxis_camera');
				c.commit('dhcp');
				later('/etc/init.d/dnsmasq reload');
				return { ok: true, message: 'Removed the camera\'s fixed address.' };
			}
			if (!match(mac, /^([0-9A-F]{2}:){5}[0-9A-F]{2}$/))
				return fail('The camera\'s MAC address must look like AA:BB:CC:DD:EE:FF.');
			if (!valid_ip(ip) || join('.', slice(split(ip, '.'), 0, 3)) != lan.prefix)
				return fail(`The camera's address must be on this network (${lan.prefix}.x).`);
			let host = +split(ip, '.')[3];
			let pool_end = lan.dhcp_start + lan.dhcp_limit - 1;
			if (host < 2 || host > 254 || ip == lan.ip)
				return fail('Pick an address from .2 to .254, other than the relay\'s own.');
			if (host >= lan.dhcp_start && host <= pool_end)
				return fail(`Pick an address outside the automatic range (.${lan.dhcp_start}-.${pool_end}).`);
			c.set('dhcp', 'pyxis_camera', 'host');
			c.set('dhcp', 'pyxis_camera', 'name', 'pyxis-camera');
			c.set('dhcp', 'pyxis_camera', 'mac', mac);
			c.set('dhcp', 'pyxis_camera', 'ip', ip);
			c.commit('dhcp');
			later('/etc/init.d/dnsmasq reload');
			return { ok: true, message: `Saved. The camera gets ${ip} the next time it connects (unplug and replug its cable).` };
		}
	},

	set_quality: {
		args: { default: 'high', rates: {} },
		call: function(req) {
			let a = req.args ?? {};
			if (!(a.default in PRESET_NAMES))
				return fail('Unknown default quality.');
			let rates = a.rates ?? {};
			for (let p in PRESETS)
				for (let m in MODES) {
					let v = rates?.[p]?.[m];
					if (type(v) == 'string') v = +v;
					if (!(type(v) in ['int', 'double']) || v != v || v < 0.5 || v > 100)
						return fail(`${PRESET_NAMES[p]} ${MODE_ATTRS[m][0]}${MODE_ATTRS[m][1]}: enter 0.5-100 Mbps.`);
				}
			if (!stat('/etc/config/pyxis')) writefile('/etc/config/pyxis', '');
			let c = cursor();
			c.set('pyxis', 'quality', 'quality');
			c.set('pyxis', 'quality', 'default', a.default);
			for (let p in PRESETS)
				for (let m in MODES)
					c.set('pyxis', 'quality', `${p}_${m}`, sprintf('%g', +rates[p][m]));
			c.commit('pyxis');
			return { ok: true, message: 'Saved. Download the camera profile again and load it on the camera.' };
		}
	},

	set_autostart: {
		args: { enabled: true, host: 'host', user: 'user', password: 'password', clear_login: true, stream_lut: true },
		call: function(req) {
			let a = req.args ?? {};
			if (type(a.enabled) != 'bool') return fail('Send enabled as true or false.');
			if (a.stream_lut != null && type(a.stream_lut) != 'bool') return fail('Send stream_lut as true or false.');
			let host = trim(a.host ?? '');
			if (host != '' && !match(host, /^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$/))
				return fail('The camera address must be an IP address or host name (or empty to find it).');
			let user = a.user ?? '', pw = a.password ?? '';
			if (index(user + pw, '\n') >= 0 || index(user + pw, '\r') >= 0)
				return fail('The login can\'t contain line breaks.');
			if (index(user, ':') >= 0) return fail('The username can\'t contain a colon.');
			if (pw != '' && user == '') return fail('Enter the Secure Login username with the password.');
			if (!stat('/usr/bin/pyxis-autostart'))
				return fail('Auto-start isn\'t installed on this relay. Run setup again.');

			if (a.clear_login) {
				system(`rm -f '${CAMERA_LOGIN}'`);
			} else if (pw != '') {
				// curl config file, readable by root only; created empty first so it's never
				// briefly world-readable.
				let esc = (v) => replace(v, /["\\]/g, (ch) => '\\' + ch);
				system(`mkdir -p /etc/pyxis && umask 077 && : > '${CAMERA_LOGIN}' && chmod 600 '${CAMERA_LOGIN}'`);
				if (!writefile(CAMERA_LOGIN, `user = "${esc(user + ':' + pw)}"\n`))
					return fail('Couldn\'t save the login.');
			}
			if (!stat('/etc/config/pyxis')) writefile('/etc/config/pyxis', '');
			let c = cursor();
			c.set('pyxis', 'autostart', 'autostart');
			c.set('pyxis', 'autostart', 'enabled', a.enabled ? '1' : '0');
			c.set('pyxis', 'autostart', 'host', host);
			if (a.stream_lut != null) c.set('pyxis', 'autostart', 'stream_lut', a.stream_lut ? '1' : '0');
			c.commit('pyxis');
			system('/etc/init.d/pyxis-autostart restart >/dev/null 2>&1');
			return { ok: true, message: a.enabled
				? 'Saved. The relay starts the camera\'s stream each time the camera comes online.'
				: 'Saved. Auto-start is off.' };
		}
	},

	set_hdmi: {
		args: { enabled: true, match_rate: true, low_latency: true },
		call: function(req) {
			let a = req.args ?? {};
			if (type(a.enabled) != 'bool' || type(a.match_rate) != 'bool')
				return fail('Send enabled and match_rate as true or false.');
			if (a.low_latency != null && type(a.low_latency) != 'bool')
				return fail('Send low_latency as true or false.');
			if (!stat('/usr/bin/pyxis-hdmi'))
				return fail('The HDMI player isn\'t installed on this relay.');
			if (!stat('/etc/config/pyxis')) writefile('/etc/config/pyxis', '');
			let c = cursor();
			c.set('pyxis', 'hdmi', 'hdmi');
			c.set('pyxis', 'hdmi', 'enabled', a.enabled ? '1' : '0');
			c.set('pyxis', 'hdmi', 'match_rate', a.match_rate ? '1' : '0');
			if (a.low_latency != null) c.set('pyxis', 'hdmi', 'low_latency', a.low_latency ? '1' : '0');
			c.commit('pyxis');
			// The service reads these when it starts; with enabled=0 it starts nothing.
			system('/etc/init.d/pyxis-hdmi restart >/dev/null 2>&1');
			return { ok: true, message: a.enabled ? 'HDMI output is on.' : 'HDMI output is off.' };
		}
	},

	profile: {
		call: function() {
			let c = cursor();
			let ip = lan_info(c).ip;
			return {
				ok: true,
				filename: `PYXIS-LAN-${ip}.xml`,
				xml: camera_profile_xml(ip, quality_default(c), rates_from(c)),
			};
		}
	},

	log: {
		call: function() {
			return { ok: true, log: sh('logread -e mediamtx 2>/dev/null | tail -n 200') };
		}
	},

	restart_relay: {
		call: function() {
			let rc = system('/etc/init.d/mediamtx restart >/dev/null 2>&1');
			return rc == 0 ? { ok: true, message: 'Relay restarted.' } : fail('The relay could not be restarted.');
		}
	},

	reboot: {
		call: function() {
			later('reboot');
			return { ok: true, message: 'Rebooting. The relay is back in about a minute.' };
		}
	},

	set_password: {
		args: { password: 'password' },
		call: function(req) {
			let pw = req.args?.password ?? '';
			if (!match(pw, /^[\x20-\x7e]{8,128}$/))
				return fail('The admin password must be 8-128 characters (letters, digits, symbols, spaces).');
			if (pw == 'password')
				return fail('Choose something other than the factory default.');
			// BusyBox passwd, fed through a pipe (the password never touches a command line).
			// Not ubus "luci.setPassword": that object lives inside rpcd and would deadlock.
			let p = popen('passwd root >/dev/null 2>&1', 'w');
			if (!p) return fail('The password could not be changed.');
			p.write(pw + '\n');
			p.flush();
			sleep(1000);        // passwd asks twice; give it time to print the second prompt
			p.write(pw + '\n');
			let rc = p.close();
			return rc == 0 ? { ok: true, message: 'Admin password changed. Use it next time you sign in.' }
			               : fail('The password could not be changed.');
		}
	},
};

return { pyxis: methods };
