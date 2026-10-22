"""Printable label for one relay unit (run by provision.sh inside the tools container).

usage: python3 label.py <code> <ssid> <wifi_key> <admin_password>   > label.html
Reads the product names from /in/brand.env. Two QR codes:
  - the app link: joins the relay's Wi-Fi and opens the viewer app (iPhone camera, or Scan QR in the app)
  - a standard Wi-Fi QR, for phones without the app
"""
import html
import subprocess
import sys
import urllib.parse


def brand():
    values = {}
    for line in open("/in/brand.env"):
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip('"')
    return values


def qr_svg(text):
    svg = subprocess.run(["qrencode", "-t", "SVG", "-m", "1", "-l", "M", "-o", "-", text],
                         check=True, capture_output=True, text=True).stdout
    return svg[svg.index("<svg"):]


def wifi_escape(s):
    return "".join("\\" + c if c in '\\;,:"' else c for c in s)


code, ssid, key, admin = sys.argv[1:5]
b = brand()
relay = "192.168.50.1"
join = f"{b['APP_SCHEME']}://join?" + urllib.parse.urlencode({"ssid": ssid, "pass": key, "relay": relay})
wifi = f"WIFI:T:WPA;S:{wifi_escape(ssid)};P:{wifi_escape(key)};;"
e = html.escape

print(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{e(b['BRAND_NAME'])} {e(code)}</title>
<style>
  @page {{ size: 4in 3in; margin: 0; }}
  body {{ margin: 0; font: 10pt -apple-system, Helvetica, Arial, sans-serif; color: #000; background: #fff; }}
  .card {{ width: 4in; height: 3in; box-sizing: border-box; padding: 0.18in 0.22in; display: grid;
          grid-template-columns: 1.25in 1fr; grid-template-rows: auto 1fr auto; gap: 0.06in 0.18in; }}
  h1 {{ grid-column: 1 / 3; margin: 0; font-size: 13pt; display: flex; justify-content: space-between; }}
  h1 small {{ font-weight: 600; letter-spacing: 0.08em; }}
  .qr svg {{ width: 1.25in; height: 1.25in; display: block; }}
  .qr p {{ margin: 0.03in 0 0; font-size: 7pt; text-align: center; }}
  dl {{ margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 0.03in 0.08in; align-content: start; }}
  dt {{ font-size: 7pt; text-transform: uppercase; letter-spacing: 0.06em; color: #444; align-self: center; }}
  dd {{ margin: 0; font: 600 9pt ui-monospace, Menlo, monospace; white-space: nowrap; }}
  .small {{ grid-column: 1 / 3; font-size: 7pt; color: #333; }}
  .wifi svg {{ width: 0.75in; height: 0.75in; }}
  .right {{ display: grid; grid-template-rows: auto 1fr; gap: 0.08in; }}
  .wifirow {{ display: flex; gap: 0.1in; align-items: center; font-size: 7pt; }}
</style></head>
<body><div class="card">
  <h1>{e(b['BRAND_NAME'])}<small>UNIT {e(code)}</small></h1>
  <div class="qr">{qr_svg(join)}<p>Scan with your phone camera:<br>joins Wi-Fi and opens {e(b['APP_NAME'])}</p></div>
  <div class="right">
    <dl>
      <dt>Wi-Fi</dt><dd>{e(ssid)}</dd>
      <dt>Password</dt><dd>{e(key)}</dd>
      <dt>Settings</dt><dd>{e(b['RELAY_HOSTNAME'])}.local</dd>
      <dt>Admin</dt><dd>{e(admin)}</dd>
    </dl>
    <div class="wifirow"><div class="wifi">{qr_svg(wifi)}</div><div>Wi-Fi only<br>(no app)</div></div>
  </div>
  <div class="small">Plug the camera into the LAN port. Install {e(b['APP_NAME'])} first, then scan.
  Keep this label: it's the only copy of the admin password.</div>
</div></body></html>""")
