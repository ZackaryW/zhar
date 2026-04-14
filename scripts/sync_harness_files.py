"""Mirror repo `.github` harness files into `src/zhar/harness/files`."""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path


SUPPORTED_DIRS = ("agents", "instructions", "skills")


def _iter_relative_files(root: Path) -> list[Path]:
    """Return all relative file paths under the supported harness directories."""
    relative_paths: list[Path] = []
    for dirname in SUPPORTED_DIRS:
        source_dir = root / dirname
        if not source_dir.exists():
            continue
        for path in source_dir.rglob("*"):
            if path.is_file():
                relative_paths.append(path.relative_to(root))
    return sorted(relative_paths)


def _prune_empty_dirs(root: Path) -> None:
    """Remove empty directories below *root* after file deletions."""
    if not root.exists():
        return
    for path in sorted((candidate for candidate in root.rglob("*") if candidate.is_dir()), reverse=True):
        try:
            path.rmdir()
        except OSError:
            continue


def sync_harness_files(source_root: Path, target_root: Path) -> list[Path]:
    """Mirror supported harness files from *source_root* into *target_root*."""
    changed: list[Path] = []
    expected_files = set(_iter_relative_files(source_root))

    for relative_path in expected_files:
        source_path = source_root / relative_path
        target_path = target_root / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if not target_path.exists() or not filecmp.cmp(source_path, target_path, shallow=False):
            shutil.copy2(source_path, target_path)
            changed.append(target_path)

    if target_root.exists():
        for dirname in SUPPORTED_DIRS:
            existing_dir = target_root / dirname
            if not existing_dir.exists():
                continue
            for target_path in sorted(path for path in existing_dir.rglob("*") if path.is_file()):
                relative_path = target_path.relative_to(target_root)
                if relative_path not in expected_files:
                    target_path.unlink()
                    changed.append(target_path)

    _prune_empty_dirs(target_root)
    return sorted(changed)


def check_harness_files(source_root: Path, target_root: Path) -> list[Path]:
    """Return target-relative files that are missing, stale, or unexpected."""
    mismatches: list[Path] = []
    expected_files = set(_iter_relative_files(source_root))

    for relative_path in expected_files:
        source_path = source_root / relative_path
        target_path = target_root / relative_path
        if not target_path.exists() or not filecmp.cmp(source_path, target_path, shallow=False):
            mismatches.append(target_path)

    if target_root.exists():
        for dirname in SUPPORTED_DIRS:
            existing_dir = target_root / dirname
            if not existing_dir.exists():
                continue
            for target_path in sorted(path for path in existing_dir.rglob("*") if path.is_file()):
                relative_path = target_path.relative_to(target_root)
                if relative_path not in expected_files:
                    mismatches.append(target_path)

    return sorted(mismatches)


def _repo_root() -> Path:
    """Return the repository root based on this script location."""
    return Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    """Run the harness-file sync or check workflow for this repository."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the mirrored harness files are stale.")
    args = parser.parse_args(argv)

    repo_root = _repo_root()
    source_root = repo_root / ".github"
    target_root = repo_root / "src" / "zhar" / "harness" / "files"

    if args.check:
        mismatches = check_harness_files(source_root, target_root)
        if mismatches:
            for path in mismatches:
                print(path.relative_to(repo_root).as_posix())
            return 1
        print("Harness file mirror is up to date.")
        return 0

    changed = sync_harness_files(source_root, target_root)
    print(f"Synced {len(changed)} harness file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())