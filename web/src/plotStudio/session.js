export function normalizePlotStudioSource(source) {
  if (!source) return null;
  return {
    sourceKind: source.sourceKind || source.source_kind || "analysis_output",
    taskId: source.taskId || source.task_id || "",
    taskName: source.taskName || source.task_name || "",
    nodeId: source.nodeId || source.node_id || source.id || "",
    name: source.name || "Untitled output",
    status: source.status || "",
    type: source.type || "",
    summary: source.summary || source.type || "",
    dataPath: source.dataPath || source.data_path || "",
    previewUrl: source.previewUrl || source.preview_url || "",
    htmlUrl: source.htmlUrl || source.html_url || "",
    meta: source.meta || {},
  };
}

export function plotStudioSourceKey(source) {
  if (!source) return "empty";
  return [source.taskId, source.nodeId, source.type, source.dataPath].join("::");
}

export function createPlotStudioSession(overrides = {}) {
  const source = normalizePlotStudioSource(overrides.source);
  const returnTarget = normalizePlotStudioSource(overrides.returnTarget);
  return {
    mode: source ? "analysis_result" : "scratch",
    source,
    returnTarget,
    selectedPlotId: "",
    params: {},
    editHistory: [],
    ...overrides,
    source,
    returnTarget,
  };
}

export function createPlotStudioSessionFromSource(source, overrides = {}) {
  const normalizedSource = normalizePlotStudioSource(source);
  return createPlotStudioSession({
    mode: normalizedSource ? "analysis_result" : "scratch",
    source: normalizedSource,
    ...overrides,
  });
}

export function updatePlotStudioSessionSource(session, source) {
  const normalizedSource = normalizePlotStudioSource(source);
  return {
    ...(session || createPlotStudioSession()),
    mode: normalizedSource ? "analysis_result" : "scratch",
    source: normalizedSource,
    selectedPlotId: "",
    params: {},
    editHistory: [],
  };
}
