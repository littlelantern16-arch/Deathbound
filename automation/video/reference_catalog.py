"""Real reference-file cataloging for the character reference bank.

Scans ``assets/characters/<id>/references/`` and catalogs REAL image files
into ``references_catalog.json``. No fake/placeholder references are ever
generated here — an empty directory simply yields an empty catalog.

Cataloged metadata per reference file:
    reference_id, path, sha256, type, pose_view, wardrobe, expression,
    source, canonical_status, size_bytes, cataloged_utc

Supported types (minimum set required by production):
    FACE, FULL_BODY, THREE_QUARTER, PROFILE, WARDROBE, EXPRESSION

Canon is untouched: this module only catalogs files; it never writes to
projects/<episode>/characters/riven.json or any canonical file.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .media import MediaToolkit
from .paths import find_project_root, load_json, write_json

REFERENCE_TYPES = ["FACE", "FULL_BODY", "THREE_QUARTER", "PROFILE", "WARDROBE", "EXPRESSION"]

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

CATALOG_FILENAME = "references_catalog.json"


def references_dir(project_root: Any, character_id: str = "riven") -> Path:
    return Path(project_root) / "assets" / "characters" / character_id / "references"


def classify_reference(filename: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    """Classify a reference file.

    Priority: explicit ``type`` in a sibling ``<stem>.json`` metadata file,
    then filename conventions (riven_face_01.png -> FACE), then UNCLASSIFIED.
    """
    if metadata and metadata.get("type"):
        value = str(metadata["type"]).upper()
        if value in REFERENCE_TYPES:
            return value
    lowered = filename.lower()
    for token, ref_type in [
        ("face", "FACE"),
        ("fullbody", "FULL_BODY"),
        ("full_body", "FULL_BODY"),
        ("threequarter", "THREE_QUARTER"),
        ("three_quarter", "THREE_QUARTER"),
        ("3q", "THREE_QUARTER"),
        ("profile", "PROFILE"),
        ("wardrobe", "WARDROBE"),
        ("expression", "EXPRESSION"),
    ]:
        if token in lowered:
            return ref_type
    return "UNCLASSIFIED"


def catalog_references(
    project_root: Optional[Any] = None,
    character_id: str = "riven",
    *, toolkit: Optional[MediaToolkit] = None,
) -> Dict[str, Any]:
    """Detect and catalog real reference images. Never invents entries."""
    root = find_project_root(project_root)
    directory = references_dir(root, character_id)
    toolkit = toolkit or MediaToolkit(root)

    entries: List[Dict[str, Any]] = []
    if directory.exists():
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            if path.name == CATALOG_FILENAME:
                continue
            metadata: Dict[str, Any] = {}
            sidecar = path.with_suffix(".json")
            if sidecar.exists():
                try:
                    metadata = load_json(sidecar)
                except Exception:
                    metadata = {}
            sha256 = toolkit.sha256_file(path)
            entries.append(
                {
                    "reference_id": metadata.get("reference_id")
                    or f"{character_id}-{path.stem}",
                    "path": str(path.relative_to(root)),
                    "sha256": sha256,
                    "type": classify_reference(path.name, metadata),
                    "pose_view": metadata.get("pose_view"),
                    "wardrobe": metadata.get("wardrobe"),
                    "expression": metadata.get("expression"),
                    "source": metadata.get("source"),
                    "canonical_status": metadata.get("canonical_status", "pending_review"),
                    "size_bytes": path.stat().st_size,
                    "cataloged_utc": datetime.now(timezone.utc).isoformat(),
                }
            )

    catalog = {
        "schema_version": "1.0",
        "kind": "DEATHBOUND_REFERENCE_CATALOG",
        "character_id": character_id,
        "references_directory": str(references_dir(root, character_id)),
        "reference_types": REFERENCE_TYPES,
        "policy": {
            "only_real_files_cataloged": True,
            "no_fake_references_generated": True,
            "canon_untouched": True,
            "note": "Riven canon identity/wardrobe remain governed by "
            "config/DEATHBOUND_RULES.json and config/DEATHBOUND_VISUAL_STYLE_DNA.json.",
        },
        "reference_count": len(entries),
        "references": entries,
    }

    catalog_path = directory / CATALOG_FILENAME
    write_json(catalog_path, catalog)
    return catalog
