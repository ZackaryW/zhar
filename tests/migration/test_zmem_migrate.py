"""Integration tests for zmem JSON migration into zhar memory."""

from pathlib import Path

import orjson
import pytest
from click.testing import CliRunner

from zhar.cli import cli
from zhar.mem.node import Node
from zhar.mem.query import Query
from zhar.mem.store import MemStore
from zhar.migration.zmem import ZmemMigrationReport, migrate_zmem_json


_FIXTURE_ZMEM = Path(__file__).resolve().parents[2] / "test_src" / "from_zmem"


@pytest.fixture
def migrated_store(tmp_path) -> tuple[MemStore, ZmemMigrationReport]:
    """Return a MemStore populated by migrating the copied zmem fixture."""
    store = MemStore(tmp_path / ".zhar")
    report = migrate_zmem_json(store, _FIXTURE_ZMEM)
    return store, report


def _extract_json_record(note: Node) -> dict[str, object]:
    """Parse the original zmem JSON record stored in a migration note."""
    assert note.content is not None
    lines = note.content.splitlines()
    start = lines.index("```json") + 1
    end = lines.index("```", start)
    payload = "\n".join(lines[start:end])
    return orjson.loads(payload)


class TestMigrateZmemCommand:
    """Verify the CLI entrypoint for zmem migration."""

    def test_cli_migrate_zmem_imports_fixture(self, tmp_path):
        runner = CliRunner()
        zhar_root = tmp_path / ".zhar"

        init = runner.invoke(cli, ["--root", str(zhar_root), "init"])
        assert init.exit_code == 0, init.output

        result = runner.invoke(cli, ["--root", str(zhar_root), "migrate", "zmem", str(_FIXTURE_ZMEM)])

        assert result.exit_code == 0, result.output
        assert "Migrated 7 node(s), created 8 note(s), reused 6 legacy id(s)." in result.output


class TestMigrateZmemIntegration:
    """Verify graph.json-only zmem migration behavior against a copied zmem fixture."""

    def test_report_and_group_counts_match_expected_fixture_shape(self, migrated_store):
        store, report = migrated_store
        stats = store.stats()

        assert report == ZmemMigrationReport(migrated_nodes=7, created_notes=8, preserved_ids=6)
        assert stats["project_dna"]["total"] == 6
        assert stats["decision_trail"]["total"] == 1
        assert stats["notes"]["total"] == 8

    def test_direct_nodes_are_mapped_with_expected_groups_types_and_ids(self, migrated_store):
        store, _ = migrated_store

        goal = store.get("c27b")
        requirement = store.get("d566")
        architecture = store.get("9ffb")

        assert goal is not None
        assert goal.group == "project_dna"
        assert goal.node_type == "core_goal"
        assert goal.status == "active"
        assert goal.tags == ["pvtro", "slang", "flutter"]
        assert goal.custom["migration_source"] == "zmem-json"
        assert goal.custom["zmem_type"] == "core_goal"

        assert requirement is not None
        assert requirement.group == "project_dna"
        assert requirement.node_type == "core_requirement"
        assert requirement.metadata["agent"] == "migration"
        assert requirement.content is not None
        assert "original_id: d566" in requirement.content
        assert "original_source: .zmem/memory/d566.md" in requirement.content

        assert architecture is not None
        assert architecture.group == "decision_trail"
        assert architecture.node_type == "decision"
        assert architecture.status == "active"
        assert architecture.custom["zmem_type"] == "architecture"

    def test_notes_capture_original_json_records_for_direct_and_task_state_nodes(self, migrated_store):
        store, _ = migrated_store
        goal_notes = store.attached_notes("c27b")
        task_state_host = next(
            node
            for node in store.query(Query(groups=["project_dna"], node_types=["product_context"]))
            if node.summary == "Migrated zmem task-state context"
        )
        task_state_notes = store.attached_notes(task_state_host.id)
        all_notes = store.query(Query(groups=["notes"]))

        goal_payload = _extract_json_record(goal_notes[0])
        task_state_payloads = [_extract_json_record(note) for note in task_state_notes]

        assert len(goal_notes) == 1
        assert goal_payload["id"] == "c27b"
        assert goal_payload["type"] == "core_goal"
        assert goal_notes[0].metadata["target_ids"] == "c27b"

        assert len(task_state_notes) == 2
        assert {payload["type"] for payload in task_state_payloads} == {"current_focus", "next_step"}
        assert {payload["status"] for payload in task_state_payloads} == {"archived", "active"}
        assert len(all_notes) == 8

    def test_task_state_host_is_synthetic_and_non_legacy(self, migrated_store):
        store, _ = migrated_store

        host = next(
            node
            for node in store.query(Query(groups=["project_dna"], node_types=["product_context"]))
            if node.summary == "Migrated zmem task-state context"
        )

        assert host.id not in {"b037", "395a"}
        assert host.metadata["agent"] == "migration"
        assert host.content is not None
        assert "Synthetic host for task-state notes." in host.content