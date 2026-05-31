from __future__ import annotations

import json
import csv
import re
from pathlib import Path
from typing import Any

from yzwcloud.config import PROJECT_ROOT


def _select_source_table(source: dict[str, Any]) -> tuple[Path | None, str]:
    meta = dict(source.get("meta") or {})
    source_type = str(source.get("type") or source.get("output_type") or "").lower()
    data_path = _resolve_allowed_path(str(source.get("data_path") or source.get("dataPath") or ""))
    if data_path and data_path.suffix.lower() == ".json":
        meta.update(_read_meta_from_json(data_path))
    if data_path and data_path.suffix.lower() in {".csv", ".tsv", ".txt", ".xlsx", ".xlsm"}:
        return data_path, "source.data_path"

    for key in (
        "plot_studio_table_file",
        "gene_expression_table_file",
        "heatmap_table_file",
        "metabolomics_result_file",
        "pca_scores_file",
        "sample_correlation_file",
        "qc_file",
        "diff_result_file",
        "matrix_file",
        "module_file",
        "sample_metadata_file",
    ):
        candidate = _resolve_allowed_path(str(meta.get(key) or ""))
        if candidate and candidate.suffix.lower() in {".csv", ".tsv", ".txt", ".xlsx", ".xlsm"}:
            return candidate, f"source.meta.{key}"
        if key == "pca_scores_file" and "pca" in source_type:
            html_candidate = _resolve_allowed_path(str(meta.get("html_file") or ""))
            derived = _derive_pca_scores_from_html(html_candidate)
            if derived:
                return derived, "source.meta.html_file.points"
        if key == "gene_expression_table_file" and "gene_expression" in source_type:
            html_candidate = _resolve_allowed_path(str(meta.get("html_file") or ""))
            derived = _derive_gene_expression_table_from_html(html_candidate)
            if derived:
                return derived, "source.meta.html_file.gene_expression"
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


def _derive_pca_scores_from_html(path: Path | None) -> Path | None:
    if path is None or path.suffix.lower() != ".html":
        return None
    target = path.with_name(f"{path.stem}_plot_studio_scores.csv")
    if target.exists():
        return target
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"const\s+points\s*=\s*(\[.*?\]);\s*const\s+explained", text, re.S)
    if not match:
        return None
    try:
        points = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(points, list) or not points:
        return None
    fieldnames = ["sample", "condition", "group", "pc1", "pc2"]
    try:
        with target.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for point in points:
                if isinstance(point, dict):
                    writer.writerow({key: point.get(key, "") for key in fieldnames})
    except OSError:
        return None
    return target


def _derive_gene_expression_table_from_html(path: Path | None) -> Path | None:
    if path is None or path.suffix.lower() != ".html":
        return None
    target = path.with_name(f"{path.stem}_plot_studio_table.csv")
    if target.exists():
        return target
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"const\s+data\s*=\s*(\{.*?\});\s*const\s+palette", text, re.S)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    points = payload.get("points") if isinstance(payload, dict) else None
    if not isinstance(points, list) or not points:
        return None
    fieldnames = ["gene", "gene_id", "sample", "condition", "group", "value"]
    try:
        with target.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for point in points:
                if isinstance(point, dict):
                    writer.writerow(
                        {
                            "gene": payload.get("gene", ""),
                            "gene_id": payload.get("gene_id", ""),
                            "sample": point.get("sample", ""),
                            "condition": point.get("condition", ""),
                            "group": point.get("group", ""),
                            "value": point.get("value", ""),
                        }
                    )
    except OSError:
        return None
    return target


def _source_summary(source: dict[str, Any], data_path: Path | None) -> dict[str, Any]:
    return {
        "source_kind": source.get("source_kind") or source.get("sourceKind") or "analysis_output",
        "task_id": source.get("task_id") or source.get("taskId") or "",
        "node_id": source.get("node_id") or source.get("nodeId") or source.get("id") or "",
        "name": source.get("name") or "",
        "type": source.get("type") or "",
        "data_path": str(data_path) if data_path else "",
    }


