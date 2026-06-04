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
    write_data_output,
    write_json_detail,
)
from yzwcloud.analyses.rendering import write_heatmap_html, write_heatmap_preview
from yzwcloud.analyses.r_runner import run_r_script
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

    r_matrix, r_metadata, r_comparisons, slug = _write_r_differential_inputs(
        matrix_path=matrix_path,
        metadata_path=metadata_path,
        case_condition=case_condition,
        control_condition=control_condition,
        case_columns=case_columns,
        control_columns=control_columns,
        output_dir=output_dir,
        node_id=node_id,
    )
    r_output_file, r_log_file, method, r_script_file = _run_r_differential(
        params=params,
        output_dir=output_dir,
        r_matrix=r_matrix,
        r_metadata=r_metadata,
        r_comparisons=r_comparisons,
        slug=slug,
        node_id=node_id,
    )
    rows = _write_canonical_diff_csv(
        r_output_file=r_output_file,
        r_matrix=r_matrix,
        diff_csv=diff_csv,
        case_samples=[item.name for item in case_columns],
        control_samples=[item.name for item in control_columns],
    )

    significant = [
        item
        for item in rows
        if item["p_value"] <= params.get("p_value", 0.05) and abs(item["log2fc"]) >= params.get("log2fc", 1.0)
    ]
    meta = {
        "diff_gene_count": len(significant),
        "tested_gene_count": len(rows),
        "method": method,
        "case_condition": case_condition,
        "control_condition": control_condition,
        "comparison_label": f"{case_condition} vs {control_condition}",
        "case_sample_count": len(case_columns),
        "control_sample_count": len(control_columns),
        "diff_result_file": str(diff_csv),
        "p_value_threshold": params.get("p_value", 0.05),
        "log2fc_threshold": params.get("log2fc", 1.0),
        "r_script_file": str(r_script_file),
        "r_matrix_file": str(r_matrix),
        "r_metadata_file": str(r_metadata),
        "r_comparisons_file": str(r_comparisons),
        "r_result_file": str(r_output_file),
        "r_log_file": str(r_log_file),
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


def _write_r_differential_inputs(
    matrix_path: Path,
    metadata_path: Path,
    case_condition: str,
    control_condition: str,
    case_columns: list[SampleColumn],
    control_columns: list[SampleColumn],
    output_dir: Path,
    node_id: str,
) -> tuple[Path, Path, Path, str]:
    slug = _safe_slug(f"{case_condition}_vs_{control_condition}") or _safe_slug(node_id)
    selected_columns = [*case_columns, *control_columns]
    r_matrix = output_dir / f"{node_id}_r_matrix.csv"
    r_metadata = output_dir / f"{node_id}_r_metadata.csv"
    r_comparisons = output_dir / f"{node_id}_r_comparisons.csv"

    with matrix_path.open(encoding="utf-8-sig", newline="") as source_file, r_matrix.open(
        "w", encoding="utf-8-sig", newline=""
    ) as target_file:
        reader = csv.reader(source_file)
        next(reader, None)
        writer = csv.writer(target_file)
        writer.writerow(["feature_id", "feature_name", "description", *[item.name for item in selected_columns]])
        for row in reader:
            if len(row) <= GENE_INFO_COLUMNS:
                continue
            values = []
            for column in selected_columns:
                values.append(row[column.index] if column.index < len(row) else "")
            writer.writerow([row[1] or row[0], row[0] or row[1], row[2] if len(row) > 2 else "", *values])

    with r_metadata.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["sample", "group", "condition"])
        writer.writeheader()
        for column in selected_columns:
            writer.writerow({"sample": column.name, "group": column.group, "condition": column.condition})

    with r_comparisons.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["numerator", "denominator", "slug"])
        writer.writeheader()
        writer.writerow({"numerator": case_condition, "denominator": control_condition, "slug": slug})

    return r_matrix, r_metadata, r_comparisons, slug


def _run_r_differential(
    params: dict[str, Any],
    output_dir: Path,
    r_matrix: Path,
    r_metadata: Path,
    r_comparisons: Path,
    slug: str,
    node_id: str,
) -> tuple[Path, Path, str, Path]:
    script_dir = Path(__file__).resolve().parents[1] / "r"
    p_value = float(params.get("p_value", 0.05))
    log2fc = float(params.get("log2fc", 1.0))
    log_path = output_dir / f"{node_id}_r.log"

    if _is_protein_mode(params):
        script_path = script_dir / "differential_protein.R"
        fold_change = 2**log2fc
        args = [str(r_matrix), str(r_metadata), str(r_comparisons), str(output_dir), str(p_value), str(fold_change)]
        r_output = output_dir / f"{slug}_all_results.csv"
        method = "r_protein_ttest"
        failure_hint = "R protein differential analysis failed"
    else:
        script_path = script_dir / "differential_transcriptomics.R"
        args = [str(r_matrix), str(r_metadata), str(r_comparisons), str(output_dir), str(p_value), str(log2fc)]
        r_output = output_dir / f"{slug}_all_genes.csv"
        method = "r_transcriptomics_differential"
        failure_hint = "R transcriptomics differential analysis failed"

    run_r_script(
        script_path=script_path,
        args=args,
        cwd=Path(__file__).resolve().parents[3],
        log_path=log_path,
        timeout=600,
        failure_hint=failure_hint,
    )
    if not r_output.exists():
        raise ValueError(f"R differential analysis finished without result table: {r_output}. Log: {log_path}")
    return r_output, log_path, method, script_path


def _write_canonical_diff_csv(
    r_output_file: Path,
    r_matrix: Path,
    diff_csv: Path,
    case_samples: list[str],
    control_samples: list[str],
) -> list[dict[str, Any]]:
    matrix_stats = _read_r_matrix_stats(r_matrix, case_samples, control_samples)
    rows: list[dict[str, Any]] = []
    with r_output_file.open(encoding="utf-8-sig", newline="") as file:
        for raw in csv.DictReader(file):
            gene_id = (
                raw.get("gene_id")
                or raw.get("feature_id")
                or raw.get("id")
                or raw.get("row")
                or raw.get("")
                or ""
            ).strip()
            if not gene_id:
                continue
            stats = matrix_stats.get(gene_id, {})
            gene = (raw.get("gene") or raw.get("feature_name") or raw.get("gene_name") or stats.get("gene") or gene_id).strip()
            case_mean = _first_float(raw.get("mean_numerator"), raw.get("case_mean"))
            control_mean = _first_float(raw.get("mean_denominator"), raw.get("control_mean"))
            if case_mean is None:
                case_mean = stats.get("case_mean", 0.0)
            if control_mean is None:
                control_mean = stats.get("control_mean", 0.0)
            log2fc = _first_float(raw.get("log2FoldChange"), raw.get("log2_fc"), raw.get("log2fc"))
            if log2fc is None:
                raise ValueError(f"R differential output missing log2 fold-change for {gene_id}: {r_output_file}")
            p_value = _first_float(raw.get("pvalue"), raw.get("p_value"), raw.get("p.val"), raw.get("padj"))
            if p_value is None:
                raise ValueError(f"R differential output missing p-value for {gene_id}: {r_output_file}")
            rows.append(
                {
                    "gene": gene,
                    "gene_id": gene_id,
                    "case_mean": float(case_mean),
                    "control_mean": float(control_mean),
                    "log2fc": float(log2fc),
                    "p_value": float(p_value),
                    "neg_log10_p": -math.log10(max(float(p_value), 1e-300)),
                }
            )

    rows.sort(key=lambda item: item["p_value"])
    with diff_csv.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["gene", "gene_id", "case_mean", "control_mean", "log2fc", "p_value", "neg_log10_p"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return rows


def _read_r_matrix_stats(
    r_matrix: Path,
    case_samples: list[str],
    control_samples: list[str],
) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    with r_matrix.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            gene_id = str(row.get("feature_id") or "").strip()
            if not gene_id:
                continue
            case_values = [_float_or_none(row.get(sample)) for sample in case_samples]
            control_values = [_float_or_none(row.get(sample)) for sample in control_samples]
            case_values = [value for value in case_values if value is not None]
            control_values = [value for value in control_values if value is not None]
            stats[gene_id] = {
                "gene": row.get("feature_name") or gene_id,
                "case_mean": fmean(case_values) if case_values else 0.0,
                "control_mean": fmean(control_values) if control_values else 0.0,
            }
    return stats


def _is_protein_mode(params: dict[str, Any]) -> bool:
    marker = " ".join(str(params.get(key, "")) for key in ("method", "omics_type", "analysis_kind")).lower()
    return "protein" in marker or "proteom" in marker


def _safe_slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _first_float(*values: Any) -> float | None:
    for value in values:
        number = _float_or_none(value)
        if number is not None:
            return number
    return None


def create_volcano_result(diff: DataObject, output_dir: Path, node_id: str) -> DataObject:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = read_diff_rows(Path(str(diff.meta["diff_result_file"])))
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"
    comparison = diff.meta.get("comparison_label", "comparison")
    p_value_threshold = float(diff.meta.get("p_value_threshold", 0.05))
    log2fc_threshold = float(diff.meta.get("log2fc_threshold", 1.0))

    points = [
        {
            "gene": row["gene"],
            "x": round(row["log2fc"], 4),
            "y": round(row["neg_log10_p"], 4),
            "p": row["p_value"],
            "group": _volcano_group(row["log2fc"], row["p_value"], p_value_threshold, log2fc_threshold),
            "strong": row["p_value"] <= p_value_threshold and abs(row["log2fc"]) >= log2fc_threshold,
        }
        for row in rows[:5000]
    ]
    write_volcano_html(html_path, comparison, points, p_value_threshold, log2fc_threshold)
    write_volcano_preview(preview_path, points, comparison)
    meta = {
        "data_type": diff.meta.get("data_type", ""),
        "assay_profile": diff.meta.get("assay_profile", ""),
        "feature_label": diff.meta.get("feature_label", ""),
        "comparison_label": comparison,
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "point_count": len(points),
        "up_count": sum(1 for point in points if point["group"] == "Up"),
        "down_count": sum(1 for point in points if point["group"] == "Down"),
        "p_value_threshold": p_value_threshold,
        "log2fc_threshold": log2fc_threshold,
    }
    return write_data_output(output_json, "volcano_plot", meta)


def _volcano_group(log2fc: float, p_value: float, p_value_threshold: float, log2fc_threshold: float) -> str:
    if p_value <= p_value_threshold and log2fc > 0:
        return "Up"
    if p_value <= p_value_threshold and log2fc < 0:
        return "Down"
    if abs(log2fc) >= log2fc_threshold:
        return "Large FC"
    return "Not significant"


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
        "data_type": diff.meta.get("data_type", ""),
        "assay_profile": diff.meta.get("assay_profile", ""),
        "feature_label": diff.meta.get("feature_label", ""),
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


def write_volcano_html(
    path: Path,
    comparison: str,
    points: list[dict[str, Any]],
    p_value_threshold: float = 0.05,
    log2fc_threshold: float = 1.0,
) -> None:
    payload = json.dumps(points, ensure_ascii=False)
    label_count = min(10, len(points))
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Volcano {html.escape(comparison)}</title>
<style>
body{{margin:0;font-family:Inter,'Noto Sans SC',Arial,sans-serif;background:#f6f8fb;color:#07131f}}
.wrap{{padding:24px}}
.head{{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:16px}}
h1{{margin:0 0 8px;font-size:30px;line-height:1.1}}
p{{margin:0;color:#52616b}}
.legend{{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;max-width:520px}}
.legend span{{display:inline-flex;align-items:center;gap:6px;padding:7px 10px;border:1px solid #d8e5ee;border-radius:999px;background:white;font-size:12px;font-weight:800;color:#345}}
.legend i{{display:inline-block;width:9px;height:9px;border-radius:999px}}
.plot-shell{{overflow:auto}}
canvas{{display:block;width:min(100%,1200px);height:auto;aspect-ratio:1200/640;border:1px solid #d8e5ee;border-radius:14px;background:white}}
.tip{{position:fixed;display:none;padding:8px 10px;border-radius:10px;background:#17211b;color:white;font-size:12px;pointer-events:none}}
</style></head><body><div class="wrap"><div class="head"><div><h1>Volcano plot: {html.escape(comparison)}</h1>
<p>Colored by p-value significant direction. Thresholds: p <= {p_value_threshold:g}, |log2FC| >= {log2fc_threshold:g}. Top {label_count} hits are labeled.</p></div>
<div class="legend"><span><i style="background:#c44f3a"></i>Up, p-significant</span><span><i style="background:#315fd6"></i>Down, p-significant</span><span><i style="background:#d48806"></i>Large FC only</span><span><i style="background:#9aaab7"></i>Not significant</span></div></div>
<div class="plot-shell"><canvas id="plot" width="1200" height="640"></canvas></div></div><div class="tip" id="tip"></div>
<script>
const points = {payload};
const canvas = document.getElementById('plot');
const ctx = canvas.getContext('2d');
const tip = document.getElementById('tip');
const pad = 74;
const xs = points.map(p => p.x), ys = points.map(p => p.y);
const xAbs = Math.max(...xs.map(v => Math.abs(v)), {log2fc_threshold:g}, 1);
const xmin = -xAbs * 1.12, xmax = xAbs * 1.12, ymax = Math.max(...ys, -Math.log10({p_value_threshold:g}), 1) * 1.12;
function sx(x){{ return pad + (x - xmin) / (xmax - xmin) * (canvas.width - pad * 2); }}
function sy(y){{ return canvas.height - pad - y / ymax * (canvas.height - pad * 2); }}
const colors = {{'Up': '#c44f3a', 'Down': '#315fd6', 'Large FC': '#d48806', 'Not significant': '#9aaab7'}};
ctx.clearRect(0,0,canvas.width,canvas.height);
ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
ctx.strokeStyle = '#edf2f7'; ctx.lineWidth = 1;
for (let i = 0; i <= 5; i += 1) {{
  const y = pad + i * (canvas.height - pad * 2) / 5;
  ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(canvas.width - pad, y); ctx.stroke();
}}
ctx.strokeStyle = '#cbd5e1'; ctx.lineWidth = 1.2;
ctx.beginPath(); ctx.moveTo(pad, canvas.height-pad); ctx.lineTo(canvas.width-pad, canvas.height-pad); ctx.moveTo(pad,pad); ctx.lineTo(pad,canvas.height-pad); ctx.stroke();
ctx.setLineDash([7, 7]);
ctx.strokeStyle = '#98a2b3';
ctx.beginPath();
ctx.moveTo(sx(-{log2fc_threshold:g}), pad); ctx.lineTo(sx(-{log2fc_threshold:g}), canvas.height - pad);
ctx.moveTo(sx({log2fc_threshold:g}), pad); ctx.lineTo(sx({log2fc_threshold:g}), canvas.height - pad);
ctx.moveTo(pad, sy(-Math.log10({p_value_threshold:g}))); ctx.lineTo(canvas.width - pad, sy(-Math.log10({p_value_threshold:g})));
ctx.stroke();
ctx.setLineDash([]);
ctx.fillStyle = '#52616b'; ctx.font = '13px Inter, Arial, sans-serif';
ctx.fillText('log2FC', canvas.width/2 - 24, canvas.height-24); ctx.fillText('-log10(p)', 18, 42);
for (const group of ['Not significant', 'Large FC', 'Down', 'Up']) {{
  for (const p of points.filter(item => item.group === group)) {{
    const strong = p.group !== 'Not significant';
    ctx.fillStyle = colors[p.group] || '#9aaab7';
    ctx.globalAlpha = p.strong ? 0.92 : strong ? 0.72 : 0.30;
    ctx.beginPath(); ctx.arc(sx(p.x), sy(p.y), p.strong ? 4.3 : strong ? 3.4 : 2.3, 0, Math.PI*2); ctx.fill();
  }}
}}
ctx.globalAlpha = 1;
const labeled = points
  .sort((a, b) => (b.y + Math.abs(b.x) * 0.35) - (a.y + Math.abs(a.x) * 0.35))
  .slice(0, {label_count});
ctx.font = '12px Inter, Arial, sans-serif';
ctx.textBaseline = 'middle';
for (const p of labeled) {{
  const x = sx(p.x), y = sy(p.y);
  const label = String(p.gene || '').slice(0, 18);
  const right = p.x >= 0;
  ctx.strokeStyle = colors[p.group] || '#52616b';
  ctx.fillStyle = colors[p.group] || '#52616b';
  ctx.beginPath();
  ctx.moveTo(x + (right ? 6 : -6), y);
  ctx.lineTo(x + (right ? 26 : -26), y - 12);
  ctx.stroke();
  ctx.fillText(label, x + (right ? 30 : -30 - ctx.measureText(label).width), y - 14);
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
    tip.innerHTML = `${{best.gene}}<br>${{best.group}}<br>log2FC=${{best.x}}<br>p=${{Number(best.p).toExponential(2)}}`;
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
        group = str(p.get("group") or "Not significant")
        color = {"Up": "#c44f3a", "Down": "#315fd6"}.get(group, "#9aaab7")
        opacity = ".82" if group != "Not significant" else ".42"
        radius = "2.2" if group != "Not significant" else "1.6"
        circles.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{color}" opacity="{opacity}"/>')
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#f6f8fb"/><text x="12" y="18" font-size="11" fill="#17211b">Volcano plot</text><text x="12" y="31" font-size="8.5" fill="#52616b">{html.escape(comparison[:28])}</text>{"".join(circles)}</svg>',
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
<style>body{{margin:0;font-family:Inter,'Segoe UI','Microsoft YaHei',sans-serif;background:#f7f9fc;color:#1d2939}}.wrap{{padding:24px}}table{{width:100%;border-collapse:collapse;background:white;border:1px solid #d9e2ec;border-radius:16px;overflow:hidden}}td,th{{padding:8px 10px;border-bottom:1px solid #e7edf5}}th{{color:#003cab;background:#f2f6ff}}a{{color:#0052d9;font-weight:800}}</style>
</head><body><div class="wrap"><h1>差异结果导出：{html.escape(comparison)}</h1><p><a href="{html.escape(export_name)}">下载 CSV 结果表</a></p><table><thead><tr><th>Gene</th><th>log2FC</th><th>p-value</th></tr></thead><tbody>{rows_html}</tbody></table></div></body></html>""",
        encoding="utf-8",
    )


def write_diff_export_preview(path: Path) -> None:
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#f7f9fc"/><text x="12" y="17" font-size="11" fill="#1d2939">结果导出</text><rect x="28" y="30" width="164" height="62" rx="10" fill="#fff" stroke="#d9e2ec"/><line x1="40" y1="50" x2="180" y2="50" stroke="#0052d9"/><line x1="40" y1="64" x2="168" y2="64" stroke="#c9d4e5"/><line x1="40" y1="76" x2="152" y2="76" stroke="#c9d4e5"/></svg>',
        encoding="utf-8",
    )
