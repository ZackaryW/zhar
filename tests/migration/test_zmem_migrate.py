"""TDD: zmem JSON migration into zhar memory."""

from pathlib import Path

import orjson
from click.testing import CliRunner

from zhar.cli import cli
from zhar.mem.store import MemStore


def _write_zmem_graph(zmem_root: Path) -> None:
    """Write a minimal zmem graph.json fixture for migration tests."""
    zmem_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "0.3",
        "nodes": [
            {
                "id": "0d33",
                "type": "core_goal",
                "tags": ["memory", "agents"],
                "status": "active",
                "source": ".zmem/memory/0d33.md",
                "created_at": "2026-04-07T20:03:17Z",
                "updated_at": "2026-04-07T20:04:26Z",
                "expires_at": None,
                "metadata": {},
                "custom": {},
            },
            {
                "id": "2294",
                "type": "architecture",
                "tags": ["graph", "providers"],
                "status": "active",
                "source": ".zmem/memory/2294.md",
                "created_at": "2026-04-07T20:03:17Z",
                "updated_at": "2026-04-07T20:04:26Z",
                "expires_at": None,
                "metadata": {"agent": "copilot"},
                "custom": {},
            },
            {
                "id": "07e1",
                "type": "current_focus",
                "tags": [],
                "status": "active",
                "source": "",
                "created_at": "2026-04-11T19:30:33Z",
                "updated_at": "2026-04-11T19:30:33Z",
                "expires_at": None,
                "metadata": {"agent": "copilot"},
                "custom": {"summary": "Align instructions with verify behavior"},
            },
        ],
        "edges": [],
    }
    (zmem_root / "graph.json").write_bytes(orjson.dumps(payload))


class TestMigrateCommand:
    """Verify graph.json-only zmem migration behavior."""

    def test_migrate_imports_json_nodes_into_zhar_and_creates_notes(self, tmp_path):
        runner = CliRunner()
        zhar_root = tmp_path / ".zhar"
        zmem_root = tmp_path / ".zmem"
        _write_zmem_graph(zmem_root)

        init = runner.invoke(cli, ["--root", str(zhar_root), "init"])
        assert init.exit_code == 0, init.output

        result = runner.invoke(cli, ["--root", str(zhar_root), "migrate", str(zmem_root)])

        assert result.exit_code == 0, result.output
        assert "Migrated" in result.output

        store = MemStore(zhar_root)
        nodes = store.query(__import__("zhar.mem.query", fromlist=["Query"]).Query())
        assert any(node.group == "project_dna" and node.node_type == "core_goal" for node in nodes)
        assert any(node.group == "decision_trail" and node.node_type == "decision" for node in nodes)
        assert any(node.group == "notes" and node.node_type == "note" for node in nodes)

    def test_migrate_preserves_legacy_zmem_id_when_available(self, tmp_path):
        runner = CliRunner()
        zhar_root = tmp_path / ".zhar"
        zmem_root = tmp_path / ".zmem"
        _write_zmem_graph(zmem_root)

        runner.invoke(cli, ["--root", str(zhar_root), "init"])
        result = runner.invoke(cli, ["--root", str(zhar_root), "migrate", str(zmem_root)])
        assert result.exit_code == 0, result.output

        store = MemStore(zhar_root)
        migrated = store.get("0d33")
        assert migrated is not None
        assert migrated.id == "0d33"

    def test_migrate_converts_task_state_into_attached_note_context(self, tmp_path):
        runner = CliRunner()
        zhar_root = tmp_path / ".zhar"
        zmem_root = tmp_path / ".zmem"
        _write_zmem_graph(zmem_root)

        runner.invoke(cli, ["--root", str(zhar_root), "init"])
        result = runner.invoke(cli, ["--root", str(zhar_root), "migrate", str(zmem_root)])
        assert result.exit_code == 0, result.output

        store = MemStore(zhar_root)
        nodes = store.query(__import__("zhar.mem.query", fromlist=["Query"]).Query(groups=["notes"]))
        assert any("current_focus" in (node.content or "") for node in nodes)