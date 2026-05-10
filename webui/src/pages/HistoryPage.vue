<template>
  <section class="history-page">
    <header class="history-head">
      <div class="history-head__copy">
        <p class="section-kicker">历史任务</p>
        <h2>任务历史中心</h2>
        <p>
          查看每次运行的开始时间、结束时间、运行时长、阶段结果、失败原因与输出目录，
          支持搜索、筛选、导出与一键复跑。
        </p>
      </div>

      <div class="history-head__actions">
        <button class="ghost-button" @click="historyStore.exportJson()" :disabled="historyStore.exporting">
          {{ historyStore.exporting ? "导出中..." : "导出 JSON" }}
        </button>
        <button class="refresh-button" @click="refreshHistory" :disabled="historyStore.loading">
          {{ historyStore.loading ? "刷新中..." : "刷新历史" }}
        </button>
      </div>
    </header>

    <section class="surface history-toolbar">
      <label class="toolbar-field toolbar-field--search">
        <span>搜索</span>
        <input
          v-model.trim="keyword"
          placeholder="搜索运行模式、状态、失败原因、输出目录、运行 ID"
        />
      </label>

      <label class="toolbar-field">
        <span>状态筛选</span>
        <select v-model="statusFilter">
          <option value="ALL">全部状态</option>
          <option value="completed">已完成</option>
          <option value="failed">失败</option>
          <option value="cancelled">已终止</option>
          <option value="running">运行中</option>
          <option value="paused">已暂停</option>
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

      <div v-if="filteredItems.length === 0" class="history-empty">
        没有匹配的历史任务
      </div>

      <div v-else class="history-cards">
        <article v-for="item in pagedItems" :key="item.runId" class="history-card">
          <div class="history-card__top">
            <div class="history-card__title-wrap">
              <h3 class="history-card__title">{{ modeText(item.mode) }}</h3>
              <p class="history-card__subtitle">运行 ID：{{ item.runId }}</p>
            </div>
            <div class="history-card__status" :data-tone="runStatusTone(item)">
              {{ runStatusText(item) }}
            </div>
          </div>

          <div class="history-card__grid">
            <div class="history-meta">
              <span class="history-meta__label">开始时间</span>
              <strong class="history-meta__value">{{ formatDateTime(item.startedAt) }}</strong>
            </div>
            <div class="history-meta">
              <span class="history-meta__label">结束时间</span>
              <strong class="history-meta__value">{{ formatDateTime(item.finishedAt) }}</strong>
            </div>
            <div class="history-meta">
              <span class="history-meta__label">运行时长</span>
              <strong class="history-meta__value">{{ formatDuration(item.startedAt, item.finishedAt) }}</strong>
            </div>
            <div class="history-meta">
              <span class="history-meta__label">输出目录</span>
              <strong class="history-meta__value history-meta__value--path">{{ item.outputDir || "-" }}</strong>
            </div>
          </div>

          <p v-if="item.error" class="history-card__error">失败原因：{{ item.error }}</p>

          <div class="history-card__footer">
            <div class="history-card__actions">
              <button class="mini-link" @click="openDetail(item)">查看详情</button>
              <button
                class="mini-link mini-link--success"
                @click="rerun(item)"
                :disabled="taskStore.isBusy"
              >
                一键复跑
              </button>
              <button class="mini-link" @click="openPath(item.outputDir)" :disabled="!item.outputDir">
                打开输出目录
              </button>
            </div>
          </div>
        </article>
      </div>

      <div v-if="filteredItems.length > pageSize" class="history-pagination">
        <ElPagination
          background
          layout="total, prev, pager, next, jumper"
          :total="filteredItems.length"
          :page-size="pageSize"
          :current-page="currentPage"
          @current-change="handlePageChange"
        />
      </div>
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
              <span>{{ statusText(stage.status) }}</span>
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
import { computed, onMounted, ref, watch } from "vue";
import { ElDialog, ElPagination } from "element-plus";
import { bridge } from "@/services/bridge";
import { formatDateTime, formatDuration } from "@/services/datetime";
import { getErrorMessage } from "@/services/errors";
import type { AppSettings, HistoryItem } from "@/services/types";
import { useAppStore } from "@/stores/app";
import { useHistoryStore } from "@/stores/history";
import { useSettingsStore } from "@/stores/settings";
import { useTaskStore } from "@/stores/task";

const appStore = useAppStore();
const historyStore = useHistoryStore();
const settingsStore = useSettingsStore();
const taskStore = useTaskStore();

const keyword = ref("");
const statusFilter = ref("ALL");
const modeFilter = ref("ALL");
const currentPage = ref(1);
const pageSize = 12;
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
    paused: "已暂停",
    completed: "已完成",
    failed: "执行失败",
    cancelled: "已终止",
    cancelling: "终止中",
    idle: "空闲",
  }[status] || status;
}

function runStatusText(item: HistoryItem) {
  if (item.status === "cancelled" && String(item.error || "").includes("窗口关闭")) {
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
  if (item.status === "paused" || item.status === "cancelling") return "warning";
  if (item.status === "failed") return "danger";
  if (item.status === "cancelled" && String(item.error || "").includes("窗口关闭")) return "danger";
  if (item.status === "cancelled") return "warning";
  return "muted";
}

function modeText(mode: string) {
  return {
    links: "公告链接抓取",
    pdf: "PDF 下载",
    extract: "文本提取",
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
    ]
      .join(" ")
      .toLowerCase();

    return searchText.includes(text);
  });
});

const pagedItems = computed(() => {
  const start = (currentPage.value - 1) * pageSize;
  return filteredItems.value.slice(start, start + pageSize);
});

function openPath(path: string) {
  if (!path) return;
  bridge.openPath(path);
}

function handlePageChange(page: number) {
  currentPage.value = page;
}

async function refreshHistory() {
  if (historyStore.loading) return;
  appStore.showAlert("正在刷新历史任务...", "info", "历史任务");
  try {
    await historyStore.load();
    appStore.showAlert(`历史任务刷新完成，共 ${historyStore.items.length} 条`, "success", "历史任务");
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
      message: `将使用该任务保存时的原配置，并重新执行“${modeText(item.mode)}”`,
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
    historyStore.load().catch(() => {});
  }
});

watch([keyword, statusFilter, modeFilter], () => {
  currentPage.value = 1;
});

watch(
  () => filteredItems.value.length,
  (total) => {
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    if (currentPage.value > totalPages) {
      currentPage.value = totalPages;
    }
  },
);
</script>

<style scoped>
.history-page {
  display: grid;
  gap: 24px;
}

.history-head {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: flex-start;
}

.history-head__copy {
  display: grid;
  gap: 8px;
}

.history-head h2 {
  margin: 6px 0 0;
  font-size: 40px;
}

.history-head p:last-child {
  margin: 0;
  color: var(--muted);
  max-width: 820px;
  line-height: 1.7;
}

.history-head__actions {
  display: flex;
  gap: 12px;
}

.refresh-button,
.ghost-button {
  border: 0;
  border-radius: 999px;
  padding: 14px 20px;
  font-weight: 700;
  cursor: pointer;
}

.refresh-button {
  background: linear-gradient(135deg, #0f766e, #155e75);
  color: #fff;
}

.ghost-button {
  background: #eef6f3;
  color: #0f766e;
}

.history-toolbar {
  display: grid;
  grid-template-columns: 1.2fr 0.4fr 0.4fr;
  gap: 16px;
}

.toolbar-field {
  display: grid;
  gap: 8px;
}

.toolbar-field span {
  font-size: 13px;
  color: var(--muted);
}

.toolbar-field input,
.toolbar-field select {
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

.history-list {
  display: grid;
  gap: 16px;
}

.history-summary {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  color: var(--muted);
}

.history-empty {
  color: var(--muted);
  min-height: 120px;
  display: grid;
  place-items: center;
}

.history-cards {
  display: grid;
  gap: 16px;
}

.history-card {
  display: grid;
  gap: 16px;
  padding: 22px;
  border-radius: 24px;
  background: var(--panel-alt);
  border: 1px solid rgba(17, 24, 39, 0.06);
}

.history-card__top {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.history-card__title-wrap {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.history-card__title {
  margin: 0;
  font-size: 22px;
  line-height: 1.3;
  color: #1f2937;
}

.history-card__subtitle {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  word-break: break-all;
}

.history-card__status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 36px;
  padding: 0 16px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
  white-space: nowrap;
}

.history-card__status[data-tone="success"] {
  background: #dcfce7;
  color: #166534;
}

.history-card__status[data-tone="running"] {
  background: #dbeafe;
  color: #1d4ed8;
}

.history-card__status[data-tone="warning"] {
  background: #fff7ed;
  color: #c2410c;
}

.history-card__status[data-tone="danger"] {
  background: #fee2e2;
  color: #b91c1c;
}

.history-card__status[data-tone="muted"] {
  background: #e5e7eb;
  color: #4b5563;
}

.history-card__grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.history-meta {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.6);
}

.history-meta__label {
  color: var(--muted);
  font-size: 12px;
}

.history-meta__value {
  color: #1f2937;
  font-size: 14px;
  line-height: 1.6;
}

.history-meta__value--path {
  word-break: break-all;
}

.history-card__error {
  margin: 0;
  color: #dc2626;
  font-size: 13px;
  line-height: 1.7;
  word-break: break-all;
}

.history-card__footer {
  display: flex;
  justify-content: flex-end;
  gap: 18px;
  align-items: center;
}

.history-card__actions {
  display: flex;
  gap: 8px;
  flex-wrap: nowrap;
  overflow-x: auto;
  overflow-y: hidden;
  align-items: center;
  justify-content: flex-end;
  flex: 0 0 auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.history-card__actions::-webkit-scrollbar {
  width: 0;
  height: 0;
}

.history-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

.mini-link {
  border: 0;
  background: #eef2ff;
  color: #1d4ed8;
  border-radius: 999px;
  padding: 10px 14px;
  cursor: pointer;
  flex: 0 0 auto;
  white-space: nowrap;
}

.mini-link--success {
  background: #dcfce7;
  color: #166534;
}

.dialog__meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 20px;
}

.dialog__meta p {
  margin: 0;
  word-break: break-all;
  color: var(--muted);
}

.dialog-block {
  display: grid;
  gap: 14px;
}

.dialog-block__head h4 {
  margin: 0;
  font-size: 20px;
}

.dialog-stage-list {
  display: grid;
  gap: 12px;
}

.dialog-stage-card {
  display: grid;
  gap: 10px;
  padding: 16px;
  border-radius: 18px;
  background: var(--panel-alt);
}

.dialog-stage-card__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.dialog-stage-card p,
pre {
  margin: 0;
}

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

pre::-webkit-scrollbar {
  width: 0;
  height: 0;
}

@media (max-width: 1180px) {
  .history-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .history-toolbar,
  .dialog__meta,
  .history-card__grid {
    grid-template-columns: 1fr;
  }

  .history-card__top,
  .history-card__footer {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
