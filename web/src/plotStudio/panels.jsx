import { normalizePlotStudioSource } from "./session.js";

export function PlotTypePanel({
  t,
  sourceStatus,
  selectedSource,
  error,
  uploadStatus,
  uploadError,
  onUploadTable,
  plotSearch,
  onPlotSearchChange,
  recommendedOnly,
  onToggleRecommendedOnly,
  recommendedPlotIds,
  visiblePlotCount,
  plotPresets,
  filteredGroupedPresets,
  expandedPlotCategories,
  onTogglePlotCategory,
  selectedPreset,
  tableSummary,
  tableSuitabilityWarning,
  onSelectPlot,
  onLoadExampleData,
  exampleLoadingId,
  outputs,
  activeTaskId,
  onSelectSource,
  Thumbnail,
}) {
  return (
    <aside className="plot-agent-panel">
      <div className="panel-title">
        <h2>{t("figureTypes")}</h2>
        <span className="muted">{sourceStatus === "loading" ? t("updating") : selectedSource?.type || t("selectSourceFirst")}</span>
      </div>
      {error ? <p className="plot-error">{error}</p> : null}
      <label className={`plot-upload-card ${uploadStatus === "loading" ? "loading" : ""}`}>
        <input
          type="file"
          accept=".csv,.tsv,.txt,.xlsx,.xlsm"
          onChange={(event) => {
            onUploadTable(event.target.files?.[0]);
            event.target.value = "";
          }}
        />
        <span>{t("uploadTable")}</span>
        <strong>{uploadStatus === "loading" ? t("uploading") : t("uploadTableHint")}</strong>
      </label>
      {uploadError ? <p className="plot-error">{uploadError}</p> : null}
      <div className="plot-type-filter" role="search">
        <input
          type="search"
          value={plotSearch}
          onChange={(event) => onPlotSearchChange(event.target.value)}
          placeholder={t("plotSearchPlaceholder")}
          aria-label={t("plotSearchPlaceholder")}
        />
        <button
          className={recommendedOnly ? "active" : ""}
          type="button"
          onClick={onToggleRecommendedOnly}
          disabled={!recommendedPlotIds.length}
        >
          {t("recommendedOnly")}
        </button>
        <span>{visiblePlotCount} / {plotPresets.length}</span>
      </div>
      <div className="plot-type-toolbox">
        {filteredGroupedPresets.length ? filteredGroupedPresets.map((group) => (
          <section className={`plot-type-section ${expandedPlotCategories.has(group.category) ? "expanded" : "collapsed"}`} key={group.category}>
            <button
              className="plot-type-section-header"
              type="button"
              aria-expanded={expandedPlotCategories.has(group.category)}
              onClick={() => onTogglePlotCategory(group.category)}
            >
              <span>
                <strong>{group.category}</strong>
                <small>{group.items.length}</small>
              </span>
              <i aria-hidden="true">{expandedPlotCategories.has(group.category) ? "-" : "+"}</i>
            </button>
            {expandedPlotCategories.has(group.category) ? (
              <div className="plot-type-grid compact">
                {group.items.map((plot) => {
                  const recommended = recommendedPlotIds.includes(plot.id);
                  const active = selectedPreset?.id === plot.id;
                  const unsupportedReason = tableSuitabilityWarning(plot, tableSummary);
                  const supported = !unsupportedReason;
                  return (
                    <article
                      className={`plot-type-card ${recommended ? "recommended" : ""} ${active ? "active" : ""} ${supported ? "" : "unsupported"}`}
                      key={plot.id}
                      title={supported ? plot.label : unsupportedReason}
                    >
                      <button
                        className="plot-type-select"
                        type="button"
                        disabled={!supported}
                        onClick={() => onSelectPlot(plot)}
                      >
                        <span className="plot-card-example">
                          <Thumbnail plotId={plot.id} thumbnail={plot.thumbnail} />
                          <em>{t("plotExample")}</em>
                        </span>
                        <span className="plot-type-card-main">
                          <strong>{plot.label}</strong>
                          <small>{plot.use_case || plot.description}</small>
                          {!supported ? <small className="plot-type-unsupported-reason">{unsupportedReason}</small> : null}
                          <span className="plot-type-meta">
                            <em>{plot.engine}</em>
                            {recommended ? <em className="recommended-badge">{t("recommendedForSource")}</em> : null}
                            {!supported ? <em className="unsupported-badge">{t("chartNotSuitable")}</em> : null}
                          </span>
                        </span>
                      </button>
                      <button
                        className="plot-example-action"
                        type="button"
                        onClick={() => onLoadExampleData(plot)}
                        disabled={exampleLoadingId === plot.id}
                      >
                        {exampleLoadingId === plot.id ? t("loadingExample") : t("useExampleData")}
                      </button>
                    </article>
                  );
                })}
              </div>
            ) : null}
          </section>
        )) : (
          <p className="muted">
            {recommendedOnly && selectedSource && sourceStatus === "loading"
              ? "濮濓絽婀弽瑙勫祦瑜版挸澧犻弫鐗堝祦缁涙盯鈧娴橀崹?.."
              : plotPresets.length ? t("noPlotTypeMatches") : t("loadingPresets")}
          </p>
        )}
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
              <button type="button" onClick={() => onSelectSource?.(normalizePlotStudioSource(output))}>
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
  );
}

export function PlotPreviewPanel({
  t,
  selectedPreset,
  selectedSource,
  specStatus,
  normalizedReturnTarget,
  canSaveBackToResult,
  previewSpec,
  saveBackStatus,
  saveBackError,
  onSaveBack,
  tableSummary,
  params,
  specError,
  recommendedPresets,
  onSelectPlot,
  MethodOverview,
  MappingSummary,
  InteractivePlotComponent,
  EmptyPreview,
}) {
  return (
    <section className="plot-preview-panel plot-preview-main">
      <div className="panel-title">
        <div>
          <h2>{selectedPreset?.label || t("interactivePreview")}</h2>
          <p>{selectedPreset?.description || t("interactiveEnginePlan")}</p>
        </div>
        <div className="plot-preview-actions">
          <span className="muted">{specStatus === "loading" ? t("rendering") : specStatus === "ready" ? t("ready") : specStatus}</span>
          {normalizedReturnTarget ? (
            <button
              className="plot-save-back"
              type="button"
              onClick={onSaveBack}
              disabled={!canSaveBackToResult || !previewSpec?.data?.length || saveBackStatus === "saving"}
              title={canSaveBackToResult ? "保存当前图到刚才打开的结果" : "请使用刚才打开结果对应的数据源"}
            >
              {saveBackStatus === "saving" ? "保存中..." : "保存回结果"}
            </button>
          ) : null}
        </div>
      </div>
      {saveBackError ? <p className="plot-error">{saveBackError}</p> : null}
      <MethodOverview preset={selectedPreset} source={selectedSource} tableSummary={tableSummary} t={t} />
      <MappingSummary preset={selectedPreset} params={params} tableSummary={tableSummary} />
      {specError ? <p className="plot-error">{specError}</p> : null}
      {previewSpec?.data?.length ? (
        <InteractivePlotComponent spec={previewSpec} />
      ) : (
        <EmptyPreview
          selectedPreset={selectedPreset}
          plotSpec={previewSpec}
          recommendedPresets={recommendedPresets}
          onSelectPlot={onSelectPlot}
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
  );
}

export function PlotDataPreviewPanel({
  t,
  tableSummary,
  preferredPreviewNumericColumns,
  skippedPreviewNumericColumns,
  metaEntries,
  valuePreview,
}) {
  return (
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
  );
}

export function PlotSourcePanel({ t, selectedSource }) {
  return (
    <>
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
        </div>
      )}
    </>
  );
}

export function PlotParamsPanel({
  t,
  selectedPreset,
  parameterSearch,
  onParameterSearchChange,
  onClearParameterSearch,
  onResetParams,
  onRunPreview,
  editCommand,
  onEditCommandChange,
  onApplyEditCommand,
  editCommandStatus,
  filteredBasicParameterGroups,
  filteredAdvancedParameterGroups,
  basicParameterCount,
  advancedParameterCount,
  hasParameterMatches,
  params,
  tableSummary,
  onUpdateParam,
  ParameterControlComponent,
}) {
  return (
    <article className="plot-config-panel">
      <div className="panel-title">
        <h2>{selectedPreset ? `${selectedPreset.label} ${t("parameters")}` : t("parameters")}</h2>
        <span className="muted">{selectedPreset?.engine || "-"}</span>
      </div>
      <div className="plot-action-strip">
        <button type="button" onClick={onResetParams}>{t("resetDefaults")}</button>
        <button className="primary" type="button" onClick={onRunPreview}>
          {t("runPreview")}
        </button>
      </div>
      <div className="plot-param-search" role="search">
        <input
          type="search"
          value={parameterSearch}
          onChange={(event) => onParameterSearchChange(event.target.value)}
          placeholder={t("parameterSearchPlaceholder")}
          aria-label={t("parameterSearchPlaceholder")}
        />
        {parameterSearch ? (
          <button type="button" onClick={onClearParameterSearch}>{t("clear")}</button>
        ) : null}
      </div>
      <form className="plot-agent-editor" onSubmit={onApplyEditCommand}>
        <label htmlFor="plot-agent-edit">PS Agent</label>
        <textarea
          id="plot-agent-edit"
          value={editCommand}
          onChange={(event) => onEditCommandChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder="例如：X 标签改为 PC1；散点大小 12；隐藏网格"
          rows={3}
        />
        <div>
          <button type="submit" disabled={!selectedPreset || !editCommand.trim()}>应用</button>
          {editCommandStatus ? <span>{editCommandStatus}</span> : null}
        </div>
      </form>
      <div className="plot-param-groups">
        {filteredBasicParameterGroups.length ? (
          <details className="plot-param-advanced plot-param-basic">
            <summary>
              <span>{t("basicParameters")}</span>
              <em>{basicParameterCount}</em>
            </summary>
            <div className="plot-param-stack" aria-label={t("basicParameters")}>
              {filteredBasicParameterGroups.map((group) => (
                <section className="plot-param-group" key={group.id}>
                  <h4>{group.label}</h4>
                  <div className="plot-param-controls">
                    {group.parameters.map((parameter) => (
                      <ParameterControlComponent
                        key={parameter.id}
                        parameter={parameter}
                        value={params[parameter.id]}
                        tableSummary={tableSummary}
                        plotId={selectedPreset?.id}
                        onChange={onUpdateParam}
                        t={t}
                      />
                    ))}
                  </div>
                </section>
              ))}
            </div>
          </details>
        ) : !hasParameterMatches ? <p className="muted">{parameterSearch ? t("noParameterMatches") : t("loadingPresets")}</p> : null}
        {filteredAdvancedParameterGroups.length ? (
          <details className="plot-param-advanced">
            <summary>
              <span>{t("advancedParameters")}</span>
              <em>{advancedParameterCount}</em>
            </summary>
            <div className="plot-param-stack">
              {filteredAdvancedParameterGroups.map((group) => (
                <section className="plot-param-group" key={group.id}>
                  <h4>{group.label}</h4>
                  <div className="plot-param-controls">
                    {group.parameters.map((parameter) => (
                      <ParameterControlComponent
                        key={parameter.id}
                        parameter={parameter}
                        value={params[parameter.id]}
                        tableSummary={tableSummary}
                        plotId={selectedPreset?.id}
                        onChange={onUpdateParam}
                        t={t}
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
  );
}

export function PlotReportPanel({
  t,
  status,
  studioReport,
  reportSections,
  reportGuidance,
  reportPrompt,
  reportPromptCopied,
  onCopyReportPrompt,
  agentContextText,
  agentContextCopied,
  onCopyAgentContext,
  ReportSectionComponent,
  ReportGuidanceComponent,
  ReportPromptComponent,
}) {
  return (
    <article className="plot-report-panel">
      <div className="panel-title">
        <h2>{t("agentReport")}</h2>
        <span className="muted">{status}</span>
      </div>
      {studioReport?.report?.headline ? <p className="plot-report-headline">{studioReport.report.headline}</p> : null}
      <div className="plot-report-sections">
        {reportSections.length ? reportSections.map((section) => (
          <ReportSectionComponent section={section} key={section.title} />
        )) : <p className="muted">{t("selectSourceReport")}</p>}
      </div>
      <ReportGuidanceComponent guidance={reportGuidance} t={t} />
      <ReportPromptComponent
        prompt={reportPrompt}
        copied={reportPromptCopied}
        t={t}
        onCopy={onCopyReportPrompt}
      />
      {studioReport?.report?.limitations?.length ? (
        <div className="plot-limitations">
          {studioReport.report.limitations.map((item) => <span key={item}>{item}</span>)}
        </div>
      ) : null}
      {agentContextText ? (
        <details className="plot-agent-context">
          <summary>
            <span>{t("llmContext")}</span>
            <button type="button" onClick={onCopyAgentContext}>
              {agentContextCopied ? t("copied") : t("copyContext")}
            </button>
          </summary>
          <p>{t("llmContextHint")}</p>
          <pre>{agentContextText}</pre>
        </details>
      ) : null}
    </article>
  );
}
