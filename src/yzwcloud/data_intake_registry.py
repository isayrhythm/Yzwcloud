from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


DEFAULT_MAX_ITERATIONS = 3


DATA_TYPE_CAPABILITY_MAP = {
    "expression_matrix": {
        "qc",
        "sample_correlation",
        "expression_heatmap",
        "gene_expression",
        "pca",
        "diff_analysis",
        "multigroup_differential",
        "wgcna",
    },
    "metabolomics_matrix": {
        "qc",
        "sample_correlation",
        "expression_heatmap",
        "gene_expression",
        "pca",
        "metabolomics_normalization",
        "metabolomics_differential",
    },
    "single_cell_matrix": set(),
    "feature_table": set(),
    "diff_result": {"heatmap", "volcano", "enrichment"},
    "gene_list": {"enrichment"},
    "sample_metadata": set(),
    "unknown_table": set(),
}


def build_processing_plan(
    inspection: dict[str, Any],
    llm_plan: dict[str, Any],
    metadata_path: Path | None,
    max_iterations: int,
) -> dict[str, Any]:
    detected_type = str(llm_plan.get("data_type") or "unknown_table")
    file_type = str(inspection.get("file_type") or "unknown")
    has_metadata = bool(metadata_path and metadata_path.exists()) or inspection.get("metadata_rows", 0) > 0
    routed_type = detected_type
    if inspection.get("likely_metabolomics_columns") or inspection.get("likely_quantitative_feature_matrix"):
        routed_type = "metabolomics_matrix"
    if routed_type != "expression_matrix" and inspection.get("likely_gene_columns"):
        routed_type = "expression_matrix"
    strategies = _strategies_for_data_type(routed_type, file_type, has_metadata)[:max_iterations]

    unsupported_reason = ""
    if not strategies:
        if detected_type == "single_cell_matrix":
            unsupported_reason = "当前识别结果更像单细胞矩阵，但平台还没有接入单细胞标准化处理器。"
        elif detected_type == "feature_table":
            unsupported_reason = "当前识别结果更像机器学习/特征表，而不是可直接进入 bulk RNA 流程的表达矩阵。"
        else:
            unsupported_reason = "当前文件没有命中已支持的数据标准化路径。"

    return {
        "detected_data_type": detected_type,
        "routed_data_type": routed_type,
        "file_type": file_type,
        "max_iterations": max_iterations,
        "has_metadata": has_metadata,
        "strategies": strategies,
        "unsupported_reason": unsupported_reason,
    }


def execute_processing_strategy(
    source_path: Path,
    metadata_path: Path | None,
    output_dir: Path,
    inspection: dict[str, Any],
    llm_plan: dict[str, Any],
    strategy: dict[str, Any],
    standardizers: dict[str, Callable[..., dict[str, Any]]],
) -> dict[str, Any]:
    data_type = str(strategy.get("data_type") or "unknown_table")
    standardizer = standardizers.get(data_type)
    if standardizer is None:
        raise ValueError(f"No standardizer registered for data type: {data_type}")
    return standardizer(
        source_path=source_path,
        metadata_path=metadata_path,
        output_dir=output_dir,
        inspection=inspection,
        llm_plan=llm_plan,
        strategy=strategy,
    )


def direct_capabilities_for_data_type(data_type: str, capabilities: list[str]) -> list[str]:
    allowed_set = DATA_TYPE_CAPABILITY_MAP.get(data_type, set())
    return [capability for capability in capabilities if capability in allowed_set]


def plan_stop_message(plan: dict[str, Any]) -> str:
    return str(plan.get("unsupported_reason") or "当前文件未命中可执行的数据处理策略。")


def attempt_stop_reason(attempts: list[dict[str, Any]], plan: dict[str, Any]) -> str:
    if not attempts:
        return plan.get("unsupported_reason", "Agent 没有找到可执行的处理策略。")
    last_attempt = attempts[-1]
    if len(attempts) >= int(plan.get("max_iterations", DEFAULT_MAX_ITERATIONS)):
        return (
            f"Agent 已达到最大重试轮次 {plan.get('max_iterations', DEFAULT_MAX_ITERATIONS)}，"
            f"最后一次失败策略为“{last_attempt.get('label', '')}”。"
        )
    return f"Agent 已尝试策略“{last_attempt.get('label', '')}”，但仍未得到可用分析输入。"


def _strategies_for_data_type(
    data_type: str,
    file_type: str,
    has_metadata: bool,
) -> list[dict[str, Any]]:
    if data_type == "expression_matrix":
        return _expression_matrix_strategies(file_type, has_metadata)
    if data_type == "metabolomics_matrix":
        return _metabolomics_matrix_strategies(file_type, has_metadata)
    return []


def _expression_matrix_strategies(file_type: str, has_metadata: bool) -> list[dict[str, Any]]:
    strategies: list[dict[str, Any]] = []
    if has_metadata:
        strategies.append(
            {
                "id": f"{file_type}_metadata_last",
                "label": "优先按 metadata 匹配样本列",
                "data_type": "expression_matrix",
                "sample_mode": "metadata",
                "duplicate_policy": "last",
            }
        )
    strategies.append(
        {
            "id": f"{file_type}_numeric_last",
            "label": "按数值列推断样本，保留最后一组重复列",
            "data_type": "expression_matrix",
            "sample_mode": "numeric",
            "duplicate_policy": "last",
        }
    )
    strategies.append(
        {
            "id": f"{file_type}_numeric_first",
            "label": "按数值列推断样本，保留第一组重复列",
            "data_type": "expression_matrix",
            "sample_mode": "numeric",
            "duplicate_policy": "first",
        }
    )
    return strategies


def _metabolomics_matrix_strategies(file_type: str, has_metadata: bool) -> list[dict[str, Any]]:
    strategies: list[dict[str, Any]] = []
    strategies.append(
        {
            "id": f"{file_type}_metabolights_maf",
            "label": "按 MetaboLights MAF/代谢物峰表读取",
            "data_type": "metabolomics_matrix",
            "metadata_mode": "auto",
        }
    )
    if has_metadata:
        strategies.append(
            {
                "id": f"{file_type}_metabolomics_metadata",
                "label": "按上传 metadata 匹配代谢组样本列",
                "data_type": "metabolomics_matrix",
                "metadata_mode": "uploaded",
            }
        )
    return strategies
