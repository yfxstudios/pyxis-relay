"""Generates KiCad 10 schematics from Python descriptions.

Each part is placed as drawn in its library (no rotation). Every connected pin gets a short wire stub ending in a
net label (or a GND symbol), and every unused pin gets a no-connect flag, so connectivity is explicit and checkable
with KiCad's ERC. Nets named in a sheet's `globals` (or shared across sheets) use global labels; the rest use local
labels.
"""
import copy
import os
import uuid

from sexpr import Sym, dump, find, find_all, parse, q

KICAD_SYMBOLS = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
PROJECT = "relay"
NS = uuid.UUID("6b9c7a52-6a1f-4f0e-9a51-6d1e6a3f0001")
STUB = 2.54
GRID = 1.27


def uid(*parts):
    return str(uuid.uuid5(NS, "/".join(str(p) for p in parts)))


def snap(v):
    return round(round(v / GRID) * GRID, 4)


# ---------------------------------------------------------------- libraries

_libs = {}
_custom = {}  # name -> parsed symbol node (for the project library "relay")


def _lib(name):
    if name == "relay":
        return _custom
    if name not in _libs:
        tree = parse(open(os.path.join(KICAD_SYMBOLS, name + ".kicad_sym")).read())
        _libs[name] = {x[1]: x for x in find_all(tree, "symbol")}
    return _libs[name]


def add_custom(text):
    node = parse(text)
    _custom[node[1]] = node
    return node[1]


def _flat(lib, name):
    node = _lib(lib)[name]
    ext = find(node, "extends")
    if not ext:
        return copy.deepcopy(node)
    parent = _flat(lib, ext[1])
    out = [Sym("symbol"), name]
    child_props = {p[1]: p for p in find_all(node, "property")}
    for x in parent[2:]:
        if isinstance(x, list) and x[0] == "property":
            out.append(copy.deepcopy(child_props.pop(x[1], x)))
        elif isinstance(x, list) and x[0] == "symbol":
            sub = copy.deepcopy(x)
            sub[1] = name + sub[1][len(ext[1]):]
            out.append(sub)
        else:
            out.append(copy.deepcopy(x))
    out[2:2] = list(child_props.values())
    return out


class LibSymbol:
    def __init__(self, lib_id):
        lib, name = lib_id.split(":", 1)
        self.lib_id = lib_id
        self.node = _flat(lib, name)
        self.embedded = copy.deepcopy(self.node)
        self.embedded[1] = lib_id
        self.pins = {}  # number -> dict(name, x, y, angle, unit)
        self.power = find(self.node, "power") is not None
        for sub in find_all(self.node, "symbol"):
            unit = int(sub[1].rsplit("_", 2)[-2])
            for p in find_all(sub, "pin"):
                at = find(p, "at")
                name = find(p, "name")[1]
                num = find(p, "number")[1]
                self.pins.setdefault(num, []).append(
                    dict(name=name, x=float(at[1]), y=float(at[2]), angle=int(float(at[3])), unit=unit, type=str(p[1])))
        self.units = sorted({p["unit"] for ps in self.pins.values() for p in ps if p["unit"] > 0}) or [1]

    def pin_by(self, key):
        """Pin numbers for a pin number, or for every pin with that name (stacked and repeated pins)."""
        if key in self.pins:
            return [key]
        hits = [n for n, ps in self.pins.items() if any(p["name"] == key for p in ps)]
        if not hits:
            raise KeyError(f"{self.lib_id}: no pin {key!r}")
        return hits


_symcache = {}


def libsym(lib_id):
    if lib_id not in _symcache:
        _symcache[lib_id] = LibSymbol(lib_id)
    return _symcache[lib_id]


# ---------------------------------------------------------------- custom symbol builder

def box_symbol(name, left, right, top=(), bottom=(), ref="U", value=None, footprint="", description="",
               datasheet="~", width=None, pin_len=2.54):
    """A rectangle symbol. Each side is a list of (number, name, type) or None for a gap.
    Numbers may be a list to stack several pads on one pin position (extra ones are hidden, same net)."""
    rows = max(len(left), len(right))
    h = (rows + 1) * 2.54
    longest = max([len(p[1]) for p in list(left) + list(right) if p] + [4])
    w = width or snap(max(15.24, longest * 1.27 * 2 + 5.08))
    w = snap(w / 2) * 2
    top_y = snap(h / 2)
    pins = []

    def add(num, pname, ptype, x, y, ang, hidden=False):
        nums = num if isinstance(num, (list, tuple)) else [num]
        for i, n in enumerate(nums):
            # extra stacked pads are hidden *passive* pins: a hidden power_in pin would join a net named after it
            ptype_i = "passive" if i else ptype
            pins.append(f'(pin {ptype_i} line (at {x} {y} {ang}) (length {pin_len}){" (hide yes)" if (i or hidden) else ""} '
                        f'(name {q(pname)} (effects (font (size 1.27 1.27)))) '
                        f'(number {q(n)} (effects (font (size 1.27 1.27)))))')

    for i, p in enumerate(left):
        if p:
            add(p[0], p[1], p[2], -w / 2 - pin_len, snap(top_y - 2.54 * (i + 1)), 0)
    for i, p in enumerate(right):
        if p:
            add(p[0], p[1], p[2], w / 2 + pin_len, snap(top_y - 2.54 * (i + 1)), 180)
    for i, p in enumerate(top):
        if p:
            add(p[0], p[1], p[2], snap(-w / 2 + 2.54 * (i + 1)), top_y + pin_len, 270)
    for i, p in enumerate(bottom):
        if p:
            add(p[0], p[1], p[2], snap(-w / 2 + 2.54 * (i + 1)), -top_y - pin_len, 90)
    text = f'''(symbol {q(name)} (pin_names (offset 1.016)) (exclude_from_sim no) (in_bom yes) (on_board yes)
  (property "Reference" {q(ref)} (at {-w/2} {top_y + 1.27} 0) (effects (font (size 1.27 1.27)) (justify left bottom)))
  (property "Value" {q(value or name)} (at {w/2} {top_y + 1.27} 0) (effects (font (size 1.27 1.27)) (justify right bottom)))
  (property "Footprint" {q(footprint)} (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
  (property "Datasheet" {q(datasheet)} (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
  (property "Description" {q(description)} (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
  (symbol {q(name + "_0_1")} (rectangle (start {-w/2} {top_y}) (end {w/2} {-top_y}) (stroke (width 0.254) (type default)) (fill (type background))))
  (symbol {q(name + "_1_1")} {" ".join(pins)})
  (embedded_fonts no))'''
    return add_custom(text)


def write_custom_library(path):
    lines = ["(kicad_symbol_lib", '\t(version 20251024)', '\t(generator "relay_gen")', '\t(generator_version "10.0")']
    for name in sorted(_custom):
        lines.append("\t" + dump(_custom[name], 1))
    lines.append(")")
    open(path, "w").write("\n".join(lines) + "\n")


# ---------------------------------------------------------------- sheets

class Part:
    def __init__(self, sheet, lib_id, ref, value, at, footprint, props, conn, dnp, unit):
        self.sheet, self.sym = sheet, libsym(lib_id)
        self.ref, self.value, self.at = ref, value, (snap(at[0]), snap(at[1]))
        self.footprint, self.props, self.dnp, self.unit = footprint, props, dnp, unit
        self.conn = {}
        for k, net in conn.items():
            for n in self.sym.pin_by(str(k)):
                self.conn[n] = net

    def pin_points(self):
        """(number, pin record, absolute point, outward vector) for this part's unit."""
        X, Y = self.at
        out = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}
        for num, recs in self.sym.pins.items():
            for r in recs:
                if r["unit"] not in (0, self.unit):
                    continue
                yield num, r, (snap(X + r["x"]), snap(Y - r["y"])), out[r["angle"]]


class Sheet:
    def __init__(self, project, name, title, ref_base, paper="A3"):
        self.project, self.name, self.title, self.paper = project, name, title, paper
        self.file = name + ".kicad_sch"
        self.uuid = uid("sheet", name)
        self.parts, self.texts, self.items = [], [], []
        self.counters = {}
        self.ref_base = ref_base
        self.globals = set()
        project.sheets.append(self)

    def next_ref(self, prefix):
        n = self.counters.get(prefix, 0) + 1
        self.counters[prefix] = n
        return f"{prefix}{self.ref_base + n}"

    def add(self, lib_id, at, conn, value=None, ref=None, footprint="", dnp=False, unit=1, **props):
        sym = libsym(lib_id)
        prefix = ref or find(sym.node, "property") and next(
            p[2] for p in find_all(sym.node, "property") if p[1] == "Reference")
        if not prefix or prefix[-1].isdigit():
            raise ValueError(f"need a reference prefix for {lib_id}")
        refname = self.next_ref(prefix.rstrip("?"))
        if value is None:
            value = next(p[2] for p in find_all(sym.node, "property") if p[1] == "Value")
        if not footprint:  # fall back to the library symbol's own footprint
            footprint = next((p[2] for p in find_all(sym.node, "property") if p[1] == "Footprint"), "")
        p = Part(self, lib_id, refname, value, at, footprint, props, conn, dnp, unit)
        self.parts.append(p)
        return p

    def text(self, s, at, size=1.27):
        self.texts.append((s, (snap(at[0]), snap(at[1])), size))

    def flag(self, net, at):
        """PWR_FLAG on a net: tells ERC this net is driven (for nets fed only through passive pins)."""
        self.add("power:PWR_FLAG", at, {"1": net}, ref="#FLG")

    # ------------------------------------------------------------ output

    def _label(self, net, pt, vec):
        ang = {(-1, 0): 180, (1, 0): 0, (0, 1): 270, (0, -1): 90}[vec]
        just = "left" if ang in (0, 90) else "right"
        u = uid(self.name, "label", net, pt)
        if net in self.project.global_nets:
            return (f'(global_label {q(net)} (shape passive) (at {pt[0]} {pt[1]} {ang}) (fields_autoplaced yes) '
                    f'(effects (font (size 1.27 1.27)) (justify {just})) (uuid {q(u)}) '
                    f'(property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {pt[0]} {pt[1]} 0) '
                    f'(effects (font (size 1.27 1.27)) (hide yes))))')
        return (f'(label {q(net)} (at {pt[0]} {pt[1]} {ang}) (effects (font (size 1.27 1.27)) '
                f'(justify {just} bottom)) (uuid {q(u)}))')

    def _gnd(self, pt, vec):
        """A GND power symbol at pt; drawn pointing away from the pin."""
        ang = {(0, 1): 0, (0, -1): 180, (-1, 0): 270, (1, 0): 90}[vec]
        ref = self.next_ref("#PWR")
        u = uid(self.name, "gnd", pt)
        return (f'(symbol (lib_id "power:GND") (at {pt[0]} {pt[1]} {ang}) (unit 1) (exclude_from_sim no) (in_bom yes) '
                f'(on_board yes) (dnp no) (uuid {q(u)}) '
                f'(property "Reference" {q(ref)} (at {pt[0]} {pt[1]} 0) (effects (font (size 1.27 1.27)) (hide yes))) '
                f'(property "Value" "GND" (at {pt[0]} {pt[1] + 3.81} 0) (effects (font (size 1.27 1.27)) (hide yes))) '
                f'(property "Footprint" "" (at {pt[0]} {pt[1]} 0) (effects (font (size 1.27 1.27)) (hide yes))) '
                f'(property "Datasheet" "" (at {pt[0]} {pt[1]} 0) (effects (font (size 1.27 1.27)) (hide yes))) '
                f'(property "Description" "" (at {pt[0]} {pt[1]} 0) (effects (font (size 1.27 1.27)) (hide yes))) '
                f'(pin "1" (uuid {q(uid(u, "p1"))})) '
                f'(instances (project {q(PROJECT)} (path {q(self.project.path(self))} (reference {q(ref)}) (unit 1)))))')

    def render(self):
        libids = sorted({p.sym.lib_id for p in self.parts} | {"power:GND"})
        out = [f'(kicad_sch (version 20251024) (generator "relay_gen") (generator_version "10.0") '
               f'(uuid {q(self.uuid)}) (paper {q(self.paper)}) (title_block (title {q(self.title)}) '
               f'(date "2026-10-22") (rev "A") (company "HDMI-in relay"))']
        out.append("(lib_symbols " + " ".join(dump(libsym(i).embedded) for i in libids) + ")")
        for p in self.parts:
            out.append(self._symbol(p))
            drawn = {}  # stacked pins share one point: draw it once, and they must share a net
            for num, r, pt, vec in sorted(p.pin_points(), key=lambda t: t[0]):
                if pt in drawn:
                    if p.conn.get(num, drawn[pt]) != drawn[pt]:
                        raise ValueError(f"{p.ref}: stacked pin {num} at {pt} on {p.conn.get(num)} vs {drawn[pt]}")
                    continue
                if num in p.conn:
                    drawn[pt] = p.conn[num]
                if p.sym.power:
                    if num in p.conn and p.conn[num] is not None and p.sym.lib_id == "power:PWR_FLAG":
                        end = (pt[0], snap(pt[1] + STUB))
                        out.append(f'(wire (pts (xy {pt[0]} {pt[1]}) (xy {end[0]} {end[1]})) (stroke (width 0) '
                                   f'(type default)) (uuid {q(uid(self.name, "w", p.ref, num, pt))}))')
                        net = p.conn[num]
                        out.append(self._gnd(end, (0, 1)) if net == "GND" else self._label(net, end, (0, 1)))
                    continue
                if r["type"] == "no_connect" and num not in p.conn:
                    continue
                net = p.conn.get(num, "__NC__")
                if net == "__NC__" and num not in p.conn:
                    # unlisted pin: leave it for ERC to report as unconnected (catches omissions)
                    continue
                if net is None:
                    out.append(f'(no_connect (at {pt[0]} {pt[1]}) (uuid {q(uid(self.name, "nc", p.ref, num, pt))}))')
                    continue
                end = (snap(pt[0] + vec[0] * STUB), snap(pt[1] + vec[1] * STUB))
                out.append(f'(wire (pts (xy {pt[0]} {pt[1]}) (xy {end[0]} {end[1]})) (stroke (width 0) (type default)) '
                           f'(uuid {q(uid(self.name, "w", p.ref, num, pt))}))')
                out.append(self._gnd(end, vec) if net == "GND" else self._label(net, end, vec))
        for s, pt, size in self.texts:
            out.append(f'(text {q(s)} (exclude_from_sim no) (at {pt[0]} {pt[1]} 0) '
                       f'(effects (font (size {size} {size})) (justify left top)) (uuid {q(uid(self.name, "t", s, pt))}))')
        out.append('(sheet_instances (path "/" (page "1"))) (embedded_fonts no))')
        return pretty(" ".join(out))

    def _symbol(self, p):
        X, Y = p.at
        u = uid(self.name, "sym", p.ref)
        # Reference and Value where the library symbol puts them (two-pin parts: to the right of the body)
        lib = {pp[1]: pp for pp in find_all(p.sym.node, "property")}

        def spot(key, default):
            at = find(lib.get(key, []), "at")
            return (snap(X + float(at[1])), snap(Y - float(at[2]))) if at else default
        props = [("Reference", p.ref, spot("Reference", (X, Y - 2.54)), False),
                 ("Value", p.value, spot("Value", (X, Y + 2.54)), False),
                 ("Footprint", p.footprint, (X, Y), True), ("Datasheet", "~", (X, Y), True),
                 ("Description", "", (X, Y), True)]
        if p.sym.power:
            props = [("Reference", p.ref, (X, Y), True), ("Value", p.value, (X, Y - 3.81), False),
                     ("Footprint", "", (X, Y), True), ("Datasheet", "~", (X, Y), True), ("Description", "", (X, Y), True)]
        for k, v in p.props.items():
            props.append((k, v, (X, Y), True))
        ptxt = " ".join(
            f'(property {q(k)} {q(v)} (at {xy[0]} {xy[1]} 0) (effects (font (size 1.27 1.27)){" (hide yes)" if hid else ""}))'
            for k, v, xy, hid in props)
        pins = " ".join(f'(pin {q(n)} (uuid {q(uid(u, n))}))' for n in sorted(p.sym.pins))
        return (f'(symbol (lib_id {q(p.sym.lib_id)}) (at {X} {Y} 0) (unit {p.unit}) (exclude_from_sim no) '
                f'(in_bom {"no" if p.sym.power else "yes"}) (on_board {"no" if p.sym.power else "yes"}) '
                f'(dnp {"yes" if p.dnp else "no"}) (uuid {q(u)}) {ptxt} {pins} '
                f'(instances (project {q(PROJECT)} (path {q(self.project.path(self))} (reference {q(p.ref)}) '
                f'(unit {p.unit})))))')


def pretty(text):
    depth = 0
    for ch in text:
        depth += (ch == "(") - (ch == ")")
    if depth:
        raise ValueError(f"unbalanced s-expression ({depth:+d})")
    return dump(parse(text)) + "\n"


class Project:
    def __init__(self, outdir, title):
        self.outdir, self.title = outdir, title
        self.sheets = []
        self.root_uuid = uid("root")
        self.global_nets = set()

    def path(self, sheet):
        return f"/{self.root_uuid}/{sheet.uuid}"

    def write(self):
        os.makedirs(self.outdir, exist_ok=True)
        # nets used on more than one sheet, or declared global, get global labels
        seen = {}
        for s in self.sheets:
            for p in s.parts:
                for net in p.conn.values():
                    if net and net != "GND":
                        seen.setdefault(net, set()).add(s.name)
        for net, where in seen.items():
            if len(where) > 1:
                self.global_nets.add(net)
        for s in self.sheets:
            self.global_nets |= s.globals
        for s in self.sheets:
            open(os.path.join(self.outdir, s.file), "w").write(s.render())
        self._root()
        write_custom_library(os.path.join(self.outdir, "relay.kicad_sym"))
        open(os.path.join(self.outdir, "sym-lib-table"), "w").write(
            '(sym_lib_table\n\t(version 7)\n\t(lib (name "relay")(type "KiCad")(uri "${KIPRJMOD}/relay.kicad_sym")'
            '(options "")(descr "Project symbols"))\n)\n')
        pro = os.path.join(self.outdir, PROJECT + ".kicad_pro")
        if not os.path.exists(pro):
            open(pro, "w").write('{\n  "meta": {\n    "filename": "%s.kicad_pro",\n    "version": 3\n  }\n}\n' % PROJECT)

    def _root(self):
        items = []
        for i, s in enumerate(self.sheets):
            x, y = 30 + (i % 4) * 70, 40 + (i // 4) * 40
            items.append(
                f'(sheet (at {x} {y}) (size 55 20) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) '
                f'(fields_autoplaced yes) (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0000)) '
                f'(uuid {q(s.uuid)}) '
                f'(property "Sheetname" {q(s.title)} (at {x} {y - 0.7} 0) (effects (font (size 1.27 1.27)) (justify left bottom))) '
                f'(property "Sheetfile" {q(s.file)} (at {x} {y + 20.6} 0) (effects (font (size 1.27 1.27)) (justify left top))) '
                f'(instances (project {q(PROJECT)} (path {q("/" + self.root_uuid)} (page {q(str(i + 2))})))))')
        text = (f'(kicad_sch (version 20251024) (generator "relay_gen") (generator_version "10.0") '
                f'(uuid {q(self.root_uuid)}) (paper "A4") (title_block (title {q(self.title)}) (date "2026-10-22") '
                f'(rev "A") (company "HDMI-in relay")) (lib_symbols) {" ".join(items)} '
                f'(sheet_instances (path "/" (page "1"))) (embedded_fonts no))')
        open(os.path.join(self.outdir, PROJECT + ".kicad_sch"), "w").write(pretty(text))
