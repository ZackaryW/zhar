"""TDD: zhar.harness.installer — agent file writer."""
from types import SimpleNamespace
from pathlib import Path
import pytest
from zhar.harness.installer import install_agent_file, uninstall_agent_file
from zhar.mem.store import MemStore
from zhar.mem.node import make_node
from zhar.utils.facts import Facts


@pytest.fixture
def store(tmp_path) -> MemStore:
    s = MemStore(tmp_path / ".zhar")
    s.save(make_node(group="project_dna", node_type="core_goal",
                     summary="Build zhar", metadata={"agent": "claude"}))
    s.save(make_node(group="project_dna", node_type="core_requirement",
                     summary="Use orjson", metadata={"priority": "high"}))
    s.save(make_node(group="decision_trail", node_type="adr",
                     summary="Group-clustered storage",
                     content="## Status\naccepted"))
    return s


@pytest.fixture
def facts(tmp_path) -> Facts:
    f = Facts(tmp_path / ".zhar" / "facts.json")
    f.set("primary_language", "python")
    f.set("test_runner", "pytest")
    f.set("is_python_project", "uv")
    return f


@pytest.fixture
def out_path(tmp_path) -> Path:
    return tmp_path / ".github" / "agents" / "zhar.agent.md"


# ── install ───────────────────────────────────────────────────────────────────

class TestInstall:
    def test_creates_output_file(self, store, facts, out_path):
        install_agent_file(store, facts, out_path)
        assert out_path.exists()

    def test_creates_parent_dirs(self, store, facts, out_path):
        install_agent_file(store, facts, out_path)
        assert out_path.parent.exists()

    def test_file_contains_memory_snapshot(self, store, facts, out_path):
        install_agent_file(store, facts, out_path)
        content = out_path.read_text()
        assert "Build zhar" in content
        assert "Use orjson" in content

    def test_file_contains_facts(self, store, facts, out_path):
        install_agent_file(store, facts, out_path)
        content = out_path.read_text()
        assert "python" in content
        assert "pytest" in content

    def test_file_contains_zhar_header(self, store, facts, out_path):
        install_agent_file(store, facts, out_path)
        content = out_path.read_text()
        assert "zhar" in content.lower()

    def test_overwrites_existing_file(self, store, facts, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("old content")
        install_agent_file(store, facts, out_path)
        assert "old content" not in out_path.read_text()

    def test_install_without_facts_still_works(self, store, out_path):
        install_agent_file(store, None, out_path)
        assert out_path.exists()
        assert "Build zhar" in out_path.read_text()

    def test_returns_path(self, store, facts, out_path):
        result = install_agent_file(store, facts, out_path)
        assert result == out_path

    def test_install_includes_runtime_context_when_available(self, tmp_path, facts, out_path, monkeypatch):
        from zhar.mem.groups import code_history as code_history_group

        outputs = {
            ("rev-parse", "--show-toplevel"): "D:/repo\n",
            ("status", "--short", "--", "src/zhar/harness/stack/template.py"): " M src/zhar/harness/stack/template.py\n",
            ("diff", "--stat", "--", "src/zhar/harness/stack/template.py"): " src/zhar/harness/stack/template.py | 2 +-\n 1 file changed, 1 insertion(+), 1 deletion(-)\n",
            ("log", "--oneline", "-n", "5", "--", "src/zhar/harness/stack/template.py"): "abc1234 template parser\n",
        }

        def fake_run(args, cwd, capture_output, text, check):
            return SimpleNamespace(returncode=0, stdout=outputs.get(tuple(args[1:]), ""))

        monkeypatch.setattr(code_history_group.subprocess, "run", fake_run)

        store = MemStore(tmp_path / ".zhar")
        store.save(make_node(
            group="code_history",
            node_type="file_change",
            summary="template parser",
            source="src/zhar/harness/stack/template.py::26::%ZHAR:ffff%",
            metadata={"significance": "feature"},
        ))

        install_agent_file(store, facts, out_path)
        content = out_path.read_text()

        assert "Runtime context" in content
        assert "git_companion" in content
        assert "Diff stat:" in content


# ── uninstall ─────────────────────────────────────────────────────────────────

class TestUninstall:
    def test_removes_existing_file(self, store, facts, out_path):
        install_agent_file(store, facts, out_path)
        uninstall_agent_file(out_path)
        assert not out_path.exists()

    def test_noop_when_file_missing(self, out_path):
        uninstall_agent_file(out_path)  # should not raise

    def test_returns_true_when_removed(self, store, facts, out_path):
        install_agent_file(store, facts, out_path)
        assert uninstall_agent_file(out_path) is True

    def test_returns_false_when_missing(self, out_path):
        assert uninstall_agent_file(out_path) is False
