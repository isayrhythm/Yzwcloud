from __future__ import annotations

import base64
import html
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from yzwcloud.models import Graph, GraphNode
from yzwcloud.task_store import get_task_dir, load_graph, load_task, read_log

DEFAULT_REPORT_MODEL = "deepseek-v4-flash"

TASK_REPORT_SYSTEM_PROMPT = """You are YZW BioCloud Workflow Report Agent.
Write a concise Chinese workflow-level report from node-level bioinformatics reports.

Rules:
- Return JSON only.
- Use exactly these keys: summary, narrative, methods, results, limitations, next_steps.
- narrative, methods, results, limitations, and next_steps must be arrays of short strings.
- Base claims only on the provided node reports, workflow graph, methods, and metadata.
- Do not invent biological conclusions, statistical significance, or visual patterns.
- Explain how the current result was produced step by step.
"""


def build_task_report(task_id: str) -> dict[str, Any]:
    task = load_task(task_id)
    graph = load_graph(task_id)
    task_dir = get_task_dir(task_id)
    output_dir = task_dir / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    nodes = _ordered_nodes(graph)
    log_lines = [line for line in read_log(task_id).splitlines() if line.strip()]
    workflow_svg_path = output_dir / "analysis_report_current_workflow.svg"
    workflow_svg_path.write_text(_workflow_svg(nodes, graph.edges), encoding="utf-8")
    steps = [_node_report_entry(node, output_dir) for node in nodes]
    figures = _figure_entries(nodes, output_dir)
    report = {
        "task": task.model_dump(mode="json"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": _task_summary(nodes),
        "agent_summary": _create_task_agent_summary(task.model_dump(mode="json"), graph, steps, figures),
        "workflow": {
            "node_count": len(nodes),
            "edge_count": len(graph.edges),
            "svg_file": str(workflow_svg_path),
        },
        "steps": steps,
        "figures": figures,
        "warnings": _collect_warnings(nodes),
        "next_steps": _collect_next_steps(nodes),
        "log_tail": log_lines[-16:],
    }
    json_path = output_dir / "analysis_report_current.json"
    html_path = output_dir / "analysis_report_current.html"
    pdf_path = output_dir / "analysis_report_current.pdf"
    report["json_file"] = str(json_path)
    report["html_file"] = str(html_path)
    report["pdf_file"] = str(pdf_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(_task_report_html(report, workflow_svg_path), encoding="utf-8")
    return report


def render_task_report_pdf(report: dict[str, Any]) -> Path:
    html_path = Path(str(report["html_file"])).resolve()
    pdf_path = Path(str(report["pdf_file"])).resolve()
    browser = _find_pdf_browser()
    if browser is None:
        raise RuntimeError("Edge or Chrome is required for server-side PDF export. Open the HTML report and use browser Print to PDF.")
    command = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--allow-file-access-from-files",
        "--print-to-pdf-no-header",
        f"--print-to-pdf={pdf_path}",
        html_path.as_uri(),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    if completed.returncode != 0 or not pdf_path.exists() or pdf_path.stat().st_size == 0:
        error = (completed.stderr or completed.stdout or "unknown browser export error").strip()
        raise RuntimeError(f"PDF export failed: {error}")
    return pdf_path


def _find_pdf_browser() -> Path | None:
    candidates = [
        shutil.which("msedge"),
        shutil.which("chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def _ordered_nodes(graph: Graph) -> list[GraphNode]:
    nodes = {node.id: node for node in graph.nodes}
    incoming = {node_id: 0 for node_id in nodes}
    children: dict[str, list[str]] = {}
    for edge in graph.edges:
        source = edge.get("source", "")
        target = edge.get("target", "")
        if source not in nodes or target not in nodes:
            continue
        children.setdefault(source, []).append(target)
        incoming[target] += 1
    queue = [node.id for node in graph.nodes if incoming[node.id] == 0]
    ordered = []
    seen = set()
    while queue:
        node_id = queue.pop(0)
        if node_id in seen:
            continue
        seen.add(node_id)
        ordered.append(nodes[node_id])
        for child in children.get(node_id, []):
            incoming[child] -= 1
            if incoming[child] == 0:
                queue.append(child)
    ordered.extend(node for node in graph.nodes if node.id not in seen)
    return ordered


def _task_summary(nodes: list[GraphNode]) -> dict[str, Any]:
    completed = [node for node in nodes if node.status == "completed"]
    failed = [node for node in nodes if node.status == "failed"]
    outputs = [node for node in nodes if node.output]
    return {
        "total_nodes": len(nodes),
        "completed_nodes": len(completed),
        "failed_nodes": len(failed),
        "output_nodes": len(outputs),
        "figure_count": sum(bool(node.output and node.output.meta.get("preview_file")) for node in nodes),
        "status_text": (
            f"当前流程包含 {len(nodes)} 个节点，已完成 {len(completed)} 个，"
            f"有 {len(outputs)} 个可汇报输出，失败节点 {len(failed)} 个。"
        ),
    }


def _node_report_entry(node: GraphNode, output_dir: Path) -> dict[str, Any]:
    output = node.output
    meta = dict(output.meta) if output else {}
    report = meta.get("agent_report") or {}
    return {
        "id": node.id,
        "name": node.name,
        "description": node.description,
        "status": str(node.status.value if hasattr(node.status, "value") else node.status),
        "depends_on": node.depends_on,
        "output_type": output.type if output else node.output_type,
        "params": _compact_params(node.params),
        "summary": report.get("summary") or _fallback_node_summary(node),
        "findings": report.get("findings") or [],
        "methods": report.get("methods") or _method_lines(meta, node.params),
        "warnings": report.get("warnings") or [],
        "next_steps": report.get("next_steps") or [],
        "preview": _preview_data_uri(meta.get("preview_file"), output_dir),
    }


def _figure_entries(nodes: list[GraphNode], output_dir: Path) -> list[dict[str, Any]]:
    figures = []
    for node in nodes:
        if not node.output:
            continue
        preview = _preview_data_uri(node.output.meta.get("preview_file"), output_dir)
        if not preview:
            continue
        report = node.output.meta.get("agent_report") or {}
        figures.append(
            {
                "node_id": node.id,
                "title": node.name,
                "output_type": node.output.type,
                "summary": report.get("summary") or _fallback_node_summary(node),
                "preview": preview,
            }
        )
    return figures


def _collect_warnings(nodes: list[GraphNode]) -> list[str]:
    warnings = []
    for node in nodes:
        if node.status == "failed":
            warnings.append(f"{node.name} 执行失败：{node.error or '未记录错误'}")
        if node.output:
            report = node.output.meta.get("agent_report") or {}
            warnings.extend(f"{node.name}：{item}" for item in report.get("warnings") or [])
    return _dedupe(warnings) or ["当前没有记录到阻断流程的失败节点；正式解读前仍需人工复核实验设计和统计假设。"]


def _collect_next_steps(nodes: list[GraphNode]) -> list[str]:
    steps = []
    for node in nodes:
        if not node.output:
            continue
        report = node.output.meta.get("agent_report") or {}
        steps.extend(report.get("next_steps") or [])
    return _dedupe(steps)[:12] or ["继续完成下游分析节点，并结合实验设计复核当前结果。"]


def _fallback_node_summary(node: GraphNode) -> str:
    if node.output:
        return f"{node.name} 已生成 {node.output.type} 输出。"
    return f"{node.name} 当前状态为 {node.status.value if hasattr(node.status, 'value') else node.status}。"


def _method_lines(meta: dict[str, Any], params: dict[str, Any]) -> list[str]:
    methods = []
    if meta.get("method"):
        methods.append(f"方法：{meta['method']}。")
    for key in ("qc_preset", "p_value", "log2fc", "cluster_method", "normalization_method", "transform", "scaling"):
        value = (meta.get("params") or {}).get(key, meta.get(key, params.get(key)))
        if value not in {None, ""}:
            methods.append(f"{key}={value}")
    return methods


def _create_task_agent_summary(
    task: dict[str, Any],
    graph: Graph,
    steps: list[dict[str, Any]],
    figures: list[dict[str, Any]],
) -> dict[str, Any]:
    evidence = {
        "task": {
            "id": task.get("task_id", ""),
            "name": task.get("name", ""),
            "status": task.get("status", ""),
        },
        "workflow": {
            "node_count": len(steps),
            "edge_count": len(graph.edges),
            "completed_nodes": sum(step["status"] == "completed" for step in steps),
            "failed_nodes": sum(step["status"] == "failed" for step in steps),
            "figure_count": len(figures),
            "lineage": [
                {
                    "source": edge.get("source", ""),
                    "target": edge.get("target", ""),
                }
                for edge in graph.edges
            ],
        },
        "nodes": [
            {
                "id": step["id"],
                "name": step["name"],
                "status": step["status"],
                "output_type": step["output_type"],
                "summary": step["summary"],
                "findings": step["findings"][:4],
                "methods": step["methods"][:4],
                "warnings": step["warnings"][:4],
                "next_steps": step["next_steps"][:4],
            }
            for step in steps
        ],
        "figures": [
            {
                "node_id": figure["node_id"],
                "title": figure["title"],
                "output_type": figure["output_type"],
                "summary": figure["summary"],
            }
            for figure in figures
        ],
    }
    fallback = _rule_based_task_summary(evidence)
    llm_result = _generate_task_llm_summary(evidence)
    content = llm_result.get("report") if llm_result.get("llm_status") == "ok" else fallback
    return {
        "title": "流程报告 · Agent 总结",
        "summary": content["summary"],
        "narrative": content["narrative"],
        "methods": content["methods"],
        "results": content["results"],
        "limitations": content["limitations"],
        "next_steps": content["next_steps"],
        "evidence": evidence,
        "generated_by": "llm" if llm_result.get("llm_status") == "ok" else "rule_based_fallback",
        "llm_status": llm_result.get("llm_status", "fallback"),
        "llm_error": llm_result.get("llm_error", ""),
        "model": llm_result.get("model", ""),
    }


def _rule_based_task_summary(evidence: dict[str, Any]) -> dict[str, Any]:
    task = evidence["task"]
    workflow = evidence["workflow"]
    nodes = evidence["nodes"]
    completed = [node for node in nodes if node["status"] == "completed"]
    output_nodes = [node for node in completed if node["output_type"]]
    method_lines = _dedupe([item for node in completed for item in node.get("methods", [])])[:8]
    result_lines = _dedupe([node["summary"] for node in output_nodes if node.get("summary")])[:8]
    limitation_lines = _dedupe([item for node in nodes for item in node.get("warnings", [])])[:8]
    next_lines = _dedupe([item for node in nodes for item in node.get("next_steps", [])])[:8]
    first_node = completed[0]["name"] if completed else "输入节点"
    last_node = completed[-1]["name"] if completed else "当前节点"
    return {
        "summary": (
            f"{task.get('name') or '当前任务'} 已形成包含 {workflow['node_count']} 个节点的分析流程，"
            f"当前完成 {workflow['completed_nodes']} 个节点，产出 {workflow['figure_count']} 张可汇报结果图。"
        ),
        "narrative": [
            f"用户当前围绕任务“{task.get('name') or task.get('id')}”构建分析流程，状态为 {task.get('status') or 'unknown'}。",
            f"流程从 {first_node} 开始，沿依赖关系逐步生成到 {last_node} 等结果节点。",
            f"当前报告由 {len(output_nodes)} 个节点级 Agent 总结组合而成，并嵌入 {workflow['figure_count']} 张实际分析图。",
        ],
        "methods": method_lines or ["当前节点报告中尚未记录可汇总的方法参数。"],
        "results": result_lines or ["当前流程尚未产生可汇总的结果节点。"],
        "limitations": limitation_lines or ["正式解释前仍需人工复核实验设计、统计阈值和样本分组。"],
        "next_steps": next_lines or ["继续补齐下游分析，并复核关键结果图与节点级解释。"],
    }


def _generate_task_llm_summary(evidence: dict[str, Any]) -> dict[str, Any]:
    api_key = _env_value("DEEPSEEK_API_KEY")
    if not api_key:
        return {"llm_status": "missing_api_key"}
    base_url = _env_value("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = _env_value("DEEPSEEK_REPORT_MODEL", _env_value("DEEPSEEK_ROUTER_MODEL", DEFAULT_REPORT_MODEL))
    payload = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": TASK_REPORT_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(evidence, ensure_ascii=False)},
        ],
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        return {"llm_status": "ok", "report": _validate_task_llm_report(json.loads(content)), "model": model}
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError, ValueError) as exc:
        return {"llm_status": "error", "llm_error": str(exc), "model": model}


def _validate_task_llm_report(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": str(value["summary"])[:800],
        "narrative": _clean_text_list(value["narrative"]),
        "methods": _clean_text_list(value["methods"]),
        "results": _clean_text_list(value["results"]),
        "limitations": _clean_text_list(value["limitations"]),
        "next_steps": _clean_text_list(value["next_steps"]),
    }


def _clean_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("Expected list in task report LLM response")
    return [str(item)[:500] for item in value if str(item).strip()][:12]


def _env_value(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value.strip() if value else default


def _compact_params(params: dict[str, Any]) -> dict[str, Any]:
    ignored = {"uploaded_inputs", "agent_progress", "agent_report"}
    return {
        str(key): value
        for key, value in params.items()
        if key not in ignored and isinstance(value, (str, int, float, bool, list))
    }


def _preview_data_uri(value: Any, output_dir: Path) -> str:
    if not value:
        return ""
    path = Path(str(value))
    try:
        resolved = path.resolve()
        if output_dir.resolve() not in resolved.parents or not resolved.exists():
            return ""
        suffix = resolved.suffix.lower()
        mime = {
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(suffix)
        if not mime:
            return ""
        encoded = base64.b64encode(resolved.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    except OSError:
        return ""


def _workflow_svg(nodes: list[GraphNode], edges: list[dict[str, str]]) -> str:
    levels = _workflow_levels(nodes, edges)
    grouped: dict[int, list[GraphNode]] = {}
    for node in nodes:
        grouped.setdefault(levels.get(node.id, 0), []).append(node)

    card_width = 220
    card_height = 60
    column_gap = 42
    row_gap = 28
    left_pad = 42
    top_pad = 36
    max_level = max(grouped, default=0)
    max_rows = max((len(group) for group in grouped.values()), default=1)
    width = max(980, left_pad * 2 + (max_level + 1) * card_width + max_level * column_gap)
    height = max(300, top_pad * 2 + max_rows * card_height + (max_rows - 1) * row_gap)

    node_positions: dict[str, tuple[int, int]] = {}
    for level in range(max_level + 1):
        group = grouped.get(level, [])
        group_height = len(group) * card_height + max(0, len(group) - 1) * row_gap
        y_offset = top_pad + max(0, (height - top_pad * 2 - group_height) // 2)
        for row, node in enumerate(group):
            x = left_pad + level * (card_width + column_gap)
            y = y_offset + row * (card_height + row_gap)
            node_positions[node.id] = (x, y)

    edge_lines = []
    for edge in edges:
        source = node_positions.get(edge.get("source", ""))
        target = node_positions.get(edge.get("target", ""))
        if not source or not target:
            continue
        source_x = source[0] + card_width
        source_y = source[1] + card_height // 2
        target_x = target[0]
        target_y = target[1] + card_height // 2
        curve = max(48, (target_x - source_x) // 2)
        edge_lines.append(
            f'<path d="M {source_x} {source_y} C {source_x + curve} {source_y}, {target_x - curve} {target_y}, {target_x} {target_y}" '
            'fill="none" stroke="#8ab9b5" stroke-width="3" marker-end="url(#arrow)"/>'
        )
    cards = []
    for node in nodes:
        x, y = node_positions[node.id]
        color = {"completed": "#0f8a8f", "failed": "#c44f3a", "running": "#315fd6"}.get(
            node.status.value if hasattr(node.status, "value") else str(node.status),
            "#7d8d99",
        )
        cards.append(
            f'<rect x="{x}" y="{y}" width="{card_width}" height="{card_height}" rx="14" fill="#ffffff" stroke="{color}" stroke-width="2"/>'
            f'<circle cx="{x + 23}" cy="{y + 32}" r="8" fill="{color}"/>'
            f'<text x="{x + 38}" y="{y + 25}" fill="#14303a" font-size="13" font-weight="700">{html.escape(_short_svg_text(node.name, 23))}</text>'
            f'<text x="{x + 38}" y="{y + 44}" fill="#6b7c88" font-size="10">{html.escape(_short_svg_text(node.id, 20))} · {html.escape(str(node.status.value if hasattr(node.status, "value") else node.status))}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#8ab9b5"/></marker></defs>'
        '<rect width="100%" height="100%" rx="24" fill="#f6fbfb"/>'
        f'{"".join(edge_lines)}{"".join(cards)}</svg>'
    )


def _workflow_levels(nodes: list[GraphNode], edges: list[dict[str, str]]) -> dict[str, int]:
    node_ids = {node.id for node in nodes}
    children: dict[str, list[str]] = {}
    incoming = {node_id: 0 for node_id in node_ids}
    for edge in edges:
        source = edge.get("source", "")
        target = edge.get("target", "")
        if source not in node_ids or target not in node_ids:
            continue
        children.setdefault(source, []).append(target)
        incoming[target] += 1

    levels = {node_id: 0 for node_id in node_ids}
    queue = [node.id for node in nodes if incoming.get(node.id, 0) == 0]
    seen: set[str] = set()
    while queue:
        node_id = queue.pop(0)
        if node_id in seen:
            continue
        seen.add(node_id)
        for child in children.get(node_id, []):
            levels[child] = max(levels[child], levels[node_id] + 1)
            incoming[child] -= 1
            if incoming[child] == 0:
                queue.append(child)
    return levels


def _short_svg_text(value: Any, max_chars: int) -> str:
    text = str(value)
    return text if len(text) <= max_chars else f"{text[: max_chars - 1]}…"


def _task_report_html(report: dict[str, Any], workflow_svg_path: Path) -> str:
    summary = report["summary"]
    agent_summary = report["agent_summary"]
    steps = report["steps"]
    figures = report["figures"]
    workflow_uri = _preview_data_uri(workflow_svg_path, workflow_svg_path.parent)
    pages = [
        _page(
            "01",
            "分析任务总览",
            f"""<div class="cover"><p class="eyebrow">YZW BioCloud · Analysis Report</p>
<h1>{html.escape(str(report["task"]["name"]))}</h1>
<p class="lead">{html.escape(agent_summary["summary"])}</p>
<p class="stamp">{html.escape(summary["status_text"])}</p>
<div class="metrics">{_metric("节点", summary["total_nodes"])}{_metric("已完成", summary["completed_nodes"])}
{_metric("输出", summary["output_nodes"])}{_metric("结果图", summary["figure_count"])}</div>
<p class="stamp">生成时间：{html.escape(report["generated_at"])}</p></div>""",
        ),
        _page(
            "02",
            "当前分析流程",
            f"""<p class="lead">流程图记录了当前任务如何从输入逐步产生结果。每个节点的状态、方法与输出均保留在任务图中。</p>
<div class="workflow-figure"><img src="{workflow_uri}" alt="workflow"/></div>""",
        ),
        _page("03", "方法与执行轨迹", _step_table(steps)),
        _page(
            "04",
            "流程报告总结",
            f"""<div class="summary-grid"><section><h2>用户做了什么</h2>{_list(agent_summary["narrative"])}</section>
<section><h2>使用的方法</h2>{_list(agent_summary["methods"])}</section>
<section><h2>当前结果</h2>{_list(agent_summary["results"])}</section>
<section><h2>解释边界</h2>{_list(agent_summary["limitations"])}</section></div>""",
        ),
    ]
    for index in range(0, len(figures), 2):
        chunk = figures[index : index + 2]
        pages.append(_page(f"{5 + index // 2:02d}", "实际结果图", _figure_grid(chunk)))
    pages.append(
        _page(
            f"{5 + (len(figures) + 1) // 2:02d}",
            "Agent 汇总与解释边界",
            f"""<div class="split"><section><h2>当前结论</h2>{_finding_cards(steps)}</section>
<section><h2>需要注意</h2>{_list(report["warnings"])}</section></div>""",
        )
    )
    pages.append(
        _page(
            f"{6 + (len(figures) + 1) // 2:02d}",
            "建议的下一步",
            f"""<div class="split"><section><h2>继续分析</h2>{_list(agent_summary["next_steps"] or report["next_steps"])}</section>
<section><h2>执行日志末尾</h2><pre>{html.escape(chr(10).join(report["log_tail"]))}</pre></section></div>""",
        )
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(str(report["task"]["name"]))} · Analysis Report</title>
<style>{_report_css()}</style></head><body>
<button class="print-button" onclick="window.print()">打印 / 保存为 PDF</button>
{"".join(pages)}
</body></html>"""


def _page(number: str, title: str, content: str) -> str:
    return f'<article class="slide"><header><span>{number}</span><h1>{html.escape(title)}</h1></header><main>{content}</main><footer>YZW BioCloud · Agent-driven bioinformatics workflow</footer></article>'


def _metric(label: str, value: Any) -> str:
    return f'<div><span>{html.escape(label)}</span><strong>{html.escape(str(value))}</strong></div>'


def _step_table(steps: list[dict[str, Any]]) -> str:
    rows = []
    for index, step in enumerate(steps, start=1):
        methods = "；".join(step["methods"]) or "未记录额外方法参数"
        rows.append(
            f"<tr><td>{index}</td><td><strong>{html.escape(step['name'])}</strong><small>{html.escape(step['id'])}</small></td>"
            f"<td>{html.escape(step['status'])}</td><td>{html.escape(step['output_type'])}</td><td>{html.escape(methods)}</td></tr>"
        )
    return f'<table><thead><tr><th>#</th><th>节点</th><th>状态</th><th>输出</th><th>方法与参数</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'


def _figure_grid(figures: list[dict[str, Any]]) -> str:
    cards = []
    for figure in figures:
        cards.append(
            f"""<section class="figure-card"><div><h2>{html.escape(figure["title"])}</h2>
<span>{html.escape(figure["output_type"])}</span></div><img src="{figure["preview"]}" alt="{html.escape(figure["title"])}"/>
<p>{html.escape(figure["summary"])}</p></section>"""
        )
    return f'<div class="figure-grid">{"".join(cards)}</div>'


def _finding_cards(steps: list[dict[str, Any]]) -> str:
    cards = []
    for step in steps:
        if not step["findings"]:
            continue
        cards.append(f'<article class="note"><strong>{html.escape(step["name"])}</strong>{_list(step["findings"])}</article>')
    return "".join(cards) or '<p class="muted">当前节点尚未产生可汇总发现。</p>'


def _list(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{html.escape(str(item))}</li>" for item in items) + "</ul>"


def _report_css() -> str:
    return """
@page{size:13.333in 7.5in;margin:0}*{box-sizing:border-box}body{margin:0;background:#dfeaea;color:#112b35;font-family:Inter,"Microsoft YaHei",Arial,sans-serif}
.print-button{position:fixed;right:18px;top:18px;z-index:10;padding:10px 14px;border:0;border-radius:999px;background:#0f6b57;color:#fff;font-weight:800;cursor:pointer}
.slide{position:relative;width:min(1280px,calc(100vw - 24px));height:720px;margin:22px auto;padding:34px 44px 38px;overflow:auto;background:#fff;box-shadow:0 18px 54px rgba(17,43,53,.16);page-break-after:always}
header{display:flex;align-items:center;gap:14px;border-bottom:2px solid #d9e9e9;padding-bottom:12px}header span{display:grid;width:34px;height:34px;place-items:center;border-radius:999px;background:#0f8a8f;color:#fff;font-size:12px;font-weight:900}
h1{margin:0;color:#0f5e59;font-size:30px}h2{margin:0 0 8px;color:#0e5160;font-size:17px}.eyebrow{color:#0f8a8f;font-size:14px;font-weight:900;letter-spacing:.18em;text-transform:uppercase}
main{padding-top:20px}.cover{display:grid;align-content:center;min-height:570px}.cover h1{max-width:940px;font-size:52px}.lead{max-width:1040px;color:#536b76;font-size:19px;line-height:1.65}.stamp,.muted{color:#7a8b93}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:34px 0}.metrics div{padding:16px;border:1px solid #d8e6e7;border-radius:16px;background:#f8fbfb}.metrics span{display:block;color:#68808a;font-size:13px}.metrics strong{display:block;margin-top:6px;color:#0f6b57;font-size:30px}
.workflow-figure{height:520px;overflow:auto;border:1px solid #d8e6e7;border-radius:18px;background:#f6fbfb}.workflow-figure img{display:block;width:100%;height:auto}
table{width:100%;border-collapse:collapse;background:#fff;font-size:12px}th,td{padding:10px;border-bottom:1px solid #e4eeee;text-align:left;vertical-align:top}th{color:#0f6b57;background:#f0f8f7}td small{display:block;margin-top:4px;color:#829198}
.figure-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.figure-card{display:grid;grid-template-rows:auto 300px auto;padding:16px;border:1px solid #d8e6e7;border-radius:18px;background:#fbfdfd}.figure-card div{display:flex;justify-content:space-between;gap:14px}.figure-card span{color:#7b61b5;font-size:12px;font-weight:800}.figure-card img{width:100%;height:290px;object-fit:contain}.figure-card p{margin:8px 0 0;color:#546b75;font-size:14px;line-height:1.55}
.split,.summary-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.split>section,.summary-grid>section{padding:16px;overflow:auto;border:1px solid #d8e6e7;border-radius:18px;background:#fbfdfd}.split>section{max-height:560px}.summary-grid>section{max-height:250px}.note{margin:0 0 10px;padding:10px;border-left:4px solid #0f8a8f;background:#f4fbfb}.note strong{color:#0f6b57}.note ul,ul{margin:8px 0;padding-left:20px}li{margin:5px 0;line-height:1.45}pre{max-height:470px;padding:12px;overflow:auto;border-radius:12px;background:#102b35;color:#d8f5f0;font-size:11px;white-space:pre-wrap}
footer{position:absolute;right:44px;bottom:18px;color:#8b999e;font-size:11px}
@media(max-width:760px){.slide{padding:26px 24px 34px}.cover h1{font-size:38px}.metrics{grid-template-columns:repeat(2,1fr)}.split,.summary-grid,.figure-grid{grid-template-columns:1fr}.figure-card{grid-template-rows:auto 220px auto}.figure-card img{height:210px}}
@media print{body{background:#fff}.print-button{display:none}.slide{width:1280px;height:720px;margin:0;padding:34px 44px 38px;overflow:hidden;box-shadow:none}.split,.summary-grid,.figure-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
"""


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if str(item).strip()))
