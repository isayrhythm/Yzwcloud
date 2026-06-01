from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yzwcloud.main import app  # noqa: E402
from yzwcloud.models import DataObject, NodeStatus  # noqa: E402
from yzwcloud.task_report import build_task_report, render_task_report_pdf  # noqa: E402
from yzwcloud.task_store import create_task, save_graph  # noqa: E402


def _report_task(tmp_path: Path, monkeypatch) -> str:
    import yzwcloud.task_store as task_store

    monkeypatch.setattr(task_store, "TASKS_DIR", tmp_path / "tasks")
    task, graph = create_task("report-demo")
    output_dir = task_store.get_task_dir(task.task_id) / "outputs"
    preview = output_dir / "upload_preview.svg"
    preview.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120"><rect width="220" height="120" fill="#e8f7f4"/></svg>',
        encoding="utf-8",
    )
    upload = next(node for node in graph.nodes if node.id == "upload_expression")
    upload.status = NodeStatus.COMPLETED
    upload.output = DataObject(
        type="expression_matrix",
        data=str(output_dir / "upload_output.json"),
        meta={
            "sample_count": 6,
            "gene_count": 1200,
            "preview_file": str(preview),
            "agent_report": {
                "summary": "识别到 6 个样本和 1200 个可分析基因。",
                "findings": ["表达矩阵已完成标准化。"],
                "methods": ["数据载入与结构检查。"],
                "warnings": ["正式解读前仍需检查实验设计。"],
                "next_steps": ["继续执行 QC。"],
            },
        },
    )
    save_graph(graph)
    return task.task_id


def test_task_report_builds_slide_html_with_workflow_and_real_preview(tmp_path: Path, monkeypatch) -> None:
    task_id = _report_task(tmp_path, monkeypatch)

    report = build_task_report(task_id)
    html_text = Path(report["html_file"]).read_text(encoding="utf-8")

    assert report["summary"]["completed_nodes"] == 1
    assert report["summary"]["figure_count"] == 1
    assert Path(report["workflow"]["svg_file"]).exists()
    assert "分析任务总览" in html_text
    assert "当前分析流程" in html_text
    assert "实际结果图" in html_text
    assert "data:image/svg+xml;base64," in html_text
    assert "打印 / 保存为 PDF" in html_text


def test_task_report_api_serves_html_and_json(tmp_path: Path, monkeypatch) -> None:
    task_id = _report_task(tmp_path, monkeypatch)
    client = TestClient(app)

    html_response = client.get(f"/api/tasks/{task_id}/report.html")
    json_response = client.get(f"/api/tasks/{task_id}/report.json")

    assert html_response.status_code == 200
    assert "text/html" in html_response.headers["content-type"]
    assert json_response.status_code == 200
    assert json_response.json()["task"]["task_id"] == task_id


def test_task_report_pdf_uses_headless_browser(tmp_path: Path, monkeypatch) -> None:
    html_path = tmp_path / "report.html"
    pdf_path = tmp_path / "report.pdf"
    html_path.write_text("<html><body>report</body></html>", encoding="utf-8")

    import yzwcloud.task_report as task_report

    monkeypatch.setattr(task_report, "_find_pdf_browser", lambda: Path("C:/fake/msedge.exe"))

    def fake_run(command, **kwargs):
        target = next(item.split("=", 1)[1] for item in command if item.startswith("--print-to-pdf="))
        Path(target).write_bytes(b"%PDF-1.4\nreport")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(task_report.subprocess, "run", fake_run)

    rendered = render_task_report_pdf({"html_file": str(html_path), "pdf_file": str(pdf_path)})

    assert rendered == pdf_path.resolve()
    assert rendered.read_bytes().startswith(b"%PDF")
