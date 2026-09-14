"""Deathbound project root resolution and shared I/O helpers.

The existing Deathbound automation scripts hardcode ``D:\\Deathbound`` as the
project root. This module resolves the same repository layout from whichever
machine the pipeline runs on (production workstation, CI, or a headless agent)
without editing or redesigning any existing script.

Resolution order:
1. ``DEATHBOUND_ROOT`` environment variable (must contain the master spec marker).
2. Walk upward from this file looking for ``config/DEATHBOUND_MASTER_SPEC.md``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_MARKER = Path("config") / "DEATHBOUND_MASTER_SPEC.md"


class DeathboundRootError(FileNotFoundError):
    """Raised when the Deathbound repository root cannot be located."""


def find_project_root(start: Optional[Path] = None) -> Path:
    """Locate the Deathbound repository root."""
    env_root = os.environ.get("DEATHBOUND_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if (candidate / ROOT_MARKER).exists():
            return candidate
        raise DeathboundRootError(
            f"DEATHBOUND_ROOT={env_root} does not contain {ROOT_MARKER}"
        )

    # ``start`` is treated as a directory to search from (it may be the root
    # itself, already resolved by a caller); only the module default starts
    # from this file's own directory.
    if start is None:
        start_path = Path(__file__).resolve().parent
    else:
        start_path = Path(start).expanduser().resolve()
    for candidate in [start_path, *start_path.parents]:
        if (candidate / ROOT_MARKER).exists():
            return candidate

    raise DeathboundRootError(
        "Could not locate the Deathbound repository root "
        f"(searched upward from {start_path} for {ROOT_MARKER}). "
        "Set DEATHBOUND_ROOT to the repository root."
    )


def load_json(path: Path) -> Any:
    """Load JSON tolerating the UTF-8 BOM used by several Deathbound files."""
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    """Write UTF-8 JSON with stable formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=False)


def canonical_json(data: Any) -> str:
    """Deterministic JSON string used for fingerprints and digests."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def episode_paths(project_root: Path, episode: str = "EP001") -> Dict[str, Path]:
    """Canonical Deathbound input paths for one episode (existing architecture)."""
    episode_root = project_root / "projects" / episode
    return {
        "episode_root": episode_root,
        "shots": episode_root / "03_shots" / f"{episode}_production_shots.json",
        "bible": episode_root / "story_bible.json",
        "bible_synced": episode_root / "story_bible_synced.json",
        "episode_state": episode_root / "episode_state.json",
        "character_state": episode_root / "characters" / "riven.json",
        "production_input": episode_root / "EP001_PRODUCTION_INPUT.json",
    }


def config_paths(project_root: Path) -> Dict[str, Path]:
    """Canonical Deathbound config paths (existing architecture)."""
    config_root = project_root / "config"
    return {
        "config_root": config_root,
        "rules": config_root / "DEATHBOUND_RULES.json",
        "animation_architecture": config_root / "ANIMATION_ARCHITECTURE.json",
        "style_dna": config_root / "DEATHBOUND_VISUAL_STYLE_DNA.json",
        "shot_sequence_schema": config_root / "SHOT_SEQUENCE_INTEGRATION_SCHEMA.json",
        "generation_manifest_schema": config_root / "GENERATION_MANIFEST_SCHEMA.json",
    }


def generation_paths(project_root: Path, output_root: Optional[Path] = None) -> Dict[str, Path]:
    """Output layout for the visual state + temporal continuity engine."""
    root = Path(output_root) if output_root else project_root / "production" / "generation"
    return {
        "root": root,
        "manifests": root / "manifests",
        "artifacts": root / "artifacts",
        "state": root / "state",
        "reports": root / "reports",
    }
