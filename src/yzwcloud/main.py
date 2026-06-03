from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from yzwcloud.config import DATA_DIR, STATIC_DIR
from yzwcloud.executor import NodeExecutionError, run_node
from yzwcloud.models import (
    ComparisonOptionsResponse,
    CreateAnalysisNodeRequest,
    CreateDiffAnalysisRequest,
    CreateTaskRequest,
    HealthResponse,
    PlotStudioAgentEditRequest,
    PlotStudioReportRequest,
    PlotStudioSaveResultRequest,
    PlotStudioSourceResolveRequest,
    PlotStudioSpecRequest,
    SampleMetadataTextRequest,
    RunNodeRequest,
    TaskDetail,
    TaskState,
    UpdateTaskRequest,
    UpdateSampleGroupsRequest,
)
from yzwcloud.plot_studio import (
    create_plot_studio_report,
    create_plot_studio_spec,
    get_plot_studio_manifest,
    resolve_plot_studio_source,
)
from yzwcloud.plot_studio_agent import create_plot_studio_agent_edit
from yzwcloud.plot_studio_examples import example_source_for_plot
from yzwcloud.task_store import (
    TaskNotFoundError,
    create_diff_analysis_branch,
    create_analysis_node,
    create_task,
    delete_node_subtree,
    delete_task,
    get_task_dir,
    list_tasks,
    load_graph,
    load_task,
    read_log,
    read_sample_groups,
    rename_task,
    append_log,
    save_graph,
    save_task_input_text,
    save_task_input,
    save_task_inputs_auto,
    update_sample_groups,
)
from yzwcloud.task_report import build_task_report, render_task_report_pdf

app = FastAPI(title="Yzwcloud Bioinformatics Platform", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

PLOT_STUDIO_UPLOADS_DIR = DATA_DIR / "plot_studio_uploads"
PLOT_STUDIO_UPLOAD_SUFFIXES = {".csv", ".tsv", ".txt", ".xlsx", ".xlsm"}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="yzwcloud")


@app.get("/api/plot-studio/presets")
def api_get_plot_studio_presets() -> dict[str, object]:
    return get_plot_studio_manifest()


@app.post("/api/plot-studio/source/resolve")
def api_resolve_plot_studio_source(payload: PlotStudioSourceResolveRequest) -> dict[str, object]:
    return resolve_plot_studio_source(payload.source.model_dump(by_alias=False))


@app.post("/api/plot-studio/report")
def api_create_plot_studio_report(payload: PlotStudioReportRequest) -> dict[str, object]:
    return create_plot_studio_report(
        payload.source.model_dump(by_alias=False),
        plot_type=payload.plot_type,
        params=payload.params,
    )


@app.post("/api/plot-studio/spec")
def api_create_plot_studio_spec(payload: PlotStudioSpecRequest) -> dict[str, object]:
    return create_plot_studio_spec(
        payload.source.model_dump(by_alias=False),
        plot_type=payload.plot_type,
        params=payload.params,
    )


@app.post("/api/plot-studio/agent-edit")
def api_plot_studio_agent_edit(payload: PlotStudioAgentEditRequest) -> dict[str, object]:
    return create_plot_studio_agent_edit(
        payload.plot_type,
        params=payload.params,
        prompt=payload.prompt,
        parameter_schema=payload.parameter_schema,
        output_template=payload.output_template,
        context=payload.context,
    )


@app.post("/api/tasks/{task_id}/nodes/{node_id}/plot-studio-result", response_model=TaskDetail)
def api_save_plot_studio_result(
    task_id: str,
    node_id: str,
    payload: PlotStudioSaveResultRequest,
) -> TaskDetail:
    try:
        task = load_task(task_id)
        graph = load_graph(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc

    node = next((item for item in graph.nodes if item.id == node_id), None)
    if node is None or node.output is None:
        raise HTTPException(status_code=404, detail="Output node not found")

    source = payload.source.model_dump(by_alias=False)
    if source.get("task_id") and source.get("task_id") != task_id:
        raise HTTPException(status_code=409, detail="Plot Studio source belongs to a different task.")
    if source.get("node_id") and source.get("node_id") != node_id:
        raise HTTPException(status_code=409, detail="Plot Studio source belongs to a different node.")

    spec = create_plot_studio_spec(source, plot_type=payload.plot_type, params=payload.params)
    if not spec.get("data"):
        warning = "; ".join(str(item) for item in spec.get("warnings") or []) or "No renderable Plot Studio chart was produced."
        raise HTTPException(status_code=409, detail=warning)

    output_dir = get_task_dir(task_id) / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_node_id = _safe_output_stem(node_id)
    saved_at = datetime.now().isoformat(timespec="seconds")
    suffix = datetime.now().strftime("%Y%m%d%H%M%S")
    spec_path = output_dir / f"{safe_node_id}_plot_studio_{suffix}.json"
    html_path = output_dir / f"{safe_node_id}_plot_studio_{suffix}.html"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(_plot_studio_result_html(node.name, spec), encoding="utf-8")

    node.output.meta["plot_studio_result"] = {
        "html_file": str(html_path),
        "spec_file": str(spec_path),
        "plot_type": spec.get("plot_type") or payload.plot_type,
        "saved_at": saved_at,
    }
    save_graph(graph)
    append_log(task_id, f"Plot Studio figure saved back to result: {node.name}")
    return TaskDetail(task=task, graph=graph)


def _safe_output_stem(value: str) -> str:
    stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return stem.strip("_") or "plot_studio_result"


def _plot_studio_result_html(title: str, spec: dict[str, object]) -> str:
    safe_title = html.escape(title or "Plot Studio Result")
    spec_json = json.dumps(spec, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title} - Plot Studio</title>
  <style>
    html, body {{
      width: 100%;
      height: 100%;
      margin: 0;
      background: #f8fbfc;
      color: #172635;
      font-family: Inter, "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
    }}
    body {{
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
    }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 18px;
      border-bottom: 1px solid rgba(0, 82, 217, 0.14);
      background: #ffffff;
    }}
    header h1 {{
      margin: 0;
      color: #003cab;
      font-size: 17px;
    }}
    header span {{
      color: #5f7284;
      font-size: 12px;
      font-weight: 800;
    }}
    #plot {{
      width: 100%;
      height: 100%;
      min-height: 520px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>{safe_title}</h1>
    <span>Plot Studio saved figure</span>
  </header>
  <main id="plot"></main>
  <script>
    const spec = {spec_json};
    function plotlyUrls() {{
      const urls = ["/static/vendor/plotly.min.js"];
      if (window.location.hostname && window.location.port === "8011") {{
        urls.push(`${{window.location.protocol}}//${{window.location.hostname}}:8010/static/vendor/plotly.min.js`);
      }}
      return [...new Set(urls)];
    }}
    function loadPlotly(index = 0) {{
      if (window.Plotly) return Promise.resolve(window.Plotly);
      const src = plotlyUrls()[index];
      if (!src) return Promise.reject(new Error("Plotly failed to load"));
      return new Promise((resolve, reject) => {{
        const script = document.createElement("script");
        script.src = src;
        script.async = true;
        script.onload = () => window.Plotly ? resolve(window.Plotly) : reject(new Error("Plotly not found"));
        script.onerror = () => reject(new Error("Plotly failed to load"));
        document.head.appendChild(script);
      }}).catch(() => loadPlotly(index + 1));
    }}
    loadPlotly().then((Plotly) => {{
      const layout = {{ ...(spec.layout || {{}}), autosize: true }};
      const config = {{ ...(spec.config || {{}}), responsive: true, displaylogo: false }};
      Plotly.newPlot("plot", spec.data || [], layout, config);
      window.addEventListener("resize", () => Plotly.Plots.resize("plot"));
    }}).catch((error) => {{
      document.getElementById("plot").textContent = error.message;
    }});
  </script>
</body>
</html>
"""


@app.post("/api/plot-studio/uploads")
async def api_upload_plot_studio_table(request: Request, filename: str = "plot_studio_table.csv") -> dict[str, object]:
    original_name = Path(filename or "plot_studio_table.csv").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in PLOT_STUDIO_UPLOAD_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="Plot Studio uploads support .csv, .tsv, .txt, .xlsx, and .xlsm files.",
        )

    PLOT_STUDIO_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe_stem = "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in Path(original_name).stem
    ).strip("_") or "plot_studio_table"
    target = PLOT_STUDIO_UPLOADS_DIR / f"{safe_stem}_{uuid4().hex[:8]}{suffix}"
    content = await request.body()
    size = len(content)
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded table is empty.")
    with target.open("wb") as output:
        output.write(content)

    source = {
        "sourceKind": "plot_studio_upload",
        "taskId": "",
        "taskName": "",
        "nodeId": target.stem,
        "name": original_name,
        "status": "ready",
        "type": "uploaded_table",
        "summary": f"{original_name} ({size} bytes)",
        "dataPath": str(target),
        "previewUrl": "",
        "htmlUrl": "",
        "meta": {
            "uploaded_file": str(target),
            "filename": original_name,
            "size": size,
        },
    }
    return {"source": source}


@app.get("/api/plot-studio/examples/{plot_id}")
def api_get_plot_studio_example(plot_id: str) -> dict[str, object]:
    try:
        return {"source": example_source_for_plot(plot_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/tasks", response_model=TaskDetail)
def api_create_task(payload: CreateTaskRequest) -> TaskDetail:
    task, graph = create_task(payload.name)
    return TaskDetail(task=task, graph=graph)


@app.get("/api/tasks", response_model=list[TaskState])
def api_list_tasks() -> list[TaskState]:
    return list_tasks()


@app.get("/api/tasks/{task_id}", response_model=TaskDetail)
def api_get_task(task_id: str) -> TaskDetail:
    try:
        return TaskDetail(task=load_task(task_id), graph=load_graph(task_id))
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@app.get("/api/tasks/{task_id}/report.html", include_in_schema=False)
def api_get_task_report_html(task_id: str) -> FileResponse:
    try:
        report = build_task_report(task_id)
        return FileResponse(report["html_file"], media_type="text/html")
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@app.get("/api/tasks/{task_id}/report.json")
def api_get_task_report_json(task_id: str) -> dict[str, object]:
    try:
        return build_task_report(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@app.get("/api/tasks/{task_id}/report.pdf", include_in_schema=False)
def api_get_task_report_pdf(task_id: str) -> FileResponse:
    try:
        report = build_task_report(task_id)
        pdf_path = render_task_report_pdf(report)
        return FileResponse(pdf_path, media_type="application/pdf", filename=f"{task_id}_analysis_report.pdf")
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.delete("/api/tasks/{task_id}", status_code=204)
def api_delete_task(task_id: str) -> Response:
    try:
        delete_task(task_id)
        return Response(status_code=204)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@app.patch("/api/tasks/{task_id}", response_model=TaskDetail)
def api_update_task(task_id: str, payload: UpdateTaskRequest) -> TaskDetail:
    try:
        task = rename_task(task_id, payload.name)
        return TaskDetail(task=task, graph=load_graph(task_id))
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/tasks/{task_id}/inputs/{input_kind}", response_model=TaskDetail)
async def api_upload_task_input(
    task_id: str,
    input_kind: str,
    request: Request,
    filename: str,
) -> TaskDetail:
    try:
        content = await request.body()
        task, graph = save_task_input(
            task_id=task_id,
            input_kind=input_kind,
            filename=filename,
            content=content,
        )
        return TaskDetail(task=task, graph=graph)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/tasks/{task_id}/inputs", response_model=TaskDetail)
async def api_upload_task_inputs(
    task_id: str,
    files: list[UploadFile] = File(...),
) -> TaskDetail:
    try:
        uploaded = [(file.filename or "uploaded_file", await file.read()) for file in files]
        task, graph = save_task_inputs_auto(task_id=task_id, files=uploaded)
        return TaskDetail(task=task, graph=graph)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/tasks/{task_id}/inputs/{input_kind}/text", response_model=TaskDetail)
def api_upload_task_input_text(
    task_id: str,
    input_kind: str,
    payload: SampleMetadataTextRequest,
) -> TaskDetail:
    try:
        task, graph = save_task_input_text(
            task_id=task_id,
            input_kind=input_kind,
            filename=payload.filename,
            content=payload.content,
        )
        return TaskDetail(task=task, graph=graph)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/tasks/{task_id}/comparison-options", response_model=ComparisonOptionsResponse)
def api_get_comparison_options(task_id: str) -> ComparisonOptionsResponse:
    try:
        graph = load_graph(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc

    upload_node = next((node for node in graph.nodes if node.id == "upload_expression"), None)
    if upload_node is None or upload_node.output is None:
        raise HTTPException(status_code=409, detail="请先执行读取表达矩阵节点")

    counts = upload_node.output.meta.get("conditions") or {}
    if not counts:
        raise HTTPException(status_code=409, detail="没有找到可用于差异分析的分组信息")

    conditions = upload_node.output.meta.get("condition_options") or sorted(counts)
    return ComparisonOptionsResponse(
        conditions=[str(item) for item in conditions],
        counts={str(key): int(value) for key, value in counts.items()},
    )


@app.post("/api/tasks/{task_id}/analysis-nodes", response_model=TaskDetail)
def api_create_analysis_node(task_id: str, payload: CreateAnalysisNodeRequest) -> TaskDetail:
    try:
        task, graph = create_analysis_node(
            task_id=task_id,
            source_node_id=payload.source_node_id,
            analysis_type=payload.analysis_type,
        )
        return TaskDetail(task=task, graph=graph)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/tasks/{task_id}/sample-groups")
def api_get_sample_groups(task_id: str) -> dict[str, object]:
    try:
        graph = load_graph(task_id)
        upload_node = next((node for node in graph.nodes if node.id == "upload_expression"), None)
        colors = {}
        if upload_node and upload_node.output:
            colors = upload_node.output.meta.get("condition_colors") or {}
        return {"samples": read_sample_groups(task_id), "condition_colors": colors}
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.put("/api/tasks/{task_id}/sample-groups", response_model=TaskDetail)
def api_update_sample_groups(task_id: str, payload: UpdateSampleGroupsRequest) -> TaskDetail:
    try:
        task, graph = update_sample_groups(task_id, payload.assignments, payload.condition_colors)
        return TaskDetail(task=task, graph=graph)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/tasks/{task_id}/nodes/{node_id}", response_model=TaskDetail)
def api_delete_node(task_id: str, node_id: str) -> TaskDetail:
    try:
        task, graph, _ = delete_node_subtree(task_id, node_id)
        return TaskDetail(task=task, graph=graph)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/tasks/{task_id}/diff-analyses", response_model=TaskDetail)
def api_create_diff_analysis(
    task_id: str,
    payload: CreateDiffAnalysisRequest,
    background_tasks: BackgroundTasks,
) -> TaskDetail:
    params = {
        "method": payload.method,
        "p_value": payload.p_value,
        "log2fc": payload.log2fc,
    }
    try:
        task, graph, branch_id = create_diff_analysis_branch(
            task_id=task_id,
            case_condition=payload.case_condition,
            control_condition=payload.control_condition,
            params=params,
        )
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    background_tasks.add_task(run_node, task_id, branch_id, {})
    return TaskDetail(task=task, graph=graph)


@app.post("/api/tasks/{task_id}/nodes/{node_id}/run", response_model=TaskDetail)
def api_run_node(
    task_id: str,
    node_id: str,
    payload: RunNodeRequest,
    background_tasks: BackgroundTasks,
) -> TaskDetail:
    try:
        task = load_task(task_id)
        graph = load_graph(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc

    try:
        _validate_runnable(graph, node_id)
    except NodeExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    background_tasks.add_task(run_node, task_id, node_id, payload.params)
    return TaskDetail(task=task, graph=graph)


@app.get("/api/tasks/{task_id}/logs", response_class=PlainTextResponse)
def api_get_logs(task_id: str) -> str:
    try:
        load_task(task_id)
        return read_log(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@app.get("/api/tasks/{task_id}/outputs/{filename}", include_in_schema=False)
def api_get_output_file(task_id: str, filename: str) -> FileResponse:
    try:
        load_task(task_id)
        output_dir = (get_task_dir(task_id) / "outputs").resolve()
        target = (output_dir / filename).resolve()
        if output_dir not in target.parents or not target.exists():
            raise TaskNotFoundError(task_id)
        return FileResponse(target)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Output file not found") from exc


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str) -> FileResponse:
    if full_path.startswith(("api/", "static/")):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(STATIC_DIR / "index.html")


def _validate_runnable(graph, node_id: str) -> None:
    nodes = {node.id: node for node in graph.nodes}
    if node_id not in nodes:
        raise NodeExecutionError(f"Unknown node: {node_id}")
    node = nodes[node_id]
    if node.status == "running":
        raise NodeExecutionError(f"Node is already running: {node_id}")
    if node.depends_on and not all(nodes[dep].status == "completed" for dep in node.depends_on):
        raise NodeExecutionError("上游节点尚未完成")
