from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from yzwcloud.analysis_outputs import (
    create_heatmap_result,
    create_pca_result,
    create_volcano_result,
    run_differential_analysis,
)
from yzwcloud.expression_matrix import (
    DEFAULT_EXPRESSION_FILE,
    DEFAULT_SAMPLE_METADATA_FILE,
    prepare_expression_matrix,
)
from yzwcloud.models import DataObject, NodeDefinition


NODE_DEFINITIONS: dict[str, NodeDefinition] = {
    "upload_expression": NodeDefinition(
        id="upload_expression",
        name="数据上传",
        description="上传数据文件后由 Agent 自动识别、规整、验证，并返回可用分析入口。",
        input_types=[],
        output_type="expression_matrix",
        default_params={
            "source_path": DEFAULT_EXPRESSION_FILE,
            "sample_metadata_path": DEFAULT_SAMPLE_METADATA_FILE,
        },
    ),
    "diff_analysis": NodeDefinition(
        id="diff_analysis",
        name="差异分析",
        description="选择两个样本分组后，衍生出一个独立的差异分析分支。",
        input_types=["expression_matrix"],
        output_type="diff_selector",
        default_params={"method": "demo_ttest", "p_value": 0.05, "log2fc": 1.0},
        depends_on=["upload_expression"],
    ),
}


def build_initial_edges() -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    for node in NODE_DEFINITIONS.values():
        edges.extend({"source": dep, "target": node.id} for dep in node.depends_on)
    return edges


def execute_demo_node(
    node_id: str,
    inputs: dict[str, DataObject],
    params: dict[str, Any],
    output_dir: Path,
    progress_callback: Callable[[str, str, str], None] | None = None,
) -> DataObject:
    output_dir.mkdir(parents=True, exist_ok=True)

    if node_id == "upload_expression":
        output = prepare_expression_matrix(
            params=params,
            output_dir=output_dir,
            progress_callback=progress_callback,
        )
        _write_detail(
            output_dir / f"{node_id}_detail.json",
            {
                "message": "表达矩阵已读取并标准化",
                "output": output.model_dump(),
                "generated_at": datetime.now().isoformat(),
            },
        )
        return output

    if node_id == "diff_analysis":
        raise ValueError("差异分析节点是选择器，请先选择 case/control 组合。")

    if node_id.startswith("diff_analysis__"):
        return run_differential_analysis(
            source=inputs["upload_expression"],
            params=params,
            output_dir=output_dir,
            node_id=node_id,
        )

    if node_id.startswith("pca__"):
        return create_pca_result(
            source=inputs["upload_expression"],
            output_dir=output_dir,
            node_id=node_id,
        )

    if node_id.startswith("heatmap__"):
        return create_heatmap_result(diff=next(iter(inputs.values())), output_dir=output_dir, node_id=node_id)

    if node_id.startswith("volcano__"):
        return create_volcano_result(diff=next(iter(inputs.values())), output_dir=output_dir, node_id=node_id)

    if node_id.startswith("enrichment__"):
        return _execute_plot_node(
            node_id=node_id,
            output_type="enrichment_result",
            message="MVP 示例富集分析结果",
            meta={"term_count": 18, "database": params.get("database", "GO")},
            params=params,
            output_dir=output_dir,
        )

    raise ValueError(f"Unknown node: {node_id}")


def _execute_diff_node(
    node_id: str,
    inputs: dict[str, DataObject],
    params: dict[str, Any],
    output_dir: Path,
) -> DataObject:
    source = inputs["upload_expression"]
    case_condition = str(params["case_condition"])
    control_condition = str(params["control_condition"])
    output_file = output_dir / f"{node_id}_output.json"

    payload = {
        "message": "MVP 示例差异分析结果",
        "comparison": {
            "case": case_condition,
            "control": control_condition,
        },
        "method": params.get("method", "demo_ttest"),
        "threshold": {
            "p_value": params.get("p_value", 0.05),
            "log2fc": params.get("log2fc", 1.0),
        },
        "input": source.model_dump(),
        "generated_at": datetime.now().isoformat(),
    }
    meta = {
        "diff_gene_count": 128,
        "method": payload["method"],
        "case_condition": case_condition,
        "control_condition": control_condition,
        "comparison_label": f"{case_condition} vs {control_condition}",
    }
    return _write_output(output_file, output_type="diff_result", meta=meta, payload=payload)


def _execute_plot_node(
    node_id: str,
    output_type: str,
    message: str,
    meta: dict[str, Any],
    params: dict[str, Any],
    output_dir: Path,
) -> DataObject:
    output_file = output_dir / f"{node_id}_output.json"
    payload = {
        "message": message,
        "params": params,
        "generated_at": datetime.now().isoformat(),
    }
    return _write_output(output_file, output_type=output_type, meta=meta, payload=payload)


def _write_output(
    output_file: Path,
    output_type: str,
    meta: dict[str, Any],
    payload: dict[str, Any],
) -> DataObject:
    output = DataObject(type=output_type, data=str(output_file), meta=meta)
    output_file.write_text(output.model_dump_json(indent=2), encoding="utf-8")
    _write_detail(output_file.with_name(output_file.stem.replace("_output", "_detail") + ".json"), payload)
    return output


def _write_detail(path: Path, payload: dict[str, Any]) -> None:
    import json

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
