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
    assert [stage["id"] for stage in manifest["workflow_stages"]] == [
        "source",
        "plot",
        "mapping",
        "parameters",
        "preview",
        "report",
    ]
    assert "report agent" in manifest["workflow_stages"][-1]["description"]
    recipes = {item["id"]: item for item in manifest["style_recipes"]}
    assert {"publication", "prism_clean", "data_review", "presentation", "exploration"} <= set(recipes)
    assert recipes["publication"]["params"]["format"] == "svg"
    assert recipes["publication"]["params"]["show_grid"] is False
    assert recipes["prism_clean"]["params"]["show_grid"] is False
    assert recipes["prism_clean"]["params"]["axis_line_width"] >= 1.8
    assert recipes["prism_clean"]["params"]["tick_direction"] == "outside"
    assert recipes["data_review"]["params"]["display_modebar"] == "always"
    assert recipes["data_review"]["params"]["selection_tools"] is True
    assert recipes["data_review"]["params"]["show_spikes"] is True
    assert recipes["presentation"]["params"]["title_font_size"] > recipes["publication"]["params"]["title_font_size"]
    assert recipes["exploration"]["params"]["display_modebar"] == "always"
    assert recipes["exploration"]["params"]["selection_tools"] is True
    presets = {item["id"]: item for item in manifest["presets"]}
    assert all(any(group["advanced"] is False for group in preset["parameter_groups"]) for preset in presets.values())
    assert all(any(group["advanced"] is True for group in preset["parameter_groups"]) for preset in presets.values())
    assert {
        "boxplot",
        "grouped_dotplot",
        "raincloud",
        "heatmap",
        "volcano",
        "upset",
        "venn",
        "correlation",
        "histogram",
        "density_curve",
        "ecdf",
        "calendar_heatmap",
        "ridgeline",
        "density_contour",
        "scatter_3d",
        "surface_3d",
        "radar",
        "parallel_coordinates",
        "waterfall",
        "lollipop",
        "ma_plot",
        "qq_plot",
        "forest_plot",
        "roc_curve",
        "pr_curve",
        "kaplan_meier",
        "bland_altman",
        "dose_response",
        "paired_dot",
        "dumbbell",
        "enrichment_bar",
        "composition_bar",
        "donut",
        "sankey",
        "treemap",
        "sunburst",
        "wordcloud",
    } <= set(presets)

    boxplot = presets["boxplot"]
    assert boxplot["engine"] == "plotly"
    assert all(presets[plot_id]["engine"] == "plotly" for plot_id in SUPPORTED_PLOTLY_SPEC_TYPES)
    assert boxplot["category"] == "Distribution"
    assert boxplot["thumbnail"] == "boxplot"
    assert "Group comparison" in boxplot["use_case"]
    assert boxplot["default_params"]["show_points"] is True
    assert boxplot["default_params"]["boxpoints"] == "all"
    assert boxplot["default_params"]["point_size"] == 5
    assert boxplot["default_params"]["point_alpha"] == 0.72
    distribution_group = next(group for group in boxplot["parameter_groups"] if group["id"] == "distribution")
    assert {param["id"] for param in distribution_group["parameters"]} >= {
        "boxpoints",
        "boxmean_mode",
        "quartile_method",
        "whisker_width",
        "box_fill_alpha",
        "box_line_width",
        "show_n_labels",
        "n_label_position",
        "n_label_font_size",
        "n_label_color",
    }
    violin_distribution = next(group for group in presets["violin"]["parameter_groups"] if group["id"] == "distribution")
    assert {param["id"] for param in violin_distribution["parameters"]} >= {
        "point_size",
        "point_alpha",
        "scale_mode",
        "point_position",
        "point_jitter",
        "violin_width",
        "fill_alpha",
        "line_width",
        "show_n_labels",
        "n_label_position",
        "n_label_font_size",
        "n_label_color",
    }
    grouped_dot_points = next(group for group in presets["grouped_dotplot"]["parameter_groups"] if group["id"] == "points")
    assert presets["grouped_dotplot"]["thumbnail"] == "grouped_dotplot"
    assert {param["id"] for param in grouped_dot_points["parameters"]} >= {
        "point_jitter",
        "point_size",
        "point_alpha",
        "summary_stat",
        "summary_line_width",
        "summary_width",
        "sort_groups",
        "show_n_labels",
    }
    raincloud_display = next(group for group in presets["raincloud"]["parameter_groups"] if group["id"] == "cloud")
    assert presets["raincloud"]["thumbnail"] == "raincloud"
    assert {param["id"] for param in raincloud_display["parameters"]} >= {
        "violin_side",
        "violin_width",
        "show_box",
        "box_width",
        "box_offset",
        "show_points",
        "point_jitter",
        "point_size",
        "point_alpha",
        "show_mean",
        "mean_marker_size",
        "sort_groups",
        "max_groups",
    }
    ridge_density = next(group for group in presets["ridgeline"]["parameter_groups"] if group["id"] == "density")
    assert presets["ridgeline"]["thumbnail"] == "ridgeline"
    assert {param["id"] for param in ridge_density["parameters"]} >= {
        "max_groups",
        "density_points",
        "bandwidth",
        "ridge_height",
        "overlap",
        "sort_groups",
        "show_points",
        "point_size",
        "point_alpha",
    }
    statistics_group = next(group for group in boxplot["parameter_groups"] if group["id"] == "statistics")
    assert {param["id"] for param in statistics_group["parameters"]} >= {
        "pairwise_test",
        "multiple_testing",
        "show_p_values",
        "p_value_label_format",
        "p_value_font_size",
        "p_value_color",
        "p_value_bracket_color",
        "p_value_bracket_width",
    }
    assert any(group["id"] == "export" for group in boxplot["parameter_groups"])
    assert any(group["id"] == "labels" for group in boxplot["parameter_groups"])
    assert next(group for group in boxplot["parameter_groups"] if group["id"] == "mapping")["advanced"] is False
    labels_group = next(group for group in boxplot["parameter_groups"] if group["id"] == "labels")
    assert labels_group["advanced"] is True
    assert {param["id"] for param in labels_group["parameters"]} >= {
        "axis_title_font_size",
        "axis_title_color",
        "tick_font_size",
        "tick_color",
        "tick_direction",
        "tick_length",
        "tick_width",
        "tick_line_color",
        "title_font_size",
        "title_color",
        "subtitle_font_size",
        "subtitle_color",
        "x_range_mode",
        "x_min",
        "x_max",
        "y_range_mode",
        "y_min",
        "y_max",
        "x_tick_count",
        "y_tick_count",
        "x_tick_format",
        "y_tick_format",
        "x_tick_prefix",
        "x_tick_suffix",
        "y_tick_prefix",
        "y_tick_suffix",
    }
    guides_group = next(group for group in boxplot["parameter_groups"] if group["id"] == "guides")
    assert guides_group["advanced"] is True
    assert {param["id"] for param in guides_group["parameters"]} >= {
        "show_v_reference",
        "v_reference_value",
        "v_reference_label",
        "v_reference_color",
        "v_reference_width",
        "v_reference_dash",
        "show_h_reference",
        "h_reference_value",
        "h_reference_label",
        "h_reference_color",
        "h_reference_width",
        "h_reference_dash",
    }
    interaction_group = next(group for group in boxplot["parameter_groups"] if group["id"] == "interaction")
    assert interaction_group["advanced"] is True
    assert {param["id"] for param in interaction_group["parameters"]} >= {
        "hover_mode",
        "drag_mode",
        "display_modebar",
        "scroll_zoom",
        "selection_tools",
        "show_spikes",
        "spike_color",
        "spike_width",
        "spike_dash",
        "hover_label_background",
        "hover_label_color",
        "hover_label_font_size",
    }
    export_group = next(group for group in boxplot["parameter_groups"] if group["id"] == "export")
    assert export_group["advanced"] is True
    assert {param["id"] for param in export_group["parameters"]} >= {
        "margin_left",
        "margin_right",
        "margin_top",
        "margin_bottom",
        "export_filename",
    }
    dpi_param = next(param for param in export_group["parameters"] if param["id"] == "dpi")
    format_param = next(param for param in export_group["parameters"] if param["id"] == "format")
    assert "1000" in dpi_param["options"]
    assert set(format_param["options"]) == {"svg", "png", "jpeg", "webp"}
    theme_group = next(group for group in boxplot["parameter_groups"] if group["id"] == "theme")
    assert theme_group["advanced"] is True
    assert {param["id"] for param in theme_group["parameters"]} >= {
        "grid_color",
        "grid_width",
        "show_zero_line",
        "zero_line_color",
        "zero_line_width",
        "axis_line_color",
        "axis_line_width",
        "axis_mirror",
        "legend_title",
        "legend_font_size",
        "legend_background",
        "legend_border_color",
        "legend_border_width",
    }
    scatter_statistics = next(group for group in presets["scatter"]["parameter_groups"] if group["id"] == "statistics")
    assert {param["id"] for param in scatter_statistics["parameters"]} >= {
        "trendline",
        "loess_fraction",
        "show_fit_stats",
        "fit_stats_position",
        "fit_stats_precision",
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
        "aggregate_replicates",
        "summary_stat",
        "error_bar",
        "error_cap_width",
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
        "p_value_label_format",
        "p_value_font_size",
        "p_value_color",
        "p_value_bracket_color",
        "p_value_bracket_width",
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
    waterfall_ranking = next(group for group in presets["waterfall"]["parameter_groups"] if group["id"] == "ranking")
    assert {param["id"] for param in waterfall_ranking["parameters"]} >= {
        "sort_by",
        "top_n",
        "orientation",
        "log2fc_threshold",
        "p_value_threshold",
    }
    lollipop_ranking = next(group for group in presets["lollipop"]["parameter_groups"] if group["id"] == "ranking")
    assert presets["lollipop"]["thumbnail"] == "lollipop"
    assert {param["id"] for param in lollipop_ranking["parameters"]} >= {
        "sort_by",
        "top_n",
        "orientation",
        "baseline",
        "stem_width",
        "stem_color",
        "point_size",
        "point_alpha",
        "show_value_labels",
        "value_precision",
    }
    ma_thresholds = next(group for group in presets["ma_plot"]["parameter_groups"] if group["id"] == "thresholds")
    assert {param["id"] for param in ma_thresholds["parameters"]} >= {
        "x_log",
        "log2fc_threshold",
        "p_value_threshold",
        "show_threshold_lines",
        "label_top_n",
    }
    qq_diagnostics = next(group for group in presets["qq_plot"]["parameter_groups"] if group["id"] == "diagnostics")
    assert {param["id"] for param in qq_diagnostics["parameters"]} >= {
        "max_points",
        "confidence_band",
        "confidence_level",
        "show_diagonal",
        "label_top_n",
    }
    forest_statistics = next(group for group in presets["forest_plot"]["parameter_groups"] if group["id"] == "statistics")
    assert {param["id"] for param in forest_statistics["parameters"]} >= {
        "sort_by",
        "top_n",
        "reference_value",
        "show_reference_line",
    }
    roc_diagnostics = next(group for group in presets["roc_curve"]["parameter_groups"] if group["id"] == "diagnostics")
    assert {param["id"] for param in roc_diagnostics["parameters"]} >= {
        "direction",
        "show_diagonal",
        "show_auc",
        "show_threshold_points",
        "threshold_count",
    }
    pr_diagnostics = next(group for group in presets["pr_curve"]["parameter_groups"] if group["id"] == "diagnostics")
    assert {param["id"] for param in pr_diagnostics["parameters"]} >= {
        "direction",
        "show_baseline",
        "show_average_precision",
        "show_threshold_points",
        "threshold_count",
    }
    km_survival = next(group for group in presets["kaplan_meier"]["parameter_groups"] if group["id"] == "survival")
    assert {param["id"] for param in km_survival["parameters"]} >= {
        "curve_mode",
        "show_censor_marks",
        "show_logrank",
        "show_risk_table",
        "time_unit",
    }
    bland_agreement = next(group for group in presets["bland_altman"]["parameter_groups"] if group["id"] == "agreement")
    assert {param["id"] for param in bland_agreement["parameters"]} >= {
        "difference_mode",
        "show_bias_line",
        "show_limits",
        "limits_sd",
        "show_zero_line",
    }
    dose_curve = next(group for group in presets["dose_response"]["parameter_groups"] if group["id"] == "curve")
    assert {param["id"] for param in dose_curve["parameters"]} >= {
        "response_mode",
        "log_x",
        "normalize_response",
        "show_curve",
        "show_half_max",
        "line_shape",
    }
    paired_display = next(group for group in presets["paired_dot"]["parameter_groups"] if group["id"] == "paired")
    assert {param["id"] for param in paired_display["parameters"]} >= {
        "connect_pairs",
        "show_summary",
        "summary_stat",
        "max_subjects",
    }
    dumbbell_display = next(group for group in presets["dumbbell"]["parameter_groups"] if group["id"] == "paired")
    assert presets["dumbbell"]["thumbnail"] == "dumbbell"
    assert {param["id"] for param in dumbbell_display["parameters"]} >= {
        "sort_by",
        "top_n",
        "orientation",
        "start_label",
        "end_label",
        "line_width",
        "color_by_group",
        "point_size",
        "point_alpha",
        "show_delta_labels",
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
    ecdf_display = next(group for group in presets["ecdf"]["parameter_groups"] if group["id"] == "distribution")
    assert presets["ecdf"]["thumbnail"] == "ecdf"
    assert {param["id"] for param in ecdf_display["parameters"]} >= {
        "y_mode",
        "y_units",
        "line_shape",
        "line_width",
        "show_points",
        "point_size",
        "point_alpha",
        "show_median",
        "median_line_dash",
        "max_groups",
        "sort_groups",
    }
    density_curve_display = next(group for group in presets["density_curve"]["parameter_groups"] if group["id"] == "density")
    assert presets["density_curve"]["thumbnail"] == "density_curve"
    assert {param["id"] for param in density_curve_display["parameters"]} >= {
        "density_points",
        "bandwidth",
        "normalize",
        "fill",
        "fill_alpha",
        "line_width",
        "show_rug",
        "rug_size",
        "rug_alpha",
        "show_median",
        "median_line_dash",
        "max_groups",
        "sort_groups",
    }
    calendar_display = next(group for group in presets["calendar_heatmap"]["parameter_groups"] if group["id"] == "calendar")
    assert presets["calendar_heatmap"]["thumbnail"] == "calendar_heatmap"
    assert {param["id"] for param in calendar_display["parameters"]} >= {
        "aggregation",
        "week_start",
        "color_scale",
        "show_values",
        "value_precision",
        "missing_color",
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
    enrichment_bar_terms = next(group for group in presets["enrichment_bar"]["parameter_groups"] if group["id"] == "terms")
    assert presets["enrichment_bar"]["thumbnail"] == "enrichment_bar"
    assert {param["id"] for param in enrichment_bar_terms["parameters"]} >= {
        "top_n",
        "sort_by",
        "orientation",
        "bar_opacity",
        "bar_line_width",
        "show_value_labels",
        "value_precision",
        "color_scale",
    }
    sankey_flow = next(group for group in presets["sankey"]["parameter_groups"] if group["id"] == "flow")
    assert presets["sankey"]["thumbnail"] == "sankey"
    assert {param["id"] for param in sankey_flow["parameters"]} >= {
        "top_n",
        "min_value",
        "sort_by",
        "arrangement",
        "node_pad",
        "node_thickness",
        "link_opacity",
        "label_font_size",
    }
    composition_display = next(group for group in presets["composition_bar"]["parameter_groups"] if group["id"] == "composition")
    assert presets["composition_bar"]["thumbnail"] == "composition_bar"
    assert {param["id"] for param in composition_display["parameters"]} >= {
        "top_n",
        "normalize",
        "other_label",
        "sort_samples",
        "sort_categories",
        "orientation",
        "bar_mode",
        "show_percent_axis",
        "show_legend",
    }
    donut_display = next(group for group in presets["donut"]["parameter_groups"] if group["id"] == "composition")
    assert presets["donut"]["thumbnail"] == "donut"
    assert {param["id"] for param in donut_display["parameters"]} >= {
        "top_n",
        "other_label",
        "sort_by",
        "hole",
        "textinfo",
        "textposition",
        "pull_largest",
        "rotation",
        "show_legend",
    }
    treemap_terms = next(group for group in presets["treemap"]["parameter_groups"] if group["id"] == "terms")
    assert presets["treemap"]["thumbnail"] == "treemap"
    assert {param["id"] for param in treemap_terms["parameters"]} >= {
        "top_n",
        "branchvalues",
        "textinfo",
        "tiling",
        "color_scale",
    }
    sunburst_terms = next(group for group in presets["sunburst"]["parameter_groups"] if group["id"] == "terms")
    assert presets["sunburst"]["thumbnail"] == "sunburst"
    assert {param["id"] for param in sunburst_terms["parameters"]} >= {
        "top_n",
        "branchvalues",
        "maxdepth",
        "textinfo",
        "color_scale",
    }
    wordcloud_terms = next(group for group in presets["wordcloud"]["parameter_groups"] if group["id"] == "terms")
    assert presets["wordcloud"]["thumbnail"] == "wordcloud"
    assert {param["id"] for param in wordcloud_terms["parameters"]} >= {
        "top_n",
        "sort_by",
        "min_font_size",
        "max_font_size",
        "cloud_width",
        "cloud_height",
        "rotate_fraction",
        "color_scale",
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
    radar_profile = next(group for group in presets["radar"]["parameter_groups"] if group["id"] == "profile")
    assert {param["id"] for param in radar_profile["parameters"]} >= {
        "max_series",
        "aggregation",
        "normalize",
        "fill",
        "line_width",
        "marker_size",
    }
    parallel_dimensions = next(group for group in presets["parallel_coordinates"]["parameter_groups"] if group["id"] == "dimensions")
    assert {param["id"] for param in parallel_dimensions["parameters"]} >= {
        "max_dimensions",
        "max_rows",
        "color_scale",
        "show_colorbar",
        "line_opacity",
    }


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
                "show_zero_line": False,
                "zero_line_color": "#94a3b8",
                "zero_line_width": 2,
                "axis_line": True,
                "axis_line_color": "#0f172a",
                "axis_line_width": 2.2,
                "axis_mirror": "ticks",
                "legend_title": "Sample group",
                "legend_font_size": 15,
                "legend_background": "rgba(255,255,255,0.8)",
                "legend_border_color": "#cbd5e1",
                "legend_border_width": 1.5,
                "title_font_size": 20,
                "title_color": "#0f172a",
                "subtitle_font_size": 13,
                "subtitle_color": "#64748b",
                "axis_title_font_size": 17,
                "axis_title_color": "#172554",
                "tick_font_size": 11,
                "tick_color": "#475569",
                "tick_direction": "inside",
                "tick_length": 8,
                "tick_width": 1.5,
                "tick_line_color": "#0f172a",
                "x_range_mode": "custom",
                "x_min": -2,
                "x_max": 2,
                "y_range_mode": "custom",
                "y_min": 0,
                "y_max": 12,
                "x_tick_count": 7,
                "y_tick_count": 6,
                "x_tick_format": ".1f",
                "y_tick_format": ".2f",
                "x_tick_prefix": "PC",
                "x_tick_suffix": "",
                "y_tick_prefix": "",
                "y_tick_suffix": "%",
                "show_v_reference": True,
                "v_reference_value": 1.5,
                "v_reference_label": "cutoff",
                "v_reference_color": "#7c3aed",
                "v_reference_width": 2.1,
                "v_reference_dash": "dot",
                "show_h_reference": True,
                "h_reference_value": 6,
                "h_reference_label": "target",
                "h_reference_color": "#be123c",
                "h_reference_width": 1.8,
                "h_reference_dash": "dashdot",
                "hover_mode": "x unified",
                "drag_mode": "pan",
                "display_modebar": "always",
                "scroll_zoom": True,
                "selection_tools": True,
                "show_spikes": True,
                "spike_color": "#334155",
                "spike_width": 2.4,
                "spike_dash": "dash",
                "hover_label_background": "#020617",
                "hover_label_color": "#f8fafc",
                "hover_label_font_size": 15,
                "export_filename": "QC heatmap v1",
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
    assert "filename=QC heatmap v1" in report["agent_context"]["parameter_summary"]["export"]
    assert any("Rendered images are not inspected" in item for item in report["report"]["limitations"])
    assert report["agent_context"]["purpose"].startswith("LLM-readable")
    assert report["agent_context"]["plot"]["id"] == "heatmap"
    assert report["agent_context"]["table"]["filename"] == DATA_FILE.name
    assert report["agent_context"]["params"]["title"] == "QC heatmap"
    assert "dendrogram guides shown" in report["agent_context"]["parameter_summary"]["display"]
    assert "grid shown=False" in report["agent_context"]["parameter_summary"]["display"]
    assert "grid color=#dbeafe" in report["agent_context"]["parameter_summary"]["display"]
    assert "grid width=1.8" in report["agent_context"]["parameter_summary"]["display"]
    assert "zero line shown=False" in report["agent_context"]["parameter_summary"]["display"]
    assert "zero line color=#94a3b8" in report["agent_context"]["parameter_summary"]["display"]
    assert "zero line width=2" in report["agent_context"]["parameter_summary"]["display"]
    assert "axis line shown=True" in report["agent_context"]["parameter_summary"]["display"]
    assert "axis line color=#0f172a" in report["agent_context"]["parameter_summary"]["display"]
    assert "axis line width=2.2" in report["agent_context"]["parameter_summary"]["display"]
    assert "axis mirror=ticks" in report["agent_context"]["parameter_summary"]["display"]
    assert "legend title='Sample group'" in report["agent_context"]["parameter_summary"]["display"]
    assert "legend font size=15" in report["agent_context"]["parameter_summary"]["display"]
    assert "legend background=rgba(255,255,255,0.8)" in report["agent_context"]["parameter_summary"]["display"]
    assert "legend border color=#cbd5e1" in report["agent_context"]["parameter_summary"]["display"]
    assert "legend border width=1.5" in report["agent_context"]["parameter_summary"]["display"]
    assert "title size=20" in report["agent_context"]["parameter_summary"]["display"]
    assert "title color=#0f172a" in report["agent_context"]["parameter_summary"]["display"]
    assert "subtitle size=13" in report["agent_context"]["parameter_summary"]["display"]
    assert "subtitle color=#64748b" in report["agent_context"]["parameter_summary"]["display"]
    assert "axis title size=17" in report["agent_context"]["parameter_summary"]["display"]
    assert "axis title color=#172554" in report["agent_context"]["parameter_summary"]["display"]
    assert "tick label size=11" in report["agent_context"]["parameter_summary"]["display"]
    assert "tick label color=#475569" in report["agent_context"]["parameter_summary"]["display"]
    assert "tick direction=inside" in report["agent_context"]["parameter_summary"]["display"]
    assert "tick length=8" in report["agent_context"]["parameter_summary"]["display"]
    assert "tick width=1.5" in report["agent_context"]["parameter_summary"]["display"]
    assert "tick line color=#0f172a" in report["agent_context"]["parameter_summary"]["display"]
    assert "x range=-2 to 2" in report["agent_context"]["parameter_summary"]["display"]
    assert "y range=0 to 12" in report["agent_context"]["parameter_summary"]["display"]
    assert "x tick count=7" in report["agent_context"]["parameter_summary"]["display"]
    assert "y tick count=6" in report["agent_context"]["parameter_summary"]["display"]
    assert "x tick format=.1f" in report["agent_context"]["parameter_summary"]["display"]
    assert "y tick format=.2f" in report["agent_context"]["parameter_summary"]["display"]
    assert "x tick prefix=PC" in report["agent_context"]["parameter_summary"]["display"]
    assert "y tick suffix=%" in report["agent_context"]["parameter_summary"]["display"]
    assert "vertical guide=1.5" in report["agent_context"]["parameter_summary"]["display"]
    assert "vertical guide label='cutoff'" in report["agent_context"]["parameter_summary"]["display"]
    assert "vertical guide color=#7c3aed" in report["agent_context"]["parameter_summary"]["display"]
    assert "vertical guide width=2.1" in report["agent_context"]["parameter_summary"]["display"]
    assert "vertical guide dash=dot" in report["agent_context"]["parameter_summary"]["display"]
    assert "horizontal guide=6" in report["agent_context"]["parameter_summary"]["display"]
    assert "horizontal guide label='target'" in report["agent_context"]["parameter_summary"]["display"]
    assert "horizontal guide color=#be123c" in report["agent_context"]["parameter_summary"]["display"]
    assert "horizontal guide width=1.8" in report["agent_context"]["parameter_summary"]["display"]
    assert "horizontal guide dash=dashdot" in report["agent_context"]["parameter_summary"]["display"]
    assert "hover mode=x unified" in sections["Parameter notes"]["text"]
    assert "drag mode=pan" in sections["Parameter notes"]["text"]
    assert "toolbar=always" in sections["Parameter notes"]["text"]
    assert "scroll zoom=True" in report["agent_context"]["parameter_summary"]["interaction"]
    assert "selection tools=True" in report["agent_context"]["parameter_summary"]["interaction"]
    assert "axis hover guide=True" in report["agent_context"]["parameter_summary"]["interaction"]
    assert "hover guide color=#334155" in report["agent_context"]["parameter_summary"]["interaction"]
    assert "hover guide width=2.4" in report["agent_context"]["parameter_summary"]["interaction"]
    assert "hover guide dash=dash" in report["agent_context"]["parameter_summary"]["interaction"]
    assert "hover label background=#020617" in report["agent_context"]["parameter_summary"]["interaction"]
    assert "hover label color=#f8fafc" in report["agent_context"]["parameter_summary"]["interaction"]
    assert "hover label size=15" in report["agent_context"]["parameter_summary"]["interaction"]
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
                "meta": {
                    "comparison_label": "B vs A",
                    "diff_gene_count": 128,
                    "tested_gene_count": 2000,
                    "method": "r_transcriptomics_differential",
                    "p_value_threshold": 0.05,
                    "log2fc_threshold": 1.0,
                    "r_script_file": "E:/workspace/Yzwcloud/src/yzwcloud/r/differential_transcriptomics.R",
                },
            },
            "plotType": "Volcano",
        },
    )

    assert report["selected_plot"]["id"] == "volcano"
    assert "volcano" in report["recommended_plot_ids"]
    assert report["table_summary"] is None
    sections = {section["title"]: section for section in report["report"]["sections"]}
    assert "128 significant feature(s) out of 2000 tested" in sections["Signals to inspect"]["text"]
    assert "method=r_transcriptomics_differential" in sections["Signals to inspect"]["text"]
    assert "R script=differential_transcriptomics.R" in sections["Signals to inspect"]["text"]
    assert any("metadata-only" in item for item in report["report"]["limitations"])
    guidance = report["agent_context"]["report_guidance"]
    assert "source metadata" in guidance["evidence_sources"]
    assert any("method=r_transcriptomics_differential" in item for item in guidance["safe_claims"])
    assert any("differential_transcriptomics.R" in item for item in guidance["safe_claims"])
    assert any("metadata-only" in item for item in guidance["safe_claims"])
    assert any("Do not infer any numeric distribution" in item for item in guidance["avoid_claims"])


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
                "p_value_label_format": "stars",
                "p_value_font_size": 14,
                "p_value_color": "#552211",
                "p_value_bracket_color": "#114477",
                "p_value_bracket_width": 2.4,
            },
        },
    )
    bar_sections = {section["title"]: section["text"] for section in bar_report["report"]["sections"]}
    assert "aggregation=mean" in bar_sections["Parameter notes"]
    assert "error bar=ci95" in bar_sections["Parameter notes"]
    assert "pairwise test=wilcoxon" in bar_sections["Parameter notes"]
    assert "multiple testing=bonferroni" in bar_sections["Parameter notes"]
    assert "p-values shown on plot" in bar_report["agent_context"]["parameter_summary"]["statistics"]
    assert "p-value label format=stars" in bar_report["agent_context"]["parameter_summary"]["statistics"]
    assert "p-value font size=14" in bar_report["agent_context"]["parameter_summary"]["display"]
    assert "p-value color=#552211" in bar_report["agent_context"]["parameter_summary"]["display"]
    assert "p-value bracket color=#114477" in bar_report["agent_context"]["parameter_summary"]["display"]
    assert "p-value bracket width=2.4" in bar_report["agent_context"]["parameter_summary"]["display"]

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

    grouped_dot_report = _request(
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
            "plotType": "grouped_dotplot",
            "params": {
                "group": "condition",
                "y": "value",
                "point_jitter": 0.25,
                "point_size": 8,
                "point_alpha": 0.66,
                "summary_stat": "median",
                "summary_line_width": 3,
                "summary_line_color_mode": "custom",
                "sort_groups": "median_desc",
                "show_n_labels": True,
            },
        },
    )
    grouped_dot_sections = {section["title"]: section["text"] for section in grouped_dot_report["report"]["sections"]}
    assert "individual sample values" in grouped_dot_sections["Figure interpretation"]
    grouped_dot_summary = grouped_dot_report["agent_context"]["parameter_summary"]
    assert "value=value" in grouped_dot_summary["statistics"]
    assert "group=condition" in grouped_dot_summary["statistics"]
    assert "summary=median" in grouped_dot_summary["statistics"]
    assert "point jitter=0.25" in grouped_dot_summary["display"]
    assert "summary color mode=custom" in grouped_dot_summary["display"]

    raincloud_report = _request(
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
            "plotType": "raincloud",
            "params": {
                "group": "condition",
                "y": "value",
                "violin_side": "negative",
                "violin_width": 0.8,
                "show_box": True,
                "show_points": True,
                "point_jitter": 0.25,
                "point_size": 6,
                "point_alpha": 0.55,
                "show_mean": True,
                "sort_groups": "median_desc",
                "max_groups": 8,
            },
        },
    )
    raincloud_sections = {section["title"]: section["text"] for section in raincloud_report["report"]["sections"]}
    assert "combined distribution shape" in raincloud_sections["Figure interpretation"]
    raincloud_summary = raincloud_report["agent_context"]["parameter_summary"]
    assert "value=value" in raincloud_summary["statistics"]
    assert "group=condition" in raincloud_summary["statistics"]
    assert "mean marker=True" in raincloud_summary["statistics"]
    assert "violin side=negative" in raincloud_summary["display"]
    assert "box shown=True" in raincloud_summary["display"]
    assert "raw points shown=True" in raincloud_summary["display"]

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

    density_report = _request(
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
            "plotType": "density_curve",
            "params": {
                "x": "value",
                "group": "condition",
                "density_points": 120,
                "bandwidth": "auto",
                "normalize": "peak",
                "fill": True,
                "fill_alpha": 0.33,
                "line_width": 3,
                "show_rug": True,
                "show_median": True,
                "max_groups": 8,
                "sort_groups": "median_desc",
            },
        },
    )
    density_sections = {section["title"]: section["text"] for section in density_report["report"]["sections"]}
    assert "smoothed distribution shape" in density_sections["Figure interpretation"]
    density_summary = density_report["agent_context"]["parameter_summary"]
    assert "value=value" in density_summary["statistics"]
    assert "group=condition" in density_summary["statistics"]
    assert "normalization=peak" in density_summary["statistics"]
    assert "median guides=True" in density_summary["statistics"]
    assert "density resolution=120" in density_summary["display"]
    assert "filled curve=True" in density_summary["display"]
    assert "rug marks shown=True" in density_summary["display"]

    ecdf_report = _request(
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
            "plotType": "ecdf",
            "params": {
                "x": "value",
                "group": "condition",
                "y_mode": "survival",
                "y_units": "proportion",
                "line_shape": "hv",
                "line_width": 3,
                "show_points": True,
                "show_median": True,
                "max_groups": 8,
                "sort_groups": "median_desc",
            },
        },
    )
    ecdf_sections = {section["title"]: section["text"] for section in ecdf_report["report"]["sections"]}
    assert "cumulative distribution shifts" in ecdf_sections["Figure interpretation"]
    ecdf_summary = ecdf_report["agent_context"]["parameter_summary"]
    assert "value=value" in ecdf_summary["statistics"]
    assert "group=condition" in ecdf_summary["statistics"]
    assert "mode=survival" in ecdf_summary["statistics"]
    assert "median guides=True" in ecdf_summary["statistics"]
    assert "units=proportion" in ecdf_summary["display"]
    assert "points shown=True" in ecdf_summary["display"]

    ridgeline_report = _request(
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
            "plotType": "ridgeline",
            "params": {
                "x": "value",
                "group": "condition",
                "max_groups": 8,
                "density_points": 120,
                "bandwidth": "auto",
                "ridge_height": 0.9,
                "overlap": 0.6,
                "sort_groups": "median_desc",
                "show_points": True,
            },
        },
    )
    ridgeline_sections = {section["title"]: section["text"] for section in ridgeline_report["report"]["sections"]}
    assert "stacked group distribution shapes" in ridgeline_sections["Figure interpretation"]
    ridgeline_summary = ridgeline_report["agent_context"]["parameter_summary"]
    assert "value=value" in ridgeline_summary["statistics"]
    assert "group=condition" in ridgeline_summary["statistics"]
    assert "density resolution=120" in ridgeline_summary["display"]
    assert "group sorting=median_desc" in ridgeline_summary["display"]
    assert "rug points shown=True" in ridgeline_summary["display"]

    calendar_file = allowed_tmp / f"{tmp_path.name}_report_calendar.csv"
    calendar_file.write_text(
        "date,value\n2026-01-01,4\n2026-01-02,7\n2026-01-02,3\n",
        encoding="utf-8",
    )
    calendar_report = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "name": "Sampling calendar",
                "type": "unknown_table",
                "dataPath": str(calendar_file),
            },
            "plotType": "calendar_heatmap",
            "params": {
                "date_column": "date",
                "value_column": "value",
                "aggregation": "sum",
                "week_start": "monday",
                "color_scale": "ylorrd",
                "show_values": True,
                "missing_color": "#f1f5f9",
            },
        },
    )
    calendar_sections = {section["title"]: section["text"] for section in calendar_report["report"]["sections"]}
    assert "daily temporal intensity" in calendar_sections["Figure interpretation"]
    calendar_summary = calendar_report["agent_context"]["parameter_summary"]
    assert "date=date" in calendar_summary["statistics"]
    assert "value=value" in calendar_summary["statistics"]
    assert "aggregation=sum" in calendar_summary["statistics"]
    assert "week starts=monday" in calendar_summary["display"]
    assert "cell values shown=True" in calendar_summary["display"]


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


def test_plot_studio_report_summarizes_waterfall_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_waterfall.csv"
    table_file.write_text(
        "gene,log2fc,p_value,group\nA,2.1,0.001,up\nB,-1.8,0.002,down\nC,0.2,0.9,flat\n",
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
                "name": "Diff result",
                "type": "diff_result",
                "dataPath": str(table_file),
            },
            "plotType": "waterfall",
            "params": {
                "value_column": "log2fc",
                "sort_by": "p_value",
                "top_n": 25,
                "orientation": "horizontal",
                "color_mode": "significance",
                "log2fc_threshold": 1.2,
                "p_value_threshold": 0.01,
                "show_zero_line": True,
                "show_value_labels": True,
                "bar_opacity": 0.62,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "ranked signed effects" in sections["Figure interpretation"]
    assert "signed value=log2fc" in sections["Parameter notes"]
    summary = report["agent_context"]["parameter_summary"]
    assert "sort by=p_value" in summary["display"]
    assert "top bars=25" in summary["display"]
    assert "bar opacity=0.62" in summary["display"]


def test_plot_studio_report_summarizes_lollipop_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_lollipop.csv"
    table_file.write_text("gene,score,group,size\nA,2.5,up,10\nB,-1.4,down,4\n", encoding="utf-8")
    client = TestClient(app)

    report = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "name": "Ranked genes",
                "type": "diff_result",
                "dataPath": str(table_file),
            },
            "plotType": "lollipop",
            "params": {
                "value_column": "score",
                "sort_by": "value_desc",
                "top_n": 25,
                "orientation": "horizontal",
                "baseline": 0,
                "stem_width": 2.2,
                "stem_color": "#64748b",
                "point_size": 12,
                "point_alpha": 0.7,
                "show_value_labels": True,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "top points=25" in sections["Parameter notes"]
    summary = report["agent_context"]["parameter_summary"]
    assert "value=score" in summary["statistics"]
    assert "baseline=0" in summary["statistics"]
    assert "stem width=2.2" in summary["display"]
    assert "point opacity=0.7" in summary["display"]
    assert "value labels shown=True" in summary["display"]


def test_plot_studio_report_summarizes_ma_plot_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_ma.csv"
    table_file.write_text(
        "gene,baseMean,log2fc,p_value\nA,120,2.1,0.001\nB,70,-1.8,0.002\nC,9,0.2,0.9\n",
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
                "name": "Diff result",
                "type": "diff_result",
                "dataPath": str(table_file),
            },
            "plotType": "ma_plot",
            "params": {
                "mean_column": "baseMean",
                "log2fc_column": "log2fc",
                "x_log": True,
                "log2fc_threshold": 1.2,
                "p_value_threshold": 0.01,
                "show_threshold_lines": True,
                "label_top_n": 4,
                "point_size": 8,
                "point_alpha": 0.5,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "mean-dependent fold-change patterns" in sections["Figure interpretation"]
    assert "mean abundance=baseMean" in sections["Parameter notes"]
    summary = report["agent_context"]["parameter_summary"]
    assert "log x-axis=True" in summary["display"]
    assert "top labels=4" in summary["display"]
    assert "point opacity=0.5" in summary["display"]


def test_plot_studio_report_summarizes_qq_plot_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_qq.csv"
    table_file.write_text(
        "gene,p_value,comparison\nA,0.001,B_vs_A\nB,0.002,B_vs_A\nC,0.9,B_vs_A\n",
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
                "name": "Diff result",
                "type": "diff_result",
                "dataPath": str(table_file),
            },
            "plotType": "qq_plot",
            "params": {
                "p_value_column": "p_value",
                "group": "comparison",
                "max_points": 1000,
                "confidence_band": True,
                "confidence_level": "0.99",
                "show_diagonal": True,
                "label_top_n": 6,
                "point_size": 7,
                "point_alpha": 0.55,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "p-value calibration" in sections["Figure interpretation"]
    assert "p-value column=p_value" in sections["Parameter notes"]
    summary = report["agent_context"]["parameter_summary"]
    assert "confidence band=True" in summary["display"]
    assert "confidence level=0.99" in summary["statistics"]
    assert "point opacity=0.55" in summary["display"]


def test_plot_studio_report_summarizes_forest_plot_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_forest.csv"
    table_file.write_text(
        "term,effect,ci_low,ci_high,p_value,group\nPathway A,1.2,0.4,2.0,0.01,A\nPathway B,-0.8,-1.4,-0.2,0.03,B\n",
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
                "name": "Effect result",
                "type": "diff_result",
                "dataPath": str(table_file),
            },
            "plotType": "forest_plot",
            "params": {
                "effect_column": "effect",
                "ci_low_column": "ci_low",
                "ci_high_column": "ci_high",
                "sort_by": "abs_effect",
                "top_n": 12,
                "reference_value": 0,
                "show_reference_line": True,
                "color_mode": "group",
                "point_size": 10,
                "line_width": 2.4,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "effect-size direction" in sections["Figure interpretation"]
    assert "effect=effect" in sections["Parameter notes"]
    summary = report["agent_context"]["parameter_summary"]
    assert "sort by=abs_effect" in summary["display"]
    assert "reference=0" in summary["statistics"]
    assert "interval line width=2.4" in summary["display"]


def test_plot_studio_report_summarizes_roc_curve_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_roc.csv"
    table_file.write_text(
        "sample,score,label,model\nS1,0.95,case,A\nS2,0.82,case,A\nS3,0.44,control,A\nS4,0.12,control,A\n",
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
                "name": "Biomarker score",
                "type": "biomarker_result",
                "dataPath": str(table_file),
            },
            "plotType": "roc_curve",
            "params": {
                "score_column": "score",
                "label_column": "label",
                "positive_label": "case",
                "direction": "higher_positive",
                "show_diagonal": True,
                "show_auc": True,
                "show_threshold_points": True,
                "threshold_count": 6,
                "line_width": 3.1,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "classifier discrimination" in sections["Figure interpretation"]
    assert "score=score" in sections["Parameter notes"]
    summary = report["agent_context"]["parameter_summary"]
    assert "positive label=case" in summary["statistics"]
    assert "threshold points=True" in summary["display"]
    assert "line width=3.1" in summary["display"]


def test_plot_studio_report_summarizes_pr_curve_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_pr.csv"
    table_file.write_text(
        "sample,score,label,model\nS1,0.95,case,A\nS2,0.82,case,A\nS3,0.44,control,A\nS4,0.12,control,A\n",
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
                "name": "Biomarker score",
                "type": "biomarker_result",
                "dataPath": str(table_file),
            },
            "plotType": "pr_curve",
            "params": {
                "score_column": "score",
                "label_column": "label",
                "positive_label": "case",
                "direction": "higher_positive",
                "show_baseline": True,
                "show_average_precision": True,
                "show_threshold_points": True,
                "threshold_count": 6,
                "line_width": 3.1,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "precision-recall tradeoffs" in sections["Figure interpretation"]
    assert "score=score" in sections["Parameter notes"]
    summary = report["agent_context"]["parameter_summary"]
    assert "positive label=case" in summary["statistics"]
    assert "prevalence baseline=True" in summary["display"]
    assert "average precision annotation=True" in summary["display"]


def test_plot_studio_report_summarizes_kaplan_meier_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_km.csv"
    table_file.write_text(
        "sample,time,event,group\nS1,5,1,A\nS2,8,0,A\nS3,12,1,A\nS4,4,1,B\nS5,9,1,B\nS6,13,0,B\n",
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
                "name": "Survival table",
                "type": "survival_result",
                "dataPath": str(table_file),
            },
            "plotType": "kaplan_meier",
            "params": {
                "time_column": "time",
                "event_column": "event",
                "group": "group",
                "event_value": "1",
                "show_censor_marks": True,
                "show_logrank": True,
                "show_risk_table": True,
                "curve_mode": "survival",
                "line_width": 3.0,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "group survival separation" in sections["Figure interpretation"]
    assert "time=time" in sections["Parameter notes"]
    summary = report["agent_context"]["parameter_summary"]
    assert "event=event" in summary["statistics"]
    assert "censor marks=True" in summary["display"]
    assert "log-rank shown=True" in summary["statistics"]


def test_plot_studio_report_summarizes_bland_altman_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_bland.csv"
    table_file.write_text("sample,method_a,method_b\nS1,10,11\nS2,12,11.5\nS3,9,10\n", encoding="utf-8")
    client = TestClient(app)

    report = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "name": "Agreement table",
                "type": "agreement_result",
                "dataPath": str(table_file),
            },
            "plotType": "bland_altman",
            "params": {
                "x_method": "method_a",
                "y_method": "method_b",
                "difference_mode": "y_minus_x",
                "show_bias_line": True,
                "show_limits": True,
                "limits_sd": 1.96,
                "point_size": 9,
                "line_width": 2.0,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "measurement agreement" in sections["Figure interpretation"]
    assert "method A=method_a" in sections["Parameter notes"]
    summary = report["agent_context"]["parameter_summary"]
    assert "method B=method_b" in summary["statistics"]
    assert "limits shown=True" in summary["display"]
    assert "reference line width=2.0" in summary["display"]


def test_plot_studio_report_summarizes_dose_response_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_dose.csv"
    table_file.write_text(
        "compound,concentration,response\nA,0.1,95\nA,1,71\nA,10,32\nA,100,8\n",
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
                "name": "Dose response",
                "type": "dose_response_result",
                "dataPath": str(table_file),
            },
            "plotType": "dose_response",
            "params": {
                "dose_column": "concentration",
                "response_column": "response",
                "group": "compound",
                "response_mode": "inhibition",
                "log_x": True,
                "normalize_response": False,
                "show_half_max": True,
                "line_width": 3.0,
                "point_size": 9,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "dose-dependent response direction" in sections["Figure interpretation"]
    assert "dose=concentration" in sections["Parameter notes"]
    summary = report["agent_context"]["parameter_summary"]
    assert "response=response" in summary["statistics"]
    assert "log dose axis=True" in summary["display"]
    assert "half-max guide=True" in summary["display"]


def test_plot_studio_report_summarizes_paired_dot_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_paired.csv"
    table_file.write_text(
        "subject,condition,value\nS1,before,10\nS1,after,14\nS2,before,8\nS2,after,9\n",
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
                "name": "Paired table",
                "type": "paired_result",
                "dataPath": str(table_file),
            },
            "plotType": "paired_dot",
            "params": {
                "value_column": "value",
                "condition_column": "condition",
                "subject_column": "subject",
                "connect_pairs": True,
                "show_summary": True,
                "summary_stat": "median",
                "max_subjects": 50,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "within-subject direction of change" in sections["Figure interpretation"]
    assert "value=value" in sections["Parameter notes"]
    summary = report["agent_context"]["parameter_summary"]
    assert "subject=subject" in summary["statistics"]
    assert "paired lines=True" in summary["display"]
    assert "summary=median" in summary["statistics"]


def test_plot_studio_report_summarizes_dumbbell_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_dumbbell.csv"
    table_file.write_text(
        "feature,before,after,group\nA,1,3,up\nB,4,2,down\nC,2,2.5,flat\n",
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
                "name": "Two-condition table",
                "type": "paired_result",
                "dataPath": str(table_file),
            },
            "plotType": "dumbbell",
            "params": {
                "label_column": "feature",
                "start_column": "before",
                "end_column": "after",
                "group": "group",
                "sort_by": "delta_abs",
                "top_n": 2,
                "orientation": "horizontal",
                "start_label": "Start",
                "end_label": "End",
                "line_width": 2.4,
                "color_by_group": True,
                "point_size": 11,
                "point_alpha": 0.7,
                "show_delta_labels": True,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "two-condition changes" in sections["Figure interpretation"]
    assert "start=before" in sections["Parameter notes"]
    summary = report["agent_context"]["parameter_summary"]
    assert "end=after" in summary["statistics"]
    assert "group=group" in summary["display"]
    assert "top pairs=2" in summary["display"]
    assert "group-colored connectors=True" in summary["display"]
    assert "delta labels shown=True" in summary["display"]


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
                "matrix_type": "upper_triangle",
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
    assert "matrix type=upper_triangle" in report["agent_context"]["parameter_summary"]["display"]
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


def test_plot_studio_report_summarizes_enrichment_bar_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_enrichment_bar.csv"
    table_file.write_text(
        "term,gene_ratio,count,adjusted_p\n"
        "cell cycle,0.12,12,0.001\n"
        "immune response,0.08,8,0.004\n"
        "ribosome,0.06,6,0.02\n",
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
                "name": "Enrichment bars",
                "type": "enrichment_result",
                "dataPath": str(table_file),
            },
            "plotType": "enrichment_bar",
            "params": {
                "top_n": 12,
                "bar_value": "ratio",
                "sort_by": "gene_ratio",
                "color_transform": "minus_log10",
                "orientation": "horizontal",
                "bar_opacity": 0.72,
                "bar_line_width": 1.2,
                "bar_line_color": "#111827",
                "show_value_labels": True,
                "value_precision": 3,
                "wrap_term_label": True,
                "term_label_width": 18,
                "color_scale": "cividis",
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "top bars=12" in sections["Parameter notes"]
    summary = report["agent_context"]["parameter_summary"]
    assert "bar value=ratio" in summary["statistics"]
    assert "sort by=gene_ratio" in summary["statistics"]
    assert "orientation=horizontal" in summary["display"]
    assert "bar opacity=0.72" in summary["display"]
    assert "bar line width=1.2" in summary["display"]
    assert "value labels shown=True" in summary["display"]
    assert "value precision=3" in summary["display"]


def test_plot_studio_report_summarizes_treemap_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_treemap.csv"
    table_file.write_text(
        "term,category,count,adjusted_p\n"
        "cell cycle,GOBP,12,0.001\n"
        "immune response,GOBP,8,0.004\n"
        "ribosome,KEGG,6,0.02\n",
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
                "name": "Functional classes",
                "type": "enrichment_result",
                "dataPath": str(table_file),
            },
            "plotType": "treemap",
            "params": {
                "top_n": 12,
                "parent_column": "category",
                "branchvalues": "total",
                "sort_by": "color",
                "color_transform": "minus_log10",
                "textinfo": "label+percent root",
                "tiling": "binary",
                "color_scale": "cividis",
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "top leaves=12" in sections["Parameter notes"]
    assert "parent column=category" in sections["Parameter notes"]
    assert "branch values=total" in report["agent_context"]["parameter_summary"]["statistics"]
    assert "sort by=color" in report["agent_context"]["parameter_summary"]["statistics"]
    assert "text=label+percent root" in report["agent_context"]["parameter_summary"]["display"]
    assert "tiling=binary" in report["agent_context"]["parameter_summary"]["display"]
    assert "color scale=cividis" in report["agent_context"]["parameter_summary"]["display"]


def test_plot_studio_report_summarizes_sunburst_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_sunburst.csv"
    table_file.write_text(
        "term,category,count,adjusted_p\n"
        "cell cycle,GOBP,12,0.001\n"
        "immune response,GOBP,8,0.004\n"
        "ribosome,KEGG,6,0.02\n",
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
                "name": "Functional classes",
                "type": "enrichment_result",
                "dataPath": str(table_file),
            },
            "plotType": "sunburst",
            "params": {
                "top_n": 12,
                "parent_column": "category",
                "branchvalues": "remainder",
                "maxdepth": 4,
                "sort_by": "color",
                "color_transform": "minus_log10",
                "textinfo": "label+percent root",
                "color_scale": "cividis",
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "top leaves=12" in sections["Parameter notes"]
    assert "parent column=category" in sections["Parameter notes"]
    assert "branch values=remainder" in report["agent_context"]["parameter_summary"]["statistics"]
    assert "sort by=color" in report["agent_context"]["parameter_summary"]["statistics"]
    assert "max depth=4" in report["agent_context"]["parameter_summary"]["display"]
    assert "text=label+percent root" in report["agent_context"]["parameter_summary"]["display"]
    assert "color scale=cividis" in report["agent_context"]["parameter_summary"]["display"]


def test_plot_studio_report_summarizes_wordcloud_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_wordcloud.csv"
    table_file.write_text(
        "term,count,adjusted_p\n"
        "cell cycle,12,0.001\n"
        "immune response,8,0.004\n"
        "ribosome,6,0.02\n",
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
                "name": "Functional words",
                "type": "enrichment_result",
                "dataPath": str(table_file),
            },
            "plotType": "wordcloud",
            "params": {
                "top_n": 24,
                "weight_column": "count",
                "sort_by": "color",
                "color_transform": "minus_log10",
                "min_font_size": 10,
                "max_font_size": 64,
                "cloud_width": 12,
                "cloud_height": 7,
                "rotate_fraction": 0.25,
                "color_scale": "plasma",
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "top words=24" in sections["Parameter notes"]
    summary = report["agent_context"]["parameter_summary"]
    assert "weight column=count" in summary["statistics"]
    assert "sort by=color" in summary["statistics"]
    assert "font size range=10-64" in summary["display"]
    assert "cloud canvas=12x7" in summary["display"]
    assert "rotated fraction=0.25" in summary["display"]


def test_plot_studio_report_summarizes_sankey_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_sankey.csv"
    table_file.write_text(
        "source,target,value,group\n"
        "GO,cell cycle,12,BP\n"
        "GO,immune response,8,BP\n"
        "KEGG,ribosome,6,pathway\n",
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
                "name": "Functional flow",
                "type": "enrichment_result",
                "dataPath": str(table_file),
            },
            "plotType": "sankey",
            "params": {
                "top_n": 24,
                "min_value": 2,
                "sort_by": "source",
                "arrangement": "freeform",
                "node_pad": 22,
                "node_thickness": 16,
                "node_line_width": 1.2,
                "link_opacity": 0.44,
                "label_font_size": 13,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "top links=24" in sections["Parameter notes"]
    summary = report["agent_context"]["parameter_summary"]
    assert "minimum value=2" in summary["statistics"]
    assert "sort by=source" in summary["statistics"]
    assert "arrangement=freeform" in summary["display"]
    assert "node padding=22" in summary["display"]
    assert "link opacity=0.44" in summary["display"]


def test_plot_studio_report_summarizes_composition_bar_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_composition.csv"
    table_file.write_text(
        "sample,category,abundance,condition\n"
        "S1,A,10,case\n"
        "S1,B,5,case\n"
        "S2,A,6,control\n"
        "S2,C,4,control\n",
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
                "name": "Taxa composition",
                "type": "taxonomy_table",
                "dataPath": str(table_file),
            },
            "plotType": "composition_bar",
            "params": {
                "top_n": 8,
                "normalize": "percent",
                "other_label": "Low abundance",
                "sort_samples": "name",
                "sort_categories": "total_desc",
                "orientation": "vertical",
                "bar_mode": "stack",
                "bar_opacity": 0.74,
                "show_percent_axis": True,
                "show_legend": False,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "top categories=8" in sections["Parameter notes"]
    summary = report["agent_context"]["parameter_summary"]
    assert "normalize=percent" in summary["statistics"]
    assert "other label=Low abundance" in summary["display"]
    assert "sample order=name" in summary["display"]
    assert "bar mode=stack" in summary["display"]
    assert "legend shown=False" in summary["display"]


def test_plot_studio_report_summarizes_donut_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_report_donut.csv"
    table_file.write_text(
        "sample,category,abundance,condition\n"
        "S1,A,10,case\n"
        "S1,B,5,case\n"
        "S2,A,6,control\n"
        "S2,C,4,control\n",
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
                "name": "Taxa donut",
                "type": "taxonomy_table",
                "dataPath": str(table_file),
            },
            "plotType": "donut",
            "params": {
                "top_n": 6,
                "group_column": "condition",
                "selected_group": "case",
                "other_label": "Low abundance",
                "sort_by": "value",
                "hole": 0.52,
                "textinfo": "label+percent",
                "textposition": "outside",
                "pull_largest": True,
                "rotation": 35,
            },
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    assert "top slices=6" in sections["Parameter notes"]
    summary = report["agent_context"]["parameter_summary"]
    assert "group column=condition" in summary["statistics"]
    assert "selected group=case" in summary["statistics"]
    assert "donut hole=0.52" in summary["display"]
    assert "text position=outside" in summary["display"]
    assert "pull largest=True" in summary["display"]


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
                "boxmean_mode": "mean_sd",
                "notched": True,
                "box_width": 0.5,
                "boxpoints": "outliers",
                "quartile_method": "inclusive",
                "whisker_width": 0.25,
                "box_fill_alpha": 0.4,
                "box_line_width": 2.2,
                "show_n_labels": True,
                "n_label_position": "bottom",
                "n_label_font_size": 13,
                "n_label_color": "#123456",
                "p_value_label_format": "stars",
                "p_value_font_size": 12,
                "p_value_color": "#884422",
                "p_value_bracket_color": "#225588",
                "p_value_bracket_width": 1.8,
            },
        },
    )
    boxplot_summary = boxplot_report["agent_context"]["parameter_summary"]["display"]
    assert "raw points shown=True" in boxplot_summary
    assert "point jitter=0.45" in boxplot_summary
    assert "point size=8" in boxplot_summary
    assert "point opacity=0.48" in boxplot_summary
    assert "mean marker=False" in boxplot_summary
    assert "mean display=mean_sd" in boxplot_summary
    assert "notched boxes enabled" in boxplot_summary
    assert "box width=0.5" in boxplot_summary
    assert "point display=outliers" in boxplot_summary
    assert "whisker width=0.25" in boxplot_summary
    assert "box fill opacity=0.4" in boxplot_summary
    assert "box line width=2.2" in boxplot_summary
    assert "n labels shown=True" in boxplot_summary
    assert "n label position=bottom" in boxplot_summary
    assert "n label font size=13" in boxplot_summary
    assert "n label color=#123456" in boxplot_summary
    assert "p-value font size=12" in boxplot_summary
    assert "p-value color=#884422" in boxplot_summary
    assert "p-value bracket color=#225588" in boxplot_summary
    assert "p-value bracket width=1.8" in boxplot_summary
    assert "quartile method=inclusive" in boxplot_report["agent_context"]["parameter_summary"]["statistics"]
    assert "p-value label format=stars" in boxplot_report["agent_context"]["parameter_summary"]["statistics"]

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
                "scale_mode": "count",
                "point_position": 0.25,
                "point_jitter": 0.18,
                "point_size": 7,
                "point_alpha": 0.62,
                "violin_width": 0.8,
                "fill_alpha": 0.3,
                "line_width": 2.0,
                "show_n_labels": False,
                "n_label_position": "top",
                "n_label_font_size": 12,
                "n_label_color": "#654321",
            },
        },
    )
    violin_summary = violin_report["agent_context"]["parameter_summary"]
    assert "bandwidth=0.35" in violin_summary["statistics"]
    assert "box overlay=False" in violin_summary["display"]
    assert "mean line=True" in violin_summary["display"]
    assert "points=all" in violin_summary["display"]
    assert "side=positive" in violin_summary["display"]
    assert "scale mode=count" in violin_summary["display"]
    assert "point position=0.25" in violin_summary["display"]
    assert "point jitter=0.18" in violin_summary["display"]
    assert "point size=7" in violin_summary["display"]
    assert "point opacity=0.62" in violin_summary["display"]
    assert "violin width=0.8" in violin_summary["display"]
    assert "fill opacity=0.3" in violin_summary["display"]
    assert "line width=2.0" in violin_summary["display"]
    assert "n labels shown=False" in violin_summary["display"]
    assert "n label position=top" in violin_summary["display"]
    assert "n label font size=12" in violin_summary["display"]
    assert "n label color=#654321" in violin_summary["display"]


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
                "trendline": "linear",
                "show_fit_stats": True,
                "fit_stats_position": "bottom_right",
                "fit_stats_precision": 4,
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
    assert "trendline=linear" in sections["Parameter notes"]
    assert "fit statistics shown=True" in sections["Parameter notes"]
    assert "fit statistics precision=4" in report["agent_context"]["parameter_summary"]["statistics"]
    assert "fit statistics position=bottom_right" in report["agent_context"]["parameter_summary"]["display"]
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
                "aggregate_replicates": True,
                "summary_stat": "mean",
                "error_bar": "sem",
                "error_cap_width": 6,
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
    assert "repeated x aggregated=True" in report["agent_context"]["parameter_summary"]["statistics"]
    assert "summary statistic=mean" in report["agent_context"]["parameter_summary"]["statistics"]
    assert "error bar=sem" in report["agent_context"]["parameter_summary"]["statistics"]
    assert "error cap width=6" in report["agent_context"]["parameter_summary"]["display"]


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


def test_plot_studio_report_summarizes_radar_and_parallel_parameters(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_profile_report.csv"
    table_file.write_text(
        "sample,group,m1,m2,m3,m4,score\n"
        "S1,A,1,5,2,8,0.2\n"
        "S2,A,2,4,3,7,0.3\n"
        "S3,B,7,2,8,3,0.8\n"
        "S4,B,8,1,7,2,0.9\n",
        encoding="utf-8",
    )
    source = {
        "sourceKind": "analysis_output",
        "name": "Profile table",
        "type": "unknown_table",
        "dataPath": str(table_file),
    }
    client = TestClient(app)

    radar = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={
            "source": source,
            "plotType": "radar",
            "params": {
                "max_series": 4,
                "aggregation": "median",
                "normalize": "zscore_by_axis",
                "fill": False,
                "line_width": 3.1,
                "marker_size": 7,
            },
        },
    )
    radar_summary = radar["agent_context"]["parameter_summary"]
    assert "aggregation=median" in radar_summary["statistics"]
    assert "normalization=zscore_by_axis" in radar_summary["statistics"]
    assert "filled polygons=False" in radar_summary["display"]
    assert "marker size=7" in radar_summary["display"]

    parallel = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={
            "source": source,
            "plotType": "parallel_coordinates",
            "params": {
                "max_dimensions": 5,
                "max_rows": 200,
                "color": "score",
                "color_scale": "plasma",
                "show_colorbar": False,
                "line_opacity": 0.36,
            },
        },
    )
    parallel_summary = parallel["agent_context"]["parameter_summary"]
    assert "max dimensions=5" in parallel_summary["display"]
    assert "max rows=200" in parallel_summary["display"]
    assert "color by=score" in parallel_summary["display"]
    assert "color bar shown=False" in parallel_summary["display"]
    assert "line opacity=0.36" in parallel_summary["display"]


def test_plot_studio_report_has_plot_specific_guidance_for_every_preset() -> None:
    client = TestClient(app)
    expected_keywords = {
        "scatter": "relationship strength",
        "boxplot": "group medians",
        "grouped_dotplot": "individual sample values",
        "raincloud": "combined distribution shape",
        "violin": "distribution shape",
        "ridgeline": "stacked group distribution shapes",
        "bar": "aggregated group summaries",
        "line": "ordered trends",
        "histogram": "single-variable distribution shape",
        "density_curve": "smoothed distribution shape",
        "ecdf": "cumulative distribution shifts",
        "calendar_heatmap": "daily temporal intensity",
        "density_contour": "two-variable density structure",
        "scatter_3d": "three-dimensional separation",
        "surface_3d": "matrix-level expression ridges",
        "radar": "multi-metric sample or group profiles",
        "parallel_coordinates": "high-dimensional numeric profiles",
        "waterfall": "ranked signed effects",
        "lollipop": "ranked feature magnitude",
        "ma_plot": "mean-dependent fold-change patterns",
        "qq_plot": "p-value calibration",
        "forest_plot": "effect-size direction",
        "roc_curve": "classifier discrimination",
        "pr_curve": "precision-recall tradeoffs",
        "kaplan_meier": "group survival separation",
        "bland_altman": "measurement agreement",
        "dose_response": "dose-dependent response direction",
        "paired_dot": "within-subject direction of change",
        "dumbbell": "two-condition changes",
        "heatmap": "row/column clustering",
        "bubble": "size and color encodings",
        "volcano": "up/down significant features",
        "upset": "set intersections",
        "venn": "small-set overlaps",
        "correlation": "similarity blocks",
        "enrichment_dot": "top enriched terms",
        "enrichment_bar": "ranked enriched terms",
        "treemap": "hierarchical category composition",
        "sunburst": "radial hierarchy",
        "wordcloud": "dominant terms",
        "sankey": "dominant source-target flows",
        "composition_bar": "dominant categories per sample",
        "donut": "single-group composition",
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
        guidance = report["agent_context"]["report_guidance"]
        assert {"source metadata", "selected plot preset", "plot parameters", "table summary"} <= set(
            guidance["evidence_sources"]
        )
        assert guidance["safe_claims"]
        assert guidance["avoid_claims"]
        assert guidance["next_checks"]
        prompt = report["agent_context"]["report_prompt"]
        assert "cautious bioinformatics report agent" in prompt["system"]
        assert preset["label"] in prompt["user"]
        assert "Safe claims:" in prompt["user"]
        assert "Avoid claims:" in prompt["user"]
        assert any("cannot inspect images" in item for item in prompt["checklist"])
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
                "axis_mirror": "line",
                "show_grid": True,
                "grid_color": "#cbd5e1",
                "grid_width": 1.6,
                "show_zero_line": False,
                "zero_line_color": "#94a3b8",
                "zero_line_width": 2,
                "legend_title": "Condition",
                "legend_font_size": 14,
                "legend_background": "rgba(255,255,255,0.9)",
                "legend_border_color": "#94a3b8",
                "legend_border_width": 1.2,
                "title_font_size": 22,
                "title_color": "#0f172a",
                "subtitle_font_size": 12,
                "subtitle_color": "#475569",
                "axis_title_font_size": 18,
                "axis_title_color": "#1e3a8a",
                "tick_font_size": 11,
                "tick_color": "#475569",
                "tick_direction": "inside",
                "tick_length": 8,
                "tick_width": 1.5,
                "tick_line_color": "#0f172a",
                "y_range_mode": "custom",
                "y_min": 0,
                "y_max": 12,
                "y_tick_count": 6,
                "y_tick_format": ".2f",
                "y_tick_prefix": "",
                "y_tick_suffix": " TPM",
                "show_v_reference": True,
                "v_reference_value": 1.5,
                "v_reference_color": "#7c3aed",
                "v_reference_width": 2.1,
                "v_reference_dash": "dot",
                "show_h_reference": True,
                "h_reference_value": 6,
                "h_reference_color": "#be123c",
                "h_reference_width": 1.8,
                "h_reference_dash": "dashdot",
                "hover_mode": "x unified",
                "drag_mode": "pan",
                "display_modebar": "always",
                "scroll_zoom": True,
                "selection_tools": True,
                "show_spikes": True,
                "spike_color": "#334155",
                "spike_width": 2.4,
                "spike_dash": "dash",
                "hover_label_background": "#020617",
                "hover_label_color": "#f8fafc",
                "hover_label_font_size": 15,
                "x_tick_angle": -35,
                "width": 900,
                "height": 520,
                "margin_left": 96,
                "margin_right": 44,
                "margin_top": 120,
                "margin_bottom": 88,
                "export_filename": "Figure 1 / boxplot",
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
    assert spec["layout"]["title"]["font"] == {"size": 22, "color": "#0f172a"}
    assert spec["layout"]["annotations"][0]["text"] == "QC-filtered samples"
    assert spec["layout"]["annotations"][0]["font"] == {"size": 12, "color": "#475569"}
    assert spec["layout"]["xaxis"]["title"]["text"] == "Sample group"
    assert spec["layout"]["yaxis"]["title"]["text"] == "Normalized expression"
    assert spec["layout"]["xaxis"]["title"]["font"] == {"size": 18, "color": "#1e3a8a"}
    assert spec["layout"]["yaxis"]["title"]["font"] == {"size": 18, "color": "#1e3a8a"}
    assert spec["layout"]["xaxis"]["tickangle"] == -35
    assert spec["layout"]["xaxis"]["tickfont"] == {"size": 11, "color": "#475569"}
    assert spec["layout"]["xaxis"]["ticks"] == "inside"
    assert spec["layout"]["xaxis"]["ticklen"] == 8
    assert spec["layout"]["xaxis"]["tickwidth"] == 1.5
    assert spec["layout"]["xaxis"]["tickcolor"] == "#0f172a"
    assert spec["layout"]["yaxis"]["tickfont"] == {"size": 11, "color": "#475569"}
    assert spec["layout"]["yaxis"]["ticks"] == "inside"
    assert spec["layout"]["yaxis"]["ticklen"] == 8
    assert spec["layout"]["yaxis"]["tickwidth"] == 1.5
    assert spec["layout"]["yaxis"]["tickcolor"] == "#0f172a"
    assert spec["layout"]["xaxis"]["showline"] is False
    assert spec["layout"]["xaxis"]["linecolor"] == "#111827"
    assert spec["layout"]["xaxis"]["linewidth"] == 2.5
    assert spec["layout"]["xaxis"]["mirror"] is True
    assert spec["layout"]["xaxis"]["gridcolor"] == "#cbd5e1"
    assert spec["layout"]["xaxis"]["gridwidth"] == 1.6
    assert spec["layout"]["xaxis"]["zeroline"] is False
    assert spec["layout"]["xaxis"]["zerolinecolor"] == "#94a3b8"
    assert spec["layout"]["xaxis"]["zerolinewidth"] == 2
    assert spec["layout"]["hovermode"] == "x unified"
    assert spec["layout"]["dragmode"] == "pan"
    assert spec["config"]["displayModeBar"] is True
    assert spec["config"]["scrollZoom"] is True
    assert spec["config"]["modeBarButtonsToRemove"] == []
    assert spec["layout"]["hoverlabel"] == {
        "bgcolor": "#020617",
        "font": {"color": "#f8fafc", "size": 15},
    }
    assert spec["layout"]["xaxis"]["showspikes"] is True
    assert spec["layout"]["xaxis"]["spikecolor"] == "#334155"
    assert spec["layout"]["xaxis"]["spikethickness"] == 2.4
    assert spec["layout"]["xaxis"]["spikedash"] == "dash"
    assert spec["layout"]["yaxis"]["showspikes"] is True
    assert spec["layout"]["yaxis"]["spikecolor"] == "#334155"
    assert spec["layout"]["yaxis"]["spikethickness"] == 2.4
    assert spec["layout"]["yaxis"]["spikedash"] == "dash"
    assert any(
        shape["xref"] == "x"
        and shape["x0"] == 1.5
        and shape["line"] == {"color": "#7c3aed", "width": 2.1, "dash": "dot"}
        for shape in spec["layout"]["shapes"]
    )
    assert any(
        shape["yref"] == "y"
        and shape["y0"] == 6.0
        and shape["line"] == {"color": "#be123c", "width": 1.8, "dash": "dashdot"}
        for shape in spec["layout"]["shapes"]
    )
    assert spec["layout"]["yaxis"]["linecolor"] == "#111827"
    assert spec["layout"]["yaxis"]["linewidth"] == 2.5
    assert spec["layout"]["yaxis"]["mirror"] is True
    assert spec["layout"]["yaxis"]["range"] == [0.0, 12.0]
    assert spec["layout"]["yaxis"]["nticks"] == 6
    assert spec["layout"]["yaxis"]["tickformat"] == ".2f"
    assert spec["layout"]["yaxis"]["ticksuffix"] == " TPM"
    assert spec["layout"]["yaxis"]["gridcolor"] == "#cbd5e1"
    assert spec["layout"]["yaxis"]["gridwidth"] == 1.6
    assert spec["layout"]["yaxis"]["zeroline"] is False
    assert spec["layout"]["yaxis"]["zerolinecolor"] == "#94a3b8"
    assert spec["layout"]["yaxis"]["zerolinewidth"] == 2
    assert spec["layout"]["legend"]["title"]["text"] == "Condition"
    assert spec["layout"]["legend"]["font"]["size"] == 14
    assert spec["layout"]["legend"]["bgcolor"] == "rgba(255,255,255,0.9)"
    assert spec["layout"]["legend"]["bordercolor"] == "#94a3b8"
    assert spec["layout"]["legend"]["borderwidth"] == 1.2
    assert spec["layout"]["font"]["family"].startswith("Georgia")
    assert spec["layout"]["font"]["size"] == 16
    assert spec["layout"]["width"] == 900
    assert spec["layout"]["height"] == 520
    assert spec["layout"]["margin"] == {"l": 96, "r": 44, "t": 120, "b": 88}
    assert spec["config"]["toImageButtonOptions"]["format"] == "png"
    assert spec["config"]["toImageButtonOptions"]["filename"] == "Figure_1_boxplot"
    assert spec["config"]["toImageButtonOptions"]["scale"] == 4
    assert spec["config"]["displaylogo"] is False


def test_plot_studio_distribution_specs_can_show_group_sample_sizes(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_distribution_n_labels.csv"
    table_file.write_text(
        "\n".join(
            [
                "condition,value",
                "Control,1.0",
                "Control,1.1",
                "Control,1.2",
                "Treatment,2.2",
                "Treatment,2.6",
            ]
        ),
        encoding="utf-8",
    )
    source = {
        "sourceKind": "analysis_output",
        "name": "Grouped values",
        "type": "unknown_table",
        "dataPath": str(table_file),
    }
    client = TestClient(app)

    boxplot = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": source,
            "plotType": "boxplot",
            "params": {
                "group": "condition",
                "y": "value",
                "show_n_labels": True,
                "n_label_position": "bottom",
                "n_label_font_size": 13,
                "n_label_color": "#123456",
            },
        },
    )
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
                "show_n_labels": True,
                "n_label_position": "top",
                "n_label_font_size": 14,
                "n_label_color": "#654321",
            },
        },
    )

    boxplot_n_annotations = [
        annotation for annotation in boxplot["layout"]["annotations"] if annotation.get("text", "").startswith("n=")
    ]
    assert [(annotation["x"], annotation["text"]) for annotation in boxplot_n_annotations] == [
        ("Control", "n=3"),
        ("Treatment", "n=2"),
    ]
    assert all(annotation["xref"] == "x" for annotation in boxplot_n_annotations)
    assert all(annotation["yref"] == "paper" for annotation in boxplot_n_annotations)
    assert all(annotation["y"] == -0.14 for annotation in boxplot_n_annotations)
    assert all(annotation["yanchor"] == "top" for annotation in boxplot_n_annotations)
    assert all(annotation["font"] == {"size": 13, "color": "#123456"} for annotation in boxplot_n_annotations)
    assert boxplot["layout"]["margin"]["b"] >= 84

    violin_n_annotations = [
        annotation for annotation in violin["layout"]["annotations"] if annotation.get("text", "").startswith("n=")
    ]
    assert [(annotation["x"], annotation["text"]) for annotation in violin_n_annotations] == [
        ("Control", "n=3"),
        ("Treatment", "n=2"),
    ]
    assert all(annotation["y"] == 1.02 for annotation in violin_n_annotations)
    assert all(annotation["yanchor"] == "bottom" for annotation in violin_n_annotations)
    assert all(annotation["font"] == {"size": 14, "color": "#654321"} for annotation in violin_n_annotations)
    assert violin["layout"]["margin"]["t"] >= 88


def test_plot_studio_default_toolbar_stays_unobtrusive() -> None:
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
            },
            "plotType": "boxplot",
            "params": {"max_groups": 3},
        },
    )

    assert spec["config"]["displaylogo"] is False
    assert spec["config"]["displayModeBar"] == "hover"
    assert spec["config"]["scrollZoom"] is False
    assert spec["config"]["modeBarButtonsToRemove"] == ["lasso2d", "select2d"]


def test_plot_studio_export_uses_supported_browser_formats() -> None:
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
            },
            "plotType": "boxplot",
            "params": {"format": "jpeg", "dpi": "1000", "export_filename": "high res figure"},
        },
    )

    export = spec["config"]["toImageButtonOptions"]
    assert export["format"] == "jpeg"
    assert export["scale"] == 6
    assert export["filename"] == "high_res_figure"


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
                "show_fit_stats": True,
                "fit_stats_position": "top_left",
                "fit_stats_precision": 3,
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
    fit_annotations = [
        annotation for annotation in linear["layout"]["annotations"] if "R2 =" in annotation["text"]
    ]
    assert len(fit_annotations) == 2
    assert fit_annotations[0]["x"] == 0.02
    assert fit_annotations[0]["xanchor"] == "left"
    assert "A: y =" in fit_annotations[0]["text"]

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


def test_plot_studio_line_plot_aggregates_replicates_with_error_bars(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_line_replicates.csv"
    table_file.write_text(
        "\n".join(
            [
                "time,condition,value",
                "T0,A,1.0",
                "T0,A,1.4",
                "T1,A,2.0",
                "T1,A,2.8",
                "T0,B,0.8",
                "T0,B,1.2",
                "T1,B,1.8",
                "T1,B,2.2",
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
                "name": "Replicate time course",
                "type": "unknown_table",
                "dataPath": str(table_file),
            },
            "plotType": "line",
            "params": {
                "x": "time",
                "y": "value",
                "series": "condition",
                "aggregate_replicates": True,
                "summary_stat": "mean",
                "error_bar": "sd",
                "error_cap_width": 7,
            },
        },
    )

    traces = {trace["name"]: trace for trace in spec["data"]}
    assert traces["A"]["x"] == ["T0", "T1"]
    assert traces["A"]["y"] == [1.2, 2.4]
    assert traces["A"]["customdata"] == [[2], [2]]
    assert traces["A"]["error_y"]["visible"] is True
    assert [round(value, 3) for value in traces["A"]["error_y"]["array"]] == [0.2, 0.4]
    assert traces["A"]["error_y"]["width"] == 7.0
    assert traces["B"]["y"] == [1.0, 2.0]


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
                "scale_mode": "count",
                "point_position": 0.35,
                "point_jitter": 0.2,
                "bandwidth": 0.4,
                "point_size": 8,
                "point_alpha": 0.51,
                "violin_width": 0.82,
                "fill_alpha": 0.33,
                "line_width": 2.1,
            },
        },
    )
    assert violin["plot_type"] == "violin"
    assert all(trace["type"] == "violin" for trace in violin["data"])
    assert violin["data"][0]["points"] == "all"
    assert violin["data"][0]["side"] == "positive"
    assert violin["data"][0]["scalemode"] == "count"
    assert violin["data"][0]["pointpos"] == 0.35
    assert violin["data"][0]["jitter"] == 0.2
    assert violin["data"][0]["bandwidth"] == 0.4
    assert violin["data"][0]["width"] == 0.82
    assert violin["data"][0]["fillcolor"].startswith("rgba(")
    assert violin["data"][0]["fillcolor"].endswith(", 0.33)")
    assert violin["data"][0]["line"]["width"] == 2.1
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
                "boxpoints": "outliers",
                "boxmean_mode": "mean_sd",
                "quartile_method": "inclusive",
                "whisker_width": 0.2,
                "box_fill_alpha": 0.42,
                "box_line_width": 2.6,
                "pairwise_test": "t_test",
                "multiple_testing": "bonferroni",
                "show_p_values": True,
                "p_value_label_format": "stars",
                "p_value_font_size": 14,
                "p_value_color": "#552211",
                "p_value_bracket_color": "#114477",
                "p_value_bracket_width": 2.4,
            },
        },
    )

    assert spec["plot_type"] == "boxplot"
    assert all(trace["marker"]["size"] == 9 for trace in spec["data"])
    assert all(trace["marker"]["opacity"] == 0.44 for trace in spec["data"])
    assert all(trace["boxpoints"] == "outliers" for trace in spec["data"])
    assert all(trace["boxmean"] == "sd" for trace in spec["data"])
    assert all(trace["quartilemethod"] == "inclusive" for trace in spec["data"])
    assert all(trace["whiskerwidth"] == 0.2 for trace in spec["data"])
    assert all(trace["fillcolor"].endswith(", 0.42)") for trace in spec["data"])
    assert all(trace["line"]["width"] == 2.6 for trace in spec["data"])
    p_value_annotations = [
        annotation
        for annotation in spec["layout"]["annotations"]
        if str(annotation.get("text", "")) in {"ns", "*", "**", "***", "****"}
    ]
    assert len(p_value_annotations) == 3
    assert all(annotation["font"] == {"size": 14, "color": "#552211"} for annotation in p_value_annotations)
    assert len(spec["layout"]["shapes"]) == 9
    assert all(shape["line"] == {"color": "#114477", "width": 2.4} for shape in spec["layout"]["shapes"])
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
    assert spec["data"][0]["x"][0].startswith("I")
    assert any("A&B" in item[0] for item in spec["data"][0]["customdata"])
    assert any(trace.get("xaxis") == "x2" for trace in spec["data"][1:])
    assert spec["layout"]["xaxis3"]["title"] == "Set size"
    assert spec["layout"]["xaxis"]["tickangle"] == 0
    assert spec["layout"]["xaxis2"]["tickangle"] == 0
    assert spec["layout"]["yaxis"]["domain"][0] > spec["layout"]["yaxis2"]["domain"][1]
    assert spec["layout"]["title"]["y"] == 0.94


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
        "gene,baseMean,log2fc,ci_low,ci_high,p_value\nA,120,2.1,1.2,3.0,0.001\nB,70,-1.8,-2.4,-1.0,0.002\nC,9,0.2,-0.3,0.7,0.9\n",
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

    waterfall = _request(
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
            "plotType": "waterfall",
            "params": {
                "sort_by": "p_value",
                "top_n": 2,
                "orientation": "horizontal",
                "show_value_labels": True,
                "value_precision": 1,
                "bar_opacity": 0.5,
            },
        },
    )
    assert waterfall["plot_type"] == "waterfall"
    trace = waterfall["data"][0]
    assert trace["type"] == "bar"
    assert trace["orientation"] == "h"
    assert trace["x"] == [2.1, -1.8]
    assert trace["y"] == ["A", "B"]
    assert trace["marker"]["opacity"] == 0.5
    assert trace["text"] == ["2.1", "-1.8"]
    assert len(waterfall["layout"]["shapes"]) == 1

    lollipop = _request(
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
            "plotType": "lollipop",
            "params": {
                "label_column": "gene",
                "value_column": "log2fc",
                "size_column": "baseMean",
                "sort_by": "abs_value",
                "top_n": 2,
                "orientation": "horizontal",
                "baseline": 0,
                "stem_width": 2,
                "stem_color": "#64748b",
                "point_size": 10,
                "point_alpha": 0.6,
                "show_value_labels": True,
                "value_precision": 1,
            },
        },
    )
    assert lollipop["plot_type"] == "lollipop"
    lollipop_trace = lollipop["data"][0]
    assert lollipop_trace["type"] == "scatter"
    assert lollipop_trace["mode"] == "markers+text"
    assert lollipop_trace["x"] == [2.1, -1.8]
    assert lollipop_trace["y"] == ["A", "B"]
    assert lollipop_trace["text"] == ["2.1", "-1.8"]
    assert lollipop_trace["marker"]["opacity"] == 0.6
    assert len(lollipop["layout"]["shapes"]) == 2
    assert lollipop["layout"]["shapes"][0]["line"] == {"color": "#64748b", "width": 2.0}
    assert lollipop["layout"]["yaxis"]["autorange"] == "reversed"

    dumbbell_file = allowed_tmp / f"{tmp_path.name}_dumbbell.csv"
    dumbbell_file.write_text(
        "feature,before,after,group\nA,1,4,up\nB,5,2,down\nC,3,3.5,flat\n",
        encoding="utf-8",
    )
    dumbbell = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "name": "Two-condition table",
                "type": "paired_result",
                "dataPath": str(dumbbell_file),
            },
            "plotType": "dumbbell",
            "params": {
                "label_column": "feature",
                "start_column": "before",
                "end_column": "after",
                "group": "group",
                "sort_by": "delta_abs",
                "top_n": 2,
                "orientation": "horizontal",
                "start_label": "Start",
                "end_label": "End",
                "line_width": 2.4,
                "line_color": "#64748b",
                "point_size": 11,
                "point_alpha": 0.65,
                "show_delta_labels": True,
                "value_precision": 1,
            },
        },
    )
    assert dumbbell["plot_type"] == "dumbbell"
    assert [trace["name"] for trace in dumbbell["data"]] == ["paired shift", "Start", "End"]
    connector, start_trace, end_trace = dumbbell["data"]
    assert connector["mode"] == "lines"
    assert connector["x"] == [1.0, 4.0, None, 5.0, 2.0, None]
    assert connector["line"] == {"color": "#64748b", "width": 2.4}
    assert start_trace["x"] == [1.0, 5.0]
    assert start_trace["y"] == ["A", "B"]
    assert end_trace["mode"] == "markers+text"
    assert end_trace["text"] == ["+3.0", "-3.0"]
    assert end_trace["marker"]["opacity"] == 0.65
    assert dumbbell["layout"]["yaxis"]["autorange"] == "reversed"
    assert dumbbell["layout"]["meta"]["dumbbell"]["rows"] == 2

    grouped_dumbbell = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "name": "Two-condition table",
                "type": "paired_result",
                "dataPath": str(dumbbell_file),
            },
            "plotType": "dumbbell",
            "params": {
                "label_column": "feature",
                "start_column": "before",
                "end_column": "after",
                "group": "group",
                "top_n": 2,
                "color_by_group": True,
            },
        },
    )
    line_traces = [trace for trace in grouped_dumbbell["data"] if trace["mode"] == "lines"]
    assert [trace["name"] for trace in line_traces] == ["shift: up", "shift: down"]
    assert all(trace["showlegend"] is True for trace in line_traces)
    assert line_traces[0]["line"]["color"] != line_traces[1]["line"]["color"]

    ma_plot = _request(
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
            "plotType": "ma_plot",
            "params": {"label_top_n": 2, "point_size": 9, "point_alpha": 0.6},
        },
    )
    assert ma_plot["plot_type"] == "ma_plot"
    assert ma_plot["layout"]["xaxis"]["type"] == "log"
    assert len(ma_plot["layout"]["shapes"]) == 3
    assert {trace["name"] for trace in ma_plot["data"]} == {"Up", "Down", "Not significant", "Gene labels"}
    ma_up = next(trace for trace in ma_plot["data"] if trace["name"] == "Up")
    assert ma_up["x"] == [120.0]
    assert ma_up["y"] == [2.1]
    assert ma_up["marker"]["size"] == 9

    qq_plot = _request(
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
            "plotType": "qq_plot",
            "params": {"label_top_n": 2, "point_size": 8, "point_alpha": 0.5, "confidence_band": False},
        },
    )
    assert qq_plot["plot_type"] == "qq_plot"
    qq_trace = next(trace for trace in qq_plot["data"] if trace["name"] == "All")
    assert qq_trace["type"] == "scattergl"
    assert qq_trace["marker"]["size"] == 8
    assert qq_trace["marker"]["opacity"] == 0.5
    assert len(qq_trace["x"]) == 3
    assert qq_trace["y"][0] == 3.0
    assert len(qq_plot["layout"]["shapes"]) == 1
    assert next(trace for trace in qq_plot["data"] if trace["name"] == "Feature labels")["text"] == ["A", "B"]

    forest_plot = _request(
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
            "plotType": "forest_plot",
            "params": {"sort_by": "p_value", "top_n": 2, "point_size": 11, "line_width": 2.2},
        },
    )
    assert forest_plot["plot_type"] == "forest_plot"
    forest_trace = forest_plot["data"][0]
    assert forest_trace["type"] == "scatter"
    assert forest_trace["mode"] == "markers"
    assert forest_trace["x"] == [-1.8, 2.1]
    assert forest_trace["y"] == ["B", "A"]
    assert forest_trace["error_x"]["array"] == [0.8, 0.8999999999999999]
    assert forest_trace["error_x"]["thickness"] == 2.2
    assert forest_trace["marker"]["size"] == 11
    assert len(forest_plot["layout"]["shapes"]) == 1


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
                "matrix_type": "lower_triangle",
                "show_values": True,
                "value_precision": 3,
                "cell_gap": 2,
            },
        },
    )
    assert labeled_correlation["data"][0]["texttemplate"] == "%{text}"
    assert labeled_correlation["data"][0]["text"][0][0] == "1.000"
    assert labeled_correlation["data"][0]["z"][0][1] is None
    assert labeled_correlation["data"][0]["z"][1][0] is not None
    assert labeled_correlation["data"][0]["text"][0][1] == ""
    assert any("lower triangle display hides" in warning for warning in labeled_correlation["warnings"])
    assert labeled_correlation["data"][0]["xgap"] == 2
    assert labeled_correlation["data"][0]["ygap"] == 2
    assert "meta" not in labeled_correlation["layout"]
    assert "shapes" not in labeled_correlation["layout"]


def test_plot_studio_spec_builds_roc_curve(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_roc.csv"
    table_file.write_text(
        "sample,score,label,model\n"
        "S1,0.95,case,A\n"
        "S2,0.82,case,A\n"
        "S3,0.62,case,A\n"
        "S4,0.44,control,A\n"
        "S5,0.31,control,A\n"
        "S6,0.12,control,A\n",
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
                "name": "Biomarker score",
                "type": "biomarker_result",
                "dataPath": str(table_file),
            },
            "plotType": "roc_curve",
            "params": {
                "score_column": "score",
                "label_column": "label",
                "positive_label": "case",
                "show_threshold_points": True,
                "threshold_count": 4,
                "line_width": 3,
                "point_size": 9,
                "point_alpha": 0.6,
            },
        },
    )

    assert spec["plot_type"] == "roc_curve"
    assert spec["data"][0]["name"] == "No skill"
    roc_trace = spec["data"][1]
    assert roc_trace["name"] == "All AUC=1.000"
    assert roc_trace["mode"] == "lines+markers"
    assert roc_trace["line"]["width"] == 3
    assert roc_trace["marker"]["size"] == 9
    assert roc_trace["marker"]["opacity"] == 0.6
    assert roc_trace["x"][0] == 0.0
    assert roc_trace["y"][-1] == 1.0
    assert spec["layout"]["meta"]["roc_summary"] == ["All AUC=1.000 (n=6, pos=3, neg=3)"]

    pr_spec = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "name": "Biomarker score",
                "type": "biomarker_result",
                "dataPath": str(table_file),
            },
            "plotType": "pr_curve",
            "params": {
                "score_column": "score",
                "label_column": "label",
                "positive_label": "case",
                "show_threshold_points": True,
                "threshold_count": 4,
                "line_width": 3,
                "point_size": 9,
                "point_alpha": 0.6,
            },
        },
    )
    assert pr_spec["plot_type"] == "pr_curve"
    assert pr_spec["data"][0]["name"] == "Prevalence baseline=0.500"
    pr_trace = pr_spec["data"][1]
    assert pr_trace["name"] == "All AP=1.000"
    assert pr_trace["mode"] == "lines+markers"
    assert pr_trace["line"]["width"] == 3
    assert pr_trace["marker"]["size"] == 9
    assert pr_trace["marker"]["opacity"] == 0.6
    assert pr_trace["x"][-1] == 1.0
    assert pr_trace["y"][0] == 1.0
    assert pr_spec["layout"]["meta"]["pr_summary"] == ["All AP=1.000 (n=6, pos=3, prevalence=0.500)"]


def test_plot_studio_spec_builds_kaplan_meier(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_km.csv"
    table_file.write_text(
        "sample,time,event,group\n"
        "S1,5,1,A\n"
        "S2,8,0,A\n"
        "S3,12,1,A\n"
        "S4,4,1,B\n"
        "S5,9,1,B\n"
        "S6,13,0,B\n",
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
                "name": "Survival table",
                "type": "survival_result",
                "dataPath": str(table_file),
            },
            "plotType": "kaplan_meier",
            "params": {
                "time_column": "time",
                "event_column": "event",
                "group": "group",
                "event_value": "1",
                "show_censor_marks": True,
                "show_logrank": True,
                "line_width": 3,
            },
        },
    )

    assert spec["plot_type"] == "kaplan_meier"
    group_a = next(trace for trace in spec["data"] if trace["name"] == "A")
    assert group_a["line"]["shape"] == "hv"
    assert group_a["line"]["width"] == 3
    assert group_a["x"] == [0.0, 5.0, 12.0]
    assert [round(value, 6) for value in group_a["y"]] == [1.0, round(2 / 3, 6), 0.0]
    assert any(trace["name"] == "A censored" for trace in spec["data"])
    assert "risk_table" in spec["layout"]["meta"]
    assert "logrank" in spec["layout"]["meta"]
    assert spec["layout"]["meta"]["risk_table"]["A"][0] == {"time": 5.0, "at_risk": 3, "events": 1, "censored": 0}


def test_plot_studio_spec_builds_bland_altman(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_bland.csv"
    table_file.write_text(
        "sample,method_a,method_b,batch\nS1,10,11,A\nS2,12,11.5,A\nS3,9,10,B\nS4,13,14,B\n",
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
                "name": "Agreement table",
                "type": "agreement_result",
                "dataPath": str(table_file),
            },
            "plotType": "bland_altman",
            "params": {
                "x_method": "method_a",
                "y_method": "method_b",
                "color": "batch",
                "point_size": 10,
                "point_alpha": 0.5,
                "line_width": 2.0,
            },
        },
    )

    assert spec["plot_type"] == "bland_altman"
    assert {trace["name"] for trace in spec["data"]} == {"A", "B"}
    first_trace = next(trace for trace in spec["data"] if trace["name"] == "A")
    assert first_trace["x"] == [10.5, 11.75]
    assert first_trace["y"] == [1.0, -0.5]
    assert first_trace["marker"]["size"] == 10
    assert first_trace["marker"]["opacity"] == 0.5
    agreement = spec["layout"]["meta"]["agreement"]
    assert round(agreement["bias"], 3) == 0.625
    assert agreement["n"] == 4
    assert len(spec["layout"]["shapes"]) == 4


def test_plot_studio_spec_builds_dose_response(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_dose.csv"
    table_file.write_text(
        "compound,concentration,response\n"
        "A,0.1,95\nA,1,70\nA,10,30\nA,100,8\n"
        "B,0.1,92\nB,1,80\nB,10,55\nB,100,20\n",
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
                "name": "Dose response",
                "type": "dose_response_result",
                "dataPath": str(table_file),
            },
            "plotType": "dose_response",
            "params": {
                "dose_column": "concentration",
                "response_column": "response",
                "group": "compound",
                "response_mode": "inhibition",
                "log_x": True,
                "show_half_max": True,
                "line_width": 3,
                "point_size": 9,
            },
        },
    )

    assert spec["plot_type"] == "dose_response"
    assert spec["layout"]["xaxis"]["type"] == "log"
    assert {trace["name"] for trace in spec["data"]} >= {"A", "B", "A points", "B points"}
    curve_a = next(trace for trace in spec["data"] if trace["name"] == "A")
    assert curve_a["line"]["shape"] == "spline"
    assert curve_a["line"]["width"] == 3
    points_a = next(trace for trace in spec["data"] if trace["name"] == "A points")
    assert points_a["marker"]["size"] == 9
    estimates = spec["layout"]["meta"]["dose_response"]["estimates"]
    assert set(estimates) == {"A", "B"}
    assert estimates["A"]["label"] == "IC50"
    assert 1 < estimates["A"]["half_max_dose"] < 10
    assert len(spec["layout"]["shapes"]) >= 4


def test_plot_studio_spec_builds_paired_dot(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_paired.csv"
    table_file.write_text(
        "subject,condition,value,cohort\n"
        "S1,before,10,A\nS1,after,14,A\n"
        "S2,before,8,A\nS2,after,9,A\n"
        "S3,before,7,B\nS3,after,12,B\n",
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
                "name": "Paired table",
                "type": "paired_result",
                "dataPath": str(table_file),
            },
            "plotType": "paired_dot",
            "params": {
                "value_column": "value",
                "condition_column": "condition",
                "subject_column": "subject",
                "group": "cohort",
                "summary_stat": "mean",
                "jitter": 0,
                "point_size": 9,
            },
        },
    )

    assert spec["plot_type"] == "paired_dot"
    assert spec["layout"]["xaxis"]["ticktext"] == ["before", "after"]
    assert spec["layout"]["meta"]["paired_dot"]["subjects"] == 3
    subject_trace = next(trace for trace in spec["data"] if trace["name"] == "S1")
    assert subject_trace["x"] == [0, 1]
    assert subject_trace["y"] == [10.0, 14.0]
    group_trace = next(trace for trace in spec["data"] if trace["name"] == "A")
    assert group_trace["marker"]["size"] == 9
    summary_trace = next(trace for trace in spec["data"] if trace["name"] == "mean summary")
    assert summary_trace["y"] == [25 / 3, 35 / 3]


def test_plot_studio_spec_builds_grouped_dotplot(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_grouped_dot.csv"
    table_file.write_text(
        "sample,condition,value\n"
        "S1,A,1.0\nS2,A,1.4\nS3,A,2.0\n"
        "S4,B,3.0\nS5,B,3.2\nS6,B,3.9\n",
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
            "plotType": "grouped_dotplot",
            "params": {
                "y": "value",
                "group": "condition",
                "label": "sample",
                "summary_stat": "median",
                "summary_line_color_mode": "custom",
                "summary_line_color": "#111827",
                "summary_line_width": 3,
                "sort_groups": "median_desc",
                "show_n_labels": True,
            },
        },
    )

    assert spec["plot_type"] == "grouped_dotplot"
    assert [trace["name"] for trace in spec["data"]] == ["B", "A"]
    assert spec["data"][0]["type"] == "scattergl"
    assert spec["data"][0]["text"] == ["S4", "S5", "S6"]
    assert spec["layout"]["xaxis"]["ticktext"] == ["B", "A"]
    assert len(spec["layout"]["shapes"]) == 2
    assert spec["layout"]["shapes"][0]["line"] == {"color": "#111827", "width": 3}
    assert spec["layout"]["annotations"][0]["text"] == "n=3"


def test_plot_studio_spec_builds_raincloud(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_raincloud.csv"
    table_file.write_text(
        "sample,condition,value\n"
        "S1,A,1.0\nS2,A,1.5\nS3,A,2.0\n"
        "S4,B,3.0\nS5,B,3.5\nS6,B,4.5\n",
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
            "plotType": "raincloud",
            "params": {
                "y": "value",
                "group": "condition",
                "label": "sample",
                "violin_side": "negative",
                "show_box": True,
                "show_points": True,
                "show_mean": True,
                "sort_groups": "median_desc",
            },
        },
    )

    assert spec["plot_type"] == "raincloud"
    assert spec["layout"]["xaxis"]["ticktext"] == ["B", "A"]
    assert spec["layout"]["meta"]["raincloud"] == {"groups": 2, "violin_side": "negative", "show_box": True}
    trace_types = [trace["type"] for trace in spec["data"]]
    assert trace_types.count("violin") == 2
    assert trace_types.count("box") == 2
    assert trace_types.count("scattergl") == 2
    mean_trace = next(trace for trace in spec["data"] if trace["name"] == "B mean")
    assert mean_trace["marker"]["symbol"] == "diamond"
    point_trace = next(trace for trace in spec["data"] if trace["name"] == "B")
    assert point_trace["text"] == ["S4", "S5", "S6"]


def test_plot_studio_spec_builds_ecdf(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_ecdf.csv"
    table_file.write_text(
        "sample,condition,value\n"
        "S1,A,1.0\nS2,A,2.0\nS3,A,4.0\n"
        "S4,B,2.5\nS5,B,3.5\nS6,B,5.0\n",
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
            "plotType": "ecdf",
            "params": {
                "x": "value",
                "group": "condition",
                "y_mode": "cumulative",
                "y_units": "percent",
                "show_points": True,
                "show_median": True,
                "line_width": 3,
                "sort_groups": "median_desc",
            },
        },
    )

    assert spec["plot_type"] == "ecdf"
    assert [trace["name"] for trace in spec["data"]] == ["B", "A"]
    assert spec["data"][0]["mode"] == "lines+markers"
    assert spec["data"][0]["line"]["shape"] == "hv"
    assert spec["data"][0]["line"]["width"] == 3
    assert spec["data"][0]["y"] == [100 * (1 / 3), 100 * (2 / 3), 100.0]
    assert len(spec["layout"]["shapes"]) == 2
    assert spec["layout"]["meta"]["ecdf"] == {"groups": 2, "mode": "cumulative", "units": "percent"}


def test_plot_studio_spec_builds_density_curve(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_density_curve.csv"
    table_file.write_text(
        "sample,condition,value\n"
        "S1,A,1.0\nS2,A,1.5\nS3,A,2.0\n"
        "S4,B,3.0\nS5,B,3.5\nS6,B,4.5\n",
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
            "plotType": "density_curve",
            "params": {
                "x": "value",
                "group": "condition",
                "label": "sample",
                "density_points": 40,
                "normalize": "peak",
                "fill": True,
                "show_rug": True,
                "show_median": True,
                "sort_groups": "median_desc",
            },
        },
    )

    assert spec["plot_type"] == "density_curve"
    assert spec["layout"]["meta"]["density_curve"] == {"groups": 2, "normalize": "peak", "fill": True}
    line_traces = [trace for trace in spec["data"] if trace["type"] == "scatter"]
    rug_traces = [trace for trace in spec["data"] if trace["type"] == "scattergl"]
    assert [trace["name"] for trace in line_traces] == ["B", "A"]
    assert len(line_traces[0]["x"]) == 40
    assert max(line_traces[0]["y"]) == 1.0
    assert line_traces[0]["fill"] == "tozeroy"
    assert rug_traces[0]["name"] == "B rug"
    assert rug_traces[0]["text"] == ["S4", "S5", "S6"]
    assert len(spec["layout"]["shapes"]) == 2


def test_plot_studio_spec_builds_ridgeline(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_ridgeline.csv"
    table_file.write_text(
        "sample,condition,value\n"
        "S1,A,1.0\nS2,A,1.4\nS3,A,1.8\n"
        "S4,B,2.8\nS5,B,3.1\nS6,B,3.8\n"
        "S7,C,0.4\nS8,C,0.9\nS9,C,1.2\n",
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
            "plotType": "ridgeline",
            "params": {
                "x": "value",
                "group": "condition",
                "label": "sample",
                "density_points": 50,
                "sort_groups": "median_desc",
                "show_points": True,
                "ridge_height": 0.8,
                "overlap": 0.5,
            },
        },
    )

    assert spec["plot_type"] == "ridgeline"
    ridge_traces = [trace for trace in spec["data"] if trace["type"] == "scatter" and trace["fill"] == "toself"]
    point_traces = [trace for trace in spec["data"] if trace["type"] == "scattergl"]
    assert len(ridge_traces) == 3
    assert len(point_traces) == 3
    assert ridge_traces[0]["name"] == "B"
    assert len(ridge_traces[0]["x"]) == 100
    assert spec["layout"]["yaxis"]["ticktext"] == ["B", "A", "C"]


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

    calendar_file = ROOT / "data" / "tmp_plot_studio_tests" / "calendar_spec.csv"
    calendar_file.parent.mkdir(parents=True, exist_ok=True)
    calendar_file.write_text(
        "date,value\n2026-01-01,4\n2026-01-02,7\n2026-01-02,3\n2026-01-09,6\nbad,9\n",
        encoding="utf-8",
    )
    calendar = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": {
                "sourceKind": "analysis_output",
                "name": "Sampling calendar",
                "type": "unknown_table",
                "dataPath": str(calendar_file),
            },
            "plotType": "calendar_heatmap",
            "params": {
                "date_column": "date",
                "value_column": "value",
                "aggregation": "sum",
                "week_start": "monday",
                "color_scale": "ylorrd",
                "show_values": True,
                "value_precision": 0,
            },
        },
    )
    assert calendar["plot_type"] == "calendar_heatmap"
    calendar_trace = calendar["data"][0]
    assert calendar_trace["type"] == "heatmap"
    assert calendar_trace["texttemplate"] == "%{text}"
    assert calendar_trace["z"][3][0] == 4.0
    assert calendar_trace["z"][4][0] == 10.0
    assert calendar["layout"]["meta"]["calendar_heatmap"]["days"] == 3
    assert "Skipped 1 rows with unparseable dates." in calendar["warnings"]

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


def test_plot_studio_spec_builds_enrichment_bar_plot(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    enrichment_file = allowed_tmp / f"{tmp_path.name}_enrichment_bar.csv"
    enrichment_file.write_text(
        "term,gene_ratio,count,adjusted_p\n"
        "cell cycle checkpoint regulation,3/100,3,0.001\n"
        "apoptosis,8/200,8,0.02\n"
        "immune response,5/120,5,0.004\n"
        "ribosome biogenesis,9/180,9,0.03\n"
        "stress response,4/90,4,0.05\n",
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
            "plotType": "enrichment_bar",
            "params": {
                "term_column": "term",
                "value_column": "gene_ratio",
                "bar_value": "ratio",
                "color_column": "adjusted_p",
                "color_transform": "minus_log10",
                "top_n": 5,
                "sort_by": "gene_ratio",
                "orientation": "horizontal",
                "bar_opacity": 0.7,
                "bar_line_width": 1.3,
                "bar_line_color": "#111827",
                "show_value_labels": True,
                "value_precision": 3,
                "color_scale": "green_white_purple",
                "wrap_term_label": True,
                "term_label_width": 12,
            },
        },
    )

    trace = spec["data"][0]
    assert spec["plot_type"] == "enrichment_bar"
    assert trace["type"] == "bar"
    assert trace["orientation"] == "h"
    assert trace["marker"]["colorscale"][0][1] == "#20804f"
    assert trace["marker"]["colorbar"]["title"] == "-log10(adjusted_p)"
    assert trace["marker"]["opacity"] == 0.7
    assert trace["marker"]["line"] == {"color": "#111827", "width": 1.3}
    assert trace["text"][0] == "0.050"
    assert spec["layout"]["yaxis"]["autorange"] == "reversed"
    assert any("<br>" in label for label in trace["y"])


def test_plot_studio_spec_builds_treemap(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    tree_file = allowed_tmp / f"{tmp_path.name}_treemap.csv"
    tree_file.write_text(
        "term,category,count,adjusted_p\n"
        "cell cycle checkpoint regulation,GOBP,12,0.001\n"
        "immune response,GOBP,8,0.004\n"
        "ribosome biogenesis,KEGG,6,0.02\n"
        "photosynthesis,KEGG,4,0.03\n",
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
                "name": "Functional classes",
                "type": "enrichment_result",
                "dataPath": str(tree_file),
            },
            "plotType": "treemap",
            "params": {
                "label_column": "term",
                "parent_column": "category",
                "value_column": "count",
                "color_column": "adjusted_p",
                "color_transform": "minus_log10",
                "top_n": 4,
                "branchvalues": "total",
                "textinfo": "label+value",
                "tiling": "binary",
                "color_scale": "green_white_purple",
                "wrap_term_label": True,
                "term_label_width": 12,
            },
        },
    )

    trace = spec["data"][0]
    assert spec["plot_type"] == "treemap"
    assert trace["type"] == "treemap"
    assert trace["branchvalues"] == "total"
    assert trace["tiling"] == {"packing": "binary"}
    assert trace["marker"]["colorscale"][0][1] == "#20804f"
    assert trace["marker"]["colorbar"]["title"] == "-log10(adjusted_p)"
    assert any(parent == "parent::GOBP" for parent in trace["parents"])
    assert any("<br>" in label for label in trace["labels"])
    assert any("Grouped into 2 parent categories." == warning for warning in spec["warnings"])


def test_plot_studio_spec_builds_sunburst(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    tree_file = allowed_tmp / f"{tmp_path.name}_sunburst.csv"
    tree_file.write_text(
        "term,category,count,adjusted_p\n"
        "cell cycle checkpoint regulation,GOBP,12,0.001\n"
        "immune response,GOBP,8,0.004\n"
        "ribosome biogenesis,KEGG,6,0.02\n"
        "photosynthesis,KEGG,4,0.03\n",
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
                "name": "Functional classes",
                "type": "enrichment_result",
                "dataPath": str(tree_file),
            },
            "plotType": "sunburst",
            "params": {
                "label_column": "term",
                "parent_column": "category",
                "value_column": "count",
                "color_column": "adjusted_p",
                "color_transform": "minus_log10",
                "top_n": 4,
                "branchvalues": "total",
                "maxdepth": 3,
                "textinfo": "label+percent parent",
                "color_scale": "green_white_purple",
                "wrap_term_label": True,
                "term_label_width": 12,
            },
        },
    )

    trace = spec["data"][0]
    assert spec["plot_type"] == "sunburst"
    assert trace["type"] == "sunburst"
    assert trace["branchvalues"] == "total"
    assert trace["maxdepth"] == 3
    assert trace["marker"]["colorscale"][0][1] == "#20804f"
    assert trace["marker"]["colorbar"]["title"] == "-log10(adjusted_p)"
    assert any(parent == "parent::GOBP" for parent in trace["parents"])
    assert any("<br>" in label for label in trace["labels"])
    assert any("Grouped into 2 parent categories." == warning for warning in spec["warnings"])


def test_plot_studio_spec_builds_wordcloud(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    cloud_file = allowed_tmp / f"{tmp_path.name}_wordcloud.csv"
    cloud_file.write_text(
        "term,count,adjusted_p\n"
        "cell cycle checkpoint regulation,12,0.001\n"
        "immune response,8,0.004\n"
        "ribosome biogenesis,6,0.02\n"
        "photosynthesis,4,0.03\n"
        "stress signal,3,0.04\n"
        "protein folding,2,0.05\n"
        "membrane transport,1,0.08\n"
        "secondary metabolism,1,0.09\n"
        "hormone response,1,0.10\n"
        "chromatin,1,0.12\n",
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
                "name": "Functional words",
                "type": "enrichment_result",
                "dataPath": str(cloud_file),
            },
            "plotType": "wordcloud",
            "params": {
                "term_column": "term",
                "weight_column": "count",
                "color_column": "adjusted_p",
                "color_transform": "minus_log10",
                "top_n": 10,
                "sort_by": "weight",
                "min_font_size": 10,
                "max_font_size": 44,
                "cloud_width": 12,
                "cloud_height": 7,
                "rotate_fraction": 0.3,
                "wrap_term_label": True,
                "term_label_width": 12,
            },
        },
    )

    assert spec["plot_type"] == "wordcloud"
    assert [trace["type"] for trace in spec["data"]] == ["scatter", "scatter"]
    assert all(trace["mode"] == "text" for trace in spec["data"])
    assert spec["layout"]["showlegend"] is False
    assert spec["layout"]["xaxis"]["visible"] is False
    assert spec["layout"]["yaxis"]["visible"] is False
    all_sizes = [size for trace in spec["data"] for size in trace["textfont"]["size"]]
    assert min(all_sizes) == 10
    assert max(all_sizes) == 44
    all_labels = [label for trace in spec["data"] for label in trace["text"]]
    assert any("<br>" in label for label in all_labels)
    assert any(trace["textangle"] == -90 for trace in spec["data"])
    assert any("Text color ranking uses adjusted_p" in warning for warning in spec["warnings"])


def test_plot_studio_spec_builds_sankey(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    flow_file = allowed_tmp / f"{tmp_path.name}_sankey.csv"
    flow_file.write_text(
        "source,target,value,group\n"
        "GO,cell cycle,12,BP\n"
        "GO,immune response,8,BP\n"
        "KEGG,ribosome,6,pathway\n"
        "KEGG,photosynthesis,4,pathway\n"
        "Reactome,apoptosis,3,pathway\n",
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
                "name": "Functional flow",
                "type": "enrichment_result",
                "dataPath": str(flow_file),
            },
            "plotType": "sankey",
            "params": {
                "source_column": "source",
                "target_column": "target",
                "value_column": "value",
                "group_column": "group",
                "top_n": 4,
                "min_value": 3,
                "sort_by": "value",
                "arrangement": "freeform",
                "node_pad": 20,
                "node_thickness": 14,
                "node_line_width": 1.1,
                "node_line_color": "#111827",
                "link_opacity": 0.42,
                "label_font_size": 13,
            },
        },
    )

    trace = spec["data"][0]
    assert spec["plot_type"] == "sankey"
    assert trace["type"] == "sankey"
    assert trace["arrangement"] == "freeform"
    assert trace["node"]["pad"] == 20
    assert trace["node"]["thickness"] == 14
    assert trace["node"]["line"] == {"color": "#111827", "width": 1.1}
    assert trace["textfont"]["size"] == 13
    assert len(trace["link"]["value"]) == 4
    assert trace["link"]["value"][0] == 12.0
    assert trace["link"]["color"][0].startswith("rgba(")
    assert "xaxis" not in spec["layout"]
    assert any("Resolved" in warning for warning in spec["warnings"])


def test_plot_studio_spec_builds_composition_bar(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    composition_file = allowed_tmp / f"{tmp_path.name}_composition.csv"
    composition_file.write_text(
        "sample,category,abundance,condition\n"
        "S1,A,10,case\n"
        "S1,B,5,case\n"
        "S1,C,1,case\n"
        "S2,A,6,control\n"
        "S2,B,2,control\n"
        "S2,D,2,control\n",
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
                "name": "Taxa composition",
                "type": "taxonomy_table",
                "dataPath": str(composition_file),
            },
            "plotType": "composition_bar",
            "params": {
                "sample_column": "sample",
                "category_column": "category",
                "value_column": "abundance",
                "group_column": "condition",
                "top_n": 2,
                "normalize": "percent",
                "other_label": "Other taxa",
                "sort_samples": "name",
                "sort_categories": "total_desc",
                "orientation": "vertical",
                "bar_mode": "stack",
                "bar_opacity": 0.7,
                "bar_line_width": 1,
                "bar_line_color": "#111827",
                "show_percent_axis": True,
                "show_legend": True,
            },
        },
    )

    assert spec["plot_type"] == "composition_bar"
    assert [trace["type"] for trace in spec["data"]] == ["bar", "bar", "bar"]
    assert [trace["name"] for trace in spec["data"]] == ["A", "B", "Other taxa"]
    assert spec["layout"]["barmode"] == "stack"
    assert spec["layout"]["yaxis"]["range"] == [0, 100]
    assert spec["data"][0]["marker"]["opacity"] == 0.7
    assert spec["data"][0]["marker"]["line"] == {"color": "#111827", "width": 1.0}
    assert round(sum(trace["y"][0] for trace in spec["data"]), 6) == 100
    assert any("Collapsed 2 lower-abundance categories" in warning for warning in spec["warnings"])
    assert any("normalized to percent" in warning for warning in spec["warnings"])


def test_plot_studio_spec_builds_donut(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    donut_file = allowed_tmp / f"{tmp_path.name}_donut.csv"
    donut_file.write_text(
        "sample,category,abundance,condition\n"
        "S1,A,10,case\n"
        "S1,B,5,case\n"
        "S1,C,1,case\n"
        "S2,A,6,control\n"
        "S2,D,4,control\n",
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
                "name": "Taxa donut",
                "type": "taxonomy_table",
                "dataPath": str(donut_file),
            },
            "plotType": "donut",
            "params": {
                "category_column": "category",
                "value_column": "abundance",
                "group_column": "condition",
                "selected_group": "case",
                "top_n": 2,
                "other_label": "Other taxa",
                "hole": 0.5,
                "textinfo": "label+percent",
                "textposition": "outside",
                "pull_largest": True,
                "pull_size": 0.08,
                "rotation": 25,
                "show_legend": False,
            },
        },
    )

    trace = spec["data"][0]
    assert spec["plot_type"] == "donut"
    assert trace["type"] == "pie"
    assert trace["hole"] == 0.5
    assert trace["labels"] == ["A", "B", "Other taxa"]
    assert trace["values"] == [10.0, 5.0, 1.0]
    assert trace["pull"][0] == 0.08
    assert trace["rotation"] == 25.0
    assert spec["layout"]["showlegend"] is False
    assert "xaxis" not in spec["layout"]
    assert any("Filtered donut rows to condition=case" in warning for warning in spec["warnings"])
    assert any("Collapsed 1 lower-value categories" in warning for warning in spec["warnings"])


def test_plot_studio_spec_builds_radar_and_parallel_coordinates(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    profile_file = allowed_tmp / f"{tmp_path.name}_profiles.csv"
    profile_file.write_text(
        "sample,group,m1,m2,m3,m4,score\n"
        "S1,A,1,5,2,8,0.2\n"
        "S2,A,2,4,3,7,0.3\n"
        "S3,B,7,2,8,3,0.8\n"
        "S4,B,8,1,7,2,0.9\n",
        encoding="utf-8",
    )
    source = {
        "sourceKind": "analysis_output",
        "name": "Profile table",
        "type": "unknown_table",
        "dataPath": str(profile_file),
    }
    client = TestClient(app)

    radar = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": source,
            "plotType": "radar",
            "params": {
                "value_columns": ["m1", "m2", "m3", "m4"],
                "group": "group",
                "aggregation": "mean",
                "normalize": "minmax_by_axis",
                "fill": True,
            },
        },
    )

    assert radar["plot_type"] == "radar"
    assert [trace["type"] for trace in radar["data"]] == ["scatterpolar", "scatterpolar"]
    assert radar["data"][0]["theta"][-1] == "m1"
    assert radar["data"][0]["fill"] == "toself"
    assert radar["layout"]["polar"]["radialaxis"]["range"] == [0, 1]
    assert "xaxis" not in radar["layout"]

    parallel = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": source,
            "plotType": "parallel_coordinates",
            "params": {
                "dimensions": ["m1", "m2", "m3", "m4"],
                "color": "score",
                "max_dimensions": 4,
                "max_rows": 4,
                "color_scale": "viridis",
                "show_colorbar": True,
            },
        },
    )

    assert parallel["plot_type"] == "parallel_coordinates"
    trace = parallel["data"][0]
    assert trace["type"] == "parcoords"
    assert [dimension["label"] for dimension in trace["dimensions"]] == ["m1", "m2", "m3", "m4"]
    assert trace["line"]["color"] == [0.2, 0.3, 0.8, 0.9]
    assert trace["line"]["colorbar"]["title"] == "score"
    assert "yaxis" not in parallel["layout"]


def test_plot_studio_rejects_multisample_plots_for_single_row_tables(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_single_row_profile.csv"
    table_file.write_text(
        "sample,group,Length,S1,S2,S3\n"
        "row_1,A,10,2,4,8\n",
        encoding="utf-8",
    )
    source = {
        "sourceKind": "analysis_output",
        "name": "Single row table",
        "type": "unknown_table",
        "dataPath": str(table_file),
    }
    client = TestClient(app)

    summary = inspect_table(table_file)
    recommendations = recommend_plot_types("unknown_table", summary)
    assert "scatter" not in recommendations
    assert "radar" not in recommendations
    assert recommendations[:2] == ["bar", "histogram"]

    report = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={"source": source},
    )
    assert report["selected_plot"]["id"] == "bar"
    assert "scatter" not in report["recommended_plot_ids"]
    assert "radar" not in report["recommended_plot_ids"]
    report_suitability = report["agent_context"]["plot_suitability"]
    assert report_suitability["current_data"] == [
        {"label": "Rows", "value": 1},
        {"label": "Numeric columns", "value": 4},
        {"label": "Categorical columns", "value": 2},
    ]
    assert report_suitability["selected_requirements"] == [
        "Compatible numeric/categorical mappings for this chart type"
    ]

    scatter = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={"source": source, "plotType": "scatter"},
    )
    radar = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": source,
            "plotType": "radar",
            "params": {"value_columns": ["Length", "S1", "S2", "S3"]},
        },
    )

    assert scatter["data"] == []
    assert any("at least two complete x/y" in warning for warning in scatter["warnings"])
    assert scatter["renderability"]["status"] == "blocked"
    assert scatter["renderability"]["current_data"] == [
        {"label": "Rows", "value": 1},
        {"label": "Numeric columns", "value": 4},
        {"label": "Categorical columns", "value": 2},
    ]
    assert "At least two complete x/y observation rows" in scatter["renderability"]["requirements"]
    assert scatter["renderability"]["recommended_plot_ids"][:2] == ["bar", "histogram"]
    assert radar["data"] == []
    assert any("at least two sample or group profiles" in warning for warning in radar["warnings"])
    assert "At least two sample or group profiles" in radar["renderability"]["requirements"]

    for plot_type, expected in [
        ("bubble", "x/y/size"),
        ("density_contour", "x/y"),
        ("scatter_3d", "x/y/z"),
        ("parallel_coordinates", "sample or group profiles"),
        ("correlation", "at least two observation rows"),
    ]:
        blocked = _request(
            client,
            "POST",
            "/api/plot-studio/spec",
            json={"source": source, "plotType": plot_type},
        )
        assert blocked["plot_type"] == plot_type
        assert blocked["data"] == []
        assert any(expected in warning for warning in blocked["warnings"])
        assert blocked["renderability"]["status"] == "blocked"
        assert blocked["renderability"]["requirements"]


def test_plot_studio_recommends_profile_charts_for_single_gene_matrices(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_single_gene_matrix.csv"
    table_file.write_text(
        "gene_short_name,gene_id,Length,Group A-1,Group A-2,Group B-1,Group B-2,Group C-1,Group C-2\n"
        "AL590714.1,ENSG00000268387,1120,8.2,8.6,3.1,3.5,6.7,6.4\n",
        encoding="utf-8",
    )

    summary = inspect_table(table_file)
    recommendations = recommend_plot_types("unknown_table", summary)

    assert summary["signals"]["matrix_profile"]["kind"] == "expression_like"
    assert recommendations[:6] == ["bar", "grouped_dotplot", "boxplot", "raincloud", "histogram", "violin"]
    assert "scatter" not in recommendations
    assert "radar" not in recommendations
    assert "correlation" not in recommendations


def test_plot_studio_data_shape_overrides_expression_matrix_label_for_single_gene_profiles(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_single_gene_expression_matrix.csv"
    table_file.write_text(
        "gene_short_name,gene_id,Length,Group A-1,Group A-2,Group B-1,Group B-2\n"
        "AL590714.1,ENSG00000268387,1120,8.2,8.6,3.1,3.5\n",
        encoding="utf-8",
    )
    source = {
        "sourceKind": "analysis_output",
        "name": "Single gene expression matrix",
        "type": "expression_matrix",
        "dataPath": str(table_file),
    }
    client = TestClient(app)

    summary = inspect_table(table_file)
    recommendations = recommend_plot_types("expression_matrix", summary)
    report = _request(
        client,
        "POST",
        "/api/plot-studio/report",
        json={"source": source},
    )

    assert summary["signals"]["matrix_profile"]["kind"] == "expression_like"
    assert recommendations[:6] == ["bar", "grouped_dotplot", "boxplot", "raincloud", "histogram", "violin"]
    assert "heatmap" not in recommendations[:6]
    assert "correlation" not in recommendations
    assert report["selected_plot"]["id"] == "bar"
    assert report["recommended_plot_ids"][:4] == ["bar", "grouped_dotplot", "boxplot", "raincloud"]
    assert report["agent_context"]["plot_suitability"]["selected_requirements"] == [
        "Compatible numeric/categorical mappings for this chart type"
    ]


def test_plot_studio_detects_small_single_gene_profiles(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_four_sample_profile.csv"
    table_file.write_text(
        "gene_short_name,gene_id,Length,S1,S2,S3,S4\n"
        "AL590714.1,ENSG00000268387,1120,8.2,8.6,3.1,3.5\n",
        encoding="utf-8",
    )
    source = {
        "sourceKind": "analysis_output",
        "name": "Four sample profile",
        "type": "unknown_table",
        "dataPath": str(table_file),
    }
    client = TestClient(app)

    summary = inspect_table(table_file)
    recommendations = recommend_plot_types("unknown_table", summary)
    boxplot = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={"source": source, "plotType": "boxplot"},
    )

    assert summary["signals"]["matrix_profile"]["kind"] == "expression_like"
    assert summary["signals"]["matrix_profile"]["value_columns"] == ["S1", "S2", "S3", "S4"]
    assert "Length" in summary["signals"]["matrix_profile"]["excluded_numeric_columns"]
    assert recommendations[:4] == ["bar", "grouped_dotplot", "boxplot", "raincloud"]
    assert boxplot["layout"]["title"]["text"] == "Boxplot profile: AL590714.1"
    assert boxplot["layout"]["xaxis"]["title"]["text"] == "inferred group"
    assert boxplot["layout"]["yaxis"]["title"]["text"] == "sample-like value"
    assert [trace["name"] for trace in boxplot["data"]] == ["Profile"]
    assert boxplot["data"][0]["y"] == [8.2, 8.6, 3.1, 3.5]
    assert boxplot["data"][0]["customdata"] == ["S1", "S2", "S3", "S4"]


def test_plot_studio_single_gene_matrix_profile_charts_use_sample_columns(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_single_gene_profile_plot.csv"
    table_file.write_text(
        "gene_short_name,gene_id,Length,Group A-1,Group A-2,Group B-1,Group B-2,Group C-1,Group C-2\n"
        "AL590714.1,ENSG00000268387,1120,8.2,8.6,3.1,3.5,6.7,6.4\n",
        encoding="utf-8",
    )
    source = {
        "sourceKind": "analysis_output",
        "name": "Single gene matrix",
        "type": "unknown_table",
        "dataPath": str(table_file),
    }
    client = TestClient(app)

    bar = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={"source": source, "plotType": "bar"},
    )
    histogram = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={
            "source": source,
            "plotType": "histogram",
            "params": {"show_rug": True, "cumulative": True},
        },
    )
    boxplot = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={"source": source, "plotType": "boxplot"},
    )
    violin = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={"source": source, "plotType": "violin"},
    )
    grouped_dotplot = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={"source": source, "plotType": "grouped_dotplot"},
    )
    raincloud = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={"source": source, "plotType": "raincloud"},
    )

    assert bar["plot_type"] == "bar"
    assert bar["layout"]["title"]["text"] == "Bar profile: AL590714.1"
    assert bar["layout"]["xaxis"]["title"]["text"] == "sample-like columns"
    assert "Length" not in bar["data"][0]["x"]
    assert bar["data"][0]["x"] == [
        "Group A-1",
        "Group A-2",
        "Group B-1",
        "Group B-2",
        "Group C-1",
        "Group C-2",
    ]
    assert bar["data"][0]["y"] == [8.2, 8.6, 3.1, 3.5, 6.7, 6.4]
    assert bar["data"][0]["customdata"] == [
        ["Group A"],
        ["Group A"],
        ["Group B"],
        ["Group B"],
        ["Group C"],
        ["Group C"],
    ]
    assert len(bar["data"][0]["marker"]["color"]) == 6
    assert [trace["name"] for trace in bar["data"][1:]] == ["Group A", "Group B", "Group C"]
    assert bar["layout"]["legend"]["title"]["text"] == "Inferred group"
    assert any(
        "Skipped numeric metadata columns" in warning and "Length" in warning
        for warning in bar["warnings"]
    )

    assert histogram["plot_type"] == "histogram"
    assert histogram["layout"]["title"]["text"] == "Histogram profile: AL590714.1"
    assert histogram["layout"]["xaxis"]["title"]["text"] == "sample-like value"
    histogram_traces = [trace for trace in histogram["data"] if trace["type"] == "histogram"]
    rug_traces = [trace for trace in histogram["data"] if trace["type"] == "scattergl"]
    assert [trace["name"] for trace in histogram_traces] == ["Group A", "Group B", "Group C"]
    assert [trace["name"] for trace in rug_traces] == ["Group A rug", "Group B rug", "Group C rug"]
    assert all(trace["cumulative"]["enabled"] is True for trace in histogram_traces)
    assert histogram["data"][0]["x"] == [8.2, 8.6]
    assert histogram["data"][0]["customdata"] == ["Group A-1", "Group A-2"]
    assert histogram_traces[1]["x"] == [3.1, 3.5]
    assert histogram_traces[1]["customdata"] == ["Group B-1", "Group B-2"]
    assert rug_traces[0]["text"] == ["Group A-1", "Group A-2"]
    assert histogram["layout"]["legend"]["title"]["text"] == "Inferred group"
    assert len(histogram["layout"]["shapes"]) == 3
    assert any(
        "Skipped numeric metadata columns" in warning and "Length" in warning
        for warning in histogram["warnings"]
    )

    assert boxplot["plot_type"] == "boxplot"
    assert boxplot["layout"]["title"]["text"] == "Boxplot profile: AL590714.1"
    assert boxplot["layout"]["xaxis"]["title"]["text"] == "inferred group"
    assert boxplot["layout"]["yaxis"]["title"]["text"] == "sample-like value"
    assert [trace["name"] for trace in boxplot["data"]] == ["Group A", "Group B", "Group C"]
    assert boxplot["data"][0]["y"] == [8.2, 8.6]
    assert boxplot["data"][0]["customdata"] == ["Group A-1", "Group A-2"]
    assert any(
        "Skipped numeric metadata columns" in warning and "Length" in warning
        for warning in boxplot["warnings"]
    )

    assert violin["plot_type"] == "violin"
    assert violin["layout"]["title"]["text"] == "Violin profile: AL590714.1"
    assert [trace["name"] for trace in violin["data"]] == ["Group A", "Group B", "Group C"]
    assert violin["data"][1]["y"] == [3.1, 3.5]
    assert violin["data"][1]["customdata"] == ["Group B-1", "Group B-2"]

    assert grouped_dotplot["plot_type"] == "grouped_dotplot"
    assert grouped_dotplot["layout"]["title"]["text"] == "Grouped dot profile: AL590714.1"
    assert grouped_dotplot["layout"]["xaxis"]["title"]["text"] == "inferred group"
    assert grouped_dotplot["layout"]["yaxis"]["title"]["text"] == "sample-like value"
    assert [trace["name"] for trace in grouped_dotplot["data"]] == ["Group A", "Group B", "Group C"]
    assert grouped_dotplot["data"][2]["y"] == [6.7, 6.4]
    assert grouped_dotplot["data"][2]["text"] == ["Group C-1", "Group C-2"]
    assert any(
        "Skipped numeric metadata columns" in warning and "Length" in warning
        for warning in grouped_dotplot["warnings"]
    )

    assert raincloud["plot_type"] == "raincloud"
    assert raincloud["layout"]["title"]["text"] == "Raincloud profile: AL590714.1"
    assert raincloud["layout"]["xaxis"]["title"]["text"] == "inferred group"
    assert raincloud["layout"]["yaxis"]["title"]["text"] == "sample-like value"
    point_traces = [trace for trace in raincloud["data"] if trace["type"] == "scattergl"]
    assert [trace["name"] for trace in point_traces] == ["Group A", "Group B", "Group C"]
    assert point_traces[0]["text"] == ["Group A-1", "Group A-2"]
    assert any(
        "Skipped numeric metadata columns" in warning and "Length" in warning
        for warning in raincloud["warnings"]
    )


def test_plot_studio_report_summarizes_single_gene_profile_values(tmp_path: Path) -> None:
    allowed_tmp = ROOT / "data" / "tmp_plot_studio_tests"
    allowed_tmp.mkdir(parents=True, exist_ok=True)
    table_file = allowed_tmp / f"{tmp_path.name}_single_gene_profile_report.csv"
    table_file.write_text(
        "gene_short_name,gene_id,Length,Group A-1,Group A-2,Group B-1,Group B-2,Group C-1,Group C-2\n"
        "AL590714.1,ENSG00000268387,1120,8.2,8.6,3.1,3.5,6.7,6.4\n",
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
                "name": "Single gene matrix",
                "type": "unknown_table",
                "dataPath": str(table_file),
            },
            "plotType": "bar",
        },
    )

    sections = {section["title"]: section["text"] for section in report["report"]["sections"]}
    profile = report["agent_context"]["data_profile"]
    suitability = report["agent_context"]["plot_suitability"]
    assert profile["kind"] == "single_row_expression_profile"
    assert profile["identifier"] == "AL590714.1"
    assert profile["value_count"] == 6
    assert profile["maximum"] == {"column": "Group A-2", "value": 8.6}
    assert profile["minimum"] == {"column": "Group B-1", "value": 3.1}
    assert profile["inferred_groups"] == [
        {"group": "Group A", "count": 2},
        {"group": "Group B", "count": 2},
        {"group": "Group C", "count": 2},
    ]
    assert profile["group_statistics"] == [
        {
            "group": "Group A",
            "count": 2,
            "mean": 8.4,
            "minimum": {"column": "Group A-1", "value": 8.2},
            "maximum": {"column": "Group A-2", "value": 8.6},
        },
        {
            "group": "Group B",
            "count": 2,
            "mean": 3.3,
            "minimum": {"column": "Group B-1", "value": 3.1},
            "maximum": {"column": "Group B-2", "value": 3.5},
        },
        {
            "group": "Group C",
            "count": 2,
            "mean": 6.55,
            "minimum": {"column": "Group C-2", "value": 6.4},
            "maximum": {"column": "Group C-1", "value": 6.7},
        },
    ]
    assert profile["highest_values"][:3] == [
        {"column": "Group A-2", "value": 8.6},
        {"column": "Group A-1", "value": 8.2},
        {"column": "Group C-1", "value": 6.7},
    ]
    assert (
        "Single-row expression profile for AL590714.1 contains 6 sample-like value(s)"
        in sections["Signals to inspect"]
    )
    assert (
        "Highest values: Group A-2=8.6, Group A-1=8.2, Group C-1=6.7"
        in sections["Figure interpretation"]
    )
    assert "Inferred column groups are Group A (n=2), Group B (n=2), Group C (n=2)" in sections["Figure interpretation"]
    assert "Group means are Group A=8.4, Group B=3.3, Group C=6.55" in sections["Figure interpretation"]
    assert suitability["recommended_plot_ids"][:6] == ["bar", "grouped_dotplot", "boxplot", "raincloud", "histogram", "violin"]
    assert suitability["selected_is_recommended"] is True
    assert suitability["current_data"] == [
        {"label": "Rows", "value": 1},
        {"label": "Numeric columns", "value": 7},
        {"label": "Categorical columns", "value": 2},
        {"label": "Sample-like columns", "value": 6},
    ]
    assert suitability["selected_requirements"] == [
        "Compatible numeric/categorical mappings for this chart type"
    ]
    assert {"scatter", "radar", "correlation"}.issubset(set(suitability["not_recommended_plot_ids"]))
    assert "Single-row expression profiles" in suitability["reason"]
    assert "grouped dot plots" in suitability["reason"]
    guidance = report["agent_context"]["report_guidance"]
    prompt = report["agent_context"]["report_prompt"]
    assert "single-row expression profile statistics" in guidance["evidence_sources"]
    assert any("highest is Group A-2=8.6" in item for item in guidance["safe_claims"])
    assert any("lowest is Group B-1=3.1" in item for item in guidance["safe_claims"])
    assert any("single-row profile as a statistically tested group comparison" in item for item in guidance["avoid_claims"])
    assert "Single-row profile AL590714.1 has 6 sample-like values" in prompt["user"]
    assert "Do not claim to see the rendered image" in prompt["system"]
    assert "Do not infer visual details" in report["agent_context"]["interpretation_rules"][1]


def test_table_inspection_and_recommendations_handle_numeric_tables() -> None:
    summary = inspect_table(DATA_FILE, max_rows=25)

    assert summary["scanned_rows"] == 25
    assert summary["column_count"] > 2
    assert summary["numeric_columns"]
    assert summary["signals"]["matrix_profile"]["kind"] == "expression_like"
    assert "Length" in summary["signals"]["matrix_profile"]["excluded_numeric_columns"]
    assert summary["signals"]["matrix_profile"]["value_columns"][0].startswith("Group ")
    assert recommend_plot_types("unknown_table", summary)[:2] == ["heatmap", "correlation"]


def test_plot_studio_expression_matrix_defaults_skip_numeric_metadata() -> None:
    source = {
        "sourceKind": "analysis_output",
        "name": "Expression matrix",
        "type": "expression_matrix",
        "dataPath": str(DATA_FILE),
    }
    client = TestClient(app)

    scatter = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={"source": source, "plotType": "scatter"},
    )
    radar = _request(
        client,
        "POST",
        "/api/plot-studio/spec",
        json={"source": source, "plotType": "radar"},
    )

    assert scatter["layout"]["title"]["text"].startswith("Scatter: Group ")
    assert "Length" not in scatter["layout"]["title"]["text"]
    assert radar["data"][0]["theta"][0].startswith("Group ")
    assert "Length" not in radar["data"][0]["theta"]
