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
from yzwcloud.plot_studio_presets import PLOT_PRESETS, SUPPORTED_PLOTLY_SPEC_TYPES  # noqa: E402


DATA_FILE = ROOT / "expression_matrix.csv"


def _request(client: TestClient, method: str, path: str, **kwargs: Any) -> Any:
    response = client.request(method, path, **kwargs)
    assert response.status_code < 400, f"{method} {path} failed: {response.status_code} {response.text}"
    return response.json()


def test_plot_studio_presets_expose_prism_like_defaults() -> None:
    client = TestClient(app)

    manifest = _request(client, "GET", "/api/plot-studio/presets")

    assert manifest["version"] == "0.1"
    assert manifest["engines"] == ["plotly"]
    presets = {item["id"]: item for item in manifest["presets"]}
    assert {
        "boxplot",
        "heatmap",
        "volcano",
        "upset",
        "venn",
        "correlation",
        "histogram",
        "density_contour",
        "scatter_3d",
        "surface_3d",
    } <= set(presets)

    boxplot = presets["boxplot"]
    assert boxplot["engine"] == "plotly"
    assert all(presets[plot_id]["engine"] == "plotly" for plot_id in SUPPORTED_PLOTLY_SPEC_TYPES)
    assert boxplot["category"] == "Distribution"
    assert boxplot["thumbnail"] == "boxplot"
    assert "Group comparison" in boxplot["use_case"]
    assert boxplot["default_params"]["show_points"] is True
    assert boxplot["default_params"]["point_size"] == 5
    assert boxplot["default_params"]["point_alpha"] == 0.72
    violin_distribution = next(group for group in presets["violin"]["parameter_groups"] if group["id"] == "distribution")
    assert {param["id"] for param in violin_distribution["parameters"]} >= {"point_size", "point_alpha"}
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
    theme_group = next(group for group in boxplot["parameter_groups"] if group["id"] == "theme")
    assert theme_group["advanced"] is True
    assert {param["id"] for param in theme_group["parameters"]} >= {
        "grid_color",
        "grid_width",
        "axis_line_color",
        "axis_line_width",
        "legend_title",
        "legend_font_size",
    }
    scatter_statistics = next(group for group in presets["scatter"]["parameter_groups"] if group["id"] == "statistics")
    assert {param["id"] for param in scatter_statistics["parameters"]} >= {
        "trendline",
        "loess_fraction",
        "confidence_ellipse",
        "ellipse_level",
        "marker_line_width",
        "marker_line_color",
        "x_log",
        "y_log",
    }
    line_series = next(group for group in presets["line"]["parameter_groups"] if group["id"] == "series")
    assert {param["id"] for param in line_series["parameters"]} >= {
        "line_shape",
        "line_width",
        "line_dash",
        "marker_size",
        "marker_symbol",
    }

    bar = presets["bar"]
    assert bar["engine"] == "plotly"
    assert bar["default_params"]["show_points"] is True
    statistics_group = next(group for group in bar["parameter_groups"] if group["id"] == "statistics")
    assert {param["id"] for param in statistics_group["parameters"]} >= {
        "error_cap_width",
        "show_values",
        "value_precision",
        "bar_width",
        "sort",
        "pairwise_test",
        "multiple_testing",
        "show_p_values",
    }
    volcano = presets["volcano"]
    volcano_thresholds = next(group for group in volcano["parameter_groups"] if group["id"] == "thresholds")
    assert {param["id"] for param in volcano_thresholds["parameters"]} >= {
        "show_threshold_lines",
        "label_font_size",
        "point_size",
        "point_alpha",
    }
    volcano_style = next(group for group in volcano["parameter_groups"] if group["id"] == "style")
    assert volcano_style["advanced"] is True
    assert {param["id"] for param in volcano_style["parameters"]} >= {
        "threshold_line_width",
        "threshold_line_dash",
        "threshold_line_color",
    }

    heatmap = presets["heatmap"]
    assert heatmap["default_params"]["show_dendrogram"] is True
    assert heatmap["default_params"]["show_values"] is False
    clustering_group = next(group for group in heatmap["parameter_groups"] if group["id"] == "clustering")
    top_n = next(param for param in clustering_group["parameters"] if param["id"] == "top_n")
    assert top_n["step"] == 1
    cell_group = next(group for group in heatmap["parameter_groups"] if group["id"] == "cells")
    assert {param["id"] for param in cell_group["parameters"]} >= {"show_values", "value_precision", "cell_gap"}
    histogram_distribution = next(group for group in presets["histogram"]["parameter_groups"] if group["id"] == "distribution")
    assert {param["id"] for param in histogram_distribution["parameters"]} >= {
        "show_mean",
        "show_median",
        "show_rug",
        "bar_line_width",
        "bar_line_color",
    }
    histogram_reference = next(group for group in presets["histogram"]["parameter_groups"] if group["id"] == "reference")
    assert histogram_reference["advanced"] is True
    assert {param["id"] for param in histogram_reference["parameters"]} >= {
        "reference_line_width",
        "reference_line_color_mode",
        "reference_line_color",
    }

    upset = presets["upset"]
    upset_sets = next(group for group in upset["parameter_groups"] if group["id"] == "sets")
    assert {param["id"] for param in upset_sets["parameters"]} >= {"max_sets", "max_intersections"}
    correlation_statistics = next(group for group in presets["correlation"]["parameter_groups"] if group["id"] == "statistics")
    assert {param["id"] for param in correlation_statistics["parameters"]} >= {"show_values", "value_precision", "cell_gap"}
    venn = presets["venn"]
    assert venn["default_params"]["max_sets"] == 4
    enrichment_terms = next(group for group in presets["enrichment_dot"]["parameter_groups"] if group["id"] == "terms")
    assert {param["id"] for param in enrichment_terms["parameters"]} >= {
        "term_label_width",
        "min_dot_size",
        "max_dot_size",
        "color_scale",
        "point_alpha",
    }
    bubble_style = next(group for group in presets["bubble"]["parameter_groups"] if group["id"] == "bubble")
    assert {param["id"] for param in bubble_style["parameters"]} >= {
        "color_scale",
        "point_alpha",
        "size_scale",
        "marker_line_width",
        "marker_line_color",
    }
    density_group = next(group for group in presets["density_contour"]["parameter_groups"] if group["id"] == "density")
    assert {param["id"] for param in density_group["parameters"]} >= {
        "contour_line_width",
        "show_contour_labels",
        "contour_start",
        "contour_end",
        "contour_size",
    }
    surface_group = next(group for group in presets["surface_3d"]["parameter_groups"] if group["id"] == "surface")
    assert {param["id"] for param in surface_group["parameters"]} >= {"camera", "show_contours", "colorscale"}


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
            "params": {
                "top_n": 40,
                "title": "QC heatmap",
                "width": 980,
                "height": 640,
                "format": "png",
                "scale": "row_zscore",
                "palette": "blue_red",
                "cluster_rows": True,
                "cluster_columns": True,
                "distance": "correlation",
                "linkage": "average",
                "show_dendrogram": True,
                "show_values": True,
                "value_precision": 1,
                "cell_gap": 2,
                "show_grid": False,
                "grid_color": "#dbeafe",
                "grid_width": 1.8,
                "axis_line": True,
                "axis_line_color": "#0f172a",
                "axis_line_width": 2.2,
                "legend_title": "Sample group",
                "legend_font_size": 15,
            },
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
    assert "scale=row_zscore" in sections["Parameter notes"]["text"]
    assert "cluster rows=True" in sections["Parameter notes"]["text"]
    assert "distance=correlation" in sections["Parameter notes"]["text"]
    assert "color scale=blue_red" in sections["Parameter notes"]["text"]
    assert "cell values shown with 1 decimals" in sections["Parameter notes"]["text"]
    assert "cell gap=2" in sections["Parameter notes"]["text"]
    assert "title='QC heatmap'" in sections["Parameter notes"]["text"]
    assert "canvas=980x640" in sections["Parameter notes"]["text"]
    assert any("Rendered images are not inspected" in item for item in report["report"]["limitations"])
    assert report["agent_context"]["purpose"].startswith("LLM-readable")
    assert report["agent_context"]["plot"]["id"] == "heatmap"
    assert report["agent_context"]["table"]["filename"] == DATA_FILE.name
    assert report["agent_context"]["params"]["title"] == "QC heatmap"
    assert "dendrogram guides shown" in report["agent_context"]["parameter_summary"]["display"]
    assert "grid shown=False" in report["agent_context"]["parameter_summary"]["display"]
    assert "grid color=#dbeafe" in report["agent_context"]["parameter_summary"]["display"]
    assert "grid width=1.8" in report["agent_context"]["parameter_summary"]["display"]
    assert "axis line shown=True" in report["agent_context"]["parameter_summary"]["display"]
    assert "axis line color=#0f172a" in report["agent_context"]["parameter_summary"]["display"]
    assert "axis line width=2.2" in report["agent_context"]["parameter_summary"]["display"]
    assert "legend title='Sample group'" in report["agent_context"]["parameter_summary"]["display"]
    assert "legend font size=15" in report["agent_context"]["parameter_summary"]["display"]
    assert "linkage=average" in report["agent_context"]["parameter_summary"]["statistics"]
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
                "point_size": 9,
                "point_alpha": 0.44,
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

    bar_report = _request(
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
            "plotType": "bar",
            "params": {
                "category": "condition",
                "value": "value",
                "aggregation": "mean",
                "error_bar": "ci95",
                "pairwise_test": "wilcoxon",
                "multiple_testing": "bonferroni",
                "show_p_values": True,
            },
        },
    )
    bar_sections = {section["title"]: section["text"] for section in bar_report["report"]["sections"]}
    assert "aggregation=mean" in bar_sections["Parameter notes"]
    assert "error bar=ci95" in bar_sections["Parameter notes"]
    assert "pairwise test=wilcoxon" in bar_sections["Parameter notes"]
    assert "multiple testing=bonferroni" in bar_sections["Parameter notes"]
    assert "p-values shown on plot" in bar_report["agent_context"]["parameter_summary"]["statistics"]

    bar_display_report = _request(
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
            "plotType": "bar",
            "params": {
                "category": "condition",
                "value": "value",
                "show_points": False,
                "point_alpha": 0.44,
                "error_cap_width": 14,
                "show_values": True,
                "value_precision": 3,
                "bar_width": 0.6,
                "sort": "descending",
                "orientation": "horizontal",
            },
        },
    )
    bar_display_summary = bar_display_report["agent_context"]["parameter_summary"]["display"]
    assert "raw points shown=False" in bar_display_summary
    assert "point opacity=0.44" in bar_display_summary
    assert "error cap width=14" in bar_display_summary
    assert "value labels shown with 3 decimals" in bar_display_summary
    assert "bar width=0.6" in bar_display_summary
    assert "sort bars=descending" in bar_display_summary
    assert "orientation=horizontal" in bar_display_summary

    histogram_report = _request(
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
            "plotType": "histogram",
            "params": {
                "x": "value",
                "bins": 18,
                "histnorm": "density",
                "barmode": "stack",
                "opacity": 0.41,
                "bar_line_width": 1.7,
                "bar_line_color": "#111827",
                "reference_line_width": 2.4,
                "reference_line_color_mode": "custom",
                "reference_line_color": "#334155",
                "cumulative": True,
                "show_mean": True,
                "show_median": True,
                "show_rug": True,
            },
        },
    )
    histogram_sections = {section["title"]: section["text"] for section in histogram_report["report"]["sections"]}
    assert "cumulative histogram" in histogram_sections["Parameter notes"]
    assert "mean reference shown" in histogram_sections["Parameter notes"]
    assert "median reference shown" in histogram_sections["Parameter notes"]
    histogram_display_summary = histogram_report["agent_context"]["parameter_summary"]["display"]
    assert "bar mode=stack" in histogram_display_summary
    assert "opacity=0.41" in histogram_display_summary
    assert "bar line width=1.7" in histogram_display_summary
    assert "bar line color=#111827" in histogram_display_summary
    assert "reference line width=2.4" in histogram_display_summary
    assert "reference line color mode=custom" in histogram_display_summary
    assert "reference line color=#334155" in histogram_display_summary
    assert "rug marks shown" in histogram_display_summary


def test_plot_studio_report_summarizes_upset_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_upset.csv"
    table_file.write_text(
        "\n".join(
            [
                "gene,A,B,C",
                "g1,1,1,0",
                "g2,1,0,1",
                "g3,1,1,1",
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
                "name": "Gene sets",
                "type": "unknown_table",
                "dataPath": str(table_file),
            },
            "plotType": "upset",
            "params": {
                "item_id": "gene",
                "set_columns": ["A", "B", "C"],
                "min_intersection_size": 1,
                "max_sets": 3,
                "max_intersections": 10,
                "sort_by": "degree",
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "min intersection=1" in sections["Parameter notes"]
    assert "max intersections=10" in sections["Parameter notes"]
    assert "sort by=degree" in report["agent_context"]["parameter_summary"]["display"]


def test_plot_studio_report_summarizes_venn_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_venn.csv"
    table_file.write_text(
        "\n".join(
            [
                "gene,A,B,C",
                "g1,1,1,0",
                "g2,1,0,1",
                "g3,1,1,1",
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
                "name": "Gene sets",
                "type": "unknown_table",
                "dataPath": str(table_file),
            },
            "plotType": "venn",
            "params": {
                "item_id": "gene",
                "set_columns": ["A", "B", "C"],
                "max_sets": 3,
                "show_counts": True,
                "show_percent": True,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "max sets=3" in sections["Parameter notes"]
    assert "show percent=True" in report["agent_context"]["parameter_summary"]["display"]


def test_plot_studio_report_summarizes_volcano_label_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_volcano.csv"
    table_file.write_text("gene,log2fc,p_value\nA,2.1,0.001\nB,-1.8,0.002\n", encoding="utf-8")
    client = TestClient(app)

    report = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "name": "Diff result",
                "type": "diff_result",
                "dataPath": str(table_file),
            },
            "plotType": "volcano",
            "params": {
                "log2fc_threshold": 1.2,
                "p_value_threshold": 0.01,
                "show_threshold_lines": False,
                "threshold_line_width": 2.2,
                "threshold_line_dash": "dot",
                "threshold_line_color": "#475569",
                "label_top_n": 5,
                "label_mode": "top_p",
                "label_font_size": 14,
                "point_size": 9,
                "point_alpha": 0.42,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "abs log2FC threshold=1.2" in sections["Parameter notes"]
    assert "threshold lines=False" in report["agent_context"]["parameter_summary"]["display"]
    assert "threshold line width=2.2" in report["agent_context"]["parameter_summary"]["display"]
    assert "threshold line dash=dot" in report["agent_context"]["parameter_summary"]["display"]
    assert "threshold line color=#475569" in report["agent_context"]["parameter_summary"]["display"]
    assert "top labels=5" in report["agent_context"]["parameter_summary"]["display"]
    assert "label mode=top_p" in report["agent_context"]["parameter_summary"]["display"]
    assert "label font size=14" in report["agent_context"]["parameter_summary"]["display"]
    assert "point size=9" in report["agent_context"]["parameter_summary"]["display"]
    assert "point opacity=0.42" in report["agent_context"]["parameter_summary"]["display"]


def test_plot_studio_report_summarizes_correlation_parameters() -> None:
    client = TestClient(app)

    report = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "name": "Expression matrix",
                "type": "expression_matrix",
                "dataPath": str(DATA_FILE),
                "meta": {"sample_count": 52, "gene_count": 2000},
            },
            "plotType": "correlation",
            "params": {
                "method": "spearman",
                "cluster_rows": False,
                "cluster_columns": True,
                "show_values": True,
                "value_precision": 3,
                "cell_gap": 4,
                "color_scale": "green_white_purple",
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "method=spearman" in sections["Parameter notes"]
    assert "cluster rows=False" in sections["Parameter notes"]
    assert "cluster columns=True" in sections["Parameter notes"]
    assert "r-value labels shown with 3 decimals" in report["agent_context"]["parameter_summary"]["display"]
    assert "color scale=green_white_purple" in report["agent_context"]["parameter_summary"]["display"]
    assert "cell gap=4" in report["agent_context"]["parameter_summary"]["display"]


def test_plot_studio_report_summarizes_enrichment_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_enrichment.csv"
    table_file.write_text(
        "term,gene_ratio,count,adjusted_p\ncell cycle checkpoint,3/100,3,0.001\nimmune response,5/120,5,0.004\n",
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
                "name": "Enrichment result",
                "type": "enrichment_result",
                "dataPath": str(table_file),
            },
            "plotType": "enrichment_dot",
            "params": {
                "top_n": 10,
                "sort_by": "count",
                "color_transform": "minus_log10",
                "wrap_term_label": True,
                "term_label_width": 18,
                "min_dot_size": 5,
                "max_dot_size": 28,
                "color_scale": "plasma",
                "point_alpha": 0.64,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "top terms=10" in sections["Parameter notes"]
    assert "sort by=count" in sections["Parameter notes"]
    assert "color transform=minus_log10" in sections["Parameter notes"]
    enrichment_display_summary = report["agent_context"]["parameter_summary"]["display"]
    assert "wrapped term labels" in enrichment_display_summary
    assert "term label width=18" in enrichment_display_summary
    assert "dot size range=5-28" in enrichment_display_summary
    assert "color scale=plasma" in enrichment_display_summary
    assert "point opacity=0.64" in enrichment_display_summary


def test_plot_studio_report_summarizes_bubble_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_bubble.csv"
    table_file.write_text("x,y,size,score\n1,2,10,0.2\n2,3,20,0.8\n", encoding="utf-8")
    client = TestClient(app)

    report = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "name": "Bubble table",
                "type": "unknown_table",
                "dataPath": str(table_file),
            },
            "plotType": "bubble",
            "params": {
                "x": "x",
                "y": "y",
                "size": "size",
                "color": "score",
                "size_scale": 36,
                "min_bubble_size": 6,
                "max_bubble_size": 30,
                "color_scale": "plasma",
                "point_alpha": 0.55,
                "marker_line_width": 1.6,
                "marker_line_color": "#111827",
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "size scale=36" in sections["Parameter notes"]
    assert "bubble size range=6-30" in sections["Parameter notes"]
    assert "continuous color scale=plasma" in report["agent_context"]["parameter_summary"]["display"]
    assert "point opacity=0.55" in report["agent_context"]["parameter_summary"]["display"]
    assert "marker line width=1.6" in report["agent_context"]["parameter_summary"]["display"]
    assert "marker line color=#111827" in report["agent_context"]["parameter_summary"]["display"]


def test_plot_studio_report_summarizes_distribution_display_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_distribution_report.csv"
    table_file.write_text(
        "\n".join(["condition,value", "A,1.0", "A,1.2", "B,2.2", "B,2.5"]),
        encoding="utf-8",
    )
    client = TestClient(app)
    source = {
        "sourceKind": "analysis_output",
        "name": "Grouped values",
        "type": "unknown_table",
        "dataPath": str(table_file),
    }

    boxplot_report = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={
            "source": source,
            "plotType": "boxplot",
            "params": {
                "group": "condition",
                "y": "value",
                "show_points": True,
                "point_jitter": 0.45,
                "point_size": 8,
                "point_alpha": 0.48,
                "show_mean": False,
                "notched": True,
                "box_width": 0.5,
            },
        },
    )
    boxplot_summary = boxplot_report["agent_context"]["parameter_summary"]["display"]
    assert "raw points shown=True" in boxplot_summary
    assert "point jitter=0.45" in boxplot_summary
    assert "point size=8" in boxplot_summary
    assert "point opacity=0.48" in boxplot_summary
    assert "mean marker=False" in boxplot_summary
    assert "notched boxes enabled" in boxplot_summary
    assert "box width=0.5" in boxplot_summary

    violin_report = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={
            "source": source,
            "plotType": "violin",
            "params": {
                "group": "condition",
                "y": "value",
                "show_box": False,
                "show_mean": True,
                "show_points": "all",
                "bandwidth": 0.35,
                "side": "positive",
                "point_size": 7,
                "point_alpha": 0.62,
            },
        },
    )
    violin_summary = violin_report["agent_context"]["parameter_summary"]
    assert "bandwidth=0.35" in violin_summary["statistics"]
    assert "box overlay=False" in violin_summary["display"]
    assert "mean line=True" in violin_summary["display"]
    assert "points=all" in violin_summary["display"]
    assert "side=positive" in violin_summary["display"]
    assert "point size=7" in violin_summary["display"]
    assert "point opacity=0.62" in violin_summary["display"]


def test_plot_studio_report_summarizes_scatter_axis_transforms(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_scatter_report.csv"
    table_file.write_text("group,x,y,size,label\nA,1,10,4,g1\nB,10,100,12,g2\n", encoding="utf-8")
    client = TestClient(app)

    report = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "name": "Scatter table",
                "type": "unknown_table",
                "dataPath": str(table_file),
            },
            "plotType": "scatter",
            "params": {
                "x": "x",
                "y": "y",
                "color": "group",
                "size": "size",
                "label": "label",
                "point_size": 11,
                "point_alpha": 0.53,
                "marker_line_width": 1.4,
                "marker_line_color": "#111827",
                "x_log": True,
                "y_log": True,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "color by=group" in sections["Parameter notes"]
    assert "size by=size" in sections["Parameter notes"]
    assert "point labels=label" in sections["Parameter notes"]
    assert "point size=11" in sections["Parameter notes"]
    assert "point opacity=0.53" in sections["Parameter notes"]
    assert "marker line width=1.4" in sections["Parameter notes"]
    assert "marker line color=#111827" in sections["Parameter notes"]
    assert "log x-axis" in sections["Parameter notes"]
    assert "log y-axis" in report["agent_context"]["parameter_summary"]["display"]


def test_plot_studio_report_summarizes_line_display_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_line_report.csv"
    table_file.write_text("time,series,value\nT1,A,1\nT2,A,2\n", encoding="utf-8")
    client = TestClient(app)

    report = _request(
        client,
        "POST",
        "/api/plot-studio/report",
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
                "line_shape": "linear",
                "line_width": 3.2,
                "line_dash": "dashdot",
                "smooth": True,
                "show_points": False,
                "marker_size": 9,
                "marker_symbol": "diamond",
                "connect_gaps": True,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "line width=3.2" in sections["Parameter notes"]
    assert "line dash=dashdot" in sections["Parameter notes"]
    assert "spline smoothing enabled" in sections["Parameter notes"]
    assert "markers shown=False" in report["agent_context"]["parameter_summary"]["display"]
    assert "marker symbol=diamond" in report["agent_context"]["parameter_summary"]["display"]
    assert "missing values connected" in report["agent_context"]["parameter_summary"]["display"]


def test_plot_studio_report_summarizes_density_contour_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_density_report.csv"
    table_file.write_text("x,y\n1,2\n2,4\n3,6\n4,7\n", encoding="utf-8")
    client = TestClient(app)

    report = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "name": "Density table",
                "type": "unknown_table",
                "dataPath": str(table_file),
            },
            "plotType": "density_contour",
            "params": {
                "x": "x",
                "y": "y",
                "contours_coloring": "lines",
                "contour_line_width": 2.5,
                "show_contour_labels": True,
                "contour_start": 0.1,
                "contour_end": 0.9,
                "contour_size": 0.2,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "contour fill=lines" in sections["Parameter notes"]
    assert "contour line width=2.5" in sections["Parameter notes"]
    assert "contour range/step=0.1,0.9,0.2" in sections["Parameter notes"]
    assert "contour labels shown" in report["agent_context"]["parameter_summary"]["display"]


def test_plot_studio_report_summarizes_surface_parameters() -> None:
    client = TestClient(app)

    report = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "name": "Expression matrix",
                "type": "expression_matrix",
                "dataPath": str(DATA_FILE),
                "meta": {"sample_count": 52, "gene_count": 2000},
            },
            "plotType": "surface_3d",
            "params": {
                "scale": "log2",
                "top_n": 16,
                "colorscale": "Plasma",
                "show_contours": False,
                "camera": "top",
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "scale=log2" in sections["Parameter notes"]
    assert "top rows=16" in sections["Parameter notes"]
    assert "surface contours=False" in report["agent_context"]["parameter_summary"]["display"]
    assert "camera=top" in report["agent_context"]["parameter_summary"]["display"]


def test_plot_studio_report_summarizes_scatter_3d_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_scatter3d_report.csv"
    table_file.write_text("x,y,z\n1,2,3\n2,3,4\n", encoding="utf-8")
    client = TestClient(app)

    report = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "name": "3D scatter table",
                "type": "unknown_table",
                "dataPath": str(table_file),
            },
            "plotType": "scatter_3d",
            "params": {"x": "x", "y": "y", "z": "z", "marker_size": 9, "point_alpha": 0.42, "camera": "front"},
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "marker size=9" in sections["Parameter notes"]
    assert "point opacity=0.42" in sections["Parameter notes"]
    assert "camera=front" in report["agent_context"]["parameter_summary"]["display"]


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
                "axis_line_color": "#111827",
                "axis_line_width": 2.5,
                "show_grid": True,
                "grid_color": "#cbd5e1",
                "grid_width": 1.6,
                "legend_title": "Condition",
                "legend_font_size": 14,
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
    assert spec["layout"]["xaxis"]["linecolor"] == "#111827"
    assert spec["layout"]["xaxis"]["linewidth"] == 2.5
    assert spec["layout"]["xaxis"]["gridcolor"] == "#cbd5e1"
    assert spec["layout"]["xaxis"]["gridwidth"] == 1.6
    assert spec["layout"]["yaxis"]["linecolor"] == "#111827"
    assert spec["layout"]["yaxis"]["linewidth"] == 2.5
    assert spec["layout"]["yaxis"]["gridcolor"] == "#cbd5e1"
    assert spec["layout"]["yaxis"]["gridwidth"] == 1.6
    assert spec["layout"]["legend"]["title"]["text"] == "Condition"
    assert spec["layout"]["legend"]["font"]["size"] == 14
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
                "group,x,y,label,size",
                "A,1,2.1,a1,3",
                "A,2,4.0,a2,5",
                "A,3,6.2,a3,7",
                "A,4,8.1,a4,9",
                "B,1,1.3,b1,4",
                "B,2,1.7,b2,6",
                "B,3,2.5,b3,8",
                "B,4,3.2,b4,10",
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
                "size": "size",
                "label": "label",
                "point_size": 10,
                "point_alpha": 0.5,
                "marker_line_width": 1.2,
                "marker_line_color": "#111827",
                "trendline": "linear",
                "confidence_ellipse": True,
                "ellipse_level": 0.9,
            },
        },
    )
    names = {trace["name"] for trace in linear["data"]}
    assert {"A", "B", "A linear fit", "B linear fit", "A 90% ellipse", "B 90% ellipse"} <= names
    group_trace = next(trace for trace in linear["data"] if trace["name"] == "A")
    assert isinstance(group_trace["marker"]["size"], list)
    assert max(group_trace["marker"]["size"]) > min(group_trace["marker"]["size"])
    assert group_trace["marker"]["opacity"] == 0.5
    assert group_trace["marker"]["line"] == {"color": "#111827", "width": 1.2}
    assert "size=%{customdata[0]}" in group_trace["hovertemplate"]
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

    log_axes = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": source,
            "plotType": "scatter",
            "params": {"x": "x", "y": "y", "x_log": True, "y_log": True},
        },
    )
    assert log_axes["layout"]["xaxis"]["type"] == "log"
    assert log_axes["layout"]["yaxis"]["type"] == "log"


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
                "line_dash": "dash",
                "marker_size": 11,
                "marker_symbol": "diamond",
                "connect_gaps": True,
            },
        },
    )

    assert spec["plot_type"] == "line"
    assert {trace["name"] for trace in spec["data"]} == {"A", "B"}
    assert all(trace["line"]["shape"] == "hv" for trace in spec["data"])
    assert all(trace["line"]["dash"] == "dash" for trace in spec["data"])
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
            "params": {
                "group": "condition",
                "y": "value",
                "show_points": "all",
                "side": "positive",
                "bandwidth": 0.4,
                "point_size": 8,
                "point_alpha": 0.51,
            },
        },
    )
    assert violin["plot_type"] == "violin"
    assert all(trace["type"] == "violin" for trace in violin["data"])
    assert violin["data"][0]["points"] == "all"
    assert violin["data"][0]["side"] == "positive"
    assert violin["data"][0]["bandwidth"] == 0.4
    assert violin["data"][0]["marker"]["size"] == 8
    assert violin["data"][0]["marker"]["opacity"] == 0.51

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
                "show_values": True,
                "value_precision": 1,
                "bar_width": 0.5,
                "pairwise_test": "t_test",
                "multiple_testing": "BH",
                "show_p_values": True,
            },
        },
    )
    assert bar["plot_type"] == "bar"
    assert [trace["type"] for trace in bar["data"]] == ["bar", "scatter"]
    assert bar["data"][0]["x"] == ["B", "A"]
    assert bar["data"][0]["width"] == 0.5
    assert bar["data"][0]["text"] == ["2.5", "1.4"]
    assert bar["data"][0]["textposition"] == "outside"
    assert bar["data"][0]["error_y"]["width"] == 12
    assert bar["data"][1]["name"] == "Raw values"
    assert len(bar["layout"]["shapes"]) == 3
    assert len(bar["layout"]["annotations"]) == 1
    assert bar["layout"]["annotations"][0]["text"].startswith("p")
    assert bar["layout"]["yaxis"]["range"][1] > max(bar["data"][0]["y"])


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
                "point_size": 9,
                "point_alpha": 0.44,
                "pairwise_test": "t_test",
                "multiple_testing": "bonferroni",
                "show_p_values": True,
            },
        },
    )

    assert spec["plot_type"] == "boxplot"
    assert all(trace["marker"]["size"] == 9 for trace in spec["data"])
    assert all(trace["marker"]["opacity"] == 0.44 for trace in spec["data"])
    assert len(spec["layout"]["annotations"]) == 3
    assert all(annotation["text"].startswith("p") for annotation in spec["layout"]["annotations"])
    assert len(spec["layout"]["shapes"]) == 9
    assert spec["layout"]["yaxis"]["range"][1] > 3.7


def test_plot_studio_spec_builds_upset_intersections(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_upset.csv"
    table_file.write_text(
        "\n".join(
            [
                "gene,A,B,C",
                "g1,1,1,0",
                "g2,1,0,1",
                "g3,1,1,1",
                "g4,0,1,1",
                "g5,1,0,0",
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
                "name": "Gene sets",
                "type": "unknown_table",
                "dataPath": str(table_file),
            },
            "plotType": "upset",
            "params": {"item_id": "gene", "set_columns": ["A", "B", "C"], "max_intersections": 5},
        },
    )

    assert spec["plot_type"] == "upset"
    assert spec["data"][0]["type"] == "bar"
    assert spec["data"][0]["name"] == "Intersection size"
    assert "A&B" in spec["data"][0]["x"]
    assert any(trace.get("xaxis") == "x2" for trace in spec["data"][1:])
    assert spec["layout"]["xaxis3"]["title"] == "Set size"


def test_plot_studio_spec_builds_venn_overlap_sketch(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_venn.csv"
    table_file.write_text(
        "\n".join(
            [
                "gene,A,B,C",
                "g1,1,1,0",
                "g2,1,0,1",
                "g3,1,1,1",
                "g4,0,1,1",
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
                "name": "Gene sets",
                "type": "unknown_table",
                "dataPath": str(table_file),
            },
            "plotType": "venn",
            "params": {"item_id": "gene", "set_columns": ["A", "B", "C"], "show_counts": True, "show_percent": True},
        },
    )

    assert spec["plot_type"] == "venn"
    assert len(spec["layout"]["shapes"]) == 3
    assert spec["data"][0]["mode"] == "text"
    assert any("A&B&C" in hover for hover in spec["data"][0]["customdata"])
    assert spec["layout"]["xaxis"]["visible"] is False


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
            "params": {
                "label_top_n": 2,
                "label_mode": "top_p",
                "label_font_size": 15,
                "point_size": 10,
                "point_alpha": 0.55,
                "threshold_line_width": 2.5,
                "threshold_line_dash": "dashdot",
                "threshold_line_color": "#334155",
            },
        },
    )

    assert spec["plot_type"] == "volcano"
    assert {trace["name"] for trace in spec["data"]} == {"Up", "Down", "Not significant", "Gene labels"}
    assert len(spec["layout"]["shapes"]) == 3
    assert all(shape["line"] == {"color": "#334155", "width": 2.5, "dash": "dashdot"} for shape in spec["layout"]["shapes"])
    up_trace = next(trace for trace in spec["data"] if trace["name"] == "Up")
    assert up_trace["marker"]["size"] == 10
    assert up_trace["marker"]["opacity"] == 0.55
    labels = [trace for trace in spec["data"] if trace["name"] == "Gene labels"][0]
    assert labels["mode"] == "text"
    assert labels["text"] == ["A", "B"]
    assert labels["textfont"]["size"] == 15

    no_threshold_lines = _request(
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
            "params": {"show_threshold_lines": False},
        },
    )
    assert "shapes" not in no_threshold_lines["layout"]
    assert "annotations" not in no_threshold_lines["layout"]


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
        json={
            "source": source,
            "plotType": "heatmap",
            "params": {"top_n": 12, "max_columns": 6, "show_values": True, "value_precision": 1, "cell_gap": 3},
        },
    )
    assert heatmap["plot_type"] == "heatmap"
    assert heatmap["data"][0]["type"] == "heatmap"
    assert len(heatmap["data"][0]["z"]) == 12
    assert len(heatmap["data"][0]["x"]) == 6
    assert heatmap["layout"]["meta"]["dendrogram_guides"]["rows"] is True
    assert heatmap["layout"]["meta"]["dendrogram_guides"]["columns"] is True
    assert len(heatmap["layout"]["shapes"]) > 0
    assert heatmap["data"][0]["texttemplate"] == "%{text}"
    assert heatmap["data"][0]["xgap"] == 3
    assert heatmap["data"][0]["ygap"] == 3
    assert "." in heatmap["data"][0]["text"][0][0]

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
    assert correlation["layout"]["meta"]["dendrogram_guides"]["rows"] is True
    assert len(correlation["layout"]["shapes"]) > 0

    labeled_correlation = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": source,
            "plotType": "correlation",
            "params": {
                "max_columns": 4,
                "cluster_rows": False,
                "cluster_columns": False,
                "show_values": True,
                "value_precision": 3,
                "cell_gap": 2,
            },
        },
    )
    assert labeled_correlation["data"][0]["texttemplate"] == "%{text}"
    assert labeled_correlation["data"][0]["text"][0][0] == "1.000"
    assert labeled_correlation["data"][0]["xgap"] == 2
    assert labeled_correlation["data"][0]["ygap"] == 2
    assert "meta" not in labeled_correlation["layout"]
    assert "shapes" not in labeled_correlation["layout"]


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
        json={
            "source": source,
            "plotType": "histogram",
            "params": {
                "bins": 24,
                "bar_line_width": 2,
                "bar_line_color": "#111827",
                "reference_line_width": 2.4,
                "reference_line_color_mode": "custom",
                "reference_line_color": "#334155",
                "show_mean": True,
                "show_median": True,
                "show_rug": True,
            },
        },
    )
    assert histogram["plot_type"] == "histogram"
    assert histogram["data"][0]["type"] == "histogram"
    assert histogram["data"][0]["nbinsx"] == 24
    assert histogram["data"][0]["marker"]["line"] == {"color": "#111827", "width": 2}
    assert any(trace["name"].endswith("rug") for trace in histogram["data"])
    assert len(histogram["layout"]["shapes"]) >= 2
    assert any(shape["line"]["width"] == 2.4 and shape["line"]["color"] == "#334155" for shape in histogram["layout"]["shapes"])
    assert {annotation["text"].split()[-1] for annotation in histogram["layout"]["annotations"]} >= {"mean", "median"}

    contour = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": source,
            "plotType": "density_contour",
            "params": {
                "contours_coloring": "lines",
                "contour_line_width": 2.5,
                "show_contour_labels": True,
                "contour_start": 0.1,
                "contour_end": 0.9,
                "contour_size": 0.2,
            },
        },
    )
    assert contour["plot_type"] == "density_contour"
    assert contour["data"][0]["type"] == "histogram2dcontour"
    assert contour["data"][0]["contours"] == {
        "coloring": "lines",
        "showlabels": True,
        "start": 0.1,
        "end": 0.9,
        "size": 0.2,
    }
    assert contour["data"][0]["line"]["width"] == 2.5
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
        json={
            "source": source,
            "plotType": "surface_3d",
            "params": {"top_n": 10, "max_columns": 6, "camera": "top", "show_contours": False},
        },
    )
    assert surface["plot_type"] == "surface_3d"
    assert surface["data"][0]["type"] == "surface"
    assert len(surface["data"][0]["z"]) == 10
    assert len(surface["data"][0]["z"][0]) == 6
    assert surface["data"][0]["contours"] == {}
    assert surface["layout"]["scene"]["camera"]["eye"] == {"x": 0.05, "y": 0.05, "z": 2.25}


def test_plot_studio_spec_builds_numeric_color_bubble_plot(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_bubble.csv"
    table_file.write_text(
        "\n".join(
            [
                "label,x,y,size,score",
                "a,1,2,10,0.2",
                "b,2,3,20,0.8",
                "c,3,4,30,1.4",
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
                "name": "Bubble table",
                "type": "unknown_table",
                "dataPath": str(table_file),
            },
            "plotType": "bubble",
            "params": {
                "x": "x",
                "y": "y",
                "size": "size",
                "color": "score",
                "label": "label",
                "size_scale": 36,
                "min_bubble_size": 6,
                "max_bubble_size": 30,
                "color_scale": "plasma",
                "point_alpha": 0.55,
                "marker_line_width": 1.4,
                "marker_line_color": "#111827",
            },
        },
    )

    assert spec["plot_type"] == "bubble"
    trace = spec["data"][0]
    assert trace["type"] == "scattergl"
    assert trace["showlegend"] is False
    assert trace["marker"]["color"] == [0.2, 0.8, 1.4]
    assert trace["marker"]["colorscale"] == "Plasma"
    assert trace["marker"]["colorbar"]["title"] == "score"
    assert trace["marker"]["opacity"] == 0.55
    assert trace["marker"]["line"] == {"color": "#111827", "width": 1.4}
    assert min(trace["marker"]["size"]) == 6
    assert max(trace["marker"]["size"]) == 60


def test_plot_studio_spec_builds_enrichment_dot_plot(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    enrichment_file = allowed_tmp / f"{tmp_path.name}_enrichment.csv"
    enrichment_file.write_text(
        "term,gene_ratio,count,adjusted_p\n"
        "cell cycle checkpoint regulation,3/100,3,0.001\n"
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
            "params": {
                "top_n": 5,
                "sort_by": "adjusted_p",
                "color_transform": "minus_log10",
                "wrap_term_label": True,
                "term_label_width": 12,
                "min_dot_size": 6,
                "max_dot_size": 24,
                "color_scale": "green_white_purple",
                "point_alpha": 0.61,
            },
        },
    )

    assert spec["plot_type"] == "enrichment_dot"
    assert spec["data"][0]["type"] == "scatter"
    assert spec["data"][0]["mode"] == "markers"
    assert len(spec["data"][0]["x"]) == 3
    assert spec["data"][0]["marker"]["colorbar"]["title"] == "-log10(adjusted_p)"
    assert spec["data"][0]["marker"]["colorscale"][0][1] == "#20804f"
    assert spec["data"][0]["marker"]["opacity"] == 0.61
    assert spec["data"][0]["marker"]["color"][0] == 3.0
    assert max(spec["data"][0]["marker"]["size"]) == 24
    assert any("<br>" in label for label in spec["data"][0]["y"])


def test_table_inspection_and_recommendations_handle_numeric_tables() -> None:
    summary = inspect_table(DATA_FILE, max_rows=25)

    assert summary["scanned_rows"] == 25
    assert summary["column_count"] > 2
    assert summary["numeric_columns"]
    assert recommend_plot_types("unknown_table", summary)[0] in {"scatter", "boxplot"}
