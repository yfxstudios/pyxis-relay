"""Prints ERC violations and the netlist (from erc.json and build.net)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexpr import find, find_all, parse  # noqa: E402

d = json.load(open("erc.json"))
for sh in d["sheets"]:
    for v in sh["violations"]:
        print(f"ERC {v['severity']:7} {sh['path']:12} {v['type']}: {', '.join(i['description'] for i in v['items'])}")
t = parse(open("build.net").read())
print("components:", len(find_all(find(t, "components"), "comp")))
flt = sys.argv[1] if len(sys.argv) > 1 else None
if flt != "-":
    for n in find_all(find(t, "nets"), "net"):
        name = find(n, "name")[1]
        if flt and flt not in name:
            continue
        nodes = [f"{find(x, 'ref')[1]}.{find(x, 'pin')[1]}" + (f"({find(x, 'pinfunction')[1]})" if find(x, 'pinfunction') else "")
                 for x in find_all(n, "node")]
        print(f"  {name:24} {' '.join(nodes)}")
