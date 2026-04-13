"""TDD: zhar.utils.facts — independent key-value store."""
from pathlib import Path
import pytest
from zhar.utils.facts import Facts


@pytest.fixture
def facts_path(tmp_path) -> Path:
    return tmp_path / "facts.json"


@pytest.fixture
def facts(facts_path) -> Facts:
    return Facts(facts_path)


# ── loading ───────────────────────────────────────────────────────────────────

class TestLoad:
    def test_empty_when_file_missing(self, facts):
        assert facts.all() == {}

    def test_loads_existing_file(self, facts_path):
        import orjson
        facts_path.write_bytes(orjson.dumps({"lang": "python", "runner": "pytest"}))
        f = Facts(facts_path)
        assert f.get("lang") == "python"

    def test_path_stored(self, facts, facts_path):
        assert facts.path == facts_path


# ── get / set / unset ─────────────────────────────────────────────────────────

class TestGetSetUnset:
    def test_get_missing_key_returns_none(self, facts):
        assert facts.get("nonexistent") is None

    def test_get_missing_key_returns_default(self, facts):
        assert facts.get("nonexistent", "fallback") == "fallback"

    def test_set_then_get(self, facts):
        facts.set("runner", "pytest")
        assert facts.get("runner") == "pytest"

    def test_set_overwrites_existing(self, facts):
        facts.set("runner", "pytest")
        facts.set("runner", "unittest")
        assert facts.get("runner") == "unittest"

    def test_unset_removes_key(self, facts):
        facts.set("runner", "pytest")
        facts.unset("runner")
        assert facts.get("runner") is None

    def test_unset_missing_key_is_noop(self, facts):
        facts.unset("never_existed")  # should not raise

    def test_all_returns_copy(self, facts):
        facts.set("a", "1")
        d = facts.all()
        d["a"] = "mutated"
        assert facts.get("a") == "1"


# ── persistence ───────────────────────────────────────────────────────────────

class TestPersistence:
    def test_set_writes_to_disk(self, facts, facts_path):
        facts.set("env", "production")
        assert facts_path.exists()

    def test_new_instance_sees_persisted_data(self, facts, facts_path):
        facts.set("db", "sqlite")
        f2 = Facts(facts_path)
        assert f2.get("db") == "sqlite"

    def test_unset_persists_removal(self, facts, facts_path):
        facts.set("temp", "x")
        facts.unset("temp")
        f2 = Facts(facts_path)
        assert f2.get("temp") is None

    def test_file_is_valid_json(self, facts, facts_path):
        import orjson
        facts.set("k", "v")
        data = orjson.loads(facts_path.read_bytes())
        assert data["k"] == "v"


# ── values are always strings ─────────────────────────────────────────────────

class TestStringValues:
    def test_set_accepts_string(self, facts):
        facts.set("flag", "true")
        assert facts.get("flag") == "true"

    def test_set_rejects_non_string(self, facts):
        with pytest.raises(TypeError):
            facts.set("count", 42)  # type: ignore[arg-type]

    def test_set_rejects_none(self, facts):
        with pytest.raises(TypeError):
            facts.set("key", None)  # type: ignore[arg-type]
