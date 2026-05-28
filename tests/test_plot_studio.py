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
from yzwcloud.plot_studio_presets import PLOT_PRESETS  # noqa: E402


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
    assert {
        "boxplot",
        "heatmap",
        "volcano",
        "correlation",
        "histogram",
        "density_contour",
        "scatter_3d",
        "surface_3d",
    } <= set(presets)

    boxplot = presets["boxplot"]
    assert boxplot["engine"] == "plotly"
    assert boxplot["category"] == "Distribution"
    assert boxplot["thumbnail"] == "boxplot"
    assert "Group comparison" in boxplot["use_case"]
    assert boxplot["default_params"]["show_points"] is True
    assert any(group["id"] == "statistics" for group in boxplot["parameter_groups"])
    assert any(group["id"] == "export" for group in boxplot["parameter_groups"])
    assert any(group["id"] == "labels" for group in boxplot["parameter_groups"])
    assert next(group for group in boxplot["parameter_groups"] if group["id"] == "mapping")["advanced"] is False
    export_group = next(group for group in boxplot["parameter_groups"] if group["id"] == "export")
    assert export_group["advanced"] is True
    assert {param["id"] for param in export_group["parameters"]} >= {
        "margin_left",
        "margin_right",
        "margin_top",
        "margin_bottom",
    }
    scatter_statistics = next(group for group in presets["scatter"]["parameter_groups"] if group["id"] == "statistics")
    assert {param["id"] for param in scatter_statistics["parameters"]} >= {
        "trendline",
        "loess_fraction",
        "confidence_ellipse",
        "ellipse_level",
    }
    line_series = next(group for group in presets["line"]["parameter_groups"] if group["id"] == "series")
    assert {param["id"] for param in line_series["parameters"]} >= {
        "line_shape",
        "line_width",
        "marker_size",
        "marker_symbol",
    }

    bar = presets["bar"]
    assert bar["engine"] == "plotly"
    assert bar["default_params"]["show_points"] is True
    statistics_group = next(group for group in bar["parameter_groups"] if group["id"] == "statistics")
    assert {param["id"] for param in statistics_group["parameters"]} >= {"error_cap_width", "sort"}

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
            "params": {"top_n": 40, "title": "QC heatmap", "width": 980, "height": 640, "format": "png"},
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
    assert "title='QC heatmap'" in sections["Parameter notes"]["text"]
    assert "canvas=980x640" in sections["Parameter notes"]["text"]
    assert any("Rendered images are not inspected" in item for item in report["report"]["limitations"])
    assert report["agent_context"]["purpose"].startswith("LLM-readable")
    assert report["agent_context"]["plot"]["id"] == "heatmap"
    assert report["agent_context"]["table"]["filename"] == DATA_FILE.name
    assert report["agent_context"]["params"]["title"] == "QC heatmap"
    assert any("Do not infer visual details" in item for item in report["agent_context"]["interpretation_rules"])


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


def test_plot_studio_report_summarizes_statistical_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_stats.csv"
    table_file.write_text(
        "\n".join(
            [
                "condition,value",
                "A,1.0",
                "A,1.2",
                "B,2.4",
                "B,2.6",
            ]
        ),
        encoding="utf-8",
    )
    client = TestClient(app)

    report = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "name": "Grouped values",
                "type": "unknown_table",
                "dataPath": str(table_file),
            },
            "plotType": "boxplot",
            "params": {
                "group": "condition",
                "y": "value",
                "pairwise_test": "t_test",
                "multiple_testing": "BH",
                "show_p_values": True,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "pairwise test=t_test" in sections["Parameter notes"]
    assert "multiple testing=BH" in sections["Parameter notes"]
    assert "p-values shown on plot" in sections["Parameter notes"]
    assert "pairwise test=t_test" in report["agent_context"]["parameter_summary"]["statistics"]


def test_plot_studio_report_has_plot_specific_guidance_for_every_preset() -> None:
    client = TestClient(app)
    expected_keywords = {
        "scatter": "relationship strength",
        "boxplot": "group medians",
        "violin": "distribution shape",
        "bar": "aggregated group summaries",
        "line": "ordered trends",
        "histogram": "single-variable distribution shape",
        "density_contour": "two-variable density structure",
        "scatter_3d": "three-dimensional separation",
        "surface_3d": "matrix-level expression ridges",
        "heatmap": "row/column clustering",
        "bubble": "size and color encodings",
        "volcano": "up/down significant features",
        "upset": "set intersections",
        "venn": "small-set overlaps",
        "correlation": "similarity blocks",
        "enrichment_dot": "top enriched terms",
    }
    source = {
        "sourceKind": "analysis_output",
        "name": "Expression matrix",
        "type": "expression_matrix",
        "dataPath": str(DATA_FILE),
        "meta": {"sample_count": 52, "gene_count": 2000},
    }

    for preset in PLOT_PRESETS:
        plot_id = preset["id"]
        report = _request(
            client,
            "POST",
            "/api/plot-studio/report",
            json={"source": source, "plotType": plot_id},
        )
        sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
        assert "Figure interpretation" in sections
        assert expected_keywords[plot_id] in sections["Figure interpretation"]
        assert report["selected_plot"]["id"] == plot_id
        assert report["agent_context"]["plot"]["id"] == plot_id
        assert report["agent_context"]["plot"]["focus"]
        assert report["agent_context"]["source_type"] == "expression_matrix"
        assert report["agent_context"]["table"]["numeric_columns"]
        assert any("metadata, table summaries" in item for item in report["agent_context"]["interpretation_rules"])


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
            "params": {
                "show_points": True,
                "max_groups": 4,
                "title": "Custom expression distribution",
                "subtitle": "QC-filtered samples",
                "x_title": "Sample group",
                "y_title": "Normalized expression",
                "title_position": "center",
                "font_family": "georgia",
                "font_size": 16,
                "axis_line": False,
                "x_tick_angle": -35,
                "width": 900,
                "height": 520,
                "margin_left": 96,
                "margin_right": 44,
                "margin_top": 120,
                "margin_bottom": 88,
                "format": "png",
                "dpi": "600",
            },
        },
    )

    assert spec["engine"] == "plotly"
    assert spec["plot_type"] == "boxplot"
    assert spec["data"]
    assert all(trace["type"] == "box" for trace in spec["data"])
    assert spec["layout"]["xaxis"]["title"]
    assert spec["layout"]["title"]["text"] == "Custom expression distribution"
    assert spec["layout"]["title"]["x"] == 0.5
    assert spec["layout"]["annotations"][0]["text"] == "QC-filtered samples"
    assert spec["layout"]["xaxis"]["title"] == "Sample group"
    assert spec["layout"]["yaxis"]["title"] == "Normalized expression"
    assert spec["layout"]["xaxis"]["tickangle"] == -35
    assert spec["layout"]["xaxis"]["showline"] is False
    assert spec["layout"]["font"]["family"].startswith("Georgia")
    assert spec["layout"]["font"]["size"] == 16
    assert spec["layout"]["width"] == 900
    assert spec["layout"]["height"] == 520
    assert spec["layout"]["margin"] == {"l": 96, "r": 44, "t": 120, "b": 88}
    assert spec["config"]["toImageButtonOptions"]["format"] == "png"
    assert spec["config"]["toImageButtonOptions"]["scale"] == 4
    assert spec["config"]["displaylogo"] is False


def test_plot_studio_scatter_statistics_controls_render_overlays(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_scatter.csv"
    table_file.write_text(
        "\n".join(
            [
                "group,x,y,label",
                "A,1,2.1,a1",
                "A,2,4.0,a2",
                "A,3,6.2,a3",
                "A,4,8.1,a4",
                "B,1,1.3,b1",
                "B,2,1.7,b2",
                "B,3,2.5,b3",
                "B,4,3.2,b4",
            ]
        ),
        encoding="utf-8",
    )
    client = TestClient(app)
    source = {
        "sourceKind": "analysis_output",
        "name": "Scatter table",
        "type": "unknown_table",
        "dataPath": str(table_file),
    }

    linear = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": source,
            "plotType": "scatter",
            "params": {
                "x": "x",
                "y": "y",
                "color": "group",
                "label": "label",
                "trendline": "linear",
                "confidence_ellipse": True,
                "ellipse_level": 0.9,
            },
        },
    )
    names = {trace["name"] for trace in linear["data"]}
    assert {"A", "B", "A linear fit", "B linear fit", "A 90% ellipse", "B 90% ellipse"} <= names
    assert [trace for trace in linear["data"] if trace["name"] == "A linear fit"][0]["line"]["dash"] == "dash"
    assert [trace for trace in linear["data"] if trace["name"] == "A 90% ellipse"][0]["line"]["dash"] == "dot"

    loess = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": source,
            "plotType": "scatter",
            "params": {"x": "x", "y": "y", "color": "group", "trendline": "loess", "loess_fraction": 0.6},
        },
    )
    assert any(trace["name"] == "A LOESS smooth" for trace in loess["data"])


def test_plot_studio_line_style_controls_are_rendered(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_line.csv"
    table_file.write_text(
        "\n".join(
            [
                "time,series,value",
                "T1,A,1.0",
                "T2,A,1.5",
                "T3,A,2.0",
                "T1,B,0.8",
                "T2,B,1.1",
                "T3,B,1.6",
            ]
        ),
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
                "name": "Line table",
                "type": "unknown_table",
                "dataPath": str(table_file),
            },
            "plotType": "line",
            "params": {
                "x": "time",
                "y": "value",
                "series": "series",
                "line_shape": "hv",
                "line_width": 4.5,
                "marker_size": 11,
                "marker_symbol": "diamond",
                "connect_gaps": True,
            },
        },
    )

    assert spec["plot_type"] == "line"
    assert {trace["name"] for trace in spec["data"]} == {"A", "B"}
    assert all(trace["line"]["shape"] == "hv" for trace in spec["data"])
    assert all(trace["line"]["width"] == 4.5 for trace in spec["data"])
    assert all(trace["marker"]["size"] == 11 for trace in spec["data"])
    assert all(trace["marker"]["symbol"] == "diamond" for trace in spec["data"])
    assert all(trace["connectgaps"] is True for trace in spec["data"])


def test_plot_studio_spec_builds_prism_style_violin_and_bar(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_groups.csv"
    table_file.write_text(
        "\n".join(
            [
                "condition,value",
                "A,1.1",
                "A,1.4",
                "A,1.8",
                "B,2.2",
                "B,2.4",
                "B,2.8",
            ]
        ),
        encoding="utf-8",
    )
    client = TestClient(app)
    source = {
        "sourceKind": "analysis_output",
        "name": "Grouped values",
        "type": "unknown_table",
        "dataPath": str(table_file),
    }

    violin = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": source,
            "plotType": "violin",
            "params": {"group": "condition", "y": "value", "show_points": "all", "side": "positive", "bandwidth": 0.4},
        },
    )
    assert violin["plot_type"] == "violin"
    assert all(trace["type"] == "violin" for trace in violin["data"])
    assert violin["data"][0]["points"] == "all"
    assert violin["data"][0]["side"] == "positive"
    assert violin["data"][0]["bandwidth"] == 0.4

    bar = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": source,
            "plotType": "bar",
            "params": {
                "category": "condition",
                "value": "value",
                "show_points": True,
                "error_bar": "sem",
                "sort": "descending",
                "error_cap_width": 12,
            },
        },
    )
    assert bar["plot_type"] == "bar"
    assert [trace["type"] for trace in bar["data"]] == ["bar", "scatter"]
    assert bar["data"][0]["x"] == ["B", "A"]
    assert bar["data"][0]["error_y"]["width"] == 12
    assert bar["data"][1]["name"] == "Raw values"


def test_plot_studio_boxplot_pairwise_p_values_render_brackets(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_box_stats.csv"
    table_file.write_text(
        "\n".join(
            [
                "condition,value",
                "A,1.0",
                "A,1.2",
                "A,1.1",
                "A,1.3",
                "B,3.4",
                "B,3.6",
                "B,3.5",
                "B,3.7",
                "C,2.2",
                "C,2.0",
                "C,2.1",
                "C,2.3",
            ]
        ),
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
                "name": "Grouped values",
                "type": "unknown_table",
                "dataPath": str(table_file),
            },
            "plotType": "boxplot",
            "params": {
                "group": "condition",
                "y": "value",
                "pairwise_test": "t_test",
                "multiple_testing": "bonferroni",
                "show_p_values": True,
            },
        },
    )

    assert spec["plot_type"] == "boxplot"
    assert len(spec["layout"]["annotations"]) == 3
    assert all(annotation["text"].startswith("p") for annotation in spec["layout"]["annotations"])
    assert len(spec["layout"]["shapes"]) == 9
    assert spec["layout"]["yaxis"]["range"][1] > 3.7


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


def test_plot_studio_spec_builds_added_interactive_plot_types() -> None:
    client = TestClient(app)
    source = {
        "sourceKind": "analysis_output",
        "name": "Expression matrix",
        "type": "expression_matrix",
        "dataPath": str(DATA_FILE),
        "meta": {"sample_count": 52, "gene_count": 2000},
    }

    histogram = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={"source": source, "plotType": "histogram", "params": {"bins": 24}},
    )
    assert histogram["plot_type"] == "histogram"
    assert histogram["data"][0]["type"] == "histogram"
    assert histogram["data"][0]["nbinsx"] == 24

    contour = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={"source": source, "plotType": "density_contour"},
    )
    assert contour["plot_type"] == "density_contour"
    assert contour["data"][0]["type"] == "histogram2dcontour"
    assert any(trace["type"] == "scattergl" for trace in contour["data"])

    scatter_3d = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={"source": source, "plotType": "scatter_3d"},
    )
    assert scatter_3d["plot_type"] == "scatter_3d"
    assert scatter_3d["data"][0]["type"] == "scatter3d"
    assert "scene" in scatter_3d["layout"]

    surface = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={"source": source, "plotType": "surface_3d", "params": {"top_n": 10, "max_columns": 6}},
    )
    assert surface["plot_type"] == "surface_3d"
    assert surface["data"][0]["type"] == "surface"
    assert len(surface["data"][0]["z"]) == 10
    assert len(surface["data"][0]["z"][0]) == 6


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
