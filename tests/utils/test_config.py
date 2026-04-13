"""TDD: zhar.utils.config — project config resolution."""
from pathlib import Path
import pytest
from zhar.utils.config import ZharConfig, find_zhar_root, load_config


# ── find_zhar_root ────────────────────────────────────────────────────────────

class TestFindZharRoot:
    def test_finds_existing_zhar_dir(self, tmp_path):
        zhar = tmp_path / ".zhar"
        zhar.mkdir()
        found = find_zhar_root(tmp_path)
        assert found == zhar

    def test_finds_zhar_dir_in_parent(self, tmp_path):
        zhar = tmp_path / ".zhar"
        zhar.mkdir()
        subdir = tmp_path / "src" / "deep"
        subdir.mkdir(parents=True)
        found = find_zhar_root(subdir)
        assert found == zhar

    def test_returns_none_when_not_found(self, tmp_path):
        assert find_zhar_root(tmp_path) is None

    def test_stops_at_filesystem_root(self, tmp_path):
        # Should not raise, just return None
        result = find_zhar_root(Path("/"))
        assert result is None


# ── ZharConfig defaults ───────────────────────────────────────────────────────

class TestZharConfigDefaults:
    def test_default_store_dir(self, tmp_path):
        cfg = ZharConfig(root=tmp_path)
        assert cfg.store_dir == tmp_path / "mem"

    def test_default_cfg_dir(self, tmp_path):
        cfg = ZharConfig(root=tmp_path)
        assert cfg.cfg_dir == tmp_path / "cfg"

    def test_root_stored(self, tmp_path):
        cfg = ZharConfig(root=tmp_path)
        assert cfg.root == tmp_path


# ── load_config ───────────────────────────────────────────────────────────────

class TestLoadConfig:
    def test_returns_default_config_when_no_toml(self, tmp_path):
        cfg = load_config(tmp_path)
        assert isinstance(cfg, ZharConfig)
        assert cfg.root == tmp_path

    def test_reads_store_dir_from_toml(self, tmp_path):
        toml = tmp_path / "config.toml"
        toml.write_text('store_dir = "data"\n', encoding="utf-8")
        cfg = load_config(tmp_path)
        assert cfg.store_dir == tmp_path / "data"

    def test_relative_paths_resolved_against_root(self, tmp_path):
        toml = tmp_path / "config.toml"
        toml.write_text('store_dir = "custom/mem"\n', encoding="utf-8")
        cfg = load_config(tmp_path)
        assert cfg.store_dir == tmp_path / "custom" / "mem"
