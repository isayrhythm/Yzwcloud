from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yzwcloud.analyses.metabolomics import (  # noqa: E402
    create_metabolomics_differential_result,
    create_metabolomics_ml_classification_result,
    create_metabolomics_ml_explainability_result,
    create_metabolomics_normalization_result,
    create_metabolomics_statistics_result,
)
from yzwcloud.analyses.differential import create_volcano_result  # noqa: E402
from yzwcloud.analyses.expression import create_gene_expression_result, create_qc_result  # noqa: E402
from yzwcloud.data_intake_agent import run_data_intake_agent  # noqa: E402
from yzwcloud.models import DataObject, GraphNode, NodeStatus  # noqa: E402
from yzwcloud.node_registry import execute_demo_node  # noqa: E402
from yzwcloud.task_store import create_analysis_node, create_task, delete_task, load_graph, save_graph  # noqa: E402


def _write_metabolights_fixture(tmp_path: Path) -> tuple[Path, Path]:
    maf = tmp_path / "m_demo_metabolite_profiling_maf.tsv"
    sample = tmp_path / "s_demo.txt"
    header = [
        "database_identifier",
        "chemical_formula",
        "smiles",
        "inchi",
        "metabolite_identification",
        "chemical_shift",
        "multiplicity",
        "taxid",
        "species",
        "database",
        "database_version",
        "reliability",
        "uri",
        "search_engine",
        "search_engine_score",
        "smallmolecule_abundance_sub",
        "smallmolecule_abundance_stdev_sub",
        "smallmolecule_abundance_std_error_sub",
        "S1",
        "S2",
        "S3",
        "S4",
    ]
    rows = [
        ["HMDB00001", "C1", "", "", "met_a", "1.0", "", "", "", "HMDB", "", "", "", "", "", "", "", "", "10", "12", "2", "3"],
        ["HMDB00002", "C2", "", "", "met_b", "2.0", "", "", "", "HMDB", "", "", "", "", "", "", "", "", "1", "2", "8", "9"],
        ["", "C3", "", "", "met_c", "3.0", "", "", "", "HMDB", "", "", "", "", "", "", "", "", "5", "", "6", "7"],
    ]
    with maf.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, delimiter="\t")
        writer.writerow(header)
        writer.writerows(rows)

    sample.write_text(
        "\n".join(
            [
                "Sample Name\tFactor Value[Metabolic syndrome]\tFactor Value[Gender]",
                "S1\tcase\tfemale",
                "S2\tcase\tfemale",
                "S3\tcontrol\tmale",
                "S4\tcontrol\tmale",
            ]
        ),
        encoding="utf-8",
    )
    return maf, sample


def _write_large_metabolomics_fixture(tmp_path: Path, sample_count: int = 120) -> DataObject:
    matrix = tmp_path / "large_metabolomics_matrix.csv"
    metadata = tmp_path / "large_sample_metadata.csv"
    samples = [f"S{i + 1:03d}" for i in range(sample_count)]
    with metadata.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["sample", "group", "condition"])
        writer.writeheader()
        for index, sample in enumerate(samples):
            condition = "case" if index < sample_count // 2 else "control"
            writer.writerow({"sample": sample, "group": condition, "condition": condition})
    with matrix.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["gene_short_name", "gene_id", "description", "module", "chromosome", "gene_type", *samples])
        for feature_index in range(30):
            values = []
            for sample_index in range(sample_count):
                is_case = sample_index < sample_count // 2
                signal = 2.5 if feature_index < 5 and is_case else 0.0
                signal += -2.0 if 5 <= feature_index < 10 and is_case else 0.0
                values.append(round(signal + (sample_index % 7) * 0.03 + feature_index * 0.01, 4))
            writer.writerow([f"met_{feature_index + 1}", f"HMDB{feature_index + 1:05d}", "", "", "", "", *values])
    return DataObject(
        type="expression_matrix",
        data=str(matrix),
        meta={
            "data_type": "metabolomics_matrix",
            "matrix_file": str(matrix),
            "sample_metadata_file": str(metadata),
            "sample_count": sample_count,
            "metabolite_count": 30,
            "conditions": {"case": sample_count // 2, "control": sample_count // 2},
        },
    )


def test_metabolomics_intake_standardizes_metabolights_maf(tmp_path: Path) -> None:
    maf, sample = _write_metabolights_fixture(tmp_path)

    result = run_data_intake_agent(
        source_path=maf,
        metadata_path=sample,
        output_dir=tmp_path / "outputs",
        params={"use_llm": False},
    )

    assert result.type == "expression_matrix"
    assert result.meta["data_type"] == "metabolomics_matrix"
    assert result.meta["assay_profile"] == "metabolomics"
    assert result.meta["feature_label"] == "metabolites"
    assert result.meta["metabolite_count"] == 3
    assert result.meta["sample_count"] == 4
    assert "metabolomics_normalization" in result.meta["capabilities"]
    assert "metabolomics_differential" in result.meta["capabilities"]
    assert Path(result.meta["matrix_file"]).exists()
    assert Path(result.meta["sample_metadata_file"]).exists()


def test_metabolomics_single_metabolite_abundance_uses_english_violin_plot(tmp_path: Path) -> None:
    source = _write_large_metabolomics_fixture(tmp_path)

    result = create_gene_expression_result(
        source=source,
        params={"gene": "met_1"},
        output_dir=tmp_path / "abundance",
        node_id="gene_expression__expression",
    )

    html_text = Path(result.meta["html_file"]).read_text(encoding="utf-8")
    preview_text = Path(result.meta["preview_file"]).read_text(encoding="utf-8")

    assert result.type == "gene_expression_plot"
    assert result.meta["feature_label"] == "metabolite"
    assert "Single metabolite abundance" in html_text
    assert "单基因表达" not in html_text
    assert "type: 'violin'" in html_text
    assert "type: 'box'" not in html_text
    assert "violinmode: 'group'" in html_text
    assert "Abundance violin plot" in preview_text


def test_metabolomics_single_metabolite_abundance_node_name_is_english(tmp_path: Path) -> None:
    source = _write_large_metabolomics_fixture(tmp_path)
    task, graph = create_task("metabolomics-abundance-node-test")
    try:
        upload_node = next(node for node in graph.nodes if node.id == "upload_expression")
        upload_node.status = NodeStatus.COMPLETED
        upload_node.output = source
        qc_node = GraphNode(
            id="qc__expression",
            name="Metabolomics QC",
            description="Synthetic completed QC node.",
            status=NodeStatus.COMPLETED,
            input_types=["expression_matrix"],
            output_type="qc_report",
            depends_on=["upload_expression"],
            output=DataObject(
                type="qc_report",
                data="qc.json",
                meta={
                    **source.meta,
                    "passed_sample_count": 120,
                    "normalization_applied": True,
                },
            ),
        )
        graph.nodes.append(qc_node)
        graph.edges.append({"source": "upload_expression", "target": "qc__expression"})
        save_graph(graph)

        _, updated = create_analysis_node(task.task_id, "qc__expression", "gene_expression")
        node = next(item for item in updated.nodes if item.id.startswith("gene_expression__"))

        assert node.name == "Single metabolite abundance"
        assert node.description == "View one metabolite abundance distribution across sample groups."
    finally:
        delete_task(task.task_id)


def test_metabolomics_volcano_plot_colors_and_labels_significant_features(tmp_path: Path) -> None:
    diff_file = tmp_path / "metabolomics_diff.csv"
    diff_file.write_text(
        "\n".join(
            [
                "feature_id,metabolite,log2fc,p_value,neg_log10_p",
                "M001,high_up,2.4,0.0001,4",
                "M002,high_down,-2.1,0.0002,3.7",
                "M003,flat,0.2,0.8,0.125",
            ]
        ),
        encoding="utf-8",
    )
    diff = DataObject(
        type="metabolomics_differential_result",
        data=str(diff_file),
        meta={
            "diff_result_file": str(diff_file),
            "comparison_label": "case vs control",
            "p_value_threshold": 0.05,
            "log2fc_threshold": 1.0,
        },
    )

    result = create_volcano_result(diff=diff, output_dir=tmp_path / "volcano", node_id="volcano__case_vs_control")

    html_text = Path(result.meta["html_file"]).read_text(encoding="utf-8")
    preview_text = Path(result.meta["preview_file"]).read_text(encoding="utf-8")
    assert result.type == "volcano_plot"
    assert result.meta["up_count"] == 1
    assert result.meta["down_count"] == 1
    assert "Volcano plot: case vs control" in html_text
    assert "Colored by p-value significant direction" in html_text
    assert '"group": "Up"' in html_text
    assert '"group": "Down"' in html_text
    assert '"group": "Not significant"' in html_text
    assert '"strong": true' in html_text
    assert "#c44f3a" in html_text
    assert "#315fd6" in html_text
    assert "Top 3 hits are labeled" in html_text
    assert "Volcano plot" in preview_text


def test_metabolomics_intake_accepts_gb18030_feature_matrix(tmp_path: Path) -> None:
    source_path = ROOT / "testdata" / "WT_B.csv"

    result = run_data_intake_agent(
        source_path=source_path,
        output_dir=tmp_path / "outputs",
        params={"use_llm": False},
    )

    assert result.meta["data_type"] == "metabolomics_matrix"
    assert result.meta["assay_profile"] == "feature_intensity"
    assert result.meta["feature_label"] == "features"
    assert result.meta["sample_count"] == 6
    assert result.meta["metabolite_count"] > 0
    assert result.meta["conditions"] == {"WT": 3, "B": 3}
    assert result.meta["standardization"]["source_encoding"] == "gb18030"
    assert "metabolomics_differential" in result.meta["capabilities"]


def test_metabolomics_intake_accepts_wide_feature_matrix(tmp_path: Path) -> None:
    source_path = ROOT / "testdata" / "meta_Anth_content.csv"

    result = run_data_intake_agent(
        source_path=source_path,
        output_dir=tmp_path / "outputs",
        params={"use_llm": False},
    )

    assert result.meta["data_type"] == "metabolomics_matrix"
    assert result.meta["assay_profile"] == "feature_intensity"
    assert result.meta["feature_label"] == "features"
    assert result.meta["sample_count"] >= 6
    assert result.meta["metabolite_count"] > 0
    assert "metabolomics_normalization" in result.meta["capabilities"]


def test_intake_detects_comma_delimited_protein_group_tsv(tmp_path: Path) -> None:
    source_path = ROOT / "testdata" / "Leaf.report.pg_matrix.tsv"

    result = run_data_intake_agent(
        source_path=source_path,
        output_dir=tmp_path / "outputs",
        params={"use_llm": False},
    )

    assert result.meta["data_type"] == "metabolomics_matrix"
    assert result.meta["assay_profile"] == "protein"
    assert result.meta["feature_label"] == "proteins"
    assert result.meta["sample_count"] == 6
    assert 12000 <= result.meta["metabolite_count"] <= 13286
    assert result.meta["conditions"] == {"MT": 3, "WT": 3}
    assert result.meta["standardization"]["mode"] == "protein_group_matrix"
    assert result.meta["standardization"]["source_encoding"] == "utf-8-sig"
    assert result.meta["standardization"]["selected_sample_count"] == 6
    assert "metabolomics_differential" in result.meta["capabilities"]


def test_metabolomics_statistics_runs_r_outputs_tables(tmp_path: Path) -> None:
    maf, sample = _write_metabolights_fixture(tmp_path)
    source = run_data_intake_agent(
        source_path=maf,
        metadata_path=sample,
        output_dir=tmp_path / "intake",
        params={"use_llm": False},
    )

    result = create_metabolomics_statistics_result(
        source=source,
        output_dir=tmp_path / "stats",
        node_id="metabolomics_statistics__matrix",
        params={"case_condition": "case", "control_condition": "control"},
    )

    assert result.type == "metabolomics_statistics_result"
    assert result.meta["metabolite_count"] == 3
    assert result.meta["comparison_label"] == "case vs control"
    for key in [
        "metabolomics_result_file",
        "qc_file",
        "pca_scores_file",
        "plsda_scores_file",
        "vip_file",
        "sample_correlation_file",
    ]:
        assert Path(result.meta[key]).exists()

    with Path(result.meta["metabolomics_result_file"]).open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert rows
    assert {"feature_id", "metabolite", "log2fc", "p_value", "t_p_value", "wilcox_p_value", "vip", "vip_gt_1"}.issubset(rows[0])
    assert result.meta["univariate_method"] == "t_test"
    assert result.meta["vip_threshold"] == 1.0
    assert result.meta["vip_available"] is True


def test_metabolomics_statistics_can_use_wilcox_as_primary_p_value(tmp_path: Path) -> None:
    maf, sample = _write_metabolights_fixture(tmp_path)
    source = run_data_intake_agent(
        source_path=maf,
        metadata_path=sample,
        output_dir=tmp_path / "intake",
        params={"use_llm": False},
    )

    result = create_metabolomics_statistics_result(
        source=source,
        output_dir=tmp_path / "stats",
        node_id="metabolomics_statistics__matrix",
        params={"case_condition": "case", "control_condition": "control", "univariate_method": "wilcox"},
    )

    assert result.meta["univariate_method"] == "wilcox"
    with Path(result.meta["metabolomics_result_file"]).open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert rows
    assert rows[0]["p_value"] == rows[0]["wilcox_p_value"]


def test_metabolomics_differential_result_has_focused_output_type(tmp_path: Path) -> None:
    maf, sample = _write_metabolights_fixture(tmp_path)
    source = run_data_intake_agent(
        source_path=maf,
        metadata_path=sample,
        output_dir=tmp_path / "intake",
        params={"use_llm": False},
    )

    result = create_metabolomics_differential_result(
        source=source,
        output_dir=tmp_path / "diff",
        node_id="metabolomics_differential__matrix",
        params={"case_condition": "case", "control_condition": "control"},
    )

    assert result.type == "metabolomics_differential_result"
    assert result.meta["analysis_family"] == "metabolomics_differential"
    assert result.meta["comparison_label"] == "case vs control"
    assert Path(result.meta["diff_result_file"]).exists()


def test_metabolomics_normalization_outputs_scaled_and_differential_matrices(tmp_path: Path) -> None:
    maf, sample = _write_metabolights_fixture(tmp_path)
    source = run_data_intake_agent(
        source_path=maf,
        metadata_path=sample,
        output_dir=tmp_path / "intake",
        params={"use_llm": False},
    )

    result = create_metabolomics_normalization_result(
        source=source,
        output_dir=tmp_path / "normalize",
        node_id="metabolomics_normalization__matrix",
        params={"impute_method": "half_min", "normalization_method": "tic_median", "transform": "log2", "scaling": "pareto"},
    )

    assert result.type == "expression_matrix"
    assert result.meta["analysis_family"] == "metabolomics_normalization"
    assert result.meta["data_type"] == "metabolomics_matrix"
    assert result.meta["metabolite_count"] == 3
    assert Path(result.meta["matrix_file"]).exists()
    assert Path(result.meta["differential_matrix_file"]).exists()


@pytest.mark.parametrize(
    ("model", "node_id"),
    [
        ("svm", "metabolomics_ml__svm"),
        ("naive_bayes", "metabolomics_ml__naive_bayes"),
        ("random_forest", "metabolomics_ml__random_forest"),
    ],
)
def test_metabolomics_ml_classification_outputs_one_selected_model(
    tmp_path: Path, model: str, node_id: str
) -> None:
    source = _write_large_metabolomics_fixture(tmp_path)

    result = create_metabolomics_ml_classification_result(
        source=source,
        output_dir=tmp_path / model,
        node_id=node_id,
        params={"model": model, "min_samples": 100, "max_features": 20, "n_estimators": 30},
    )

    assert result.type == "metabolomics_ml_result"
    assert result.meta["analysis_family"] == "metabolomics_ml_classification"
    assert result.meta["sample_count"] == 120
    assert result.meta["models"] == [model]
    assert result.meta["selected_model"] == model
    assert "shap" in result.meta["available_explainability"]
    assert "permutation" in result.meta["available_explainability"]
    if model == "random_forest":
        assert "rf_importance" in result.meta["available_explainability"]
    else:
        assert "rf_importance" not in result.meta["available_explainability"]
    assert Path(result.meta["html_file"]).exists()
    assert Path(result.meta["preview_file"]).exists()
    assert Path(result.meta["metrics_file"]).exists()
    with Path(result.meta["metrics_file"]).open(encoding="utf-8-sig", newline="") as file:
        metrics = list(csv.DictReader(file))
    assert [row["model"] for row in metrics] == [model]
    assert metrics[0]["explainability_method"] == "created_by_downstream_node"


def test_metabolomics_random_forest_explainability_outputs_feature_importance(tmp_path: Path) -> None:
    source = _write_large_metabolomics_fixture(tmp_path)

    result = create_metabolomics_ml_classification_result(
        source=source,
        output_dir=tmp_path / "ml",
        node_id="metabolomics_ml__random_forest",
        params={"model": "random_forest", "min_samples": 100, "max_features": 20, "n_estimators": 30},
    )

    explain = create_metabolomics_ml_explainability_result(
        source=result,
        output_dir=tmp_path / "ml",
        node_id="metabolomics_explain__rf_importance",
        params={"explainability_method": "rf_importance", "n_estimators": 30},
    )

    assert explain.type == "metabolomics_ml_explainability_result"
    assert explain.meta["source_model"] == "random_forest"
    assert explain.meta["explainability_method"] == "rf_feature_importance"
    assert Path(explain.meta["feature_importance_file"]).exists()
    with Path(explain.meta["feature_importance_file"]).open(encoding="utf-8-sig", newline="") as file:
        importance = list(csv.DictReader(file))
    assert importance
    assert {"model", "feature", "importance", "explainability_method"}.issubset(importance[0])


def test_metabolomics_shap_explainability_outputs_report_ready_summary_plot(tmp_path: Path) -> None:
    source = _write_large_metabolomics_fixture(tmp_path)

    result = create_metabolomics_ml_classification_result(
        source=source,
        output_dir=tmp_path / "ml",
        node_id="metabolomics_ml__random_forest",
        params={"model": "random_forest", "min_samples": 100, "max_features": 14, "n_estimators": 20},
    )

    explain = create_metabolomics_ml_explainability_result(
        source=result,
        output_dir=tmp_path / "ml",
        node_id="metabolomics_explain__shap",
        params={"explainability_method": "shap", "n_estimators": 20},
    )

    html_text = Path(explain.meta["html_file"]).read_text(encoding="utf-8")
    preview_text = Path(explain.meta["preview_file"]).read_text(encoding="utf-8")

    assert explain.meta["requested_explainability"] == "shap"
    assert Path(explain.meta["shap_values_file"]).exists()
    assert "SHAP summary plot" in html_text
    assert "Top features ranked by mean absolute SHAP value" in html_text
    assert "SHAP value (impact on model output)" in html_text
    assert "negative impact" in html_text
    assert "positive impact" in html_text
    assert "shapLegend" in html_text
    assert "Feature importance" in preview_text
    assert "previewBg" in preview_text


def test_metabolomics_ml_modeling_gateway_outputs_empty_modeling_plan(tmp_path: Path) -> None:
    source = _write_large_metabolomics_fixture(tmp_path)

    result = execute_demo_node(
        node_id="metabolomics_ml_modeling__classification",
        inputs={"metabolomics_normalization__matrix": source, "upload_expression": source},
        params={
            "analysis_family": "metabolomics_ml_modeling",
            "min_samples": 100,
            "task_type": "classification",
            "available_models": ["svm", "naive_bayes", "random_forest"],
        },
        output_dir=tmp_path / "modeling",
    )

    assert result.type == "planned_analysis"
    assert result.meta["analysis_family"] == "metabolomics_ml_modeling"
    assert "matrix_file" not in result.meta
    assert "sample_metadata_file" not in result.meta
    assert "normalization_method" not in result.meta
    assert result.meta["sample_count"] == 120
    assert result.meta["feature_count"] == 30
    assert result.meta["available_models"] == ["svm", "naive_bayes", "random_forest"]


def test_metabolomics_model_node_trains_from_normalized_dependency_after_empty_gateway(tmp_path: Path) -> None:
    source = _write_large_metabolomics_fixture(tmp_path)
    gateway = DataObject(
        type="planned_analysis",
        data="metabolomics_ml_modeling.json",
        meta={
            "analysis_family": "metabolomics_ml_modeling",
            "sample_count": 120,
            "min_samples": 100,
            "available_models": ["svm", "naive_bayes", "random_forest"],
        },
    )

    result = execute_demo_node(
        node_id="metabolomics_ml__svm",
        inputs={
            "metabolomics_ml_modeling__classification": gateway,
            "metabolomics_normalization__matrix": source,
            "upload_expression": source,
        },
        params={"model": "svm", "min_samples": 100, "max_features": 20},
        output_dir=tmp_path / "ml_after_gateway",
    )

    assert result.type == "metabolomics_ml_result"
    assert result.meta["selected_model"] == "svm"
    assert result.meta["matrix_file"] == source.meta["matrix_file"]
    assert result.meta["sample_count"] == 120


def test_metabolomics_ml_models_can_only_be_created_after_modeling_gateway(tmp_path: Path) -> None:
    source = _write_large_metabolomics_fixture(tmp_path)
    task, graph = create_task("metabolomics-ml-node-test")
    try:
        upload_node = next(node for node in graph.nodes if node.id == "upload_expression")
        upload_node.status = NodeStatus.COMPLETED
        upload_node.output = source
        qc_node = GraphNode(
            id="qc__expression",
            name="Metabolomics QC",
            description="Synthetic completed QC node.",
            status=NodeStatus.COMPLETED,
            input_types=["expression_matrix"],
            output_type="qc_report",
            depends_on=["upload_expression"],
            output=DataObject(
                type="qc_report",
                data="qc.json",
                meta={
                    **source.meta,
                    "passed_sample_count": 120,
                    "normalization_applied": True,
                },
            ),
        )
        graph.nodes.append(qc_node)
        graph.edges.append({"source": "upload_expression", "target": "qc__expression"})
        normalized_node = GraphNode(
            id="metabolomics_normalization__matrix",
            name="Metabolomics normalize / impute / scale",
            description="Synthetic completed normalization node.",
            status=NodeStatus.COMPLETED,
            input_types=["qc_report", "expression_matrix"],
            output_type="expression_matrix",
            depends_on=["qc__expression", "upload_expression"],
            output=DataObject(
                type="expression_matrix",
                data=source.data,
                meta={
                    **source.meta,
                    "analysis_family": "metabolomics_normalization",
                    "sample_count": 120,
                    "normalization_applied": True,
                },
            ),
        )
        graph.nodes.append(normalized_node)
        graph.edges.append({"source": "qc__expression", "target": "metabolomics_normalization__matrix"})
        save_graph(graph)

        with pytest.raises(ValueError):
            create_analysis_node(task.task_id, "qc__expression", "metabolomics_ml_svm")

        with pytest.raises(ValueError):
            create_analysis_node(task.task_id, "metabolomics_normalization__matrix", "metabolomics_ml_svm")

        create_analysis_node(task.task_id, "metabolomics_normalization__matrix", "metabolomics_ml_modeling")

        updated = load_graph(task.task_id)
        modeling_node = next(node for node in updated.nodes if node.id.startswith("metabolomics_ml_modeling__"))
        assert modeling_node.output_type == "planned_analysis"
        assert modeling_node.params["min_samples"] == 100
        assert modeling_node.params["task_type"] == "classification"
        assert modeling_node.depends_on == ["metabolomics_normalization__matrix", "upload_expression"]

        modeling_node.status = NodeStatus.COMPLETED
        modeling_node.output = DataObject(
            type="planned_analysis",
            data="metabolomics_ml_modeling.json",
            meta={
                **source.meta,
                "analysis_family": "metabolomics_ml_modeling",
                "sample_count": 120,
                "min_samples": 100,
            },
        )
        save_graph(updated)

        create_analysis_node(task.task_id, modeling_node.id, "metabolomics_ml_svm")

        updated = load_graph(task.task_id)
        ml_node = next(node for node in updated.nodes if node.id.startswith("metabolomics_ml__"))
        assert ml_node.output_type == "metabolomics_ml_result"
        assert ml_node.params["min_samples"] == 100
        assert ml_node.params["model"] == "svm"
        assert ml_node.params["task_type"] == "classification"
        assert ml_node.input_types == ["planned_analysis", "expression_matrix"]
        assert ml_node.depends_on == [modeling_node.id, "metabolomics_normalization__matrix", "upload_expression"]
    finally:
        delete_task(task.task_id)


def test_metabolomics_qc_uses_feature_scaled_thresholds(tmp_path: Path) -> None:
    maf, sample = _write_metabolights_fixture(tmp_path)
    source = run_data_intake_agent(
        source_path=maf,
        metadata_path=sample,
        output_dir=tmp_path / "intake",
        params={"use_llm": False},
    )

    result = create_qc_result(
        source=source,
        output_dir=tmp_path / "qc",
        node_id="qc__expression",
        params={
            "qc_preset": "loose",
            "min_total_ratio": 0.15,
            "max_zero_ratio": 0.7,
            "min_detected_genes": 500,
            "max_distribution_mad": 5,
            "max_value_iqr_multiplier": 3,
            "normalize_after_qc": True,
            "impute_method": "half_min",
            "normalization_method": "tic_median",
            "transform": "log2",
            "scaling": "pareto",
        },
    )

    assert result.type == "qc_report"
    assert result.meta["params"]["qc_profile"] == "metabolomics"
    assert result.meta["normalization_applied"] is True
    assert result.meta["impute_method"] == "half_min"
    assert result.meta["normalization_method"] == "tic_median"
    assert Path(result.meta["differential_matrix_file"]).exists()
    assert Path(result.meta["normalization_html_file"]).exists()
    assert Path(result.meta["normalization_preview_file"]).exists()
    assert result.meta["params"]["min_detected_features"] <= result.meta["params"]["min_detected_genes"] <= source.meta["metabolite_count"]
    assert result.meta["passed_sample_count"] == result.meta["sample_count"]
