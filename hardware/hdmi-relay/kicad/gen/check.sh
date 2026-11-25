#!/bin/sh
# Regenerate, run ERC and print violations and nets.  usage: gen/check.sh [net-filter]
cd "$(dirname "$0")/.." || exit 1
KC=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
python3 gen/build.py || exit 1
$KC sch erc --format json -o erc.json --severity-all relay.kicad_sch 2>&1 | grep -v Fontconfig
$KC sch export netlist -o build.net relay.kicad_sch 2>&1 | grep -v Fontconfig
python3 gen/report.py "$@"
