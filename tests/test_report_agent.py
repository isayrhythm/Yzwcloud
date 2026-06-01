from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yzwcloud.models import DataObject  # noqa: E402
from yzwcloud.report_agent import attach_node_agent_report, create_node_agent_report  # noqa: E402


def test_node_report_falls_back_to_structured_pca_summary_without_llm() -> None:
    report = create_node_agent_report(
        node_id="pca__expression",
        node_name="PCA sample map",
        node_description="Inspect sample-level structure.",
        output=DataObject(
            type="pca_plot",
            data="pca_output.json",
            meta={
                "sample_count": 8,
                "gene_count": 1200,
                "explained_variance": {"pc1": 41.5, "pc2": 18.25},
                "method": "sample_covariance_power_iteration",
            },
        ),
        params={},
        inputs={},
        use_llm=False,
    )

    assert report["generated_by"] == "rule_based_fallback"
    assert report["llm_status"] == "disabled"
    assert "PCA" in report["summary"]
    assert "59.75%" in report["findings"][1]
    assert any("不等同于差异显著性检验" in item for item in report["warnings"])


def test_attach_node_report_writes_json_html_and_updates_output(tmp_path: Path) -> None:
    output_path = tmp_path / "volcano_output.json"
    output = DataObject(
        type="volcano_plot",
        data=str(output_path),
        meta={"point_count": 320, "comparison_label": "case vs control"},
    )
    output_path.write_text(output.model_dump_json(indent=2), encoding="utf-8")

    attached = attach_node_agent_report(
        node_id="volcano__case_vs_control",
        node_name="Volcano plot",
        node_description="Plot fold-change and significance.",
        output=output,
        params={"p_value": 0.05, "log2fc": 1.0},
        inputs={},
        output_dir=tmp_path,
        use_llm=False,
    )

    report = attached.meta["agent_report"]
    json_path = Path(attached.meta["agent_report_file"])
    html_path = Path(attached.meta["agent_report_html_file"])
    persisted = json.loads(output_path.read_text(encoding="utf-8"))

    assert json_path.exists()
    assert html_path.exists()
    assert "Agent 总结" in html_path.read_text(encoding="utf-8")
    assert report["output_type"] == "volcano_plot"
    assert report["generated_by"] == "rule_based_fallback"
    assert persisted["meta"]["agent_report"]["node_id"] == "volcano__case_vs_control"
