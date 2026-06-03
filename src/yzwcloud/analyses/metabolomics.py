from __future__ import annotations

import csv
import html
import json
import math
import shutil
from datetime import datetime
from pathlib import Path
from statistics import fmean
from typing import Any

from yzwcloud.analyses.common import (
    GENE_INFO_COLUMNS,
    load_sample_columns,
    write_data_output,
    write_json_detail,
)
from yzwcloud.analyses.r_runner import run_r_script
from yzwcloud.models import DataObject


def create_metabolomics_statistics_result(
    source: DataObject,
    output_dir: Path,
    node_id: str,
    params: dict[str, Any] | None = None,
    output_type: str = "metabolomics_statistics_result",
    analysis_family: str = "metabolomics_statistics",
) -> DataObject:
    params = params or {}
    matrix_path = Path(str(source.meta.get("differential_matrix_file") or source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    output_dir.mkdir(parents=True, exist_ok=True)
    sample_columns = load_sample_columns(matrix_path, metadata_path)
    conditions = _condition_counts(sample_columns)
    if len(sample_columns) < 2:
        raise ValueError("Metabolomics statistics requires at least 2 samples")

    case_condition, control_condition = _comparison_conditions(conditions, params)
    r_matrix = output_dir / f"{node_id}_r_matrix.csv"
    r_metadata = output_dir / f"{node_id}_r_metadata.csv"
    _write_r_inputs(matrix_path, metadata_path, r_matrix, r_metadata)

    script_path = Path(__file__).resolve().parents[1] / "r" / "metabolomics_statistics.R"
    log_path = output_dir / f"{node_id}_r.log"
    prefix = _safe_slug(node_id)
    p_value = float(params.get("p_value", 0.05))
    log2fc = float(params.get("log2fc", 1.0))
    univariate_method = _metabolomics_univariate_method(params)
    vip_threshold = float(params.get("vip_threshold", 1.0))
    run_r_script(
        script_path=script_path,
        args=[
            str(r_matrix),
            str(r_metadata),
            str(output_dir),
            prefix,
            case_condition,
            control_condition,
            str(p_value),
            str(log2fc),
            univariate_method,
            str(vip_threshold),
        ],
        cwd=Path(__file__).resolve().parents[3],
        log_path=log_path,
        timeout=600,
        failure_hint="R metabolomics statistics failed",
    )

    summary_file = output_dir / f"{prefix}_summary.json"
    normalized_file = output_dir / f"{prefix}_normalized_matrix.csv"
    qc_file = output_dir / f"{prefix}_qc.csv"
    pca_file = output_dir / f"{prefix}_pca_scores.csv"
    plsda_file = output_dir / f"{prefix}_plsda_scores.csv"
    vip_file = output_dir / f"{prefix}_vip.csv"
    oplsda_file = output_dir / f"{prefix}_oplsda_scores.csv"
    correlation_file = output_dir / f"{prefix}_sample_correlation.csv"
    differential_file = output_dir / f"{prefix}_differential.csv"
    for path in [summary_file, normalized_file, qc_file, pca_file, plsda_file, vip_file, correlation_file, differential_file]:
        if not path.exists():
            raise ValueError(f"R metabolomics statistics finished without expected output: {path}")

    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    diff_rows = _read_diff_rows(differential_file)
    significant = [
        row
        for row in diff_rows
        if row["p_value"] <= p_value and abs(row["log2fc"]) >= log2fc
    ]
    output_json = output_dir / f"{node_id}_output.json"
    meta = {
        "method": "r_metabolomics_univariate_pca_qc",
        "analysis_family": analysis_family,
        "matrix_file": str(normalized_file),
        "source_matrix_file": str(matrix_path),
        "sample_metadata_file": str(metadata_path),
        "metabolomics_result_file": str(differential_file),
        "diff_result_file": str(differential_file),
        "qc_file": str(qc_file),
        "pca_scores_file": str(pca_file),
        "plsda_scores_file": str(plsda_file),
        "vip_file": str(vip_file),
        "sample_correlation_file": str(correlation_file),
        "r_script_file": str(script_path),
        "r_matrix_file": str(r_matrix),
        "r_metadata_file": str(r_metadata),
        "r_log_file": str(log_path),
        "summary_file": str(summary_file),
        "metabolite_count": int(summary.get("metabolite_count") or len(diff_rows)),
        "sample_count": int(summary.get("sample_count") or len(sample_columns)),
        "case_condition": case_condition,
        "control_condition": control_condition,
        "comparison_label": f"{case_condition} vs {control_condition}",
        "significant_metabolite_count": len(significant),
        "univariate_method": univariate_method,
        "p_value_threshold": p_value,
        "log2fc_threshold": log2fc,
        "vip_threshold": vip_threshold,
        "vip_available": bool(summary.get("vip_available")),
        "vip_feature_count": int(summary.get("vip_feature_count") or 0),
        "plsda_available": bool(summary.get("plsda_available")),
        "plsda_message": str(summary.get("plsda_message") or ""),
        "oplsda_available": bool(summary.get("oplsda_available")),
        "oplsda_message": str(summary.get("oplsda_message") or ""),
        "available_tables": [
            "normalized_matrix",
            "qc",
            "pca_scores",
            "plsda_scores",
            "vip",
            "sample_correlation",
            "differential",
        ],
        "not_implemented": [
            "database-backed KEGG/HMDB enrichment",
            "species-specific pathway enrichment",
        ],
    }
    if oplsda_file.exists():
        meta["oplsda_scores_file"] = str(oplsda_file)
        meta["available_tables"].append("oplsda_scores")
    if not meta["oplsda_available"]:
        meta["not_implemented"].append("OPLS-DA requires the ropls R package")
    write_json_detail(
        output_json.with_name(output_json.stem.replace("_output", "_detail") + ".json"),
        {
            "message": "Metabolomics statistics completed with R",
            "meta": meta,
            "top_metabolites": diff_rows[:30],
        },
    )
    return write_data_output(output_json, output_type, meta)


def create_metabolomics_differential_result(
    source: DataObject,
    output_dir: Path,
    node_id: str,
    params: dict[str, Any] | None = None,
) -> DataObject:
    return create_metabolomics_statistics_result(
        source=source,
        output_dir=output_dir,
        node_id=node_id,
        params=params,
        output_type="metabolomics_differential_result",
        analysis_family="metabolomics_differential",
    )


def create_metabolomics_normalization_result(
    source: DataObject,
    output_dir: Path,
    node_id: str,
    params: dict[str, Any] | None = None,
) -> DataObject:
    params = params or {}
    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    output_dir.mkdir(parents=True, exist_ok=True)
    sample_columns = load_sample_columns(matrix_path, metadata_path)
    if len(sample_columns) < 2:
        raise ValueError("Metabolomics normalization requires at least 2 samples")

    impute_method = str(params.get("impute_method") or "half_min").lower()
    normalization_method = str(params.get("normalization_method") or "tic_median").lower()
    transform_method = str(params.get("transform") or "log2").lower()
    scaling_method = str(params.get("scaling") or "pareto").lower()
    treat_zero_as_missing = bool(params.get("treat_zero_as_missing", True))

    features, matrix = _read_metabolomics_matrix(matrix_path, sample_columns, treat_zero_as_missing)
    if len(features) < 2:
        raise ValueError("Metabolomics normalization requires at least 2 usable metabolites")

    imputed, imputed_count = _impute_matrix(matrix, impute_method)
    normalized = _normalize_samples(imputed, normalization_method)
    transformed = _transform_matrix(normalized, transform_method)
    scaled = _scale_features(transformed, scaling_method)

    prefix = _safe_slug(node_id)
    normalized_matrix_file = output_dir / f"{prefix}_log_normalized_matrix.csv"
    scaled_matrix_file = output_dir / f"{prefix}_scaled_matrix.csv"
    metadata_copy = output_dir / f"{prefix}_sample_metadata.csv"
    html_path = output_dir / f"{node_id}.html"
    preview_path = output_dir / f"{node_id}_preview.svg"
    output_json = output_dir / f"{node_id}_output.json"

    shutil.copyfile(metadata_path, metadata_copy)
    _write_matrix(normalized_matrix_file, features, sample_columns, transformed)
    _write_matrix(scaled_matrix_file, features, sample_columns, scaled)
    before_totals = _sample_totals(imputed)
    after_totals = _sample_totals(normalized)

    meta = {
        **source.meta,
        "data_type": "metabolomics_matrix",
        "matrix_file": str(scaled_matrix_file),
        "differential_matrix_file": str(normalized_matrix_file),
        "source_matrix_file": str(matrix_path),
        "sample_metadata_file": str(metadata_copy),
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "metabolite_count": len(features),
        "gene_count": len(features),
        "sample_count": len(sample_columns),
        "normalization_method": normalization_method,
        "impute_method": impute_method,
        "transform": transform_method,
        "scaling": scaling_method,
        "treat_zero_as_missing": treat_zero_as_missing,
        "imputed_value_count": imputed_count,
        "sample_total_before_min": round(min(before_totals), 4) if before_totals else 0,
        "sample_total_before_max": round(max(before_totals), 4) if before_totals else 0,
        "sample_total_after_min": round(min(after_totals), 4) if after_totals else 0,
        "sample_total_after_max": round(max(after_totals), 4) if after_totals else 0,
        "analysis_family": "metabolomics_normalization",
    }
    _write_normalization_html(html_path, meta)
    _write_normalization_preview(preview_path, meta)
    write_json_detail(
        output_json.with_name(output_json.stem.replace("_output", "_detail") + ".json"),
        {
            "message": "Metabolomics normalization, imputation, and scaling completed",
            "meta": meta,
            "steps": [
                f"Imputation: {impute_method}",
                f"Normalization: {normalization_method}",
                f"Transform: {transform_method}",
                f"Scaling: {scaling_method}",
            ],
        },
    )
    return write_data_output(output_json, "expression_matrix", meta)


def create_metabolomics_ml_classification_result(
    source: DataObject,
    output_dir: Path,
    node_id: str,
    params: dict[str, Any] | None = None,
) -> DataObject:
    params = params or {}
    min_samples = int(params.get("min_samples") or 100)
    max_features = int(params.get("max_features") or 200)
    random_state = int(params.get("random_state") or 42)

    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    output_dir.mkdir(parents=True, exist_ok=True)
    sample_columns = load_sample_columns(matrix_path, metadata_path)
    if len(sample_columns) < min_samples:
        raise ValueError(f"Metabolomics ML classification requires at least {min_samples} samples")

    try:
        import numpy as np
        from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
        from sklearn.model_selection import StratifiedKFold, cross_val_predict
        from sklearn.preprocessing import LabelEncoder
    except ImportError as exc:  # pragma: no cover - exercised only in incomplete installs
        raise ValueError("Metabolomics ML classification requires scikit-learn") from exc
    model_name = _selected_ml_model_name(params, node_id)

    features, matrix = _read_ml_matrix(matrix_path, sample_columns)
    if len(features) < 2:
        raise ValueError("Metabolomics ML classification requires at least 2 usable features")
    labels = [column.condition for column in sample_columns]
    label_counts = _condition_counts(sample_columns)
    eligible_conditions = {condition for condition, count in label_counts.items() if count >= 2}
    keep_indexes = [index for index, label in enumerate(labels) if label in eligible_conditions]
    if len(eligible_conditions) < 2 or len(keep_indexes) < min_samples:
        raise ValueError("Metabolomics ML classification requires at least two classes with enough samples")

    labels = [labels[index] for index in keep_indexes]
    sample_names = [sample_columns[index].name for index in keep_indexes]
    x_all = np.array([[row[index] for row in matrix] for index in keep_indexes], dtype=float)
    x_all = np.nan_to_num(x_all, nan=0.0, posinf=0.0, neginf=0.0)

    selected_indexes = _top_variance_feature_indexes(x_all, max_features=max_features)
    if len(selected_indexes) < 2:
        raise ValueError("Metabolomics ML classification requires at least 2 variable features")
    x = x_all[:, selected_indexes]

    encoder = LabelEncoder()
    y = encoder.fit_transform(labels)
    min_class_count = min(label_counts[label] for label in eligible_conditions)
    n_splits = max(2, min(5, min_class_count))
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    model = _build_ml_classifier(model_name, params, random_state)
    predictions = cross_val_predict(model, x, y, cv=cv)
    accuracy = accuracy_score(y, predictions)
    balanced_accuracy = balanced_accuracy_score(y, predictions)
    f1_macro = f1_score(y, predictions, average="macro", zero_division=0)
    model.fit(x, y)
    metrics_rows: list[dict[str, Any]] = [
        {
            "model": model_name,
            "accuracy": round(float(accuracy), 6),
            "balanced_accuracy": round(float(balanced_accuracy), 6),
            "f1_macro": round(float(f1_macro), 6),
            "cv_folds": n_splits,
            "explainability_method": "created_by_downstream_node",
        }
    ]
    best_model = metrics_rows[0]
    run_stamp = datetime_safe_slug()
    metrics_file = output_dir / f"{node_id}_{run_stamp}_metrics.csv"
    html_path = output_dir / f"{node_id}_{run_stamp}.html"
    preview_path = output_dir / f"{node_id}_{run_stamp}_preview.svg"
    output_json = output_dir / f"{node_id}_{run_stamp}_output.json"
    _write_ml_metrics(metrics_file, metrics_rows)
    _write_ml_model_html(
        html_path,
        task_title="Metabolomics ML classification",
        labels=labels,
        sample_names=sample_names,
        metrics_rows=metrics_rows,
        meta={
            "sample_count": len(labels),
            "feature_count": len(features),
            "selected_feature_count": len(selected_indexes),
            "min_samples": min_samples,
            "class_names": list(encoder.classes_),
            "selected_model": model_name,
        },
    )
    _write_ml_model_preview(preview_path, metrics_rows)
    meta = {
        **source.meta,
        "analysis_family": "metabolomics_ml_classification",
        "method": f"sklearn_{model_name}",
        "data_type": "metabolomics_matrix",
        "matrix_file": str(matrix_path),
        "sample_metadata_file": str(metadata_path),
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "metrics_file": str(metrics_file),
        "sample_count": len(labels),
        "feature_count": len(features),
        "selected_feature_count": len(selected_indexes),
        "max_features": max_features,
        "min_samples": min_samples,
        "models": [model_name],
        "selected_model": model_name,
        "best_model": best_model["model"],
        "best_balanced_accuracy": best_model["balanced_accuracy"],
        "best_f1_macro": best_model["f1_macro"],
        "class_names": list(encoder.classes_),
        "available_explainability": _available_explainability_methods(model_name),
        "available_tables": ["metrics"],
    }
    write_json_detail(
        output_json.with_name(output_json.stem.replace("_output", "_detail") + ".json"),
        {
            "message": "Metabolomics ML classification completed",
            "meta": meta,
            "metrics": metrics_rows,
        },
    )
    return write_data_output(output_json, "metabolomics_ml_result", meta)


def create_metabolomics_ml_explainability_result(
    source: DataObject,
    output_dir: Path,
    node_id: str,
    params: dict[str, Any] | None = None,
) -> DataObject:
    params = params or {}
    method = _selected_explainability_method(params, node_id)
    model_name = _selected_ml_model_name({"model": source.meta.get("selected_model")}, "")
    if method == "rf_importance" and model_name != "random_forest":
        raise ValueError("RF importance is only available after a Random Forest classification node")

    random_state = int(source.meta.get("random_state") or params.get("random_state") or 42)
    min_samples = int(source.meta.get("min_samples") or params.get("min_samples") or 100)
    max_features = int(source.meta.get("max_features") or params.get("max_features") or 200)
    matrix_path = Path(str(source.meta["matrix_file"]))
    metadata_path = Path(str(source.meta["sample_metadata_file"]))
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import numpy as np
        from sklearn.inspection import permutation_importance
        from sklearn.preprocessing import LabelEncoder
    except ImportError as exc:  # pragma: no cover
        raise ValueError("Metabolomics ML explainability requires scikit-learn") from exc

    sample_columns = load_sample_columns(matrix_path, metadata_path)
    features, matrix = _read_ml_matrix(matrix_path, sample_columns)
    if len(sample_columns) < min_samples:
        raise ValueError(f"Metabolomics ML explainability requires at least {min_samples} samples")
    labels = [column.condition for column in sample_columns]
    label_counts = _condition_counts(sample_columns)
    eligible_conditions = {condition for condition, count in label_counts.items() if count >= 2}
    keep_indexes = [index for index, label in enumerate(labels) if label in eligible_conditions]
    if len(eligible_conditions) < 2 or len(keep_indexes) < min_samples:
        raise ValueError("Metabolomics ML explainability requires at least two usable classes")

    labels = [labels[index] for index in keep_indexes]
    x_all = np.array([[row[index] for row in matrix] for index in keep_indexes], dtype=float)
    x_all = np.nan_to_num(x_all, nan=0.0, posinf=0.0, neginf=0.0)
    feature_names = [feature[0] or feature[1] or f"feature_{idx + 1}" for idx, feature in enumerate(features)]
    feature_ids = [feature[1] or feature[0] or f"feature_{idx + 1}" for idx, feature in enumerate(features)]
    selected_indexes = _top_variance_feature_indexes(x_all, max_features=max_features)
    x = x_all[:, selected_indexes]
    selected_feature_names = [feature_names[index] for index in selected_indexes]
    selected_feature_ids = [feature_ids[index] for index in selected_indexes]

    encoder = LabelEncoder()
    y = encoder.fit_transform(labels)
    model = _build_ml_classifier(model_name, source.meta, random_state)
    model.fit(x, y)

    shap_values: list[list[float]] = []
    if method == "shap":
        scores, resolved_method, shap_values = _shap_feature_importance(model, model_name, x)
        ranked = _rank_importances(scores)
    elif method == "permutation":
        result = permutation_importance(
            model,
            x,
            y,
            scoring="balanced_accuracy",
            n_repeats=int(params.get("n_repeats") or 8),
            random_state=random_state,
            n_jobs=1,
        )
        ranked = _rank_importances([float(value) for value in result.importances_mean])
        resolved_method = "permutation_importance"
    else:
        scores = _native_feature_importance(model, model_name)
        if not scores:
            raise ValueError("RF importance is unavailable for this model")
        ranked = _rank_importances(scores)
        resolved_method = "rf_feature_importance"

    importance_rows = []
    for rank, (feature_index, score) in enumerate(ranked[:30], start=1):
        importance_rows.append(
            {
                "model": model_name,
                "rank": rank,
                "feature": selected_feature_names[feature_index],
                "feature_id": selected_feature_ids[feature_index],
                "importance": round(float(score), 8),
                "explainability_method": resolved_method,
            }
        )

    run_stamp = datetime_safe_slug()
    method_slug = method.replace("_", "-")
    importance_file = output_dir / f"{node_id}_{run_stamp}_feature_importance.csv"
    shap_values_file = output_dir / f"{node_id}_{run_stamp}_shap_values.csv"
    html_path = output_dir / f"{node_id}_{run_stamp}.html"
    preview_path = output_dir / f"{node_id}_{run_stamp}_preview.svg"
    output_json = output_dir / f"{node_id}_{run_stamp}_output.json"
    _write_ml_importance(importance_file, importance_rows)
    if shap_values:
        _write_shap_values(shap_values_file, shap_values, selected_feature_names, labels)
    else:
        shap_values_file = Path("")
    _write_ml_explainability_html(
        html_path,
        title=f"{model_name} {method_slug} explainability",
        model_name=model_name,
        method=resolved_method,
        importance_rows=importance_rows,
        shap_values=shap_values,
        feature_names=selected_feature_names,
    )
    _write_ml_explainability_preview(preview_path, model_name, resolved_method, importance_rows)
    meta = {
        **source.meta,
        "analysis_family": "metabolomics_ml_explainability",
        "method": resolved_method,
        "explainability_method": resolved_method,
        "requested_explainability": method,
        "source_model": model_name,
        "data_type": "metabolomics_matrix",
        "html_file": str(html_path),
        "preview_file": str(preview_path),
        "feature_importance_file": str(importance_file),
        "shap_values_file": str(shap_values_file) if shap_values_file else "",
        "sample_count": len(labels),
        "feature_count": len(features),
        "selected_feature_count": len(selected_indexes),
        "top_feature": importance_rows[0]["feature"] if importance_rows else "",
        "available_tables": ["feature_importance"] + (["shap_values"] if shap_values else []),
    }
    write_json_detail(
        output_json.with_name(output_json.stem.replace("_output", "_detail") + ".json"),
        {
            "message": "Metabolomics ML explainability completed",
            "meta": meta,
            "top_features": importance_rows[:30],
        },
    )
    return write_data_output(output_json, "metabolomics_ml_explainability_result", meta)


def _write_r_inputs(matrix_path: Path, metadata_path: Path, r_matrix: Path, r_metadata: Path) -> None:
    with matrix_path.open(encoding="utf-8-sig", newline="") as source_file, r_matrix.open(
        "w", encoding="utf-8-sig", newline=""
    ) as target_file:
        reader = csv.reader(source_file)
        header = next(reader, [])
        writer = csv.writer(target_file)
        writer.writerow(["feature_id", "feature_name", "description", *header[GENE_INFO_COLUMNS:]])
        for row in reader:
            if len(row) <= GENE_INFO_COLUMNS:
                continue
            writer.writerow(
                [
                    row[1] or row[0],
                    row[0] or row[1],
                    row[2] if len(row) > 2 else "",
                    *row[GENE_INFO_COLUMNS:],
                ]
            )

    with metadata_path.open(encoding="utf-8-sig", newline="") as source_file, r_metadata.open(
        "w", encoding="utf-8-sig", newline=""
    ) as target_file:
        reader = csv.DictReader(source_file)
        writer = csv.DictWriter(target_file, fieldnames=["sample", "group", "condition"])
        writer.writeheader()
        for row in reader:
            writer.writerow(
                {
                    "sample": row.get("sample", ""),
                    "group": row.get("group", row.get("condition", "")),
                    "condition": row.get("condition", row.get("group", "")),
                }
            )


def _read_metabolomics_matrix(
    matrix_path: Path,
    sample_columns: list[Any],
    treat_zero_as_missing: bool,
) -> tuple[list[list[str]], list[list[float | None]]]:
    features: list[list[str]] = []
    matrix: list[list[float | None]] = []
    with matrix_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)
        for row in reader:
            if len(row) <= GENE_INFO_COLUMNS:
                continue
            values: list[float | None] = []
            for column in sample_columns:
                raw = row[column.index] if column.index < len(row) else ""
                value = _optional_float(raw)
                if value is not None and treat_zero_as_missing and value == 0:
                    value = None
                values.append(value)
            if sum(value is not None for value in values) < 2:
                continue
            features.append((row + [""] * GENE_INFO_COLUMNS)[:GENE_INFO_COLUMNS])
            matrix.append(values)
    return features, matrix


def _read_ml_matrix(
    matrix_path: Path,
    sample_columns: list[Any],
) -> tuple[list[list[str]], list[list[float]]]:
    features: list[list[str]] = []
    matrix: list[list[float]] = []
    with matrix_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)
        for row in reader:
            if len(row) <= GENE_INFO_COLUMNS:
                continue
            values = []
            for column in sample_columns:
                raw = row[column.index] if column.index < len(row) else ""
                values.append(_float(raw, default=0.0))
            if len(values) < 2:
                continue
            features.append((row + [""] * GENE_INFO_COLUMNS)[:GENE_INFO_COLUMNS])
            matrix.append(values)
    return features, matrix


def _top_variance_feature_indexes(x: Any, max_features: int) -> list[int]:
    import numpy as np

    variances = np.var(x, axis=0)
    indexes = [index for index, value in enumerate(variances) if math.isfinite(float(value)) and float(value) > 0]
    indexes.sort(key=lambda index: float(variances[index]), reverse=True)
    return indexes[: max(2, max_features)]


def _selected_ml_model_name(params: dict[str, Any], node_id: str) -> str:
    raw = params.get("model") or params.get("selected_model")
    if not raw and isinstance(params.get("models"), list) and params["models"]:
        raw = params["models"][0]
    if not raw:
        if "naive_bayes" in node_id or "naive-bayes" in node_id:
            raw = "naive_bayes"
        elif "random_forest" in node_id or "random-forest" in node_id:
            raw = "random_forest"
        else:
            raw = "svm"
    model_name = str(raw).strip().lower().replace("-", "_")
    aliases = {
        "bayes": "naive_bayes",
        "nb": "naive_bayes",
        "naivebayes": "naive_bayes",
        "rf": "random_forest",
        "randomforest": "random_forest",
    }
    model_name = aliases.get(model_name, model_name)
    if model_name not in {"svm", "naive_bayes", "random_forest"}:
        raise ValueError(f"Unsupported ML classification model: {raw}")
    return model_name


def _build_ml_classifier(model_name: str, params: dict[str, Any], random_state: int) -> Any:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.naive_bayes import GaussianNB
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import LinearSVC

    if model_name == "svm":
        return make_pipeline(
            StandardScaler(),
            LinearSVC(class_weight="balanced", max_iter=10000, random_state=random_state),
        )
    if model_name == "naive_bayes":
        return GaussianNB()
    if model_name == "random_forest":
        return RandomForestClassifier(
            n_estimators=int(params.get("n_estimators") or 200),
            class_weight="balanced",
            random_state=random_state,
            n_jobs=1,
        )
    raise ValueError(f"Unsupported ML classification model: {model_name}")


def _available_explainability_methods(model_name: str) -> list[str]:
    methods = ["shap", "permutation"]
    if model_name == "random_forest":
        methods.append("rf_importance")
    return methods


def _selected_explainability_method(params: dict[str, Any], node_id: str) -> str:
    raw = params.get("explainability_method") or params.get("method")
    if not raw:
        if "permutation" in node_id:
            raw = "permutation"
        elif "rf_importance" in node_id or "rf-importance" in node_id:
            raw = "rf_importance"
        else:
            raw = "shap"
    method = str(raw).strip().lower().replace("-", "_")
    aliases = {"shape": "shap", "shap_violin": "shap", "rf": "rf_importance"}
    method = aliases.get(method, method)
    if method not in {"shap", "permutation", "rf_importance"}:
        raise ValueError(f"Unsupported ML explainability method: {raw}")
    return method


def _shap_feature_importance(model: Any, model_name: str, x: Any) -> tuple[list[float], str, list[list[float]]]:
    import numpy as np

    if model_name == "random_forest":
        try:
            import shap

            explainer = shap.TreeExplainer(model)
            values = explainer.shap_values(x[: min(len(x), 120)])
            if isinstance(values, list):
                arr = np.stack(values)
                arr = np.mean(arr, axis=0)
            else:
                arr = np.asarray(values)
                if arr.ndim == 3:
                    arr = np.mean(arr, axis=2)
            scores = _relative_importance_scores([float(value) for value in np.abs(arr).mean(axis=0)])
            return scores, "shap_tree_explainer", arr.tolist()
        except Exception:
            scores = _native_feature_importance(model, model_name)
            return scores, "rf_feature_importance_fallback", _pseudo_shap_values(x, scores)

    if model_name == "svm" and hasattr(model, "named_steps"):
        scaler = model.named_steps.get("standardscaler")
        estimator = model.named_steps.get("linearsvc")
        if scaler is not None and estimator is not None and hasattr(estimator, "coef_"):
            scaled = scaler.transform(x)
            coef = np.asarray(estimator.coef_)
            if coef.ndim == 2:
                coef = np.mean(coef, axis=0)
            values = (scaled - np.mean(scaled, axis=0)) * coef
            scores = _relative_importance_scores([float(value) for value in np.abs(values).mean(axis=0)])
            return scores, "shap_linear_approximation", values.tolist()

    scores = _native_feature_importance(model, model_name)
    if not scores:
        scores = [0.0 for _ in range(x.shape[1])]
    return _relative_importance_scores(scores), f"shap_{model_name}_approximation", _pseudo_shap_values(x, scores)


def _relative_importance_scores(scores: list[float]) -> list[float]:
    max_score = max([abs(float(score)) for score in scores] or [0.0])
    if max_score <= 0:
        return scores
    return [float(score) / max_score for score in scores]


def _pseudo_shap_values(x: Any, scores: list[float]) -> list[list[float]]:
    import numpy as np

    arr = np.asarray(x, dtype=float)
    centered = arr - np.mean(arr, axis=0)
    scale = np.asarray(scores, dtype=float)
    max_abs = float(np.max(np.abs(centered))) or 1.0
    return (centered / max_abs * scale).tolist()


def _is_shap_available() -> bool:
    try:
        import shap  # noqa: F401
    except Exception:
        return False
    return True


def _model_feature_importance(
    *,
    model: Any,
    model_name: str,
    x: Any,
    y: Any,
    feature_names: list[str],
    permutation_importance: Any,
    balanced_accuracy_score: Any,
    random_state: int,
    shap_available: bool,
) -> tuple[list[tuple[int, float]], str]:
    if shap_available and model_name == "random_forest":
        shap_scores = _try_tree_shap_importance(model, x)
        if shap_scores:
            return _rank_importances(shap_scores), "shap_tree_explainer"

    native_scores = _native_feature_importance(model, model_name)
    if native_scores:
        return _rank_importances(native_scores), "model_native_importance"

    try:
        result = permutation_importance(
            model,
            x,
            y,
            scoring="balanced_accuracy",
            n_repeats=5,
            random_state=random_state,
            n_jobs=1,
        )
        return _rank_importances(list(result.importances_mean)), "permutation_importance"
    except Exception:
        return [(index, 0.0) for index, _ in enumerate(feature_names)], "importance_unavailable"


def _try_tree_shap_importance(model: Any, x: Any) -> list[float]:
    try:
        import numpy as np
        import shap

        explainer = shap.TreeExplainer(model)
        values = explainer.shap_values(x[: min(len(x), 80)])
        if isinstance(values, list):
            arr = np.stack([np.abs(item).mean(axis=0) for item in values])
            return [float(value) for value in arr.mean(axis=0)]
        arr = np.asarray(values)
        if arr.ndim == 3:
            return [float(value) for value in np.abs(arr).mean(axis=(0, 2))]
        return [float(value) for value in np.abs(arr).mean(axis=0)]
    except Exception:
        return []


def _native_feature_importance(model: Any, model_name: str) -> list[float]:
    import numpy as np

    estimator = model
    if hasattr(model, "named_steps"):
        estimator = list(model.named_steps.values())[-1]
    if model_name == "random_forest" and hasattr(estimator, "feature_importances_"):
        return [float(value) for value in estimator.feature_importances_]
    if model_name == "svm" and hasattr(estimator, "coef_"):
        coef = np.asarray(estimator.coef_)
        if coef.ndim == 1:
            return [float(value) for value in np.abs(coef)]
        return [float(value) for value in np.abs(coef).mean(axis=0)]
    if model_name == "naive_bayes" and hasattr(estimator, "theta_"):
        theta = np.asarray(estimator.theta_)
        if theta.ndim == 2 and theta.shape[0] > 1:
            return [float(value) for value in np.std(theta, axis=0)]
    return []


def _rank_importances(scores: list[float]) -> list[tuple[int, float]]:
    ranked = [(index, max(0.0, float(score))) for index, score in enumerate(scores)]
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


def _write_ml_metrics(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "model",
                "accuracy",
                "balanced_accuracy",
                "f1_macro",
                "cv_folds",
                "explainability_method",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_ml_importance(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["model", "rank", "feature", "feature_id", "importance", "explainability_method"],
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_shap_values(path: Path, shap_values: list[list[float]], feature_names: list[str], labels: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["sample_index", "condition", *feature_names])
        for index, values in enumerate(shap_values):
            writer.writerow([index + 1, labels[index] if index < len(labels) else "", *values])


def _write_ml_model_html(
    path: Path,
    *,
    task_title: str,
    labels: list[str],
    sample_names: list[str],
    metrics_rows: list[dict[str, Any]],
    meta: dict[str, Any],
) -> None:
    class_counts = _count_strings(labels)
    row = metrics_rows[0]
    class_rows = "".join(
        f"<tr><td>{html.escape(condition)}</td><td>{count}</td></tr>"
        for condition, count in sorted(class_counts.items())
    )
    sample_preview = html.escape(", ".join(sample_names[:8]))
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(task_title)}</title>
<style>
body{{margin:0;background:#f6f8fb;color:#1f2329;font-family:Inter,'Microsoft YaHei',Arial,sans-serif}}
.wrap{{max-width:980px;margin:auto;padding:30px}}.panel{{background:#fff;border:1px solid #d8dde6;border-radius:8px;padding:20px;margin-top:16px}}
h1{{font-size:30px;margin:0 0 8px}}p{{color:#5f6b7a;line-height:1.65}}.tag{{color:#0052d9;font-weight:800}}
.metrics{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:18px}}.metric{{background:#f7f9fc;border:1px solid #e3e8ef;border-radius:8px;padding:16px}}
.metric span{{display:block;color:#5f6b7a}}.metric strong{{font-size:28px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px 12px;border-bottom:1px solid #eef2f7;text-align:left;font-size:13px}}th{{background:#f1f4f8}}
</style></head><body><main class="wrap">
<section class="panel"><div class="tag">Single-model classification node</div><h1>{html.escape(task_title)}</h1>
<p>This node runs after QC and normalize / impute / scale. It trains only <strong>{html.escape(str(meta["selected_model"]))}</strong>, so downstream explainability can be chosen separately.</p></section>
<section class="metrics">
<article class="metric"><span>Accuracy</span><strong>{float(row["accuracy"]):.3f}</strong></article>
<article class="metric"><span>Balanced accuracy</span><strong>{float(row["balanced_accuracy"]):.3f}</strong></article>
<article class="metric"><span>Macro F1</span><strong>{float(row["f1_macro"]):.3f}</strong></article>
</section>
<section class="panel"><h2>Training scope</h2><p>{meta["sample_count"]} samples; {meta["selected_feature_count"]} selected high-variance features from {meta["feature_count"]} total features. Sample preview: {sample_preview}</p></section>
<section class="panel"><h2>Class balance</h2><table><thead><tr><th>Condition</th><th>Samples</th></tr></thead><tbody>{class_rows}</tbody></table></section>
</main></body></html>""",
        encoding="utf-8",
    )


def _write_ml_model_preview(path: Path, metrics_rows: list[dict[str, Any]]) -> None:
    row = metrics_rows[0] if metrics_rows else {"model": "model", "balanced_accuracy": 0}
    width = max(4, min(150, float(row["balanced_accuracy"]) * 150))
    path.write_text(
        f"""<svg xmlns="http://www.w3.org/2000/svg" width="220" height="110" viewBox="0 0 220 110">
<rect width="220" height="110" rx="14" fill="#f6f8fb"/>
<text x="14" y="24" font-size="12" fill="#1f2329" font-weight="700">{html.escape(str(row["model"]))} classification</text>
<text x="14" y="44" font-size="10" fill="#5f6b7a">balanced accuracy</text>
<rect x="14" y="56" width="150" height="14" rx="7" fill="#d8dde6"/>
<rect x="14" y="56" width="{width:.2f}" height="14" rx="7" fill="#0052d9"/>
<text x="14" y="90" font-size="18" fill="#0052d9" font-weight="800">{float(row["balanced_accuracy"]):.3f}</text>
</svg>""",
        encoding="utf-8",
    )


def _write_ml_explainability_html(
    path: Path,
    *,
    title: str,
    model_name: str,
    method: str,
    importance_rows: list[dict[str, Any]],
    shap_values: list[list[float]],
    feature_names: list[str],
) -> None:
    rows_html = "".join(
        f"<tr><td>{row['rank']}</td><td>{html.escape(row['feature'])}</td><td>{float(row['importance']):.6f}</td></tr>"
        for row in importance_rows
    )
    summary_svg = _shap_summary_svg(shap_values, feature_names, importance_rows) if shap_values else ""
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body{{margin:0;background:#f6f8fb;color:#1f2329;font-family:Inter,'Microsoft YaHei',Arial,sans-serif}}
.wrap{{max-width:1180px;margin:auto;padding:30px}}.panel{{background:#fff;border:1px solid #d8dde6;border-radius:8px;padding:20px;margin-top:16px}}
h1{{font-size:30px;margin:0 0 8px}}p{{color:#5f6b7a;line-height:1.65}}.tag{{color:#0052d9;font-weight:800}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:10px 12px;border-bottom:1px solid #eef2f7;text-align:left;font-size:13px}}th{{background:#f1f4f8}}
.bars{{display:grid;gap:8px;margin-top:12px}}.bar-row{{display:grid;grid-template-columns:220px 1fr 72px;gap:10px;align-items:center}}.bar-row span{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}}.bar-row em{{display:block;height:12px;background:linear-gradient(90deg,#0052d9,#00a870);border-radius:999px}}.bar-row strong{{font-size:12px;color:#5f6b7a;text-align:right}}
</style></head><body><main class="wrap">
<section class="panel"><div class="tag">Explainability after machine learning</div><h1>{html.escape(title)}</h1>
    <p>Source model: <strong>{html.escape(model_name)}</strong>. Explainability method: <strong>{html.escape(method)}</strong>.</p></section>
<section class="panel"><h2>Feature importance</h2><table><thead><tr><th>Rank</th><th>Feature</th><th>Importance</th></tr></thead><tbody>{rows_html}</tbody></table></section>
{f'<section class="panel"><h2>SHAP summary plot</h2>{summary_svg}</section>' if summary_svg else ''}
</main></body></html>""",
        encoding="utf-8",
    )


def _write_ml_explainability_preview(
    path: Path,
    model_name: str,
    method: str,
    importance_rows: list[dict[str, Any]],
) -> None:
    top = importance_rows[:6]
    max_score = max([float(row["importance"]) for row in top] or [1.0]) or 1.0
    bars = []
    for index, row in enumerate(top):
        y = 42 + index * 11
        width = max(6, float(row["importance"]) / max_score * 104)
        color = ["#0052d9", "#0f8a8f", "#00a870", "#e37318", "#7e3af2", "#d54941"][index % 6]
        bars.append(
            f'<text x="14" y="{y + 7}" font-size="6.8" fill="#344054">{html.escape(str(row["feature"])[:18])}</text>'
            f'<rect x="92" y="{y}" width="110" height="8" rx="4" fill="#edf2f7"/>'
            f'<rect x="92" y="{y}" width="{width:.2f}" height="8" rx="4" fill="{color}"/>'
        )
    path.write_text(
        f"""<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120">
<defs>
  <linearGradient id="previewBg" x1="0" x2="1" y1="0" y2="1">
    <stop offset="0" stop-color="#ffffff"/>
    <stop offset="1" stop-color="#f1f6ff"/>
  </linearGradient>
</defs>
<rect width="220" height="120" rx="14" fill="url(#previewBg)"/>
<rect x="8" y="8" width="204" height="104" rx="12" fill="none" stroke="#d8e3f0"/>
<text x="14" y="22" font-size="10.5" fill="#101828" font-weight="800">Feature importance</text>
<text x="14" y="34" font-size="7.5" fill="#667085">{html.escape(model_name)} / {html.escape(method)}</text>
{"".join(bars)}
</svg>""",
        encoding="utf-8",
    )


def _shap_summary_svg(
    shap_values: list[list[float]],
    feature_names: list[str],
    importance_rows: list[dict[str, Any]],
) -> str:
    if not shap_values or not importance_rows:
        return ""
    top_features = [row["feature"] for row in importance_rows[:14]]
    feature_index = {name: index for index, name in enumerate(feature_names)}
    width = 1040
    row_height = 34
    top_pad = 58
    bottom_pad = 70
    height = top_pad + row_height * len(top_features) + bottom_pad
    values = [
        float(value)
        for row in shap_values
        for value in row[: len(feature_names)]
        if math.isfinite(float(value))
    ]
    lo = min(values or [-1.0])
    hi = max(values or [1.0])
    if lo == hi:
        lo -= 1.0
        hi += 1.0
    span = max(abs(lo), abs(hi), 1e-9)
    lo = -span
    hi = span
    axis_x = 300
    plot_w = width - axis_x - 72
    axis_right = axis_x + plot_w

    def x_for(value: float) -> float:
        return axis_x + ((value - lo) / (hi - lo)) * plot_w

    def point_color(value: float) -> str:
        normalized = min(1.0, abs(value) / span)
        if value >= 0:
            red = 211
            green = int(90 - normalized * 20)
            blue = int(105 - normalized * 38)
        else:
            red = int(45 - normalized * 15)
            green = int(119 - normalized * 40)
            blue = 216
        return f"rgb({red},{green},{blue})"

    tick_values = [lo, lo / 2, 0.0, hi / 2, hi]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs>',
        '<linearGradient id="shapLegend" x1="0" x2="1" y1="0" y2="0">',
        '<stop offset="0" stop-color="#1d4ed8"/>',
        '<stop offset="0.5" stop-color="#eef2f7"/>',
        '<stop offset="1" stop-color="#d54941"/>',
        '</linearGradient>',
        '</defs>',
        '<rect width="100%" height="100%" rx="16" fill="#ffffff"/>',
        f'<rect x="{axis_x - 12}" y="28" width="{plot_w + 24}" height="{height - 98}" rx="14" fill="#f8fafc" stroke="#e5e7eb"/>',
        f'<text x="18" y="28" font-size="18" fill="#101828" font-weight="800">SHAP summary plot</text>',
        f'<text x="18" y="48" font-size="12" fill="#667085">Top features ranked by mean absolute SHAP value; each dot is one sample.</text>',
    ]
    for tick in tick_values:
        x = x_for(tick)
        stroke = "#cbd5e1" if abs(tick) < 1e-12 else "#e8edf5"
        width_attr = "1.4" if abs(tick) < 1e-12 else "1"
        parts.append(
            f'<line x1="{x:.2f}" y1="{top_pad - 14}" x2="{x:.2f}" y2="{height - bottom_pad + 12}" stroke="{stroke}" stroke-width="{width_attr}"/>'
        )
        parts.append(
            f'<text x="{x:.2f}" y="{height - 34}" font-size="11" fill="#667085" text-anchor="middle">{tick:.3g}</text>'
        )
    parts.append(
        f'<line x1="{axis_x}" y1="{height - bottom_pad + 12}" x2="{axis_right}" y2="{height - bottom_pad + 12}" stroke="#cbd5e1"/>'
    )
    for row_number, feature in enumerate(top_features):
        idx = feature_index.get(feature)
        if idx is None:
            continue
        y = top_pad + row_number * row_height
        score = float(importance_rows[row_number].get("importance", 0.0)) if row_number < len(importance_rows) else 0.0
        label = html.escape(feature[:38])
        parts.append(f'<text x="18" y="{y + 4}" font-size="12" fill="#1f2329">{label}</text>')
        parts.append(f'<text x="248" y="{y + 4}" font-size="10" fill="#98a2b3" text-anchor="end">{score:.3f}</text>')
        parts.append(f'<line x1="{axis_x}" y1="{y}" x2="{axis_right}" y2="{y}" stroke="#edf2f7"/>')
        for sample_index, sample_values in enumerate(shap_values[:140]):
            if idx >= len(sample_values):
                continue
            value = float(sample_values[idx])
            x = x_for(value)
            jitter_seed = ((sample_index * 37 + idx * 13) % 23) - 11
            jitter = jitter_seed * 0.42
            radius = 2.25 + min(1.0, abs(value) / span) * 1.2
            color = point_color(value)
            parts.append(f'<circle cx="{x:.2f}" cy="{y + jitter:.2f}" r="{radius:.2f}" fill="{color}" opacity="0.72"/>')
    parts.extend(
        [
            f'<text x="{axis_x}" y="{height - 14}" font-size="12" fill="#475467">negative impact</text>',
            f'<text x="{axis_right}" y="{height - 14}" font-size="12" fill="#475467" text-anchor="end">positive impact</text>',
            f'<text x="{(axis_x + axis_right) / 2:.2f}" y="{height - 14}" font-size="12" fill="#101828" text-anchor="middle" font-weight="700">SHAP value (impact on model output)</text>',
            f'<rect x="{width - 210}" y="18" width="118" height="10" rx="5" fill="url(#shapLegend)"/>',
            f'<text x="{width - 214}" y="27" font-size="10" fill="#667085" text-anchor="end">low</text>',
            f'<text x="{width - 84}" y="27" font-size="10" fill="#667085">high</text>',
            f'<text x="{width - 150}" y="44" font-size="10" fill="#667085" text-anchor="middle">SHAP direction / magnitude</text>',
        ]
    )
    parts.append("</svg>")
    return "".join(parts)


def _write_ml_html_legacy(
    path: Path,
    *,
    task_title: str,
    labels: list[str],
    sample_names: list[str],
    metrics_rows: list[dict[str, Any]],
    importance_rows: list[dict[str, Any]],
    meta: dict[str, Any],
) -> None:
    class_counts = _count_strings(labels)
    metric_cards = "".join(
        f"""<article class="metric">
<span>{html.escape(row["model"])}</span>
<strong>{float(row["balanced_accuracy"]):.3f}</strong>
<small>balanced accuracy / F1 {float(row["f1_macro"]):.3f}</small>
</article>"""
        for row in metrics_rows
    )
    metrics_table = "".join(
        f"""<tr><td>{html.escape(row["model"])}</td><td>{float(row["accuracy"]):.3f}</td><td>{float(row["balanced_accuracy"]):.3f}</td><td>{float(row["f1_macro"]):.3f}</td><td>{html.escape(str(row["explainability_method"]))}</td></tr>"""
        for row in metrics_rows
    )
    top_by_model = []
    for model in [row["model"] for row in metrics_rows]:
        rows = [row for row in importance_rows if row["model"] == model][:12]
        max_score = max([float(row["importance"]) for row in rows] or [1.0])
        bars = "".join(
            f"""<div class="bar-row"><span>{html.escape(row["feature"])}</span><em style="width:{max(2, float(row["importance"]) / max_score * 100):.2f}%"></em><strong>{float(row["importance"]):.4f}</strong></div>"""
            for row in rows
        )
        method = rows[0]["explainability_method"] if rows else "importance_unavailable"
        top_by_model.append(
            f"""<section class="model-block"><h2>{html.escape(model)} 特征重要性</h2><p>解释方法：{html.escape(str(method))}</p><div class="bars">{bars}</div></section>"""
        )
    class_rows = "".join(
        f"<tr><td>{html.escape(condition)}</td><td>{count}</td></tr>"
        for condition, count in sorted(class_counts.items())
    )
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(task_title)}</title>
<style>
body{{margin:0;background:#f6f8fb;color:#1f2329;font-family:Inter,'Microsoft YaHei',Arial,sans-serif}}
.wrap{{max-width:1180px;margin:auto;padding:30px}}
h1{{font-size:32px;margin:0 0 8px}}p{{color:#5f6b7a;line-height:1.65}}
.metrics{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:22px 0}}
.metric,.panel,.model-block{{background:#fff;border:1px solid #d8dde6;border-radius:8px;padding:18px}}
.metric span{{display:block;color:#0052d9;font-weight:800}}.metric strong{{font-size:30px}}.metric small{{display:block;color:#5f6b7a}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:18px 0}}
table{{width:100%;border-collapse:collapse;background:white;border:1px solid #d8dde6;border-radius:8px;overflow:hidden}}
th,td{{padding:10px 12px;border-bottom:1px solid #eef2f7;text-align:left;font-size:13px}}th{{background:#f1f4f8;color:#1f2329}}
.model-block{{margin-top:16px}}.model-block h2{{font-size:21px;margin:0 0 4px}}
.bars{{display:grid;gap:8px}}.bar-row{{display:grid;grid-template-columns:220px 1fr 72px;gap:10px;align-items:center}}
.bar-row span{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}}
.bar-row em{{display:block;height:12px;background:#0052d9;border-radius:999px}}.bar-row strong{{font-size:12px;color:#5f6b7a;text-align:right}}
@media(max-width:860px){{.metrics,.grid{{grid-template-columns:1fr}}.bar-row{{grid-template-columns:1fr}}}}
</style></head><body><main class="wrap">
<h1>{html.escape(task_title)}</h1>
<p>分类节点在 QC 通过并完成 normalize / impute / scale 后运行。当前使用 {meta["sample_count"]} 个样本、{meta["selected_feature_count"]} / {meta["feature_count"]} 个高变特征训练 SVM、Naive Bayes 和 Random Forest。</p>
<section class="metrics">{metric_cards}</section>
<section class="grid">
<div class="panel"><h2>模型评估</h2><table><thead><tr><th>Model</th><th>Accuracy</th><th>Balanced accuracy</th><th>F1 macro</th><th>解释方法</th></tr></thead><tbody>{metrics_table}</tbody></table></div>
<div class="panel"><h2>分组样本数</h2><table><thead><tr><th>Condition</th><th>Samples</th></tr></thead><tbody>{class_rows}</tbody></table><p>SHAP 可用：{str(meta["shap_available"]).lower()}；样本示例：{html.escape(", ".join(sample_names[:8]))}</p></div>
</section>
{"".join(top_by_model)}
</main></body></html>""",
        encoding="utf-8",
    )


def _write_ml_html(
    path: Path,
    *,
    task_title: str,
    labels: list[str],
    sample_names: list[str],
    metrics_rows: list[dict[str, Any]],
    importance_rows: list[dict[str, Any]],
    meta: dict[str, Any],
) -> None:
    class_counts = _count_strings(labels)
    best_row = metrics_rows[0] if metrics_rows else {
        "model": "model",
        "balanced_accuracy": 0.0,
        "f1_macro": 0.0,
    }
    metric_cards = "".join(
        f"""<article class="metric">
<span>{html.escape(row["model"])}</span>
<strong>{float(row["balanced_accuracy"]):.3f}</strong>
<small>balanced accuracy / F1 {float(row["f1_macro"]):.3f}</small>
</article>"""
        for row in metrics_rows
    )
    metrics_table = "".join(
        f"""<tr><td>{html.escape(row["model"])}</td><td>{float(row["accuracy"]):.3f}</td><td>{float(row["balanced_accuracy"]):.3f}</td><td>{float(row["f1_macro"]):.3f}</td><td>{html.escape(str(row["explainability_method"]))}</td></tr>"""
        for row in metrics_rows
    )
    model_sections = []
    for model in [row["model"] for row in metrics_rows]:
        rows = [row for row in importance_rows if row["model"] == model][:12]
        max_score = max([float(row["importance"]) for row in rows] or [1.0])
        bars = "".join(
            f"""<div class="bar-row"><span>{html.escape(row["feature"])}</span><em style="width:{max(2, float(row["importance"]) / max_score * 100):.2f}%"></em><strong>{float(row["importance"]):.4f}</strong></div>"""
            for row in rows
        )
        method = rows[0]["explainability_method"] if rows else "importance_unavailable"
        model_sections.append(
            f"""<section class="model-block">
<h2>{html.escape(model)} feature importance</h2>
<p>Explainability method: {html.escape(str(method))}. The bars rank features by the selected model-specific explanation score.</p>
<div class="bars">{bars}</div>
</section>"""
        )
    class_rows = "".join(
        f"<tr><td>{html.escape(condition)}</td><td>{count}</td></tr>"
        for condition, count in sorted(class_counts.items())
    )
    shap_status = "available" if meta["shap_available"] else "not available"
    sample_preview = html.escape(", ".join(sample_names[:8]))
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(task_title)}</title>
<style>
body{{margin:0;background:#f6f8fb;color:#1f2329;font-family:Inter,'Microsoft YaHei',Arial,sans-serif}}
.wrap{{max-width:1180px;margin:auto;padding:30px}}
h1{{font-size:32px;margin:0 0 8px}}p{{color:#5f6b7a;line-height:1.65;margin:8px 0 0}}
.hero,.metric,.panel,.model-block{{background:#fff;border:1px solid #d8dde6;border-radius:8px;padding:18px}}
.hero{{padding:22px}}.hero strong{{color:#1f2329}}.tagline{{color:#0052d9;font-weight:800}}
.metrics{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:22px 0}}
.metric span{{display:block;color:#0052d9;font-weight:800}}.metric strong{{font-size:30px}}.metric small{{display:block;color:#5f6b7a}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:18px 0}}
table{{width:100%;border-collapse:collapse;background:white;border:1px solid #d8dde6;border-radius:8px;overflow:hidden}}
th,td{{padding:10px 12px;border-bottom:1px solid #eef2f7;text-align:left;font-size:13px}}th{{background:#f1f4f8;color:#1f2329}}
.model-block{{margin-top:16px}}.model-block h2{{font-size:21px;margin:0 0 4px}}
.bars{{display:grid;gap:8px}}.bar-row{{display:grid;grid-template-columns:220px 1fr 72px;gap:10px;align-items:center}}
.bar-row span{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}}
.bar-row em{{display:block;height:12px;background:linear-gradient(90deg,#0052d9,#00a870);border-radius:999px}}.bar-row strong{{font-size:12px;color:#5f6b7a;text-align:right}}
@media(max-width:860px){{.metrics,.grid{{grid-template-columns:1fr}}.bar-row{{grid-template-columns:1fr}}}}
</style></head><body><main class="wrap">
<section class="hero">
<div class="tagline">Metabolomics ML classification</div>
<h1>{html.escape(task_title)}</h1>
<p>This node runs after QC and normalize / impute / scale. It trains SVM, Naive Bayes, and Random Forest classifiers on <strong>{meta["sample_count"]}</strong> samples, using <strong>{meta["selected_feature_count"]}</strong> selected high-variance features from <strong>{meta["feature_count"]}</strong> total features.</p>
<p>Current best model: <strong>{html.escape(str(best_row["model"]))}</strong>, balanced accuracy <strong>{float(best_row["balanced_accuracy"]):.3f}</strong>, macro F1 <strong>{float(best_row["f1_macro"]):.3f}</strong>.</p>
</section>
<section class="metrics">{metric_cards}</section>
<section class="grid">
<div class="panel"><h2>Model evaluation</h2><table><thead><tr><th>Model</th><th>Accuracy</th><th>Balanced accuracy</th><th>F1 macro</th><th>Explainability</th></tr></thead><tbody>{metrics_table}</tbody></table></div>
<div class="panel"><h2>Class balance</h2><table><thead><tr><th>Condition</th><th>Samples</th></tr></thead><tbody>{class_rows}</tbody></table><p>SHAP package: {shap_status}. Sample preview: {sample_preview}</p></div>
</section>
{"".join(model_sections)}
</main></body></html>""",
        encoding="utf-8",
    )


def _write_ml_preview(
    path: Path,
    metrics_rows: list[dict[str, Any]],
    importance_rows: list[dict[str, Any]],
) -> None:
    best = metrics_rows[0] if metrics_rows else {"model": "model", "balanced_accuracy": 0}
    top = [row for row in importance_rows if row["model"] == best["model"]][:5]
    max_score = max([float(row["importance"]) for row in top] or [1.0])
    bars = []
    for index, row in enumerate(top):
        y = 58 + index * 12
        width = max(4, float(row["importance"]) / max_score * 108)
        label = html.escape(str(row["feature"])[:18])
        bars.append(
            f'<text x="12" y="{y + 8}" font-size="7" fill="#5f6b7a">{label}</text>'
            f'<rect x="92" y="{y}" width="{width:.2f}" height="8" rx="4" fill="#0052d9"/>'
        )
    path.write_text(
        f"""<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120">
<rect width="220" height="120" rx="14" fill="#f6f8fb"/>
<text x="12" y="18" font-size="11" fill="#1f2329" font-weight="700">ML classification</text>
<text x="12" y="34" font-size="9" fill="#0052d9" font-weight="700">{html.escape(str(best["model"]))} balanced acc {float(best["balanced_accuracy"]):.3f}</text>
{"".join(bars)}
</svg>""",
        encoding="utf-8",
    )


def _count_strings(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def datetime_safe_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _impute_matrix(matrix: list[list[float | None]], method: str) -> tuple[list[list[float]], int]:
    imputed_count = 0
    output: list[list[float]] = []
    for row in matrix:
        present = [value for value in row if value is not None and math.isfinite(value)]
        positives = [value for value in present if value > 0]
        if method == "zero":
            fill = 0.0
        elif method == "median":
            fill = sorted(present)[len(present) // 2] if present else 0.0
        else:
            fill = min(positives) / 2 if positives else (min(present) / 2 if present else 0.0)
        next_row = []
        for value in row:
            if value is None or not math.isfinite(value):
                next_row.append(fill)
                imputed_count += 1
            else:
                next_row.append(value)
        output.append(next_row)
    return output, imputed_count


def _normalize_samples(matrix: list[list[float]], method: str) -> list[list[float]]:
    if method not in {"tic_median", "total_signal", "median"}:
        return [row[:] for row in matrix]
    sample_count = len(matrix[0]) if matrix else 0
    if sample_count == 0:
        return []
    if method == "median":
        factors = []
        for sample_index in range(sample_count):
            values = sorted(row[sample_index] for row in matrix if row[sample_index] > 0)
            factors.append(values[len(values) // 2] if values else 1.0)
    else:
        factors = [sum(max(row[sample_index], 0.0) for row in matrix) for sample_index in range(sample_count)]
    positive = [value for value in factors if value > 0 and math.isfinite(value)]
    target = sorted(positive)[len(positive) // 2] if positive else 1.0
    safe_factors = [factor if factor > 0 and math.isfinite(factor) else target for factor in factors]
    return [
        [value / safe_factors[index] * target for index, value in enumerate(row)]
        for row in matrix
    ]


def _transform_matrix(matrix: list[list[float]], method: str) -> list[list[float]]:
    if method == "none":
        return [row[:] for row in matrix]
    if method == "log10":
        return [[math.log10(max(value, 0.0) + 1.0) for value in row] for row in matrix]
    return [[math.log2(max(value, 0.0) + 1.0) for value in row] for row in matrix]


def _scale_features(matrix: list[list[float]], method: str) -> list[list[float]]:
    if method == "none":
        return [row[:] for row in matrix]
    scaled = []
    for row in matrix:
        mean = fmean(row) if row else 0.0
        variance_value = sum((value - mean) ** 2 for value in row) / (len(row) - 1) if len(row) > 1 else 0.0
        sd = math.sqrt(variance_value)
        if sd == 0 or not math.isfinite(sd):
            scaled.append([0.0 for _ in row])
            continue
        denominator = math.sqrt(sd) if method == "pareto" else sd
        scaled.append([(value - mean) / denominator for value in row])
    return scaled


def _write_matrix(
    path: Path,
    features: list[list[str]],
    sample_columns: list[Any],
    matrix: list[list[float]],
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "gene_short_name",
                "gene_id",
                "description",
                "module",
                "chromosome",
                "gene_type",
                *[column.name for column in sample_columns],
            ]
        )
        for feature, values in zip(features, matrix, strict=False):
            writer.writerow([*feature, *[round(value, 6) for value in values]])


def _sample_totals(matrix: list[list[float]]) -> list[float]:
    if not matrix:
        return []
    sample_count = len(matrix[0])
    return [sum(row[index] for row in matrix) for index in range(sample_count)]


def _write_normalization_html(path: Path, meta: dict[str, Any]) -> None:
    steps = [
        ("Impute", meta["impute_method"], f"{meta['imputed_value_count']} values filled"),
        ("Normalize", meta["normalization_method"], "sample total signal aligned"),
        ("Transform", meta["transform"], "intensity scale compressed"),
        ("Scale", meta["scaling"], "features made comparable"),
    ]
    cards = "".join(
        f"<article><span>{index}</span><strong>{html.escape(title)}</strong><p>{html.escape(str(method))}</p><small>{html.escape(detail)}</small></article>"
        for index, (title, method, detail) in enumerate(steps, start=1)
    )
    payload = json.dumps(meta, ensure_ascii=False)
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Metabolomics normalization</title>
<style>
body{{margin:0;font-family:Inter,'Noto Sans SC',Arial,sans-serif;background:#f7fbfb;color:#07131f}}
.wrap{{padding:28px;max-width:1120px;margin:auto}}
h1{{margin:0 0 8px;font-size:30px}}p{{color:#52616b;line-height:1.6}}
.steps{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:22px 0}}
article{{padding:16px;border:1px solid #cfe0e3;border-radius:14px;background:white;box-shadow:0 10px 24px rgba(17,42,61,.08)}}
article span{{display:inline-flex;width:24px;height:24px;align-items:center;justify-content:center;border-radius:999px;background:#0f8a8f;color:white;font-weight:900;font-size:12px}}
article strong{{display:block;margin-top:10px;font-size:16px}}article p{{margin:5px 0;color:#0f6b57;font-weight:800}}article small{{color:#52616b}}
.metrics{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}
.metric{{padding:16px;border:1px solid #d8e5ee;border-radius:14px;background:#fff}}.metric span{{display:block;color:#52616b;font-size:12px}}.metric strong{{font-size:22px}}
#bars{{width:100%;height:220px;margin-top:18px;border:1px solid #d8e5ee;border-radius:14px;background:white}}
@media(max-width:860px){{.steps,.metrics{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap">
<h1>Metabolomics normalize / impute / scale</h1>
<p>This node prepares the QC-passed metabolomics matrix for downstream PCA, heatmaps, abundance plots, and differential metabolite analysis. It does not decide whether samples pass QC.</p>
<section class="steps">{cards}</section>
<section class="metrics">
<div class="metric"><span>Metabolites</span><strong>{meta['metabolite_count']}</strong></div>
<div class="metric"><span>Samples</span><strong>{meta['sample_count']}</strong></div>
<div class="metric"><span>Imputed values</span><strong>{meta['imputed_value_count']}</strong></div>
</section>
<canvas id="bars" width="1040" height="220"></canvas></div>
<script>
const meta = {payload};
const canvas = document.getElementById('bars');
const ctx = canvas.getContext('2d');
const beforeMin = Number(meta.sample_total_before_min || 0), beforeMax = Number(meta.sample_total_before_max || 0);
const afterMin = Number(meta.sample_total_after_min || 0), afterMax = Number(meta.sample_total_after_max || 0);
const values = [beforeMin, beforeMax, afterMin, afterMax];
const labels = ['Before min', 'Before max', 'After min', 'After max'];
const colors = ['#9bb8c6','#315fd6','#98d7c9','#0f8a8f'];
const max = Math.max(...values, 1);
ctx.clearRect(0,0,canvas.width,canvas.height);
ctx.font = '13px Inter, sans-serif';
ctx.fillStyle = '#52616b';
ctx.fillText('Sample total signal range before and after normalization', 28, 28);
values.forEach((value, index) => {{
  const x = 56 + index * 235;
  const h = Math.max(4, value / max * 128);
  ctx.fillStyle = colors[index];
  ctx.fillRect(x, 168 - h, 120, h);
  ctx.fillStyle = '#07131f';
  ctx.fillText(labels[index], x, 190);
  ctx.fillStyle = '#52616b';
  ctx.fillText(Number(value).toFixed(2), x, 207);
}});
</script></body></html>""",
        encoding="utf-8",
    )


def _write_normalization_preview(path: Path, meta: dict[str, Any]) -> None:
    steps = ["Impute", "Normalize", "Log", "Scale"]
    boxes = []
    for index, step in enumerate(steps):
        x = 16 + index * 50
        boxes.append(
            f'<rect x="{x}" y="42" width="42" height="28" rx="7" fill="#e8f7f4" stroke="#0f8a8f"/>'
            f'<text x="{x + 21}" y="59" text-anchor="middle" font-size="7" fill="#0d5860" font-weight="700">{step}</text>'
        )
        if index < len(steps) - 1:
            boxes.append(f'<path d="M{x + 43} 56 H{x + 50}" stroke="#52616b" stroke-width="1.5"/>')
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120" viewBox="0 0 220 120"><rect width="220" height="120" rx="14" fill="#f7fbfb"/><text x="12" y="18" font-size="11" fill="#17211b" font-weight="700">Normalize / impute / scale</text><text x="12" y="32" font-size="9" fill="#52616b">{int(meta["metabolite_count"])} metabolites / {int(meta["sample_count"])} samples</text>{"".join(boxes)}<text x="12" y="96" font-size="9" fill="#52616b">filled {int(meta["imputed_value_count"])} missing values</text></svg>',
        encoding="utf-8",
    )


def _condition_counts(sample_columns: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for column in sample_columns:
        counts[column.condition] = counts.get(column.condition, 0) + 1
    return counts


def _comparison_conditions(conditions: dict[str, int], params: dict[str, Any]) -> tuple[str, str]:
    requested_case = str(params.get("case_condition") or "").strip()
    requested_control = str(params.get("control_condition") or "").strip()
    if requested_case and requested_control:
        return requested_case, requested_control
    eligible = [condition for condition, count in sorted(conditions.items()) if count >= 2]
    if len(eligible) >= 2:
        return eligible[1], eligible[0]
    ordered = sorted(conditions, key=conditions.get, reverse=True)
    if len(ordered) >= 2:
        return ordered[0], ordered[1]
    only = ordered[0] if ordered else "condition"
    return only, only


def _read_diff_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as file:
        for raw in csv.DictReader(file):
            rows.append(
                {
                    "metabolite": raw.get("metabolite") or raw.get("feature_name") or raw.get("feature_id") or "",
                    "feature_id": raw.get("feature_id") or "",
                    "log2fc": _float(raw.get("log2fc")),
                    "p_value": _float(raw.get("p_value"), default=1.0),
                    "vip": _float(raw.get("vip"), default=0.0),
                }
            )
    rows.sort(key=lambda row: row["p_value"])
    return rows


def _metabolomics_univariate_method(params: dict[str, Any]) -> str:
    value = str(
        params.get("univariate_method")
        or params.get("statistical_test")
        or params.get("test_method")
        or params.get("method")
        or "t_test"
    ).strip().lower()
    if value in {"", "r_metabolomics", "r_metabolomics_univariate_pca_qc", "r_transcriptomics"}:
        return "t_test"
    if value in {"t", "ttest", "t-test", "t_test", "student", "welch", "welch_t"}:
        return "t_test"
    if value in {"wilcox", "wilcoxon", "wilcox-test", "wilcox_test", "mann_whitney", "mann-whitney"}:
        return "wilcox"
    raise ValueError("Metabolomics univariate method must be t_test or wilcox")


def _float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _safe_slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_") or "metabolomics"
