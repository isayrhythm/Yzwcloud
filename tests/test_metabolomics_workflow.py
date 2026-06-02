from __future__ import annotations

import csv
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yzwcloud.analyses.metabolomics import (  # noqa: E402
    create_metabolomics_differential_result,
    create_metabolomics_normalization_result,
    create_metabolomics_statistics_result,
)
from yzwcloud.analyses.expression import create_qc_result  # noqa: E402
from yzwcloud.data_intake_agent import run_data_intake_agent  # noqa: E402


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
    for key in ["metabolomics_result_file", "qc_file", "pca_scores_file", "sample_correlation_file"]:
        assert Path(result.meta[key]).exists()

    with Path(result.meta["metabolomics_result_file"]).open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert rows
    assert {"feature_id", "metabolite", "log2fc", "p_value"}.issubset(rows[0])


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
