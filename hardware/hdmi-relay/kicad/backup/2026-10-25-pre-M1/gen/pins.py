import sys
from sch import libsym
for lid in sys.argv[1:]:
    s = libsym(lid)
    fp = [p for p in s.node if isinstance(p, list) and p[0] == "property" and p[1] in ("Footprint", "Reference")]
    print("==", lid, "units", s.units, [f"{p[1]}={p[2]}" for p in fp])
    for n in sorted(s.pins, key=lambda k: (len(k), k)):
        for r in s.pins[n]:
            print(f"  {n:>4} {r['name']:<14} {r['type']:<13} ({r['x']},{r['y']}) a{r['angle']} u{r['unit']}")
