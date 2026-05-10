import { defineStore } from "pinia";
import { bridge } from "@/services/bridge";
import type {
  IncrementalStatus,
  LogItem,
  NotificationPrefs,
  RunMode,
  RunState,
  StageName,
  StageState,
  VisualizationIndexSnapshot,
} from "@/services/types";

const RUN_POLL_INTERVAL_MS = 600;
const NOTIFICATION_PREFS_KEY = "report_spider_notification_prefs_v1";

function modeText(mode: RunMode | null) {
  return {
    links: "公告链接抓取",
    pdf: "PDF 下载",
    extract: "文本提取",
    pipeline: "完整流程",
    null: "任务",
  }[String(mode)];
}

function notificationPermissionValue(): NotificationPermission | "unsupported" {
  if (typeof window === "undefined" || typeof Notification === "undefined") {
    return "unsupported";
  }
  return Notification.permission;
}

function createDefaultNotificationPrefs(): NotificationPrefs {
  return {
    desktopEnabled: false,
    soundEnabled: true,
    permission: notificationPermissionValue(),
  };
}

function emptyStage(name: StageName, title: string): StageState {
  return {
    name,
    title,
    status: "pending",
    progress: { current: 0, total: 0, percent: 0 },
    result: null,
    hint: "",
  };
}

function emptyRun(): RunState {
  return {
    runId: null,
    mode: null,
    status: "idle",
    currentStage: null,
    startedAt: null,
    finishedAt: null,
    summary: { links: null, pdf: null, extract: null },
    error: null,
    outputs: {},
  };
}

function makeStageMap(): Record<StageName, StageState> {
  return {
    links: emptyStage("links", "公告链接抓取"),
    pdf: emptyStage("pdf", "PDF 下载"),
    extract: emptyStage("extract", "文本提取"),
  };
}

function resetStageState(stage: StageState): StageState {
  return {
    ...stage,
    status: "pending",
    progress: { current: 0, total: 0, percent: 0 },
    result: null,
    hint: "",
  };
}

function isLiveStats(value: any) {
  return Boolean(value && typeof value === "object" && Array.isArray(value.yearBuckets));
}

function numberValue(value: any, fallback = 0) {
  const result = Number(value);
  return Number.isFinite(result) ? result : fallback;
}

export const useTaskStore = defineStore("task", {
  state: () => ({
    run: emptyRun(),
    stages: makeStageMap(),
    logs: [] as LogItem[],
    pollTimer: null as number | null,
    incrementalPollTimer: null as number | null,
    incremental: null as IncrementalStatus | null,
    incrementalLoading: false,
    visualizationIndex: null as VisualizationIndexSnapshot | null,
    notificationPrefs: createDefaultNotificationPrefs() as NotificationPrefs,
  }),
  getters: {
    isBusy: (state) => ["running", "paused", "cancelling"].includes(state.run.status),
    isPausable: (state) => state.run.status === "running",
    isResumable: (state) => state.run.status === "paused",
    currentTaskProgress: (state) => {
      if (!state.run.mode) return 0;
      if (state.run.status === "completed") {
        return 1;
      }
      if (state.run.mode !== "pipeline") {
        return Number(state.stages[state.run.mode].progress.percent || 0);
      }
      const currentStage = state.run.currentStage;
      if (!currentStage) return 0;
      return Number(state.stages[currentStage].progress.percent || 0);
    },
    liveCrawl: (state) => {
      const result = state.stages.links.result;
      if (result) {
        if (isLiveStats(result.live)) return result.live;
        if (isLiveStats(result)) return result;
      }
      return state.visualizationIndex?.links || null;
    },
    livePdf: (state) => {
      const result = state.stages.pdf.result;
      if (result && isLiveStats(result)) return result;
      return state.visualizationIndex?.pdf || null;
    },
    liveExtract: (state) => {
      const result = state.stages.extract.result;
      if (result && isLiveStats(result)) return result;
      return state.visualizationIndex?.extract || null;
    },
    liveYearBuckets(): any[] {
      return this.liveCrawl?.yearBuckets || [];
    },
    liveYearTotal(): number {
      return this.liveYearBuckets.reduce((sum: number, item: any) => sum + numberValue(item.count || item.total || 0), 0);
    },
    hasVisualizationData: (state) => {
      return Boolean(
        state.stages.links.result ||
        state.stages.pdf.result ||
        state.stages.extract.result ||
        state.visualizationIndex,
      );
    },
    scannedPdfBreakdown: (state) => {
      const result = state.stages.pdf.result || {};
      const total = numberValue(result.pdfTotal, numberValue(state.incremental?.pdf.targetTotal, 0));
      const downloaded = numberValue(result.downloaded, 0);
      const exists = numberValue(result.exists, 0);
      const skipped = numberValue(result.skipped, 0);
      const failed = numberValue(result.failed, 0);
      return {
        downloaded: downloaded + exists,
        exists: 0,
        failed,
        skipped,
        pending: Math.max(total - downloaded - exists - skipped, 0),
        total,
      };
    },
    scannedExtractBreakdown: (state) => {
      const result = state.stages.extract.result || {};
      const total = numberValue(result.pdfTotal, numberValue(state.incremental?.extract.pdfTotal, 0));
      const extracted = numberValue(result.extracted, 0);
      const exists = numberValue(result.exists, 0);
      const failed = numberValue(result.failed, 0);
      return {
        extracted: extracted + exists,
        exists: 0,
        failed,
        pending: Math.max(total - extracted - exists, 0),
        total,
      };
    },
    recentLogs: (state) => state.logs.slice(-80),
  },
  actions: {
    loadNotificationPrefs() {
      const fallback = createDefaultNotificationPrefs();
      try {
        const raw = window.localStorage.getItem(NOTIFICATION_PREFS_KEY);
        if (!raw) {
          this.notificationPrefs = fallback;
          return this.notificationPrefs;
        }
        const parsed = JSON.parse(raw || "{}");
        this.notificationPrefs = {
          desktopEnabled: Boolean(parsed?.desktopEnabled),
          soundEnabled: parsed?.soundEnabled === false ? false : true,
          permission: notificationPermissionValue(),
        };
      } catch {
        this.notificationPrefs = fallback;
      }
      return this.notificationPrefs;
    },
    saveNotificationPrefs() {
      window.localStorage.setItem(
        NOTIFICATION_PREFS_KEY,
        JSON.stringify({
          desktopEnabled: this.notificationPrefs.desktopEnabled,
          soundEnabled: this.notificationPrefs.soundEnabled,
        }),
      );
    },
    async requestDesktopNotificationPermission() {
      if (typeof Notification === "undefined") {
        this.notificationPrefs.permission = "unsupported";
        this.notificationPrefs.desktopEnabled = false;
        this.saveNotificationPrefs();
        return this.notificationPrefs.permission;
      }
      const result = await Notification.requestPermission();
      this.notificationPrefs.permission = result;
      if (result !== "granted") {
        this.notificationPrefs.desktopEnabled = false;
      }
      this.saveNotificationPrefs();
      return result;
    },
    async updateNotificationPrefs(payload: Partial<NotificationPrefs>) {
      if (payload.desktopEnabled === true) {
        const permission = await this.requestDesktopNotificationPermission();
        if (permission !== "granted") {
          this.notificationPrefs.desktopEnabled = false;
        } else {
          this.notificationPrefs.desktopEnabled = true;
        }
      }
      if (payload.desktopEnabled === false) {
        this.notificationPrefs.desktopEnabled = false;
      }
      if (typeof payload.soundEnabled === "boolean") {
        this.notificationPrefs.soundEnabled = payload.soundEnabled;
      }
      this.notificationPrefs.permission = notificationPermissionValue();
      this.saveNotificationPrefs();
      return this.notificationPrefs;
    },
    playCompletionSound() {
      if (!this.notificationPrefs.soundEnabled) return;
      const AudioCtx = (window as any).AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtx) return;
      try {
        const context = new AudioCtx();
        const makeTone = (freq: number, duration: number, delay: number) => {
          const oscillator = context.createOscillator();
          const gain = context.createGain();
          oscillator.type = "sine";
          oscillator.frequency.value = freq;
          gain.gain.setValueAtTime(0.0001, context.currentTime + delay);
          gain.gain.exponentialRampToValueAtTime(0.16, context.currentTime + delay + 0.01);
          gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + delay + duration);
          oscillator.connect(gain);
          gain.connect(context.destination);
          oscillator.start(context.currentTime + delay);
          oscillator.stop(context.currentTime + delay + duration + 0.02);
        };
        makeTone(880, 0.11, 0);
        makeTone(1047, 0.14, 0.14);
        window.setTimeout(() => {
          context.close().catch(() => {});
        }, 420);
      } catch {
        return;
      }
    },
    notifyRunFinished(status: "completed" | "failed" | "cancelled", message?: string) {
      const modeLabel = modeText(this.run.mode);
      const title = status === "completed"
        ? "任务完成"
        : status === "failed"
          ? "任务失败"
          : "任务已终止";
      const body = message || `${modeLabel} 已结束`;

      if (this.notificationPrefs.desktopEnabled && this.notificationPrefs.permission === "granted" && typeof Notification !== "undefined") {
        try {
          new Notification(title, { body });
        } catch {
          // ignore
        }
      }

      if (this.notificationPrefs.soundEnabled) {
        this.playCompletionSound();
      }
    },
    reset() {
      this.stopPolling();
      this.stopIncrementalPolling();
      this.run = emptyRun();
      this.stages = makeStageMap();
      this.logs = [];
      this.incremental = null;
    },
    resetRunOnly() {
      this.stopPolling();
      this.stopIncrementalPolling();
      this.run = emptyRun();
      this.logs = [];
    },
    prepareStagesForMode(mode: RunMode) {
      const resetMap: Record<RunMode, StageName[]> = {
        links: ["links", "pdf", "extract"],
        pdf: ["pdf", "extract"],
        extract: ["extract"],
        pipeline: ["links", "pdf", "extract"],
      };
      resetMap[mode].forEach((stageName) => {
        this.stages[stageName] = resetStageState(this.stages[stageName]);
        this.run.summary[stageName] = null;
      });
    },
    async loadVisualizationIndex(payload?: unknown) {
      this.visualizationIndex = await bridge.getVisualizationIndex(payload || {});
      return this.visualizationIndex;
    },
    async loadIncrementalStatus(payload?: unknown) {
      if (this.incrementalLoading) {
        return this.incremental;
      }
      this.incrementalLoading = true;
      try {
        this.incremental = await bridge.getIncrementalStatus(payload);
        return this.incremental;
      } finally {
        this.incrementalLoading = false;
      }
    },
    async hydrateActiveRun() {
      const runtime = await bridge.getRuntime();
      if (!runtime.activeRunId) {
        this.reset();
        await this.loadVisualizationIndex().catch(() => {});
        return;
      }
      const runId = runtime.activeRunId;
      const [run, stages, logs] = await Promise.all([
        bridge.getRun(runId),
        bridge.getRunStages(runId),
        bridge.getRunLogs(runId),
      ]);
      this.applyRunSnapshot(run);
      this.applyStageSnapshot(stages.items);
      this.logs = logs.items;
      if (["running", "paused", "cancelling"].includes(this.run.status)) {
        this.startPolling();
      }
    },
    async syncActiveRun() {
      if (!this.run.runId) {
        await this.loadVisualizationIndex().catch(() => {});
        return;
      }
      const [run, stages, logs] = await Promise.all([
        bridge.getRun(this.run.runId),
        bridge.getRunStages(this.run.runId),
        bridge.getRunLogs(this.run.runId),
      ]);
      this.applyRunSnapshot(run);
      this.applyStageSnapshot(stages.items);
      this.logs = logs.items;
      if (!["running", "paused", "cancelling"].includes(this.run.status)) {
        this.stopPolling();
        await this.loadVisualizationIndex().catch(() => {});
      }
    },
    startPolling() {
      if (this.pollTimer !== null) return;
      this.pollTimer = window.setInterval(() => {
        this.syncActiveRun().catch(() => {
          this.stopPolling();
        });
      }, RUN_POLL_INTERVAL_MS);
    },
    stopPolling() {
      if (this.pollTimer === null) return;
      window.clearInterval(this.pollTimer);
      this.pollTimer = null;
    },
    startIncrementalPolling() {
      return;
    },
    stopIncrementalPolling() {
      if (this.incrementalPollTimer === null) return;
      window.clearInterval(this.incrementalPollTimer);
      this.incrementalPollTimer = null;
    },
    applyRunSnapshot(payload: any) {
      this.run = {
        runId: payload.runId,
        mode: payload.mode,
        status: payload.status,
        currentStage: payload.currentStage,
        startedAt: payload.startedAt,
        finishedAt: payload.finishedAt,
        summary: payload.summary,
        error: payload.error ?? null,
        outputs: payload.outputs || {},
      };
    },
    applyStageSnapshot(items: any[]) {
      items.forEach((item) => {
        const stageName = item.name as StageName;
        const current = this.stages[stageName];
        this.stages[stageName] = {
          ...current,
          ...item,
          title: item.title || current.title,
          result: item.result ?? current.result,
          hint: item.hint || current.hint,
        };
      });
    },
    handleEvent(event: any) {
      const type = event.event;
      const data = event.data || {};

      if (type === "run.started") {
        const mode = data.mode as RunMode;
        this.resetRunOnly();
        this.prepareStagesForMode(mode);
        this.run.runId = event.runId;
        this.run.mode = mode;
        this.run.status = "running";
        this.run.startedAt = data.startedAt;
        if (mode && mode !== "pipeline") {
          const stage = mode as StageName;
          this.run.currentStage = stage;
          this.stages[stage].status = "running";
          this.stages[stage].hint = "准备中";
        }
        this.logs.push({
          time: data.startedAt || new Date().toISOString(),
          level: "INFO",
          stage: mode === "pipeline" ? "system" : (mode as StageName),
          message: mode === "pipeline" ? "任务创建中，正在初始化全流程资源" : "任务创建中，正在初始化执行资源",
        });
        this.startPolling();
        return;
      }

      if (type === "run.paused") {
        this.run.status = "paused";
        return;
      }

      if (type === "run.resumed") {
        this.run.status = "running";
        return;
      }

      if (type === "run.completed") {
        this.run.status = "completed";
        this.run.finishedAt = data.finishedAt;
        this.run.summary = data.summary;
        this.stopPolling();
        this.loadVisualizationIndex().catch(() => {});
        this.notifyRunFinished("completed", `${modeText(this.run.mode)} 已完成`);
        return;
      }

      if (type === "run.failed") {
        this.run.status = "failed";
        this.run.finishedAt = data.finishedAt;
        this.run.error = data.error;
        this.stopPolling();
        this.loadVisualizationIndex().catch(() => {});
        this.notifyRunFinished("failed", `${modeText(this.run.mode)} 失败：${data.error || "请查看日志"}`);
        return;
      }

      if (type === "run.cancelled") {
        this.run.status = "cancelled";
        this.run.finishedAt = data.finishedAt;
        this.stopPolling();
        this.loadVisualizationIndex().catch(() => {});
        this.notifyRunFinished("cancelled", `${modeText(this.run.mode)} 已终止`);
        return;
      }

      if (type === "stage.started") {
        const stage = data.stage as StageName;
        this.run.currentStage = stage;
        this.stages[stage].status = "running";
        this.stages[stage].title = data.title || this.stages[stage].title;
        this.stages[stage].hint = "执行中";
        return;
      }

      if (type === "stage.progress") {
        const stage = data.stage as StageName;
        const current = Number(data.current || 0);
        const total = Number(data.total || 0);
        this.stages[stage].progress = {
          current: total > 0 ? Math.min(current, total) : current,
          total,
          percent: Math.min(1, Math.max(0, Number(data.percent || 0))),
        };
        this.stages[stage].hint = data.message || "";
        if (Object.keys(data.stats || {}).length > 0) {
          this.stages[stage].result = {
            ...(this.stages[stage].result || {}),
            ...data.stats,
          };
        }
        return;
      }

      if (type === "stage.completed") {
        const stage = data.stage as StageName;
        const total = Number(this.stages[stage].progress.total || 0);
        const finalTotal = total > 0 ? total : 1;
        this.stages[stage].status = "completed";
        this.stages[stage].progress = {
          current: finalTotal,
          total: finalTotal,
          percent: 1,
        };
        this.stages[stage].result = data.result;
        this.stages[stage].hint = "已完成";
        this.run.summary[stage] = data.result;
        return;
      }

      if (type === "log.append") {
        this.logs.push({
          time: data.time,
          level: data.level,
          stage: data.stage,
          message: data.message,
        });
        if (this.logs.length > 1000) {
          this.logs.splice(0, this.logs.length - 1000);
        }
      }
    },
    async startRun(mode: RunMode) {
      const startedAt = new Date().toISOString();
      this.resetRunOnly();
      this.prepareStagesForMode(mode);
      this.run.mode = mode;
      this.run.status = "running";
      this.run.startedAt = startedAt;
      this.run.currentStage = mode === "pipeline" ? "links" : mode;
      if (mode === "pipeline") {
        this.stages.links.status = "running";
        this.stages.links.hint = "准备中";
      } else {
        this.stages[mode].status = "running";
        this.stages[mode].hint = "准备中";
      }
      this.logs.push({
        time: startedAt,
        level: "INFO",
        stage: mode === "pipeline" ? "system" : mode,
        message: mode === "pipeline" ? "任务创建中，正在初始化全流程资源" : "任务创建中，正在初始化执行资源",
      });
      try {
        const payload = await bridge.createRun({ mode });
        this.applyRunSnapshot(payload);
        this.syncActiveRun().catch(() => {});
        this.startPolling();
      } catch (error) {
        this.reset();
        throw error;
      }
    },
    async pauseRun() {
      if (!this.run.runId) return;
      this.run.status = "paused";
      if (this.run.currentStage) {
        this.stages[this.run.currentStage].hint = "暂停中";
      }
      try {
        await bridge.pauseRun(this.run.runId);
        this.run.status = "paused";
        this.startPolling();
      } catch (error) {
        await this.syncActiveRun().catch(() => {});
        throw error;
      }
    },
    async resumeRun() {
      if (!this.run.runId) return;
      this.run.status = "running";
      if (this.run.currentStage) {
        this.stages[this.run.currentStage].hint = "执行中";
      }
      try {
        await bridge.resumeRun(this.run.runId);
        this.run.status = "running";
        this.startPolling();
      } catch (error) {
        await this.syncActiveRun().catch(() => {});
        throw error;
      }
    },
    async cancelRun() {
      if (!this.run.runId) return;
      this.run.status = "cancelling";
      if (this.run.currentStage) {
        this.stages[this.run.currentStage].hint = "终止中";
      }
      try {
        await bridge.cancelRun(this.run.runId);
        this.run.status = "cancelling";
        this.startPolling();
      } catch (error) {
        await this.syncActiveRun().catch(() => {});
        throw error;
      }
    },
  },
});
