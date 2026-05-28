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
            for index, value in enumerate(group_values):
                raw_point_x.append(group_name)
                raw_point_y.append(value)
                raw_point_text.append(f"{group_name} #{index + 1}")
        labels, values, errors = _sort_bar_values(labels, values, errors, str(params.get("sort") or "input"))
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
        raw_point_x = []
        raw_point_y = []
        raw_point_text = []
        labels, values, errors = _sort_bar_values(labels, values, errors, str(params.get("sort") or "input"))
        x_title = "numeric columns"
        y_title = aggregation
        title = "Bar summary by numeric column"

    trace = {
        "type": "bar",
        "x": labels,
        "y": values,
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
        x_title, y_title = y_title, x_title
        if len(data) > 1:
            point_trace = data[1]
            point_trace["x"], point_trace["y"] = point_trace["y"], point_trace["x"]

    layout = _base_layout(title=title, x_title=x_title, y_title=y_title, params=params)
    layout["bargap"] = 0.28
    return {"data": data, "layout": layout, "config": _plotly_config(), "warnings": warnings}


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
    traces = []
    for index, (group_name, rows) in enumerate(grouped.items()):
        values = [_number_or_none(row.get(x_column)) for row in rows]
        values = [value for value in values if value is not None]
        if not values:
            continue
        traces.append(
            {
                "type": "histogram",
                "name": group_name,
                "x": values,
                "nbinsx": bins,
                "histnorm": "" if histnorm == "count" else histnorm,
                "opacity": opacity,
                "marker": {"color": PLOTLY_PALETTE[index % len(PLOTLY_PALETTE)], "line": {"color": "#ffffff", "width": 0.5}},
                "cumulative": {"enabled": _truthy(params.get("cumulative"), False)},
                "hovertemplate": "%{x}<br>count=%{y}<extra>%{fullData.name}</extra>",
            }
        )
    if not traces:
        return _empty_plot_spec("histogram", "No numeric values were available for histogram rendering.", context["table_summary"])

    layout = _base_layout(
        title=f"Histogram: {x_column}",
        x_title=x_column,
        y_title="count" if histnorm == "count" else histnorm,
        params=params,
    )
    layout["barmode"] = str(params.get("barmode") or "overlay")
    return {"data": traces, "layout": layout, "config": _plotly_config(), "warnings": []}


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

    traces: list[dict[str, Any]] = [
        {
            "type": "histogram2dcontour",
            "name": "Density",
            "x": x_values,
            "y": y_values,
            "colorscale": _colorscale(str(params.get("palette") or "viridis")),
            "contours": {"coloring": str(params.get("contours_coloring") or "heatmap")},
            "line": {"width": 1.2, "color": "#294452"},
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
    return {"data": traces, "layout": layout, "config": _plotly_config(), "warnings": []}


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
    return {"data": traces, "layout": layout, "config": _plotly_config(), "warnings": []}


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
        "camera": {"eye": {"x": 1.45, "y": 1.65, "z": 0.9}},
    }
    layout["height"] = _bounded_int(params.get("height"), 780, 420, 3000)
    warnings = []
    if len(context["records"]) > len(matrix_rows):
        warnings.append(f"Showing top {len(matrix_rows)} rows ranked by variance.")
    return {"data": [trace], "layout": layout, "config": _plotly_config(), "warnings": warnings}


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
        point_mode = str(params.get("show_points") or "outliers")
        trace = {
            "type": "violin",
            "name": name,
            "y": values,
            "box": {"visible": bool(params.get("show_box", True))},
            "meanline": {"visible": bool(params.get("show_mean", True))},
            "points": False if point_mode == "none" else point_mode,
            "marker": {"color": color, "opacity": _bounded_float(params.get("point_alpha"), 0.62, 0.05, 1)},
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


def _sort_bar_values(
    labels: list[str],
    values: list[float],
    errors: list[float],
    mode: str,
) -> tuple[list[str], list[float], list[float]]:
    if mode not in {"ascending", "descending"}:
        return labels, values, errors
    reverse = mode == "descending"
    packed = sorted(zip(labels, values, errors, strict=False), key=lambda item: item[1], reverse=reverse)
    if not packed:
        return labels, values, errors
    sorted_labels, sorted_values, sorted_errors = zip(*packed, strict=False)
    return list(sorted_labels), list(sorted_values), list(sorted_errors)


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


