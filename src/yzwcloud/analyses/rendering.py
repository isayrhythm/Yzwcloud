from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from yzwcloud.analyses.common import SampleColumn


def write_heatmap_html(
    path: Path,
    comparison: str,
    columns: list[SampleColumn],
    genes: list[dict[str, Any]],
    row_tree: dict[str, Any] | None = None,
    col_tree: dict[str, Any] | None = None,
    condition_colors: dict[str, str] | None = None,
) -> None:
    payload = json.dumps(
        {
            "samples": [
                {"name": column.name, "condition": column.condition, "group": column.group}
                for column in columns
            ],
            "genes": genes,
            "rowTree": row_tree,
            "colTree": col_tree,
            "conditionColors": condition_colors or {},
        },
        ensure_ascii=False,
    )
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Heatmap {html.escape(comparison)}</title>
<style>
body{{margin:0;font-family:Inter,'Segoe UI','Microsoft YaHei',sans-serif;background:#f5f9fc;color:#172635}}
.wrap{{padding:24px}}
canvas{{border:1px solid #d8e5ee;border-radius:12px;background:white;max-width:100%}}
.tip{{position:fixed;display:none;z-index:20;padding:8px 10px;border-radius:10px;background:#172635;color:white;font-size:12px;pointer-events:none;box-shadow:0 12px 28px rgba(23,38,53,.22)}}
</style></head><body><div class="wrap"><h1>Heatmap: {html.escape(comparison)}</h1>
<p>Top {len(genes)} genes, z-scored by gene. Hover cells for values; click a gene name to copy it.</p>
<canvas id="heatmap"></canvas></div><div class="tip" id="tip"></div>
<script>
const data = {payload};
const cell = 16;
const geneLabelWidth = 150;
const rowTreeWidth = 72;
const colTreeHeight = 74;
const left = geneLabelWidth + rowTreeWidth + 16;
const topPad = colTreeHeight + 46;
const canvas = document.getElementById('heatmap');
const tip = document.getElementById('tip');
canvas.width = left + data.samples.length * cell + 32;
canvas.height = topPad + data.genes.length * cell + 42;
const ctx = canvas.getContext('2d');
const fallbackPalette = ['#0f8a8f', '#315fd6', '#c44f3a', '#7b61b5', '#20804f', '#c27a18', '#8b5f4d'];
const conditions = [...new Set(data.samples.map(sample => sample.condition || 'unknown'))];
const conditionColors = Object.fromEntries(conditions.map((condition, index) => [
  condition,
  data.conditionColors?.[condition] || fallbackPalette[index % fallbackPalette.length],
]));
const rowPalette = ['#315fd6', '#0f8a8f', '#c44f3a', '#7b61b5', '#20804f', '#c27a18'];
function sampleName(index) {{ return data.samples[index]?.name || String(index + 1); }}
function sampleCondition(index) {{ return data.samples[index]?.condition || 'unknown'; }}

function color(v) {{
  const x = Math.max(-2, Math.min(2, Number(v))) / 2;
  if (x >= 0) return `rgb(${{Math.round(245*x+245*(1-x))}},${{Math.round(245*(1-x)+88*x)}},${{Math.round(245*(1-x)+70*x)}})`;
  return `rgb(${{Math.round(245*(1+x)+55*(-x))}},${{Math.round(245*(1+x)+118*(-x))}},${{Math.round(245*(1+x)+196*(-x))}})`;
}}

function maxHeight(tree) {{
  if (!tree || tree.leaf !== undefined) return 0;
  return Math.max(Number(tree.height || 0), maxHeight(tree.left), maxHeight(tree.right));
}}

function drawColumnTree(tree) {{
  if (!tree) return;
  const leaves = Object.fromEntries(data.samples.map((_, index) => [index, left + index * cell + cell / 2]));
  const scale = (colTreeHeight - 18) / (maxHeight(tree) || 1);
  const yBase = topPad - 10;
  function drawNode(node) {{
    if (node.leaf !== undefined) {{
      const condition = sampleCondition(node.leaf);
      return {{ x: leaves[node.leaf], y: yBase, condition, color: conditionColors[condition] || '#5f7284' }};
    }}
    const leftNode = drawNode(node.left);
    const rightNode = drawNode(node.right);
    const y = yBase - Number(node.height || 0) * scale;
    const pureCondition = leftNode.condition && leftNode.condition === rightNode.condition ? leftNode.condition : null;
    const branchColor = pureCondition ? conditionColors[pureCondition] : '#8fa0ae';
    ctx.strokeStyle = branchColor;
    ctx.lineWidth = pureCondition ? 1.7 : 1.1;
    ctx.beginPath();
    ctx.moveTo(leftNode.x, leftNode.y);
    ctx.lineTo(leftNode.x, y);
    ctx.lineTo(rightNode.x, y);
    ctx.lineTo(rightNode.x, rightNode.y);
    ctx.stroke();
    return {{ x: (leftNode.x + rightNode.x) / 2, y, condition: pureCondition, color: branchColor }};
  }}
  drawNode(tree);
}}

function drawRowTree(tree) {{
  if (!tree) return;
  const leaves = Object.fromEntries(data.genes.map((_, index) => [index, topPad + index * cell + cell / 2]));
  const scale = (rowTreeWidth - 14) / (maxHeight(tree) || 1);
  const xBase = left - 10;
  function drawNode(node, branchColor = '#5f7284') {{
    if (node.leaf !== undefined) return {{ x: xBase, y: leaves[node.leaf] }};
    const leftNode = drawNode(node.left, branchColor);
    const rightNode = drawNode(node.right, branchColor);
    const x = xBase - Number(node.height || 0) * scale;
    ctx.strokeStyle = branchColor;
    ctx.lineWidth = 1.25;
    ctx.beginPath();
    ctx.moveTo(leftNode.x, leftNode.y);
    ctx.lineTo(x, leftNode.y);
    ctx.lineTo(x, rightNode.y);
    ctx.lineTo(rightNode.x, rightNode.y);
    ctx.stroke();
    return {{ x, y: (leftNode.y + rightNode.y) / 2 }};
  }}
  if (tree.left && tree.right) {{
    const leftNode = drawNode(tree.left, rowPalette[0]);
    const rightNode = drawNode(tree.right, rowPalette[1]);
    const x = xBase - Number(tree.height || 0) * scale;
    ctx.strokeStyle = '#8fa0ae';
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(leftNode.x, leftNode.y);
    ctx.lineTo(x, leftNode.y);
    ctx.lineTo(x, rightNode.y);
    ctx.lineTo(rightNode.x, rightNode.y);
    ctx.stroke();
  }} else {{
    drawNode(tree, rowPalette[0]);
  }}
}}

drawColumnTree(data.colTree);
drawRowTree(data.rowTree);

ctx.font = '11px Inter, sans-serif';
data.samples.forEach((sample, index) => {{
  const x = left + index * cell + 11;
  const condition = sample.condition || 'unknown';
  ctx.fillStyle = conditionColors[condition] || '#5f7284';
  ctx.fillRect(left + index * cell, topPad - 7, cell - 1, 5);
  ctx.save();
  ctx.translate(x, topPad - 18);
  ctx.rotate(-Math.PI / 4);
  ctx.fillStyle = conditionColors[condition] || '#5f7284';
  ctx.fillText(String(sample.name).slice(0, 16), 0, 0);
  ctx.restore();
}});
conditions.forEach((condition, index) => {{
  const x = left + index * 92;
  ctx.fillStyle = conditionColors[condition] || '#5f7284';
  ctx.fillRect(x, 18, 10, 10);
  ctx.fillStyle = '#172635';
  ctx.fillText(condition, x + 14, 27);
}});

data.genes.forEach((gene, row) => {{
  ctx.fillStyle = '#172635';
  ctx.fillText(String(gene.gene).slice(0, 20), 10, topPad + row * cell + 12);
  gene.values.forEach((value, col) => {{
    ctx.fillStyle = color(value);
    ctx.fillRect(left + col * cell, topPad + row * cell, cell - 1, cell - 1);
  }});
}});

canvas.addEventListener('click', event => {{
  const rect = canvas.getBoundingClientRect();
  const x = (event.clientX - rect.left) * canvas.width / rect.width;
  const y = (event.clientY - rect.top) * canvas.height / rect.height;
  const row = Math.floor((y - topPad) / cell);
  if (row >= 0 && row < data.genes.length && x >= 0 && x < geneLabelWidth) {{
    const gene = data.genes[row].gene;
    navigator.clipboard?.writeText(gene);
    tip.style.display = 'block';
    tip.style.left = event.clientX + 12 + 'px';
    tip.style.top = event.clientY + 12 + 'px';
    tip.innerHTML = `Copied gene: ${{gene}}`;
  }}
}});

canvas.addEventListener('mousemove', event => {{
  const rect = canvas.getBoundingClientRect();
  const x = (event.clientX - rect.left) * canvas.width / rect.width;
  const y = (event.clientY - rect.top) * canvas.height / rect.height;
  const col = Math.floor((x - left) / cell);
  const row = Math.floor((y - topPad) / cell);
  if (row >= 0 && row < data.genes.length && col >= 0 && col < data.samples.length) {{
    const gene = data.genes[row];
    const value = gene.values[col];
    tip.style.display = 'block';
    tip.style.left = event.clientX + 12 + 'px';
    tip.style.top = event.clientY + 12 + 'px';
    tip.innerHTML = `${{gene.gene}}<br>${{sampleName(col)}}<br>${{sampleCondition(col)}}<br>z=${{value}}`;
  }} else {{
    tip.style.display = 'none';
  }}
}});
canvas.addEventListener('mouseleave', () => {{ tip.style.display = 'none'; }});
</script></body></html>""",
        encoding="utf-8",
    )


def write_heatmap_preview(path: Path, comparison: str, genes: list[dict[str, Any]]) -> None:
    rects = []
    cell = 5
    for row, gene in enumerate(genes[:18]):
        for col, value in enumerate(gene["values"][:34]):
            x = 14 + col * cell
            y = 24 + row * cell
            v = max(-2, min(2, float(value))) / 2
            color = "#d94f40" if v >= 0 else "#3776c4"
            rects.append(
                f'<rect x="{x}" y="{y}" width="4" height="4" fill="{color}" opacity="{0.25 + abs(v)*0.65:.2f}"/>'
            )
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#f5f9fc"/><text x="12" y="17" font-size="11" fill="#172635">Heatmap {html.escape(comparison)}</text>{"".join(rects)}</svg>',
        encoding="utf-8",
    )
