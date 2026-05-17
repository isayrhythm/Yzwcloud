from __future__ import annotations

import json
import shutil
import csv
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from yzwcloud.config import TASKS_DIR
from yzwcloud.models import Graph, GraphNode, NodeStatus, TaskState, TaskStatus
from yzwcloud.node_registry import NODE_DEFINITIONS, build_initial_edges


class TaskNotFoundError(Exception):
    pass


def ensure_storage() -> None:
    TASKS_DIR.mkdir(parents=True, exist_ok=True)


def create_task(name: str) -> tuple[TaskState, Graph]:
    ensure_storage()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_id = f"task_{timestamp}_{uuid4().hex[:8]}"
    task_dir = get_task_dir(task_id)
    for child in ("inputs", "outputs", "logs"):
        (task_dir / child).mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    task = TaskState(
        task_id=task_id,
        name=name,
        status=TaskStatus.CREATED,
        created_at=now,
        updated_at=now,
    )
    nodes = []
    for definition in NODE_DEFINITIONS.values():
        status = NodeStatus.READY if not definition.depends_on else NodeStatus.PENDING
        nodes.append(
            GraphNode(
                id=definition.id,
                name=definition.name,
                description=definition.description,
                status=status,
                input_types=definition.input_types,
                output_type=definition.output_type,
                default_params=definition.default_params,
                params=definition.default_params.copy(),
                depends_on=definition.depends_on,
            )
        )

    graph = Graph(task_id=task_id, nodes=nodes, edges=[], updated_at=now)
    save_task(task)
    save_graph(graph)
    append_log(task_id, f"Task created: {name}")
    return task, graph


def list_tasks() -> list[TaskState]:
    ensure_storage()
    tasks = []
    for status_file in TASKS_DIR.glob("*/status.json"):
        try:
            tasks.append(TaskState.model_validate_json(status_file.read_text(encoding="utf-8")))
        except Exception:
            continue
    return sorted(tasks, key=lambda item: item.created_at, reverse=True)


def load_task(task_id: str) -> TaskState:
    path = get_task_dir(task_id) / "status.json"
    if not path.exists():
        raise TaskNotFoundError(task_id)
    return TaskState.model_validate_json(path.read_text(encoding="utf-8"))


def load_graph(task_id: str) -> Graph:
    path = get_task_dir(task_id) / "graph.json"
    if not path.exists():
        raise TaskNotFoundError(task_id)
    return Graph.model_validate_json(path.read_text(encoding="utf-8"))


def read_sample_groups(task_id: str) -> list[dict[str, str]]:
    graph = load_graph(task_id)
    upload_node = next((node for node in graph.nodes if node.id == "upload_expression"), None)
    if upload_node is None or upload_node.output is None:
        raise ValueError("Data upload node has no output")
    metadata_file = upload_node.output.meta.get("sample_metadata_file")
    if not metadata_file:
        raise ValueError("No sample metadata is available")
    path = Path(str(metadata_file))
    if not path.exists():
        raise ValueError("Sample metadata file not found")
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def update_sample_groups(
    task_id: str,
    assignments: dict[str, str],
) -> tuple[TaskState, Graph]:
    task = load_task(task_id)
    graph = load_graph(task_id)
    upload_node = next((node for node in graph.nodes if node.id == "upload_expression"), None)
    if upload_node is None or upload_node.output is None:
        raise ValueError("Data upload node has no output")
    metadata_file = upload_node.output.meta.get("sample_metadata_file")
    if not metadata_file:
        raise ValueError("No sample metadata is available")
    path = Path(str(metadata_file))
    if not path.exists():
        raise ValueError("Sample metadata file not found")

    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    required = {"sample", "group", "condition"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("Sample metadata must contain sample, group, condition")

    normalized = {sample: condition.strip() for sample, condition in assignments.items() if condition.strip()}
    for row in rows:
        sample = row["sample"]
        if sample in normalized:
            row["condition"] = normalized[sample]
            row["group"] = normalized[sample]

    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["sample", "group", "condition"])
        writer.writeheader()
        writer.writerows(rows)

    conditions = _count_values(row["condition"] for row in rows)
    groups = _count_values(row["group"] for row in rows)
    capabilities = ["pca"]
    if len(conditions) >= 2 and all(count >= 2 for count in conditions.values()):
        capabilities.append("diff_analysis")
    upload_node.output.meta["conditions"] = conditions
    upload_node.output.meta["condition_options"] = sorted(conditions)
    upload_node.output.meta["sample_groups"] = groups
    upload_node.output.meta["capabilities"] = capabilities
    upload_node.output.meta["next_analyses"] = _next_analyses_for_capabilities(capabilities)
    _reset_upload_node_for_new_input(graph, keep_upload_output=True)
    upload_node.status = NodeStatus.COMPLETED
    save_graph(graph)
    append_log(task_id, "Sample groups corrected manually")
    return task, graph


def save_task_input(
    task_id: str,
    input_kind: str,
    filename: str,
    content: bytes,
) -> tuple[TaskState, Graph]:
    if input_kind not in {"expression_matrix", "sample_metadata"}:
        raise ValueError("Unsupported input kind")
    if not content:
        raise ValueError("Uploaded file is empty")

    task = load_task(task_id)
    graph = load_graph(task_id)
    inputs_dir = get_task_dir(task_id) / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    normalized_name = _safe_filename(filename)
    lowered_name = normalized_name.lower()
    suffix = Path(lowered_name).suffix
    if input_kind == "expression_matrix" and not _is_supported_expression_upload(lowered_name):
        raise ValueError("Expression input must be .csv, .xlsx, .xlsm, .zip, .tar, .tar.gz, .tgz or .gz")
    if input_kind == "sample_metadata" and suffix != ".csv":
        raise ValueError("Sample metadata must be .csv")

    target = inputs_dir / f"{input_kind}__{normalized_name}"
    target.write_bytes(content)
    manifest_path = inputs_dir / "manifest.json"
    manifest = _read_manifest(manifest_path)
    manifest[input_kind] = {
        "filename": _safe_filename(filename),
        "path": str(target.resolve()),
        "size": len(content),
        "uploaded_at": datetime.now().isoformat(),
    }
    _atomic_write_json(manifest_path, manifest)

    upload_node = next((node for node in graph.nodes if node.id == "upload_expression"), None)
    if upload_node is None:
        raise ValueError("Upload node not found")
    if input_kind == "expression_matrix":
        upload_node.params["source_path"] = str(target.resolve())
        upload_node.default_params["source_path"] = str(target.resolve())
        upload_node.params["sample_metadata_path"] = "__missing_sample_metadata__.csv"
        upload_node.default_params["sample_metadata_path"] = "__missing_sample_metadata__.csv"
    else:
        upload_node.params["sample_metadata_path"] = str(target.resolve())
        upload_node.default_params["sample_metadata_path"] = str(target.resolve())
    upload_node.params["uploaded_inputs"] = manifest
    upload_node.default_params["uploaded_inputs"] = manifest
    _reset_upload_node_for_new_input(graph)
    save_graph(graph)
    append_log(task_id, f"Input uploaded: {input_kind} -> {filename}")
    return task, graph


def create_diff_analysis_branch(
    task_id: str,
    case_condition: str,
    control_condition: str,
    params: dict,
) -> tuple[TaskState, Graph, str]:
    task = load_task(task_id)
    graph = load_graph(task_id)
    nodes = {node.id: node for node in graph.nodes}
    source = nodes.get("upload_expression")
    if source is None or source.status != NodeStatus.COMPLETED or source.output is None:
        raise ValueError("请先完成表达矩阵读取节点")
    if case_condition == control_condition:
        raise ValueError("case 和 control 不能相同")

    conditions = set(source.output.meta.get("condition_options") or [])
    if conditions and (case_condition not in conditions or control_condition not in conditions):
        raise ValueError("选择的分组不在样本 metadata 中")

    branch_key = _slug(f"{case_condition}_vs_{control_condition}")
    branch_id = _unique_node_id(graph, f"diff_analysis__{branch_key}")
    branch_name = f"差异分析：{case_condition} vs {control_condition}"
    branch_params = {
        "case_condition": case_condition,
        "control_condition": control_condition,
        **params,
    }

    selector = nodes.get("diff_analysis")
    if selector is None:
        raise ValueError("差异分析选择器不存在")
    if selector.status == NodeStatus.PENDING:
        selector.status = NodeStatus.READY
    if not _edge_exists(graph, "upload_expression", "diff_analysis"):
        graph.edges.append({"source": "upload_expression", "target": "diff_analysis"})

    graph.nodes.append(
        GraphNode(
            id=branch_id,
            name=branch_name,
            description="基于选定 case/control 组合生成的独立差异分析节点。",
            status=NodeStatus.READY,
            input_types=["expression_matrix"],
            output_type="diff_result",
            default_params=branch_params,
            params=branch_params.copy(),
            depends_on=["upload_expression"],
        )
    )
    graph.edges.append({"source": "diff_analysis", "target": branch_id})
    save_graph(graph)
    append_log(task_id, f"Diff branch created: {branch_name}")
    return task, graph, branch_id


def create_analysis_node(task_id: str, source_node_id: str, analysis_type: str) -> tuple[TaskState, Graph]:
    task = load_task(task_id)
    graph = load_graph(task_id)
    nodes = {node.id: node for node in graph.nodes}
    source = nodes.get(source_node_id)
    if source is None:
        raise ValueError("源节点不存在")
    if source.status != NodeStatus.COMPLETED or source.output is None:
        raise ValueError("源节点尚未完成，不能创建后续分析")

    if source_node_id == "upload_expression" and analysis_type in {"diff_analysis", "pca"}:
        if analysis_type == "pca":
            _add_expression_downstream_node(graph, analysis_type)
            save_graph(graph)
            append_log(task_id, "Analysis node enabled: pca")
            return task, graph
        selector = nodes.get("diff_analysis")
        if selector is None:
            raise ValueError("差异分析选择器不存在")
        selector.status = NodeStatus.READY
        if not _edge_exists(graph, "upload_expression", "diff_analysis"):
            graph.edges.append({"source": "upload_expression", "target": "diff_analysis"})
        save_graph(graph)
        append_log(task_id, "Analysis node enabled: diff_analysis")
        return task, graph

    if source_node_id.startswith("diff_analysis__") and analysis_type in {
        "heatmap",
        "volcano",
        "enrichment",
    }:
        _add_diff_downstream_node(graph, source_node_id, analysis_type)
        save_graph(graph)
        append_log(task_id, f"Analysis node created: {analysis_type} from {source_node_id}")
        return task, graph

    raise ValueError("该节点不支持创建所选后续分析")


def delete_node_subtree(task_id: str, node_id: str) -> tuple[TaskState, Graph, list[str]]:
    task = load_task(task_id)
    graph = load_graph(task_id)
    nodes = {node.id: node for node in graph.nodes}
    if node_id not in nodes:
        raise ValueError("节点不存在")

    protected = {"upload_expression"}
    descendants = _collect_descendants(graph, node_id)
    delete_ids = {node_id, *descendants}
    if node_id in protected:
        # Keep the root input node, but remove every downstream branch and reset it.
        delete_ids.remove(node_id)
        root = nodes[node_id]
        root.status = NodeStatus.READY
        root.output = None
        root.error = None
        root.started_at = None
        root.completed_at = None

    graph.nodes = [node for node in graph.nodes if node.id not in delete_ids]
    graph.edges = [
        edge
        for edge in graph.edges
        if edge["source"] not in delete_ids and edge["target"] not in delete_ids
    ]

    # If only the hidden selector remains downstream, return it to pending after its branches are gone.
    selector = next((node for node in graph.nodes if node.id == "diff_analysis"), None)
    if selector and not any(edge["source"] == "diff_analysis" for edge in graph.edges):
        selector.status = NodeStatus.PENDING
        selector.output = None
        selector.error = None
        selector.started_at = None
        selector.completed_at = None
        graph.edges = [edge for edge in graph.edges if edge["target"] != "diff_analysis"]

    save_graph(graph)
    append_log(task_id, f"Node subtree deleted: {node_id} -> {sorted(delete_ids)}")
    return task, graph, sorted(delete_ids)


def _reset_upload_node_for_new_input(graph: Graph, keep_upload_output: bool = False) -> None:
    nodes = {node.id: node for node in graph.nodes}
    upload_node = nodes["upload_expression"]
    descendants = _collect_descendants(graph, "upload_expression")
    delete_ids = {node_id for node_id in descendants if node_id != "diff_analysis"}
    graph.nodes = [node for node in graph.nodes if node.id not in delete_ids]
    graph.edges = [
        edge
        for edge in graph.edges
        if edge["source"] not in delete_ids
        and edge["target"] not in delete_ids
        and edge != {"source": "upload_expression", "target": "diff_analysis"}
    ]
    upload_node.status = NodeStatus.READY
    if not keep_upload_output:
        upload_node.output = None
    upload_node.error = None
    upload_node.started_at = None
    upload_node.completed_at = None
    selector = nodes.get("diff_analysis")
    if selector:
        selector.status = NodeStatus.PENDING
        selector.output = None
        selector.error = None
        selector.started_at = None
        selector.completed_at = None


def ensure_diff_downstream_nodes(graph: Graph, diff_node_id: str) -> None:
    return


def _add_expression_downstream_node(graph: Graph, analysis_type: str) -> None:
    specs = {
        "pca": (
            "pca__expression",
            "PCA 样本分布",
            "基于表达矩阵计算样本 PCA，用于查看分组和离群样本。",
            "pca_plot",
            {"top_variable_genes": 2000},
        ),
    }
    if analysis_type not in specs:
        raise ValueError("Unsupported expression downstream analysis type")

    base_id, name, description, output_type, params = specs[analysis_type]
    node_id = _unique_node_id(graph, base_id)
    graph.nodes.append(
        GraphNode(
            id=node_id,
            name=name,
            description=description,
            status=NodeStatus.READY,
            input_types=["expression_matrix"],
            output_type=output_type,
            default_params=params,
            params=params.copy(),
            depends_on=["upload_expression"],
        )
    )
    graph.edges.append({"source": "upload_expression", "target": node_id})


def _add_diff_downstream_node(graph: Graph, diff_node_id: str, analysis_type: str) -> None:
    nodes = {node.id: node for node in graph.nodes}
    diff_node = nodes.get(diff_node_id)
    if diff_node is None or diff_node.output is None:
        return

    suffix = diff_node_id.removeprefix("diff_analysis__")
    comparison = diff_node.output.meta.get("comparison_label", suffix.replace("_", " "))
    specs = {
        "heatmap": (
            f"heatmap__{suffix}",
            f"热图：{comparison}",
            "基于该差异分析结果生成热图。",
            "heatmap_plot",
            {"top_genes": 50, "cluster": True},
        ),
        "volcano": (
            f"volcano__{suffix}",
            f"火山图：{comparison}",
            "基于该差异分析结果生成火山图。",
            "volcano_plot",
            {"p_value": 0.05, "log2fc": 1.0},
        ),
        "enrichment": (
            f"enrichment__{suffix}",
            f"富集分析：{comparison}",
            "基于该差异分析结果生成富集分析。",
            "enrichment_result",
            {"database": "GO", "p_adjust": 0.05},
        ),
    }
    if analysis_type not in specs:
        raise ValueError("不支持的后续分析类型")

    base_id, name, description, output_type, params = specs[analysis_type]
    node_id = _unique_node_id(graph, base_id)
    graph.nodes.append(
        GraphNode(
            id=node_id,
            name=name,
            description=description,
            status=NodeStatus.READY,
            input_types=["diff_result"],
            output_type=output_type,
            default_params=params,
            params=params.copy(),
            depends_on=[diff_node_id],
        )
    )
    graph.edges.append({"source": diff_node_id, "target": node_id})


def save_task(task: TaskState) -> None:
    path = get_task_dir(task.task_id) / "status.json"
    task.updated_at = datetime.now()
    _atomic_write_json(path, task.model_dump(mode="json"))


def save_graph(graph: Graph) -> None:
    path = get_task_dir(graph.task_id) / "graph.json"
    graph.updated_at = datetime.now()
    _atomic_write_json(path, graph.model_dump(mode="json"))


def append_log(task_id: str, message: str) -> None:
    log_dir = get_task_dir(task_id) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}\n"
    with (log_dir / "task.log").open("a", encoding="utf-8") as file:
        file.write(line)


def read_log(task_id: str) -> str:
    path = get_task_dir(task_id) / "logs" / "task.log"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def delete_task(task_id: str) -> None:
    task_dir = get_task_dir(task_id)
    if not task_dir.exists():
        raise TaskNotFoundError(task_id)

    root = TASKS_DIR.resolve()
    target = task_dir.resolve()
    if root not in target.parents:
        raise TaskNotFoundError(task_id)

    shutil.rmtree(target)


def get_task_dir(task_id: str) -> Path:
    if "/" in task_id or "\\" in task_id or ".." in task_id:
        raise TaskNotFoundError(task_id)
    return TASKS_DIR / task_id


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _read_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _safe_filename(filename: str) -> str:
    raw_name = Path(filename).name or "uploaded_file"
    return "".join(char if char.isalnum() or char in {".", "-", "_"} else "_" for char in raw_name)


def _is_supported_expression_upload(filename: str) -> bool:
    return filename.endswith((".csv", ".xlsx", ".xlsm", ".zip", ".tar", ".tar.gz", ".tgz", ".gz"))


def _count_values(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _next_analyses_for_capabilities(capabilities: list[str]) -> list[dict[str, str]]:
    specs = {
        "pca": {
            "type": "pca",
            "label": "PCA",
            "description": "基于表达矩阵查看样本整体分布。",
        },
        "diff_analysis": {
            "type": "diff_analysis",
            "label": "差异分析",
            "description": "选择两个样本分组进行差异表达分析。",
        },
    }
    return [specs[item] for item in capabilities if item in specs]


def _unique_node_id(graph: Graph, base_id: str) -> str:
    existing = {node.id for node in graph.nodes}
    if base_id not in existing:
        return base_id
    counter = 2
    while f"{base_id}_{counter}" in existing:
        counter += 1
    return f"{base_id}_{counter}"


def _edge_exists(graph: Graph, source: str, target: str) -> bool:
    return any(edge["source"] == source and edge["target"] == target for edge in graph.edges)


def _collect_descendants(graph: Graph, node_id: str) -> set[str]:
    children_by_source: dict[str, list[str]] = {}
    for edge in graph.edges:
        children_by_source.setdefault(edge["source"], []).append(edge["target"])

    descendants: set[str] = set()
    stack = list(children_by_source.get(node_id, []))
    while stack:
        current = stack.pop()
        if current in descendants:
            continue
        descendants.add(current)
        stack.extend(children_by_source.get(current, []))
    return descendants


def _slug(value: str) -> str:
    cleaned = []
    for char in value.lower():
        if char.isalnum():
            cleaned.append(char)
        else:
            cleaned.append("_")
    return "_".join("".join(cleaned).split("_"))
