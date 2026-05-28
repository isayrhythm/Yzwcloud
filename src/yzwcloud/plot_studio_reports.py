from __future__ import annotations

from pathlib import Path
from typing import Any

from yzwcloud.plot_studio_presets import PLOT_PRESETS, PLOT_STUDIO_VERSION, recommend_plot_types
from yzwcloud.plot_studio_source import _select_source_table, _source_summary
from yzwcloud.plot_studio_specs import _select_plot_id
from yzwcloud.plot_studio_tables import inspect_table


PLOT_REPORT_GUIDANCE = {
    "scatter": {
        "focus": "relationship strength, outliers, group separation, and whether a fitted trend is biologically plausible",
        "parameter_hint": "Check axis mapping first, then add color, labels, log scaling, and an optional trend line only when the variables justify it.",
    },
    "boxplot": {
        "focus": "group medians, spread, raw point distribution, outliers, and whether a pairwise test is appropriate",
        "parameter_hint": "Keep raw points visible by default, use group colors consistently, and add pairwise tests only after confirming the grouping design.",
    },
    "violin": {
        "focus": "distribution shape, multimodality, group spread, and whether a box overlay clarifies the summary",
        "parameter_hint": "Use violin plots when distribution shape matters; keep a box overlay and points when sample size is modest.",
    },
    "bar": {
        "focus": "aggregated group summaries, error bar meaning, and whether raw values should be overlaid",
        "parameter_hint": "Make the aggregation explicit, choose SD/SEM/CI deliberately, and prefer raw-point overlays for small sample sizes.",
    },
    "line": {
        "focus": "ordered trends, time-course behavior, missing values, and consistency across series",
        "parameter_hint": "Confirm the x-axis has a meaningful order before smoothing or connecting gaps.",
    },
    "histogram": {
        "focus": "single-variable distribution shape, skewness, tails, bin sensitivity, and group shifts",
        "parameter_hint": "Start with 30 bins, keep grouped histograms semi-transparent, and switch to density scaling when group sizes differ.",
    },
    "density_contour": {
        "focus": "two-variable density structure, crowded point regions, outliers, and whether groups occupy distinct regions",
        "parameter_hint": "Use contours for crowded scatter data, then add raw points with low opacity to avoid hiding rare samples.",
    },
    "scatter_3d": {
        "focus": "three-dimensional separation, outliers, axis contribution, and whether rotation changes the apparent grouping",
        "parameter_hint": "Map the three most interpretable numeric dimensions first, then use color for sample group or class.",
    },
    "surface_3d": {
        "focus": "matrix-level expression ridges, scaled feature blocks, row ranking, and whether 3D perspective helps or obscures the pattern",
        "parameter_hint": "Keep top_n modest for the first render, use row z-score scaling, and export 2D heatmap as the publication fallback.",
    },
    "radar": {
        "focus": "multi-metric sample or group profiles, axis balance, dominant metrics, and whether normalization changes the apparent pattern",
        "parameter_hint": "Use radar for a small number of profiles, normalize by axis for mixed-scale metrics, and switch to parallel coordinates when series count grows.",
    },
    "parallel_coordinates": {
        "focus": "high-dimensional numeric profiles, outlier trajectories, group coloring, and dimensions that separate samples",
        "parameter_hint": "Limit dimensions on the first render, color by a meaningful group or score, and use brushing to inspect unusual trajectories.",
    },
    "waterfall": {
        "focus": "ranked signed effects, strongest positive and negative changes, threshold-sensitive hits, and whether a few features dominate the result",
        "parameter_hint": "Use abs-value sorting for first review, keep the zero line visible, and color by significance when p-values are available.",
    },
    "ma_plot": {
        "focus": "mean-dependent fold-change patterns, low-abundance noise, high-abundance shifts, and asymmetry around the zero line",
        "parameter_hint": "Use a log x-axis for abundance, keep the zero line visible, and label only the strongest significant features.",
    },
    "heatmap": {
        "focus": "row/column clustering, scaled expression blocks, annotation consistency, and candidate feature groups",
        "parameter_hint": "Start with row z-score scaling, keep dendrograms enabled, and tune top_n for readability before exporting.",
    },
    "bubble": {
        "focus": "x/y relationships plus size and color encodings, especially whether large bubbles dominate interpretation",
        "parameter_hint": "Map size to a meaningful numeric variable, cap maximum bubble size, and use hover labels for dense regions.",
    },
    "volcano": {
        "focus": "up/down significant features, fold-change magnitude, p-value thresholds, and top labeled genes",
        "parameter_hint": "Start with abs(log2FC)=1 and p=0.05, then expose label count and adjusted-p threshold controls.",
    },
    "upset": {
        "focus": "set intersections, dominant overlap patterns, and whether rare intersections should be filtered",
        "parameter_hint": "Limit max sets and minimum intersection size so the chart stays interpretable.",
    },
    "venn": {
        "focus": "small-set overlaps, unique/shared counts, and whether percent labels help the audience",
        "parameter_hint": "Use Venn only for two to four sets; switch to UpSet when set count or overlap complexity grows.",
    },
    "correlation": {
        "focus": "sample or variable similarity blocks, low-correlation outliers, and group consistency after clustering",
        "parameter_hint": "Use Pearson for linear numeric relationships, Spearman for monotonic ranks, and keep group color bars consistent with upstream metadata.",
    },
    "enrichment_dot": {
        "focus": "top enriched terms, gene ratio, term size, adjusted significance, and redundant pathway labels",
        "parameter_hint": "Sort by adjusted p-value first, cap top terms, and use count/ratio encodings consistently.",
    },
}


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
    agent_context = _build_agent_context(
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
        "agent_context": agent_context,
    }


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
            {
                "title": "Figure interpretation",
                "text": observations["figure_interpretation"],
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
    figure_interpretation = _figure_interpretation(selected_preset["id"], table_summary)
    return {
        "data_readiness": data_readiness,
        "figure_choice": figure_choice,
        "signals": signals,
        "parameter_notes": parameter_notes,
        "figure_interpretation": figure_interpretation,
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
    if "diff" in source_type or meta.get("diff_gene_count") is not None:
        parts = []
        if meta.get("diff_gene_count") is not None:
            tested = meta.get("tested_gene_count", "unknown")
            parts.append(f"{meta.get('diff_gene_count')} significant feature(s) out of {tested} tested")
        if meta.get("comparison_label"):
            parts.append(f"comparison={meta.get('comparison_label')}")
        if meta.get("method"):
            parts.append(f"method={meta.get('method')}")
        if meta.get("p_value_threshold") is not None or meta.get("log2fc_threshold") is not None:
            parts.append(
                f"thresholds p<={meta.get('p_value_threshold', 'auto')}, abs(log2FC)>={meta.get('log2fc_threshold', 'auto')}"
            )
        if meta.get("r_script_file"):
            parts.append(f"R script={Path(str(meta.get('r_script_file'))).name}")
        if parts:
            return "Differential result metadata reports " + "; ".join(parts) + "."
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
    guidance = PLOT_REPORT_GUIDANCE.get(plot_id)
    if plot_id in {"heatmap", "correlation"}:
        group_note = "Group colors are available." if meta.get("condition_colors") else "Group colors are not attached yet."
        top_n = params.get("top_n") or params.get("top_genes") or 50
        hint = guidance["parameter_hint"] if guidance else "Keep clustering enabled and review dendrogram stability."
        return f"Use top_n={top_n} for the first render. {hint} {group_note} {_analysis_parameter_text(plot_id, params)} {_layout_parameter_summary(params)}"
    if guidance:
        return f"{guidance['parameter_hint']} {_analysis_parameter_text(plot_id, params)} {_layout_parameter_summary(params)}"
    if table_summary and len(table_summary.get("numeric_columns") or []) >= 2:
        return (
            "Map numeric columns first, then add color/facet fields only if categorical columns are present. "
            f"{_analysis_parameter_text(plot_id, params)} {_layout_parameter_summary(params)}"
        )
    return f"Start from the preset defaults, then refine mappings after the source table is inspected. {_analysis_parameter_text(plot_id, params)} {_layout_parameter_summary(params)}"


def _figure_interpretation(plot_id: str, table_summary: dict[str, Any] | None) -> str:
    guidance = PLOT_REPORT_GUIDANCE.get(plot_id)
    if not guidance:
        return "The report agent should describe what the selected chart can and cannot prove from the attached table."
    if table_summary:
        numeric_count = len(table_summary.get("numeric_columns") or [])
        categorical_count = len(table_summary.get("categorical_columns") or [])
        data_context = f"The scanned table has {numeric_count} numeric field(s) and {categorical_count} categorical field(s)."
    else:
        data_context = "No table was resolved, so interpretation must stay at the metadata-planning level."
    return (
        f"For {plot_id}, the report agent should focus on {guidance['focus']}. "
        f"{data_context} It should avoid claiming causality or visual details that are not present in the structured data."
    )


def _build_headline(
    source: dict[str, Any],
    selected_preset: dict[str, Any],
    table_summary: dict[str, Any] | None,
) -> str:
    name = str(source.get("name") or source.get("node_id") or source.get("nodeId") or "Selected source")
    if table_summary:
        return f"{selected_preset['label']} ready for {name}: {table_summary['scanned_rows']} scanned row(s)."
    return f"{selected_preset['label']} plan ready for {name}."


def _layout_parameter_summary(params: dict[str, Any]) -> str:
    notes = []
    title = str(params.get("title") or "").strip()
    subtitle = str(params.get("subtitle") or "").strip()
    if title:
        notes.append(f"title='{title}'")
    if subtitle:
        notes.append(f"subtitle='{subtitle}'")
    x_title = str(params.get("x_title") or "").strip()
    y_title = str(params.get("y_title") or "").strip()
    if x_title or y_title:
        notes.append(f"axis labels=({x_title or 'auto'}, {y_title or 'auto'})")
    if params.get("width") or params.get("height"):
        notes.append(f"canvas={params.get('width', 'auto')}x{params.get('height', 'auto')}")
    if params.get("format") or params.get("dpi"):
        notes.append(f"export={params.get('format', 'svg')}@{params.get('dpi', '300')}dpi")
    if not notes:
        return "No manual layout override is currently applied."
    return "Manual layout/export overrides: " + "; ".join(notes) + "."


def _analysis_parameter_text(plot_id: str, params: dict[str, Any]) -> str:
    summary = _parameter_summary(plot_id, params)
    notes = summary.get("statistics", []) + summary.get("display", []) + summary.get("interaction", [])
    if not notes:
        return "No analysis-specific parameter override is currently applied."
    return "Analysis/display overrides: " + "; ".join(notes) + "."


def _parameter_summary(plot_id: str, params: dict[str, Any]) -> dict[str, list[str]]:
    summary: dict[str, list[str]] = {"statistics": [], "display": [], "interaction": [], "export": []}
    if plot_id == "boxplot":
        pairwise_test = str(params.get("pairwise_test") or "none")
        if pairwise_test != "none":
            summary["statistics"].append(f"pairwise test={pairwise_test}")
            summary["statistics"].append(f"multiple testing={params.get('multiple_testing') or 'BH'}")
        if params.get("show_p_values"):
            summary["statistics"].append("p-values shown on plot")
        if "show_points" in params:
            summary["display"].append(f"raw points shown={bool(params.get('show_points'))}")
        if params.get("point_jitter") is not None:
            summary["display"].append(f"point jitter={params.get('point_jitter')}")
        if params.get("point_size"):
            summary["display"].append(f"point size={params.get('point_size')}")
        if params.get("point_alpha"):
            summary["display"].append(f"point opacity={params.get('point_alpha')}")
        if "show_mean" in params:
            summary["display"].append(f"mean marker={bool(params.get('show_mean'))}")
        if params.get("notched"):
            summary["display"].append("notched boxes enabled")
        if params.get("box_width"):
            summary["display"].append(f"box width={params.get('box_width')}")
    if plot_id == "violin":
        if "show_box" in params:
            summary["display"].append(f"box overlay={bool(params.get('show_box'))}")
        if "show_mean" in params:
            summary["display"].append(f"mean line={bool(params.get('show_mean'))}")
        if params.get("show_points"):
            summary["display"].append(f"points={params.get('show_points')}")
        if params.get("bandwidth"):
            summary["statistics"].append(f"bandwidth={params.get('bandwidth')}")
        if params.get("side"):
            summary["display"].append(f"side={params.get('side')}")
        if params.get("point_size"):
            summary["display"].append(f"point size={params.get('point_size')}")
        if params.get("point_alpha"):
            summary["display"].append(f"point opacity={params.get('point_alpha')}")
    if plot_id == "scatter":
        trendline = str(params.get("trendline") or "none")
        if trendline != "none":
            summary["statistics"].append(f"trendline={trendline}")
        if params.get("confidence_ellipse"):
            summary["statistics"].append(f"confidence ellipse={params.get('ellipse_level') or 0.95}")
        if params.get("color"):
            summary["display"].append(f"color by={params.get('color')}")
        if params.get("size"):
            summary["display"].append(f"size by={params.get('size')}")
        if params.get("label"):
            summary["display"].append(f"point labels={params.get('label')}")
        if params.get("point_size"):
            summary["display"].append(f"point size={params.get('point_size')}")
        if params.get("point_alpha"):
            summary["display"].append(f"point opacity={params.get('point_alpha')}")
        if params.get("marker_line_width") is not None:
            summary["display"].append(f"marker line width={params.get('marker_line_width')}")
        if params.get("marker_line_color"):
            summary["display"].append(f"marker line color={params.get('marker_line_color')}")
        if params.get("x_log"):
            summary["display"].append("log x-axis")
        if params.get("y_log"):
            summary["display"].append("log y-axis")
    if plot_id == "bar":
        if params.get("aggregation"):
            summary["statistics"].append(f"aggregation={params.get('aggregation')}")
        if params.get("error_bar"):
            summary["statistics"].append(f"error bar={params.get('error_bar')}")
        if "show_points" in params:
            summary["display"].append(f"raw points shown={bool(params.get('show_points'))}")
        if params.get("point_alpha"):
            summary["display"].append(f"point opacity={params.get('point_alpha')}")
        if params.get("error_cap_width") is not None:
            summary["display"].append(f"error cap width={params.get('error_cap_width')}")
        if params.get("show_values"):
            summary["display"].append(f"value labels shown with {params.get('value_precision', 2)} decimals")
        if params.get("bar_width"):
            summary["display"].append(f"bar width={params.get('bar_width')}")
        if params.get("sort"):
            summary["display"].append(f"sort bars={params.get('sort')}")
        if params.get("orientation"):
            summary["display"].append(f"orientation={params.get('orientation')}")
        pairwise_test = str(params.get("pairwise_test") or "none")
        if pairwise_test != "none":
            summary["statistics"].append(f"pairwise test={pairwise_test}")
            summary["statistics"].append(f"multiple testing={params.get('multiple_testing') or 'BH'}")
        if params.get("show_p_values"):
            summary["statistics"].append("p-values shown on plot")
    if plot_id == "line":
        if params.get("line_shape"):
            summary["display"].append(f"line shape={params.get('line_shape')}")
        if params.get("line_width"):
            summary["display"].append(f"line width={params.get('line_width')}")
        if params.get("line_dash"):
            summary["display"].append(f"line dash={params.get('line_dash')}")
        if params.get("smooth"):
            summary["display"].append("spline smoothing enabled")
        if "show_points" in params:
            summary["display"].append(f"markers shown={bool(params.get('show_points'))}")
        if params.get("marker_size"):
            summary["display"].append(f"marker size={params.get('marker_size')}")
        if params.get("marker_symbol"):
            summary["display"].append(f"marker symbol={params.get('marker_symbol')}")
        if params.get("connect_gaps"):
            summary["display"].append("missing values connected")
    if plot_id == "histogram":
        if params.get("bins"):
            summary["display"].append(f"bins={params.get('bins')}")
        if params.get("histnorm"):
            summary["display"].append(f"scale={params.get('histnorm')}")
        if params.get("barmode"):
            summary["display"].append(f"bar mode={params.get('barmode')}")
        if params.get("opacity") is not None:
            summary["display"].append(f"opacity={params.get('opacity')}")
        if params.get("bar_line_width") is not None:
            summary["display"].append(f"bar line width={params.get('bar_line_width')}")
        if params.get("bar_line_color"):
            summary["display"].append(f"bar line color={params.get('bar_line_color')}")
        if params.get("reference_line_width") is not None:
            summary["display"].append(f"reference line width={params.get('reference_line_width')}")
        if params.get("reference_line_color_mode"):
            summary["display"].append(f"reference line color mode={params.get('reference_line_color_mode')}")
        if params.get("reference_line_color_mode") == "custom" and params.get("reference_line_color"):
            summary["display"].append(f"reference line color={params.get('reference_line_color')}")
        if params.get("cumulative"):
            summary["statistics"].append("cumulative histogram")
        if params.get("show_mean"):
            summary["statistics"].append("mean reference shown")
        if params.get("show_median"):
            summary["statistics"].append("median reference shown")
        if params.get("show_rug"):
            summary["display"].append("rug marks shown")
    if plot_id == "radar":
        if params.get("max_series"):
            summary["display"].append(f"max series={params.get('max_series')}")
        if params.get("aggregation"):
            summary["statistics"].append(f"aggregation={params.get('aggregation')}")
        if params.get("normalize"):
            summary["statistics"].append(f"normalization={params.get('normalize')}")
        if "fill" in params:
            summary["display"].append(f"filled polygons={bool(params.get('fill'))}")
        if params.get("line_width"):
            summary["display"].append(f"line width={params.get('line_width')}")
        if params.get("marker_size") is not None:
            summary["display"].append(f"marker size={params.get('marker_size')}")
    if plot_id == "parallel_coordinates":
        if params.get("max_dimensions"):
            summary["display"].append(f"max dimensions={params.get('max_dimensions')}")
        if params.get("max_rows"):
            summary["display"].append(f"max rows={params.get('max_rows')}")
        if params.get("color"):
            summary["display"].append(f"color by={params.get('color')}")
        if params.get("color_scale"):
            summary["display"].append(f"color scale={params.get('color_scale')}")
        if "show_colorbar" in params:
            summary["display"].append(f"color bar shown={bool(params.get('show_colorbar'))}")
        if params.get("line_opacity") is not None:
            summary["display"].append(f"line opacity={params.get('line_opacity')}")
    if plot_id == "bubble":
        if params.get("size_scale"):
            summary["display"].append(f"size scale={params.get('size_scale')}")
        if params.get("min_bubble_size") or params.get("max_bubble_size"):
            summary["display"].append(
                f"bubble size range={params.get('min_bubble_size', 'auto')}-{params.get('max_bubble_size', 'auto')}"
            )
        if params.get("color_scale"):
            summary["display"].append(f"continuous color scale={params.get('color_scale')}")
        if params.get("point_alpha"):
            summary["display"].append(f"point opacity={params.get('point_alpha')}")
        if params.get("marker_line_width") is not None:
            summary["display"].append(f"marker line width={params.get('marker_line_width')}")
        if params.get("marker_line_color"):
            summary["display"].append(f"marker line color={params.get('marker_line_color')}")
    if plot_id == "density_contour":
        if params.get("contours_coloring"):
            summary["display"].append(f"contour fill={params.get('contours_coloring')}")
        if params.get("contour_line_width"):
            summary["display"].append(f"contour line width={params.get('contour_line_width')}")
        if params.get("show_contour_labels"):
            summary["display"].append("contour labels shown")
        contour_window = [
            str(params.get("contour_start", "auto")),
            str(params.get("contour_end", "auto")),
            str(params.get("contour_size", "auto")),
        ]
        if contour_window != ["auto", "auto", "auto"]:
            summary["statistics"].append(f"contour range/step={','.join(contour_window)}")
    if plot_id == "scatter_3d":
        if params.get("marker_size"):
            summary["display"].append(f"marker size={params.get('marker_size')}")
        if params.get("point_alpha"):
            summary["display"].append(f"point opacity={params.get('point_alpha')}")
        if params.get("camera"):
            summary["display"].append(f"camera={params.get('camera')}")
    if plot_id == "surface_3d":
        if params.get("scale"):
            summary["statistics"].append(f"scale={params.get('scale')}")
        if params.get("top_n"):
            summary["display"].append(f"top rows={params.get('top_n')}")
        if params.get("colorscale"):
            summary["display"].append(f"colorscale={params.get('colorscale')}")
        if "show_contours" in params:
            summary["display"].append(f"surface contours={bool(params.get('show_contours'))}")
        if params.get("camera"):
            summary["display"].append(f"camera={params.get('camera')}")
    if plot_id == "volcano":
        if params.get("log2fc_threshold") is not None:
            summary["statistics"].append(f"abs log2FC threshold={params.get('log2fc_threshold')}")
        if params.get("p_value_threshold") is not None:
            summary["statistics"].append(f"p-value threshold={params.get('p_value_threshold')}")
        if "show_threshold_lines" in params:
            summary["display"].append(f"threshold lines={bool(params.get('show_threshold_lines'))}")
        if params.get("threshold_line_width") is not None:
            summary["display"].append(f"threshold line width={params.get('threshold_line_width')}")
        if params.get("threshold_line_dash"):
            summary["display"].append(f"threshold line dash={params.get('threshold_line_dash')}")
        if params.get("threshold_line_color"):
            summary["display"].append(f"threshold line color={params.get('threshold_line_color')}")
        if params.get("label_top_n") is not None:
            summary["display"].append(f"top labels={params.get('label_top_n')}")
        if params.get("label_mode"):
            summary["display"].append(f"label mode={params.get('label_mode')}")
        if params.get("label_font_size"):
            summary["display"].append(f"label font size={params.get('label_font_size')}")
        if params.get("point_size"):
            summary["display"].append(f"point size={params.get('point_size')}")
        if params.get("point_alpha"):
            summary["display"].append(f"point opacity={params.get('point_alpha')}")
    if plot_id == "waterfall":
        if params.get("value_column"):
            summary["statistics"].append(f"signed value={params.get('value_column')}")
        if params.get("sort_by"):
            summary["display"].append(f"sort by={params.get('sort_by')}")
        if params.get("top_n"):
            summary["display"].append(f"top bars={params.get('top_n')}")
        if params.get("orientation"):
            summary["display"].append(f"orientation={params.get('orientation')}")
        if params.get("color_mode"):
            summary["display"].append(f"color mode={params.get('color_mode')}")
        if params.get("log2fc_threshold") is not None:
            summary["statistics"].append(f"abs value threshold={params.get('log2fc_threshold')}")
        if params.get("p_value_threshold") is not None:
            summary["statistics"].append(f"p-value threshold={params.get('p_value_threshold')}")
        if "show_zero_line" in params:
            summary["display"].append(f"zero line={bool(params.get('show_zero_line'))}")
        if "show_value_labels" in params:
            summary["display"].append(f"value labels={bool(params.get('show_value_labels'))}")
        if params.get("bar_opacity") is not None:
            summary["display"].append(f"bar opacity={params.get('bar_opacity')}")
    if plot_id == "ma_plot":
        if params.get("mean_column"):
            summary["statistics"].append(f"mean abundance={params.get('mean_column')}")
        if params.get("log2fc_column"):
            summary["statistics"].append(f"log2FC={params.get('log2fc_column')}")
        if params.get("log2fc_threshold") is not None:
            summary["statistics"].append(f"abs log2FC threshold={params.get('log2fc_threshold')}")
        if params.get("p_value_threshold") is not None:
            summary["statistics"].append(f"p-value threshold={params.get('p_value_threshold')}")
        if "x_log" in params:
            summary["display"].append(f"log x-axis={bool(params.get('x_log'))}")
        if "show_threshold_lines" in params:
            summary["display"].append(f"threshold lines={bool(params.get('show_threshold_lines'))}")
        if params.get("label_top_n") is not None:
            summary["display"].append(f"top labels={params.get('label_top_n')}")
        if params.get("point_size"):
            summary["display"].append(f"point size={params.get('point_size')}")
        if params.get("point_alpha"):
            summary["display"].append(f"point opacity={params.get('point_alpha')}")
    if plot_id in {"heatmap", "correlation"}:
        if plot_id == "correlation" and params.get("method"):
            summary["statistics"].append(f"method={params.get('method')}")
        if plot_id == "heatmap" and params.get("scale"):
            summary["statistics"].append(f"scale={params.get('scale')}")
        if "cluster_rows" in params:
            summary["statistics"].append(f"cluster rows={bool(params.get('cluster_rows'))}")
        if "cluster_columns" in params:
            summary["statistics"].append(f"cluster columns={bool(params.get('cluster_columns'))}")
        if params.get("distance"):
            summary["statistics"].append(f"distance={params.get('distance')}")
        if params.get("linkage"):
            summary["statistics"].append(f"linkage={params.get('linkage')}")
        if plot_id == "heatmap" and params.get("show_dendrogram"):
            summary["display"].append("dendrogram guides shown")
        if plot_id == "heatmap" and params.get("palette"):
            summary["display"].append(f"color scale={params.get('palette')}")
        if plot_id == "heatmap" and params.get("show_values"):
            summary["display"].append(f"cell values shown with {params.get('value_precision', 2)} decimals")
        if plot_id == "heatmap" and params.get("cell_gap") is not None:
            summary["display"].append(f"cell gap={params.get('cell_gap')}")
        if plot_id == "correlation" and params.get("show_values"):
            summary["display"].append(f"r-value labels shown with {params.get('value_precision', 2)} decimals")
        if plot_id == "correlation" and params.get("color_scale"):
            summary["display"].append(f"color scale={params.get('color_scale')}")
        if plot_id == "correlation" and params.get("cell_gap") is not None:
            summary["display"].append(f"cell gap={params.get('cell_gap')}")
        if params.get("top_n"):
            summary["display"].append(f"top rows={params.get('top_n')}")
    if plot_id == "upset":
        if params.get("min_intersection_size"):
            summary["statistics"].append(f"min intersection={params.get('min_intersection_size')}")
        if params.get("max_sets"):
            summary["display"].append(f"max sets={params.get('max_sets')}")
        if params.get("max_intersections"):
            summary["display"].append(f"max intersections={params.get('max_intersections')}")
        if params.get("sort_by"):
            summary["display"].append(f"sort by={params.get('sort_by')}")
    if plot_id == "venn":
        if params.get("max_sets"):
            summary["display"].append(f"max sets={params.get('max_sets')}")
        if "show_counts" in params:
            summary["display"].append(f"show counts={bool(params.get('show_counts'))}")
        if "show_percent" in params:
            summary["display"].append(f"show percent={bool(params.get('show_percent'))}")
    if plot_id == "enrichment_dot":
        if params.get("top_n"):
            summary["display"].append(f"top terms={params.get('top_n')}")
        if params.get("sort_by"):
            summary["statistics"].append(f"sort by={params.get('sort_by')}")
        if params.get("color_transform"):
            summary["statistics"].append(f"color transform={params.get('color_transform')}")
        if params.get("wrap_term_label"):
            summary["display"].append("wrapped term labels")
        if params.get("term_label_width"):
            summary["display"].append(f"term label width={params.get('term_label_width')}")
        if params.get("min_dot_size") or params.get("max_dot_size"):
            summary["display"].append(
                f"dot size range={params.get('min_dot_size', 'auto')}-{params.get('max_dot_size', 'auto')}"
            )
        if params.get("color_scale"):
            summary["display"].append(f"color scale={params.get('color_scale')}")
        if params.get("point_alpha"):
            summary["display"].append(f"point opacity={params.get('point_alpha')}")
    if params.get("width") or params.get("height"):
        summary["export"].append(f"canvas={params.get('width', 'auto')}x{params.get('height', 'auto')}")
    if params.get("format") or params.get("dpi"):
        summary["export"].append(f"export={params.get('format', 'svg')}@{params.get('dpi', '300')}dpi")
    if params.get("export_filename"):
        summary["export"].append(f"filename={params.get('export_filename')}")
    if "show_grid" in params:
        summary["display"].append(f"grid shown={bool(params.get('show_grid'))}")
    if params.get("grid_color"):
        summary["display"].append(f"grid color={params.get('grid_color')}")
    if params.get("grid_width") is not None:
        summary["display"].append(f"grid width={params.get('grid_width')}")
    if "show_zero_line" in params:
        summary["display"].append(f"zero line shown={bool(params.get('show_zero_line'))}")
    if params.get("zero_line_color"):
        summary["display"].append(f"zero line color={params.get('zero_line_color')}")
    if params.get("zero_line_width") is not None:
        summary["display"].append(f"zero line width={params.get('zero_line_width')}")
    if "axis_line" in params:
        summary["display"].append(f"axis line shown={bool(params.get('axis_line'))}")
    if params.get("axis_line_color"):
        summary["display"].append(f"axis line color={params.get('axis_line_color')}")
    if params.get("axis_line_width") is not None:
        summary["display"].append(f"axis line width={params.get('axis_line_width')}")
    if params.get("axis_mirror"):
        summary["display"].append(f"axis mirror={params.get('axis_mirror')}")
    if params.get("legend_title"):
        summary["display"].append(f"legend title='{params.get('legend_title')}'")
    if params.get("legend_font_size") is not None:
        summary["display"].append(f"legend font size={params.get('legend_font_size')}")
    if params.get("legend_background"):
        summary["display"].append(f"legend background={params.get('legend_background')}")
    if params.get("legend_border_color"):
        summary["display"].append(f"legend border color={params.get('legend_border_color')}")
    if params.get("legend_border_width") is not None:
        summary["display"].append(f"legend border width={params.get('legend_border_width')}")
    if params.get("title_font_size") is not None:
        summary["display"].append(f"title size={params.get('title_font_size')}")
    if params.get("title_color"):
        summary["display"].append(f"title color={params.get('title_color')}")
    if params.get("subtitle_font_size") is not None:
        summary["display"].append(f"subtitle size={params.get('subtitle_font_size')}")
    if params.get("subtitle_color"):
        summary["display"].append(f"subtitle color={params.get('subtitle_color')}")
    if params.get("axis_title_font_size") is not None:
        summary["display"].append(f"axis title size={params.get('axis_title_font_size')}")
    if params.get("axis_title_color"):
        summary["display"].append(f"axis title color={params.get('axis_title_color')}")
    if params.get("tick_font_size") is not None:
        summary["display"].append(f"tick label size={params.get('tick_font_size')}")
    if params.get("tick_color"):
        summary["display"].append(f"tick label color={params.get('tick_color')}")
    if params.get("tick_direction"):
        summary["display"].append(f"tick direction={params.get('tick_direction')}")
    if params.get("tick_length") is not None:
        summary["display"].append(f"tick length={params.get('tick_length')}")
    if params.get("tick_width") is not None:
        summary["display"].append(f"tick width={params.get('tick_width')}")
    if params.get("tick_line_color"):
        summary["display"].append(f"tick line color={params.get('tick_line_color')}")
    if params.get("x_range_mode") == "custom":
        summary["display"].append(f"x range={params.get('x_min', 'auto')} to {params.get('x_max', 'auto')}")
    if params.get("y_range_mode") == "custom":
        summary["display"].append(f"y range={params.get('y_min', 'auto')} to {params.get('y_max', 'auto')}")
    if params.get("x_tick_count") not in {None, "", "auto"}:
        summary["display"].append(f"x tick count={params.get('x_tick_count')}")
    if params.get("y_tick_count") not in {None, "", "auto"}:
        summary["display"].append(f"y tick count={params.get('y_tick_count')}")
    if params.get("x_tick_format"):
        summary["display"].append(f"x tick format={params.get('x_tick_format')}")
    if params.get("y_tick_format"):
        summary["display"].append(f"y tick format={params.get('y_tick_format')}")
    if params.get("x_tick_prefix"):
        summary["display"].append(f"x tick prefix={params.get('x_tick_prefix')}")
    if params.get("x_tick_suffix"):
        summary["display"].append(f"x tick suffix={params.get('x_tick_suffix')}")
    if params.get("y_tick_prefix"):
        summary["display"].append(f"y tick prefix={params.get('y_tick_prefix')}")
    if params.get("y_tick_suffix"):
        summary["display"].append(f"y tick suffix={params.get('y_tick_suffix')}")
    if params.get("show_v_reference"):
        summary["display"].append(f"vertical guide={params.get('v_reference_value', 'auto')}")
        if params.get("v_reference_label"):
            summary["display"].append(f"vertical guide label='{params.get('v_reference_label')}'")
        if params.get("v_reference_color"):
            summary["display"].append(f"vertical guide color={params.get('v_reference_color')}")
        if params.get("v_reference_width") is not None:
            summary["display"].append(f"vertical guide width={params.get('v_reference_width')}")
        if params.get("v_reference_dash"):
            summary["display"].append(f"vertical guide dash={params.get('v_reference_dash')}")
    if params.get("show_h_reference"):
        summary["display"].append(f"horizontal guide={params.get('h_reference_value', 'auto')}")
        if params.get("h_reference_label"):
            summary["display"].append(f"horizontal guide label='{params.get('h_reference_label')}'")
        if params.get("h_reference_color"):
            summary["display"].append(f"horizontal guide color={params.get('h_reference_color')}")
        if params.get("h_reference_width") is not None:
            summary["display"].append(f"horizontal guide width={params.get('h_reference_width')}")
        if params.get("h_reference_dash"):
            summary["display"].append(f"horizontal guide dash={params.get('h_reference_dash')}")
    if params.get("hover_mode"):
        summary["interaction"].append(f"hover mode={params.get('hover_mode')}")
    if params.get("drag_mode"):
        summary["interaction"].append(f"drag mode={params.get('drag_mode')}")
    if params.get("display_modebar"):
        summary["interaction"].append(f"toolbar={params.get('display_modebar')}")
    if "scroll_zoom" in params:
        summary["interaction"].append(f"scroll zoom={bool(params.get('scroll_zoom'))}")
    if "selection_tools" in params:
        summary["interaction"].append(f"selection tools={bool(params.get('selection_tools'))}")
    if "show_spikes" in params:
        summary["interaction"].append(f"axis hover guide={bool(params.get('show_spikes'))}")
    if params.get("spike_color"):
        summary["interaction"].append(f"hover guide color={params.get('spike_color')}")
    if params.get("spike_width") is not None:
        summary["interaction"].append(f"hover guide width={params.get('spike_width')}")
    if params.get("spike_dash"):
        summary["interaction"].append(f"hover guide dash={params.get('spike_dash')}")
    if params.get("hover_label_background"):
        summary["interaction"].append(f"hover label background={params.get('hover_label_background')}")
    if params.get("hover_label_color"):
        summary["interaction"].append(f"hover label color={params.get('hover_label_color')}")
    if params.get("hover_label_font_size") is not None:
        summary["interaction"].append(f"hover label size={params.get('hover_label_font_size')}")
    return {key: value for key, value in summary.items() if value}


def _build_agent_context(
    *,
    source: dict[str, Any],
    source_type: str,
    selected_preset: dict[str, Any],
    table_summary: dict[str, Any] | None,
    params: dict[str, Any],
    path_reason: str,
) -> dict[str, Any]:
    meta = dict(source.get("meta") or {})
    return {
        "purpose": "LLM-readable context for explaining a Plot Studio figure without image vision.",
        "source_type": source_type or "unknown",
        "source_name": source.get("name") or source.get("nodeId") or source.get("node_id"),
        "path_reason": path_reason,
        "plot": {
            "id": selected_preset["id"],
            "label": selected_preset["label"],
            "engine": selected_preset["engine"],
            "focus": PLOT_REPORT_GUIDANCE.get(selected_preset["id"], {}).get("focus", ""),
        },
        "table": _compact_table_context(table_summary),
        "metadata": {key: meta[key] for key in sorted(meta)[:12]},
        "params": params,
        "parameter_summary": _parameter_summary(selected_preset["id"], params),
        "interpretation_rules": [
            "Use only metadata, table summaries, statistics, and parameters in this object.",
            "Do not infer visual details from a rendered image.",
            "State uncertainty when the table is missing or only partially scanned.",
        ],
    }


def _compact_table_context(table_summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if table_summary is None:
        return None
    signals = table_summary.get("signals") or {}
    return {
        "filename": table_summary.get("filename"),
        "scanned_rows": table_summary.get("scanned_rows"),
        "column_count": table_summary.get("column_count"),
        "numeric_columns": (table_summary.get("numeric_columns") or [])[:20],
        "categorical_columns": (table_summary.get("categorical_columns") or [])[:20],
        "signals": signals,
    }


