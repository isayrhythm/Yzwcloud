import { outputUrl } from "../workflow/format.js";
import { summarizeOutput } from "../workflow/options.js";
import { useI18n } from "../i18n.jsx";

function Metric({ label, value }) {
  return (
    <article className="report-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function summarizeTaskGraph(detail) {
  if (!detail) {
    return {
      totalNodes: 0,
      completedNodes: 0,
      failedNodes: 0,
      outputNodes: 0,
    };
  }
  const nodes = detail.graph.nodes || [];
  return {
    totalNodes: nodes.length,
    completedNodes: nodes.filter((node) => node.status === "completed").length,
    failedNodes: nodes.filter((node) => node.status === "failed").length,
    outputNodes: nodes.filter((node) => node.output).length,
  };
}

function collectReportOutputs(detail) {
  if (!detail) return [];
  const taskId = detail.task?.task_id;
  return (detail.graph.nodes || [])
    .filter((node) => node.output)
    .map((node) => ({
      id: node.id,
      sourceKind: "report_output",
      taskId,
      taskName: detail.task?.name || "",
      nodeId: node.id,
      name: node.name,
      status: node.status,
      type: node.output?.type || "-",
      summary: summarizeOutput(node.output),
      dataPath: node.output?.data || "",
      meta: node.output?.meta || {},
      hasPreview: Boolean(node.output?.meta?.preview_file),
      hasHtml: Boolean(node.output?.meta?.html_file),
      previewUrl: taskId && node.output?.meta?.preview_file ? outputUrl(taskId, node.output.meta.preview_file) : "",
      htmlUrl: taskId && node.output?.meta?.html_file ? outputUrl(taskId, node.output.meta.html_file) : "",
    }));
}

function buildReportInsights(detail) {
  if (!detail) return [];
  const outputs = collectReportOutputs(detail);
  const nodes = detail.graph.nodes || [];
  const expressionNode = nodes.find((node) => node.id === "upload_expression");
  const diffNodes = nodes.filter((node) => node.id.startsWith("diff_analysis__") && node.output);
  const failedNodes = nodes.filter((node) => node.status === "failed");
  const insights = [];

  if (expressionNode?.output?.meta?.sample_count) {
    insights.push({
      title: "Matrix intake",
      text: `Expression matrix loaded with ${expressionNode.output.meta.sample_count} samples and ${expressionNode.output.meta.gene_count || 0} genes.`,
      tone: "neutral",
    });
  }

  if (diffNodes.length) {
    insights.push({
      title: "Differential branches ready",
      text: `${diffNodes.length} differential comparison branch${diffNodes.length > 1 ? "es are" : " is"} available for downstream plots and export.`,
      tone: "positive",
    });
  }

  if (failedNodes.length) {
    insights.push({
      title: "Rerun required",
      text: `${failedNodes.length} node${failedNodes.length > 1 ? "s" : ""} failed. Clean up the failed branch before exporting a final report.`,
      tone: "warning",
    });
  }

  if (!outputs.length) {
    insights.push({
      title: "No reportable output yet",
      text: "Run the upload node and at least one downstream analysis node before using the report view.",
      tone: "warning",
    });
  }

  return insights;
}

function buildReportSections(detail, summary, outputs, insights) {
  const warnings = insights.filter((item) => item.tone === "warning");
  const failedCount = summary.failedNodes;
  const completedCount = summary.completedNodes;
  return [
    {
      title: "Summary",
      text: detail
        ? `Current task has ${summary.totalNodes} nodes, ${completedCount} completed nodes, and ${outputs.length} reportable outputs.`
        : "Select or create an analysis task before preparing a report.",
      tone: "neutral",
    },
    {
      title: "Findings",
      text: outputs.length
        ? `${outputs.length} outputs are available for review. Open plots and exports from the output list before final interpretation.`
        : "No analysis output is ready yet. Run upload and downstream analysis nodes first.",
      tone: outputs.length ? "positive" : "warning",
    },
    {
      title: "Warnings",
      text: warnings.length || failedCount
        ? `${warnings.length + failedCount} warning signal(s) need review before this report is final.`
        : "No failed node or warning signal is currently detected.",
      tone: warnings.length || failedCount ? "warning" : "positive",
    },
    {
      title: "Next Steps",
      text: outputs.length
        ? "Review each output, rerun failed branches if needed, then generate the report-agent interpretation."
        : "Return to Analysis Workspace, finish the core workflow, then come back to Reports.",
      tone: "neutral",
    },
  ];
}

export function buildReportModel(detail, logs) {
  const summary = summarizeTaskGraph(detail);
  const outputs = collectReportOutputs(detail);
  const insights = buildReportInsights(detail);
  const sections = buildReportSections(detail, summary, outputs, insights);
  const logLines = String(logs || "").split(/\r?\n/).filter(Boolean);

  return {
    task: detail?.task || null,
    summary,
    outputs,
    insights,
    sections,
    warnings: insights.filter((item) => item.tone === "warning"),
    logTail: logLines.slice(-12).join("\n"),
    logLineCount: logLines.length,
    readyForAgent: Boolean(detail?.task && (outputs.length || insights.length || logLines.length)),
    agentContext: {
      task: detail?.task || null,
      nodes: detail?.graph?.nodes || [],
      edges: detail?.graph?.edges || [],
      outputs,
      insights,
      logTail: logLines.slice(-12),
    },
  };
}

export function ReportsPage({ tasks, activeTaskId, report, onSelectTask, onOpenAnalysis }) {
  const { t } = useI18n();
  const task = report?.task || null;
  const summary = report?.summary || summarizeTaskGraph(null);
  const outputs = report?.outputs || [];
  const sections = report?.sections || [];
  const logPreview = report?.logTail || "";
  const reportHtmlUrl = task ? `/api/tasks/${encodeURIComponent(task.task_id)}/report.html` : "";
  const reportPdfUrl = task ? `/api/tasks/${encodeURIComponent(task.task_id)}/report.pdf` : "";

  return (
    <main className="reports-page shell">
      <section className="hero report-hero">
        <div>
          <p className="eyebrow">Reports</p>
          <h1>{t("reportWorkspace")}</h1>
          <p className="summary">{t("reportSummary")}</p>
        </div>
        <div className="report-hero-actions">
          {task ? <a href={reportHtmlUrl} target="_blank" rel="noreferrer">演示版 HTML</a> : null}
          {task ? <a href={reportPdfUrl} target="_blank" rel="noreferrer">导出 PDF</a> : null}
          <button className="primary" onClick={onOpenAnalysis}>{t("backToAnalysis")}</button>
        </div>
      </section>

      <section className="layout reports-layout">
        <aside className="panel">
          <div className="panel-title">
            <h2>{t("tasks")}</h2>
            <span className="muted">{tasks.length} {t("total")}</span>
          </div>
          <div className="task-list">
            {tasks.length === 0 ? <p className="muted">{t("noTaskYet")}</p> : null}
            {tasks.map((item) => (
              <div className={`task-item ${item.task_id === activeTaskId ? "active" : ""}`} key={item.task_id}>
                <button className="task-select" onClick={() => onSelectTask(item.task_id)}>
                  <strong>{item.name}</strong>
                  <span className="task-id">{item.status} / {item.task_id}</span>
                </button>
              </div>
            ))}
          </div>
        </aside>

        <section className="workspace reports-workspace">
          <div className="panel-title">
            <h2>{task ? task.name : t("reportSummary")}</h2>
            <span className="muted">{task ? `${task.status} / ${task.task_id}` : t("selectTask")}</span>
          </div>

          <div className="report-summary-grid">
            <Metric label={t("nodes")} value={task ? `${summary.totalNodes}` : "-"} />
            <Metric label={t("completed")} value={task ? `${summary.completedNodes}` : "-"} />
            <Metric label={t("failed")} value={task ? `${summary.failedNodes}` : "-"} />
            <Metric label={t("outputs")} value={task ? `${summary.outputNodes}` : "-"} />
          </div>

          <section className="report-surface">
            <div className="panel-title">
              <h2>{t("reportStructure")}</h2>
              <span className="muted">{report?.readyForAgent ? "agent context ready" : "pending analysis"}</span>
            </div>
            <div className="report-structure-grid">
              {sections.map((section) => (
                <article key={section.title} className={`report-insight ${section.tone || "neutral"}`}>
                  <strong>{section.title}</strong>
                  <p>{section.text}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="report-surface">
            <div className="panel-title">
              <h2>{t("outputs")}</h2>
              <span className="muted">{outputs.length} item(s)</span>
            </div>
            <div className="report-output-list">
              {outputs.length ? outputs.map((output) => {
                const href = output.htmlUrl || output.previewUrl;
                return (
                  <article key={output.id} className="report-output-card">
                    <div>
                      <strong>{output.name}</strong>
                      <span>{output.type}</span>
                    </div>
                    <p>{output.summary}</p>
                    <small>
                      {output.status}
                      {output.hasHtml ? " / interactive" : ""}
                      {output.hasPreview ? " / preview" : ""}
                    </small>
                    <div className="report-output-actions">
                      {href ? <a href={href} target="_blank" rel="noreferrer">Open output</a> : null}
                    </div>
                  </article>
                );
              }) : <p className="muted">No output object is ready for reporting yet.</p>}
            </div>
          </section>

          <section className="report-surface">
            <div className="panel-title">
            <h2>{t("reportAgentInput")}</h2>
              <span className="muted">{report?.readyForAgent ? "ready" : "pending"}</span>
            </div>
            <div className="report-summary-grid">
              <Metric label={t("warnings")} value={`${report?.warnings?.length || 0}`} />
              <Metric label={t("outputs")} value={`${outputs.length}`} />
              <Metric label={t("logLines")} value={`${report?.logLineCount || 0}`} />
              <Metric label={t("nodesInContext")} value={`${report?.agentContext?.nodes?.length || 0}`} />
            </div>
          </section>

          <section className="report-surface">
            <div className="panel-title">
              <h2>{t("logTail")}</h2>
            </div>
            <pre className="logs report-log">{logPreview || t("noLogYet")}</pre>
          </section>
        </section>
      </section>
    </main>
  );
}

