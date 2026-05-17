from __future__ import annotations

import csv
import html
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any

from yzwcloud.models import DataObject


GENE_INFO_COLUMNS = 6


@dataclass
class SampleColumn:
    index: int
    name: str
    condition: str
    group: str


def run_differential_analysis(
    source: DataObject,
    params: dict[str, Any],
    output_dir: Path,
    node_id: str,
) -> DataObject:
    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    case_condition = str(params["case_condition"])
    control_condition = str(params["control_condition"])

    sample_columns = _load_sample_columns(matrix_path, metadata_path)
    case_columns = [item for item in sample_columns if item.condition == case_condition]
    control_columns = [item for item in sample_columns if item.condition == control_condition]
    if not case_columns or not control_columns:
        raise ValueError("选择的 case/control 分组没有可用样本列")

    diff_csv = output_dir / f"{node_id}_diff.csv"
    output_json = output_dir / f"{node_id}_output.json"
    rows = []
    with matrix_path.open(encoding="utf-8-sig", newline="") as file:
      reader = csv.reader(file)
      header = next(reader)
      for row in reader:
          if len(row) <= GENE_INFO_COLUMNS:
              continue
          gene_name = row[0] or row[1]
          gene_id = row[1] or row[0]
          case_values = _values_at(row, case_columns)
          control_values = _values_at(row, control_columns)
          if len(case_values) < 2 or len(control_values) < 2:
              continue
          case_mean = fmean(case_values)
          control_mean = fmean(control_values)
          log2fc = case_mean - control_mean
          p_value = _welch_p_value(case_values, control_values)
          rows.append(
              {
                  "gene": gene_name,
                  "gene_id": gene_id,
                  "case_mean": case_mean,
                  "control_mean": control_mean,
                  "log2fc": log2fc,
                  "p_value": p_value,
                  "neg_log10_p": -math.log10(max(p_value, 1e-300)),
              }
          )

    rows.sort(key=lambda item: item["p_value"])
    with diff_csv.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "gene",
                "gene_id",
                "case_mean",
                "control_mean",
                "log2fc",
                "p_value",
                "neg_log10_p",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    significant = [
        item for item in rows if item["p_value"] <= params.get("p_value", 0.05)
        and abs(item["log2fc"]) >= params.get("log2fc", 1.0)
    ]
    meta = {
        "diff_gene_count": len(significant),
        "tested_gene_count": len(rows),
        "method": params.get("method", "demo_welch_ttest"),
        "case_condition": case_condition,
        "control_condition": control_condition,
        "comparison_label": f"{case_condition} vs {control_condition}",
        "case_sample_count": len(case_columns),
        "control_sample_count": len(control_columns),
        "diff_result_file": str(diff_csv),
        "matrix_file": str(matrix_path),
        "sample_metadata_file": str(metadata_path),
    }
    output = DataObject(type="diff_result", data=str(output_json), meta=meta)
    output_json.write_text(output.model_dump_json(indent=2), encoding="utf-8")
    _write_json_detail(
        output_json.with_name(output_json.stem.replace("_output", "_detail") + ".json"),
        {"message": "差异分析完成", "meta": meta, "top_genes": rows[:30]},
    )
    return output


def create_volcano_result(diff: DataObject, output_dir: Path, node_id: str) -> DataObject:
    rows = _read_diff_rows(Path(str(diff.meta["diff_result_file"])))
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    comparison = diff.meta.get("comparison_label", "comparison")

    points = [
        {
            "gene": row["gene"],
            "x": round(row["log2fc"], 4),
            "y": round(row["neg_log10_p"], 4),
            "p": row["p_value"],
        }
        for row in rows[:5000]
    ]
    _write_volcano_html(html_path, comparison, points)
    _write_volcano_preview(preview_path, points, comparison)
    meta = {
        "comparison_label": comparison,
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "point_count": len(points),
    }
    return _write_data_output(output_json, "volcano_plot", meta)


def create_heatmap_result(diff: DataObject, output_dir: Path, node_id: str) -> DataObject:
    matrix_path = Path(str(diff.meta["matrix_file"]))
    metadata_path = Path(str(diff.meta["sample_metadata_file"]))
    diff_rows = _read_diff_rows(Path(str(diff.meta["diff_result_file"])))[:50]
    sample_columns = _load_sample_columns(matrix_path, metadata_path)
    case_condition = str(diff.meta["case_condition"])
    control_condition = str(diff.meta["control_condition"])
    selected_columns = [
        item for item in sample_columns if item.condition in {case_condition, control_condition}
    ]

    genes = _extract_heatmap_values(matrix_path, diff_rows, selected_columns)
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    comparison = diff.meta.get("comparison_label", "comparison")

    _write_heatmap_html(html_path, comparison, selected_columns, genes)
    _write_heatmap_preview(preview_path, comparison, genes)
    meta = {
        "comparison_label": comparison,
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "gene_count": len(genes),
        "sample_count": len(selected_columns),
    }
    return _write_data_output(output_json, "heatmap_plot", meta)


def create_pca_result(source: DataObject, output_dir: Path, node_id: str) -> DataObject:
    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    sample_columns = _load_sample_columns(matrix_path, metadata_path)
    max_genes = 2000

    gene_vectors = _load_standardized_gene_vectors(matrix_path, sample_columns, max_genes=max_genes)
    if len(gene_vectors) < 2 or len(sample_columns) < 2:
        raise ValueError("PCA 需要至少 2 个样本和 2 个可用基因")

    covariance = _sample_covariance(gene_vectors, len(sample_columns))
    pc1_value, pc1_vector = _principal_component(covariance)
    covariance = _deflate(covariance, pc1_value, pc1_vector)
    pc2_value, pc2_vector = _principal_component(covariance)
    total_variance = sum(max(covariance[index][index], 0.0) for index in range(len(covariance)))
    total_variance += max(pc1_value, 0.0)
    total_variance = total_variance or 1.0

    pc1_scale = math.sqrt(max(pc1_value, 0.0))
    pc2_scale = math.sqrt(max(pc2_value, 0.0))
    points = [
        {
            "sample": column.name,
            "condition": column.condition,
            "group": column.group,
            "pc1": round(pc1_vector[index] * pc1_scale, 5),
            "pc2": round(pc2_vector[index] * pc2_scale, 5),
        }
        for index, column in enumerate(sample_columns)
    ]

    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    explained = {
        "pc1": round(max(pc1_value, 0.0) / total_variance * 100, 2),
        "pc2": round(max(pc2_value, 0.0) / total_variance * 100, 2),
    }

    _write_pca_html(html_path, points, explained, len(gene_vectors))
    _write_pca_preview(preview_path, points)
    meta = {
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "sample_count": len(sample_columns),
        "gene_count": len(gene_vectors),
        "explained_variance": explained,
        "method": "sample_covariance_power_iteration",
    }
    return _write_data_output(output_json, "pca_plot", meta)


def create_qc_result(source: DataObject, output_dir: Path, node_id: str) -> DataObject:
    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    sample_columns = _load_sample_columns(matrix_path, metadata_path)
    series = _load_sample_series(matrix_path, sample_columns)
    stats = [_sample_qc_stats(column, values) for column, values in zip(sample_columns, series, strict=False)]
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    _write_qc_html(html_path, stats)
    _write_qc_preview(preview_path, stats)
    meta = {
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "sample_count": len(stats),
        "metric_count": 4,
    }
    return _write_data_output(output_json, "qc_report", meta)


def create_sample_correlation_result(source: DataObject, output_dir: Path, node_id: str) -> DataObject:
    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    sample_columns = _load_sample_columns(matrix_path, metadata_path)
    series = _load_sample_series(matrix_path, sample_columns)
    matrix = [
        [round(_pearson(series[i], series[j]), 3) for j in range(len(sample_columns))]
        for i in range(len(sample_columns))
    ]
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    _write_correlation_html(html_path, sample_columns, matrix)
    _write_correlation_preview(preview_path, matrix)
    meta = {
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "sample_count": len(sample_columns),
    }
    return _write_data_output(output_json, "sample_correlation_plot", meta)


def create_expression_heatmap_result(source: DataObject, output_dir: Path, node_id: str) -> DataObject:
    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    sample_columns = _load_sample_columns(matrix_path, metadata_path)
    genes = _top_variable_heatmap_genes(matrix_path, sample_columns, top_n=40)
    ordered_columns = _order_samples_by_condition(sample_columns)
    order_index = [sample_columns.index(item) for item in ordered_columns]
    for gene in genes:
        gene["values"] = [gene["values"][index] for index in order_index]
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    _write_heatmap_html(html_path, "表达矩阵聚类热图", ordered_columns, genes)
    _write_heatmap_preview(preview_path, "表达聚类", genes)
    meta = {
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "gene_count": len(genes),
        "sample_count": len(ordered_columns),
    }
    return _write_data_output(output_json, "expression_heatmap_plot", meta)


def create_gene_expression_result(
    source: DataObject,
    params: dict[str, Any],
    output_dir: Path,
    node_id: str,
) -> DataObject:
    gene_query = str(params.get("gene") or "").strip()
    if not gene_query:
        raise ValueError("请输入要查看的基因名或 gene_id")
    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    sample_columns = _load_sample_columns(matrix_path, metadata_path)
    gene_payload = _find_gene_expression(matrix_path, sample_columns, gene_query)
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    _write_gene_expression_html(html_path, gene_payload)
    _write_gene_expression_preview(preview_path, gene_payload)
    meta = {
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "gene": gene_payload["gene"],
        "gene_id": gene_payload["gene_id"],
        "sample_count": len(gene_payload["points"]),
    }
    return _write_data_output(output_json, "gene_expression_plot", meta)


def create_diff_export_result(diff: DataObject, output_dir: Path, node_id: str) -> DataObject:
    diff_csv = Path(str(diff.meta["diff_result_file"]))
    export_csv = output_dir / f"{node_id}_export.csv"
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    shutil.copyfile(diff_csv, export_csv)
    top_rows = _read_diff_rows(diff_csv)[:20]
    _write_diff_export_html(html_path, diff.meta.get("comparison_label", "comparison"), export_csv.name, top_rows)
    _write_diff_export_preview(preview_path, diff.meta.get("comparison_label", "comparison"))
    meta = {
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "export_file": str(export_csv),
        "comparison_label": diff.meta.get("comparison_label", "comparison"),
        "row_count": int(diff.meta.get("tested_gene_count", 0)),
    }
    return _write_data_output(output_json, "diff_export", meta)


def _load_standardized_gene_vectors(
    matrix_path: Path,
    columns: list[SampleColumn],
    max_genes: int,
) -> list[list[float]]:
    candidates: list[tuple[float, list[float]]] = []
    with matrix_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)
        for row in reader:
            values = _values_at(row, columns)
            if len(values) != len(columns):
                continue
            variance = _variance(values)
            if variance <= 0:
                continue
            mean = fmean(values)
            scale = math.sqrt(variance)
            candidates.append((variance, [(value - mean) / scale for value in values]))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [values for _, values in candidates[:max_genes]]


def _sample_covariance(gene_vectors: list[list[float]], sample_count: int) -> list[list[float]]:
    covariance = [[0.0 for _ in range(sample_count)] for _ in range(sample_count)]
    for values in gene_vectors:
        for i, left in enumerate(values):
            row = covariance[i]
            for j in range(i, sample_count):
                row[j] += left * values[j]

    denom = max(len(gene_vectors) - 1, 1)
    for i in range(sample_count):
        for j in range(i, sample_count):
            value = covariance[i][j] / denom
            covariance[i][j] = value
            covariance[j][i] = value
    return covariance


def _principal_component(matrix: list[list[float]], iterations: int = 80) -> tuple[float, list[float]]:
    size = len(matrix)
    vector = [1.0 / math.sqrt(size) for _ in range(size)]
    for _ in range(iterations):
        next_vector = [sum(row[j] * vector[j] for j in range(size)) for row in matrix]
        norm = math.sqrt(sum(value * value for value in next_vector))
        if norm == 0:
            return 0.0, vector
        vector = [value / norm for value in next_vector]

    projected = [sum(row[j] * vector[j] for j in range(size)) for row in matrix]
    eigenvalue = sum(vector[i] * projected[i] for i in range(size))
    return eigenvalue, vector


def _deflate(
    matrix: list[list[float]],
    eigenvalue: float,
    vector: list[float],
) -> list[list[float]]:
    size = len(matrix)
    return [
        [matrix[i][j] - eigenvalue * vector[i] * vector[j] for j in range(size)]
        for i in range(size)
    ]


def _load_sample_columns(matrix_path: Path, metadata_path: Path) -> list[SampleColumn]:
    with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
        header = next(csv.reader(matrix_file))
    with metadata_path.open(encoding="utf-8-sig", newline="") as metadata_file:
        metadata = list(csv.DictReader(metadata_file))

    raw_columns = [
        SampleColumn(
            index=GENE_INFO_COLUMNS + idx,
            name=meta["sample"],
            condition=meta["condition"],
            group=meta.get("group", ""),
        )
        for idx, meta in enumerate(metadata)
        if GENE_INFO_COLUMNS + idx < len(header)
    ]

    counts: dict[str, int] = {}
    for item in raw_columns:
        counts[item.name] = counts.get(item.name, 0) + 1
    if not any(count > 1 for count in counts.values()):
        return raw_columns

    # The demo CSV contains raw and normalized blocks with duplicate sample names.
    # Use the last occurrence for each sample, which corresponds to the normalized block.
    last_by_name = {item.name: item for item in raw_columns}
    return list(last_by_name.values())


def _values_at(row: list[str], columns: list[SampleColumn]) -> list[float]:
    values = []
    for column in columns:
        if column.index >= len(row):
            continue
        try:
            values.append(float(row[column.index]))
        except ValueError:
            continue
    return values


def _variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = fmean(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def _welch_p_value(a: list[float], b: list[float]) -> float:
    var_a = _variance(a)
    var_b = _variance(b)
    denom = math.sqrt(var_a / len(a) + var_b / len(b))
    if denom == 0:
        return 1.0
    t_stat = abs((fmean(a) - fmean(b)) / denom)
    return math.erfc(t_stat / math.sqrt(2))


def _read_diff_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = []
        for row in csv.DictReader(file):
            rows.append(
                {
                    "gene": row["gene"],
                    "gene_id": row["gene_id"],
                    "log2fc": float(row["log2fc"]),
                    "p_value": float(row["p_value"]),
                    "neg_log10_p": float(row["neg_log10_p"]),
                }
            )
        return rows


def _extract_heatmap_values(
    matrix_path: Path,
    diff_rows: list[dict[str, Any]],
    columns: list[SampleColumn],
) -> list[dict[str, Any]]:
    wanted = {row["gene_id"] for row in diff_rows}
    order = {row["gene_id"]: index for index, row in enumerate(diff_rows)}
    found = []
    with matrix_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        next(reader)
        for row in reader:
            gene_id = row[1]
            if gene_id not in wanted:
                continue
            values = _values_at(row, columns)
            if not values:
                continue
            mean = fmean(values)
            var = math.sqrt(_variance(values)) or 1.0
            found.append(
                {
                    "gene": row[0] or gene_id,
                    "gene_id": gene_id,
                    "values": [round((value - mean) / var, 3) for value in values],
                }
            )
    return sorted(found, key=lambda item: order[item["gene_id"]])


def _load_sample_series(matrix_path: Path, columns: list[SampleColumn]) -> list[list[float]]:
    series = [[] for _ in columns]
    with matrix_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)
        for row in reader:
            for index, column in enumerate(columns):
                if column.index >= len(row):
                    continue
                try:
                    series[index].append(float(row[column.index]))
                except ValueError:
                    continue
    return series


def _sample_qc_stats(column: SampleColumn, values: list[float]) -> dict[str, Any]:
    sorted_values = sorted(values)
    return {
        "sample": column.name,
        "condition": column.condition,
        "group": column.group,
        "count": len(values),
        "mean": round(fmean(values) if values else 0.0, 4),
        "median": round(_quantile(sorted_values, 0.5), 4),
        "q1": round(_quantile(sorted_values, 0.25), 4),
        "q3": round(_quantile(sorted_values, 0.75), 4),
        "min": round(sorted_values[0], 4) if sorted_values else 0.0,
        "max": round(sorted_values[-1], 4) if sorted_values else 0.0,
        "zero_ratio": round(_safe_ratio(sum(value == 0 for value in values), len(values)), 4),
        "total": round(sum(values), 4),
    }


def _top_variable_heatmap_genes(
    matrix_path: Path,
    columns: list[SampleColumn],
    top_n: int,
) -> list[dict[str, Any]]:
    ranked: list[tuple[float, dict[str, Any]]] = []
    with matrix_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)
        for row in reader:
            values = _values_at(row, columns)
            if len(values) != len(columns):
                continue
            variance = _variance(values)
            if variance <= 0:
                continue
            mean = fmean(values)
            scale = math.sqrt(variance) or 1.0
            ranked.append(
                (
                    variance,
                    {
                        "gene": row[0] or row[1],
                        "gene_id": row[1] or row[0],
                        "values": [round((value - mean) / scale, 3) for value in values],
                    },
                )
            )
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in ranked[:top_n]]


def _order_samples_by_condition(columns: list[SampleColumn]) -> list[SampleColumn]:
    return sorted(columns, key=lambda item: (item.condition, item.group, item.name))


def _find_gene_expression(
    matrix_path: Path,
    columns: list[SampleColumn],
    gene_query: str,
) -> dict[str, Any]:
    query = gene_query.lower()
    with matrix_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)
        for row in reader:
            gene = (row[0] or "").strip()
            gene_id = (row[1] or "").strip()
            if query not in {gene.lower(), gene_id.lower()}:
                continue
            points = []
            for column in columns:
                if column.index >= len(row):
                    continue
                try:
                    value = float(row[column.index])
                except ValueError:
                    continue
                points.append(
                    {
                        "sample": column.name,
                        "condition": column.condition,
                        "group": column.group,
                        "value": round(value, 4),
                    }
                )
            grouped = {}
            for point in points:
                grouped.setdefault(point["condition"], []).append(point["value"])
            return {
                "gene": gene or gene_id,
                "gene_id": gene_id or gene,
                "points": points,
                "groups": {
                    key: {
                        "count": len(values),
                        "mean": round(fmean(values), 4),
                        "median": round(_quantile(sorted(values), 0.5), 4),
                    }
                    for key, values in grouped.items()
                },
            }
    raise ValueError(f"没有在表达矩阵中找到基因：{gene_query}")


def _quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return sorted_values[lower]
    weight = pos - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _pearson(left: list[float], right: list[float]) -> float:
    size = min(len(left), len(right))
    if size < 2:
        return 0.0
    a = left[:size]
    b = right[:size]
    mean_a = fmean(a)
    mean_b = fmean(b)
    num = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b, strict=False))
    den_a = math.sqrt(sum((x - mean_a) ** 2 for x in a))
    den_b = math.sqrt(sum((y - mean_b) ** 2 for y in b))
    if den_a == 0 or den_b == 0:
        return 0.0
    return num / (den_a * den_b)


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _write_volcano_html(path: Path, comparison: str, points: list[dict[str, Any]]) -> None:
    payload = json.dumps(points, ensure_ascii=False)
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Volcano {html.escape(comparison)}</title>
<style>
body{{margin:0;font-family:Georgia,'Noto Serif SC',serif;background:#fffaf0;color:#17211b}}
.wrap{{padding:24px}}
.plot-shell{{overflow:auto}}
canvas{{display:block;width:min(100%,1200px);height:auto;aspect-ratio:1200/640;border:1px solid #ded4c2;border-radius:18px;background:white}}
.tip{{position:fixed;display:none;padding:8px 10px;border-radius:10px;background:#17211b;color:white;font-size:12px;pointer-events:none}}
</style></head><body><div class="wrap"><h1>火山图：{html.escape(comparison)}</h1>
<p>悬停查看基因、log2FC 和 p 值。展示前 {len(points)} 个基因。</p><canvas id="plot" width="1200" height="640"></canvas></div><div class="tip" id="tip"></div>
<script>
const points = {payload};
const canvas = document.getElementById('plot');
const ctx = canvas.getContext('2d');
const tip = document.getElementById('tip');
const pad = 58;
const xs = points.map(p => p.x), ys = points.map(p => p.y);
const xmin = Math.min(...xs, -1), xmax = Math.max(...xs, 1), ymax = Math.max(...ys, 1);
function sx(x){{ return pad + (x - xmin) / (xmax - xmin) * (canvas.width - pad * 2); }}
function sy(y){{ return canvas.height - pad - y / ymax * (canvas.height - pad * 2); }}
ctx.clearRect(0,0,canvas.width,canvas.height);
ctx.strokeStyle = '#ded4c2'; ctx.lineWidth = 1;
ctx.beginPath(); ctx.moveTo(pad, canvas.height-pad); ctx.lineTo(canvas.width-pad, canvas.height-pad); ctx.moveTo(pad,pad); ctx.lineTo(pad,canvas.height-pad); ctx.stroke();
ctx.fillStyle = '#667067'; ctx.fillText('log2FC', canvas.width/2, canvas.height-18); ctx.fillText('-log10(p)', 12, 36);
for (const p of points) {{
  const strong = Math.abs(p.x) >= 1 && p.y >= 1.3;
  ctx.fillStyle = strong ? (p.x > 0 ? '#b93d2f' : '#2176c9') : 'rgba(15,107,87,.32)';
  ctx.beginPath(); ctx.arc(sx(p.x), sy(p.y), strong ? 3.2 : 2.1, 0, Math.PI*2); ctx.fill();
}}
canvas.addEventListener('mousemove', ev => {{
  const rect = canvas.getBoundingClientRect();
  const x = (ev.clientX - rect.left) * canvas.width / rect.width;
  const y = (ev.clientY - rect.top) * canvas.height / rect.height;
  let best = null, bd = 999;
  for (const p of points) {{
    const dx = sx(p.x)-x, dy = sy(p.y)-y, d = dx*dx+dy*dy;
    if (d < bd) {{ best = p; bd = d; }}
  }}
  if (best && bd < 90) {{
    tip.style.display = 'block'; tip.style.left = ev.clientX + 12 + 'px'; tip.style.top = ev.clientY + 12 + 'px';
    tip.innerHTML = `${{best.gene}}<br>log2FC=${{best.x}}<br>p=${{Number(best.p).toExponential(2)}}`;
  }} else tip.style.display = 'none';
}});
</script></body></html>""",
        encoding="utf-8",
    )


def _write_heatmap_html(
    path: Path,
    comparison: str,
    columns: list[SampleColumn],
    genes: list[dict[str, Any]],
) -> None:
    payload = json.dumps({"samples": [c.name for c in columns], "genes": genes}, ensure_ascii=False)
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Heatmap {html.escape(comparison)}</title>
<style>
body{{margin:0;font-family:Georgia,'Noto Serif SC',serif;background:#fffaf0;color:#17211b}}
.wrap{{padding:24px}}canvas{{border:1px solid #ded4c2;border-radius:18px;background:white;max-width:100%}}
.tip{{position:fixed;display:none;padding:8px 10px;border-radius:10px;background:#17211b;color:white;font-size:12px;pointer-events:none}}
</style></head><body><div class="wrap"><h1>热图：{html.escape(comparison)}</h1>
<p>Top {len(genes)} 差异基因，数值为按基因标准化后的表达。悬停查看单元格。</p><canvas id="heatmap"></canvas></div><div class="tip" id="tip"></div>
<script>
const data = {payload};
const cell = 16, left = 130, topPad = 34;
const canvas = document.getElementById('heatmap');
const tip = document.getElementById('tip');
canvas.width = left + data.samples.length * cell + 24;
canvas.height = topPad + data.genes.length * cell + 28;
const ctx = canvas.getContext('2d');
function color(v) {{
  const x = Math.max(-2, Math.min(2, v)) / 2;
  if (x >= 0) return `rgb(${{Math.round(245*x+245*(1-x))}},${{Math.round(245*(1-x)+88*x)}},${{Math.round(245*(1-x)+70*x)}})`;
  return `rgb(${{Math.round(245*(1+x)+55*(-x))}},${{Math.round(245*(1+x)+118*(-x))}},${{Math.round(245*(1+x)+196*(-x))}})`;
}}
ctx.fillStyle = '#667067'; ctx.font = '11px Georgia';
data.genes.forEach((g, r) => {{
  ctx.fillStyle = '#17211b'; ctx.fillText(g.gene.slice(0,18), 10, topPad + r*cell + 12);
  g.values.forEach((v, c) => {{
    ctx.fillStyle = color(v); ctx.fillRect(left+c*cell, topPad+r*cell, cell-1, cell-1);
  }});
}});
canvas.addEventListener('mousemove', ev => {{
  const rect = canvas.getBoundingClientRect();
  const x = (ev.clientX - rect.left) * canvas.width / rect.width;
  const y = (ev.clientY - rect.top) * canvas.height / rect.height;
  const c = Math.floor((x-left)/cell), r = Math.floor((y-topPad)/cell);
  if (r>=0 && r<data.genes.length && c>=0 && c<data.samples.length) {{
    const g = data.genes[r], v = g.values[c];
    tip.style.display='block'; tip.style.left=ev.clientX+12+'px'; tip.style.top=ev.clientY+12+'px';
    tip.innerHTML = `${{g.gene}}<br>${{data.samples[c]}}<br>z=${{v}}`;
  }} else tip.style.display='none';
}});
</script></body></html>""",
        encoding="utf-8",
    )


def _write_volcano_preview(path: Path, points: list[dict[str, Any]], comparison: str) -> None:
    sample = points[:600]
    xs = [p["x"] for p in sample] or [0]
    ys = [p["y"] for p in sample] or [0]
    xmin, xmax, ymax = min(xs + [-1]), max(xs + [1]), max(ys + [1])
    circles = []
    for p in sample:
        x = 16 + (p["x"] - xmin) / (xmax - xmin) * 188
        y = 104 - p["y"] / ymax * 88
        color = "#b93d2f" if abs(p["x"]) >= 1 and p["y"] >= 1.3 else "#0f6b57"
        circles.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.7" fill="{color}" opacity=".55"/>')
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#fffaf0"/><text x="12" y="18" font-size="11" fill="#17211b">火山图 {html.escape(comparison)}</text>{"".join(circles)}</svg>',
        encoding="utf-8",
    )


def _write_heatmap_preview(path: Path, comparison: str, genes: list[dict[str, Any]]) -> None:
    rects = []
    cell = 5
    for r, gene in enumerate(genes[:18]):
        for c, value in enumerate(gene["values"][:34]):
            x = 14 + c * cell
            y = 24 + r * cell
            v = max(-2, min(2, float(value))) / 2
            color = "#d94f40" if v >= 0 else "#3776c4"
            rects.append(f'<rect x="{x}" y="{y}" width="4" height="4" fill="{color}" opacity="{0.25 + abs(v)*0.65:.2f}"/>')
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#fffaf0"/><text x="12" y="17" font-size="11" fill="#17211b">热图 {html.escape(comparison)}</text>{"".join(rects)}</svg>',
        encoding="utf-8",
    )


def _write_pca_html(
    path: Path,
    points: list[dict[str, Any]],
    explained: dict[str, float],
    gene_count: int,
) -> None:
    payload = json.dumps(points, ensure_ascii=False)
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>PCA</title>
<style>
body{{margin:0;font-family:Georgia,'Noto Serif SC',serif;background:#fffaf0;color:#17211b}}
.wrap{{padding:24px}}
.plot-shell{{overflow:auto}}
canvas{{display:block;width:min(100%,1200px);height:auto;aspect-ratio:1200/640;border:1px solid #ded4c2;border-radius:18px;background:white}}
.legend{{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0 18px}}
.legend span{{display:inline-flex;align-items:center;gap:6px;padding:5px 9px;border:1px solid #e3d6c2;border-radius:999px;background:#fff}}
.dot{{width:10px;height:10px;border-radius:50%;display:inline-block}}
.tip{{position:fixed;display:none;padding:8px 10px;border-radius:10px;background:#17211b;color:white;font-size:12px;pointer-events:none}}
</style></head><body><div class="wrap"><h1>PCA 样本分布</h1>
<p>基于表达矩阵中方差最高的 {gene_count} 个基因计算。悬停查看样本、分组和坐标。</p>
<div class="legend" id="legend"></div><div class="plot-shell"><canvas id="plot" width="1200" height="640"></canvas></div></div><div class="tip" id="tip"></div>
<script>
const points = {payload};
const explained = {json.dumps(explained)};
const palette = ['#b93d2f','#2176c9','#0f6b57','#d58b22','#7557a8','#455a64','#9f4b6b'];
const conditions = [...new Set(points.map(p => p.condition))];
const colorByCondition = Object.fromEntries(conditions.map((condition, index) => [condition, palette[index % palette.length]]));
const canvas = document.getElementById('plot');
const ctx = canvas.getContext('2d');
const tip = document.getElementById('tip');
const legend = document.getElementById('legend');
legend.innerHTML = conditions.map(c => `<span><i class="dot" style="background:${{colorByCondition[c]}}"></i>${{c}}</span>`).join('');
const pad = 64;
const xs = points.map(p => p.pc1), ys = points.map(p => p.pc2);
const xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys);
const xspan = xmax - xmin || 1, yspan = ymax - ymin || 1;
function sx(x){{ return pad + (x - xmin + xspan * 0.08) / (xspan * 1.16) * (canvas.width - pad * 2); }}
function sy(y){{ return canvas.height - pad - (y - ymin + yspan * 0.08) / (yspan * 1.16) * (canvas.height - pad * 2); }}
function draw() {{
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.strokeStyle = '#ded4c2'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(pad, canvas.height-pad); ctx.lineTo(canvas.width-pad, canvas.height-pad); ctx.moveTo(pad,pad); ctx.lineTo(pad,canvas.height-pad); ctx.stroke();
  ctx.fillStyle = '#667067'; ctx.font = '15px Georgia';
  ctx.fillText(`PC1 (${{explained.pc1}}%)`, canvas.width / 2 - 38, canvas.height - 20);
  ctx.save(); ctx.translate(24, canvas.height / 2 + 38); ctx.rotate(-Math.PI / 2); ctx.fillText(`PC2 (${{explained.pc2}}%)`, 0, 0); ctx.restore();
  for (const p of points) {{
    ctx.fillStyle = colorByCondition[p.condition] || '#0f6b57';
    ctx.beginPath(); ctx.arc(sx(p.pc1), sy(p.pc2), 6, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = 'rgba(23,33,27,.28)'; ctx.stroke();
  }}
}}
draw();
window.addEventListener('resize', draw);
canvas.addEventListener('mousemove', ev => {{
  const rect = canvas.getBoundingClientRect();
  const x = (ev.clientX - rect.left) * canvas.width / rect.width;
  const y = (ev.clientY - rect.top) * canvas.height / rect.height;
  let best = null, bd = 999;
  for (const p of points) {{
    const dx = sx(p.pc1)-x, dy = sy(p.pc2)-y, d = dx*dx+dy*dy;
    if (d < bd) {{ best = p; bd = d; }}
  }}
  if (best && bd < 160) {{
    tip.style.display = 'block'; tip.style.left = ev.clientX + 12 + 'px'; tip.style.top = ev.clientY + 12 + 'px';
    tip.innerHTML = `${{best.sample}}<br>${{best.condition}} / ${{best.group}}<br>PC1=${{best.pc1}}<br>PC2=${{best.pc2}}`;
  }} else tip.style.display = 'none';
}});
</script></body></html>""",
        encoding="utf-8",
    )


def _write_pca_preview(path: Path, points: list[dict[str, Any]]) -> None:
    xs = [p["pc1"] for p in points] or [0]
    ys = [p["pc2"] for p in points] or [0]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    xspan = xmax - xmin or 1
    yspan = ymax - ymin or 1
    palette = ["#b93d2f", "#2176c9", "#0f6b57", "#d58b22", "#7557a8", "#455a64", "#9f4b6b"]
    conditions = []
    for point in points:
        if point["condition"] not in conditions:
            conditions.append(point["condition"])
    colors = {condition: palette[index % len(palette)] for index, condition in enumerate(conditions)}
    circles = []
    for point in points:
        x = 18 + (point["pc1"] - xmin + xspan * 0.08) / (xspan * 1.16) * 184
        y = 106 - (point["pc2"] - ymin + yspan * 0.08) / (yspan * 1.16) * 84
        circles.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{colors[point["condition"]]}" opacity=".78"/>'
        )
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#fffaf0"/><text x="12" y="17" font-size="11" fill="#17211b">PCA 样本分布</text><line x1="18" y1="106" x2="204" y2="106" stroke="#ded4c2"/><line x1="18" y1="22" x2="18" y2="106" stroke="#ded4c2"/>{"".join(circles)}</svg>',
        encoding="utf-8",
    )


def _write_qc_html(path: Path, stats: list[dict[str, Any]]) -> None:
    payload = json.dumps(stats, ensure_ascii=False)
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>QC</title>
<style>
body{{margin:0;font-family:Georgia,'Noto Serif SC',serif;background:#fffaf0;color:#17211b}}
.wrap{{padding:24px}}canvas{{display:block;max-width:100%;border:1px solid #ded4c2;border-radius:18px;background:white}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:0 0 18px}}
.card{{padding:12px 14px;border:1px solid #e3d6c2;border-radius:16px;background:#fff}}
</style></head><body><div class="wrap"><h1>表达矩阵 QC</h1><div class="grid" id="summary"></div><canvas id="plot" width="1200" height="620"></canvas></div>
<script>
const stats = {payload};
const summary = document.getElementById('summary');
const sampleCount = stats.length;
const meanTotal = stats.reduce((s, x) => s + x.total, 0) / Math.max(sampleCount, 1);
const meanZero = stats.reduce((s, x) => s + x.zero_ratio, 0) / Math.max(sampleCount, 1);
summary.innerHTML = `
  <div class="card"><strong>样本数</strong><div>${{sampleCount}}</div></div>
  <div class="card"><strong>平均总表达</strong><div>${{meanTotal.toFixed(2)}}</div></div>
  <div class="card"><strong>平均零值比例</strong><div>${{(meanZero*100).toFixed(1)}}%</div></div>
`;
const canvas = document.getElementById('plot');
const ctx = canvas.getContext('2d');
const pad = 56, bottom = canvas.height - 70, left = 90, width = canvas.width - 140;
const values = stats.map(x => x.median);
const vmax = Math.max(...stats.map(x => x.max), 1);
ctx.strokeStyle = '#ded4c2'; ctx.beginPath(); ctx.moveTo(left, 30); ctx.lineTo(left, bottom); ctx.lineTo(left + width, bottom); ctx.stroke();
ctx.fillStyle = '#667067'; ctx.fillText('样本表达分布（箱线近似）', left, 18);
stats.forEach((item, index) => {{
  const x = left + (index + 0.5) / stats.length * width;
  const sy = v => bottom - v / vmax * (bottom - 40);
  ctx.strokeStyle = '#0f6b57';
  ctx.beginPath(); ctx.moveTo(x, sy(item.min)); ctx.lineTo(x, sy(item.max)); ctx.stroke();
  ctx.fillStyle = 'rgba(15,107,87,.18)';
  ctx.fillRect(x - 7, sy(item.q3), 14, Math.max(3, sy(item.q1) - sy(item.q3)));
  ctx.strokeRect(x - 7, sy(item.q3), 14, Math.max(3, sy(item.q1) - sy(item.q3)));
  ctx.fillStyle = '#b93d2f';
  ctx.fillRect(x - 8, sy(item.median) - 1, 16, 2);
}});
</script></body></html>""",
        encoding="utf-8",
    )


def _write_qc_preview(path: Path, stats: list[dict[str, Any]]) -> None:
    bars = []
    max_total = max((item["total"] for item in stats), default=1)
    for index, item in enumerate(stats[:20]):
        height = item["total"] / max_total * 60
        bars.append(f'<rect x="{16 + index * 9}" y="{92 - height:.1f}" width="6" height="{height:.1f}" fill="#0f6b57" opacity=".65"/>')
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#fffaf0"/><text x="12" y="17" font-size="11" fill="#17211b">表达矩阵 QC</text>{"".join(bars)}</svg>',
        encoding="utf-8",
    )


def _write_correlation_html(path: Path, columns: list[SampleColumn], matrix: list[list[float]]) -> None:
    payload = json.dumps({"samples": [item.name for item in columns], "matrix": matrix}, ensure_ascii=False)
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Correlation</title>
<style>body{{margin:0;font-family:Georgia,'Noto Serif SC',serif;background:#fffaf0;color:#17211b}}.wrap{{padding:24px}}canvas{{border:1px solid #ded4c2;border-radius:18px;background:white;max-width:100%}}</style>
</head><body><div class="wrap"><h1>样本相关性热图</h1><canvas id="plot"></canvas></div>
<script>
const data = {payload};
const cell = 18, pad = 140;
const canvas = document.getElementById('plot');
canvas.width = pad + data.samples.length * cell + 24;
canvas.height = pad + data.samples.length * cell + 24;
const ctx = canvas.getContext('2d');
function color(v) {{
  const x = (Math.max(-1, Math.min(1, v)) + 1) / 2;
  const r = Math.round(55 * (1 - x) + 217 * x);
  const g = Math.round(118 * (1 - x) + 79 * x);
  const b = Math.round(196 * (1 - x) + 64 * x);
  return `rgb(${{r}},${{g}},${{b}})`;
}}
data.samples.forEach((sample, i) => {{
  ctx.save(); ctx.translate(pad + i * cell + 9, 118); ctx.rotate(-Math.PI / 4); ctx.fillText(sample.slice(0,14), 0, 0); ctx.restore();
  ctx.fillText(sample.slice(0,14), 10, pad + i * cell + 12);
  data.matrix[i].forEach((v, j) => {{
    ctx.fillStyle = color(v); ctx.fillRect(pad + j*cell, pad + i*cell, cell-1, cell-1);
  }});
}});
</script></body></html>""",
        encoding="utf-8",
    )


def _write_correlation_preview(path: Path, matrix: list[list[float]]) -> None:
    rects = []
    for r, row in enumerate(matrix[:18]):
        for c, value in enumerate(row[:18]):
            opacity = 0.25 + abs(value) * 0.65
            color = "#d94f40" if value >= 0 else "#3776c4"
            rects.append(f'<rect x="{18 + c*5}" y="{24 + r*5}" width="4" height="4" fill="{color}" opacity="{opacity:.2f}"/>')
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#fffaf0"/><text x="12" y="17" font-size="11" fill="#17211b">样本相关性</text>{"".join(rects)}</svg>',
        encoding="utf-8",
    )


def _write_gene_expression_html(path: Path, gene_payload: dict[str, Any]) -> None:
    payload = json.dumps(gene_payload, ensure_ascii=False)
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Gene Expression</title>
<style>body{{margin:0;font-family:Georgia,'Noto Serif SC',serif;background:#fffaf0;color:#17211b}}.wrap{{padding:24px}}canvas{{border:1px solid #ded4c2;border-radius:18px;background:white;max-width:100%}}</style>
</head><body><div class="wrap"><h1>单基因表达：{html.escape(str(gene_payload["gene"]))}</h1><p>{html.escape(str(gene_payload["gene_id"]))}</p><canvas id="plot" width="1200" height="620"></canvas></div>
<script>
const data = {payload};
const canvas = document.getElementById('plot');
const ctx = canvas.getContext('2d');
const groups = Object.entries(data.groups);
const pad = 80, bottom = canvas.height - 70, left = 90, width = canvas.width - 150;
const vmax = Math.max(...data.points.map(x => x.value), 1);
ctx.strokeStyle = '#ded4c2'; ctx.beginPath(); ctx.moveTo(left, 30); ctx.lineTo(left, bottom); ctx.lineTo(left + width, bottom); ctx.stroke();
groups.forEach(([name, info], index) => {{
  const x = left + (index + 0.5) / groups.length * width;
  ctx.fillStyle = '#17211b'; ctx.fillText(name, x - 14, bottom + 20);
  ctx.fillStyle = '#0f6b57';
  const y = bottom - info.mean / vmax * (bottom - 40);
  ctx.beginPath(); ctx.arc(x, y, 8, 0, Math.PI * 2); ctx.fill();
  data.points.filter(p => p.condition === name).forEach((point, offset) => {{
    const sx = x - 18 + (offset % 7) * 6;
    const sy = bottom - point.value / vmax * (bottom - 40);
    ctx.fillStyle = 'rgba(185,61,47,.55)';
    ctx.beginPath(); ctx.arc(sx, sy, 3, 0, Math.PI * 2); ctx.fill();
  }});
}});
</script></body></html>""",
        encoding="utf-8",
    )


def _write_gene_expression_preview(path: Path, gene_payload: dict[str, Any]) -> None:
    circles = []
    groups = list(gene_payload["groups"].items())
    max_mean = max((item["mean"] for _, item in groups), default=1)
    for index, (name, item) in enumerate(groups[:6]):
        x = 36 + index * 28
        y = 90 - item["mean"] / max_mean * 48
        circles.append(f'<circle cx="{x}" cy="{y:.1f}" r="6" fill="#0f6b57" opacity=".72"/>')
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#fffaf0"/><text x="12" y="17" font-size="11" fill="#17211b">{html.escape(str(gene_payload["gene"]))}</text>{"".join(circles)}</svg>',
        encoding="utf-8",
    )


def _write_diff_export_html(path: Path, comparison: str, export_name: str, rows: list[dict[str, Any]]) -> None:
    rows_html = "".join(
        f"<tr><td>{html.escape(row['gene'])}</td><td>{row['log2fc']:.3f}</td><td>{row['p_value']:.3e}</td></tr>"
        for row in rows
    )
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Diff Export</title>
<style>body{{margin:0;font-family:Georgia,'Noto Serif SC',serif;background:#fffaf0;color:#17211b}}.wrap{{padding:24px}}table{{width:100%;border-collapse:collapse;background:white;border-radius:16px;overflow:hidden}}td,th{{padding:8px 10px;border-bottom:1px solid #eee}}</style>
</head><body><div class="wrap"><h1>差异结果导出：{html.escape(comparison)}</h1><p><a href="{html.escape(export_name)}">下载 CSV 结果表</a></p><table><thead><tr><th>Gene</th><th>log2FC</th><th>p-value</th></tr></thead><tbody>{rows_html}</tbody></table></div></body></html>""",
        encoding="utf-8",
    )


def _write_diff_export_preview(path: Path, comparison: str) -> None:
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#fffaf0"/><text x="12" y="17" font-size="11" fill="#17211b">结果导出</text><rect x="28" y="30" width="164" height="62" rx="10" fill="#fff" stroke="#ded4c2"/><line x1="40" y1="50" x2="180" y2="50" stroke="#0f6b57"/><line x1="40" y1="64" x2="168" y2="64" stroke="#d2cabd"/><line x1="40" y1="76" x2="152" y2="76" stroke="#d2cabd"/></svg>',
        encoding="utf-8",
    )


def _write_data_output(path: Path, output_type: str, meta: dict[str, Any]) -> DataObject:
    output = DataObject(type=output_type, data=str(path), meta=meta)
    path.write_text(output.model_dump_json(indent=2), encoding="utf-8")
    return output


def _write_json_detail(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
