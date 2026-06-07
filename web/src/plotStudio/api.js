export async function fetchPlotStudioJson(path, options = {}) {
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
  return response.json();
}

export function resolvePlotStudioSource(source, options = {}) {
  return fetchPlotStudioJson("/api/plot-studio/source/resolve", {
    method: "POST",
    body: JSON.stringify({ source }),
    ...options,
  });
}

export function createPlotStudioReport({ source, plotType, params }, options = {}) {
  return fetchPlotStudioJson("/api/plot-studio/report", {
    method: "POST",
    body: JSON.stringify({ source, plotType, params }),
    ...options,
  });
}

export function createPlotStudioSpec({ source, plotType, params }, options = {}) {
  return fetchPlotStudioJson("/api/plot-studio/spec", {
    method: "POST",
    body: JSON.stringify({ source, plotType, params }),
    ...options,
  });
}

export function createPlotStudioAgentEdit(payload) {
  return fetchPlotStudioJson("/api/plot-studio/agent-edit", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function loadPlotStudioExample(plotId) {
  return fetchPlotStudioJson(`/api/plot-studio/examples/${encodeURIComponent(plotId)}`);
}

export function loadDefaultPlotStudioExample() {
  return fetchPlotStudioJson("/api/plot-studio/examples/default");
}
