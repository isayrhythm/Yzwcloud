import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  applyEdgeChanges,
  applyNodeChanges,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import "./styles.css";

const statusLabel = {
  pending: "待创建",
  ready: "可执行",
  running: "执行中",
  completed: "完成",
  failed: "错误",
  blocked: "等待上游",
};

const statusColor = {
  pending: "#d2cabd",
  ready: "#2f78c4",
  running: "#315fd6",
  completed: "#20804f",
  failed: "#b93d2f",
  blocked: "#8c8172",
};

const defaultPositions = {
  upload_expression: { x: 80, y: 210 },
  diff_analysis: { x: 360, y: 210 },
  pca__expression: { x: 640, y: 390 },
};

async function api(path, options = {}) {
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
  return response;
}

function App() {
  const { getViewport, setViewport } = useReactFlow();
  const [tasks, setTasks] = useState([]);
  const [activeTaskId, setActiveTaskId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [logs, setLogs] = useState("");
  const [modal, setModal] = useState(null);
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [page, setPage] = useState("home");
  const [showMiniMap, setShowMiniMap] = useState(false);
  const flowPanelRef = useRef(null);
  const miniMapTimerRef = useRef(null);

  const loadTasks = useCallback(async () => {
    const response = await api("/api/tasks");
    const data = await response.json();
    setTasks(data);
    if (!activeTaskId && data.length) {
      setActiveTaskId(data[0].task_id);
    }
  }, [activeTaskId]);

  const loadDetail = useCallback(async (taskId) => {
    if (!taskId) {
      setDetail(null);
      setLogs("");
      return;
    }
    const [detailResponse, logsResponse] = await Promise.all([
      api(`/api/tasks/${taskId}`),
      fetch(`/api/tasks/${taskId}/logs`),
    ]);
    setDetail(await detailResponse.json());
    setLogs(await logsResponse.text());
  }, []);

  useEffect(() => {
    loadTasks().catch((error) => window.alert(error.message));
  }, [loadTasks]);

  useEffect(() => {
    loadDetail(activeTaskId).catch((error) => window.alert(error.message));
  }, [activeTaskId, loadDetail]);

  useEffect(() => {
    if (!activeTaskId) return undefined;
    const timer = window.setInterval(() => {
      loadDetail(activeTaskId).catch(() => {});
    }, 1800);
    return () => window.clearInterval(timer);
  }, [activeTaskId, loadDetail]);

  useEffect(() => {
    if (!detail) {
      setNodes([]);
      setEdges([]);
      return;
    }
    const graphNodes = visibleGraphNodes(detail.graph.nodes);
    const flowNodes = graphNodes.map((node, index) => ({
      id: node.id,
      type: "analysisNode",
      position: readNodePosition(detail.task.task_id, node.id) || fallbackPosition(node, index, graphNodes),
      data: {
        node,
        detail,
        onRun: runNode,
        onDelete: deleteNode,
        onAddNext: openNextModal,
        onOpenResult: openResultModal,
      },
    }));
    const visibleIds = new Set(graphNodes.map((node) => node.id));
    const flowEdges = detail.graph.edges
      .filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target))
      .map((edge) => ({
        id: `${edge.source}->${edge.target}`,
        source: edge.source,
        target: edge.target,
        animated: true,
        className: "flow-edge",
      }));
    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [detail]);

  const createTask = async () => {
    const response = await api("/api/tasks", {
      method: "POST",
      body: JSON.stringify({ name: "生信分析任务" }),
    });
    const data = await response.json();
    setActiveTaskId(data.task.task_id);
    await loadTasks();
  };

  const deleteTask = async (taskId) => {
    if (!window.confirm("确定删除这个任务吗？任务数据、输出和日志都会删除。")) return;
    await api(`/api/tasks/${taskId}`, { method: "DELETE" });
    if (taskId === activeTaskId) {
      const nextTask = tasks.find((task) => task.task_id !== taskId);
      setActiveTaskId(nextTask?.task_id || null);
      setDetail(null);
    }
    await loadTasks();
  };

  async function runNode(nodeId) {
    if (!activeTaskId) return;
    if (nodeId === "diff_analysis") {
      await openComparisonModal();
      return;
    }
    await api(`/api/tasks/${activeTaskId}/nodes/${encodeURIComponent(nodeId)}/run`, {
      method: "POST",
      body: JSON.stringify({ params: {} }),
    });
    await loadDetail(activeTaskId);
  }

  async function deleteNode(nodeId) {
    const message =
      nodeId === "upload_expression"
        ? "确定清空表达矩阵结果，并删除所有下游节点吗？"
        : "确定删除这个节点及所有下游子节点吗？";
    if (!window.confirm(message)) return;
    await api(`/api/tasks/${activeTaskId}/nodes/${encodeURIComponent(nodeId)}`, {
      method: "DELETE",
    });
    removeStoredNodePosition(activeTaskId, nodeId);
    await loadDetail(activeTaskId);
  }

  function openNextModal(nodeId) {
    const node = detail?.graph.nodes.find((item) => item.id === nodeId);
    const options = node ? nextAnalysisOptions(node, detail) : [];
    if (!options.length) return;
    setModal({ kind: "next", sourceNodeId: nodeId, options });
  }

  function openResultModal(node) {
    const htmlFile = node.output?.meta?.html_file;
    if (!htmlFile) return;
    setModal({
      kind: "result",
      title: node.name,
      url: outputUrl(activeTaskId, htmlFile),
    });
  }

  async function openComparisonModal() {
    try {
      const response = await api(`/api/tasks/${activeTaskId}/comparison-options`);
      setModal({ kind: "comparison", options: await response.json() });
    } catch (error) {
      window.alert(`无法读取分组信息：${error.message}`);
    }
  }

  const createAnalysisNode = async (sourceNodeId, analysisType) => {
    await api(`/api/tasks/${activeTaskId}/analysis-nodes`, {
      method: "POST",
      body: JSON.stringify({ source_node_id: sourceNodeId, analysis_type: analysisType }),
    });
    setModal(null);
    await loadDetail(activeTaskId);
  };

  const createDiffAnalysis = async (caseCondition, controlCondition) => {
    await api(`/api/tasks/${activeTaskId}/diff-analyses`, {
      method: "POST",
      body: JSON.stringify({
        case_condition: caseCondition,
        control_condition: controlCondition,
      }),
    });
    setModal(null);
    await loadDetail(activeTaskId);
  };

  const onNodesChange = useCallback(
    (changes) => {
      setNodes((current) => {
        const next = applyNodeChanges(changes, current);
        changes.forEach((change) => {
          if (change.type === "position" && change.position && activeTaskId) {
            saveNodePosition(activeTaskId, change.id, change.position);
          }
        });
        return next;
      });
    },
    [activeTaskId],
  );

  const onEdgesChange = useCallback((changes) => {
    setEdges((current) => applyEdgeChanges(changes, current));
  }, []);

  const nodeTypes = useMemo(() => ({ analysisNode: AnalysisNode }), []);

  const revealMiniMap = useCallback(() => {
    setShowMiniMap(true);
    if (miniMapTimerRef.current) {
      window.clearTimeout(miniMapTimerRef.current);
    }
    miniMapTimerRef.current = window.setTimeout(() => {
      setShowMiniMap(false);
      miniMapTimerRef.current = null;
    }, 1400);
  }, []);

  useEffect(() => () => {
    if (miniMapTimerRef.current) {
      window.clearTimeout(miniMapTimerRef.current);
    }
  }, []);

  useEffect(() => {
    const panel = flowPanelRef.current;
    if (!panel) return undefined;

    const handleWheel = (event) => {
      if (!event.ctrlKey && !event.metaKey) return;

      event.stopImmediatePropagation();
      event.preventDefault();
      revealMiniMap();
      const viewport = getViewport();
      const nextZoom = Math.min(2, Math.max(0.2, viewport.zoom + (event.deltaY < 0 ? 0.08 : -0.08)));
      setViewport({ x: viewport.x, y: viewport.y, zoom: nextZoom }, { duration: 0 });
    };

    panel.addEventListener("wheel", handleWheel, { capture: true, passive: false });
    return () => panel.removeEventListener("wheel", handleWheel, { capture: true });
  }, [getViewport, revealMiniMap, setViewport]);

  const openWorkbench = () => setPage("workbench");

  if (page === "home") {
    return (
      <AppChrome page={page} onNavigate={setPage}>
        <HomePage onStart={openWorkbench} />
      </AppChrome>
    );
  }

  if (page === "docs") {
    return (
      <AppChrome page={page} onNavigate={setPage}>
        <DocsPage onStart={openWorkbench} />
      </AppChrome>
    );
  }

  return (
    <AppChrome page={page} onNavigate={setPage}>
    <main className="shell workbench-shell">
      <section className="hero">
        <div>
          <p className="eyebrow">YZW Bioinformatics Cloud</p>
          <h1>React Flow 分析流程台</h1>
          <p className="summary">
            表达矩阵读取、分组差异分析、后续分析节点按需创建。节点可拖拽、缩放、删除子图。
          </p>
        </div>
        <button className="primary" onClick={createTask}>创建示例任务</button>
      </section>

      <section className="layout">
        <aside className="panel">
          <div className="panel-title">
            <h2>任务列表</h2>
            <button className="ghost" onClick={loadTasks}>刷新</button>
          </div>
          <div className="task-list">
            {tasks.length === 0 ? <p className="muted">还没有任务</p> : null}
            {tasks.map((task) => (
              <div className={`task-item ${task.task_id === activeTaskId ? "active" : ""}`} key={task.task_id}>
                <button className="task-select" onClick={() => setActiveTaskId(task.task_id)}>
                  <strong>{task.name}</strong>
                  <span className="task-id">{task.status} · {task.task_id}</span>
                </button>
                <button className="task-delete" onClick={() => deleteTask(task.task_id)}>删除</button>
              </div>
            ))}
          </div>
        </aside>

        <section className="workspace">
          <div className="panel-title">
            <h2>流程节点</h2>
            <span className="muted">{detail ? `${detail.task.status} · ${detail.task.task_id}` : "未选择任务"}</span>
          </div>
          <div className="flow-panel" ref={flowPanelRef}>
            {detail ? (
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onMoveStart={revealMiniMap}
                onMove={revealMiniMap}
                onMoveEnd={revealMiniMap}
                onNodeDragStart={revealMiniMap}
                onNodeDrag={revealMiniMap}
                onNodeDragStop={revealMiniMap}
                fitView
                minZoom={0.2}
                maxZoom={2}
                zoomOnScroll={false}
                panOnScroll={false}
                proOptions={{ hideAttribution: true }}
                deleteKeyCode={null}
              >
                <Background gap={28} color="#d9cbb7" />
                <Controls position="top-right" />
                {showMiniMap ? (
                  <MiniMap pannable zoomable nodeColor={(node) => statusColor[node.data.node.status] || "#d2cabd"} />
                ) : null}
              </ReactFlow>
            ) : (
              <div className="empty-flow">先创建或选择一个任务</div>
            )}
          </div>
          <h2>任务日志</h2>
          <pre className="logs">{logs}</pre>
        </section>
      </section>

      {modal?.kind === "comparison" ? (
        <ComparisonModal
          options={modal.options}
          onClose={() => setModal(null)}
          onSubmit={createDiffAnalysis}
        />
      ) : null}
      {modal?.kind === "next" ? (
        <NextAnalysisModal
          options={modal.options}
          onClose={() => setModal(null)}
          onSubmit={(analysisType) => createAnalysisNode(modal.sourceNodeId, analysisType)}
        />
      ) : null}
      {modal?.kind === "result" ? (
        <ResultModal title={modal.title} url={modal.url} onClose={() => setModal(null)} />
      ) : null}
    </main>
    </AppChrome>
  );
}

function AppChrome({ page, onNavigate, children }) {
  const items = [
    { id: "home", label: "首页" },
    { id: "workbench", label: "开始分析" },
    { id: "docs", label: "操作文档" },
  ];

  return (
    <div className="app-frame">
      <header className="topbar">
        <button className="brand" onClick={() => onNavigate("home")}>
          <span className="brand-mark">Y</span>
          <span>
            <strong>YZW Cloud</strong>
            <small>Bioinformatics Workflow</small>
          </span>
        </button>
        <nav className="topnav">
          {items.map((item) => (
            <button
              className={page === item.id ? "active" : ""}
              key={item.id}
              onClick={() => onNavigate(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </header>
      {children}
    </div>
  );
}

function HomePage({ onStart }) {
  return (
    <main className="landing">
      <section className="landing-hero">
        <div className="hero-copy">
          <p className="eyebrow">YZW Bioinformatics Cloud</p>
          <h1>把表达矩阵拖进流程，让分析结果自己长出来</h1>
          <p>
            面向演示和轻量分析的生信流程工作台。读取表达矩阵后，可以按需创建 PCA、差异分析、热图和火山图节点，结果以交互页面呈现。
          </p>
          <div className="hero-actions">
            <button className="primary launch" onClick={onStart}>开始分析</button>
            <a href="#capabilities">查看能力</a>
          </div>
        </div>
        <div className="hero-visual" aria-hidden="true">
          <div className="orbit orbit-a" />
          <div className="orbit orbit-b" />
          <div className="data-card card-a">
            <span>PCA</span>
            <strong>52 samples</strong>
          </div>
          <div className="data-card card-b">
            <span>Volcano</span>
            <strong>5k genes</strong>
          </div>
          <div className="pipeline-line" />
          <div className="node-glow n1" />
          <div className="node-glow n2" />
          <div className="node-glow n3" />
        </div>
      </section>

      <section className="capabilities" id="capabilities">
        <FeatureCard title="流程化分析" text="每一步都是可拖动节点，前置节点完成后再按需创建后续节点。" />
        <FeatureCard title="真实图形输出" text="PCA、热图、火山图会生成预览和可交互的大图页面。" />
        <FeatureCard title="适合演示扩展" text="当前保持轻量实现，后续可以继续接入调度、数据库和更多分析模块。" />
      </section>
    </main>
  );
}

function FeatureCard({ title, text }) {
  return (
    <article className="feature-card">
      <span />
      <h2>{title}</h2>
      <p>{text}</p>
    </article>
  );
}

function DocsPage({ onStart }) {
  return (
    <main className="docs-page">
      <section className="docs-hero">
        <p className="eyebrow">Workflow Guide</p>
        <h1>操作文档</h1>
        <p>按下面顺序做，可以完成表达矩阵读取、PCA、分组差异分析、热图和火山图演示。</p>
        <button className="primary compact" onClick={onStart}>进入分析台</button>
      </section>
      <section className="doc-grid">
        <DocStep index="01" title="创建任务" text="进入分析台后点击创建示例任务，任务会出现在左侧列表。" />
        <DocStep index="02" title="读取表达矩阵" text="执行读取表达矩阵节点，系统会读取项目根目录的 expression_matrix.csv 和 sample_metadata.csv。" />
        <DocStep index="03" title="创建 PCA" text="表达矩阵节点完成后点击节点上的 +，选择 PCA，执行后点击预览打开交互图。" />
        <DocStep index="04" title="做差异分析" text="点击 + 选择差异分析，再选择 case/control 分组，例如 cancer vs normal。" />
        <DocStep index="05" title="生成图表" text="差异分析完成后点击该分支节点的 +，选择热图或火山图，执行后点击预览查看大图。" />
        <DocStep index="06" title="管理流程" text="节点可以拖动，Ctrl + 滚轮缩放；删除节点时，下游子节点会一起删除。" />
      </section>
    </main>
  );
}

function DocStep({ index, title, text }) {
  return (
    <article className="doc-step">
      <span>{index}</span>
      <h2>{title}</h2>
      <p>{text}</p>
    </article>
  );
}

function AnalysisNode({ data }) {
  const node = data.node;
  const output = summarizeOutput(node.output);
  const options = nextAnalysisOptions(node, data.detail);
  const canRun = node.id === "diff_analysis" || node.status === "ready" || node.status === "failed";
  const previewUrl = node.output?.meta?.preview_file
    ? outputUrl(data.detail.task.task_id, node.output.meta.preview_file)
    : null;
  const canOpenResult = Boolean(node.output?.meta?.html_file);

  return (
    <article className={`analysis-node ${node.status}`}>
      <Handle type="target" position={Position.Left} />
      <div className="node-topline">
        <span className="status-dot" />
        <span className="status">{statusLabel[node.status] || node.status}</span>
        <button className="node-delete" onClick={() => data.onDelete(node.id)} title="删除节点及下游">×</button>
      </div>
      <h3 title={node.description}>{node.name}</h3>
      <small>输出：{output}</small>
      {previewUrl ? (
        <button className="result-preview nodrag" onClick={() => data.onOpenResult(node)}>
          <img src={previewUrl} alt={`${node.name} 预览`} />
          {canOpenResult ? <span>点击查看大图</span> : null}
        </button>
      ) : null}
      <div className="node-actions">
        <button className="run" disabled={!canRun} onClick={() => data.onRun(node.id)}>
          {node.id === "diff_analysis" ? "选择分组" : node.status === "failed" ? "重新执行" : "执行节点"}
        </button>
        {options.length ? (
          <button className="add-next" onClick={() => data.onAddNext(node.id)} title="添加后续分析">+</button>
        ) : null}
      </div>
      <Handle type="source" position={Position.Right} />
    </article>
  );
}

function ResultModal({ title, url, onClose }) {
  return (
    <div className="result-backdrop">
      <section className="result-shell">
        <div className="result-header">
          <h2>{title}</h2>
          <button onClick={onClose}>×</button>
        </div>
        <iframe title={title} src={url} />
      </section>
    </div>
  );
}

function ComparisonModal({ options, onClose, onSubmit }) {
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

function NextAnalysisModal({ options, onClose, onSubmit }) {
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

function Modal({ children, onClose }) {
  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      {children}
    </div>
  );
}

function visibleGraphNodes(nodes) {
  return nodes.filter((node) => node.status !== "pending" && node.status !== "blocked");
}

function nextAnalysisOptions(node, detail) {
  if (node.status !== "completed") return [];
  if (node.id === "upload_expression") {
    const hasSelector = detail?.graph.edges.some(
      (edge) => edge.source === "upload_expression" && edge.target === "diff_analysis",
    );
    const hasPca = detail?.graph.edges.some(
      (edge) => edge.source === "upload_expression" && edge.target.startsWith("pca__"),
    );
    const options = [];
    if (!hasSelector) options.push({ type: "diff_analysis", label: "差异分析" });
    if (!hasPca) options.push({ type: "pca", label: "PCA" });
    return options;
  }
  if (node.id.startsWith("diff_analysis__")) {
    return [
      { type: "heatmap", label: "热图" },
      { type: "volcano", label: "火山图" },
      { type: "enrichment", label: "富集分析" },
    ];
  }
  return [];
}

function summarizeOutput(output) {
  if (!output) return "暂无";
  const meta = output.meta || {};
  if (output.type === "expression_matrix" && meta.gene_count && meta.sample_count) {
    return `${meta.gene_count} 基因 / ${meta.sample_count} 样本`;
  }
  if (output.type === "diff_result" && meta.comparison_label) {
    return meta.comparison_label;
  }
  if (output.type === "pca_plot" && meta.sample_count) {
    return `${meta.sample_count} 样本 PCA`;
  }
  return output.type;
}

function outputUrl(taskId, path) {
  const filename = String(path).split(/[\\/]/).pop();
  return `/api/tasks/${taskId}/outputs/${encodeURIComponent(filename)}`;
}

function fallbackPosition(node, index, nodes) {
  if (defaultPositions[node.id]) return defaultPositions[node.id];
  const diffBranches = nodes.filter((item) => item.id.startsWith("diff_analysis__"));
  if (node.id.startsWith("diff_analysis__")) {
    const branchIndex = Math.max(0, diffBranches.findIndex((item) => item.id === node.id));
    return { x: 680, y: 120 + branchIndex * 190 };
  }
  if (node.id.startsWith("pca__")) {
    return { x: 640, y: 390 };
  }
  const downstreamPrefix = ["heatmap__", "volcano__", "enrichment__"].find((prefix) => node.id.startsWith(prefix));
  if (downstreamPrefix) {
    const diffId = node.depends_on?.[0];
    const branchIndex = Math.max(0, diffBranches.findIndex((item) => item.id === diffId));
    const offset = node.id.startsWith("heatmap__") ? -70 : node.id.startsWith("volcano__") ? 35 : 140;
    return { x: 1000, y: 120 + branchIndex * 190 + offset };
  }
  return { x: 100 + (index % 4) * 280, y: 120 + Math.floor(index / 4) * 180 };
}

function positionKey(taskId) {
  return `yzwcloud.reactflow.positions.${taskId}`;
}

function readNodePosition(taskId, nodeId) {
  try {
    return JSON.parse(localStorage.getItem(positionKey(taskId)) || "{}")[nodeId] || null;
  } catch {
    return null;
  }
}

function saveNodePosition(taskId, nodeId, position) {
  const positions = JSON.parse(localStorage.getItem(positionKey(taskId)) || "{}");
  positions[nodeId] = position;
  localStorage.setItem(positionKey(taskId), JSON.stringify(positions));
}

function removeStoredNodePosition(taskId, nodeId) {
  const positions = JSON.parse(localStorage.getItem(positionKey(taskId)) || "{}");
  delete positions[nodeId];
  localStorage.setItem(positionKey(taskId), JSON.stringify(positions));
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ReactFlowProvider>
      <App />
    </ReactFlowProvider>
  </React.StrictMode>,
);
