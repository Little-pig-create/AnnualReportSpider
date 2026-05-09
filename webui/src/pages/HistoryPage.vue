<template>
  <section class="history-page">
    <header class="history-head">
      <div>
        <p class="section-kicker">历史任务</p>
        <h2>任务历史中心</h2>
        <p>查看每次运行的开始/结束时间、阶段结果、失败原因、输出目录，并支持搜索、筛选与导出。</p>
      </div>
      <div class="history-head__actions">
        <button class="ghost-button" @click="historyStore.exportJson()" :disabled="historyStore.exporting">
          {{ historyStore.exporting ? "导出中..." : "导出 JSON" }}
        </button>
        <button class="refresh-button" @click="refreshHistory()" :disabled="historyStore.loading">
          {{ historyStore.loading ? "刷新中..." : "刷新历史" }}
        </button>
      </div>
    </header>

    <section class="surface history-toolbar">
      <label class="toolbar-field toolbar-field--search">
        <span>搜索</span>
        <input v-model.trim="keyword" placeholder="搜索运行模式、状态、错误原因、输出目录、运行 ID" />
      </label>

      <label class="toolbar-field">
        <span>状态筛选</span>
        <select v-model="statusFilter">
          <option value="ALL">全部状态</option>
          <option value="completed">已完成</option>
          <option value="failed">失败</option>
          <option value="cancelled">已取消</option>
          <option value="running">运行中</option>
        </select>
      </label>

      <label class="toolbar-field">
        <span>模式筛选</span>
        <select v-model="modeFilter">
          <option value="ALL">全部模式</option>
          <option value="pipeline">完整流程</option>
          <option value="links">仅抓链接</option>
          <option value="pdf">仅下载 PDF</option>
          <option value="extract">仅提取文本</option>
        </select>
      </label>
    </section>

    <section class="surface history-list">
      <div class="history-summary">
        <strong>共 {{ filteredItems.length }} 条</strong>
        <span v-if="keyword">当前搜索：{{ keyword }}</span>
      </div>

      <div v-if="filteredItems.length === 0" class="history-empty">没有匹配的历史任务</div>

      <article v-for="item in filteredItems" :key="item.runId" class="history-card">
        <header class="history-card__head">
          <div>
            <strong>{{ modeText(item.mode) }}</strong>
            <span :data-tone="runStatusTone(item)">{{ runStatusText(item) }}</span>
          </div>
          <div class="history-card__actions">
            <button class="mini-link" @click="openDetail(item)">查看详情</button>
            <button class="mini-link mini-link--success" @click="rerun(item)" :disabled="taskStore.isBusy">一键复跑</button>
            <button class="mini-link" @click="openPath(item.outputDir)" :disabled="!item.outputDir">打开输出目录</button>
          </div>
        </header>

        <div class="history-card__meta">
          <p><b>开始时间：</b>{{ formatDateTime(item.startedAt) }}</p>
          <p><b>结束时间：</b>{{ formatDateTime(item.finishedAt) }}</p>
          <p><b>运行时长：</b>{{ formatDuration(item.startedAt, item.finishedAt) }}</p>
          <p><b>输出目录：</b>{{ item.outputDir || "-" }}</p>
          <p><b>失败原因：</b>{{ item.error || "无" }}</p>
        </div>

        <div class="history-card__stages">
          <div v-for="stage in item.stages" :key="stage.name" class="stage-pill">
            <strong>{{ stage.title }}</strong>
            <span>{{ statusText(stage.status as any) }}</span>
          </div>
        </div>
      </article>
    </section>

    <ElDialog
      v-model="detailVisible"
      :title="selectedItem ? modeText(selectedItem.mode) : '任务详情'"
      width="90%"
      append-to-body
    >
      <div v-if="selectedItem" class="dialog__meta">
        <p><b>运行 ID：</b>{{ selectedItem.runId }}</p>
        <p><b>状态：</b>{{ runStatusText(selectedItem) }}</p>
        <p><b>开始时间：</b>{{ formatDateTime(selectedItem.startedAt) }}</p>
        <p><b>结束时间：</b>{{ formatDateTime(selectedItem.finishedAt) }}</p>
        <p><b>运行时长：</b>{{ formatDuration(selectedItem.startedAt, selectedItem.finishedAt) }}</p>
        <p><b>输出目录：</b>{{ selectedItem.outputDir || "-" }}</p>
        <p><b>失败原因：</b>{{ selectedItem.error || "无" }}</p>
      </div>

      <section v-if="selectedItem" class="dialog-block">
        <header class="dialog-block__head">
          <h4>阶段详情</h4>
        </header>
        <div class="dialog-stage-list">
          <article v-for="stage in selectedItem.stages" :key="stage.name" class="dialog-stage-card">
            <div class="dialog-stage-card__head">
              <strong>{{ stage.title }}</strong>
              <span>{{ statusText(stage.status as any) }}</span>
            </div>
            <p><b>提示：</b>{{ stage.hint || "无" }}</p>
            <p><b>进度：</b>{{ stage.progress.current }}/{{ stage.progress.total }}</p>
            <pre>{{ formatJson(stage.result) }}</pre>
          </article>
        </div>
      </section>

      <section v-if="selectedItem" class="dialog-block">
        <header class="dialog-block__head">
          <h4>结果摘要</h4>
        </header>
        <pre>{{ formatJson(selectedItem.summary) }}</pre>
      </section>
    </ElDialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElDialog } from "element-plus/es/components/dialog/index";
import { bridge } from "@/services/bridge";
import { formatDateTime, formatDuration } from "@/services/datetime";
import { getErrorMessage } from "@/services/errors";
import { useAppStore } from "@/stores/app";
import { useHistoryStore } from "@/stores/history";
import { useSettingsStore } from "@/stores/settings";
import { useTaskStore } from "@/stores/task";
import type { AppSettings, HistoryItem } from "@/services/types";

const appStore = useAppStore();
const historyStore = useHistoryStore();
const settingsStore = useSettingsStore();
const taskStore = useTaskStore();
const keyword = ref("");
const statusFilter = ref("ALL");
const modeFilter = ref("ALL");
const selectedItem = ref<HistoryItem | null>(null);
const detailVisible = computed({
  get: () => Boolean(selectedItem.value),
  set: (value: boolean) => {
    if (!value) selectedItem.value = null;
  },
});

function statusText(status: string) {
  return {
    pending: "等待中",
    running: "运行中",
    completed: "已完成",
    failed: "执行失败",
    cancelled: "已取消",
    cancelling: "终止中",
    idle: "空闲",
  }[status] || status;
}

function runStatusText(item: HistoryItem) {
  if (item.status === "cancelled" && String(item.error || "").includes("窗口关闭导致任务中断")) {
    return "强制退出";
  }
  if (item.status === "cancelled") {
    return "手动终止";
  }
  return statusText(item.status);
}

function runStatusTone(item: HistoryItem) {
  if (item.status === "completed") return "success";
  if (item.status === "running") return "running";
  if (item.status === "cancelling") return "warning";
  if (item.status === "failed") return "danger";
  if (item.status === "cancelled" && String(item.error || "").includes("窗口关闭导致任务中断")) {
    return "danger";
  }
  if (item.status === "cancelled") return "warning";
  return "muted";
}

function modeText(mode: string) {
  return {
    links: "仅抓链接",
    pdf: "仅下载 PDF",
    extract: "仅提取文本",
    pipeline: "完整流程",
  }[mode] || mode;
}

const filteredItems = computed(() => {
  const text = keyword.value.toLowerCase();
  return historyStore.items.filter((item) => {
    const statusOk = statusFilter.value === "ALL" || item.status === statusFilter.value;
    const modeOk = modeFilter.value === "ALL" || item.mode === modeFilter.value;
    if (!statusOk || !modeOk) return false;
    if (!text) return true;
    const searchText = [
      item.runId,
      item.mode,
      modeText(item.mode),
      item.status,
      runStatusText(item),
      item.error || "",
      item.outputDir || "",
      item.startedAt || "",
      item.finishedAt || "",
    ].join(" ").toLowerCase();
    return searchText.includes(text);
  });
});

function openPath(path: string) {
  if (!path) return;
  bridge.openPath(path);
}

async function refreshHistory() {
  if (historyStore.loading) return;
  appStore.showAlert("正在刷新历史任务...", "info", "历史任务");
  try {
    await historyStore.load();
    appStore.showAlert(`历史任务刷新完成：${historyStore.items.length} 条`, "success", "历史任务");
  } catch (error) {
    appStore.showAlert(getErrorMessage(error, "刷新历史任务失败"), "error", "历史任务");
  }
}

function openDetail(item: HistoryItem) {
  selectedItem.value = item;
}

function cloneSettingsSnapshot(snapshot: AppSettings): AppSettings {
  return JSON.parse(JSON.stringify(snapshot));
}

async function rerun(item: HistoryItem) {
  if (taskStore.isBusy) {
    appStore.showAlert("当前有任务正在运行，请先暂停或终止后再复跑", "warning");
    return;
  }
  if (!item.settingsSnapshot) {
    appStore.showAlert("该历史任务缺少配置快照，无法一键复跑", "warning");
    return;
  }

  try {
    await appStore.showConfirm({
      title: "确认一键复跑",
      message: `将使用该任务保存时的原配置并重新执行“${modeText(item.mode)}”`,
      type: "warning",
      confirmText: "开始复跑",
      cancelText: "取消",
    });
  } catch {
    return;
  }

  try {
    const snapshot = cloneSettingsSnapshot(item.settingsSnapshot);
    await bridge.updateSettings(snapshot);
    settingsStore.data = snapshot;
    settingsStore.dirty = false;
    await taskStore.startRun(item.mode);
    appStore.setPage("command");
    appStore.showAlert(`已开始复跑：${modeText(item.mode)}`, "success");
  } catch (error) {
    appStore.showAlert(getErrorMessage(error, "一键复跑失败"), "error");
  }
}

function formatJson(value: unknown) {
  if (!value) return "无";
  return JSON.stringify(value, null, 2);
}

onMounted(() => {
  if (historyStore.items.length === 0) {
    historyStore.load();
  }
});
</script>

<style scoped>
.history-page { display: grid; gap: 24px; }
.history-head { display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; }
.history-head h2 { margin: 6px 0 12px; font-size: 40px; }
.history-head p:last-child { margin: 0; color: var(--muted); max-width: 760px; }
.history-head__actions { display: flex; gap: 12px; }
.refresh-button,.ghost-button { border: 0; border-radius: 999px; padding: 14px 20px; font-weight: 700; cursor: pointer; }
.refresh-button { background: linear-gradient(135deg, #0f766e, #155e75); color: white; }
.ghost-button { background: #eef6f3; color: #0f766e; }
.history-toolbar { display: grid; grid-template-columns: 1.2fr 0.4fr 0.4fr; gap: 16px; }
.toolbar-field { display: grid; gap: 8px; }
.toolbar-field span { font-size: 13px; color: var(--muted); }
.toolbar-field input,.toolbar-field select {
  width: 100%;
  border: 1px solid rgba(29, 78, 216, 0.12);
  border-radius: 16px;
  padding: 12px 14px;
  background: #eef2ff;
  color: #1d4ed8;
  appearance: none;
  -webkit-appearance: none;
  -moz-appearance: none;
}

.toolbar-field input::placeholder {
  color: rgba(29, 78, 216, 0.65);
}

.toolbar-field select {
  background-image:
    linear-gradient(45deg, transparent 50%, #1d4ed8 50%),
    linear-gradient(135deg, #1d4ed8 50%, transparent 50%);
  background-position:
    calc(100% - 22px) calc(50% - 3px),
    calc(100% - 14px) calc(50% - 3px);
  background-size: 8px 8px, 8px 8px;
  background-repeat: no-repeat;
  padding-right: 40px;
}

.toolbar-field select option {
  color: #1d4ed8;
  background: #eef2ff;
}
.history-list { display: grid; gap: 16px; }
.history-summary { display: flex; justify-content: space-between; gap: 16px; color: var(--muted); }
.history-empty { color: var(--muted); }
.history-card { display: grid; gap: 14px; padding: 18px 20px; border-radius: 20px; background: var(--panel-alt); }
.history-card__head { display: flex; justify-content: space-between; gap: 16px; align-items: center; }
.history-card__head > div:first-child { display: flex; gap: 12px; align-items: center; }
.history-card__head span {
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(17, 24, 39, 0.06);
  color: var(--muted);
  font-weight: 700;
}
.history-card__head span[data-tone="success"] {
  background: #dcfce7;
  color: #166534;
}
.history-card__head span[data-tone="running"] {
  background: #dbeafe;
  color: #1d4ed8;
}
.history-card__head span[data-tone="warning"] {
  background: #ffedd5;
  color: #c2410c;
}
.history-card__head span[data-tone="danger"] {
  background: #fee2e2;
  color: #b91c1c;
}
.history-card__actions { display: flex; gap: 10px; flex-wrap: wrap; }
.history-card__meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 20px; }
.history-card__meta p { margin: 0; color: var(--muted); word-break: break-all; }
.history-card__stages { display: flex; flex-wrap: wrap; gap: 10px; }
.stage-pill { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-radius: 14px; background: #fff; }
.mini-link { border: 0; background: #eef2ff; color: #1d4ed8; border-radius: 999px; padding: 10px 14px; cursor: pointer; }
.mini-link--success { background: #dcfce7; color: #166534; }
pre::-webkit-scrollbar,
pre::-webkit-scrollbar {
  width: 0;
  height: 0;
}
.dialog__meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 20px; }
.dialog__meta p { margin: 0; word-break: break-all; color: var(--muted); }
.dialog-block { display: grid; gap: 14px; }
.dialog-block__head h4 { margin: 0; font-size: 20px; }
.dialog-stage-list { display: grid; gap: 12px; }
.dialog-stage-card { display: grid; gap: 10px; padding: 16px; border-radius: 18px; background: var(--panel-alt); }
.dialog-stage-card__head { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.dialog-stage-card p, pre { margin: 0; }
pre {
  padding: 14px;
  border-radius: 14px;
  background: #0f172a;
  color: #e2e8f0;
  overflow: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px;
  line-height: 1.6;
}
@media (max-width: 1180px) {
  .history-head, .history-card__head { flex-direction: column; align-items: flex-start; }
  .history-toolbar, .history-card__meta, .dialog__meta { grid-template-columns: 1fr; }
}
</style>
