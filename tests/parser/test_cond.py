"""Unit tests for src/zhar/parser/cond.py

Tests the condition evaluator in isolation.
All fact values are strings (matching the Facts model).

Grammar inside FACT()/ORFACT()/MEMCOND():
  - Comparisons: key == val, key != val, key < val, key > val, key <= val, key >= val
  - Membership:  key in [a,b,c]   (list literal — RHS starts with '[')
                 key in somestring  (substring check — RHS does not start with '[')
  - Connectors:  lowercase 'and', 'or', 'not'
  - _ver suffix: key_ver >= 3.12  (packaging.version.Version comparison)

FACT/ORFACT chaining (evaluated by eval_condition_groups):
  - Multiple FACT expressions AND together within a group
  - ORFACT creates a new AND-group that ORs against previous groups
  - Final result: OR of all AND-groups
"""
from __future__ import annotations

import pytest

from zhar.parser.cond import eval_condition_groups, eval_expr


FACTS = {
    "lang": "python",
    "ver": "3.12",
    "env": "prod",
    "flag": "true",
    "count": "5",
    "empty": "",
}


# ── eval_expr: single expression string ──────────────────────────────────────

class TestEvalExprEquality:
    def test_eq_true(self):
        assert eval_expr("lang == python", FACTS) is True

    def test_eq_false(self):
        assert eval_expr("lang == ruby", FACTS) is False

    def test_neq_true(self):
        assert eval_expr("lang != ruby", FACTS) is True

    def test_neq_false(self):
        assert eval_expr("lang != python", FACTS) is False

    def test_missing_key_is_false(self):
        assert eval_expr("missing == anything", FACTS) is False


class TestEvalExprOrdering:
    def test_lt_true(self):
        assert eval_expr("count < 9", FACTS) is True

    def test_lt_false(self):
        assert eval_expr("count < 3", FACTS) is False

    def test_gt_true(self):
        assert eval_expr("count > 3", FACTS) is True

    def test_lte_equal(self):
        assert eval_expr("count <= 5", FACTS) is True

    def test_gte_equal(self):
        assert eval_expr("count >= 5", FACTS) is True


class TestEvalExprIn:
    def test_in_list_true(self):
        assert eval_expr("lang in [python,ruby,go]", FACTS) is True

    def test_in_list_false(self):
        assert eval_expr("lang in [ruby,go,java]", FACTS) is False

    def test_in_list_spaces(self):
        assert eval_expr("lang in [python, ruby, go]", FACTS) is True

    def test_in_string_substring_true(self):
        # "python" in "python3" → True
        assert eval_expr("lang in python3", FACTS) is True

    def test_in_string_substring_false(self):
        assert eval_expr("lang in java", FACTS) is False

    def test_not_in_list(self):
        assert eval_expr("not lang in [ruby,go]", FACTS) is True


class TestEvalExprVersion:
    def test_ver_gte_true(self):
        assert eval_expr("ver_ver >= 3.11", FACTS) is True

    def test_ver_gte_false(self):
        assert eval_expr("ver_ver >= 3.13", FACTS) is False

    def test_ver_eq_true(self):
        assert eval_expr("ver_ver == 3.12", FACTS) is True

    def test_ver_lt_false(self):
        assert eval_expr("ver_ver < 3.12", FACTS) is False

    def test_ver_neq_true(self):
        assert eval_expr("ver_ver != 3.11", FACTS) is True


class TestEvalExprCompound:
    def test_and_both_true(self):
        assert eval_expr("lang == python and env == prod", FACTS) is True

    def test_and_one_false(self):
        assert eval_expr("lang == python and env == dev", FACTS) is False

    def test_or_one_true(self):
        assert eval_expr("lang == ruby or env == prod", FACTS) is True

    def test_or_both_false(self):
        assert eval_expr("lang == ruby or env == dev", FACTS) is False

    def test_not_negates(self):
        assert eval_expr("not lang == ruby", FACTS) is True

    def test_and_takes_precedence_over_or(self):
        # (lang==python and env==prod) or (lang==ruby) → True
        assert eval_expr("lang == python and env == prod or lang == ruby", FACTS) is True

    def test_chained_and(self):
        assert eval_expr("lang == python and env == prod and flag == true", FACTS) is True


class TestEvalExprErrors:
    def test_unknown_op_raises(self):
        from zhar.parser.cond import CondError
        with pytest.raises(CondError):
            eval_expr("lang ??? python", FACTS)

    def test_empty_expr_returns_false(self):
        assert eval_expr("", FACTS) is False


# ── eval_condition_groups: FACT/ORFACT chaining ───────────────────────────────

class TestEvalConditionGroups:
    def test_single_fact(self):
        # [["lang == python"]] → True
        assert eval_condition_groups([["lang == python"]], FACTS) is True

    def test_single_fact_false(self):
        assert eval_condition_groups([["lang == ruby"]], FACTS) is False

    def test_two_facts_and(self):
        # [["lang == python", "env == prod"]] → lang==python AND env==prod
        assert eval_condition_groups([["lang == python", "env == prod"]], FACTS) is True

    def test_two_facts_and_one_false(self):
        assert eval_condition_groups([["lang == python", "env == dev"]], FACTS) is False

    def test_orfact_or_logic(self):
        # [["lang == ruby"], ["env == prod"]] → ruby OR prod → True
        assert eval_condition_groups([["lang == ruby"], ["env == prod"]], FACTS) is True

    def test_orfact_both_false(self):
        assert eval_condition_groups([["lang == ruby"], ["env == dev"]], FACTS) is False

    def test_orfact_first_true_short_circuits(self):
        # first group is true → whole result is True regardless of second
        assert eval_condition_groups([["lang == python"], ["lang == ruby"]], FACTS) is True

    def test_empty_groups_false(self):
        assert eval_condition_groups([], FACTS) is False

    def test_empty_fact_in_group_false(self):
        assert eval_condition_groups([[""]], FACTS) is False

    def test_mixed_and_or(self):
        # [["lang==python", "env==dev"], ["env==prod"]]
        # → (python AND dev) OR prod → False OR True → True
        assert eval_condition_groups(
            [["lang == python", "env == dev"], ["env == prod"]], FACTS
        ) is True
