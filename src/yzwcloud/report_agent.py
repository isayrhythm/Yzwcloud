from __future__ import annotations

import csv
import html
import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from yzwcloud.config import PROJECT_ROOT
from yzwcloud.models import DataObject


DEFAULT_MODEL = "deepseek-v4-flash"

NODE_REPORT_SYSTEM_PROMPT = """You are YZW BioCloud Node Report Agent.
Write a concise Chinese report for one bioinformatics workflow node.

Rules:
- Return JSON only.
- Use exactly these keys: summary, findings, methods, warnings, next_steps.
- findings, methods, warnings, and next_steps must be arrays of short strings.
- Base claims only on the provided structured evidence.
- Do not invent biological conclusions, statistical significance, visual patterns, or causal explanations.
- Distinguish completed computation from planned or placeholder analysis.
- Mention limitations when evidence is metadata-only.
- Explain user-facing technical terms, especially feature, importance, SHAP, VIP, log2FC, and p-value, when they appear.
- Tie the explanation to the current result rows, thresholds, model, assay profile, and output files in the evidence.
- If "feature" appears, state whether it means gene, metabolite, protein, generic measured peak, or model input variable for this node.
- Write for a user reading the current analysis page, not for an internal developer.
"""


def attach_node_agent_report(
    *,
    node_id: str,
    node_name: str,
    node_description: str,
    output: DataObject,
    params: dict[str, Any],
    inputs: dict[str, DataObject],
    output_dir: Path,
    use_llm: bool = True,
) -> DataObject:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = create_node_agent_report(
        node_id=node_id,
        node_name=node_name,
        node_description=node_description,
        output=output,
        params=params,
        inputs=inputs,
        use_llm=use_llm,
    )
    stem = _safe_stem(node_id)
    json_path = output_dir / f"{stem}_agent_report.json"
    html_path = output_dir / f"{stem}_agent_report.html"
    report["json_file"] = str(json_path)
    report["html_file"] = str(html_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(_report_html(report), encoding="utf-8")
    output.meta["agent_report"] = report
    output.meta["agent_report_file"] = str(json_path)
    output.meta["agent_report_html_file"] = str(html_path)
    _persist_output(output)
    return output


def create_node_agent_report(
    *,
    node_id: str,
    node_name: str,
    node_description: str,
    output: DataObject,
    params: dict[str, Any],
    inputs: dict[str, DataObject],
    use_llm: bool = True,
) -> dict[str, Any]:
    evidence = _build_evidence(
        node_id=node_id,
        node_name=node_name,
        node_description=node_description,
        output=output,
        params=params,
        inputs=inputs,
    )
    fallback = _rule_based_report(evidence)
    report_prompt = _build_report_prompt(evidence)
    llm_result = _generate_llm_report(report_prompt) if use_llm else {"llm_status": "disabled"}
    content = llm_result.get("report") if llm_result.get("llm_status") == "ok" else fallback
    return {
        "title": f"{node_name} · Agent 总结",
        "node_id": node_id,
        "node_name": node_name,
        "output_type": output.type,
        "summary": content["summary"],
        "findings": content["findings"],
        "methods": content["methods"],
        "warnings": content["warnings"],
        "next_steps": content["next_steps"],
        "evidence": evidence,
        "llm_prompt": report_prompt,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "generated_by": "llm" if llm_result.get("llm_status") == "ok" else "rule_based_fallback",
        "llm_status": llm_result.get("llm_status", "fallback"),
        "llm_error": llm_result.get("llm_error", ""),
        "model": llm_result.get("model", ""),
    }


def _build_evidence(
    *,
    node_id: str,
    node_name: str,
    node_description: str,
    output: DataObject,
    params: dict[str, Any],
    inputs: dict[str, DataObject],
) -> dict[str, Any]:
    return {
        "node": {
            "id": node_id,
            "name": node_name,
            "description": node_description,
        },
        "output": {
            "type": output.type,
            "data_file": _file_name(output.data),
            "meta": _compact_value(output.meta),
        },
        "params": _compact_value(params),
        "inputs": [
            {
                "node_id": input_id,
                "type": item.type,
                "data_file": _file_name(item.data),
                "meta": _compact_value(item.meta),
            }
            for input_id, item in inputs.items()
        ],
        "method_context": _method_context(output.type, output.meta, params),
        "result_context": _result_context(output.type, output.meta),
        "term_glossary": _term_glossary(output.type, output.meta, inputs),
    }


def _rule_based_report(evidence: dict[str, Any]) -> dict[str, Any]:
    output = evidence["output"]
    output_type = str(output["type"])
    meta = dict(output.get("meta") or {})
    node = evidence["node"]
    params = evidence.get("params") or {}
    findings = _findings_for_output(output_type, meta)
    methods = _methods_for_output(output_type, meta, params)
    warnings = _warnings_for_output(output_type, meta)
    next_steps = _next_steps_for_output(output_type, meta)
    return {
        "summary": _summary_for_output(str(node["name"]), output_type, meta),
        "findings": findings or ["节点已完成，当前输出可用于后续流程或人工复核。"],
        "methods": methods or ["当前节点未记录额外的方法参数。"],
        "warnings": warnings or ["当前结构化元数据中没有发现必须阻断流程的警告。"],
        "next_steps": next_steps or ["打开结果图或结果表，结合实验设计进行人工复核。"],
    }


def _method_context(output_type: str, meta: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {
        "output_type": output_type,
        "method": meta.get("method") or params.get("method") or "",
        "params": _compact_value(params),
    }
    if output_type == "metabolomics_ml_explainability_result":
        context.update(
            {
                "plain_language_method": (
                    "Feature importance explains which model input variables contributed most to the trained classifier. "
                    "For metabolomics, a feature is usually a metabolite or measured metabolite-like peak. "
                    "Importance is model evidence, not a causal biological conclusion."
                ),
                "source_model": meta.get("source_model", ""),
                "explainability_method": meta.get("explainability_method", ""),
                "top_feature": meta.get("top_feature", ""),
            }
        )
    elif output_type == "metabolomics_ml_result":
        context.update(
            {
                "plain_language_method": (
                    "A classification model tries to learn sample groups from the measured molecular features. "
                    "Balanced accuracy summarizes performance while reducing class imbalance effects."
                ),
                "selected_model": meta.get("selected_model") or meta.get("best_model") or "",
                "balanced_accuracy": meta.get("best_balanced_accuracy", ""),
            }
        )
    elif output_type == "volcano_plot":
        context.update(
            {
                "plain_language_method": (
                    "A volcano plot places fold change on the x-axis and statistical evidence on the y-axis. "
                    "Colored points indicate p-value significant up/down direction in the current implementation."
                ),
                "p_value_threshold": meta.get("p_value_threshold"),
                "log2fc_threshold": meta.get("log2fc_threshold"),
                "up_count": meta.get("up_count"),
                "down_count": meta.get("down_count"),
            }
        )
    elif output_type in {"diff_result", "metabolomics_differential_result", "metabolomics_statistics_result"}:
        context.update(
            {
                "plain_language_method": (
                    "Differential analysis compares feature values between two conditions and reports fold change "
                    "plus p-values; candidates require biological and statistical review."
                ),
                "comparison": meta.get("comparison_label", ""),
                "p_value_threshold": meta.get("p_value_threshold"),
                "log2fc_threshold": meta.get("log2fc_threshold"),
                "univariate_method": meta.get("univariate_method", ""),
                "vip_threshold": meta.get("vip_threshold"),
            }
        )
    return context


def _result_context(output_type: str, meta: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    if meta.get("feature_importance_file"):
        rows = _read_table_preview(meta["feature_importance_file"], limit=12)
        context["feature_importance_table"] = rows
        context["feature_importance_explanation"] = (
            "feature is the measured input variable used by the model; importance is a relative score ranking "
            "how much that variable influenced the model/explainability method for this node."
        )
    if meta.get("metrics_file"):
        context["metrics_table"] = _read_table_preview(meta["metrics_file"], limit=8)
    diff_path = meta.get("diff_result_file") or meta.get("metabolomics_result_file")
    if diff_path:
        context["differential_table"] = _read_table_preview(diff_path, limit=12)
    if meta.get("shap_values_file"):
        context["shap_values_table"] = _read_table_preview(meta["shap_values_file"], limit=6)
    if output_type == "volcano_plot":
        context["counts"] = {
            "points": meta.get("point_count", 0),
            "up": meta.get("up_count", 0),
            "down": meta.get("down_count", 0),
            "comparison": meta.get("comparison_label", ""),
        }
    if output_type == "gene_expression_plot":
        context["single_feature"] = {
            "feature": meta.get("gene") or meta.get("gene_id") or "",
            "feature_label": meta.get("feature_label", "feature"),
            "sample_count": meta.get("sample_count", 0),
            "value_label": meta.get("value_label", ""),
        }
    return context


def _term_glossary(output_type: str, meta: dict[str, Any], inputs: dict[str, DataObject]) -> dict[str, str]:
    feature_kind = _feature_kind(meta, inputs)
    glossary = {
        "feature": f"当前节点里的 feature 指模型或统计分析使用的输入变量；结合本数据，它更接近“{feature_kind}”。",
        "importance": "importance 是相对重要性或贡献排序，用来提示模型更依赖哪些变量，不等同于因果关系。",
    }
    if output_type == "metabolomics_ml_explainability_result":
        glossary["SHAP"] = "SHAP 用样本级贡献值解释模型预测；summary plot 中点的位置表示该变量对模型输出方向和大小的影响。"
    if output_type in {"volcano_plot", "diff_result", "metabolomics_differential_result", "metabolomics_statistics_result"}:
        glossary["log2FC"] = "log2FC 表示两组均值或模型估计差异的 log2 倍数变化，正负方向取决于比较顺序。"
        glossary["p_value"] = "p-value 衡量在零假设下观察到当前差异的概率大小，仍需结合多重检验和实验设计。"
    if meta.get("vip_threshold") is not None or meta.get("vip_available") is not None:
        glossary["VIP"] = "VIP 是 PLS-DA/OPLS-DA 中变量投影重要性指标，常用 VIP > 1 作为候选变量提示。"
    return glossary


def _feature_kind(meta: dict[str, Any], inputs: dict[str, DataObject]) -> str:
    candidates = [meta]
    candidates.extend(item.meta for item in inputs.values())
    for item in candidates:
        assay_profile = str(item.get("assay_profile") or "")
        data_type = str(item.get("data_type") or "")
        feature_label = str(item.get("feature_label") or "")
        if assay_profile == "protein":
            return "蛋白/蛋白定量特征"
        if assay_profile == "feature_intensity":
            return "未命名峰或通用定量特征"
        if data_type == "metabolomics_matrix" or "metabolite" in feature_label:
            return "代谢物或代谢物峰"
        if "protein" in feature_label:
            return "蛋白"
        if "gene" in feature_label or item.get("gene_count"):
            return "基因"
    return "特征变量"


def _read_table_preview(value: Any, *, limit: int) -> list[dict[str, Any]]:
    path = Path(str(value or ""))
    if not path.exists() or not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8-sig", newline="") as file:
            sample = file.read(4096)
            file.seek(0)
            delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
            reader = csv.DictReader(file, delimiter=delimiter)
            rows = []
            for index, row in enumerate(reader):
                if index >= limit:
                    break
                rows.append({str(key): _compact_scalar(value) for key, value in row.items() if key is not None})
            return rows
    except (OSError, UnicodeDecodeError, csv.Error):
        return []


def _compact_scalar(value: Any) -> Any:
    text = str(value or "").strip()
    if len(text) > 80:
        return text[:77] + "..."
    return text


def _summary_for_output(node_name: str, output_type: str, meta: dict[str, Any]) -> str:
    if output_type == "metabolomics_ml_explainability_result":
        return (
            f"{node_name} 已完成机器学习解释性分析："
            f"{meta.get('source_model', 'ML')} / {meta.get('explainability_method', 'importance')}。"
        )
    if output_type == "metabolomics_ml_result":
        return (
            f"{node_name} 已完成单模型机器学习分类："
            f"{meta.get('selected_model', meta.get('best_model', 'ML'))}，"
            f"balanced accuracy 为 {meta.get('best_balanced_accuracy', 'NA')}。"
        )
    if output_type == "pca_plot":
        explained = meta.get("explained_variance") or {}
        return (
            f"{node_name} 已完成：基于 {meta.get('gene_count', 0)} 个特征对 {meta.get('sample_count', 0)} "
            f"个样本进行 PCA，PC1 和 PC2 分别解释 {explained.get('pc1', 0)}% 与 {explained.get('pc2', 0)}% 的变异。"
        )
    if output_type == "qc_report":
        return (
            f"{node_name} 已完成：{meta.get('passed_sample_count', 0)}/{meta.get('sample_count', 0)} 个样本通过 QC，"
            f"{meta.get('failed_sample_count', 0)} 个样本需要复核。"
        )
    if output_type in {"diff_result", "metabolomics_differential_result", "metabolomics_statistics_result"}:
        significant = meta.get("diff_gene_count", meta.get("significant_metabolite_count", 0))
        tested = meta.get("tested_gene_count", meta.get("metabolite_count", 0))
        return f"{node_name} 已完成：{meta.get('comparison_label', '当前比较')} 共检验 {tested} 个特征，筛得 {significant} 个候选差异特征。"
    if output_type == "wgcna_result":
        return f"{node_name} 已完成：从 {meta.get('gene_count', 0)} 个基因中识别出 {meta.get('module_count', 0)} 个共表达模块。"
    if output_type == "metabolomics_ml_result":
        return (
            f"{node_name} 已完成机器学习分类：最佳模型为 {meta.get('best_model', 'ML')}，"
            f"balanced accuracy 为 {meta.get('best_balanced_accuracy', 'NA')}。"
        )
    if output_type == "planned_analysis":
        return f"{node_name} 已创建为规划节点；当前仅提供分析占位与上下文，还没有真实统计结果。"
    return f"{node_name} 已完成并生成 {output_type} 输出，可打开结果进行查看。"


def _findings_for_output(output_type: str, meta: dict[str, Any]) -> list[str]:
    if output_type == "metabolomics_ml_result":
        return [
            f"分类样本数：{meta.get('sample_count', 0)}。",
            f"训练模型：{meta.get('selected_model', meta.get('best_model', 'NA'))}。",
            f"balanced accuracy：{meta.get('best_balanced_accuracy', 'NA')}。",
            f"可选解释性：{', '.join(meta.get('available_explainability') or [])}。",
        ]
    if output_type == "metabolomics_ml_explainability_result":
        feature_kind = _feature_kind(meta, {})
        findings = [
            f"源模型：{meta.get('source_model', 'NA')}。",
            f"解释性方法：{meta.get('explainability_method', 'NA')}。",
            f"Top feature：{meta.get('top_feature', 'NA')}。",
            f"特征重要性表：{Path(str(meta.get('feature_importance_file', ''))).name if meta.get('feature_importance_file') else 'NA'}。",
            f"这里的 feature 指模型输入变量；结合当前数据，可理解为{feature_kind}，importance 是该变量对模型解释结果的相对贡献排序。",
        ]
        rows = _read_table_preview(meta.get("feature_importance_file"), limit=3) if meta.get("feature_importance_file") else []
        if rows:
            top_features = [str(row.get("feature") or row.get("metabolite") or row.get("gene") or "") for row in rows]
            findings.append(f"当前表中排名靠前的 feature 包括：{', '.join([item for item in top_features if item][:3])}。")
        return findings
    if output_type == "expression_matrix":
        feature_count = meta.get("metabolite_count", meta.get("gene_count", 0))
        return [
            f"识别到 {meta.get('sample_count', 0)} 个样本和 {feature_count} 个可分析特征。",
            f"数据类型：{meta.get('data_type', 'expression_matrix')}。",
        ]
    if output_type == "pca_plot":
        explained = meta.get("explained_variance") or {}
        return [
            f"进入 PCA 的样本数：{meta.get('sample_count', 0)}。",
            f"PC1 + PC2 累计解释变异：{float(explained.get('pc1', 0)) + float(explained.get('pc2', 0)):.2f}%。",
        ]
    if output_type == "qc_report":
        findings = [
            f"通过 QC：{meta.get('passed_sample_count', 0)} 个样本。",
            f"未通过 QC：{meta.get('failed_sample_count', 0)} 个样本。",
        ]
        if meta.get("normalization_applied"):
            findings.append(f"QC 后已执行 {meta.get('normalization_method', 'configured')} 归一化。")
        return findings
    if output_type == "sample_correlation_plot":
        return [
            f"相关性矩阵覆盖 {meta.get('sample_count', 0)} 个样本。",
            f"样本顺序策略：{meta.get('sample_ordering', '未记录')}。",
        ]
    if output_type in {"expression_heatmap_plot", "heatmap_plot"}:
        return [
            f"热图展示 {meta.get('gene_count', 0)} 个特征和 {meta.get('sample_count', 0)} 个样本。",
            f"比较或样本范围：{meta.get('comparison_label') or ', '.join(meta.get('selected_conditions') or []) or '当前选择'}。",
        ]
    if output_type == "gene_expression_plot":
        return [
            f"展示特征：{meta.get('gene', meta.get('gene_id', 'AUTO'))}。",
            f"样本数：{meta.get('sample_count', 0)}；数值类型：{meta.get('value_label', 'Expression')}。",
        ]
    if output_type == "volcano_plot":
        return [
            f"火山图包含 {meta.get('point_count', 0)} 个可视化点。",
            f"p 值显著上调：{meta.get('up_count', 0)}；p 值显著下调：{meta.get('down_count', 0)}。",
            f"比较：{meta.get('comparison_label', '当前比较')}。",
        ]
    if output_type in {"diff_result", "metabolomics_differential_result", "metabolomics_statistics_result"}:
        return [
            f"比较：{meta.get('comparison_label', '当前比较')}。",
            f"候选差异特征：{meta.get('diff_gene_count', meta.get('significant_metabolite_count', 0))}。",
            f"进入检验的特征：{meta.get('tested_gene_count', meta.get('metabolite_count', 0))}。",
        ]
    if output_type == "wgcna_result":
        return [
            f"模块数：{meta.get('module_count', 0)}。",
            f"模块内基因数：{meta.get('gene_count', 0)}；样本数：{meta.get('sample_count', 0)}。",
        ]
    if output_type == "metabolomics_ml_result":
        return [
            f"分类样本数：{meta.get('sample_count', 0)}。",
            f"训练模型：{', '.join(meta.get('models') or [])}。",
            f"最佳模型：{meta.get('best_model', 'NA')}；balanced accuracy：{meta.get('best_balanced_accuracy', 'NA')}。",
            f"特征重要性表：{Path(str(meta.get('feature_importance_file', ''))).name if meta.get('feature_importance_file') else 'NA'}。",
        ]
    if output_type == "diff_export":
        return [f"结果表包含 {meta.get('row_count', 0)} 行。", f"比较：{meta.get('comparison_label', '当前比较')}。"]
    return []


def _methods_for_output(output_type: str, meta: dict[str, Any], params: dict[str, Any]) -> list[str]:
    methods = []
    if output_type == "metabolomics_ml_result":
        methods.append(f"分类模型：{meta.get('selected_model', meta.get('best_model', 'ML'))}。")
        methods.append(f"特征筛选：高变特征 {meta.get('selected_feature_count', 0)} / {meta.get('feature_count', 0)}。")
        methods.append("解释性分析：机器学习节点完成后再创建 SHAP / permutation / RF importance 节点。")
        return methods
    if output_type == "metabolomics_ml_explainability_result":
        methods.append(f"解释性方法：{meta.get('explainability_method', 'importance')}。")
        methods.append(f"源模型：{meta.get('source_model', 'ML')}。")
        return methods
    if meta.get("method"):
        methods.append(f"方法：{meta['method']}。")
    if output_type == "qc_report":
        qc_params = meta.get("params") or params
        methods.append(f"QC 预设：{qc_params.get('qc_preset', 'normal')}。")
    if output_type in {"expression_heatmap_plot", "heatmap_plot"} and meta.get("cluster_method"):
        methods.append(f"聚类方法：{meta['cluster_method']}。")
    if output_type in {"diff_result", "metabolomics_differential_result", "metabolomics_statistics_result"}:
        if meta.get("univariate_method"):
            methods.append(f"单变量检验：{meta['univariate_method']}。")
        methods.append(
            f"筛选阈值：p <= {meta.get('p_value_threshold', params.get('p_value', 0.05))}，"
            f"|log2FC| >= {meta.get('log2fc_threshold', params.get('log2fc', 1.0))}。"
        )
        if meta.get("vip_threshold") is not None:
            methods.append(f"VIP 阈值：>{meta.get('vip_threshold')}。")
    if output_type == "expression_matrix" and meta.get("analysis_family") == "metabolomics_normalization":
        methods.append(
            f"代谢组处理：{meta.get('impute_method')} / {meta.get('normalization_method')} / "
            f"{meta.get('transform')} / {meta.get('scaling')}。"
        )
    if output_type == "metabolomics_ml_result":
        methods.append("分类模型：SVM、Naive Bayes、Random Forest。")
        methods.append(f"特征筛选：高变特征 {meta.get('selected_feature_count', 0)} / {meta.get('feature_count', 0)}。")
        methods.append(f"解释性分析：SHAP 可用={meta.get('shap_available', False)}；输出每个模型的特征重要性。")
    return methods


def _warnings_for_output(output_type: str, meta: dict[str, Any]) -> list[str]:
    warnings = []
    if output_type == "metabolomics_ml_explainability_result":
        warnings.append("解释性结果用于提示模型依赖的特征，不等同于因果结论。")
    if output_type == "planned_analysis":
        warnings.append("这是规划节点，不应当作已完成的统计分析结果引用。")
    if output_type == "qc_report" and int(meta.get("failed_sample_count") or 0):
        warnings.append("存在未通过 QC 的样本；下游解释前应检查剔除原因。")
    if output_type == "pca_plot":
        warnings.append("PCA 只描述样本整体分布，不等同于差异显著性检验。")
    if output_type in {"expression_heatmap_plot", "heatmap_plot"}:
        warnings.append("热图聚类用于探索模式，不能单独证明组间差异显著。")
    if output_type == "volcano_plot":
        warnings.append("火山图是阈值筛选视图，候选特征仍需要结合多重检验、注释和实验设计复核。")
    if output_type == "gene_expression_plot":
        warnings.append("单特征图是描述性视图；如需组间结论，应补充适当统计检验。")
    if output_type == "metabolomics_ml_result":
        warnings.append("机器学习分类结果用于探索分组可分性；正式结论仍需独立验证集、交叉验证设计和生物学解释共同支持。")
    return warnings


def _next_steps_for_output(output_type: str, meta: dict[str, Any]) -> list[str]:
    if output_type == "metabolomics_ml_result":
        return ["从该模型节点继续创建 SHAP、permutation 或 RF importance 节点，查看模型依赖的关键特征。"]
    if output_type == "metabolomics_ml_explainability_result":
        return ["把高重要性特征回到差异分析、通路分析和原始丰度图中复核。"]
    if output_type == "qc_report":
        return ["复核未通过 QC 的样本，再从 QC 节点创建 PCA、相关性、热图或差异分析。"]
    if output_type == "pca_plot":
        return ["结合分组颜色查看样本分离与离群情况，并用相关性热图交叉检查。"]
    if output_type in {"diff_result", "metabolomics_differential_result", "metabolomics_statistics_result"}:
        return ["继续生成火山图、差异热图和结果导出，并检查候选特征注释。"]
    if output_type == "volcano_plot":
        return ["打开差异结果表核对排名靠前的特征，并配合差异热图查看样本层面的模式。"]
    if output_type in {"expression_heatmap_plot", "heatmap_plot"}:
        return ["检查聚类是否与实验分组一致，并对关键特征回到单特征图或结果表复核。"]
    if output_type == "metabolomics_ml_result":
        return ["查看各模型特征重要性，优先复核多个模型共同排在前列的代谢物，并结合差异分析和通路分析进行解释。"]
    return []


def _build_report_prompt(evidence: dict[str, Any]) -> dict[str, Any]:
    user_prompt = json.dumps(
        {
            "task": "Generate a node-level bioinformatics report from the current node evidence.",
            "input_contract": "分析系统提示词 + 使用的方法 + 当前用户结果 -> agent报告",
            "required_focus": [
                "说明这个节点做了什么",
                "说明使用了什么分析方法和关键阈值",
                "解释当前结果中用户可能看不懂的术语",
                "引用当前结果表摘录，不要只复述模板",
                "给出下一步复核建议",
            ],
            "evidence": evidence,
        },
        ensure_ascii=False,
    )
    return {
        "system": NODE_REPORT_SYSTEM_PROMPT,
        "user": user_prompt,
    }


def _generate_llm_report(report_prompt: dict[str, str]) -> dict[str, Any]:
    api_key = _env_value("DEEPSEEK_API_KEY")
    if not api_key:
        return {"llm_status": "missing_api_key"}
    base_url = _env_value("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = _env_value("DEEPSEEK_REPORT_MODEL", _env_value("DEEPSEEK_ROUTER_MODEL", DEFAULT_MODEL))
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": report_prompt["system"]},
            {"role": "user", "content": report_prompt["user"]},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 2200,
        "temperature": 0.0,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = json.loads(response.read().decode("utf-8"))
        parsed = _parse_llm_json(raw["choices"][0]["message"].get("content") or "")
        return {"llm_status": "ok", "model": model, "report": _sanitize_report(parsed)}
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError, ValueError) as exc:
        return {"llm_status": "fallback", "llm_error": str(exc), "model": model}


def _parse_llm_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _sanitize_report(parsed: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        raise ValueError("LLM report is not a JSON object")
    summary = str(parsed.get("summary") or "").strip()
    if not summary:
        raise ValueError("LLM report summary is empty")
    return {
        "summary": summary,
        "findings": _string_list(parsed.get("findings")),
        "methods": _string_list(parsed.get("methods")),
        "warnings": _string_list(parsed.get("warnings")),
        "next_steps": _string_list(parsed.get("next_steps")),
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:12]


def _compact_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 3:
        return "..."
    if isinstance(value, dict):
        return {
            str(key): _compact_value(item, depth=depth + 1)
            for key, item in value.items()
            if key not in {"agent_report"}
        }
    if isinstance(value, list):
        return [_compact_value(item, depth=depth + 1) for item in value[:30]]
    if isinstance(value, Path):
        return value.name
    if isinstance(value, str) and ("\\" in value or "/" in value):
        return _file_name(value)
    return value


def _persist_output(output: DataObject) -> None:
    path = Path(str(output.data))
    if path.exists() and path.suffix.lower() == ".json":
        path.write_text(output.model_dump_json(indent=2), encoding="utf-8")


def _report_html(report: dict[str, Any]) -> str:
    def items(key: str) -> str:
        values = report.get(key) or []
        return "".join(f"<li>{html.escape(str(item))}</li>" for item in values)

    badge = "LLM" if report.get("generated_by") == "llm" else "Rule-based fallback"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(report["title"])}</title>
<style>
@page{{size:A4 landscape;margin:12mm}}*{{box-sizing:border-box}}
body{{margin:0;background:#eef5f5;color:#102333;font-family:Inter,"Microsoft YaHei",Arial,sans-serif}}
.page{{width:min(1120px,100%);min-height:720px;margin:20px auto;padding:34px;border:1px solid #d5e5e6;border-radius:24px;background:#fff;box-shadow:0 18px 44px rgba(23,58,70,.10)}}
.top{{display:flex;justify-content:space-between;gap:24px;border-bottom:2px solid #dceced;padding-bottom:18px}}
h1{{margin:0;color:#0f6b57;font-size:30px}}.badge{{align-self:flex-start;padding:7px 10px;border-radius:999px;background:#e8f7f4;color:#0f6b57;font-size:12px;font-weight:800}}
.summary{{margin:20px 0;padding:16px 18px;border-left:5px solid #0f8a8f;background:#f4fbfb;font-size:17px;line-height:1.7}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}
section{{padding:16px;border:1px solid #dbe7ec;border-radius:16px}}h2{{margin:0 0 8px;color:#0e5160;font-size:16px}}ul{{margin:0;padding-left:19px}}li{{margin:6px 0;line-height:1.5}}
footer{{margin-top:18px;color:#6a7b88;font-size:12px}}@media print{{body{{background:#fff}}.page{{margin:0;border:0;box-shadow:none}}}}
</style></head><body><article class="page">
<div class="top"><div><h1>{html.escape(report["title"])}</h1><p>{html.escape(report["output_type"])}</p></div><span class="badge">{badge}</span></div>
<p class="summary">{html.escape(report["summary"])}</p>
<div class="grid">
<section><h2>关键发现</h2><ul>{items("findings")}</ul></section>
<section><h2>方法与参数</h2><ul>{items("methods")}</ul></section>
<section><h2>解释边界</h2><ul>{items("warnings")}</ul></section>
<section><h2>下一步建议</h2><ul>{items("next_steps")}</ul></section>
</div><footer>Generated at {html.escape(report["generated_at"])} · {html.escape(str(report.get("llm_status", "")))}</footer>
</article></body></html>"""


def _safe_stem(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value).strip("_") or "node"


def _file_name(value: Any) -> str:
    text = str(value or "")
    return Path(text).name if text else ""


def _env_value(name: str, default: str = "") -> str:
    if name in os.environ:
        return os.environ[name]
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return default
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return default
