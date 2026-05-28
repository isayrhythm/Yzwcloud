import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Background,
  Controls,
  MiniMap,
  MarkerType,
  ReactFlow,
  ReactFlowProvider,
  applyEdgeChanges,
  applyNodeChanges,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { AnalysisNode } from "./components/AnalysisNode.jsx";
import { AppChrome } from "./components/AppChrome.jsx";
import { HeatmapParamsModal } from "./components/HeatmapParamsModal.jsx";
import { NodeParamsModal } from "./components/NodeParamsModal.jsx";
import { WgcnaParamsModal } from "./components/WgcnaParamsModal.jsx";
import {
  AgentReportModal,
  ComparisonModal,
  ConfirmDeleteModal,
  DatasetParamsModal,
  NextAnalysisModal,
  ResultModal,
} from "./components/WorkflowModals.jsx";
import { HomePage } from "./pages/HomePage.jsx";
import { DocsPage } from "./pages/DocsPage.jsx";
import { MolecularLabPage } from "./pages/MolecularLabPage.jsx";
import { PlotStudioPage } from "./pages/PlotStudioPage.jsx";
import { ReportsPage, buildReportModel } from "./pages/ReportsPage.jsx";
import { outputUrl } from "./workflow/format.js";
import {
  collectOccupiedNodeRects,
  fallbackPosition,
  findOpenNodePosition,
  nodeRect,
  readNodePosition,
  removeStoredNodePosition,
  rectsOverlap,
  saveNodePosition,
  visibleGraphNodes,
} from "./workflow/layout.js";
import { nextAnalysisOptions, summarizeOutput } from "./workflow/options.js";
import { statusColor } from "./workflow/status.js";
import { I18nProvider, useI18n } from "./i18n.jsx";
import "./styles.css";

const PAGE_IDS = new Set(["home", "workbench", "plot", "docs", "lab", "reports"]);
const PAGE_STORAGE_KEY = "yzwcloud.currentPage";

function normalizePage(value) {
  const page = String(value || "").replace(/^#\/?/, "").replace(/^\//, "");
  return PAGE_IDS.has(page) ? page : "home";
}

function initialPage() {
  const hashPage = normalizePage(window.location.hash);
  if (hashPage !== "home" || window.location.hash) return hashPage;
  const pathPage = normalizePage(window.location.pathname);
  if (pathPage !== "home") return pathPage;
  return normalizePage(localStorage.getItem(PAGE_STORAGE_KEY));
}

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
  const { t } = useI18n();
  const { getViewport, setViewport } = useReactFlow();
  const [tasks, setTasks] = useState([]);
  const [activeTaskId, setActiveTaskId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [logs, setLogs] = useState("");
  const [modal, setModal] = useState(null);
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [page, setPage] = useState(initialPage);
  const [showMiniMap, setShowMiniMap] = useState(false);
  const [taskMenuId, setTaskMenuId] = useState(null);
  const [taskMenuPosition, setTaskMenuPosition] = useState(null);
  const [editingTaskId, setEditingTaskId] = useState(null);
  const [editingTaskName, setEditingTaskName] = useState("");
  const [plotStudioSource, setPlotStudioSource] = useState(null);
  const flowPanelRef = useRef(null);
  const miniMapTimerRef = useRef(null);   const reportModel = useMemo(() => buildReportModel(detail, logs), [detail, logs]);

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
    localStorage.setItem(PAGE_STORAGE_KEY, page);
    const nextHash = `#${page}`;
    if (window.location.hash !== nextHash) {
      window.history.replaceState(null, "", nextHash);
    }
  }, [page]);

  useEffect(() => {
    const handleHashChange = () => {
      setPage(normalizePage(window.location.hash));
    };
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  useEffect(() => {
    if (!taskMenuId) return undefined;
    const closeTaskMenu = (event) => {
      if (event.target.closest?.(".task-menu-wrap, .task-menu")) return;
      setTaskMenuId(null);
      setTaskMenuPosition(null);
    };
    window.addEventListener("pointerdown", closeTaskMenu);
    return () => window.removeEventListener("pointerdown", closeTaskMenu);
  }, [taskMenuId]);

  useEffect(() => {
    if (!detail) {
      setNodes([]);
      setEdges([]);
      return;
    }
    const graphNodes = visibleGraphNodes(detail.graph.nodes, detail.graph.edges);
    const flowNodes = graphNodes.map((node, index) => ({
      id: node.id,
      type: "analysisNode",
      position: readNodePosition(detail.task.task_id, node.id) || fallbackPosition(node, index, graphNodes),
      data: {
        node,
        detail,
        onRun: runNode,
        onDelete: deleteNode,
        onUploadInput: uploadInputFile,
        onUploadMetadataText: uploadSampleMetadataText,
        onEditGroups: openGroupEditor,
        onAddNext: openNextModal,
        onOpenResult: openResultModal,
        onOpenAgentReport: openAgentReport,
        onOpenPlotStudio: openPlotStudioFromNode,
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
        style: { strokeWidth: 4 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 18,
          height: 18,
          color: "#0f6b57",
        },
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

  const requestDeleteTask = (task) => {
    setTaskMenuId(null);
    setTaskMenuPosition(null);
    setModal({
      kind: "confirmDelete",
      title: "删除任务",
      message: `确定删除「${task.name}」吗？任务数据、输出和日志都会删除。`,
      confirmLabel: "删除任务",
      target: { type: "task", taskId: task.task_id },
    });
  };

  const deleteTask = async (taskId) => {
    setTaskMenuId(null);
    setTaskMenuPosition(null);
    await api(`/api/tasks/${taskId}`, { method: "DELETE" });
    if (taskId === activeTaskId) {
      const nextTask = tasks.find((task) => task.task_id !== taskId);
      setActiveTaskId(nextTask?.task_id || null);
      setDetail(null);
    }
    await loadTasks();
  };

  const confirmDelete = async () => {
    if (modal?.kind !== "confirmDelete") return;
    const target = modal.target;
    setModal(null);
    if (target.type === "task") {
      await deleteTask(target.taskId);
      return;
    }
    if (target.type === "node" && activeTaskId) {
      await api(`/api/tasks/${activeTaskId}/nodes/${encodeURIComponent(target.nodeId)}`, {
        method: "DELETE",
      });
      removeStoredNodePosition(activeTaskId, target.nodeId);
      await loadDetail(activeTaskId);
    }
  };

  const startRenameTask = (task) => {
    setTaskMenuId(null);
    setTaskMenuPosition(null);
    setEditingTaskId(task.task_id);
    setEditingTaskName(task.name);
  };

  const cancelRenameTask = () => {
    setEditingTaskId(null);
    setEditingTaskName("");
  };

  const submitRenameTask = async (task) => {
    const cleanName = editingTaskName.trim();
    if (!cleanName || cleanName === task.name) {
      cancelRenameTask();
      return;
    }
    await api(`/api/tasks/${task.task_id}`, {
      method: "PATCH",
      body: JSON.stringify({ name: cleanName }),
    });
    cancelRenameTask();
    await loadTasks();
    if (task.task_id === activeTaskId) {
      await loadDetail(task.task_id);
    }
  };

  async function runNode(nodeId) {
    if (!activeTaskId) return;
    if (nodeId === "diff_analysis") {
      await openComparisonModal();
      return;
    }
    const node = detail?.graph.nodes.find((item) => item.id === nodeId);
    if (nodeId.startsWith("qc__") && node) {
      setModal({ kind: "nodeParams", node });
      return;
    }
    if (nodeId.startsWith("expression_heatmap__") && node) {
      setModal({ kind: "heatmapParams", node });
      return;
    }
    if (nodeId.startsWith("wgcna__") && node) {
      setModal({ kind: "wgcnaParams", node });
      return;
    }
    if (nodeId.startsWith("gene_expression__")) {
      const defaultGene = node?.output?.meta?.gene_id || node?.output?.meta?.gene || node?.params?.gene || "AUTO";
      const gene = window.prompt("请输入基因名或 gene_id；保留 AUTO 自动选择高变基因", defaultGene);
      if (gene === null) return;
      await api(`/api/tasks/${activeTaskId}/nodes/${encodeURIComponent(nodeId)}/run`, {
        method: "POST",
        body: JSON.stringify({ params: { gene: gene.trim() || "AUTO" } }),
      });
      await loadDetail(activeTaskId);
      return;
    }
    await api(`/api/tasks/${activeTaskId}/nodes/${encodeURIComponent(nodeId)}/run`, {
      method: "POST",
      body: JSON.stringify({ params: {} }),
    });
    await loadDetail(activeTaskId);
  }

  async function runNodeWithParams(nodeId, params) {
    if (!activeTaskId) return;
    await api(`/api/tasks/${activeTaskId}/nodes/${encodeURIComponent(nodeId)}/run`, {
      method: "POST",
      body: JSON.stringify({ params }),
    });
    setModal(null);
    await loadDetail(activeTaskId);
  }

  async function deleteNode(nodeId) {
    const message =
      nodeId === "upload_expression"
        ? "确定清空表达矩阵结果，并删除所有下游节点吗？"
        : "确定删除这个节点及所有下游子节点吗？";
    setModal({
      kind: "confirmDelete",
      title: nodeId === "upload_expression" ? "清空表达矩阵" : "删除流程节点",
      message,
      confirmLabel: nodeId === "upload_expression" ? "清空并删除下游" : "删除节点",
      target: { type: "node", nodeId },
    });
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
    const version = encodeURIComponent(node.completed_at || Date.now());
    setModal({
      kind: "result",
      title: node.name,
      url: `${outputUrl(activeTaskId, htmlFile)}?v=${version}`,
    });
  }

  function openAgentReport(node) {
    setModal({ kind: "agentReport", node });
  }

  function buildPlotSourceFromNode(node) {
    const meta = node.output?.meta || {};
    return {
      sourceKind: "analysis_node",
      taskId: activeTaskId,
      taskName: detail?.task?.name || "",
      nodeId: node.id,
      name: node.name,
      status: node.status,
      type: node.output?.type || "",
      summary: summarizeOutput(node.output),
      dataPath: node.output?.data || "",
      previewUrl: meta.preview_file ? outputUrl(activeTaskId, meta.preview_file) : "",
      htmlUrl: meta.html_file ? outputUrl(activeTaskId, meta.html_file) : "",
      meta,
    };
  }

  function openPlotStudio(source = null) {
    if (source && !source.currentTarget) {
      setPlotStudioSource(source);
    }
    setPage("plot");
  }

  function openPlotStudioFromNode(node) {
    if (!node?.output || !activeTaskId) return;
    openPlotStudio(buildPlotSourceFromNode(node));
  }

  async function openGroupEditor() {
    if (!activeTaskId) return;
    try {
      const response = await api(`/api/tasks/${activeTaskId}/sample-groups`);
      setModal({ kind: "groups", payload: await response.json() });
    } catch (error) {
      window.alert(`无法读取分组信息：${error.message}`);
    }
  }

  async function openComparisonModal() {
    try {
      const response = await api(`/api/tasks/${activeTaskId}/comparison-options`);
      setModal({ kind: "comparison", options: await response.json() });
    } catch (error) {
      window.alert(`无法读取分组信息：${error.message}`);
    }
  }

  const keepNewNodesInView = (sourceNodeId, updatedDetail) => {
    if (!activeTaskId || !detail || !updatedDetail) return;
    const panel = flowPanelRef.current;
    if (!panel) return;

    const previousVisible = new Set(visibleGraphNodes(detail.graph.nodes, detail.graph.edges).map((node) => node.id));
    const previousSourceTargets = new Set(
      detail.graph.edges
        .filter((edge) => edge.source === sourceNodeId)
        .map((edge) => edge.target),
    );
    const updatedVisibleNodes = visibleGraphNodes(updatedDetail.graph.nodes, updatedDetail.graph.edges);
    const createdIds = updatedVisibleNodes
      .filter((node) => !previousVisible.has(node.id))
      .map((node) => node.id);
    const newlyLinkedIds = updatedDetail.graph.edges
      .filter((edge) => edge.source === sourceNodeId && !previousSourceTargets.has(edge.target))
      .map((edge) => edge.target);
    const targetIds = Array.from(new Set([...createdIds, ...newlyLinkedIds]));
    if (!targetIds.length) return;

    const viewport = getViewport();
    const width = panel.clientWidth || 1000;
    const height = panel.clientHeight || 700;
    const zoom = viewport.zoom || 1;
    const bounds = {
      left: (-viewport.x / zoom) + 24,
      top: (-viewport.y / zoom) + 24,
      right: ((width - viewport.x) / zoom) - 300,
      bottom: ((height - viewport.y) / zoom) - 190,
    };
    const sourcePosition =
      nodes.find((node) => node.id === sourceNodeId)?.position ||
      readNodePosition(activeTaskId, sourceNodeId) ||
      fallbackPosition(
        updatedVisibleNodes.find((node) => node.id === sourceNodeId) || { id: sourceNodeId },
        0,
        updatedVisibleNodes,
      );

    const targetIdSet = new Set(targetIds);
    const occupiedRects = collectOccupiedNodeRects(activeTaskId, nodes, updatedVisibleNodes, targetIdSet);

    targetIds.forEach((nodeId, index) => {
      const graphNode = updatedVisibleNodes.find((node) => node.id === nodeId) || { id: nodeId };
      const currentPosition =
        nodes.find((node) => node.id === nodeId)?.position ||
        readNodePosition(activeTaskId, nodeId) ||
        fallbackPosition(graphNode, index, updatedVisibleNodes);
      const desired = {
        x: sourcePosition.x + 320,
        y: sourcePosition.y + index * 170,
      };
      const preferredPosition = previousVisible.has(nodeId) ? currentPosition : desired;
      const preferredRect = nodeRect(preferredPosition);
      const hasCollision = occupiedRects.some((rect) => rectsOverlap(preferredRect, rect));
      const position = hasCollision ? findOpenNodePosition(desired, occupiedRects, bounds) : preferredPosition;
      saveNodePosition(activeTaskId, nodeId, position);
      occupiedRects.push(nodeRect(position));
    });
  };

  const createAnalysisNode = async (sourceNodeId, analysisType) => {
    const response = await api(`/api/tasks/${activeTaskId}/analysis-nodes`, {
      method: "POST",
      body: JSON.stringify({ source_node_id: sourceNodeId, analysis_type: analysisType }),
    });
    const updatedDetail = await response.json();
    keepNewNodesInView(sourceNodeId, updatedDetail);
    setModal(null);
    await loadDetail(activeTaskId);
  };

  const uploadInputFile = async (inputKind, file) => {
    if (!activeTaskId || !file) return;
    const response = await fetch(
      `/api/tasks/${activeTaskId}/inputs/${inputKind}?filename=${encodeURIComponent(file.name)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: file,
      },
    );
    if (!response.ok) {
      let detail = response.statusText;
      try {
        detail = (await response.json()).detail || detail;
      } catch {
        detail = await response.text();
      }
      window.alert(`上传失败：${detail}`);
      return;
    }
    await loadDetail(activeTaskId);
  };

  const uploadSampleMetadataText = async (content) => {
    if (!activeTaskId) return;
    const response = await api(`/api/tasks/${activeTaskId}/inputs/sample_metadata/text`, {
      method: "POST",
      body: JSON.stringify({ content, filename: "sample_metadata.csv" }),
    });
    if (!response) {
      throw new Error("metadata upload failed");
    }
    await loadDetail(activeTaskId);
  };

  const updateSampleGroups = async ({ assignments, condition_colors }) => {
    await api(`/api/tasks/${activeTaskId}/sample-groups`, {
      method: "PUT",
      body: JSON.stringify({ assignments, condition_colors }),
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

  const showFlowMiniMap = useCallback(() => {
    setShowMiniMap(true);
  }, []);

  const hideFlowMiniMap = useCallback(() => {
    if (miniMapTimerRef.current) {
      window.clearTimeout(miniMapTimerRef.current);
      miniMapTimerRef.current = null;
    }
    setShowMiniMap(false);
  }, []);

  const pulseMiniMap = useCallback(() => {
    setShowMiniMap(true);
    if (miniMapTimerRef.current) {
      window.clearTimeout(miniMapTimerRef.current);
    }
    miniMapTimerRef.current = window.setTimeout(() => {
      setShowMiniMap(false);
      miniMapTimerRef.current = null;
    }, 140);
  }, []);

  useEffect(() => () => {
    if (miniMapTimerRef.current) {
      window.clearTimeout(miniMapTimerRef.current);
    }
  }, []);

  useEffect(() => {
    if (page !== "workbench") return undefined;

    const panel = flowPanelRef.current;
    if (!panel) return undefined;

    const handleWheel = (event) => {
      if (!event.ctrlKey && !event.metaKey) return;

      event.stopImmediatePropagation();
      event.preventDefault();
      pulseMiniMap();
      const viewport = getViewport();
      const nextZoom = Math.min(2, Math.max(0.2, viewport.zoom + (event.deltaY < 0 ? 0.08 : -0.08)));
      setViewport({ x: viewport.x, y: viewport.y, zoom: nextZoom }, { duration: 0 });
    };

    panel.addEventListener("wheel", handleWheel, { capture: true, passive: false });
    return () => panel.removeEventListener("wheel", handleWheel, { capture: true });
  }, [getViewport, page, pulseMiniMap, setViewport]);

  const openWorkbench = () => setPage("workbench");
  const openReports = () => setPage("reports");

  if (page === "home") {
    return (
      <AppChrome page={page} onNavigate={setPage}>
        <HomePage onStart={openWorkbench} onOpenPlot={openPlotStudio} />
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

  if (page === "lab") {
    return (
      <AppChrome page={page} onNavigate={setPage}>
        <MolecularLabPage />
      </AppChrome>
    );
  }

  if (page === "plot") {
    return (
      <AppChrome page={page} onNavigate={setPage}>
        <PlotStudioPage
          source={plotStudioSource}
          report={reportModel}
          activeTaskId={activeTaskId}
          onSelectSource={setPlotStudioSource}
          onOpenAnalysis={openWorkbench}
        />
      </AppChrome>
    );
  }

  if (page === "reports") {
    return (
      <AppChrome page={page} onNavigate={setPage}>
        <ReportsPage
          tasks={tasks}
          activeTaskId={activeTaskId}
          report={reportModel}
          onSelectTask={setActiveTaskId}
          onOpenAnalysis={openWorkbench}
          onOpenPlotStudio={openPlotStudio}
        />
      </AppChrome>
    );
  }

  return (
    <AppChrome page={page} onNavigate={setPage}>
    <main className="workbench-shell">
      <section className="workbench-layout">
        <aside className="panel task-sidebar">
          <div className="task-sidebar-top">
            <button className="workbench-brand" onClick={() => setPage("home")}>
              <span className="brand-mark">Y</span>
              <span>
                <strong>YZW BioCloud</strong>
                <small>{t("home")}</small>
              </span>
            </button>
            <button className="primary new-task-button" onClick={createTask}>{t("newAnalysisTask")}</button>
            <div className="task-sidebar-actions">
              <button className="ghost" onClick={loadTasks}>{t("refresh")}</button>
              <button className="ghost" onClick={openReports} disabled={!detail}>{t("reportButton")}</button>
            </div>
          </div>
          <div className="panel-title task-list-title">
            <h2>{t("taskList")}</h2>
            <span className="muted">{tasks.length} {t("total")}</span>
          </div>
          <div className="task-list">
            {tasks.length === 0 ? <p className="muted">还没有任务</p> : null}
            {tasks.map((task) => (
              <div className={`task-item ${task.task_id === activeTaskId ? "active" : ""} ${editingTaskId === task.task_id ? "editing" : ""}`} key={task.task_id}>
                {editingTaskId === task.task_id ? (
                  <form
                    className="task-rename-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      submitRenameTask(task);
                    }}
                  >
                    <input
                      autoFocus
                      value={editingTaskName}
                      onBlur={() => submitRenameTask(task)}
                      onChange={(event) => setEditingTaskName(event.target.value)}
                      onFocus={(event) => event.target.select()}
                      onKeyDown={(event) => {
                        if (event.key === "Escape") {
                          event.preventDefault();
                          cancelRenameTask();
                        }
                      }}
                    />
                    <span className="task-id">{task.status} · {task.task_id}</span>
                  </form>
                ) : (
                  <button className="task-select" onClick={() => setActiveTaskId(task.task_id)}>
                    <strong>{task.name}</strong>
                    <span className="task-id">{task.status} · {task.task_id}</span>
                  </button>
                )}
                <div className="task-menu-wrap">
                  <button
                    className="task-menu-button"
                    type="button"
                    aria-label={t("task")}
                    onClick={(event) => {
                      event.stopPropagation();
                      const rect = event.currentTarget.getBoundingClientRect();
                      const menuHeight = 104;
                      const openUp = rect.bottom + menuHeight > window.innerHeight - 12;
                      setTaskMenuPosition({
                        top: openUp ? rect.top - menuHeight - 6 : rect.bottom + 6,
                        right: window.innerWidth - rect.right,
                      });
                      setTaskMenuId((current) => {
                        if (current === task.task_id) {
                          setTaskMenuPosition(null);
                          return null;
                        }
                        return task.task_id;
                      });
                    }}
                  >
                    ...
                  </button>
                  {taskMenuId === task.task_id ? (
                    <div
                      className="task-menu"
                      style={taskMenuPosition ? { top: taskMenuPosition.top, right: taskMenuPosition.right } : undefined}
                    >
                      <button type="button" onClick={() => startRenameTask(task)}>{t("rename")}</button>
                      <button type="button" className="danger" onClick={() => requestDeleteTask(task)}>{t("delete")}</button>
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </aside>

        <section className="workspace workflow-workspace">
          <div className="workflow-topbar">
            <div>
              <h1>流程节点</h1>
              <span className="muted">{detail ? `${detail.task.name} · ${detail.task.status}` : "未选择任务"}</span>
            </div>
            <span className="task-id">{detail ? detail.task.task_id : ""}</span>
          </div>
          <div className="flow-panel" ref={flowPanelRef}>
            {detail ? (
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onMoveStart={showFlowMiniMap}
                onMove={showFlowMiniMap}
                onMoveEnd={hideFlowMiniMap}
                onNodeDragStart={showFlowMiniMap}
                onNodeDrag={showFlowMiniMap}
                onNodeDragStop={hideFlowMiniMap}
                fitView
                minZoom={0.2}
                maxZoom={2}
                zoomOnScroll={false}
                panOnScroll={false}
                proOptions={{ hideAttribution: true }}
                deleteKeyCode={null}
              >
                <Background gap={28} color="#b9cbd8" />
                <Controls position="top-right" />
                {showMiniMap ? (
                  <MiniMap pannable zoomable nodeColor={(node) => statusColor[node.data.node.status] || "#d2cabd"} />
                ) : null}
              </ReactFlow>
            ) : (
              <div className="empty-flow">先创建或选择一个任务</div>
            )}
          </div>
          <details className="log-drawer">
            <summary>任务日志</summary>
            <pre className="logs">{logs}</pre>
          </details>
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
      {modal?.kind === "agentReport" ? (
        <AgentReportModal node={modal.node} onClose={() => setModal(null)} />
      ) : null}
      {modal?.kind === "nodeParams" ? (
        <NodeParamsModal
          node={modal.node}
          onClose={() => setModal(null)}
          onSubmit={(params) => runNodeWithParams(modal.node.id, params)}
        />
      ) : null}
      {modal?.kind === "heatmapParams" ? (
        <HeatmapParamsModal
          node={modal.node}
          detail={detail}
          onClose={() => setModal(null)}
          onSubmit={(params) => runNodeWithParams(modal.node.id, params)}
        />
      ) : null}
      {modal?.kind === "wgcnaParams" ? (
        <WgcnaParamsModal
          node={modal.node}
          onClose={() => setModal(null)}
          onSubmit={(params) => runNodeWithParams(modal.node.id, params)}
        />
      ) : null}
      {modal?.kind === "groups" ? (
        <DatasetParamsModal
          payload={modal.payload}
          onClose={() => setModal(null)}
          onSubmit={updateSampleGroups}
        />
      ) : null}
      {modal?.kind === "confirmDelete" ? (
        <ConfirmDeleteModal
          title={modal.title}
          message={modal.message}
          confirmLabel={modal.confirmLabel}
          onClose={() => setModal(null)}
          onConfirm={confirmDelete}
        />
      ) : null}
    </main>
    </AppChrome>
  );
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <I18nProvider>
      <ReactFlowProvider>
        <App />
      </ReactFlowProvider>
    </I18nProvider>
  </React.StrictMode>,
);
