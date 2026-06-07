import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "tdesign-react/es/_util/react-19-adapter";
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
import { Button, Dropdown, Tag } from "tdesign-react";
import { AddIcon, MoreIcon, RefreshIcon } from "tdesign-icons-react";
import "@xyflow/react/dist/style.css";
import "tdesign-react/es/style/index.css";
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
import { SubscriptionPage } from "./pages/SubscriptionPage.jsx";
import {
  createPlotStudioSession,
  createPlotStudioSessionFromSource,
  updatePlotStudioSessionSource,
} from "./plotStudio/session.js";
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

const PAGE_IDS = new Set(["home", "workbench", "plot", "subscription", "docs", "lab", "reports"]);
const PAGE_STORAGE_KEY = "yzwcloud.currentPage";
const TASK_STORAGE_KEY = "yzwcloud.activeTaskId";

function notifyError(message) {
  console.error(message || "操作失败");
}

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
  return response;
}

function edgeHandlesForPositions(sourcePosition, targetPosition) {
  if (!sourcePosition || !targetPosition) {
    return { sourceHandle: "source-right", targetHandle: "target-left" };
  }
  const sourceCenter = {
    x: sourcePosition.x + 89,
    y: sourcePosition.y + 75,
  };
  const targetCenter = {
    x: targetPosition.x + 89,
    y: targetPosition.y + 75,
  };
  const verticalDelta = targetCenter.y - sourceCenter.y;
  const horizontalDelta = targetCenter.x - sourceCenter.x;
  const verticalThreshold = 70;

  if (Math.abs(verticalDelta) <= verticalThreshold) {
    return { sourceHandle: "source-right", targetHandle: "target-left" };
  }
  if (verticalDelta < 0) {
    return {
      sourceHandle: horizontalDelta > 120 ? "source-right" : "source-top",
      targetHandle: "target-bottom",
    };
  }
  return {
    sourceHandle: horizontalDelta > 120 ? "source-right" : "source-bottom",
    targetHandle: "target-top",
  };
}

function App() {
  const { t } = useI18n();
  const { getViewport, setViewport } = useReactFlow();
  const [tasks, setTasks] = useState([]);
  const [activeTaskId, setActiveTaskId] = useState(() => localStorage.getItem(TASK_STORAGE_KEY) || null);
  const [detail, setDetail] = useState(null);
  const [logs, setLogs] = useState("");
  const [modal, setModal] = useState(null);
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [page, setPage] = useState(initialPage);
  const [showMiniMap, setShowMiniMap] = useState(false);
  const [editingTaskId, setEditingTaskId] = useState(null);
  const [editingTaskName, setEditingTaskName] = useState("");
  const [plotStudioSession, setPlotStudioSession] = useState(() => createPlotStudioSession());
  const flowPanelRef = useRef(null);
  const miniMapTimerRef = useRef(null);
  const reportModel = useMemo(() => buildReportModel(detail, logs), [detail, logs]);

  const loadTasks = useCallback(async () => {
    const response = await api("/api/tasks");
    const data = await response.json();
    setTasks(data);
    setActiveTaskId((currentTaskId) => {
      if (currentTaskId && data.some((task) => task.task_id === currentTaskId)) {
        return currentTaskId;
      }
      return data[0]?.task_id || null;
    });
  }, []);

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
    loadTasks().catch((error) => notifyError(error.message));
  }, [loadTasks]);

  useEffect(() => {
    loadDetail(activeTaskId).catch((error) => notifyError(error.message));
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
    if (activeTaskId) {
      localStorage.setItem(TASK_STORAGE_KEY, activeTaskId);
    } else {
      localStorage.removeItem(TASK_STORAGE_KEY);
    }
  }, [activeTaskId]);

  useEffect(() => {
    const handleHashChange = () => {
      const nextPage = normalizePage(window.location.hash);
      if (nextPage === "plot") {
        setPlotStudioSession(createPlotStudioSession());
      }
      setPage(nextPage);
    };
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  useEffect(() => {
    if (!detail) {
      setNodes([]);
      setEdges([]);
      return;
    }
    const graphNodes = visibleGraphNodes(detail.graph.nodes, detail.graph.edges);
    const flowNodes = graphNodes.map((node, index) => {
      const position = readNodePosition(detail.task.task_id, node.id) || fallbackPosition(node, index, graphNodes);
      return {
        id: node.id,
        type: "analysisNode",
        position,
        data: {
          node,
          detail,
          onRun: runNode,
          onDelete: deleteNode,
          onUploadInput: uploadInputFile,
          onEditGroups: openGroupEditor,
          onAddNext: openNextModal,
          onOpenResult: openResultModal,
          onOpenAgentReport: openAgentReport,
          onOpenPlotStudio: openPlotStudioFromNode,
        },
      };
    });
    const nodePositions = new Map(flowNodes.map((node) => [node.id, node.position]));
    const visibleIds = new Set(graphNodes.map((node) => node.id));
    const flowEdges = detail.graph.edges
      .filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target))
      .map((edge) => {
        const handles = edgeHandlesForPositions(nodePositions.get(edge.source), nodePositions.get(edge.target));
        return {
          id: `${edge.source}->${edge.target}`,
          source: edge.source,
          target: edge.target,
          sourceHandle: handles.sourceHandle,
          targetHandle: handles.targetHandle,
          animated: true,
          className: "flow-edge",
          style: { strokeWidth: 4 },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 18,
            height: 18,
            color: "#0052d9",
          },
        };
      });
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
    setModal({
      kind: "confirmDelete",
      title: "删除任务",
      message: `确定删除「${task.name}」吗？任务数据、输出和日志都会删除。`,
      confirmLabel: "删除任务",
      target: { type: "task", taskId: task.task_id },
    });
  };

  const deleteTask = async (taskId) => {
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
    setEditingTaskId(task.task_id);
    setEditingTaskName(task.name);
  };

  const handleTaskMenuClick = (task, item) => {
    if (item.value === "rename") {
      startRenameTask(task);
      return;
    }
    if (item.value === "delete") {
      requestDeleteTask(task);
    }
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

  function openResultModal(node, taskId = activeTaskId) {
    const htmlFile = node.output?.meta?.html_file;
    if (!htmlFile) return;
    const version = encodeURIComponent(node.completed_at || Date.now());
    const plotStudioResult = node.output?.meta?.plot_studio_result || null;
    const savedHtmlFile = plotStudioResult?.html_file || "";
    const source = buildPlotSourceFromNode(node);
    setModal({
      kind: "result",
      title: node.name,
      url: `${outputUrl(taskId, savedHtmlFile || htmlFile)}?v=${encodeURIComponent(plotStudioResult?.saved_at || version)}`,
      originalUrl: savedHtmlFile ? `${outputUrl(taskId, htmlFile)}?v=${version}` : "",
      hasSavedPlot: Boolean(savedHtmlFile),
      source,
      agentReportNode: node.output?.meta?.agent_report ? node : null,
    });
  }

  function openAgentReport(node) {
    setModal({ kind: "agentReport", node });
  }

  function buildPlotSourceFromNode(node) {
    const meta = node.output?.meta || {};
    const upstreamMeta = mergedUpstreamOutputMeta(node.id);
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
      meta: { ...upstreamMeta, ...meta },
    };
  }

  function mergedUpstreamOutputMeta(nodeId, visited = new Set()) {
    if (!detail || visited.has(nodeId)) return {};
    visited.add(nodeId);
    const incomingNodes = (detail.graph.edges || [])
      .filter((edge) => edge.target === nodeId)
      .map((edge) => detail.graph.nodes.find((item) => item.id === edge.source))
      .filter(Boolean);
    return incomingNodes.reduce((merged, upstreamNode) => ({
      ...mergedUpstreamOutputMeta(upstreamNode.id, visited),
      ...merged,
      ...(upstreamNode.output?.meta || {}),
    }), {});
  }

  function openPlotStudio(source = null) {
    if (source && !source.currentTarget) {
      setPlotStudioSession(createPlotStudioSessionFromSource(source));
    } else {
      setPlotStudioSession(createPlotStudioSession());
    }
    setPage("plot");
  }

  function navigatePage(nextPage) {
    if (nextPage === "plot") {
      setPlotStudioSession(createPlotStudioSession());
    }
    setPage(nextPage);
  }

  function openPlotStudioFromNode(node) {
    if (!node?.output || !activeTaskId) return;
    openPlotStudio(buildPlotSourceFromNode(node));
  }

  function openPlotStudioFromResult(source) {
    if (!source || !activeTaskId) return;
    setModal(null);
    setPlotStudioSession(createPlotStudioSessionFromSource(source, { returnTarget: source }));
    setPage("plot");
  }

  async function savePlotStudioBackToResult({ source, plotType, params }) {
    if (!activeTaskId || !source?.nodeId) return;
    const response = await api(
      `/api/tasks/${activeTaskId}/nodes/${encodeURIComponent(source.nodeId)}/plot-studio-result`,
      {
        method: "POST",
        body: JSON.stringify({
          source,
          plotType,
          params,
        }),
      },
    );
    const updatedDetail = await response.json();
    setDetail(updatedDetail);
    setPlotStudioSession((current) => ({ ...current, returnTarget: null }));
    setPage("workbench");
    const updatedNode = updatedDetail.graph.nodes.find((item) => item.id === source.nodeId);
    if (updatedNode) {
      openResultModal(updatedNode, updatedDetail.task.task_id);
    }
  }

  async function openGroupEditor() {
    if (!activeTaskId) return;
    try {
      const response = await api(`/api/tasks/${activeTaskId}/sample-groups`);
      setModal({ kind: "groups", payload: await response.json() });
    } catch (error) {
      notifyError(`无法读取分组信息：${error.message}`);
    }
  }

  async function openComparisonModal() {
    try {
      const response = await api(`/api/tasks/${activeTaskId}/comparison-options`);
      setModal({ kind: "comparison", options: await response.json() });
    } catch (error) {
      notifyError(`无法读取分组信息：${error.message}`);
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

  const uploadInputFile = async (_inputKind, fileList) => {
    if (!activeTaskId || !fileList) return;
    const files = Array.from(fileList);
    if (!files.length) return;
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file, file.name));
    const response = await fetch(`/api/tasks/${activeTaskId}/inputs`, {
      method: "POST",
      body: formData,
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
      notifyError(`上传失败：${detail}`);
      return;
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

  const openWorkbench = () => navigatePage("workbench");
  const taskReportHtmlUrl = detail ? `/api/tasks/${encodeURIComponent(detail.task.task_id)}/report.html` : "";
  const taskStatusTheme = (status) => {
    if (status === "failed") return "danger";
    if (status === "completed") return "success";
    if (status === "running") return "primary";
    return "default";
  };

  if (page === "home") {
    return (
      <AppChrome page={page} onNavigate={navigatePage}>
        <HomePage onStart={openWorkbench} onOpenPlot={openPlotStudio} />
      </AppChrome>
    );
  }

  if (page === "docs") {
    return (
      <AppChrome page={page} onNavigate={navigatePage}>
        <DocsPage onStart={openWorkbench} onOpenPlot={openPlotStudio} />
      </AppChrome>
    );
  }

  if (page === "lab") {
    return (
      <AppChrome page={page} onNavigate={navigatePage}>
        <MolecularLabPage />
      </AppChrome>
    );
  }

  if (page === "plot") {
    return (
      <AppChrome page={page} onNavigate={navigatePage}>
        <PlotStudioPage
          session={plotStudioSession}
          report={reportModel}
          activeTaskId={activeTaskId}
          onSessionChange={setPlotStudioSession}
          onSelectSource={(nextSource) => {
            setPlotStudioSession((current) => updatePlotStudioSessionSource(current, nextSource));
          }}
          onOpenAnalysis={openWorkbench}
          onSaveToResult={savePlotStudioBackToResult}
        />
      </AppChrome>
    );
  }

  if (page === "subscription") {
    return (
      <AppChrome page={page} onNavigate={navigatePage}>
        <SubscriptionPage onStart={openWorkbench} />
      </AppChrome>
    );
  }

  if (page === "reports") {
    return (
      <AppChrome page={page} onNavigate={navigatePage}>
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
    <AppChrome page={page} onNavigate={navigatePage}>
    <main className="workbench-shell">
      <section className="workbench-layout">
        <aside className="panel task-sidebar">
          <div className="task-sidebar-top">
            <Button
              className="workbench-brand"
              variant="text"
              onClick={() => setPage("home")}
            >
              <span className="brand-mark">Y</span>
              <span>
                <strong>YZW BioCloud</strong>
                <small>{t("home")}</small>
              </span>
            </Button>
            <Button
              className="new-task-button"
              theme="primary"
              shape="round"
              block
              icon={<AddIcon />}
              onClick={createTask}
            >
              {t("newAnalysisTask")}
            </Button>
            <div className="task-sidebar-actions">
              <Button variant="outline" shape="round" block icon={<RefreshIcon />} onClick={loadTasks}>
                {t("refresh")}
              </Button>
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
                    <span className="task-meta">
                      <Tag
                        className={`task-status-tag ${task.status}`}
                        theme={taskStatusTheme(task.status)}
                        variant="light"
                        shape="round"
                        size="small"
                      >
                        {task.status}
                      </Tag>
                      <span className="task-id">{task.task_id}</span>
                    </span>
                  </button>
                )}
                <div className="task-menu-wrap">
                  <Dropdown
                    trigger="click"
                    placement="bottom-right"
                    options={[
                      { content: t("rename"), value: "rename" },
                      { content: t("delete"), value: "delete", theme: "error" },
                    ]}
                    onClick={(item) => handleTaskMenuClick(task, item)}
                  >
                    <Button
                      className="task-menu-button"
                      type="button"
                      aria-label={t("task")}
                      shape="circle"
                      variant="text"
                      icon={<MoreIcon />}
                    >
                    </Button>
                  </Dropdown>
                </div>
              </div>
            ))}
          </div>
        </aside>

        <section className="workspace workflow-workspace">
          <div className="workflow-topbar">
            <div>
              <div className="workflow-title-row">
                <h1>流程节点</h1>
                {detail ? (
                  <a className="workflow-report-primary" href={taskReportHtmlUrl} target="_blank" rel="noreferrer">
                    流程报告
                  </a>
                ) : null}
              </div>
              <span className="muted">{detail ? `${detail.task.name} · ${detail.task.status}` : "未选择任务"}</span>
            </div>
            <div className="workflow-report-actions">
              <span className="task-id">{detail ? detail.task.task_id : ""}</span>
            </div>
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
                  <MiniMap pannable zoomable nodeColor={(node) => statusColor[node.data.node.status] || "#c9d4e5"} />
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
        <ResultModal
          title={modal.title}
          url={modal.url}
          originalUrl={modal.originalUrl}
          hasSavedPlot={modal.hasSavedPlot}
          source={modal.source}
          agentReportNode={modal.agentReportNode}
          onClose={() => setModal(null)}
          onOpenPlotStudio={openPlotStudioFromResult}
          onOpenAgentReport={openAgentReport}
        />
      ) : null}
      {modal?.kind === "agentReport" ? (
        <AgentReportModal node={modal.node} onClose={() => setModal(null)} />
      ) : null}
      {modal?.kind === "nodeParams" ? (
        <NodeParamsModal
          node={modal.node}
          detail={detail}
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
