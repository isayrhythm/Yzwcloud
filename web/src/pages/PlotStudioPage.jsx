import { useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "../i18n.jsx";

let plotlyLoader = null;

function loadPlotly() {
  if (!plotlyLoader) {
    plotlyLoader = new Promise((resolve, reject) => {
      if (window.Plotly) {
        resolve(window.Plotly);
        return;
      }
      const existingScript = document.querySelector("script[data-yzw-plotly]");
      if (existingScript) {
        existingScript.addEventListener("load", () => resolve(window.Plotly));
        existingScript.addEventListener("error", () => reject(new Error("Plotly failed to load")));
        return;
      }
      const script = document.createElement("script");
      script.src = "/static/vendor/plotly.min.js";
      script.async = true;
      script.dataset.yzwPlotly = "true";
      script.onload = () => resolve(window.Plotly);
      script.onerror = () => reject(new Error("Plotly failed to load"));
      document.head.appendChild(script);
    });
  }
  return plotlyLoader;
}

const FALLBACK_PARAMETER_GROUPS = [
  "Data mapping",
  "Grouping and facets",
  "Palette and theme",
  "Statistics and error bars",
  "Labels and annotations",
  "Export size and format",
];

const FALLBACK_WORKFLOW_STAGES = [
  { id: "source", label: "Select source", description: "Attach an upstream result or table." },
  { id: "plot", label: "Choose plot", description: "Pick a recommended figure type." },
  { id: "mapping", label: "Map data", description: "Bind columns to figure roles." },
  { id: "parameters", label: "Tune parameters", description: "Set basic and advanced controls." },
  { id: "preview", label: "Render preview", description: "Review the interactive chart." },
  { id: "report", label: "Explain / export", description: "Generate context and export." },
];

async function fetchJson(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      detail = await response.text();
    }
    throw new Error(detail);
  }
  return response.json();
}

function normalizeSource(source) {
  if (!source) return null;
  return {
    sourceKind: source.sourceKind || source.source_kind || "analysis_output",
    taskId: source.taskId || source.task_id || "",
    taskName: source.taskName || source.task_name || "",
    nodeId: source.nodeId || source.node_id || source.id || "",
    name: source.name || "Untitled output",
    status: source.status || "",
    type: source.type || "",
    summary: source.summary || source.type || "",
    dataPath: source.dataPath || source.data_path || "",
    previewUrl: source.previewUrl || source.preview_url || "",
    htmlUrl: source.htmlUrl || source.html_url || "",
    meta: source.meta || {},
  };
}

function sourceKey(source) {
  if (!source) return "empty";
  return [source.taskId, source.nodeId, source.type, source.dataPath].join("::");
}

function valuePreview(value) {
  if (Array.isArray(value)) return value.join(", ");
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value ?? "");
}

async function copyTextToClipboard(text) {
  if (!text) return false;
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return true;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  document.body.removeChild(textarea);
  return copied;
}

function defaultParamsFromPreset(preset) {
  return { ...(preset?.default_params || {}) };
}

function parameterIdsForPreset(preset) {
  const ids = new Set();
  (preset?.parameter_groups || []).forEach((group) => {
    (group.parameters || []).forEach((parameter) => ids.add(parameter.id));
  });
  return ids;
}

function preferredNumericColumns(tableSummary) {
  const numericColumns = tableSummary?.numeric_columns || [];
  const matrixProfile = tableSummary?.signals?.matrix_profile || null;
  const sampleColumns = Array.isArray(matrixProfile?.value_columns)
    ? matrixProfile.value_columns.filter((column) => numericColumns.includes(column))
    : [];
  if (!sampleColumns.length) return numericColumns;
  const sampleSet = new Set(sampleColumns);
  return [...sampleColumns, ...numericColumns.filter((column) => !sampleSet.has(column))];
}

function numericParameterIdsForPlot(plotId) {
  const idsByPlot = {
    scatter: ["x", "y", "size"],
    bubble: ["x", "y", "size"],
    density_contour: ["x", "y"],
    scatter_3d: ["x", "y", "z", "size"],
    surface_3d: ["x", "y", "z"],
    boxplot: ["y"],
    violin: ["y"],
    raincloud: ["y"],
    grouped_dotplot: ["y"],
    histogram: ["x"],
    density_curve: ["x"],
    ecdf: ["x"],
    line: ["y"],
    paired_dot: ["before", "after"],
    dumbbell: ["start", "end"],
  };
  return new Set(idsByPlot[plotId] || []);
}

function optionsForParameter(parameter, tableSummary, plotId) {
  const columns = tableSummary?.columns || [];
  const numericColumns = preferredNumericColumns(tableSummary);
  if (parameter.type === "numeric_columns") return numericColumns;
  if (numericParameterIdsForPlot(plotId).has(parameter.id)) return numericColumns;
  if (parameter.type === "column" || parameter.type === "column_or_none" || parameter.type === "columns") return columns;
  return parameter.options || [];
}

function normalizeParamValue(parameter, value) {
  if (parameter.type === "boolean") return Boolean(value);
  if (parameter.type === "number") {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : parameter.default;
  }
  if (parameter.type === "columns" || parameter.type === "numeric_columns") {
    return Array.isArray(value) ? value : value ? [value] : [];
  }
  return value;
}

function colorInputValue(value) {
  const text = String(value || "").trim();
  return /^#[0-9a-fA-F]{6}$/.test(text) ? text : "#ffffff";
}

function parameterHelpText(parameter, options) {
  if (parameter.help) return parameter.help;
  if (parameter.type === "number") {
    const bounds = [parameter.min ?? null, parameter.max ?? null].every((item) => item !== null)
      ? `${parameter.min}-${parameter.max}`
      : "";
    return bounds ? `Range ${bounds}; step ${parameter.step || 1}.` : "";
  }
  if (parameter.type === "number_or_auto") return "Use Auto or type a numeric value.";
  if (parameter.type === "color") return "Hex, rgb(), or rgba() are supported.";
  if (["column", "column_or_none", "columns", "numeric_columns"].includes(parameter.type)) {
    return options.length ? `${options.length} compatible column(s) detected.` : "No compatible columns detected yet.";
  }
  return "";
}

function isEmptyParamValue(value) {
  return value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0);
}

function autoMappingParamsForPreset(preset, tableSummary) {
  if (!preset || !tableSummary) return {};
  const numericColumns = preferredNumericColumns(tableSummary);
  const auto = {};
  const numericIds = numericParameterIdsForPlot(preset.id);
  (preset.parameter_groups || []).forEach((group) => {
    (group.parameters || []).forEach((parameter) => {
      if (parameter.type === "numeric_columns") {
        const limit = parameter.id === "dimensions" ? 8 : 24;
        auto[parameter.id] = numericColumns.slice(0, limit);
      } else if (numericIds.has(parameter.id)) {
        const indexById = { x: 0, y: 1, z: 2, size: 2, before: 0, after: 1, start: 0, end: 1 };
        const fallbackIndex = indexById[parameter.id] ?? 0;
        if (numericColumns[fallbackIndex]) auto[parameter.id] = numericColumns[fallbackIndex];
      }
    });
  });
  return auto;
}

function compactValueList(value, fallback = "-") {
  const values = Array.isArray(value) ? value : value ? [value] : [];
  if (!values.length) return fallback;
  const visible = values.slice(0, 5);
  const suffix = values.length > visible.length ? ` +${values.length - visible.length}` : "";
  return `${visible.join(", ")}${suffix}`;
}

function renderabilityWarning(preset, spec, tableSummary) {
  if (!preset || !spec?.data?.length) return "";
  const rowCount = Number(tableSummary?.scanned_rows ?? tableSummary?.row_count ?? 0);
  if (rowCount > 1) return "";
  if (["scatter", "density_contour", "scatter_3d", "bubble"].includes(preset.id)) {
    return "This plot needs at least two complete observation rows. For a single-row profile, use Bar or Histogram first.";
  }
  if (["radar", "parallel_coordinates"].includes(preset.id)) {
    return "This plot needs at least two sample or group profiles. A single-row table is better shown as Bar or Histogram.";
  }
  return "";
}

function previewSpecForRenderability(preset, spec, tableSummary) {
  const warning = renderabilityWarning(preset, spec, tableSummary);
  if (!warning) return spec;
  return {
    ...spec,
    data: [],
    warnings: [warning, ...(spec.warnings || [])],
  };
}

function mappingSummaryForPlot(preset, params, tableSummary) {
  if (!preset || !tableSummary) return [];
  const autoParams = autoMappingParamsForPreset(preset, tableSummary);
  const resolved = { ...autoParams, ...(params || {}) };
  const rows = [];
  const add = (label, value) => {
    if (!isEmptyParamValue(value)) rows.push({ label, value: compactValueList(value) });
  };
  if (preset.id === "scatter" || preset.id === "density_contour") {
    add("X", resolved.x);
    add("Y", resolved.y);
    add("Color", resolved.color);
  } else if (preset.id === "bubble") {
    add("X", resolved.x);
    add("Y", resolved.y);
    add("Size", resolved.size);
    add("Color", resolved.color);
  } else if (preset.id === "scatter_3d" || preset.id === "surface_3d") {
    add("X", resolved.x);
    add("Y", resolved.y);
    add("Z", resolved.z);
  } else if (["boxplot", "violin", "raincloud", "grouped_dotplot"].includes(preset.id)) {
    add("Y", resolved.y);
    add("Group", resolved.group);
  } else if (["histogram", "density_curve", "ecdf"].includes(preset.id)) {
    add("Value", resolved.x);
    add("Group", resolved.group);
  } else if (["heatmap", "radar"].includes(preset.id)) {
    add("Values", resolved.value_columns);
    add("Group", resolved.group);
  } else if (preset.id === "correlation") {
    add("Values", resolved.value_columns);
  } else if (preset.id === "parallel_coordinates") {
    add("Dimensions", resolved.dimensions);
    add("Color", resolved.color);
  } else if (["paired_dot", "dumbbell"].includes(preset.id)) {
    add("Start", resolved.before || resolved.start);
    add("End", resolved.after || resolved.end);
    add("Group", resolved.group);
  }
  return rows;
}

function ParamLabel({ parameter, options }) {
  const help = parameterHelpText(parameter, options);
  return (
    <span className="plot-param-label">
      <strong>{parameter.label}</strong>
      {help ? <small>{help}</small> : null}
    </span>
  );
}

function ParameterControl({ parameter, value, tableSummary, plotId, onChange }) {
  const options = optionsForParameter(parameter, tableSummary, plotId);
  const resolvedValue = value ?? parameter.default ?? "";

  if (parameter.type === "boolean") {
    return (
      <label className="plot-param-row checkbox">
        <input
          type="checkbox"
          checked={Boolean(resolvedValue)}
          onChange={(event) => onChange(parameter.id, event.target.checked)}
        />
        <ParamLabel parameter={parameter} options={options} />
      </label>
    );
  }

  if (parameter.type === "select") {
    return (
      <label className="plot-param-row">
        <ParamLabel parameter={parameter} options={options} />
        <select value={resolvedValue} onChange={(event) => onChange(parameter.id, event.target.value)}>
          {(parameter.options || []).map((option) => (
            <option value={option} key={option}>{option}</option>
          ))}
        </select>
      </label>
    );
  }

  if (parameter.type === "columns" || parameter.type === "numeric_columns") {
    const selected = Array.isArray(resolvedValue) ? resolvedValue : [];
    return (
      <label className="plot-param-row">
        <ParamLabel parameter={parameter} options={options} />
        <select
          multiple
          value={selected}
          onChange={(event) => {
            const values = Array.from(event.target.selectedOptions).map((item) => item.value);
            onChange(parameter.id, values);
          }}
        >
          {options.map((option) => (
            <option value={option} key={option}>{option}</option>
          ))}
        </select>
      </label>
    );
  }

  if (parameter.type === "column" || parameter.type === "column_or_none") {
    return (
      <label className="plot-param-row">
        <ParamLabel parameter={parameter} options={options} />
        <select value={resolvedValue || ""} onChange={(event) => onChange(parameter.id, event.target.value || null)}>
          <option value="">{parameter.required ? "Select column" : "Auto / none"}</option>
          {options.map((option) => (
            <option value={option} key={option}>{option}</option>
          ))}
        </select>
      </label>
    );
  }

  if (parameter.type === "color") {
    return (
      <label className="plot-param-row">
        <ParamLabel parameter={parameter} options={options} />
        <span className="plot-param-color-controls">
          <input
            aria-label={`${parameter.label} swatch`}
            type="color"
            value={colorInputValue(resolvedValue)}
            onChange={(event) => onChange(parameter.id, event.target.value)}
          />
          <input
            aria-label={parameter.label}
            value={resolvedValue}
            onChange={(event) => onChange(parameter.id, event.target.value)}
          />
        </span>
      </label>
    );
  }

  if (parameter.type === "number" || parameter.type === "number_or_auto") {
    const isAuto = resolvedValue === "auto";
    return (
      <label className="plot-param-row">
        <ParamLabel parameter={parameter} options={options} />
        <span className="plot-param-number-controls">
          <input
            type="number"
            value={isAuto ? "" : resolvedValue}
            min={parameter.min}
            max={parameter.max}
            step={parameter.step || 1}
            placeholder={isAuto ? "Auto" : undefined}
            disabled={isAuto}
            onChange={(event) => onChange(parameter.id, normalizeParamValue(parameter, event.target.value))}
          />
          {parameter.type === "number_or_auto" ? (
            <button
              className={isAuto ? "active" : ""}
              type="button"
              onClick={() => onChange(parameter.id, isAuto ? (parameter.min ?? 0) : "auto")}
            >
              Auto
            </button>
          ) : null}
        </span>
      </label>
    );
  }

  return (
    <label className="plot-param-row">
      <ParamLabel parameter={parameter} options={options} />
      <input value={resolvedValue} onChange={(event) => onChange(parameter.id, event.target.value)} />
    </label>
  );
}

function ReportSection({ section }) {
  return (
    <article className={`plot-report-section ${section.tone || "neutral"}`}>
      <strong>{section.title}</strong>
      <p>{section.text}</p>
    </article>
  );
}

function PlotMethodOverview({ preset, source, tableSummary, t }) {
  if (!preset) return null;
  const matrixProfile = tableSummary?.signals?.matrix_profile || null;
  const inputSummary = tableSummary
    ? matrixProfile
      ? `${tableSummary.scanned_rows} rows / ${matrixProfile.numeric_value_count} sample-like columns`
      : `${tableSummary.scanned_rows} rows / ${tableSummary.column_count} columns`
    : source?.type || t("selectSourceFirst");
  const outputSummary = preset.engine === "plotly" ? t("interactivePlotlyOutput") : preset.engine || "-";
  return (
    <section className="plot-method-overview" aria-label={t("methodOverview")}>
      <div>
        <span>{t("application")}</span>
        <strong>{preset.use_case || preset.description || preset.label}</strong>
      </div>
      <div>
        <span>{t("input")}</span>
        <strong>{inputSummary}</strong>
      </div>
      <div>
        <span>{t("output")}</span>
        <strong>{outputSummary}</strong>
      </div>
    </section>
  );
}

function PlotMappingSummary({ preset, params, tableSummary }) {
  if (!preset || !tableSummary) return null;
  const matrixProfile = tableSummary?.signals?.matrix_profile || null;
  const mappingRows = mappingSummaryForPlot(preset, params, tableSummary);
  const skippedColumns = matrixProfile?.excluded_numeric_columns || [];
  return (
    <section className="plot-mapping-summary" aria-label="Current data mapping">
      <div>
        <span>Auto mapping</span>
        <strong>{mappingRows.length ? "ready" : "inspect parameters"}</strong>
      </div>
      {mappingRows.map((row) => (
        <div key={row.label}>
          <span>{row.label}</span>
          <strong title={row.value}>{row.value}</strong>
        </div>
      ))}
      {matrixProfile ? (
        <div>
          <span>Sample-like columns</span>
          <strong>{matrixProfile.numeric_value_count}</strong>
        </div>
      ) : null}
      {skippedColumns.length ? (
        <div>
          <span>Metadata skipped</span>
          <strong title={skippedColumns.join(", ")}>{compactValueList(skippedColumns)}</strong>
        </div>
      ) : null}
    </section>
  );
}

function PlotPreviewEmpty({ selectedPreset, plotSpec, recommendedPresets, onSelectPlot, t }) {
  const message = plotSpec?.warnings?.[0] || t("noRenderableChart");
  const alternatives = recommendedPresets.filter((preset) => preset.id !== selectedPreset?.id).slice(0, 4);
  return (
    <div className="plot-preview-empty">
      <div className="plot-preview-empty-copy">
        <span>{t("chartNotSuitable")}</span>
        <strong>{selectedPreset?.label || t("plotStudio")}</strong>
        <p>{message}</p>
      </div>
      {alternatives.length ? (
        <div className="plot-preview-recommendations" aria-label={t("tryRecommendedPlot")}>
          <small>{t("tryRecommendedPlot")}</small>
          <div>
            {alternatives.map((plot) => (
              <button type="button" key={plot.id} onClick={() => onSelectPlot(plot)}>
                <MiniPlotThumbnail plotId={plot.id} thumbnail={plot.thumbnail} />
                <span>{plot.label}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function InteractivePlot({ spec }) {
  const plotRef = useRef(null);

  useEffect(() => {
    if (!plotRef.current || !spec) return undefined;
    let cancelled = false;
    const plotElement = plotRef.current;
    let resizeObserver = null;
    loadPlotly().then((Plotly) => {
      if (cancelled) return;
      Plotly.react(plotElement, spec.data || [], spec.layout || {}, spec.config || {});
      resizeObserver = new ResizeObserver(() => {
        Plotly.Plots.resize(plotElement);
      });
      resizeObserver.observe(plotElement);
    });
    return () => {
      cancelled = true;
      resizeObserver?.disconnect();
      loadPlotly().then((Plotly) => Plotly.purge(plotElement));
    };
  }, [spec]);

  return <div className="plotly-preview" ref={plotRef} />;
}

function MiniPlotThumbnail({ plotId, thumbnail }) {
  const kind = thumbnail || plotId;
  if (kind === "boxplot") {
    return (
      <div className="mini-plot mini-boxplot" aria-hidden="true">
        {[0, 1, 2].map((item) => (
          <span className={`box box-${item}`} key={item}>
            <i />
          </span>
        ))}
      </div>
    );
  }
  if (kind === "grouped_dotplot") {
    return (
      <div className="mini-plot mini-grouped-dotplot" aria-hidden="true">
        {[0, 1, 2].map((group) => (
          <span className={`group g${group}`} key={group}>
            {[0, 1, 2, 3].map((dot) => <i key={dot} />)}
          </span>
        ))}
      </div>
    );
  }
  if (kind === "raincloud") {
    return (
      <div className="mini-plot mini-raincloud" aria-hidden="true">
        {[0, 1, 2].map((group) => (
          <span className={`cloud c${group}`} key={group}>
            <i className="box" />
            <i className="dot d1" />
            <i className="dot d2" />
            <i className="dot d3" />
          </span>
        ))}
      </div>
    );
  }
  if (kind === "violin") {
    return (
      <div className="mini-plot mini-violin" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
    );
  }
  if (kind === "ridgeline") {
    return (
      <div className="mini-plot mini-ridgeline" aria-hidden="true">
        <span className="ridge r1" />
        <span className="ridge r2" />
        <span className="ridge r3" />
        <span className="ridge r4" />
      </div>
    );
  }
  if (kind === "bar") {
    return (
      <div className="mini-plot mini-bar" aria-hidden="true">
        {[38, 62, 48, 78, 54].map((height, index) => (
          <span style={{ height: `${height}%` }} key={index} />
        ))}
      </div>
    );
  }
  if (kind === "line") {
    return (
      <div className="mini-plot mini-line" aria-hidden="true">
        <span className="line-segment s1" />
        <span className="line-segment s2" />
        <span className="line-segment s3" />
        <i className="dot d1" />
        <i className="dot d2" />
        <i className="dot d3" />
        <i className="dot d4" />
      </div>
    );
  }
  if (kind === "histogram") {
    return (
      <div className="mini-plot mini-histogram" aria-hidden="true">
        {[28, 42, 67, 54, 78, 49, 32].map((height, index) => (
          <span style={{ height: `${height}%` }} key={index} />
        ))}
      </div>
    );
  }
  if (kind === "density_curve") {
    return (
      <div className="mini-plot mini-density-curve" aria-hidden="true">
        <span className="curve c1" />
        <span className="curve c2" />
        <i className="rug r1" />
        <i className="rug r2" />
        <i className="rug r3" />
      </div>
    );
  }
  if (kind === "ecdf") {
    return (
      <div className="mini-plot mini-ecdf" aria-hidden="true">
        <span className="step s1" />
        <span className="step s2" />
        <span className="step s3" />
        <i className="median" />
      </div>
    );
  }
  if (kind === "calendar_heatmap") {
    return (
      <div className="mini-plot mini-calendar" aria-hidden="true">
        {Array.from({ length: 35 }, (_, index) => (
          <span key={index} />
        ))}
      </div>
    );
  }
  if (kind === "density_contour") {
    return (
      <div className="mini-plot mini-density" aria-hidden="true">
        <span className="ring r1" />
        <span className="ring r2" />
        <span className="ring r3" />
        <i className="dot d1" />
        <i className="dot d2" />
        <i className="dot d3" />
      </div>
    );
  }
  if (kind === "scatter_3d") {
    return (
      <div className="mini-plot mini-3d-scatter" aria-hidden="true">
        {Array.from({ length: 14 }, (_, index) => (
          <span key={index} />
        ))}
      </div>
    );
  }
  if (kind === "surface_3d") {
    return (
      <div className="mini-plot mini-surface" aria-hidden="true">
        {Array.from({ length: 24 }, (_, index) => (
          <span key={index} />
        ))}
      </div>
    );
  }
  if (kind === "radar") {
    return (
      <div className="mini-plot mini-radar" aria-hidden="true">
        <span className="axis a1" />
        <span className="axis a2" />
        <span className="axis a3" />
        <i className="poly p1" />
        <i className="poly p2" />
      </div>
    );
  }
  if (kind === "parallel_coordinates") {
    return (
      <div className="mini-plot mini-parallel" aria-hidden="true">
        {[0, 1, 2, 3, 4].map((axis) => <span className="axis" style={{ left: `${14 + axis * 18}%` }} key={axis} />)}
        <i className="path p1" />
        <i className="path p2" />
        <i className="path p3" />
      </div>
    );
  }
  if (kind === "heatmap" || kind === "correlation") {
    return (
      <div className={`mini-plot mini-heatmap ${kind === "correlation" ? "corr" : ""}`} aria-hidden="true">
        {Array.from({ length: 30 }, (_, index) => (
          <span key={index} />
        ))}
      </div>
    );
  }
  if (kind === "bubble") {
    return (
      <div className="mini-plot mini-bubble" aria-hidden="true">
        <span className="b1" />
        <span className="b2" />
        <span className="b3" />
        <span className="b4" />
      </div>
    );
  }
  if (kind === "volcano") {
    return (
      <div className="mini-plot mini-volcano" aria-hidden="true">
        {Array.from({ length: 24 }, (_, index) => (
          <span key={index} />
        ))}
      </div>
    );
  }
  if (kind === "waterfall") {
    return (
      <div className="mini-plot mini-waterfall" aria-hidden="true">
        {[-52, -38, -21, 16, 29, 44, 63, 78].map((height, index) => (
          <span className={height < 0 ? "neg" : "pos"} style={{ height: `${Math.abs(height)}%` }} key={index} />
        ))}
      </div>
    );
  }
  if (kind === "lollipop") {
    return (
      <div className="mini-plot mini-lollipop" aria-hidden="true">
        {[18, 34, 50, 66, 82].map((top, index) => (
          <span style={{ top: `${top}%`, width: `${28 + index * 10}%` }} key={top}>
            <i />
          </span>
        ))}
      </div>
    );
  }
  if (kind === "ma_plot") {
    return (
      <div className="mini-plot mini-ma" aria-hidden="true">
        {Array.from({ length: 20 }, (_, index) => (
          <span key={index} />
        ))}
      </div>
    );
  }
  if (kind === "qq_plot") {
    return (
      <div className="mini-plot mini-qq" aria-hidden="true">
        <i />
        {Array.from({ length: 16 }, (_, index) => (
          <span key={index} />
        ))}
      </div>
    );
  }
  if (kind === "forest_plot") {
    return (
      <div className="mini-plot mini-forest" aria-hidden="true">
        {[0, 1, 2, 3].map((item) => (
          <span key={item}>
            <i />
          </span>
        ))}
      </div>
    );
  }
  if (kind === "roc_curve") {
    return (
      <div className="mini-plot mini-roc" aria-hidden="true">
        <i />
        <b />
        {[0, 1, 2, 3, 4, 5].map((item) => (
          <span key={item} />
        ))}
      </div>
    );
  }
  if (kind === "pr_curve") {
    return (
      <div className="mini-plot mini-pr" aria-hidden="true">
        <i />
        <b />
        {[0, 1, 2, 3, 4].map((item) => (
          <span key={item} />
        ))}
      </div>
    );
  }
  if (kind === "kaplan_meier") {
    return (
      <div className="mini-plot mini-km" aria-hidden="true">
        <i className="curve c1" />
        <i className="curve c2" />
        {[0, 1, 2, 3].map((item) => (
          <span key={item} />
        ))}
      </div>
    );
  }
  if (kind === "bland_altman") {
    return (
      <div className="mini-plot mini-bland" aria-hidden="true">
        <i className="bias" />
        <i className="limit upper" />
        <i className="limit lower" />
        {Array.from({ length: 16 }, (_, index) => (
          <span key={index} />
        ))}
      </div>
    );
  }
  if (kind === "dose_response") {
    return (
      <div className="mini-plot mini-dose" aria-hidden="true">
        <i />
        {[0, 1, 2, 3, 4, 5].map((item) => (
          <span key={item} />
        ))}
      </div>
    );
  }
  if (kind === "paired_dot") {
    return (
      <div className="mini-plot mini-paired" aria-hidden="true">
        {[0, 1, 2].map((item) => (
          <i key={item} />
        ))}
        {Array.from({ length: 6 }, (_, index) => (
          <span key={index} />
        ))}
      </div>
    );
  }
  if (kind === "dumbbell") {
    return (
      <div className="mini-plot mini-dumbbell" aria-hidden="true">
        {[20, 38, 56, 74].map((top, index) => (
          <span style={{ top: `${top}%`, left: `${18 + index * 3}%`, width: `${42 + index * 7}%` }} key={top}>
            <i />
            <b />
          </span>
        ))}
      </div>
    );
  }
  if (kind === "upset") {
    return (
      <div className="mini-plot mini-upset" aria-hidden="true">
        <div className="upset-bars">
          {[75, 58, 44, 30].map((height, index) => <span style={{ height: `${height}%` }} key={index} />)}
        </div>
        <div className="upset-dots">
          {Array.from({ length: 12 }, (_, index) => <i key={index} />)}
        </div>
      </div>
    );
  }
  if (kind === "venn") {
    return (
      <div className="mini-plot mini-venn" aria-hidden="true">
        <span className="v1" />
        <span className="v2" />
        <span className="v3" />
      </div>
    );
  }
  if (kind === "enrichment_dot") {
    return (
      <div className="mini-plot mini-enrichment" aria-hidden="true">
        {[0, 1, 2, 3, 4].map((row) => (
          <span style={{ left: `${28 + row * 10}%`, top: `${18 + row * 14}%` }} key={row} />
        ))}
      </div>
    );
  }
  if (kind === "enrichment_bar") {
    return (
      <div className="mini-plot mini-enrichment-bar" aria-hidden="true">
        {[82, 68, 54, 43, 31].map((width, row) => (
          <span style={{ width: `${width}%`, top: `${16 + row * 14}%` }} key={row} />
        ))}
      </div>
    );
  }
  if (kind === "treemap") {
    return (
      <div className="mini-plot mini-treemap" aria-hidden="true">
        <span className="tile t1" />
        <span className="tile t2" />
        <span className="tile t3" />
        <span className="tile t4" />
        <span className="tile t5" />
      </div>
    );
  }
  if (kind === "sunburst") {
    return (
      <div className="mini-plot mini-sunburst" aria-hidden="true">
        <span className="ring r1" />
        <span className="ring r2" />
        <span className="ring r3" />
        <span className="wedge w1" />
        <span className="wedge w2" />
        <span className="wedge w3" />
      </div>
    );
  }
  if (kind === "wordcloud") {
    return (
      <div className="mini-plot mini-wordcloud" aria-hidden="true">
        <span className="w1">GO</span>
        <span className="w2">RNA</span>
        <span className="w3">KEGG</span>
        <span className="w4">cell</span>
        <span className="w5">stress</span>
      </div>
    );
  }
  if (kind === "sankey") {
    return (
      <div className="mini-plot mini-sankey" aria-hidden="true">
        <span className="node n1" />
        <span className="node n2" />
        <span className="node n3" />
        <span className="node n4" />
        <i className="flow f1" />
        <i className="flow f2" />
        <i className="flow f3" />
      </div>
    );
  }
  if (kind === "composition_bar") {
    return (
      <div className="mini-plot mini-composition" aria-hidden="true">
        {[0, 1, 2].map((bar) => (
          <span className={`bar b${bar}`} key={bar}>
            <i className="c1" />
            <i className="c2" />
            <i className="c3" />
          </span>
        ))}
      </div>
    );
  }
  if (kind === "donut") {
    return (
      <div className="mini-plot mini-donut" aria-hidden="true">
        <span className="ring" />
        <span className="slice s1" />
        <span className="slice s2" />
        <span className="slice s3" />
        <i />
      </div>
    );
  }
  return (
    <div className="mini-plot mini-scatter" aria-hidden="true">
      {Array.from({ length: 18 }, (_, index) => (
        <span key={index} />
      ))}
    </div>
  );
}

function groupPlotPresets(presets) {
  const groups = new Map();
  presets.forEach((preset) => {
    const category = preset.category || "Other";
    if (!groups.has(category)) groups.set(category, []);
    groups.get(category).push(preset);
  });
  return Array.from(groups.entries()).map(([category, items]) => ({ category, items }));
}

function isAdvancedParameterGroup(group) {
  if (typeof group.advanced === "boolean") return group.advanced;
  return ["theme", "export", "labels", "style"].includes(group.id);
}

function workflowStageState(stage, { selectedSource, selectedPreset, params, plotSpec, studioReport }) {
  if (stage.id === "source") return selectedSource ? "done" : "active";
  if (!selectedSource) return "locked";
  if (stage.id === "plot") return selectedPreset ? "done" : "active";
  if (!selectedPreset) return "locked";
  if (stage.id === "mapping") {
    const mappingGroup = selectedPreset.parameter_groups?.find((group) => group.id === "mapping");
    const requiredParams = mappingGroup?.parameters?.filter((parameter) => parameter.required) || [];
    const mapped = requiredParams.length === 0 || requiredParams.every((parameter) => {
      const value = params[parameter.id];
      return Array.isArray(value) ? value.length > 0 : value !== null && value !== undefined && value !== "";
    });
    return mapped ? "done" : "active";
  }
  if (stage.id === "parameters") return Object.keys(params || {}).length ? "done" : "active";
  if (stage.id === "preview") return plotSpec?.data?.length ? "done" : "active";
  if (stage.id === "report") return studioReport?.report ? "done" : "active";
  return "active";
}

export function PlotStudioPage({ source, report, activeTaskId, onSelectSource, onOpenAnalysis }) {
  const { t } = useI18n();
  const outputs = report?.outputs || [];
  const selectedSource = useMemo(() => normalizeSource(source), [source]);
  const [manifest, setManifest] = useState(null);
  const [selectedPlotId, setSelectedPlotId] = useState("");
  const [params, setParams] = useState({});
  const [studioReport, setStudioReport] = useState(null);
  const [plotSpec, setPlotSpec] = useState(null);
  const [status, setStatus] = useState("idle");
  const [specStatus, setSpecStatus] = useState("idle");
  const [error, setError] = useState("");
  const [specError, setSpecError] = useState("");
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [agentContextCopied, setAgentContextCopied] = useState(false);
  const [plotSearch, setPlotSearch] = useState("");
  const [recommendedOnly, setRecommendedOnly] = useState(false);
  const [selectedRecipeId, setSelectedRecipeId] = useState("");

  useEffect(() => {
    let active = true;
    fetchJson("/api/plot-studio/presets")
      .then((payload) => {
        if (active) setManifest(payload);
      })
      .catch((fetchError) => {
        if (active) setError(fetchError.message);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    setSelectedPlotId("");
    setParams({});
    setSelectedRecipeId("");
  }, [sourceKey(selectedSource)]);

  const plotPresets = manifest?.presets || [];
  const styleRecipes = manifest?.style_recipes || [];
  const workflowStages = manifest?.workflow_stages?.length ? manifest.workflow_stages : FALLBACK_WORKFLOW_STAGES;
  const tableSummary = studioReport?.table_summary || null;
  const preferredPreviewNumericColumns = useMemo(() => preferredNumericColumns(tableSummary), [tableSummary]);
  const skippedPreviewNumericColumns = tableSummary?.signals?.matrix_profile?.excluded_numeric_columns || [];
  const recommendedPlotIds = studioReport?.recommended_plot_ids || [];
  const filteredGroupedPresets = useMemo(() => {
    const query = plotSearch.trim().toLowerCase();
    const recommendedSet = new Set(recommendedPlotIds);
    const filtered = plotPresets.filter((preset) => {
      if (recommendedOnly && !recommendedSet.has(preset.id)) return false;
      if (!query) return true;
      return [preset.id, preset.label, preset.category, preset.engine, preset.use_case, preset.description]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query));
    });
    return groupPlotPresets(filtered);
  }, [plotPresets, plotSearch, recommendedOnly, recommendedPlotIds]);
  const visiblePlotCount = filteredGroupedPresets.reduce((total, group) => total + group.items.length, 0);
  const selectedPreset = useMemo(() => {
    if (!plotPresets.length) return null;
    const reportSelected = studioReport?.selected_plot?.id;
    const preferredId = selectedPlotId || reportSelected || recommendedPlotIds[0] || plotPresets[0]?.id;
    return plotPresets.find((preset) => preset.id === preferredId) || plotPresets[0];
  }, [plotPresets, recommendedPlotIds, selectedPlotId, studioReport?.selected_plot?.id]);
  const recommendedPresets = useMemo(
    () => recommendedPlotIds
      .map((plotId) => plotPresets.find((preset) => preset.id === plotId))
      .filter(Boolean),
    [plotPresets, recommendedPlotIds],
  );

  useEffect(() => {
    if (!selectedPreset) return;
    setParams((current) => ({ ...defaultParamsFromPreset(selectedPreset), ...current }));
  }, [selectedPreset?.id]);

  useEffect(() => {
    if (!selectedPreset || !tableSummary) return;
    const autoParams = autoMappingParamsForPreset(selectedPreset, tableSummary);
    if (!Object.keys(autoParams).length) return;
    setParams((current) => {
      let changed = false;
      const next = { ...current };
      Object.entries(autoParams).forEach(([key, value]) => {
        if (isEmptyParamValue(next[key])) {
          next[key] = value;
          changed = true;
        }
      });
      return changed ? next : current;
    });
  }, [selectedPreset?.id, sourceKey(selectedSource), tableSummary]);

  const supportedParamIds = useMemo(() => parameterIdsForPreset(selectedPreset), [selectedPreset]);

  useEffect(() => {
    if (!selectedSource) {
      setStudioReport(null);
      setPlotSpec(null);
      setStatus("idle");
      setSpecStatus("idle");
      return undefined;
    }
    const controller = new AbortController();
    setStatus("loading");
    setError("");
    fetchJson("/api/plot-studio/report", {
      method: "POST",
      body: JSON.stringify({
        source: selectedSource,
        plotType: selectedPlotId || undefined,
        params,
      }),
      signal: controller.signal,
    })
      .then((payload) => {
        setStudioReport(payload);
        setSelectedPlotId((current) => current || payload.selected_plot?.id || payload.recommended_plot_ids?.[0] || "");
        setStatus("ready");
      })
      .catch((fetchError) => {
        if (fetchError.name === "AbortError") return;
        setError(fetchError.message);
        setStatus("error");
      });
    return () => controller.abort();
  }, [selectedSource, selectedPlotId, params, refreshNonce]);

  useEffect(() => {
    if (!selectedSource || !selectedPlotId) {
      setPlotSpec(null);
      setSpecStatus("idle");
      return undefined;
    }
    const controller = new AbortController();
    setSpecStatus("loading");
    setSpecError("");
    fetchJson("/api/plot-studio/spec", {
      method: "POST",
      body: JSON.stringify({
        source: selectedSource,
        plotType: selectedPlotId,
        params,
      }),
      signal: controller.signal,
    })
      .then((payload) => {
        setPlotSpec(payload);
        setSpecStatus("ready");
      })
      .catch((fetchError) => {
        if (fetchError.name === "AbortError") return;
        setPlotSpec(null);
        setSpecError(fetchError.message);
        setSpecStatus("error");
      });
    return () => controller.abort();
  }, [selectedSource, selectedPlotId, params]);

  const metaEntries = selectedSource?.meta
    ? Object.entries(selectedSource.meta).filter(([, value]) => value !== null && value !== undefined && value !== "")
    : [];
  const parameterGroups = selectedPreset?.parameter_groups || [];
  const basicParameterGroups = parameterGroups.filter((group) => !isAdvancedParameterGroup(group));
  const advancedParameterGroups = parameterGroups.filter(isAdvancedParameterGroup);
  const reportSections = studioReport?.report?.sections || [];
  const agentContextText = useMemo(
    () => (studioReport?.agent_context ? JSON.stringify(studioReport.agent_context, null, 2) : ""),
    [studioReport?.agent_context],
  );
  const previewSpec = useMemo(
    () => previewSpecForRenderability(selectedPreset, plotSpec, tableSummary),
    [selectedPreset?.id, plotSpec, tableSummary],
  );

  const updateParam = (paramId, value) => {
    setParams((current) => ({ ...current, [paramId]: value }));
  };

  const selectPlotPreset = (plot) => {
    setSelectedPlotId(plot.id);
    setParams(defaultParamsFromPreset(plot));
    setSelectedRecipeId("");
  };

  const resetParams = () => {
    if (selectedPreset) setParams(defaultParamsFromPreset(selectedPreset));
    setSelectedRecipeId("");
  };

  return (
    <main className="plot-page shell">
      <section className="hero plot-hero">
        <div>
          <p className="eyebrow">Plot Studio</p>
          <h1>{t("figureWorkspaceTitle")}</h1>
          <p className="summary">{t("figureWorkspaceSummary")}</p>
        </div>
        <button className="primary" type="button" onClick={onOpenAnalysis}>{t("backToAnalysis")}</button>
      </section>

      <section className="plot-workflow-strip" aria-label="Plot Studio workflow">
        {workflowStages.map((stage, index) => {
          const state = workflowStageState(stage, { selectedSource, selectedPreset, params, plotSpec: previewSpec, studioReport });
          return (
            <article className={`plot-workflow-step ${state}`} key={stage.id}>
              <span>{index + 1}</span>
              <div>
                <strong>{stage.label}</strong>
                <small>{stage.description}</small>
              </div>
            </article>
          );
        })}
      </section>

      <section className="plot-studio-layout">
        <aside className="plot-agent-panel">
          <div className="panel-title">
            <h2>{t("figureTypes")}</h2>
            <span className="muted">{status === "loading" ? t("updating") : selectedSource?.type || t("selectSourceFirst")}</span>
          </div>
          {error ? <p className="plot-error">{error}</p> : null}
          <div className="plot-type-filter" role="search">
            <input
              type="search"
              value={plotSearch}
              onChange={(event) => setPlotSearch(event.target.value)}
              placeholder={t("plotSearchPlaceholder")}
              aria-label={t("plotSearchPlaceholder")}
            />
            <button
              className={recommendedOnly ? "active" : ""}
              type="button"
              onClick={() => setRecommendedOnly((current) => !current)}
              disabled={!recommendedPlotIds.length}
            >
              {t("recommendedOnly")}
            </button>
            <span>{visiblePlotCount} / {plotPresets.length}</span>
          </div>
          <div className="plot-type-toolbox">
            {filteredGroupedPresets.length ? filteredGroupedPresets.map((group) => (
              <section className="plot-type-section" key={group.category}>
                <h3>{group.category}</h3>
                <div className="plot-type-grid compact">
                  {group.items.map((plot) => {
                    const recommended = recommendedPlotIds.includes(plot.id);
                    const active = selectedPreset?.id === plot.id;
                    return (
                      <button
                        className={`plot-type-card ${recommended ? "recommended" : ""} ${active ? "active" : ""}`}
                        key={plot.id}
                        type="button"
                        onClick={() => selectPlotPreset(plot)}
                      >
                        <MiniPlotThumbnail plotId={plot.id} thumbnail={plot.thumbnail} />
                        <span className="plot-type-card-main">
                          <strong>{plot.label}</strong>
                          <small>{plot.use_case || plot.description}</small>
                          <span className="plot-type-meta">
                            <em>{plot.engine}</em>
                            {recommended ? <em className="recommended-badge">{t("recommendedForSource")}</em> : null}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </section>
            )) : <p className="muted">{plotPresets.length ? t("noPlotTypeMatches") : t("loadingPresets")}</p>}
          </div>

          <section className="plot-source-list">
            <div className="panel-title">
              <h2>{t("currentTaskOutputs")}</h2>
              <span className="muted">{outputs.length} item(s)</span>
            </div>
            <div className="plot-output-grid single">
              {outputs.length ? outputs.map((output) => (
                <article className={selectedSource?.nodeId === output.nodeId ? "active" : ""} key={output.id}>
                  <div>
                    <strong>{output.name}</strong>
                    <span>{output.type}</span>
                  </div>
                  <p>{output.summary}</p>
                  <button type="button" onClick={() => onSelectSource?.(normalizeSource(output))}>
                    {t("useAsSource")}
                  </button>
                </article>
              )) : (
                <p className="muted">
                  {activeTaskId ? t("runAnalysisNodeFirst") : t("selectAnalysisTaskFirst")}
                </p>
              )}
            </div>
          </section>
        </aside>

        <section className="plot-library-panel">
          <section className="plot-preview-panel plot-preview-main">
            <div className="panel-title">
              <div>
                <h2>{selectedPreset?.label || t("interactivePreview")}</h2>
                <p>{selectedPreset?.description || t("interactiveEnginePlan")}</p>
              </div>
              <span className="muted">{specStatus === "loading" ? t("rendering") : specStatus === "ready" ? t("ready") : specStatus}</span>
            </div>
            <PlotMethodOverview preset={selectedPreset} source={selectedSource} tableSummary={tableSummary} t={t} />
            <PlotMappingSummary preset={selectedPreset} params={params} tableSummary={tableSummary} />
            {specError ? <p className="plot-error">{specError}</p> : null}
            {previewSpec?.data?.length ? (
              <InteractivePlot spec={previewSpec} />
            ) : (
              <PlotPreviewEmpty
                selectedPreset={selectedPreset}
                plotSpec={previewSpec}
                recommendedPresets={recommendedPresets}
                onSelectPlot={selectPlotPreset}
                t={t}
              />
            )}
            {previewSpec?.warnings?.length ? (
              <div className="plot-warning-list">
                <strong>{t("plotWarnings")}</strong>
                {previewSpec.warnings.map((warning) => <span key={warning}>{warning}</span>)}
              </div>
            ) : null}
          </section>

          <section className="plot-source-list">
            <div className="panel-title">
              <h2>{t("dataPreview")}</h2>
              <span className="muted">
                {tableSummary ? `${tableSummary.scanned_rows} rows / ${tableSummary.column_count} columns` : t("noTable")}
              </span>
            </div>
            {tableSummary ? (
              <div className="plot-data-summary">
                <div>
                  <span>{t("numericColumns")}</span>
                  <strong>{preferredPreviewNumericColumns.slice(0, 8).join(", ") || "-"}</strong>
                </div>
                {skippedPreviewNumericColumns.length ? (
                  <div>
                    <span>Skipped metadata</span>
                    <strong>{skippedPreviewNumericColumns.slice(0, 8).join(", ")}</strong>
                  </div>
                ) : null}
                <div>
                  <span>{t("categoricalColumns")}</span>
                  <strong>{tableSummary.categorical_columns.slice(0, 8).join(", ") || "-"}</strong>
                </div>
                <div>
                  <span>{t("sourceFile")}</span>
                  <strong>{tableSummary.filename}</strong>
                </div>
              </div>
            ) : (
              <div className="plot-meta-grid">
                {metaEntries.length ? metaEntries.slice(0, 12).map(([key, value]) => (
                  <div key={key}>
                    <span>{key}</span>
                    <strong>{valuePreview(value)}</strong>
                  </div>
                )) : <p className="muted">{t("metadataAfterSource")}</p>}
              </div>
            )}
          </section>
        </section>

        <aside className="plot-inspector-panel">
          <div className="panel-title">
            <h2>{t("inputSource")}</h2>
            <span className="muted">{selectedSource ? t("connected") : t("empty")}</span>
          </div>

          {selectedSource ? (
            <article className="plot-source-card">
              <span>{selectedSource.sourceKind.replace(/_/g, " ")}</span>
              <strong>{selectedSource.name}</strong>
              <p>{selectedSource.summary}</p>
              <dl>
                <div><dt>{t("task")}</dt><dd>{selectedSource.taskName || selectedSource.taskId || "-"}</dd></div>
                <div><dt>{t("node")}</dt><dd>{selectedSource.nodeId || "-"}</dd></div>
                <div><dt>{t("type")}</dt><dd>{selectedSource.type || "-"}</dd></div>
              </dl>
              <div className="plot-source-actions">
                {selectedSource.htmlUrl ? <a href={selectedSource.htmlUrl} target="_blank" rel="noreferrer">{t("openInteractiveOutput")}</a> : null}
                {selectedSource.previewUrl ? <a href={selectedSource.previewUrl} target="_blank" rel="noreferrer">{t("openPreview")}</a> : null}
              </div>
            </article>
          ) : (
            <div className="plot-dropzone compact">
              <strong>{t("selectAnalysisOutput")}</strong>
              <p>{t("chooseWorkflowResult")}</p>
            </div>
          )}

          <article className="plot-config-panel">
            <div className="panel-title">
              <h2>{selectedPreset ? `${selectedPreset.label} ${t("parameters")}` : t("parameters")}</h2>
              <span className="muted">{selectedPreset?.engine || "-"}</span>
            </div>
            <div className="plot-action-strip">
              <button type="button" onClick={resetParams}>{t("resetDefaults")}</button>
              <button className="primary" type="button" onClick={() => setRefreshNonce((current) => current + 1)}>
                {t("runPreview")}
              </button>
            </div>
            {styleRecipes.length ? (
              <section className="plot-recipe-strip" aria-label={t("styleRecipes")}>
                <div>
                  <strong>{t("styleRecipes")}</strong>
                  <small>{t("styleRecipesHint")}</small>
                </div>
                <div className="plot-recipe-list">
                  {styleRecipes.map((recipe) => (
                    <button
                      className={selectedRecipeId === recipe.id ? "active" : ""}
                      type="button"
                      key={recipe.id}
                      title={recipe.description}
                      onClick={() => {
                        const nextParams = Object.fromEntries(
                          Object.entries(recipe.params || {}).filter(([key]) => supportedParamIds.has(key)),
                        );
                        setParams((current) => ({ ...current, ...nextParams }));
                        setSelectedRecipeId(recipe.id);
                      }}
                    >
                      <strong>{recipe.label}</strong>
                      <span>{recipe.description}</span>
                    </button>
                  ))}
                </div>
              </section>
            ) : null}
            <div className="plot-param-groups">
              {basicParameterGroups.length ? (
                <section className="plot-param-stack" aria-label={t("basicParameters")}>
                  <h3>{t("basicParameters")}</h3>
                  {basicParameterGroups.map((group) => (
                    <section className="plot-param-group" key={group.id}>
                      <h4>{group.label}</h4>
                      <div className="plot-param-controls">
                        {group.parameters.map((parameter) => (
                          <ParameterControl
                            key={parameter.id}
                            parameter={parameter}
                            value={params[parameter.id]}
                            tableSummary={tableSummary}
                            plotId={selectedPreset?.id}
                            onChange={updateParam}
                          />
                        ))}
                      </div>
                    </section>
                  ))}
                </section>
              ) : <p className="muted">{t("loadingPresets")}</p>}
              {advancedParameterGroups.length ? (
                <details className="plot-param-advanced">
                  <summary>{t("advancedParameters")}</summary>
                  <div className="plot-param-stack">
                    {advancedParameterGroups.map((group) => (
                      <section className="plot-param-group" key={group.id}>
                        <h4>{group.label}</h4>
                        <div className="plot-param-controls">
                          {group.parameters.map((parameter) => (
                            <ParameterControl
                              key={parameter.id}
                              parameter={parameter}
                              value={params[parameter.id]}
                              tableSummary={tableSummary}
                              plotId={selectedPreset?.id}
                              onChange={updateParam}
                            />
                          ))}
                        </div>
                      </section>
                    ))}
                  </div>
                </details>
              ) : null}
            </div>
          </article>

          <article className="plot-report-panel">
            <div className="panel-title">
              <h2>{t("agentReport")}</h2>
              <span className="muted">{status}</span>
            </div>
            {studioReport?.report?.headline ? <p className="plot-report-headline">{studioReport.report.headline}</p> : null}
            <div className="plot-report-sections">
              {reportSections.length ? reportSections.map((section) => (
                <ReportSection section={section} key={section.title} />
              )) : <p className="muted">{t("selectSourceReport")}</p>}
            </div>
            {studioReport?.report?.limitations?.length ? (
              <div className="plot-limitations">
                {studioReport.report.limitations.map((item) => <span key={item}>{item}</span>)}
              </div>
            ) : null}
            {agentContextText ? (
              <details className="plot-agent-context">
                <summary>
                  <span>{t("llmContext")}</span>
                  <button
                    type="button"
                    onClick={async (event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      const copied = await copyTextToClipboard(agentContextText);
                      setAgentContextCopied(copied);
                      window.setTimeout(() => setAgentContextCopied(false), 1600);
                    }}
                  >
                    {agentContextCopied ? t("copied") : t("copyContext")}
                  </button>
                </summary>
                <p>{t("llmContextHint")}</p>
                <pre>{agentContextText}</pre>
              </details>
            ) : null}
          </article>
        </aside>
      </section>
    </main>
  );
}
