from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


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


def test_node_report_explains_feature_importance_terms_without_llm(tmp_path: Path) -> None:
    importance_file = tmp_path / "feature_importance.csv"
    importance_file.write_text(
        "model,feature,importance,explainability_method\n"
        "naive_bayes,creatine,1.0,shap_naive_bayes_approximation\n"
        "naive_bayes,citrate,0.74,shap_naive_bayes_approximation\n",
        encoding="utf-8",
    )

    report = create_node_agent_report(
        node_id="metabolomics_explain__shap",
        node_name="SHAP summary plot",
        node_description="Explain the trained classifier.",
        output=DataObject(
            type="metabolomics_ml_explainability_result",
            data="shap_output.json",
            meta={
                "data_type": "metabolomics_matrix",
                "source_model": "naive_bayes",
                "explainability_method": "shap_naive_bayes_approximation",
                "top_feature": "creatine",
                "feature_importance_file": str(importance_file),
            },
        ),
        params={"explainability_method": "shap"},
        inputs={},
        use_llm=False,
    )

    assert report["evidence"]["result_context"]["feature_importance_table"][0]["feature"] == "creatine"
    assert "feature 指模型输入变量" in " ".join(report["findings"])
    assert "creatine" in " ".join(report["findings"])
    assert "feature_importance_table" in report["llm_prompt"]["user"]


def test_node_report_uses_llm_prompt_with_current_results(monkeypatch: Any, tmp_path: Path) -> None:
    importance_file = tmp_path / "feature_importance.csv"
    importance_file.write_text(
        "model,feature,importance,explainability_method\n"
        "random_forest,creatine,0.91,rf_feature_importance\n",
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}

    class _FakeResponse:
        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "summary": "LLM 根据当前 feature importance 表总结：creatine 排名靠前。",
                                        "findings": ["feature 在这里指代谢物输入变量。"],
                                        "methods": ["使用 RF importance 解释 random_forest。"],
                                        "warnings": ["importance 不是因果结论。"],
                                        "next_steps": ["回到单代谢物丰度图复核 creatine。"],
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                },
                ensure_ascii=False,
            ).encode("utf-8")

    def fake_urlopen(request: Any, timeout: int) -> _FakeResponse:
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("DEEPSEEK_REPORT_MODEL", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    report = create_node_agent_report(
        node_id="metabolomics_explain__rf_importance",
        node_name="RF importance",
        node_description="Explain the trained classifier.",
        output=DataObject(
            type="metabolomics_ml_explainability_result",
            data="rf_output.json",
            meta={
                "data_type": "metabolomics_matrix",
                "source_model": "random_forest",
                "explainability_method": "rf_feature_importance",
                "top_feature": "creatine",
                "feature_importance_file": str(importance_file),
            },
        ),
        params={},
        inputs={},
        use_llm=True,
    )

    user_prompt = captured["payload"]["messages"][1]["content"]
    assert report["generated_by"] == "llm"
    assert report["model"] == "deepseek-v4-flash"
    assert "feature_importance_table" in user_prompt
    assert "creatine" in user_prompt
    assert "feature 在这里指代谢物输入变量" in report["findings"][0]
