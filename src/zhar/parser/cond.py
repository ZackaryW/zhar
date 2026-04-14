"""Condition evaluator for the %%ZHAR.*%% template language.

Public API
----------
eval_expr(expr, facts)
    Evaluate a single condition expression string against a facts dict.
    Supports: ==, !=, <, >, <=, >=, in (list or substring),
    lowercase and/or/not connectors, _ver key suffix for version comparison.

eval_condition_groups(groups, facts)
    Evaluate accumulated FACT/ORFACT groups.
    groups is a list of AND-groups; each AND-group is a list of expr strings.
    Result: OR of (AND of each group's expressions).
"""
from __future__ import annotations

import re
from typing import Any

try:
    from packaging.version import Version as _Version

    _HAS_PACKAGING = True
except ImportError:  # pragma: no cover
    _HAS_PACKAGING = False


class CondError(Exception):
    """Raised when a condition expression cannot be parsed or evaluated."""


# ── tokeniser ─────────────────────────────────────────────────────────────────

_TOK_RE = re.compile(
    r"""
    (?P<NOT>\bnot\b)
    | (?P<AND>\band\b)
    | (?P<OR>\bor\b)
    | (?P<CMP>
        [^\s\(\)]+          # key
        \s*
        (?:==|!=|<=|>=|<|>|in)  # operator
        \s*
        (?:\[[^\]]*\]|\S+)  # value: list literal or bare word
      )
    """,
    re.VERBOSE | re.IGNORECASE,
)

_SINGLE_RE = re.compile(
    r"""^
    (?P<key>[^\s]+?)
    \s+
    (?P<op>==|!=|<=|>=|<|>|in)
    \s+
    (?P<val>.+)
    $""",
    re.VERBOSE,
)


# ── single comparison ─────────────────────────────────────────────────────────

def _eval_single(key: str, op: str, raw_val: str, facts: dict[str, str]) -> bool:
    """Evaluate one key op value comparison against facts."""
    use_ver = key.endswith("_ver")
    fact_key = key[:-4] if use_ver else key
    fact_val = facts.get(fact_key)

    if fact_val is None:
        return False

    if op == "in":
        raw_val = raw_val.strip()
        if raw_val.startswith("[") and raw_val.endswith("]"):
            # List literal: [a, b, c]
            items = [v.strip() for v in raw_val[1:-1].split(",") if v.strip()]
            return fact_val in items
        else:
            # Substring check: fact_val in raw_val (as string)
            return fact_val in raw_val

    if use_ver:
        if not _HAS_PACKAGING:  # pragma: no cover
            raise CondError("packaging required for _ver comparisons.")
        try:
            lhs, rhs = _Version(fact_val), _Version(raw_val.strip())
        except Exception as exc:
            raise CondError(f"Bad version string: {exc}") from exc
        return {
            "==": lhs == rhs, "!=": lhs != rhs,
            "<":  lhs <  rhs, ">":  lhs >  rhs,
            "<=": lhs <= rhs, ">=": lhs >= rhs,
        }[op]

    rhs = raw_val.strip()
    return {
        "==": fact_val == rhs, "!=": fact_val != rhs,
        "<":  fact_val <  rhs, ">":  fact_val >  rhs,
        "<=": fact_val <= rhs, ">=": fact_val >= rhs,
    }.get(op, False)


# ── expression evaluator ──────────────────────────────────────────────────────

def eval_expr(expr: str, facts: dict[str, str]) -> bool:
    """Evaluate a compound condition expression.

    Supports lowercase ``and``, ``or``, ``not`` connectors with standard
    ``and > or`` precedence.  Raises ``CondError`` on parse failure.
    """
    expr = expr.strip()
    if not expr:
        return False

    # Tokenise
    atoms: list[tuple[str, str]] = []  # (kind, text)
    pos = 0
    while pos < len(expr):
        # skip whitespace
        ws = re.match(r"\s+", expr[pos:])
        if ws:
            pos += ws.end()
            continue
        # 'not'
        m = re.match(r"\bnot\b", expr[pos:], re.IGNORECASE)
        if m:
            atoms.append(("NOT", "not"))
            pos += m.end()
            continue
        # 'and'
        m = re.match(r"\band\b", expr[pos:], re.IGNORECASE)
        if m:
            atoms.append(("AND", "and"))
            pos += m.end()
            continue
        # 'or'
        m = re.match(r"\bor\b", expr[pos:], re.IGNORECASE)
        if m:
            atoms.append(("OR", "or"))
            pos += m.end()
            continue
        # comparison: key op val  (op includes 'in')
        m = re.match(
            r"""([^\s]+)\s+(==|!=|<=|>=|<|>|in)\s+(\[[^\]]*\]|\S+)""",
            expr[pos:],
            re.IGNORECASE,
        )
        if m:
            atoms.append(("CMP", m.group(0)))
            pos += m.end()
            continue
        raise CondError(f"Unrecognised token near {expr[pos:pos+20]!r}")

    # Build value stream (resolve NOTs inline)
    values: list[Any] = []
    i = 0
    while i < len(atoms):
        kind, text = atoms[i]
        if kind == "NOT":
            i += 1
            if i >= len(atoms) or atoms[i][0] != "CMP":
                raise CondError("'not' must be followed by a comparison.")
            m2 = re.match(
                r"""([^\s]+)\s+(==|!=|<=|>=|<|>|in)\s+(.+)""",
                atoms[i][1].strip(),
                re.IGNORECASE,
            )
            if not m2:
                raise CondError(f"Bad comparison after 'not': {atoms[i][1]!r}")
            values.append(
                not _eval_single(m2.group(1), m2.group(2).lower(), m2.group(3), facts)
            )
        elif kind == "CMP":
            m2 = re.match(
                r"""([^\s]+)\s+(==|!=|<=|>=|<|>|in)\s+(.+)""",
                text.strip(),
                re.IGNORECASE,
            )
            if not m2:
                raise CondError(f"Bad comparison: {text!r}")
            values.append(
                _eval_single(m2.group(1), m2.group(2).lower(), m2.group(3), facts)
            )
        elif kind in ("AND", "OR"):
            values.append(text.lower())  # normalise to lowercase for fold steps
        i += 1

    if not values:
        return False

    # Fold AND first (higher precedence)
    and_folded: list[Any] = []
    i = 0
    while i < len(values):
        v = values[i]
        if v == "and":
            lhs = and_folded.pop()
            i += 1
            and_folded.append(bool(lhs) and bool(values[i]))
        else:
            and_folded.append(v)
        i += 1

    # Fold OR
    result = bool(and_folded[0])
    i = 1
    while i < len(and_folded):
        conn = and_folded[i]
        i += 1
        rhs = bool(and_folded[i])
        i += 1
        if conn == "or":
            result = result or rhs
        else:
            raise CondError(f"Unexpected connector: {conn!r}")
    return result


# ── group evaluator ───────────────────────────────────────────────────────────

def eval_condition_groups(
    groups: list[list[str]],
    facts: dict[str, str],
) -> bool:
    """Evaluate accumulated FACT/ORFACT groups.

    ``groups`` is a list of AND-groups.  Each AND-group is a list of
    expression strings that all must be true.  Groups are ORed together.
    An empty ``groups`` list returns ``False``.
    """
    if not groups:
        return False
    for and_group in groups:
        if all(eval_expr(e, facts) for e in and_group):
            return True
    return False
