"""TDD: zhar.utils.cache — MtimeFileCache."""
import time
from pathlib import Path
import pytest
from zhar.utils.cache import MtimeFileCache


@pytest.fixture
def cache():
    return MtimeFileCache()


@pytest.fixture
def text_file(tmp_path) -> Path:
    f = tmp_path / "node.json"
    f.write_text('{"id": "a1b2"}', encoding="utf-8")
    return f


class TestReadText:
    def test_reads_file_content(self, cache, text_file):
        assert cache.read_text(text_file) == '{"id": "a1b2"}'

    def test_returns_empty_for_missing_file(self, cache, tmp_path):
        assert cache.read_text(tmp_path / "missing.json") == ""

    def test_second_read_returns_same_content(self, cache, text_file):
        first = cache.read_text(text_file)
        second = cache.read_text(text_file)
        assert first == second

    def test_cached_read_does_not_re_read_disk(self, cache, text_file, monkeypatch):
        cache.read_text(text_file)          # prime cache
        # overwrite on disk without changing mtime — cache should return stale value
        original_stat = text_file.stat()
        text_file.write_text('{"id": "changed"}', encoding="utf-8")
        import os
        os.utime(text_file, (original_stat.st_atime, original_stat.st_mtime))
        assert cache.read_text(text_file) == '{"id": "a1b2"}'

    def test_detects_mtime_change(self, cache, text_file):
        cache.read_text(text_file)          # prime cache
        time.sleep(0.01)                    # ensure mtime advances
        text_file.write_text('{"id": "new"}', encoding="utf-8")
        assert cache.read_text(text_file) == '{"id": "new"}'

    def test_missing_file_clears_cache_entry(self, cache, text_file):
        cache.read_text(text_file)          # prime cache
        text_file.unlink()
        assert cache.read_text(text_file) == ""


class TestInvalidate:
    def test_invalidate_forces_re_read(self, cache, text_file):
        cache.read_text(text_file)
        text_file.write_text('{"id": "updated"}', encoding="utf-8")
        cache.invalidate(text_file)
        assert cache.read_text(text_file) == '{"id": "updated"}'

    def test_invalidate_missing_path_is_noop(self, cache, tmp_path):
        cache.invalidate(tmp_path / "ghost.json")   # must not raise


class TestReadBytes:
    def test_reads_bytes(self, cache, text_file):
        data = cache.read_bytes(text_file)
        assert isinstance(data, bytes)
        assert b"a1b2" in data

    def test_returns_empty_bytes_for_missing(self, cache, tmp_path):
        assert cache.read_bytes(tmp_path / "no.json") == b""

    def test_bytes_cached_by_mtime(self, cache, text_file):
        cache.read_bytes(text_file)
        original_stat = text_file.stat()
        text_file.write_bytes(b'{"id":"changed"}')
        import os
        os.utime(text_file, (original_stat.st_atime, original_stat.st_mtime))
        assert cache.read_bytes(text_file) == b'{"id": "a1b2"}'
