import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "tdesign-react";
import { useI18n } from "../i18n.jsx";
import {
  createPlotStudioAgentEdit,
  createPlotStudioReport,
  createPlotStudioSpec,
  fetchPlotStudioJson,
  loadDefaultPlotStudioExample,
  loadPlotStudioExample,
  resolvePlotStudioSource,
} from "../plotStudio/api.js";
import {
  PlotDataPreviewPanel,
  PlotGalleryPanel,
  PlotParamsPanel,
  PlotPreviewPanel,
  PlotReportPanel,
  PlotSourcePanel,
  PlotTypePanel,
} from "../plotStudio/panels.jsx";
import {
  normalizePlotStudioSource,
  plotStudioSourceKey,
} from "../plotStudio/session.js";

let plotlyLoader = null;

function plotlyScriptUrls() {
  return ["/static/vendor/plotly.min.js"];
}

function loadPlotly() {
  if (!plotlyLoader) {
    plotlyLoader = new Promise((resolve, reject) => {
      if (window.Plotly) {
        resolve(window.Plotly);
        return;
      }
      const staleScripts = document.querySelectorAll("script[data-yzw-plotly]");
      staleScripts.forEach((script) => script.remove());
      const urls = plotlyScriptUrls();
      const tryLoad = (index) => {
        const src = urls[index];
        if (!src) {
          reject(new Error("Plotly failed to load"));
          return;
        }
        const script = document.createElement("script");
        script.src = src;
        script.async = true;
        script.dataset.yzwPlotly = "true";
        script.onload = () => {
          if (window.Plotly) {
            resolve(window.Plotly);
            return;
          }
          script.remove();
          tryLoad(index + 1);
        };
        script.onerror = () => {
          script.remove();
          tryLoad(index + 1);
        };
        document.head.appendChild(script);
      };
      tryLoad(0);
    });
  }
  const loader = plotlyLoader;
  return loader.catch((error) => {
    if (plotlyLoader === loader) plotlyLoader = null;
    throw error;
  });
}

const FALLBACK_PARAMETER_GROUPS = [
  "Data mapping",
  "Grouping and facets",
  "Palette and theme",
  "Statistics and error bars",
  "Labels and annotations",
  "Export size and format",
];

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

function sanitizePlotExportFilename(value) {
  const text = String(value || "").trim();
  const sanitized = text.replace(/[\\/:*?"<>|]+/g, "-").replace(/\s+/g, "-").replace(/^-+|-+$/g, "");
  return sanitized || "plot-studio-figure";
}

function plotExportOptionsFromSpec(spec, fallbackFormat = "png") {
  const rawOptions = spec?.config?.toImageButtonOptions || {};
  const supportedFormats = new Set(["tif", "tiff", "svg", "png", "jpeg", "webp"]);
  const rawFormat = String(rawOptions.exportFormat || rawOptions.format || fallbackFormat).toLowerCase();
  const format = supportedFormats.has(rawFormat) ? (rawFormat === "tiff" ? "tif" : rawFormat) : fallbackFormat;
  const scale = Number(rawOptions.scale);
  const options = {
    format,
    filename: sanitizePlotExportFilename(rawOptions.filename || spec?.layout?.title?.text),
    scale: Number.isFinite(scale) && scale > 0 ? scale : 2,
  };
  if (Number(rawOptions.width) > 0) options.width = Number(rawOptions.width);
  if (Number(rawOptions.height) > 0) options.height = Number(rawOptions.height);
  return options;
}

function downloadDataUrl(dataUrl, filename) {
  const link = document.createElement("a");
  link.href = dataUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  try {
    downloadDataUrl(url, filename);
  } finally {
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

function downloadTextFile(text, filename, type = "text/html;charset=utf-8") {
  downloadBlob(new Blob([text], { type }), filename);
}

function loadImageFromDataUrl(dataUrl) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("无法读取导出图像。"));
    image.src = dataUrl;
  });
}

function writeTiffEntry(view, offset, tag, type, count, value) {
  view.setUint16(offset, tag, true);
  view.setUint16(offset + 2, type, true);
  view.setUint32(offset + 4, count, true);
  if (type === 3 && count === 1) {
    view.setUint16(offset + 8, value, true);
    view.setUint16(offset + 10, 0, true);
  } else {
    view.setUint32(offset + 8, value, true);
  }
}

async function dataUrlToTiffBlob(dataUrl) {
  const image = await loadImageFromDataUrl(dataUrl);
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth || image.width;
  canvas.height = image.naturalHeight || image.height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context || !canvas.width || !canvas.height) {
    throw new Error("无法创建 TIFF 导出画布。");
  }
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(image, 0, 0);

  const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
  const pixelBytes = canvas.width * canvas.height * 3;
  const entryCount = 12;
  const ifdOffset = 8;
  const ifdBytes = 2 + entryCount * 12 + 4;
  const bitsOffset = ifdOffset + ifdBytes;
  const xResolutionOffset = bitsOffset + 6;
  const yResolutionOffset = xResolutionOffset + 8;
  const imageOffset = yResolutionOffset + 8;
  const buffer = new ArrayBuffer(imageOffset + pixelBytes);
  const view = new DataView(buffer);

  view.setUint8(0, 0x49);
  view.setUint8(1, 0x49);
  view.setUint16(2, 42, true);
  view.setUint32(4, ifdOffset, true);
  view.setUint16(ifdOffset, entryCount, true);

  let entryOffset = ifdOffset + 2;
  const entry = (tag, type, count, value) => {
    writeTiffEntry(view, entryOffset, tag, type, count, value);
    entryOffset += 12;
  };
  entry(256, 4, 1, canvas.width);
  entry(257, 4, 1, canvas.height);
  entry(258, 3, 3, bitsOffset);
  entry(259, 3, 1, 1);
  entry(262, 3, 1, 2);
  entry(273, 4, 1, imageOffset);
  entry(277, 3, 1, 3);
  entry(278, 4, 1, canvas.height);
  entry(279, 4, 1, pixelBytes);
  entry(282, 5, 1, xResolutionOffset);
  entry(283, 5, 1, yResolutionOffset);
  entry(296, 3, 1, 2);
  view.setUint32(entryOffset, 0, true);

  view.setUint16(bitsOffset, 8, true);
  view.setUint16(bitsOffset + 2, 8, true);
  view.setUint16(bitsOffset + 4, 8, true);
  view.setUint32(xResolutionOffset, 300, true);
  view.setUint32(xResolutionOffset + 4, 1, true);
  view.setUint32(yResolutionOffset, 300, true);
  view.setUint32(yResolutionOffset + 4, 1, true);

  let target = imageOffset;
  for (let source = 0; source < data.length; source += 4) {
    view.setUint8(target, data[source]);
    view.setUint8(target + 1, data[source + 1]);
    view.setUint8(target + 2, data[source + 2]);
    target += 3;
  }
  return new Blob([buffer], { type: "image/tiff" });
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function createPlotExportPrintWindow() {
  return window.open("", "_blank", "width=1200,height=850");
}

function plotExportPrintHtml({ dataUrl, title, filename }) {
  const safeTitle = escapeHtml(title || filename);
  const safeFilename = escapeHtml(filename);
  const safeDataUrl = escapeHtml(dataUrl);
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>${safeTitle}</title>
    <style>
      @page { size: 16in 9in; margin: 0.45in; }
      * { box-sizing: border-box; }
      body { margin: 0; color: #102333; font-family: Arial, "Microsoft YaHei", sans-serif; background: #ffffff; }
      main { display: grid; grid-template-rows: auto 1fr auto; width: 100vw; min-height: 100vh; gap: 18px; padding: 28px 34px; }
      header { display: flex; align-items: baseline; justify-content: space-between; gap: 24px; border-bottom: 1px solid #d8e5ea; padding-bottom: 12px; }
      h1 { margin: 0; font-size: 24px; line-height: 1.25; }
      small { color: #607584; font-weight: 700; }
      figure { display: grid; place-items: center; min-height: 0; margin: 0; }
      img { display: block; max-width: 100%; max-height: calc(100vh - 150px); object-fit: contain; }
      footer { color: #607584; font-size: 12px; }
      .toolbar { position: fixed; right: 18px; top: 18px; display: flex; gap: 8px; }
      button { min-height: 36px; padding: 0 14px; border: 1px solid #b7cffb; border-radius: 999px; background: #0052d9; color: #ffffff; font-weight: 800; cursor: pointer; }
      @media print {
        .toolbar { display: none; }
        body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        main { width: auto; min-height: auto; padding: 0; }
        img { max-height: 6.9in; }
      }
    </style>
  </head>
  <body>
    <div class="toolbar"><button type="button" onclick="window.print()">保存 PDF</button></div>
    <main>
      <header><h1>${safeTitle}</h1><small>${safeFilename}.pdf</small></header>
      <figure><img alt="${safeTitle}" src="${safeDataUrl}" /></figure>
      <footer>Plot Studio export</footer>
    </main>
    <script>window.addEventListener("load", () => { window.focus(); window.setTimeout(() => window.print(), 250); });</script>
  </body>
</html>`;
}

function openPlotExportPrintWindow({ dataUrl, title, filename, printWindow = null }) {
  const targetWindow = printWindow || createPlotExportPrintWindow();
  const html = plotExportPrintHtml({ dataUrl, title, filename });
  if (!targetWindow) {
    downloadTextFile(html, `${filename}-print.html`);
    return false;
  }
  targetWindow.document.write(html);
  targetWindow.document.close();
  return true;
}

function parameterDefaultsFromPreset(preset) {
  const defaults = {};
  (preset?.parameter_groups || []).forEach((group) => {
    (group.parameters || []).forEach((parameter) => {
      if (parameter.id && Object.prototype.hasOwnProperty.call(parameter, "default")) {
        defaults[parameter.id] = parameter.default;
      }
    });
  });
  return defaults;
}

function defaultParamsFromPreset(preset) {
  return { ...parameterDefaultsFromPreset(preset), ...(preset?.default_params || {}) };
}

function mergePresetDefaultsWithCurrent(preset, current) {
  const defaults = defaultParamsFromPreset(preset);
  const next = { ...defaults, ...(current || {}) };
  if (defaults.format === "tif" && (!current || current.format === undefined || current.format === "svg")) {
    next.format = "tif";
  }
  return next;
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
  if (parameter.type === "json") {
    if (value && typeof value === "object") return value;
    try {
      return value ? JSON.parse(value) : {};
    } catch {
      return {};
    }
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
  if (parameter.type === "json") return "Use JSON object syntax.";
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
        if (preset.id === "scatter" && parameter.id === "size") return;
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

function tableSuitabilityWarning(preset, tableSummary) {
  if (!preset || !tableSummary) return "";
  const rowCount = Number(tableSummary?.scanned_rows ?? tableSummary?.row_count ?? 0);
  if (rowCount > 1) return "";
  if (["scatter", "density_contour", "scatter_3d", "bubble"].includes(preset.id)) {
    return "This plot needs at least two complete observation rows. For a single-row profile, use Bar or Histogram first.";
  }
  if (["radar", "parallel_coordinates"].includes(preset.id)) {
    return "This plot needs at least two sample or group profiles. A single-row table is better shown as Bar or Histogram.";
  }
  if (preset.id === "correlation") {
    return "Correlation needs at least two observation rows. A single-row profile is better shown as Bar or Histogram.";
  }
  return "";
}

function plotSupportedForTable(preset, tableSummary) {
  return !tableSuitabilityWarning(preset, tableSummary);
}

function previewSpecForRenderability(preset, spec, tableSummary) {
  const warning = tableSuitabilityWarning(preset, tableSummary);
  if (!warning) return spec;
  return {
    ...(spec || {}),
    plot_type: spec?.plot_type || preset?.id,
    data: [],
    layout: spec?.layout || {},
    config: spec?.config || {},
    warnings: [warning, ...(spec?.warnings || [])],
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

function paramValuesEqual(left, right) {
  return JSON.stringify(left ?? "") === JSON.stringify(right ?? "");
}

function parameterValueIsModified(parameter, value) {
  if (value === undefined) return false;
  return !paramValuesEqual(value, parameter.default);
}

function ParamLabel({ parameter, options, modified, modifiedLabel }) {
  const help = parameterHelpText(parameter, options);
  return (
    <span className="plot-param-label">
      <strong>
        {parameter.label}
        {modified ? <em className="plot-param-modified">{modifiedLabel}</em> : null}
      </strong>
      {help ? <small>{help}</small> : null}
    </span>
  );
}

function ParameterControl({ parameter, value, tableSummary, plotId, onChange, t }) {
  const options = optionsForParameter(parameter, tableSummary, plotId);
  const resolvedValue = value ?? parameter.default ?? "";
  const modified = parameterValueIsModified(parameter, value);

  if (parameter.type === "boolean") {
    return (
      <label className="plot-param-row checkbox">
        <input
          type="checkbox"
          checked={Boolean(resolvedValue)}
          onChange={(event) => onChange(parameter.id, event.target.checked)}
        />
        <ParamLabel parameter={parameter} options={options} modified={modified} modifiedLabel={t("parameterModified")} />
      </label>
    );
  }

  if (parameter.type === "select") {
    return (
      <label className="plot-param-row">
        <ParamLabel parameter={parameter} options={options} modified={modified} modifiedLabel={t("parameterModified")} />
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
        <ParamLabel parameter={parameter} options={options} modified={modified} modifiedLabel={t("parameterModified")} />
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
        <ParamLabel parameter={parameter} options={options} modified={modified} modifiedLabel={t("parameterModified")} />
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
        <ParamLabel parameter={parameter} options={options} modified={modified} modifiedLabel={t("parameterModified")} />
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
        <ParamLabel parameter={parameter} options={options} modified={modified} modifiedLabel={t("parameterModified")} />
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

  if (parameter.type === "json") {
    return (
      <label className="plot-param-row">
        <ParamLabel parameter={parameter} options={options} modified={modified} modifiedLabel={t("parameterModified")} />
        <textarea
          value={JSON.stringify(resolvedValue || {}, null, 2)}
          rows={4}
          onChange={(event) => onChange(parameter.id, normalizeParamValue(parameter, event.target.value))}
        />
      </label>
    );
  }

  return (
    <label className="plot-param-row">
      <ParamLabel parameter={parameter} options={options} modified={modified} modifiedLabel={t("parameterModified")} />
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

function ReportGuidance({ guidance, t }) {
  if (!guidance) return null;
  const groups = [
    { id: "safe", title: t("safeClaims"), items: guidance.safe_claims || [] },
    { id: "avoid", title: t("avoidClaims"), items: guidance.avoid_claims || [] },
    { id: "next", title: t("nextChecks"), items: guidance.next_checks || [] },
  ].filter((group) => group.items.length);
  if (!groups.length) return null;
  return (
    <section className="plot-report-guidance" aria-label={t("reportGuidance")}>
      <div>
        <strong>{t("reportGuidance")}</strong>
        <small>{t("reportGuidanceHint")}</small>
      </div>
      {groups.map((group) => (
        <article className={`plot-report-guidance-card ${group.id}`} key={group.id}>
          <span>{group.title}</span>
          <ul>
            {group.items.slice(0, 4).map((item) => <li key={item}>{item}</li>)}
          </ul>
        </article>
      ))}
    </section>
  );
}

function formatReportPrompt(prompt) {
  if (!prompt) return "";
  const checklist = Array.isArray(prompt.checklist) && prompt.checklist.length
    ? `\n\nChecklist:\n${prompt.checklist.map((item) => `- ${item}`).join("\n")}`
    : "";
  return `System:\n${prompt.system || ""}\n\nUser:\n${prompt.user || ""}${checklist}`;
}

function ReportPrompt({ prompt, copied, onCopy, t }) {
  if (!prompt) return null;
  return (
    <details className="plot-report-prompt">
      <summary>
        <span>{t("reportPrompt")}</span>
        <Button shape="round" size="small" variant="outline" onClick={onCopy}>
          {copied ? t("copied") : t("copyPrompt")}
        </Button>
      </summary>
      <p>{t("reportPromptHint")}</p>
      <div>
        <strong>System</strong>
        <pre>{prompt.system}</pre>
      </div>
      <div>
        <strong>User</strong>
        <pre>{prompt.user}</pre>
      </div>
      {Array.isArray(prompt.checklist) && prompt.checklist.length ? (
        <div>
          <strong>{t("promptChecklist")}</strong>
          <ul>{prompt.checklist.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      ) : null}
    </details>
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
  const renderability = plotSpec?.renderability || null;
  const currentData = renderability?.current_data || [];
  const requirements = renderability?.requirements || [];
  const alternatives = recommendedPresets.filter((preset) => preset.id !== selectedPreset?.id).slice(0, 4);
  return (
    <div className="plot-preview-empty">
      <div className="plot-preview-empty-copy">
        <span>{t("chartNotSuitable")}</span>
        <strong>{selectedPreset?.label || t("plotStudio")}</strong>
        <p>{message}</p>
      </div>
      {currentData.length || requirements.length ? (
        <div className="plot-renderability-grid">
          {currentData.length ? (
            <section>
              <small>{t("currentData")}</small>
              <div>
                {currentData.map((item) => (
                  <span key={item.label}>
                    <em>{item.label}</em>
                    <strong>{item.value}</strong>
                  </span>
                ))}
              </div>
            </section>
          ) : null}
          {requirements.length ? (
            <section>
              <small>{t("chartRequirements")}</small>
              <ul>
                {requirements.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </section>
          ) : null}
        </div>
      ) : null}
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

function clampPreviewMargin(margin, width, height) {
  const fallback = { l: 72, r: 42, t: 62, b: 64 };
  const source = margin || {};
  const maxHorizontal = Math.max(42, Math.floor(width * 0.26));
  const maxVertical = Math.max(40, Math.floor(height * 0.26));
  const fit = (value, defaultValue, maxValue) => {
    const numericValue = Number(value);
    return Math.min(Number.isFinite(numericValue) ? numericValue : defaultValue, maxValue);
  };
  return {
    l: fit(source.l, fallback.l, maxHorizontal),
    r: fit(source.r, fallback.r, Math.max(24, Math.floor(width * 0.14))),
    t: fit(source.t, fallback.t, maxVertical),
    b: fit(source.b, fallback.b, Math.max(30, Math.floor(height * 0.22))),
  };
}

function fitPlotlyLayoutToPreview(layout, width, height) {
  const renderInset = 10;
  const fittedWidth = Math.max(260, Math.floor(width - renderInset));
  const fittedHeight = Math.max(300, Math.floor(height - renderInset));
  const margin = clampPreviewMargin(layout?.margin, fittedWidth, fittedHeight);
  const previewLayout = {
    ...(layout || {}),
    autosize: false,
    width: fittedWidth,
    height: fittedHeight,
    margin: { ...margin, pad: 0 },
    title: {
      ...(layout?.title || {}),
      automargin: true,
    },
  };
  Object.keys(previewLayout)
    .filter((key) => /^xaxis\d*$|^yaxis\d*$/.test(key))
    .forEach((key) => {
      previewLayout[key] = {
        ...(previewLayout[key] || {}),
        automargin: true,
      };
    });
  if (layout?.polar) {
    const radialPad = fittedHeight < 520 ? 0.16 : 0.12;
    const availableRatio = Math.min(1, fittedHeight / Math.max(fittedWidth, 1));
    const halfWidth = Math.max(0.22, Math.min(0.42, availableRatio * 0.42));
    previewLayout.polar = {
      ...layout.polar,
      domain: {
        ...(layout.polar.domain || {}),
        x: [0.5 - halfWidth, 0.5 + halfWidth],
        y: [radialPad, 1 - radialPad],
      },
    };
  }
  if (layout?.scene) {
    previewLayout.scene = {
      ...layout.scene,
      domain: { ...(layout.scene.domain || {}), x: [0.04, 0.96], y: [0.05, 0.95] },
    };
    previewLayout.dragmode = ["orbit", "turntable"].includes(layout.dragmode) ? layout.dragmode : "orbit";
  }
  if (layout?.ternary) {
    previewLayout.ternary = {
      ...layout.ternary,
      domain: { ...(layout.ternary.domain || {}), x: [0.08, 0.92], y: [0.08, 0.92] },
    };
  }
  return previewLayout;
}

function fitPlotlyConfigToPreview(config, layout) {
  const has3dScene = Boolean(layout?.scene);
  return {
    ...(config || {}),
    responsive: true,
    displaylogo: false,
    displayModeBar: has3dScene ? "hover" : false,
    scrollZoom: has3dScene || Boolean(config?.scrollZoom),
  };
}

function InteractivePlot({ spec, plotRef: externalPlotRef }) {
  const localPlotRef = useRef(null);
  const plotRef = externalPlotRef || localPlotRef;
  const [plotError, setPlotError] = useState("");

  useEffect(() => {
    if (!plotRef.current || !spec) return undefined;
    setPlotError("");
    let cancelled = false;
    const plotElement = plotRef.current;
    let resizeObserver = null;
    let resizeFrame = null;
    let lastSize = { width: 0, height: 0 };
    loadPlotly().then((Plotly) => {
      if (cancelled) return;
      const renderPlot = (force = false) => {
        if (cancelled) return;
        const shellElement = plotElement.closest(".plotly-preview-shell") || plotElement;
        const bounds = shellElement.getBoundingClientRect();
        const width = Math.max(280, Math.floor(shellElement.clientWidth || bounds.width || 640));
        const height = Math.max(320, Math.floor(shellElement.clientHeight || bounds.height || 520));
        if (!force && width === lastSize.width && height === lastSize.height) return;
        lastSize = { width, height };
        const previewLayout = fitPlotlyLayoutToPreview(spec.layout, width, height);
        Plotly.react(plotElement, spec.data || [], previewLayout, fitPlotlyConfigToPreview(spec.config, previewLayout));
      };
      renderPlot(true);
      resizeObserver = new ResizeObserver(() => {
        if (resizeFrame) window.cancelAnimationFrame(resizeFrame);
        resizeFrame = window.requestAnimationFrame(renderPlot);
      });
      const shellElement = plotElement.closest(".plotly-preview-shell");
      resizeObserver.observe(shellElement || plotElement);
    }).catch((error) => {
      if (!cancelled) setPlotError(error.message || "Plotly failed to load");
    });
    return () => {
      cancelled = true;
      if (resizeFrame) window.cancelAnimationFrame(resizeFrame);
      resizeObserver?.disconnect();
      if (window.Plotly) window.Plotly.purge(plotElement);
    };
  }, [spec]);

  return (
    <div className="plotly-preview-shell">
      <div className="plotly-preview" ref={plotRef} />
      {plotError ? <p className="plot-error">{plotError}</p> : null}
    </div>
  );
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

function sortPresetsByRecommendation(presets, recommendedPlotIds) {
  if (!recommendedPlotIds.length) return presets;
  const recommendedRank = new Map(recommendedPlotIds.map((plotId, index) => [plotId, index]));
  return [...presets].sort((left, right) => {
    const leftRank = recommendedRank.has(left.id) ? recommendedRank.get(left.id) : Number.MAX_SAFE_INTEGER;
    const rightRank = recommendedRank.has(right.id) ? recommendedRank.get(right.id) : Number.MAX_SAFE_INTEGER;
    if (leftRank !== rightRank) return leftRank - rightRank;
    return 0;
  });
}

function isAdvancedParameterGroup(group) {
  if (typeof group.advanced === "boolean") return group.advanced;
  return ["theme", "export", "labels", "style"].includes(group.id);
}

function filterParameterGroups(groups, query) {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) return groups;
  return groups
    .map((group) => {
      const groupText = [group.id, group.label].filter(Boolean).join(" ").toLowerCase();
      const groupMatches = groupText.includes(normalizedQuery);
      const parameters = groupMatches
        ? group.parameters || []
        : (group.parameters || []).filter((parameter) => (
          [
            parameter.id,
            parameter.label,
            parameter.type,
            parameter.help,
            ...(parameter.options || []),
          ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase()
            .includes(normalizedQuery)
        ));
      return { ...group, parameters };
    })
    .filter((group) => group.parameters.length > 0);
}

function parameterCount(groups) {
  return groups.reduce((total, group) => total + (group.parameters?.length || 0), 0);
}

export function PlotStudioPage({ session, report, activeTaskId, onSelectSource, onSessionChange, onOpenAnalysis, onSaveToResult }) {
  const { t } = useI18n();
  const outputs = report?.outputs || [];
  const selectedSource = useMemo(() => normalizePlotStudioSource(session?.source), [session?.source]);
  const selectedSourceKey = plotStudioSourceKey(selectedSource);
  const normalizedReturnTarget = useMemo(
    () => normalizePlotStudioSource(session?.returnTarget),
    [session?.returnTarget],
  );
  const [manifest, setManifest] = useState(null);
  const [selectedPlotId, setSelectedPlotId] = useState(session?.selectedPlotId || "");
  const [params, setParams] = useState(session?.params || {});
  const [studioReport, setStudioReport] = useState(null);
  const [sourceResolution, setSourceResolution] = useState(null);
  const [plotSpec, setPlotSpec] = useState(null);
  const [status, setStatus] = useState("idle");
  const [sourceStatus, setSourceStatus] = useState("idle");
  const [specStatus, setSpecStatus] = useState("idle");
  const [error, setError] = useState("");
  const [specError, setSpecError] = useState("");
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [agentContextCopied, setAgentContextCopied] = useState(false);
  const [reportPromptCopied, setReportPromptCopied] = useState(false);
  const [plotSearch, setPlotSearch] = useState("");
  const [parameterSearch, setParameterSearch] = useState("");
  const [recommendedOnly, setRecommendedOnly] = useState(false);
  const [plotStudioView, setPlotStudioView] = useState("workbench");
  const [activeGalleryCategory, setActiveGalleryCategory] = useState("All");
  const [editCommand, setEditCommand] = useState("");
  const [editCommandStatus, setEditCommandStatus] = useState("");
  const [expandedPlotCategories, setExpandedPlotCategories] = useState(() => new Set());
  const [uploadStatus, setUploadStatus] = useState("idle");
  const [uploadError, setUploadError] = useState("");
  const [exampleLoadingId, setExampleLoadingId] = useState("");
  const [saveBackStatus, setSaveBackStatus] = useState("idle");
  const [saveBackError, setSaveBackError] = useState("");
  const [plotExportStatus, setPlotExportStatus] = useState("idle");
  const [plotExportError, setPlotExportError] = useState("");
  const [editHistory, setEditHistory] = useState(session?.editHistory || []);
  const plotExportRef = useRef(null);
  const defaultExampleLoadedRef = useRef(false);

  useEffect(() => {
    let active = true;
    fetchPlotStudioJson("/api/plot-studio/presets")
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

  const plotPresets = manifest?.presets || [];

  useEffect(() => {
    if (selectedSource || defaultExampleLoadedRef.current || !plotPresets.length) return;
    defaultExampleLoadedRef.current = true;
    setExampleLoadingId("default");
    setUploadError("");
    loadDefaultPlotStudioExample()
      .then((payload) => {
        const nextSource = normalizePlotStudioSource(payload.source);
        const defaultPlotId = nextSource?.meta?.plot_id || "scatter";
        const defaultPreset = plotPresets.find((preset) => preset.id === defaultPlotId);
        onSelectSource?.(nextSource);
        setSelectedPlotId(defaultPlotId);
        if (defaultPreset) setParams(defaultParamsFromPreset(defaultPreset));
        setEditCommandStatus("");
        setUploadStatus("idle");
        setPlotStudioView("workbench");
      })
      .catch((defaultExampleFailure) => {
        setUploadError(defaultExampleFailure.message);
      })
      .finally(() => {
        setExampleLoadingId("");
      });
  }, [onSelectSource, plotPresets, selectedSource]);

  useEffect(() => {
    const examplePlotId = selectedSource?.sourceKind === "plot_studio_example"
      ? selectedSource?.meta?.plot_id || ""
      : "";
    setSelectedPlotId(session?.selectedPlotId || examplePlotId);
    setParams(session?.params || {});
    setEditCommand("");
    setEditCommandStatus("");
    setEditHistory(session?.editHistory || []);
    setPlotSearch("");
    setRecommendedOnly(Boolean(selectedSource && selectedSource.sourceKind !== "plot_studio_example"));
  }, [selectedSourceKey]);

  useEffect(() => {
    onSessionChange?.((current) => {
      if (!current || plotStudioSourceKey(current.source) !== selectedSourceKey) return current;
      if (
        current.selectedPlotId === selectedPlotId &&
        current.params === params &&
        current.editHistory === editHistory
      ) {
        return current;
      }
      return {
        ...current,
        selectedPlotId,
        params,
        editHistory,
      };
    });
  }, [editHistory, onSessionChange, params, selectedPlotId, selectedSourceKey]);

  useEffect(() => {
    if (!selectedSource) {
      setSourceResolution(null);
      setSourceStatus("idle");
      return undefined;
    }
    const controller = new AbortController();
    setSourceResolution(null);
    setSourceStatus("loading");
    resolvePlotStudioSource(selectedSource, {
      signal: controller.signal,
    })
      .then((payload) => {
        setSourceResolution(payload);
        setSourceStatus("ready");
        if (payload.default_plot_id) {
          setSelectedPlotId((current) => current || payload.default_plot_id);
        }
      })
      .catch((resolveError) => {
        if (resolveError.name === "AbortError") return;
        setSourceResolution(null);
        setError(resolveError.message);
        setSourceStatus("error");
      });
    return () => controller.abort();
  }, [selectedSource]);

  const tableSummary = sourceResolution?.table_summary || studioReport?.table_summary || null;
  const preferredPreviewNumericColumns = useMemo(() => preferredNumericColumns(tableSummary), [tableSummary]);
  const skippedPreviewNumericColumns = tableSummary?.signals?.matrix_profile?.excluded_numeric_columns || [];
  const recommendedPlotIds = sourceResolution?.recommended_plot_ids || studioReport?.recommended_plot_ids || [];
  const filteredGroupedPresets = useMemo(() => {
    const query = plotSearch.trim().toLowerCase();
    const recommendedSet = new Set(recommendedPlotIds);
    const waitingForRecommendations = recommendedOnly && selectedSource && sourceStatus === "loading";
    const applyRecommendedFilter = recommendedOnly && recommendedPlotIds.length > 0;
    if (waitingForRecommendations) return [];
    const filtered = plotPresets.filter((preset) => {
      if (applyRecommendedFilter && !recommendedSet.has(preset.id)) return false;
      if (!query) return true;
      return [preset.id, preset.label, preset.category, preset.engine, preset.use_case, preset.description]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query));
    });
    return groupPlotPresets(sortPresetsByRecommendation(filtered, recommendedPlotIds));
  }, [plotPresets, plotSearch, recommendedOnly, recommendedPlotIds, selectedSource, sourceStatus]);
  const visiblePlotCount = filteredGroupedPresets.reduce((total, group) => total + group.items.length, 0);
  const filteredGroupSignature = filteredGroupedPresets
    .map((group) => `${group.category}:${group.items.map((item) => item.id).join(",")}`)
    .join("|");
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
  const selectedPresetIsSupported = plotSupportedForTable(selectedPreset, tableSummary);

  useEffect(() => {
    const categories = filteredGroupedPresets.map((group) => group.category);
    if (!categories.length) {
      setExpandedPlotCategories(new Set());
      setActiveGalleryCategory("All");
      return;
    }
    setActiveGalleryCategory((current) => (current === "All" || categories.includes(current) ? current : "All"));
    const requiredOpen = new Set();
    if (selectedPreset?.category) requiredOpen.add(selectedPreset.category || "Other");
    filteredGroupedPresets.forEach((group) => {
      if (group.items.some((plot) => recommendedPlotIds.includes(plot.id))) {
        requiredOpen.add(group.category);
      }
    });
    setExpandedPlotCategories((current) => {
      if (plotSearch.trim()) return new Set(categories);
      const next = current.size
        ? new Set([...current].filter((category) => categories.includes(category)))
        : new Set(requiredOpen);
      requiredOpen.forEach((category) => next.add(category));
      return next;
    });
  }, [filteredGroupSignature, plotSearch, recommendedPlotIds.join("|"), selectedPreset?.category]);

  useEffect(() => {
    if (!selectedPreset) return;
    setParams((current) => mergePresetDefaultsWithCurrent(selectedPreset, current));
  }, [selectedPreset?.id]);

  useEffect(() => {
    if (!selectedPreset || selectedPresetIsSupported || !recommendedPlotIds.length) return;
    const fallbackId = recommendedPlotIds.find((plotId) => {
      const fallbackPreset = plotPresets.find((preset) => preset.id === plotId);
      return plotSupportedForTable(fallbackPreset, tableSummary);
    });
    if (!fallbackId || fallbackId === selectedPreset.id) return;
    const fallbackPreset = plotPresets.find((preset) => preset.id === fallbackId);
    setSelectedPlotId(fallbackId);
    setParams(defaultParamsFromPreset(fallbackPreset));
  }, [plotPresets, recommendedPlotIds, selectedPreset?.id, selectedPresetIsSupported, tableSummary]);

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
  }, [selectedPreset?.id, plotStudioSourceKey(selectedSource), tableSummary]);

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
    createPlotStudioReport({
      source: selectedSource,
      plotType: selectedPlotId || undefined,
      params,
    }, {
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
    createPlotStudioSpec({
      source: selectedSource,
      plotType: selectedPlotId,
      params,
    }, {
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
  const filteredBasicParameterGroups = useMemo(
    () => filterParameterGroups(basicParameterGroups, parameterSearch),
    [basicParameterGroups, parameterSearch],
  );
  const filteredAdvancedParameterGroups = useMemo(
    () => filterParameterGroups(advancedParameterGroups, parameterSearch),
    [advancedParameterGroups, parameterSearch],
  );
  const basicParameterCount = parameterCount(filteredBasicParameterGroups);
  const advancedParameterCount = parameterCount(filteredAdvancedParameterGroups);
  const hasParameterMatches = basicParameterCount + advancedParameterCount > 0;
  const reportSections = studioReport?.report?.sections || [];
  const reportGuidance = studioReport?.agent_context?.report_guidance || null;
  const reportPrompt = studioReport?.agent_context?.report_prompt || null;
  const reportPromptText = useMemo(
    () => formatReportPrompt(reportPrompt),
    [reportPrompt],
  );
  const agentContextText = useMemo(
    () => (studioReport?.agent_context ? JSON.stringify(studioReport.agent_context, null, 2) : ""),
    [studioReport?.agent_context],
  );
  const previewSpec = useMemo(
    () => previewSpecForRenderability(selectedPreset, plotSpec, tableSummary),
    [selectedPreset?.id, plotSpec, tableSummary],
  );
  const canSaveBackToResult = Boolean(
    normalizedReturnTarget &&
    selectedSource &&
    selectedSource.taskId &&
    selectedSource.taskId === normalizedReturnTarget.taskId &&
    selectedSource.nodeId === normalizedReturnTarget.nodeId &&
    onSaveToResult,
  );

  useEffect(() => {
    setSaveBackStatus("idle");
    setSaveBackError("");
    setPlotExportStatus("idle");
    setPlotExportError("");
  }, [plotStudioSourceKey(selectedSource), selectedPreset?.id, params]);

  const updateParam = (paramId, value) => {
    setParams((current) => ({ ...current, [paramId]: value }));
  };

  const selectPlotPreset = (plot) => {
    if (!plotSupportedForTable(plot, tableSummary)) return;
    setSelectedPlotId(plot.id);
    setParams(defaultParamsFromPreset(plot));
    setEditCommandStatus("");
  };

  const loadExampleData = async (plot) => {
    setExampleLoadingId(plot.id);
    setUploadError("");
    try {
      const payload = await loadPlotStudioExample(plot.id);
      const nextSource = normalizePlotStudioSource(payload.source);
      onSelectSource?.(nextSource);
      setSelectedPlotId(plot.id);
      setParams(defaultParamsFromPreset(plot));
      setEditCommandStatus("");
      setUploadStatus("idle");
      setPlotStudioView("workbench");
    } catch (exampleFailure) {
      setUploadError(exampleFailure.message);
    } finally {
      setExampleLoadingId("");
    }
  };

  const togglePlotCategory = (category) => {
    setExpandedPlotCategories((current) => {
      const next = new Set(current);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });
  };

  const resetParams = () => {
    if (selectedPreset) setParams(defaultParamsFromPreset(selectedPreset));
    setEditCommandStatus("");
  };

  const uploadPlotStudioTable = async (file) => {
    if (!file) return;
    setUploadStatus("loading");
    setUploadError("");
    try {
      const response = await fetch(`/api/plot-studio/uploads?filename=${encodeURIComponent(file.name)}`, {
        method: "POST",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file,
      });
      if (!response.ok) {
        const text = await response.text();
        let detail = text || response.statusText;
        try {
          const payload = JSON.parse(text);
          detail = payload.detail || detail;
        } catch {
          // Keep the plain-text response body or status text.
        }
        throw new Error(detail);
      }
      const payload = await response.json();
      const nextSource = normalizePlotStudioSource(payload.source);
      onSelectSource?.(nextSource);
      setSelectedPlotId("");
      setParams({});
      setEditCommand("");
      setEditCommandStatus("");
      setUploadStatus("ready");
    } catch (uploadFailure) {
      setUploadError(uploadFailure.message);
      setUploadStatus("error");
    }
  };

  const saveCurrentPlotToResult = async () => {
    if (!canSaveBackToResult || !selectedSource || !selectedPreset) return;
    setSaveBackStatus("saving");
    setSaveBackError("");
    try {
      await onSaveToResult({
        source: selectedSource,
        plotType: selectedPreset.id || selectedPlotId,
        params,
      });
      setSaveBackStatus("saved");
    } catch (saveFailure) {
      setSaveBackError(saveFailure.message);
      setSaveBackStatus("error");
    }
  };

  const exportCurrentPlotImage = async () => {
    if (!previewSpec?.data?.length || !plotExportRef.current) return;
    setPlotExportStatus("image");
    setPlotExportError("");
    try {
      const Plotly = await loadPlotly();
      const options = plotExportOptionsFromSpec(previewSpec, "png");
      if (options.format === "tif") {
        const dataUrl = await Plotly.toImage(plotExportRef.current, { ...options, format: "png" });
        const tiffBlob = await dataUrlToTiffBlob(dataUrl);
        downloadBlob(tiffBlob, `${options.filename}.tif`);
      } else {
        const dataUrl = await Plotly.toImage(plotExportRef.current, options);
        downloadDataUrl(dataUrl, `${options.filename}.${options.format}`);
      }
      setPlotExportStatus("ready");
    } catch (exportFailure) {
      setPlotExportError(exportFailure.message || "导出高清图失败。");
      setPlotExportStatus("error");
    }
  };

  const exportCurrentPlotPdf = async () => {
    if (!previewSpec?.data?.length || !plotExportRef.current) return;
    const printWindow = createPlotExportPrintWindow();
    setPlotExportStatus("pdf");
    setPlotExportError("");
    try {
      const Plotly = await loadPlotly();
      const options = plotExportOptionsFromSpec(previewSpec, "svg");
      const dataUrl = await Plotly.toImage(plotExportRef.current, { ...options, format: "svg" });
      const opened = openPlotExportPrintWindow({
        dataUrl,
        filename: options.filename,
        printWindow,
        title: selectedPreset?.label || "Plot Studio",
      });
      if (!opened) {
        setPlotExportError("浏览器阻止了 PDF 打印窗口，已下载可打印 HTML 文件。打开后按 Ctrl+P 保存为 PDF。");
      }
      setPlotExportStatus("ready");
    } catch (exportFailure) {
      if (printWindow) printWindow.close();
      setPlotExportError(exportFailure.message || "导出 PDF 失败。");
      setPlotExportStatus("error");
    }
  };

  const applyEditCommand = async (event) => {
    event.preventDefault();
    if (!selectedPreset || !editCommand.trim()) return;
    setEditCommandStatus("Agent 正在解析...");
    try {
      const payload = await createPlotStudioAgentEdit({
        plotType: selectedPreset.id || selectedPlotId,
        params,
        prompt: editCommand,
        parameterSchema: selectedPreset,
        outputTemplate: { param_patch: {}, applied: [], message: "" },
        context: {
          source: selectedSource,
          tableSummary,
          selectedPlot: {
            id: selectedPreset.id,
            label: selectedPreset.label,
            description: selectedPreset.description,
            use_case: selectedPreset.use_case,
          },
          editHistory,
        },
      });
      const patch = payload.param_patch || {};
      if (!Object.keys(patch).length) {
        setEditCommandStatus(payload.message || "没有识别到可更新的参数。");
        return;
      }
      setParams((current) => ({ ...current, ...patch }));
      setEditHistory((current) => [
        ...current.slice(-7),
        {
          request: editCommand,
          param_patch: patch,
          message: payload.message || "",
        },
      ]);
      setEditCommandStatus(payload.applied?.length ? `已更新：${payload.applied.join("；")}` : "已更新参数。");
    } catch (agentFailure) {
      setEditCommandStatus(agentFailure.message);
    }
  };

  return (
    <main className="plot-page shell">
      <section className="hero plot-hero">
        <div>
          <p className="eyebrow plot-title-line">
            <span>Plot Studio</span>
            <small>{t("figureWorkspaceTitle")}</small>
          </p>
        </div>
        <div className="plot-view-switch">
          <Button
            className={plotStudioView === "gallery" ? "active" : ""}
            theme={plotStudioView === "gallery" ? "primary" : "default"}
            variant={plotStudioView === "gallery" ? "base" : "outline"}
            shape="round"
            onClick={() => setPlotStudioView("gallery")}
          >
            示例画廊
          </Button>
          <Button
            className={plotStudioView === "workbench" ? "active" : ""}
            theme={plotStudioView === "workbench" ? "primary" : "default"}
            variant={plotStudioView === "workbench" ? "base" : "outline"}
            shape="round"
            onClick={() => setPlotStudioView("workbench")}
          >
            参数工作台
          </Button>
          <Button theme="primary" variant="outline" shape="round" onClick={onOpenAnalysis}>
            {t("backToAnalysis")}
          </Button>
        </div>
      </section>

      {plotStudioView === "gallery" ? (
        <PlotGalleryPanel
          t={t}
          sourceStatus={sourceStatus}
          selectedSource={selectedSource}
          plotSearch={plotSearch}
          onPlotSearchChange={setPlotSearch}
          recommendedOnly={recommendedOnly}
          onToggleRecommendedOnly={() => setRecommendedOnly((current) => !current)}
          recommendedPlotIds={recommendedPlotIds}
          visiblePlotCount={visiblePlotCount}
          plotPresets={plotPresets}
          filteredGroupedPresets={filteredGroupedPresets}
          selectedPreset={selectedPreset}
          activeCategory={activeGalleryCategory}
          onActiveCategoryChange={setActiveGalleryCategory}
          onLoadExampleData={loadExampleData}
          exampleLoadingId={exampleLoadingId}
          onOpenWorkbench={() => setPlotStudioView("workbench")}
          Thumbnail={MiniPlotThumbnail}
        />
      ) : (
        <section className="plot-studio-layout">
        <PlotTypePanel
          t={t}
          sourceStatus={sourceStatus}
          selectedSource={selectedSource}
          error={error}
          uploadStatus={uploadStatus}
          uploadError={uploadError}
          onUploadTable={uploadPlotStudioTable}
          plotSearch={plotSearch}
          onPlotSearchChange={setPlotSearch}
          recommendedOnly={recommendedOnly}
          onToggleRecommendedOnly={() => setRecommendedOnly((current) => !current)}
          recommendedPlotIds={recommendedPlotIds}
          visiblePlotCount={visiblePlotCount}
          plotPresets={plotPresets}
          filteredGroupedPresets={filteredGroupedPresets}
          expandedPlotCategories={expandedPlotCategories}
          onTogglePlotCategory={togglePlotCategory}
          selectedPreset={selectedPreset}
          onLoadExampleData={loadExampleData}
          exampleLoadingId={exampleLoadingId}
          outputs={outputs}
          activeTaskId={activeTaskId}
          onSelectSource={onSelectSource}
          Thumbnail={MiniPlotThumbnail}
        />

        <section className="plot-library-panel">
          <PlotPreviewPanel
            t={t}
            selectedPreset={selectedPreset}
            selectedSource={selectedSource}
            specStatus={specStatus}
            normalizedReturnTarget={normalizedReturnTarget}
            canSaveBackToResult={canSaveBackToResult}
            previewSpec={previewSpec}
            saveBackStatus={saveBackStatus}
            saveBackError={saveBackError}
            onSaveBack={saveCurrentPlotToResult}
            plotExportStatus={plotExportStatus}
            plotExportError={plotExportError}
            onExportImage={exportCurrentPlotImage}
            onExportPdf={exportCurrentPlotPdf}
            tableSummary={tableSummary}
            params={params}
            specError={specError}
            recommendedPresets={recommendedPresets}
            onSelectPlot={selectPlotPreset}
            plotRef={plotExportRef}
            MethodOverview={PlotMethodOverview}
            MappingSummary={PlotMappingSummary}
            InteractivePlotComponent={InteractivePlot}
            EmptyPreview={PlotPreviewEmpty}
          />
          <PlotDataPreviewPanel
            t={t}
            tableSummary={tableSummary}
            preferredPreviewNumericColumns={preferredPreviewNumericColumns}
            skippedPreviewNumericColumns={skippedPreviewNumericColumns}
            metaEntries={metaEntries}
            valuePreview={valuePreview}
          />
        </section>

        <aside className="plot-inspector-panel">
          <PlotSourcePanel t={t} selectedSource={selectedSource} />
          <PlotParamsPanel
            t={t}
            selectedPreset={selectedPreset}
            parameterSearch={parameterSearch}
            onParameterSearchChange={setParameterSearch}
            onClearParameterSearch={() => setParameterSearch("")}
            onResetParams={resetParams}
            onRunPreview={() => setRefreshNonce((current) => current + 1)}
            editCommand={editCommand}
            onEditCommandChange={setEditCommand}
            onApplyEditCommand={applyEditCommand}
            editCommandStatus={editCommandStatus}
            filteredBasicParameterGroups={filteredBasicParameterGroups}
            filteredAdvancedParameterGroups={filteredAdvancedParameterGroups}
            basicParameterCount={basicParameterCount}
            advancedParameterCount={advancedParameterCount}
            hasParameterMatches={hasParameterMatches}
            params={params}
            tableSummary={tableSummary}
            onUpdateParam={updateParam}
            ParameterControlComponent={ParameterControl}
          />
          <PlotReportPanel
            t={t}
            status={status}
            studioReport={studioReport}
            reportSections={reportSections}
            reportGuidance={reportGuidance}
            reportPrompt={reportPrompt}
            reportPromptCopied={reportPromptCopied}
            onCopyReportPrompt={async (event) => {
              event.preventDefault();
              event.stopPropagation();
              const copied = await copyTextToClipboard(reportPromptText);
              setReportPromptCopied(copied);
              window.setTimeout(() => setReportPromptCopied(false), 1600);
            }}
            agentContextText={agentContextText}
            agentContextCopied={agentContextCopied}
            onCopyAgentContext={async (event) => {
              event.preventDefault();
              event.stopPropagation();
              const copied = await copyTextToClipboard(agentContextText);
              setAgentContextCopied(copied);
              window.setTimeout(() => setAgentContextCopied(false), 1600);
            }}
            ReportSectionComponent={ReportSection}
            ReportGuidanceComponent={ReportGuidance}
            ReportPromptComponent={ReportPrompt}
          />
        </aside>
        </section>
      )}
    </main>
  );
}

