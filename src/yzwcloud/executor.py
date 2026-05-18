from __future__ import annotations

import time
from datetime import datetime

from yzwcloud.data_intake_agent import build_failure_report
from yzwcloud.models import DataObject, Graph, GraphNode, NodeStatus, TaskStatus
from yzwcloud.node_registry import execute_demo_node
from yzwcloud.task_store import (
    append_log,
    get_task_dir,
    load_graph,
    load_task,
    save_graph,
    save_task,
)


class NodeExecutionError(Exception):
    pass


def run_node(task_id: str, node_id: str, params: dict) -> None:
    task = load_task(task_id)
    graph = load_graph(task_id)
    node = _get_node(graph, node_id)

    if node.status == NodeStatus.RUNNING:
        raise NodeExecutionError(f"Node is already running: {node_id}")
    if not _dependencies_completed(graph, node):
        node.status = NodeStatus.BLOCKED
        node.error = "上游节点尚未完成"
        save_graph(graph)
        raise NodeExecutionError(node.error)

    merged_params = node.default_params | node.params | params
    node.params = merged_params
    if node_id == "upload_expression":
        node.params["agent_progress"] = {
            "step": "queued",
            "status": "running",
            "label": "准备启动 Agent",
            "history": [],
            "updated_at": datetime.now().isoformat(),
        }
    node.status = NodeStatus.RUNNING
    node.error = None
    node.started_at = datetime.now()
    node.completed_at = None
    task.status = TaskStatus.RUNNING
    task.current_node = node_id
    save_task(task)
    save_graph(graph)
    append_log(task_id, f"Node started: {node_id}")

    try:
        # Simulate a real analysis job so the UI can show running state.
        time.sleep(1)
        inputs = _collect_inputs(graph, node)
        output = execute_demo_node(
            node_id=node_id,
            inputs=inputs,
            params=merged_params,
            output_dir=get_task_dir(task_id) / "outputs",
            progress_callback=_make_progress_callback(task_id, node_id)
            if node_id == "upload_expression"
            else None,
        )

        graph = load_graph(task_id)
        node = _get_node(graph, node_id)
        node.output = output
        node.status = NodeStatus.COMPLETED
        node.completed_at = datetime.now()
        node.error = None
        _refresh_readiness(graph)

        task = load_task(task_id)
        task.status = TaskStatus.COMPLETED if _all_nodes_completed(graph) else TaskStatus.RUNNING
        task.current_node = None
        save_graph(graph)
        save_task(task)
        append_log(task_id, f"Node completed: {node_id}")
    except Exception as exc:
        graph = load_graph(task_id)
        node = _get_node(graph, node_id)
        node.status = NodeStatus.FAILED
        node.error = str(exc)
        if node_id == "upload_expression":
            checkpoint_path = get_task_dir(task_id) / "outputs" / "data_intake_checkpoint.json"
            node.params["agent_report"] = build_failure_report(checkpoint_path, str(exc))
            _set_progress(node, "failed", "failed", "处理失败，等待重试")
        node.completed_at = datetime.now()
        task = load_task(task_id)
        task.status = TaskStatus.FAILED
        task.current_node = None
        save_graph(graph)
        save_task(task)
        append_log(task_id, f"Node failed: {node_id} - {exc}")
        raise


def _get_node(graph: Graph, node_id: str) -> GraphNode:
    for node in graph.nodes:
        if node.id == node_id:
            return node
    raise NodeExecutionError(f"Unknown node: {node_id}")


def _dependencies_completed(graph: Graph, node: GraphNode) -> bool:
    if not node.depends_on:
        return True
    nodes = {item.id: item for item in graph.nodes}
    return all(nodes[dep].status == NodeStatus.COMPLETED for dep in node.depends_on)


def _collect_inputs(graph: Graph, node: GraphNode) -> dict[str, DataObject]:
    nodes = {item.id: item for item in graph.nodes}
    inputs = {}
    for dep in node.depends_on:
        output = nodes[dep].output
        if output is None:
            raise NodeExecutionError(f"Dependency has no output: {dep}")
        if node.input_types and output.type not in node.input_types:
            raise NodeExecutionError(f"Invalid input type from {dep}: {output.type}")
        inputs[dep] = output
    return inputs


def _refresh_readiness(graph: Graph) -> None:
    for node in graph.nodes:
        if node.status in {NodeStatus.COMPLETED, NodeStatus.RUNNING, NodeStatus.FAILED}:
            continue
        if node.id == "diff_analysis" and not any(
            edge["target"] == "diff_analysis"
            for edge in graph.edges
        ):
            node.status = NodeStatus.PENDING
            continue
        node.status = NodeStatus.READY if _dependencies_completed(graph, node) else NodeStatus.BLOCKED


def _all_nodes_completed(graph: Graph) -> bool:
    return all(node.status == NodeStatus.COMPLETED for node in graph.nodes)


def _make_progress_callback(task_id: str, node_id: str):
    def callback(step: str, status: str, label: str) -> None:
        graph = load_graph(task_id)
        node = _get_node(graph, node_id)
        _set_progress(node, step, status, label)
        save_graph(graph)
        append_log(task_id, f"Agent progress: {step} - {label}")

    return callback


def _set_progress(node: GraphNode, step: str, status: str, label: str) -> None:
    progress = dict(node.params.get("agent_progress") or {})
    history = list(progress.get("history") or [])
    if not history or history[-1].get("step") != step or history[-1].get("status") != status:
        history.append(
            {
                "step": step,
                "status": status,
                "label": label,
                "timestamp": datetime.now().isoformat(),
            }
        )
    node.params["agent_progress"] = {
        "step": step,
        "status": status,
        "label": label,
        "history": history[-8:],
        "updated_at": datetime.now().isoformat(),
    }
