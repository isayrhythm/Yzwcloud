const defaultPositions = {
  upload_expression: { x: 80, y: 210 },
  qc__expression: { x: 360, y: 210 },
  pca__expression: { x: 640, y: 70 },
  correlation__expression: { x: 640, y: 210 },
  diff_analysis: { x: 640, y: 390 },
  expression_heatmap__expression: { x: 640, y: 530 },
};

const FLOW_NODE_BOX = { width: 224, height: 150 };
const FLOW_NODE_STEP = { x: 300, y: 170 };

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
  const maxX = Math.max(bounds.left, bounds.right);
  const maxY = Math.max(bounds.top, bounds.bottom);
  const candidates = [];
  for (let row = 0; row < 8; row += 1) {
    for (let col = 0; col < 5; col += 1) {
      candidates.push({ x: desired.x + col * FLOW_NODE_STEP.x, y: desired.y + row * FLOW_NODE_STEP.y });
      if (col > 0) {
        candidates.push({ x: desired.x - col * FLOW_NODE_STEP.x, y: desired.y + row * FLOW_NODE_STEP.y });
      }
    }
  }

  for (const candidate of candidates) {
    const position = {
      x: clampNumber(candidate.x, bounds.left, maxX),
      y: clampNumber(candidate.y, bounds.top, maxY),
    };
    if (!occupiedRects.some((rect) => rectsOverlap(nodeRect(position), rect))) {
      return position;
    }
  }

  return {
    x: clampNumber(desired.x, bounds.left, maxX),
    y: clampNumber(desired.y + occupiedRects.length * 18, bounds.top, maxY),
  };
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
