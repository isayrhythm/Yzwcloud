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
<p>Top {len(genes)} 个基因，数值为按基因标准化后的表达。悬停可查看单元格。</p><canvas id="heatmap"></canvas></div><div class="tip" id="tip"></div>
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


def write_heatmap_preview(path: Path, comparison: str, genes: list[dict[str, Any]]) -> None:
    rects = []
    cell = 5
    for r, gene in enumerate(genes[:18]):
        for c, value in enumerate(gene["values"][:34]):
            x = 14 + c * cell
            y = 24 + r * cell
            v = max(-2, min(2, float(value))) / 2
            color = "#d94f40" if v >= 0 else "#3776c4"
            rects.append(
                f'<rect x="{x}" y="{y}" width="4" height="4" fill="{color}" opacity="{0.25 + abs(v)*0.65:.2f}"/>'
            )
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#fffaf0"/><text x="12" y="17" font-size="11" fill="#17211b">热图 {html.escape(comparison)}</text>{"".join(rects)}</svg>',
        encoding="utf-8",
    )
