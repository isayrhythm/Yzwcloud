from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

from yzwcloud.analyses.common import (
    GENE_INFO_COLUMNS,
    load_sample_columns,
    write_data_output,
    write_json_detail,
)
from yzwcloud.analyses.r_runner import run_r_script
from yzwcloud.models import DataObject


def create_metabolomics_statistics_result(
    source: DataObject,
    output_dir: Path,
    node_id: str,
    params: dict[str, Any] | None = None,
) -> DataObject:
    params = params or {}
    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    output_dir.mkdir(parents=True, exist_ok=True)
    sample_columns = load_sample_columns(matrix_path, metadata_path)
    conditions = _condition_counts(sample_columns)
    if len(sample_columns) < 2:
        raise ValueError("Metabolomics statistics requires at least 2 samples")

    case_condition, control_condition = _comparison_conditions(conditions, params)
    r_matrix = output_dir / f"{node_id}_r_matrix.csv"
    r_metadata = output_dir / f"{node_id}_r_metadata.csv"
    _write_r_inputs(matrix_path, metadata_path, r_matrix, r_metadata)

    script_path = Path(__file__).resolve().parents[1] / "r" / "metabolomics_statistics.R"
    log_path = output_dir / f"{node_id}_r.log"
    prefix = _safe_slug(node_id)
    p_value = float(params.get("p_value", 0.05))
    log2fc = float(params.get("log2fc", 1.0))
    run_r_script(
        script_path=script_path,
        args=[
            str(r_matrix),
            str(r_metadata),
            str(output_dir),
            prefix,
            case_condition,
            control_condition,
            str(p_value),
            str(log2fc),
        ],
        cwd=Path(__file__).resolve().parents[3],
        log_path=log_path,
        timeout=600,
        failure_hint="R metabolomics statistics failed",
    )

    summary_file = output_dir / f"{prefix}_summary.json"
    normalized_file = output_dir / f"{prefix}_normalized_matrix.csv"
    qc_file = output_dir / f"{prefix}_qc.csv"
    pca_file = output_dir / f"{prefix}_pca_scores.csv"
    correlation_file = output_dir / f"{prefix}_sample_correlation.csv"
    differential_file = output_dir / f"{prefix}_differential.csv"
    for path in [summary_file, normalized_file, qc_file, pca_file, correlation_file, differential_file]:
        if not path.exists():
            raise ValueError(f"R metabolomics statistics finished without expected output: {path}")

    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    diff_rows = _read_diff_rows(differential_file)
    significant = [
        row
        for row in diff_rows
        if row["p_value"] <= p_value and abs(row["log2fc"]) >= log2fc
    ]
    output_json = output_dir / f"{node_id}_output.json"
    meta = {
        "method": "r_metabolomics_univariate_pca_qc",
        "matrix_file": str(normalized_file),
        "source_matrix_file": str(matrix_path),
        "sample_metadata_file": str(metadata_path),
        "metabolomics_result_file": str(differential_file),
        "diff_result_file": str(differential_file),
        "qc_file": str(qc_file),
        "pca_scores_file": str(pca_file),
        "sample_correlation_file": str(correlation_file),
        "r_script_file": str(script_path),
        "r_matrix_file": str(r_matrix),
        "r_metadata_file": str(r_metadata),
        "r_log_file": str(log_path),
        "summary_file": str(summary_file),
        "metabolite_count": int(summary.get("metabolite_count") or len(diff_rows)),
        "sample_count": int(summary.get("sample_count") or len(sample_columns)),
        "case_condition": case_condition,
        "control_condition": control_condition,
        "comparison_label": f"{case_condition} vs {control_condition}",
        "significant_metabolite_count": len(significant),
        "p_value_threshold": p_value,
        "log2fc_threshold": log2fc,
        "available_tables": [
            "normalized_matrix",
            "qc",
            "pca_scores",
            "sample_correlation",
            "differential",
        ],
        "not_implemented": [
            "database-backed KEGG/HMDB enrichment",
            "species-specific pathway enrichment",
            "OPLS-DA/VIP package-dependent modeling",
        ],
    }
    write_json_detail(
        output_json.with_name(output_json.stem.replace("_output", "_detail") + ".json"),
        {
            "message": "Metabolomics statistics completed with R",
            "meta": meta,
            "top_metabolites": diff_rows[:30],
        },
    )
    return write_data_output(output_json, "metabolomics_statistics_result", meta)


def _write_r_inputs(matrix_path: Path, metadata_path: Path, r_matrix: Path, r_metadata: Path) -> None:
    with matrix_path.open(encoding="utf-8-sig", newline="") as source_file, r_matrix.open(
        "w", encoding="utf-8-sig", newline=""
    ) as target_file:
        reader = csv.reader(source_file)
        header = next(reader, [])
        writer = csv.writer(target_file)
        writer.writerow(["feature_id", "feature_name", "description", *header[GENE_INFO_COLUMNS:]])
        for row in reader:
            if len(row) <= GENE_INFO_COLUMNS:
                continue
            writer.writerow(
                [
                    row[1] or row[0],
                    row[0] or row[1],
                    row[2] if len(row) > 2 else "",
                    *row[GENE_INFO_COLUMNS:],
                ]
            )

    with metadata_path.open(encoding="utf-8-sig", newline="") as source_file, r_metadata.open(
        "w", encoding="utf-8-sig", newline=""
    ) as target_file:
        reader = csv.DictReader(source_file)
        writer = csv.DictWriter(target_file, fieldnames=["sample", "group", "condition"])
        writer.writeheader()
        for row in reader:
            writer.writerow(
                {
                    "sample": row.get("sample", ""),
                    "group": row.get("group", row.get("condition", "")),
                    "condition": row.get("condition", row.get("group", "")),
                }
            )


def _condition_counts(sample_columns: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for column in sample_columns:
        counts[column.condition] = counts.get(column.condition, 0) + 1
    return counts


def _comparison_conditions(conditions: dict[str, int], params: dict[str, Any]) -> tuple[str, str]:
    requested_case = str(params.get("case_condition") or "").strip()
    requested_control = str(params.get("control_condition") or "").strip()
    if requested_case and requested_control:
        return requested_case, requested_control
    eligible = [condition for condition, count in sorted(conditions.items()) if count >= 2]
    if len(eligible) >= 2:
        return eligible[1], eligible[0]
    ordered = sorted(conditions, key=conditions.get, reverse=True)
    if len(ordered) >= 2:
        return ordered[0], ordered[1]
    only = ordered[0] if ordered else "condition"
    return only, only


def _read_diff_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as file:
        for raw in csv.DictReader(file):
            rows.append(
                {
                    "metabolite": raw.get("metabolite") or raw.get("feature_name") or raw.get("feature_id") or "",
                    "feature_id": raw.get("feature_id") or "",
                    "log2fc": _float(raw.get("log2fc")),
                    "p_value": _float(raw.get("p_value"), default=1.0),
                }
            )
    rows.sort(key=lambda row: row["p_value"])
    return rows


def _float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _safe_slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_") or "metabolomics"
