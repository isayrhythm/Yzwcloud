from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yzwcloud.main import app  # noqa: E402
from yzwcloud.plot_studio import inspect_table, recommend_plot_types  # noqa: E402


DATA_FILE = ROOT / "expression_matrix.csv"


def _request(client: TestClient, method: str, path: str, **kwargs: Any) -> Any:
    response = client.request(method, path, **kwargs)
    assert response.status_code < 400, f"{method} {path} failed: {response.status_code} {response.text}"
    return response.json()


def test_plot_studio_presets_expose_prism_like_defaults() -> None:
    client = TestClient(app)

    manifest = _request(client, "GET", "/api/plot-studio/presets")

    assert manifest["version"] == "0.1"
    assert {"plotly", "echarts"} <= set(manifest["engines"])
    presets = {item["id"]: item for item in manifest["presets"]}
    assert {"boxplot", "heatmap", "volcano", "correlation"} <= set(presets)

    boxplot = presets["boxplot"]
    assert boxplot["engine"] == "plotly"
    assert boxplot["default_params"]["show_points"] is True
    assert any(group["id"] == "statistics" for group in boxplot["parameter_groups"])
    assert any(group["id"] == "export" for group in boxplot["parameter_groups"])

    heatmap = presets["heatmap"]
    assert heatmap["default_params"]["show_dendrogram"] is True
    clustering_group = next(group for group in heatmap["parameter_groups"] if group["id"] == "clustering")
    top_n = next(param for param in clustering_group["parameters"] if param["id"] == "top_n")
    assert top_n["step"] == 1


def test_plot_studio_report_is_data_driven_for_expression_matrix() -> None:
    assert DATA_FILE.exists(), f"Missing demo expression matrix: {DATA_FILE}"
    client = TestClient(app)

    report = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "taskId": "demo",
                "nodeId": "upload_expression",
                "name": "Expression matrix",
                "type": "expression_matrix",
                "dataPath": str(DATA_FILE),
                "meta": {"sample_count": 52, "gene_count": 2000},
            },
            "plotType": "Heatmap",
            "params": {"top_n": 40},
        },
    )

    assert report["selected_plot"]["id"] == "heatmap"
    assert "heatmap" in report["recommended_plot_ids"]
    assert report["table_summary"]["filename"] == DATA_FILE.name
    assert report["table_summary"]["scanned_rows"] > 0
    assert report["table_summary"]["numeric_columns"]
    sections = {section["title"]: section for section in report["report"]["sections"]}
    assert "scanned" in sections["Data readiness"]["text"]
    assert "top_n=40" in sections["Parameter notes"]["text"]
    assert any("Rendered images are not inspected" in item for item in report["report"]["limitations"])


def test_plot_studio_metadata_only_report_still_recommends_by_output_type() -> None:
    client = TestClient(app)

    report = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={
            "source": {
                "sourceKind": "report_output",
                "name": "DE genes",
                "type": "diff_result",
                "meta": {"comparison_label": "B vs A", "diff_gene_count": 128},
            },
            "plotType": "Volcano",
        },
    )

    assert report["selected_plot"]["id"] == "volcano"
    assert "volcano" in report["recommended_plot_ids"]
    assert report["table_summary"] is None
    assert any("metadata-only" in item for item in report["report"]["limitations"])


def test_plot_studio_spec_builds_interactive_plotly_boxplot() -> None:
    client = TestClient(app)

    spec = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "name": "Expression matrix",
                "type": "expression_matrix",
                "dataPath": str(DATA_FILE),
                "meta": {"sample_count": 52, "gene_count": 2000},
            },
            "plotType": "boxplot",
            "params": {"show_points": True, "max_groups": 4},
        },
    )

    assert spec["engine"] == "plotly"
    assert spec["plot_type"] == "boxplot"
    assert spec["data"]
    assert all(trace["type"] == "box" for trace in spec["data"])
    assert spec["layout"]["xaxis"]["title"]
    assert spec["config"]["displaylogo"] is False


def test_plot_studio_spec_builds_volcano_from_diff_table(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    diff_file = allowed_tmp / f"{tmp_path.name}_diff.csv"
    diff_file.write_text(
        "gene,log2fc,p_value\nA,2.1,0.001\nB,-1.8,0.002\nC,0.2,0.9\n",
        encoding="utf-8",
    )
    client = TestClient(app)

    spec = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "name": "Diff result",
                "type": "diff_result",
                "dataPath": str(diff_file),
            },
            "plotType": "volcano",
        },
    )

    assert spec["plot_type"] == "volcano"
    assert {trace["name"] for trace in spec["data"]} == {"Up", "Down", "Not significant"}
    assert len(spec["layout"]["shapes"]) == 3


def test_plot_studio_spec_builds_heatmap_and_correlation() -> None:
    client = TestClient(app)
    source = {
        "sourceKind": "analysis_output",
        "name": "Expression matrix",
        "type": "expression_matrix",
        "dataPath": str(DATA_FILE),
        "meta": {"sample_count": 52, "gene_count": 2000},
    }

    heatmap = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={"source": source, "plotType": "heatmap", "params": {"top_n": 12, "max_columns": 6}},
    )
    assert heatmap["plot_type"] == "heatmap"
    assert heatmap["data"][0]["type"] == "heatmap"
    assert len(heatmap["data"][0]["z"]) == 12
    assert len(heatmap["data"][0]["x"]) == 6

    correlation = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={"source": source, "plotType": "correlation", "params": {"max_columns": 7}},
    )
    assert correlation["plot_type"] == "correlation"
    assert correlation["data"][0]["type"] == "heatmap"
    assert len(correlation["data"][0]["z"]) == 7
    assert correlation["data"][0]["z"][0][0] == 1


def test_plot_studio_spec_builds_enrichment_dot_plot(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    enrichment_file = allowed_tmp / f"{tmp_path.name}_enrichment.csv"
    enrichment_file.write_text(
        "term,gene_ratio,count,adjusted_p\n"
        "cell cycle,3/100,3,0.001\n"
        "apoptosis,8/200,8,0.02\n"
        "immune response,5/120,5,0.004\n",
        encoding="utf-8",
    )
    client = TestClient(app)

    spec = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "name": "Enrichment result",
                "type": "enrichment_result",
                "dataPath": str(enrichment_file),
            },
            "plotType": "enrichment_dot",
            "params": {"top_n": 5},
        },
    )

    assert spec["plot_type"] == "enrichment_dot"
    assert spec["data"][0]["type"] == "scatter"
    assert spec["data"][0]["mode"] == "markers"
    assert len(spec["data"][0]["x"]) == 3


def test_table_inspection_and_recommendations_handle_numeric_tables() -> None:
    summary = inspect_table(DATA_FILE, max_rows=25)

    assert summary["scanned_rows"] == 25
    assert summary["column_count"] > 2
    assert summary["numeric_columns"]
    assert recommend_plot_types("unknown_table", summary)[0] in {"scatter", "boxplot"}
