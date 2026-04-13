"""TDD: zhar.mem.scan — source file marker parser."""
from pathlib import Path
import pytest
from zhar.mem.scan import MarkerHit, scan_file, scan_tree, sync_sources
from zhar.mem.store import MemStore
from zhar.mem.node import make_node


# ── MarkerHit ─────────────────────────────────────────────────────────────────

class TestMarkerHit:
    def test_fields_accessible(self):
        hit = MarkerHit(path=Path("src/foo.py"), line=42, node_id="a1b2")
        assert hit.path == Path("src/foo.py")
        assert hit.line == 42
        assert hit.node_id == "a1b2"


# ── scan_file ─────────────────────────────────────────────────────────────────

class TestScanFile:
    def test_returns_empty_for_no_markers(self, tmp_path):
        f = tmp_path / "clean.py"
        f.write_text("def foo():\n    pass\n")
        assert scan_file(f) == []

    def test_finds_single_marker(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("def auth():  # %ZHAR:a1b2%\n    pass\n")
        hits = scan_file(f)
        assert len(hits) == 1
        assert hits[0].node_id == "a1b2"
        assert hits[0].line == 1

    def test_finds_multiple_markers_in_one_file(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text(
            "# %ZHAR:a1b2%\n"
            "def foo(): pass\n"
            "# %ZHAR:c3d4%\n"
        )
        hits = scan_file(f)
        assert len(hits) == 2
        assert {h.node_id for h in hits} == {"a1b2", "c3d4"}

    def test_marker_can_appear_anywhere_on_line(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("x = 1  # some comment %ZHAR:ffff% trailing\n")
        hits = scan_file(f)
        assert hits[0].node_id == "ffff"

    def test_returns_correct_line_numbers(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("line1\nline2\n# %ZHAR:ab12%\nline4\n")
        hits = scan_file(f)
        assert hits[0].line == 3

    def test_missing_file_returns_empty(self, tmp_path):
        assert scan_file(tmp_path / "ghost.py") == []

    def test_marker_pattern_is_case_sensitive(self, tmp_path):
        f = tmp_path / "code.py"
        # lowercase zhar should NOT match
        f.write_text("# %zhar:a1b2%\n")
        assert scan_file(f) == []


# ── scan_tree ─────────────────────────────────────────────────────────────────

class TestScanTree:
    def _make_tree(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.py").write_text("# %ZHAR:a1b2%\n")
        (tmp_path / "src" / "b.py").write_text("no markers\n")
        (tmp_path / "src" / "c.ts").write_text("// %ZHAR:c3d4%\n")
        (tmp_path / "README.md").write_text("# %ZHAR:e5f6%\n")
        return tmp_path

    def test_finds_markers_across_default_extensions(self, tmp_path):
        self._make_tree(tmp_path)
        hits = scan_tree(tmp_path)
        ids = {h.node_id for h in hits}
        assert "a1b2" in ids

    def test_respects_extensions_filter(self, tmp_path):
        self._make_tree(tmp_path)
        hits = scan_tree(tmp_path, extensions={".ts"})
        ids = {h.node_id for h in hits}
        assert "c3d4" in ids
        assert "a1b2" not in ids

    def test_empty_tree_returns_empty(self, tmp_path):
        assert scan_tree(tmp_path) == []

    def test_skips_hidden_directories(self, tmp_path):
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "secret.py").write_text("# %ZHAR:9999%\n")
        hits = scan_tree(tmp_path)
        assert not any(h.node_id == "9999" for h in hits)


# ── sync_sources ──────────────────────────────────────────────────────────────

class TestSyncSources:
    def test_updates_source_on_matching_node(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")
        node = make_node(group="project_dna", node_type="core_requirement",
                         summary="Some req")
        store.save(node)

        hits = [MarkerHit(path=Path("src/foo.py"), line=10, node_id=node.id)]
        report = sync_sources(store, hits)

        updated = store.get(node.id)
        assert updated.source == f"src/foo.py::10::%ZHAR:{node.id}%"
        assert report["updated"] == 1

    def test_skips_unknown_node_ids(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")
        hits = [MarkerHit(path=Path("src/x.py"), line=1, node_id="zzzz")]
        report = sync_sources(store, hits)
        assert report["skipped"] == 1
        assert report["updated"] == 0

    def test_report_counts_correctly(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")
        n1 = make_node(group="project_dna", node_type="core_requirement", summary="R1")
        n2 = make_node(group="project_dna", node_type="core_requirement", summary="R2")
        store.save(n1)
        store.save(n2)

        hits = [
            MarkerHit(path=Path("a.py"), line=1, node_id=n1.id),
            MarkerHit(path=Path("b.py"), line=2, node_id=n2.id),
            MarkerHit(path=Path("c.py"), line=3, node_id="zzzz"),
        ]
        report = sync_sources(store, hits)
        assert report["updated"] == 2
        assert report["skipped"] == 1

    def test_sync_sources_strips_redundant_file_change_path_metadata(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")
        node = make_node(
            group="code_history",
            node_type="file_change",
            summary="stack bucket manager",
            metadata={
                "path": "src/zhar/stack/bucket.py",
                "significance": "feature",
            },
        )
        store.save(node)

        hits = [MarkerHit(path=Path("src/zhar/stack/bucket.py"), line=16, node_id=node.id)]
        sync_sources(store, hits)

        updated = store.get(node.id)
        assert updated.source == f"src/zhar/stack/bucket.py::16::%ZHAR:{node.id}%"
        assert "path" not in updated.metadata
