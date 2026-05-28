from __future__ import annotations

import csv
import json
import math
from copy import deepcopy
from pathlib import Path
from statistics import fmean, median, pstdev
from typing import Any

from yzwcloud.config import PROJECT_ROOT


PLOT_STUDIO_VERSION = "0.1"
PLOTLY_PALETTE = [
    "#0f8a8f",
    "#315fd6",
    "#c44f3a",
    "#20804f",
    "#7a4fb3",
    "#b7791f",
    "#2d7a9f",
    "#9a3f6f",
]
SUPPORTED_PLOTLY_SPEC_TYPES = {
    "scatter",
    "boxplot",
    "violin",
    "bar",
    "line",
    "bubble",
    "volcano",
    "heatmap",
    "correlation",
    "enrichment_dot",
}


def _param(
    param_id: str,
    label: str,
    param_type: str,
    default: Any = None,
    *,
    options: list[str] | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    step: float | None = None,
    required: bool = False,
    help_text: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": param_id,
        "label": label,
        "type": param_type,
        "default": default,
        "required": required,
    }
    if options is not None:
        payload["options"] = options
    if min_value is not None:
        payload["min"] = min_value
    if max_value is not None:
        payload["max"] = max_value
    if step is not None:
        payload["step"] = step
    if help_text:
        payload["help"] = help_text
    return payload


def _group(group_id: str, label: str, parameters: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": group_id, "label": label, "parameters": parameters}


COMMON_THEME_GROUPS = [
    _group(
        "theme",
        "Palette and theme",
        [
            _param(
                "palette",
                "Palette",
                "select",
                "group",
                options=["group", "viridis", "blue_red", "prism_muted", "okabe_ito", "custom"],
            ),
            _param("background", "Background", "select", "white", options=["white", "transparent"]),
            _param("font_size", "Font size", "number", 13, min_value=8, max_value=28, step=1),
            _param("show_grid", "Show grid", "boolean", True),
            _param("legend_position", "Legend", "select", "right", options=["right", "top", "bottom", "none"]),
        ],
    ),
    _group(
        "export",
        "Export size and format",
        [
            _param("width", "Width", "number", 1200, min_value=320, max_value=4000, step=10),
            _param("height", "Height", "number", 760, min_value=240, max_value=3000, step=10),
            _param("dpi", "DPI", "select", "300", options=["150", "300", "600"]),
            _param("format", "Format", "select", "svg", options=["svg", "png", "pdf", "html"]),
        ],
    ),
]


PLOT_PRESETS: list[dict[str, Any]] = [
    {
        "id": "scatter",
        "label": "Scatter",
        "engine": "plotly",
        "description": "Two-variable relationship plot with optional group color, size mapping, and trend line.",
        "default_params": {
            "point_size": 8,
            "point_alpha": 0.85,
            "trendline": "none",
            "confidence_ellipse": False,
            "x_log": False,
            "y_log": False,
        },
        "parameter_groups": [
            _group(
                "mapping",
                "Data mapping",
                [
                    _param("x", "X axis", "column", None, required=True),
                    _param("y", "Y axis", "column", None, required=True),
                    _param("color", "Color by", "column_or_none", None),
                    _param("size", "Size by", "column_or_none", None),
                    _param("label", "Point label", "column_or_none", None),
                ],
            ),
            _group(
                "statistics",
                "Statistics and fit",
                [
                    _param("trendline", "Trend line", "select", "none", options=["none", "linear", "loess"]),
                    _param("confidence_ellipse", "Confidence ellipse", "boolean", False),
                    _param("ellipse_level", "Ellipse level", "number", 0.95, min_value=0.5, max_value=0.99, step=0.01),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "boxplot",
        "label": "Boxplot",
        "engine": "plotly",
        "description": "Grouped distribution plot with optional points, mean marker, and pairwise tests.",
        "default_params": {
            "show_points": True,
            "point_jitter": 0.35,
            "show_mean": True,
            "notched": False,
            "pairwise_test": "none",
        },
        "parameter_groups": [
            _group(
                "mapping",
                "Data mapping",
                [
                    _param("y", "Value", "column", None, required=True),
                    _param("group", "Group", "column", None, required=True),
                    _param("color", "Color by", "column_or_none", None),
                    _param("facet", "Facet by", "column_or_none", None),
                ],
            ),
            _group(
                "distribution",
                "Distribution display",
                [
                    _param("show_points", "Show individual points", "boolean", True),
                    _param("point_jitter", "Point jitter", "number", 0.35, min_value=0, max_value=1, step=0.05),
                    _param("show_mean", "Show mean", "boolean", True),
                    _param("notched", "Notched boxes", "boolean", False),
                    _param("box_width", "Box width", "number", 0.62, min_value=0.2, max_value=1.0, step=0.02),
                ],
            ),
            _group(
                "statistics",
                "Statistics and error bars",
                [
                    _param(
                        "pairwise_test",
                        "Pairwise test",
                        "select",
                        "none",
                        options=["none", "t_test", "wilcoxon", "anova_then_tukey"],
                    ),
                    _param("multiple_testing", "Multiple testing", "select", "BH", options=["none", "BH", "bonferroni"]),
                    _param("show_p_values", "Show p-values", "boolean", False),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "violin",
        "label": "Violin",
        "engine": "plotly",
        "description": "Distribution shape plot for group comparisons, optionally overlaid with box and points.",
        "default_params": {"show_box": True, "show_points": "outliers", "span_mode": "soft"},
        "parameter_groups": [
            _group(
                "mapping",
                "Data mapping",
                [
                    _param("y", "Value", "column", None, required=True),
                    _param("group", "Group", "column", None, required=True),
                    _param("color", "Color by", "column_or_none", None),
                ],
            ),
            _group(
                "distribution",
                "Distribution display",
                [
                    _param("show_box", "Show box", "boolean", True),
                    _param("show_points", "Points", "select", "outliers", options=["none", "outliers", "all"]),
                    _param("bandwidth", "Bandwidth", "number_or_auto", "auto", min_value=0.01, max_value=2.0, step=0.01),
                    _param("side", "Side", "select", "both", options=["both", "positive", "negative"]),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "bar",
        "label": "Bar",
        "engine": "echarts",
        "description": "Summary bar chart with configurable aggregation and error bars.",
        "default_params": {"aggregation": "mean", "error_bar": "sem", "orientation": "vertical"},
        "parameter_groups": [
            _group(
                "mapping",
                "Data mapping",
                [
                    _param("category", "Category", "column", None, required=True),
                    _param("value", "Value", "column", None, required=True),
                    _param("color", "Color by", "column_or_none", None),
                ],
            ),
            _group(
                "statistics",
                "Statistics and error bars",
                [
                    _param("aggregation", "Aggregation", "select", "mean", options=["mean", "median", "sum", "count"]),
                    _param("error_bar", "Error bar", "select", "sem", options=["none", "sd", "sem", "ci95"]),
                    _param("show_points", "Overlay points", "boolean", False),
                    _param("orientation", "Orientation", "select", "vertical", options=["vertical", "horizontal"]),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "line",
        "label": "Line",
        "engine": "echarts",
        "description": "Time-course or ordered series plot with optional grouping and smoothing.",
        "default_params": {"line_shape": "linear", "show_points": True, "smooth": False},
        "parameter_groups": [
            _group(
                "mapping",
                "Data mapping",
                [
                    _param("x", "X axis", "column", None, required=True),
                    _param("y", "Y axis", "column", None, required=True),
                    _param("series", "Series", "column_or_none", None),
                ],
            ),
            _group(
                "series",
                "Series display",
                [
                    _param("line_shape", "Line shape", "select", "linear", options=["linear", "spline", "hv", "vh"]),
                    _param("show_points", "Show points", "boolean", True),
                    _param("smooth", "Smooth line", "boolean", False),
                    _param("connect_gaps", "Connect missing values", "boolean", False),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "heatmap",
        "label": "Heatmap",
        "engine": "echarts",
        "description": "Matrix heatmap with row and column scaling, clustering, annotations, and labels.",
        "default_params": {
            "scale": "row_zscore",
            "cluster_rows": True,
            "cluster_columns": True,
            "show_dendrogram": True,
            "top_n": 50,
        },
        "parameter_groups": [
            _group(
                "mapping",
                "Data mapping",
                [
                    _param("row_id", "Row ID", "column", None),
                    _param("value_columns", "Value columns", "numeric_columns", None, required=True),
                    _param("column_annotation", "Column annotation", "column_or_none", None),
                    _param("row_annotation", "Row annotation", "column_or_none", None),
                ],
            ),
            _group(
                "clustering",
                "Clustering",
                [
                    _param("scale", "Scale", "select", "row_zscore", options=["none", "row_zscore", "column_zscore", "log2"]),
                    _param("cluster_rows", "Cluster rows", "boolean", True),
                    _param("cluster_columns", "Cluster columns", "boolean", True),
                    _param("show_dendrogram", "Show dendrogram", "boolean", True),
                    _param("distance", "Distance", "select", "correlation", options=["correlation", "euclidean", "manhattan"]),
                    _param("linkage", "Linkage", "select", "average", options=["average", "complete", "single", "ward"]),
                    _param("top_n", "Top rows", "number", 50, min_value=5, max_value=5000, step=1),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "bubble",
        "label": "Bubble",
        "engine": "plotly",
        "description": "Scatter-like chart for x/y position plus size and color encodings.",
        "default_params": {"size_scale": 18, "min_bubble_size": 4, "max_bubble_size": 48},
        "parameter_groups": [
            _group(
                "mapping",
                "Data mapping",
                [
                    _param("x", "X axis", "column", None, required=True),
                    _param("y", "Y axis", "column", None, required=True),
                    _param("size", "Bubble size", "column", None, required=True),
                    _param("color", "Color by", "column_or_none", None),
                    _param("label", "Label", "column_or_none", None),
                ],
            ),
            _group(
                "bubble",
                "Bubble style",
                [
                    _param("size_scale", "Size scale", "number", 18, min_value=1, max_value=100, step=1),
                    _param("min_bubble_size", "Min bubble size", "number", 4, min_value=1, max_value=40, step=1),
                    _param("max_bubble_size", "Max bubble size", "number", 48, min_value=8, max_value=120, step=1),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "volcano",
        "label": "Volcano",
        "engine": "plotly",
        "description": "Differential result plot using log2 fold-change and significance thresholds.",
        "default_params": {
            "log2fc_column": "log2fc",
            "p_value_column": "p_value",
            "log2fc_threshold": 1.0,
            "p_value_threshold": 0.05,
            "label_top_n": 20,
        },
        "parameter_groups": [
            _group(
                "mapping",
                "Data mapping",
                [
                    _param("gene", "Gene label", "column", "gene"),
                    _param("log2fc_column", "log2FC", "column", "log2fc", required=True),
                    _param("p_value_column", "P value", "column", "p_value", required=True),
                ],
            ),
            _group(
                "thresholds",
                "Thresholds and labels",
                [
                    _param("log2fc_threshold", "Abs log2FC threshold", "number", 1.0, min_value=0, max_value=10, step=0.1),
                    _param("p_value_threshold", "P value threshold", "number", 0.05, min_value=0, max_value=1, step=0.001),
                    _param("label_top_n", "Top labels", "number", 20, min_value=0, max_value=200, step=1),
                    _param("label_mode", "Label mode", "select", "significant", options=["none", "significant", "top_p", "custom"]),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "upset",
        "label": "UpSet",
        "engine": "echarts",
        "description": "Set intersection chart for multiple gene lists or feature groups.",
        "default_params": {"min_intersection_size": 1, "max_sets": 8, "sort_by": "intersection_size"},
        "parameter_groups": [
            _group(
                "mapping",
                "Data mapping",
                [
                    _param("item_id", "Item ID", "column", None, required=True),
                    _param("set_columns", "Set columns", "columns", None, required=True),
                ],
            ),
            _group(
                "sets",
                "Set display",
                [
                    _param("min_intersection_size", "Min intersection", "number", 1, min_value=1, max_value=1000, step=1),
                    _param("max_sets", "Max sets", "number", 8, min_value=2, max_value=20, step=1),
                    _param("sort_by", "Sort by", "select", "intersection_size", options=["intersection_size", "degree", "set_name"]),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "venn",
        "label": "Venn",
        "engine": "echarts",
        "description": "Two- to four-set overlap diagram for small set comparisons.",
        "default_params": {"max_sets": 4, "show_counts": True, "show_percent": False},
        "parameter_groups": [
            _group(
                "mapping",
                "Data mapping",
                [
                    _param("item_id", "Item ID", "column", None, required=True),
                    _param("set_columns", "Set columns", "columns", None, required=True),
                ],
            ),
            _group(
                "sets",
                "Set display",
                [
                    _param("max_sets", "Max sets", "number", 4, min_value=2, max_value=4, step=1),
                    _param("show_counts", "Show counts", "boolean", True),
                    _param("show_percent", "Show percent", "boolean", False),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "correlation",
        "label": "Correlation",
        "engine": "echarts",
        "description": "Correlation matrix heatmap with optional hierarchical clustering and group side bars.",
        "default_params": {
            "method": "pearson",
            "cluster_rows": True,
            "cluster_columns": True,
            "color_scale": "blue_white_red",
        },
        "parameter_groups": [
            _group(
                "mapping",
                "Data mapping",
                [
                    _param("value_columns", "Value columns", "numeric_columns", None, required=True),
                    _param("sample_group", "Sample group", "column_or_none", None),
                ],
            ),
            _group(
                "statistics",
                "Correlation settings",
                [
                    _param("method", "Method", "select", "pearson", options=["pearson", "spearman"]),
                    _param("cluster_rows", "Cluster rows", "boolean", True),
                    _param("cluster_columns", "Cluster columns", "boolean", True),
                    _param("show_values", "Show r values", "boolean", False),
                    _param(
                        "color_scale",
                        "Color scale",
                        "select",
                        "blue_white_red",
                        options=["blue_white_red", "viridis", "magma", "green_white_purple"],
                    ),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "enrichment_dot",
        "label": "Enrichment dot plot",
        "engine": "plotly",
        "description": "Pathway or term enrichment dot plot using ratio, count, and adjusted significance.",
        "default_params": {
            "term_column": "term",
            "x_column": "gene_ratio",
            "size_column": "count",
            "color_column": "adjusted_p",
            "top_n": 20,
        },
        "parameter_groups": [
            _group(
                "mapping",
                "Data mapping",
                [
                    _param("term_column", "Term", "column", "term", required=True),
                    _param("x_column", "X axis", "column", "gene_ratio", required=True),
                    _param("size_column", "Point size", "column", "count"),
                    _param("color_column", "Color", "column", "adjusted_p"),
                ],
            ),
            _group(
                "terms",
                "Term display",
                [
                    _param("top_n", "Top terms", "number", 20, min_value=5, max_value=200, step=1),
                    _param("sort_by", "Sort by", "select", "adjusted_p", options=["adjusted_p", "count", "gene_ratio"]),
                    _param("wrap_term_label", "Wrap labels", "boolean", True),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
]


RECOMMENDATIONS_BY_OUTPUT = {
    "gene_expression": ["boxplot", "violin", "bar"],
    "pca": ["scatter", "bubble"],
    "sample_correlation": ["correlation", "heatmap"],
    "correlation": ["correlation", "heatmap"],
    "expression_heatmap": ["heatmap", "correlation"],
    "heatmap": ["heatmap", "correlation"],
    "volcano": ["volcano", "scatter"],
    "diff": ["volcano", "heatmap", "bar"],
    "wgcna": ["heatmap", "bubble", "correlation"],
    "enrichment": ["enrichment_dot", "bar", "bubble"],
    "expression_matrix": ["boxplot", "heatmap", "correlation"],
}


def list_plot_presets() -> list[dict[str, Any]]:
    return deepcopy(PLOT_PRESETS)


def get_plot_studio_manifest() -> dict[str, Any]:
    return {
        "version": PLOT_STUDIO_VERSION,
        "engines": ["plotly", "echarts"],
        "parameter_groups": [
            "Data mapping",
            "Grouping and facets",
            "Palette and theme",
            "Statistics and error bars",
            "Labels and annotations",
            "Export size and format",
        ],
        "presets": list_plot_presets(),
    }


def recommend_plot_types(source_type: str, table_summary: dict[str, Any] | None = None) -> list[str]:
    normalized_type = source_type.lower()
    for key, plot_ids in RECOMMENDATIONS_BY_OUTPUT.items():
        if key in normalized_type:
            return plot_ids[:]

    if table_summary:
        numeric_count = len(table_summary.get("numeric_columns") or [])
        categorical_count = len(table_summary.get("categorical_columns") or [])
        if numeric_count >= 2 and categorical_count >= 1:
            return ["scatter", "boxplot", "heatmap"]
        if numeric_count >= 2:
            return ["scatter", "correlation", "heatmap"]
        if numeric_count == 1 and categorical_count >= 1:
            return ["boxplot", "bar", "violin"]
    return ["scatter", "boxplot", "bar"]


def create_plot_studio_report(
    source: dict[str, Any],
    *,
    plot_type: str | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_type = str(source.get("type") or source.get("output_type") or "")
    data_path, path_reason = _select_source_table(source)
    table_summary = inspect_table(data_path) if data_path else None
    recommended_plot_ids = recommend_plot_types(source_type, table_summary)
    selected_plot_id = _select_plot_id(plot_type, recommended_plot_ids)
    selected_preset = next(item for item in PLOT_PRESETS if item["id"] == selected_plot_id)
    report = _build_report(
        source=source,
        source_type=source_type,
        selected_preset=selected_preset,
        table_summary=table_summary,
        params=params or {},
        path_reason=path_reason,
    )
    return {
        "version": PLOT_STUDIO_VERSION,
        "source": _source_summary(source, data_path),
        "selected_plot": {
            "id": selected_preset["id"],
            "label": selected_preset["label"],
            "engine": selected_preset["engine"],
            "default_params": selected_preset["default_params"],
        },
        "recommended_plot_ids": recommended_plot_ids,
        "table_summary": table_summary,
        "report": report,
    }


def create_plot_studio_spec(
    source: dict[str, Any],
    *,
    plot_type: str | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_params = params or {}
    source_type = str(source.get("type") or source.get("output_type") or "")
    data_path, path_reason = _select_source_table(source)
    if data_path is None:
        selected_plot_id = _select_plot_id(plot_type, recommend_plot_types(source_type))
        return _empty_plot_spec(selected_plot_id, "No readable table was found for this source.")

    table_summary = inspect_table(data_path)
    selected_plot_id = _select_plot_id(plot_type, recommend_plot_types(source_type, table_summary))
    columns, records = _load_table_records(
        data_path,
        max_rows=_bounded_int(resolved_params.get("max_rows"), 800, 50, 5000),
    )
    numeric_columns = [
        column
        for column in table_summary["numeric_columns"]
        if column in columns and _numeric_value_count(records, column) > 0
    ]
    categorical_columns = [column for column in table_summary["categorical_columns"] if column in columns]

    context = {
        "source": source,
        "source_type": source_type,
        "path_reason": path_reason,
        "columns": columns,
        "records": records,
        "numeric_columns": numeric_columns,
        "categorical_columns": categorical_columns,
        "table_summary": table_summary,
        "params": resolved_params,
    }
    builders = {
        "scatter": _build_scatter_spec,
        "boxplot": _build_boxplot_spec,
        "violin": _build_violin_spec,
        "bar": _build_bar_spec,
        "line": _build_line_spec,
        "bubble": _build_bubble_spec,
        "volcano": _build_volcano_spec,
        "heatmap": _build_heatmap_spec,
        "correlation": _build_correlation_spec,
        "enrichment_dot": _build_enrichment_dot_spec,
    }
    builder = builders.get(selected_plot_id)
    if builder is None:
        return _empty_plot_spec(
            selected_plot_id,
            f"{selected_plot_id} rendering is planned; choose a Plotly-ready type first.",
            table_summary=table_summary,
        )

    spec = builder(context)
    spec.update(
        {
            "version": PLOT_STUDIO_VERSION,
            "plot_type": selected_plot_id,
            "engine": "plotly",
            "source": _source_summary(source, data_path),
            "table_summary": table_summary,
            "path_reason": path_reason,
            "supported_plot_types": sorted(SUPPORTED_PLOTLY_SPEC_TYPES),
        }
    )
    return spec


def inspect_table(path: Path, *, max_rows: int = 2000) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        header, rows, truncated = _read_xlsx_rows(path, max_rows=max_rows)
        file_format = "xlsx"
    else:
        header, rows, truncated = _read_delimited_rows(path, max_rows=max_rows)
        file_format = "delimited"

    columns = _clean_header(header)
    column_stats = _collect_column_stats(columns, rows)
    numeric_columns = [name for name, stats in column_stats.items() if stats["kind"] == "numeric"]
    categorical_columns = [name for name, stats in column_stats.items() if stats["kind"] != "numeric"]
    signals = _detect_table_signals(columns, rows)

    return {
        "path": str(path),
        "filename": path.name,
        "format": file_format,
        "scanned_rows": len(rows),
        "truncated": truncated,
        "column_count": len(columns),
        "columns": columns,
        "numeric_columns": numeric_columns,
        "categorical_columns": categorical_columns,
        "column_summaries": column_stats,
        "signals": signals,
    }


def _build_scatter_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    numeric_columns = context["numeric_columns"]
    x_column = _choose_column(params.get("x"), numeric_columns, fallback_index=0)
    y_column = _choose_column(params.get("y"), numeric_columns, fallback_index=1)
    if not x_column or not y_column:
        return _empty_plot_spec("scatter", "Scatter requires at least two numeric columns.", context["table_summary"])

    color_column = _choose_column(params.get("color"), context["categorical_columns"])
    label_column = _choose_column(params.get("label"), context["columns"])
    traces = _grouped_marker_traces(
        context["records"],
        x_column=x_column,
        y_column=y_column,
        color_column=color_column,
        label_column=label_column,
        size_column=None,
        mode="markers",
        marker_size=_bounded_float(params.get("point_size"), 8, 1, 40),
        marker_opacity=_bounded_float(params.get("point_alpha"), 0.85, 0.05, 1),
    )
    layout = _base_layout(
        title=f"Scatter: {x_column} vs {y_column}",
        x_title=x_column,
        y_title=y_column,
        params=params,
    )
    return {"data": traces, "layout": layout, "config": _plotly_config(), "warnings": []}


def _build_bubble_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    numeric_columns = context["numeric_columns"]
    x_column = _choose_column(params.get("x"), numeric_columns, fallback_index=0)
    y_column = _choose_column(params.get("y"), numeric_columns, fallback_index=1)
    size_column = _choose_column(params.get("size"), numeric_columns, fallback_index=2)
    if not x_column or not y_column or not size_column:
        return _empty_plot_spec("bubble", "Bubble plot requires at least three numeric columns.", context["table_summary"])

    sizes = [_number_or_none(row.get(size_column)) for row in context["records"]]
    finite_sizes = [value for value in sizes if value is not None]
    min_size = min(finite_sizes) if finite_sizes else 0.0
    max_size = max(finite_sizes) if finite_sizes else 1.0
    span = max(max_size - min_size, 1e-9)
    min_marker = _bounded_float(params.get("min_bubble_size"), 4, 1, 80)
    max_marker = _bounded_float(params.get("max_bubble_size"), 48, min_marker, 160)
    color_column = _choose_column(params.get("color"), context["categorical_columns"])
    label_column = _choose_column(params.get("label"), context["columns"])
    traces = []
    for trace in _grouped_marker_traces(
        context["records"],
        x_column=x_column,
        y_column=y_column,
        color_column=color_column,
        label_column=label_column,
        size_column=size_column,
        mode="markers",
        marker_size=10,
        marker_opacity=0.72,
    ):
        marker_sizes = []
        for raw_size in trace.pop("_raw_sizes", []):
            parsed = _number_or_none(raw_size)
            if parsed is None:
                marker_sizes.append(min_marker)
            else:
                marker_sizes.append(min_marker + (parsed - min_size) / span * (max_marker - min_marker))
        trace["marker"]["size"] = marker_sizes
        trace["marker"]["sizemode"] = "diameter"
        traces.append(trace)

    layout = _base_layout(
        title=f"Bubble: {x_column} vs {y_column}, size={size_column}",
        x_title=x_column,
        y_title=y_column,
        params=params,
    )
    return {"data": traces, "layout": layout, "config": _plotly_config(), "warnings": []}


def _build_boxplot_spec(context: dict[str, Any]) -> dict[str, Any]:
    return _build_distribution_spec(context, trace_type="box")


def _build_violin_spec(context: dict[str, Any]) -> dict[str, Any]:
    return _build_distribution_spec(context, trace_type="violin")


def _build_distribution_spec(context: dict[str, Any], *, trace_type: str) -> dict[str, Any]:
    params = context["params"]
    y_column = _choose_column(params.get("y"), context["numeric_columns"])
    group_column = _choose_column(params.get("group"), context["categorical_columns"])
    traces = []
    warnings = []
    if y_column and group_column:
        grouped = _records_by_category(context["records"], group_column)
        for index, (group_name, rows) in enumerate(grouped.items()):
            values = [_number_or_none(row.get(y_column)) for row in rows]
            values = [value for value in values if value is not None]
            if not values:
                continue
            traces.append(
                _distribution_trace(
                    trace_type,
                    name=group_name,
                    values=values,
                    color=PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)],
                    params=params,
                )
            )
        x_title = group_column
        y_title = y_column
    else:
        max_groups = _bounded_int(params.get("max_groups"), 12, 2, 40)
        for index, column in enumerate(context["numeric_columns"][:max_groups]):
            values = [_number_or_none(row.get(column)) for row in context["records"]]
            values = [value for value in values if value is not None]
            if not values:
                continue
            traces.append(
                _distribution_trace(
                    trace_type,
                    name=column,
                    values=values,
                    color=PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)],
                    params=params,
                )
            )
        if len(context["numeric_columns"]) > max_groups:
            warnings.append(f"Showing first {max_groups} numeric columns to keep the chart readable.")
        x_title = "numeric columns"
        y_title = "value"

    if not traces:
        return _empty_plot_spec(trace_type, "No numeric values were available for distribution plotting.", context["table_summary"])

    layout = _base_layout(
        title=f"{'Boxplot' if trace_type == 'box' else 'Violin'} distribution",
        x_title=x_title,
        y_title=y_title,
        params=params,
    )
    layout["boxmode"] = "group"
    layout["violingap"] = 0.18
    return {"data": traces, "layout": layout, "config": _plotly_config(), "warnings": warnings}


def _build_bar_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    category_column = _choose_column(params.get("category"), context["categorical_columns"])
    value_column = _choose_column(params.get("value"), context["numeric_columns"])
    aggregation = str(params.get("aggregation") or "mean")
    warnings = []
    if category_column and value_column:
        grouped = _records_by_category(context["records"], category_column)
        labels = []
        values = []
        errors = []
        for group_name, rows in grouped.items():
            group_values = [_number_or_none(row.get(value_column)) for row in rows]
            group_values = [value for value in group_values if value is not None]
            if not group_values:
                continue
            labels.append(group_name)
            values.append(_aggregate_values(group_values, aggregation))
            errors.append(_error_bar_value(group_values, str(params.get("error_bar") or "sem")))
        x_title = category_column
        y_title = f"{aggregation} {value_column}"
        title = f"Bar: {value_column} by {category_column}"
    else:
        max_groups = _bounded_int(params.get("max_groups"), 20, 2, 80)
        labels = context["numeric_columns"][:max_groups]
        values = []
        errors = []
        for column in labels:
            column_values = [_number_or_none(row.get(column)) for row in context["records"]]
            column_values = [value for value in column_values if value is not None]
            values.append(_aggregate_values(column_values, aggregation) if column_values else 0)
            errors.append(_error_bar_value(column_values, str(params.get("error_bar") or "sem")))
        if len(context["numeric_columns"]) > max_groups:
            warnings.append(f"Showing first {max_groups} numeric columns to keep the chart readable.")
        x_title = "numeric columns"
        y_title = aggregation
        title = "Bar summary by numeric column"

    trace = {
        "type": "bar",
        "x": labels,
        "y": values,
        "marker": {"color": PLOTLY_PALETTE[0], "line": {"color": "#0a4f52", "width": 1}},
        "error_y": {"type": "data", "array": errors, "visible": any(value > 0 for value in errors)},
        "hovertemplate": "%{x}<br>value=%{y:.4g}<extra></extra>",
    }
    if str(params.get("orientation") or "vertical") == "horizontal":
        trace["orientation"] = "h"
        trace["x"], trace["y"] = trace["y"], trace["x"]
        x_title, y_title = y_title, x_title

    layout = _base_layout(title=title, x_title=x_title, y_title=y_title, params=params)
    return {"data": [trace], "layout": layout, "config": _plotly_config(), "warnings": warnings}


def _build_line_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    x_column = _choose_column(params.get("x"), context["columns"])
    y_column = _choose_column(params.get("y"), context["numeric_columns"])
    series_column = _choose_column(params.get("series"), context["categorical_columns"])
    traces = []
    if y_column and series_column:
        grouped = _records_by_category(context["records"], series_column)
        for index, (series_name, rows) in enumerate(grouped.items()):
            traces.append(
                _line_trace(
                    rows,
                    x_column=x_column,
                    y_column=y_column,
                    name=series_name,
                    color=PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)],
                    params=params,
                )
            )
        title = f"Line: {y_column} by {series_column}"
        y_title = y_column
    else:
        max_series = _bounded_int(params.get("max_series"), 8, 1, 24)
        columns = [y_column] if y_column else context["numeric_columns"][:max_series]
        for index, column in enumerate(columns):
            traces.append(
                _line_trace(
                    context["records"],
                    x_column=x_column,
                    y_column=column,
                    name=column,
                    color=PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)],
                    params=params,
                )
            )
        title = "Line series"
        y_title = "value"
    traces = [trace for trace in traces if trace["y"]]
    if not traces:
        return _empty_plot_spec("line", "Line plot requires at least one numeric column.", context["table_summary"])

    layout = _base_layout(title=title, x_title=x_column or "row index", y_title=y_title, params=params)
    return {"data": traces, "layout": layout, "config": _plotly_config(), "warnings": []}


def _build_volcano_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    columns = context["columns"]
    log2fc_column = _requested_column(params.get("log2fc_column"), columns) or _find_column(
        columns, ["log2fc", "log2_fold_change"]
    )
    p_value_column = _requested_column(params.get("p_value_column"), columns) or _find_column(
        columns, ["p_value", "pvalue", "padj"]
    )
    gene_column = _requested_column(params.get("gene"), columns) or _find_column(columns, ["gene", "symbol", "name"])
    if not log2fc_column or not p_value_column:
        return _empty_plot_spec("volcano", "Volcano plot requires log2FC and p-value columns.", context["table_summary"])

    log2fc_threshold = _bounded_float(params.get("log2fc_threshold"), 1.0, 0, 20)
    p_value_threshold = _bounded_float(params.get("p_value_threshold"), 0.05, 1e-300, 1)
    grouped = {"Up": [], "Down": [], "Not significant": []}
    for row in context["records"]:
        log2fc = _number_or_none(row.get(log2fc_column))
        p_value = _number_or_none(row.get(p_value_column))
        if log2fc is None or p_value is None or p_value <= 0:
            continue
        point = {
            "x": log2fc,
            "y": -math.log10(max(p_value, 1e-300)),
            "gene": str(row.get(gene_column) or "") if gene_column else "",
            "p_value": p_value,
        }
        if log2fc >= log2fc_threshold and p_value <= p_value_threshold:
            grouped["Up"].append(point)
        elif log2fc <= -log2fc_threshold and p_value <= p_value_threshold:
            grouped["Down"].append(point)
        else:
            grouped["Not significant"].append(point)

    colors = {"Up": "#c44f3a", "Down": "#315fd6", "Not significant": "#9aaab7"}
    traces = []
    for name, points in grouped.items():
        if not points:
            continue
        traces.append(
            {
                "type": "scattergl",
                "mode": "markers",
                "name": name,
                "x": [point["x"] for point in points],
                "y": [point["y"] for point in points],
                "text": [point["gene"] for point in points],
                "customdata": [[point["p_value"]] for point in points],
                "marker": {"size": 7, "opacity": 0.78, "color": colors[name]},
                "hovertemplate": "%{text}<br>log2FC=%{x:.3g}<br>-log10(p)=%{y:.3g}<br>p=%{customdata[0]:.3g}<extra></extra>",
            }
        )
    layout = _base_layout(
        title=f"Volcano: {log2fc_column} vs {p_value_column}",
        x_title=log2fc_column,
        y_title="-log10(p value)",
        params=params,
    )
    layout["shapes"] = [
        _vertical_line(log2fc_threshold),
        _vertical_line(-log2fc_threshold),
        _horizontal_line(-math.log10(p_value_threshold)),
    ]
    layout["annotations"] = [
        {
            "x": 0,
            "y": -math.log10(p_value_threshold),
            "text": f"p = {p_value_threshold:g}",
            "showarrow": False,
            "yshift": 10,
            "font": {"size": 11, "color": "#52616b"},
        }
    ]
    warnings = []
    if not traces:
        warnings.append("No valid p-value/log2FC rows were available.")
    return {"data": traces, "layout": layout, "config": _plotly_config(), "warnings": warnings}


def _build_heatmap_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    numeric_columns = _selected_columns(
        params.get("value_columns"),
        context["numeric_columns"],
        limit=_bounded_int(params.get("max_columns"), 60, 2, 300),
    )
    if len(numeric_columns) < 2:
        return _empty_plot_spec("heatmap", "Heatmap requires at least two numeric value columns.", context["table_summary"])

    row_id_column = _requested_column(params.get("row_id"), context["columns"]) or _best_label_column(context["columns"])
    top_n = _bounded_int(params.get("top_n"), 50, 5, 5000)
    matrix_rows = _top_matrix_rows(context["records"], numeric_columns, row_id_column, top_n)
    if not matrix_rows:
        return _empty_plot_spec("heatmap", "No numeric matrix rows were available for heatmap rendering.", context["table_summary"])

    scale = str(params.get("scale") or "row_zscore")
    labels = [item["label"] for item in matrix_rows]
    z_values = [_scale_values(item["values"], scale) for item in matrix_rows]
    trace = {
        "type": "heatmap",
        "x": numeric_columns,
        "y": labels,
        "z": z_values,
        "colorscale": _colorscale(str(params.get("palette") or "blue_red")),
        "colorbar": {"title": scale},
        "hovertemplate": "row=%{y}<br>column=%{x}<br>value=%{z:.4g}<extra></extra>",
    }
    layout = _base_layout(
        title=f"Heatmap: top {len(labels)} variable rows",
        x_title="sample / numeric column",
        y_title=row_id_column or "row",
        params=params,
    )
    layout["height"] = max(520, min(1800, 220 + len(labels) * 14))
    layout["yaxis"]["automargin"] = True
    layout["xaxis"]["automargin"] = True
    warnings = []
    if len(context["records"]) > len(matrix_rows):
        warnings.append(f"Showing top {len(matrix_rows)} rows ranked by variance.")
    return {"data": [trace], "layout": layout, "config": _plotly_config(), "warnings": warnings}


def _build_correlation_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    numeric_columns = _selected_columns(
        params.get("value_columns"),
        context["numeric_columns"],
        limit=_bounded_int(params.get("max_columns"), 80, 2, 300),
    )
    if len(numeric_columns) < 2:
        return _empty_plot_spec("correlation", "Correlation heatmap requires at least two numeric columns.", context["table_summary"])

    method = str(params.get("method") or "pearson")
    series = {column: _numeric_series(context["records"], column) for column in numeric_columns}
    z_values = []
    for row_column in numeric_columns:
        row = []
        for column in numeric_columns:
            if method == "spearman":
                row.append(_pearson(_rank_values(series[row_column]), _rank_values(series[column])))
            else:
                row.append(_pearson(series[row_column], series[column]))
        z_values.append(row)

    trace = {
        "type": "heatmap",
        "x": numeric_columns,
        "y": numeric_columns,
        "z": z_values,
        "zmin": -1,
        "zmax": 1,
        "colorscale": _colorscale(str(params.get("color_scale") or "blue_white_red")),
        "colorbar": {"title": "r"},
        "hovertemplate": "%{y} vs %{x}<br>r=%{z:.3f}<extra></extra>",
    }
    layout = _base_layout(
        title=f"{method.title()} correlation heatmap",
        x_title="numeric column",
        y_title="numeric column",
        params=params,
    )
    layout["height"] = max(560, min(1800, 220 + len(numeric_columns) * 13))
    layout["xaxis"]["automargin"] = True
    layout["yaxis"]["automargin"] = True
    warnings = []
    if len(context["numeric_columns"]) > len(numeric_columns):
        warnings.append(f"Showing first {len(numeric_columns)} numeric columns to keep correlation readable.")
    return {"data": [trace], "layout": layout, "config": _plotly_config(), "warnings": warnings}


def _build_enrichment_dot_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    columns = context["columns"]
    term_column = _requested_column(params.get("term_column"), columns) or _find_column(
        columns, ["term", "description", "pathway", "name"]
    )
    x_column = _requested_column(params.get("x_column"), columns) or _find_column(
        columns, ["gene_ratio", "ratio", "rich_factor", "enrichment_score"]
    )
    size_column = _requested_column(params.get("size_column"), columns) or _find_column(columns, ["count", "gene_count", "size"])
    color_column = _requested_column(params.get("color_column"), columns) or _find_column(
        columns, ["adjusted_p", "padj", "p_adjust", "p_value", "pvalue"]
    )
    if not term_column or not x_column:
        return _empty_plot_spec("enrichment_dot", "Enrichment dot plot requires term and x-value columns.", context["table_summary"])

    rows = []
    for row in context["records"]:
        x_value = _number_or_ratio(row.get(x_column))
        if x_value is None:
            continue
        size_value = _number_or_none(row.get(size_column)) if size_column else None
        color_value = _number_or_none(row.get(color_column)) if color_column else None
        rows.append(
            {
                "term": str(row.get(term_column) or ""),
                "x": x_value,
                "size": size_value if size_value is not None else 1.0,
                "color": color_value if color_value is not None else x_value,
            }
        )
    if not rows:
        return _empty_plot_spec("enrichment_dot", "No valid enrichment rows were available.", context["table_summary"])

    sort_by = str(params.get("sort_by") or color_column or x_column)
    if "p" in sort_by.lower() or sort_by == color_column:
        rows.sort(key=lambda item: item["color"])
    else:
        rows.sort(key=lambda item: item["x"], reverse=True)
    top_n = _bounded_int(params.get("top_n"), 20, 5, 200)
    rows = rows[:top_n]
    max_size = max(item["size"] for item in rows) or 1.0
    marker_sizes = [8 + item["size"] / max_size * 30 for item in rows]
    trace = {
        "type": "scatter",
        "mode": "markers",
        "x": [item["x"] for item in rows],
        "y": [item["term"] for item in rows],
        "marker": {
            "size": marker_sizes,
            "color": [item["color"] for item in rows],
            "colorscale": "Viridis",
            "showscale": True,
            "colorbar": {"title": color_column or x_column},
            "line": {"color": "#ffffff", "width": 1},
            "opacity": 0.86,
        },
        "text": [item["term"] for item in rows],
        "customdata": [[item["size"], item["color"]] for item in rows],
        "hovertemplate": "%{text}<br>x=%{x:.4g}<br>size=%{customdata[0]:.4g}<br>color=%{customdata[1]:.4g}<extra></extra>",
    }
    layout = _base_layout(
        title=f"Enrichment dot plot: top {len(rows)} terms",
        x_title=x_column,
        y_title=term_column,
        params=params,
    )
    layout["height"] = max(520, min(1600, 180 + len(rows) * 24))
    layout["yaxis"]["automargin"] = True
    warnings = []
    if len(context["records"]) > len(rows):
        warnings.append(f"Showing top {len(rows)} enrichment terms.")
    return {"data": [trace], "layout": layout, "config": _plotly_config(), "warnings": warnings}


def _read_delimited_rows(path: Path, *, max_rows: int) -> tuple[list[str], list[list[str]], bool]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        sample = file.read(4096)
        file.seek(0)
        delimiter = _infer_delimiter(path, sample)
        reader = csv.reader(file, delimiter=delimiter)
        header = next(reader, [])
        rows = []
        truncated = False
        for index, row in enumerate(reader):
            if index >= max_rows:
                truncated = True
                break
            rows.append([str(value) for value in row])
    return [str(value) for value in header], rows, truncated


def _load_table_records(path: Path, *, max_rows: int) -> tuple[list[str], list[dict[str, str]]]:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        header, rows, _ = _read_xlsx_rows(path, max_rows=max_rows)
    else:
        header, rows, _ = _read_delimited_rows(path, max_rows=max_rows)
    columns = _clean_header(header)
    records = []
    for row in rows:
        records.append({column: row[index] if index < len(row) else "" for index, column in enumerate(columns)})
    return columns, records


def _read_xlsx_rows(path: Path, *, max_rows: int) -> tuple[list[str], list[list[str]], bool]:
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    iterator = sheet.iter_rows(values_only=True)
    header = ["" if value is None else str(value) for value in next(iterator, [])]
    rows: list[list[str]] = []
    truncated = False
    for index, row in enumerate(iterator):
        if index >= max_rows:
            truncated = True
            break
        rows.append(["" if value is None else str(value) for value in row])
    workbook.close()
    return header, rows, truncated


def _empty_plot_spec(
    plot_type: str,
    message: str,
    table_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "version": PLOT_STUDIO_VERSION,
        "plot_type": plot_type,
        "engine": "plotly",
        "data": [],
        "layout": _base_layout(title="No renderable chart", x_title="", y_title="", params={}),
        "config": _plotly_config(),
        "warnings": [message],
        "table_summary": table_summary,
        "supported_plot_types": sorted(SUPPORTED_PLOTLY_SPEC_TYPES),
    }


def _base_layout(title: str, x_title: str, y_title: str, params: dict[str, Any]) -> dict[str, Any]:
    show_grid = bool(params.get("show_grid", True))
    background = "rgba(0,0,0,0)" if params.get("background") == "transparent" else "#ffffff"
    legend_position = str(params.get("legend_position") or "right")
    font_size = _bounded_int(params.get("font_size"), 13, 8, 28)
    layout: dict[str, Any] = {
        "title": {"text": title, "x": 0.02, "xanchor": "left"},
        "font": {"family": "Inter, Arial, sans-serif", "size": font_size, "color": "#07131f"},
        "paper_bgcolor": background,
        "plot_bgcolor": background,
        "margin": {"l": 72, "r": 32, "t": 72, "b": 64},
        "hovermode": "closest",
        "xaxis": {
            "title": x_title,
            "showgrid": show_grid,
            "gridcolor": "#e7eef4",
            "zerolinecolor": "#b8c7d4",
        },
        "yaxis": {
            "title": y_title,
            "showgrid": show_grid,
            "gridcolor": "#e7eef4",
            "zerolinecolor": "#b8c7d4",
        },
    }
    if legend_position == "none":
        layout["showlegend"] = False
    elif legend_position == "top":
        layout["legend"] = {"orientation": "h", "x": 0, "y": 1.14}
    elif legend_position == "bottom":
        layout["legend"] = {"orientation": "h", "x": 0, "y": -0.22}
    else:
        layout["legend"] = {"orientation": "v", "x": 1.02, "y": 1}
    return layout


def _plotly_config() -> dict[str, Any]:
    return {
        "displaylogo": False,
        "responsive": True,
        "toImageButtonOptions": {"format": "svg", "filename": "yzw_biocloud_plot", "scale": 2},
        "modeBarButtonsToRemove": ["lasso2d", "select2d"],
    }


def _choose_column(
    requested: Any,
    columns: list[str],
    *,
    fallback_index: int = 0,
) -> str | None:
    if requested and str(requested) in columns:
        return str(requested)
    if fallback_index < len(columns):
        return columns[fallback_index]
    return None


def _requested_column(requested: Any, columns: list[str]) -> str | None:
    if requested and str(requested) in columns:
        return str(requested)
    return None


def _selected_columns(requested: Any, columns: list[str], *, limit: int) -> list[str]:
    if isinstance(requested, list):
        selected = [str(item) for item in requested if str(item) in columns]
    elif requested and str(requested) in columns:
        selected = [str(requested)]
    else:
        selected = columns[:limit]
    return selected[:limit]


def _best_label_column(columns: list[str]) -> str | None:
    preferred = _find_column(columns, ["gene", "symbol", "gene_id", "id", "name", "term", "description"])
    if preferred:
        return preferred
    return columns[0] if columns else None


def _find_column(columns: list[str], candidates: list[str]) -> str | None:
    normalized = {_normalize_column_name(column): column for column in columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    return None


def _top_matrix_rows(
    records: list[dict[str, str]],
    numeric_columns: list[str],
    row_id_column: str | None,
    top_n: int,
) -> list[dict[str, Any]]:
    ranked = []
    for index, row in enumerate(records):
        values = [_number_or_none(row.get(column)) for column in numeric_columns]
        if not any(value is not None for value in values):
            continue
        filled_values = _fill_missing_numeric(values)
        label = str(row.get(row_id_column) or f"row_{index + 1}") if row_id_column else f"row_{index + 1}"
        ranked.append({"label": label, "values": filled_values, "variance": _variance(filled_values)})
    ranked.sort(key=lambda item: item["variance"], reverse=True)
    return ranked[:top_n]


def _fill_missing_numeric(values: list[float | None]) -> list[float]:
    present = [value for value in values if value is not None]
    fallback = fmean(present) if present else 0.0
    return [value if value is not None else fallback for value in values]


def _scale_values(values: list[float], scale: str) -> list[float]:
    if scale == "none":
        return values
    if scale == "log2":
        return [math.log2(max(value, 0.0) + 1.0) for value in values]
    if scale in {"row_zscore", "column_zscore"}:
        mean = fmean(values) if values else 0.0
        sd = pstdev(values) if len(values) > 1 else 0.0
        if sd == 0:
            return [0.0 for _ in values]
        return [(value - mean) / sd for value in values]
    return values


def _numeric_series(records: list[dict[str, str]], column: str) -> list[float]:
    values = [_number_or_none(row.get(column)) for row in records]
    return [value for value in values if value is not None]


def _pearson(left: list[float], right: list[float]) -> float:
    size = min(len(left), len(right))
    if size < 2:
        return 0.0
    a = left[:size]
    b = right[:size]
    mean_a = fmean(a)
    mean_b = fmean(b)
    numerator = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b, strict=False))
    denom_a = math.sqrt(sum((x - mean_a) ** 2 for x in a))
    denom_b = math.sqrt(sum((y - mean_b) ** 2 for y in b))
    if denom_a == 0 or denom_b == 0:
        return 0.0
    return _round_number(numerator / (denom_a * denom_b))


def _rank_values(values: list[float]) -> list[float]:
    sorted_pairs = sorted((value, index) for index, value in enumerate(values))
    ranks = [0.0] * len(values)
    index = 0
    while index < len(sorted_pairs):
        end = index + 1
        while end < len(sorted_pairs) and sorted_pairs[end][0] == sorted_pairs[index][0]:
            end += 1
        rank = (index + end + 1) / 2
        for _, original_index in sorted_pairs[index:end]:
            ranks[original_index] = rank
        index = end
    return ranks


def _variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = fmean(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def _number_or_ratio(value: Any) -> float | None:
    parsed = _number_or_none(value)
    if parsed is not None:
        return parsed
    text = str(value or "").strip()
    if "/" not in text:
        return None
    numerator, denominator = text.split("/", 1)
    left = _number_or_none(numerator)
    right = _number_or_none(denominator)
    if left is None or right in {None, 0}:
        return None
    return left / right


def _colorscale(name: str) -> str | list[list[Any]]:
    normalized = name.lower()
    if normalized in {"viridis", "magma", "plasma", "cividis"}:
        return normalized.title()
    if normalized in {"green_white_purple", "green_purple"}:
        return [[0, "#20804f"], [0.5, "#ffffff"], [1, "#7a4fb3"]]
    if normalized in {"prism_muted", "group"}:
        return [[0, "#315fd6"], [0.5, "#ffffff"], [1, "#c44f3a"]]
    return [[0, "#315fd6"], [0.5, "#ffffff"], [1, "#c44f3a"]]


def _numeric_value_count(records: list[dict[str, str]], column: str) -> int:
    return sum(1 for row in records if _number_or_none(row.get(column)) is not None)


def _number_or_none(value: Any) -> float | None:
    parsed = _parse_float(value)
    if parsed is None or not math.isfinite(parsed):
        return None
    return parsed


def _grouped_marker_traces(
    records: list[dict[str, str]],
    *,
    x_column: str,
    y_column: str,
    color_column: str | None,
    label_column: str | None,
    size_column: str | None,
    mode: str,
    marker_size: float,
    marker_opacity: float,
) -> list[dict[str, Any]]:
    grouped = _records_by_category(records, color_column) if color_column else {"All": records}
    traces = []
    for index, (group_name, rows) in enumerate(grouped.items()):
        x_values = []
        y_values = []
        labels = []
        raw_sizes = []
        for row in rows:
            x_value = _number_or_none(row.get(x_column))
            y_value = _number_or_none(row.get(y_column))
            if x_value is None or y_value is None:
                continue
            x_values.append(x_value)
            y_values.append(y_value)
            labels.append(str(row.get(label_column) or "") if label_column else "")
            raw_sizes.append(row.get(size_column, "") if size_column else "")
        if not x_values:
            continue
        traces.append(
            {
                "type": "scattergl",
                "mode": mode,
                "name": group_name,
                "x": x_values,
                "y": y_values,
                "text": labels,
                "marker": {
                    "size": marker_size,
                    "opacity": marker_opacity,
                    "color": PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)],
                    "line": {"color": "#ffffff", "width": 0.5},
                },
                "hovertemplate": "%{text}<br>x=%{x:.4g}<br>y=%{y:.4g}<extra>%{fullData.name}</extra>",
                "_raw_sizes": raw_sizes,
            }
        )
    return traces


def _records_by_category(records: list[dict[str, str]], column: str | None) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in records:
        key = str(row.get(column) or "All") if column else "All"
        grouped.setdefault(key, []).append(row)
    return grouped


def _distribution_trace(
    trace_type: str,
    *,
    name: str,
    values: list[float],
    color: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    if trace_type == "violin":
        return {
            "type": "violin",
            "name": name,
            "y": values,
            "box": {"visible": bool(params.get("show_box", True))},
            "meanline": {"visible": bool(params.get("show_mean", True))},
            "points": str(params.get("show_points") or "outliers"),
            "marker": {"color": color, "opacity": 0.72},
            "line": {"color": color},
            "hovertemplate": f"{name}<br>value=%{{y:.4g}}<extra></extra>",
        }
    return {
        "type": "box",
        "name": name,
        "y": values,
        "boxpoints": "all" if params.get("show_points", True) else False,
        "jitter": _bounded_float(params.get("point_jitter"), 0.35, 0, 1),
        "notched": bool(params.get("notched", False)),
        "marker": {"color": color, "opacity": 0.72, "size": 5},
        "line": {"color": color},
        "boxmean": bool(params.get("show_mean", True)),
        "hovertemplate": f"{name}<br>value=%{{y:.4g}}<extra></extra>",
    }


def _aggregate_values(values: list[float], method: str) -> float:
    if not values:
        return 0.0
    if method == "median":
        return float(median(values))
    if method == "sum":
        return float(sum(values))
    if method == "count":
        return float(len(values))
    return float(fmean(values))


def _error_bar_value(values: list[float], method: str) -> float:
    if len(values) < 2 or method == "none":
        return 0.0
    sd = pstdev(values)
    if method == "sd":
        return sd
    if method == "ci95":
        return 1.96 * sd / math.sqrt(len(values))
    return sd / math.sqrt(len(values))


def _line_trace(
    records: list[dict[str, str]],
    *,
    x_column: str | None,
    y_column: str,
    name: str,
    color: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    x_values = []
    y_values = []
    for index, row in enumerate(records):
        y_value = _number_or_none(row.get(y_column))
        if y_value is None:
            continue
        x_values.append(row.get(x_column) if x_column else index + 1)
        y_values.append(y_value)
    return {
        "type": "scatter",
        "mode": "lines+markers" if params.get("show_points", True) else "lines",
        "name": name,
        "x": x_values,
        "y": y_values,
        "line": {"color": color, "shape": "spline" if params.get("smooth") else "linear", "width": 2.4},
        "marker": {"color": color, "size": 6},
        "hovertemplate": "%{x}<br>value=%{y:.4g}<extra>%{fullData.name}</extra>",
        "connectgaps": bool(params.get("connect_gaps", False)),
    }


def _vertical_line(x_value: float) -> dict[str, Any]:
    return {
        "type": "line",
        "xref": "x",
        "yref": "paper",
        "x0": x_value,
        "x1": x_value,
        "y0": 0,
        "y1": 1,
        "line": {"color": "#8799aa", "width": 1, "dash": "dash"},
    }


def _horizontal_line(y_value: float) -> dict[str, Any]:
    return {
        "type": "line",
        "xref": "paper",
        "yref": "y",
        "x0": 0,
        "x1": 1,
        "y0": y_value,
        "y1": y_value,
        "line": {"color": "#8799aa", "width": 1, "dash": "dash"},
    }


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _infer_delimiter(path: Path, sample: str) -> str:
    if path.suffix.lower() == ".tsv":
        return "\t"
    if path.suffix.lower() == ".csv":
        return ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        return ","
    return str(dialect.delimiter)


def _clean_header(header: list[str]) -> list[str]:
    used: dict[str, int] = {}
    columns = []
    for index, raw_name in enumerate(header):
        name = str(raw_name or "").strip() or f"column_{index + 1}"
        count = used.get(name, 0) + 1
        used[name] = count
        if count > 1:
            name = f"{name}_{count}"
        columns.append(name)
    return columns


def _collect_column_stats(columns: list[str], rows: list[list[str]]) -> dict[str, dict[str, Any]]:
    raw_stats: dict[str, dict[str, Any]] = {
        name: {"missing": 0, "non_missing": 0, "numeric_values": [], "distinct": set()}
        for name in columns
    }
    for row in rows:
        for index, column in enumerate(columns):
            value = row[index] if index < len(row) else ""
            text = str(value).strip()
            stats = raw_stats[column]
            if text == "":
                stats["missing"] += 1
                continue
            stats["non_missing"] += 1
            if len(stats["distinct"]) < 25:
                stats["distinct"].add(text)
            parsed = _parse_float(text)
            if parsed is not None and math.isfinite(parsed):
                stats["numeric_values"].append(parsed)

    summaries: dict[str, dict[str, Any]] = {}
    for column, stats in raw_stats.items():
        values = stats["numeric_values"]
        non_missing = int(stats["non_missing"])
        numeric_ratio = len(values) / non_missing if non_missing else 0.0
        if values and numeric_ratio >= 0.8:
            summaries[column] = {
                "kind": "numeric",
                "count": len(values),
                "missing": int(stats["missing"]),
                "min": _round_number(min(values)),
                "max": _round_number(max(values)),
                "mean": _round_number(fmean(values)),
                "std": _round_number(pstdev(values)) if len(values) > 1 else 0,
            }
        else:
            summaries[column] = {
                "kind": "categorical",
                "count": non_missing,
                "missing": int(stats["missing"]),
                "unique_preview": sorted(str(item) for item in stats["distinct"]),
            }
    return summaries


def _detect_table_signals(columns: list[str], rows: list[list[str]]) -> dict[str, Any]:
    normalized = {_normalize_column_name(column): index for index, column in enumerate(columns)}
    signals: dict[str, Any] = {}

    log2fc_index = _first_present(normalized, "log2fc", "log2_fold_change")
    p_index = _first_present(normalized, "p_value", "pvalue", "padj")
    if log2fc_index is not None and p_index is not None:
        significant = 0
        up = 0
        down = 0
        for row in rows:
            if log2fc_index >= len(row) or p_index >= len(row):
                continue
            log2fc = _parse_float(row[log2fc_index])
            p_value = _parse_float(row[p_index])
            if log2fc is None or p_value is None:
                continue
            if abs(log2fc) >= 1.0 and p_value <= 0.05:
                significant += 1
                if log2fc > 0:
                    up += 1
                elif log2fc < 0:
                    down += 1
        signals["differential_default_threshold"] = {
            "abs_log2fc": 1.0,
            "p_value": 0.05,
            "significant": significant,
            "up": up,
            "down": down,
        }
    return signals


def _select_source_table(source: dict[str, Any]) -> tuple[Path | None, str]:
    meta = dict(source.get("meta") or {})
    data_path = _resolve_allowed_path(str(source.get("data_path") or source.get("dataPath") or ""))
    if data_path and data_path.suffix.lower() == ".json":
        meta.update(_read_meta_from_json(data_path))
    if data_path and data_path.suffix.lower() in {".csv", ".tsv", ".txt", ".xlsx", ".xlsm"}:
        return data_path, "source.data_path"

    for key in ("diff_result_file", "matrix_file", "module_file", "sample_metadata_file"):
        candidate = _resolve_allowed_path(str(meta.get(key) or ""))
        if candidate and candidate.suffix.lower() in {".csv", ".tsv", ".txt", ".xlsx", ".xlsm"}:
            return candidate, f"source.meta.{key}"
    return None, "no readable tabular source was found"


def _read_meta_from_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(payload, dict) and isinstance(payload.get("meta"), dict):
        return dict(payload["meta"])
    return {}


def _resolve_allowed_path(value: str) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    try:
        resolved = path.resolve()
        project_root = PROJECT_ROOT.resolve()
    except OSError:
        return None
    if resolved != project_root and project_root not in resolved.parents:
        return None
    if not resolved.exists():
        return None
    return resolved


def _select_plot_id(plot_type: str | None, recommended_plot_ids: list[str]) -> str:
    known_ids = {item["id"] for item in PLOT_PRESETS}
    if plot_type:
        normalized = _normalize_plot_id(plot_type)
        if normalized in known_ids:
            return normalized
        for item in PLOT_PRESETS:
            if _normalize_plot_id(item["label"]) == normalized:
                return item["id"]
    for item in recommended_plot_ids:
        if item in known_ids:
            return item
    return "scatter"


def _build_report(
    *,
    source: dict[str, Any],
    source_type: str,
    selected_preset: dict[str, Any],
    table_summary: dict[str, Any] | None,
    params: dict[str, Any],
    path_reason: str,
) -> dict[str, Any]:
    observations = _build_observations(source, source_type, selected_preset, table_summary, params, path_reason)
    limitations = [
        "This report is generated from source metadata and tabular statistics only.",
        "Rendered images are not inspected by the report agent.",
    ]
    if table_summary is None:
        limitations.append("No readable table was available, so the report is metadata-only.")

    return {
        "headline": _build_headline(source, selected_preset, table_summary),
        "sections": [
            {
                "title": "Data readiness",
                "text": observations["data_readiness"],
                "tone": "positive" if table_summary else "warning",
            },
            {
                "title": "Recommended figure",
                "text": observations["figure_choice"],
                "tone": "neutral",
            },
            {
                "title": "Signals to inspect",
                "text": observations["signals"],
                "tone": "neutral",
            },
            {
                "title": "Parameter notes",
                "text": observations["parameter_notes"],
                "tone": "neutral",
            },
        ],
        "limitations": limitations,
    }


def _build_observations(
    source: dict[str, Any],
    source_type: str,
    selected_preset: dict[str, Any],
    table_summary: dict[str, Any] | None,
    params: dict[str, Any],
    path_reason: str,
) -> dict[str, str]:
    meta = dict(source.get("meta") or {})
    if table_summary:
        data_readiness = (
            f"Using {table_summary['filename']} from {path_reason}; scanned "
            f"{table_summary['scanned_rows']} rows and {table_summary['column_count']} columns. "
            f"{len(table_summary['numeric_columns'])} numeric column(s) and "
            f"{len(table_summary['categorical_columns'])} categorical column(s) were detected."
        )
    else:
        data_readiness = (
            f"No tabular file was resolved from this source. Source type is '{source_type or 'unknown'}' "
            "and available metadata will be used for planning only."
        )

    figure_choice = (
        f"{selected_preset['label']} is selected with the {selected_preset['engine']} engine. "
        f"Default parameters include {', '.join(sorted(selected_preset['default_params'])[:5])}."
    )

    signals = _signal_text(source_type, table_summary, meta)
    parameter_notes = _parameter_notes(selected_preset["id"], table_summary, meta, params)
    return {
        "data_readiness": data_readiness,
        "figure_choice": figure_choice,
        "signals": signals,
        "parameter_notes": parameter_notes,
    }


def _signal_text(source_type: str, table_summary: dict[str, Any] | None, meta: dict[str, Any]) -> str:
    if table_summary:
        diff_signal = table_summary.get("signals", {}).get("differential_default_threshold")
        if diff_signal:
            return (
                "At abs(log2FC) >= {abs_log2fc} and p <= {p_value}, {significant} feature(s) pass "
                "the default differential threshold: {up} up and {down} down."
            ).format(**diff_signal)
        numeric_columns = table_summary.get("numeric_columns") or []
        if "expression" in source_type or meta.get("sample_count"):
            sample_count = meta.get("passed_sample_count") or meta.get("sample_count") or len(numeric_columns)
            gene_count = meta.get("gene_count") or table_summary.get("scanned_rows")
            return f"The source looks expression-like with {gene_count} row(s) and {sample_count} sample-like numeric column(s)."
        if numeric_columns:
            preview = ", ".join(numeric_columns[:5])
            return f"Numeric signal columns are available for plotting: {preview}."
    if meta:
        keys = ", ".join(sorted(meta)[:8])
        return f"Metadata keys available for interpretation: {keys}."
    return "No statistical signal can be inferred until a readable table or richer metadata is attached."


def _parameter_notes(
    plot_id: str,
    table_summary: dict[str, Any] | None,
    meta: dict[str, Any],
    params: dict[str, Any],
) -> str:
    if plot_id in {"heatmap", "correlation"}:
        group_note = "Group colors are available." if meta.get("condition_colors") else "Group colors are not attached yet."
        top_n = params.get("top_n") or params.get("top_genes") or 50
        return f"Use top_n={top_n} for the first render, keep clustering enabled, and review dendrogram stability. {group_note}"
    if plot_id in {"boxplot", "violin"}:
        return "Default view should show raw points, group colors, median/box summaries, and optional pairwise tests."
    if plot_id == "volcano":
        return "Start with abs(log2FC)=1 and p=0.05, then expose labels and multiple-testing threshold controls."
    if table_summary and len(table_summary.get("numeric_columns") or []) >= 2:
        return "Map numeric columns first, then add color/facet fields only if categorical columns are present."
    return "Start from the preset defaults, then refine mappings after the source table is inspected."


def _build_headline(
    source: dict[str, Any],
    selected_preset: dict[str, Any],
    table_summary: dict[str, Any] | None,
) -> str:
    name = str(source.get("name") or source.get("node_id") or source.get("nodeId") or "Selected source")
    if table_summary:
        return f"{selected_preset['label']} ready for {name}: {table_summary['scanned_rows']} scanned row(s)."
    return f"{selected_preset['label']} plan ready for {name}."


def _source_summary(source: dict[str, Any], data_path: Path | None) -> dict[str, Any]:
    return {
        "source_kind": source.get("source_kind") or source.get("sourceKind") or "analysis_output",
        "task_id": source.get("task_id") or source.get("taskId") or "",
        "node_id": source.get("node_id") or source.get("nodeId") or source.get("id") or "",
        "name": source.get("name") or "",
        "type": source.get("type") or "",
        "data_path": str(data_path) if data_path else "",
    }


def _normalize_plot_id(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _first_present(values: dict[str, int], *keys: str) -> int | None:
    for key in keys:
        if key in values:
            return values[key]
    return None


def _normalize_column_name(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _parse_float(value: Any) -> float | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _round_number(value: float) -> float:
    if abs(value) >= 1000:
        return round(value, 2)
    return round(value, 4)
