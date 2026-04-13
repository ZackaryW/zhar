"""Tests for src/zhar/harness/stack/template.py

Grammar recap
-------------
%ZO% <cond>           open conditional block
  !! <chunk_ref>      true-branch file ref  (exactly one path, no eval)
  %TEXT%              true-branch inline text open
  ...text...
  %TEXT%              true-branch inline text close
  ?? <chunk_ref>      false-branch file ref
  %TEXT% ... %TEXT%   false-branch inline text
%ZC%                  close block

%ZIF% <cond>          nested condition header (opens scope within %ZO% or another %ZIF%)
  !! <chunk_ref> | %TEXT%..%TEXT%
  ?? <chunk_ref> | %TEXT%..%TEXT%
%ZC%

[[<ref>]]             raw paste — insert file content verbatim, no eval
%ZM% <expr>           Python eval against memory context (group names as node lists)

Condition grammar
-----------------
  <operand> <op> <value>
    op   : == | != | < | > | <= | >=
    value: bare word or quoted string
  Compound via AND / OR / NOT (must be UPPER, space-separated)
  + as shorthand for AND

_ver suffix on key triggers packaging.version.Version comparison.
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from zhar.harness.stack.template import (
    TemplateContext,
    TemplateError,
    render_template,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def ctx(**facts: str) -> TemplateContext:
    """Build a TemplateContext with given facts and no memory / chunk resolver."""
    return TemplateContext(facts=facts, groups={}, chunk_resolver=None)


def ctx_with_resolver(chunks: dict[str, str], **facts: str) -> TemplateContext:
    """TemplateContext that resolves chunk refs from an in-memory dict."""
    def resolver(ref: str, base_dir: Path | None = None) -> str:
        if ref not in chunks:
            raise FileNotFoundError(ref)
        return chunks[ref]
    return TemplateContext(facts=facts, groups={}, chunk_resolver=resolver)


# ── TemplateContext construction ──────────────────────────────────────────────

class TestTemplateContext:
    def test_facts_accessible(self):
        c = ctx(lang="python", ver="3.12")
        assert c.facts["lang"] == "python"
        assert c.facts["ver"] == "3.12"

    def test_groups_accessible(self):
        c = TemplateContext(facts={}, groups={"g": ["node1"]}, chunk_resolver=None)
        assert c.groups["g"] == ["node1"]


# ── simple passthrough (no tokens) ───────────────────────────────────────────

class TestPassthrough:
    def test_plain_text_unchanged(self):
        assert render_template("hello world\n", ctx()) == "hello world\n"

    def test_empty_string(self):
        assert render_template("", ctx()) == ""

    def test_multi_line_no_tokens(self):
        src = "line1\nline2\nline3\n"
        assert render_template(src, ctx()) == src


# ── [[ref]] raw paste ─────────────────────────────────────────────────────────

class TestRawRef:
    def test_ref_is_replaced_by_chunk_content(self):
        c = ctx_with_resolver({"header.md": "# Title\n"})
        out = render_template("[[header.md]]\n", c)
        assert out == "# Title\n\n"

    def test_ref_inline_with_surrounding_text(self):
        c = ctx_with_resolver({"snippet.txt": "SNIP"})
        out = render_template("before [[snippet.txt]] after\n", c)
        assert "SNIP" in out

    def test_missing_ref_raises(self):
        c = ctx()
        with pytest.raises(TemplateError, match="chunk"):
            render_template("[[missing.md]]", c)

    def test_ref_no_recursive_template_eval(self):
        """Content of a [[ref]] must NOT be re-parsed for template tokens."""
        c = ctx_with_resolver({"raw.md": "%ZO% x == y\n!! other.md\n%ZC%\n"})
        out = render_template("[[raw.md]]", c)
        # The literal %ZO% etc. should appear verbatim — not evaluated
        assert "%ZO%" in out


# ── %ZO% / %ZC% conditional blocks ───────────────────────────────────────────

class TestConditionalBlock:
    def test_true_branch_file_ref(self):
        c = ctx_with_resolver({"yes.md": "YES\n"}, flag="true")
        src = textwrap.dedent("""\
            %ZO% flag == true
            !! yes.md
            %ZC%
        """)
        assert "YES" in render_template(src, c)

    def test_false_branch_not_rendered_when_true(self):
        c = ctx_with_resolver({"yes.md": "YES\n", "no.md": "NO\n"}, flag="true")
        src = textwrap.dedent("""\
            %ZO% flag == true
            !! yes.md
            ?? no.md
            %ZC%
        """)
        out = render_template(src, c)
        assert "YES" in out
        assert "NO" not in out

    def test_false_branch_rendered_when_condition_false(self):
        c = ctx_with_resolver({"yes.md": "YES\n", "no.md": "NO\n"}, flag="false")
        src = textwrap.dedent("""\
            %ZO% flag == true
            !! yes.md
            ?? no.md
            %ZC%
        """)
        out = render_template(src, c)
        assert "NO" in out
        assert "YES" not in out

    def test_missing_condition_fact_treated_as_false(self):
        c = ctx_with_resolver({"no.md": "NO\n"})
        src = textwrap.dedent("""\
            %ZO% undeclared == true
            !! nonexistent.md
            ?? no.md
            %ZC%
        """)
        assert "NO" in render_template(src, c)

    def test_no_false_branch_renders_nothing_when_false(self):
        c = ctx()
        src = textwrap.dedent("""\
            %ZO% x == true
            !! whatever.md
            %ZC%
        """)
        assert render_template(src, c).strip() == ""


# ── %TEXT% inline text branches ──────────────────────────────────────────────

class TestTextBlock:
    def test_text_block_as_true_branch(self):
        c = ctx(flag="true")
        src = textwrap.dedent("""\
            %ZO% flag == true
            %TEXT%
            inline content here
            %TEXT%
            %ZC%
        """)
        out = render_template(src, c)
        assert "inline content here" in out

    def test_text_block_not_rendered_when_false(self):
        c = ctx(flag="false")
        src = textwrap.dedent("""\
            %ZO% flag == true
            %TEXT%
            should not appear
            %TEXT%
            %ZC%
        """)
        assert "should not appear" not in render_template(src, c)

    def test_text_block_as_false_branch(self):
        c = ctx(flag="false")
        src = textwrap.dedent("""\
            %ZO% flag == true
            !! some.md
            %TEXT%
            fallback text
            %TEXT%
            %ZC%
        """)
        assert "fallback text" in render_template(src, c)

    def test_text_block_multiline(self):
        c = ctx(x="1")
        src = textwrap.dedent("""\
            %ZO% x == 1
            %TEXT%
            line one
            line two
            line three
            %TEXT%
            %ZC%
        """)
        out = render_template(src, c)
        assert "line one" in out
        assert "line two" in out
        assert "line three" in out


# ── compound conditions ───────────────────────────────────────────────────────

class TestCompoundConditions:
    def test_and_both_true(self):
        c = ctx_with_resolver({"y.md": "Y\n"}, a="true", b="true")
        src = textwrap.dedent("""\
            %ZO% a == true AND b == true
            !! y.md
            %ZC%
        """)
        assert "Y" in render_template(src, c)

    def test_and_one_false(self):
        c = ctx_with_resolver({"y.md": "Y\n"}, a="true", b="false")
        src = textwrap.dedent("""\
            %ZO% a == true AND b == true
            !! y.md
            %ZC%
        """)
        assert "Y" not in render_template(src, c)

    def test_or_one_true(self):
        c = ctx_with_resolver({"y.md": "Y\n"}, a="false", b="true")
        src = textwrap.dedent("""\
            %ZO% a == true OR b == true
            !! y.md
            %ZC%
        """)
        assert "Y" in render_template(src, c)

    def test_not_negation(self):
        c = ctx_with_resolver({"y.md": "Y\n"}, flag="false")
        src = textwrap.dedent("""\
            %ZO% NOT flag == true
            !! y.md
            %ZC%
        """)
        assert "Y" in render_template(src, c)

    def test_plus_as_and_shorthand(self):
        """+ in branch refs is AND shorthand; test it in condition expression too."""
        c = ctx_with_resolver({"y.md": "Y\n"}, a="1", b="1")
        src = textwrap.dedent("""\
            %ZO% a == 1 + b == 1
            !! y.md
            %ZC%
        """)
        assert "Y" in render_template(src, c)

    def test_chained_and_or(self):
        c = ctx_with_resolver({"y.md": "Y\n"}, a="true", b="false", cc="true")
        src = textwrap.dedent("""\
            %ZO% a == true AND b == false OR cc == true
            !! y.md
            %ZC%
        """)
        # (a==true AND b==false) OR cc==true  => True AND True => True (short-circuit)
        assert "Y" in render_template(src, c)


# ── _ver suffix version comparison ───────────────────────────────────────────

class TestVerSuffix:
    def test_ver_gt(self):
        c = ctx_with_resolver({"y.md": "Y\n"}, python_ver="3.12")
        src = textwrap.dedent("""\
            %ZO% python_ver_ver >= 3.11
            !! y.md
            %ZC%
        """)
        assert "Y" in render_template(src, c)

    def test_ver_lt_false(self):
        c = ctx_with_resolver({"y.md": "Y\n"}, python_ver="3.10")
        src = textwrap.dedent("""\
            %ZO% python_ver_ver >= 3.12
            !! y.md
            %ZC%
        """)
        assert "Y" not in render_template(src, c)

    def test_ver_eq(self):
        c = ctx_with_resolver({"y.md": "Y\n"}, mylib_ver="1.2.3")
        src = textwrap.dedent("""\
            %ZO% mylib_ver_ver == 1.2.3
            !! y.md
            %ZC%
        """)
        assert "Y" in render_template(src, c)


# ── %ZIF% nested conditions ───────────────────────────────────────────────────

class TestNestedZif:
    def test_single_zif_true_branch(self):
        c = ctx_with_resolver({"y.md": "Y\n"}, a="true")
        src = textwrap.dedent("""\
            %ZIF% a == true
            !! y.md
            %ZC%
        """)
        assert "Y" in render_template(src, c)

    def test_nested_zif_all_true(self):
        c = ctx_with_resolver({"y.md": "Y\n"}, a="true", b="true", cc="true")
        src = textwrap.dedent("""\
            %ZIF% a == true
            %ZIF% b == true
            %ZIF% cc == true
            !! y.md
            %ZC%
            %ZC%
            %ZC%
        """)
        assert "Y" in render_template(src, c)

    def test_nested_zif_middle_false(self):
        c = ctx_with_resolver({"y.md": "Y\n", "n.md": "N\n"}, a="true", b="false", cc="true")
        src = textwrap.dedent("""\
            %ZIF% a == true
            %ZIF% b == true
            %ZIF% cc == true
            !! y.md
            %ZC%
            ?? n.md
            %ZC%
            %ZC%
        """)
        out = render_template(src, c)
        assert "N" in out
        assert "Y" not in out

    def test_zif_false_branch_text(self):
        c = ctx(a="false")
        src = textwrap.dedent("""\
            %ZIF% a == true
            %TEXT%
            should not show
            %TEXT%
            %TEXT%
            fallback
            %TEXT%
            %ZC%
        """)
        assert "fallback" in render_template(src, c)
        assert "should not show" not in render_template(src, c)


# ── %ZM% memory eval ─────────────────────────────────────────────────────────

class TestMemoryEval:
    def test_zm_returns_string_from_expr(self):
        c = TemplateContext(
            facts={},
            groups={"project_dna": [{"summary": "use orjson"}]},
            chunk_resolver=None,
        )
        src = "%ZM% len(project_dna)\n"
        out = render_template(src, c)
        assert "1" in out

    def test_zm_accesses_multiple_groups(self):
        c = TemplateContext(
            facts={},
            groups={
                "project_dna": ["a", "b"],
                "decision_trail": ["x"],
            },
            chunk_resolver=None,
        )
        src = "%ZM% len(project_dna) + len(decision_trail)\n"
        out = render_template(src, c)
        assert "3" in out

    def test_zm_no_builtins_escape(self):
        """__import__ must not be available inside %ZM% eval."""
        c = TemplateContext(facts={}, groups={}, chunk_resolver=None)
        with pytest.raises((TemplateError, NameError)):
            render_template("%ZM% __import__('os').getcwd()\n", c)

    def test_zm_syntax_error_raises_template_error(self):
        c = TemplateContext(facts={}, groups={}, chunk_resolver=None)
        with pytest.raises(TemplateError):
            render_template("%ZM% (\n", c)


# ── error cases ───────────────────────────────────────────────────────────────

class TestErrors:
    def test_unclosed_zo_raises(self):
        with pytest.raises(TemplateError, match="unclosed"):
            render_template("%ZO% x == 1\n!! f.md\n", ctx())

    def test_unmatched_zc_raises(self):
        with pytest.raises(TemplateError, match="unexpected"):
            render_template("%ZC%\n", ctx())

    def test_unclosed_text_block_raises(self):
        with pytest.raises(TemplateError, match="%TEXT%"):
            render_template("%ZO% x == 1\n%TEXT%\nhello\n%ZC%\n", ctx(x="1"))

    def test_invalid_condition_op_raises(self):
        with pytest.raises(TemplateError):
            render_template("%ZO% x ??? 1\n!! f.md\n%ZC%\n", ctx())
