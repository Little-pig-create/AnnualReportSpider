import type { ApiResult } from "@/services/types";
import { BridgeError, normalizeBridgeError } from "@/services/errors";

const REQUIRED_METHODS = [
  "get_settings",
  "update_settings",
  "get_runtime",
  "get_pending_events",
  "create_run",
  "get_run",
  "cancel_run",
  "pause_run",
  "resume_run",
  "get_run_stages",
  "get_run_logs",
  "open_path",
  "select_directory",
  "get_about",
  "get_incremental_status",
  "get_visualization_index",
  "get_run_history",
  "export_run_history",
  "confirm_close_window",
  "cancel_close_window_request",
] as const;

function hasRequiredMethods(candidate: Record<string, any> | undefined): boolean {
  if (!candidate) return false;
  return REQUIRED_METHODS.every((method) => typeof candidate[method] === "function");
}

function currentApi() {
  return window.pywebview?.api as Record<string, any> | undefined;
}

let readyPromise: Promise<void> | null = null;

function resetReadyPromise() {
  readyPromise = null;
}

function createReadyPromise(timeoutMs: number, intervalMs: number) {
  return new Promise<void>((resolve, reject) => {
    const startedAt = Date.now();
    let settled = false;
    let timerId: number | null = null;

    const finish = (error?: Error) => {
      if (settled) return;
      settled = true;
      window.removeEventListener("pywebviewready", onReady);
      if (timerId !== null) {
        window.clearInterval(timerId);
      }
      if (error) {
        resetReadyPromise();
        reject(error);
        return;
      }
      resolve();
    };

    const checkReady = () => {
      if (hasRequiredMethods(currentApi())) {
        finish();
        return true;
      }
      if (Date.now() - startedAt >= timeoutMs) {
        finish(new BridgeError("BRIDGE_NOT_READY"));
        return true;
      }
      return false;
    };

    const onReady = () => {
      window.setTimeout(() => {
        checkReady();
      }, 0);
    };

    window.addEventListener("pywebviewready", onReady, { once: false });

    if (checkReady()) {
      return;
    }

    timerId = window.setInterval(checkReady, intervalMs);
  });
}

async function waitForApi(timeoutMs = 15000, intervalMs = 100): Promise<void> {
  if (hasRequiredMethods(currentApi())) {
    return;
  }
  if (!readyPromise) {
    readyPromise = createReadyPromise(timeoutMs, intervalMs);
  }
  await readyPromise;
}

async function api() {
  await waitForApi();
  const bridge = currentApi();
  if (!bridge || !hasRequiredMethods(bridge)) {
    resetReadyPromise();
    throw new BridgeError("BRIDGE_NOT_READY");
  }
  return bridge;
}

async function call<T>(method: string, ...args: any[]): Promise<T> {
  try {
    const result = await (await api())[method](...args);
    const payload = result as ApiResult<T>;
    if (!payload.ok) {
      throw new BridgeError(payload.error?.code || "BRIDGE_CALL_FAILED", payload.error?.message);
    }
    return payload.data as T;
  } catch (error) {
    throw normalizeBridgeError(error, "BRIDGE_CALL_EXCEPTION", "桥接调用失败");
  }
}

export const bridge = {
  waitUntilReady: async (timeoutMs = 15000, intervalMs = 100) => {
    await waitForApi(timeoutMs, intervalMs);
  },
  getSettings: () => call("get_settings"),
  updateSettings: (payload: unknown) => call("update_settings", payload),
  getRuntime: () => call("get_runtime"),
  getPendingEvents: (limit = 200) => call<{ items: any[] }>("get_pending_events", { limit }),
  createRun: (payload: unknown) => call("create_run", payload),
  getRun: (runId: string) => call("get_run", runId),
  cancelRun: (runId: string) => call("cancel_run", runId),
  pauseRun: (runId: string) => call("pause_run", runId),
  resumeRun: (runId: string) => call("resume_run", runId),
  getRunStages: (runId: string) => call("get_run_stages", runId),
  getRunLogs: (runId: string) => call("get_run_logs", runId),
  openPath: (path: string) => call("open_path", { path }),
  selectDirectory: (path: string) => call<{ path: string }>("select_directory", { path }),
  getAbout: () => call("get_about"),
  getIncrementalStatus: (payload?: unknown) => call("get_incremental_status", payload || {}),
  getVisualizationIndex: (payload?: unknown) => call("get_visualization_index", payload || {}),
  getRunHistory: () => call<{ items: any[] }>("get_run_history"),
  exportRunHistory: () => call<{ path: string; count: number }>("export_run_history"),
  confirmCloseWindow: () => call("confirm_close_window"),
  cancelCloseWindowRequest: () => call("cancel_close_window_request"),
};
