"""zhar stack template language — parser and renderer.

Token reference
---------------
%ZO% <cond>         Open conditional block
  !! <chunk_ref>    True-branch: insert rendered chunk file
  %TEXT%            True-branch: open inline text block
  ...               Inline text lines
  %TEXT%            Close inline text block
  ?? <chunk_ref>    False-branch: insert rendered chunk file
  %TEXT% ... %TEXT% False-branch: inline text block
%ZC%                Close block (%ZO% or %ZIF%)

%ZIF% <cond>        Nested condition (same as %ZO%, used for nested scopes)

[[<ref>]]           Raw paste — insert chunk content verbatim, no re-evaluation
%ZM% <expr>         Python eval against memory context (group names → node lists)

Condition grammar
-----------------
  <operand> <op> <value>  — single comparison
  Compound via AND / OR (capitalised, space-separated); NOT prefix
  + is shorthand for AND
  _ver suffix on operand key triggers packaging.version.Version comparison
"""
# %ZHAR:da1b% %ZHAR:f3a6% %ZHAR:1782%
# %ZHAR:5969% %ZHAR:5dc4%
from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

try:
    from packaging.version import Version as _Version
    _HAS_PACKAGING = True
except ImportError:  # pragma: no cover
    _HAS_PACKAGING = False


# ── public exceptions ─────────────────────────────────────────────────────────

class TemplateError(Exception):
    """Raised on any template parse or evaluation error."""


# ── context ───────────────────────────────────────────────────────────────────

@dataclass
class TemplateContext:
    """All inputs available during template rendering.

    Attributes
    ----------
    facts:
        Flat string key-value store (from ``Facts.all()``).
    groups:
        Dict mapping group name → list of Node objects (or any object with
        attributes).  Available as variables inside ``%ZM%`` expressions.
    chunk_resolver:
        Callable ``(ref: str, base_dir: Path | None) -> str`` that resolves
        a chunk reference string to its text content.  May be ``None`` if
        the template contains no ``!!``/``??``/``[[ref]]`` tokens.
    """
    facts: dict[str, str]
    groups: dict[str, Any]
    chunk_resolver: Callable[[str, Path | None], str] | None
    base_dir: Path | None = field(default=None)


# ── condition evaluation ──────────────────────────────────────────────────────

# Tokenise a condition string into atoms: operand strings and AND/OR connectors
_COND_TOKEN_RE = re.compile(
    r"""
    (?P<NOT>NOT(?=\s))
    | (?P<AND>AND(?=\s)|\+)
    | (?P<OR>OR(?=\s))
    | (?P<CMP>[^\s]+\s*(?:==|!=|<=|>=|<|>)\s*\S+)
    """,
    re.VERBOSE,
)

_CMP_RE = re.compile(
    r"""^
    (?P<key>[^\s<>=!]+)
    \s*
    (?P<op>==|!=|<=|>=|<|>)
    \s*
    (?P<val>\S+)
    $""",
    re.VERBOSE,
)


def _eval_single(key: str, op: str, raw_val: str, facts: dict[str, str]) -> bool:
    """Evaluate a single comparison against *facts*."""
    use_version = key.endswith("_ver")
    fact_key = key[:-4] if use_version else key
    fact_val = facts.get(fact_key)

    if fact_val is None:
        return False

    if use_version:
        if not _HAS_PACKAGING:
            raise TemplateError(
                "packaging library required for _ver comparisons but is not installed."
            )
        try:
            lhs = _Version(fact_val)
            rhs = _Version(raw_val)
        except Exception as exc:
            raise TemplateError(f"Invalid version string in condition: {exc}") from exc
        ops = {
            "==": lhs == rhs,
            "!=": lhs != rhs,
            "<":  lhs <  rhs,
            ">":  lhs >  rhs,
            "<=": lhs <= rhs,
            ">=": lhs >= rhs,
        }
    else:
        ops = {
            "==": fact_val == raw_val,
            "!=": fact_val != raw_val,
            "<":  fact_val <  raw_val,
            ">":  fact_val >  raw_val,
            "<=": fact_val <= raw_val,
            ">=": fact_val >= raw_val,
        }

    if op not in ops:
        raise TemplateError(f"Unknown comparison operator: {op!r}")
    return ops[op]


def _eval_condition(cond_str: str, facts: dict[str, str]) -> bool:
    """Evaluate a possibly-compound condition string.

    Supports: single comparisons, AND / OR (capitalized), NOT prefix, + (AND).
    Operator precedence: NOT > AND > OR (left-to-right within each level).
    """
    cond_str = cond_str.strip()
    if not cond_str:
        return False

    # Normalise + → AND (with spaces to match token regex)
    cond_str = re.sub(r'\s*\+\s*', ' AND ', cond_str)

    # Split into tokens
    atoms: list[tuple[str, str]] = []  # (kind, text)
    pos = 0
    while pos < len(cond_str):
        # skip whitespace
        m_ws = re.match(r'\s+', cond_str[pos:])
        if m_ws:
            pos += m_ws.end()
            continue
        # try NOT
        m_not = re.match(r'NOT(?=\s|$)', cond_str[pos:])
        if m_not:
            atoms.append(('NOT', 'NOT'))
            pos += m_not.end()
            continue
        # try AND
        m_and = re.match(r'AND(?=\s|$)', cond_str[pos:])
        if m_and:
            atoms.append(('AND', 'AND'))
            pos += m_and.end()
            continue
        # try OR
        m_or = re.match(r'OR(?=\s|$)', cond_str[pos:])
        if m_or:
            atoms.append(('OR', 'OR'))
            pos += m_or.end()
            continue
        # try comparison: key op val
        m_cmp = re.match(r'([^\s]+)\s*(==|!=|<=|>=|<|>)\s*([^\s]+)', cond_str[pos:])
        if m_cmp:
            atoms.append(('CMP', m_cmp.group(0)))
            pos += m_cmp.end()
            continue
        raise TemplateError(
            f"Unrecognised token in condition near {cond_str[pos:pos+20]!r}"
        )

    # Evaluate atoms with NOT > AND > OR precedence
    # Step 1: resolve CMPs and NOTs into boolean list with AND/OR connectors
    # We do a two-pass: first handle NOTs, then AND, then OR
    # Convert to value stream
    values: list[bool | str] = []  # bools and 'AND'/'OR' strings
    i = 0
    while i < len(atoms):
        kind, text = atoms[i]
        if kind == 'NOT':
            # NOT must be followed by a CMP
            i += 1
            if i >= len(atoms) or atoms[i][0] != 'CMP':
                raise TemplateError("NOT must be followed by a comparison.")
            cmp_text = atoms[i][1]
            m = _CMP_RE.match(cmp_text)
            if not m:
                raise TemplateError(f"Invalid comparison: {cmp_text!r}")
            values.append(not _eval_single(m.group('key'), m.group('op'), m.group('val'), facts))
        elif kind == 'CMP':
            m = _CMP_RE.match(text)
            if not m:
                raise TemplateError(f"Invalid comparison: {text!r}")
            values.append(_eval_single(m.group('key'), m.group('op'), m.group('val'), facts))
        elif kind in ('AND', 'OR'):
            values.append(kind)
        i += 1

    if not values:
        return False

    # Step 2: fold AND
    and_folded: list[bool | str] = []
    i = 0
    while i < len(values):
        v = values[i]
        if v == 'AND':
            lhs = and_folded.pop()
            i += 1
            rhs = values[i]
            and_folded.append(bool(lhs) and bool(rhs))
        else:
            and_folded.append(v)
        i += 1

    # Step 3: fold OR
    result = bool(and_folded[0])
    i = 1
    while i < len(and_folded):
        connector = and_folded[i]
        i += 1
        rhs = bool(and_folded[i])
        i += 1
        if connector == 'OR':
            result = result or rhs
        else:
            raise TemplateError(f"Unexpected connector: {connector!r}")

    return result


# ── tokeniser ─────────────────────────────────────────────────────────────────

# Matches lines with template tokens
_LINE_ZO   = re.compile(r'^\s*%ZO%\s+(.+)$')
_LINE_ZIF  = re.compile(r'^\s*%ZIF%\s+(.+)$')
_LINE_ZC   = re.compile(r'^\s*%ZC%\s*$')
_LINE_TRUE = re.compile(r'^\s*!!\s+(.+)$')
_LINE_FALSE = re.compile(r'^\s*\?\?\s+(.+)$')
_LINE_TEXT  = re.compile(r'^\s*%TEXT%\s*$')
_LINE_ZM    = re.compile(r'^\s*%ZM%\s+(.+)$')
_RAW_REF    = re.compile(r'\[\[([^\]]+)\]\]')


# ── renderer ──────────────────────────────────────────────────────────────────

def _resolve_chunk(ref: str, context: TemplateContext) -> str:
    """Resolve a chunk reference string to its text content (raw paste)."""
    ref = ref.strip()
    if context.chunk_resolver is None:
        raise TemplateError(
            f"Cannot resolve chunk ref {ref!r}: no chunk_resolver in context."
        )
    try:
        return context.chunk_resolver(ref, context.base_dir)
    except FileNotFoundError:
        raise TemplateError(f"Chunk not found: {ref!r}")


def _eval_zm(expr: str, context: TemplateContext) -> str:
    """Evaluate a %ZM% expression with restricted builtins."""
    safe_builtins = {
        "len": len,
        "sorted": sorted,
        "list": list,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "range": range,
        "enumerate": enumerate,
        "zip": zip,
        "sum": sum,
        "min": min,
        "max": max,
        "abs": abs,
        "round": round,
        "any": any,
        "all": all,
    }
    eval_globals: dict[str, Any] = {"__builtins__": safe_builtins}
    eval_globals.update(context.groups)
    try:
        result = eval(expr.strip(), eval_globals)  # noqa: S307
    except SyntaxError as exc:
        raise TemplateError(f"Syntax error in %ZM% expression: {exc}") from exc
    except Exception as exc:
        raise TemplateError(f"Error evaluating %ZM% expression: {exc}") from exc
    return str(result)


def _expand_raw_refs(line: str, context: TemplateContext) -> str:
    """Replace all [[ref]] occurrences in a single line with raw chunk content."""
    def replacer(m: re.Match) -> str:
        return _resolve_chunk(m.group(1), context)
    return _RAW_REF.sub(replacer, line)


# Sentinel for parse state
_STATE_ROOT = "root"
_STATE_TRUE = "true"
_STATE_FALSE = "false"
_STATE_TEXT_TRUE = "text_true"
_STATE_TEXT_FALSE = "text_false"


def render_template(
    source: str,
    context: TemplateContext,
) -> str:
    """Render *source* against *context* and return the output string.

    Raises
    ------
    TemplateError
        On any parse or evaluation error.
    """
    lines = source.splitlines(keepends=True)
    output_parts: list[str] = []

    # Stack of frames; each frame is a dict describing the current block:
    #   {
    #     "cond": bool,          # evaluated condition
    #     "has_true": bool,      # have we seen the !! branch yet
    #     "has_false": bool,     # have we seen the ?? branch yet
    #     "active_branch": str,  # "none" | "true" | "false"
    #     "text_lines": list,    # accumulate lines inside %TEXT%
    #     "in_text": bool,       # currently inside a %TEXT% block
    #     "text_for": str,       # "true" | "false"
    #   }
    stack: list[dict] = []

    def _is_active() -> bool:
        """True if all enclosing blocks are in their active branch.

        %ZIF% frames use implicit true-branch semantics: the body of a %ZIF%
        is executed when the condition is true (no explicit !! required).
        %ZO% frames require an explicit !! or ?? branch to be active.
        """
        for frame in stack:
            kind = frame["kind"]
            branch = frame["active_branch"]
            cond = frame["cond"]
            if kind == "zif":
                # Implicit true-branch: active iff condition is met
                # Unless we're in an explicit false branch (??)
                if branch == "false":
                    if cond:
                        return False  # cond true but we're in false branch → skip
                else:
                    if not cond:
                        return False  # cond false → skip
            else:  # kind == "zo"
                if branch == "none":
                    return False
                if branch == "true" and not cond:
                    return False
                if branch == "false" and cond:
                    return False
        return True

    def _current_in_text() -> dict | None:
        if stack and stack[-1]["in_text"]:
            return stack[-1]
        return None

    for lineno, raw_line in enumerate(lines, 1):
        line_stripped = raw_line.rstrip('\n').rstrip('\r')

        # ── inside a %TEXT% block ───────────────────────────────────────────
        frame_in_text = _current_in_text()
        if frame_in_text is not None:
            if _LINE_TEXT.match(line_stripped):
                # Close the text block
                text_content = "".join(frame_in_text["text_lines"])
                for_branch = frame_in_text["text_for"]
                frame_in_text["in_text"] = False
                frame_in_text["text_lines"] = []
                # Was this block for the active branch?
                cond = frame_in_text["cond"]
                if for_branch == "true" and cond and _is_active():
                    output_parts.append(text_content)
                elif for_branch == "false" and not cond and _is_active():
                    output_parts.append(text_content)
            elif _LINE_ZC.match(line_stripped):
                raise TemplateError(
                    f"Line {lineno}: %ZC% found inside an unclosed %TEXT% block."
                )
            else:
                frame_in_text["text_lines"].append(raw_line)
            continue

        # ── %ZO% / %ZIF% ───────────────────────────────────────────────────
        m_zo = _LINE_ZO.match(line_stripped)
        m_zif = _LINE_ZIF.match(line_stripped)
        if m_zo or m_zif:
            m = m_zo or m_zif
            kind = "zo" if m_zo else "zif"
            cond_str = m.group(1)
            cond = _eval_condition(cond_str, context.facts)
            stack.append({
                "kind": kind,
                "cond": cond,
                # %ZIF% starts with implicit "true" active_branch; %ZO% starts "none"
                "active_branch": "true" if kind == "zif" else "none",
                "true_defined": False,  # has !! or first %TEXT% been seen?
                "false_defined": False, # has ?? or second %TEXT% been seen?
                "in_text": False,
                "text_lines": [],
                "text_for": None,
            })
            continue

        # ── %ZC% ───────────────────────────────────────────────────────────
        if _LINE_ZC.match(line_stripped):
            if not stack:
                raise TemplateError(
                    f"Line {lineno}: unexpected %ZC% — no open block."
                )
            frame = stack[-1]
            if frame["in_text"]:
                raise TemplateError(
                    f"Line {lineno}: unclosed %TEXT% block before %ZC%."
                )
            stack.pop()
            continue

        # ── !! true branch ──────────────────────────────────────────────────
        m_true = _LINE_TRUE.match(line_stripped)
        if m_true:
            if not stack:
                raise TemplateError(f"Line {lineno}: !! outside of block.")
            frame = stack[-1]
            frame["active_branch"] = "true"
            frame["true_defined"] = True
            if frame["cond"] and _is_active():
                chunk_text = _resolve_chunk(m_true.group(1), context)
                output_parts.append(chunk_text)
                if not chunk_text.endswith('\n'):
                    output_parts.append('\n')
            continue

        # ── ?? false branch ─────────────────────────────────────────────────
        m_false = _LINE_FALSE.match(line_stripped)
        if m_false:
            if not stack:
                raise TemplateError(f"Line {lineno}: ?? outside of block.")
            frame = stack[-1]
            frame["active_branch"] = "false"
            frame["false_defined"] = True
            if not frame["cond"] and _is_active():
                chunk_text = _resolve_chunk(m_false.group(1), context)
                output_parts.append(chunk_text)
                if not chunk_text.endswith('\n'):
                    output_parts.append('\n')
            continue

        # ── %TEXT% open ─────────────────────────────────────────────────────
        if _LINE_TEXT.match(line_stripped):
            if not stack:
                raise TemplateError(f"Line {lineno}: %TEXT% outside of block.")
            frame = stack[-1]
            # Which branch does this %TEXT% block belong to?
            # Rule: if the true branch is not yet defined → true branch
            #       otherwise → false branch
            if not frame["true_defined"]:
                text_for = "true"
                frame["active_branch"] = "true"
                frame["true_defined"] = True
            else:
                text_for = "false"
                frame["active_branch"] = "false"
                frame["false_defined"] = True
            frame["in_text"] = True
            frame["text_for"] = text_for
            frame["text_lines"] = []
            continue

        # ── %ZM% ────────────────────────────────────────────────────────────
        m_zm = _LINE_ZM.match(line_stripped)
        if m_zm and _is_active():
            result = _eval_zm(m_zm.group(1), context)
            output_parts.append(result + '\n')
            continue
        if m_zm:
            continue  # inactive block — skip

        # ── [[ref]] raw paste ────────────────────────────────────────────────
        if _RAW_REF.search(line_stripped) and _is_active():
            expanded = _expand_raw_refs(line_stripped, context)
            # Preserve the original line ending (e.g. '\n') after expanded content.
            # The [[ref]] occupies a full line so always re-emit the line separator.
            line_ending = raw_line[len(line_stripped):]
            output_parts.append(expanded)
            if line_ending:
                output_parts.append(line_ending)
            continue
        if _RAW_REF.search(line_stripped):
            continue  # inactive — skip

        # ── plain text ───────────────────────────────────────────────────────
        if _is_active():
            output_parts.append(raw_line)

    # End-of-file checks
    if stack:
        depth = len(stack)
        raise TemplateError(
            f"unclosed block(s) at end of template ({depth} block(s) not closed)."
        )
    for frame in stack:  # pragma: no cover  (unreachable — stack is empty)
        if frame["in_text"]:
            raise TemplateError("Unclosed %TEXT% block at end of template.")

    return "".join(output_parts)
