import { Graph, layout as dagreLayout } from "@dagrejs/dagre";

const defaultPositions = {
  upload_expression: { x: 80, y: 210 },
  qc__expression: { x: 360, y: 210 },
  pca__expression: { x: 640, y: 70 },
  correlation__expression: { x: 640, y: 210 },
  diff_analysis: { x: 640, y: 390 },
  expression_heatmap__expression: { x: 640, y: 530 },
};

const FLOW_NODE_BOX = { width: 224, height: 150 };
const FLOW_NODE_STEP = { x: 500, y: 340 };

export function visibleGraphNodes(nodes, edges) {
  return nodes.filter((node) => {
    if (node.status === "pending" || node.status === "blocked") return false;
    if (node.id === "diff_analysis") {
      return edges.some((edge) => edge.target === "diff_analysis");
    }
    return true;
  });
}

export function collectOccupiedNodeRects(taskId, flowNodes, graphNodes, excludeIds = new Set()) {
  return graphNodes
    .map((node, index) => {
      if (excludeIds.has(node.id)) return null;
      const flowNode = flowNodes.find((item) => item.id === node.id);
      const position =
        flowNode?.position ||
        (taskId ? readNodePosition(taskId, node.id) : null) ||
        fallbackPosition(node, index, graphNodes);
      return nodeRect(position);
    })
    .filter(Boolean);
}

export function findOpenNodePosition(desired, occupiedRects, bounds) {
  const viewportBounds = normalizeBounds(bounds);
  const expandedBounds = expandBounds(viewportBounds, FLOW_NODE_STEP.x * 2, FLOW_NODE_STEP.y * 3);
  const candidates = nodePositionCandidates(desired);
  return (
    firstOpenCandidate(candidates, occupiedRects, viewportBounds) ||
    firstOpenCandidate(candidates, occupiedRects, expandedBounds) ||
    leastCrowdedCandidate(candidates, occupiedRects, expandedBounds)
  );
}

export function arrangeGraphNodePositions(graphNodes, graphEdges, options = {}) {
  try {
    return arrangeGraphNodePositionsWithDagre(graphNodes, graphEdges, options);
  } catch (error) {
    console.warn("Dagre workflow layout failed, falling back to local layout.", error);
    return arrangeGraphNodePositionsWithLocalLayers(graphNodes, graphEdges, options);
  }
}

function arrangeGraphNodePositionsWithDagre(graphNodes, graphEdges, options = {}) {
  const currentPositions = options.currentPositions || new Map();
  const origin = options.origin || { x: 80, y: 80 };
  const ids = new Set(graphNodes.map((node) => node.id));
  const visibleEdges = graphEdges.filter((edge) => ids.has(edge.source) && ids.has(edge.target));
  const graph = new Graph({ multigraph: true });
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: "LR",
    ranker: "network-simplex",
    acyclicer: "greedy",
    nodesep: 190,
    ranksep: 270,
    edgesep: 120,
    marginx: 0,
    marginy: 0,
  });

  [...graphNodes]
    .sort((a, b) => nodeSortValue(a, currentPositions, graphNodes) - nodeSortValue(b, currentPositions, graphNodes))
    .forEach((node) => {
      graph.setNode(node.id, { width: FLOW_NODE_BOX.width, height: FLOW_NODE_BOX.height });
    });
  visibleEdges.forEach((edge, index) => {
    graph.setEdge(edge.source, edge.target, {}, `${edge.source}->${edge.target}:${index}`);
  });

  dagreLayout(graph);

  const arranged = {};
  const nodesWithLayout = graphNodes
    .map((node) => ({ node, layout: graph.node(node.id) }))
    .filter((item) => item.layout);
  const minX = Math.min(...nodesWithLayout.map((item) => item.layout.x - FLOW_NODE_BOX.width / 2));
  const minY = Math.min(...nodesWithLayout.map((item) => item.layout.y - FLOW_NODE_BOX.height / 2));

  nodesWithLayout.forEach(({ node, layout }) => {
    arranged[node.id] = {
      x: origin.x + layout.x - FLOW_NODE_BOX.width / 2 - minX,
      y: origin.y + layout.y - FLOW_NODE_BOX.height / 2 - minY,
    };
  });

  return arranged;
}

function arrangeGraphNodePositionsWithLocalLayers(graphNodes, graphEdges, options = {}) {
  const currentPositions = options.currentPositions || new Map();
  const origin = options.origin || { x: 80, y: 80 };
  const levels = graphNodeLevels(graphNodes, graphEdges);
  const maxLevel = Math.max(0, ...Array.from(levels.values()));
  const arranged = {};

  const orderedLevels = orderedGraphLevels(graphNodes, graphEdges, levels, currentPositions);

  for (let level = 0; level <= maxLevel; level += 1) {
    const levelNodes = orderedLevels.get(level) || [];

    levelNodes.forEach((node, index) => {
      arranged[node.id] = {
        x: origin.x + level * FLOW_NODE_STEP.x,
        y: origin.y + index * FLOW_NODE_STEP.y,
      };
    });
  }

  return arranged;
}

function graphNodeLevels(graphNodes, graphEdges) {
  const ids = new Set(graphNodes.map((node) => node.id));
  const levels = new Map(graphNodes.map((node) => [node.id, 0]));
  const visibleEdges = graphEdges.filter((edge) => ids.has(edge.source) && ids.has(edge.target));

  for (let pass = 0; pass < graphNodes.length; pass += 1) {
    let changed = false;
    visibleEdges.forEach((edge) => {
      const sourceLevel = levels.get(edge.source) || 0;
      const targetLevel = levels.get(edge.target) || 0;
      if (targetLevel <= sourceLevel) {
        levels.set(edge.target, sourceLevel + 1);
        changed = true;
      }
    });
    if (!changed) break;
  }

  return levels;
}

function orderedGraphLevels(graphNodes, graphEdges, levels, currentPositions) {
  const ids = new Set(graphNodes.map((node) => node.id));
  const visibleEdges = graphEdges.filter((edge) => ids.has(edge.source) && ids.has(edge.target));
  const maxLevel = Math.max(0, ...Array.from(levels.values()));
  const treeSpans = graphSubtreeSpans(graphNodes, visibleEdges, levels, currentPositions);
  const layers = new Map();

  for (let level = 0; level <= maxLevel; level += 1) {
    layers.set(
      level,
      graphNodes
        .filter((node) => levels.get(node.id) === level)
        .sort((a, b) => {
          const aCenter = subtreeCenter(treeSpans.get(a.id));
          const bCenter = subtreeCenter(treeSpans.get(b.id));
          if (aCenter !== bCenter) return aCenter - bCenter;
          return nodeSortValue(a, currentPositions, graphNodes) - nodeSortValue(b, currentPositions, graphNodes);
        }),
    );
  }

  for (let pass = 0; pass < 3; pass += 1) {
    for (let level = 1; level <= maxLevel; level += 1) {
      sortLayerByNeighborBarycenter(layers, level, visibleEdges, "source", "target", currentPositions, graphNodes);
    }
    for (let level = maxLevel - 1; level >= 0; level -= 1) {
      sortLayerByNeighborBarycenter(layers, level, visibleEdges, "target", "source", currentPositions, graphNodes);
    }
  }
  minimizeLayerCrossings(layers, visibleEdges);

  return layers;
}

function graphSubtreeSpans(graphNodes, edges, levels, currentPositions) {
  const byId = new Map(graphNodes.map((node) => [node.id, node]));
  const childMap = new Map(graphNodes.map((node) => [node.id, []]));
  const incoming = new Map(graphNodes.map((node) => [node.id, 0]));
  edges.forEach((edge) => {
    if ((levels.get(edge.target) || 0) <= (levels.get(edge.source) || 0)) return;
    childMap.get(edge.source)?.push(edge.target);
    incoming.set(edge.target, (incoming.get(edge.target) || 0) + 1);
  });
  childMap.forEach((children) => {
    children.sort((a, b) => nodeSortValue(byId.get(a), currentPositions, graphNodes) - nodeSortValue(byId.get(b), currentPositions, graphNodes));
  });

  const spans = new Map();
  let cursor = 0;
  const roots = graphNodes
    .filter((node) => (incoming.get(node.id) || 0) === 0)
    .sort((a, b) => nodeSortValue(a, currentPositions, graphNodes) - nodeSortValue(b, currentPositions, graphNodes));

  const walk = (nodeId, stack = new Set()) => {
    if (spans.has(nodeId)) return spans.get(nodeId);
    if (stack.has(nodeId)) {
      const cycleSpan = { start: cursor, end: cursor };
      cursor += 1;
      spans.set(nodeId, cycleSpan);
      return cycleSpan;
    }
    const nextStack = new Set(stack);
    nextStack.add(nodeId);
    const children = childMap.get(nodeId) || [];
    if (!children.length) {
      const leafSpan = { start: cursor, end: cursor };
      cursor += 1;
      spans.set(nodeId, leafSpan);
      return leafSpan;
    }
    const childSpans = children.map((childId) => walk(childId, nextStack));
    const span = {
      start: Math.min(...childSpans.map((item) => item.start)),
      end: Math.max(...childSpans.map((item) => item.end)),
    };
    spans.set(nodeId, span);
    return span;
  };

  roots.forEach((node) => walk(node.id));
  graphNodes.forEach((node) => {
    if (!spans.has(node.id)) walk(node.id);
  });
  return spans;
}

function subtreeCenter(span) {
  if (!span) return Number.POSITIVE_INFINITY;
  return (span.start + span.end) / 2;
}

function sortLayerByNeighborBarycenter(layers, level, edges, neighborKey, nodeKey, currentPositions, graphNodes) {
  const layer = layers.get(level) || [];
  const layerIds = new Set(layer.map((node) => node.id));
  const order = layerOrderMap(layers);
  layers.set(
    level,
    [...layer].sort((a, b) => {
      const aScore = neighborBarycenter(a.id, layerIds, edges, order, neighborKey, nodeKey);
      const bScore = neighborBarycenter(b.id, layerIds, edges, order, neighborKey, nodeKey);
      if (aScore !== bScore) return aScore - bScore;
      return nodeSortValue(a, currentPositions, graphNodes) - nodeSortValue(b, currentPositions, graphNodes);
    }),
  );
}

function minimizeLayerCrossings(layers, edges) {
  for (let pass = 0; pass < 8; pass += 1) {
    let improved = false;
    layers.forEach((layer, level) => {
      for (let index = 0; index < layer.length - 1; index += 1) {
        const before = countLayerEdgeCrossings(layers, edges);
        const swapped = [...layer];
        [swapped[index], swapped[index + 1]] = [swapped[index + 1], swapped[index]];
        layers.set(level, swapped);
        const after = countLayerEdgeCrossings(layers, edges);
        if (after < before) {
          improved = true;
          layer = swapped;
        } else {
          layers.set(level, layer);
        }
      }
    });
    if (!improved || countLayerEdgeCrossings(layers, edges) === 0) break;
  }
}

function layerOrderMap(layers) {
  const order = new Map();
  layers.forEach((layer) => {
    layer.forEach((node, index) => order.set(node.id, index));
  });
  return order;
}

function countLayerEdgeCrossings(layers, edges) {
  const order = layerOrderMap(layers);
  let crossings = 0;
  for (let left = 0; left < edges.length; left += 1) {
    for (let right = left + 1; right < edges.length; right += 1) {
      if (edges[left].source === edges[right].source || edges[left].target === edges[right].target) continue;
      const leftSourceOrder = order.get(edges[left].source);
      const rightSourceOrder = order.get(edges[right].source);
      const leftTargetOrder = order.get(edges[left].target);
      const rightTargetOrder = order.get(edges[right].target);
      if (
        [leftSourceOrder, rightSourceOrder, leftTargetOrder, rightTargetOrder].every((value) => Number.isFinite(value)) &&
        (leftSourceOrder - rightSourceOrder) * (leftTargetOrder - rightTargetOrder) < 0
      ) {
        crossings += 1;
      }
    }
  }
  return crossings;
}

function neighborBarycenter(nodeId, layerIds, edges, order, neighborKey, nodeKey) {
  const neighbors = edges
    .filter((edge) => edge[nodeKey] === nodeId && !layerIds.has(edge[neighborKey]))
    .map((edge) => order.get(edge[neighborKey]))
    .filter((value) => Number.isFinite(value));
  if (!neighbors.length) return Number.POSITIVE_INFINITY;
  return neighbors.reduce((sum, value) => sum + value, 0) / neighbors.length;
}

function nodeSortValue(node, currentPositions, graphNodes) {
  const currentPosition = currentPositions.get(node.id);
  if (currentPosition) return currentPosition.y;
  return fallbackPosition(node, Math.max(0, graphNodes.findIndex((item) => item.id === node.id)), graphNodes).y;
}

export function nodePositionCandidates(desired) {
  const rowOffsets = [0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6];
  const colOffsets = [0, 1, -1, 2, -2, 3, -3];
  const seen = new Set();
  const candidates = [];
  rowOffsets.forEach((row) => {
    colOffsets.forEach((col) => {
      const position = {
        x: desired.x + col * FLOW_NODE_STEP.x,
        y: desired.y + row * FLOW_NODE_STEP.y,
      };
      const key = `${position.x}:${position.y}`;
      if (!seen.has(key)) {
        seen.add(key);
        candidates.push(position);
      }
    });
  });
  return candidates;
}

function firstOpenCandidate(candidates, occupiedRects, bounds) {
  const seen = new Set();
  for (const candidate of candidates) {
    const position = clampPositionToBounds(candidate, bounds);
    const key = `${position.x}:${position.y}`;
    if (seen.has(key)) continue;
    seen.add(key);
    if (!occupiedRects.some((rect) => rectsOverlap(nodeRect(position), rect))) {
      return position;
    }
  }
  return null;
}

function leastCrowdedCandidate(candidates, occupiedRects, bounds) {
  return candidates
    .map((candidate) => clampPositionToBounds(candidate, bounds))
    .reduce((best, position) => {
      const score = occupiedRects.reduce((total, rect) => total + rectOverlapArea(nodeRect(position), rect), 0);
      const distance = Math.abs(position.x - candidates[0].x) + Math.abs(position.y - candidates[0].y);
      if (!best || score < best.score || (score === best.score && distance < best.distance)) {
        return { position, score, distance };
      }
      return best;
    }, null)?.position;
}

function normalizeBounds(bounds) {
  return {
    left: Math.min(bounds.left, bounds.right),
    top: Math.min(bounds.top, bounds.bottom),
    right: Math.max(bounds.left, bounds.right),
    bottom: Math.max(bounds.top, bounds.bottom),
  };
}

function expandBounds(bounds, xPadding, yPadding) {
  return {
    left: bounds.left - xPadding,
    top: bounds.top - yPadding,
    right: bounds.right + xPadding,
    bottom: bounds.bottom + yPadding,
  };
}

function clampPositionToBounds(position, bounds) {
  return {
    x: clampNumber(position.x, bounds.left, bounds.right),
    y: clampNumber(position.y, bounds.top, bounds.bottom),
  };
}

function rectOverlapArea(a, b) {
  const width = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
  const height = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  return width * height;
}

export function nodeRect(position) {
  return {
    left: position.x - 12,
    top: position.y - 12,
    right: position.x + FLOW_NODE_BOX.width + 12,
    bottom: position.y + FLOW_NODE_BOX.height + 12,
  };
}

export function rectsOverlap(a, b) {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
}

export function fallbackPosition(node, index, nodes) {
  if (defaultPositions[node.id]) return defaultPositions[node.id];
  const diffBranches = nodes.filter((item) => item.id.startsWith("diff_analysis__"));
  if (node.id.startsWith("diff_analysis__")) {
    const branchIndex = Math.max(0, diffBranches.findIndex((item) => item.id === node.id));
    return { x: 920, y: 120 + branchIndex * 190 };
  }
  if (node.id.startsWith("pca__")) {
    return { x: 640, y: 70 };
  }
  if (node.id.startsWith("correlation__")) {
    return { x: 640, y: 210 };
  }
  if (node.id.startsWith("expression_heatmap__")) {
    return { x: 640, y: 530 };
  }
  if (node.id.startsWith("gene_expression__")) {
    const geneNodes = nodes.filter((item) => item.id.startsWith("gene_expression__"));
    const geneIndex = Math.max(0, geneNodes.findIndex((item) => item.id === node.id));
    return { x: 640, y: 690 + geneIndex * 150 };
  }
  if (node.id.startsWith("wgcna__")) {
    return { x: 920, y: 690 };
  }
  if (node.id.startsWith("metabolomics_normalization__")) {
    return { x: 920, y: 210 };
  }
  if (node.id.startsWith("metabolomics_ml_modeling__")) {
    const sourceId = node.depends_on?.[0];
    const sourceNode = nodes.find((item) => item.id === sourceId);
    const base = sourceNode ? fallbackPositionForNode(sourceNode, nodes) : { x: 920, y: 210 };
    return { x: base.x + 280, y: base.y + 170 };
  }
  if (node.id.startsWith("metabolomics_ml__")) {
    const sourceId = node.depends_on?.[0];
    const sourceNode = nodes.find((item) => item.id === sourceId);
    const base = sourceNode ? fallbackPositionForNode(sourceNode, nodes) : { x: 1200, y: 380 };
    const mlNodes = nodes.filter((item) => item.depends_on?.[0] === sourceId && item.id.startsWith("metabolomics_ml__"));
    const mlIndex = Math.max(0, mlNodes.findIndex((item) => item.id === node.id));
    return { x: base.x + 280, y: base.y - 170 + mlIndex * 170 };
  }
  if (node.id.startsWith("metabolomics_explain__")) {
    const sourceId = node.depends_on?.[0];
    const sourceNode = nodes.find((item) => item.id === sourceId);
    const base = sourceNode ? fallbackPositionForNode(sourceNode, nodes) : { x: 920, y: 520 };
    const explainNodes = nodes.filter((item) => item.depends_on?.[0] === sourceId && item.id.startsWith("metabolomics_explain__"));
    const explainIndex = Math.max(0, explainNodes.findIndex((item) => item.id === node.id));
    return { x: base.x + 260, y: base.y + explainIndex * 150 };
  }
  const downstreamPrefix = ["heatmap__", "volcano__", "enrichment__", "diff_export__"].find((prefix) =>
    node.id.startsWith(prefix),
  );
  if (downstreamPrefix) {
    const diffId = node.depends_on?.[0];
    const branchIndex = Math.max(0, diffBranches.findIndex((item) => item.id === diffId));
    const offset = node.id.startsWith("heatmap__")
      ? -90
      : node.id.startsWith("volcano__")
        ? 10
        : node.id.startsWith("diff_export__")
          ? 110
          : 210;
    return { x: 1200, y: 120 + branchIndex * 190 + offset };
  }
  return { x: 100 + (index % 4) * 280, y: 120 + Math.floor(index / 4) * 180 };
}

function fallbackPositionForNode(node, nodes) {
  const index = Math.max(0, nodes.findIndex((item) => item.id === node.id));
  return fallbackPosition(node, index, nodes);
}

export function clampNumber(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function positionKey(taskId) {
  return `yzwcloud.reactflow.positions.${taskId}`;
}

export function readNodePosition(taskId, nodeId) {
  try {
    return JSON.parse(localStorage.getItem(positionKey(taskId)) || "{}")[nodeId] || null;
  } catch {
    return null;
  }
}

export function saveNodePosition(taskId, nodeId, position) {
  const positions = JSON.parse(localStorage.getItem(positionKey(taskId)) || "{}");
  positions[nodeId] = position;
  localStorage.setItem(positionKey(taskId), JSON.stringify(positions));
}

export function removeStoredNodePosition(taskId, nodeId) {
  const positions = JSON.parse(localStorage.getItem(positionKey(taskId)) || "{}");
  delete positions[nodeId];
  localStorage.setItem(positionKey(taskId), JSON.stringify(positions));
}
