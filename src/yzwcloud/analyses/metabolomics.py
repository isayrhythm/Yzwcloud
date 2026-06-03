from __future__ import annotations

import csv
import html
import json
import math
import shutil
from pathlib import Path
from statistics import fmean
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
    output_type: str = "metabolomics_statistics_result",
    analysis_family: str = "metabolomics_statistics",
) -> DataObject:
    params = params or {}
    matrix_path = Path(str(source.meta.get("differential_matrix_file") or source.meta["matrix_file"]))
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
    univariate_method = _metabolomics_univariate_method(params)
    vip_threshold = float(params.get("vip_threshold", 1.0))
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
            univariate_method,
            str(vip_threshold),
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
    plsda_file = output_dir / f"{prefix}_plsda_scores.csv"
    vip_file = output_dir / f"{prefix}_vip.csv"
    oplsda_file = output_dir / f"{prefix}_oplsda_scores.csv"
    correlation_file = output_dir / f"{prefix}_sample_correlation.csv"
    differential_file = output_dir / f"{prefix}_differential.csv"
    for path in [summary_file, normalized_file, qc_file, pca_file, plsda_file, vip_file, correlation_file, differential_file]:
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
        "analysis_family": analysis_family,
        "matrix_file": str(normalized_file),
        "source_matrix_file": str(matrix_path),
        "sample_metadata_file": str(metadata_path),
        "metabolomics_result_file": str(differential_file),
        "diff_result_file": str(differential_file),
        "qc_file": str(qc_file),
        "pca_scores_file": str(pca_file),
        "plsda_scores_file": str(plsda_file),
        "vip_file": str(vip_file),
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
        "univariate_method": univariate_method,
        "p_value_threshold": p_value,
        "log2fc_threshold": log2fc,
        "vip_threshold": vip_threshold,
        "vip_available": bool(summary.get("vip_available")),
        "vip_feature_count": int(summary.get("vip_feature_count") or 0),
        "plsda_available": bool(summary.get("plsda_available")),
        "plsda_message": str(summary.get("plsda_message") or ""),
        "oplsda_available": bool(summary.get("oplsda_available")),
        "oplsda_message": str(summary.get("oplsda_message") or ""),
        "available_tables": [
            "normalized_matrix",
            "qc",
            "pca_scores",
            "plsda_scores",
            "vip",
            "sample_correlation",
            "differential",
        ],
        "not_implemented": [
            "database-backed KEGG/HMDB enrichment",
            "species-specific pathway enrichment",
        ],
    }
    if oplsda_file.exists():
        meta["oplsda_scores_file"] = str(oplsda_file)
        meta["available_tables"].append("oplsda_scores")
    if not meta["oplsda_available"]:
        meta["not_implemented"].append("OPLS-DA requires the ropls R package")
    write_json_detail(
        output_json.with_name(output_json.stem.replace("_output", "_detail") + ".json"),
        {
            "message": "Metabolomics statistics completed with R",
            "meta": meta,
            "top_metabolites": diff_rows[:30],
        },
    )
    return write_data_output(output_json, output_type, meta)


def create_metabolomics_differential_result(
    source: DataObject,
    output_dir: Path,
    node_id: str,
    params: dict[str, Any] | None = None,
) -> DataObject:
    return create_metabolomics_statistics_result(
        source=source,
        output_dir=output_dir,
        node_id=node_id,
        params=params,
        output_type="metabolomics_differential_result",
        analysis_family="metabolomics_differential",
    )


def create_metabolomics_normalization_result(
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
    if len(sample_columns) < 2:
        raise ValueError("Metabolomics normalization requires at least 2 samples")

    impute_method = str(params.get("impute_method") or "half_min").lower()
    normalization_method = str(params.get("normalization_method") or "tic_median").lower()
    transform_method = str(params.get("transform") or "log2").lower()
    scaling_method = str(params.get("scaling") or "pareto").lower()
    treat_zero_as_missing = bool(params.get("treat_zero_as_missing", True))

    features, matrix = _read_metabolomics_matrix(matrix_path, sample_columns, treat_zero_as_missing)
    if len(features) < 2:
        raise ValueError("Metabolomics normalization requires at least 2 usable metabolites")

    imputed, imputed_count = _impute_matrix(matrix, impute_method)
    normalized = _normalize_samples(imputed, normalization_method)
    transformed = _transform_matrix(normalized, transform_method)
    scaled = _scale_features(transformed, scaling_method)

    prefix = _safe_slug(node_id)
    normalized_matrix_file = output_dir / f"{prefix}_log_normalized_matrix.csv"
    scaled_matrix_file = output_dir / f"{prefix}_scaled_matrix.csv"
    metadata_copy = output_dir / f"{prefix}_sample_metadata.csv"
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"

    shutil.copyfile(metadata_path, metadata_copy)
    _write_matrix(normalized_matrix_file, features, sample_columns, transformed)
    _write_matrix(scaled_matrix_file, features, sample_columns, scaled)
    before_totals = _sample_totals(imputed)
    after_totals = _sample_totals(normalized)

    meta = {
        **source.meta,
        "data_type": "metabolomics_matrix",
        "matrix_file": str(scaled_matrix_file),
        "differential_matrix_file": str(normalized_matrix_file),
        "source_matrix_file": str(matrix_path),
        "sample_metadata_file": str(metadata_copy),
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "metabolite_count": len(features),
        "gene_count": len(features),
        "sample_count": len(sample_columns),
        "normalization_method": normalization_method,
        "impute_method": impute_method,
        "transform": transform_method,
        "scaling": scaling_method,
        "treat_zero_as_missing": treat_zero_as_missing,
        "imputed_value_count": imputed_count,
        "sample_total_before_min": round(min(before_totals), 4) if before_totals else 0,
        "sample_total_before_max": round(max(before_totals), 4) if before_totals else 0,
        "sample_total_after_min": round(min(after_totals), 4) if after_totals else 0,
        "sample_total_after_max": round(max(after_totals), 4) if after_totals else 0,
        "analysis_family": "metabolomics_normalization",
    }
    _write_normalization_html(html_path, meta)
    _write_normalization_preview(preview_path, meta)
    write_json_detail(
        output_json.with_name(output_json.stem.replace("_output", "_detail") + ".json"),
        {
            "message": "Metabolomics normalization, imputation, and scaling completed",
            "meta": meta,
            "steps": [
                f"Imputation: {impute_method}",
                f"Normalization: {normalization_method}",
                f"Transform: {transform_method}",
                f"Scaling: {scaling_method}",
            ],
        },
    )
    return write_data_output(output_json, "expression_matrix", meta)


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


def _read_metabolomics_matrix(
    matrix_path: Path,
    sample_columns: list[Any],
    treat_zero_as_missing: bool,
) -> tuple[list[list[str]], list[list[float | None]]]:
    features: list[list[str]] = []
    matrix: list[list[float | None]] = []
    with matrix_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)
        for row in reader:
            if len(row) <= GENE_INFO_COLUMNS:
                continue
            values: list[float | None] = []
            for column in sample_columns:
                raw = row[column.index] if column.index < len(row) else ""
                value = _optional_float(raw)
                if value is not None and treat_zero_as_missing and value == 0:
                    value = None
                values.append(value)
            if sum(value is not None for value in values) < 2:
                continue
            features.append((row + [""] * GENE_INFO_COLUMNS)[:GENE_INFO_COLUMNS])
            matrix.append(values)
    return features, matrix


def _impute_matrix(matrix: list[list[float | None]], method: str) -> tuple[list[list[float]], int]:
    imputed_count = 0
    output: list[list[float]] = []
    for row in matrix:
        present = [value for value in row if value is not None and math.isfinite(value)]
        positives = [value for value in present if value > 0]
        if method == "zero":
            fill = 0.0
        elif method == "median":
            fill = sorted(present)[len(present) // 2] if present else 0.0
        else:
            fill = min(positives) / 2 if positives else (min(present) / 2 if present else 0.0)
        next_row = []
        for value in row:
            if value is None or not math.isfinite(value):
                next_row.append(fill)
                imputed_count += 1
            else:
                next_row.append(value)
        output.append(next_row)
    return output, imputed_count


def _normalize_samples(matrix: list[list[float]], method: str) -> list[list[float]]:
    if method not in {"tic_median", "total_signal", "median"}:
        return [row[:] for row in matrix]
    sample_count = len(matrix[0]) if matrix else 0
    if sample_count == 0:
        return []
    if method == "median":
        factors = []
        for sample_index in range(sample_count):
            values = sorted(row[sample_index] for row in matrix if row[sample_index] > 0)
            factors.append(values[len(values) // 2] if values else 1.0)
    else:
        factors = [sum(max(row[sample_index], 0.0) for row in matrix) for sample_index in range(sample_count)]
    positive = [value for value in factors if value > 0 and math.isfinite(value)]
    target = sorted(positive)[len(positive) // 2] if positive else 1.0
    safe_factors = [factor if factor > 0 and math.isfinite(factor) else target for factor in factors]
    return [
        [value / safe_factors[index] * target for index, value in enumerate(row)]
        for row in matrix
    ]


def _transform_matrix(matrix: list[list[float]], method: str) -> list[list[float]]:
    if method == "none":
        return [row[:] for row in matrix]
    if method == "log10":
        return [[math.log10(max(value, 0.0) + 1.0) for value in row] for row in matrix]
    return [[math.log2(max(value, 0.0) + 1.0) for value in row] for row in matrix]


def _scale_features(matrix: list[list[float]], method: str) -> list[list[float]]:
    if method == "none":
        return [row[:] for row in matrix]
    scaled = []
    for row in matrix:
        mean = fmean(row) if row else 0.0
        variance_value = sum((value - mean) ** 2 for value in row) / (len(row) - 1) if len(row) > 1 else 0.0
        sd = math.sqrt(variance_value)
        if sd == 0 or not math.isfinite(sd):
            scaled.append([0.0 for _ in row])
            continue
        denominator = math.sqrt(sd) if method == "pareto" else sd
        scaled.append([(value - mean) / denominator for value in row])
    return scaled


def _write_matrix(
    path: Path,
    features: list[list[str]],
    sample_columns: list[Any],
    matrix: list[list[float]],
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "gene_short_name",
                "gene_id",
                "description",
                "module",
                "chromosome",
                "gene_type",
                *[column.name for column in sample_columns],
            ]
        )
        for feature, values in zip(features, matrix, strict=False):
            writer.writerow([*feature, *[round(value, 6) for value in values]])


def _sample_totals(matrix: list[list[float]]) -> list[float]:
    if not matrix:
        return []
    sample_count = len(matrix[0])
    return [sum(row[index] for row in matrix) for index in range(sample_count)]


def _write_normalization_html(path: Path, meta: dict[str, Any]) -> None:
    steps = [
        ("Impute", meta["impute_method"], f"{meta['imputed_value_count']} values filled"),
        ("Normalize", meta["normalization_method"], "sample total signal aligned"),
        ("Transform", meta["transform"], "intensity scale compressed"),
        ("Scale", meta["scaling"], "features made comparable"),
    ]
    cards = "".join(
        f"<article><span>{index}</span><strong>{html.escape(title)}</strong><p>{html.escape(str(method))}</p><small>{html.escape(detail)}</small></article>"
        for index, (title, method, detail) in enumerate(steps, start=1)
    )
    payload = json.dumps(meta, ensure_ascii=False)
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Metabolomics normalization</title>
<style>
body{{margin:0;font-family:Inter,'Noto Sans SC',Arial,sans-serif;background:#f7fbfb;color:#07131f}}
.wrap{{padding:28px;max-width:1120px;margin:auto}}
h1{{margin:0 0 8px;font-size:30px}}p{{color:#52616b;line-height:1.6}}
.steps{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:22px 0}}
article{{padding:16px;border:1px solid #cfe0e3;border-radius:14px;background:white;box-shadow:0 10px 24px rgba(17,42,61,.08)}}
article span{{display:inline-flex;width:24px;height:24px;align-items:center;justify-content:center;border-radius:999px;background:#0f8a8f;color:white;font-weight:900;font-size:12px}}
article strong{{display:block;margin-top:10px;font-size:16px}}article p{{margin:5px 0;color:#0f6b57;font-weight:800}}article small{{color:#52616b}}
.metrics{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}
.metric{{padding:16px;border:1px solid #d8e5ee;border-radius:14px;background:#fff}}.metric span{{display:block;color:#52616b;font-size:12px}}.metric strong{{font-size:22px}}
#bars{{width:100%;height:220px;margin-top:18px;border:1px solid #d8e5ee;border-radius:14px;background:white}}
@media(max-width:860px){{.steps,.metrics{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap">
<h1>Metabolomics normalize / impute / scale</h1>
<p>This node prepares the QC-passed metabolomics matrix for downstream PCA, heatmaps, abundance plots, and differential metabolite analysis. It does not decide whether samples pass QC.</p>
<section class="steps">{cards}</section>
<section class="metrics">
<div class="metric"><span>Metabolites</span><strong>{meta['metabolite_count']}</strong></div>
<div class="metric"><span>Samples</span><strong>{meta['sample_count']}</strong></div>
<div class="metric"><span>Imputed values</span><strong>{meta['imputed_value_count']}</strong></div>
</section>
<canvas id="bars" width="1040" height="220"></canvas></div>
<script>
const meta = {payload};
const canvas = document.getElementById('bars');
const ctx = canvas.getContext('2d');
const beforeMin = Number(meta.sample_total_before_min || 0), beforeMax = Number(meta.sample_total_before_max || 0);
const afterMin = Number(meta.sample_total_after_min || 0), afterMax = Number(meta.sample_total_after_max || 0);
const values = [beforeMin, beforeMax, afterMin, afterMax];
const labels = ['Before min', 'Before max', 'After min', 'After max'];
const colors = ['#9bb8c6','#315fd6','#98d7c9','#0f8a8f'];
const max = Math.max(...values, 1);
ctx.clearRect(0,0,canvas.width,canvas.height);
ctx.font = '13px Inter, sans-serif';
ctx.fillStyle = '#52616b';
ctx.fillText('Sample total signal range before and after normalization', 28, 28);
values.forEach((value, index) => {{
  const x = 56 + index * 235;
  const h = Math.max(4, value / max * 128);
  ctx.fillStyle = colors[index];
  ctx.fillRect(x, 168 - h, 120, h);
  ctx.fillStyle = '#07131f';
  ctx.fillText(labels[index], x, 190);
  ctx.fillStyle = '#52616b';
  ctx.fillText(Number(value).toFixed(2), x, 207);
}});
</script></body></html>""",
        encoding="utf-8",
    )


def _write_normalization_preview(path: Path, meta: dict[str, Any]) -> None:
    steps = ["Impute", "Normalize", "Log", "Scale"]
    boxes = []
    for index, step in enumerate(steps):
        x = 16 + index * 50
        boxes.append(
            f'<rect x="{x}" y="42" width="42" height="28" rx="7" fill="#e8f7f4" stroke="#0f8a8f"/>'
            f'<text x="{x + 21}" y="59" text-anchor="middle" font-size="7" fill="#0d5860" font-weight="700">{step}</text>'
        )
        if index < len(steps) - 1:
            boxes.append(f'<path d="M{x + 43} 56 H{x + 50}" stroke="#52616b" stroke-width="1.5"/>')
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#f7fbfb"/><text x="12" y="18" font-size="11" fill="#17211b" font-weight="700">Normalize / impute / scale</text><text x="12" y="32" font-size="9" fill="#52616b">{int(meta["metabolite_count"])} metabolites / {int(meta["sample_count"])} samples</text>{"".join(boxes)}<text x="12" y="96" font-size="9" fill="#52616b">filled {int(meta["imputed_value_count"])} missing values</text></svg>',
        encoding="utf-8",
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
                    "vip": _float(raw.get("vip"), default=0.0),
                }
            )
    rows.sort(key=lambda row: row["p_value"])
    return rows


def _metabolomics_univariate_method(params: dict[str, Any]) -> str:
    value = str(
        params.get("univariate_method")
        or params.get("statistical_test")
        or params.get("test_method")
        or params.get("method")
        or "t_test"
    ).strip().lower()
    if value in {"", "r_metabolomics", "r_metabolomics_univariate_pca_qc", "r_transcriptomics"}:
        return "t_test"
    if value in {"t", "ttest", "t-test", "t_test", "student", "welch", "welch_t"}:
        return "t_test"
    if value in {"wilcox", "wilcoxon", "wilcox-test", "wilcox_test", "mann_whitney", "mann-whitney"}:
        return "wilcox"
    raise ValueError("Metabolomics univariate method must be t_test or wilcox")


def _float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _safe_slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_") or "metabolomics"
