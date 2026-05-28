from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from yzwcloud.config import STATIC_DIR
from yzwcloud.executor import NodeExecutionError, run_node
from yzwcloud.models import (
    ComparisonOptionsResponse,
    CreateAnalysisNodeRequest,
    CreateDiffAnalysisRequest,
    CreateTaskRequest,
    HealthResponse,
    PlotStudioReportRequest,
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
)
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
    save_task_input_text,
    save_task_input,
    update_sample_groups,
)

app = FastAPI(title="Yzwcloud Bioinformatics Platform", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="yzwcloud")


@app.get("/api/plot-studio/presets")
def api_get_plot_studio_presets() -> dict[str, object]:
    return get_plot_studio_manifest()


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
