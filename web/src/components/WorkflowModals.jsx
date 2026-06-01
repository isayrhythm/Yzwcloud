import { useState } from "react";

import { formatBytes } from "../workflow/format.js";
import { Modal } from "./Modal.jsx";

export function ConfirmDeleteModal({ title, message, confirmLabel, onClose, onConfirm }) {
  return (
    <div className="modal-backdrop">
      <section className="modal confirm-modal">
        <h2>{title}</h2>
        <p>{message}</p>
        <div className="modal-actions">
          <button type="button" className="ghost" onClick={onClose}>取消</button>
          <button type="button" className="danger-primary" onClick={onConfirm}>{confirmLabel || "删除"}</button>
        </div>
      </section>
    </div>
  );
}

export function ResultModal({ title, url, originalUrl, hasSavedPlot, source, onClose, onOpenPlotStudio }) {
  return (
    <div className="result-backdrop">
      <section className="result-shell">
        <div className="result-header">
          <div>
            <h2>{title}</h2>
            {hasSavedPlot ? <span>已显示 Plot Studio 保存图</span> : null}
          </div>
          <div className="result-header-actions">
            {originalUrl && hasSavedPlot ? (
              <a href={originalUrl} target="_blank" rel="noreferrer">原始结果</a>
            ) : null}
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
            <button type="button" onClick={onClose}>关闭</button>
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
          <button type="button" onClick={onClose}>关闭</button>
        </div>
      </section>
    </Modal>
  );
}

const CONDITION_COLOR_PRESETS = [
  "#0f8a8f",
  "#315fd6",
  "#c44f3a",
  "#7b61b5",
  "#20804f",
  "#c27a18",
  "#b33d7a",
  "#52616b",
  "#d94f40",
  "#3776c4",
  "#12a36f",
  "#aa6f19",
];

function normalizeColor(value, fallback = "#0f8a8f") {
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
      window.alert(error.message);
      setBusy(false);
    }
  };

  return (
    <Modal onClose={onClose}>
      <form className="modal group-modal dataset-param-modal" onSubmit={submit}>
        <h2>调整数据参数</h2>
        <p>这里可以修正样本分组，并设置后续 PCA、热图等图形使用的分组颜色。</p>
        <div className="param-tabs">
          <button
            type="button"
            className={activeTab === "groups" ? "active" : ""}
            onClick={() => setActiveTab("groups")}
          >
            修正分组
          </button>
          <button
            type="button"
            className={activeTab === "colors" ? "active" : ""}
            onClick={() => setActiveTab("colors")}
          >
            设置颜色
          </button>
        </div>
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
                  "--group-row-color": colorByCondition[assignments[sample.sample] || ""] || "#0f8a8f",
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
          <button type="button" className="ghost" onClick={onClose}>取消</button>
          <button className="primary compact" disabled={busy}>{busy ? "保存中..." : "保存参数"}</button>
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
      window.alert(error.message);
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
          <button type="button" className="ghost" onClick={onClose}>取消</button>
          <button className="primary compact" disabled={busy}>{busy ? "保存中..." : "保存分组"}</button>
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
    <Modal onClose={onClose}>
      <form className="modal" onSubmit={submit}>
        <h2>选择差异分析组合</h2>
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
          <button type="button" className="ghost" onClick={onClose}>取消</button>
          <button className="primary compact" disabled={busy}>{busy ? "创建中..." : "创建并执行"}</button>
        </div>
        {error ? <p className="modal-error">{error}</p> : null}
      </form>
    </Modal>
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
    <Modal onClose={onClose}>
      <form className="modal" onSubmit={submit}>
        <h2>添加后续分析</h2>
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
          <button type="button" className="ghost" onClick={onClose}>取消</button>
          <button className="primary compact" disabled={busy}>{busy ? "创建中..." : "创建节点"}</button>
        </div>
        {error ? <p className="modal-error">{error}</p> : null}
      </form>
    </Modal>
  );
}
