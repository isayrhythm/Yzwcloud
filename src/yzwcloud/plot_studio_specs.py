from __future__ import annotations

import math
import re
from datetime import date, datetime
from statistics import fmean, median, pstdev
from typing import Any

from yzwcloud.plot_studio_presets import (
    PLOTLY_PALETTE,
    PLOT_PRESETS,
    PLOT_STUDIO_VERSION,
    SUPPORTED_PLOTLY_SPEC_TYPES,
    recommend_plot_types,
)
from yzwcloud.plot_studio_source import _select_source_table, _source_summary
from yzwcloud.plot_studio_tables import _load_table_records, inspect_table
from yzwcloud.plot_studio_utils import _normalize_column_name, _normalize_plot_id, _parse_float, _round_number


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
    single_row_warning = _single_row_plot_warning(selected_plot_id, table_summary)
    if single_row_warning:
        return _empty_plot_spec(selected_plot_id, single_row_warning, table_summary)
    columns, records = _load_table_records(
        data_path,
        max_rows=_bounded_int(resolved_params.get("max_rows"), 800, 50, 5000),
    )
    raw_numeric_columns = [
        column
        for column in table_summary["numeric_columns"]
        if column in columns and _numeric_value_count(records, column) > 0
    ]
    numeric_columns = _preferred_numeric_columns(table_summary, raw_numeric_columns)
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
        "grouped_dotplot": _build_grouped_dotplot_spec,
        "raincloud": _build_raincloud_spec,
        "violin": _build_violin_spec,
        "ridgeline": _build_ridgeline_spec,
        "bar": _build_bar_spec,
        "line": _build_line_spec,
        "histogram": _build_histogram_spec,
        "density_curve": _build_density_curve_spec,
        "ecdf": _build_ecdf_spec,
        "calendar_heatmap": _build_calendar_heatmap_spec,
        "density_contour": _build_density_contour_spec,
        "scatter_3d": _build_scatter_3d_spec,
        "surface_3d": _build_surface_3d_spec,
        "radar": _build_radar_spec,
        "parallel_coordinates": _build_parallel_coordinates_spec,
        "waterfall": _build_waterfall_spec,
        "lollipop": _build_lollipop_spec,
        "ma_plot": _build_ma_plot_spec,
        "qq_plot": _build_qq_plot_spec,
        "forest_plot": _build_forest_plot_spec,
        "roc_curve": _build_roc_curve_spec,
        "pr_curve": _build_pr_curve_spec,
        "kaplan_meier": _build_kaplan_meier_spec,
        "bland_altman": _build_bland_altman_spec,
        "dose_response": _build_dose_response_spec,
        "paired_dot": _build_paired_dot_spec,
        "dumbbell": _build_dumbbell_spec,
        "bubble": _build_bubble_spec,
        "volcano": _build_volcano_spec,
        "upset": _build_upset_spec,
        "venn": _build_venn_spec,
        "heatmap": _build_heatmap_spec,
        "correlation": _build_correlation_spec,
        "enrichment_dot": _build_enrichment_dot_spec,
        "enrichment_bar": _build_enrichment_bar_spec,
        "composition_bar": _build_composition_bar_spec,
        "donut": _build_donut_spec,
        "sankey": _build_sankey_spec,
        "treemap": _build_treemap_spec,
        "sunburst": _build_sunburst_spec,
        "wordcloud": _build_wordcloud_spec,
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


def _single_row_plot_warning(plot_id: str, table_summary: dict[str, Any]) -> str:
    row_count = int(table_summary.get("scanned_rows") or table_summary.get("row_count") or 0)
    if row_count > 1:
        return ""
    if plot_id in {"scatter", "density_contour"}:
        return "Scatter-style plots require at least two complete x/y numeric rows; choose Bar or Histogram for a single-row profile."
    if plot_id == "scatter_3d":
        return "3D scatter requires at least two complete x/y/z numeric rows; choose Bar or Histogram for a single-row profile."
    if plot_id == "bubble":
        return "Bubble plots require at least two complete x/y/size rows; choose Bar or Histogram for a single-row profile."
    if plot_id in {"radar", "parallel_coordinates"}:
        return "Radar and parallel-coordinate plots require at least two sample or group profiles; choose Bar or Histogram for a single-row profile."
    if plot_id == "correlation":
        return "Correlation heatmaps require at least two observation rows; choose Bar or Histogram for a single-row profile."
    return ""


def _build_scatter_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    numeric_columns = context["numeric_columns"]
    x_column = _choose_column(params.get("x"), numeric_columns, fallback_index=0)
    y_column = _choose_column(params.get("y"), numeric_columns, fallback_index=1)
    if not x_column or not y_column:
        return _empty_plot_spec("scatter", "Scatter requires at least two numeric columns.", context["table_summary"])
    if _complete_numeric_row_count(context["records"], [x_column, y_column]) < 2:
        return _empty_plot_spec(
            "scatter",
            "Scatter requires at least two complete x/y numeric rows; upload more rows or choose a single-row summary chart.",
            context["table_summary"],
        )

    color_column = _choose_column(params.get("color"), context["categorical_columns"])
    label_column = _choose_column(params.get("label"), context["columns"])
    size_column = _requested_column(params.get("size"), numeric_columns)
    warnings = []
    if size_column in {x_column, y_column}:
        warnings.append("Ignored size mapping because it reused the X/Y axis column.")
        size_column = None
    traces = _grouped_marker_traces(
        context["records"],
        x_column=x_column,
        y_column=y_column,
        color_column=color_column,
        label_column=label_column,
        size_column=size_column,
        mode="markers",
        marker_size=_bounded_float(params.get("point_size"), 8, 1, 40),
        marker_opacity=_bounded_float(params.get("point_alpha"), 0.85, 0.05, 1),
        marker_line_width=_bounded_float(params.get("marker_line_width"), 0.5, 0, 5),
        marker_line_color=str(params.get("marker_line_color") or "#ffffff"),
        category_label_map=_category_label_map(params),
    )
    overlays, overlay_warnings, overlay_annotations = _scatter_statistical_overlays(traces, params)
    traces.extend(overlays)
    warnings.extend(overlay_warnings)
    layout = _base_layout(
        title=f"Scatter: {x_column} vs {y_column}",
        x_title=x_column,
        y_title=y_column,
        params=params,
    )
    if _truthy(params.get("x_log"), False):
        layout["xaxis"]["type"] = "log"
    if _truthy(params.get("y_log"), False):
        layout["yaxis"]["type"] = "log"
    if overlay_annotations:
        layout.setdefault("annotations", []).extend(overlay_annotations)
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


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
    size_scale = _bounded_float(params.get("size_scale"), 18, 1, 100)
    max_marker = _bounded_float(params.get("max_bubble_size"), 48, min_marker, 160) * size_scale / 18
    max_marker = _bounded_float(max_marker, 48, min_marker, 220)
    requested_color = _requested_column(params.get("color"), context["columns"])
    color_is_numeric = bool(requested_color and requested_color in numeric_columns)
    color_column = requested_color if requested_color and requested_color in context["categorical_columns"] else None
    label_column = _choose_column(params.get("label"), context["columns"])
    traces = []
    grouped = _records_by_category(context["records"], color_column) if color_column else {"All": context["records"]}
    for index, (group_name, rows) in enumerate(grouped.items()):
        x_values = []
        y_values = []
        marker_sizes = []
        labels = []
        size_values = []
        color_values = []
        for row in rows:
            x_value = _number_or_none(row.get(x_column))
            y_value = _number_or_none(row.get(y_column))
            size_value = _number_or_none(row.get(size_column))
            if x_value is None or y_value is None or size_value is None:
                continue
            x_values.append(x_value)
            y_values.append(y_value)
            size_values.append(size_value)
            marker_sizes.append(min_marker + (size_value - min_size) / span * (max_marker - min_marker))
            labels.append(str(row.get(label_column) or "") if label_column else "")
            if color_is_numeric and requested_color:
                color_values.append(_number_or_none(row.get(requested_color)))
        if not x_values:
            continue
        marker: dict[str, Any] = {
            "size": marker_sizes,
            "sizemode": "diameter",
            "opacity": _bounded_float(params.get("point_alpha"), 0.72, 0.05, 1),
            "line": {
                "color": str(params.get("marker_line_color") or "#ffffff"),
                "width": _bounded_float(params.get("marker_line_width"), 0.7, 0, 5),
            },
        }
        if color_is_numeric and requested_color:
            marker["color"] = [value if value is not None else 0.0 for value in color_values]
            marker["colorscale"] = _colorscale(str(params.get("color_scale") or "viridis"))
            marker["showscale"] = True
            marker["colorbar"] = {"title": requested_color}
        else:
            marker["color"] = PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)]
        traces.append(
            {
                "type": "scattergl",
                "mode": "markers",
                "name": group_name if not color_is_numeric else requested_color or "All",
                "x": x_values,
                "y": y_values,
                "text": labels,
                "customdata": [[size_values[item_index]] for item_index in range(len(size_values))],
                "marker": marker,
                "hovertemplate": "%{text}<br>x=%{x:.4g}<br>y=%{y:.4g}<br>size=%{customdata[0]:.4g}<extra>%{fullData.name}</extra>",
                "showlegend": not color_is_numeric,
            }
        )

    layout = _base_layout(
        title=f"Bubble: {x_column} vs {y_column}, size={size_column}",
        x_title=x_column,
        y_title=y_column,
        params=params,
    )
    warnings = []
    if not traces:
        warnings.append("No complete x/y/size rows were available for bubble rendering.")
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _build_radar_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    max_series = _bounded_int(params.get("max_series"), 6, 1, 24)
    value_columns = _selected_columns(params.get("value_columns"), context["numeric_columns"], limit=24)
    if len(value_columns) < 3:
        return _empty_plot_spec("radar", "Radar requires at least three numeric metric columns.", context["table_summary"])

    group_column = _choose_column(params.get("group"), context["categorical_columns"])
    label_column = _choose_column(params.get("label"), context["columns"])
    series = []
    if group_column:
        grouped = _records_by_category(context["records"], group_column)
        for group_name, rows in list(grouped.items())[:max_series]:
            values = [_aggregate_column(rows, column, str(params.get("aggregation") or "mean")) for column in value_columns]
            if any(value is not None for value in values):
                series.append({"name": group_name, "values": _fill_missing_numeric(values)})
    else:
        for index, row in enumerate(context["records"][:max_series]):
            values = [_number_or_none(row.get(column)) for column in value_columns]
            if any(value is not None for value in values):
                name = str(row.get(label_column) or f"row_{index + 1}") if label_column else f"row_{index + 1}"
                series.append({"name": name, "values": _fill_missing_numeric(values)})

    if not series:
        return _empty_plot_spec("radar", "No complete numeric profiles were available for radar rendering.", context["table_summary"])
    if len(series) < 2:
        return _empty_plot_spec(
            "radar",
            "Radar requires at least two sample or group profiles; a single row is not enough for a meaningful radar comparison.",
            context["table_summary"],
        )

    normalized_series = _normalize_profile_series(series, str(params.get("normalize") or "minmax_by_axis"))
    closed_theta = value_columns + [value_columns[0]]
    traces = []
    for index, item in enumerate(normalized_series):
        values = item["values"] + [item["values"][0]]
        traces.append(
            {
                "type": "scatterpolar",
                "mode": "lines+markers" if _bounded_float(params.get("marker_size"), 5, 0, 20) > 0 else "lines",
                "name": item["name"],
                "theta": closed_theta,
                "r": values,
                "fill": "toself" if _truthy(params.get("fill"), True) else "none",
                "line": {"color": PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)], "width": _bounded_float(params.get("line_width"), 2.2, 0.5, 8)},
                "marker": {"size": _bounded_float(params.get("marker_size"), 5, 0, 20)},
                "hovertemplate": "%{theta}<br>value=%{r:.4g}<extra>%{fullData.name}</extra>",
            }
        )

    layout = _base_layout(title="Radar profile", x_title="", y_title="", params=params)
    layout.pop("xaxis", None)
    layout.pop("yaxis", None)
    layout["polar"] = {
        "bgcolor": layout.get("plot_bgcolor", "#ffffff"),
        "radialaxis": {"visible": True, "showline": True, "gridcolor": str(params.get("grid_color") or "#e7eef4")},
        "angularaxis": {"direction": "clockwise", "gridcolor": str(params.get("grid_color") or "#e7eef4")},
    }
    if str(params.get("normalize") or "minmax_by_axis") == "minmax_by_axis":
        layout["polar"]["radialaxis"]["range"] = [0, 1]
    warnings = []
    if group_column and len(_records_by_category(context["records"], group_column)) > max_series:
        warnings.append(f"Showing first {max_series} group profiles to keep the radar readable.")
    elif not group_column and len(context["records"]) > max_series:
        warnings.append(f"Showing first {max_series} row profiles to keep the radar readable.")
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _build_parallel_coordinates_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    max_dimensions = _bounded_int(params.get("max_dimensions"), 8, 3, 24)
    max_rows = _bounded_int(params.get("max_rows"), 800, 20, 5000)
    dimension_columns = _selected_columns(params.get("dimensions"), context["numeric_columns"], limit=max_dimensions)
    if len(dimension_columns) < 3:
        return _empty_plot_spec(
            "parallel_coordinates",
            "Parallel coordinates requires at least three numeric dimension columns.",
            context["table_summary"],
        )

    rows = context["records"][:max_rows]
    if len(rows) < 2:
        return _empty_plot_spec(
            "parallel_coordinates",
            "Parallel coordinates requires at least two rows to compare profile paths.",
            context["table_summary"],
        )
    dimensions = []
    for column in dimension_columns:
        values = [_number_or_none(row.get(column)) for row in rows]
        filled_values = _fill_missing_numeric(values)
        if not filled_values:
            continue
        dimensions.append({"label": column, "values": filled_values})
    if len(dimensions) < 3:
        return _empty_plot_spec("parallel_coordinates", "Not enough complete numeric dimensions were available.", context["table_summary"])

    color_column = _requested_column(params.get("color"), context["columns"])
    color_values, color_title = _parallel_color_values(rows, color_column, context["numeric_columns"])
    trace = {
        "type": "parcoords",
        "dimensions": dimensions,
        "line": {
            "color": color_values,
            "colorscale": _colorscale(str(params.get("color_scale") or "viridis")),
            "showscale": _truthy(params.get("show_colorbar"), True),
            "colorbar": {"title": color_title},
        },
        "labelfont": {"size": _bounded_int(params.get("font_size"), 13, 8, 28), "color": "#07131f"},
        "tickfont": {"size": _bounded_int(params.get("tick_font_size"), 12, 6, 28), "color": str(params.get("tick_color") or "#324657")},
    }
    layout = _base_layout(title="Parallel coordinates", x_title="", y_title="", params=params)
    layout.pop("xaxis", None)
    layout.pop("yaxis", None)
    warnings = []
    if len(context["records"]) > max_rows:
        warnings.append(f"Showing first {max_rows} row profiles to keep the interactive render responsive.")
    if len(context["numeric_columns"]) > len(dimension_columns):
        warnings.append(f"Showing {len(dimension_columns)} numeric dimensions; refine the mapping to inspect others.")
    return {"data": [trace], "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _build_boxplot_spec(context: dict[str, Any]) -> dict[str, Any]:
    return _build_distribution_spec(context, trace_type="box")


def _build_grouped_dotplot_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    requested_y = _requested_column(params.get("y"), context["numeric_columns"])
    requested_group = _requested_column(params.get("group"), context["categorical_columns"])
    y_column = requested_y
    group_column = requested_group
    profile_groups = None
    if not (requested_y and requested_group):
        profile_groups = _single_row_profile_grouped_values(
            context,
            max_columns=_bounded_int(params.get("max_groups"), 20, 2, 80),
        )
    if profile_groups:
        profile, grouped, warnings = profile_groups
        y_column = "sample-like value"
        group_column = "inferred group"
    else:
        warnings = []
        y_column = y_column or _choose_column(None, context["numeric_columns"])
        group_column = group_column or _choose_column(None, context["categorical_columns"])
    if not y_column or not group_column:
        return _empty_plot_spec(
            "grouped_dotplot",
            "Grouped dot plot requires one numeric value column and one grouping column.",
            context["table_summary"],
        )

    if not profile_groups:
        grouped = []
        label_column = _choose_column(params.get("label"), context["columns"])
        for group_name, rows in _records_by_category(context["records"], group_column).items():
            values = []
            for row in rows:
                y_value = _number_or_none(row.get(y_column))
                if y_value is None:
                    continue
                label = str(row.get(label_column) or group_name) if label_column else group_name
                values.append((y_value, label))
            if values:
                grouped.append((group_name, values))
    if not grouped:
        return _empty_plot_spec("grouped_dotplot", "No grouped numeric values were available.", context["table_summary"])

    sort_groups = str(params.get("sort_groups") or "input")
    if sort_groups == "median_desc":
        grouped.sort(key=lambda item: median([value for value, _ in item[1]]), reverse=True)
    elif sort_groups == "median_asc":
        grouped.sort(key=lambda item: median([value for value, _ in item[1]]))
    elif sort_groups == "size_desc":
        grouped.sort(key=lambda item: len(item[1]), reverse=True)

    jitter = _bounded_float(params.get("point_jitter"), 0.32, 0, 0.8)
    point_size = _bounded_float(params.get("point_size"), 7, 1, 30)
    point_alpha = _bounded_float(params.get("point_alpha"), 0.78, 0.05, 1)
    summary_stat = str(params.get("summary_stat") or "mean")
    summary_width = _bounded_float(params.get("summary_width"), 0.56, 0.15, 0.95)
    summary_line_width = _bounded_float(params.get("summary_line_width"), 2.4, 0.5, 10)
    summary_color_mode = str(params.get("summary_line_color_mode") or "group")
    summary_custom_color = str(params.get("summary_line_color") or "#07131f")
    traces = []
    shapes = []
    annotations = []
    for group_index, (group_name, values) in enumerate(grouped):
        color = PLOTLY_PALETTE[group_index % len(PLOTLY_PALETTE)]
        y_values = [value for value, _ in values]
        x_values = [group_index + _deterministic_jitter(item_index, jitter) for item_index in range(len(values))]
        traces.append(
            {
                "type": "scattergl",
                "mode": "markers",
                "name": group_name,
                "x": x_values,
                "y": y_values,
                "text": [label for _, label in values],
                "marker": {
                    "color": color,
                    "size": point_size,
                    "opacity": point_alpha,
                    "line": {"color": "#ffffff", "width": 0.7},
                },
                "hovertemplate": "%{text}<br>group=%{fullData.name}<br>value=%{y:.4g}<extra></extra>",
            }
        )
        if summary_stat in {"mean", "median"}:
            summary_value = fmean(y_values) if summary_stat == "mean" else float(median(y_values))
            summary_color = color if summary_color_mode == "group" else summary_custom_color
            shapes.append(
                {
                    "type": "line",
                    "xref": "x",
                    "yref": "y",
                    "x0": group_index - summary_width / 2,
                    "x1": group_index + summary_width / 2,
                    "y0": summary_value,
                    "y1": summary_value,
                    "line": {"color": summary_color, "width": summary_line_width},
                }
            )
        if _truthy(params.get("show_n_labels"), True):
            annotations.append(
                {
                    "xref": "x",
                    "yref": "paper",
                    "x": group_index,
                    "y": 1.02,
                    "text": f"n={len(y_values)}",
                    "showarrow": False,
                    "font": {"size": 11, "color": "#617383"},
                }
            )

    title = f"Grouped dot profile: {profile['label']}" if profile_groups else f"Grouped dot plot: {y_column} by {group_column}"
    layout = _base_layout(title=title, x_title=group_column, y_title=y_column, params=params)
    layout["xaxis"]["tickmode"] = "array"
    layout["xaxis"]["tickvals"] = list(range(len(grouped)))
    layout["xaxis"]["ticktext"] = [group_name for group_name, _ in grouped]
    layout["xaxis"]["range"] = [-0.7, max(len(grouped) - 0.3, 0.7)]
    if shapes:
        layout.setdefault("shapes", []).extend(shapes)
    if annotations:
        layout.setdefault("annotations", []).extend(annotations)
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _build_raincloud_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    requested_y = _requested_column(params.get("y"), context["numeric_columns"])
    requested_group = _requested_column(params.get("group"), context["categorical_columns"])
    y_column = requested_y
    group_column = requested_group
    profile_groups = None
    if not (requested_y and requested_group):
        profile_groups = _single_row_profile_grouped_values(
            context,
            max_columns=_bounded_int(params.get("max_groups"), 20, 2, 80),
        )
    if profile_groups:
        profile, grouped, warnings = profile_groups
        y_column = "sample-like value"
        group_column = "inferred group"
    else:
        warnings = []
        y_column = y_column or _choose_column(None, context["numeric_columns"])
        group_column = group_column or _choose_column(None, context["categorical_columns"])
    if not y_column or not group_column:
        return _empty_plot_spec(
            "raincloud",
            "Raincloud requires one numeric value column and one grouping column.",
            context["table_summary"],
        )

    if not profile_groups:
        label_column = _choose_column(params.get("label"), context["columns"])
        grouped = []
        for group_name, rows in _records_by_category(context["records"], group_column).items():
            values = []
            for row in rows:
                y_value = _number_or_none(row.get(y_column))
                if y_value is None:
                    continue
                label = str(row.get(label_column) or group_name) if label_column else group_name
                values.append((y_value, label))
            if values:
                grouped.append((group_name, values))
    if not grouped:
        return _empty_plot_spec("raincloud", "No grouped numeric values were available for raincloud rendering.", context["table_summary"])

    sort_groups = str(params.get("sort_groups") or "input")
    if sort_groups == "median_desc":
        grouped.sort(key=lambda item: median([value for value, _ in item[1]]), reverse=True)
    elif sort_groups == "median_asc":
        grouped.sort(key=lambda item: median([value for value, _ in item[1]]))
    elif sort_groups == "size_desc":
        grouped.sort(key=lambda item: len(item[1]), reverse=True)
    max_groups = _bounded_int(params.get("max_groups"), 16, 2, 40)
    if len(grouped) > max_groups:
        warnings.append(f"Showing first {max_groups} groups to keep the raincloud readable.")
        grouped = grouped[:max_groups]

    violin_side = str(params.get("violin_side") or "negative")
    if violin_side not in {"negative", "positive"}:
        violin_side = "negative"
    point_offset = 0.22 if violin_side == "negative" else -0.22
    box_offset = _bounded_float(params.get("box_offset"), 0.18, -0.5, 0.5)
    jitter = _bounded_float(params.get("point_jitter"), 0.22, 0, 0.8)
    point_size = _bounded_float(params.get("point_size"), 5, 1, 24)
    point_alpha = _bounded_float(params.get("point_alpha"), 0.68, 0.05, 1)
    traces = []
    for group_index, (group_name, values_with_labels) in enumerate(grouped):
        y_values = [value for value, _ in values_with_labels]
        labels = [label for _, label in values_with_labels]
        color = PLOTLY_PALETTE[group_index % len(PLOTLY_PALETTE)]
        traces.append(
            {
                "type": "violin",
                "name": f"{group_name} density",
                "x": [group_index for _ in y_values],
                "y": y_values,
                "side": violin_side,
                "width": _bounded_float(params.get("violin_width"), 0.72, 0.15, 1.4),
                "points": False,
                "box": {"visible": False},
                "meanline": {"visible": False},
                "scalemode": "width",
                "fillcolor": _rgba_from_hex(color, 0.34),
                "line": {"color": color, "width": 1.2},
                "hovertemplate": f"{group_name}<br>{y_column}=%{{y:.4g}}<extra>density</extra>",
                "showlegend": False,
            }
        )
        if _truthy(params.get("show_box"), True):
            traces.append(
                {
                    "type": "box",
                    "name": f"{group_name} box",
                    "x": [group_index + box_offset for _ in y_values],
                    "y": y_values,
                    "width": _bounded_float(params.get("box_width"), 0.24, 0.08, 0.6),
                    "boxpoints": False,
                    "marker": {"color": color, "opacity": 0.1},
                    "fillcolor": _rgba_from_hex(color, 0.14),
                    "line": {"color": color, "width": 1.4},
                    "hovertemplate": f"{group_name}<br>{y_column}=%{{y:.4g}}<extra>box</extra>",
                    "showlegend": False,
                }
            )
        if _truthy(params.get("show_points"), True):
            point_x = [
                group_index + point_offset + _deterministic_jitter(item_index, jitter)
                for item_index in range(len(y_values))
            ]
            traces.append(
                {
                    "type": "scattergl",
                    "mode": "markers",
                    "name": group_name,
                    "x": point_x,
                    "y": y_values,
                    "text": labels,
                    "marker": {
                        "color": color,
                        "size": point_size,
                        "opacity": point_alpha,
                        "line": {"color": "#ffffff", "width": 0.6},
                    },
                    "hovertemplate": "%{text}<br>group=%{fullData.name}<br>value=%{y:.4g}<extra></extra>",
                }
            )
        if _truthy(params.get("show_mean"), True):
            traces.append(
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": f"{group_name} mean",
                    "x": [group_index + box_offset],
                    "y": [fmean(y_values)],
                    "marker": {
                        "symbol": "diamond",
                        "size": _bounded_float(params.get("mean_marker_size"), 9, 2, 28),
                        "color": "#ffffff",
                        "line": {"color": color, "width": 1.8},
                    },
                    "hovertemplate": f"{group_name}<br>mean=%{{y:.4g}}<extra></extra>",
                    "showlegend": False,
                }
            )

    title = f"Raincloud profile: {profile['label']}" if profile_groups else f"Raincloud: {y_column} by {group_column}"
    layout = _base_layout(title=title, x_title=group_column, y_title=y_column, params=params)
    layout["xaxis"]["tickmode"] = "array"
    layout["xaxis"]["tickvals"] = list(range(len(grouped)))
    layout["xaxis"]["ticktext"] = [group_name for group_name, _ in grouped]
    layout["xaxis"]["range"] = [-0.85, max(len(grouped) - 0.15, 0.85)]
    layout["violingap"] = 0
    layout["boxmode"] = "overlay"
    layout["meta"] = {"raincloud": {"groups": len(grouped), "violin_side": violin_side, "show_box": _truthy(params.get("show_box"), True)}}
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _build_violin_spec(context: dict[str, Any]) -> dict[str, Any]:
    return _build_distribution_spec(context, trace_type="violin")


def _build_ridgeline_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    x_column = _choose_column(params.get("x"), context["numeric_columns"])
    group_column = _choose_column(params.get("group"), context["categorical_columns"])
    if not x_column or not group_column:
        return _empty_plot_spec("ridgeline", "Ridgeline requires one numeric value column and one grouping column.", context["table_summary"])

    grouped = []
    for group_name, rows in _records_by_category(context["records"], group_column).items():
        values = [_number_or_none(row.get(x_column)) for row in rows]
        values = [value for value in values if value is not None]
        if values:
            grouped.append((group_name, values))
    if not grouped:
        return _empty_plot_spec("ridgeline", "No numeric grouped values were available for ridgeline rendering.", context["table_summary"])

    sort_groups = str(params.get("sort_groups") or "input")
    if sort_groups == "median_desc":
        grouped.sort(key=lambda item: median(item[1]), reverse=True)
    elif sort_groups == "median_asc":
        grouped.sort(key=lambda item: median(item[1]))
    elif sort_groups == "size_desc":
        grouped.sort(key=lambda item: len(item[1]), reverse=True)

    max_groups = _bounded_int(params.get("max_groups"), 12, 2, 40)
    warnings = []
    if len(grouped) > max_groups:
        warnings.append(f"Showing first {max_groups} groups to keep the ridgeline readable.")
        grouped = grouped[:max_groups]

    all_values = [value for _, values in grouped for value in values]
    x_min = min(all_values)
    x_max = max(all_values)
    span = max(x_max - x_min, 1e-9)
    padding = span * 0.08
    x_grid = _linspace(x_min - padding, x_max + padding, _bounded_int(params.get("density_points"), 90, 30, 300))
    ridge_height = _bounded_float(params.get("ridge_height"), 0.86, 0.1, 2.5)
    overlap = _bounded_float(params.get("overlap"), 0.55, 0, 1.5)
    step = max(0.18, ridge_height * max(0.12, 1 - min(overlap, 0.95)))
    fill_alpha = _bounded_float(params.get("fill_alpha"), 0.52, 0.05, 1)
    line_width = _bounded_float(params.get("line_width"), 1.8, 0.2, 8)
    traces = []
    tick_values = []
    tick_text = []
    label_column = _choose_column(params.get("label"), context["columns"])

    for index, (group_name, values) in enumerate(grouped):
        offset = index * step
        tick_values.append(offset)
        tick_text.append(group_name)
        color = PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)]
        density_values = _kernel_density(values, x_grid, params.get("bandwidth"))
        max_density = max(density_values) if density_values else 0
        scaled = [offset + (value / max_density * ridge_height if max_density > 0 else 0) for value in density_values]
        traces.append(
            {
                "type": "scatter",
                "mode": "lines",
                "name": group_name,
                "x": [*x_grid, *reversed(x_grid)],
                "y": [*scaled, *([offset] * len(x_grid))],
                "fill": "toself",
                "fillcolor": _rgba_from_hex(color, fill_alpha),
                "line": {"color": color, "width": line_width},
                "hovertemplate": f"{group_name}<br>{x_column}=%{{x:.4g}}<extra></extra>",
            }
        )
        if _truthy(params.get("show_points"), True):
            point_text = []
            for row in context["records"]:
                if str(row.get(group_column) or "All") == group_name and _number_or_none(row.get(x_column)) is not None:
                    point_text.append(str(row.get(label_column) or group_name) if label_column else group_name)
            traces.append(
                {
                    "type": "scattergl",
                    "mode": "markers",
                    "name": f"{group_name} points",
                    "x": values,
                    "y": [offset - ridge_height * 0.08 + ((item % 5) - 2) * ridge_height * 0.012 for item in range(len(values))],
                    "text": point_text[: len(values)],
                    "marker": {
                        "color": color,
                        "size": _bounded_float(params.get("point_size"), 4, 1, 16),
                        "opacity": _bounded_float(params.get("point_alpha"), 0.45, 0.05, 1),
                    },
                    "hovertemplate": "%{text}<br>value=%{x:.4g}<extra></extra>",
                    "showlegend": False,
                }
            )

    layout = _base_layout(title=f"Ridgeline: {x_column} by {group_column}", x_title=x_column, y_title=group_column, params=params)
    layout["yaxis"]["tickmode"] = "array"
    layout["yaxis"]["tickvals"] = tick_values
    layout["yaxis"]["ticktext"] = tick_text
    layout["yaxis"]["range"] = [-ridge_height * 0.22, tick_values[-1] + ridge_height * 1.18]
    layout["hovermode"] = str(params.get("hover_mode") or "closest")
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _build_distribution_spec(context: dict[str, Any], *, trace_type: str) -> dict[str, Any]:
    params = context["params"]
    requested_y = _requested_column(params.get("y"), context["numeric_columns"])
    requested_group = _requested_column(params.get("group"), context["categorical_columns"])
    y_column = requested_y
    group_column = requested_group
    traces = []
    warnings = []
    grouped_values: list[tuple[str, list[float]]] = []
    profile_groups = None
    if not (requested_y and requested_group):
        profile_groups = _single_row_profile_grouped_values(
            context,
            max_columns=_bounded_int(params.get("max_groups"), 20, 2, 80),
        )
    if profile_groups:
        profile, grouped_profile_values, profile_warnings = profile_groups
        warnings.extend(profile_warnings)
        for index, (group_name, values_with_labels) in enumerate(grouped_profile_values):
            values = [value for value, _ in values_with_labels]
            labels = [label for _, label in values_with_labels]
            grouped_values.append((group_name, values))
            trace = _distribution_trace(
                trace_type,
                name=group_name,
                values=values,
                color=PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)],
                params=params,
            )
            trace["customdata"] = labels
            trace["hovertemplate"] = f"{group_name}<br>sample=%{{customdata}}<br>value=%{{y:.4g}}<extra></extra>"
            traces.append(trace)
        x_title = "inferred group"
        y_title = "sample-like value"
        title = f"{'Boxplot' if trace_type == 'box' else 'Violin'} profile: {profile['label']}"
    else:
        y_column = y_column or _choose_column(None, context["numeric_columns"])
        group_column = group_column or _choose_column(None, context["categorical_columns"])
        if y_column and group_column:
            grouped = _records_by_category(context["records"], group_column)
            for index, (group_name, rows) in enumerate(grouped.items()):
                values = [_number_or_none(row.get(y_column)) for row in rows]
                values = [value for value in values if value is not None]
                if not values:
                    continue
                grouped_values.append((group_name, values))
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
            title = f"{'Boxplot' if trace_type == 'box' else 'Violin'} distribution"
        else:
            max_groups = _bounded_int(params.get("max_groups"), 12, 2, 40)
            for index, column in enumerate(context["numeric_columns"][:max_groups]):
                values = [_number_or_none(row.get(column)) for row in context["records"]]
                values = [value for value in values if value is not None]
                if not values:
                    continue
                grouped_values.append((column, values))
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
            title = f"{'Boxplot' if trace_type == 'box' else 'Violin'} distribution"

    if not traces:
        return _empty_plot_spec(trace_type, "No numeric values were available for distribution plotting.", context["table_summary"])

    layout = _base_layout(
        title=title,
        x_title=x_title,
        y_title=y_title,
        params=params,
    )
    layout["boxmode"] = "group"
    layout["violingap"] = 0.18
    if _truthy(params.get("show_n_labels"), True):
        layout.setdefault("annotations", []).extend(_distribution_n_annotations(grouped_values, params))
        if str(params.get("n_label_position") or "top") == "bottom":
            layout["margin"]["b"] = max(layout["margin"]["b"], 84)
        else:
            layout["margin"]["t"] = max(layout["margin"]["t"], 88)
    if trace_type == "box" and _truthy(params.get("show_p_values"), False):
        comparison_result = _pairwise_comparison_overlays(grouped_values, params)
        layout.setdefault("shapes", []).extend(comparison_result["shapes"])
        layout.setdefault("annotations", []).extend(comparison_result["annotations"])
        if comparison_result["y_range"]:
            layout["yaxis"]["range"] = comparison_result["y_range"]
        warnings.extend(comparison_result["warnings"])
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _distribution_n_annotations(grouped_values: list[tuple[str, list[float]]], params: dict[str, Any]) -> list[dict[str, Any]]:
    position = str(params.get("n_label_position") or "top")
    is_bottom = position == "bottom"
    font_size = _bounded_int(params.get("n_label_font_size"), 11, 8, 22)
    font_color = str(params.get("n_label_color") or "#617383")
    annotations = []
    for group_name, values in grouped_values:
        annotations.append(
            {
                "xref": "x",
                "yref": "paper",
                "x": group_name,
                "y": -0.14 if is_bottom else 1.02,
                "text": f"n={len(values)}",
                "showarrow": False,
                "yanchor": "top" if is_bottom else "bottom",
                "font": {"size": font_size, "color": font_color},
            }
        )
    return annotations


def _build_bar_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    profile = _single_row_matrix_profile(context, max_columns=_bounded_int(params.get("max_groups"), 20, 2, 80))
    profile_group_lookup: dict[str, str] = {}
    profile_group_colors: dict[str, str] = {}
    requested_category = _requested_column(params.get("category"), context["categorical_columns"])
    requested_value = _requested_column(params.get("value"), context["numeric_columns"])
    if profile and not (requested_category and requested_value):
        category_column = None
        value_column = None
    else:
        category_column = requested_category or _choose_column(None, context["categorical_columns"])
        value_column = requested_value or _choose_column(None, context["numeric_columns"])
    aggregation = str(params.get("aggregation") or "mean")
    warnings = []
    if category_column and value_column:
        grouped = _records_by_category(context["records"], category_column)
        labels = []
        values = []
        errors = []
        grouped_values = []
        raw_point_x = []
        raw_point_y = []
        raw_point_text = []
        for group_name, rows in grouped.items():
            group_values = [_number_or_none(row.get(value_column)) for row in rows]
            group_values = [value for value in group_values if value is not None]
            if not group_values:
                continue
            labels.append(group_name)
            values.append(_aggregate_values(group_values, aggregation))
            errors.append(_error_bar_value(group_values, str(params.get("error_bar") or "sem")))
            grouped_values.append((group_name, group_values))
            for index, value in enumerate(group_values):
                raw_point_x.append(group_name)
                raw_point_y.append(value)
                raw_point_text.append(f"{group_name} #{index + 1}")
        labels, values, errors, grouped_values = _sort_bar_values(
            labels,
            values,
            errors,
            str(params.get("sort") or "input"),
            grouped_values=grouped_values,
        )
        x_title = category_column
        y_title = f"{aggregation} {value_column}"
        title = f"Bar: {value_column} by {category_column}"
    else:
        max_groups = _bounded_int(params.get("max_groups"), 20, 2, 80)
        labels = profile["columns"] if profile else context["numeric_columns"][:max_groups]
        values = []
        errors = []
        grouped_values = []
        for column in labels:
            column_values = [_number_or_none(row.get(column)) for row in context["records"]]
            column_values = [value for value in column_values if value is not None]
            values.append(_aggregate_values(column_values, aggregation) if column_values else 0)
            errors.append(_error_bar_value(column_values, str(params.get("error_bar") or "sem")))
            grouped_values.append((column, column_values))
        if len(context["numeric_columns"]) > max_groups:
            warnings.append(f"Showing first {max_groups} numeric columns to keep the chart readable.")
        if profile and profile["excluded_columns"]:
            warnings.append(
                "Skipped numeric metadata columns for this single-row profile: "
                + ", ".join(profile["excluded_columns"][:6])
            )
        raw_point_x = []
        raw_point_y = []
        raw_point_text = []
        labels, values, errors, grouped_values = _sort_bar_values(
            labels,
            values,
            errors,
            str(params.get("sort") or "input"),
            grouped_values=grouped_values,
        )
        if profile:
            x_title = "sample-like columns"
            y_title = "value"
            title = f"Bar profile: {profile['label']}"
            profile_group_lookup = _profile_group_lookup(labels)
            profile_group_colors = {
                group: PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)]
                for index, group in enumerate(dict.fromkeys(profile_group_lookup.values()))
            }
        else:
            x_title = "numeric columns"
            y_title = aggregation
            title = "Bar summary by numeric column"

    marker_color: str | list[str] = PLOTLY_PALETTE[0]
    customdata = None
    if profile_group_lookup:
        groups = [profile_group_lookup.get(label, "Profile") for label in labels]
        marker_color = [profile_group_colors[group] for group in groups]
        customdata = [[group] for group in groups]

    trace = {
        "type": "bar",
        "x": labels,
        "y": values,
        "width": _bounded_float(params.get("bar_width"), 0.72, 0.1, 1.0),
        "marker": {"color": marker_color, "line": {"color": "#0a4f52", "width": 1}},
        "error_y": {
            "type": "data",
            "array": errors,
            "visible": any(value > 0 for value in errors),
            "thickness": 1.6,
            "width": _bounded_float(params.get("error_cap_width"), 8, 0, 32),
        },
        "hovertemplate": "%{x}<br>value=%{y:.4g}<extra></extra>",
    }
    if customdata:
        trace["customdata"] = customdata
        trace["hovertemplate"] = "%{x}<br>group=%{customdata[0]}<br>value=%{y:.4g}<extra></extra>"
    if _truthy(params.get("show_values"), False):
        precision = _bounded_int(params.get("value_precision"), 2, 0, 6)
        trace["text"] = [f"{value:.{precision}f}" for value in values]
        trace["textposition"] = "outside"
        trace["cliponaxis"] = False
    data = [trace]
    if category_column and value_column and bool(params.get("show_points", True)) and raw_point_x:
        data.append(
            {
                "type": "scatter",
                "mode": "markers",
                "name": "Raw values",
                "x": raw_point_x,
                "y": raw_point_y,
                "text": raw_point_text,
                "marker": {
                    "size": 7,
                    "opacity": _bounded_float(params.get("point_alpha"), 0.68, 0.05, 1),
                    "color": "#07131f",
                    "line": {"color": "#ffffff", "width": 0.6},
                },
                "hovertemplate": "%{text}<br>value=%{y:.4g}<extra></extra>",
            }
        )
    if str(params.get("orientation") or "vertical") == "horizontal":
        trace["orientation"] = "h"
        trace["x"], trace["y"] = trace["y"], trace["x"]
        trace["error_x"] = trace.pop("error_y")
        if _truthy(params.get("show_values"), False):
            trace["textposition"] = "outside"
        x_title, y_title = y_title, x_title
        if len(data) > 1:
            point_trace = data[1]
            point_trace["x"], point_trace["y"] = point_trace["y"], point_trace["x"]

    layout = _base_layout(title=title, x_title=x_title, y_title=y_title, params=params)
    layout["bargap"] = 0.28
    if profile_group_colors and len(profile_group_colors) > 1:
        for group, color in profile_group_colors.items():
            data.append(
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": group,
                    "x": [None],
                    "y": [None],
                    "marker": {"color": color, "size": 9},
                    "hoverinfo": "skip",
                    "showlegend": True,
                }
            )
        layout.setdefault("legend", {})["title"] = {"text": "Inferred group"}
        if len(labels) > 8:
            layout["xaxis"]["tickangle"] = -35
    if _truthy(params.get("show_p_values"), False):
        if str(params.get("orientation") or "vertical") == "horizontal":
            warnings.append("Pairwise p-value brackets are currently available for vertical bar charts.")
        else:
            comparison_result = _pairwise_comparison_overlays(grouped_values, params)
            layout.setdefault("shapes", []).extend(comparison_result["shapes"])
            layout.setdefault("annotations", []).extend(comparison_result["annotations"])
            if comparison_result["y_range"]:
                layout["yaxis"]["range"] = comparison_result["y_range"]
            warnings.extend(comparison_result["warnings"])
    return {"data": data, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


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
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": []}


def _build_histogram_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    profile = _single_row_matrix_profile(context, max_columns=200)
    requested_x = _requested_column(params.get("x"), context["numeric_columns"])
    if profile and (requested_x is None or requested_x in profile["columns"]):
        values = []
        labels = []
        row = context["records"][0]
        for column in profile["columns"]:
            value = _number_or_none(row.get(column))
            if value is None:
                continue
            values.append(value)
            labels.append(column)
        if not values:
            return _empty_plot_spec(
                "histogram",
                "No sample-like values were available for histogram rendering.",
                context["table_summary"],
            )
        bins = _bounded_int(params.get("bins"), min(20, max(5, len(values))), 5, 200)
        histnorm = str(params.get("histnorm") or "count")
        opacity = _bounded_float(params.get("opacity"), 0.72, 0.1, 1)
        bar_line_color = str(params.get("bar_line_color") or "#ffffff")
        bar_line_width = _bounded_float(params.get("bar_line_width"), 0.5, 0, 4)
        group_lookup = _profile_group_lookup(labels)
        grouped_profile_values: dict[str, dict[str, list[Any]]] = {}
        for label, value in zip(labels, values, strict=False):
            group = group_lookup.get(label, "Profile")
            group_bucket = grouped_profile_values.setdefault(group, {"values": [], "labels": []})
            group_bucket["values"].append(value)
            group_bucket["labels"].append(label)
        multiple_groups = len(grouped_profile_values) > 1
        traces = []
        shapes = []
        annotations = []
        reference_line_width = _bounded_float(params.get("reference_line_width"), 1.7, 0.5, 6)
        for index, (group, bucket) in enumerate(grouped_profile_values.items()):
            color = PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)]
            group_values = [float(value) for value in bucket["values"]]
            traces.append(
                {
                    "type": "histogram",
                    "name": group if multiple_groups else profile["label"],
                    "x": group_values,
                    "customdata": bucket["labels"],
                    "nbinsx": bins,
                    "histnorm": "" if histnorm == "count" else histnorm,
                    "opacity": opacity if not multiple_groups else min(opacity, 0.64),
                    "marker": {
                        "color": color,
                        "line": {"color": bar_line_color, "width": bar_line_width},
                    },
                    "cumulative": {"enabled": _truthy(params.get("cumulative"), False)},
                    "hovertemplate": (
                        "value=%{x:.4g}<br>sample=%{customdata}"
                        + ("<extra>%{fullData.name}</extra>" if multiple_groups else "<extra></extra>")
                    ),
                }
            )
            if _truthy(params.get("show_rug"), False):
                traces.append(
                    {
                        "type": "scattergl",
                        "mode": "markers",
                        "name": f"{group} rug",
                        "x": group_values,
                        "y": [0 for _ in group_values],
                        "text": bucket["labels"],
                        "marker": {"symbol": "line-ns-open", "size": 10, "color": color, "opacity": 0.72},
                        "hovertemplate": "%{text}<br>value=%{x:.4g}<extra>rug</extra>",
                        "showlegend": False,
                    }
                )
            if _truthy(params.get("show_mean"), True):
                mean_value = fmean(group_values)
                shapes.append(_x_reference_line(mean_value, color, dash="dash", width=reference_line_width))
                annotations.append(_x_reference_annotation(mean_value, f"{group} mean" if multiple_groups else "mean", color))
            if _truthy(params.get("show_median"), False):
                median_value = float(median(group_values))
                shapes.append(_x_reference_line(median_value, color, dash="dot", width=reference_line_width))
                annotations.append(_x_reference_annotation(median_value, f"{group} median" if multiple_groups else "median", color))
        layout = _base_layout(
            title=f"Histogram profile: {profile['label']}",
            x_title="sample-like value",
            y_title="count" if histnorm == "count" else histnorm,
            params=params,
        )
        layout["barmode"] = str(params.get("barmode") or "overlay")
        if multiple_groups:
            layout.setdefault("legend", {})["title"] = {"text": "Inferred group"}
        if shapes:
            layout.setdefault("shapes", []).extend(shapes)
            layout.setdefault("annotations", []).extend(annotations)
        warnings = []
        if profile["excluded_columns"]:
            warnings.append(
                "Skipped numeric metadata columns for this single-row profile: "
                + ", ".join(profile["excluded_columns"][:6])
            )
        return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}

    x_column = _choose_column(params.get("x"), context["numeric_columns"])
    if not x_column:
        return _empty_plot_spec("histogram", "Histogram requires at least one numeric column.", context["table_summary"])

    color_column = _choose_column(params.get("color"), context["categorical_columns"])
    grouped = _records_by_category(context["records"], color_column) if color_column else {"All": context["records"]}
    bins = _bounded_int(params.get("bins"), 30, 5, 200)
    histnorm = str(params.get("histnorm") or "count")
    opacity = _bounded_float(params.get("opacity"), 0.68, 0.1, 1)
    bar_line_width = _bounded_float(params.get("bar_line_width"), 0.5, 0, 4)
    bar_line_color = str(params.get("bar_line_color") or "#ffffff")
    reference_line_width = _bounded_float(params.get("reference_line_width"), 1.7, 0.5, 6)
    reference_line_color_mode = str(params.get("reference_line_color_mode") or "group")
    reference_line_color = str(params.get("reference_line_color") or "#324657")
    traces = []
    reference_shapes = []
    reference_annotations = []
    for index, (group_name, rows) in enumerate(grouped.items()):
        values = [_number_or_none(row.get(x_column)) for row in rows]
        values = [value for value in values if value is not None]
        if not values:
            continue
        color = PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)]
        traces.append(
            {
                "type": "histogram",
                "name": group_name,
                "x": values,
                "nbinsx": bins,
                "histnorm": "" if histnorm == "count" else histnorm,
                "opacity": opacity,
                "marker": {"color": color, "line": {"color": bar_line_color, "width": bar_line_width}},
                "cumulative": {"enabled": _truthy(params.get("cumulative"), False)},
                "hovertemplate": "%{x}<br>count=%{y}<extra>%{fullData.name}</extra>",
            }
        )
        if _truthy(params.get("show_rug"), False):
            traces.append(
                {
                    "type": "scattergl",
                    "mode": "markers",
                    "name": f"{group_name} rug",
                    "x": values,
                    "y": [0 for _ in values],
                    "marker": {"symbol": "line-ns-open", "size": 10, "color": color, "opacity": 0.72},
                    "hovertemplate": "%{x:.4g}<extra>%{fullData.name}</extra>",
                    "showlegend": False,
                }
            )
        reference_specs = []
        if _truthy(params.get("show_mean"), True):
            reference_specs.append(("mean", fmean(values), "dash"))
        if _truthy(params.get("show_median"), False):
            reference_specs.append(("median", float(median(values)), "dot"))
        for label, x_value, dash in reference_specs:
            line_color = color if reference_line_color_mode == "group" else reference_line_color
            reference_shapes.append(_x_reference_line(x_value, line_color, dash=dash, width=reference_line_width))
            reference_annotations.append(_x_reference_annotation(x_value, f"{group_name} {label}", line_color))
    if not traces:
        return _empty_plot_spec("histogram", "No numeric values were available for histogram rendering.", context["table_summary"])

    layout = _base_layout(
        title=f"Histogram: {x_column}",
        x_title=x_column,
        y_title="count" if histnorm == "count" else histnorm,
        params=params,
    )
    layout["barmode"] = str(params.get("barmode") or "overlay")
    if reference_shapes:
        layout.setdefault("shapes", []).extend(reference_shapes)
        layout.setdefault("annotations", []).extend(reference_annotations)
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": []}


def _build_density_curve_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    x_column = _choose_column(params.get("x"), context["numeric_columns"])
    if not x_column:
        return _empty_plot_spec("density_curve", "Density curve requires at least one numeric value column.", context["table_summary"])

    group_column = _choose_column(params.get("group"), context["categorical_columns"])
    grouped = _records_by_category(context["records"], group_column) if group_column else {"All": context["records"]}
    grouped_values: list[tuple[str, list[float], list[str]]] = []
    label_column = _choose_column(params.get("label"), context["columns"])
    for group_name, rows in grouped.items():
        values = []
        labels = []
        for row in rows:
            value = _number_or_none(row.get(x_column))
            if value is None:
                continue
            values.append(value)
            labels.append(str(row.get(label_column) or group_name) if label_column else group_name)
        if values:
            grouped_values.append((group_name, sorted(values), labels))
    if not grouped_values:
        return _empty_plot_spec("density_curve", "No numeric values were available for density curve rendering.", context["table_summary"])

    sort_groups = str(params.get("sort_groups") or "input")
    if sort_groups == "median_desc":
        grouped_values.sort(key=lambda item: median(item[1]), reverse=True)
    elif sort_groups == "median_asc":
        grouped_values.sort(key=lambda item: median(item[1]))
    elif sort_groups == "size_desc":
        grouped_values.sort(key=lambda item: len(item[1]), reverse=True)

    max_groups = _bounded_int(params.get("max_groups"), 12, 1, 40)
    warnings = []
    if len(grouped_values) > max_groups:
        warnings.append(f"Showing first {max_groups} groups to keep the density curve readable.")
        grouped_values = grouped_values[:max_groups]

    all_values = [value for _, values, _ in grouped_values for value in values]
    x_min = min(all_values)
    x_max = max(all_values)
    span = max(x_max - x_min, 1e-9)
    x_grid = _linspace(x_min - span * 0.08, x_max + span * 0.08, _bounded_int(params.get("density_points"), 160, 30, 500))
    traces = []
    shapes = []
    annotations = []
    line_width = _bounded_float(params.get("line_width"), 2.4, 0.5, 10)
    fill = _truthy(params.get("fill"), True)
    normalize = str(params.get("normalize") or "area")
    for index, (group_name, values, labels) in enumerate(grouped_values):
        color = PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)]
        density_values = _kernel_density(values, x_grid, params.get("bandwidth"))
        if normalize == "peak":
            peak = max(density_values) if density_values else 0.0
            density_values = [value / peak if peak > 0 else 0.0 for value in density_values]
        traces.append(
            {
                "type": "scatter",
                "mode": "lines",
                "name": group_name,
                "x": x_grid,
                "y": density_values,
                "fill": "tozeroy" if fill else "none",
                "fillcolor": _rgba_from_hex(color, _bounded_float(params.get("fill_alpha"), 0.24, 0.02, 1)),
                "line": {"color": color, "width": line_width, "shape": "spline"},
                "hovertemplate": f"{x_column}=%{{x:.4g}}<br>density=%{{y:.4g}}<extra>{group_name}</extra>",
            }
        )
        if _truthy(params.get("show_rug"), True):
            traces.append(
                {
                    "type": "scattergl",
                    "mode": "markers",
                    "name": f"{group_name} rug",
                    "x": values,
                    "y": [0 for _ in values],
                    "text": labels[: len(values)],
                    "marker": {
                        "symbol": "line-ns-open",
                        "size": _bounded_float(params.get("rug_size"), 8, 2, 20),
                        "color": color,
                        "opacity": _bounded_float(params.get("rug_alpha"), 0.42, 0.05, 1),
                    },
                    "hovertemplate": "%{text}<br>value=%{x:.4g}<extra></extra>",
                    "showlegend": False,
                }
            )
        if _truthy(params.get("show_median"), True):
            median_value = float(median(values))
            shapes.append(
                {
                    "type": "line",
                    "xref": "x",
                    "yref": "paper",
                    "x0": median_value,
                    "x1": median_value,
                    "y0": 0,
                    "y1": 1,
                    "line": {"color": color, "width": 1.2, "dash": str(params.get("median_line_dash") or "dot")},
                }
            )
            annotations.append(
                {
                    "xref": "x",
                    "yref": "paper",
                    "x": median_value,
                    "y": 1.01,
                    "text": f"{group_name} median",
                    "showarrow": False,
                    "textangle": -90,
                    "font": {"size": 10, "color": color},
                    "xanchor": "left",
                    "yanchor": "bottom",
                }
            )

    y_title = "density" if normalize == "area" else "relative density"
    layout = _base_layout(title=f"Density curve: {x_column}", x_title=x_column, y_title=y_title, params=params)
    if shapes:
        layout.setdefault("shapes", []).extend(shapes)
        layout.setdefault("annotations", []).extend(annotations)
    layout["meta"] = {"density_curve": {"groups": len(grouped_values), "normalize": normalize, "fill": fill}}
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _build_ecdf_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    x_column = _choose_column(params.get("x"), context["numeric_columns"])
    if not x_column:
        return _empty_plot_spec("ecdf", "ECDF requires at least one numeric value column.", context["table_summary"])

    group_column = _choose_column(params.get("group"), context["categorical_columns"])
    grouped = _records_by_category(context["records"], group_column) if group_column else {"All": context["records"]}
    grouped_values: list[tuple[str, list[float]]] = []
    for group_name, rows in grouped.items():
        values = [_number_or_none(row.get(x_column)) for row in rows]
        values = sorted(value for value in values if value is not None)
        if values:
            grouped_values.append((group_name, values))
    if not grouped_values:
        return _empty_plot_spec("ecdf", "No numeric values were available for ECDF rendering.", context["table_summary"])

    sort_groups = str(params.get("sort_groups") or "input")
    if sort_groups == "median_desc":
        grouped_values.sort(key=lambda item: median(item[1]), reverse=True)
    elif sort_groups == "median_asc":
        grouped_values.sort(key=lambda item: median(item[1]))
    elif sort_groups == "size_desc":
        grouped_values.sort(key=lambda item: len(item[1]), reverse=True)

    max_groups = _bounded_int(params.get("max_groups"), 12, 1, 40)
    warnings = []
    if len(grouped_values) > max_groups:
        warnings.append(f"Showing first {max_groups} groups to keep the ECDF readable.")
        grouped_values = grouped_values[:max_groups]

    y_mode = str(params.get("y_mode") or "cumulative")
    y_units = str(params.get("y_units") or "percent")
    multiplier = 100.0 if y_units == "percent" else 1.0
    line_shape = str(params.get("line_shape") or "hv")
    if line_shape not in {"hv", "linear"}:
        line_shape = "hv"
    show_points = _truthy(params.get("show_points"), False)
    traces = []
    shapes = []
    annotations = []
    for index, (group_name, values) in enumerate(grouped_values):
        count = len(values)
        y_values = []
        for item_index in range(count):
            fraction = (item_index + 1) / count
            if y_mode == "survival":
                fraction = 1 - item_index / count
            y_values.append(fraction * multiplier)
        color = PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)]
        traces.append(
            {
                "type": "scatter",
                "mode": "lines+markers" if show_points else "lines",
                "name": group_name,
                "x": values,
                "y": y_values,
                "line": {
                    "color": color,
                    "width": _bounded_float(params.get("line_width"), 2.4, 0.5, 10),
                    "shape": line_shape,
                },
                "marker": {
                    "color": color,
                    "size": _bounded_float(params.get("point_size"), 5, 1, 20),
                    "opacity": _bounded_float(params.get("point_alpha"), 0.62, 0.05, 1),
                },
                "customdata": [[count] for _ in values],
                "hovertemplate": f"{x_column}=%{{x:.4g}}<br>{y_mode}=%{{y:.4g}}<br>n=%{{customdata[0]}}<extra>{group_name}</extra>",
            }
        )
        if _truthy(params.get("show_median"), True):
            median_value = float(median(values))
            shapes.append(
                {
                    "type": "line",
                    "xref": "x",
                    "yref": "paper",
                    "x0": median_value,
                    "x1": median_value,
                    "y0": 0,
                    "y1": 1,
                    "line": {
                        "color": color,
                        "width": 1.2,
                        "dash": str(params.get("median_line_dash") or "dot"),
                    },
                }
            )
            annotations.append(
                {
                    "xref": "x",
                    "yref": "paper",
                    "x": median_value,
                    "y": 1.01,
                    "text": f"{group_name} median",
                    "showarrow": False,
                    "textangle": -90,
                    "font": {"size": 10, "color": color},
                    "xanchor": "left",
                    "yanchor": "bottom",
                }
            )

    y_title = "cumulative percent" if y_units == "percent" else "cumulative proportion"
    if y_mode == "survival":
        y_title = "survival percent" if y_units == "percent" else "survival proportion"
    layout = _base_layout(title=f"ECDF: {x_column}", x_title=x_column, y_title=y_title, params=params)
    layout["yaxis"]["range"] = [-2 if y_units == "percent" else -0.02, 102 if y_units == "percent" else 1.02]
    if shapes:
        layout.setdefault("shapes", []).extend(shapes)
        layout.setdefault("annotations", []).extend(annotations)
    layout["meta"] = {"ecdf": {"groups": len(grouped_values), "mode": y_mode, "units": y_units}}
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _build_calendar_heatmap_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    columns = context["columns"]
    date_column = _requested_column(params.get("date_column"), columns) or _find_column(
        columns, ["date", "day", "time", "sample_date", "collection_date", "sampling_date"]
    )
    value_column = _requested_column(params.get("value_column"), context["numeric_columns"]) or _find_column(
        context["numeric_columns"], ["count", "counts", "value", "score", "abundance", "intensity"]
    )
    if not date_column:
        return _empty_plot_spec("calendar_heatmap", "Calendar heatmap requires a date column.", context["table_summary"])

    aggregation = str(params.get("aggregation") or "sum")
    if aggregation != "count" and not value_column:
        return _empty_plot_spec("calendar_heatmap", "Calendar heatmap requires a numeric value column unless aggregation=count.", context["table_summary"])

    by_day: dict[date, list[float]] = {}
    skipped_dates = 0
    skipped_values = 0
    for row in context["records"]:
        parsed_date = _parse_calendar_date(row.get(date_column))
        if parsed_date is None:
            skipped_dates += 1
            continue
        value = 1.0 if aggregation == "count" else _number_or_none(row.get(value_column))
        if value is None:
            skipped_values += 1
            continue
        by_day.setdefault(parsed_date, []).append(value)
    if not by_day:
        return _empty_plot_spec("calendar_heatmap", "No valid date/value rows were available for calendar heatmap rendering.", context["table_summary"])

    aggregated = {day: _aggregate_calendar_values(values, aggregation) for day, values in by_day.items()}
    week_start = str(params.get("week_start") or "monday")
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] if week_start != "sunday" else ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    years = sorted({day.year for day in aggregated})
    y_labels = [f"{year} {weekday}" for year in years for weekday in weekdays]
    week_numbers = list(range(54))
    z_matrix = [[None for _ in week_numbers] for _ in y_labels]
    text_matrix = [["" for _ in week_numbers] for _ in y_labels]
    customdata = [["" for _ in week_numbers] for _ in y_labels]
    y_index = {label: index for index, label in enumerate(y_labels)}
    precision = _bounded_int(params.get("value_precision"), 0, 0, 6)
    for day, value in aggregated.items():
        weekday_index = _calendar_weekday_index(day, week_start)
        week_number = _calendar_week_number(day, week_start)
        y_label = f"{day.year} {weekdays[weekday_index]}"
        row_index = y_index[y_label]
        z_matrix[row_index][week_number] = value
        text_matrix[row_index][week_number] = f"{value:.{precision}f}"
        customdata[row_index][week_number] = day.isoformat()

    trace = {
        "type": "heatmap",
        "name": value_column or "event count",
        "x": week_numbers,
        "y": y_labels,
        "z": z_matrix,
        "text": text_matrix,
        "customdata": customdata,
        "colorscale": _colorscale(str(params.get("color_scale") or "ylorrd")),
        "colorbar": {"title": value_column or "count"},
        "hovertemplate": "date=%{customdata}<br>week=%{x}<br>value=%{z:.4g}<extra></extra>",
        "xgap": 1,
        "ygap": 1,
    }
    if _truthy(params.get("show_values"), False):
        trace["texttemplate"] = "%{text}"
        trace["textfont"] = {"size": 9, "color": "#07131f"}

    warnings = []
    if skipped_dates:
        warnings.append(f"Skipped {skipped_dates} rows with unparseable dates.")
    if skipped_values:
        warnings.append(f"Skipped {skipped_values} rows without finite values.")
    layout = _base_layout(
        title=f"Calendar heatmap: {value_column or 'row count'} by {date_column}",
        x_title="week of year",
        y_title="year / weekday",
        params=params,
    )
    layout["height"] = max(layout.get("height", 760), min(3000, 180 + len(y_labels) * 24))
    layout["xaxis"]["tickmode"] = "array"
    layout["xaxis"]["tickvals"] = list(range(0, 54, 4))
    layout["xaxis"]["dtick"] = 4
    layout["yaxis"]["autorange"] = "reversed"
    layout["plot_bgcolor"] = str(params.get("missing_color") or "#f1f5f9")
    layout["meta"] = {
        "calendar_heatmap": {
            "date_column": date_column,
            "value_column": value_column,
            "aggregation": aggregation,
            "days": len(aggregated),
            "years": years,
        }
    }
    return {"data": [trace], "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _parse_calendar_date(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    formats = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m-%d-%Y", "%Y%m%d", "%d/%m/%Y", "%d-%m-%Y")
    for fmt in formats:
        try:
            return datetime.strptime(raw.split()[0], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _aggregate_calendar_values(values: list[float], aggregation: str) -> float:
    if aggregation == "mean":
        return fmean(values)
    if aggregation == "median":
        return float(median(values))
    if aggregation == "count":
        return float(len(values))
    return float(sum(values))


def _calendar_weekday_index(day: date, week_start: str) -> int:
    weekday = day.weekday()
    return (weekday + 1) % 7 if week_start == "sunday" else weekday


def _calendar_week_number(day: date, week_start: str) -> int:
    return int(day.strftime("%U" if week_start == "sunday" else "%W"))


def _build_density_contour_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    numeric_columns = context["numeric_columns"]
    x_column = _choose_column(params.get("x"), numeric_columns, fallback_index=0)
    y_column = _choose_column(params.get("y"), numeric_columns, fallback_index=1)
    if not x_column or not y_column:
        return _empty_plot_spec("density_contour", "2D density contour requires at least two numeric columns.", context["table_summary"])

    x_values = []
    y_values = []
    for row in context["records"]:
        x_value = _number_or_none(row.get(x_column))
        y_value = _number_or_none(row.get(y_column))
        if x_value is None or y_value is None:
            continue
        x_values.append(x_value)
        y_values.append(y_value)
    if len(x_values) < 3:
        return _empty_plot_spec(
            "density_contour",
            "2D density contour requires at least three paired numeric rows.",
            context["table_summary"],
        )

    contour_settings: dict[str, Any] = {
        "coloring": str(params.get("contours_coloring") or "heatmap"),
        "showlabels": _truthy(params.get("show_contour_labels"), False),
    }
    for source_key, plotly_key in {
        "contour_start": "start",
        "contour_end": "end",
        "contour_size": "size",
    }.items():
        value = _number_or_none(params.get(source_key))
        if value is not None:
            contour_settings[plotly_key] = value
    traces: list[dict[str, Any]] = [
        {
            "type": "histogram2dcontour",
            "name": "Density",
            "x": x_values,
            "y": y_values,
            "colorscale": _colorscale(str(params.get("palette") or "viridis")),
            "contours": contour_settings,
            "line": {"width": _bounded_float(params.get("contour_line_width"), 1.2, 0.2, 8), "color": "#294452"},
            "showscale": True,
            "hovertemplate": f"{x_column}=%{{x:.4g}}<br>{y_column}=%{{y:.4g}}<extra>density</extra>",
        }
    ]
    if _truthy(params.get("show_points"), True):
        color_column = _choose_column(params.get("color"), context["categorical_columns"])
        label_column = _choose_column(params.get("label"), context["columns"])
        traces.extend(
            _grouped_marker_traces(
                context["records"],
                x_column=x_column,
                y_column=y_column,
                color_column=color_column,
                label_column=label_column,
                size_column=None,
                mode="markers",
                marker_size=_bounded_float(params.get("point_size"), 5, 1, 24),
                marker_opacity=_bounded_float(params.get("point_alpha"), 0.38, 0.05, 1),
            )
        )

    layout = _base_layout(
        title=f"2D density contour: {x_column} vs {y_column}",
        x_title=x_column,
        y_title=y_column,
        params=params,
    )
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": []}


def _build_scatter_3d_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    numeric_columns = context["numeric_columns"]
    x_column = _choose_column(params.get("x"), numeric_columns, fallback_index=0)
    y_column = _choose_column(params.get("y"), numeric_columns, fallback_index=1)
    z_column = _choose_column(params.get("z"), numeric_columns, fallback_index=2)
    if not x_column or not y_column or not z_column:
        return _empty_plot_spec("scatter_3d", "3D scatter requires at least three numeric columns.", context["table_summary"])

    color_column = _choose_column(params.get("color"), context["categorical_columns"])
    label_column = _choose_column(params.get("label"), context["columns"]) or _best_label_column(context["columns"])
    grouped = _records_by_category(context["records"], color_column) if color_column else {"All": context["records"]}
    traces = []
    for index, (group_name, rows) in enumerate(grouped.items()):
        x_values = []
        y_values = []
        z_values = []
        labels = []
        for row in rows:
            x_value = _number_or_none(row.get(x_column))
            y_value = _number_or_none(row.get(y_column))
            z_value = _number_or_none(row.get(z_column))
            if x_value is None or y_value is None or z_value is None:
                continue
            x_values.append(x_value)
            y_values.append(y_value)
            z_values.append(z_value)
            labels.append(str(row.get(label_column) or "") if label_column else "")
        if not x_values:
            continue
        traces.append(
            {
                "type": "scatter3d",
                "mode": "markers",
                "name": group_name,
                "x": x_values,
                "y": y_values,
                "z": z_values,
                "text": labels,
                "marker": {
                    "size": _bounded_float(params.get("marker_size"), 5, 1, 30),
                    "opacity": _bounded_float(params.get("point_alpha"), 0.78, 0.05, 1),
                    "color": PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)],
                    "line": {"color": "#ffffff", "width": 0.4},
                },
                "hovertemplate": "%{text}<br>x=%{x:.4g}<br>y=%{y:.4g}<br>z=%{z:.4g}<extra>%{fullData.name}</extra>",
            }
        )
    total_points = sum(len(trace.get("x", [])) for trace in traces)
    if total_points < 2:
        return _empty_plot_spec(
            "scatter_3d",
            "3D scatter requires at least two complete x/y/z numeric rows.",
            context["table_summary"],
        )

    layout = _base_layout(
        title=f"3D scatter: {x_column}, {y_column}, {z_column}",
        x_title="",
        y_title="",
        params=params,
    )
    layout["scene"] = {
        "xaxis": {"title": x_column, "backgroundcolor": "#f7fbfd", "gridcolor": "#dde8ef"},
        "yaxis": {"title": y_column, "backgroundcolor": "#f7fbfd", "gridcolor": "#dde8ef"},
        "zaxis": {"title": z_column, "backgroundcolor": "#f7fbfd", "gridcolor": "#dde8ef"},
        "camera": {"eye": _camera_eye(str(params.get("camera") or "isometric"))},
    }
    layout["height"] = _bounded_int(params.get("height"), 760, 360, 3000)
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": []}


def _build_surface_3d_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    numeric_columns = _selected_columns(
        params.get("value_columns"),
        context["numeric_columns"],
        limit=_bounded_int(params.get("max_columns"), 50, 2, 140),
    )
    if len(numeric_columns) < 2:
        return _empty_plot_spec("surface_3d", "3D surface heatmap requires at least two numeric columns.", context["table_summary"])

    row_id_column = _requested_column(params.get("row_id"), context["columns"]) or _best_label_column(context["columns"])
    top_n = _bounded_int(params.get("top_n"), 40, 5, 2000)
    matrix_rows = _top_matrix_rows(context["records"], numeric_columns, row_id_column, top_n)
    if not matrix_rows:
        return _empty_plot_spec("surface_3d", "No numeric matrix rows were available for surface rendering.", context["table_summary"])

    scale = str(params.get("scale") or "row_zscore")
    labels = [item["label"] for item in matrix_rows]
    z_values = [_scale_values(item["values"], scale) for item in matrix_rows]
    text = [[f"{label} / {column}" for column in numeric_columns] for label in labels]
    contours = (
        {
            "z": {
                "show": True,
                "usecolormap": True,
                "highlightcolor": "#ffffff",
                "project": {"z": True},
            }
        }
        if _truthy(params.get("show_contours"), True)
        else {}
    )
    trace = {
        "type": "surface",
        "x": list(range(len(numeric_columns))),
        "y": list(range(len(labels))),
        "z": z_values,
        "text": text,
        "colorscale": str(params.get("colorscale") or "Viridis"),
        "colorbar": {"title": scale},
        "contours": contours,
        "hovertemplate": "%{text}<br>value=%{z:.4g}<extra></extra>",
    }
    layout = _base_layout(
        title=f"3D surface heatmap: top {len(labels)} variable rows",
        x_title="",
        y_title="",
        params=params,
    )
    layout["scene"] = {
        "xaxis": {
            "title": "sample / numeric column",
            "tickmode": "array",
            "tickvals": list(range(len(numeric_columns))),
            "ticktext": numeric_columns,
        },
        "yaxis": {
            "title": row_id_column or "row",
            "tickmode": "array",
            "tickvals": list(range(len(labels))),
            "ticktext": labels,
        },
        "zaxis": {"title": scale},
        "camera": {"eye": _camera_eye(str(params.get("camera") or "isometric"))},
    }
    layout["height"] = _bounded_int(params.get("height"), 780, 420, 3000)
    warnings = []
    if len(context["records"]) > len(matrix_rows):
        warnings.append(f"Showing top {len(matrix_rows)} rows ranked by variance.")
    return {"data": [trace], "layout": layout, "config": _plotly_config(params), "warnings": warnings}


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
    marker_size = _bounded_float(params.get("point_size"), 7, 1, 30)
    marker_opacity = _bounded_float(params.get("point_alpha"), 0.78, 0.05, 1)
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
                "marker": {"size": marker_size, "opacity": marker_opacity, "color": colors[name]},
                "hovertemplate": "%{text}<br>log2FC=%{x:.3g}<br>-log10(p)=%{y:.3g}<br>p=%{customdata[0]:.3g}<extra></extra>",
            }
        )
    label_trace = _volcano_label_trace(grouped, params)
    if label_trace:
        traces.append(label_trace)
    layout = _base_layout(
        title=f"Volcano: {log2fc_column} vs {p_value_column}",
        x_title=log2fc_column,
        y_title="-log10(p value)",
        params=params,
    )
    if _truthy(params.get("show_threshold_lines"), True):
        threshold_line_dash = str(params.get("threshold_line_dash") or "dash")
        if threshold_line_dash not in {"solid", "dash", "dot", "dashdot"}:
            threshold_line_dash = "dash"
        threshold_line = {
            "color": str(params.get("threshold_line_color") or "#8799aa"),
            "width": _bounded_float(params.get("threshold_line_width"), 1.0, 0.5, 6),
            "dash": threshold_line_dash,
        }
        layout.setdefault("shapes", []).extend(
            [
                _vertical_line(log2fc_threshold, line=threshold_line),
                _vertical_line(-log2fc_threshold, line=threshold_line),
                _horizontal_line(-math.log10(p_value_threshold), line=threshold_line),
            ]
        )
        layout.setdefault("annotations", []).append(
            {
                "x": 0,
                "y": -math.log10(p_value_threshold),
                "text": f"p = {p_value_threshold:g}",
                "showarrow": False,
                "yshift": 10,
                "font": {"size": 11, "color": "#52616b"},
            }
        )
    warnings = []
    if not traces:
        warnings.append("No valid p-value/log2FC rows were available.")
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _build_waterfall_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    columns = context["columns"]
    value_column = _requested_column(params.get("value_column"), columns) or _find_column(
        columns, ["log2fc", "log2_fold_change", "fold_change", "effect_size", "score", "value"]
    )
    label_column = _requested_column(params.get("label_column"), columns) or _find_column(
        columns, ["gene", "symbol", "name", "feature", "id"]
    )
    p_value_column = _requested_column(params.get("p_value_column"), columns) or _find_column(
        columns, ["padj", "p_adjust", "p_value", "pvalue"]
    )
    group_column = _requested_column(params.get("group"), columns)
    if not value_column:
        return _empty_plot_spec("waterfall", "Waterfall requires one signed numeric value column.", context["table_summary"])

    rows = []
    for index, row in enumerate(context["records"]):
        value = _number_or_none(row.get(value_column))
        if value is None:
            continue
        p_value = _number_or_none(row.get(p_value_column)) if p_value_column else None
        label = str(row.get(label_column) or f"row {index + 1}") if label_column else f"row {index + 1}"
        rows.append(
            {
                "label": label,
                "value": value,
                "p_value": p_value,
                "group": str(row.get(group_column) or "Group") if group_column else "",
                "input_index": index,
            }
        )
    if not rows:
        return _empty_plot_spec("waterfall", "No finite signed values were available for waterfall rendering.", context["table_summary"])

    sort_by = str(params.get("sort_by") or "abs_value")
    if sort_by == "value_desc":
        rows.sort(key=lambda item: item["value"], reverse=True)
    elif sort_by == "value_asc":
        rows.sort(key=lambda item: item["value"])
    elif sort_by == "p_value" and p_value_column:
        rows.sort(key=lambda item: item["p_value"] if item["p_value"] is not None else math.inf)
    elif sort_by == "input":
        rows.sort(key=lambda item: item["input_index"])
    else:
        rows.sort(key=lambda item: abs(item["value"]), reverse=True)

    top_n = _bounded_int(params.get("top_n"), 80, 1, 5000)
    warnings = []
    if len(rows) > top_n:
        warnings.append(f"Showing top {top_n} rows ranked by {sort_by}.")
        rows = rows[:top_n]

    positive_color = str(params.get("positive_color") or "#c44f3a")
    negative_color = str(params.get("negative_color") or "#315fd6")
    neutral_color = str(params.get("neutral_color") or "#9aaab7")
    color_mode = str(params.get("color_mode") or "significance")
    log2fc_threshold = _bounded_float(params.get("log2fc_threshold"), 1.0, 0, 20)
    p_value_threshold = _bounded_float(params.get("p_value_threshold"), 0.05, 0, 1)
    group_colors = {
        group: PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)]
        for index, group in enumerate(dict.fromkeys(item["group"] for item in rows if item["group"]))
    }
    marker_colors = [
        _waterfall_color(
            item,
            color_mode=color_mode,
            p_value_column=p_value_column,
            log2fc_threshold=log2fc_threshold,
            p_value_threshold=p_value_threshold,
            positive_color=positive_color,
            negative_color=negative_color,
            neutral_color=neutral_color,
            group_colors=group_colors,
        )
        for item in rows
    ]
    precision = _bounded_int(params.get("value_precision"), 2, 0, 6)
    orientation = str(params.get("orientation") or "vertical")
    is_horizontal = orientation == "horizontal"
    labels = [item["label"] for item in rows]
    values = [item["value"] for item in rows]
    customdata = [[item["p_value"] if item["p_value"] is not None else "", item["group"]] for item in rows]
    trace = {
        "type": "bar",
        "name": value_column,
        "x": values if is_horizontal else labels,
        "y": labels if is_horizontal else values,
        "orientation": "h" if is_horizontal else "v",
        "marker": {
            "color": marker_colors,
            "opacity": _bounded_float(params.get("bar_opacity"), 0.88, 0.05, 1),
            "line": {"color": "rgba(255,255,255,0.85)", "width": 0.6},
        },
        "customdata": customdata,
        "hovertemplate": (
            "%{y}<br>"
            + f"{value_column}=%{{x:.4g}}<br>p=%{{customdata[0]}}<br>group=%{{customdata[1]}}<extra></extra>"
            if is_horizontal
            else "%{x}<br>"
            + f"{value_column}=%{{y:.4g}}<br>p=%{{customdata[0]}}<br>group=%{{customdata[1]}}<extra></extra>"
        ),
    }
    if _truthy(params.get("show_value_labels"), False):
        trace["text"] = [f"{value:.{precision}f}" for value in values]
        trace["textposition"] = "outside"
        trace["cliponaxis"] = False

    layout = _base_layout(
        title=f"Waterfall: ranked {value_column}",
        x_title=value_column if is_horizontal else label_column or "feature",
        y_title=(label_column or "feature") if is_horizontal else value_column,
        params=params,
    )
    layout["bargap"] = _bounded_float(params.get("bargap"), 0.08, 0, 0.8)
    layout["xaxis"]["automargin"] = True
    layout["yaxis"]["automargin"] = True
    if _truthy(params.get("show_zero_line"), True):
        zero_line = {"color": "#52616b", "width": 1.2, "dash": "solid"}
        layout.setdefault("shapes", []).append(_vertical_line(0, line=zero_line) if is_horizontal else _horizontal_line(0, line=zero_line))
    if len(rows) > 60 and not is_horizontal:
        layout["xaxis"]["tickangle"] = _bounded_float(params.get("x_tick_angle"), -55, -90, 90)
    return {"data": [trace], "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _waterfall_color(
    item: dict[str, Any],
    *,
    color_mode: str,
    p_value_column: str | None,
    log2fc_threshold: float,
    p_value_threshold: float,
    positive_color: str,
    negative_color: str,
    neutral_color: str,
    group_colors: dict[str, str],
) -> str:
    if color_mode == "group" and item.get("group"):
        return group_colors.get(str(item["group"]), neutral_color)
    if color_mode == "single":
        return positive_color
    is_significant = (
        color_mode == "significance"
        and p_value_column
        and item.get("p_value") is not None
        and item["p_value"] <= p_value_threshold
        and abs(item["value"]) >= log2fc_threshold
    )
    if color_mode == "significance" and not is_significant:
        return neutral_color
    return positive_color if item["value"] >= 0 else negative_color


def _build_lollipop_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    columns = context["columns"]
    value_column = _requested_column(params.get("value_column"), columns) or _find_column(
        columns, ["score", "log2fc", "log2_fold_change", "effect_size", "importance", "count", "value"]
    )
    label_column = _requested_column(params.get("label_column"), columns) or _find_column(
        columns, ["gene", "symbol", "term", "description", "name", "feature", "id"]
    )
    color_column = _requested_column(params.get("color_column"), columns)
    size_column = _requested_column(params.get("size_column"), columns)
    if not value_column:
        return _empty_plot_spec("lollipop", "Lollipop requires one numeric value column.", context["table_summary"])

    rows = []
    for index, row in enumerate(context["records"]):
        value = _number_or_none(row.get(value_column))
        if value is None:
            continue
        label = str(row.get(label_column) or f"row {index + 1}") if label_column else f"row {index + 1}"
        color_value = str(row.get(color_column) or "") if color_column else ""
        size_value = _number_or_none(row.get(size_column)) if size_column else None
        rows.append({"label": label, "value": value, "color": color_value, "size_value": size_value, "input_index": index})
    if not rows:
        return _empty_plot_spec("lollipop", "No finite values were available for lollipop rendering.", context["table_summary"])

    sort_by = str(params.get("sort_by") or "abs_value")
    if sort_by == "value_desc":
        rows.sort(key=lambda item: item["value"], reverse=True)
    elif sort_by == "value_asc":
        rows.sort(key=lambda item: item["value"])
    elif sort_by == "input":
        rows.sort(key=lambda item: item["input_index"])
    else:
        rows.sort(key=lambda item: abs(item["value"]), reverse=True)
    top_n = _bounded_int(params.get("top_n"), 40, 1, 5000)
    warnings = []
    if len(rows) > top_n:
        warnings.append(f"Showing top {top_n} lollipop points ranked by {sort_by}.")
        rows = rows[:top_n]

    baseline = _bounded_float(params.get("baseline"), 0, -1_000_000, 1_000_000)
    is_horizontal = str(params.get("orientation") or "horizontal") == "horizontal"
    labels = [row["label"] for row in rows]
    values = [row["value"] for row in rows]
    positive_color = str(params.get("positive_color") or "#c44f3a")
    negative_color = str(params.get("negative_color") or "#315fd6")
    neutral_color = str(params.get("neutral_color") or "#667085")
    group_colors: dict[str, str] = {}
    colors = []
    for row in rows:
        if color_column and row["color"]:
            group_colors.setdefault(row["color"], PLOTLY_PALETTE[len(group_colors) % len(PLOTLY_PALETTE)])
            colors.append(group_colors[row["color"]])
        elif row["value"] > baseline:
            colors.append(positive_color)
        elif row["value"] < baseline:
            colors.append(negative_color)
        else:
            colors.append(neutral_color)

    precision = _bounded_int(params.get("value_precision"), 2, 0, 6)
    customdata = [[row["color"], row["size_value"] if row["size_value"] is not None else ""] for row in rows]
    trace = {
        "type": "scatter",
        "mode": "markers+text" if _truthy(params.get("show_value_labels"), False) else "markers",
        "name": value_column,
        "x": values if is_horizontal else labels,
        "y": labels if is_horizontal else values,
        "marker": {
            "size": _lollipop_marker_sizes(rows, params=params),
            "color": colors,
            "opacity": _bounded_float(params.get("point_alpha"), 0.88, 0.05, 1),
            "line": {"color": "#ffffff", "width": 0.8},
        },
        "customdata": customdata,
        "hovertemplate": (
            "%{y}<br>"
            + f"{value_column}=%{{x:.4g}}<br>color=%{{customdata[0]}}<br>size=%{{customdata[1]}}<extra></extra>"
            if is_horizontal
            else "%{x}<br>"
            + f"{value_column}=%{{y:.4g}}<br>color=%{{customdata[0]}}<br>size=%{{customdata[1]}}<extra></extra>"
        ),
    }
    if _truthy(params.get("show_value_labels"), False):
        trace["text"] = [f"{value:.{precision}f}" for value in values]
        trace["textposition"] = "middle right" if is_horizontal else "top center"

    stem_line = {
        "color": str(params.get("stem_color") or "#9aaab7"),
        "width": _bounded_float(params.get("stem_width"), 1.4, 0.2, 8),
    }
    shapes = [
        {
            "type": "line",
            "xref": "x",
            "yref": "y",
            "x0": baseline if is_horizontal else label,
            "x1": value if is_horizontal else label,
            "y0": label if is_horizontal else baseline,
            "y1": label if is_horizontal else value,
            "line": stem_line,
            "layer": "below",
        }
        for label, value in zip(labels, values, strict=False)
    ]
    layout = _base_layout(
        title=f"Lollipop: ranked {value_column}",
        x_title=value_column if is_horizontal else label_column or "feature",
        y_title=(label_column or "feature") if is_horizontal else value_column,
        params=params,
    )
    layout["shapes"] = [*layout.get("shapes", []), *shapes]
    layout["xaxis"]["automargin"] = True
    layout["yaxis"]["automargin"] = True
    if is_horizontal:
        layout["yaxis"]["autorange"] = "reversed"
    elif len(rows) > 30:
        layout["xaxis"]["tickangle"] = _bounded_float(params.get("x_tick_angle"), -45, -90, 90)
    return {"data": [trace], "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _lollipop_marker_sizes(rows: list[dict[str, Any]], *, params: dict[str, Any]) -> list[float]:
    default_size = _bounded_float(params.get("point_size"), 10, 2, 64)
    numeric_sizes = [row["size_value"] for row in rows if row.get("size_value") is not None]
    if not numeric_sizes:
        return [default_size for _ in rows]
    minimum = min(numeric_sizes)
    maximum = max(numeric_sizes)
    span = max(maximum - minimum, 1e-9)
    return [
        default_size * 0.65 + ((row.get("size_value") or minimum) - minimum) / span * default_size * 1.35
        for row in rows
    ]


def _build_ma_plot_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    columns = context["columns"]
    mean_column = _requested_column(params.get("mean_column"), columns) or _find_column(
        columns, ["basemean", "mean_expression", "mean_abundance", "mean", "abundance", "intensity"]
    )
    log2fc_column = _requested_column(params.get("log2fc_column"), columns) or _find_column(
        columns, ["log2fc", "log2_fold_change", "fold_change"]
    )
    p_value_column = _requested_column(params.get("p_value_column"), columns) or _find_column(
        columns, ["padj", "p_adjust", "p_value", "pvalue"]
    )
    gene_column = _requested_column(params.get("gene"), columns) or _find_column(columns, ["gene", "symbol", "name"])
    if not mean_column or not log2fc_column:
        return _empty_plot_spec("ma_plot", "MA plot requires mean abundance and log2FC columns.", context["table_summary"])

    log2fc_threshold = _bounded_float(params.get("log2fc_threshold"), 1.0, 0, 20)
    p_value_threshold = _bounded_float(params.get("p_value_threshold"), 0.05, 0, 1)
    grouped = {"Up": [], "Down": [], "Not significant": []}
    for row in context["records"]:
        mean_value = _number_or_none(row.get(mean_column))
        log2fc = _number_or_none(row.get(log2fc_column))
        p_value = _number_or_none(row.get(p_value_column)) if p_value_column else None
        if mean_value is None or log2fc is None:
            continue
        if _truthy(params.get("x_log"), True) and mean_value <= 0:
            continue
        point = {
            "x": mean_value,
            "y": log2fc,
            "gene": str(row.get(gene_column) or "") if gene_column else "",
            "p_value": p_value,
        }
        is_significant = (
            p_value_column
            and p_value is not None
            and p_value <= p_value_threshold
            and abs(log2fc) >= log2fc_threshold
        )
        if is_significant and log2fc >= 0:
            grouped["Up"].append(point)
        elif is_significant:
            grouped["Down"].append(point)
        else:
            grouped["Not significant"].append(point)

    colors = {
        "Up": str(params.get("up_color") or "#c44f3a"),
        "Down": str(params.get("down_color") or "#315fd6"),
        "Not significant": str(params.get("neutral_color") or "#9aaab7"),
    }
    marker_size = _bounded_float(params.get("point_size"), 7, 1, 30)
    marker_opacity = _bounded_float(params.get("point_alpha"), 0.76, 0.05, 1)
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
                "customdata": [[point["p_value"] if point["p_value"] is not None else ""] for point in points],
                "marker": {"size": marker_size, "opacity": marker_opacity, "color": colors[name]},
                "hovertemplate": "%{text}<br>mean=%{x:.4g}<br>log2FC=%{y:.3g}<br>p=%{customdata[0]}<extra>%{fullData.name}</extra>",
            }
        )
    label_trace = _ma_label_trace(grouped, params)
    if label_trace:
        traces.append(label_trace)

    layout = _base_layout(
        title=f"MA plot: {mean_column} vs {log2fc_column}",
        x_title=mean_column,
        y_title=log2fc_column,
        params=params,
    )
    if _truthy(params.get("x_log"), True):
        layout["xaxis"]["type"] = "log"
    if _truthy(params.get("show_threshold_lines"), True):
        line = {"color": "#8799aa", "width": 1.0, "dash": "dash"}
        layout.setdefault("shapes", []).extend(
            [_horizontal_line(0, line={"color": "#52616b", "width": 1.2, "dash": "solid"})]
        )
        if log2fc_threshold > 0:
            layout["shapes"].extend([_horizontal_line(log2fc_threshold, line=line), _horizontal_line(-log2fc_threshold, line=line)])
    warnings = []
    if not traces:
        warnings.append("No valid mean/log2FC rows were available.")
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _ma_label_trace(grouped: dict[str, list[dict[str, Any]]], params: dict[str, Any]) -> dict[str, Any] | None:
    label_top_n = _bounded_int(params.get("label_top_n"), 12, 0, 200)
    if label_top_n <= 0:
        return None
    candidates = [point for group_name in ("Up", "Down") for point in grouped.get(group_name, []) if point.get("gene")]
    candidates.sort(key=lambda point: (point["p_value"] if point["p_value"] is not None else math.inf, -abs(point["y"])))
    selected = candidates[:label_top_n]
    if not selected:
        return None
    return {
        "type": "scatter",
        "mode": "text",
        "name": "Gene labels",
        "x": [point["x"] for point in selected],
        "y": [point["y"] for point in selected],
        "text": [point["gene"] for point in selected],
        "textposition": ["middle right" if point["y"] >= 0 else "middle left" for point in selected],
        "textfont": {"size": _bounded_int(params.get("label_font_size"), 12, 6, 24), "color": "#07131f"},
        "hoverinfo": "skip",
        "showlegend": False,
    }


def _build_qq_plot_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    columns = context["columns"]
    p_value_column = _requested_column(params.get("p_value_column"), columns) or _find_column(
        columns, ["padj", "p_adjust", "p_value", "pvalue"]
    )
    label_column = _requested_column(params.get("label_column"), columns) or _find_column(
        columns, ["gene", "symbol", "name", "feature", "id"]
    )
    group_column = _requested_column(params.get("group"), columns)
    if not p_value_column:
        return _empty_plot_spec("qq_plot", "QQ plot requires one p-value column.", context["table_summary"])

    rows = []
    for index, row in enumerate(context["records"]):
        p_value = _number_or_none(row.get(p_value_column))
        if p_value is None or p_value <= 0 or p_value > 1:
            continue
        rows.append(
            {
                "p_value": p_value,
                "label": str(row.get(label_column) or f"row {index + 1}") if label_column else f"row {index + 1}",
                "group": str(row.get(group_column) or "All") if group_column else "All",
            }
        )
    if not rows:
        return _empty_plot_spec("qq_plot", "No valid p-values in (0, 1] were available.", context["table_summary"])

    max_points = _bounded_int(params.get("max_points"), 5000, 100, 200000)
    if len(rows) > max_points:
        rows.sort(key=lambda item: item["p_value"])
        step = max(1, len(rows) // max_points)
        rows = rows[: max_points // 2] + rows[max_points // 2 :: step][: max_points - max_points // 2]

    grouped = _group_qq_rows(rows, group_column is not None)
    traces = []
    all_expected = []
    label_candidates = []
    marker_size = _bounded_float(params.get("point_size"), 6, 1, 30)
    marker_opacity = _bounded_float(params.get("point_alpha"), 0.72, 0.05, 1)
    for index, (group_name, group_rows) in enumerate(grouped.items()):
        group_rows = sorted(group_rows, key=lambda item: item["p_value"])
        n = len(group_rows)
        expected = [-math.log10((rank - 0.5) / n) for rank in range(1, n + 1)]
        observed = [-math.log10(max(item["p_value"], 1e-300)) for item in group_rows]
        all_expected.extend(expected)
        traces.append(
            {
                "type": "scattergl",
                "mode": "markers",
                "name": group_name,
                "x": expected,
                "y": observed,
                "text": [item["label"] for item in group_rows],
                "customdata": [[item["p_value"]] for item in group_rows],
                "marker": {
                    "size": marker_size,
                    "opacity": marker_opacity,
                    "color": PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)],
                    "line": {"color": "#ffffff", "width": 0.4},
                },
                "hovertemplate": "%{text}<br>expected=%{x:.3g}<br>observed=%{y:.3g}<br>p=%{customdata[0]:.3g}<extra>%{fullData.name}</extra>",
            }
        )
        for item, expected_value, observed_value in zip(group_rows, expected, observed):
            label_candidates.append(
                {
                    "x": expected_value,
                    "y": observed_value,
                    "label": item["label"],
                    "p_value": item["p_value"],
                    "group": group_name,
                }
            )

    layout = _base_layout(
        title=f"QQ plot: {p_value_column}",
        x_title="Expected -log10(p)",
        y_title="Observed -log10(p)",
        params=params,
    )
    max_axis = max(max(all_expected or [1]), max(candidate["y"] for candidate in label_candidates), 1)
    if _truthy(params.get("confidence_band"), True):
        band_trace = _qq_confidence_band_trace(len(rows), max_axis, params)
        if band_trace:
            traces.insert(0, band_trace)
    if _truthy(params.get("show_diagonal"), True):
        layout.setdefault("shapes", []).append(
            {
                "type": "line",
                "xref": "x",
                "yref": "y",
                "x0": 0,
                "x1": max_axis,
                "y0": 0,
                "y1": max_axis,
                "line": {"color": str(params.get("diagonal_color") or "#52616b"), "width": 1.2, "dash": "dash"},
            }
        )
    label_trace = _qq_label_trace(label_candidates, params)
    if label_trace:
        traces.append(label_trace)
    layout["xaxis"]["range"] = [0, max_axis * 1.04]
    layout["yaxis"]["range"] = [0, max_axis * 1.04]
    warnings = []
    if len(context["records"]) > len(rows):
        warnings.append(f"Rendered {len(rows)} valid p-values after filtering invalid values and max point limits.")
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _group_qq_rows(rows: list[dict[str, Any]], has_group: bool) -> dict[str, list[dict[str, Any]]]:
    if not has_group:
        return {"All": rows}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("group") or "All"), []).append(row)
    return grouped


def _qq_confidence_band_trace(row_count: int, max_axis: float, params: dict[str, Any]) -> dict[str, Any] | None:
    if row_count < 20:
        return None
    confidence_level = _bounded_float(params.get("confidence_level"), 0.95, 0.5, 0.999)
    z_value = 2.576 if confidence_level >= 0.99 else 1.645 if confidence_level <= 0.90 else 1.96
    ranks = [max(1, round(1 + index * (row_count - 1) / 120)) for index in range(121)]
    expected = []
    lower = []
    upper = []
    for rank in ranks:
        probability = (rank - 0.5) / row_count
        se = math.sqrt(max(probability * (1 - probability) / row_count, 1e-12))
        lower_p = max(1e-300, probability - z_value * se)
        upper_p = min(1.0, probability + z_value * se)
        x_value = -math.log10(probability)
        expected.append(min(x_value, max_axis))
        lower.append(-math.log10(upper_p))
        upper.append(-math.log10(lower_p))
    return {
        "type": "scatter",
        "mode": "lines",
        "name": f"{confidence_level:.0%} null band",
        "x": expected + list(reversed(expected)),
        "y": upper + list(reversed(lower)),
        "fill": "toself",
        "fillcolor": str(params.get("band_color") or "rgba(49, 95, 214, 0.16)"),
        "line": {"color": "rgba(0,0,0,0)", "width": 0},
        "hoverinfo": "skip",
    }


def _qq_label_trace(candidates: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any] | None:
    label_top_n = _bounded_int(params.get("label_top_n"), 10, 0, 200)
    if label_top_n <= 0:
        return None
    selected = sorted([item for item in candidates if item.get("label")], key=lambda item: item["p_value"])[:label_top_n]
    if not selected:
        return None
    return {
        "type": "scatter",
        "mode": "text",
        "name": "Feature labels",
        "x": [item["x"] for item in selected],
        "y": [item["y"] for item in selected],
        "text": [item["label"] for item in selected],
        "textposition": "top center",
        "textfont": {"size": _bounded_int(params.get("label_font_size"), 11, 6, 24), "color": "#07131f"},
        "hoverinfo": "skip",
        "showlegend": False,
    }


def _build_forest_plot_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    columns = context["columns"]
    label_column = _requested_column(params.get("label_column"), columns) or _find_column(
        columns, ["term", "gene", "feature", "comparison", "name", "id"]
    )
    effect_column = _requested_column(params.get("effect_column"), columns) or _find_column(
        columns, ["effect", "estimate", "log2fc", "beta", "odds_ratio", "hazard_ratio"]
    )
    ci_low_column = _requested_column(params.get("ci_low_column"), columns) or _find_column(
        columns, ["ci_low", "ci_lower", "lower_ci", "conf_low", "lcl"]
    )
    ci_high_column = _requested_column(params.get("ci_high_column"), columns) or _find_column(
        columns, ["ci_high", "ci_upper", "upper_ci", "conf_high", "ucl"]
    )
    p_value_column = _requested_column(params.get("p_value_column"), columns) or _find_column(
        columns, ["padj", "p_adjust", "p_value", "pvalue"]
    )
    group_column = _requested_column(params.get("group"), columns)
    if not effect_column or not ci_low_column or not ci_high_column:
        return _empty_plot_spec("forest_plot", "Forest plot requires effect, CI lower, and CI upper columns.", context["table_summary"])

    rows = []
    for index, row in enumerate(context["records"]):
        effect = _number_or_none(row.get(effect_column))
        ci_low = _number_or_none(row.get(ci_low_column))
        ci_high = _number_or_none(row.get(ci_high_column))
        if effect is None or ci_low is None or ci_high is None:
            continue
        lower = min(ci_low, ci_high)
        upper = max(ci_low, ci_high)
        p_value = _number_or_none(row.get(p_value_column)) if p_value_column else None
        rows.append(
            {
                "label": str(row.get(label_column) or f"row {index + 1}") if label_column else f"row {index + 1}",
                "effect": effect,
                "ci_low": lower,
                "ci_high": upper,
                "p_value": p_value,
                "group": str(row.get(group_column) or "Group") if group_column else "",
                "input_index": index,
            }
        )
    if not rows:
        return _empty_plot_spec("forest_plot", "No finite effect-size rows were available.", context["table_summary"])

    sort_by = str(params.get("sort_by") or "p_value")
    if sort_by == "abs_effect":
        rows.sort(key=lambda item: abs(item["effect"]), reverse=True)
    elif sort_by == "effect_desc":
        rows.sort(key=lambda item: item["effect"], reverse=True)
    elif sort_by == "effect_asc":
        rows.sort(key=lambda item: item["effect"])
    elif sort_by == "input":
        rows.sort(key=lambda item: item["input_index"])
    else:
        rows.sort(key=lambda item: item["p_value"] if item["p_value"] is not None else math.inf)

    top_n = _bounded_int(params.get("top_n"), 30, 1, 500)
    warnings = []
    if len(rows) > top_n:
        warnings.append(f"Showing top {top_n} rows ranked by {sort_by}.")
        rows = rows[:top_n]
    rows = list(reversed(rows))

    reference_value = _bounded_float(params.get("reference_value"), 0, -100000, 100000)
    group_colors = {
        group: PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)]
        for index, group in enumerate(dict.fromkeys(item["group"] for item in rows if item["group"]))
    }
    marker_colors = [
        _forest_color(
            item,
            color_mode=str(params.get("color_mode") or "significance"),
            reference_value=reference_value,
            p_value_column=p_value_column,
            positive_color=str(params.get("positive_color") or "#c44f3a"),
            negative_color=str(params.get("negative_color") or "#315fd6"),
            neutral_color=str(params.get("neutral_color") or "#9aaab7"),
            group_colors=group_colors,
        )
        for item in rows
    ]
    labels = [item["label"] for item in rows]
    effects = [item["effect"] for item in rows]
    trace = {
        "type": "scatter",
        "mode": "markers",
        "name": effect_column,
        "x": effects,
        "y": labels,
        "error_x": {
            "type": "data",
            "symmetric": False,
            "array": [max(0.0, item["ci_high"] - item["effect"]) for item in rows],
            "arrayminus": [max(0.0, item["effect"] - item["ci_low"]) for item in rows],
            "thickness": _bounded_float(params.get("line_width"), 1.8, 0.2, 8),
            "width": _bounded_float(params.get("cap_width"), 5, 0, 20),
            "color": "#52616b",
        },
        "marker": {
            "size": _bounded_float(params.get("point_size"), 9, 1, 36),
            "opacity": _bounded_float(params.get("point_alpha"), 0.9, 0.05, 1),
            "color": marker_colors,
            "line": {"color": "#ffffff", "width": 0.8},
        },
        "customdata": [[item["ci_low"], item["ci_high"], item["p_value"] if item["p_value"] is not None else "", item["group"]] for item in rows],
        "hovertemplate": "%{y}<br>effect=%{x:.4g}<br>CI=%{customdata[0]:.4g} to %{customdata[1]:.4g}<br>p=%{customdata[2]}<br>group=%{customdata[3]}<extra></extra>",
    }
    layout = _base_layout(
        title=f"Forest plot: {effect_column}",
        x_title=effect_column,
        y_title=label_column or "feature",
        params=params,
    )
    layout["yaxis"]["automargin"] = True
    if params.get("height") in {None, ""}:
        layout["height"] = max(520, min(1800, 180 + len(rows) * 28))
    if _truthy(params.get("show_reference_line"), True):
        layout.setdefault("shapes", []).append(
            _vertical_line(reference_value, line={"color": "#52616b", "width": 1.2, "dash": "dash"})
        )
    return {"data": [trace], "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _forest_color(
    item: dict[str, Any],
    *,
    color_mode: str,
    reference_value: float,
    p_value_column: str | None,
    positive_color: str,
    negative_color: str,
    neutral_color: str,
    group_colors: dict[str, str],
) -> str:
    if color_mode == "group" and item.get("group"):
        return group_colors.get(str(item["group"]), neutral_color)
    if color_mode == "single":
        return positive_color
    if color_mode == "significance" and p_value_column and item.get("p_value") is not None and item["p_value"] > 0.05:
        return neutral_color
    return positive_color if item["effect"] >= reference_value else negative_color


def _build_roc_curve_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    columns = context["columns"]
    score_column = _requested_column(params.get("score_column"), columns) or _find_column(
        columns, ["score", "probability", "prediction", "risk_score", "auc_score"]
    )
    label_column = _requested_column(params.get("label_column"), columns) or _find_column(
        columns, ["label", "class", "group", "status", "outcome"]
    )
    group_column = _requested_column(params.get("group"), columns)
    if not score_column or not label_column:
        return _empty_plot_spec("roc_curve", "ROC curve requires a numeric score column and a binary label column.", context["table_summary"])

    rows = []
    for row in context["records"]:
        score = _number_or_none(row.get(score_column))
        label = str(row.get(label_column) or "").strip()
        if score is None or not label:
            continue
        rows.append({"score": score, "label": label, "group": str(row.get(group_column) or "All") if group_column else "All"})
    if not rows:
        return _empty_plot_spec("roc_curve", "No valid score/label rows were available.", context["table_summary"])

    grouped = _records_by_roc_group(rows, group_column is not None)
    traces = []
    auc_annotations = []
    warnings = []
    line_width = _bounded_float(params.get("line_width"), 2.6, 0.5, 8)
    marker_size = _bounded_float(params.get("point_size"), 6, 1, 30)
    marker_opacity = _bounded_float(params.get("point_alpha"), 0.8, 0.05, 1)
    show_threshold_points = _truthy(params.get("show_threshold_points"), False)
    for index, (group_name, group_rows) in enumerate(grouped.items()):
        result = _roc_points(group_rows, params)
        if result is None:
            warnings.append(f"Skipping {group_name}: ROC needs both positive and negative labels.")
            continue
        auc_annotations.append(f"{group_name} AUC={result['auc']:.3f} (n={len(group_rows)}, pos={result['positive_count']}, neg={result['negative_count']})")
        trace = {
            "type": "scatter",
            "mode": "lines+markers" if show_threshold_points else "lines",
            "name": f"{group_name} AUC={result['auc']:.3f}" if _truthy(params.get("show_auc"), True) else group_name,
            "x": result["fpr"],
            "y": result["tpr"],
            "customdata": [[threshold, specificity] for threshold, specificity in zip(result["thresholds"], result["specificity"])],
            "line": {"color": PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)], "width": line_width},
            "marker": {"size": marker_size, "opacity": marker_opacity},
            "hovertemplate": "FPR=%{x:.3f}<br>TPR=%{y:.3f}<br>specificity=%{customdata[1]:.3f}<br>threshold=%{customdata[0]}<extra>%{fullData.name}</extra>",
        }
        if show_threshold_points:
            trace = _thin_threshold_markers(trace, _bounded_int(params.get("threshold_count"), 12, 2, 100))
        traces.append(trace)

    if _truthy(params.get("show_diagonal"), True):
        traces.insert(
            0,
            {
                "type": "scatter",
                "mode": "lines",
                "name": "No skill",
                "x": [0, 1],
                "y": [0, 1],
                "line": {"color": str(params.get("diagonal_color") or "#8799aa"), "width": 1.2, "dash": "dash"},
                "hoverinfo": "skip",
            },
        )
    layout = _base_layout(
        title=f"ROC curve: {score_column} vs {label_column}",
        x_title="False positive rate",
        y_title="True positive rate",
        params=params,
    )
    layout["xaxis"]["range"] = [0, 1]
    layout["yaxis"]["range"] = [0, 1]
    layout["xaxis"]["constrain"] = "domain"
    layout["yaxis"]["scaleanchor"] = "x"
    layout["meta"] = {"roc_summary": auc_annotations}
    if _truthy(params.get("show_auc"), True) and auc_annotations:
        layout.setdefault("annotations", []).append(
            {
                "text": "<br>".join(auc_annotations[:4]),
                "xref": "paper",
                "yref": "paper",
                "x": 0.98,
                "y": 0.04,
                "xanchor": "right",
                "yanchor": "bottom",
                "showarrow": False,
                "align": "right",
                "font": {"size": 12, "color": "#324657"},
                "bgcolor": "rgba(255,255,255,0.78)",
                "bordercolor": "rgba(82,97,107,0.18)",
            }
        )
    if not traces or (len(traces) == 1 and traces[0].get("name") == "No skill"):
        warnings.append("No renderable ROC curve was available.")
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _records_by_roc_group(rows: list[dict[str, Any]], has_group: bool) -> dict[str, list[dict[str, Any]]]:
    if not has_group:
        return {"All": rows}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("group") or "All"), []).append(row)
    return grouped


def _roc_points(rows: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any] | None:
    labels = sorted({row["label"] for row in rows})
    if len(labels) != 2:
        return None
    requested_positive = str(params.get("positive_label") or "auto").strip()
    positive_label = requested_positive if requested_positive and requested_positive != "auto" and requested_positive in labels else labels[-1]
    direction = str(params.get("direction") or "higher_positive")
    scored = [
        {
            "score": row["score"] if direction != "lower_positive" else -row["score"],
            "raw_score": row["score"],
            "positive": row["label"] == positive_label,
        }
        for row in rows
    ]
    positive_count = sum(1 for row in scored if row["positive"])
    negative_count = len(scored) - positive_count
    if positive_count == 0 or negative_count == 0:
        return None
    scored.sort(key=lambda row: row["score"], reverse=True)
    points = [{"fpr": 0.0, "tpr": 0.0, "threshold": "Inf"}]
    tp = 0
    fp = 0
    last_score = None
    for row in scored:
        if last_score is not None and row["score"] != last_score:
            points.append({"fpr": fp / negative_count, "tpr": tp / positive_count, "threshold": _round_number(last_score)})
        if row["positive"]:
            tp += 1
        else:
            fp += 1
        last_score = row["score"]
    points.append({"fpr": fp / negative_count, "tpr": tp / positive_count, "threshold": _round_number(last_score)})
    points.append({"fpr": 1.0, "tpr": 1.0, "threshold": "-Inf"})
    points = _dedupe_roc_points(points)
    auc = 0.0
    for left, right in zip(points, points[1:]):
        auc += (right["fpr"] - left["fpr"]) * (right["tpr"] + left["tpr"]) / 2
    return {
        "fpr": [point["fpr"] for point in points],
        "tpr": [point["tpr"] for point in points],
        "specificity": [1 - point["fpr"] for point in points],
        "thresholds": [point["threshold"] for point in points],
        "auc": auc,
        "positive_count": positive_count,
        "negative_count": negative_count,
    }


def _dedupe_roc_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = []
    seen = set()
    for point in points:
        key = (round(point["fpr"], 12), round(point["tpr"], 12), str(point["threshold"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(point)
    return deduped


def _thin_threshold_markers(trace: dict[str, Any], threshold_count: int) -> dict[str, Any]:
    count = len(trace["x"])
    if count <= threshold_count:
        return trace
    keep = {0, count - 1}
    for index in range(threshold_count):
        keep.add(round(index * (count - 1) / max(1, threshold_count - 1)))
    for key in ("x", "y", "customdata"):
        trace[key] = [value for index, value in enumerate(trace[key]) if index in keep]
    return trace


def _build_pr_curve_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    columns = context["columns"]
    score_column = _requested_column(params.get("score_column"), columns) or _find_column(
        columns, ["score", "probability", "prediction", "risk_score", "auc_score"]
    )
    label_column = _requested_column(params.get("label_column"), columns) or _find_column(
        columns, ["label", "class", "group", "status", "outcome"]
    )
    group_column = _requested_column(params.get("group"), columns)
    if not score_column or not label_column:
        return _empty_plot_spec("pr_curve", "Precision-recall curve requires a numeric score column and a binary label column.", context["table_summary"])

    rows = []
    for row in context["records"]:
        score = _number_or_none(row.get(score_column))
        label = str(row.get(label_column) or "").strip()
        if score is None or not label:
            continue
        rows.append({"score": score, "label": label, "group": str(row.get(group_column) or "All") if group_column else "All"})
    grouped = _records_by_roc_group(rows, group_column is not None)
    traces = []
    summaries = []
    warnings = []
    prevalence_values = []
    show_threshold_points = _truthy(params.get("show_threshold_points"), False)
    for index, (group_name, group_rows) in enumerate(grouped.items()):
        result = _precision_recall_points(group_rows, params)
        if result is None:
            warnings.append(f"Skipping {group_name}: precision-recall needs both positive and negative labels.")
            continue
        prevalence_values.append(result["prevalence"])
        summaries.append(
            f"{group_name} AP={result['average_precision']:.3f} (n={len(group_rows)}, pos={result['positive_count']}, prevalence={result['prevalence']:.3f})"
        )
        trace = {
            "type": "scatter",
            "mode": "lines+markers" if show_threshold_points else "lines",
            "name": f"{group_name} AP={result['average_precision']:.3f}" if _truthy(params.get("show_average_precision"), True) else group_name,
            "x": result["recall"],
            "y": result["precision"],
            "customdata": [[threshold] for threshold in result["thresholds"]],
            "line": {"color": PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)], "width": _bounded_float(params.get("line_width"), 2.6, 0.5, 8)},
            "marker": {
                "size": _bounded_float(params.get("point_size"), 6, 1, 30),
                "opacity": _bounded_float(params.get("point_alpha"), 0.8, 0.05, 1),
            },
            "hovertemplate": "recall=%{x:.3f}<br>precision=%{y:.3f}<br>threshold=%{customdata[0]}<extra>%{fullData.name}</extra>",
        }
        if show_threshold_points:
            trace = _thin_threshold_markers(trace, _bounded_int(params.get("threshold_count"), 12, 2, 100))
        traces.append(trace)
    if _truthy(params.get("show_baseline"), True) and prevalence_values:
        baseline = sum(prevalence_values) / len(prevalence_values)
        traces.insert(
            0,
            {
                "type": "scatter",
                "mode": "lines",
                "name": f"Prevalence baseline={baseline:.3f}",
                "x": [0, 1],
                "y": [baseline, baseline],
                "line": {"color": str(params.get("baseline_color") or "#8799aa"), "width": 1.2, "dash": "dash"},
                "hoverinfo": "skip",
            },
        )
    layout = _base_layout(
        title=f"Precision-recall: {score_column} vs {label_column}",
        x_title="Recall",
        y_title="Precision",
        params=params,
    )
    layout["xaxis"]["range"] = [0, 1]
    layout["yaxis"]["range"] = [0, 1]
    layout["meta"] = {"pr_summary": summaries}
    if _truthy(params.get("show_average_precision"), True) and summaries:
        layout.setdefault("annotations", []).append(
            {
                "text": "<br>".join(summaries[:4]),
                "xref": "paper",
                "yref": "paper",
                "x": 0.98,
                "y": 0.04,
                "xanchor": "right",
                "yanchor": "bottom",
                "showarrow": False,
                "align": "right",
                "font": {"size": 12, "color": "#324657"},
                "bgcolor": "rgba(255,255,255,0.78)",
                "bordercolor": "rgba(82,97,107,0.18)",
            }
        )
    if not traces:
        warnings.append("No renderable precision-recall curve was available.")
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _precision_recall_points(rows: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any] | None:
    labels = sorted({row["label"] for row in rows})
    if len(labels) != 2:
        return None
    requested_positive = str(params.get("positive_label") or "auto").strip()
    positive_label = requested_positive if requested_positive and requested_positive != "auto" and requested_positive in labels else labels[-1]
    direction = str(params.get("direction") or "higher_positive")
    scored = [
        {
            "score": row["score"] if direction != "lower_positive" else -row["score"],
            "positive": row["label"] == positive_label,
        }
        for row in rows
    ]
    positive_count = sum(1 for row in scored if row["positive"])
    negative_count = len(scored) - positive_count
    if positive_count == 0 or negative_count == 0:
        return None
    scored.sort(key=lambda row: row["score"], reverse=True)
    points = [{"recall": 0.0, "precision": 1.0, "threshold": "Inf"}]
    tp = 0
    fp = 0
    last_score = None
    for row in scored:
        if last_score is not None and row["score"] != last_score:
            points.append(
                {
                    "recall": tp / positive_count,
                    "precision": tp / max(tp + fp, 1),
                    "threshold": _round_number(last_score),
                }
            )
        if row["positive"]:
            tp += 1
        else:
            fp += 1
        last_score = row["score"]
    points.append({"recall": tp / positive_count, "precision": tp / max(tp + fp, 1), "threshold": _round_number(last_score)})
    points = _dedupe_pr_points(points)
    average_precision = 0.0
    previous_recall = 0.0
    for point in points[1:]:
        average_precision += max(0.0, point["recall"] - previous_recall) * point["precision"]
        previous_recall = point["recall"]
    return {
        "recall": [point["recall"] for point in points],
        "precision": [point["precision"] for point in points],
        "thresholds": [point["threshold"] for point in points],
        "average_precision": average_precision,
        "positive_count": positive_count,
        "negative_count": negative_count,
        "prevalence": positive_count / len(scored),
    }


def _dedupe_pr_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = []
    seen = set()
    for point in points:
        key = (round(point["recall"], 12), round(point["precision"], 12), str(point["threshold"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(point)
    return deduped


def _build_kaplan_meier_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    columns = context["columns"]
    time_column = _requested_column(params.get("time_column"), columns) or _find_column(
        columns, ["time", "survival_time", "os_time", "pfs_time", "days", "months"]
    )
    event_column = _requested_column(params.get("event_column"), columns) or _find_column(
        columns, ["event", "status", "os_event", "pfs_event", "death"]
    )
    group_column = _requested_column(params.get("group"), columns)
    if not time_column or not event_column:
        return _empty_plot_spec("kaplan_meier", "Kaplan-Meier requires time and event columns.", context["table_summary"])

    records = []
    for row in context["records"]:
        time_value = _number_or_none(row.get(time_column))
        if time_value is None or time_value < 0:
            continue
        event = _is_event_value(row.get(event_column), params)
        records.append(
            {
                "time": time_value,
                "event": event,
                "group": str(row.get(group_column) or "All") if group_column else "All",
            }
        )
    if not records:
        return _empty_plot_spec("kaplan_meier", "No valid time-to-event rows were available.", context["table_summary"])

    grouped = _records_by_km_group(records)
    traces = []
    risk_table = {}
    warnings = []
    curve_mode = str(params.get("curve_mode") or "survival")
    for index, (group_name, group_rows) in enumerate(grouped.items()):
        result = _kaplan_meier_curve(group_rows)
        if result is None:
            warnings.append(f"Skipping {group_name}: no subjects were available.")
            continue
        y_values = result["survival"] if curve_mode == "survival" else [1 - value for value in result["survival"]]
        traces.append(
            {
                "type": "scatter",
                "mode": "lines",
                "name": group_name,
                "x": result["times"],
                "y": y_values,
                "line": {
                    "shape": "hv",
                    "width": _bounded_float(params.get("line_width"), 2.6, 0.5, 8),
                    "color": PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)],
                },
                "hovertemplate": f"{group_name}<br>{time_column}=%{{x:.4g}}<br>{curve_mode}=%{{y:.3f}}<extra></extra>",
            }
        )
        if _truthy(params.get("show_censor_marks"), True) and result["censor_times"]:
            censor_y = result["censor_survival"] if curve_mode == "survival" else [1 - value for value in result["censor_survival"]]
            traces.append(
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": f"{group_name} censored",
                    "x": result["censor_times"],
                    "y": censor_y,
                    "marker": {
                        "symbol": "line-ns-open",
                        "size": _bounded_float(params.get("censor_marker_size"), 7, 2, 24),
                        "color": PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)],
                    },
                    "hovertemplate": f"{group_name}<br>censored at {time_column}=%{{x:.4g}}<extra></extra>",
                    "showlegend": False,
                }
            )
        risk_table[group_name] = result["risk_table"]

    layout = _base_layout(
        title=f"Kaplan-Meier: {time_column}",
        x_title=str(params.get("time_unit") or time_column),
        y_title="Survival probability" if curve_mode == "survival" else "Failure probability",
        params=params,
    )
    layout["yaxis"]["range"] = [0, 1.02]
    layout["meta"] = {"risk_table": risk_table}
    if _truthy(params.get("show_logrank"), True):
        logrank = _logrank_two_group(grouped)
        if logrank:
            layout["meta"]["logrank"] = logrank
            layout.setdefault("annotations", []).append(
                {
                    "text": f"log-rank p={logrank['p_value']:.3g}",
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.98,
                    "y": 0.04,
                    "xanchor": "right",
                    "yanchor": "bottom",
                    "showarrow": False,
                    "font": {"size": 12, "color": "#324657"},
                    "bgcolor": "rgba(255,255,255,0.78)",
                    "bordercolor": "rgba(82,97,107,0.18)",
                }
            )
    if _truthy(params.get("show_confidence_band"), False):
        warnings.append("Kaplan-Meier confidence bands are recorded as planned controls; interval rendering is not enabled yet.")
    if not traces:
        warnings.append("No renderable Kaplan-Meier curves were available.")
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _is_event_value(value: Any, params: dict[str, Any]) -> bool:
    event_value = str(params.get("event_value") or "1").strip().lower()
    censor_value = str(params.get("censor_value") or "0").strip().lower()
    raw = str(value or "").strip().lower()
    if raw == event_value:
        return True
    if raw == censor_value:
        return False
    return raw in {"1", "true", "yes", "event", "dead", "deceased", "progressed"}


def _records_by_km_group(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        grouped.setdefault(str(row.get("group") or "All"), []).append(row)
    return grouped


def _kaplan_meier_curve(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not records:
        return None
    sorted_records = sorted(records, key=lambda item: item["time"])
    times = [0.0]
    survival = [1.0]
    censor_times = []
    censor_survival = []
    risk_table = []
    current_survival = 1.0
    unique_times = sorted({row["time"] for row in sorted_records})
    for time_value in unique_times:
        at_risk = sum(1 for row in sorted_records if row["time"] >= time_value)
        events = sum(1 for row in sorted_records if row["time"] == time_value and row["event"])
        censored = sum(1 for row in sorted_records if row["time"] == time_value and not row["event"])
        risk_table.append({"time": time_value, "at_risk": at_risk, "events": events, "censored": censored})
        if censored:
            censor_times.extend([time_value] * censored)
            censor_survival.extend([current_survival] * censored)
        if events and at_risk:
            current_survival *= max(0.0, 1 - events / at_risk)
            times.append(time_value)
            survival.append(current_survival)
    if times[-1] < unique_times[-1]:
        times.append(unique_times[-1])
        survival.append(current_survival)
    return {
        "times": times,
        "survival": survival,
        "censor_times": censor_times,
        "censor_survival": censor_survival,
        "risk_table": risk_table,
    }


def _logrank_two_group(grouped: dict[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    if len(grouped) != 2:
        return None
    group_names = list(grouped)
    first, second = grouped[group_names[0]], grouped[group_names[1]]
    event_times = sorted({row["time"] for row in first + second if row["event"]})
    observed = expected = variance = 0.0
    for time_value in event_times:
        n1 = sum(1 for row in first if row["time"] >= time_value)
        n2 = sum(1 for row in second if row["time"] >= time_value)
        d1 = sum(1 for row in first if row["time"] == time_value and row["event"])
        d2 = sum(1 for row in second if row["time"] == time_value and row["event"])
        total_risk = n1 + n2
        total_events = d1 + d2
        if total_risk <= 1 or total_events == 0:
            continue
        observed += d1
        expected += total_events * n1 / total_risk
        variance += (n1 * n2 * total_events * (total_risk - total_events)) / (
            total_risk * total_risk * max(total_risk - 1, 1)
        )
    if variance <= 0:
        return None
    chi_square = (observed - expected) ** 2 / variance
    p_value = math.erfc(math.sqrt(chi_square / 2))
    return {"groups": group_names, "chi_square": chi_square, "p_value": p_value}


def _build_bland_altman_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    x_column = _choose_column(params.get("x_method"), context["numeric_columns"], fallback_index=0)
    y_column = _choose_column(params.get("y_method"), context["numeric_columns"], fallback_index=1)
    if not x_column or not y_column:
        return _empty_plot_spec("bland_altman", "Bland-Altman requires two numeric measurement columns.", context["table_summary"])

    label_column = _choose_column(params.get("label"), context["columns"])
    color_column = _choose_column(params.get("color"), context["categorical_columns"])
    difference_mode = str(params.get("difference_mode") or "y_minus_x")
    rows = []
    for row in context["records"]:
        x_value = _number_or_none(row.get(x_column))
        y_value = _number_or_none(row.get(y_column))
        if x_value is None or y_value is None:
            continue
        mean_value = (x_value + y_value) / 2
        if difference_mode == "x_minus_y":
            difference = x_value - y_value
        elif difference_mode == "percent_difference":
            denominator = mean_value if mean_value else None
            if denominator is None:
                continue
            difference = (y_value - x_value) / denominator * 100
        else:
            difference = y_value - x_value
        rows.append(
            {
                "mean": mean_value,
                "difference": difference,
                "label": str(row.get(label_column) or "") if label_column else "",
                "group": str(row.get(color_column) or "All") if color_column else "All",
                "x": x_value,
                "y": y_value,
            }
        )
    if not rows:
        return _empty_plot_spec("bland_altman", "No complete paired measurements were available.", context["table_summary"])

    bias = fmean(item["difference"] for item in rows)
    sd = pstdev([item["difference"] for item in rows]) if len(rows) > 1 else 0.0
    multiplier = _bounded_float(params.get("limits_sd"), 1.96, 0.5, 4)
    lower = bias - multiplier * sd
    upper = bias + multiplier * sd
    grouped = {}
    for row in rows:
        grouped.setdefault(row["group"], []).append(row)
    traces = []
    for index, (group_name, group_rows) in enumerate(grouped.items()):
        traces.append(
            {
                "type": "scatter",
                "mode": "markers",
                "name": group_name,
                "x": [item["mean"] for item in group_rows],
                "y": [item["difference"] for item in group_rows],
                "text": [item["label"] for item in group_rows],
                "customdata": [[item["x"], item["y"]] for item in group_rows],
                "marker": {
                    "size": _bounded_float(params.get("point_size"), 8, 1, 36),
                    "opacity": _bounded_float(params.get("point_alpha"), 0.78, 0.05, 1),
                    "color": PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)],
                    "line": {
                        "color": str(params.get("marker_line_color") or "#ffffff"),
                        "width": _bounded_float(params.get("marker_line_width"), 0.6, 0, 5),
                    },
                },
                "hovertemplate": "%{text}<br>mean=%{x:.4g}<br>difference=%{y:.4g}<br>A=%{customdata[0]:.4g}<br>B=%{customdata[1]:.4g}<extra>%{fullData.name}</extra>",
            }
        )

    layout = _base_layout(
        title=f"Bland-Altman: {y_column} vs {x_column}",
        x_title=f"Mean of {x_column} and {y_column}",
        y_title="% difference" if difference_mode == "percent_difference" else f"Difference ({difference_mode.replace('_', ' ')})",
        params=params,
    )
    line_width = _bounded_float(params.get("line_width"), 1.4, 0.4, 8)
    shapes = layout.setdefault("shapes", [])
    annotations = layout.setdefault("annotations", [])
    if _truthy(params.get("show_zero_line"), True):
        shapes.append(_horizontal_line(0, line={"color": "#a5b4c3", "width": 1.0, "dash": "dot"}))
    if _truthy(params.get("show_bias_line"), True):
        shapes.append(_horizontal_line(bias, line={"color": "#07131f", "width": line_width, "dash": "solid"}))
        annotations.append(_line_label_annotation(bias, f"bias {bias:.3g}"))
    if _truthy(params.get("show_limits"), True):
        limit_line = {"color": "#c44f3a", "width": line_width, "dash": "dash"}
        shapes.extend([_horizontal_line(lower, line=limit_line), _horizontal_line(upper, line=limit_line)])
        annotations.extend([_line_label_annotation(lower, f"lower {lower:.3g}"), _line_label_annotation(upper, f"upper {upper:.3g}")])
    layout["meta"] = {
        "agreement": {
            "bias": bias,
            "sd": sd,
            "lower_limit": lower,
            "upper_limit": upper,
            "n": len(rows),
            "difference_mode": difference_mode,
        }
    }
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": []}


def _line_label_annotation(y_value: float, text: str) -> dict[str, Any]:
    return {
        "text": text,
        "xref": "paper",
        "yref": "y",
        "x": 1,
        "y": y_value,
        "xanchor": "right",
        "yanchor": "bottom",
        "showarrow": False,
        "font": {"size": 11, "color": "#324657"},
        "bgcolor": "rgba(255,255,255,0.75)",
    }


def _build_dose_response_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    dose_column = _choose_column(params.get("dose_column"), context["numeric_columns"], fallback_index=0)
    response_column = _choose_column(params.get("response_column"), context["numeric_columns"], fallback_index=1)
    if not dose_column or not response_column:
        return _empty_plot_spec("dose_response", "Dose-response requires dose and response numeric columns.", context["table_summary"])

    group_column = _choose_column(params.get("group"), context["categorical_columns"])
    label_column = _choose_column(params.get("label"), context["columns"])
    log_x = _truthy(params.get("log_x"), True)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in context["records"]:
        dose = _number_or_none(row.get(dose_column))
        response = _number_or_none(row.get(response_column))
        if dose is None or response is None:
            continue
        if log_x and dose <= 0:
            continue
        group_name = str(row.get(group_column) or "All") if group_column else "All"
        grouped.setdefault(group_name, []).append(
            {
                "dose": dose,
                "response": response,
                "label": str(row.get(label_column) or "") if label_column else "",
            }
        )
    if not grouped:
        return _empty_plot_spec("dose_response", "No complete dose-response rows were available.", context["table_summary"])

    traces = []
    estimates = {}
    warnings = []
    response_mode = str(params.get("response_mode") or "inhibition")
    normalize = _truthy(params.get("normalize_response"), False)
    for index, (group_name, rows) in enumerate(grouped.items()):
        rows = sorted(rows, key=lambda item: item["dose"])
        prepared = _prepare_dose_response_rows(rows, normalize)
        color = PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)]
        if _truthy(params.get("show_points"), True):
            traces.append(
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": f"{group_name} points" if _truthy(params.get("show_curve"), True) else group_name,
                    "x": [item["dose"] for item in prepared],
                    "y": [item["display_response"] for item in prepared],
                    "text": [item["label"] for item in prepared],
                    "customdata": [[item["response"]] for item in prepared],
                    "marker": {
                        "size": _bounded_float(params.get("point_size"), 8, 1, 36),
                        "opacity": _bounded_float(params.get("point_alpha"), 0.78, 0.05, 1),
                        "color": color,
                        "line": {
                            "color": str(params.get("marker_line_color") or "#ffffff"),
                            "width": _bounded_float(params.get("marker_line_width"), 0.6, 0, 5),
                        },
                    },
                    "hovertemplate": "%{text}<br>dose=%{x:.4g}<br>display response=%{y:.4g}<br>raw response=%{customdata[0]:.4g}<extra>%{fullData.name}</extra>",
                }
            )
        if _truthy(params.get("show_curve"), True):
            traces.append(
                {
                    "type": "scatter",
                    "mode": "lines",
                    "name": group_name,
                    "x": [item["dose"] for item in prepared],
                    "y": [item["display_response"] for item in prepared],
                    "line": {
                        "color": color,
                        "width": _bounded_float(params.get("line_width"), 2.6, 0.5, 8),
                        "shape": _dose_line_shape(params.get("line_shape")),
                    },
                    "hovertemplate": f"{group_name}<br>dose=%{{x:.4g}}<br>response=%{{y:.4g}}<extra></extra>",
                }
            )
        estimate = _dose_half_max_estimate(prepared, response_mode)
        if estimate:
            estimates[group_name] = estimate
    layout = _base_layout(
        title=f"Dose-response: {response_column} by {dose_column}",
        x_title=dose_column,
        y_title=f"{response_column} (% normalized)" if normalize else response_column,
        params=params,
    )
    if log_x:
        layout["xaxis"]["type"] = "log"
    if _truthy(params.get("show_half_max"), True):
        guide_shapes, guide_annotations = _dose_response_guides(estimates)
        layout.setdefault("shapes", []).extend(guide_shapes)
        layout.setdefault("annotations", []).extend(guide_annotations)
    layout["meta"] = {"dose_response": {"estimates": estimates, "normalized": normalize, "response_mode": response_mode}}
    if any(len(rows) < 3 for rows in grouped.values()):
        warnings.append("Some dose-response groups have fewer than three points; IC50/EC50 estimates are approximate.")
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _prepare_dose_response_rows(rows: list[dict[str, Any]], normalize: bool) -> list[dict[str, Any]]:
    if not normalize:
        return [{**row, "display_response": row["response"]} for row in rows]
    values = [row["response"] for row in rows]
    low, high = min(values), max(values)
    span = max(high - low, 1e-12)
    return [{**row, "display_response": (row["response"] - low) / span * 100} for row in rows]


def _dose_half_max_estimate(rows: list[dict[str, Any]], response_mode: str) -> dict[str, Any] | None:
    if len(rows) < 2:
        return None
    values = [row["display_response"] for row in rows]
    low, high = min(values), max(values)
    if high == low:
        return None
    target = (low + high) / 2
    ordered = rows if response_mode != "inhibition" else sorted(rows, key=lambda item: item["dose"])
    for left, right in zip(ordered, ordered[1:]):
        y1, y2 = left["display_response"], right["display_response"]
        if (y1 - target) == 0:
            dose = left["dose"]
            break
        if (y1 - target) * (y2 - target) <= 0 and y1 != y2:
            fraction = (target - y1) / (y2 - y1)
            if left["dose"] > 0 and right["dose"] > 0:
                log_dose = math.log10(left["dose"]) + fraction * (math.log10(right["dose"]) - math.log10(left["dose"]))
                dose = 10**log_dose
            else:
                dose = left["dose"] + fraction * (right["dose"] - left["dose"])
            break
    else:
        return None
    return {
        "half_max_dose": dose,
        "half_max_response": target,
        "min_response": low,
        "max_response": high,
        "label": "IC50" if response_mode == "inhibition" else "EC50",
    }


def _dose_response_guides(estimates: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    shapes = []
    annotations = []
    for index, (group_name, estimate) in enumerate(estimates.items()):
        color = PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)]
        line = {"color": color, "width": 1.1, "dash": "dot"}
        shapes.append(_vertical_line(estimate["half_max_dose"], line=line))
        shapes.append(_horizontal_line(estimate["half_max_response"], line=line))
        annotations.append(
            {
                "text": f"{group_name} {estimate['label']}={estimate['half_max_dose']:.3g}",
                "xref": "x",
                "yref": "paper",
                "x": estimate["half_max_dose"],
                "y": 0.98,
                "showarrow": False,
                "font": {"size": 11, "color": color},
                "bgcolor": "rgba(255,255,255,0.74)",
            }
        )
    return shapes, annotations


def _dose_line_shape(value: Any) -> str:
    shape = str(value or "spline")
    return shape if shape in {"linear", "spline", "hv"} else "spline"


def _build_paired_dot_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    value_column = _choose_column(params.get("value_column"), context["numeric_columns"], fallback_index=0)
    condition_column = _choose_column(params.get("condition_column"), context["categorical_columns"])
    subject_column = _choose_column(params.get("subject_column"), context["columns"])
    if not value_column or not condition_column or not subject_column:
        return _empty_plot_spec("paired_dot", "Paired dot requires value, condition, and subject columns.", context["table_summary"])

    group_column = _choose_column(params.get("group"), context["categorical_columns"])
    subject_rows: dict[str, list[dict[str, Any]]] = {}
    conditions = []
    for row in context["records"]:
        value = _number_or_none(row.get(value_column))
        condition = str(row.get(condition_column) or "").strip()
        subject = str(row.get(subject_column) or "").strip()
        if value is None or not condition or not subject:
            continue
        if condition not in conditions:
            conditions.append(condition)
        subject_rows.setdefault(subject, []).append(
            {
                "condition": condition,
                "value": value,
                "group": str(row.get(group_column) or "All") if group_column else "All",
            }
        )
    if not subject_rows or len(conditions) < 2:
        return _empty_plot_spec("paired_dot", "Paired dot requires at least two conditions with paired subjects.", context["table_summary"])

    max_subjects = _bounded_int(params.get("max_subjects"), 120, 2, 2000)
    warnings = []
    subjects = list(subject_rows)[:max_subjects]
    if len(subject_rows) > max_subjects:
        warnings.append(f"Showing first {max_subjects} subjects to keep the paired plot readable.")
    condition_index = {condition: index for index, condition in enumerate(conditions)}
    traces = []
    line_alpha = _bounded_float(params.get("line_alpha"), 0.35, 0.05, 1)
    line_color = f"rgba(82, 97, 107, {line_alpha:.3f})"
    if _truthy(params.get("connect_pairs"), True):
        for subject in subjects:
            rows = sorted(subject_rows[subject], key=lambda item: condition_index.get(item["condition"], 999))
            traces.append(
                {
                    "type": "scatter",
                    "mode": "lines",
                    "name": subject,
                    "x": [condition_index[item["condition"]] for item in rows],
                    "y": [item["value"] for item in rows],
                    "line": {"color": line_color, "width": _bounded_float(params.get("line_width"), 1.2, 0.2, 8)},
                    "hoverinfo": "skip",
                    "showlegend": False,
                }
            )

    grouped_points: dict[str, list[dict[str, Any]]] = {}
    for subject in subjects:
        for item in subject_rows[subject]:
            grouped_points.setdefault(item["group"], []).append({"subject": subject, **item})
    jitter = _bounded_float(params.get("jitter"), 0.05, 0, 0.45)
    for index, (group_name, rows) in enumerate(grouped_points.items()):
        traces.append(
            {
                "type": "scatter",
                "mode": "markers",
                "name": group_name,
                "x": [_jittered_condition(item["condition"], condition_index, item["subject"], jitter) for item in rows],
                "y": [item["value"] for item in rows],
                "text": [item["subject"] for item in rows],
                "customdata": [[item["condition"]] for item in rows],
                "marker": {
                    "size": _bounded_float(params.get("point_size"), 8, 1, 36),
                    "opacity": _bounded_float(params.get("point_alpha"), 0.82, 0.05, 1),
                    "color": PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)],
                    "line": {"color": "#ffffff", "width": 0.6},
                },
                "hovertemplate": "%{text}<br>condition=%{customdata[0]}<br>value=%{y:.4g}<extra>%{fullData.name}</extra>",
            }
        )

    if _truthy(params.get("show_summary"), True):
        summary = _paired_summary_by_condition(subjects, subject_rows, conditions, str(params.get("summary_stat") or "mean"))
        traces.append(
            {
                "type": "scatter",
                "mode": "lines+markers",
                "name": f"{params.get('summary_stat') or 'mean'} summary",
                "x": list(range(len(conditions))),
                "y": [summary.get(condition) for condition in conditions],
                "line": {"color": "#07131f", "width": 2.4},
                "marker": {"size": 9, "color": "#07131f"},
                "hovertemplate": "%{x}<br>summary=%{y:.4g}<extra></extra>",
            }
        )

    layout = _base_layout(
        title=f"Paired dot: {value_column} by {condition_column}",
        x_title=condition_column,
        y_title=value_column,
        params=params,
    )
    layout["xaxis"]["tickmode"] = "array"
    layout["xaxis"]["tickvals"] = list(range(len(conditions)))
    layout["xaxis"]["ticktext"] = conditions
    layout["meta"] = {"paired_dot": {"subjects": len(subjects), "conditions": conditions, "value_column": value_column}}
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _build_dumbbell_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    columns = context["columns"]
    numeric_columns = context["numeric_columns"]
    label_column = _requested_column(params.get("label_column"), columns) or _find_column(
        columns, ["feature", "gene", "symbol", "term", "description", "name", "sample", "id"]
    )
    start_column = _requested_column(params.get("start_column"), numeric_columns) or _find_column(
        numeric_columns, ["before", "baseline", "control", "start", "pre", "condition_a", "group_a"]
    )
    end_column = _requested_column(params.get("end_column"), numeric_columns) or _find_column(
        numeric_columns, ["after", "case", "treated", "end", "post", "condition_b", "group_b"]
    )
    if not start_column and numeric_columns:
        start_column = numeric_columns[0]
    if not end_column and len(numeric_columns) > 1:
        end_column = numeric_columns[1]
    group_column = _requested_column(params.get("group"), columns)
    if not start_column or not end_column or start_column == end_column:
        return _empty_plot_spec("dumbbell", "Dumbbell requires two different numeric columns.", context["table_summary"])

    rows = []
    for index, row in enumerate(context["records"]):
        start_value = _number_or_none(row.get(start_column))
        end_value = _number_or_none(row.get(end_column))
        if start_value is None or end_value is None:
            continue
        label = str(row.get(label_column) or f"row {index + 1}") if label_column else f"row {index + 1}"
        group = str(row.get(group_column) or "All") if group_column else "All"
        rows.append(
            {
                "label": label,
                "start": start_value,
                "end": end_value,
                "delta": end_value - start_value,
                "group": group,
                "input_index": index,
            }
        )
    if not rows:
        return _empty_plot_spec("dumbbell", "No finite paired values were available for dumbbell rendering.", context["table_summary"])

    sort_by = str(params.get("sort_by") or "delta_abs")
    if sort_by == "delta_desc":
        rows.sort(key=lambda item: item["delta"], reverse=True)
    elif sort_by == "delta_asc":
        rows.sort(key=lambda item: item["delta"])
    elif sort_by == "start":
        rows.sort(key=lambda item: item["start"], reverse=True)
    elif sort_by == "end":
        rows.sort(key=lambda item: item["end"], reverse=True)
    elif sort_by == "input":
        rows.sort(key=lambda item: item["input_index"])
    else:
        rows.sort(key=lambda item: abs(item["delta"]), reverse=True)

    top_n = _bounded_int(params.get("top_n"), 40, 1, 5000)
    warnings = []
    if len(rows) > top_n:
        warnings.append(f"Showing top {top_n} dumbbell pairs ranked by {sort_by}.")
        rows = rows[:top_n]

    is_horizontal = str(params.get("orientation") or "horizontal") == "horizontal"
    labels = [row["label"] for row in rows]
    start_values = [row["start"] for row in rows]
    end_values = [row["end"] for row in rows]
    deltas = [row["delta"] for row in rows]
    groups = [row["group"] for row in rows]
    precision = _bounded_int(params.get("value_precision"), 2, 0, 6)
    start_label = str(params.get("start_label") or start_column)
    end_label = str(params.get("end_label") or end_column)
    point_alpha = _bounded_float(params.get("point_alpha"), 0.88, 0.05, 1)
    point_size = _bounded_float(params.get("point_size"), 10, 2, 64)
    line_width = _bounded_float(params.get("line_width"), 1.6, 0.2, 8)
    line_color = str(params.get("line_color") or "#9aaab7")
    color_by_group = bool(group_column and _truthy(params.get("color_by_group"), False))
    line_traces = _dumbbell_line_traces(
        rows,
        is_horizontal=is_horizontal,
        color_by_group=color_by_group,
        line_color=line_color,
        line_width=line_width,
    )
    common_customdata = [[delta, group] for delta, group in zip(deltas, groups, strict=False)]
    hover_prefix = "%{y}" if is_horizontal else "%{x}"
    start_trace = {
        "type": "scatter",
        "mode": "markers",
        "name": start_label,
        "x": start_values if is_horizontal else labels,
        "y": labels if is_horizontal else start_values,
        "customdata": common_customdata,
        "marker": {
            "size": point_size,
            "color": str(params.get("start_color") or "#315fd6"),
            "opacity": point_alpha,
            "line": {"color": "#ffffff", "width": 0.7},
        },
        "hovertemplate": (
            f"{hover_prefix}<br>{start_label}=%{{x:.4g}}<br>delta=%{{customdata[0]:.4g}}<br>group=%{{customdata[1]}}<extra></extra>"
            if is_horizontal
            else f"{hover_prefix}<br>{start_label}=%{{y:.4g}}<br>delta=%{{customdata[0]:.4g}}<br>group=%{{customdata[1]}}<extra></extra>"
        ),
    }
    end_trace = {
        "type": "scatter",
        "mode": "markers+text" if _truthy(params.get("show_delta_labels"), False) else "markers",
        "name": end_label,
        "x": end_values if is_horizontal else labels,
        "y": labels if is_horizontal else end_values,
        "customdata": common_customdata,
        "marker": {
            "size": point_size,
            "color": str(params.get("end_color") or "#c44f3a"),
            "opacity": point_alpha,
            "line": {"color": "#ffffff", "width": 0.7},
        },
        "hovertemplate": (
            f"{hover_prefix}<br>{end_label}=%{{x:.4g}}<br>delta=%{{customdata[0]:.4g}}<br>group=%{{customdata[1]}}<extra></extra>"
            if is_horizontal
            else f"{hover_prefix}<br>{end_label}=%{{y:.4g}}<br>delta=%{{customdata[0]:.4g}}<br>group=%{{customdata[1]}}<extra></extra>"
        ),
    }
    if _truthy(params.get("show_delta_labels"), False):
        end_trace["text"] = [f"{delta:+.{precision}f}" for delta in deltas]
        end_trace["textposition"] = "middle right" if is_horizontal else "top center"

    layout = _base_layout(
        title=f"Dumbbell: {start_label} vs {end_label}",
        x_title=f"{start_column} / {end_column}" if is_horizontal else label_column or "feature",
        y_title=(label_column or "feature") if is_horizontal else f"{start_column} / {end_column}",
        params=params,
    )
    layout["xaxis"]["automargin"] = True
    layout["yaxis"]["automargin"] = True
    if is_horizontal:
        layout["yaxis"]["autorange"] = "reversed"
    elif len(rows) > 24:
        layout["xaxis"]["tickangle"] = _bounded_float(params.get("x_tick_angle"), -45, -90, 90)
    layout["meta"] = {
        "dumbbell": {
            "rows": len(rows),
            "label_column": label_column,
            "start_column": start_column,
            "end_column": end_column,
            "group_column": group_column,
        }
    }
    return {"data": [*line_traces, start_trace, end_trace], "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _dumbbell_line_traces(
    rows: list[dict[str, Any]],
    *,
    is_horizontal: bool,
    color_by_group: bool,
    line_color: str,
    line_width: float,
) -> list[dict[str, Any]]:
    grouped_rows: dict[str, list[dict[str, Any]]] = {}
    if color_by_group:
        for row in rows:
            grouped_rows.setdefault(str(row.get("group") or "All"), []).append(row)
    else:
        grouped_rows = {"paired shift": rows}

    traces = []
    for index, (group_name, group_rows) in enumerate(grouped_rows.items()):
        line_x: list[Any] = []
        line_y: list[Any] = []
        for row in group_rows:
            if is_horizontal:
                line_x.extend([row["start"], row["end"], None])
                line_y.extend([row["label"], row["label"], None])
            else:
                line_x.extend([row["label"], row["label"], None])
                line_y.extend([row["start"], row["end"], None])
        traces.append(
            {
                "type": "scatter",
                "mode": "lines",
                "name": f"shift: {group_name}" if color_by_group else "paired shift",
                "x": line_x,
                "y": line_y,
                "line": {
                    "color": PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)] if color_by_group else line_color,
                    "width": line_width,
                },
                "hoverinfo": "skip",
                "showlegend": color_by_group,
            }
        )
    return traces


def _jittered_condition(condition: str, condition_index: dict[str, int], subject: str, jitter: float) -> str | float:
    if jitter <= 0:
        return condition
    base = condition_index[condition]
    offset = ((sum(ord(char) for char in subject + condition) % 100) / 99 - 0.5) * jitter
    return base + offset


def _paired_summary_by_condition(
    subjects: list[str],
    subject_rows: dict[str, list[dict[str, Any]]],
    conditions: list[str],
    summary_stat: str,
) -> dict[str, float]:
    result = {}
    for condition in conditions:
        values = [
            item["value"]
            for subject in subjects
            for item in subject_rows[subject]
            if item["condition"] == condition
        ]
        if not values:
            continue
        result[condition] = median(values) if summary_stat == "median" else fmean(values)
    return result


def _volcano_label_trace(grouped: dict[str, list[dict[str, Any]]], params: dict[str, Any]) -> dict[str, Any] | None:
    label_top_n = _bounded_int(params.get("label_top_n"), 20, 0, 200)
    label_mode = str(params.get("label_mode") or "significant")
    if label_top_n <= 0 or label_mode == "none":
        return None
    if label_mode == "top_p":
        candidates = [point for points in grouped.values() for point in points if point.get("gene")]
    else:
        candidates = [point for group_name in ("Up", "Down") for point in grouped.get(group_name, []) if point.get("gene")]
    candidates.sort(key=lambda point: (point["p_value"], -abs(point["x"])))
    selected = candidates[:label_top_n]
    if not selected:
        return None
    return {
        "type": "scatter",
        "mode": "text",
        "name": "Gene labels",
        "x": [point["x"] for point in selected],
        "y": [point["y"] for point in selected],
        "text": [point["gene"] for point in selected],
        "textposition": [
            "middle right" if point["x"] >= 0 else "middle left"
            for point in selected
        ],
        "textfont": {
            "size": _bounded_int(params.get("label_font_size"), _bounded_int(params.get("font_size"), 13, 8, 28) - 1, 6, 24),
            "color": "#172331",
        },
        "hovertemplate": "%{text}<br>log2FC=%{x:.3g}<br>-log10(p)=%{y:.3g}<extra>label</extra>",
        "showlegend": False,
    }


def _build_upset_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    item_column = _requested_column(params.get("item_id"), context["columns"]) or _best_label_column(context["columns"])
    max_sets = _bounded_int(params.get("max_sets"), 8, 2, 20)
    set_columns = _set_membership_columns(context, params, item_column=item_column, limit=max_sets)
    if not item_column or len(set_columns) < 2:
        return _empty_plot_spec("upset", "UpSet requires an item ID column and at least two set membership columns.", context["table_summary"])

    min_intersection = _bounded_int(params.get("min_intersection_size"), 1, 1, 1000)
    intersections: dict[tuple[str, ...], set[str]] = {}
    set_totals = {column: 0 for column in set_columns}
    for row in context["records"]:
        item_id = str(row.get(item_column) or "").strip()
        if not item_id:
            continue
        memberships = tuple(column for column in set_columns if _truthy_membership(row.get(column)))
        if not memberships:
            continue
        for column in memberships:
            set_totals[column] += 1
        intersections.setdefault(memberships, set()).add(item_id)
    rows = [
        {"sets": sets, "count": len(items), "items": sorted(items)[:8]}
        for sets, items in intersections.items()
        if len(items) >= min_intersection
    ]
    sort_by = str(params.get("sort_by") or "intersection_size")
    if sort_by == "degree":
        rows.sort(key=lambda item: (len(item["sets"]), item["count"], "+".join(item["sets"])), reverse=True)
    elif sort_by == "set_name":
        rows.sort(key=lambda item: "+".join(item["sets"]))
    else:
        rows.sort(key=lambda item: (item["count"], len(item["sets"])), reverse=True)
    max_intersections = _bounded_int(params.get("max_intersections"), 40, 5, 120)
    if len(rows) > max_intersections:
        rows = rows[:max_intersections]
    if not rows:
        return _empty_plot_spec("upset", "No set intersections passed the current filters.", context["table_summary"])

    intersection_labels = [_intersection_label(row["sets"]) for row in rows]
    x_labels = [f"I{index + 1}" for index in range(len(rows))]
    bar_trace = {
        "type": "bar",
        "name": "Intersection size",
        "x": x_labels,
        "y": [row["count"] for row in rows],
        "text": [row["count"] for row in rows],
        "textposition": "outside",
        "cliponaxis": False,
        "marker": {"color": "#315fd6", "line": {"color": "#183f99", "width": 1}},
        "customdata": [
            [intersection_labels[index], ", ".join(row["items"]), len(row["sets"])]
            for index, row in enumerate(rows)
        ],
        "hovertemplate": "%{customdata[0]}<br>count=%{y}<br>degree=%{customdata[2]}<br>items=%{customdata[1]}<extra></extra>",
    }
    matrix_traces = []
    line_traces = []
    for set_index, set_name in enumerate(set_columns):
        matrix_traces.append(
            {
                "type": "scatter",
                "mode": "markers",
                "name": set_name,
                "x": x_labels,
                "y": [set_name for _ in rows],
                "xaxis": "x2",
                "yaxis": "y2",
                "customdata": [[intersection_labels[index]] for index in range(len(rows))],
                "marker": {
                    "size": [11 if set_name in row["sets"] else 5 for row in rows],
                    "color": ["#07131f" if set_name in row["sets"] else "#d7e1ea" for row in rows],
                    "line": {"color": "#ffffff", "width": 0.6},
                },
                "hovertemplate": f"{set_name}<br>%{{customdata[0]}}<extra></extra>",
                "showlegend": False,
            }
        )
    for label, row in zip(x_labels, rows, strict=False):
        active_sets = [set_name for set_name in set_columns if set_name in row["sets"]]
        if len(active_sets) > 1:
            line_traces.append(
                {
                    "type": "scatter",
                    "mode": "lines",
                    "x": [label, label],
                    "y": [active_sets[0], active_sets[-1]],
                    "xaxis": "x2",
                    "yaxis": "y2",
                    "line": {"color": "#07131f", "width": 1.1},
                    "hoverinfo": "skip",
                    "showlegend": False,
                }
            )
    set_size_trace = {
        "type": "bar",
        "orientation": "h",
        "name": "Set size",
        "x": [set_totals[set_name] for set_name in set_columns],
        "y": set_columns,
        "xaxis": "x3",
        "yaxis": "y3",
        "marker": {"color": "#0052d9"},
        "hovertemplate": "%{y}<br>set size=%{x}<extra></extra>",
        "showlegend": False,
    }
    layout = _base_layout(title=f"UpSet: {len(rows)} intersections", x_title="", y_title="intersection size", params=params)
    layout["title"].update({"y": 0.94, "yanchor": "top", "pad": {"t": 0, "b": 12}})
    layout["height"] = max(int(layout.get("height") or 760), 740)
    layout["margin"].update({"l": 96, "r": 40, "t": 96, "b": 76})
    layout.update(
        {
            "grid": {"rows": 2, "columns": 2, "pattern": "independent"},
            "xaxis": {
                "domain": [0.24, 1.0],
                "anchor": "y",
                "tickangle": 0,
                "tickmode": "array",
                "tickvals": x_labels,
                "ticktext": x_labels,
                "title": "Intersection",
                "automargin": True,
            },
            "yaxis": {"domain": [0.58, 0.98], "anchor": "x", "title": "Intersection size", "rangemode": "tozero"},
            "xaxis2": {
                "domain": [0.24, 1.0],
                "anchor": "y2",
                "tickangle": 0,
                "tickmode": "array",
                "tickvals": x_labels,
                "ticktext": x_labels,
                "title": "Intersection",
                "showgrid": True,
                "gridcolor": "#eef3f6",
            },
            "yaxis2": {
                "domain": [0.14, 0.50],
                "anchor": "x2",
                "categoryorder": "array",
                "categoryarray": set_columns[::-1],
                "automargin": True,
            },
            "xaxis3": {"domain": [0.0, 0.18], "anchor": "y3", "title": "Set size", "autorange": "reversed"},
            "yaxis3": {
                "domain": [0.14, 0.50],
                "anchor": "x3",
                "categoryorder": "array",
                "categoryarray": set_columns[::-1],
                "automargin": True,
            },
            "bargap": 0.24,
            "showlegend": False,
        }
    )
    warnings = []
    if len(intersections) > len(rows):
        warnings.append(f"Showing top {len(rows)} intersections after filtering.")
    return {
        "data": [bar_trace, *line_traces, *matrix_traces, set_size_trace],
        "layout": layout,
        "config": _plotly_config(params),
        "warnings": warnings,
    }


def _build_venn_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    item_column = _requested_column(params.get("item_id"), context["columns"]) or _best_label_column(context["columns"])
    set_columns = _set_membership_columns(
        context,
        params,
        item_column=item_column,
        limit=_bounded_int(params.get("max_sets"), 4, 2, 4),
    )
    if not item_column or len(set_columns) < 2:
        return _empty_plot_spec("venn", "Venn requires an item ID column and two to four set membership columns.", context["table_summary"])

    intersections: dict[tuple[str, ...], set[str]] = {}
    total_items: set[str] = set()
    for row in context["records"]:
        item_id = str(row.get(item_column) or "").strip()
        if not item_id:
            continue
        memberships = tuple(column for column in set_columns if _truthy_membership(row.get(column)))
        if not memberships:
            continue
        total_items.add(item_id)
        intersections.setdefault(memberships, set()).add(item_id)
    if not intersections:
        return _empty_plot_spec("venn", "No set memberships were detected for Venn rendering.", context["table_summary"])

    circle_layout = _venn_circle_layout(set_columns)
    shapes = []
    for index, set_name in enumerate(set_columns):
        center_x, center_y = circle_layout[set_name]
        color = PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)]
        shapes.append(
            {
                "type": "circle",
                "xref": "x",
                "yref": "y",
                "x0": center_x - 1.0,
                "x1": center_x + 1.0,
                "y0": center_y - 1.0,
                "y1": center_y + 1.0,
                "fillcolor": color,
                "opacity": 0.24,
                "line": {"color": color, "width": 2},
                "layer": "below",
            }
        )

    show_counts = _truthy(params.get("show_counts"), True)
    show_percent = _truthy(params.get("show_percent"), False)
    label_x = []
    label_y = []
    label_text = []
    label_hover = []
    denominator = max(len(total_items), 1)
    for memberships, items in sorted(intersections.items(), key=lambda item: (len(item[0]), item[0])):
        x_value, y_value = _venn_label_position(memberships, circle_layout)
        count = len(items)
        parts = []
        if show_counts:
            parts.append(str(count))
        if show_percent:
            parts.append(f"{count / denominator:.1%}")
        label_x.append(x_value)
        label_y.append(y_value)
        label_text.append("<br>".join(parts) if parts else _intersection_label(memberships))
        label_hover.append(f"{_intersection_label(memberships)}<br>count={count}<br>items={', '.join(sorted(items)[:8])}")

    set_label_x = []
    set_label_y = []
    set_label_text = []
    for set_name in set_columns:
        center_x, center_y = circle_layout[set_name]
        set_label_x.append(center_x)
        set_label_y.append(center_y + 1.12)
        set_label_text.append(set_name)

    label_trace = {
        "type": "scatter",
        "mode": "text",
        "name": "Intersection labels",
        "x": label_x,
        "y": label_y,
        "text": label_text,
        "customdata": label_hover,
        "textfont": {"size": _bounded_int(params.get("font_size"), 13, 8, 28), "color": "#07131f"},
        "hovertemplate": "%{customdata}<extra></extra>",
        "showlegend": False,
    }
    set_trace = {
        "type": "scatter",
        "mode": "text",
        "name": "Set labels",
        "x": set_label_x,
        "y": set_label_y,
        "text": set_label_text,
        "textfont": {"size": 13, "color": "#24323f"},
        "hoverinfo": "skip",
        "showlegend": False,
    }
    layout = _base_layout(title=f"Venn: {len(set_columns)} sets", x_title="", y_title="", params=params)
    layout.update(
        {
            "shapes": shapes,
            "xaxis": {"visible": False, "range": [-2.25, 2.25], "scaleanchor": "y", "scaleratio": 1},
            "yaxis": {"visible": False, "range": [-1.9, 2.0]},
            "showlegend": False,
            "plot_bgcolor": "rgba(0,0,0,0)" if params.get("background") == "transparent" else "#ffffff",
        }
    )
    warnings = []
    if len(set_columns) == 4:
        warnings.append("Four-set Venn is an approximate sketch; use UpSet for publication-grade complex intersections.")
    return {"data": [label_trace, set_trace], "layout": layout, "config": _plotly_config(params), "warnings": warnings}


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
    cluster_warning: str | None = None
    row_cluster = _cluster_vectors(z_values, params) if _truthy(params.get("cluster_rows"), True) else None
    if row_cluster:
        labels = [labels[index] for index in row_cluster["order"]]
        z_values = [z_values[index] for index in row_cluster["order"]]
    elif _truthy(params.get("cluster_rows"), True) and len(z_values) > 180:
        cluster_warning = "Row clustering skipped for more than 180 rows to keep interactive rendering responsive."
    column_cluster = _cluster_vectors(_transpose(z_values), params) if _truthy(params.get("cluster_columns"), True) else None
    if column_cluster:
        numeric_columns = [numeric_columns[index] for index in column_cluster["order"]]
        z_values = [[row[index] for index in column_cluster["order"]] for row in z_values]
    trace = {
        "type": "heatmap",
        "x": numeric_columns,
        "y": labels,
        "z": z_values,
        "colorscale": _colorscale(str(params.get("palette") or "blue_red")),
        "colorbar": {"title": scale},
        "hovertemplate": "row=%{y}<br>column=%{x}<br>value=%{z:.4g}<extra></extra>",
        "xgap": _bounded_int(params.get("cell_gap"), 1, 0, 8),
        "ygap": _bounded_int(params.get("cell_gap"), 1, 0, 8),
    }
    warnings = []
    if _truthy(params.get("show_values"), False):
        if len(labels) * len(numeric_columns) <= 900:
            precision = _bounded_int(params.get("value_precision"), 2, 0, 6)
            trace["text"] = [[f"{value:.{precision}f}" for value in row] for row in z_values]
            trace["texttemplate"] = "%{text}"
            trace["textfont"] = {"size": max(8, _bounded_int(params.get("font_size"), 13, 8, 28) - 2), "color": "#172331"}
        else:
            warnings.append("Heatmap cell value labels were hidden because more than 900 cells are displayed.")
    layout = _base_layout(
        title=f"Heatmap: top {len(labels)} variable rows",
        x_title="sample / numeric column",
        y_title=row_id_column or "row",
        params=params,
    )
    if params.get("height") in {None, ""}:
        layout["height"] = max(520, min(1800, 220 + len(labels) * 14))
    layout["yaxis"]["automargin"] = True
    layout["xaxis"]["automargin"] = True
    if _truthy(params.get("show_dendrogram"), True):
        _attach_dendrogram_guides(layout, row_cluster, column_cluster, row_count=len(labels), column_count=len(numeric_columns))
    if len(context["records"]) > len(matrix_rows):
        warnings.append(f"Showing top {len(matrix_rows)} rows ranked by variance.")
    if cluster_warning:
        warnings.append(cluster_warning)
    return {"data": [trace], "layout": layout, "config": _plotly_config(params), "warnings": warnings}


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
    cluster_rows = _truthy(params.get("cluster_rows"), True)
    cluster_columns = _truthy(params.get("cluster_columns"), True)
    cluster_result = _cluster_vectors(z_values, params) if cluster_rows or cluster_columns else None
    if cluster_result:
        order = cluster_result["order"]
        numeric_columns = [numeric_columns[index] for index in order]
        z_values = [[row[index] for index in order] for row in [z_values[index] for index in order]]

    matrix_type = str(params.get("matrix_type") or "full")
    z_display_values, masked_cells = _correlation_matrix_display_values(z_values, matrix_type)
    trace = {
        "type": "heatmap",
        "x": numeric_columns,
        "y": numeric_columns,
        "z": z_display_values,
        "zmin": -1,
        "zmax": 1,
        "colorscale": _colorscale(str(params.get("color_scale") or "blue_white_red")),
        "colorbar": {"title": "r"},
        "hovertemplate": "%{y} vs %{x}<br>r=%{z:.3f}<extra></extra>",
        "xgap": _bounded_int(params.get("cell_gap"), 1, 0, 8),
        "ygap": _bounded_int(params.get("cell_gap"), 1, 0, 8),
    }
    warnings = []
    if _truthy(params.get("show_values"), False):
        if len(numeric_columns) <= 40:
            precision = _bounded_int(params.get("value_precision"), 2, 0, 4)
            trace["text"] = [
                ["" if value is None else f"{value:.{precision}f}" for value in row]
                for row in z_display_values
            ]
            trace["texttemplate"] = "%{text}"
            trace["textfont"] = {"size": 10, "color": "#152433"}
        else:
            warnings.append("Correlation r-value labels were hidden because more than 40 columns are displayed.")
    layout = _base_layout(
        title=f"{method.title()} correlation heatmap",
        x_title="numeric column",
        y_title="numeric column",
        params=params,
    )
    if params.get("height") in {None, ""}:
        layout["height"] = max(560, min(1800, 220 + len(numeric_columns) * 13))
    layout["xaxis"]["automargin"] = True
    layout["yaxis"]["automargin"] = True
    _attach_dendrogram_guides(
        layout,
        cluster_result if cluster_rows else None,
        cluster_result if cluster_columns else None,
        row_count=len(numeric_columns),
        column_count=len(numeric_columns),
    )
    if len(context["numeric_columns"]) > len(numeric_columns):
        warnings.append(f"Showing first {len(numeric_columns)} numeric columns to keep correlation readable.")
    if masked_cells:
        warnings.append(f"{matrix_type.replace('_', ' ')} display hides {masked_cells} redundant correlation cells.")
    return {"data": [trace], "layout": layout, "config": _plotly_config(params), "warnings": warnings}


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

    color_transform = str(params.get("color_transform") or "minus_log10")
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
                "raw_color": color_value if color_value is not None else x_value,
            }
        )
    if not rows:
        return _empty_plot_spec("enrichment_dot", "No valid enrichment rows were available.", context["table_summary"])

    sort_by = str(params.get("sort_by") or color_column or x_column)
    if "p" in sort_by.lower() or sort_by == color_column:
        rows.sort(key=lambda item: item["raw_color"])
    elif sort_by in {"count", "size"} or sort_by == size_column:
        rows.sort(key=lambda item: item["size"], reverse=True)
    else:
        rows.sort(key=lambda item: item["x"], reverse=True)
    top_n = _bounded_int(params.get("top_n"), 20, 5, 200)
    rows = rows[:top_n]
    max_size = max(item["size"] for item in rows) or 1.0
    min_dot_size = _bounded_float(params.get("min_dot_size"), 8, 2, 60)
    max_dot_size = _bounded_float(params.get("max_dot_size"), 38, min_dot_size, 120)
    marker_sizes = [min_dot_size + item["size"] / max_size * (max_dot_size - min_dot_size) for item in rows]
    color_values = [_enrichment_color_value(item["raw_color"], color_transform) for item in rows]
    term_labels = [
        _wrap_text_label(item["term"], _bounded_int(params.get("term_label_width"), 26, 8, 100))
        if _truthy(params.get("wrap_term_label"), True)
        else item["term"]
        for item in rows
    ]
    colorbar_title = f"-log10({color_column})" if color_transform == "minus_log10" and color_column else color_column or x_column
    trace = {
        "type": "scatter",
        "mode": "markers",
        "x": [item["x"] for item in rows],
        "y": term_labels,
        "marker": {
            "size": marker_sizes,
            "color": color_values,
            "colorscale": _colorscale(str(params.get("color_scale") or "viridis")),
            "showscale": True,
            "colorbar": {"title": colorbar_title},
            "line": {"color": "#ffffff", "width": 1},
            "opacity": _bounded_float(params.get("point_alpha"), 0.86, 0.05, 1),
        },
        "text": [item["term"] for item in rows],
        "customdata": [[item["size"], item["raw_color"], color_values[index]] for index, item in enumerate(rows)],
        "hovertemplate": "%{text}<br>x=%{x:.4g}<br>size=%{customdata[0]:.4g}<br>raw color=%{customdata[1]:.4g}<br>display color=%{customdata[2]:.4g}<extra></extra>",
    }
    layout = _base_layout(
        title=f"Enrichment dot plot: top {len(rows)} terms",
        x_title=x_column,
        y_title=term_column,
        params=params,
    )
    if params.get("height") in {None, ""}:
        layout["height"] = max(520, min(1600, 180 + len(rows) * 24))
    layout["yaxis"]["automargin"] = True
    warnings = []
    if len(context["records"]) > len(rows):
        warnings.append(f"Showing top {len(rows)} enrichment terms.")
    return {"data": [trace], "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _build_enrichment_bar_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    columns = context["columns"]
    term_column = _requested_column(params.get("term_column"), columns) or _find_column(
        columns, ["term", "description", "pathway", "name"]
    )
    ratio_column = _requested_column(params.get("value_column"), columns) or _find_column(
        columns, ["gene_ratio", "ratio", "rich_factor", "enrichment_score"]
    )
    count_column = _find_column(columns, ["count", "gene_count", "size", "number"])
    color_column = _requested_column(params.get("color_column"), columns) or _find_column(
        columns, ["adjusted_p", "padj", "p_adjust", "p_value", "pvalue", "score"]
    )
    bar_mode = str(params.get("bar_value") or "count")
    if bar_mode == "count" and count_column:
        value_column = count_column
    elif bar_mode == "score" and color_column:
        value_column = color_column
    else:
        value_column = ratio_column
    if not term_column or not value_column:
        return _empty_plot_spec("enrichment_bar", "Enrichment bar plot requires term and numeric value columns.", context["table_summary"])

    color_transform = str(params.get("color_transform") or "minus_log10")
    rows = []
    for row in context["records"]:
        term = str(row.get(term_column) or "").strip()
        value = _number_or_ratio(row.get(value_column))
        if not term or value is None:
            continue
        ratio = _number_or_ratio(row.get(ratio_column)) if ratio_column else None
        count = _number_or_none(row.get(count_column)) if count_column else None
        raw_color = _number_or_none(row.get(color_column)) if color_column else None
        rows.append(
            {
                "term": term,
                "value": value,
                "ratio": ratio if ratio is not None else value,
                "count": count if count is not None else value,
                "raw_color": raw_color if raw_color is not None else value,
                "display_color": _enrichment_color_value(raw_color, color_transform) if raw_color is not None else value,
            }
        )
    if not rows:
        return _empty_plot_spec("enrichment_bar", "No valid enrichment bar rows were available.", context["table_summary"])

    sort_by = str(params.get("sort_by") or "adjusted_p")
    if "p" in sort_by.lower() and color_column:
        rows.sort(key=lambda item: item["raw_color"])
    elif sort_by == "count":
        rows.sort(key=lambda item: item["count"], reverse=True)
    elif sort_by in {"gene_ratio", "value"}:
        rows.sort(key=lambda item: item["value"], reverse=True)
    else:
        rows.sort(key=lambda item: item["value"], reverse=True)
    top_n = _bounded_int(params.get("top_n"), 20, 5, 200)
    rows = rows[:top_n]

    wrap_labels = _truthy(params.get("wrap_term_label"), True)
    label_width = _bounded_int(params.get("term_label_width"), 28, 8, 100)
    labels = [
        _wrap_text_label(row["term"], label_width) if wrap_labels else row["term"]
        for row in rows
    ]
    values = [row["value"] for row in rows]
    precision = _bounded_int(params.get("value_precision"), 2, 0, 6)
    text = [f"{value:.{precision}f}" for value in values] if _truthy(params.get("show_value_labels"), True) else []
    colorbar_title = f"-log10({color_column})" if color_transform == "minus_log10" and color_column else color_column or value_column
    orientation = str(params.get("orientation") or "horizontal")
    trace: dict[str, Any] = {
        "type": "bar",
        "orientation": "h" if orientation == "horizontal" else "v",
        "marker": {
            "color": [row["display_color"] for row in rows],
            "colorscale": _colorscale(str(params.get("color_scale") or "viridis")),
            "showscale": True,
            "colorbar": {"title": colorbar_title},
            "opacity": _bounded_float(params.get("bar_opacity"), 0.88, 0.05, 1),
            "line": {
                "color": str(params.get("bar_line_color") or "#ffffff"),
                "width": _bounded_float(params.get("bar_line_width"), 0.6, 0, 4),
            },
        },
        "text": text,
        "textposition": "outside",
        "customdata": [[row["term"], row["ratio"], row["count"], row["raw_color"]] for row in rows],
        "hovertemplate": "%{customdata[0]}<br>value=%{x:.4g}<br>ratio=%{customdata[1]:.4g}<br>count=%{customdata[2]:.4g}<br>raw color=%{customdata[3]:.4g}<extra></extra>",
    }
    if orientation == "horizontal":
        trace["x"] = values
        trace["y"] = labels
        layout = _base_layout(
            title=f"Enrichment bar plot: top {len(rows)} terms",
            x_title=value_column,
            y_title=term_column,
            params=params,
        )
        layout["yaxis"]["automargin"] = True
        layout["yaxis"]["autorange"] = "reversed"
    else:
        trace["x"] = labels
        trace["y"] = values
        trace["hovertemplate"] = "%{customdata[0]}<br>value=%{y:.4g}<br>ratio=%{customdata[1]:.4g}<br>count=%{customdata[2]:.4g}<br>raw color=%{customdata[3]:.4g}<extra></extra>"
        layout = _base_layout(
            title=f"Enrichment bar plot: top {len(rows)} terms",
            x_title=term_column,
            y_title=value_column,
            params=params,
        )
        layout["xaxis"]["automargin"] = True
    if params.get("height") in {None, ""}:
        layout["height"] = max(520, min(1600, 180 + len(rows) * 24))
    layout["bargap"] = 0.24
    warnings = []
    if len(context["records"]) > len(rows):
        warnings.append(f"Showing top {len(rows)} enrichment bars.")
    return {"data": [trace], "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _build_treemap_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    columns = context["columns"]
    label_column = _requested_column(params.get("label_column"), columns) or _find_column(
        columns, ["term", "description", "pathway", "name", "label"]
    )
    value_column = _requested_column(params.get("value_column"), columns) or _find_column(
        columns, ["count", "gene_count", "size", "value", "number"]
    )
    parent_column = _requested_column(params.get("parent_column"), columns) or _find_column(
        columns, ["category", "ontology", "class", "parent", "group"]
    )
    color_column = _requested_column(params.get("color_column"), columns) or _find_column(
        columns, ["adjusted_p", "padj", "p_adjust", "p_value", "pvalue", "score"]
    )
    if not label_column or not value_column:
        return _empty_plot_spec("treemap", "Treemap requires label and positive value columns.", context["table_summary"])

    color_transform = str(params.get("color_transform") or "minus_log10")
    rows = []
    for row in context["records"]:
        label = str(row.get(label_column) or "").strip()
        value = _number_or_ratio(row.get(value_column))
        if not label or value is None or value <= 0:
            continue
        parent = str(row.get(parent_column) or "").strip() if parent_column else ""
        raw_color = _number_or_none(row.get(color_column)) if color_column else None
        rows.append(
            {
                "label": label,
                "value": value,
                "parent": parent,
                "raw_color": raw_color if raw_color is not None else value,
            }
        )
    if not rows:
        return _empty_plot_spec("treemap", "No valid treemap rows were available.", context["table_summary"])

    sort_by = str(params.get("sort_by") or "value")
    if sort_by == "color" and color_column:
        rows.sort(key=lambda item: item["raw_color"])
    else:
        rows.sort(key=lambda item: item["value"], reverse=True)
    top_n = _bounded_int(params.get("top_n"), 30, 5, 200)
    rows = rows[:top_n]
    wrap_labels = _truthy(params.get("wrap_term_label"), True)
    label_width = _bounded_int(params.get("term_label_width"), 22, 8, 100)

    ids: list[str] = []
    labels: list[str] = []
    parents: list[str] = []
    values: list[float] = []
    colors: list[float] = []
    hover_rows: list[list[Any]] = []
    parent_nodes: dict[str, dict[str, Any]] = {}

    for row in rows:
        parent = row["parent"]
        if parent:
            parent_id = f"parent::{parent}"
            parent_payload = parent_nodes.setdefault(parent_id, {"label": parent, "value": 0.0, "colors": []})
            parent_payload["value"] += row["value"]
            parent_payload["colors"].append(_enrichment_color_value(row["raw_color"], color_transform))

    for parent_id, payload in parent_nodes.items():
        ids.append(parent_id)
        labels.append(payload["label"])
        parents.append("")
        values.append(payload["value"])
        colors.append(fmean(payload["colors"]) if payload["colors"] else payload["value"])
        hover_rows.append([payload["label"], payload["value"], "parent"])

    for index, row in enumerate(rows):
        parent_id = f"parent::{row['parent']}" if row["parent"] else ""
        display_label = _wrap_text_label(row["label"], label_width) if wrap_labels else row["label"]
        ids.append(f"leaf::{index}::{row['label']}")
        labels.append(display_label)
        parents.append(parent_id)
        values.append(row["value"])
        colors.append(_enrichment_color_value(row["raw_color"], color_transform))
        hover_rows.append([row["label"], row["value"], row["parent"] or "root"])

    trace = {
        "type": "treemap",
        "ids": ids,
        "labels": labels,
        "parents": parents,
        "values": values,
        "branchvalues": str(params.get("branchvalues") or "total"),
        "textinfo": str(params.get("textinfo") or "label+value"),
        "tiling": {"packing": str(params.get("tiling") or "squarify")},
        "marker": {
            "colors": colors,
            "colorscale": _colorscale(str(params.get("color_scale") or "viridis")),
            "showscale": True,
            "colorbar": {
                "title": f"-log10({color_column})" if color_transform == "minus_log10" and color_column else color_column or value_column
            },
            "line": {"color": "#ffffff", "width": 1.2},
        },
        "customdata": hover_rows,
        "hovertemplate": "%{customdata[0]}<br>value=%{customdata[1]:.4g}<br>parent=%{customdata[2]}<extra></extra>",
    }
    layout = _base_layout(
        title=f"Treemap: top {len(rows)} terms",
        x_title="",
        y_title="",
        params=params,
    )
    layout.pop("xaxis", None)
    layout.pop("yaxis", None)
    layout["uniformtext"] = {"minsize": 10, "mode": "hide"}
    warnings = []
    if len(context["records"]) > len(rows):
        warnings.append(f"Showing top {len(rows)} treemap leaves.")
    if parent_nodes:
        warnings.append(f"Grouped into {len(parent_nodes)} parent categories.")
    return {"data": [trace], "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _build_sankey_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    columns = context["columns"]
    source_column = _requested_column(params.get("source_column"), columns) or _find_column(
        columns, ["source", "from", "parent", "class", "category"]
    )
    target_column = _requested_column(params.get("target_column"), columns) or _find_column(
        columns, ["target", "to", "child", "term", "description", "pathway"]
    )
    value_column = _requested_column(params.get("value_column"), columns) or _find_column(
        columns, ["value", "count", "gene_count", "size", "weight", "number"]
    )
    group_column = _requested_column(params.get("group_column"), columns)
    if not source_column or not target_column or not value_column:
        return _empty_plot_spec("sankey", "Sankey requires source, target, and positive value columns.", context["table_summary"])

    min_value = _bounded_float(params.get("min_value"), 0, 0, 1_000_000_000)
    links = []
    for row in context["records"]:
        source = str(row.get(source_column) or "").strip()
        target = str(row.get(target_column) or "").strip()
        value = _number_or_ratio(row.get(value_column))
        if not source or not target or value is None or value <= min_value:
            continue
        group = str(row.get(group_column) or source).strip() if group_column else source
        links.append({"source": source, "target": target, "value": value, "group": group})
    if not links:
        return _empty_plot_spec("sankey", "No valid Sankey links were available.", context["table_summary"])

    sort_by = str(params.get("sort_by") or "value")
    if sort_by == "source":
        links.sort(key=lambda item: (item["source"], item["target"]))
    elif sort_by == "target":
        links.sort(key=lambda item: (item["target"], item["source"]))
    else:
        links.sort(key=lambda item: item["value"], reverse=True)
    top_n = _bounded_int(params.get("top_n"), 80, 5, 500)
    links = links[:top_n]

    node_labels: list[str] = []
    node_index: dict[str, int] = {}
    for link in links:
        for label in (link["source"], link["target"]):
            if label not in node_index:
                node_index[label] = len(node_labels)
                node_labels.append(label)
    group_palette: dict[str, str] = {}
    for link in links:
        if link["group"] not in group_palette:
            group_palette[link["group"]] = PLOTLY_PALETTE[len(group_palette) % len(PLOTLY_PALETTE)]
    node_colors = [PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)] for index in range(len(node_labels))]
    link_colors = [_rgba_from_hex(group_palette[link["group"]], _bounded_float(params.get("link_opacity"), 0.38, 0.05, 1)) for link in links]

    trace = {
        "type": "sankey",
        "arrangement": _sankey_arrangement(params.get("arrangement")),
        "node": {
            "label": node_labels,
            "color": node_colors,
            "pad": _bounded_int(params.get("node_pad"), 16, 4, 80),
            "thickness": _bounded_int(params.get("node_thickness"), 18, 4, 80),
            "line": {
                "color": str(params.get("node_line_color") or "#ffffff"),
                "width": _bounded_float(params.get("node_line_width"), 0.6, 0, 6),
            },
        },
        "link": {
            "source": [node_index[link["source"]] for link in links],
            "target": [node_index[link["target"]] for link in links],
            "value": [link["value"] for link in links],
            "color": link_colors,
            "customdata": [[link["source"], link["target"], link["group"]] for link in links],
            "hovertemplate": "%{customdata[0]} -> %{customdata[1]}<br>value=%{value:.4g}<br>group=%{customdata[2]}<extra></extra>",
        },
        "textfont": {"size": _bounded_int(params.get("label_font_size"), 12, 6, 28)},
    }
    layout = _base_layout(title=f"Sankey: {len(links)} links", x_title="", y_title="", params=params)
    layout.pop("xaxis", None)
    layout.pop("yaxis", None)
    warnings = []
    if len(context["records"]) > len(links):
        warnings.append(f"Showing top {len(links)} Sankey links.")
    warnings.append(f"Resolved {len(node_labels)} unique Sankey nodes.")
    return {"data": [trace], "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _build_composition_bar_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    columns = context["columns"]
    sample_column = _requested_column(params.get("sample_column"), columns) or _find_column(
        columns, ["sample", "sample_id", "group", "condition", "name"]
    )
    category_column = _requested_column(params.get("category_column"), columns) or _find_column(
        columns, ["category", "taxon", "taxonomy", "term", "pathway", "feature", "class"]
    )
    value_column = _requested_column(params.get("value_column"), columns) or _find_column(
        columns, ["abundance", "relative_abundance", "count", "value", "size", "reads"]
    )
    group_column = _requested_column(params.get("group_column"), columns)
    if not sample_column or not category_column or not value_column:
        return _empty_plot_spec("composition_bar", "Composition bar requires sample, category, and numeric value columns.", context["table_summary"])

    matrix: dict[str, dict[str, float]] = {}
    sample_order: list[str] = []
    category_totals: dict[str, float] = {}
    raw_totals: dict[str, float] = {}
    sample_groups: dict[str, str] = {}
    for row in context["records"]:
        sample = str(row.get(sample_column) or "").strip()
        category = str(row.get(category_column) or "").strip()
        value = _number_or_ratio(row.get(value_column))
        if not sample or not category or value is None or value < 0:
            continue
        if sample not in matrix:
            matrix[sample] = {}
            sample_order.append(sample)
        matrix[sample][category] = matrix[sample].get(category, 0.0) + value
        category_totals[category] = category_totals.get(category, 0.0) + value
        raw_totals[sample] = raw_totals.get(sample, 0.0) + value
        if group_column and sample not in sample_groups:
            sample_groups[sample] = str(row.get(group_column) or "")
    if not matrix:
        return _empty_plot_spec("composition_bar", "No valid composition rows were available.", context["table_summary"])

    top_n = _bounded_int(params.get("top_n"), 12, 2, 80)
    sort_categories = str(params.get("sort_categories") or "total_desc")
    categories = sorted(category_totals, key=str.lower) if sort_categories == "name" else sorted(
        category_totals,
        key=lambda item: category_totals[item],
        reverse=True,
    )
    top_categories = categories[:top_n]
    other_label = str(params.get("other_label") or "Other")
    has_other = any(category not in top_categories for category in categories)
    display_categories = top_categories + ([other_label] if has_other else [])

    sort_samples = str(params.get("sort_samples") or "input")
    if sort_samples == "name":
        sample_order = sorted(sample_order, key=str.lower)
    elif sort_samples == "total_desc":
        sample_order = sorted(sample_order, key=lambda sample: raw_totals.get(sample, 0.0), reverse=True)

    normalize = str(params.get("normalize") or "percent")
    traces = []
    for index, category in enumerate(display_categories):
        values = []
        raw_values = []
        for sample in sample_order:
            sample_values = matrix[sample]
            if category == other_label and has_other:
                raw_value = sum(value for item, value in sample_values.items() if item not in top_categories)
            else:
                raw_value = sample_values.get(category, 0.0)
            denominator = raw_totals.get(sample, 0.0) or 1.0
            values.append(raw_value / denominator * 100 if normalize == "percent" else raw_value)
            raw_values.append(raw_value)
        customdata = [
            [sample, category, raw_values[item_index], raw_totals.get(sample, 0.0), sample_groups.get(sample, "")]
            for item_index, sample in enumerate(sample_order)
        ]
        trace: dict[str, Any] = {
            "type": "bar",
            "name": category,
            "marker": {
                "color": PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)],
                "opacity": _bounded_float(params.get("bar_opacity"), 0.9, 0.05, 1),
                "line": {
                    "color": str(params.get("bar_line_color") or "#ffffff"),
                    "width": _bounded_float(params.get("bar_line_width"), 0.4, 0, 4),
                },
            },
            "customdata": customdata,
            "hovertemplate": "%{customdata[0]}<br>category=%{fullData.name}<br>display=%{y:.4g}<br>raw=%{customdata[2]:.4g}<br>sample total=%{customdata[3]:.4g}<br>group=%{customdata[4]}<extra></extra>",
        }
        if str(params.get("orientation") or "vertical") == "horizontal":
            trace["orientation"] = "h"
            trace["x"] = values
            trace["y"] = sample_order
            trace["hovertemplate"] = "%{customdata[0]}<br>category=%{fullData.name}<br>display=%{x:.4g}<br>raw=%{customdata[2]:.4g}<br>sample total=%{customdata[3]:.4g}<br>group=%{customdata[4]}<extra></extra>"
        else:
            trace["x"] = sample_order
            trace["y"] = values
        traces.append(trace)

    y_title = "Relative abundance (%)" if normalize == "percent" else value_column
    layout = _base_layout(
        title=f"Composition bar: {len(sample_order)} samples",
        x_title=sample_column,
        y_title=y_title,
        params=params,
    )
    orientation = str(params.get("orientation") or "vertical")
    if orientation == "horizontal":
        layout["xaxis"]["title"]["text"] = y_title
        layout["yaxis"]["title"]["text"] = sample_column
        if normalize == "percent" and _truthy(params.get("show_percent_axis"), True):
            layout["xaxis"]["range"] = [0, 100]
    elif normalize == "percent" and _truthy(params.get("show_percent_axis"), True):
        layout["yaxis"]["range"] = [0, 100]
    layout["barmode"] = str(params.get("bar_mode") or "stack")
    layout["showlegend"] = _truthy(params.get("show_legend"), True)
    warnings = []
    if has_other:
        warnings.append(f"Collapsed {len(categories) - len(top_categories)} lower-abundance categories into {other_label}.")
    if normalize == "percent":
        warnings.append("Values are normalized to percent within each sample.")
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _build_donut_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    columns = context["columns"]
    category_column = _requested_column(params.get("category_column"), columns) or _find_column(
        columns, ["category", "taxon", "taxonomy", "term", "pathway", "feature", "class"]
    )
    value_column = _requested_column(params.get("value_column"), columns) or _find_column(
        columns, ["abundance", "relative_abundance", "count", "value", "size", "reads"]
    )
    group_column = _requested_column(params.get("group_column"), columns)
    selected_group = str(params.get("selected_group") or "").strip()
    if not category_column or not value_column:
        return _empty_plot_spec("donut", "Donut requires category and numeric value columns.", context["table_summary"])

    totals: dict[str, float] = {}
    scanned_rows = 0
    for row in context["records"]:
        if group_column and selected_group and str(row.get(group_column) or "").strip() != selected_group:
            continue
        category = str(row.get(category_column) or "").strip()
        value = _number_or_ratio(row.get(value_column))
        if not category or value is None or value < 0:
            continue
        scanned_rows += 1
        totals[category] = totals.get(category, 0.0) + value
    if not totals:
        return _empty_plot_spec("donut", "No valid donut composition rows were available.", context["table_summary"])

    sort_by = str(params.get("sort_by") or "value")
    categories = sorted(totals, key=str.lower) if sort_by == "name" else sorted(totals, key=lambda item: totals[item], reverse=True)
    top_n = _bounded_int(params.get("top_n"), 10, 2, 80)
    top_categories = categories[:top_n]
    labels = top_categories[:]
    values = [totals[category] for category in top_categories]
    other_count = len(categories) - len(top_categories)
    if other_count > 0:
        labels.append(str(params.get("other_label") or "Other"))
        values.append(sum(totals[category] for category in categories[top_n:]))
    pull = [0.0 for _ in labels]
    if pull and _truthy(params.get("pull_largest"), True):
        pull[0] = _bounded_float(params.get("pull_size"), 0.04, 0, 0.25)

    trace = {
        "type": "pie",
        "labels": labels,
        "values": values,
        "hole": _bounded_float(params.get("hole"), 0.48, 0, 0.8),
        "sort": False,
        "direction": "clockwise",
        "rotation": _bounded_float(params.get("rotation"), 0, 0, 360),
        "textinfo": str(params.get("textinfo") or "label+percent"),
        "textposition": str(params.get("textposition") or "auto"),
        "pull": pull,
        "marker": {
            "colors": [PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)] for index in range(len(labels))],
            "line": {"color": "#ffffff", "width": 1.2},
        },
        "customdata": [[label, value, sum(values)] for label, value in zip(labels, values)],
        "hovertemplate": "%{label}<br>value=%{value:.4g}<br>percent=%{percent}<extra></extra>",
    }
    layout = _base_layout(
        title=f"Donut composition{f': {selected_group}' if selected_group else ''}",
        x_title="",
        y_title="",
        params=params,
    )
    layout.pop("xaxis", None)
    layout.pop("yaxis", None)
    layout["showlegend"] = _truthy(params.get("show_legend"), True)
    warnings = []
    if group_column and selected_group:
        warnings.append(f"Filtered donut rows to {group_column}={selected_group}.")
    if other_count > 0:
        warnings.append(f"Collapsed {other_count} lower-value categories into {labels[-1]}.")
    warnings.append(f"Aggregated {scanned_rows} rows into {len(labels)} donut slices.")
    return {"data": [trace], "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _build_sunburst_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    hierarchy = _hierarchy_rows_for_area_chart(context, params=params, plot_type="sunburst")
    if "error" in hierarchy:
        return _empty_plot_spec("sunburst", hierarchy["error"], context["table_summary"])

    trace = {
        "type": "sunburst",
        "ids": hierarchy["ids"],
        "labels": hierarchy["labels"],
        "parents": hierarchy["parents"],
        "values": hierarchy["values"],
        "branchvalues": str(params.get("branchvalues") or "total"),
        "maxdepth": _bounded_int(params.get("maxdepth"), 3, 2, 8),
        "textinfo": str(params.get("textinfo") or "label+percent parent"),
        "marker": {
            "colors": hierarchy["colors"],
            "colorscale": _colorscale(str(params.get("color_scale") or "viridis")),
            "showscale": True,
            "colorbar": {"title": hierarchy["colorbar_title"]},
            "line": {"color": "#ffffff", "width": 1.2},
        },
        "customdata": hierarchy["hover_rows"],
        "hovertemplate": "%{customdata[0]}<br>value=%{customdata[1]:.4g}<br>parent=%{customdata[2]}<extra></extra>",
    }
    layout = _base_layout(
        title=f"Sunburst: top {hierarchy['leaf_count']} terms",
        x_title="",
        y_title="",
        params=params,
    )
    layout.pop("xaxis", None)
    layout.pop("yaxis", None)
    layout["uniformtext"] = {"minsize": 10, "mode": "hide"}
    return {"data": [trace], "layout": layout, "config": _plotly_config(params), "warnings": hierarchy["warnings"]}


def _build_wordcloud_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    columns = context["columns"]
    term_column = _requested_column(params.get("term_column"), columns) or _find_column(
        columns, ["term", "description", "pathway", "keyword", "word", "name", "label"]
    )
    weight_column = _requested_column(params.get("weight_column"), columns) or _find_column(
        columns, ["count", "gene_count", "size", "frequency", "freq", "weight", "value", "score"]
    )
    color_column = _requested_column(params.get("color_column"), columns) or _find_column(
        columns, ["adjusted_p", "padj", "p_adjust", "p_value", "pvalue", "score"]
    )
    if not term_column or not weight_column:
        return _empty_plot_spec("wordcloud", "Word cloud requires term and positive weight columns.", context["table_summary"])

    rows = []
    color_transform = str(params.get("color_transform") or "minus_log10")
    for row in context["records"]:
        term = str(row.get(term_column) or "").strip()
        weight = _number_or_ratio(row.get(weight_column))
        if not term or weight is None or weight <= 0:
            continue
        raw_color = _number_or_none(row.get(color_column)) if color_column else None
        rows.append(
            {
                "term": term,
                "weight": weight,
                "color_value": _enrichment_color_value(raw_color, color_transform) if raw_color is not None else weight,
                "raw_color": raw_color if raw_color is not None else weight,
            }
        )
    if not rows:
        return _empty_plot_spec("wordcloud", "No valid word cloud rows were available.", context["table_summary"])

    sort_by = str(params.get("sort_by") or "weight")
    if sort_by == "alphabetical":
        rows.sort(key=lambda item: item["term"].lower())
    elif sort_by == "color" and color_column:
        rows.sort(key=lambda item: item["raw_color"])
    else:
        rows.sort(key=lambda item: item["weight"], reverse=True)
    top_n = _bounded_int(params.get("top_n"), 60, 10, 300)
    rows = rows[:top_n]

    min_font = _bounded_float(params.get("min_font_size"), 12, 6, 80)
    max_font = _bounded_float(params.get("max_font_size"), 52, min_font, 140)
    weights = [row["weight"] for row in rows]
    min_weight = min(weights)
    max_weight = max(weights)
    span = max(max_weight - min_weight, 1e-9)
    cloud_width = _bounded_float(params.get("cloud_width"), 10, 4, 30)
    cloud_height = _bounded_float(params.get("cloud_height"), 6, 3, 20)
    rotate_fraction = _bounded_float(params.get("rotate_fraction"), 0.18, 0, 0.8)
    wrap_labels = _truthy(params.get("wrap_term_label"), False)
    label_width = _bounded_int(params.get("term_label_width"), 18, 8, 100)

    flat_points: list[dict[str, Any]] = []
    rotated_points: list[dict[str, Any]] = []
    denominator = max(len(rows) - 1, 1)
    for index, row in enumerate(rows):
        angle = index * 2.399963229728653
        radius = math.sqrt(index / denominator)
        x_value = math.cos(angle) * radius * cloud_width / 2
        y_value = math.sin(angle) * radius * cloud_height / 2
        size = min_font + ((row["weight"] - min_weight) / span) * (max_font - min_font)
        label = _wrap_text_label(row["term"], label_width) if wrap_labels else row["term"]
        color_rank = index / denominator
        point = {
            "x": x_value,
            "y": y_value,
            "text": label,
            "size": size,
            "color": PLOTLY_PALETTE[int(color_rank * (len(PLOTLY_PALETTE) - 1))],
            "custom": [row["term"], row["weight"], row["raw_color"], row["color_value"]],
        }
        if rotate_fraction > 0 and (index / max(len(rows), 1)) < rotate_fraction and index % 2 == 1:
            rotated_points.append(point)
        else:
            flat_points.append(point)

    traces = [
        _wordcloud_trace(flat_points, name="Horizontal labels", textangle=0),
        _wordcloud_trace(rotated_points, name="Rotated labels", textangle=-90),
    ]
    traces = [trace for trace in traces if trace["text"]]
    layout = _base_layout(
        title=f"Word cloud: top {len(rows)} terms",
        x_title="",
        y_title="",
        params=params,
    )
    layout["xaxis"].update({"visible": False, "range": [-cloud_width / 2 - 1, cloud_width / 2 + 1], "fixedrange": False})
    layout["yaxis"].update({"visible": False, "range": [-cloud_height / 2 - 1, cloud_height / 2 + 1], "scaleanchor": "x", "fixedrange": False})
    layout["showlegend"] = False
    layout["annotations"] = []
    warnings = []
    if len(context["records"]) > len(rows):
        warnings.append(f"Showing top {len(rows)} word cloud terms.")
    if color_column:
        warnings.append(f"Text color ranking uses {color_column}; hover keeps the raw value.")
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


def _wordcloud_trace(points: list[dict[str, Any]], *, name: str, textangle: int) -> dict[str, Any]:
    return {
        "type": "scatter",
        "mode": "text",
        "name": name,
        "x": [point["x"] for point in points],
        "y": [point["y"] for point in points],
        "text": [point["text"] for point in points],
        "textangle": textangle,
        "textfont": {
            "size": [point["size"] for point in points],
            "color": [point["color"] for point in points],
        },
        "customdata": [point["custom"] for point in points],
        "hovertemplate": "%{customdata[0]}<br>weight=%{customdata[1]:.4g}<br>raw color=%{customdata[2]:.4g}<br>display score=%{customdata[3]:.4g}<extra></extra>",
    }


def _hierarchy_rows_for_area_chart(
    context: dict[str, Any],
    *,
    params: dict[str, Any],
    plot_type: str,
) -> dict[str, Any]:
    columns = context["columns"]
    label_column = _requested_column(params.get("label_column"), columns) or _find_column(
        columns, ["term", "description", "pathway", "name", "label"]
    )
    value_column = _requested_column(params.get("value_column"), columns) or _find_column(
        columns, ["count", "gene_count", "size", "value", "number"]
    )
    parent_column = _requested_column(params.get("parent_column"), columns) or _find_column(
        columns, ["category", "ontology", "class", "parent", "group"]
    )
    color_column = _requested_column(params.get("color_column"), columns) or _find_column(
        columns, ["adjusted_p", "padj", "p_adjust", "p_value", "pvalue", "score"]
    )
    if not label_column or not value_column:
        return {"error": f"{plot_type.title()} requires label and positive value columns."}

    color_transform = str(params.get("color_transform") or "minus_log10")
    rows = []
    for row in context["records"]:
        label = str(row.get(label_column) or "").strip()
        value = _number_or_ratio(row.get(value_column))
        if not label or value is None or value <= 0:
            continue
        parent = str(row.get(parent_column) or "").strip() if parent_column else ""
        raw_color = _number_or_none(row.get(color_column)) if color_column else None
        rows.append(
            {
                "label": label,
                "value": value,
                "parent": parent,
                "raw_color": raw_color if raw_color is not None else value,
            }
        )
    if not rows:
        return {"error": f"No valid {plot_type} rows were available."}

    sort_by = str(params.get("sort_by") or "value")
    if sort_by == "color" and color_column:
        rows.sort(key=lambda item: item["raw_color"])
    else:
        rows.sort(key=lambda item: item["value"], reverse=True)
    top_n = _bounded_int(params.get("top_n"), 30, 5, 200)
    rows = rows[:top_n]
    wrap_labels = _truthy(params.get("wrap_term_label"), True)
    label_width = _bounded_int(params.get("term_label_width"), 22, 8, 100)

    ids: list[str] = []
    labels: list[str] = []
    parents: list[str] = []
    values: list[float] = []
    colors: list[float] = []
    hover_rows: list[list[Any]] = []
    parent_nodes: dict[str, dict[str, Any]] = {}

    for row in rows:
        parent = row["parent"]
        if parent:
            parent_id = f"parent::{parent}"
            parent_payload = parent_nodes.setdefault(parent_id, {"label": parent, "value": 0.0, "colors": []})
            parent_payload["value"] += row["value"]
            parent_payload["colors"].append(_enrichment_color_value(row["raw_color"], color_transform))

    for parent_id, payload in parent_nodes.items():
        ids.append(parent_id)
        labels.append(payload["label"])
        parents.append("")
        values.append(payload["value"])
        colors.append(fmean(payload["colors"]) if payload["colors"] else payload["value"])
        hover_rows.append([payload["label"], payload["value"], "parent"])

    for index, row in enumerate(rows):
        parent_id = f"parent::{row['parent']}" if row["parent"] else ""
        display_label = _wrap_text_label(row["label"], label_width) if wrap_labels else row["label"]
        ids.append(f"leaf::{index}::{row['label']}")
        labels.append(display_label)
        parents.append(parent_id)
        values.append(row["value"])
        colors.append(_enrichment_color_value(row["raw_color"], color_transform))
        hover_rows.append([row["label"], row["value"], row["parent"] or "root"])

    warnings = []
    if len(context["records"]) > len(rows):
        warnings.append(f"Showing top {len(rows)} {plot_type} leaves.")
    if parent_nodes:
        warnings.append(f"Grouped into {len(parent_nodes)} parent categories.")
    return {
        "ids": ids,
        "labels": labels,
        "parents": parents,
        "values": values,
        "colors": colors,
        "hover_rows": hover_rows,
        "leaf_count": len(rows),
        "warnings": warnings,
        "colorbar_title": f"-log10({color_column})" if color_transform == "minus_log10" and color_column else color_column or value_column,
    }


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
        "config": _plotly_config({}),
        "warnings": [message],
        "table_summary": table_summary,
        "renderability": _renderability_context(plot_type, message, table_summary),
        "supported_plot_types": sorted(SUPPORTED_PLOTLY_SPEC_TYPES),
    }


def _renderability_context(
    plot_type: str,
    message: str,
    table_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    row_count = int((table_summary or {}).get("scanned_rows") or (table_summary or {}).get("row_count") or 0)
    numeric_columns = list((table_summary or {}).get("numeric_columns") or [])
    categorical_columns = list((table_summary or {}).get("categorical_columns") or [])
    matrix_profile = ((table_summary or {}).get("signals") or {}).get("matrix_profile") or {}
    profile_value_columns = list(matrix_profile.get("value_columns") or [])
    current_data = [
        {"label": "Rows", "value": row_count},
        {"label": "Numeric columns", "value": len(numeric_columns)},
        {"label": "Categorical columns", "value": len(categorical_columns)},
    ]
    if profile_value_columns:
        current_data.append({"label": "Sample-like columns", "value": len(profile_value_columns)})

    return {
        "status": "blocked",
        "message": message,
        "current_data": current_data,
        "requirements": _plot_requirements(plot_type),
        "recommended_plot_ids": recommend_plot_types("", table_summary) if table_summary else [],
    }


def _plot_requirements(plot_type: str) -> list[str]:
    requirements_by_plot = {
        "scatter": ["At least two numeric columns", "At least two complete x/y observation rows"],
        "density_contour": ["At least two numeric columns", "At least three paired numeric rows for density estimation"],
        "bubble": ["At least three numeric columns", "At least two complete x/y/size rows"],
        "scatter_3d": ["At least three numeric columns", "At least two complete x/y/z rows"],
        "radar": ["At least three numeric metric columns", "At least two sample or group profiles"],
        "parallel_coordinates": ["At least three numeric dimensions", "At least two rows to compare profile paths"],
        "correlation": ["At least two numeric columns", "At least two observation rows"],
        "calendar_heatmap": ["One date column", "One numeric value column unless aggregation is count"],
        "roc_curve": ["One numeric score column", "One binary label column with positive and negative labels"],
        "pr_curve": ["One numeric score column", "One binary label column with positive and negative labels"],
        "kaplan_meier": ["One time column", "One event/censor column"],
        "paired_dot": ["One subject column", "One condition column", "At least two paired conditions"],
        "upset": ["One item ID column", "At least two set membership columns"],
        "venn": ["One item ID column", "Two to four set membership columns"],
        "sankey": ["Source column", "Target column", "Positive flow value column"],
    }
    return requirements_by_plot.get(plot_type, ["Compatible numeric/categorical mappings for this chart type"])


def _base_layout(title: str, x_title: str, y_title: str, params: dict[str, Any]) -> dict[str, Any]:
    show_grid = bool(params.get("show_grid", True))
    background = "rgba(0,0,0,0)" if params.get("background") == "transparent" else "#ffffff"
    legend_position = str(params.get("legend_position") or "right")
    legend_font_size = _bounded_int(params.get("legend_font_size"), 12, 8, 24)
    legend_title = str(params.get("legend_title") or "").strip()
    legend_background = str(params.get("legend_background") or "rgba(255,255,255,0)")
    legend_border_color = str(params.get("legend_border_color") or "rgba(0,0,0,0)")
    legend_border_width = _bounded_float(params.get("legend_border_width"), 0, 0, 6)
    font_size = _bounded_int(params.get("font_size"), 13, 8, 28)
    axis_line = bool(params.get("axis_line", True))
    axis_line_color = str(params.get("axis_line_color") or "#425466")
    axis_line_width = _bounded_float(params.get("axis_line_width"), 1.0, 0.5, 6)
    axis_mirror = _axis_mirror(params.get("axis_mirror"))
    grid_color = str(params.get("grid_color") or "#e7eef4")
    grid_width = _bounded_float(params.get("grid_width"), 1.0, 0.2, 4)
    show_zero_line = bool(params.get("show_zero_line", True))
    zero_line_color = str(params.get("zero_line_color") or "#b8c7d4")
    zero_line_width = _bounded_float(params.get("zero_line_width"), 1.0, 0.2, 6)
    resolved_title = _text_or_default(params.get("title"), title)
    subtitle = str(params.get("subtitle") or "").strip()
    title_position = str(params.get("title_position") or "left")
    title_x = 0.5 if title_position == "center" else 0.02
    title_anchor = "center" if title_position == "center" else "left"
    title_font_size = _bounded_int(params.get("title_font_size"), max(16, font_size + 3), 10, 40)
    title_color = str(params.get("title_color") or "#07131f")
    subtitle_font_size = _bounded_int(params.get("subtitle_font_size"), max(10, font_size - 1), 8, 28)
    subtitle_color = str(params.get("subtitle_color") or "#617383")
    width = _bounded_int(params.get("width"), 1200, 320, 4000)
    height = _bounded_int(params.get("height"), 760, 240, 3000)
    margin = {
        "l": _bounded_int(params.get("margin_left"), 72, 20, 300),
        "r": _bounded_int(params.get("margin_right"), 32, 10, 300),
        "t": _bounded_int(params.get("margin_top"), 72, 20, 300),
        "b": _bounded_int(params.get("margin_bottom"), 64, 20, 300),
    }
    x_tick_angle = _bounded_float(params.get("x_tick_angle"), 0, -90, 90)
    y_tick_angle = _bounded_float(params.get("y_tick_angle"), 0, -90, 90)
    axis_title_font_size = _bounded_int(params.get("axis_title_font_size"), font_size, 8, 32)
    axis_title_color = str(params.get("axis_title_color") or "#07131f")
    tick_font_size = _bounded_int(params.get("tick_font_size"), max(8, font_size - 1), 6, 28)
    tick_color = str(params.get("tick_color") or "#324657")
    tick_direction = _tick_direction(params.get("tick_direction"))
    tick_length = _bounded_float(params.get("tick_length"), 5, 0, 20)
    tick_width = _bounded_float(params.get("tick_width"), 1, 0, 6)
    tick_line_color = str(params.get("tick_line_color") or axis_line_color)
    font_family = _font_family(str(params.get("font_family") or "inter"))
    show_spikes = _truthy(params.get("show_spikes"), False)
    spike_color = str(params.get("spike_color") or "#64748b")
    spike_width = _bounded_float(params.get("spike_width"), 1.0, 0.2, 6)
    spike_dash = _dash_style(params.get("spike_dash"), default="dot")
    layout: dict[str, Any] = {
        "title": {
            "text": resolved_title,
            "x": title_x,
            "xanchor": title_anchor,
            "font": {"size": title_font_size, "color": title_color},
        },
        "font": {"family": font_family, "size": font_size, "color": "#07131f"},
        "paper_bgcolor": background,
        "plot_bgcolor": background,
        "width": width,
        "height": height,
        "margin": margin,
        "hovermode": _hover_mode(params.get("hover_mode")),
        "dragmode": _drag_mode(params.get("drag_mode")),
        "hoverlabel": {
            "bgcolor": str(params.get("hover_label_background") or "#111827"),
            "font": {
                "color": str(params.get("hover_label_color") or "#ffffff"),
                "size": _bounded_int(params.get("hover_label_font_size"), 12, 8, 24),
            },
        },
        "xaxis": {
            "title": {
                "text": _text_or_default(params.get("x_title"), x_title),
                "font": {"size": axis_title_font_size, "color": axis_title_color},
            },
            "showgrid": show_grid,
            "gridcolor": grid_color,
            "gridwidth": grid_width,
            "zeroline": show_zero_line,
            "zerolinecolor": zero_line_color,
            "zerolinewidth": zero_line_width,
            "showline": axis_line,
            "linecolor": axis_line_color,
            "linewidth": axis_line_width,
            "mirror": axis_mirror,
            "ticks": tick_direction,
            "ticklen": tick_length,
            "tickwidth": tick_width,
            "tickcolor": tick_line_color,
            "tickangle": x_tick_angle,
            "tickfont": {"size": tick_font_size, "color": tick_color},
            "showspikes": show_spikes,
            "spikecolor": spike_color,
            "spikethickness": spike_width,
            "spikedash": spike_dash,
            "spikemode": "across",
            "spikesnap": "cursor",
        },
        "yaxis": {
            "title": {
                "text": _text_or_default(params.get("y_title"), y_title),
                "font": {"size": axis_title_font_size, "color": axis_title_color},
            },
            "showgrid": show_grid,
            "gridcolor": grid_color,
            "gridwidth": grid_width,
            "zeroline": show_zero_line,
            "zerolinecolor": zero_line_color,
            "zerolinewidth": zero_line_width,
            "showline": axis_line,
            "linecolor": axis_line_color,
            "linewidth": axis_line_width,
            "mirror": axis_mirror,
            "ticks": tick_direction,
            "ticklen": tick_length,
            "tickwidth": tick_width,
            "tickcolor": tick_line_color,
            "tickangle": y_tick_angle,
            "tickfont": {"size": tick_font_size, "color": tick_color},
            "showspikes": show_spikes,
            "spikecolor": spike_color,
            "spikethickness": spike_width,
            "spikedash": spike_dash,
            "spikemode": "across",
            "spikesnap": "cursor",
        },
    }
    x_range = _axis_range(params.get("x_range_mode"), params.get("x_min"), params.get("x_max"))
    if x_range:
        layout["xaxis"]["range"] = x_range
    y_range = _axis_range(params.get("y_range_mode"), params.get("y_min"), params.get("y_max"))
    if y_range:
        layout["yaxis"]["range"] = y_range
    x_tick_count = _number_or_none(params.get("x_tick_count"))
    if x_tick_count is not None:
        layout["xaxis"]["nticks"] = _bounded_int(x_tick_count, 6, 2, 30)
    y_tick_count = _number_or_none(params.get("y_tick_count"))
    if y_tick_count is not None:
        layout["yaxis"]["nticks"] = _bounded_int(y_tick_count, 6, 2, 30)
    x_tick_format = str(params.get("x_tick_format") or "").strip()
    if x_tick_format:
        layout["xaxis"]["tickformat"] = x_tick_format
    y_tick_format = str(params.get("y_tick_format") or "").strip()
    if y_tick_format:
        layout["yaxis"]["tickformat"] = y_tick_format
    x_tick_prefix = str(params.get("x_tick_prefix") or "")
    if x_tick_prefix:
        layout["xaxis"]["tickprefix"] = x_tick_prefix
    x_tick_suffix = str(params.get("x_tick_suffix") or "")
    if x_tick_suffix:
        layout["xaxis"]["ticksuffix"] = x_tick_suffix
    y_tick_prefix = str(params.get("y_tick_prefix") or "")
    if y_tick_prefix:
        layout["yaxis"]["tickprefix"] = y_tick_prefix
    y_tick_suffix = str(params.get("y_tick_suffix") or "")
    if y_tick_suffix:
        layout["yaxis"]["ticksuffix"] = y_tick_suffix
    _attach_common_guide_lines(layout, params)
    if subtitle:
        layout.setdefault("annotations", []).append(
            {
                "text": subtitle,
                "xref": "paper",
                "yref": "paper",
                "x": title_x,
                "y": 1.08,
                "xanchor": title_anchor,
                "yanchor": "bottom",
                "showarrow": False,
                "font": {"size": subtitle_font_size, "color": subtitle_color},
            }
        )
        layout["margin"]["t"] = max(layout["margin"]["t"], 92)
    legend_style = {
        "font": {"size": legend_font_size},
        "bgcolor": legend_background,
        "bordercolor": legend_border_color,
        "borderwidth": legend_border_width,
    }
    if legend_position == "none":
        layout["showlegend"] = False
    elif legend_position == "top":
        layout["legend"] = {"orientation": "h", "x": 0, "y": 1.14, **legend_style}
    elif legend_position == "bottom":
        layout["legend"] = {"orientation": "h", "x": 0, "y": -0.22, **legend_style}
    else:
        layout["legend"] = {"orientation": "v", "x": 1.02, "y": 1, **legend_style}
    if legend_title and layout.get("legend"):
        layout["legend"]["title"] = {"text": legend_title, "font": {"size": legend_font_size}}
    return layout


def _plotly_config(params: dict[str, Any]) -> dict[str, Any]:
    export_format = str(params.get("format") or "svg")
    if export_format not in {"svg", "png", "jpeg", "webp"}:
        export_format = "svg"
    dpi = str(params.get("dpi") or "300")
    scale = {"150": 1, "300": 2, "600": 4, "1000": 6}.get(dpi, 2)
    filename = _plot_filename(params.get("export_filename"))
    modebar = _display_modebar(params.get("display_modebar"))
    buttons_to_remove = [] if _truthy(params.get("selection_tools"), False) else ["lasso2d", "select2d"]
    return {
        "displaylogo": False,
        "displayModeBar": modebar,
        "responsive": True,
        "scrollZoom": _truthy(params.get("scroll_zoom"), False),
        "toImageButtonOptions": {"format": export_format, "filename": filename, "scale": scale},
        "modeBarButtonsToRemove": buttons_to_remove,
    }


def _plot_filename(value: Any) -> str:
    raw = str(value or "yzw_biocloud_plot").strip()
    allowed = []
    for char in raw:
        if char.isalnum() or char in {"-", "_"}:
            allowed.append(char)
        elif char.isspace() or char in {".", "/", "\\"}:
            allowed.append("_")
    filename = "".join(allowed)
    while "__" in filename:
        filename = filename.replace("__", "_")
    filename = filename.strip("_")
    return filename[:80] or "yzw_biocloud_plot"


def _display_modebar(value: Any) -> bool | str:
    mode = str(value or "hover")
    if mode == "always":
        return True
    if mode == "never":
        return False
    return "hover"


def _axis_range(mode: Any, minimum: Any, maximum: Any) -> list[float] | None:
    if str(mode or "auto") != "custom":
        return None
    lower = _number_or_none(minimum)
    upper = _number_or_none(maximum)
    if lower is None or upper is None or lower >= upper:
        return None
    return [lower, upper]


def _axis_mirror(value: Any) -> bool | str:
    mode = str(value or "none")
    if mode == "line":
        return True
    if mode == "ticks":
        return "ticks"
    return False


def _hover_mode(value: Any) -> bool | str:
    mode = str(value or "closest")
    if mode == "none":
        return False
    return mode if mode in {"closest", "x", "x unified", "y", "y unified"} else "closest"


def _drag_mode(value: Any) -> bool | str:
    mode = str(value or "zoom")
    if mode == "none":
        return False
    return mode if mode in {"zoom", "pan", "select", "lasso", "orbit", "turntable"} else "zoom"


def _dash_style(value: Any, default: str = "dash") -> str:
    dash = str(value or default)
    return dash if dash in {"solid", "dash", "dot", "dashdot"} else default


def _attach_common_guide_lines(layout: dict[str, Any], params: dict[str, Any]) -> None:
    if _truthy(params.get("show_v_reference"), False):
        x_value = _number_or_none(params.get("v_reference_value"))
        if x_value is not None:
            color = str(params.get("v_reference_color") or "#475569")
            width = _bounded_float(params.get("v_reference_width"), 1.4, 0.2, 8)
            layout.setdefault("shapes", []).append(
                {
                    "type": "line",
                    "xref": "x",
                    "yref": "paper",
                    "x0": x_value,
                    "x1": x_value,
                    "y0": 0,
                    "y1": 1,
                    "line": {"color": color, "width": width, "dash": _dash_style(params.get("v_reference_dash"))},
                }
            )
            label = str(params.get("v_reference_label") or "").strip()
            if label:
                layout.setdefault("annotations", []).append(
                    {
                        "xref": "x",
                        "yref": "paper",
                        "x": x_value,
                        "y": 1.01,
                        "text": label,
                        "showarrow": False,
                        "font": {"size": 11, "color": color},
                        "xanchor": "left",
                        "yanchor": "bottom",
                    }
                )
    if _truthy(params.get("show_h_reference"), False):
        y_value = _number_or_none(params.get("h_reference_value"))
        if y_value is not None:
            color = str(params.get("h_reference_color") or "#475569")
            width = _bounded_float(params.get("h_reference_width"), 1.4, 0.2, 8)
            layout.setdefault("shapes", []).append(
                {
                    "type": "line",
                    "xref": "paper",
                    "yref": "y",
                    "x0": 0,
                    "x1": 1,
                    "y0": y_value,
                    "y1": y_value,
                    "line": {"color": color, "width": width, "dash": _dash_style(params.get("h_reference_dash"))},
                }
            )
            label = str(params.get("h_reference_label") or "").strip()
            if label:
                layout.setdefault("annotations", []).append(
                    {
                        "xref": "paper",
                        "yref": "y",
                        "x": 1.01,
                        "y": y_value,
                        "text": label,
                        "showarrow": False,
                        "font": {"size": 11, "color": color},
                        "xanchor": "left",
                        "yanchor": "middle",
                    }
                )


def _tick_direction(value: Any) -> str:
    direction = str(value or "outside")
    if direction == "inside":
        return "inside"
    if direction == "none":
        return ""
    return "outside"


def _text_or_default(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def _font_family(font_key: str) -> str:
    return {
        "arial": "Arial, Helvetica, sans-serif",
        "helvetica": "Helvetica, Arial, sans-serif",
        "times": "'Times New Roman', Times, serif",
        "georgia": "Georgia, 'Times New Roman', serif",
        "noto_sans": "'Noto Sans SC', 'Noto Sans', Arial, sans-serif",
    }.get(font_key, "Inter, Arial, sans-serif")


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


def _preferred_numeric_columns(table_summary: dict[str, Any], numeric_columns: list[str]) -> list[str]:
    matrix_profile = (table_summary.get("signals") or {}).get("matrix_profile") or {}
    preferred = [
        column
        for column in matrix_profile.get("value_columns") or []
        if column in numeric_columns
    ]
    if not preferred:
        return numeric_columns
    preferred_set = set(preferred)
    return preferred + [column for column in numeric_columns if column not in preferred_set]


def _single_row_matrix_profile(context: dict[str, Any], *, max_columns: int) -> dict[str, Any] | None:
    if len(context["records"]) != 1:
        return None
    matrix_profile = (context["table_summary"].get("signals") or {}).get("matrix_profile") or {}
    if matrix_profile.get("kind") != "expression_like":
        return None
    available_numeric = set(context["numeric_columns"])
    columns = [
        column
        for column in matrix_profile.get("value_columns") or []
        if column in available_numeric
    ][:max_columns]
    if not columns:
        return None
    row = context["records"][0]
    label = None
    for column in matrix_profile.get("identifier_columns") or []:
        value = str(row.get(column) or "").strip()
        if value:
            label = value
            break
    return {
        "columns": columns,
        "label": label or "row_1",
        "excluded_columns": [
            column
            for column in matrix_profile.get("excluded_numeric_columns") or []
            if column in available_numeric
        ],
    }


def _single_row_profile_grouped_values(
    context: dict[str, Any],
    *,
    max_columns: int,
) -> tuple[dict[str, Any], list[tuple[str, list[tuple[float, str]]]], list[str]] | None:
    profile = _single_row_matrix_profile(context, max_columns=max_columns)
    if not profile:
        return None
    row = context["records"][0]
    group_lookup = _profile_group_lookup(profile["columns"])
    grouped: dict[str, list[tuple[float, str]]] = {}
    for column in profile["columns"]:
        value = _number_or_none(row.get(column))
        if value is None:
            continue
        grouped.setdefault(group_lookup.get(column, "Profile"), []).append((value, column))
    if not grouped:
        return None
    warnings = []
    if profile["excluded_columns"]:
        warnings.append(
            "Skipped numeric metadata columns for this single-row profile: "
            + ", ".join(profile["excluded_columns"][:6])
        )
    return profile, list(grouped.items()), warnings


def _profile_group_lookup(columns: list[str]) -> dict[str, str]:
    inferred = {column: _profile_group_from_column(column) for column in columns}
    if len(set(inferred.values())) < 2:
        return {column: "Profile" for column in columns}
    return inferred


def _profile_group_from_column(column: str) -> str:
    text = str(column).strip()
    if not text:
        return "Profile"
    cleaned = re.sub(r"[-_.\s]+(?:rep(?:licate)?|r)?\d+$", "", text, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"(?<=[A-Za-z])\d+$", "", cleaned).strip()
    return cleaned or "Profile"


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


def _set_membership_columns(
    context: dict[str, Any],
    params: dict[str, Any],
    *,
    item_column: str | None,
    limit: int,
) -> list[str]:
    candidates = [column for column in context["columns"] if column != item_column]
    requested = params.get("set_columns")
    if requested:
        return _selected_columns(requested, candidates, limit=limit)

    membership_tokens = {
        "",
        "0",
        "1",
        "true",
        "false",
        "yes",
        "no",
        "y",
        "n",
        "present",
        "absent",
        "in",
        "out",
        "none",
        "na",
        "nan",
        "-",
        "x",
    }
    scored: list[tuple[float, bool, str]] = []
    for column in candidates:
        normalized_name = _normalize_column_name(column)
        name_like = (
            normalized_name.startswith("set")
            or normalized_name.startswith("list")
            or normalized_name in {"a", "b", "c", "d"}
        )
        values = [str(row.get(column) or "").strip().lower() for row in context["records"]]
        unique_values = set(values)
        truthy_count = sum(1 for value in values if _truthy_membership(value))
        if truthy_count <= 0:
            continue
        numeric_values = [_number_or_none(value) for value in values if value != ""]
        binary_numeric = bool(numeric_values) and all(value in {0, 1} for value in numeric_values)
        token_membership = unique_values.issubset(membership_tokens)
        if not token_membership and not binary_numeric and not name_like:
            continue
        score = 0.0
        if token_membership or binary_numeric:
            score += 4.0
        if name_like:
            score += 2.0
        score -= len(unique_values) * 0.01
        scored.append((score, name_like, column))

    scored.sort(key=lambda item: item[0], reverse=True)
    named_membership_columns = [column for _, name_like, column in scored if name_like]
    selected = named_membership_columns[:limit] if len(named_membership_columns) >= 2 else [column for _, _, column in scored[:limit]]
    return selected or candidates[:limit]


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


def _correlation_matrix_display_values(
    z_values: list[list[float]],
    matrix_type: str,
) -> tuple[list[list[float | None]], int]:
    if matrix_type not in {"lower_triangle", "upper_triangle"}:
        return [[float(value) for value in row] for row in z_values], 0
    displayed: list[list[float | None]] = []
    masked = 0
    for row_index, row in enumerate(z_values):
        display_row: list[float | None] = []
        for column_index, value in enumerate(row):
            hide_upper = matrix_type == "lower_triangle" and column_index > row_index
            hide_lower = matrix_type == "upper_triangle" and column_index < row_index
            if hide_upper or hide_lower:
                display_row.append(None)
                masked += 1
            else:
                display_row.append(float(value))
        displayed.append(display_row)
    return displayed, masked


def _cluster_vectors(vectors: list[list[float]], params: dict[str, Any]) -> dict[str, Any] | None:
    if len(vectors) < 2 or len(vectors) > 180:
        return None
    distance = str(params.get("distance") or "correlation")
    linkage = str(params.get("linkage") or "average")
    clusters = [
        {"items": [index], "height": 0.0, "left": None, "right": None}
        for index in range(len(vectors))
    ]
    active = list(range(len(clusters)))
    while len(active) > 1:
        best_pair: tuple[int, int] | None = None
        best_distance = math.inf
        for first_pos, first_id in enumerate(active[:-1]):
            for second_id in active[first_pos + 1 :]:
                merged_distance = _cluster_distance(clusters[first_id]["items"], clusters[second_id]["items"], vectors, distance, linkage)
                if merged_distance < best_distance:
                    best_distance = merged_distance
                    best_pair = (first_id, second_id)
        if best_pair is None:
            break
        left_id, right_id = best_pair
        clusters.append(
            {
                "items": clusters[left_id]["items"] + clusters[right_id]["items"],
                "height": best_distance,
                "left": left_id,
                "right": right_id,
            }
        )
        active = [cluster_id for cluster_id in active if cluster_id not in {left_id, right_id}]
        active.append(len(clusters) - 1)
    if not active:
        return None
    root_id = active[0]
    order = _cluster_leaf_order(root_id, clusters)
    return {"order": order, "clusters": clusters, "root": root_id}


def _cluster_distance(
    first_items: list[int],
    second_items: list[int],
    vectors: list[list[float]],
    distance: str,
    linkage: str,
) -> float:
    distances = [
        _vector_distance(vectors[first_index], vectors[second_index], distance)
        for first_index in first_items
        for second_index in second_items
    ]
    if not distances:
        return 0.0
    if linkage == "single":
        return min(distances)
    if linkage == "complete":
        return max(distances)
    return fmean(distances)


def _vector_distance(left: list[float], right: list[float], distance: str) -> float:
    pairs = list(zip(left, right, strict=False))
    if not pairs:
        return 0.0
    if distance == "euclidean":
        return math.sqrt(sum((left_value - right_value) ** 2 for left_value, right_value in pairs))
    if distance == "manhattan":
        return sum(abs(left_value - right_value) for left_value, right_value in pairs)
    return 1 - _pearson([left_value for left_value, _ in pairs], [right_value for _, right_value in pairs])


def _cluster_leaf_order(cluster_id: int, clusters: list[dict[str, Any]]) -> list[int]:
    cluster = clusters[cluster_id]
    left_id = cluster.get("left")
    right_id = cluster.get("right")
    if left_id is None or right_id is None:
        return cluster["items"][:]
    left_order = _cluster_leaf_order(left_id, clusters)
    right_order = _cluster_leaf_order(right_id, clusters)
    return left_order + right_order


def _transpose(matrix: list[list[float]]) -> list[list[float]]:
    if not matrix:
        return []
    return [list(column) for column in zip(*matrix, strict=False)]


def _attach_dendrogram_guides(
    layout: dict[str, Any],
    row_cluster: dict[str, Any] | None,
    column_cluster: dict[str, Any] | None,
    *,
    row_count: int,
    column_count: int,
) -> None:
    if not row_cluster and not column_cluster:
        return
    shapes = layout.setdefault("shapes", [])
    if row_cluster:
        shapes.extend(_dendrogram_shapes(row_cluster, orientation="row", leaf_count=row_count))
    if column_cluster:
        shapes.extend(_dendrogram_shapes(column_cluster, orientation="column", leaf_count=column_count))
    if row_cluster or column_cluster:
        layout["meta"] = {
            **dict(layout.get("meta") or {}),
            "dendrogram_guides": {
                "rows": bool(row_cluster),
                "columns": bool(column_cluster),
                "note": "Lightweight Plotly paper-space dendrogram guides; leaf order is clustered in the heatmap trace.",
            },
        }


def _dendrogram_shapes(cluster_result: dict[str, Any], *, orientation: str, leaf_count: int) -> list[dict[str, Any]]:
    if leaf_count < 2:
        return []
    clusters = cluster_result["clusters"]
    order = cluster_result["order"]
    ranks = {leaf: rank for rank, leaf in enumerate(order)}
    max_height = max((float(cluster.get("height") or 0.0) for cluster in clusters), default=1.0) or 1.0
    positions: dict[int, tuple[float, float]] = {}
    shapes: list[dict[str, Any]] = []

    def build(cluster_id: int) -> tuple[float, float]:
        cluster = clusters[cluster_id]
        left_id = cluster.get("left")
        right_id = cluster.get("right")
        if left_id is None or right_id is None:
            leaf = cluster["items"][0]
            position = (ranks[leaf] + 0.5) / leaf_count
            positions[cluster_id] = (position, 0.0)
            return positions[cluster_id]
        left_position, left_height = build(left_id)
        right_position, right_height = build(right_id)
        current_height = float(cluster.get("height") or 0.0) / max_height
        position = (left_position + right_position) / 2
        positions[cluster_id] = (position, current_height)
        shapes.extend(_cluster_branch_shapes(left_position, left_height, right_position, right_height, current_height, orientation))
        return positions[cluster_id]

    build(cluster_result["root"])
    return shapes


def _cluster_branch_shapes(
    first_position: float,
    first_height: float,
    second_position: float,
    second_height: float,
    parent_height: float,
    orientation: str,
) -> list[dict[str, Any]]:
    if orientation == "row":
        x_base = -0.012
        width = 0.055
        parent_x = x_base - parent_height * width
        first_x = x_base - first_height * width
        second_x = x_base - second_height * width
        return [
            _paper_shape_line(first_x, first_position, parent_x, first_position),
            _paper_shape_line(second_x, second_position, parent_x, second_position),
            _paper_shape_line(parent_x, first_position, parent_x, second_position),
        ]
    y_base = 1.012
    height = 0.055
    parent_y = y_base + parent_height * height
    first_y = y_base + first_height * height
    second_y = y_base + second_height * height
    return [
        _paper_shape_line(first_position, first_y, first_position, parent_y),
        _paper_shape_line(second_position, second_y, second_position, parent_y),
        _paper_shape_line(first_position, parent_y, second_position, parent_y),
    ]


def _paper_shape_line(x0: float, y0: float, x1: float, y1: float) -> dict[str, Any]:
    return {
        "type": "line",
        "xref": "paper",
        "yref": "paper",
        "x0": x0,
        "x1": x1,
        "y0": y0,
        "y1": y1,
        "line": {"color": "#8ba1b2", "width": 0.85},
    }


def _fill_missing_numeric(values: list[float | None]) -> list[float]:
    present = [value for value in values if value is not None]
    fallback = fmean(present) if present else 0.0
    return [value if value is not None else fallback for value in values]


def _aggregate_column(rows: list[dict[str, str]], column: str, method: str) -> float | None:
    values = [_number_or_none(row.get(column)) for row in rows]
    values = [value for value in values if value is not None]
    if not values:
        return None
    if method == "median":
        return median(values)
    if method == "first":
        return values[0]
    return fmean(values)


def _normalize_profile_series(series: list[dict[str, Any]], method: str) -> list[dict[str, Any]]:
    if method == "none" or not series:
        return series
    matrix = [item["values"] for item in series]
    column_count = len(matrix[0]) if matrix else 0
    normalized_matrix = [[0.0 for _ in range(column_count)] for _ in matrix]
    for column_index in range(column_count):
        column_values = [row[column_index] for row in matrix]
        if method == "zscore_by_axis":
            mean = fmean(column_values)
            sd = pstdev(column_values) if len(column_values) > 1 else 0.0
            for row_index, value in enumerate(column_values):
                normalized_matrix[row_index][column_index] = (value - mean) / sd if sd else 0.0
        else:
            minimum = min(column_values)
            span = max(max(column_values) - minimum, 1e-9)
            for row_index, value in enumerate(column_values):
                normalized_matrix[row_index][column_index] = (value - minimum) / span
    return [
        {"name": item["name"], "values": normalized_matrix[index]}
        for index, item in enumerate(series)
    ]


def _parallel_color_values(
    rows: list[dict[str, str]],
    color_column: str | None,
    numeric_columns: list[str],
) -> tuple[list[float], str]:
    if color_column and color_column in numeric_columns:
        values = [_number_or_none(row.get(color_column)) for row in rows]
        return _fill_missing_numeric(values), color_column
    if color_column:
        categories = []
        mapping: dict[str, float] = {}
        values = []
        for row in rows:
            category = str(row.get(color_column) or "missing")
            if category not in mapping:
                mapping[category] = float(len(categories))
                categories.append(category)
            values.append(mapping[category])
        return values, color_column
    return [float(index) for index, _ in enumerate(rows)], "row"


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


def _enrichment_color_value(value: float, transform: str) -> float:
    if transform == "minus_log10":
        return -math.log10(max(value, 1e-300))
    return value


def _wrap_text_label(text: str, width: int) -> str:
    words = str(text or "").split()
    if not words:
        return ""
    lines = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= width:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return "<br>".join(lines)


def _colorscale(name: str) -> str | list[list[Any]]:
    normalized = name.lower()
    if normalized in {"viridis", "magma", "plasma", "cividis"}:
        return normalized.title()
    if normalized in {"green_white_purple", "green_purple"}:
        return [[0, "#0052d9"], [0.5, "#ffffff"], [1, "#7a4fb3"]]
    if normalized in {"ylorrd", "yellow_orange_red"}:
        return [[0, "#fff7bc"], [0.5, "#fdae61"], [1, "#b2182b"]]
    if normalized in {"tealrose", "teal_rose"}:
        return [[0, "#0052d9"], [0.5, "#ffffff"], [1, "#c44f3a"]]
    if normalized in {"rdbu", "blue_white_red"}:
        return [[0, "#315fd6"], [0.5, "#ffffff"], [1, "#c44f3a"]]
    if normalized in {"prism_muted", "group"}:
        return [[0, "#315fd6"], [0.5, "#ffffff"], [1, "#c44f3a"]]
    return [[0, "#315fd6"], [0.5, "#ffffff"], [1, "#c44f3a"]]


def _rgba_from_hex(color: str, alpha: float) -> str:
    text = str(color or "").strip().lstrip("#")
    if len(text) != 6:
        return f"rgba(49, 95, 214, {alpha:.3g})"
    try:
        red = int(text[0:2], 16)
        green = int(text[2:4], 16)
        blue = int(text[4:6], 16)
    except ValueError:
        return f"rgba(49, 95, 214, {alpha:.3g})"
    return f"rgba({red}, {green}, {blue}, {alpha:.3g})"


def _sankey_arrangement(value: Any) -> str:
    text = str(value or "snap")
    if text in {"snap", "perpendicular", "freeform", "fixed"}:
        return text
    return "snap"


def _camera_eye(camera: str) -> dict[str, float]:
    if camera == "front":
        return {"x": 0.0, "y": 2.2, "z": 0.05}
    if camera == "top":
        return {"x": 0.05, "y": 0.05, "z": 2.25}
    return {"x": 1.45, "y": 1.45, "z": 1.05}


def _numeric_value_count(records: list[dict[str, str]], column: str) -> int:
    return sum(1 for row in records if _number_or_none(row.get(column)) is not None)


def _complete_numeric_row_count(records: list[dict[str, str]], columns: list[str]) -> int:
    return sum(
        1
        for row in records
        if all(_number_or_none(row.get(column)) is not None for column in columns)
    )


def _number_or_none(value: Any) -> float | None:
    parsed = _parse_float(value)
    if parsed is None or not math.isfinite(parsed):
        return None
    return parsed


def _truthy(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


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
    marker_line_width: float = 0.5,
    marker_line_color: str = "#ffffff",
    category_label_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    grouped = _records_by_category(records, color_column) if color_column else {"All": records}
    finite_sizes = [_number_or_none(row.get(size_column)) for row in records] if size_column else []
    finite_sizes = [value for value in finite_sizes if value is not None]
    size_min = min(finite_sizes) if finite_sizes else 0.0
    size_span = max((max(finite_sizes) - size_min) if finite_sizes else 0.0, 1e-9)
    marker_min = max(3.0, marker_size * 0.55)
    marker_max = max(marker_min, marker_size * 2.4)
    traces = []
    for index, (group_name, rows) in enumerate(grouped.items()):
        display_group_name = _display_category_label(group_name, category_label_map)
        x_values = []
        y_values = []
        labels = []
        raw_sizes = []
        marker_sizes = []
        for row in rows:
            x_value = _number_or_none(row.get(x_column))
            y_value = _number_or_none(row.get(y_column))
            if x_value is None or y_value is None:
                continue
            x_values.append(x_value)
            y_values.append(y_value)
            labels.append(str(row.get(label_column) or "") if label_column else "")
            size_value = _number_or_none(row.get(size_column)) if size_column else None
            raw_sizes.append(size_value if size_value is not None else "")
            if size_column and size_value is not None:
                marker_sizes.append(marker_min + (size_value - size_min) / size_span * (marker_max - marker_min))
            else:
                marker_sizes.append(marker_size)
        if not x_values:
            continue
        marker: dict[str, Any] = {
            "size": marker_sizes if size_column else marker_size,
            "opacity": marker_opacity,
            "color": PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)],
            "line": {"color": marker_line_color, "width": marker_line_width},
        }
        hovertemplate = "%{text}<br>x=%{x:.4g}<br>y=%{y:.4g}<extra>%{fullData.name}</extra>"
        if size_column:
            hovertemplate = (
                "%{text}<br>x=%{x:.4g}<br>y=%{y:.4g}"
                f"<br>{size_column}=%{{customdata[0]}}<extra>%{{fullData.name}}</extra>"
            )
        traces.append(
            {
                "type": "scattergl",
                "mode": mode,
                "name": display_group_name,
                "x": x_values,
                "y": y_values,
                "text": labels,
                "customdata": [[value] for value in raw_sizes],
                "marker": marker,
                "hovertemplate": hovertemplate,
                "_raw_sizes": raw_sizes,
            }
        )
    return traces


def _category_label_map(params: dict[str, Any]) -> dict[str, str]:
    raw = params.get("category_label_map")
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items() if str(key) and str(value)}
    return {}


def _display_category_label(value: str, label_map: dict[str, str] | None) -> str:
    if not label_map:
        return value
    return str(label_map.get(str(value), value))


def _scatter_statistical_overlays(
    traces: list[dict[str, Any]],
    params: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    trendline = str(params.get("trendline") or "none")
    show_ellipse = bool(params.get("confidence_ellipse", False))
    ellipse_level = _bounded_float(params.get("ellipse_level"), 0.95, 0.5, 0.99)
    show_fit_stats = _truthy(params.get("show_fit_stats"), True)
    overlays: list[dict[str, Any]] = []
    warnings: list[str] = []
    annotations: list[dict[str, Any]] = []
    for trace in traces:
        points = _trace_numeric_points(trace)
        if len(points) < 3:
            if trendline != "none" or show_ellipse:
                warnings.append(f"Skipping statistical overlay for {trace.get('name', 'group')}: fewer than 3 points.")
            continue
        x_values = [point[0] for point in points]
        y_values = [point[1] for point in points]
        color = str(trace.get("marker", {}).get("color") or PLOTLY_PALETTE[0])
        name = str(trace.get("name") or "All")
        if trendline == "linear":
            fit_trace = _linear_fit_trace(name, x_values, y_values, color)
            if fit_trace:
                overlays.append(fit_trace)
                if show_fit_stats:
                    annotations.append(
                        _linear_fit_annotation(
                            name,
                            fit_trace.get("meta", {}).get("fit_stats", {}),
                            color,
                            len(annotations),
                            params,
                        )
                    )
        elif trendline == "loess":
            smooth_trace = _loess_fit_trace(name, x_values, y_values, color, params)
            if smooth_trace:
                overlays.append(smooth_trace)
        elif trendline != "none":
            warnings.append(f"Unsupported trend line '{trendline}' was ignored.")
        if show_ellipse:
            ellipse_trace = _confidence_ellipse_trace(name, x_values, y_values, color, ellipse_level)
            if ellipse_trace:
                overlays.append(ellipse_trace)
            else:
                warnings.append(f"Skipping confidence ellipse for {name}: covariance is degenerate.")
    return overlays, warnings, annotations


def _trace_numeric_points(trace: dict[str, Any]) -> list[tuple[float, float]]:
    points = []
    for raw_x, raw_y in zip(trace.get("x", []), trace.get("y", []), strict=False):
        x_value = _number_or_none(raw_x)
        y_value = _number_or_none(raw_y)
        if x_value is not None and y_value is not None:
            points.append((x_value, y_value))
    return points


def _linear_fit_trace(name: str, x_values: list[float], y_values: list[float], color: str) -> dict[str, Any] | None:
    if len(set(x_values)) < 2:
        return None
    x_mean = fmean(x_values)
    y_mean = fmean(y_values)
    ss_xx = sum((x_value - x_mean) ** 2 for x_value in x_values)
    if ss_xx <= 0:
        return None
    ss_xy = sum((x_value - x_mean) * (y_value - y_mean) for x_value, y_value in zip(x_values, y_values, strict=False))
    slope = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean
    predicted = [slope * x_value + intercept for x_value in x_values]
    ss_total = sum((y_value - y_mean) ** 2 for y_value in y_values)
    ss_residual = sum((y_value - y_hat) ** 2 for y_value, y_hat in zip(y_values, predicted, strict=False))
    r_squared = 1 - ss_residual / ss_total if ss_total > 0 else 1.0
    x_min = min(x_values)
    x_max = max(x_values)
    return {
        "type": "scatter",
        "mode": "lines",
        "name": f"{name} linear fit",
        "x": [x_min, x_max],
        "y": [slope * x_min + intercept, slope * x_max + intercept],
        "line": {"color": color, "width": 2.2, "dash": "dash"},
        "hovertemplate": (
            f"y={_round_number(slope)}x+{_round_number(intercept)}<br>"
            f"R2={_round_number(r_squared)}<extra>{name} linear fit</extra>"
        ),
        "meta": {
            "fit_stats": {
                "slope": slope,
                "intercept": intercept,
                "r_squared": r_squared,
                "n": len(x_values),
            }
        },
    }


def _linear_fit_annotation(
    name: str,
    stats: dict[str, Any],
    color: str,
    index: int,
    params: dict[str, Any],
) -> dict[str, Any]:
    precision = _bounded_int(params.get("fit_stats_precision"), 3, 1, 6)
    slope = _format_fit_number(stats.get("slope"), precision)
    intercept = _format_fit_intercept(stats.get("intercept"), precision)
    r_squared = _format_fit_number(stats.get("r_squared"), precision)
    position = str(params.get("fit_stats_position") or "top_right")
    if position not in {"top_right", "top_left", "bottom_right", "bottom_left"}:
        position = "top_right"
    x = 0.98 if position.endswith("right") else 0.02
    xanchor = "right" if position.endswith("right") else "left"
    if position.startswith("top"):
        y = max(0.02, 0.98 - index * 0.075)
        yanchor = "top"
    else:
        y = min(0.98, 0.02 + index * 0.075)
        yanchor = "bottom"
    return {
        "xref": "paper",
        "yref": "paper",
        "x": x,
        "y": y,
        "xanchor": xanchor,
        "yanchor": yanchor,
        "showarrow": False,
        "align": xanchor,
        "text": f"{name}: y = {slope}x {intercept}<br>R2 = {r_squared}",
        "font": {"size": _bounded_int(params.get("subtitle_font_size"), 12, 8, 28), "color": color},
        "bgcolor": "rgba(255,255,255,0.78)",
        "bordercolor": color,
        "borderwidth": 1,
        "borderpad": 5,
    }


def _format_fit_number(value: Any, precision: int) -> str:
    numeric = _number_or_none(value)
    if numeric is None:
        return "NA"
    return f"{numeric:.{precision}g}"


def _format_fit_intercept(value: Any, precision: int) -> str:
    numeric = _number_or_none(value)
    if numeric is None:
        return "+ NA"
    sign = "+" if numeric >= 0 else "-"
    return f"{sign} {abs(numeric):.{precision}g}"


def _loess_fit_trace(
    name: str,
    x_values: list[float],
    y_values: list[float],
    color: str,
    params: dict[str, Any],
) -> dict[str, Any] | None:
    if len(set(x_values)) < 3:
        return None
    fraction = _bounded_float(params.get("loess_fraction"), 0.35, 0.15, 0.9)
    paired = sorted(zip(x_values, y_values, strict=False), key=lambda item: item[0])
    smoothed = []
    for x_target, _ in paired:
        y_hat = _local_linear_prediction(paired, x_target, fraction)
        if y_hat is not None:
            smoothed.append((x_target, y_hat))
    if len(smoothed) < 2:
        return None
    return {
        "type": "scatter",
        "mode": "lines",
        "name": f"{name} LOESS smooth",
        "x": [point[0] for point in smoothed],
        "y": [point[1] for point in smoothed],
        "line": {"color": color, "width": 2.4, "shape": "spline"},
        "hovertemplate": "x=%{x:.4g}<br>smoothed y=%{y:.4g}<extra>%{fullData.name}</extra>",
    }


def _local_linear_prediction(points: list[tuple[float, float]], x_target: float, fraction: float) -> float | None:
    window_size = max(3, min(len(points), math.ceil(len(points) * fraction)))
    neighbors = sorted(points, key=lambda point: abs(point[0] - x_target))[:window_size]
    max_distance = max(abs(point[0] - x_target) for point in neighbors) or 1.0
    weights = []
    for x_value, y_value in neighbors:
        scaled = abs(x_value - x_target) / max_distance
        weights.append(((1 - scaled**3) ** 3, x_value, y_value))
    weight_sum = sum(weight for weight, _, _ in weights)
    if weight_sum <= 0:
        return None
    x_mean = sum(weight * x_value for weight, x_value, _ in weights) / weight_sum
    y_mean = sum(weight * y_value for weight, _, y_value in weights) / weight_sum
    denominator = sum(weight * (x_value - x_mean) ** 2 for weight, x_value, _ in weights)
    if denominator <= 1e-12:
        return y_mean
    slope = sum(
        weight * (x_value - x_mean) * (y_value - y_mean)
        for weight, x_value, y_value in weights
    ) / denominator
    intercept = y_mean - slope * x_mean
    return slope * x_target + intercept


def _confidence_ellipse_trace(
    name: str,
    x_values: list[float],
    y_values: list[float],
    color: str,
    level: float,
) -> dict[str, Any] | None:
    if len(x_values) < 3 or len(set(x_values)) < 2 or len(set(y_values)) < 2:
        return None
    x_mean = fmean(x_values)
    y_mean = fmean(y_values)
    sample_size = len(x_values)
    cov_xx = sum((x_value - x_mean) ** 2 for x_value in x_values) / (sample_size - 1)
    cov_yy = sum((y_value - y_mean) ** 2 for y_value in y_values) / (sample_size - 1)
    cov_xy = sum(
        (x_value - x_mean) * (y_value - y_mean)
        for x_value, y_value in zip(x_values, y_values, strict=False)
    ) / (sample_size - 1)
    trace_value = cov_xx + cov_yy
    determinant = cov_xx * cov_yy - cov_xy**2
    eigen_part = max(trace_value**2 / 4 - determinant, 0)
    eigen_1 = trace_value / 2 + math.sqrt(eigen_part)
    eigen_2 = trace_value / 2 - math.sqrt(eigen_part)
    if eigen_1 <= 0 or eigen_2 <= 0:
        return None
    angle = 0.5 * math.atan2(2 * cov_xy, cov_xx - cov_yy)
    chi_square_scale = math.sqrt(-2 * math.log(max(1e-6, 1 - level)))
    radius_1 = chi_square_scale * math.sqrt(eigen_1)
    radius_2 = chi_square_scale * math.sqrt(eigen_2)
    cos_angle = math.cos(angle)
    sin_angle = math.sin(angle)
    ellipse_x = []
    ellipse_y = []
    for degree in range(0, 361, 5):
        theta = math.radians(degree)
        x_offset = radius_1 * math.cos(theta)
        y_offset = radius_2 * math.sin(theta)
        ellipse_x.append(x_mean + x_offset * cos_angle - y_offset * sin_angle)
        ellipse_y.append(y_mean + x_offset * sin_angle + y_offset * cos_angle)
    return {
        "type": "scatter",
        "mode": "lines",
        "name": f"{name} {int(round(level * 100))}% ellipse",
        "x": ellipse_x,
        "y": ellipse_y,
        "line": {"color": color, "width": 1.5, "dash": "dot"},
        "hoverinfo": "skip",
    }


def _records_by_category(records: list[dict[str, str]], column: str | None) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in records:
        key = str(row.get(column) or "All") if column else "All"
        grouped.setdefault(key, []).append(row)
    return grouped


def _linspace(start: float, stop: float, count: int) -> list[float]:
    if count <= 1:
        return [start]
    step = (stop - start) / (count - 1)
    return [start + index * step for index in range(count)]


def _kernel_density(values: list[float], grid: list[float], bandwidth_value: Any) -> list[float]:
    if not values:
        return [0.0 for _ in grid]
    requested_bandwidth = _number_or_none(bandwidth_value)
    if requested_bandwidth is not None and requested_bandwidth > 0:
        bandwidth = requested_bandwidth
    else:
        value_span = max(values) - min(values)
        sd = pstdev(values) if len(values) > 1 else 0.0
        bandwidth = 1.06 * sd * (len(values) ** -0.2) if sd > 0 else value_span / 8
        if bandwidth <= 0:
            bandwidth = max(abs(values[0]) * 0.05, 1.0)
    norm = len(values) * bandwidth * math.sqrt(2 * math.pi)
    densities = []
    for point in grid:
        kernel_sum = sum(math.exp(-0.5 * ((point - value) / bandwidth) ** 2) for value in values)
        densities.append(kernel_sum / norm)
    return densities


def _deterministic_jitter(index: int, width: float) -> float:
    if width <= 0:
        return 0.0
    cycle = [-0.5, 0.18, -0.08, 0.42, -0.32, 0.31, -0.44, 0.06, 0.5, -0.2]
    return cycle[index % len(cycle)] * width


def _distribution_trace(
    trace_type: str,
    *,
    name: str,
    values: list[float],
    color: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    if trace_type == "violin":
        point_mode = str(params.get("show_points") or "outliers")
        scale_mode = str(params.get("scale_mode") or "width")
        if scale_mode not in {"width", "count"}:
            scale_mode = "width"
        trace = {
            "type": "violin",
            "name": name,
            "y": values,
            "box": {"visible": bool(params.get("show_box", True))},
            "meanline": {"visible": bool(params.get("show_mean", True))},
            "points": False if point_mode == "none" else point_mode,
            "jitter": _bounded_float(params.get("point_jitter"), 0.12, 0, 1),
            "pointpos": _bounded_float(params.get("point_position"), 0, -2, 2),
            "width": _bounded_float(params.get("violin_width"), 0.72, 0.15, 1.4),
            "scalemode": scale_mode,
            "fillcolor": _rgba_from_hex(color, _bounded_float(params.get("fill_alpha"), 0.28, 0.02, 1)),
            "marker": {
                "color": color,
                "opacity": _bounded_float(params.get("point_alpha"), 0.62, 0.05, 1),
                "size": _bounded_float(params.get("point_size"), 5, 1, 24),
                "line": {"color": "#ffffff", "width": 0.6},
            },
            "line": {"color": color, "width": _bounded_float(params.get("line_width"), 1.4, 0.2, 8)},
            "side": str(params.get("side") or "both"),
            "spanmode": str(params.get("span_mode") or "soft"),
            "hovertemplate": f"{name}<br>value=%{{y:.4g}}<extra></extra>",
        }
        bandwidth = _number_or_none(params.get("bandwidth"))
        if bandwidth is not None:
            trace["bandwidth"] = _bounded_float(bandwidth, 0.2, 0.01, 3.0)
        return trace
    boxpoint_mode = str(params.get("boxpoints") or "all")
    if not _truthy(params.get("show_points"), True):
        boxpoint_value: bool | str = False
    elif boxpoint_mode == "none":
        boxpoint_value = False
    elif boxpoint_mode in {"outliers", "suspectedoutliers", "all"}:
        boxpoint_value = boxpoint_mode
    else:
        boxpoint_value = "all"
    mean_mode = str(params.get("boxmean_mode") or "mean")
    if not _truthy(params.get("show_mean"), True) or mean_mode == "none":
        boxmean: bool | str = False
    elif mean_mode == "mean_sd":
        boxmean = "sd"
    else:
        boxmean = True
    quartile_method = str(params.get("quartile_method") or "linear")
    if quartile_method not in {"linear", "exclusive", "inclusive"}:
        quartile_method = "linear"
    return {
        "type": "box",
        "name": name,
        "y": values,
        "boxpoints": boxpoint_value,
        "jitter": _bounded_float(params.get("point_jitter"), 0.35, 0, 1),
        "notched": bool(params.get("notched", False)),
        "width": _bounded_float(params.get("box_width"), 0.62, 0.1, 1.0),
        "whiskerwidth": _bounded_float(params.get("whisker_width"), 0.5, 0, 1),
        "quartilemethod": quartile_method,
        "fillcolor": _rgba_from_hex(color, _bounded_float(params.get("box_fill_alpha"), 0.18, 0, 1)),
        "marker": {
            "color": color,
            "opacity": _bounded_float(params.get("point_alpha"), 0.72, 0.05, 1),
            "size": _bounded_float(params.get("point_size"), 5, 1, 24),
            "line": {"color": "#ffffff", "width": 0.6},
        },
        "line": {"color": color, "width": _bounded_float(params.get("box_line_width"), 1.5, 0.2, 8)},
        "boxmean": boxmean,
        "hovertemplate": f"{name}<br>value=%{{y:.4g}}<extra></extra>",
    }


def _pairwise_comparison_overlays(
    grouped_values: list[tuple[str, list[float]]],
    params: dict[str, Any],
) -> dict[str, Any]:
    method = str(params.get("pairwise_test") or "none")
    if method == "none" or len(grouped_values) < 2:
        return {"shapes": [], "annotations": [], "warnings": [], "y_range": None}
    if method not in {"t_test", "wilcoxon", "anova_then_tukey"}:
        return {
            "shapes": [],
            "annotations": [],
            "warnings": [f"Unsupported pairwise test '{method}' was ignored."],
            "y_range": None,
        }

    comparisons = []
    for first_index, (first_name, first_values) in enumerate(grouped_values[:-1]):
        for second_index, (second_name, second_values) in enumerate(grouped_values[first_index + 1 :], start=first_index + 1):
            if len(first_values) < 2 or len(second_values) < 2:
                continue
            if method == "wilcoxon":
                p_value = _mann_whitney_p_value(first_values, second_values)
            else:
                p_value = _welch_t_p_value(first_values, second_values)
            comparisons.append(
                {
                    "first_index": first_index,
                    "second_index": second_index,
                    "first_name": first_name,
                    "second_name": second_name,
                    "p_value": p_value,
                }
            )
    if not comparisons:
        return {
            "shapes": [],
            "annotations": [],
            "warnings": ["Pairwise p-values require at least two values in each compared group."],
            "y_range": None,
        }

    adjusted_values = _adjust_p_values([item["p_value"] for item in comparisons], str(params.get("multiple_testing") or "BH"))
    all_values = [value for _, values in grouped_values for value in values]
    y_min = min(all_values)
    y_max = max(all_values)
    y_span = max(y_max - y_min, abs(y_max) * 0.05, 1e-9)
    base_y = y_max + y_span * 0.12
    step_y = y_span * 0.12
    bracket_height = y_span * 0.035
    denominator = max(len(grouped_values) - 1, 1)
    bracket_color = str(params.get("p_value_bracket_color") or "#324657")
    bracket_width = _bounded_float(params.get("p_value_bracket_width"), 1.1, 0.4, 5)
    label_color = str(params.get("p_value_color") or "#24323f")
    label_font_size = _bounded_int(params.get("p_value_font_size"), 11, 8, 22)
    label_format = str(params.get("p_value_label_format") or "threshold")
    shapes = []
    annotations = []
    for layer, (comparison, adjusted_p) in enumerate(zip(comparisons, adjusted_values, strict=False)):
        x0 = comparison["first_index"] / denominator
        x1 = comparison["second_index"] / denominator
        y = base_y + layer * step_y
        shapes.extend(
            [
                _paper_y_line(x0, y, y + bracket_height, bracket_color, bracket_width),
                _paper_y_line(x1, y, y + bracket_height, bracket_color, bracket_width),
                _paper_x_line(x0, x1, y + bracket_height, bracket_color, bracket_width),
            ]
        )
        annotations.append(
            {
                "xref": "paper",
                "yref": "y",
                "x": (x0 + x1) / 2,
                "y": y + bracket_height,
                "text": _p_value_label(adjusted_p, label_format),
                "showarrow": False,
                "yshift": 7,
                "font": {"size": label_font_size, "color": label_color},
                "hovertext": (
                    f"{comparison['first_name']} vs {comparison['second_name']}: "
                    f"raw p={comparison['p_value']:.4g}, adjusted p={adjusted_p:.4g}"
                ),
            }
        )
    y_top = base_y + len(comparisons) * step_y + bracket_height + y_span * 0.08
    warnings = []
    if method == "anova_then_tukey":
        warnings.append("ANOVA/Tukey display uses pairwise Welch p-values as a lightweight browser-ready approximation.")
    return {
        "shapes": shapes,
        "annotations": annotations,
        "warnings": warnings,
        "y_range": [y_min - y_span * 0.08, y_top],
    }


def _paper_y_line(x_value: float, y0: float, y1: float, color: str = "#324657", width: float = 1.1) -> dict[str, Any]:
    return {
        "type": "line",
        "xref": "paper",
        "yref": "y",
        "x0": x_value,
        "x1": x_value,
        "y0": y0,
        "y1": y1,
        "line": {"color": color, "width": width},
    }


def _paper_x_line(x0: float, x1: float, y_value: float, color: str = "#324657", width: float = 1.1) -> dict[str, Any]:
    return {
        "type": "line",
        "xref": "paper",
        "yref": "y",
        "x0": x0,
        "x1": x1,
        "y0": y_value,
        "y1": y_value,
        "line": {"color": color, "width": width},
    }


def _x_reference_line(x_value: float, color: str, *, dash: str, width: float = 1.7) -> dict[str, Any]:
    return {
        "type": "line",
        "xref": "x",
        "yref": "paper",
        "x0": x_value,
        "x1": x_value,
        "y0": 0,
        "y1": 1,
        "line": {"color": color, "width": width, "dash": dash},
    }


def _x_reference_annotation(x_value: float, text: str, color: str) -> dict[str, Any]:
    return {
        "xref": "x",
        "yref": "paper",
        "x": x_value,
        "y": 1.02,
        "text": text,
        "showarrow": False,
        "textangle": -90,
        "font": {"size": 10, "color": color},
        "xanchor": "left",
        "yanchor": "bottom",
    }


def _welch_t_p_value(first_values: list[float], second_values: list[float]) -> float:
    if len(first_values) < 2 or len(second_values) < 2:
        return 1.0
    first_mean = fmean(first_values)
    second_mean = fmean(second_values)
    first_var = _sample_variance(first_values)
    second_var = _sample_variance(second_values)
    standard_error = math.sqrt(first_var / len(first_values) + second_var / len(second_values))
    if standard_error <= 0:
        return 1.0
    z_score = abs(first_mean - second_mean) / standard_error
    return max(0.0, min(1.0, math.erfc(z_score / math.sqrt(2))))


def _mann_whitney_p_value(first_values: list[float], second_values: list[float]) -> float:
    first_count = len(first_values)
    second_count = len(second_values)
    if first_count < 2 or second_count < 2:
        return 1.0
    ranked = _average_ranks([(value, "first") for value in first_values] + [(value, "second") for value in second_values])
    first_rank_sum = sum(rank for rank, group in ranked if group == "first")
    u_value = first_rank_sum - first_count * (first_count + 1) / 2
    mean_u = first_count * second_count / 2
    sd_u = math.sqrt(first_count * second_count * (first_count + second_count + 1) / 12)
    if sd_u <= 0:
        return 1.0
    z_score = abs(u_value - mean_u) / sd_u
    return max(0.0, min(1.0, math.erfc(z_score / math.sqrt(2))))


def _average_ranks(values: list[tuple[float, str]]) -> list[tuple[float, str]]:
    sorted_values = sorted(enumerate(values), key=lambda item: item[1][0])
    ranked = [0.0] * len(values)
    index = 0
    while index < len(sorted_values):
        end = index + 1
        while end < len(sorted_values) and sorted_values[end][1][0] == sorted_values[index][1][0]:
            end += 1
        average_rank = (index + 1 + end) / 2
        for original_index, _ in sorted_values[index:end]:
            ranked[original_index] = average_rank
        index = end
    return [(rank, group) for rank, (_, group) in zip(ranked, values, strict=False)]


def _sample_variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean_value = fmean(values)
    return sum((value - mean_value) ** 2 for value in values) / (len(values) - 1)


def _adjust_p_values(p_values: list[float], method: str) -> list[float]:
    if method == "bonferroni":
        return [min(1.0, value * len(p_values)) for value in p_values]
    if method != "BH":
        return [min(1.0, max(0.0, value)) for value in p_values]
    indexed = sorted(enumerate(p_values), key=lambda item: item[1], reverse=True)
    adjusted = [1.0] * len(p_values)
    running = 1.0
    total = len(p_values)
    for reverse_rank, (original_index, value) in enumerate(indexed, start=1):
        rank = total - reverse_rank + 1
        running = min(running, value * total / rank)
        adjusted[original_index] = min(1.0, max(0.0, running))
    return adjusted


def _p_value_label(p_value: float, label_format: str = "threshold") -> str:
    if label_format == "stars":
        if p_value < 0.0001:
            return "****"
        if p_value < 0.001:
            return "***"
        if p_value < 0.01:
            return "**"
        if p_value < 0.05:
            return "*"
        return "ns"
    if label_format == "exact":
        return f"p={p_value:.3g}"
    if p_value < 0.0001:
        return "p<0.0001"
    if p_value < 0.001:
        return "p<0.001"
    return f"p={p_value:.3g}"


def _truthy_membership(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value).strip().lower()
    return normalized not in {"", "0", "false", "no", "none", "na", "nan", "-"}


def _intersection_label(set_names: tuple[str, ...]) -> str:
    return "&".join(set_names)


def _venn_circle_layout(set_columns: list[str]) -> dict[str, tuple[float, float]]:
    centers_by_count = {
        2: [(-0.62, 0.0), (0.62, 0.0)],
        3: [(-0.68, 0.42), (0.68, 0.42), (0.0, -0.62)],
        4: [(-0.72, 0.52), (0.72, 0.52), (-0.72, -0.52), (0.72, -0.52)],
    }
    centers = centers_by_count.get(len(set_columns), centers_by_count[4])
    return {set_name: centers[index] for index, set_name in enumerate(set_columns)}


def _venn_label_position(
    memberships: tuple[str, ...],
    circle_layout: dict[str, tuple[float, float]],
) -> tuple[float, float]:
    points = [circle_layout[set_name] for set_name in memberships if set_name in circle_layout]
    if not points:
        return (0.0, 0.0)
    x_value = fmean([point[0] for point in points])
    y_value = fmean([point[1] for point in points])
    if len(memberships) == 1:
        center_x, center_y = points[0]
        x_value += 0.22 if center_x >= 0 else -0.22
        y_value += 0.08 if center_y >= 0 else -0.08
    return (x_value, y_value)


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


def _sort_bar_values(
    labels: list[str],
    values: list[float],
    errors: list[float],
    mode: str,
    *,
    grouped_values: list[tuple[str, list[float]]] | None = None,
) -> tuple[list[str], list[float], list[float], list[tuple[str, list[float]]]]:
    if mode not in {"ascending", "descending"}:
        return labels, values, errors, grouped_values or []
    reverse = mode == "descending"
    grouped_map = {name: group_values for name, group_values in grouped_values or []}
    packed = sorted(zip(labels, values, errors, strict=False), key=lambda item: item[1], reverse=reverse)
    if not packed:
        return labels, values, errors, grouped_values or []
    sorted_labels, sorted_values, sorted_errors = zip(*packed, strict=False)
    sorted_grouped_values = [(label, grouped_map.get(label, [])) for label in sorted_labels]
    return list(sorted_labels), list(sorted_values), list(sorted_errors), sorted_grouped_values


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
    error_values = []
    customdata = []
    aggregate_replicates = bool(params.get("aggregate_replicates", True)) and bool(x_column)
    if aggregate_replicates:
        grouped_values: dict[Any, list[float]] = {}
        grouped_order: list[Any] = []
        for row in records:
            y_value = _number_or_none(row.get(y_column))
            if y_value is None:
                continue
            x_value = row.get(x_column) if x_column else len(grouped_order) + 1
            if x_value not in grouped_values:
                grouped_values[x_value] = []
                grouped_order.append(x_value)
            grouped_values[x_value].append(y_value)
        summary_stat = str(params.get("summary_stat") or "mean")
        if summary_stat not in {"mean", "median"}:
            summary_stat = "mean"
        error_bar = str(params.get("error_bar") or "sem")
        if error_bar not in {"none", "sd", "sem", "ci95"}:
            error_bar = "sem"
        for x_value in grouped_order:
            values = grouped_values[x_value]
            x_values.append(x_value)
            y_values.append(_aggregate_values(values, summary_stat))
            error_values.append(_error_bar_value(values, error_bar))
            customdata.append([len(values)])
    else:
        for index, row in enumerate(records):
            y_value = _number_or_none(row.get(y_column))
            if y_value is None:
                continue
            x_values.append(row.get(x_column) if x_column else index + 1)
            y_values.append(y_value)
            customdata.append([1])
    line_shape = str(params.get("line_shape") or "linear")
    if bool(params.get("smooth")):
        line_shape = "spline"
    if line_shape not in {"linear", "spline", "hv", "vh"}:
        line_shape = "linear"
    line_dash = str(params.get("line_dash") or "solid")
    if line_dash not in {"solid", "dash", "dot", "dashdot"}:
        line_dash = "solid"
    show_points = bool(params.get("show_points", True))
    trace = {
        "type": "scatter",
        "mode": "lines+markers" if show_points else "lines",
        "name": name,
        "x": x_values,
        "y": y_values,
        "customdata": customdata,
        "line": {
            "color": color,
            "shape": line_shape,
            "dash": line_dash,
            "width": _bounded_float(params.get("line_width"), 2.4, 0.5, 10),
        },
        "marker": {
            "color": color,
            "size": _bounded_float(params.get("marker_size"), 6, 0, 30),
            "symbol": str(params.get("marker_symbol") or "circle"),
        },
        "hovertemplate": "%{x}<br>value=%{y:.4g}<br>n=%{customdata[0]}<extra>%{fullData.name}</extra>",
        "connectgaps": bool(params.get("connect_gaps", False)),
    }
    if aggregate_replicates and any(value > 0 for value in error_values):
        trace["error_y"] = {
            "type": "data",
            "array": error_values,
            "visible": True,
            "thickness": 1.2,
            "width": _bounded_float(params.get("error_cap_width"), 4, 0, 16),
        }
    return trace


def _vertical_line(x_value: float, *, line: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": "line",
        "xref": "x",
        "yref": "paper",
        "x0": x_value,
        "x1": x_value,
        "y0": 0,
        "y1": 1,
        "line": line or {"color": "#8799aa", "width": 1, "dash": "dash"},
    }


def _horizontal_line(y_value: float, *, line: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": "line",
        "xref": "paper",
        "yref": "y",
        "x0": 0,
        "x1": 1,
        "y0": y_value,
        "y1": y_value,
        "line": line or {"color": "#8799aa", "width": 1, "dash": "dash"},
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



