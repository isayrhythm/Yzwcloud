import { useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "../i18n.jsx";

let plotlyLoader = null;

function loadPlotly() {
  if (!plotlyLoader) {
    plotlyLoader = import("plotly.js-dist-min").then((module) => module.default || module);
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

function defaultParamsFromPreset(preset) {
  return { ...(preset?.default_params || {}) };
}

function optionsForParameter(parameter, tableSummary) {
  const columns = tableSummary?.columns || [];
  const numericColumns = tableSummary?.numeric_columns || [];
  if (parameter.type === "numeric_columns") return numericColumns;
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

function ParameterControl({ parameter, value, tableSummary, onChange }) {
  const options = optionsForParameter(parameter, tableSummary);
  const resolvedValue = value ?? parameter.default ?? "";

  if (parameter.type === "boolean") {
    return (
      <label className="plot-param-row checkbox">
        <input
          type="checkbox"
          checked={Boolean(resolvedValue)}
          onChange={(event) => onChange(parameter.id, event.target.checked)}
        />
        <span>{parameter.label}</span>
      </label>
    );
  }

  if (parameter.type === "select") {
    return (
      <label className="plot-param-row">
        <span>{parameter.label}</span>
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
        <span>{parameter.label}</span>
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
        <span>{parameter.label}</span>
        <select value={resolvedValue || ""} onChange={(event) => onChange(parameter.id, event.target.value || null)}>
          <option value="">{parameter.required ? "Select column" : "Auto / none"}</option>
          {options.map((option) => (
            <option value={option} key={option}>{option}</option>
          ))}
        </select>
      </label>
    );
  }

  if (parameter.type === "number" || parameter.type === "number_or_auto") {
    const isAuto = resolvedValue === "auto";
    return (
      <label className="plot-param-row">
        <span>{parameter.label}</span>
        <input
          type={isAuto ? "text" : "number"}
          value={resolvedValue}
          min={parameter.min}
          max={parameter.max}
          step={parameter.step || 1}
          onChange={(event) => onChange(parameter.id, normalizeParamValue(parameter, event.target.value))}
        />
      </label>
    );
  }

  return (
    <label className="plot-param-row">
      <span>{parameter.label}</span>
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

function MiniPlotThumbnail({ plotId }) {
  if (plotId === "boxplot") {
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
  if (plotId === "violin") {
    return (
      <div className="mini-plot mini-violin" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
    );
  }
  if (plotId === "bar") {
    return (
      <div className="mini-plot mini-bar" aria-hidden="true">
        {[38, 62, 48, 78, 54].map((height, index) => (
          <span style={{ height: `${height}%` }} key={index} />
        ))}
      </div>
    );
  }
  if (plotId === "line") {
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
  if (plotId === "heatmap" || plotId === "correlation") {
    return (
      <div className={`mini-plot mini-heatmap ${plotId === "correlation" ? "corr" : ""}`} aria-hidden="true">
        {Array.from({ length: 30 }, (_, index) => (
          <span key={index} />
        ))}
      </div>
    );
  }
  if (plotId === "bubble") {
    return (
      <div className="mini-plot mini-bubble" aria-hidden="true">
        <span className="b1" />
        <span className="b2" />
        <span className="b3" />
        <span className="b4" />
      </div>
    );
  }
  if (plotId === "volcano") {
    return (
      <div className="mini-plot mini-volcano" aria-hidden="true">
        {Array.from({ length: 24 }, (_, index) => (
          <span key={index} />
        ))}
      </div>
    );
  }
  if (plotId === "upset") {
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
  if (plotId === "venn") {
    return (
      <div className="mini-plot mini-venn" aria-hidden="true">
        <span className="v1" />
        <span className="v2" />
        <span className="v3" />
      </div>
    );
  }
  if (plotId === "enrichment_dot") {
    return (
      <div className="mini-plot mini-enrichment" aria-hidden="true">
        {[0, 1, 2, 3, 4].map((row) => (
          <span style={{ left: `${28 + row * 10}%`, top: `${18 + row * 14}%` }} key={row} />
        ))}
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
  }, [sourceKey(selectedSource)]);

  const plotPresets = manifest?.presets || [];
  const tableSummary = studioReport?.table_summary || null;
  const recommendedPlotIds = studioReport?.recommended_plot_ids || [];
  const selectedPreset = useMemo(() => {
    if (!plotPresets.length) return null;
    const reportSelected = studioReport?.selected_plot?.id;
    const preferredId = selectedPlotId || reportSelected || recommendedPlotIds[0] || plotPresets[0]?.id;
    return plotPresets.find((preset) => preset.id === preferredId) || plotPresets[0];
  }, [plotPresets, recommendedPlotIds, selectedPlotId, studioReport?.selected_plot?.id]);

  useEffect(() => {
    if (!selectedPreset) return;
    setParams((current) => ({ ...defaultParamsFromPreset(selectedPreset), ...current }));
  }, [selectedPreset?.id]);

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
  }, [selectedSource, selectedPlotId, params]);

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
  const reportSections = studioReport?.report?.sections || [];

  const updateParam = (paramId, value) => {
    setParams((current) => ({ ...current, [paramId]: value }));
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

      <section className="plot-studio-layout">
        <aside className="plot-agent-panel">
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
            <div className="plot-dropzone">
              <strong>{t("selectAnalysisOutput")}</strong>
              <p>{t("chooseWorkflowResult")}</p>
            </div>
          )}

          <div className="plot-param-list">
            {(manifest?.parameter_groups || FALLBACK_PARAMETER_GROUPS).map((group) => (
              <span key={group}>{group}</span>
            ))}
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
          <div className="panel-title">
            <h2>{t("figureTypes")}</h2>
            <span className="muted">{status === "loading" ? t("updating") : selectedSource?.type || t("selectSourceFirst")}</span>
          </div>
          <p className="plot-note">{t("interactiveEnginePlan")}</p>
          {error ? <p className="plot-error">{error}</p> : null}
          <div className="plot-type-grid">
            {plotPresets.map((plot) => {
              const recommended = recommendedPlotIds.includes(plot.id);
              const active = selectedPreset?.id === plot.id;
              return (
                <button
                  className={`plot-type-card ${recommended ? "recommended" : ""} ${active ? "active" : ""}`}
                  key={plot.id}
                  type="button"
                  onClick={() => {
                    setSelectedPlotId(plot.id);
                    setParams(defaultParamsFromPreset(plot));
                  }}
                >
                  <MiniPlotThumbnail plotId={plot.id} />
                  <strong>{plot.label}</strong>
                  <small>{recommended ? t("recommendedForSource") : plot.engine}</small>
                </button>
              );
            })}
          </div>

          <section className="plot-preview-panel">
            <div className="panel-title">
              <h2>{t("interactivePreview")}</h2>
              <span className="muted">{specStatus === "loading" ? t("rendering") : specStatus === "ready" ? t("ready") : specStatus}</span>
            </div>
            {specError ? <p className="plot-error">{specError}</p> : null}
            {plotSpec?.data?.length ? (
              <InteractivePlot spec={plotSpec} />
            ) : (
              <div className="plot-preview-empty">
                <strong>{selectedPreset?.label || t("plotStudio")}</strong>
                <p>{plotSpec?.warnings?.[0] || t("noRenderableChart")}</p>
              </div>
            )}
            {plotSpec?.warnings?.length ? (
              <div className="plot-warning-list">
                <strong>{t("plotWarnings")}</strong>
                {plotSpec.warnings.map((warning) => <span key={warning}>{warning}</span>)}
              </div>
            ) : null}
          </section>

          <section className="plot-workbench-grid">
            <article className="plot-config-panel">
              <div className="panel-title">
                <h2>{selectedPreset ? `${selectedPreset.label} ${t("parameters")}` : t("parameters")}</h2>
                <span className="muted">{selectedPreset?.engine || "-"}</span>
              </div>
              {selectedPreset?.description ? <p className="plot-note">{selectedPreset.description}</p> : null}
              <div className="plot-param-groups">
                {parameterGroups.length ? parameterGroups.map((group) => (
                  <section className="plot-param-group" key={group.id}>
                    <h3>{group.label}</h3>
                    <div className="plot-param-controls">
                      {group.parameters.map((parameter) => (
                        <ParameterControl
                          key={parameter.id}
                          parameter={parameter}
                          value={params[parameter.id]}
                          tableSummary={tableSummary}
                          onChange={updateParam}
                        />
                      ))}
                    </div>
                  </section>
                )) : <p className="muted">{t("loadingPresets")}</p>}
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
            </article>
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
                  <strong>{tableSummary.numeric_columns.slice(0, 8).join(", ") || "-"}</strong>
                </div>
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
      </section>
    </main>
  );
}
