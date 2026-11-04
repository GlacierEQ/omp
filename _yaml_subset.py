"""Minimal YAML subset parser for omp/roster.yaml.

Supports only the constructs used in roster.yaml:
  - block mappings (indentation-based)
  - block sequences (`- item`)
  - flow sequences (`[a, b]`)
  - scalars: quoted strings, unquoted strings, ints, floats, null, booleans
  - multi-line folded scalars (`>`)

Not a general YAML parser. Intentionally tiny and dependency-free.
"""

from __future__ import annotations

import re

_INT = re.compile(r"^-?[0-9]+$")
_FLOAT = re.compile(r"^-?[0-9]+\.[0-9]+")
_NULL = {"null", "~", ""}
_BOOL = {"true": True, "false": False, "yes": True, "no": False, "on": True, "off": False}


def _scalar(token: str):
    token = token.strip()
    if token in _NULL:
        return None
    if token in _BOOL:
        return _BOOL[token]
    if _INT.match(token):
        return int(token)
    if _FLOAT.match(token):
        return float(token)
    if (token.startswith('"') and token.endswith('"')) or (
        token.startswith("'") and token.endswith("'")
    ):
        return token[1:-1]
    return token


def _parse_flow_sequence(text: str):
    text = text.strip()
    if not (text.startswith("[") and text.endswith("]")):
        raise ValueError(f"not a flow sequence: {text!r}")
    inner = text[1:-1].strip()
    if not inner:
        return []
    return [_scalar(p.strip()) for p in inner.split(",")]


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _blank_or_comment(line: str) -> bool:
    s = line.strip()
    return not s or s.startswith("#")


class _Parser:
    def __init__(self, lines):
        self.lines = lines
        self.n = len(lines)
        self.i = 0

    def parse(self):
        return self._parse_mapping(0)

    def _parse_mapping(self, base_indent):
        result = {}
        while self.i < self.n:
            line = self.lines[self.i]
            if _blank_or_comment(line):
                self.i += 1
                continue
            ind = _indent(line)
            if ind < base_indent:
                break
            if ind > base_indent:
                break
            stripped = line.strip()
            if ":" not in stripped:
                self.i += 1
                continue
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            self.i += 1
            if val == "":
                nested = self._parse_collection(base_indent + 2)
                result[key] = nested
            elif val.startswith("["):
                result[key] = _parse_flow_sequence(val)
            elif val.startswith(">"):
                parts = []
                while self.i < self.n:
                    l = self.lines[self.i]
                    if _blank_or_comment(l):
                        self.i += 1
                        continue
                    if _indent(l) <= base_indent:
                        break
                    parts.append(l.strip())
                    self.i += 1
                result[key] = " ".join(parts)
            else:
                result[key] = _scalar(val)
        return result

    def _parse_collection(self, base_indent):
        if self.i < self.n and self.lines[self.i].strip().startswith("- "):
            return self._parse_sequence(base_indent)
        return self._parse_mapping(base_indent)

    def _parse_sequence(self, base_indent):
        seq = []
        while self.i < self.n:
            line = self.lines[self.i]
            if _blank_or_comment(line):
                self.i += 1
                continue
            ind = _indent(line)
            if ind < base_indent:
                break
            if ind > base_indent:
                break
            stripped = line.strip()
            if not stripped.startswith("- "):
                break
            item_text = stripped[2:].strip()
            self.i += 1
            if ":" in item_text and not item_text.startswith(": "):
                # `- key: value` -> mapping item; subsequent deeper-indent keys join it
                key, _, val = item_text.partition(":")
                key = key.strip()
                val = val.strip()
                item = {}
                if val == "":
                    item[key] = self._parse_collection(ind + 2)
                elif val.startswith("["):
                    item[key] = _parse_flow_sequence(val)
                else:
                    item[key] = _scalar(val)
                # collect remaining keys of this mapping item (deeper indent than the dash)
                while self.i < self.n:
                    l = self.lines[self.i]
                    if _blank_or_comment(l):
                        self.i += 1
                        continue
                    ind2 = _indent(l)
                    if ind2 <= ind:
                        break
                    s2 = l.strip()
                    if s2.startswith("- "):
                        break
                    if ":" not in s2:
                        self.i += 1
                        continue
                    k2, _, v2 = s2.partition(":")
                    k2 = k2.strip()
                    v2 = v2.strip()
                    self.i += 1
                    if v2 == "":
                        item[k2] = self._parse_collection(ind2 + 2)
                    elif v2.startswith("["):
                        item[k2] = _parse_flow_sequence(v2)
                    else:
                        item[k2] = _scalar(v2)
                seq.append(item)
            else:
                seq.append(_scalar(item_text))
        return seq


def safe_load(text: str):
    return _Parser(text.splitlines()).parse()
