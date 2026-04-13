"""zhar stack template language — parser and renderer."""
# %ZHAR:da1b% %ZHAR:f3a6% %ZHAR:1782%
# %ZHAR:5969% %ZHAR:5dc4%
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

try:
    from packaging.version import Version as _Version

    _HAS_PACKAGING = True
except ImportError:  # pragma: no cover
    _HAS_PACKAGING = False


class TemplateError(Exception):
    """Raised on any template parse or evaluation error."""


@dataclass
class TemplateContext:
    """All inputs available during template rendering."""

    facts: dict[str, str]
    groups: dict[str, Any]
    chunk_resolver: Callable[[str, Path | None], str] | None
    base_dir: Path | None = field(default=None)


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
            "<": lhs < rhs,
            ">": lhs > rhs,
            "<=": lhs <= rhs,
            ">=": lhs >= rhs,
        }
    else:
        ops = {
            "==": fact_val == raw_val,
            "!=": fact_val != raw_val,
            "<": fact_val < raw_val,
            ">": fact_val > raw_val,
            "<=": fact_val <= raw_val,
            ">=": fact_val >= raw_val,
        }

    if op not in ops:
        raise TemplateError(f"Unknown comparison operator: {op!r}")
    return ops[op]


def _eval_condition(cond_str: str, facts: dict[str, str]) -> bool:
    """Evaluate a possibly-compound condition string."""
    cond_str = cond_str.strip()
    if not cond_str:
        return False

    cond_str = re.sub(r"\s*\+\s*", " AND ", cond_str)

    atoms: list[tuple[str, str]] = []
    pos = 0
    while pos < len(cond_str):
        m_ws = re.match(r"\s+", cond_str[pos:])
        if m_ws:
            pos += m_ws.end()
            continue
        m_not = re.match(r"NOT(?=\s|$)", cond_str[pos:])
        if m_not:
            atoms.append(("NOT", "NOT"))
            pos += m_not.end()
            continue
        m_and = re.match(r"AND(?=\s|$)", cond_str[pos:])
        if m_and:
            atoms.append(("AND", "AND"))
            pos += m_and.end()
            continue
        m_or = re.match(r"OR(?=\s|$)", cond_str[pos:])
        if m_or:
            atoms.append(("OR", "OR"))
            pos += m_or.end()
            continue
        m_cmp = re.match(r"([^\s]+)\s*(==|!=|<=|>=|<|>)\s*([^\s]+)", cond_str[pos:])
        if m_cmp:
            atoms.append(("CMP", m_cmp.group(0)))
            pos += m_cmp.end()
            continue
        raise TemplateError(
            f"Unrecognised token in condition near {cond_str[pos:pos+20]!r}"
        )

    values: list[bool | str] = []
    i = 0
    while i < len(atoms):
        kind, text = atoms[i]
        if kind == "NOT":
            i += 1
            if i >= len(atoms) or atoms[i][0] != "CMP":
                raise TemplateError("NOT must be followed by a comparison.")
            m = _CMP_RE.match(atoms[i][1])
            if not m:
                raise TemplateError(f"Invalid comparison: {atoms[i][1]!r}")
            values.append(not _eval_single(m.group("key"), m.group("op"), m.group("val"), facts))
        elif kind == "CMP":
            m = _CMP_RE.match(text)
            if not m:
                raise TemplateError(f"Invalid comparison: {text!r}")
            values.append(_eval_single(m.group("key"), m.group("op"), m.group("val"), facts))
        elif kind in ("AND", "OR"):
            values.append(kind)
        i += 1

    if not values:
        return False

    and_folded: list[bool | str] = []
    i = 0
    while i < len(values):
        value = values[i]
        if value == "AND":
            lhs = and_folded.pop()
            i += 1
            rhs = values[i]
            and_folded.append(bool(lhs) and bool(rhs))
        else:
            and_folded.append(value)
        i += 1

    result = bool(and_folded[0])
    i = 1
    while i < len(and_folded):
        connector = and_folded[i]
        i += 1
        rhs = bool(and_folded[i])
        i += 1
        if connector == "OR":
            result = result or rhs
        else:
            raise TemplateError(f"Unexpected connector: {connector!r}")

    return result


_LINE_ZO = re.compile(r"^\s*%ZO%\s+(.+)$")
_LINE_ZIF = re.compile(r"^\s*%ZIF%\s+(.+)$")
_LINE_ZC = re.compile(r"^\s*%ZC%\s*$")
_LINE_TRUE = re.compile(r"^\s*!!\s+(.+)$")
_LINE_FALSE = re.compile(r"^\s*\?\?\s+(.+)$")
_LINE_TEXT = re.compile(r"^\s*%TEXT%\s*$")
_LINE_ZM = re.compile(r"^\s*%ZM%\s+(.+)$")
_RAW_REF = re.compile(r"\[\[([^\]]+)\]\]")


def _resolve_chunk(ref: str, context: TemplateContext) -> str:
    """Resolve a chunk reference string to its raw text content."""
    ref = ref.strip()
    if context.chunk_resolver is None:
        raise TemplateError(
            f"Cannot resolve chunk ref {ref!r}: no chunk_resolver in context."
        )
    try:
        return context.chunk_resolver(ref, context.base_dir)
    except FileNotFoundError as exc:
        raise TemplateError(f"Chunk not found: {ref!r}") from exc


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
    """Replace all ``[[ref]]`` occurrences in a single line."""
    def replacer(match: re.Match) -> str:
        return _resolve_chunk(match.group(1), context)

    return _RAW_REF.sub(replacer, line)


_STATE_TEXT_TRUE = "text_true"
_STATE_TEXT_FALSE = "text_false"


def render_template(source: str, context: TemplateContext) -> str:
    """Render *source* against *context* and return the output string."""
    lines = source.splitlines(keepends=True)
    output_parts: list[str] = []
    stack: list[dict[str, Any]] = []

    def _is_active() -> bool:
        """Return ``True`` if every enclosing block is on its active branch."""
        for frame in stack:
            kind = frame["kind"]
            branch = frame["active_branch"]
            cond = frame["cond"]
            if kind == "zif":
                if branch == "false":
                    if cond:
                        return False
                else:
                    if not cond:
                        return False
            else:
                if branch == "none":
                    return False
                if branch == "true" and not cond:
                    return False
                if branch == "false" and cond:
                    return False
        return True

    def _current_in_text() -> dict[str, Any] | None:
        """Return the current text frame when a %TEXT% block is open."""
        if stack and stack[-1]["in_text"]:
            return stack[-1]
        return None

    for lineno, raw_line in enumerate(lines, 1):
        line_stripped = raw_line.rstrip("\n").rstrip("\r")

        frame_in_text = _current_in_text()
        if frame_in_text is not None:
            if _LINE_TEXT.match(line_stripped):
                text_content = "".join(frame_in_text["text_lines"])
                for_branch = frame_in_text["text_for"]
                frame_in_text["in_text"] = False
                frame_in_text["text_lines"] = []
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

        m_zo = _LINE_ZO.match(line_stripped)
        m_zif = _LINE_ZIF.match(line_stripped)
        if m_zo or m_zif:
            match = m_zo or m_zif
            kind = "zo" if m_zo else "zif"
            stack.append({
                "kind": kind,
                "cond": _eval_condition(match.group(1), context.facts),
                "active_branch": "true" if kind == "zif" else "none",
                "true_defined": False,
                "false_defined": False,
                "in_text": False,
                "text_lines": [],
                "text_for": None,
            })
            continue

        if _LINE_ZC.match(line_stripped):
            if not stack:
                raise TemplateError(f"Line {lineno}: unexpected %ZC% — no open block.")
            frame = stack[-1]
            if frame["in_text"]:
                raise TemplateError(f"Line {lineno}: unclosed %TEXT% block before %ZC%.")
            stack.pop()
            continue

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
                if not chunk_text.endswith("\n"):
                    output_parts.append("\n")
            continue

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
                if not chunk_text.endswith("\n"):
                    output_parts.append("\n")
            continue

        if _LINE_TEXT.match(line_stripped):
            if not stack:
                raise TemplateError(f"Line {lineno}: %TEXT% outside of block.")
            frame = stack[-1]
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

        m_zm = _LINE_ZM.match(line_stripped)
        if m_zm and _is_active():
            output_parts.append(_eval_zm(m_zm.group(1), context) + "\n")
            continue
        if m_zm:
            continue

        if _RAW_REF.search(line_stripped) and _is_active():
            expanded = _expand_raw_refs(line_stripped, context)
            line_ending = raw_line[len(line_stripped):]
            output_parts.append(expanded)
            if line_ending:
                output_parts.append(line_ending)
            continue
        if _RAW_REF.search(line_stripped):
            continue

        if _is_active():
            output_parts.append(raw_line)

    if stack:
        depth = len(stack)
        raise TemplateError(
            f"unclosed block(s) at end of template ({depth} block(s) not closed)."
        )
    for frame in stack:  # pragma: no cover
        if frame["in_text"]:
            raise TemplateError("Unclosed %TEXT% block at end of template.")

    return "".join(output_parts)