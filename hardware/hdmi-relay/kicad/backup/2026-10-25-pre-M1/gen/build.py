"""Builds the rev A schematic: python3 build.py  ->  ../relay.kicad_sch and one file per sheet."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ethernet  # noqa: E402
import footprints  # noqa: E402
import hdmi_in  # noqa: E402
import board_io_sheets as io_sheets  # noqa: E402
import module  # noqa: E402
import power  # noqa: E402
from sch import Project  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

project = Project(OUT, "HDMI-in relay carrier, rev A")
power.build(project)
hdmi_in.build(project)
io_sheets.hdmi_out(project)
ethernet.build(project)
io_sheets.m2(project)
io_sheets.board_io(project)
module.build(project)
project.write()
footprints.write(OUT)
print("wrote", ", ".join(s.file for s in project.sheets))
