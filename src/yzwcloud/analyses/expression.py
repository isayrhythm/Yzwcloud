from __future__ import annotations

import csv
import html
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import fmean
from typing import Any

from yzwcloud.analyses.common import (
    SampleColumn,
    load_sample_columns,
    load_sample_series,
    pearson,
    quantile,
    safe_ratio,
    values_at,
    variance,
    write_data_output,
)
from yzwcloud.analyses.rendering import write_heatmap_html, write_heatmap_preview
from yzwcloud.color_palette import condition_color_map
from yzwcloud.models import DataObject


def create_pca_result(source: DataObject, output_dir: Path, node_id: str) -> DataObject:
    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    sample_columns = load_sample_columns(matrix_path, metadata_path)
    gene_vectors = load_standardized_gene_vectors(matrix_path, sample_columns, max_genes=2000)
    if len(gene_vectors) < 2 or len(sample_columns) < 2:
        raise ValueError("PCA 需要至少 2 个样本和 2 个可用基因")

    covariance = sample_covariance(gene_vectors, len(sample_columns))
    pc1_value, pc1_vector = principal_component(covariance)
    covariance = deflate(covariance, pc1_value, pc1_vector)
    pc2_value, pc2_vector = principal_component(covariance)
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

    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    html_path = output_dir / f"{node_id}_{run_stamp}.html"
    preview_path = output_dir / f"{node_id}_{run_stamp}_preview.svg"
    output_json = output_dir / f"{node_id}_{run_stamp}_output.json"
    scores_path = output_dir / f"{node_id}_{run_stamp}_scores.csv"
    explained = {
        "pc1": round(max(pc1_value, 0.0) / total_variance * 100, 2),
        "pc2": round(max(pc2_value, 0.0) / total_variance * 100, 2),
    }

    condition_colors = source.meta.get("condition_colors") or condition_color_map(source.meta.get("conditions") or [])
    write_pca_scores_table(scores_path, points)
    write_pca_html(html_path, points, explained, len(gene_vectors), condition_colors=condition_colors)
    write_pca_preview(preview_path, points)
    meta = {
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "pca_scores_file": str(scores_path),
        "sample_count": len(sample_columns),
        "gene_count": len(gene_vectors),
        "explained_variance": explained,
        "method": "sample_covariance_power_iteration",
        "condition_colors": condition_colors,
    }
    return write_data_output(output_json, "pca_plot", meta)


def create_qc_result(
    source: DataObject,
    output_dir: Path,
    node_id: str,
    params: dict[str, Any] | None = None,
) -> DataObject:
    qc_params = resolve_qc_params(params or {})
    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    sample_columns = load_sample_columns(matrix_path, metadata_path)
    series = load_sample_series(matrix_path, sample_columns)
    stats = [sample_qc_stats(column, values) for column, values in zip(sample_columns, series, strict=False)]
    median_total = quantile(sorted(item["total"] for item in stats), 0.5) if stats else 0.0
    min_total = median_total * float(qc_params["min_total_ratio"])
    max_values = sorted(item["max"] for item in stats)
    max_q1 = quantile(max_values, 0.25) if max_values else 0.0
    max_q3 = quantile(max_values, 0.75) if max_values else 0.0
    max_iqr = max_q3 - max_q1
    max_value_upper = max_q3 + float(qc_params["max_value_iqr_multiplier"]) * max_iqr
    distribution_scores = robust_distribution_scores(stats)
    after_stats = []
    for item in stats:
        reasons = []
        distribution_score = distribution_scores.get(item["sample"], 0.0)
        item["distribution_mad_score"] = round(distribution_score, 3)
        item["max_value_upper"] = round(max_value_upper, 4)
        if item["total"] < min_total:
            reasons.append("low_total")
        if item["zero_ratio"] > float(qc_params["max_zero_ratio"]):
            reasons.append("high_zero_ratio")
        if item["detected_genes"] < int(qc_params["min_detected_genes"]):
            reasons.append("low_detected_genes")
        if distribution_score > float(qc_params["max_distribution_mad"]):
            reasons.append("expression_distribution_outlier")
        if item["max"] > max_value_upper:
            reasons.append("high_max_expression_outlier")
        item["qc_pass"] = not reasons
        item["qc_reasons"] = reasons
        if item["qc_pass"]:
            after_stats.append(item)
    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    html_path = output_dir / f"{node_id}_{run_stamp}.html"
    preview_path = output_dir / f"{node_id}_{run_stamp}_preview.svg"
    output_json = output_dir / f"{node_id}_{run_stamp}_output.json"
    filtered_metadata_path = output_dir / f"{node_id}_{run_stamp}_passed_samples.csv"
    passed_names = {item["sample"] for item in after_stats}
    passed_columns = [column for column in sample_columns if column.name in passed_names]
    with filtered_metadata_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["sample", "group", "condition"])
        writer.writeheader()
        writer.writerows(
            {
                "sample": column.name,
                "group": column.group,
                "condition": column.condition,
            }
            for column in passed_columns
        )
    passed_conditions = {}
    for column in passed_columns:
        passed_conditions[column.condition] = passed_conditions.get(column.condition, 0) + 1
    write_qc_html(html_path, stats, after_stats, qc_params)
    write_qc_preview(preview_path, stats, after_stats)
    meta = {
        "matrix_file": str(matrix_path),
        "sample_metadata_file": str(filtered_metadata_path),
        "source_sample_metadata_file": str(metadata_path),
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "sample_count": len(stats),
        "passed_sample_count": len(after_stats),
        "failed_sample_count": len(stats) - len(after_stats),
        "passed_samples": [column.name for column in passed_columns],
        "conditions": passed_conditions,
        "condition_options": sorted(passed_conditions),
        "condition_colors": condition_color_map(
            passed_conditions,
            source.meta.get("condition_colors") or {},
        ),
        "metric_count": 5,
        "run_id": run_stamp,
        "params": qc_params,
        "thresholds": {
            "min_total": round(min_total, 4),
            "max_distribution_mad": float(qc_params["max_distribution_mad"]),
            "max_value_upper": round(max_value_upper, 4),
        },
    }
    return write_data_output(output_json, "qc_report", meta)


def resolve_qc_params(params: dict[str, Any]) -> dict[str, Any]:
    presets = {
        "loose": {
            "min_total_ratio": 0.15,
            "max_zero_ratio": 0.7,
            "min_detected_genes": 500,
            "max_distribution_mad": 5.0,
            "max_value_iqr_multiplier": 3.0,
        },
        "normal": {
            "min_total_ratio": 0.25,
            "max_zero_ratio": 0.5,
            "min_detected_genes": 1000,
            "max_distribution_mad": 3.5,
            "max_value_iqr_multiplier": 1.5,
        },
        "strict": {
            "min_total_ratio": 0.4,
            "max_zero_ratio": 0.35,
            "min_detected_genes": 1500,
            "max_distribution_mad": 2.5,
            "max_value_iqr_multiplier": 1.0,
        },
    }
    preset = str(params.get("qc_preset") or "normal").lower()
    if preset not in presets:
        preset = "normal"
    resolved = {"qc_preset": preset, **presets[preset]}
    for key in [
        "min_total_ratio",
        "max_zero_ratio",
        "min_detected_genes",
        "max_distribution_mad",
        "max_value_iqr_multiplier",
    ]:
        if key in params and params[key] not in {None, ""}:
            resolved[key] = params[key]
    return resolved


def create_sample_correlation_result(source: DataObject, output_dir: Path, node_id: str) -> DataObject:
    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    sample_columns = load_sample_columns(matrix_path, metadata_path)
    series = load_sample_series(matrix_path, sample_columns)
    matrix = [[round(pearson(series[i], series[j]), 3) for j in range(len(sample_columns))] for i in range(len(sample_columns))]
    sample_order = order_samples_by_condition_cluster(sample_columns, series)
    sample_columns = [sample_columns[index] for index in sample_order]
    matrix = [[matrix[row_index][column_index] for column_index in sample_order] for row_index in sample_order]
    colors = condition_color_map(
        [column.condition for column in sample_columns],
        source.meta.get("condition_colors") or {},
    )
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    write_correlation_html(html_path, sample_columns, matrix, colors)
    write_correlation_preview(preview_path, matrix)
    meta = {
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "sample_count": len(sample_columns),
        "condition_colors": colors,
        "sample_ordering": "condition_blocks_within_group_clustering",
    }
    return write_data_output(output_json, "sample_correlation_plot", meta)


def create_expression_heatmap_result(
    source: DataObject,
    output_dir: Path,
    node_id: str,
    params: dict[str, Any] | None = None,
) -> DataObject:
    params = params or {}
    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    sample_columns = load_sample_columns(matrix_path, metadata_path)
    selected_conditions = [str(item) for item in params.get("selected_conditions") or [] if str(item)]
    if selected_conditions:
        selected_set = set(selected_conditions)
        sample_columns = [column for column in sample_columns if column.condition in selected_set]
    if len(sample_columns) < 2:
        raise ValueError("Expression heatmap needs at least 2 selected samples")
    top_n = int(params.get("top_genes") or 40)
    genes = top_variable_heatmap_genes(matrix_path, sample_columns, top_n=top_n)
    sample_cluster = hierarchical_cluster(transpose([gene["values"] for gene in genes]))
    sample_order = sample_cluster["order"]
    ordered_columns = [sample_columns[index] for index in sample_order]
    for gene in genes:
        gene["values"] = [gene["values"][index] for index in sample_order]
    gene_cluster = hierarchical_cluster([gene["values"] for gene in genes])
    gene_order = gene_cluster["order"]
    genes = [genes[index] for index in gene_order]
    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    html_path = output_dir / f"{node_id}_{run_stamp}.html"
    preview_path = output_dir / f"{node_id}_{run_stamp}_preview.svg"
    output_json = output_dir / f"{node_id}_{run_stamp}_output.json"
    plot_studio_table_path = output_dir / f"{node_id}_{run_stamp}_plot_studio_table.csv"
    condition_label = ", ".join(selected_conditions) if selected_conditions else "all samples"
    write_heatmap_plot_studio_table(plot_studio_table_path, ordered_columns, genes)
    write_heatmap_html(
        html_path,
        f"Clustered top variable genes: {condition_label}",
        ordered_columns,
        genes,
        row_tree=gene_cluster["tree"],
        col_tree=sample_cluster["tree"],
        condition_colors=condition_color_map(
            [column.condition for column in sample_columns],
            source.meta.get("condition_colors") or {},
        ),
    )
    write_heatmap_preview(preview_path, f"Clustered {condition_label}", genes)
    meta = {
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "plot_studio_table_file": str(plot_studio_table_path),
        "heatmap_table_file": str(plot_studio_table_path),
        "matrix_file": str(matrix_path),
        "sample_metadata_file": str(metadata_path),
        "gene_count": len(genes),
        "sample_count": len(ordered_columns),
        "selected_conditions": selected_conditions or sorted({column.condition for column in ordered_columns}),
        "top_genes": top_n,
        "clustered": True,
        "cluster_method": "average_linkage_pearson_distance",
        "condition_colors": condition_color_map(
            [column.condition for column in ordered_columns],
            source.meta.get("condition_colors") or {},
        ),
        "run_id": run_stamp,
    }
    return write_data_output(output_json, "expression_heatmap_plot", meta)


def create_gene_expression_result(
    source: DataObject,
    params: dict[str, Any],
    output_dir: Path,
    node_id: str,
) -> DataObject:
    gene_query = str(params.get("gene") or "").strip()
    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    sample_columns = load_sample_columns(matrix_path, metadata_path)
    auto_selected = False
    if gene_query.lower() in {"", "auto", "__auto__"}:
        gene_query = find_top_variable_gene(matrix_path, sample_columns)
        auto_selected = True
    gene_payload = find_gene_expression(matrix_path, sample_columns, gene_query)
    gene_payload["condition_colors"] = condition_color_map(
        [column.condition for column in sample_columns],
        source.meta.get("condition_colors") or {},
    )
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    plot_studio_table_path = output_dir / f"{node_id}_plot_studio_table.csv"
    write_gene_expression_plot_studio_table(plot_studio_table_path, gene_payload)
    write_gene_expression_html(html_path, gene_payload)
    write_gene_expression_preview(preview_path, gene_payload)
    meta = {
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "plot_studio_table_file": str(plot_studio_table_path),
        "gene_expression_table_file": str(plot_studio_table_path),
        "gene": gene_payload["gene"],
        "gene_id": gene_payload["gene_id"],
        "sample_count": len(gene_payload["points"]),
        "auto_selected": auto_selected,
        "selection_method": "top_variable_gene" if auto_selected else "manual",
    }
    return write_data_output(output_json, "gene_expression_plot", meta)


def load_standardized_gene_vectors(
    matrix_path: Path,
    columns: list[SampleColumn],
    max_genes: int,
) -> list[list[float]]:
    candidates: list[tuple[float, list[float]]] = []
    with matrix_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)
        for row in reader:
            values = values_at(row, columns)
            if len(values) != len(columns):
                continue
            row_variance = variance(values)
            if row_variance <= 0:
                continue
            mean = fmean(values)
            scale = math.sqrt(row_variance)
            candidates.append((row_variance, [(value - mean) / scale for value in values]))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [values for _, values in candidates[:max_genes]]


def sample_covariance(gene_vectors: list[list[float]], sample_count: int) -> list[list[float]]:
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


def principal_component(matrix: list[list[float]], iterations: int = 80) -> tuple[float, list[float]]:
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


def deflate(matrix: list[list[float]], eigenvalue: float, vector: list[float]) -> list[list[float]]:
    size = len(matrix)
    return [[matrix[i][j] - eigenvalue * vector[i] * vector[j] for j in range(size)] for i in range(size)]


def sample_qc_stats(column: SampleColumn, values: list[float]) -> dict[str, Any]:
    sorted_values = sorted(values)
    return {
        "sample": column.name,
        "condition": column.condition,
        "group": column.group,
        "count": len(values),
        "mean": round(fmean(values) if values else 0.0, 4),
        "median": round(quantile(sorted_values, 0.5), 4),
        "q1": round(quantile(sorted_values, 0.25), 4),
        "q3": round(quantile(sorted_values, 0.75), 4),
        "min": round(sorted_values[0], 4) if sorted_values else 0.0,
        "max": round(sorted_values[-1], 4) if sorted_values else 0.0,
        "zero_ratio": round(safe_ratio(sum(value == 0 for value in values), len(values)), 4),
        "detected_genes": sum(value > 0 for value in values),
        "total": round(sum(values), 4),
    }


def robust_distribution_scores(stats: list[dict[str, Any]]) -> dict[str, float]:
    metrics = ["total", "median", "q3", "max"]
    scores: dict[str, float] = {item["sample"]: 0.0 for item in stats}
    for metric in metrics:
        values = sorted(float(item.get(metric, 0.0)) for item in stats)
        center = quantile(values, 0.5) if values else 0.0
        deviations = sorted(abs(value - center) for value in values)
        mad = quantile(deviations, 0.5) if deviations else 0.0
        scale = mad * 1.4826 or 1.0
        for item in stats:
            sample = item["sample"]
            score = abs(float(item.get(metric, 0.0)) - center) / scale
            scores[sample] = max(scores[sample], score)
    return scores


def top_variable_heatmap_genes(
    matrix_path: Path,
    columns: list[SampleColumn],
    top_n: int,
) -> list[dict[str, Any]]:
    ranked: list[tuple[float, dict[str, Any]]] = []
    with matrix_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)
        for row in reader:
            values = values_at(row, columns)
            if len(values) != len(columns):
                continue
            row_variance = variance(values)
            if row_variance <= 0:
                continue
            mean = fmean(values)
            scale = math.sqrt(row_variance) or 1.0
            ranked.append(
                (
                    row_variance,
                    {
                        "gene": row[0] or row[1],
                        "gene_id": row[1] or row[0],
                        "values": [round((value - mean) / scale, 3) for value in values],
                    },
                )
            )
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in ranked[:top_n]]


def find_top_variable_gene(matrix_path: Path, columns: list[SampleColumn]) -> str:
    best: tuple[float, str] | None = None
    with matrix_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)
        for row in reader:
            values = values_at(row, columns)
            if len(values) != len(columns):
                continue
            row_variance = variance(values)
            if row_variance <= 0:
                continue
            gene = (row[0] if len(row) > 0 else "") or (row[1] if len(row) > 1 else "")
            gene = str(gene).strip()
            if not gene:
                continue
            if best is None or row_variance > best[0]:
                best = (row_variance, gene)
    if best is None:
        raise ValueError("表达矩阵中没有可用于单基因表达展示的变异基因")
    return best[1]


def write_heatmap_plot_studio_table(
    path: Path,
    columns: list[SampleColumn],
    genes: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["gene", "gene_id", *[column.name for column in columns]]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for gene in genes:
            values = list(gene.get("values") or [])
            row = {
                "gene": gene.get("gene") or gene.get("gene_id") or "",
                "gene_id": gene.get("gene_id") or gene.get("gene") or "",
            }
            row.update(
                {
                    column.name: values[index] if index < len(values) else ""
                    for index, column in enumerate(columns)
                }
            )
            writer.writerow(row)


def transpose(rows: list[list[float]]) -> list[list[float]]:
    if not rows:
        return []
    return [[row[index] for row in rows] for index in range(len(rows[0]))]


def cluster_order(vectors: list[list[float]]) -> list[int]:
    return hierarchical_cluster(vectors)["order"]


def hierarchical_cluster(vectors: list[list[float]]) -> dict[str, Any]:
    if not vectors:
        return {"order": [], "tree": {"leaf": 0, "height": 0.0}}
    if len(vectors) == 1:
        return {"order": [0], "tree": {"leaf": 0, "height": 0.0}}
    clusters = [{"items": [index], "tree": {"leaf": index, "height": 0.0}} for index in range(len(vectors))]
    while len(clusters) > 1:
        best_pair = (0, 1)
        best_distance = float("inf")
        for left_index in range(len(clusters)):
            for right_index in range(left_index + 1, len(clusters)):
                distance = average_cluster_distance(
                    clusters[left_index]["items"],
                    clusters[right_index]["items"],
                    vectors,
                )
                if distance < best_distance:
                    best_distance = distance
                    best_pair = (left_index, right_index)
        left_index, right_index = best_pair
        left_cluster = clusters[left_index]
        right_cluster = clusters[right_index]
        merged = {
            "items": left_cluster["items"] + right_cluster["items"],
            "tree": {
                "left": left_cluster["tree"],
                "right": right_cluster["tree"],
                "height": round(best_distance, 6),
            },
        }
        clusters = [
            cluster
            for index, cluster in enumerate(clusters)
            if index not in {left_index, right_index}
        ]
        clusters.append(merged)
    return {"order": clusters[0]["items"], "tree": clusters[0]["tree"]}


def average_cluster_distance(left: list[int], right: list[int], vectors: list[list[float]]) -> float:
    distances = [
        vector_distance(vectors[left_index], vectors[right_index])
        for left_index in left
        for right_index in right
    ]
    return sum(distances) / len(distances)


def vector_distance(left: list[float], right: list[float]) -> float:
    if len(left) == len(right) and len(left) >= 2:
        correlation = pearson(left, right)
        if math.isfinite(correlation):
            return 1 - correlation
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))


def order_samples_by_condition(columns: list[SampleColumn]) -> list[SampleColumn]:
    return sorted(columns, key=lambda item: (item.condition, item.group, item.name))


def order_samples_by_condition_cluster(columns: list[SampleColumn], series: list[list[float]]) -> list[int]:
    condition_order: list[str] = []
    for column in columns:
        if column.condition not in condition_order:
            condition_order.append(column.condition)

    ordered_indices: list[int] = []
    for condition in condition_order:
        condition_indices = [index for index, column in enumerate(columns) if column.condition == condition]
        if len(condition_indices) <= 2:
            ordered_indices.extend(condition_indices)
            continue
        local_order = cluster_order([series[index] for index in condition_indices])
        ordered_indices.extend(condition_indices[index] for index in local_order)
    return ordered_indices


def find_gene_expression(
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
                    key: {"count": len(values), "mean": round(fmean(values), 4), "median": round(quantile(sorted(values), 0.5), 4)}
                    for key, values in grouped.items()
                },
            }
    raise ValueError(f"没有在表达矩阵中找到基因：{gene_query}")


def write_pca_scores_table(path: Path, points: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["sample", "condition", "group", "pc1", "pc2"]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for point in points:
            writer.writerow({key: point.get(key, "") for key in fieldnames})


def write_gene_expression_plot_studio_table(path: Path, gene_payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["gene", "gene_id", "sample", "condition", "group", "value"]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for point in gene_payload.get("points") or []:
            writer.writerow(
                {
                    "gene": gene_payload.get("gene", ""),
                    "gene_id": gene_payload.get("gene_id", ""),
                    "sample": point.get("sample", ""),
                    "condition": point.get("condition", ""),
                    "group": point.get("group", ""),
                    "value": point.get("value", ""),
                }
            )


def write_pca_html(
    path: Path,
    points: list[dict[str, Any]],
    explained: dict[str, float],
    gene_count: int,
    condition_colors: dict[str, str] | None = None,
) -> None:
    payload = json.dumps(points, ensure_ascii=False)
    colors_payload = json.dumps(condition_colors or {}, ensure_ascii=False)
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
<p>基于表达矩阵中方差最高的 {gene_count} 个基因计算。悬停可查看样本、分组和坐标。</p>
<div class="legend" id="legend"></div><div class="plot-shell"><canvas id="plot" width="1200" height="640"></canvas></div></div><div class="tip" id="tip"></div>
<script>
const points = {payload};
const explained = {json.dumps(explained)};
const savedColors = {colors_payload};
const palette = ['#b93d2f','#2176c9','#0f6b57','#d58b22','#7557a8','#455a64','#9f4b6b'];
const conditions = [...new Set(points.map(p => p.condition))];
const colorByCondition = Object.fromEntries(conditions.map((condition, index) => [condition, savedColors[condition] || palette[index % palette.length]]));
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


def write_pca_preview(path: Path, points: list[dict[str, Any]]) -> None:
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
        circles.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{colors[point["condition"]]}" opacity=".78"/>')
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#fffaf0"/><text x="12" y="17" font-size="11" fill="#17211b">PCA 样本分布</text><line x1="18" y1="106" x2="204" y2="106" stroke="#ded4c2"/><line x1="18" y1="22" x2="18" y2="106" stroke="#ded4c2"/>{"".join(circles)}</svg>',
        encoding="utf-8",
    )


def write_qc_html(path: Path, stats: list[dict[str, Any]]) -> None:
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


def write_qc_preview(path: Path, stats: list[dict[str, Any]]) -> None:
    bars = []
    max_total = max((item["total"] for item in stats), default=1)
    for index, item in enumerate(stats[:20]):
        height = item["total"] / max_total * 60
        bars.append(f'<rect x="{16 + index * 9}" y="{92 - height:.1f}" width="6" height="{height:.1f}" fill="#0f6b57" opacity=".65"/>')
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#fffaf0"/><text x="12" y="17" font-size="11" fill="#17211b">表达矩阵 QC</text>{"".join(bars)}</svg>',
        encoding="utf-8",
    )


def write_qc_html(
    path: Path,
    before_stats: list[dict[str, Any]],
    after_stats: list[dict[str, Any]],
    params: dict[str, Any],
) -> None:
    payload = json.dumps({"before": before_stats, "after": after_stats, "params": params}, ensure_ascii=False)
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>QC</title>
<style>
body{{margin:0;font-family:Inter,'Segoe UI','Microsoft YaHei',sans-serif;background:#f5f9fc;color:#172635}}
.wrap{{padding:24px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:0 0 18px}}
.card{{padding:12px 14px;border:1px solid #d8e5ee;border-radius:12px;background:white}}
.plots{{display:grid;grid-template-columns:1fr;gap:18px}}canvas{{display:block;max-width:100%;border:1px solid #d8e5ee;border-radius:14px;background:white}}
.flagged{{margin-top:16px;border:1px solid #d8e5ee;border-radius:12px;background:white;overflow:hidden}}
.flagged table{{width:100%;border-collapse:collapse;font-size:13px}}.flagged th,.flagged td{{padding:8px 10px;border-bottom:1px solid #edf3f7;text-align:left}}
.pass{{color:#087a55}}.fail{{color:#bd3f32}}
.tip{{position:fixed;display:none;z-index:20;max-width:280px;padding:10px 12px;border-radius:10px;background:#172635;color:white;font-size:12px;line-height:1.5;box-shadow:0 12px 28px rgba(23,38,53,.22);pointer-events:none}}
</style></head><body><div class="wrap"><h1>Multi-sample QC</h1>
<div class="grid" id="summary"></div><div class="plots"><canvas id="before" width="1200" height="500"></canvas><canvas id="after" width="1200" height="500"></canvas></div>
<section class="flagged"><table><thead><tr><th>Sample</th><th>Condition</th><th>Status</th><th>Total</th><th>Zero %</th><th>Detected genes</th><th>Outlier / reason</th></tr></thead><tbody id="rows"></tbody></table></section>
</div><div class="tip" id="tip"></div><script>
const data = {payload};
const before = data.before;
const after = data.after;
const failed = before.filter(x => !x.qc_pass);
const tip = document.getElementById('tip');
const chartState = {{}};
const mean = (items, key) => items.reduce((s, x) => s + Number(x[key] || 0), 0) / Math.max(items.length, 1);
document.getElementById('summary').innerHTML = `
  <div class="card"><strong>Before QC</strong><div>${{before.length}} samples</div></div>
  <div class="card"><strong>After QC</strong><div>${{after.length}} samples</div></div>
  <div class="card"><strong>Flagged</strong><div>${{failed.length}} samples</div></div>
  <div class="card"><strong>Parameters</strong><div>total >= median * ${{data.params.min_total_ratio}}, zero <= ${{data.params.max_zero_ratio}}, detected >= ${{data.params.min_detected_genes}}, outlier score <= ${{data.params.max_distribution_mad}}, max <= Q3 + ${{data.params.max_value_iqr_multiplier}} * IQR</div></div>
`;
document.getElementById('rows').innerHTML = before.map(item => `
  <tr><td>${{item.sample}}</td><td>${{item.condition}}</td><td class="${{item.qc_pass ? 'pass' : 'fail'}}">${{item.qc_pass ? 'pass' : 'flagged'}}</td>
  <td>${{Number(item.total).toFixed(2)}}</td><td>${{(Number(item.zero_ratio)*100).toFixed(1)}}%</td><td>${{item.detected_genes}}</td><td>${{Number(item.distribution_mad_score || 0).toFixed(2)}} / ${{(item.qc_reasons || []).join(', ') || '-'}}</td></tr>
`).join('');
function draw(canvasId, items, title) {{
  const canvas = document.getElementById(canvasId), ctx = canvas.getContext('2d');
  const left = 116, right = 44, top = 72, bottom = 124, width = canvas.width - left - right, height = canvas.height - top - bottom;
  const boxes = [];
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.fillStyle = '#172635'; ctx.font = '18px Inter, sans-serif'; ctx.fillText(title, left, 25);
  ctx.strokeStyle = '#d8e5ee'; ctx.beginPath(); ctx.moveTo(left, top); ctx.lineTo(left, top+height); ctx.lineTo(left+width, top+height); ctx.stroke();
  ctx.fillStyle = '#172635'; ctx.font = '700 14px Inter, sans-serif';
  ctx.fillText('Y: expression value per gene', left, 52);
  ctx.fillText('X: samples ordered as input metadata', left + width / 2 - 128, top + height + 98);
  ctx.save();
  ctx.translate(28, top + height / 2 + 92);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText('expression value per gene', 0, 0);
  ctx.restore();
  const vmax = Math.max(...before.map(x => x.max), 1);
  const sy = v => top + height - Number(v || 0) / vmax * height;
  [0, 0.25, 0.5, 0.75, 1].forEach(fraction => {{
    const y = top + height - fraction * height;
    const value = fraction * vmax;
    ctx.strokeStyle = '#edf3f7'; ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(left + width, y); ctx.stroke();
    ctx.fillStyle = '#5f7284'; ctx.fillText(value.toFixed(0), 34, y + 4);
  }});
  items.forEach((item, index) => {{
    const x = left + (index + 0.5) / Math.max(items.length, 1) * width;
    ctx.strokeStyle = item.qc_pass ? '#0f8a8f' : '#bd3f32';
    ctx.fillStyle = item.qc_pass ? 'rgba(15,138,143,.18)' : 'rgba(189,63,50,.18)';
    ctx.beginPath(); ctx.moveTo(x, sy(item.min)); ctx.lineTo(x, sy(item.max)); ctx.stroke();
    const boxTop = sy(item.q3), boxHeight = Math.max(3, sy(item.q1) - sy(item.q3));
    ctx.fillRect(x - 6, boxTop, 12, boxHeight); ctx.strokeRect(x - 6, boxTop, 12, boxHeight);
    ctx.fillStyle = '#172635'; ctx.fillRect(x - 7, sy(item.median) - 1, 14, 2);
    boxes.push({{item, index, x, yTop: sy(item.max), yBottom: sy(item.min), boxTop, boxBottom: boxTop + boxHeight}});
  }});
  const tickEvery = Math.max(1, Math.ceil(items.length / 12));
  items.forEach((item, index) => {{
    if (index % tickEvery !== 0 && index !== items.length - 1) return;
    const x = left + (index + 0.5) / Math.max(items.length, 1) * width;
    ctx.strokeStyle = '#b9cbd8'; ctx.beginPath(); ctx.moveTo(x, top + height); ctx.lineTo(x, top + height + 6); ctx.stroke();
    ctx.save();
    ctx.translate(x - 4, top + height + 14);
    ctx.rotate(-Math.PI / 4);
    ctx.fillStyle = '#5f7284';
    ctx.font = '11px Inter, sans-serif';
    ctx.fillText(String(item.sample || index + 1).slice(0, 18), 0, 0);
    ctx.restore();
  }});
  ctx.fillStyle = '#5f7284'; ctx.font = '13px Inter, sans-serif';
  ctx.fillText(`mean total: ${{mean(items, 'total').toFixed(2)}} / mean zero: ${{(mean(items, 'zero_ratio')*100).toFixed(1)}}% / red = flagged before filtering`, left, canvas.height - 36);
  chartState[canvasId] = {{left, top, width, height, boxes}};
}}
draw('before', before, 'Before QC: all uploaded samples');
draw('after', after, 'After QC: samples passing current thresholds');
function bindHover(canvasId) {{
  const canvas = document.getElementById(canvasId);
  canvas.addEventListener('mousemove', event => {{
    const state = chartState[canvasId];
    if (!state) return;
    const rect = canvas.getBoundingClientRect();
    const x = (event.clientX - rect.left) * canvas.width / rect.width;
    const y = (event.clientY - rect.top) * canvas.height / rect.height;
    let best = null;
    let bestDistance = Infinity;
    for (const box of state.boxes) {{
      const dx = Math.abs(box.x - x);
      const withinY = y >= Math.min(box.yTop, box.boxTop) - 8 && y <= Math.max(box.yBottom, box.boxBottom) + 8;
      if (dx < bestDistance && dx < 12 && withinY) {{
        best = box;
        bestDistance = dx;
      }}
    }}
    if (!best) {{
      tip.style.display = 'none';
      return;
    }}
    const item = best.item;
    tip.style.display = 'block';
    tip.style.left = `${{event.clientX + 14}}px`;
    tip.style.top = `${{event.clientY + 14}}px`;
    tip.innerHTML = `
      <strong>${{item.sample}}</strong><br>
      condition: ${{item.condition}} / group: ${{item.group}}<br>
      status: ${{item.qc_pass ? 'pass' : 'flagged'}}<br>
      total: ${{Number(item.total).toFixed(2)}} / zero: ${{(Number(item.zero_ratio) * 100).toFixed(1)}}%<br>
      detected genes: ${{item.detected_genes}}<br>
      median: ${{Number(item.median).toFixed(2)}} / max: ${{Number(item.max).toFixed(2)}}<br>
      reason: ${{(item.qc_reasons || []).join(', ') || '-'}}
    `;
  }});
  canvas.addEventListener('mouseleave', () => {{
    tip.style.display = 'none';
  }});
}}
bindHover('before');
bindHover('after');
</script></body></html>""",
        encoding="utf-8",
    )


def write_qc_preview(path: Path, before_stats: list[dict[str, Any]], after_stats: list[dict[str, Any]]) -> None:
    max_total = max((item["total"] for item in before_stats), default=1)
    before_bars = []
    after_names = {item["sample"] for item in after_stats}
    for index, item in enumerate(before_stats[:20]):
        height = item["total"] / max_total * 48
        color = "#0f8a8f" if item["sample"] in after_names else "#bd3f32"
        before_bars.append(f'<rect x="{16 + index * 9}" y="{86 - height:.1f}" width="6" height="{height:.1f}" fill="{color}" opacity=".72"/>')
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="12" fill="#f5f9fc"/><text x="12" y="17" font-size="11" fill="#172635">QC before / after</text><text x="12" y="106" font-size="10" fill="#5f7284">{len(after_stats)}/{len(before_stats)} samples passed</text>{"".join(before_bars)}</svg>',
        encoding="utf-8",
    )


def write_qc_html(
    path: Path,
    before_stats: list[dict[str, Any]],
    after_stats: list[dict[str, Any]],
    params: dict[str, Any],
) -> None:
    payload = json.dumps({"before": before_stats, "after": after_stats, "params": params}, ensure_ascii=False)
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>QC</title>
<style>
body{{margin:0;font-family:Inter,'Segoe UI','Microsoft YaHei',sans-serif;background:#f5f9fc;color:#172635}}
.wrap{{padding:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:0 0 18px}}
.card{{padding:12px 14px;border:1px solid #d8e5ee;border-radius:10px;background:white}}
.plots{{display:grid;grid-template-columns:1fr;gap:18px}}
.plot-card{{padding:14px 16px;border:1px solid #d8e5ee;border-radius:12px;background:white;overflow:auto}}
svg{{display:block;min-width:1080px;width:100%;height:auto}}
.axis{{stroke:#40566a;stroke-width:1.5}}
.grid-line{{stroke:#edf3f7;stroke-width:1}}
.tick text,.axis-label{{fill:#172635;font-size:14px;font-weight:700}}
.tick-value{{fill:#5f7284;font-size:12px}}
.sample-line{{stroke-width:1.5}}
.sample-box{{stroke-width:1.4}}
.sample-median{{stroke:#172635;stroke-width:2}}
.sample-row{{cursor:crosshair}}
.sample-row:hover .sample-line,.sample-row:hover .sample-box{{stroke:#315fd6;stroke-width:2.4}}
.flagged{{margin-top:16px;border:1px solid #d8e5ee;border-radius:12px;background:white;overflow:auto}}
.flagged table{{width:100%;border-collapse:collapse;font-size:13px}}
.flagged th,.flagged td{{padding:8px 10px;border-bottom:1px solid #edf3f7;text-align:left;white-space:nowrap}}
.pass{{color:#087a55}}.fail{{color:#bd3f32}}
.tip{{position:fixed;display:none;z-index:20;max-width:300px;padding:10px 12px;border-radius:10px;background:#172635;color:white;font-size:12px;line-height:1.5;box-shadow:0 12px 28px rgba(23,38,53,.22);pointer-events:none}}
</style></head><body><div class="wrap"><h1>Multi-sample QC</h1>
<div class="grid" id="summary"></div>
<div class="plots">
  <section class="plot-card"><div id="beforePlot"></div></section>
  <section class="plot-card"><div id="afterPlot"></div></section>
</div>
<section class="flagged"><table><thead><tr><th>Sample</th><th>Condition</th><th>Status</th><th>Total</th><th>Zero %</th><th>Detected genes</th><th>Outlier / reason</th></tr></thead><tbody id="rows"></tbody></table></section>
</div><div class="tip" id="tip"></div><script>
const data = {payload};
const before = data.before;
const after = data.after;
const failed = before.filter(item => !item.qc_pass);
const tip = document.getElementById('tip');
const mean = (items, key) => items.reduce((sum, item) => sum + Number(item[key] || 0), 0) / Math.max(items.length, 1);
document.getElementById('summary').innerHTML = `
  <div class="card"><strong>Before QC</strong><div>${{before.length}} samples</div></div>
  <div class="card"><strong>After QC</strong><div>${{after.length}} samples</div></div>
  <div class="card"><strong>Flagged</strong><div>${{failed.length}} samples</div></div>
  <div class="card"><strong>QC preset</strong><div>${{data.params.qc_preset || 'normal'}}</div></div>
  <div class="card"><strong>Parameters</strong><div>total >= median * ${{data.params.min_total_ratio}}, zero <= ${{data.params.max_zero_ratio}}, detected >= ${{data.params.min_detected_genes}}, max <= Q3 + ${{data.params.max_value_iqr_multiplier}} * IQR</div></div>
`;
document.getElementById('rows').innerHTML = before.map(item => `
  <tr><td>${{item.sample}}</td><td>${{item.condition}}</td><td class="${{item.qc_pass ? 'pass' : 'fail'}}">${{item.qc_pass ? 'pass' : 'flagged'}}</td>
  <td>${{Number(item.total).toFixed(2)}}</td><td>${{(Number(item.zero_ratio)*100).toFixed(1)}}%</td><td>${{item.detected_genes}}</td><td>${{Number(item.distribution_mad_score || 0).toFixed(2)}} / ${{(item.qc_reasons || []).join(', ') || '-'}}</td></tr>
`).join('');
function svgEl(name, attrs = {{}}, text = '') {{
  const el = document.createElementNS('http://www.w3.org/2000/svg', name);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  if (text) el.textContent = text;
  return el;
}}
function renderPlot(containerId, items, title) {{
  const container = document.getElementById(containerId);
  const svg = svgEl('svg', {{viewBox: '0 0 1200 560', role: 'img', 'aria-label': title}});
  const left = 118, right = 34, top = 72, bottom = 124;
  const plotWidth = 1200 - left - right;
  const plotHeight = 560 - top - bottom;
  const vmax = Math.max(...before.map(item => Number(item.max || 0)), 1);
  const sy = value => top + plotHeight - Number(value || 0) / vmax * plotHeight;
  svg.appendChild(svgEl('text', {{x: left, y: 28, fill: '#172635', 'font-size': 20, 'font-weight': 700}}, title));
  svg.appendChild(svgEl('text', {{x: left, y: 54, class: 'axis-label'}}, 'Y: expression value per gene'));
  svg.appendChild(svgEl('text', {{x: left + plotWidth / 2 - 138, y: top + plotHeight + 104, class: 'axis-label'}}, 'X: samples ordered as input metadata'));
  const yLabel = svgEl('text', {{x: 24, y: top + plotHeight / 2 + 90, class: 'axis-label', transform: `rotate(-90 24 ${{top + plotHeight / 2 + 90}})`}}, 'expression value per gene');
  svg.appendChild(yLabel);
  svg.appendChild(svgEl('line', {{x1: left, y1: top, x2: left, y2: top + plotHeight, class: 'axis'}}));
  svg.appendChild(svgEl('line', {{x1: left, y1: top + plotHeight, x2: left + plotWidth, y2: top + plotHeight, class: 'axis'}}));
  [0, 0.25, 0.5, 0.75, 1].forEach(fraction => {{
    const y = top + plotHeight - fraction * plotHeight;
    const value = fraction * vmax;
    svg.appendChild(svgEl('line', {{x1: left, y1: y, x2: left + plotWidth, y2: y, class: 'grid-line'}}));
    svg.appendChild(svgEl('text', {{x: left - 12, y: y + 4, 'text-anchor': 'end', class: 'tick-value'}}, value.toFixed(0)));
  }});
  const tickEvery = Math.max(1, Math.ceil(items.length / 12));
  items.forEach((item, index) => {{
    const x = left + (index + 0.5) / Math.max(items.length, 1) * plotWidth;
    const color = item.qc_pass ? '#0f8a8f' : '#bd3f32';
    const group = svgEl('g', {{class: 'sample-row'}});
    group.appendChild(svgEl('line', {{x1: x, y1: sy(item.min), x2: x, y2: sy(item.max), stroke: color, class: 'sample-line'}}));
    const boxTop = sy(item.q3);
    const boxHeight = Math.max(3, sy(item.q1) - sy(item.q3));
    group.appendChild(svgEl('rect', {{x: x - 6, y: boxTop, width: 12, height: boxHeight, fill: item.qc_pass ? 'rgba(15,138,143,.18)' : 'rgba(189,63,50,.18)', stroke: color, class: 'sample-box'}}));
    group.appendChild(svgEl('line', {{x1: x - 8, y1: sy(item.median), x2: x + 8, y2: sy(item.median), class: 'sample-median'}}));
    group.addEventListener('mousemove', event => {{
      tip.style.display = 'block';
      tip.style.left = `${{event.clientX + 14}}px`;
      tip.style.top = `${{event.clientY + 14}}px`;
      tip.innerHTML = `<strong>${{item.sample}}</strong><br>condition: ${{item.condition}} / group: ${{item.group}}<br>status: ${{item.qc_pass ? 'pass' : 'flagged'}}<br>total: ${{Number(item.total).toFixed(2)}} / zero: ${{(Number(item.zero_ratio) * 100).toFixed(1)}}%<br>detected genes: ${{item.detected_genes}}<br>median: ${{Number(item.median).toFixed(2)}} / max: ${{Number(item.max).toFixed(2)}}<br>reason: ${{(item.qc_reasons || []).join(', ') || '-'}}`;
    }});
    group.addEventListener('mouseleave', () => {{ tip.style.display = 'none'; }});
    svg.appendChild(group);
    if (index % tickEvery === 0 || index === items.length - 1) {{
      svg.appendChild(svgEl('line', {{x1: x, y1: top + plotHeight, x2: x, y2: top + plotHeight + 7, stroke: '#8799aa'}}));
      const label = svgEl('text', {{x: x - 5, y: top + plotHeight + 20, class: 'tick-value', transform: `rotate(-38 ${{x - 5}} ${{top + plotHeight + 20}})`}}, String(item.sample || index + 1).slice(0, 18));
      svg.appendChild(label);
    }}
  }});
  svg.appendChild(svgEl('text', {{x: left, y: 536, fill: '#5f7284', 'font-size': 13}}, `mean total: ${{mean(items, 'total').toFixed(2)}} / mean zero: ${{(mean(items, 'zero_ratio') * 100).toFixed(1)}}% / red = flagged`));
  container.replaceChildren(svg);
}}
renderPlot('beforePlot', before, 'Before QC: all uploaded samples');
renderPlot('afterPlot', after, 'After QC: samples passing current thresholds');
</script></body></html>""",
        encoding="utf-8",
    )


def write_correlation_html(
    path: Path,
    columns: list[SampleColumn],
    matrix: list[list[float]],
    condition_colors: dict[str, str],
) -> None:
    cell = 18
    left = 158
    top = 154
    band = 9
    right = 60
    bottom = 92
    size = len(columns)
    width = left + size * cell + right
    height = top + size * cell + bottom
    values = [
        value
        for row_index, row in enumerate(matrix)
        for column_index, value in enumerate(row)
        if row_index != column_index and math.isfinite(value)
    ]
    min_corr = min(values, default=0.6)
    max_corr = 1.0
    span = max(max_corr - min_corr, 0.001)

    def mix(left_rgb: tuple[int, int, int], right_rgb: tuple[int, int, int], t: float) -> tuple[int, int, int]:
        return tuple(round(left_rgb[index] + (right_rgb[index] - left_rgb[index]) * t) for index in range(3))

    def corr_color(value: float) -> str:
        t = max(0.0, min(1.0, (value - min_corr) / span))
        low = (49, 95, 214)
        mid = (246, 249, 252)
        high = (196, 79, 58)
        rgb = mix(low, mid, t * 2) if t < 0.5 else mix(mid, high, (t - 0.5) * 2)
        return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"

    fallback_colors = ["#0f8a8f", "#315fd6", "#c44f3a", "#7b61b5", "#20804f", "#c27a18"]
    conditions = []
    for column in columns:
        if column.condition not in conditions:
            conditions.append(column.condition)

    def group_color(condition: str) -> str:
        if condition in condition_colors:
            return condition_colors[condition]
        index = conditions.index(condition) if condition in conditions else 0
        return fallback_colors[index % len(fallback_colors)]

    parts = [
        f'<rect width="{width}" height="{height}" rx="14" fill="#ffffff"/>',
        f'<rect x="{left}" y="{top}" width="{size * cell}" height="{size * cell}" fill="#f6f9fc"/>',
    ]
    for row_index, column in enumerate(columns):
        y = top + row_index * cell
        label = html.escape(column.name[:18])
        color = group_color(column.condition)
        parts.append(f'<rect x="{left - band - 5}" y="{y}" width="{band}" height="{cell - 1}" fill="{color}"/>')
        parts.append(f'<text x="12" y="{y + 13}" font-size="11" fill="#52616b">{label}</text>')
        for column_index, value in enumerate(matrix[row_index]):
            x = left + column_index * cell
            fill = corr_color(value)
            sample_x = html.escape(columns[column_index].name)
            sample_y = html.escape(column.name)
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell - 1}" height="{cell - 1}" fill="{fill}">'
                f'<title>{sample_y} vs {sample_x}: r={value:.3f}</title></rect>'
            )
    for column_index, column in enumerate(columns):
        x = left + column_index * cell
        label = html.escape(column.name[:18])
        color = group_color(column.condition)
        parts.append(f'<rect x="{x}" y="{top - band - 5}" width="{cell - 1}" height="{band}" fill="{color}"/>')
        parts.append(
            f'<text x="{x + 11}" y="{top - 20}" font-size="11" fill="#52616b" '
            f'transform="rotate(-45 {x + 11} {top - 20})">{label}</text>'
        )
    parts.append(f'<rect x="{left}" y="{top}" width="{size * cell}" height="{size * cell}" fill="none" stroke="#b9cbd8"/>')
    legend_x = left
    legend_y = height - 46
    legend_width = 220
    for offset in range(legend_width):
        value = min_corr + (offset / legend_width) * span
        parts.append(f'<rect x="{legend_x + offset}" y="{legend_y}" width="1" height="12" fill="{corr_color(value)}"/>')
    parts.append(f'<text x="{legend_x}" y="{legend_y + 31}" font-size="12" fill="#52616b">r min {min_corr:.2f}</text>')
    parts.append(f'<text x="{legend_x + legend_width - 40}" y="{legend_y + 31}" font-size="12" fill="#52616b">r 1.00</text>')
    legend_group_x = legend_x + 280
    for index, condition in enumerate(conditions):
        y = legend_y + index * 20
        parts.append(f'<rect x="{legend_group_x}" y="{y}" width="12" height="12" rx="2" fill="{group_color(condition)}"/>')
        parts.append(f'<text x="{legend_group_x + 18}" y="{y + 11}" font-size="12" fill="#52616b">{html.escape(condition)}</text>')

    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">{"".join(parts)}</svg>'
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Sample Correlation</title>
<style>
body{{margin:0;font-family:Inter,'Noto Sans SC',Arial,sans-serif;background:#f4f8fb;color:#07131f}}
.wrap{{padding:24px}}
h1{{margin:0 0 8px;font-size:28px}}
p{{margin:0 0 16px;color:#52616b}}
.plot-frame{{width:min(100%, {width}px);overflow:auto;border:1px solid #d8e5ee;border-radius:14px;background:white}}
svg{{display:block}}
</style></head><body><div class="wrap"><h1>&#26679;&#26412;&#30456;&#20851;&#24615;&#28909;&#22270;</h1><p>&#39068;&#33394;&#25353;&#30456;&#20851;&#31995;&#25968;&#33539;&#22260;&#21160;&#24577;&#32553;&#25918;&#65307;&#39030;&#37096;&#21644;&#24038;&#20391;&#33394;&#26465;&#34920;&#31034;&#26679;&#26412;&#20998;&#32452;&#65292;&#24748;&#20572;&#21333;&#20803;&#26684;&#21487;&#26597;&#30475; r &#20540;&#12290;</p><div class="plot-frame">{svg}</div></div></body></html>""",
        encoding="utf-8",
    )


def write_correlation_preview(path: Path, matrix: list[list[float]]) -> None:
    rects = []
    values = [
        value
        for r, row in enumerate(matrix)
        for c, value in enumerate(row)
        if r != c and math.isfinite(value)
    ]
    min_corr = min(values, default=0.6)
    span = max(1 - min_corr, 0.001)
    for r, row in enumerate(matrix[:18]):
        for c, value in enumerate(row[:18]):
            t = max(0.0, min(1.0, (value - min_corr) / span))
            color = "#c44f3a" if t >= 0.5 else "#315fd6"
            opacity = 0.35 + abs(t - 0.5) * 1.1
            rects.append(f'<rect x="{18 + c*5}" y="{24 + r*5}" width="4" height="4" fill="{color}" opacity="{opacity:.2f}"/>')
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#f4f8fb"/><text x="12" y="17" font-size="11" fill="#17211b">样本相关性</text>{"".join(rects)}</svg>',
        encoding="utf-8",
    )


def write_gene_expression_html(path: Path, gene_payload: dict[str, Any]) -> None:
    payload = json.dumps(gene_payload, ensure_ascii=False)
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Gene Expression</title>
<script src="/static/vendor/plotly.min.js"></script>
<style>
body{{margin:0;font-family:Inter,'Noto Sans SC',Arial,sans-serif;background:#f4f8fb;color:#07131f}}
.wrap{{padding:24px}}
.head{{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:16px}}
h1{{margin:0 0 8px;font-size:28px;line-height:1.1}}
p{{margin:0;color:#52616b}}
.summary{{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end}}
.summary span{{padding:7px 10px;border:1px solid #d8e5ee;border-radius:999px;background:white;font-size:12px;font-weight:800;color:#345}}
#plot{{width:1180px;height:680px;border:1px solid #d8e5ee;border-radius:14px;background:white}}
.plot-frame{{width:min(100%,1180px);overflow:auto}}
.plot-error{{padding:18px;border:1px solid #efb8ae;border-radius:12px;background:#fff6f3;color:#9a352a;font-weight:800}}
.modebar,.modebar-container,.modebar-btn--logo,.plotlyjsicon,.modebar-logo{{display:none!important}}
</style>
</head><body><div class="wrap"><div class="head"><div><h1>单基因表达：{html.escape(str(gene_payload["gene"]))}</h1><p>{html.escape(str(gene_payload["gene_id"]))}</p></div><div class="summary" id="summary"></div></div><div class="plot-frame"><div id="plot"></div></div></div>
<script>
const data = {payload};
const palette = ['#0f8a8f', '#315fd6', '#c44f3a', '#7b61b5', '#20804f', '#c27a18', '#b33d7a', '#52616b'];
const conditionColors = data.condition_colors || {{}};
const groups = Object.keys(data.groups || {{}});
const plotEl = document.getElementById('plot');
function transparentColor(hex, alpha) {{
  const match = String(hex || '').match(/^#?([0-9a-f]{{6}})$/i);
  if (!match) return `rgba(15,138,143,${{alpha}})`;
  const raw = match[1];
  const r = parseInt(raw.slice(0, 2), 16);
  const g = parseInt(raw.slice(2, 4), 16);
  const b = parseInt(raw.slice(4, 6), 16);
  return `rgba(${{r}},${{g}},${{b}},${{alpha}})`;
}}
document.getElementById('summary').innerHTML = groups.map(name => {{
  const info = data.groups[name] || {{}};
  return `<span>${{name}} · n=${{info.count || 0}} · median=${{info.median ?? '-'}}</span>`;
}}).join('');
const traces = groups.map((name, index) => {{
  const points = data.points.filter(point => point.condition === name);
  const color = conditionColors[name] || palette[index % palette.length];
  return {{
    type: 'box',
    name,
    y: points.map(point => point.value),
    x: points.map(() => name),
    text: points.map(point => point.sample),
    customdata: points.map(point => [point.group, data.groups[name]?.mean, data.groups[name]?.median]),
    boxpoints: 'all',
    jitter: 0.42,
    pointpos: 0,
    marker: {{color, size: 8, opacity: 0.72, line: {{color: '#ffffff', width: 1}}}},
    line: {{color, width: 2}},
    fillcolor: transparentColor(color, 0.2),
    hovertemplate: '<b>%{{text}}</b><br>condition=%{{x}}<br>expression=%{{y:.4f}}<br>group=%{{customdata[0]}}<br>mean=%{{customdata[1]}}<br>median=%{{customdata[2]}}<extra></extra>',
    boxmean: true,
  }};
}});
try {{
if (!window.Plotly) throw new Error('Plotly library did not load');
Plotly.newPlot(plotEl, traces, {{
  title: {{text: 'Expression distribution by condition', x: 0.02, xanchor: 'left'}},
  width: 1180,
  height: 680,
  paper_bgcolor: '#ffffff',
  plot_bgcolor: '#ffffff',
  margin: {{l: 74, r: 28, t: 70, b: 86}},
  xaxis: {{title: 'Condition', zeroline: false, tickangle: groups.length > 5 ? -30 : 0}},
  yaxis: {{title: 'Expression', zeroline: false, gridcolor: '#e8f0f5'}},
  boxmode: 'group',
  hovermode: 'closest',
  showlegend: groups.length <= 8,
  font: {{family: "Inter, 'Noto Sans SC', Arial, sans-serif", color: '#07131f'}},
}}, {{
  responsive: false,
  displayModeBar: false,
  displaylogo: false,
  toImageButtonOptions: {{format: 'png', filename: `gene-expression-${{data.gene || 'gene'}}`, height: 900, width: 1400, scale: 2}},
}});
}} catch (error) {{
  plotEl.className = 'plot-error';
  plotEl.textContent = `Plotly 渲染失败：${{error.message}}`;
}}
</script></body></html>""",
        encoding="utf-8",
    )


def write_gene_expression_preview(path: Path, gene_payload: dict[str, Any]) -> None:
    boxes = []
    groups = list(gene_payload["groups"].items())
    max_mean = max((item["mean"] for _, item in groups), default=1)
    min_mean = min((item["mean"] for _, item in groups), default=0)
    span = max(max_mean - min_mean, 1)
    for index, (_, item) in enumerate(groups[:6]):
        x = 32 + index * 30
        mean_y = 92 - (item["mean"] - min_mean) / span * 48
        median_y = 92 - (item["median"] - min_mean) / span * 48
        boxes.append(
            f'<line x1="{x}" x2="{x}" y1="{max(28, mean_y - 18):.1f}" y2="{min(98, mean_y + 18):.1f}" stroke="#0f8a8f" stroke-width="2"/>'
            f'<rect x="{x - 8}" y="{max(30, mean_y - 10):.1f}" width="16" height="20" rx="3" fill="#d8f0ef" stroke="#0f8a8f"/>'
            f'<line x1="{x - 8}" x2="{x + 8}" y1="{median_y:.1f}" y2="{median_y:.1f}" stroke="#07131f" stroke-width="2"/>'
        )
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#f4f8fb"/><text x="12" y="17" font-size="11" fill="#17211b">{html.escape(str(gene_payload["gene"]))}</text><text x="12" y="31" font-size="9" fill="#52616b">Interactive boxplot</text>{"".join(boxes)}</svg>',
        encoding="utf-8",
    )

