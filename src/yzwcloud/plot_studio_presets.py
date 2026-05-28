from __future__ import annotations

from copy import deepcopy
from typing import Any


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
    "histogram",
    "density_contour",
    "scatter_3d",
    "surface_3d",
    "bubble",
    "volcano",
    "upset",
    "venn",
    "heatmap",
    "correlation",
    "enrichment_dot",
}

ADVANCED_PARAMETER_GROUP_IDS = {"theme", "labels", "export", "style"}

PLOT_UI_METADATA: dict[str, dict[str, str]] = {
    "scatter": {
        "category": "Relationship",
        "thumbnail": "scatter",
        "use_case": "Two numeric variables, PCA scores, sample maps.",
    },
    "boxplot": {
        "category": "Distribution",
        "thumbnail": "boxplot",
        "use_case": "Group comparison with medians, spread, and raw points.",
    },
    "violin": {
        "category": "Distribution",
        "thumbnail": "violin",
        "use_case": "Group distribution shape and hidden multimodality.",
    },
    "bar": {
        "category": "Distribution",
        "thumbnail": "bar",
        "use_case": "Aggregated group summaries with error bars.",
    },
    "line": {
        "category": "Relationship",
        "thumbnail": "line",
        "use_case": "Ordered series, time course, and trajectory trends.",
    },
    "histogram": {
        "category": "Distribution",
        "thumbnail": "histogram",
        "use_case": "Single-variable distribution and value range checks.",
    },
    "density_contour": {
        "category": "Relationship",
        "thumbnail": "density_contour",
        "use_case": "Crowded two-variable scatter with density structure.",
    },
    "scatter_3d": {
        "category": "Relationship",
        "thumbnail": "scatter_3d",
        "use_case": "Three-axis separation, PCA-like embedding, feature space.",
    },
    "surface_3d": {
        "category": "Matrix",
        "thumbnail": "surface_3d",
        "use_case": "Expression-like matrices as interactive surface ridges.",
    },
    "heatmap": {
        "category": "Matrix",
        "thumbnail": "heatmap",
        "use_case": "Scaled matrices with clustering and annotation.",
    },
    "bubble": {
        "category": "Relationship",
        "thumbnail": "bubble",
        "use_case": "X/Y position plus size and color encodings.",
    },
    "volcano": {
        "category": "Omics results",
        "thumbnail": "volcano",
        "use_case": "Differential result significance versus effect size.",
    },
    "upset": {
        "category": "Sets",
        "thumbnail": "upset",
        "use_case": "Multi-set intersections beyond simple Venn diagrams.",
    },
    "venn": {
        "category": "Sets",
        "thumbnail": "venn",
        "use_case": "Two- to four-set overlap sketches.",
    },
    "correlation": {
        "category": "Matrix",
        "thumbnail": "correlation",
        "use_case": "Sample similarity blocks with optional clustering.",
    },
    "enrichment_dot": {
        "category": "Omics results",
        "thumbnail": "enrichment_dot",
        "use_case": "Pathway or term enrichment overview.",
    },
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
            _param(
                "font_family",
                "Font family",
                "select",
                "inter",
                options=["inter", "arial", "helvetica", "times", "georgia", "noto_sans"],
            ),
            _param("font_size", "Font size", "number", 13, min_value=8, max_value=28, step=1),
            _param("show_grid", "Show grid", "boolean", True),
            _param("axis_line", "Axis line", "boolean", True),
            _param("legend_position", "Legend", "select", "right", options=["right", "top", "bottom", "none"]),
        ],
    ),
    _group(
        "labels",
        "Labels and axes",
        [
            _param("title", "Figure title", "text", ""),
            _param("subtitle", "Subtitle", "text", ""),
            _param("x_title", "X title", "text", ""),
            _param("y_title", "Y title", "text", ""),
            _param("title_position", "Title position", "select", "left", options=["left", "center"]),
            _param("x_tick_angle", "X tick angle", "number", 0, min_value=-90, max_value=90, step=5),
            _param("y_tick_angle", "Y tick angle", "number", 0, min_value=-90, max_value=90, step=5),
        ],
    ),
    _group(
        "export",
        "Export size and format",
        [
            _param("width", "Width", "number", 1200, min_value=320, max_value=4000, step=10),
            _param("height", "Height", "number", 760, min_value=240, max_value=3000, step=10),
            _param("margin_left", "Left margin", "number", 72, min_value=20, max_value=300, step=1),
            _param("margin_right", "Right margin", "number", 32, min_value=10, max_value=300, step=1),
            _param("margin_top", "Top margin", "number", 72, min_value=20, max_value=300, step=1),
            _param("margin_bottom", "Bottom margin", "number", 64, min_value=20, max_value=300, step=1),
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
                    _param("loess_fraction", "LOESS span", "number", 0.35, min_value=0.15, max_value=0.9, step=0.05),
                    _param("confidence_ellipse", "Confidence ellipse", "boolean", False),
                    _param("ellipse_level", "Ellipse level", "number", 0.95, min_value=0.5, max_value=0.99, step=0.01),
                    _param("x_log", "Log X axis", "boolean", False),
                    _param("y_log", "Log Y axis", "boolean", False),
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
        "default_params": {
            "show_box": True,
            "show_mean": True,
            "show_points": "outliers",
            "span_mode": "soft",
            "side": "both",
        },
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
                    _param("show_mean", "Show mean line", "boolean", True),
                    _param("show_points", "Points", "select", "outliers", options=["none", "outliers", "all"]),
                    _param("bandwidth", "Bandwidth", "number_or_auto", "auto", min_value=0.01, max_value=2.0, step=0.01),
                    _param("side", "Side", "select", "both", options=["both", "positive", "negative"]),
                    _param("point_alpha", "Point opacity", "number", 0.62, min_value=0.05, max_value=1, step=0.05),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "bar",
        "label": "Bar",
        "engine": "plotly",
        "description": "Summary bar chart with configurable aggregation and error bars.",
        "default_params": {
            "aggregation": "mean",
            "error_bar": "sem",
            "show_points": True,
            "orientation": "vertical",
            "sort": "input",
            "pairwise_test": "none",
            "show_p_values": False,
        },
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
                    _param("show_points", "Overlay raw points", "boolean", True),
                    _param("point_alpha", "Point opacity", "number", 0.68, min_value=0.05, max_value=1, step=0.05),
                    _param("error_cap_width", "Error cap width", "number", 8, min_value=0, max_value=24, step=1),
                    _param(
                        "pairwise_test",
                        "Pairwise test",
                        "select",
                        "none",
                        options=["none", "t_test", "wilcoxon", "anova_then_tukey"],
                    ),
                    _param("multiple_testing", "Multiple testing", "select", "BH", options=["none", "BH", "bonferroni"]),
                    _param("show_p_values", "Show p-values", "boolean", False),
                    _param("sort", "Sort bars", "select", "input", options=["input", "ascending", "descending"]),
                    _param("orientation", "Orientation", "select", "vertical", options=["vertical", "horizontal"]),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "line",
        "label": "Line",
        "engine": "plotly",
        "description": "Time-course or ordered series plot with optional grouping and smoothing.",
        "default_params": {
            "line_shape": "linear",
            "line_width": 2.4,
            "show_points": True,
            "marker_size": 6,
            "marker_symbol": "circle",
            "smooth": False,
        },
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
                    _param("line_width", "Line width", "number", 2.4, min_value=0.5, max_value=10, step=0.1),
                    _param("show_points", "Show points", "boolean", True),
                    _param("marker_size", "Marker size", "number", 6, min_value=0, max_value=30, step=1),
                    _param("marker_symbol", "Marker symbol", "select", "circle", options=["circle", "square", "diamond", "cross", "x"]),
                    _param("smooth", "Smooth line", "boolean", False),
                    _param("connect_gaps", "Connect missing values", "boolean", False),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "histogram",
        "label": "Histogram",
        "engine": "plotly",
        "description": "Single-variable distribution chart with bins, density scaling, grouping, and cumulative display.",
        "default_params": {
            "bins": 30,
            "histnorm": "count",
            "barmode": "overlay",
            "opacity": 0.68,
            "cumulative": False,
            "show_mean": True,
            "show_median": False,
            "show_rug": False,
        },
        "parameter_groups": [
            _group(
                "mapping",
                "Data mapping",
                [
                    _param("x", "Value", "column", None, required=True),
                    _param("color", "Color by", "column_or_none", None),
                ],
            ),
            _group(
                "distribution",
                "Distribution display",
                [
                    _param("bins", "Bins", "number", 30, min_value=5, max_value=200, step=1),
                    _param("histnorm", "Scale", "select", "count", options=["count", "probability", "density", "probability density"]),
                    _param("barmode", "Bar mode", "select", "overlay", options=["overlay", "group", "stack"]),
                    _param("opacity", "Opacity", "number", 0.68, min_value=0.1, max_value=1, step=0.02),
                    _param("cumulative", "Cumulative", "boolean", False),
                    _param("show_mean", "Mean reference", "boolean", True),
                    _param("show_median", "Median reference", "boolean", False),
                    _param("show_rug", "Rug marks", "boolean", False),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "density_contour",
        "label": "2D density contour",
        "engine": "plotly",
        "description": "Two-variable density contour with optional raw point overlay for crowded scatter data.",
        "default_params": {
            "contours_coloring": "heatmap",
            "show_points": True,
            "point_size": 5,
            "point_alpha": 0.38,
            "contour_line_width": 1.2,
            "show_contour_labels": False,
        },
        "parameter_groups": [
            _group(
                "mapping",
                "Data mapping",
                [
                    _param("x", "X axis", "column", None, required=True),
                    _param("y", "Y axis", "column", None, required=True),
                    _param("color", "Color by", "column_or_none", None),
                    _param("label", "Point label", "column_or_none", None),
                ],
            ),
            _group(
                "density",
                "Density display",
                [
                    _param("contours_coloring", "Contour fill", "select", "heatmap", options=["heatmap", "lines", "fill"]),
                    _param("show_points", "Overlay points", "boolean", True),
                    _param("point_size", "Point size", "number", 5, min_value=1, max_value=24, step=1),
                    _param("point_alpha", "Point opacity", "number", 0.38, min_value=0.05, max_value=1, step=0.02),
                    _param("contour_line_width", "Contour line width", "number", 1.2, min_value=0.2, max_value=6, step=0.1),
                    _param("show_contour_labels", "Show contour labels", "boolean", False),
                    _param("contour_start", "Contour start", "number_or_auto", "auto"),
                    _param("contour_end", "Contour end", "number_or_auto", "auto"),
                    _param("contour_size", "Contour step", "number_or_auto", "auto"),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "scatter_3d",
        "label": "3D scatter",
        "engine": "plotly",
        "description": "Three-axis interactive scatter plot for PCA-like or multi-feature numeric tables.",
        "default_params": {
            "marker_size": 5,
            "point_alpha": 0.78,
            "camera": "isometric",
        },
        "parameter_groups": [
            _group(
                "mapping",
                "Data mapping",
                [
                    _param("x", "X axis", "column", None, required=True),
                    _param("y", "Y axis", "column", None, required=True),
                    _param("z", "Z axis", "column", None, required=True),
                    _param("color", "Color by", "column_or_none", None),
                    _param("label", "Point label", "column_or_none", None),
                ],
            ),
            _group(
                "three_d",
                "3D display",
                [
                    _param("marker_size", "Marker size", "number", 5, min_value=1, max_value=30, step=1),
                    _param("point_alpha", "Point opacity", "number", 0.78, min_value=0.05, max_value=1, step=0.02),
                    _param("camera", "Camera", "select", "isometric", options=["isometric", "front", "top"]),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "surface_3d",
        "label": "3D surface heatmap",
        "engine": "plotly",
        "description": "Matrix surface view for expression-like tables, ranked by row variance and optionally scaled.",
        "default_params": {
            "scale": "row_zscore",
            "top_n": 40,
            "colorscale": "Viridis",
            "show_contours": True,
            "camera": "isometric",
        },
        "parameter_groups": [
            _group(
                "mapping",
                "Data mapping",
                [
                    _param("row_id", "Row ID", "column", None),
                    _param("value_columns", "Value columns", "numeric_columns", None, required=True),
                ],
            ),
            _group(
                "surface",
                "Surface display",
                [
                    _param("scale", "Scale", "select", "row_zscore", options=["none", "row_zscore", "log2"]),
                    _param("top_n", "Top rows", "number", 40, min_value=5, max_value=2000, step=1),
                    _param("colorscale", "Colorscale", "select", "Viridis", options=["Viridis", "Plasma", "Cividis", "RdBu"]),
                    _param("show_contours", "Show contours", "boolean", True),
                    _param("camera", "Camera", "select", "isometric", options=["isometric", "front", "top"]),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "heatmap",
        "label": "Heatmap",
        "engine": "plotly",
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
        "default_params": {
            "size_scale": 18,
            "min_bubble_size": 4,
            "max_bubble_size": 48,
            "color_scale": "viridis",
            "point_alpha": 0.72,
        },
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
                    _param(
                        "color_scale",
                        "Continuous color scale",
                        "select",
                        "viridis",
                        options=["viridis", "magma", "plasma", "cividis", "blue_white_red", "green_white_purple"],
                    ),
                    _param("point_alpha", "Point opacity", "number", 0.72, min_value=0.05, max_value=1, step=0.02),
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
        "engine": "plotly",
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
                    _param("max_intersections", "Max intersections", "number", 40, min_value=5, max_value=120, step=1),
                    _param("sort_by", "Sort by", "select", "intersection_size", options=["intersection_size", "degree", "set_name"]),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
    {
        "id": "venn",
        "label": "Venn",
        "engine": "plotly",
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
        "engine": "plotly",
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
            "color_transform": "minus_log10",
            "top_n": 20,
            "min_dot_size": 8,
            "max_dot_size": 38,
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
                    _param("color_transform", "Color transform", "select", "minus_log10", options=["raw", "minus_log10"]),
                ],
            ),
            _group(
                "terms",
                "Term display",
                [
                    _param("top_n", "Top terms", "number", 20, min_value=5, max_value=200, step=1),
                    _param("sort_by", "Sort by", "select", "adjusted_p", options=["adjusted_p", "count", "gene_ratio"]),
                    _param("wrap_term_label", "Wrap labels", "boolean", True),
                    _param("term_label_width", "Label width", "number", 26, min_value=8, max_value=80, step=1),
                    _param("min_dot_size", "Min dot size", "number", 8, min_value=2, max_value=40, step=1),
                    _param("max_dot_size", "Max dot size", "number", 38, min_value=8, max_value=100, step=1),
                ],
            ),
            *COMMON_THEME_GROUPS,
        ],
    },
]


RECOMMENDATIONS_BY_OUTPUT = {
    "gene_expression": ["boxplot", "violin", "bar", "histogram"],
    "pca": ["scatter", "bubble", "scatter_3d", "density_contour"],
    "sample_correlation": ["correlation", "heatmap"],
    "correlation": ["correlation", "heatmap"],
    "expression_heatmap": ["heatmap", "correlation"],
    "heatmap": ["heatmap", "correlation"],
    "volcano": ["volcano", "scatter"],
    "diff": ["volcano", "heatmap", "bar"],
    "wgcna": ["heatmap", "bubble", "correlation", "density_contour"],
    "enrichment": ["enrichment_dot", "bar", "bubble"],
    "expression_matrix": ["boxplot", "heatmap", "correlation", "histogram", "surface_3d"],
}


def _enrich_plot_preset(preset: dict[str, Any]) -> dict[str, Any]:
    enriched = deepcopy(preset)
    metadata = PLOT_UI_METADATA.get(enriched["id"], {})
    enriched["category"] = metadata.get("category", "Other")
    enriched["thumbnail"] = metadata.get("thumbnail", enriched["id"])
    enriched["use_case"] = metadata.get("use_case", enriched.get("description", ""))
    for group in enriched.get("parameter_groups", []):
        group["advanced"] = group.get("id") in ADVANCED_PARAMETER_GROUP_IDS
    return enriched


def list_plot_presets() -> list[dict[str, Any]]:
    return [_enrich_plot_preset(preset) for preset in PLOT_PRESETS]


def get_plot_studio_manifest() -> dict[str, Any]:
    return {
        "version": PLOT_STUDIO_VERSION,
        "engines": ["plotly"],
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


