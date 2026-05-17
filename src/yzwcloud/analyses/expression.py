from __future__ import annotations

import csv
import html
import json
import math
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

    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    explained = {
        "pc1": round(max(pc1_value, 0.0) / total_variance * 100, 2),
        "pc2": round(max(pc2_value, 0.0) / total_variance * 100, 2),
    }

    write_pca_html(html_path, points, explained, len(gene_vectors))
    write_pca_preview(preview_path, points)
    meta = {
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "sample_count": len(sample_columns),
        "gene_count": len(gene_vectors),
        "explained_variance": explained,
        "method": "sample_covariance_power_iteration",
    }
    return write_data_output(output_json, "pca_plot", meta)


def create_qc_result(source: DataObject, output_dir: Path, node_id: str) -> DataObject:
    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    sample_columns = load_sample_columns(matrix_path, metadata_path)
    series = load_sample_series(matrix_path, sample_columns)
    stats = [sample_qc_stats(column, values) for column, values in zip(sample_columns, series, strict=False)]
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    write_qc_html(html_path, stats)
    write_qc_preview(preview_path, stats)
    meta = {"html_file": str(html_path), "preview_file": str(preview_path), "sample_count": len(stats), "metric_count": 4}
    return write_data_output(output_json, "qc_report", meta)


def create_sample_correlation_result(source: DataObject, output_dir: Path, node_id: str) -> DataObject:
    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    sample_columns = load_sample_columns(matrix_path, metadata_path)
    series = load_sample_series(matrix_path, sample_columns)
    matrix = [[round(pearson(series[i], series[j]), 3) for j in range(len(sample_columns))] for i in range(len(sample_columns))]
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    write_correlation_html(html_path, sample_columns, matrix)
    write_correlation_preview(preview_path, matrix)
    meta = {"html_file": str(html_path), "preview_file": str(preview_path), "sample_count": len(sample_columns)}
    return write_data_output(output_json, "sample_correlation_plot", meta)


def create_expression_heatmap_result(source: DataObject, output_dir: Path, node_id: str) -> DataObject:
    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    sample_columns = load_sample_columns(matrix_path, metadata_path)
    genes = top_variable_heatmap_genes(matrix_path, sample_columns, top_n=40)
    ordered_columns = order_samples_by_condition(sample_columns)
    order_index = [sample_columns.index(item) for item in ordered_columns]
    for gene in genes:
        gene["values"] = [gene["values"][index] for index in order_index]
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    write_heatmap_html(html_path, "表达矩阵聚类热图", ordered_columns, genes)
    write_heatmap_preview(preview_path, "表达聚类", genes)
    meta = {
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "gene_count": len(genes),
        "sample_count": len(ordered_columns),
    }
    return write_data_output(output_json, "expression_heatmap_plot", meta)


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
    sample_columns = load_sample_columns(matrix_path, metadata_path)
    gene_payload = find_gene_expression(matrix_path, sample_columns, gene_query)
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    write_gene_expression_html(html_path, gene_payload)
    write_gene_expression_preview(preview_path, gene_payload)
    meta = {
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "gene": gene_payload["gene"],
        "gene_id": gene_payload["gene_id"],
        "sample_count": len(gene_payload["points"]),
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
        "total": round(sum(values), 4),
    }


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


def order_samples_by_condition(columns: list[SampleColumn]) -> list[SampleColumn]:
    return sorted(columns, key=lambda item: (item.condition, item.group, item.name))


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


def write_pca_html(
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
<p>基于表达矩阵中方差最高的 {gene_count} 个基因计算。悬停可查看样本、分组和坐标。</p>
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


def write_correlation_html(path: Path, columns: list[SampleColumn], matrix: list[list[float]]) -> None:
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


def write_correlation_preview(path: Path, matrix: list[list[float]]) -> None:
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


def write_gene_expression_html(path: Path, gene_payload: dict[str, Any]) -> None:
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


def write_gene_expression_preview(path: Path, gene_payload: dict[str, Any]) -> None:
    circles = []
    groups = list(gene_payload["groups"].items())
    max_mean = max((item["mean"] for _, item in groups), default=1)
    for index, (_, item) in enumerate(groups[:6]):
        x = 36 + index * 28
        y = 90 - item["mean"] / max_mean * 48
        circles.append(f'<circle cx="{x}" cy="{y:.1f}" r="6" fill="#0f6b57" opacity=".72"/>')
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#fffaf0"/><text x="12" y="17" font-size="11" fill="#17211b">{html.escape(str(gene_payload["gene"]))}</text>{"".join(circles)}</svg>',
        encoding="utf-8",
    )
