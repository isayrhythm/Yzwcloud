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
    SampleColumn,
    load_sample_columns,
    read_diff_rows,
    values_at,
    variance,
    welch_p_value,
    write_data_output,
    write_json_detail,
)
from yzwcloud.analyses.rendering import write_heatmap_html, write_heatmap_preview
from yzwcloud.models import DataObject


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

    sample_columns = load_sample_columns(matrix_path, metadata_path)
    case_columns = [item for item in sample_columns if item.condition == case_condition]
    control_columns = [item for item in sample_columns if item.condition == control_condition]
    if not case_columns or not control_columns:
        raise ValueError("选择的 case/control 分组没有可用样本列")

    diff_csv = output_dir / f"{node_id}_diff.csv"
    output_json = output_dir / f"{node_id}_output.json"
    rows = []
    with matrix_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        next(reader)
        for row in reader:
            if len(row) <= GENE_INFO_COLUMNS:
                continue
            gene_name = row[0] or row[1]
            gene_id = row[1] or row[0]
            case_values = values_at(row, case_columns)
            control_values = values_at(row, control_columns)
            if len(case_values) < 2 or len(control_values) < 2:
                continue
            case_mean = fmean(case_values)
            control_mean = fmean(control_values)
            log2fc = case_mean - control_mean
            p_value = welch_p_value(case_values, control_values)
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
        item
        for item in rows
        if item["p_value"] <= params.get("p_value", 0.05) and abs(item["log2fc"]) >= params.get("log2fc", 1.0)
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
    write_json_detail(
        output_json.with_name(output_json.stem.replace("_output", "_detail") + ".json"),
        {"message": "差异分析完成", "meta": meta, "top_genes": rows[:30]},
    )
    return output


def create_volcano_result(diff: DataObject, output_dir: Path, node_id: str) -> DataObject:
    rows = read_diff_rows(Path(str(diff.meta["diff_result_file"])))
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    comparison = diff.meta.get("comparison_label", "comparison")

    points = [
        {"gene": row["gene"], "x": round(row["log2fc"], 4), "y": round(row["neg_log10_p"], 4), "p": row["p_value"]}
        for row in rows[:5000]
    ]
    write_volcano_html(html_path, comparison, points)
    write_volcano_preview(preview_path, points, comparison)
    meta = {
        "comparison_label": comparison,
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "point_count": len(points),
    }
    return write_data_output(output_json, "volcano_plot", meta)


def create_heatmap_result(diff: DataObject, output_dir: Path, node_id: str) -> DataObject:
    matrix_path = Path(str(diff.meta["matrix_file"]))
    metadata_path = Path(str(diff.meta["sample_metadata_file"]))
    diff_rows = read_diff_rows(Path(str(diff.meta["diff_result_file"])))[:50]
    sample_columns = load_sample_columns(matrix_path, metadata_path)
    case_condition = str(diff.meta["case_condition"])
    control_condition = str(diff.meta["control_condition"])
    selected_columns = [item for item in sample_columns if item.condition in {case_condition, control_condition}]

    genes = extract_heatmap_values(matrix_path, diff_rows, selected_columns)
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    comparison = diff.meta.get("comparison_label", "comparison")

    write_heatmap_html(html_path, comparison, selected_columns, genes)
    write_heatmap_preview(preview_path, comparison, genes)
    meta = {
        "comparison_label": comparison,
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "gene_count": len(genes),
        "sample_count": len(selected_columns),
    }
    return write_data_output(output_json, "heatmap_plot", meta)


def create_diff_export_result(diff: DataObject, output_dir: Path, node_id: str) -> DataObject:
    diff_csv = Path(str(diff.meta["diff_result_file"]))
    export_csv = output_dir / f"{node_id}_export.csv"
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    shutil.copyfile(diff_csv, export_csv)
    top_rows = read_diff_rows(diff_csv)[:20]
    write_diff_export_html(html_path, diff.meta.get("comparison_label", "comparison"), export_csv.name, top_rows)
    write_diff_export_preview(preview_path)
    meta = {
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "export_file": str(export_csv),
        "comparison_label": diff.meta.get("comparison_label", "comparison"),
        "row_count": int(diff.meta.get("tested_gene_count", 0)),
    }
    return write_data_output(output_json, "diff_export", meta)


def extract_heatmap_values(
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
            values = values_at(row, columns)
            if not values:
                continue
            mean = fmean(values)
            std = math.sqrt(variance(values)) or 1.0
            found.append(
                {
                    "gene": row[0] or gene_id,
                    "gene_id": gene_id,
                    "values": [round((value - mean) / std, 3) for value in values],
                }
            )
    return sorted(found, key=lambda item: order[item["gene_id"]])


def write_volcano_html(path: Path, comparison: str, points: list[dict[str, Any]]) -> None:
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


def write_volcano_preview(path: Path, points: list[dict[str, Any]], comparison: str) -> None:
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


def write_diff_export_html(path: Path, comparison: str, export_name: str, rows: list[dict[str, Any]]) -> None:
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


def write_diff_export_preview(path: Path) -> None:
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#fffaf0"/><text x="12" y="17" font-size="11" fill="#17211b">结果导出</text><rect x="28" y="30" width="164" height="62" rx="10" fill="#fff" stroke="#ded4c2"/><line x1="40" y1="50" x2="180" y2="50" stroke="#0f6b57"/><line x1="40" y1="64" x2="168" y2="64" stroke="#d2cabd"/><line x1="40" y1="76" x2="152" y2="76" stroke="#d2cabd"/></svg>',
        encoding="utf-8",
    )
