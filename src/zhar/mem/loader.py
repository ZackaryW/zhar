"""Group discovery: load built-in groups and scan .zhar/cfg/ for mem_*.py files.

Contract for user-defined group files
--------------------------------------
Any ``mem_<name>.py`` dropped in ``.zhar/cfg/`` must expose a module-level
variable::

    GROUP: GroupDef

The file is loaded via ``importlib`` in an isolated namespace so it doesn't
pollute ``sys.modules`` with a permanent entry (it uses a throwaway spec).

Load order / precedence
------------------------
``load_all_groups(cfg_dir)`` returns built-in groups first, then user groups.
User groups with the same name as a built-in override the built-in.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from zhar.mem.group import GroupDef

# ── built-in group registry ───────────────────────────────────────────────────
# Populated by importing the four canonical group modules.

_BUILTIN_MODULE_PATHS = [
    "zhar.mem.groups.project_dna",
    "zhar.mem.groups.problem_tracking",
    "zhar.mem.groups.decision_trail",
    "zhar.mem.groups.architecture_context",
    "zhar.mem.groups.code_history",
    "zhar.mem.groups.notes",
]


def load_builtin_groups() -> dict[str, GroupDef]:
    """Import and return all built-in GroupDef instances keyed by name."""
    groups: dict[str, GroupDef] = {}
    for module_path in _BUILTIN_MODULE_PATHS:
        mod = importlib.import_module(module_path)
        _register_module(mod, source=module_path, groups=groups)
    return groups


# ── user-defined group discovery ──────────────────────────────────────────────

def discover_groups(cfg_dir: Path) -> dict[str, GroupDef]:
    """Scan *cfg_dir* for ``mem_*.py`` files and load each as a GroupDef.

    Returns a dict keyed by ``GroupDef.name``.

    Raises
    ------
    ImportError
        If a matching file does not expose a ``GROUP`` variable.
    TypeError
        If ``GROUP`` exists but is not a ``GroupDef`` instance.
    """
    if not cfg_dir.exists():
        return {}

    groups: dict[str, GroupDef] = {}
    for path in sorted(cfg_dir.glob("mem_*.py")):
        mod = _load_file_as_module(path)
        _register_module(mod, source=str(path), groups=groups)
    return groups


def load_all_groups(cfg_dir: Path) -> dict[str, GroupDef]:
    """Return merged dict of built-in groups + user groups.

    User groups with the same name override built-ins.
    """
    groups = load_builtin_groups()
    groups.update(discover_groups(cfg_dir))
    return groups


# ── internal helpers ──────────────────────────────────────────────────────────

def _load_file_as_module(path: Path) -> ModuleType:
    """Load *path* as a module without permanently adding it to sys.modules."""
    module_name = f"_zhar_user_group_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    # Temporarily register so relative imports inside the file work
    sys.modules[module_name] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    finally:
        sys.modules.pop(module_name, None)
    return mod


def _register_module(
    mod: ModuleType, source: str, groups: dict[str, GroupDef]
) -> None:
    """Extract ``GROUP`` from *mod* and add it to *groups*."""
    if not hasattr(mod, "GROUP"):
        raise ImportError(
            f"Group file '{source}' does not expose a module-level 'GROUP' variable."
        )
    group = mod.GROUP
    if not isinstance(group, GroupDef):
        raise TypeError(
            f"Group file '{source}': 'GROUP' must be a GroupDef instance, "
            f"got {type(group).__name__!r}."
        )
    groups[group.name] = group
