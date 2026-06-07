export function formatBytes(size) {
  const bytes = Number(size) || 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function outputUrl(taskId, path) {
  const filename = String(path).split(/[\\/]/).pop();
  const route = `/api/tasks/${taskId}/outputs/${encodeURIComponent(filename)}`;
  const apiBase = import.meta.env.VITE_YZWCLOUD_API_BASE || "";
  return `${apiBase}${route}`;
}
