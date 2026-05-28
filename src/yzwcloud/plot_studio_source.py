from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yzwcloud.config import PROJECT_ROOT


def _select_source_table(source: dict[str, Any]) -> tuple[Path | None, str]:
    meta = dict(source.get("meta") or {})
    data_path = _resolve_allowed_path(str(source.get("data_path") or source.get("dataPath") or ""))
    if data_path and data_path.suffix.lower() == ".json":
        meta.update(_read_meta_from_json(data_path))
    if data_path and data_path.suffix.lower() in {".csv", ".tsv", ".txt", ".xlsx", ".xlsm"}:
        return data_path, "source.data_path"

    for key in ("diff_result_file", "matrix_file", "module_file", "sample_metadata_file"):
        candidate = _resolve_allowed_path(str(meta.get(key) or ""))
        if candidate and candidate.suffix.lower() in {".csv", ".tsv", ".txt", ".xlsx", ".xlsm"}:
            return candidate, f"source.meta.{key}"
    return None, "no readable tabular source was found"


def _read_meta_from_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(payload, dict) and isinstance(payload.get("meta"), dict):
        return dict(payload["meta"])
    return {}


def _resolve_allowed_path(value: str) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    try:
        resolved = path.resolve()
        project_root = PROJECT_ROOT.resolve()
    except OSError:
        return None
    if resolved != project_root and project_root not in resolved.parents:
        return None
    if not resolved.exists():
        return None
    return resolved


def _source_summary(source: dict[str, Any], data_path: Path | None) -> dict[str, Any]:
    return {
        "source_kind": source.get("source_kind") or source.get("sourceKind") or "analysis_output",
        "task_id": source.get("task_id") or source.get("taskId") or "",
        "node_id": source.get("node_id") or source.get("nodeId") or source.get("id") or "",
        "name": source.get("name") or "",
        "type": source.get("type") or "",
        "data_path": str(data_path) if data_path else "",
    }


