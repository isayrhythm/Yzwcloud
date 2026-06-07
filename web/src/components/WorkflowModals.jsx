import { useState } from "react";

import { formatBytes } from "../workflow/format.js";
import { Button, Dialog, Tabs } from "tdesign-react";
import { Modal } from "./Modal.jsx";

function notifyError(message) {
  console.error(message || "操作失败");
}

export function ConfirmDeleteModal({ title, message, confirmLabel, onClose, onConfirm }) {
  return (
    <Dialog
      visible
      header={title}
      theme="danger"
      width={420}
      placement="center"
      closeOnOverlayClick
      destroyOnClose
      dialogClassName="td-workflow-dialog confirm-delete-dialog"
      cancelBtn={{ content: "取消", variant: "outline" }}
      confirmBtn={{ content: confirmLabel || "删除", theme: "danger" }}
      onClose={onClose}
      onCancel={onClose}
      onConfirm={onConfirm}
    >
      <p className="confirm-delete-copy">{message}</p>
    </Dialog>
  );
}

export function ResultModal({ title, url, originalUrl, hasSavedPlot, source, agentReportNode, onClose, onOpenPlotStudio, onOpenAgentReport }) {
  return (
    <div className="result-backdrop">
      <section className="result-shell">
        <div className="result-header">
          <div>
            <div className="result-title-row">
              <h2>{title}</h2>
              {source && onOpenPlotStudio ? (
                <button
                  className="result-plot-send"
                  type="button"
                  onClick={() => onOpenPlotStudio(source)}
                  title="Send this result to Plot Studio"
                >
                  Plot Studio
                </button>
              ) : null}
              {agentReportNode && onOpenAgentReport ? (
                <button
                  className="result-agent-summary"
                  type="button"
                  onClick={() => onOpenAgentReport(agentReportNode)}
                  title="Open the agent summary for this result"
                >
                  Agent 总结
                </button>
              ) : null}
            </div>
            {hasSavedPlot ? <span>已显示 Plot Studio 保存图</span> : null}
          </div>
          <div className="result-header-actions">
            {originalUrl && hasSavedPlot ? (
              <a href={originalUrl} target="_blank" rel="noreferrer">原始结果</a>
            ) : null}
            <button className="result-close" type="button" onClick={onClose}>×</button>
          </div>
        </div>
        <iframe title={title} src={url} />
      </section>
    </div>
  );
}

export function AgentReportModal({ node, onClose }) {
  const progress = node.params?.agent_progress || {};
  const analysisReport = node.output?.meta?.agent_report || null;
  const report = analysisReport || node.params?.agent_report || {};
  const history = progress.history || [];
  const uploaded = node.params?.uploaded_inputs?.expression_matrix;
  if (analysisReport) {
    const sections = [
      ["关键发现", report.findings],
      ["方法与参数", report.methods],
      ["解释边界", report.warnings],
      ["下一步建议", report.next_steps],
    ];
    return (
      <Modal onClose={onClose}>
        <section className="modal agent-report-modal analysis-agent-report-modal">
          <div className="agent-report-heading">
            <div>
              <h2>{report.title || `${node.name} · Agent 总结`}</h2>
              <p>{report.summary}</p>
            </div>
            <span className={`agent-report-badge ${report.generated_by === "llm" ? "llm" : "fallback"}`}>
              {report.generated_by === "llm" ? "LLM" : "规则化回退"}
            </span>
          </div>
          <div className="analysis-agent-report-grid">
            {sections.map(([title, items]) => (
              <div className="report-block" key={title}>
                <strong>{title}</strong>
                <ul className="report-list">
                  {(items || []).map((item, index) => <li key={`${title}-${index}`}>{item}</li>)}
                </ul>
              </div>
            ))}
          </div>
          <div className="report-grid">
            <span>输出类型</span>
            <strong>{report.output_type || node.output?.type || "-"}</strong>
            <span>生成方式</span>
            <strong>{report.generated_by || "-"}</strong>
            <span>LLM 状态</span>
            <strong>{report.llm_status || "-"}</strong>
          </div>
          <div className="modal-actions">
            <Button theme="primary" shape="round" type="button" onClick={onClose}>关闭</Button>
          </div>
        </section>
      </Modal>
    );
  }
  return (
    <Modal onClose={onClose}>
      <section className="modal agent-report-modal">
        <h2>{report.title || "数据处理报告"}</h2>
        <p>{report.summary || "Agent 没有把这个文件整理成当前流程可用的数据对象。"}</p>
        {Array.isArray(report.reasons) && report.reasons.length ? (
          <div className="report-block">
            <strong>为什么现在不能分析</strong>
            <ul className="report-list">
              {report.reasons.map((item, index) => (
                <li key={`reason-${index}`}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {Array.isArray(report.findings) && report.findings.length ? (
          <div className="report-block">
            <strong>Agent 实际看到了什么</strong>
            <ul className="report-list">
              {report.findings.map((item, index) => (
                <li key={`finding-${index}`}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {Array.isArray(report.suggestions) && report.suggestions.length ? (
          <div className="report-block">
            <strong>建议怎么改</strong>
            <ul className="report-list">
              {report.suggestions.map((item, index) => (
                <li key={`suggestion-${index}`}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}
        <div className="report-block">
          <strong>原始报错</strong>
          <pre>{report.raw_error || node.error || progress.label || "未知错误"}</pre>
        </div>
        {uploaded ? (
          <div className="report-grid">
            <span>文件</span>
            <strong title={uploaded.filename}>{uploaded.filename}</strong>
            <span>大小</span>
            <strong>{formatBytes(uploaded.size)}</strong>
          </div>
        ) : null}
        {report.inspection?.header_preview?.length ? (
          <div className="report-block">
            <strong>识别到的前几列表头</strong>
            <pre>{report.inspection.header_preview.join(", ")}</pre>
          </div>
        ) : null}
        {history.length ? (
          <div className="report-block">
            <strong>处理过程</strong>
            <ol className="report-timeline">
              {history.map((item, index) => (
                <li key={`${item.step}-${item.status}-${index}`}>
                  <span>{item.status}</span>
                  {item.label}
                </li>
              ))}
            </ol>
          </div>
        ) : null}
        {Array.isArray(report.attempts) && report.attempts.length ? (
          <div className="report-block">
            <strong>尝试过的处理策略</strong>
            <ol className="report-timeline">
              {report.attempts.map((item, index) => (
                <li key={`attempt-${index}`}>
                  <span>{item.status}</span>
                  {item.label}
                  {item.error ? `：${item.error}` : ""}
                </li>
              ))}
            </ol>
          </div>
        ) : null}
        <div className="modal-actions">
          <Button theme="primary" shape="round" type="button" onClick={onClose}>关闭</Button>
        </div>
      </section>
    </Modal>
  );
}

const CONDITION_COLOR_PRESETS = [
  "#0052d9",
  "#2b74d6",
  "#315fd6",
  "#244ba8",
  "#7a4fb3",
  "#52616b",
  "#98a2b3",
  "#d94f40",
  "#b33d7a",
  "#1d2939",
  "#667085",
  "#175cd3",
];

function normalizeColor(value, fallback = "#0052d9") {
  const text = String(value || "").trim();
  return /^#[0-9a-fA-F]{6}$/.test(text) ? text : fallback;
}

export function DatasetParamsModal({ payload, onClose, onSubmit }) {
  const samples = payload.samples || [];
  const [activeTab, setActiveTab] = useState("groups");
  const [assignments, setAssignments] = useState(
    Object.fromEntries(samples.map((sample) => [sample.sample, sample.condition || "unknown"])),
  );
  const [colors, setColors] = useState(payload.condition_colors || {});
  const [busy, setBusy] = useState(false);
  const conditions = Array.from(new Set(Object.values(assignments))).filter(Boolean);
  const colorByCondition = Object.fromEntries(
    conditions.map((condition, index) => [
      condition,
      normalizeColor(colors[condition], CONDITION_COLOR_PRESETS[index % CONDITION_COLOR_PRESETS.length]),
    ]),
  );

  const setConditionColor = (condition, color) => {
    setColors((current) => ({ ...current, [condition]: color }));
  };

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      await onSubmit({ assignments, condition_colors: colorByCondition });
    } catch (error) {
      notifyError(error.message);
      setBusy(false);
    }
  };

  return (
    <Modal onClose={onClose}>
      <form className="modal group-modal dataset-param-modal" onSubmit={submit}>
        <h2>调整数据参数</h2>
        <p>这里可以修正样本分组，并设置后续 PCA、热图等图形使用的分组颜色。</p>
        <Tabs className="param-tabs tdesign-param-tabs" value={activeTab} onChange={setActiveTab} theme="card">
          <Tabs.TabPanel value="groups" label="修正分组" />
          <Tabs.TabPanel value="colors" label="设置颜色" />
        </Tabs>
        <div className="condition-grid">
          {conditions.map((condition) => (
            <span key={condition}>
              <i style={{ background: colorByCondition[condition] }} />
              {condition} <strong>{Object.values(assignments).filter((item) => item === condition).length}</strong>
            </span>
          ))}
        </div>
        {activeTab === "groups" ? (
          <div className="group-editor-list">
            {samples.map((sample) => (
              <label
                key={sample.sample}
                style={{
                  "--group-row-color": colorByCondition[assignments[sample.sample] || ""] || "#0052d9",
                }}
              >
                <span>{sample.sample}</span>
                <input
                  value={assignments[sample.sample] || ""}
                  onChange={(event) =>
                    setAssignments((current) => ({
                      ...current,
                      [sample.sample]: event.target.value,
                    }))
                  }
                />
              </label>
            ))}
          </div>
        ) : (
          <div className="color-editor-list">
            {conditions.map((condition) => (
              <section className="color-editor-row" key={condition}>
                <div>
                  <span className="color-preview" style={{ background: colorByCondition[condition] }} />
                  <strong>{condition}</strong>
                </div>
                <div className="palette-grid">
                  {CONDITION_COLOR_PRESETS.map((color) => (
                    <button
                      type="button"
                      key={`${condition}-${color}`}
                      className={colorByCondition[condition].toLowerCase() === color.toLowerCase() ? "active" : ""}
                      style={{ background: color }}
                      title={color}
                      onClick={() => setConditionColor(condition, color)}
                    />
                  ))}
                </div>
                <input
                  type="color"
                  value={colorByCondition[condition]}
                  onChange={(event) => setConditionColor(condition, event.target.value)}
                  aria-label={`${condition} color`}
                />
              </section>
            ))}
          </div>
        )}
        <div className="modal-actions">
          <Button type="button" variant="outline" shape="round" onClick={onClose}>取消</Button>
          <Button theme="primary" shape="round" type="submit" loading={busy} disabled={busy}>
            {busy ? "保存中..." : "保存参数"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function GroupEditorModal({ payload, onClose, onSubmit }) {
  const samples = payload.samples || [];
  const [assignments, setAssignments] = useState(
    Object.fromEntries(samples.map((sample) => [sample.sample, sample.condition || "unknown"])),
  );
  const [busy, setBusy] = useState(false);
  const conditions = Array.from(new Set(Object.values(assignments))).filter(Boolean);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      await onSubmit(assignments);
    } catch (error) {
      notifyError(error.message);
      setBusy(false);
    }
  };

  return (
    <Modal onClose={onClose}>
      <form className="modal group-modal" onSubmit={submit}>
        <h2>修正样本分组</h2>
        <p>修改 condition 后会重新计算该数据节点的下一步分析入口。</p>
        <div className="condition-grid">
          {conditions.map((condition) => (
            <span key={condition}>
              {condition} <strong>{Object.values(assignments).filter((item) => item === condition).length}</strong>
            </span>
          ))}
        </div>
        <div className="group-editor-list">
          {samples.map((sample) => (
            <label key={sample.sample}>
              <span>{sample.sample}</span>
              <input
                value={assignments[sample.sample] || ""}
                onChange={(event) =>
                  setAssignments((current) => ({
                    ...current,
                    [sample.sample]: event.target.value,
                  }))
                }
              />
            </label>
          ))}
        </div>
        <div className="modal-actions">
          <Button type="button" variant="outline" shape="round" onClick={onClose}>取消</Button>
          <Button theme="primary" shape="round" type="submit" loading={busy} disabled={busy}>
            {busy ? "保存中..." : "保存分组"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function ComparisonModal({ options, onClose, onSubmit }) {
  const conditions = options.conditions || [];
  const counts = options.counts || {};
  const controlDefault = conditions.includes("normal") ? "normal" : conditions[0];
  const caseDefault = conditions.find((item) => item !== controlDefault) || conditions[1];
  const [caseCondition, setCaseCondition] = useState(caseDefault);
  const [controlCondition, setControlCondition] = useState(controlDefault);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (caseCondition === controlCondition) {
      setError("Case 和 Control 不能相同。");
      return;
    }
    setBusy(true);
    try {
      await onSubmit(caseCondition, controlCondition);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <Dialog
      visible
      header="选择差异分析组合"
      width={560}
      placement="center"
      closeOnOverlayClick
      destroyOnClose
      footer={false}
      dialogClassName="td-workflow-dialog td-param-dialog"
      onClose={onClose}
      onCancel={onClose}
    >
      <form className="modal" onSubmit={submit}>
        <p>每次选择会衍生一个独立差异分析分支，可以重复创建不同组合。</p>
        <div className="condition-grid">
          {conditions.map((condition) => (
            <span key={condition}>{condition} <strong>{counts[condition] || 0}</strong></span>
          ))}
        </div>
        <label>
          Case 分组
          <select value={caseCondition} onChange={(event) => setCaseCondition(event.target.value)}>
            {conditions.map((condition) => <option key={condition}>{condition}</option>)}
          </select>
        </label>
        <label>
          Control 分组
          <select value={controlCondition} onChange={(event) => setControlCondition(event.target.value)}>
            {conditions.map((condition) => <option key={condition}>{condition}</option>)}
          </select>
        </label>
        <div className="modal-actions">
          <Button type="button" variant="outline" shape="round" onClick={onClose}>取消</Button>
          <Button theme="primary" shape="round" type="submit" loading={busy} disabled={busy}>
            {busy ? "创建中..." : "创建并执行"}
          </Button>
        </div>
        {error ? <p className="modal-error">{error}</p> : null}
      </form>
    </Dialog>
  );
}

export function NextAnalysisModal({ options, onClose, onSubmit }) {
  const [selected, setSelected] = useState(options[0]?.type || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      await onSubmit(selected);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <Dialog
      visible
      header="添加后续分析"
      width={540}
      placement="center"
      closeOnOverlayClick
      destroyOnClose
      footer={false}
      dialogClassName="td-workflow-dialog td-param-dialog"
      onClose={onClose}
      onCancel={onClose}
    >
      <form className="modal" onSubmit={submit}>
        <p>节点只会在选择后创建，避免画布一次性铺满。</p>
        <div className="analysis-choice-list">
          {options.map((option) => (
            <label className="analysis-choice" key={option.type}>
              <input
                type="radio"
                name="analysis_type"
                value={option.type}
                checked={selected === option.type}
                onChange={() => setSelected(option.type)}
              />
              <span>{option.label}</span>
            </label>
          ))}
        </div>
        <div className="modal-actions">
          <Button type="button" variant="outline" shape="round" onClick={onClose}>取消</Button>
          <Button theme="primary" shape="round" type="submit" loading={busy} disabled={busy}>
            {busy ? "创建中..." : "创建节点"}
          </Button>
        </div>
        {error ? <p className="modal-error">{error}</p> : null}
      </form>
    </Dialog>
  );
}
