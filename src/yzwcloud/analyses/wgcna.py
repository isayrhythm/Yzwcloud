from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from yzwcloud.analyses.common import load_sample_columns, write_data_output
from yzwcloud.models import DataObject


def create_wgcna_result(
    source: DataObject,
    output_dir: Path,
    node_id: str,
    params: dict[str, Any] | None = None,
) -> DataObject:
    params = params or {}
    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    sample_columns = load_sample_columns(matrix_path, metadata_path)
    if len(sample_columns) <= 20:
        raise ValueError("WGCNA needs more than 20 samples after QC")

    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_prefix = output_dir / f"{node_id}_{run_stamp}"
    html_path = output_dir / f"{node_id}_{run_stamp}.html"
    preview_path = output_dir / f"{node_id}_{run_stamp}_preview.svg"
    output_json = output_dir / f"{node_id}_{run_stamp}_output.json"

    r_payload = run_r_wgcna(
        matrix_path=matrix_path,
        metadata_path=metadata_path,
        output_prefix=output_prefix,
        params=params,
    )
    write_wgcna_html(html_path, r_payload)
    write_wgcna_preview(preview_path, r_payload.get("modules", []))

    meta = {
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "module_file": r_payload["files"]["modules"],
        "hub_file": r_payload["files"]["hub_genes"],
        "module_trait_file": r_payload["files"]["module_trait"],
        "soft_threshold_file": r_payload["files"]["soft_threshold"],
        "gene_count": int(r_payload["summary"]["assigned_gene_count"]),
        "module_count": int(r_payload["summary"]["module_count"]),
        "sample_count": int(r_payload["summary"]["sample_count"]),
        "soft_power": int(r_payload["summary"]["soft_power"]),
        "network_type": r_payload["summary"].get("network_type", "signed"),
        "gene_selection_mode": r_payload["summary"].get("gene_selection_mode", "top_percent"),
        "top_gene_percent": r_payload["summary"].get("top_gene_percent"),
        "selected_gene_count": int(r_payload["summary"].get("selected_gene_count", r_payload["summary"]["assigned_gene_count"])),
        "variable_gene_count": int(r_payload["summary"].get("variable_gene_count", 0)),
        "method": "r_wgcna",
        "run_id": run_stamp,
    }
    return write_data_output(output_json, "wgcna_result", meta)


def run_r_wgcna(
    matrix_path: Path,
    metadata_path: Path,
    output_prefix: Path,
    params: dict[str, Any],
) -> dict[str, Any]:
    rscript = find_rscript()
    script_path = Path(__file__).resolve().parents[1] / "r" / "run_wgcna.R"
    if not script_path.exists():
        raise ValueError(f"WGCNA R script not found: {script_path}")

    selection_mode = str(params.get("gene_selection_mode") or "fixed")
    if selection_mode not in {"fixed", "top_percent"}:
        selection_mode = "top_percent"
    max_genes = max(50, min(int(params.get("max_genes") or 2000), 10000))
    top_gene_percent = max(1, min(float(params.get("top_gene_percent") or 25), 100))
    min_module_size = max(4, int(params.get("min_module_size") or 20))
    soft_power = int(params.get("soft_power") or 0)
    merge_cut_height = float(params.get("merge_cut_height") or 0.25)
    network_type = str(params.get("network_type") or "signed")
    payload_path = output_prefix.with_name(output_prefix.name + "_r_payload.json")
    log_path = output_prefix.with_name(output_prefix.name + "_r.log")

    command = [
        str(rscript),
        str(script_path),
        str(matrix_path),
        str(metadata_path),
        str(output_prefix),
        str(max_genes),
        str(min_module_size),
        str(soft_power),
        str(merge_cut_height),
        network_type,
        selection_mode,
        str(top_gene_percent if selection_mode == "top_percent" else max_genes),
    ]
    completed = subprocess.run(
        command,
        cwd=str(Path(__file__).resolve().parents[3]),
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    log_path.write_text(
        "\n".join(
            [
                "COMMAND:",
                " ".join(command),
                "",
                "STDOUT:",
                completed.stdout,
                "",
                "STDERR:",
                completed.stderr,
            ]
        ),
        encoding="utf-8",
    )
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()[-8:]
        raise ValueError(
            "R WGCNA failed. Check that R package WGCNA is installed. "
            f"Log: {log_path}. Error: {' | '.join(tail)}"
        )
    if not payload_path.exists():
        raise ValueError(f"R WGCNA finished without payload: {payload_path}. Log: {log_path}")
    return json.loads(payload_path.read_text(encoding="utf-8"))


def find_rscript() -> Path:
    configured = os.getenv("YZWCLOUD_RSCRIPT")
    candidates = [Path(configured)] if configured else []
    resolved = shutil.which("Rscript")
    if resolved:
        candidates.append(Path(resolved))
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    candidates.extend(sorted(program_files.glob("R/R-*/bin/Rscript.exe"), reverse=True))
    candidates.extend(sorted(program_files.glob("R/R-*/bin/x64/Rscript.exe"), reverse=True))
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    raise ValueError(
        "Rscript is not available. Install R and WGCNA, or set YZWCLOUD_RSCRIPT to Rscript.exe."
    )


def write_wgcna_html(path: Path, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False)
    rows_html = []
    for module in payload.get("modules", []):
        hubs = ", ".join(item["gene"] for item in module.get("top_hubs", [])[:5])
        rows_html.append(
            "<tr>"
            f"<td><span class='swatch' style='background:{html.escape(module['color_hex'])}'></span>{html.escape(module['module'])}</td>"
            f"<td>{module['gene_count']}</td>"
            f"<td>{html.escape(module['top_condition'])}</td>"
            f"<td>{float(module['top_correlation']):.3f}</td>"
            f"<td>{html.escape(hubs)}</td>"
            "</tr>"
        )
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>WGCNA</title>
<style>
body{{margin:0;font-family:Inter,'Segoe UI','Microsoft YaHei',sans-serif;background:#f4f8fb;color:#172635}}
.wrap{{padding:24px}}
.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:0 0 18px}}
.card{{padding:12px 14px;border:1px solid #d9e5ec;border-radius:12px;background:white}}
.card strong{{display:block;color:#0e5160;font-size:12px;text-transform:uppercase}}
.card span{{font-size:24px;font-weight:900}}
.grid{{display:grid;grid-template-columns:minmax(420px,1fr) minmax(340px,.82fr);gap:18px;align-items:start}}
.panel{{padding:14px;border:1px solid #d9e5ec;border-radius:16px;background:white;overflow:hidden}}
canvas{{display:block;width:100%;max-width:100%;height:auto;margin:0 auto}}
table{{width:100%;border-collapse:collapse;background:white;border:1px solid #d9e5ec;border-radius:14px;overflow:hidden}}
th,td{{padding:8px 10px;border-bottom:1px solid #edf3f6;text-align:left;font-size:13px;vertical-align:top}}
th{{color:#0e5160;background:#eaf3f6;font-size:12px;text-transform:uppercase}}
.swatch{{display:inline-block;width:11px;height:11px;margin-right:7px;border-radius:999px;vertical-align:-1px}}
.tip{{position:fixed;display:none;padding:8px 10px;border-radius:10px;background:#172635;color:white;font-size:12px;pointer-events:none;box-shadow:0 12px 28px rgba(23,38,53,.22)}}
</style></head><body><div class="wrap"><h1>R WGCNA co-expression modules</h1>
<p>Computed by the R package WGCNA. Interactive plots are rendered by YZWcloud from WGCNA result tables.</p>
<div class="summary">
<div class="card"><strong>Modules</strong><span>{payload["summary"]["module_count"]}</span></div>
<div class="card"><strong>Genes assigned</strong><span>{payload["summary"]["assigned_gene_count"]}</span></div>
<div class="card"><strong>Genes selected</strong><span>{payload["summary"]["selected_gene_count"]}</span></div>
<div class="card"><strong>Samples</strong><span>{payload["summary"]["sample_count"]}</span></div>
<div class="card"><strong>Soft power</strong><span>{payload["summary"]["soft_power"]}</span></div>
</div>
<div class="grid">
<section class="panel"><h2>Module-condition correlation</h2><canvas id="traitPlot" width="920" height="520"></canvas></section>
<section class="panel"><h2>Module summary</h2><table><thead><tr><th>Module</th><th>Genes</th><th>Top condition</th><th>r</th><th>Hub genes</th></tr></thead><tbody>{"".join(rows_html)}</tbody></table></section>
<section class="panel"><h2>Module correlation waterfall</h2><canvas id="waterfallPlot" width="920" height="440"></canvas></section>
<section class="panel"><h2>Soft-threshold fit</h2><canvas id="powerPlot" width="560" height="360"></canvas></section>
</div></div><div class="tip" id="tip"></div>
<script>
const data = {data};
const tip = document.getElementById('tip');
const modules = data.modules || [];
const conditions = data.conditions || [];
function setPlotFont(ctx, size = 12, weight = 400) {{
  ctx.font = `${{weight}} ${{size}}px Inter, "Segoe UI", sans-serif`;
}}
function canvasPanelWidth(canvas, fallback = 680) {{
  const panel = canvas.closest('.panel');
  return Math.max(320, Math.floor((panel?.clientWidth || fallback) - 28));
}}
function maxTextWidth(ctx, texts) {{
  return Math.max(0, ...texts.map(text => ctx.measureText(String(text || '')).width));
}}
function fitText(ctx, text, maxWidth) {{
  const value = String(text || '');
  if (ctx.measureText(value).width <= maxWidth) return value;
  let clipped = value;
  while (clipped.length > 1 && ctx.measureText(clipped + '...').width > maxWidth) {{
    clipped = clipped.slice(0, -1);
  }}
  return clipped.length > 1 ? clipped + '...' : value.slice(0, 1);
}}
function heatColor(value) {{
  const v = Math.max(-1, Math.min(1, value));
  if (v >= 0) {{
    const g = Math.round(245 * (1 - v) + 79 * v);
    const b = Math.round(245 * (1 - v) + 64 * v);
    return `rgb(217,${{g}},${{b}})`;
  }}
  const x = -v;
  const r = Math.round(245 * (1 - x) + 55 * x);
  const g = Math.round(245 * (1 - x) + 118 * x);
  return `rgb(${{r}},${{g}},196)`;
}}
function drawTraitHeatmap() {{
  const canvas = document.getElementById('traitPlot');
  const ctx = canvas.getContext('2d');
  setPlotFont(ctx, 12, 400);
  const panelWidth = canvasPanelWidth(canvas, 680);
  const moduleLabels = modules.map(module => `${{module.module}} (${{module.gene_count}})`);
  const labelWidth = Math.min(Math.max(96, panelWidth * 0.34), Math.max(126, Math.ceil(maxTextWidth(ctx, moduleLabels))));
  const topPad = 44, cellH = 32;
  const cellW = Math.max(
    42,
    Math.min(96, Math.floor((panelWidth - labelWidth - 66) / Math.max(1, conditions.length))),
  );
  const contentWidth = 24 + labelWidth + 18 + conditions.length * cellW;
  const contentStart = Math.max(10, Math.floor((panelWidth - contentWidth) / 2));
  const swatchX = contentStart + 6, labelX = contentStart + 24, left = labelX + labelWidth + 18;
  canvas.width = panelWidth;
  canvas.height = Math.max(240, topPad + modules.length * cellH + 42);
  ctx.clearRect(0,0,canvas.width,canvas.height);
  setPlotFont(ctx, 12, 400);
  ctx.fillStyle = '#172635';
  conditions.forEach((condition, c) => {{
    const x = left + c * cellW + Math.max(6, (cellW - ctx.measureText(condition).width) / 2);
    ctx.fillText(condition, x, 24);
  }});
  modules.forEach((module, r) => {{
    ctx.fillStyle = module.color_hex;
    ctx.beginPath(); ctx.arc(swatchX, topPad + r * cellH + 15, 6, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#172635';
    ctx.fillText(fitText(ctx, `${{module.module}} (${{module.gene_count}})`, labelWidth), labelX, topPad + r * cellH + 19);
    conditions.forEach((condition, c) => {{
      const entry = (data.module_trait || []).find(item => item.module === module.module && item.condition === condition);
      const value = Number(entry?.correlation || 0);
      const x = left + c * cellW, y = topPad + r * cellH;
      ctx.fillStyle = heatColor(value); ctx.fillRect(x, y, cellW - 2, cellH - 2);
      ctx.fillStyle = Math.abs(value) > .55 ? 'white' : '#172635';
      ctx.fillText(value.toFixed(2), x + 28, y + 20);
    }});
  }});
  canvas.onmousemove = event => {{
    const rect = canvas.getBoundingClientRect();
    const x = (event.clientX - rect.left) * canvas.width / rect.width;
    const y = (event.clientY - rect.top) * canvas.height / rect.height;
    const c = Math.floor((x - left) / cellW);
    const r = Math.floor((y - topPad) / cellH);
    if (r >= 0 && r < modules.length && c >= 0 && c < conditions.length) {{
      const module = modules[r], condition = conditions[c];
      const entry = (data.module_trait || []).find(item => item.module === module.module && item.condition === condition);
      tip.style.display = 'block'; tip.style.left = event.clientX + 12 + 'px'; tip.style.top = event.clientY + 12 + 'px';
      tip.innerHTML = `${{module.module}} / ${{condition}}<br>r=${{Number(entry?.correlation || 0).toFixed(3)}}<br>p=${{Number(entry?.p_value || 1).toExponential(2)}}`;
    }} else tip.style.display = 'none';
  }};
}}
function drawWaterfall() {{
  const canvas = document.getElementById('waterfallPlot'), ctx = canvas.getContext('2d');
  const sorted = [...modules].sort((a,b) => Math.abs(b.top_correlation) - Math.abs(a.top_correlation));
  setPlotFont(ctx, 12, 400);
  const panelWidth = canvasPanelWidth(canvas, 720);
  const valueLabels = sorted.map(module => `${{module.top_condition}} ${{Number(module.top_correlation || 0).toFixed(2)}}`);
  const moduleLabelWidth = Math.min(Math.max(82, panelWidth * 0.28), Math.max(88, Math.ceil(maxTextWidth(ctx, sorted.map(module => module.module)))));
  const valueLabelWidth = Math.min(Math.max(72, panelWidth * 0.22), Math.max(72, Math.ceil(maxTextWidth(ctx, valueLabels))));
  const barMax = Math.max(70, Math.floor((panelWidth - moduleLabelWidth - valueLabelWidth - 88) / 2));
  const contentWidth = 22 + moduleLabelWidth + 18 + barMax * 2 + 16 + valueLabelWidth;
  const contentStart = Math.max(10, Math.floor((panelWidth - contentWidth) / 2));
  const dotX = contentStart + 6, labelX = contentStart + 22, left = labelX + moduleLabelWidth + 18;
  const mid = left + barMax, valueX = mid + barMax + 16, top = 42, rowH = 30;
  canvas.width = panelWidth;
  canvas.height = Math.max(220, top + sorted.length * rowH + 36);
  ctx.clearRect(0,0,canvas.width,canvas.height);
  setPlotFont(ctx, 12, 400);
  ctx.strokeStyle = '#b9cbd8'; ctx.beginPath(); ctx.moveTo(mid, top-12); ctx.lineTo(mid, canvas.height-24); ctx.stroke();
  ctx.fillStyle = '#5f7284';
  ctx.fillText('-1', mid - barMax - 4, 18);
  ctx.fillText('0', mid - 4, 18);
  ctx.fillText('+1', mid + barMax - 10, 18);
  sorted.forEach((module, i) => {{
    const y = top + i * rowH;
    const value = Number(module.top_correlation || 0);
    const w = Math.abs(value) * barMax;
    const x = value >= 0 ? mid : mid - w;
    ctx.fillStyle = module.color_hex;
    ctx.beginPath(); ctx.arc(dotX, y + 8, 5, 0, Math.PI * 2); ctx.fill();
    ctx.fillRect(x, y, w, 16);
    ctx.fillStyle = '#172635';
    ctx.fillText(fitText(ctx, module.module, moduleLabelWidth), labelX, y + 12);
    ctx.fillText(fitText(ctx, `${{module.top_condition}} ${{value.toFixed(2)}}`, valueLabelWidth), valueX, y + 12);
  }});
}}
function drawPower() {{
  const canvas = document.getElementById('powerPlot'), ctx = canvas.getContext('2d');
  const rows = data.soft_threshold || [];
  if (!rows.length) return;
  canvas.width = canvasPanelWidth(canvas, 560);
  canvas.height = Math.max(300, Math.min(360, Math.floor(canvas.width * 0.64)));
  const left = 58, top = 28, width = canvas.width - 94, height = canvas.height - 72;
  const xs = rows.map(item => Number(item.power));
  const ys = rows.map(item => Number(item.scale_free_fit || 0));
  const xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys, 0), ymax = Math.max(...ys, .9);
  const sx = v => left + (v - xmin) / Math.max(1, xmax - xmin) * width;
  const sy = v => top + height - (v - ymin) / Math.max(.1, ymax - ymin) * height;
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.strokeStyle = '#b9cbd8'; ctx.beginPath(); ctx.moveTo(left, top); ctx.lineTo(left, top+height); ctx.lineTo(left+width, top+height); ctx.stroke();
  ctx.strokeStyle = '#315fd6'; ctx.beginPath();
  rows.forEach((item, i) => {{ const x = sx(Number(item.power)), y = sy(Number(item.scale_free_fit || 0)); i ? ctx.lineTo(x,y) : ctx.moveTo(x,y); }});
  ctx.stroke();
  rows.forEach(item => {{ ctx.fillStyle = Number(item.power) === Number(data.summary.soft_power) ? '#c44f3a' : '#315fd6'; ctx.beginPath(); ctx.arc(sx(Number(item.power)), sy(Number(item.scale_free_fit || 0)), 4, 0, Math.PI*2); ctx.fill(); }});
  ctx.fillStyle = '#172635'; ctx.fillText('power', left + width / 2, canvas.height - 14); ctx.fillText('scale-free fit', 8, top + 10);
}}
function drawAllPlots() {{
  drawTraitHeatmap(); drawWaterfall(); drawPower();
}}
drawAllPlots();
let resizeTimer;
window.addEventListener('resize', () => {{
  window.clearTimeout(resizeTimer);
  resizeTimer = window.setTimeout(drawAllPlots, 120);
}});
</script></body></html>""",
        encoding="utf-8",
    )


def write_wgcna_preview(path: Path, modules: list[dict[str, Any]]) -> None:
    bars = []
    max_count = max((int(module.get("gene_count", 0)) for module in modules), default=1)
    for index, module in enumerate(modules[:8]):
        height = int(module.get("gene_count", 0)) / max_count * 58
        x = 22 + index * 22
        color = html.escape(str(module.get("color_hex") or "#0052d9"))
        bars.append(
            f'<rect x="{x}" y="{90 - height:.1f}" width="14" height="{height:.1f}" rx="3" fill="{color}" opacity=".82"/>'
        )
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#f5f9fc"/><text x="12" y="18" font-size="11" fill="#172635">R WGCNA modules</text>{"".join(bars)}</svg>',
        encoding="utf-8",
    )
