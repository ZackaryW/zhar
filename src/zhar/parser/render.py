"""Renderer for the %%ZHAR.*%% template language.

Public API
----------
ParseContext   dataclass — facts, memory groups, chunk resolver, base_dir
ParseError     exception — any parse or evaluation error
render(source, context) -> str

Token reference
---------------
// <text>                    comment line — stripped
%%ZHAR.FACT(expr)%%          AND condition (multiple FACT lines AND together)
%%ZHAR.ORFACT(expr)%%        OR a new AND-group against accumulated FACTs
%%ZHAR.MEMCOND(expr)%%       condition evaluated against memory group lengths
%%ZHAR.IF%%                  open conditional block
%%ZHAR.IFTRUE%%              true branch
%%ZHAR.IFFALSE%%             false branch
%%ZHAR.IFEND%%               close innermost IF
%%ZHAR.RTEXT_START%%         raw inline text block — open
%%ZHAR.RTEXT_END%%           raw inline text block — close
%%ZHAR.RCHUNK(path)%%        insert file from bucket; verbatim, no re-parse
%%ZHAR.RSKILL(name)%%        insert skill from any repo's skills/ folder
%%ZHAR.RSKILL(repo:name)%%   insert skill from specific repo's skills/ folder
%%ZHAR.MEM(expr)%%           eval expr against memory groups, emit result
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from zhar.parser.cond import CondError, eval_condition_groups, eval_expr


# ── public exceptions ─────────────────────────────────────────────────────────

class ParseError(Exception):
    """Raised on any template parse or evaluation error."""


# ── context ───────────────────────────────────────────────────────────────────

@dataclass
class ParseContext:
    """All inputs available during template rendering.

    Attributes
    ----------
    facts:
        Flat string KV store (from ``Facts.all()``).
    groups:
        Dict of group name → list of Node objects, used by MEM/MEMCOND.
    chunk_resolver:
        Callable ``(ref, base_dir) -> str`` resolving a chunk ref to text.
        May be ``None`` when the template contains no RCHUNK/RSKILL tokens.
    base_dir:
        Optional base directory forwarded to chunk_resolver.
    """
    facts: dict[str, str]
    groups: dict[str, Any]
    chunk_resolver: Callable[[str, Path | None], str] | None
    base_dir: Path | None = field(default=None)
    expand_skills: bool = field(default=False)
    """When True, %%ZHAR.RSKILL%% tokens are resolved and inlined.
    When False (default), they are emitted verbatim so that a later
    ``zhar agent get`` call can resolve them against the live workspace."""


# Keep the old name as an alias so callers that import TemplateContext still work.
TemplateContext = ParseContext


# ── token regex ───────────────────────────────────────────────────────────────

# Greedy arg match (.+) handles nested parens like len(group_name)
_TOKEN_RE = re.compile(r"%%ZHAR\.([A-Z_]+)(?:\((.+)\))?%%")
_COMMENT_RE = re.compile(r"^\s*//")


# ── safe builtins for MEM eval ────────────────────────────────────────────────

_SAFE_BUILTINS: dict[str, Any] = {
    "len": len, "sorted": sorted, "list": list, "str": str,
    "int": int, "float": float, "bool": bool, "range": range,
    "sum": sum, "min": min, "max": max, "abs": abs, "round": round,
    "any": any, "all": all, "enumerate": enumerate, "zip": zip,
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _resolve_chunk(ref: str, context: ParseContext) -> str:
    """Resolve a chunk/skill reference to its text content (verbatim, no re-parse)."""
    ref = ref.strip()
    if context.chunk_resolver is None:
        raise ParseError(f"Cannot resolve chunk {ref!r}: no chunk_resolver in context.")
    try:
        return context.chunk_resolver(ref, context.base_dir)
    except FileNotFoundError:
        raise ParseError(f"chunk not found: {ref!r}")


def _eval_mem(expr: str, context: ParseContext) -> str:
    """Evaluate a MEM expression with restricted builtins."""
    globs: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}
    globs.update(context.groups)
    try:
        return str(eval(expr.strip(), globs))  # noqa: S307
    except SyntaxError as exc:
        raise ParseError(f"Syntax error in MEM expression: {exc}") from exc
    except Exception as exc:
        raise ParseError(f"Error in MEM expression: {exc}") from exc


def _memcond_facts(groups: dict[str, Any]) -> dict[str, str]:
    """Build a synthetic facts dict from group sizes for MEMCOND evaluation.

    Exposes ``<group_name>_count`` as a string-integer for each group.
    """
    return {f"{name}_count": str(len(nodes)) for name, nodes in groups.items()}


# ── frame type for IF stack ───────────────────────────────────────────────────

@dataclass
class _Frame:
    """State for one open IF block."""
    cond: bool             # evaluated condition
    branch: str = "none"  # "none" | "true" | "false"

    def is_active(self) -> bool:
        """Return True when the current branch should produce output."""
        if self.branch == "none":
            return True   # before IFTRUE — forward to detect nesting errors
        return (self.branch == "true") == self.cond


# ── line processor states ─────────────────────────────────────────────────────

_IN_RTEXT = "rtext"
_IN_NONE = "none"


# ── renderer ──────────────────────────────────────────────────────────────────

def render(source: str, context: ParseContext) -> str:
    """Render *source* against *context* and return the output string.

    Raises
    ------
    ParseError
        On any structural or evaluation error.
    """
    lines = source.splitlines(keepends=True)
    out: list[str] = []

    # Stack of IF frames (innermost last)
    stack: list[_Frame] = []

    # Pending FACT/ORFACT/MEMCOND groups: list-of-AND-groups
    # Each AND-group is a list of expr strings
    pending_groups: list[list[str]] = []
    current_and: list[str] = []  # current (innermost) AND-group being built

    # Inline text accumulation
    rtext_lines: list[str] = []
    in_rtext: bool = False
    rtext_is_conditional: bool = False  # True when RTEXT was preceded by FACT
    rtext_condition: bool = True        # evaluated condition for the RTEXT block

    def _all_active() -> bool:
        """True when every IF frame is on its active branch."""
        return all(f.is_active() for f in stack)

    def _flush_and_group() -> None:
        """Move the current AND-group into pending_groups if non-empty."""
        nonlocal current_and
        if current_and:
            pending_groups.append(current_and)
            current_and = []

    def _consume_condition() -> bool:
        """Evaluate and clear the pending condition groups.

        Returns ``True`` (always-true) when no FACT/ORFACT/MEMCOND preceded.
        """
        nonlocal pending_groups, current_and
        _flush_and_group()
        if not pending_groups:
            return True
        result = eval_condition_groups(pending_groups, context.facts)
        pending_groups = []
        return result

    for lineno, raw_line in enumerate(lines, 1):
        stripped = raw_line.rstrip("\n").rstrip("\r")

        # ── inside RTEXT block ────────────────────────────────────────────────
        if in_rtext:
            m = _TOKEN_RE.fullmatch(stripped.strip())
            if m and m.group(1) == "RTEXT_END":
                in_rtext = False
                content = "".join(rtext_lines)
                rtext_lines = []
                if not rtext_is_conditional or rtext_condition:
                    if _all_active():
                        out.append(content)
            else:
                rtext_lines.append(raw_line)
            continue

        # ── comment stripping ─────────────────────────────────────────────────
        if _COMMENT_RE.match(stripped):
            continue

        # ── scan for %%ZHAR.*%% tokens on this line ───────────────────────────
        # We only process lines that are solely a token (no surrounding text).
        # Mixed lines (text + token) are treated as plain text.
        m = _TOKEN_RE.fullmatch(stripped.strip())
        if not m:
            # Plain text line
            if _all_active():
                out.append(raw_line)
            continue

        tag = m.group(1)
        arg = (m.group(2) or "").strip()

        # ── FACT ─────────────────────────────────────────────────────────────
        if tag == "FACT":
            current_and.append(arg)
            continue

        # ── ORFACT ───────────────────────────────────────────────────────────
        if tag == "ORFACT":
            _flush_and_group()       # close current AND-group
            current_and = [arg]      # start new AND-group for this ORFACT
            continue

        # ── MEMCOND ───────────────────────────────────────────────────────────
        if tag == "MEMCOND":
            mem_facts = _memcond_facts(context.groups)
            try:
                result = eval_expr(arg, mem_facts)
            except CondError as exc:
                raise ParseError(f"Line {lineno}: MEMCOND error: {exc}") from exc
            # Store the pre-evaluated boolean directly as a sentinel fact.
            # Use a unique key that cannot collide with user facts.
            _key = f"__memcond_{lineno}__"
            context.facts[_key] = "yes" if result else "no"
            current_and.append(f"{_key} == yes")
            continue

        # ── IF ────────────────────────────────────────────────────────────────
        if tag == "IF":
            cond = _consume_condition() if _all_active() else False
            stack.append(_Frame(cond=cond))
            continue

        # ── IFTRUE ───────────────────────────────────────────────────────────
        if tag == "IFTRUE":
            if not stack:
                raise ParseError(f"Line {lineno}: %%ZHAR.IFTRUE%% outside of IF block.")
            stack[-1].branch = "true"
            continue

        # ── IFFALSE ──────────────────────────────────────────────────────────
        if tag == "IFFALSE":
            if not stack:
                raise ParseError(f"Line {lineno}: %%ZHAR.IFFALSE%% outside of IF block.")
            stack[-1].branch = "false"
            continue

        # ── IFEND ────────────────────────────────────────────────────────────
        if tag == "IFEND":
            if not stack:
                raise ParseError(f"Line {lineno}: unexpected %%ZHAR.IFEND%% — no open IF.")
            stack.pop()
            continue

        # ── RTEXT_START ───────────────────────────────────────────────────────
        if tag == "RTEXT_START":
            cond = _consume_condition()
            in_rtext = True
            rtext_lines = []
            rtext_is_conditional = bool(
                pending_groups or current_and
                # already consumed above; check if condition was pending at all
            )
            # Re-evaluate: condition is in `cond`; mark as conditional if there
            # were pending groups before consume
            rtext_is_conditional = True   # always check condition flag
            rtext_condition = cond if _all_active() else False
            continue

        # ── RTEXT_END outside block ───────────────────────────────────────────
        if tag == "RTEXT_END":
            raise ParseError(f"Line {lineno}: %%ZHAR.RTEXT_END%% without matching RTEXT_START.")

        # ── RCHUNK ───────────────────────────────────────────────────────────
        if tag == "RCHUNK":
            cond = _consume_condition()
            if cond and _all_active():
                content = _resolve_chunk(arg, context)
                out.append(content)
                if not content.endswith("\n"):
                    out.append("\n")
            continue

        # ── RSKILL ───────────────────────────────────────────────────────────
        if tag == "RSKILL":
            cond = _consume_condition()
            if not (cond and _all_active()):
                # Condition false or inactive branch — always suppress
                continue
            if context.expand_skills:
                # Eager mode (skill-in-skill): resolve and inline the content
                content = _resolve_chunk(arg, context)
                out.append(content)
                if not content.endswith("\n"):
                    out.append("\n")
            else:
                # Lazy mode (agent/instruction/hook referencing a skill):
                # emit the token verbatim so runtime `agent get` can resolve it
                out.append(f"%%ZHAR.RSKILL({arg})%%\n")
            continue

        # ── MEM ──────────────────────────────────────────────────────────────
        if tag == "MEM":
            if _all_active():
                out.append(_eval_mem(arg, context) + "\n")
            continue

        raise ParseError(f"Line {lineno}: unknown token %%ZHAR.{tag}%%.")

    # ── end-of-file checks ────────────────────────────────────────────────────
    if in_rtext:
        raise ParseError("Unclosed %%ZHAR.RTEXT_START%% block at end of template.")
    if stack:
        raise ParseError(
            f"unclosed IF block(s) at end of template ({len(stack)} block(s) not closed)."
        )

    return "".join(out)


# Keep old name alias so stack/sync.py still works without changes
render_template = render
