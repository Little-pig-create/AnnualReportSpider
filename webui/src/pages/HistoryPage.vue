<template>
  <section class="history-page">
    <header class="history-head">
      <div class="history-head__copy">
        <p class="section-kicker">历史任务</p>
        <h2>任务历史中心</h2>
        <p>查看每次运行的开始时间、结束时间、运行时长、阶段结果、失败原因与输出目录，支持搜索、筛选、导出与一键复跑。</p>
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
      <div v-if="selectedItem" class="dialog-layout">
        <section class="dialog-hero">
          <div class="dialog-hero__main">
            <p class="section-kicker">任务摘要</p>
            <h3>{{ modeText(selectedItem.mode) }}</h3>
            <p class="dialog-hero__desc">
              运行 ID：{{ selectedItem.runId }}
            </p>
          </div>
          <div class="dialog-hero__status" :data-tone="runStatusTone(selectedItem)">
            {{ runStatusText(selectedItem) }}
          </div>
        </section>

        <section v-if="selectedItem.error" class="dialog-alert">
          <strong>失败原因</strong>
          <p>{{ selectedItem.error }}</p>
        </section>

        <section class="dialog-block">
          <header class="dialog-block__head">
            <h4>基础信息</h4>
          </header>
          <div class="dialog-summary-grid">
            <article class="dialog-summary-card">
              <small>运行模式</small>
              <strong>{{ modeText(selectedItem.mode) }}</strong>
            </article>
            <article class="dialog-summary-card">
              <small>开始时间</small>
              <strong>{{ formatDateTime(selectedItem.startedAt) }}</strong>
            </article>
            <article class="dialog-summary-card">
              <small>结束时间</small>
              <strong>{{ formatDateTime(selectedItem.finishedAt) }}</strong>
            </article>
            <article class="dialog-summary-card">
              <small>运行时长</small>
              <strong>{{ formatDuration(selectedItem.startedAt, selectedItem.finishedAt) }}</strong>
            </article>
            <article class="dialog-summary-card dialog-summary-card--wide">
              <small>输出目录</small>
              <strong>{{ selectedItem.outputDir || "-" }}</strong>
            </article>
          </div>
        </section>

        <section class="dialog-block">
          <header class="dialog-block__head">
            <h4>阶段结果结构图</h4>
          </header>
          <article class="dialog-chart-card">
            <header class="dialog-chart-card__head">
              <strong>单次任务结果构成</strong>
              <span>用一张堆叠图解释各阶段的结果结构，适合快速复盘。</span>
            </header>
            <BaseChart :option="stageStructureChartOption" />
          </article>
        </section>

        <section class="dialog-block">
          <header class="dialog-block__head">
            <h4>阶段摘要卡</h4>
          </header>
          <div class="dialog-stage-list">
            <article v-for="stage in selectedItem.stages" :key="stage.name" class="dialog-stage-card">
              <div class="dialog-stage-card__head">
                <div class="dialog-stage-card__title">
                  <strong>{{ stage.title }}</strong>
                  <span class="dialog-stage-card__status" :data-status="stage.status">
                    {{ statusText(stage.status) }}
                  </span>
                </div>
                <div class="dialog-stage-card__metrics">
                  <strong class="dialog-stage-card__percent">{{ stagePercentText(stage) }}</strong>
                  <span class="dialog-stage-card__progress">
                    {{ stage.progress.current }}/{{ stage.progress.total }}
                  </span>
                </div>
              </div>
              <div class="dialog-stage-card__bar">
                <div
                  class="dialog-stage-card__bar-fill"
                  :data-status="stage.status"
                  :style="{ width: `${stagePercent(stage)}%` }"
                />
              </div>
              <div class="dialog-stage-card__meta">
                <span>进度百分比：{{ stagePercentText(stage) }}</span>
                <span>阶段状态：{{ statusText(stage.status) }}</span>
              </div>
              <div v-if="stageMetrics(stage).length" class="dialog-stage-card__stats">
                <article
                  v-for="metric in stageMetrics(stage)"
                  :key="`${stage.name}-${metric.label}`"
                  class="dialog-stage-card__stat"
                >
                  <small>{{ metric.label }}</small>
                  <strong>{{ metric.value }}</strong>
                </article>
              </div>
              <p class="dialog-stage-card__hint">{{ stage.hint || "暂无阶段提示" }}</p>
              <button class="mini-link dialog-stage-card__detail" @click="toggleStage(stage.name)">
                {{ expandedStages.includes(stage.name) ? "收起原始结果" : "查看原始结果" }}
              </button>
              <pre v-if="expandedStages.includes(stage.name)">{{ formatJson(stage.result) }}</pre>
            </article>
          </div>
        </section>

        <section class="dialog-block">
          <header class="dialog-block__head">
            <h4>原始 JSON / 原始结果</h4>
          </header>
          <div class="dialog-raw-actions">
            <button class="mini-link" @click="rawVisible = !rawVisible">
              {{ rawVisible ? "收起摘要 JSON" : "展开摘要 JSON" }}
            </button>
          </div>
          <pre v-if="rawVisible">{{ formatJson(selectedItem.summary) }}</pre>
        </section>
      </div>
    </ElDialog>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElDialog } from "element-plus/es/components/dialog/index";
import { ElPagination } from "element-plus/es/components/pagination/index";
import BaseChart from "@/components/BaseChart.vue";
import { bridge } from "@/services/bridge";
import { formatDateTime, formatDuration } from "@/services/datetime";
import { getErrorMessage } from "@/services/errors";
import type { AppSettings, HistoryItem, StageName, StageState } from "@/services/types";
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
const expandedStages = ref<StageName[]>([]);
const rawVisible = ref(false);

const detailVisible = computed({
  get: () => Boolean(selectedItem.value),
  set: (value: boolean) => {
    if (!value) {
      selectedItem.value = null;
      expandedStages.value = [];
      rawVisible.value = false;
    }
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

function stagePercent(stage: StageState) {
  const percent = Number(stage.progress?.percent || 0);
  if (Number.isFinite(percent) && percent > 0) {
    return Math.max(0, Math.min(100, Math.round(percent * 100)));
  }
  const current = Number(stage.progress?.current || 0);
  const total = Number(stage.progress?.total || 0);
  if (total > 0) {
    return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
  }
  if (stage.status === "completed") return 100;
  return 0;
}

function stagePercentText(stage: StageState) {
  return `${stagePercent(stage)}%`;
}

function metricValue(source: Record<string, any>, keys: string[]) {
  for (const key of keys) {
    if (source[key] !== undefined && source[key] !== null && source[key] !== "") {
      return source[key];
    }
  }
  return null;
}

function stageMetrics(stage: StageState) {
  const source = (stage.result || {}) as Record<string, any>;

  if (stage.name === "links") {
    const rows = metricValue(source, ["rows", "totalAnnouncements", "recordsFound"]);
    const rawRows = metricValue(source, ["rawRecordsFound"]);
    const years = Array.isArray(source.years) ? source.years.length : metricValue(source, ["yearTotal"]);
    const summaryPath = metricValue(source, ["summary_path", "summaryPath"]);
    return [
      rows !== null ? { label: "抓取条数", value: rows } : null,
      rawRows !== null ? { label: "原始条数", value: rawRows } : null,
      years !== null ? { label: "年份数量", value: years } : null,
      summaryPath ? { label: "摘要文件", value: "已生成" } : null,
    ].filter(Boolean) as Array<{ label: string; value: string | number }>;
  }

  if (stage.name === "pdf") {
    const downloaded = Number(metricValue(source, ["downloaded"]) || 0);
    const exists = Number(metricValue(source, ["exists"]) || 0);
    const failed = Number(metricValue(source, ["failed"]) || 0);
    const skipped = Number(metricValue(source, ["skipped"]) || 0);
    return [
      { label: "下载完成", value: downloaded },
      { label: "已存在", value: exists },
      { label: "失败数量", value: failed },
      { label: "跳过数量", value: skipped },
    ];
  }

  if (stage.name === "extract") {
    const extracted = Number(metricValue(source, ["extracted"]) || 0);
    const exists = Number(metricValue(source, ["exists"]) || 0);
    const failed = Number(metricValue(source, ["failed"]) || 0);
    const pdfTotal = metricValue(source, ["pdfTotal", "total"]);
    return [
      { label: "提取成功", value: extracted },
      { label: "已存在", value: exists },
      { label: "失败数量", value: failed },
      pdfTotal !== null ? { label: "PDF 总量", value: pdfTotal } : null,
    ].filter(Boolean) as Array<{ label: string; value: string | number }>;
  }

  return [];
}

const stageStructureChartOption = computed(() => {
  const palette = {
    linksMain: "#2A9D8F",
    linksSoft: "#7FD1C7",
    pdfMain: "#4C6FFF",
    pdfSoft: "#A9B8FF",
    pdfWarn: "#F4A261",
    extractMain: "#7B61FF",
    extractSoft: "#C5B8FF",
    danger: "#E76F51",
    axis: "#64748b",
    grid: "rgba(148, 163, 184, 0.18)",
    text: "#334155",
  };

  const stages = selectedItem.value?.stages || [];
  const categories = stages.map((stage) => stage.title);

  const linksProduced = stages.map((stage) => {
    if (stage.name !== "links") return 0;
    const source = (stage.result || {}) as Record<string, any>;
    return Number(metricValue(source, ["rows", "totalAnnouncements", "recordsFound"]) || 0);
  });

  const linksRaw = stages.map((stage) => {
    if (stage.name !== "links") return 0;
    const source = (stage.result || {}) as Record<string, any>;
    return Number(metricValue(source, ["rawRecordsFound"]) || 0);
  });

  const pdfCompleted = stages.map((stage) => {
    if (stage.name !== "pdf") return 0;
    const source = (stage.result || {}) as Record<string, any>;
    return Number(source.downloaded || 0) + Number(source.exists || 0);
  });

  const pdfFailed = stages.map((stage) => {
    if (stage.name !== "pdf") return 0;
    const source = (stage.result || {}) as Record<string, any>;
    return Number(source.failed || 0);
  });

  const pdfSkipped = stages.map((stage) => {
    if (stage.name !== "pdf") return 0;
    const source = (stage.result || {}) as Record<string, any>;
    return Number(source.skipped || 0);
  });

  const extractCompleted = stages.map((stage) => {
    if (stage.name !== "extract") return 0;
    const source = (stage.result || {}) as Record<string, any>;
    return Number(source.extracted || 0) + Number(source.exists || 0);
  });

  const extractFailed = stages.map((stage) => {
    if (stage.name !== "extract") return 0;
    const source = (stage.result || {}) as Record<string, any>;
    return Number(source.failed || 0);
  });

  return {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: "rgba(255,255,255,0.96)",
      borderColor: "rgba(148,163,184,0.2)",
      borderWidth: 1,
      textStyle: { color: palette.text },
      extraCssText: "box-shadow: 0 16px 40px rgba(15, 23, 42, 0.14); border-radius: 14px;",
    },
    legend: {
      bottom: 0,
      itemWidth: 12,
      itemHeight: 12,
      icon: "roundRect",
      textStyle: {
        color: palette.axis,
        fontSize: 12,
        fontWeight: 600,
      },
    },
    grid: {
      left: 24,
      right: 16,
      top: 24,
      bottom: 54,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: categories,
      axisTick: { show: false },
      axisLabel: {
        color: palette.axis,
        fontSize: 12,
        margin: 12,
      },
      axisLine: {
        lineStyle: {
          color: "rgba(148, 163, 184, 0.35)",
        },
      },
    },
    yAxis: {
      type: "value",
      axisLabel: {
        color: palette.axis,
        fontSize: 12,
        margin: 12,
      },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: {
        lineStyle: {
          color: palette.grid,
          type: "dashed",
        },
      },
    },
    series: [
      {
        name: "链接抓取",
        type: "bar",
        stack: "links",
        data: linksProduced,
        itemStyle: { color: palette.linksMain, borderRadius: 0 },
        barMaxWidth: 28,
      },
      {
        name: "链接原始",
        type: "bar",
        stack: "links",
        data: linksRaw,
        itemStyle: { color: palette.linksSoft, borderRadius: 0 },
        barMaxWidth: 28,
      },
      {
        name: "PDF 完成",
        type: "bar",
        stack: "pdf",
        data: pdfCompleted,
        itemStyle: { color: palette.pdfMain, borderRadius: 0 },
        barMaxWidth: 28,
      },
      {
        name: "PDF 失败",
        type: "bar",
        stack: "pdf",
        data: pdfFailed,
        itemStyle: { color: palette.danger, borderRadius: 0 },
        barMaxWidth: 28,
      },
      {
        name: "PDF 跳过",
        type: "bar",
        stack: "pdf",
        data: pdfSkipped,
        itemStyle: { color: palette.pdfWarn, borderRadius: 0 },
        barMaxWidth: 28,
      },
      {
        name: "提取完成",
        type: "bar",
        stack: "extract",
        data: extractCompleted,
        itemStyle: { color: palette.extractMain, borderRadius: 0 },
        barMaxWidth: 28,
      },
      {
        name: "提取失败",
        type: "bar",
        stack: "extract",
        data: extractFailed,
        itemStyle: { color: palette.extractSoft, borderRadius: 0 },
        barMaxWidth: 28,
      },
    ],
  };
});

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
  expandedStages.value = [];
  rawVisible.value = false;
}

function toggleStage(name: StageName) {
  if (expandedStages.value.includes(name)) {
    expandedStages.value = expandedStages.value.filter((item) => item !== name);
    return;
  }
  expandedStages.value = [...expandedStages.value, name];
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
  align-items: center;
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
  line-height: 1.7;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-head__actions {
  display: flex;
  gap: 12px;
  align-items: center;
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
  align-items: center;
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

.dialog-layout {
  display: grid;
  gap: 18px;
}

.dialog-hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 20px 22px;
  border-radius: 22px;
  background: linear-gradient(135deg, rgba(15, 118, 110, 0.08), rgba(29, 78, 216, 0.06));
}

.dialog-hero__main {
  display: grid;
  gap: 8px;
}

.dialog-hero__main h3 {
  margin: 0;
  font-size: 28px;
}

.dialog-hero__desc {
  margin: 0;
  color: var(--muted);
  word-break: break-all;
}

.dialog-hero__status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 40px;
  padding: 0 18px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 700;
  white-space: nowrap;
}

.dialog-hero__status[data-tone="success"] {
  background: #dcfce7;
  color: #166534;
}

.dialog-hero__status[data-tone="running"] {
  background: #dbeafe;
  color: #1d4ed8;
}

.dialog-hero__status[data-tone="warning"] {
  background: #fff7ed;
  color: #c2410c;
}

.dialog-hero__status[data-tone="danger"] {
  background: #fee2e2;
  color: #b91c1c;
}

.dialog-hero__status[data-tone="muted"] {
  background: #e5e7eb;
  color: #4b5563;
}

.dialog-alert {
  display: grid;
  gap: 8px;
  padding: 16px 18px;
  border-radius: 18px;
  background: #fef2f2;
  border: 1px solid #fecaca;
}

.dialog-alert strong {
  color: #b91c1c;
}

.dialog-alert p {
  margin: 0;
  color: #991b1b;
  line-height: 1.7;
  word-break: break-all;
}

.dialog-block {
  display: grid;
  gap: 14px;
}

.dialog-block__head h4 {
  margin: 0;
  font-size: 20px;
}

.dialog-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.dialog-summary-card {
  display: grid;
  gap: 8px;
  padding: 16px 18px;
  border-radius: 18px;
  background: var(--panel-alt);
}

.dialog-summary-card small {
  color: var(--muted);
}

.dialog-summary-card strong {
  color: #1f2937;
  line-height: 1.6;
  word-break: break-all;
}

.dialog-summary-card--wide {
  grid-column: span 2;
}

.dialog-chart-card {
  display: grid;
  gap: 12px;
  padding: 16px 18px;
  border-radius: 18px;
  background: var(--panel-alt);
}

.dialog-chart-card__head {
  display: grid;
  gap: 4px;
}

.dialog-chart-card__head strong {
  color: #1f2937;
  font-size: 16px;
}

.dialog-chart-card__head span {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
}

.dialog-chart-card :deep(.chart) {
  min-height: 320px;
}

.dialog-stage-list {
  display: grid;
  gap: 12px;
}

.dialog-stage-card {
  display: grid;
  gap: 12px;
  padding: 16px;
  border-radius: 18px;
  background: var(--panel-alt);
}

.dialog-stage-card__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.dialog-stage-card__title {
  display: grid;
  gap: 6px;
}

.dialog-stage-card__metrics {
  display: grid;
  justify-items: end;
  gap: 4px;
}

.dialog-stage-card__status {
  font-size: 13px;
  font-weight: 600;
}

.dialog-stage-card__status[data-status="completed"] {
  color: #166534;
}

.dialog-stage-card__status[data-status="running"] {
  color: #1d4ed8;
}

.dialog-stage-card__status[data-status="failed"],
.dialog-stage-card__status[data-status="cancelled"] {
  color: #b91c1c;
}

.dialog-stage-card__progress {
  color: var(--muted);
  font-size: 13px;
  white-space: nowrap;
}

.dialog-stage-card__percent {
  color: #1f2937;
  font-size: 20px;
  line-height: 1;
}

.dialog-stage-card__bar {
  position: relative;
  width: 100%;
  height: 10px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.16);
  overflow: hidden;
}

.dialog-stage-card__bar-fill {
  height: 100%;
  border-radius: 999px;
  background: #94a3b8;
  transition: width 0.24s ease;
}

.dialog-stage-card__bar-fill[data-status="completed"] {
  background: linear-gradient(90deg, #34d399, #0f766e);
}

.dialog-stage-card__bar-fill[data-status="running"] {
  background: linear-gradient(90deg, #60a5fa, #1d4ed8);
}

.dialog-stage-card__bar-fill[data-status="failed"],
.dialog-stage-card__bar-fill[data-status="cancelled"] {
  background: linear-gradient(90deg, #f87171, #dc2626);
}

.dialog-stage-card__meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
  flex-wrap: wrap;
}

.dialog-stage-card__stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.dialog-stage-card__stat {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.58);
}

.dialog-stage-card__stat small {
  color: var(--muted);
  font-size: 12px;
}

.dialog-stage-card__stat strong {
  color: #1f2937;
  font-size: 16px;
  line-height: 1.4;
  word-break: break-all;
}

.dialog-stage-card__hint {
  margin: 0;
  color: var(--muted);
  line-height: 1.7;
}

.dialog-stage-card__detail {
  justify-self: start;
}

.dialog-raw-actions {
  display: flex;
  justify-content: flex-start;
}

pre {
  margin: 0;
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
  .history-head,
  .dialog-hero {
    flex-direction: column;
    align-items: flex-start;
  }

  .history-toolbar,
  .history-card__grid,
  .dialog-summary-grid,
  .dialog-stage-card__stats {
    grid-template-columns: 1fr;
  }

  .dialog-summary-card--wide {
    grid-column: span 1;
  }
}
</style>
