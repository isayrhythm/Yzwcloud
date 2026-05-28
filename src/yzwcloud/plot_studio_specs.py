from __future__ import annotations

import math
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
        "histogram": _build_histogram_spec,
        "density_contour": _build_density_contour_spec,
        "scatter_3d": _build_scatter_3d_spec,
        "surface_3d": _build_surface_3d_spec,
        "radar": _build_radar_spec,
        "parallel_coordinates": _build_parallel_coordinates_spec,
        "waterfall": _build_waterfall_spec,
        "ma_plot": _build_ma_plot_spec,
        "bubble": _build_bubble_spec,
        "volcano": _build_volcano_spec,
        "upset": _build_upset_spec,
        "venn": _build_venn_spec,
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


def _build_scatter_spec(context: dict[str, Any]) -> dict[str, Any]:
    params = context["params"]
    numeric_columns = context["numeric_columns"]
    x_column = _choose_column(params.get("x"), numeric_columns, fallback_index=0)
    y_column = _choose_column(params.get("y"), numeric_columns, fallback_index=1)
    if not x_column or not y_column:
        return _empty_plot_spec("scatter", "Scatter requires at least two numeric columns.", context["table_summary"])

    color_column = _choose_column(params.get("color"), context["categorical_columns"])
    label_column = _choose_column(params.get("label"), context["columns"])
    size_column = _choose_column(params.get("size"), numeric_columns)
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
    )
    warnings = []
    overlays, overlay_warnings = _scatter_statistical_overlays(traces, params)
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


def _build_violin_spec(context: dict[str, Any]) -> dict[str, Any]:
    return _build_distribution_spec(context, trace_type="violin")


def _build_distribution_spec(context: dict[str, Any], *, trace_type: str) -> dict[str, Any]:
    params = context["params"]
    y_column = _choose_column(params.get("y"), context["numeric_columns"])
    group_column = _choose_column(params.get("group"), context["categorical_columns"])
    traces = []
    warnings = []
    grouped_values: list[tuple[str, list[float]]] = []
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
    if trace_type == "box" and _truthy(params.get("show_p_values"), False):
        comparison_result = _pairwise_comparison_overlays(grouped_values, params)
        layout.setdefault("shapes", []).extend(comparison_result["shapes"])
        layout.setdefault("annotations", []).extend(comparison_result["annotations"])
        if comparison_result["y_range"]:
            layout["yaxis"]["range"] = comparison_result["y_range"]
        warnings.extend(comparison_result["warnings"])
    return {"data": traces, "layout": layout, "config": _plotly_config(params), "warnings": warnings}


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
        labels = context["numeric_columns"][:max_groups]
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
        x_title = "numeric columns"
        y_title = aggregation
        title = "Bar summary by numeric column"

    trace = {
        "type": "bar",
        "x": labels,
        "y": values,
        "width": _bounded_float(params.get("bar_width"), 0.72, 0.1, 1.0),
        "marker": {"color": PLOTLY_PALETTE[0], "line": {"color": "#0a4f52", "width": 1}},
        "error_y": {
            "type": "data",
            "array": errors,
            "visible": any(value > 0 for value in errors),
            "thickness": 1.6,
            "width": _bounded_float(params.get("error_cap_width"), 8, 0, 32),
        },
        "hovertemplate": "%{x}<br>value=%{y:.4g}<extra></extra>",
    }
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
    if not x_values:
        return _empty_plot_spec("density_contour", "No paired numeric values were available for contour rendering.", context["table_summary"])

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
    if not traces:
        return _empty_plot_spec("scatter_3d", "No complete x/y/z numeric rows were available.", context["table_summary"])

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
    requested_sets = _selected_columns(
        params.get("set_columns"),
        [column for column in context["columns"] if column != item_column],
        limit=_bounded_int(params.get("max_sets"), 8, 2, 20),
    )
    set_columns = requested_sets[: _bounded_int(params.get("max_sets"), 8, 2, 20)]
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

    x_labels = [_intersection_label(row["sets"]) for row in rows]
    bar_trace = {
        "type": "bar",
        "name": "Intersection size",
        "x": x_labels,
        "y": [row["count"] for row in rows],
        "marker": {"color": "#315fd6", "line": {"color": "#183f99", "width": 1}},
        "customdata": [[", ".join(row["items"]), len(row["sets"])] for row in rows],
        "hovertemplate": "%{x}<br>count=%{y}<br>degree=%{customdata[1]}<br>items=%{customdata[0]}<extra></extra>",
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
                "marker": {
                    "size": [12 if set_name in row["sets"] else 6 for row in rows],
                    "color": ["#07131f" if set_name in row["sets"] else "#d7e1ea" for row in rows],
                    "line": {"color": "#ffffff", "width": 0.6},
                },
                "hovertemplate": f"{set_name}<br>%{{x}}<extra></extra>",
                "showlegend": False,
            }
        )
    for row in rows:
        active_sets = [set_name for set_name in set_columns if set_name in row["sets"]]
        if len(active_sets) > 1:
            line_traces.append(
                {
                    "type": "scatter",
                    "mode": "lines",
                    "x": [_intersection_label(row["sets"]), _intersection_label(row["sets"])],
                    "y": [active_sets[0], active_sets[-1]],
                    "xaxis": "x2",
                    "yaxis": "y2",
                    "line": {"color": "#07131f", "width": 1.2},
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
        "marker": {"color": "#0f8a8f"},
        "hovertemplate": "%{y}<br>set size=%{x}<extra></extra>",
        "showlegend": False,
    }
    layout = _base_layout(title=f"UpSet: {len(rows)} intersections", x_title="", y_title="intersection size", params=params)
    layout.update(
        {
            "grid": {"rows": 2, "columns": 2, "pattern": "independent"},
            "xaxis": {"domain": [0.22, 1.0], "anchor": "y", "tickangle": -45, "automargin": True},
            "yaxis": {"domain": [0.45, 1.0], "anchor": "x", "title": "Intersection size"},
            "xaxis2": {"domain": [0.22, 1.0], "anchor": "y2", "tickangle": -45, "showticklabels": False},
            "yaxis2": {"domain": [0.05, 0.36], "anchor": "x2", "categoryorder": "array", "categoryarray": set_columns[::-1]},
            "xaxis3": {"domain": [0.0, 0.18], "anchor": "y3", "title": "Set size", "autorange": "reversed"},
            "yaxis3": {"domain": [0.05, 0.36], "anchor": "x3", "categoryorder": "array", "categoryarray": set_columns[::-1]},
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
    set_columns = _selected_columns(
        params.get("set_columns"),
        [column for column in context["columns"] if column != item_column],
        limit=_bounded_int(params.get("max_sets"), 4, 2, 4),
    )
    set_columns = set_columns[: _bounded_int(params.get("max_sets"), 4, 2, 4)]
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
        "xgap": _bounded_int(params.get("cell_gap"), 1, 0, 8),
        "ygap": _bounded_int(params.get("cell_gap"), 1, 0, 8),
    }
    warnings = []
    if _truthy(params.get("show_values"), False):
        if len(numeric_columns) <= 40:
            precision = _bounded_int(params.get("value_precision"), 2, 0, 4)
            trace["text"] = [[f"{value:.{precision}f}" for value in row] for row in z_values]
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
        "supported_plot_types": sorted(SUPPORTED_PLOTLY_SPEC_TYPES),
    }


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
        return [[0, "#20804f"], [0.5, "#ffffff"], [1, "#7a4fb3"]]
    if normalized in {"prism_muted", "group"}:
        return [[0, "#315fd6"], [0.5, "#ffffff"], [1, "#c44f3a"]]
    return [[0, "#315fd6"], [0.5, "#ffffff"], [1, "#c44f3a"]]


def _camera_eye(camera: str) -> dict[str, float]:
    if camera == "front":
        return {"x": 0.0, "y": 2.2, "z": 0.05}
    if camera == "top":
        return {"x": 0.05, "y": 0.05, "z": 2.25}
    return {"x": 1.45, "y": 1.45, "z": 1.05}


def _numeric_value_count(records: list[dict[str, str]], column: str) -> int:
    return sum(1 for row in records if _number_or_none(row.get(column)) is not None)


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
                "name": group_name,
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


def _scatter_statistical_overlays(
    traces: list[dict[str, Any]],
    params: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    trendline = str(params.get("trendline") or "none")
    show_ellipse = bool(params.get("confidence_ellipse", False))
    ellipse_level = _bounded_float(params.get("ellipse_level"), 0.95, 0.5, 0.99)
    overlays: list[dict[str, Any]] = []
    warnings: list[str] = []
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
    return overlays, warnings


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
    }


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
        trace = {
            "type": "violin",
            "name": name,
            "y": values,
            "box": {"visible": bool(params.get("show_box", True))},
            "meanline": {"visible": bool(params.get("show_mean", True))},
            "points": False if point_mode == "none" else point_mode,
            "marker": {
                "color": color,
                "opacity": _bounded_float(params.get("point_alpha"), 0.62, 0.05, 1),
                "size": _bounded_float(params.get("point_size"), 5, 1, 24),
            },
            "line": {"color": color},
            "side": str(params.get("side") or "both"),
            "spanmode": str(params.get("span_mode") or "soft"),
            "hovertemplate": f"{name}<br>value=%{{y:.4g}}<extra></extra>",
        }
        bandwidth = _number_or_none(params.get("bandwidth"))
        if bandwidth is not None:
            trace["bandwidth"] = _bounded_float(bandwidth, 0.2, 0.01, 3.0)
        return trace
    return {
        "type": "box",
        "name": name,
        "y": values,
        "boxpoints": "all" if params.get("show_points", True) else False,
        "jitter": _bounded_float(params.get("point_jitter"), 0.35, 0, 1),
        "notched": bool(params.get("notched", False)),
        "width": _bounded_float(params.get("box_width"), 0.62, 0.1, 1.0),
        "marker": {
            "color": color,
            "opacity": _bounded_float(params.get("point_alpha"), 0.72, 0.05, 1),
            "size": _bounded_float(params.get("point_size"), 5, 1, 24),
        },
        "line": {"color": color},
        "boxmean": bool(params.get("show_mean", True)),
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
    shapes = []
    annotations = []
    for layer, (comparison, adjusted_p) in enumerate(zip(comparisons, adjusted_values, strict=False)):
        x0 = comparison["first_index"] / denominator
        x1 = comparison["second_index"] / denominator
        y = base_y + layer * step_y
        shapes.extend(
            [
                _paper_y_line(x0, y, y + bracket_height),
                _paper_y_line(x1, y, y + bracket_height),
                _paper_x_line(x0, x1, y + bracket_height),
            ]
        )
        annotations.append(
            {
                "xref": "paper",
                "yref": "y",
                "x": (x0 + x1) / 2,
                "y": y + bracket_height,
                "text": _p_value_label(adjusted_p),
                "showarrow": False,
                "yshift": 7,
                "font": {"size": 11, "color": "#24323f"},
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


def _paper_y_line(x_value: float, y0: float, y1: float) -> dict[str, Any]:
    return {
        "type": "line",
        "xref": "paper",
        "yref": "y",
        "x0": x_value,
        "x1": x_value,
        "y0": y0,
        "y1": y1,
        "line": {"color": "#324657", "width": 1.1},
    }


def _paper_x_line(x0: float, x1: float, y_value: float) -> dict[str, Any]:
    return {
        "type": "line",
        "xref": "paper",
        "yref": "y",
        "x0": x0,
        "x1": x1,
        "y0": y_value,
        "y1": y_value,
        "line": {"color": "#324657", "width": 1.1},
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


def _p_value_label(p_value: float) -> str:
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
    for index, row in enumerate(records):
        y_value = _number_or_none(row.get(y_column))
        if y_value is None:
            continue
        x_values.append(row.get(x_column) if x_column else index + 1)
        y_values.append(y_value)
    line_shape = str(params.get("line_shape") or "linear")
    if bool(params.get("smooth")):
        line_shape = "spline"
    if line_shape not in {"linear", "spline", "hv", "vh"}:
        line_shape = "linear"
    line_dash = str(params.get("line_dash") or "solid")
    if line_dash not in {"solid", "dash", "dot", "dashdot"}:
        line_dash = "solid"
    show_points = bool(params.get("show_points", True))
    return {
        "type": "scatter",
        "mode": "lines+markers" if show_points else "lines",
        "name": name,
        "x": x_values,
        "y": y_values,
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
        "hovertemplate": "%{x}<br>value=%{y:.4g}<extra>%{fullData.name}</extra>",
        "connectgaps": bool(params.get("connect_gaps", False)),
    }


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



