"""Minimal S-expression reader/writer for KiCad files."""
import re

_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


class Sym(str):
    """An unquoted atom (keyword or number)."""


def parse(text):
    stack, cur = [], []
    pos = 0
    n = len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise ValueError(f"bad token at {pos}: {text[pos:pos+40]!r}")
        pos = m.end()
        if m.group(1):
            stack.append(cur)
            cur = []
        elif m.group(2):
            done = cur
            cur = stack.pop()
            cur.append(done)
        elif m.group(3) is not None:
            cur.append(re.sub(r"\\(.)", lambda e: "\n" if e.group(1) == "n" else e.group(1), m.group(3)))
        else:
            cur.append(Sym(m.group(4)))
    return cur[0] if len(cur) == 1 else cur


def q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def dump(node, indent=0):
    """Serialize a parsed tree back to text (atoms stay atoms, strings get quoted)."""
    if not isinstance(node, list):
        return str(node) if isinstance(node, Sym) else (fmt_num(node) if isinstance(node, (int, float)) else q(node))
    if not node:
        return "()"
    simple = all(not isinstance(x, list) for x in node)
    head = dump(node[0])
    if simple:
        return "(" + " ".join(dump(x) for x in node) + ")"
    pad = "\t" * (indent + 1)
    parts = ["(" + head]
    for x in node[1:]:
        if isinstance(x, list):
            parts.append("\n" + pad + dump(x, indent + 1))
        else:
            parts.append(" " + dump(x))
    parts.append("\n" + "\t" * indent + ")")
    return "".join(parts)


def fmt_num(v):
    if isinstance(v, int):
        return str(v)
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def find(node, key):
    for x in node:
        if isinstance(x, list) and x and x[0] == key:
            return x
    return None


def find_all(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]
