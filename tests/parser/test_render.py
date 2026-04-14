"""Integration tests for src/zhar/parser/render.py

Full grammar:

  // comment line                        stripped, never emitted

  %%ZHAR.FACT(expr)%%                    condition (AND-group; multiple FACT AND together)
  %%ZHAR.ORFACT(expr)%%                  OR a new AND-group against accumulated FACTs
  %%ZHAR.MEMCOND(expr)%%                 condition evaluated against memory groups

  %%ZHAR.IF%%                            open conditional block
  %%ZHAR.IFTRUE%%                        true branch inside IF
  %%ZHAR.IFFALSE%%                       false branch inside IF
  %%ZHAR.IFEND%%                         close innermost IF

  %%ZHAR.RTEXT_START%%                   inline raw-text block open
  ...text...
  %%ZHAR.RTEXT_END%%                     inline raw-text block close

  %%ZHAR.RCHUNK(path)%%                  insert chunk file from bucket repos
  %%ZHAR.RSKILL(name)%%                  insert skill from any repo's skills/ folder
  %%ZHAR.RSKILL(repo:name)%%             insert skill from specific repo's skills/ folder

  %%ZHAR.MEM(expr)%%                     eval expr against memory groups, emit result
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from zhar.parser.render import ParseContext, ParseError, render


# ── helpers ───────────────────────────────────────────────────────────────────

def ctx(**facts: str) -> ParseContext:
    return ParseContext(facts=facts, groups={}, chunk_resolver=None)


def ctx_chunks(chunks: dict[str, str], **facts: str) -> ParseContext:
    def _resolve(ref: str, base_dir: Path | None = None) -> str:
        if ref not in chunks:
            raise FileNotFoundError(ref)
        return chunks[ref]
    return ParseContext(facts=facts, groups={}, chunk_resolver=_resolve)


def ctx_mem(groups: dict, **facts: str) -> ParseContext:
    return ParseContext(facts=facts, groups=groups, chunk_resolver=None)


# ── passthrough ───────────────────────────────────────────────────────────────

class TestPassthrough:
    def test_plain_text_unchanged(self):
        assert render("hello world\n", ctx()) == "hello world\n"

    def test_empty_string(self):
        assert render("", ctx()) == ""

    def test_multiline_no_tokens(self):
        src = "line1\nline2\nline3\n"
        assert render(src, ctx()) == src


# ── comment stripping ─────────────────────────────────────────────────────────

class TestComments:
    def test_comment_line_stripped(self):
        src = "before\n// this is a comment\nafter\n"
        assert render(src, ctx()) == "before\nafter\n"

    def test_indented_comment_stripped(self):
        assert render("  // also a comment\ntext\n", ctx()) == "text\n"

    def test_non_comment_double_slash_preserved(self):
        # Only lines STARTING with // are stripped
        src = "https://example.com\n"
        assert render(src, ctx()) == "https://example.com\n"

    def test_multiple_comments(self):
        src = "// c1\nkeep\n// c2\n"
        assert render(src, ctx()) == "keep\n"


# ── RTEXT_START / RTEXT_END standalone ───────────────────────────────────────

class TestRText:
    def test_rtext_emitted(self):
        src = "%%ZHAR.RTEXT_START%%\nhello\n%%ZHAR.RTEXT_END%%\n"
        assert render(src, ctx()) == "hello\n"

    def test_rtext_multiline(self):
        src = "%%ZHAR.RTEXT_START%%\nline1\nline2\n%%ZHAR.RTEXT_END%%\n"
        out = render(src, ctx())
        assert "line1" in out and "line2" in out

    def test_rtext_unclosed_raises(self):
        with pytest.raises(ParseError, match="RTEXT"):
            render("%%ZHAR.RTEXT_START%%\nhello\n", ctx())


# ── RCHUNK standalone ─────────────────────────────────────────────────────────

class TestRChunk:
    def test_rchunk_inserts_content(self):
        c = ctx_chunks({"header.md": "# Title\n"})
        assert render("%%ZHAR.RCHUNK(header.md)%%\n", c) == "# Title\n"

    def test_rchunk_missing_raises(self):
        with pytest.raises(ParseError, match="chunk"):
            render("%%ZHAR.RCHUNK(missing.md)%%\n", ctx())

    def test_rchunk_no_resolver_raises(self):
        with pytest.raises(ParseError):
            render("%%ZHAR.RCHUNK(file.md)%%\n", ctx())

    def test_rchunk_content_not_re_parsed(self):
        """Chunk content is inserted verbatim — template tokens inside are not re-evaluated."""
        c = ctx_chunks({"raw.md": "%%ZHAR.FACT(x==1)%%\n%%ZHAR.RCHUNK(other.md)%%\n"})
        out = render("%%ZHAR.RCHUNK(raw.md)%%\n", c)
        assert "%%ZHAR.FACT" in out


# ── FACT + standalone content (no IF/IFEND) ───────────────────────────────────

class TestFactStandalone:
    def test_fact_true_rchunk(self):
        c = ctx_chunks({"y.md": "YES\n"}, flag="true")
        src = "%%ZHAR.FACT(flag == true)%%\n%%ZHAR.RCHUNK(y.md)%%\n"
        assert "YES" in render(src, c)

    def test_fact_false_rchunk_suppressed(self):
        c = ctx_chunks({"y.md": "YES\n"}, flag="false")
        src = "%%ZHAR.FACT(flag == true)%%\n%%ZHAR.RCHUNK(y.md)%%\n"
        assert "YES" not in render(src, c)

    def test_fact_true_rtext(self):
        c = ctx(flag="true")
        src = "%%ZHAR.FACT(flag == true)%%\n%%ZHAR.RTEXT_START%%\nhello\n%%ZHAR.RTEXT_END%%\n"
        assert "hello" in render(src, c)

    def test_fact_false_rtext_suppressed(self):
        c = ctx(flag="false")
        src = "%%ZHAR.FACT(flag == true)%%\n%%ZHAR.RTEXT_START%%\nhello\n%%ZHAR.RTEXT_END%%\n"
        assert "hello" not in render(src, c)

    def test_fact_consumed_after_content(self):
        """After a FACT+content pair, subsequent plain text is always emitted."""
        c = ctx_chunks({"y.md": "YES\n"}, flag="false")
        src = (
            "%%ZHAR.FACT(flag == true)%%\n"
            "%%ZHAR.RCHUNK(y.md)%%\n"
            "always visible\n"
        )
        out = render(src, c)
        assert "YES" not in out
        assert "always visible" in out

    def test_multiple_fact_lines_and(self):
        c = ctx_chunks({"y.md": "Y\n"}, a="1", b="2")
        src = (
            "%%ZHAR.FACT(a == 1)%%\n"
            "%%ZHAR.FACT(b == 2)%%\n"
            "%%ZHAR.RCHUNK(y.md)%%\n"
        )
        assert "Y" in render(src, c)

    def test_multiple_fact_lines_one_false(self):
        c = ctx_chunks({"y.md": "Y\n"}, a="1", b="9")
        src = (
            "%%ZHAR.FACT(a == 1)%%\n"
            "%%ZHAR.FACT(b == 2)%%\n"
            "%%ZHAR.RCHUNK(y.md)%%\n"
        )
        assert "Y" not in render(src, c)

    def test_orfact_or_logic(self):
        c = ctx_chunks({"y.md": "Y\n"}, lang="ruby")
        src = (
            "%%ZHAR.FACT(lang == python)%%\n"
            "%%ZHAR.ORFACT(lang == ruby)%%\n"
            "%%ZHAR.RCHUNK(y.md)%%\n"
        )
        assert "Y" in render(src, c)

    def test_orfact_both_false(self):
        c = ctx_chunks({"y.md": "Y\n"}, lang="go")
        src = (
            "%%ZHAR.FACT(lang == python)%%\n"
            "%%ZHAR.ORFACT(lang == ruby)%%\n"
            "%%ZHAR.RCHUNK(y.md)%%\n"
        )
        assert "Y" not in render(src, c)


# ── IF / IFTRUE / IFFALSE / IFEND blocks ─────────────────────────────────────

class TestIfBlock:
    def test_if_true_branch(self):
        c = ctx_chunks({"y.md": "YES\n"}, flag="true")
        src = textwrap.dedent("""\
            %%ZHAR.FACT(flag == true)%%
            %%ZHAR.IF%%
            %%ZHAR.IFTRUE%%
            %%ZHAR.RCHUNK(y.md)%%
            %%ZHAR.IFEND%%
        """)
        assert "YES" in render(src, c)

    def test_if_false_branch(self):
        c = ctx_chunks({"n.md": "NO\n"}, flag="false")
        src = textwrap.dedent("""\
            %%ZHAR.FACT(flag == true)%%
            %%ZHAR.IF%%
            %%ZHAR.IFTRUE%%
            %%ZHAR.RCHUNK(other.md)%%
            %%ZHAR.IFFALSE%%
            %%ZHAR.RCHUNK(n.md)%%
            %%ZHAR.IFEND%%
        """)
        assert "NO" in render(src, c)

    def test_if_true_branch_not_emitted_when_false(self):
        c = ctx_chunks({"y.md": "YES\n", "n.md": "NO\n"}, flag="false")
        src = textwrap.dedent("""\
            %%ZHAR.FACT(flag == true)%%
            %%ZHAR.IF%%
            %%ZHAR.IFTRUE%%
            %%ZHAR.RCHUNK(y.md)%%
            %%ZHAR.IFFALSE%%
            %%ZHAR.RCHUNK(n.md)%%
            %%ZHAR.IFEND%%
        """)
        out = render(src, c)
        assert "YES" not in out
        assert "NO" in out

    def test_if_without_fact_always_true(self):
        """IF with no preceding FACT is always true."""
        c = ctx_chunks({"y.md": "YES\n"})
        src = textwrap.dedent("""\
            %%ZHAR.IF%%
            %%ZHAR.IFTRUE%%
            %%ZHAR.RCHUNK(y.md)%%
            %%ZHAR.IFEND%%
        """)
        assert "YES" in render(src, c)

    def test_if_rtext_true_branch(self):
        c = ctx(flag="true")
        src = textwrap.dedent("""\
            %%ZHAR.FACT(flag == true)%%
            %%ZHAR.IF%%
            %%ZHAR.IFTRUE%%
            %%ZHAR.RTEXT_START%%
            inline true
            %%ZHAR.RTEXT_END%%
            %%ZHAR.IFFALSE%%
            %%ZHAR.RTEXT_START%%
            inline false
            %%ZHAR.RTEXT_END%%
            %%ZHAR.IFEND%%
        """)
        out = render(src, c)
        assert "inline true" in out
        assert "inline false" not in out

    def test_nested_if(self):
        c = ctx_chunks({"y.md": "Y\n", "n.md": "N\n"}, a="true", b="true")
        src = textwrap.dedent("""\
            %%ZHAR.FACT(a == true)%%
            %%ZHAR.IF%%
            %%ZHAR.IFTRUE%%
            %%ZHAR.FACT(b == true)%%
            %%ZHAR.IF%%
            %%ZHAR.IFTRUE%%
            %%ZHAR.RCHUNK(y.md)%%
            %%ZHAR.IFFALSE%%
            %%ZHAR.RCHUNK(n.md)%%
            %%ZHAR.IFEND%%
            %%ZHAR.IFEND%%
        """)
        out = render(src, c)
        assert "Y" in out
        assert "N" not in out

    def test_unclosed_if_raises(self):
        with pytest.raises(ParseError, match="unclosed"):
            render("%%ZHAR.IF%%\n%%ZHAR.IFTRUE%%\n", ctx())

    def test_ifend_without_if_raises(self):
        with pytest.raises(ParseError, match="unexpected"):
            render("%%ZHAR.IFEND%%\n", ctx())


# ── MEM expression ────────────────────────────────────────────────────────────

class TestMem:
    def test_mem_len(self):
        c = ctx_mem({"project_dna": ["a", "b", "c"]})
        out = render("%%ZHAR.MEM(len(project_dna))%%\n", c)
        assert "3" in out

    def test_mem_no_builtins_escape(self):
        c = ctx_mem({})
        with pytest.raises(ParseError):
            render("%%ZHAR.MEM(__import__('os').getcwd())%%\n", c)

    def test_mem_syntax_error_raises(self):
        c = ctx_mem({})
        with pytest.raises(ParseError):
            render("%%ZHAR.MEM(()%%\n", c)


# ── MEMCOND ───────────────────────────────────────────────────────────────────

class TestMemCond:
    def test_memcond_evaluates_against_groups(self):
        """MEMCOND(group_name != empty) — treat group node count as string fact."""
        c_with = ctx_mem({"project_dna": ["node1"]})
        c_without = ctx_mem({"project_dna": []})
        src = (
            "%%ZHAR.MEMCOND(project_dna_count > 0)%%\n"
            "%%ZHAR.RTEXT_START%%\nhas nodes\n%%ZHAR.RTEXT_END%%\n"
        )
        assert "has nodes" in render(src, c_with)
        assert "has nodes" not in render(src, c_without)


# ── RSKILL lazy vs eager expansion ───────────────────────────────────────────

class TestRSkill:
    def test_rskill_verbatim_by_default(self):
        """Without expand_skills, RSKILL token is left in the output verbatim."""
        c = ctx()   # no chunk_resolver — would error if it tried to resolve
        src = "%%ZHAR.RSKILL(my-skill)%%\n"
        out = render(src, c)
        assert "%%ZHAR.RSKILL(my-skill)%%" in out

    def test_rskill_expanded_when_flag_set(self):
        """With expand_skills=True, RSKILL token is resolved and its content inlined."""
        def resolver(ref: str, base_dir=None) -> str:
            if ref == "my-skill":
                return "skill content\n"
            raise FileNotFoundError(ref)
        c = ParseContext(facts={}, groups={}, chunk_resolver=resolver, expand_skills=True)
        out = render("%%ZHAR.RSKILL(my-skill)%%\n", c)
        assert "skill content" in out
        assert "%%ZHAR.RSKILL" not in out

    def test_rskill_verbatim_does_not_require_resolver(self):
        """Lazy RSKILL must not call the resolver at all."""
        c = ParseContext(facts={}, groups={}, chunk_resolver=None, expand_skills=False)
        out = render("%%ZHAR.RSKILL(anything)%%\n", c)
        assert "%%ZHAR.RSKILL(anything)%%" in out

    def test_rchunk_always_expanded(self):
        """RCHUNK is always expanded regardless of expand_skills."""
        c = ctx_chunks({"f.md": "chunk\n"})
        out = render("%%ZHAR.RCHUNK(f.md)%%\n", c)
        assert "chunk" in out
        assert "%%ZHAR.RCHUNK" not in out

    def test_rskill_verbatim_inside_true_if_branch(self):
        """RSKILL is still left verbatim (not suppressed) in an active IF branch."""
        c = ParseContext(facts={"x": "1"}, groups={}, chunk_resolver=None, expand_skills=False)
        src = (
            "%%ZHAR.FACT(x == 1)%%\n"
            "%%ZHAR.IF%%\n"
            "%%ZHAR.IFTRUE%%\n"
            "%%ZHAR.RSKILL(cool-skill)%%\n"
            "%%ZHAR.IFEND%%\n"
        )
        out = render(src, c)
        assert "%%ZHAR.RSKILL(cool-skill)%%" in out

    def test_rskill_suppressed_inside_false_if_branch(self):
        """RSKILL inside a false branch is suppressed even in verbatim mode."""
        c = ParseContext(facts={"x": "0"}, groups={}, chunk_resolver=None, expand_skills=False)
        src = (
            "%%ZHAR.FACT(x == 1)%%\n"
            "%%ZHAR.IF%%\n"
            "%%ZHAR.IFTRUE%%\n"
            "%%ZHAR.RSKILL(cool-skill)%%\n"
            "%%ZHAR.IFEND%%\n"
        )
        out = render(src, c)
        assert "%%ZHAR.RSKILL(cool-skill)%%" not in out

    def test_rskill_fact_condition_respected_in_verbatim_mode(self):
        """A FACT-guarded RSKILL: token emitted when condition true, absent when false."""
        def _ctx(flag: str):
            return ParseContext(facts={"flag": flag}, groups={}, chunk_resolver=None, expand_skills=False)
        src = "%%ZHAR.FACT(flag == yes)%%\n%%ZHAR.RSKILL(s)%%\n"
        assert "%%ZHAR.RSKILL(s)%%" in render(src, _ctx("yes"))
        assert "%%ZHAR.RSKILL(s)%%" not in render(src, _ctx("no"))


# ── error cases ───────────────────────────────────────────────────────────────

class TestErrors:
    def test_unknown_token_raises(self):
        with pytest.raises(ParseError):
            render("%%ZHAR.UNKNOWN(x)%%\n", ctx())

    def test_iftrue_outside_if_raises(self):
        with pytest.raises(ParseError):
            render("%%ZHAR.IFTRUE%%\n", ctx())

    def test_iffalse_outside_if_raises(self):
        with pytest.raises(ParseError):
            render("%%ZHAR.IFFALSE%%\n", ctx())
