"""Project configuration for zhar.

Layout
------
A ``.zhar/`` directory sits at the project root.  Inside it::

    .zhar/
        config.toml      # optional overrides
        mem/             # one JSON file per group
        cfg/             # user-defined mem_*.py group files

``ZharConfig`` is the resolved, typed view of that layout.
``load_config(root)`` reads ``root/config.toml`` and merges with defaults.
``find_zhar_root(start)`` walks up the directory tree looking for ``.zhar/``.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]


@dataclass
class ZharConfig:
    """Resolved configuration for a zhar project."""

    root: Path
    store_dir: Path = field(init=False)
    cfg_dir: Path = field(init=False)

    # Raw overrides (filled in by load_config before __post_init__)
    _store_dir_override: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self._store_dir_override:
            self.store_dir = self.root / self._store_dir_override
        else:
            self.store_dir = self.root / "mem"
        self.cfg_dir = self.root / "cfg"


def load_config(root: Path) -> ZharConfig:
    """Load ``root/config.toml`` and return a ``ZharConfig``.

    Falls back to all defaults when the file does not exist.
    """
    toml_path = root / "config.toml"
    raw: dict = {}
    if toml_path.exists():
        with toml_path.open("rb") as fh:
            raw = tomllib.load(fh)

    return ZharConfig(
        root=root,
        _store_dir_override=raw.get("store_dir"),
    )


def find_zhar_root(start: Path) -> Path | None:
    """Walk up from *start* looking for a project-local ``.zhar/`` directory.

    Returns the ``.zhar/`` path if found, or ``None``. A user-level
    ``Path.home() / '.zhar'`` is ignored unless it also looks like an actual
    project root instead of the harness cache location.
    """
    current = start.resolve()
    home_zhar = Path.home().resolve() / ".zhar"
    while True:
        candidate = current / ".zhar"
        if candidate.is_dir():
            if candidate == home_zhar:
                has_project_layout = any(
                    (candidate / entry).exists()
                    for entry in ("mem", "cfg", "config.toml")
                )
                if not has_project_layout:
                    return None
            return candidate
        parent = current.parent
        if parent == current:
            # Reached filesystem root
            return None
        current = parent
