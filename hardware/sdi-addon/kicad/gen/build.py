"""Builds the SDI add-on schematic: python3 build.py  ->  ../sdi.kicad_sch and one file per sheet."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import footprints  # noqa: E402
import sheets  # noqa: E402
from sch import Project  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

project = Project(OUT, "HDMI-in relay: SDI add-on, rev A")
sheets.receiver(project)
sheets.power(project)
sheets.interface(project)
project.write()
footprints.write(OUT)
print("wrote", ", ".join(s.file for s in project.sheets))
