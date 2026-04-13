"""GroupDef and NodeTypeDef — the lightweight metadata semantic contract.

A *group* is a named collection of node types.  Each node type owns:
  - a Python dataclass as its metadata schema (the "metadata semantic")
  - a list of valid status strings
  - an optional singleton flag

Built-in groups (project_dna, etc.) and user-defined groups dropped in
``.zhar/cfg/mem_<name>.py`` follow the same contract: expose a module-level
``GROUP: GroupDef`` variable.
"""
from __future__ import annotations

import dataclasses
import typing
from dataclasses import dataclass, field
from typing import Any, get_args, get_origin


@dataclass(frozen=True)
class NodeTypeDef:
    """Descriptor for a single node type within a group."""

    name: str
    meta_cls: type                       # must be a @dataclass
    valid_statuses: list[str]
    default_status: str = "active"
    singleton: bool = False
    auto_expires: bool = False
    # True  → nodes of this type carry a content markdown body
    # False → graph-only / summary-only nodes (content is always None)
    memory_backed: bool = False

    def __post_init__(self) -> None:
        if self.default_status not in self.valid_statuses:
            raise ValueError(
                f"NodeTypeDef '{self.name}': default_status "
                f"'{self.default_status}' is not in valid_statuses "
                f"{self.valid_statuses}"
            )


@dataclass
class GroupDef:
    """Descriptor for a memory group."""

    name: str
    node_types: list[NodeTypeDef] = field(default_factory=list)

    def __post_init__(self) -> None:
        names = [nt.name for nt in self.node_types]
        seen: set[str] = set()
        for n in names:
            if n in seen:
                raise ValueError(
                    f"GroupDef '{self.name}': duplicate node type name '{n}'"
                )
            seen.add(n)
        # build fast lookup
        self._by_name: dict[str, NodeTypeDef] = {nt.name: nt for nt in self.node_types}

    # ── lookup ────────────────────────────────────────────────────────────────

    def get_type(self, name: str) -> NodeTypeDef:
        """Return the NodeTypeDef for *name* or raise KeyError."""
        try:
            return self._by_name[name]
        except KeyError:
            raise KeyError(
                f"Group '{self.name}' has no node type '{name}'. "
                f"Known types: {list(self._by_name)}"
            )

    @property
    def type_names(self) -> list[str]:
        return list(self._by_name)

    @property
    def singletons(self) -> list[str]:
        return [nt.name for nt in self.node_types if nt.singleton]

    def is_valid_status(self, type_name: str, status: str) -> bool:
        return status in self.get_type(type_name).valid_statuses

    def default_status(self, type_name: str) -> str:
        return self.get_type(type_name).default_status


# ── metadata validation ───────────────────────────────────────────────────────

def validate_node_metadata(node_type: NodeTypeDef, metadata: dict[str, Any]) -> list[str]:
    """Validate *metadata* dict against *node_type.meta_cls*.

    Returns a list of error strings (empty → valid).

    Rules:
    - Unknown keys (not in the dataclass fields) → error
    - Values present are checked against their field type annotation where
      possible (Literal values, basic types).
    - Missing keys use defaults — not an error.
    """
    if not dataclasses.is_dataclass(node_type.meta_cls):
        return []  # non-dataclass meta — skip validation

    cls = node_type.meta_cls
    known_fields = {f.name: f for f in dataclasses.fields(cls)}
    errors: list[str] = []

    for key, value in metadata.items():
        if key not in known_fields:
            errors.append(
                f"Unknown metadata field '{key}' for node type '{node_type.name}'. "
                f"Known fields: {list(known_fields)}"
            )
            continue

        annotation = known_fields[key].type
        # Resolve string-form annotations if needed
        if isinstance(annotation, str):
            try:
                annotation = eval(annotation, vars(typing))  # noqa: S307
            except Exception:
                continue  # can't resolve — skip type check

        err = _check_type(key, value, annotation)
        if err:
            errors.append(err)

    return errors


def _check_type(field_name: str, value: Any, annotation: Any) -> str | None:
    """Return an error string if *value* doesn't match *annotation*, else None."""
    origin = get_origin(annotation)

    # Literal[...] — check allowed values
    if origin is typing.Literal:
        allowed = get_args(annotation)
        if value not in allowed:
            return (
                f"Field '{field_name}': value {value!r} not in "
                f"Literal{list(allowed)}"
            )
        return None

    # Plain type (str, int, float, bool, …)
    if isinstance(annotation, type):
        if not isinstance(value, annotation):
            return (
                f"Field '{field_name}': expected {annotation.__name__}, "
                f"got {type(value).__name__} ({value!r})"
            )

    return None
