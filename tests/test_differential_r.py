from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yzwcloud.analyses import differential  # noqa: E402
from yzwcloud.models import DataObject  # noqa: E402


def _write_demo_inputs(tmp_path: Path) -> tuple[Path, Path, DataObject]:
    matrix = tmp_path / "matrix.csv"
    metadata = tmp_path / "metadata.csv"
    matrix.write_text(
        "\n".join(
            [
                "gene_short_name,gene_id,biotype,strand,locus,Length,S1,S2,S3,S4",
                "GENE_A,ENSGA,protein_coding,+,chr1:1-10,10,10,12,2,3",
                "GENE_B,ENSGB,protein_coding,+,chr1:11-20,10,3,4,9,11",
            ]
        ),
        encoding="utf-8",
    )
    metadata.write_text(
        "\n".join(
            [
                "sample,group,condition",
                "S1,A,case",
                "S2,A,case",
                "S3,B,control",
                "S4,B,control",
            ]
        ),
        encoding="utf-8",
    )
    source = DataObject(
        type="expression_matrix",
        data=str(matrix),
        meta={"matrix_file": str(matrix), "sample_metadata_file": str(metadata)},
    )
    return matrix, metadata, source


def test_differential_analysis_calls_transcriptomics_r(monkeypatch: Any, tmp_path: Path) -> None:
    _, _, source = _write_demo_inputs(tmp_path)
    calls: list[Path] = []

    def fake_run_r_script(script_path: Path, args: list[str], **_: Any) -> None:
        calls.append(script_path)
        output_dir = Path(args[3])
        output_dir.joinpath("case_vs_control_all_genes.csv").write_text(
            "\n".join(
                [
                    "gene_id,feature_name,baseMean,log2FoldChange,pvalue,padj",
                    "ENSGA,GENE_A,6.75,3.2,0.001,0.002",
                    "ENSGB,GENE_B,6.75,-2.1,0.02,0.03",
                ]
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(differential, "run_r_script", fake_run_r_script)

    result = differential.run_differential_analysis(
        source=source,
        params={"case_condition": "case", "control_condition": "control", "method": "r_transcriptomics"},
        output_dir=tmp_path,
        node_id="diff_analysis__case_vs_control",
    )

    assert calls and calls[0].name == "differential_transcriptomics.R"
    assert result.meta["method"] == "r_transcriptomics_differential"
    assert result.meta["diff_gene_count"] == 2

    with Path(result.meta["diff_result_file"]).open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert rows[0]["gene"] == "GENE_A"
    assert rows[0]["gene_id"] == "ENSGA"
    assert rows[0]["log2fc"] == "3.2"
    assert float(rows[0]["case_mean"]) == 11.0
    assert float(rows[0]["control_mean"]) == 2.5


def test_differential_analysis_calls_protein_r(monkeypatch: Any, tmp_path: Path) -> None:
    _, _, source = _write_demo_inputs(tmp_path)
    calls: list[tuple[Path, list[str]]] = []

    def fake_run_r_script(script_path: Path, args: list[str], **_: Any) -> None:
        calls.append((script_path, args))
        output_dir = Path(args[3])
        output_dir.joinpath("case_vs_control_all_results.csv").write_text(
            "\n".join(
                [
                    "feature_id,feature_name,mean_numerator,mean_denominator,fold_change,log2_fc,pvalue,padj",
                    "ENSGA,GENE_A,11,2.5,4.4,2.1375,0.004,0.008",
                ]
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(differential, "run_r_script", fake_run_r_script)

    result = differential.run_differential_analysis(
        source=source,
        params={"case_condition": "case", "control_condition": "control", "method": "r_protein"},
        output_dir=tmp_path,
        node_id="diff_analysis__case_vs_control",
    )

    assert calls and calls[0][0].name == "differential_protein.R"
    assert calls[0][1][-1] == "2.0"
    assert result.meta["method"] == "r_protein_ttest"
    assert result.meta["tested_gene_count"] == 1
