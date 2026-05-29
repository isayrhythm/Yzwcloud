from __future__ import annotations

import json
import shutil
import csv
from io import StringIO
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from yzwcloud.config import TASKS_DIR
from yzwcloud.color_palette import condition_color_map
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
    graph = Graph.model_validate_json(path.read_text(encoding="utf-8"))
    if _migrate_legacy_analysis_nodes(graph):
        save_graph(graph)
    return graph


def _migrate_legacy_analysis_nodes(graph: Graph) -> bool:
    changed = False
    for node in graph.nodes:
        if not node.id.startswith("wgcna__"):
            continue
        node.name = "WGCNA"
        node.description = "Detect co-expression modules from top-variable genes and summarize module-condition correlations."
        node.output_type = "wgcna_result"
        defaults = {
            "gene_selection_mode": "fixed",
            "max_genes": 2000,
            "top_gene_percent": 25,
            "min_module_size": 20,
            "soft_power": 0,
            "merge_cut_height": 0.25,
            "network_type": "signed",
        }
        if node.default_params != defaults:
            node.default_params = defaults.copy()
            changed = True
        if node.output and node.output.type == "planned_analysis":
            node.output = None
            node.status = NodeStatus.READY
            node.error = None
            node.params = defaults.copy()
            node.started_at = None
            node.completed_at = None
            changed = True
        elif node.params.keys() <= {"min_samples", "network"}:
            node.params = defaults.copy()
            changed = True
    return changed


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
    condition_colors: dict[str, str] | None = None,
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
    is_metabolomics = upload_node.output.meta.get("data_type") == "metabolomics_matrix"
    capabilities = ["qc", "sample_correlation", "expression_heatmap", "gene_expression", "pca"]
    if is_metabolomics:
        capabilities.append("metabolomics_statistics")
    if sum(conditions.values()) > 20 and not is_metabolomics:
        capabilities.append("wgcna")
    if len(conditions) >= 2 and all(count >= 2 for count in conditions.values()) and not is_metabolomics:
        capabilities.append("diff_analysis")
    if len(conditions) >= 3 and not is_metabolomics:
        capabilities.append("multigroup_differential")
    upload_node.output.meta["conditions"] = conditions
    upload_node.output.meta["condition_options"] = sorted(conditions)
    uploaded_colors = {key: value for key, value in (condition_colors or {}).items() if value}
    upload_node.output.meta["condition_colors"] = condition_color_map(
        conditions,
        uploaded_colors or upload_node.output.meta.get("condition_colors") or {},
    )
    upload_node.output.meta["sample_groups"] = groups
    upload_node.output.meta["capabilities"] = capabilities
    upload_node.output.meta["next_analyses"] = _next_analyses_for_capabilities(capabilities)
    _reset_upload_node_for_new_input(graph, keep_upload_output=True)
    upload_node.status = NodeStatus.COMPLETED
    save_graph(graph)
    append_log(task_id, "Sample groups and display colors updated manually")
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
        raise ValueError("Expression input must be .csv, .tsv, .txt, .xlsx, .xlsm, .zip, .tar, .tar.gz, .tgz or .gz")
    if input_kind == "sample_metadata" and suffix not in {".csv", ".tsv", ".txt"}:
        raise ValueError("Sample metadata must be .csv, .tsv, or .txt")

    existing_path: Path | None = None
    if input_kind == "sample_metadata":
        metadata_rows = _parse_metadata_bytes(content)
        existing_manifest = _read_manifest(inputs_dir / "manifest.json").get("sample_metadata")
        existing_path = (
            Path(str(existing_manifest.get("path"))) if isinstance(existing_manifest, dict) and existing_manifest.get("path") else None
        )
        if existing_path and existing_path.exists():
            existing_rows = _read_metadata_rows(existing_path)
        else:
            existing_path = None
            existing_rows = []
        merged_rows = _merge_metadata_rows(existing_rows=existing_rows, incoming_rows=metadata_rows)
        canonical = _serialize_metadata_rows(merged_rows)
        content = canonical.encode("utf-8-sig")

    target = existing_path or (inputs_dir / f"{input_kind}__{normalized_name}")
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
    existing_manifest = manifest.get("sample_metadata")
    existing_sample_metadata_path = None
    if isinstance(existing_manifest, dict):
        existing_path = str(existing_manifest.get("path") or "")
        if existing_path:
            existing_sample_metadata_path = existing_path

    if input_kind == "expression_matrix":
        upload_node.params["source_path"] = str(target.resolve())
        upload_node.default_params["source_path"] = str(target.resolve())
        sample_metadata_path = existing_sample_metadata_path or "__missing_sample_metadata__.csv"
        upload_node.params["sample_metadata_path"] = sample_metadata_path
        upload_node.default_params["sample_metadata_path"] = sample_metadata_path
    else:
        upload_node.params["sample_metadata_path"] = str(target.resolve())
        upload_node.default_params["sample_metadata_path"] = str(target.resolve())
    upload_node.params["uploaded_inputs"] = manifest
    upload_node.default_params["uploaded_inputs"] = manifest
    _reset_upload_node_for_new_input(graph)
    save_graph(graph)
    append_log(task_id, f"Input uploaded: {input_kind} -> {filename}")
    return task, graph


def save_task_inputs_auto(
    task_id: str,
    files: list[tuple[str, bytes]],
) -> tuple[TaskState, Graph]:
    if not files:
        raise ValueError("No files were uploaded")

    metadata_files: list[tuple[str, bytes]] = []
    data_files: list[tuple[str, bytes]] = []
    extras: list[dict[str, str | int]] = []
    for filename, content in files:
        if not content:
            raise ValueError(f"Uploaded file is empty: {filename}")
        safe_name = _safe_filename(filename)
        lowered = safe_name.lower()
        if _looks_like_metadata_upload(safe_name, content):
            metadata_files.append((safe_name, content))
            continue
        if _is_supported_expression_upload(lowered):
            data_files.append((safe_name, content))
            continue
        extras.append({"filename": safe_name, "size": len(content), "reason": "unsupported"})

    if not data_files:
        raise ValueError("No supported data table was found in the upload batch")

    ordered_data = sorted(data_files, key=lambda item: _data_upload_priority(item[0]))
    selected_data = ordered_data[0]
    for filename, content in metadata_files:
        save_task_input(task_id, "sample_metadata", filename, content)
    task, graph = save_task_input(task_id, "expression_matrix", selected_data[0], selected_data[1])

    inputs_dir = get_task_dir(task_id) / "inputs"
    extra_data_files = []
    for filename, content in data_files:
        if filename == selected_data[0]:
            continue
        target = _unique_input_path(inputs_dir, f"batch_extra__{_safe_filename(filename)}")
        target.write_bytes(content)
        extra_data_files.append({"filename": filename, "path": str(target.resolve()), "size": len(content)})

    manifest_path = inputs_dir / "manifest.json"
    manifest = _read_manifest(manifest_path)
    manifest["upload_batch"] = {
        "files": [
            {"filename": _safe_filename(filename), "size": len(content)}
            for filename, content in files
        ],
        "metadata_files": [filename for filename, _ in metadata_files],
        "data_files": [filename for filename, _ in data_files],
        "selected_data_file": selected_data[0],
        "extra_data_files": extra_data_files,
        "ignored_files": extras,
        "uploaded_at": datetime.now().isoformat(),
    }
    _atomic_write_json(manifest_path, manifest)

    graph = load_graph(task_id)
    upload_node = next((node for node in graph.nodes if node.id == "upload_expression"), None)
    if upload_node is not None:
        upload_node.params["uploaded_inputs"] = manifest
        upload_node.default_params["uploaded_inputs"] = manifest
        save_graph(graph)
    append_log(
        task_id,
        f"Batch input uploaded: {len(files)} file(s), selected data -> {selected_data[0]}",
    )
    return task, graph


def save_task_input_text(
    task_id: str,
    input_kind: str,
    content: str,
    filename: str = "sample_metadata.csv",
) -> tuple[TaskState, Graph]:
    if input_kind != "sample_metadata":
        raise ValueError("Only sample_metadata text upload is supported")
    text = content.strip()
    if not text:
        raise ValueError("Metadata content is empty")

    metadata_rows = _parse_metadata_text(text)
    canonical = _serialize_metadata_rows(metadata_rows)
    safe_name = filename.strip() or "sample_metadata.csv"
    if not safe_name.lower().endswith(".csv"):
        safe_name = f"{safe_name}.csv"
    return save_task_input(task_id, input_kind, safe_name, canonical.encode("utf-8-sig"))


def _parse_metadata_bytes(content: bytes) -> list[dict[str, str]]:
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Sample metadata file must be UTF-8 encoded text") from exc
    rows = _parse_metadata_text(decoded)
    return rows


def _read_metadata_rows(path: Path) -> list[dict[str, str]]:
    return _parse_metadata_text(path.read_text(encoding="utf-8-sig"))


def _merge_metadata_rows(
    *,
    existing_rows: list[dict[str, str]],
    incoming_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for row in existing_rows:
        sample = row["sample"]
        if sample not in merged:
            order.append(sample)
        merged[sample] = dict(row)
    for row in incoming_rows:
        sample = row["sample"]
        if sample in merged:
            merged[sample] = {**merged[sample], **row}
            continue
        order.append(sample)
        merged[sample] = dict(row)
    return [merged[sample] for sample in order]


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
    if not any(edge["target"] == "diff_analysis" for edge in graph.edges):
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

    if source_node_id == "upload_expression":
        if analysis_type != "qc":
            raise ValueError("Upload output must pass multi-sample QC before downstream analysis")
        _add_expression_downstream_node(graph, analysis_type, source_node_id=source_node_id)
        save_graph(graph)
        append_log(task_id, "Analysis node enabled: qc")
        return task, graph

    if source_node_id.startswith("qc__") and analysis_type in {
        "diff_analysis",
        "pca",
        "sample_correlation",
        "expression_heatmap",
        "gene_expression",
        "multigroup_differential",
        "wgcna",
        "metabolomics_statistics",
    }:
        if analysis_type in {
            "pca",
            "sample_correlation",
            "expression_heatmap",
            "gene_expression",
            "multigroup_differential",
            "wgcna",
            "metabolomics_statistics",
        }:
            if analysis_type == "wgcna":
                sample_count = int(
                    source.output.meta.get("passed_sample_count")
                    or source.output.meta.get("sample_count")
                    or 0
                )
                if sample_count <= 20:
                    raise ValueError("WGCNA requires more than 20 samples after QC")
            _add_expression_downstream_node(graph, analysis_type, source_node_id=source_node_id)
            save_graph(graph)
            append_log(task_id, f"Analysis node enabled: {analysis_type}")
            return task, graph
        selector = nodes.get("diff_analysis")
        if selector is None:
            raise ValueError("Differential analysis selector is not available")
        selector.status = NodeStatus.READY
        if not _edge_exists(graph, source_node_id, "diff_analysis"):
            graph.edges.append({"source": source_node_id, "target": "diff_analysis"})
        save_graph(graph)
        append_log(task_id, "Analysis node enabled: diff_analysis")
        return task, graph

    if source_node_id == "upload_expression" and analysis_type in {
        "diff_analysis",
        "pca",
        "qc",
        "sample_correlation",
        "expression_heatmap",
        "gene_expression",
    }:
        if analysis_type == "pca":
            _add_expression_downstream_node(graph, analysis_type)
            save_graph(graph)
            append_log(task_id, "Analysis node enabled: pca")
            return task, graph
        if analysis_type in {"qc", "sample_correlation", "expression_heatmap", "gene_expression"}:
            _add_expression_downstream_node(graph, analysis_type)
            save_graph(graph)
            append_log(task_id, f"Analysis node enabled: {analysis_type}")
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
        "diff_export",
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


def _add_expression_downstream_node(graph: Graph, analysis_type: str, source_node_id: str = "upload_expression") -> None:
    specs = {
        "pca": (
            "pca__expression",
            "PCA 样本分布",
            "基于表达矩阵计算样本 PCA，用于查看分组和离群样本。",
            "pca_plot",
            {"top_variable_genes": 2000},
        ),
        "qc": (
            "qc__expression",
            "表达矩阵 QC",
            "查看样本表达量分布、总量和零值比例。",
            "qc_report",
            {
                "qc_preset": "normal",
            },
        ),
        "sample_correlation": (
            "correlation__expression",
            "样本相关性",
            "查看样本之间的相关性热图。",
            "sample_correlation_plot",
            {},
        ),
        "expression_heatmap": (
            "expression_heatmap__expression",
            "表达聚类热图",
            "基于表达矩阵的高变基因生成样本聚类热图。",
            "expression_heatmap_plot",
            {"top_genes": 40, "selected_conditions": []},
        ),
        "gene_expression": (
            "gene_expression__expression",
            "单基因表达",
            "查看指定基因在不同分组中的表达分布。",
            "gene_expression_plot",
            {"gene": "AUTO"},
        ),
    }
    specs.update(
        {
            "multigroup_differential": (
                "multigroup_differential__expression",
                "Multi-group differential plan",
                "Plan ANOVA or model-based multi-group differential analysis before post-hoc pairwise contrasts.",
                "planned_analysis",
                {"requires": "three or more conditions"},
            ),
            "wgcna": (
                "wgcna__expression",
                "WGCNA",
                "Detect co-expression modules from top-variable genes and summarize module-condition correlations.",
                "wgcna_result",
                {
                    "gene_selection_mode": "fixed",
                    "max_genes": 2000,
                    "top_gene_percent": 25,
                    "min_module_size": 20,
                    "soft_power": 0,
                    "merge_cut_height": 0.25,
                    "network_type": "signed",
                },
            ),
            "metabolomics_statistics": (
                "metabolomics_statistics__matrix",
                "Metabolomics statistics",
                "Run R-based metabolomics preprocessing, QC, PCA, correlation, and univariate differential statistics.",
                "metabolomics_statistics_result",
                {"p_value": 0.05, "log2fc": 1.0},
            ),
        }
    )

    if analysis_type not in specs:
        raise ValueError("Unsupported expression downstream analysis type")

    base_id, name, description, output_type, params = specs[analysis_type]
    node_id = _unique_node_id(graph, base_id)
    if analysis_type == "qc":
        input_types = ["expression_matrix"]
        depends_on = [source_node_id]
    elif source_node_id == "upload_expression":
        input_types = ["expression_matrix"]
        depends_on = [source_node_id]
    else:
        input_types = ["expression_matrix", "qc_report"]
        depends_on = [source_node_id, "upload_expression"]

    graph.nodes.append(
        GraphNode(
            id=node_id,
            name=name,
            description=description,
            status=NodeStatus.READY,
            input_types=input_types,
            output_type=output_type,
            default_params=params,
            params=params.copy(),
            depends_on=depends_on,
        )
    )
    graph.edges.append({"source": source_node_id, "target": node_id})


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
        "diff_export": (
            f"diff_export__{suffix}",
            f"结果导出：{comparison}",
            "导出该差异分析结果表，并提供结果预览。",
            "diff_export",
            {},
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


def rename_task(task_id: str, name: str) -> TaskState:
    task = load_task(task_id)
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Task name cannot be empty")
    task.name = clean_name[:80]
    save_task(task)
    append_log(task_id, f"Task renamed: {task.name}")
    return task


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


def _unique_input_path(inputs_dir: Path, filename: str) -> Path:
    target = inputs_dir / filename
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    counter = 2
    while True:
        candidate = inputs_dir / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _parse_metadata_text(content: str) -> list[dict[str, str]]:
    parsed = _parse_metadata_text_as_csv(content, ",")
    if parsed:
        return parsed
    parsed = _parse_metadata_text_as_csv(content, "\t")
    if parsed:
        return parsed

    try:
        loaded = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("Metadata text must be CSV/TSV text or JSON list format") from exc

    if isinstance(loaded, dict):
        loaded = [loaded]
    if not isinstance(loaded, list):
        raise ValueError("Metadata JSON must be an object or array of objects")

    if not loaded:
        raise ValueError("Metadata content is empty")

    rows: list[dict[str, str]] = []
    for raw_row in loaded:
        if not isinstance(raw_row, dict):
            raise ValueError("Metadata JSON records must be objects")
        row = {
            _metadata_header(key): str(value).strip()
            for key, value in raw_row.items()
            if _metadata_header(key)
        }
        if not row:
            continue
        rows.append(row)
    if not rows:
        raise ValueError("Metadata JSON has no valid records")

    if not _is_valid_metadata_rows(rows):
        raise ValueError("Metadata JSON must include sample, group, and condition for each row")
    return rows


def _parse_metadata_text_as_csv(content: str, delimiter: str) -> list[dict[str, str]]:
    reader = csv.DictReader(StringIO(content), delimiter=delimiter)
    if not reader.fieldnames:
        return []

    fieldnames = [_metadata_header(name) for name in reader.fieldnames]
    field_lookup = {name.lower(): name for name in fieldnames if name.strip()}
    if not set(("sample", "group", "condition")).issubset(field_lookup.keys()):
        sample_match = _metadata_alias_match(field_lookup, {"sample name", "sample_name", "sample"})
        metabolomics_condition = _metadata_alias_match(
            field_lookup,
            {
                "factor value[metabolic syndrome]",
                "factor_value[metabolic syndrome]",
                "factor value metabolic syndrome",
                "factor_value_metabolic_syndrome",
            },
        )
        if sample_match and metabolomics_condition:
            normalized_lookup = {
                "sample": sample_match,
                "group": _metadata_alias_match(
                    field_lookup,
                    {"factor value[gender]", "factor_value[gender]", "source name", "source_name"},
                )
                or metabolomics_condition,
                "condition": metabolomics_condition,
            }
        else:
            # Allow aliased input from quick manual copy/paste.
            aliases = {
                "sample": {"sample", "sample_id", "sample name", "sample_name"},
                "group": {"group", "group_id", "group name", "group_name"},
                "condition": {"condition", "condition_id", "condition name", "condition_name"},
            }
            normalized_lookup = {}
            for required, candidates in aliases.items():
                match = _metadata_alias_match(field_lookup, candidates)
                if match is None:
                    return []
                normalized_lookup[required] = match
    else:
        normalized_lookup = {key: key for key in ("sample", "group", "condition")}

    rows: list[dict[str, str]] = []
    for raw_row in reader:
        normalized_row = {_metadata_header(key): str(value or "").strip() for key, value in raw_row.items()}
        row = {key: str(normalized_row.get(source, "")).strip() for key, source in normalized_lookup.items()}
        if row["sample"] or row["group"] or row["condition"]:
            rows.append(row)
    if not rows:
        return []
    if not _is_valid_metadata_rows(rows):
        raise ValueError("Metadata text must include sample, group, and condition for each row")
    return rows


def _metadata_alias_match(field_lookup: dict[str, str], candidates: set[str]) -> str | None:
    normalized_lookup = {
        _metadata_header(key).replace("[", "").replace("]", "").replace(" ", "_"): value
        for key, value in field_lookup.items()
    }
    for candidate in candidates:
        direct = field_lookup.get(candidate.lower())
        if direct is not None:
            return direct
        normalized = _metadata_header(candidate).replace("[", "").replace("]", "").replace(" ", "_")
        if normalized in normalized_lookup:
            return normalized_lookup[normalized]
    return None


def _is_valid_metadata_rows(rows: list[dict[str, str]]) -> bool:
    return all(
        bool(row.get("sample", "").strip()) and bool(row.get("group", "").strip()) and bool(row.get("condition", "").strip())
        for row in rows
    )


def _metadata_header(value: str | None) -> str:
    return (value or "").lstrip("\ufeff").strip().lower()


def _serialize_metadata_rows(rows: list[dict[str, str]]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=["sample", "group", "condition"])
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _is_supported_expression_upload(filename: str) -> bool:
    return filename.endswith((".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".zip", ".tar", ".tar.gz", ".tgz", ".gz"))


def _looks_like_metadata_upload(filename: str, content: bytes) -> bool:
    if Path(filename).suffix.lower() not in {".csv", ".tsv", ".txt"}:
        return False
    try:
        _parse_metadata_bytes(content)
    except ValueError:
        return False
    return True


def _data_upload_priority(filename: str) -> tuple[int, str]:
    lowered = filename.lower()
    if lowered.startswith("m_") or "maf" in lowered or "metabolite" in lowered or "metabolomics" in lowered:
        return (0, lowered)
    if any(token in lowered for token in ("matrix", "expression", "count", "counts", "mrna", "gene")):
        return (1, lowered)
    if lowered.endswith((".csv", ".xlsx", ".xlsm")):
        return (2, lowered)
    return (3, lowered)


def _count_values(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _next_analyses_for_capabilities(capabilities: list[str]) -> list[dict[str, str]]:
    if "qc" in capabilities:
        return [
            {
                "type": "qc",
                "label": "Multi-sample QC",
                "description": "Gate expression data through sample QC before downstream analysis.",
            }
        ]
    specs = {
        "qc": {
            "type": "qc",
            "label": "矩阵 QC",
            "description": "查看表达量分布、总量和零值比例。",
        },
        "sample_correlation": {
            "type": "sample_correlation",
            "label": "样本相关性",
            "description": "查看样本间相关性热图。",
        },
        "expression_heatmap": {
            "type": "expression_heatmap",
            "label": "表达热图",
            "description": "基于高变基因生成表达聚类热图。",
        },
        "gene_expression": {
            "type": "gene_expression",
            "label": "单基因表达",
            "description": "查看指定基因在不同分组中的表达。",
        },
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
        "diff_export": {
            "type": "diff_export",
            "label": "结果导出",
            "description": "导出差异分析结果表并查看预览。",
        },
        "metabolomics_statistics": {
            "type": "metabolomics_statistics",
            "label": "Metabolomics statistics",
            "description": "Run R preprocessing, QC, PCA, correlation, and differential metabolite statistics.",
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
