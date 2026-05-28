from __future__ import annotations

import csv
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yzwcloud.analyses.metabolomics import create_metabolomics_statistics_result  # noqa: E402
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
    assert result.meta["metabolite_count"] == 3
    assert result.meta["sample_count"] == 4
    assert "metabolomics_statistics" in result.meta["capabilities"]
    assert Path(result.meta["matrix_file"]).exists()
    assert Path(result.meta["sample_metadata_file"]).exists()


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
