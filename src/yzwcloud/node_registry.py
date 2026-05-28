from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from yzwcloud.analysis_outputs import (
    create_diff_export_result,
    create_expression_heatmap_result,
    create_gene_expression_result,
    create_heatmap_result,
    create_pca_result,
    create_qc_result,
    create_sample_correlation_result,
    create_wgcna_result,
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
        default_params={"method": "r_transcriptomics", "p_value": 0.05, "log2fc": 1.0},
        depends_on=["upload_expression"],
    ),
}


def build_initial_edges() -> list[dict[str, str]]:
    # The diff selector is hidden until the user explicitly creates it from "+".
    return []


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
            source=_expression_source(inputs),
            output_dir=output_dir,
            node_id=node_id,
        )

    if node_id.startswith("qc__"):
        return create_qc_result(
            source=inputs["upload_expression"],
            output_dir=output_dir,
            node_id=node_id,
            params=params,
        )

    if node_id.startswith("correlation__"):
        return create_sample_correlation_result(
            source=_expression_source(inputs),
            output_dir=output_dir,
            node_id=node_id,
        )

    if node_id.startswith("expression_heatmap__"):
        return create_expression_heatmap_result(
            source=_expression_source(inputs),
            output_dir=output_dir,
            node_id=node_id,
            params=params,
        )

    if node_id.startswith("gene_expression__"):
        return create_gene_expression_result(
            source=_expression_source(inputs),
            params=params,
            output_dir=output_dir,
            node_id=node_id,
        )

    if node_id.startswith("wgcna__"):
        return create_wgcna_result(
            source=_expression_source(inputs),
            output_dir=output_dir,
            node_id=node_id,
            params=params,
        )

    if (
        node_id.startswith("paired_differential__")
        or node_id.startswith("multigroup_differential__")
    ):
        return _execute_plot_node(
            node_id=node_id,
            output_type="planned_analysis",
            message="Planned analysis node. Algorithm integration is pending.",
            meta={
                "analysis_family": node_id.split("__", 1)[0],
                "ready_for_agent": True,
                "sample_count": _expression_source(inputs).meta.get("sample_count"),
            },
            params=params,
            output_dir=output_dir,
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

    if node_id.startswith("diff_export__"):
        return create_diff_export_result(
            diff=next(iter(inputs.values())),
            output_dir=output_dir,
            node_id=node_id,
        )

    raise ValueError(f"Unknown node: {node_id}")


def _expression_source(inputs: dict[str, DataObject]) -> DataObject:
    for key, data_object in inputs.items():
        if key != "upload_expression" and _has_expression_matrix_meta(data_object):
            return _as_expression_matrix(data_object)
    upload = inputs.get("upload_expression")
    if upload is not None and _has_expression_matrix_meta(upload):
        return _as_expression_matrix(upload)
    for data_object in inputs.values():
        if _has_expression_matrix_meta(data_object):
            return _as_expression_matrix(data_object)
    raise ValueError("No expression matrix input is available")


def _has_expression_matrix_meta(data_object: DataObject) -> bool:
    return bool(data_object.meta.get("matrix_file") and data_object.meta.get("sample_metadata_file"))


def _as_expression_matrix(data_object: DataObject) -> DataObject:
    if data_object.type == "expression_matrix":
        return data_object
    return DataObject(
        type="expression_matrix",
        data=str(data_object.meta["matrix_file"]),
        meta=data_object.meta,
    )


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
