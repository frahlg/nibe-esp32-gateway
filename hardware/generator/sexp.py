"""Minimal S-expression reader/writer for KiCad files."""
import re

_tok = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))')


class Sym(str):
    """Unquoted atom."""


def parse(text):
    stack, cur = [], []
    pos = 0
    n = len(text)
    while pos < n:
        m = _tok.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise ValueError("parse error at %d: %r" % (pos, text[pos:pos + 40]))
        pos = m.end()
        if m.group(1):
            stack.append(cur)
            cur = []
        elif m.group(2):
            done = cur
            cur = stack.pop()
            cur.append(done)
        elif m.group(3) is not None:
            cur.append(m.group(3).replace('\\"', '"').replace("\\\\", "\\"))
        elif m.group(4):
            cur.append(Sym(m.group(4)))
    return cur[0] if len(cur) == 1 else cur


def _atom(x):
    if isinstance(x, Sym):
        return str(x)
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, (int, float)):
        if isinstance(x, float):
            s = ("%.4f" % x).rstrip("0").rstrip(".")
            return "0" if s in ("-0", "") else s
        return str(x)
    s = str(x).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return '"%s"' % s


def dump(e, indent=0):
    if not isinstance(e, list):
        return _atom(e)
    if not e:
        return "()"
    simple = all(not isinstance(c, list) for c in e)
    if simple:
        return "(" + " ".join(_atom(c) for c in e) + ")"
    pad = "\t" * (indent + 1)
    head = []
    i = 0
    while i < len(e) and not isinstance(e[i], list):
        head.append(_atom(e[i]))
        i += 1
    out = "(" + " ".join(head)
    for c in e[i:]:
        out += "\n" + pad + dump(c, indent + 1)
    out += "\n" + "\t" * indent + ")"
    return out


def find(e, key):
    for c in e:
        if isinstance(c, list) and c and c[0] == key:
            return c
    return None


def findall(e, key):
    return [c for c in e if isinstance(c, list) and c and c[0] == key]
