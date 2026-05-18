import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  MarkerType,
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
  qc__expression: { x: 640, y: 70 },
  correlation__expression: { x: 640, y: 210 },
  expression_heatmap__expression: { x: 640, y: 530 },
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

const NN_PARAMS = {
  AA: { dh: -7.9, ds: -22.2 },
  TT: { dh: -7.9, ds: -22.2 },
  AT: { dh: -7.2, ds: -20.4 },
  TA: { dh: -7.2, ds: -21.3 },
  CA: { dh: -8.5, ds: -22.7 },
  TG: { dh: -8.5, ds: -22.7 },
  GT: { dh: -8.4, ds: -22.4 },
  AC: { dh: -8.4, ds: -22.4 },
  CT: { dh: -7.8, ds: -21.0 },
  AG: { dh: -7.8, ds: -21.0 },
  GA: { dh: -8.2, ds: -22.2 },
  TC: { dh: -8.2, ds: -22.2 },
  CG: { dh: -10.6, ds: -27.2 },
  GC: { dh: -9.8, ds: -24.4 },
  GG: { dh: -8.0, ds: -19.9 },
  CC: { dh: -8.0, ds: -19.9 },
};

const DNA_COMPLEMENT = { A: "T", T: "A", C: "G", G: "C", N: "N" };

function normalizeSequence(value) {
  return String(value || "")
    .toUpperCase()
    .replace(/U/g, "T")
    .replace(/[^ATCGN]/g, "");
}

function gcContent(sequence) {
  if (!sequence.length) return 0;
  const gcCount = [...sequence].filter((base) => base === "G" || base === "C").length;
  return (gcCount / sequence.length) * 100;
}

function reverseSequence(sequence) {
  return [...sequence].reverse().join("");
}

function complementSequence(sequence) {
  return [...sequence].map((base) => DNA_COMPLEMENT[base] || "N").join("");
}

function reverseComplementSequence(sequence) {
  return reverseSequence(complementSequence(sequence));
}

function estimateTm(sequence, primerConcentrationNm = 250, saltConcentrationMm = 50) {
  const normalized = normalizeSequence(sequence);
  if (normalized.length < 2) {
    return { normalized, error: "Sequence must contain at least 2 DNA bases." };
  }

  let dh = 0.2;
  let ds = -5.7;
  for (let index = 0; index < normalized.length - 1; index += 1) {
    const pair = normalized.slice(index, index + 2);
    const params = NN_PARAMS[pair];
    if (!params) {
      return { normalized, error: `Unsupported dinucleotide: ${pair}` };
    }
    dh += params.dh;
    ds += params.ds;
  }

  const aCount = [...normalized].filter((base) => base === "A").length;
  const tCount = [...normalized].filter((base) => base === "T").length;
  const gCount = [...normalized].filter((base) => base === "G").length;
  const cCount = [...normalized].filter((base) => base === "C").length;
  const concentrationM = Math.max(primerConcentrationNm, 1) * 1e-9;
  const sodiumM = Math.max(saltConcentrationMm, 1) * 1e-3;
  const gasConstant = 1.987;
  const tmNearestNeighbor =
    (1000 * dh) / (ds + gasConstant * Math.log(concentrationM / 4)) - 273.15 + 16.6 * Math.log10(sodiumM);

  return {
    normalized,
    length: normalized.length,
    gcPercent: gcContent(normalized),
    tmNearestNeighbor,
    tmWallace: 2 * (aCount + tCount) + 4 * (gCount + cCount),
    recommendedAnnealing: tmNearestNeighbor - 5,
  };
}

async function copyToClipboard(value) {
  if (!navigator.clipboard) return false;
  await navigator.clipboard.writeText(value);
  return true;
}

const CODON_TABLE = {
  TTT: "F", TTC: "F", TTA: "L", TTG: "L",
  TCT: "S", TCC: "S", TCA: "S", TCG: "S",
  TAT: "Y", TAC: "Y", TAA: "*", TAG: "*",
  TGT: "C", TGC: "C", TGA: "*", TGG: "W",
  CTT: "L", CTC: "L", CTA: "L", CTG: "L",
  CCT: "P", CCC: "P", CCA: "P", CCG: "P",
  CAT: "H", CAC: "H", CAA: "Q", CAG: "Q",
  CGT: "R", CGC: "R", CGA: "R", CGG: "R",
  ATT: "I", ATC: "I", ATA: "I", ATG: "M",
  ACT: "T", ACC: "T", ACA: "T", ACG: "T",
  AAT: "N", AAC: "N", AAA: "K", AAG: "K",
  AGT: "S", AGC: "S", AGA: "R", AGG: "R",
  GTT: "V", GTC: "V", GTA: "V", GTG: "V",
  GCT: "A", GCC: "A", GCA: "A", GCG: "A",
  GAT: "D", GAC: "D", GAA: "E", GAG: "E",
  GGT: "G", GGC: "G", GGA: "G", GGG: "G",
};

const RESTRICTION_ENZYMES = [
  { name: "EcoRI", site: "GAATTC" },
  { name: "BamHI", site: "GGATCC" },
  { name: "HindIII", site: "AAGCTT" },
  { name: "NotI", site: "GCGGCCGC" },
  { name: "XhoI", site: "CTCGAG" },
  { name: "NheI", site: "GCTAGC" },
  { name: "XbaI", site: "TCTAGA" },
  { name: "SpeI", site: "ACTAGT" },
  { name: "KpnI", site: "GGTACC" },
  { name: "SacI", site: "GAGCTC" },
  { name: "PstI", site: "CTGCAG" },
  { name: "SalI", site: "GTCGAC" },
];

const LAB_MODULES = [
  {
    id: "primer_tm",
    group: "Primer",
    title: "Primer Tm",
    summary: "Single-primer Tm, GC, and annealing estimate.",
  },
  {
    id: "primer_pair",
    group: "Primer",
    title: "Primer Pair",
    summary: "Forward/reverse comparison and Tm balance.",
  },
  {
    id: "oligo_screen",
    group: "Primer",
    title: "Hairpin/Dimer",
    summary: "Rough self- and cross-dimer screening.",
  },
  {
    id: "dna_tools",
    group: "Sequence",
    title: "DNA Tools",
    summary: "Reverse, complement, reverse-complement, and copy helpers.",
  },
  {
    id: "transcription",
    group: "Sequence",
    title: "DNA/RNA Convert",
    summary: "DNA<->RNA conversion for coding strand workflows.",
  },
  {
    id: "translation",
    group: "Sequence",
    title: "ORF/Translation",
    summary: "Translate frames and enumerate ORFs.",
  },
  {
    id: "restriction_scan",
    group: "Cloning",
    title: "Restriction Scan",
    summary: "Scan common enzyme sites and cut positions.",
  },
];

function normalizeRnaSequence(value) {
  return String(value || "")
    .toUpperCase()
    .replace(/T/g, "U")
    .replace(/[^AUCGN]/g, "");
}

function dnaToRna(sequence) {
  return normalizeSequence(sequence).replace(/T/g, "U");
}

function rnaToDna(sequence) {
  return normalizeRnaSequence(sequence).replace(/U/g, "T");
}

function longestCommonSubstring(first, second) {
  if (!first || !second) return "";
  const matrix = Array.from({ length: first.length + 1 }, () => Array(second.length + 1).fill(0));
  let maxLength = 0;
  let endIndex = 0;
  for (let row = 1; row <= first.length; row += 1) {
    for (let col = 1; col <= second.length; col += 1) {
      if (first[row - 1] === second[col - 1]) {
        matrix[row][col] = matrix[row - 1][col - 1] + 1;
        if (matrix[row][col] > maxLength) {
          maxLength = matrix[row][col];
          endIndex = row;
        }
      }
    }
  }
  return first.slice(endIndex - maxLength, endIndex);
}

function scoreComplementRisk(matchLength, threePrimeMatch) {
  if (matchLength >= 6 || threePrimeMatch >= 4) return "High";
  if (matchLength >= 4 || threePrimeMatch >= 3) return "Medium";
  return "Low";
}

function countThreePrimeComplement(first, second) {
  let count = 0;
  const limit = Math.min(first.length, second.length);
  for (let index = 0; index < limit; index += 1) {
    const leftBase = first[first.length - 1 - index];
    const rightBase = second[second.length - 1 - index];
    if ((DNA_COMPLEMENT[leftBase] || "N") !== rightBase) break;
    count += 1;
  }
  return count;
}

function screenOligos(primerA, primerB = "") {
  const first = normalizeSequence(primerA);
  const second = normalizeSequence(primerB || primerA);
  const firstRc = reverseComplementSequence(first);
  const secondRc = reverseComplementSequence(second);
  const hairpinSeed = longestCommonSubstring(first, firstRc);
  const selfDimerSeed = longestCommonSubstring(first, firstRc);
  const crossDimerSeed = longestCommonSubstring(first, secondRc);
  const self3Prime = countThreePrimeComplement(first, firstRc);
  const cross3Prime = countThreePrimeComplement(first, secondRc);

  return {
    first,
    second,
    hairpin: {
      seed: hairpinSeed,
      matchLength: hairpinSeed.length,
      risk: scoreComplementRisk(hairpinSeed.length, self3Prime),
      threePrimeMatch: self3Prime,
    },
    selfDimer: {
      seed: selfDimerSeed,
      matchLength: selfDimerSeed.length,
      risk: scoreComplementRisk(selfDimerSeed.length, self3Prime),
      threePrimeMatch: self3Prime,
    },
    crossDimer: {
      seed: crossDimerSeed,
      matchLength: crossDimerSeed.length,
      risk: scoreComplementRisk(crossDimerSeed.length, cross3Prime),
      threePrimeMatch: cross3Prime,
    },
  };
}

function translateSequence(sequence, frame = 1) {
  const normalized = normalizeSequence(sequence);
  let peptide = "";
  for (let index = frame - 1; index + 2 < normalized.length; index += 3) {
    peptide += CODON_TABLE[normalized.slice(index, index + 3)] || "X";
  }
  return peptide;
}

function findOrfs(sequence, strand = "forward") {
  const normalized = strand === "reverse" ? reverseComplementSequence(sequence) : normalizeSequence(sequence);
  const orfs = [];
  for (let frame = 0; frame < 3; frame += 1) {
    for (let index = frame; index + 2 < normalized.length; index += 3) {
      if (normalized.slice(index, index + 3) !== "ATG") continue;
      let peptide = "M";
      let stopIndex = -1;
      for (let cursor = index + 3; cursor + 2 < normalized.length; cursor += 3) {
        const codon = normalized.slice(cursor, cursor + 3);
        const aa = CODON_TABLE[codon] || "X";
        if (aa === "*") {
          stopIndex = cursor + 3;
          break;
        }
        peptide += aa;
      }
      if (stopIndex > 0) {
        orfs.push({
          strand,
          frame: frame + 1,
          start: index + 1,
          end: stopIndex,
          lengthNt: stopIndex - index,
          peptide,
        });
      }
    }
  }
  return orfs.sort((left, right) => right.lengthNt - left.lengthNt);
}

function scanRestrictionSites(sequence) {
  const normalized = normalizeSequence(sequence);
  return RESTRICTION_ENZYMES.map((enzyme) => {
    const positions = [];
    let startIndex = 0;
    while (startIndex < normalized.length) {
      const matchIndex = normalized.indexOf(enzyme.site, startIndex);
      if (matchIndex < 0) break;
      positions.push(matchIndex + 1);
      startIndex = matchIndex + 1;
    }
    return {
      ...enzyme,
      positions,
      count: positions.length,
      ranges: positions.map((position) => ({
        start: position - 1,
        end: position - 1 + enzyme.site.length,
      })),
    };
  }).filter((enzyme) => enzyme.count > 0);
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
  return (detail.graph.nodes || [])
    .filter((node) => node.output)
    .map((node) => ({
      id: node.id,
      name: node.name,
      status: node.status,
      type: node.output?.type || "-",
      summary: summarizeOutput(node.output),
      hasPreview: Boolean(node.output?.meta?.preview_file),
      hasHtml: Boolean(node.output?.meta?.html_file),
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

function buildReportModel(detail, logs) {
  const summary = summarizeTaskGraph(detail);
  const outputs = collectReportOutputs(detail);
  const insights = buildReportInsights(detail);
  const logLines = String(logs || "").split(/\r?\n/).filter(Boolean);

  return {
    task: detail?.task || null,
    summary,
    outputs,
    insights,
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
        onEditGroups: openGroupEditor,
        onAddNext: openNextModal,
        onOpenResult: openResultModal,
        onOpenAgentReport: openAgentReport,
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
    if (nodeId.startsWith("gene_expression__")) {
      const gene = window.prompt("请输入基因名或 gene_id");
      if (!gene) return;
      await api(`/api/tasks/${activeTaskId}/nodes/${encodeURIComponent(nodeId)}/run`, {
        method: "POST",
        body: JSON.stringify({ params: { gene } }),
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

  function openAgentReport(node) {
    setModal({ kind: "agentReport", node });
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

  const createAnalysisNode = async (sourceNodeId, analysisType) => {
    await api(`/api/tasks/${activeTaskId}/analysis-nodes`, {
      method: "POST",
      body: JSON.stringify({ source_node_id: sourceNodeId, analysis_type: analysisType }),
    });
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

  const updateSampleGroups = async (assignments) => {
    await api(`/api/tasks/${activeTaskId}/sample-groups`, {
      method: "PUT",
      body: JSON.stringify({ assignments }),
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
    if (page !== "workbench") return undefined;

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
  }, [getViewport, page, revealMiniMap, setViewport]);

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

  if (page === "lab") {
    return (
      <AppChrome page={page} onNavigate={setPage}>
        <MolecularLabPage />
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
        />
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
      {modal?.kind === "agentReport" ? (
        <AgentReportModal node={modal.node} onClose={() => setModal(null)} />
      ) : null}
      {modal?.kind === "groups" ? (
        <GroupEditorModal
          payload={modal.payload}
          onClose={() => setModal(null)}
          onSubmit={updateSampleGroups}
        />
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
    { id: "lab", label: "Experiment Design" },
    { id: "reports", label: "Reports" },
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
        <DocStep index="02" title="上传数据" text="在数据上传节点选择数据文件，Agent 会自动识别类型、规整格式，并判断下一步可做哪些分析。" />
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

function ReportsPage({ tasks, activeTaskId, report, onSelectTask, onOpenAnalysis }) {   const task = report?.task || null;   const summary = report?.summary || summarizeTaskGraph(null);   const outputs = report?.outputs || [];   const insights = report?.insights || [];   const logPreview = report?.logTail || "";   return (     <main className="reports-page shell">       <section className="hero report-hero">         <div>           <p className="eyebrow">Reports</p>           <h1>Interpretation And Export</h1>           <p className="summary">Review finished outputs, flag failed branches, and package the current task into a report-friendly summary.</p>         </div>         <button className="primary" onClick={onOpenAnalysis}>Back To Analysis Workspace</button>       </section>       <section className="layout reports-layout">         <aside className="panel">           <div className="panel-title">             <h2>Tasks</h2>             <span className="muted">{tasks.length} total</span>           </div>           <div className="task-list">             {tasks.length === 0 ? <p className="muted">No task yet.</p> : null}             {tasks.map((item) => (               <div className={`task-item ${item.task_id === activeTaskId ? "active" : ""}`} key={item.task_id}>                 <button className="task-select" onClick={() => onSelectTask(item.task_id)}>                   <strong>{item.name}</strong>                   <span className="task-id">{item.status} ? {item.task_id}</span>                 </button>               </div>             ))}           </div>         </aside>         <section className="workspace reports-workspace">           <div className="panel-title">             <h2>{task ? task.name : "Report Summary"}</h2>             <span className="muted">{task ? `${task.status} ? ${task.task_id}` : "Select a task"}</span>           </div>           <div className="report-summary-grid">             <Metric label="Nodes" value={task ? `${summary.totalNodes}` : "-"} />             <Metric label="Completed" value={task ? `${summary.completedNodes}` : "-"} />             <Metric label="Failed" value={task ? `${summary.failedNodes}` : "-"} />             <Metric label="Outputs" value={task ? `${summary.outputNodes}` : "-"} />           </div>           <div className="report-section-grid">             <section className="report-surface">               <div className="panel-title"><h2>Key Findings</h2></div>               <div className="report-insight-list">                 {insights.length ? insights.map((insight) => (                   <article key={insight.title} className={`report-insight ${insight.tone || "neutral"}`}>                     <strong>{insight.title}</strong>                     <p>{insight.text}</p>                   </article>                 )) : <p className="muted">Run analysis nodes to populate interpretation cards.</p>}               </div>             </section>             <section className="report-surface">               <div className="panel-title"><h2>Outputs</h2></div>               <div className="report-output-list">                 {outputs.length ? outputs.map((output) => (                   <article key={output.id} className="report-output-card">                     <div><strong>{output.name}</strong><span>{output.type}</span></div>                     <p>{output.summary}</p>                     <small>{output.status}{output.hasHtml ? " ? interactive" : ""}{output.hasPreview ? " ? preview" : ""}</small>                   </article>                 )) : <p className="muted">No output object is ready for reporting yet.</p>}               </div>             </section>           </div>           <section className="report-surface">             <div className="panel-title">               <h2>Report Agent Context</h2>               <span className="muted">{report?.readyForAgent ? "ready" : "pending"}</span>             </div>             <div className="report-summary-grid">               <Metric label="Warnings" value={`${report?.warnings?.length || 0}`} />               <Metric label="Outputs" value={`${outputs.length}`} />               <Metric label="Log lines" value={`${report?.logLineCount || 0}`} />               <Metric label="Nodes in context" value={`${report?.agentContext?.nodes?.length || 0}`} />             </div>             <p className="report-note">This object is the stable input boundary for the future report agent. It keeps task metadata, graph state, outputs, insights, and log tail in one place instead of scattering them across the page.</p>           </section>           <section className="report-surface">             <div className="panel-title"><h2>Log Tail</h2></div>             <pre className="logs report-log">{logPreview || "No log yet."}</pre>           </section>         </section>       </section>     </main>   ); }  function MolecularLabPage() {
  const [activeModule, setActiveModule] = useState("primer_tm");
  const activeModuleMeta = LAB_MODULES.find((item) => item.id === activeModule) || LAB_MODULES[0];

  return (
    <main className="lab-page">
      <section className="lab-hero">
        <div>
          <p className="eyebrow">Molecular Biology</p>
          <h1>Molecular Lab</h1>
          <p className="summary">
            Experiment design utilities organized as selectable units. Invalid characters stay visible and are
            highlighted instead of being hard-blocked.
          </p>
        </div>
      </section>
      <section className="lab-module-picker">
        {LAB_MODULES.map((module) => (
          <button
            key={module.id}
            type="button"
            className={`lab-module-tile ${activeModule === module.id ? "active" : ""}`}
            onClick={() => setActiveModule(module.id)}
          >
            <span>{module.group}</span>
            <strong>{module.title}</strong>
            <small>{module.summary}</small>
          </button>
        ))}
      </section>
      <section className="lab-workspace">
        <div className="lab-workspace-head">
          <div>
            <span className="lab-chip">{activeModuleMeta.group}</span>
            <h2>{activeModuleMeta.title}</h2>
          </div>
          <p>{activeModuleMeta.summary}</p>
        </div>
        <MolecularLabModule moduleId={activeModule} />
      </section>
    </main>
  );
}

function PrimerTmCard() {
  const [sequence, setSequence] = useState("");
  const [primerConcentration, setPrimerConcentration] = useState("250");
  const [saltConcentration, setSaltConcentration] = useState("50");
  const result = useMemo(
    () => estimateTm(sequence, Number(primerConcentration), Number(saltConcentration)),
    [primerConcentration, saltConcentration, sequence],
  );

  return (
    <section className="lab-card">
      <div className="lab-card-header">
        <div>
          <span className="lab-chip">Primer</span>
          <h2>Primer Tm Calculator</h2>
        </div>
      </div>
      <label className="lab-field">
        <span>Primer sequence</span>
        <textarea
          rows="8"
          value={sequence}
          onChange={(event) => setSequence(event.target.value)}
          placeholder="Paste a primer sequence. Non-DNA characters are ignored."
        />
      </label>
      <div className="lab-form-grid">
        <label className="lab-field">
          <span>Primer concentration (nM)</span>
          <input
            type="number"
            min="1"
            step="1"
            value={primerConcentration}
            onChange={(event) => setPrimerConcentration(event.target.value)}
          />
        </label>
        <label className="lab-field">
          <span>Salt concentration (mM)</span>
          <input
            type="number"
            min="1"
            step="1"
            value={saltConcentration}
            onChange={(event) => setSaltConcentration(event.target.value)}
          />
        </label>
      </div>
      {result.error ? (
        <p className="lab-error">{result.error}</p>
      ) : (
        <>
          <div className="lab-sequence-box">
            <strong>Normalized</strong>
            <code>{result.normalized || "-"}</code>
          </div>
          <div className="lab-metric-grid">
            <Metric label="Length" value={result.length ? `${result.length} nt` : "-"} />
            <Metric label="GC%" value={result.length ? `${result.gcPercent.toFixed(1)}%` : "-"} />
            <Metric label="Tm (NN)" value={result.length ? `${result.tmNearestNeighbor.toFixed(2)} °C` : "-"} />
            <Metric label="Tm (Wallace)" value={result.length ? `${result.tmWallace.toFixed(2)} °C` : "-"} />
            <Metric
              label="Suggested annealing"
              value={result.length ? `${result.recommendedAnnealing.toFixed(2)} °C` : "-"}
            />
          </div>
        </>
      )}
    </section>
  );
}

function DnaSequenceCard() {
  const [sequence, setSequence] = useState("");
  const [copiedLabel, setCopiedLabel] = useState("");
  const normalized = useMemo(() => normalizeSequence(sequence), [sequence]);
  const reversed = useMemo(() => reverseSequence(normalized), [normalized]);
  const complemented = useMemo(() => complementSequence(normalized), [normalized]);
  const reverseComplemented = useMemo(() => reverseComplementSequence(normalized), [normalized]);

  async function handleCopy(label, value) {
    if (!value) return;
    try {
      await copyToClipboard(value);
      setCopiedLabel(label);
      window.setTimeout(() => setCopiedLabel(""), 1400);
    } catch {
      setCopiedLabel("");
    }
  }

  return (
    <section className="lab-card">
      <div className="lab-card-header">
        <div>
          <span className="lab-chip">Sequence</span>
          <h2>DNA Sequence Tools</h2>
        </div>
      </div>
      <label className="lab-field">
        <span>DNA sequence</span>
        <textarea
          rows="8"
          value={sequence}
          onChange={(event) => setSequence(event.target.value)}
          placeholder="Paste a DNA sequence to generate normalized, reverse, complement, and reverse-complement forms."
        />
      </label>
      <div className="lab-metric-grid compact">
        <Metric label="Length" value={normalized ? `${normalized.length} nt` : "-"} />
        <Metric label="GC%" value={normalized ? `${gcContent(normalized).toFixed(1)}%` : "-"} />
      </div>
      <SequenceResult
        label="Normalized"
        value={normalized}
        copied={copiedLabel === "Normalized"}
        onCopy={() => handleCopy("Normalized", normalized)}
      />
      <SequenceResult
        label="Reverse"
        value={reversed}
        copied={copiedLabel === "Reverse"}
        onCopy={() => handleCopy("Reverse", reversed)}
      />
      <SequenceResult
        label="Complement"
        value={complemented}
        copied={copiedLabel === "Complement"}
        onCopy={() => handleCopy("Complement", complemented)}
      />
      <SequenceResult
        label="Reverse complement"
        value={reverseComplemented}
        copied={copiedLabel === "Reverse complement"}
        onCopy={() => handleCopy("Reverse complement", reverseComplemented)}
      />
    </section>
  );
}

function Metric({ label, value }) {
  return (
    <div className="lab-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SequenceResult({ label, value, onCopy, copied }) {
  return (
    <div className="sequence-result">
      <div className="sequence-result-top">
        <strong>{label}</strong>
        <button type="button" className="ghost" onClick={onCopy} disabled={!value}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <code>{value || "-"}</code>
    </div>
  );
}

function MolecularLabModule({ moduleId }) {
  if (moduleId === "primer_tm") return <PrimerTmWorkbench />;
  if (moduleId === "primer_pair") return <PrimerPairWorkbench />;
  if (moduleId === "oligo_screen") return <OligoScreenWorkbench />;
  if (moduleId === "dna_tools") return <DnaToolsWorkbench />;
  if (moduleId === "transcription") return <TranscriptionWorkbench />;
  if (moduleId === "translation") return <TranslationWorkbench />;
  if (moduleId === "restriction_scan") return <RestrictionScanWorkbench />;
  return null;
}

function HighlightedSequenceInput({ value, onChange, placeholder, rows = 8, mode = "dna" }) {
  return (
    <div className={`sequence-editor ${mode === "rna" ? "rna" : "dna"}`}>
      <textarea rows={rows} value={value} onChange={onChange} placeholder={placeholder} spellCheck="false" />
      <div className="sequence-editor-preview">
        <span>Invalid character preview</span>
        <pre aria-hidden="true" className="sequence-editor-highlight">
          {renderHighlightedSequence(value, mode)}
        </pre>
      </div>
    </div>
  );
}

function renderHighlightedSequence(value, mode) {
  const source = String(value || "");
  return source.split("").map((char, index) => {
    const upper = char.toUpperCase();
    const valid = /\s/.test(char) || (mode === "rna" ? /[AUCGN]/.test(upper) : /[ATCGUN]/.test(upper));
    return (
      <span key={`${char}-${index}`} className={valid ? "" : "invalid"}>
        {char}
      </span>
    );
  });
}

function PrimerTmWorkbench() {
  const [sequence, setSequence] = useState("");
  const [primerConcentration, setPrimerConcentration] = useState("250");
  const [saltConcentration, setSaltConcentration] = useState("50");
  const result = useMemo(
    () => estimateTm(sequence, Number(primerConcentration), Number(saltConcentration)),
    [primerConcentration, saltConcentration, sequence],
  );

  return (
    <section className="lab-card">
      <label className="lab-field">
        <span>Primer sequence</span>
        <HighlightedSequenceInput
          rows={8}
          value={sequence}
          onChange={(event) => setSequence(event.target.value)}
          placeholder="Paste a primer sequence. Invalid symbols are highlighted."
        />
      </label>
      <div className="lab-form-grid">
        <label className="lab-field">
          <span>Primer concentration (nM)</span>
          <input type="number" min="1" step="1" value={primerConcentration} onChange={(event) => setPrimerConcentration(event.target.value)} />
        </label>
        <label className="lab-field">
          <span>Salt concentration (mM)</span>
          <input type="number" min="1" step="1" value={saltConcentration} onChange={(event) => setSaltConcentration(event.target.value)} />
        </label>
      </div>
      {result.error ? <p className="lab-error">{result.error}</p> : (
        <>
          <div className="lab-sequence-box">
            <strong>Normalized</strong>
            <code>{result.normalized || "-"}</code>
          </div>
          <div className="lab-metric-grid">
            <Metric label="Length" value={result.length ? `${result.length} nt` : "-"} />
            <Metric label="GC%" value={result.length ? `${result.gcPercent.toFixed(1)}%` : "-"} />
            <Metric label="Tm (NN)" value={result.length ? `${result.tmNearestNeighbor.toFixed(2)} degC` : "-"} />
            <Metric label="Tm (Wallace)" value={result.length ? `${result.tmWallace.toFixed(2)} degC` : "-"} />
            <Metric label="Suggested annealing" value={result.length ? `${result.recommendedAnnealing.toFixed(2)} degC` : "-"} />
          </div>
        </>
      )}
    </section>
  );
}

function PrimerPairWorkbench() {
  const [forward, setForward] = useState("");
  const [reverse, setReverse] = useState("");
  const [primerConcentration, setPrimerConcentration] = useState("250");
  const [saltConcentration, setSaltConcentration] = useState("50");
  const left = useMemo(() => estimateTm(forward, Number(primerConcentration), Number(saltConcentration)), [forward, primerConcentration, saltConcentration]);
  const right = useMemo(() => estimateTm(reverse, Number(primerConcentration), Number(saltConcentration)), [reverse, primerConcentration, saltConcentration]);
  const tmGap = !left.error && !right.error && left.length && right.length ? Math.abs(left.tmNearestNeighbor - right.tmNearestNeighbor) : null;

  return (
    <section className="lab-card">
      <div className="lab-form-grid">
        <label className="lab-field">
          <span>Forward primer</span>
          <HighlightedSequenceInput rows={6} value={forward} onChange={(event) => setForward(event.target.value)} placeholder="Forward primer" />
        </label>
        <label className="lab-field">
          <span>Reverse primer</span>
          <HighlightedSequenceInput rows={6} value={reverse} onChange={(event) => setReverse(event.target.value)} placeholder="Reverse primer" />
        </label>
      </div>
      <div className="lab-form-grid">
        <label className="lab-field">
          <span>Primer concentration (nM)</span>
          <input value={primerConcentration} onChange={(event) => setPrimerConcentration(event.target.value)} />
        </label>
        <label className="lab-field">
          <span>Salt concentration (mM)</span>
          <input value={saltConcentration} onChange={(event) => setSaltConcentration(event.target.value)} />
        </label>
      </div>
      <div className="lab-metric-grid">
        <Metric label="Forward Tm" value={!left.error && left.length ? `${left.tmNearestNeighbor.toFixed(2)} degC` : "-"} />
        <Metric label="Reverse Tm" value={!right.error && right.length ? `${right.tmNearestNeighbor.toFixed(2)} degC` : "-"} />
        <Metric label="Tm gap" value={tmGap !== null ? `${tmGap.toFixed(2)} degC` : "-"} />
        <Metric label="Forward GC%" value={!left.error && left.length ? `${left.gcPercent.toFixed(1)}%` : "-"} />
        <Metric label="Reverse GC%" value={!right.error && right.length ? `${right.gcPercent.toFixed(1)}%` : "-"} />
        <Metric label="Pair balance" value={tmGap === null ? "-" : tmGap <= 2 ? "Tight" : tmGap <= 5 ? "Usable" : "Poor"} />
      </div>
    </section>
  );
}

function OligoScreenWorkbench() {
  const [primerA, setPrimerA] = useState("");
  const [primerB, setPrimerB] = useState("");
  const result = useMemo(() => screenOligos(primerA, primerB), [primerA, primerB]);

  return (
    <section className="lab-card">
      <div className="lab-form-grid">
        <label className="lab-field">
          <span>Primer A</span>
          <HighlightedSequenceInput rows={6} value={primerA} onChange={(event) => setPrimerA(event.target.value)} placeholder="Primer A" />
        </label>
        <label className="lab-field">
          <span>Primer B (optional)</span>
          <HighlightedSequenceInput rows={6} value={primerB} onChange={(event) => setPrimerB(event.target.value)} placeholder="Leave blank to reuse primer A" />
        </label>
      </div>
      <div className="lab-risk-grid">
        <RiskCard title="Hairpin" data={result.hairpin} />
        <RiskCard title="Self-dimer" data={result.selfDimer} />
        <RiskCard title="Cross-dimer" data={result.crossDimer} />
      </div>
    </section>
  );
}

function DnaToolsWorkbench() {
  const [sequence, setSequence] = useState("");
  const [copiedLabel, setCopiedLabel] = useState("");
  const normalized = useMemo(() => normalizeSequence(sequence), [sequence]);
  const reversed = useMemo(() => reverseSequence(normalized), [normalized]);
  const complemented = useMemo(() => complementSequence(normalized), [normalized]);
  const reverseComplemented = useMemo(() => reverseComplementSequence(normalized), [normalized]);

  async function handleCopy(label, value) {
    if (!value) return;
    try {
      await copyToClipboard(value);
      setCopiedLabel(label);
      window.setTimeout(() => setCopiedLabel(""), 1400);
    } catch {
      setCopiedLabel("");
    }
  }

  return (
    <section className="lab-card">
      <label className="lab-field">
        <span>DNA sequence</span>
        <HighlightedSequenceInput rows={8} value={sequence} onChange={(event) => setSequence(event.target.value)} placeholder="Paste a DNA sequence." />
      </label>
      <div className="lab-metric-grid compact">
        <Metric label="Length" value={normalized ? `${normalized.length} nt` : "-"} />
        <Metric label="GC%" value={normalized ? `${gcContent(normalized).toFixed(1)}%` : "-"} />
      </div>
      <SequenceResult label="Normalized" value={normalized} copied={copiedLabel === "Normalized"} onCopy={() => handleCopy("Normalized", normalized)} />
      <SequenceResult label="Reverse" value={reversed} copied={copiedLabel === "Reverse"} onCopy={() => handleCopy("Reverse", reversed)} />
      <SequenceResult label="Complement" value={complemented} copied={copiedLabel === "Complement"} onCopy={() => handleCopy("Complement", complemented)} />
      <SequenceResult label="Reverse complement" value={reverseComplemented} copied={copiedLabel === "Reverse complement"} onCopy={() => handleCopy("Reverse complement", reverseComplemented)} />
    </section>
  );
}

function TranscriptionWorkbench() {
  const [dna, setDna] = useState("");
  const [rna, setRna] = useState("");
  const dnaNormalized = useMemo(() => normalizeSequence(dna), [dna]);
  const rnaNormalized = useMemo(() => normalizeRnaSequence(rna), [rna]);

  return (
    <section className="lab-card">
      <div className="lab-form-grid">
        <label className="lab-field">
          <span>DNA sequence</span>
          <HighlightedSequenceInput rows={7} value={dna} onChange={(event) => setDna(event.target.value)} placeholder="Coding strand DNA" />
        </label>
        <label className="lab-field">
          <span>RNA sequence</span>
          <HighlightedSequenceInput rows={7} mode="rna" value={rna} onChange={(event) => setRna(event.target.value)} placeholder="mRNA sequence" />
        </label>
      </div>
      <SequenceResult label="DNA -> RNA" value={dnaNormalized ? dnaToRna(dnaNormalized) : ""} onCopy={() => copyToClipboard(dnaToRna(dnaNormalized))} copied={false} />
      <SequenceResult label="RNA -> DNA" value={rnaNormalized ? rnaToDna(rnaNormalized) : ""} onCopy={() => copyToClipboard(rnaToDna(rnaNormalized))} copied={false} />
    </section>
  );
}

function TranslationWorkbench() {
  const [sequence, setSequence] = useState("");
  const [frame, setFrame] = useState("1");
  const [strand, setStrand] = useState("forward");
  const source = useMemo(() => {
    const normalized = normalizeSequence(sequence);
    return strand === "reverse" ? reverseComplementSequence(normalized) : normalized;
  }, [sequence, strand]);
  const translated = useMemo(() => translateSequence(source, Number(frame)), [source, frame]);
  const orfs = useMemo(() => [...findOrfs(sequence, "forward"), ...findOrfs(sequence, "reverse")].slice(0, 12), [sequence]);

  return (
    <section className="lab-card">
      <label className="lab-field">
        <span>DNA/RNA sequence</span>
        <HighlightedSequenceInput rows={8} value={sequence} onChange={(event) => setSequence(event.target.value)} placeholder="Paste DNA or RNA. U is accepted." />
      </label>
      <div className="lab-form-grid">
        <label className="lab-field">
          <span>Frame</span>
          <select value={frame} onChange={(event) => setFrame(event.target.value)}>
            <option value="1">Frame 1</option>
            <option value="2">Frame 2</option>
            <option value="3">Frame 3</option>
          </select>
        </label>
        <label className="lab-field">
          <span>Strand</span>
          <select value={strand} onChange={(event) => setStrand(event.target.value)}>
            <option value="forward">Forward</option>
            <option value="reverse">Reverse complement</option>
          </select>
        </label>
      </div>
      <SequenceResult label="Translated peptide" value={translated} onCopy={() => copyToClipboard(translated)} copied={false} />
      <div className="orf-list">
        {orfs.length ? orfs.map((orf, index) => (
          <div key={`${orf.strand}-${orf.frame}-${orf.start}-${index}`} className="orf-row">
            <strong>{orf.strand} / frame {orf.frame}</strong>
            <span>{orf.start}-{orf.end} ({orf.lengthNt} nt)</span>
            <code>{orf.peptide}</code>
          </div>
        )) : <p className="muted">No complete ORF found yet.</p>}
      </div>
    </section>
  );
}

function RestrictionScanWorkbench() {
  const [sequence, setSequence] = useState("");
  const hits = useMemo(() => scanRestrictionSites(sequence), [sequence]);

  return (
    <section className="lab-card">
      <label className="lab-field">
        <span>DNA sequence</span>
        <HighlightedSequenceInput rows={8} value={sequence} onChange={(event) => setSequence(event.target.value)} placeholder="Paste a DNA sequence to scan common restriction sites." />
      </label>
      <div className="restriction-table">
        {hits.length ? hits.map((hit) => (
          <div key={hit.name} className="restriction-row">
            <strong>{hit.name}</strong>
            <span>{hit.site}</span>
            <span>{hit.count} site(s)</span>
            <code>{hit.positions.join(", ")}</code>
          </div>
        )) : <p className="muted">No common sites detected in the current panel.</p>}
      </div>
    </section>
  );
}

function RiskCard({ title, data }) {
  return (
    <div className={`risk-card risk-${String(data.risk || "").toLowerCase()}`}>
      <div className="sequence-result-top">
        <strong>{title}</strong>
        <span className="risk-badge">{data.risk}</span>
      </div>
      <div className="lab-metric-grid compact">
        <Metric label="Longest seed" value={data.matchLength ? `${data.matchLength} bp` : "-"} />
        <Metric label="3' match" value={data.threePrimeMatch ? `${data.threePrimeMatch} bp` : "-"} />
      </div>
      <code>{data.seed || "-"}</code>
    </div>
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
  const uploadedInput = node.params?.uploaded_inputs?.expression_matrix;
  const uploadStateLabel = node.output ? "已识别" : uploadedInput ? "已上传，待 Agent 检查" : "等待上传";

  return (
    <article className={`analysis-node ${node.status} ${uploadedInput ? "has-uploaded-input" : ""}`}>
      <Handle type="target" position={Position.Left} />
      <div className="node-topline">
        <span className="status-dot" />
        <span className="status">{statusLabel[node.status] || node.status}</span>
        <button className="node-delete" onClick={() => data.onDelete(node.id)} title="删除节点及下游">×</button>
      </div>
      <h3 title={node.description}>{node.name}</h3>
      <small>输出：{output}</small>
      {node.id === "upload_expression" ? (
        <div className="upload-controls nodrag">
          {uploadedInput ? (
            <div className="uploaded-file-card">
              <span>{uploadStateLabel}</span>
              <strong title={uploadedInput.filename}>{uploadedInput.filename}</strong>
              <small>
                {formatBytes(uploadedInput.size)}
                {uploadedInput.uploaded_at ? ` · ${formatDateTime(uploadedInput.uploaded_at)}` : ""}
              </small>
            </div>
          ) : null}
          <label className={uploadedInput ? "replace-upload" : ""}>
            {uploadedInput ? "更换数据" : "上传数据"}
            <input
              type="file"
              accept=".csv,.xlsx,.xlsm,.zip,.tar,.tgz,.gz,.tar.gz"
              onChange={(event) => {
                data.onUploadInput("expression_matrix", event.target.files?.[0]);
                event.target.value = "";
              }}
            />
          </label>
          {node.output?.meta?.sample_metadata_file ? (
            <button type="button" onClick={() => data.onEditGroups()}>
              矫正分组
            </button>
          ) : null}
        </div>
      ) : null}
      {node.id === "upload_expression" && (node.status === "running" || node.params?.agent_progress) ? (
        <AgentProgress
          progress={node.params?.agent_progress}
          failed={node.status === "failed"}
          onOpenReport={() => data.onOpenAgentReport(node)}
        />
      ) : null}
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

function AgentProgress({ progress, failed, onOpenReport }) {
  const history = progress?.history || [];
  const currentStep = progress?.step || "queued";
  const steps = [
    { step: "inspect_file", label: "读取数据" },
    { step: "classify_data", label: "识别类型" },
    { step: "standardize_data", label: "规整数据" },
    { step: "validate_output", label: "验证数据" },
  ];
  const activeIndex = steps.findIndex((item) => item.step === currentStep);
  const completedCount = history.filter((item) => item.status === "completed").length;
  const stepCount =
    progress?.status === "completed"
      ? steps.length
      : activeIndex >= 0
        ? activeIndex + 1
        : Math.min(completedCount + 1, steps.length);
  const lastDone = [...history].reverse().find((item) => item.status === "completed");
  return (
    <div className={`agent-progress compact ${failed ? "failed" : progress?.status || "running"}`}>
      <span className="agent-pulse" />
      <div className="agent-copy">
        <strong key={progress?.label || "Agent 正在准备"}>{progress?.label || "Agent 正在准备"}</strong>
        {lastDone && progress?.status !== "completed" ? <small>刚完成：{lastDone.label}</small> : null}
      </div>
      <span className="agent-step-count">{stepCount}/{steps.length}</span>
      {failed ? (
        <button className="agent-report-link nodrag" type="button" onClick={onOpenReport}>
          查看报告
        </button>
      ) : null}
    </div>
  );
}

function AgentReportModal({ node, onClose }) {
  const progress = node.params?.agent_progress || {};
  const report = node.params?.agent_report || {};
  const history = progress.history || [];
  const uploaded = node.params?.uploaded_inputs?.expression_matrix;
  return (
    <Modal onClose={onClose}>
      <section className="modal agent-report-modal">
        <h2>{report.title || "数据处理报告"}</h2>
        <p>{report.summary || "Agent 没有把这个文件规整成当前流程可用的数据对象。"}</p>
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

function GroupEditorModal({ payload, onClose, onSubmit }) {
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
        <h2>矫正样本分组</h2>
        <p>修改 condition 后会重新计算该数据节点的下一步分析入口。至少两个分组且每组样本数足够时，才会开放差异分析。</p>
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

function visibleGraphNodes(nodes, edges) {
  return nodes.filter((node) => {
    if (node.status === "pending" || node.status === "blocked") return false;
    if (node.id === "diff_analysis") {
      return edges.some((edge) => edge.source === "upload_expression" && edge.target === "diff_analysis");
    }
    return true;
  });
}

function nextAnalysisOptions(node, detail) {
  if (node.status !== "completed") return [];
  if (node.id === "upload_expression") {
    const nextAnalyses = node.output?.meta?.next_analyses;
    if (Array.isArray(nextAnalyses)) {
      const created = {
        diff_analysis: detail?.graph.edges.some(
          (edge) => edge.source === "upload_expression" && edge.target === "diff_analysis",
        ),
        pca: detail?.graph.edges.some(
          (edge) => edge.source === "upload_expression" && edge.target.startsWith("pca__"),
        ),
        qc: detail?.graph.edges.some(
          (edge) => edge.source === "upload_expression" && edge.target.startsWith("qc__"),
        ),
        sample_correlation: detail?.graph.edges.some(
          (edge) => edge.source === "upload_expression" && edge.target.startsWith("correlation__"),
        ),
        expression_heatmap: detail?.graph.edges.some(
          (edge) => edge.source === "upload_expression" && edge.target.startsWith("expression_heatmap__"),
        ),
      };
      return nextAnalyses.filter((analysis) => analysis.type === "gene_expression" || !created[analysis.type]);
    }
    const capabilities = new Set(node.output?.meta?.capabilities || ["qc", "sample_correlation", "expression_heatmap", "gene_expression", "pca", "diff_analysis"]);
    const hasSelector = !capabilities.has("diff_analysis") || detail?.graph.edges.some(
      (edge) => edge.source === "upload_expression" && edge.target === "diff_analysis",
    );
    const hasPca = !capabilities.has("pca") || detail?.graph.edges.some(
      (edge) => edge.source === "upload_expression" && edge.target.startsWith("pca__"),
    );
    const hasQc = !capabilities.has("qc") || detail?.graph.edges.some(
      (edge) => edge.source === "upload_expression" && edge.target.startsWith("qc__"),
    );
    const hasCorrelation = !capabilities.has("sample_correlation") || detail?.graph.edges.some(
      (edge) => edge.source === "upload_expression" && edge.target.startsWith("correlation__"),
    );
    const hasExpressionHeatmap = !capabilities.has("expression_heatmap") || detail?.graph.edges.some(
      (edge) => edge.source === "upload_expression" && edge.target.startsWith("expression_heatmap__"),
    );
    const options = [];
    if (!hasQc) options.push({ type: "qc", label: "矩阵 QC" });
    if (!hasCorrelation) options.push({ type: "sample_correlation", label: "样本相关性" });
    if (!hasExpressionHeatmap) options.push({ type: "expression_heatmap", label: "表达热图" });
    if (capabilities.has("gene_expression")) options.push({ type: "gene_expression", label: "单基因表达" });
    if (!hasSelector) options.push({ type: "diff_analysis", label: "差异分析" });
    if (!hasPca) options.push({ type: "pca", label: "PCA" });
    return options;
  }
  if (node.id.startsWith("diff_analysis__")) {
    return [
      { type: "heatmap", label: "热图" },
      { type: "volcano", label: "火山图" },
      { type: "diff_export", label: "结果导出" },
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
  if (output.type === "qc_report" && meta.sample_count) {
    return `${meta.sample_count} 样本 QC`;
  }
  if (output.type === "sample_correlation_plot" && meta.sample_count) {
    return `${meta.sample_count} 样本相关性`;
  }
  if (output.type === "expression_heatmap_plot" && meta.gene_count) {
    return `${meta.gene_count} 基因热图`;
  }
  if (output.type === "gene_expression_plot" && meta.gene) {
    return meta.gene;
  }
  if (output.type === "diff_export" && meta.row_count) {
    return `${meta.row_count} 行结果`;
  }
  return output.type;
}

function formatBytes(size) {
  const bytes = Number(size) || 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
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
  if (node.id.startsWith("gene_expression__")) {
    const geneNodes = nodes.filter((item) => item.id.startsWith("gene_expression__"));
    const geneIndex = Math.max(0, geneNodes.findIndex((item) => item.id === node.id));
    return { x: 640, y: 690 + geneIndex * 150 };
  }
  const downstreamPrefix = ["heatmap__", "volcano__", "enrichment__", "diff_export__"].find((prefix) => node.id.startsWith(prefix));
  if (downstreamPrefix) {
    const diffId = node.depends_on?.[0];
    const branchIndex = Math.max(0, diffBranches.findIndex((item) => item.id === diffId));
    const offset = node.id.startsWith("heatmap__") ? -90 : node.id.startsWith("volcano__") ? 10 : node.id.startsWith("diff_export__") ? 110 : 210;
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
