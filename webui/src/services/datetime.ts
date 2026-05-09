function pad(value: number) {
  return String(value).padStart(2, "0");
}

export function formatDateTime(value?: string | null, fallback = "-") {
  if (!value) return fallback;

  const normalized = String(value).trim();
  if (!normalized) return fallback;

  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) {
    return normalized;
  }

  const year = date.getFullYear();
  const month = pad(date.getMonth() + 1);
  const day = pad(date.getDate());
  const hour = pad(date.getHours());
  const minute = pad(date.getMinutes());
  const second = pad(date.getSeconds());
  return `${year}年${month}月${day}日 ${hour}时${minute}分${second}秒`;
}

export function formatDuration(start?: string | null, end?: string | null, fallback = "-") {
  if (!start || !end) return fallback;

  const startedAt = new Date(String(start).trim());
  const finishedAt = new Date(String(end).trim());
  if (Number.isNaN(startedAt.getTime()) || Number.isNaN(finishedAt.getTime())) {
    return fallback;
  }

  const diffMs = Math.max(0, finishedAt.getTime() - startedAt.getTime());
  const totalSeconds = Math.floor(diffMs / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}小时${minutes}分${seconds}秒`;
  }
  if (minutes > 0) {
    return `${minutes}分${seconds}秒`;
  }
  return `${seconds}秒`;
}
