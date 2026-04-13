"""TDD: zhar.mem.ids — short ID generation and collision avoidance."""
import pytest
from zhar.mem.ids import new_id, is_valid_id, make_id_unique


class TestNewId:
    def test_returns_string(self):
        assert isinstance(new_id(), str)

    def test_default_length_is_four(self):
        assert len(new_id()) == 4

    def test_custom_length(self):
        assert len(new_id(length=8)) == 8

    def test_only_hex_characters(self):
        for _ in range(50):
            assert all(c in "0123456789abcdef" for c in new_id())

    def test_ids_are_not_all_identical(self):
        ids = {new_id() for _ in range(20)}
        # extremely unlikely all 20 collide
        assert len(ids) > 1


class TestIsValidId:
    def test_valid_four_char_hex(self):
        assert is_valid_id("a3f9") is True

    def test_valid_eight_char_hex(self):
        assert is_valid_id("deadbeef") is True

    def test_rejects_uppercase(self):
        assert is_valid_id("A3F9") is False

    def test_rejects_non_hex(self):
        assert is_valid_id("xyz!") is False

    def test_rejects_empty(self):
        assert is_valid_id("") is False

    def test_rejects_too_short(self):
        assert is_valid_id("ab") is False

    def test_rejects_spaces(self):
        assert is_valid_id("ab cd") is False


class TestMakeIdUnique:
    def test_returns_candidate_when_not_taken(self):
        taken: set[str] = set()
        result = make_id_unique("a3f9", taken)
        assert result == "a3f9"

    def test_generates_new_id_when_candidate_taken(self):
        taken = {"a3f9"}
        result = make_id_unique("a3f9", taken)
        assert result != "a3f9"
        assert is_valid_id(result)

    def test_result_not_in_taken(self):
        taken = {"a3f9", "b2c1", "e8f2"}
        result = make_id_unique("a3f9", taken)
        assert result not in taken

    def test_preserves_length(self):
        taken = {"a3f9"}
        result = make_id_unique("a3f9", taken, length=4)
        assert len(result) == 4
