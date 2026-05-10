const ERROR_MESSAGE_MAP: Record<string, string> = {
  BRIDGE_NOT_READY: "pywebview 桥接尚未就绪",
  BRIDGE_CALL_FAILED: "桥接调用失败",
  BRIDGE_CALL_EXCEPTION: "桥接调用异常",
  SETTINGS_VALIDATION_FAILED: "配置校验失败",
  RUN_ALREADY_ACTIVE: "已有任务正在运行",
  INVALID_MODE: "任务模式不合法",
  RUN_NOT_FOUND: "任务不存在",
  RUN_NOT_PAUSABLE: "当前任务不可暂停",
  RUN_NOT_RESUMABLE: "当前任务不可继续",
  RUN_NOT_CANCELLABLE: "当前任务不可终止",
  INVALID_PAYLOAD: "请求参数不合法",
  INTERNAL_ERROR: "内部错误",
  INCREMENTAL_STATUS_FAILED: "增量状态读取失败",
  VISUALIZATION_INDEX_FAILED: "可视化索引读取失败",
};

export class BridgeError extends Error {
  code: string;

  constructor(code: string, message?: string) {
    const mapped = ERROR_MESSAGE_MAP[code];
    const finalMessage = message?.trim() || mapped || "操作失败";
    super(finalMessage);
    this.name = "BridgeError";
    this.code = code;
  }
}

export function isBridgeError(error: unknown): error is BridgeError {
  return error instanceof BridgeError;
}

export function normalizeBridgeError(
  error: unknown,
  fallbackCode: string,
  fallbackMessage: string,
): BridgeError {
  if (isBridgeError(error)) {
    return error;
  }

  if (error instanceof Error) {
    return new BridgeError(fallbackCode, error.message || fallbackMessage);
  }

  return new BridgeError(fallbackCode, fallbackMessage);
}

export function getErrorMessage(error: unknown, fallbackMessage: string): string {
  const normalized = normalizeBridgeError(error, "BRIDGE_CALL_EXCEPTION", fallbackMessage);
  return normalized.message || fallbackMessage;
}

