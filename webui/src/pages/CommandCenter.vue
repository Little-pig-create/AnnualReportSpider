<template>
  <section class="console-page">
    <header class="console-head surface">
      <div class="console-head__copy">
        <p class="section-kicker">任务面板</p>
        <h2>任务控制台</h2>
        <p>运行中实时展示阶段进度、年份统计图表与日志，同时尽量避免影响 PDF 下载和文本提取速度。</p>
      </div>

      <div class="console-head__actions">
        <button class="action subtle" @click="start('links')" :disabled="taskStore.isBusy">仅抓链接</button>
        <button class="action subtle" @click="start('pdf')" :disabled="taskStore.isBusy">仅下 PDF</button>
        <button class="action subtle" @click="start('extract')" :disabled="taskStore.isBusy">仅提文本</button>
        <button class="action primary" @click="start('pipeline')" :disabled="taskStore.isBusy">执行全流程</button>
        <button class="action warning" @click="togglePause" :disabled="!taskStore.isPausable && !taskStore.isResumable">
          {{ taskStore.isResumable ? "继续任务" : "暂停任务" }}
        </button>
        <button class="action danger" @click="terminateRun" :disabled="!taskStore.isBusy">终止任务</button>
      </div>
    </header>

    <div class="console-grid">
      <section class="surface overview-stack">
        <div class="focus-panel">
          <div class="focus-panel__gauge">
            <div class="gauge-card">
              <BaseChart :option="progressGaugeOption" />
            </div>
          </div>

          <div class="focus-panel__meta">
              <article>
                <small>运行模式</small>
                <strong>{{ modeLabel }}</strong>
              </article>
              <article>
                <small>进度口径</small>
                <strong>{{ progressLogicLabel }}</strong>
              </article>
            <article>
              <small>开始时间</small>
              <strong>{{ formatDateTime(taskStore.run.startedAt, "等待任务启动") }}</strong>
            </article>
            <article>
              <small>输出目录</small>
              <strong>{{ outputDirLabel }}</strong>
            </article>
          </div>
        </div>

        <section class="overview-stack__logs">
          <header class="section-header">
            <div>
              <p class="section-kicker">日志</p>
              <h3>最近日志</h3>
            </div>
            <button class="mini-link" @click="appStore.setPage('logs')">打开日志中心</button>
          </header>
          <LogConsole :items="taskStore.recentLogs" />
        </section>
      </section>

      <section class="surface status-wall">
        <header class="section-header">
          <div>
            <p class="section-kicker">阶段</p>
            <h3>阶段状态</h3>
          </div>
          <span class="mono">{{ runStatusText }}</span>
        </header>
        <div class="stage-stack">
          <StageCard :stage="taskStore.stages.links" />
          <StageCard :stage="taskStore.stages.pdf" />
          <StageCard :stage="taskStore.stages.extract" />
        </div>
      </section>
    </div>

    <section class="surface live-strip">
      <header class="section-header">
        <div>
          <p class="section-kicker">实时抓取</p>
          <h3>公告链接抓取实时进度</h3>
        </div>
        <span class="mono">{{ liveCrawlLabel }}</span>
      </header>

      <div class="live-layout">
        <article class="live-chart-card">
          <BaseChart :option="liveYearOption" />
        </article>

        <div class="live-grid">
          <article class="live-card live-card--accent">
            <small>当前年份</small>
            <strong>{{ taskStore.liveCrawl?.currentYear ?? "-" }}</strong>
            <span>{{ yearStepLabel }}</span>
          </article>

          <article class="live-card">
            <small>当前区间</small>
            <strong>{{ taskStore.liveCrawl?.currentWindow || "-" }}</strong>
            <span>{{ windowStepLabel }}</span>
          </article>

          <article class="live-card">
            <small>公告数量</small>
            <strong>{{ resolvedLiveTotal }}</strong>
            <span>运行中按当前任务实时结果展示</span>
          </article>

          <article class="live-card">
            <small>当前年份数量</small>
            <strong>{{ currentYearCount }}</strong>
            <span>当前年份累计数量</span>
          </article>
        </div>
      </div>
    </section>

    <div v-if="taskStore.hasVisualizationData" class="metrics-grid">
      <article class="surface chart-card chart-card--pdf">
        <header class="section-header section-header--chart">
          <div>
            <p class="section-kicker">PDF</p>
            <h3>PDF 下载实时进度</h3>
          </div>
          <div class="chart-header-right">
            <div class="view-switch">
              <button :class="{ active: pdfView === 'stacked' }" @click="pdfView = 'stacked'">堆叠柱状</button>
              <button :class="{ active: pdfView === 'trend' }" @click="pdfView = 'trend'">趋势曲线</button>
            </div>
            <div class="chart-header-meta">
              <span class="speed-badge speed-badge--pdf">{{ pdfSpeedLabel }}</span>
              <span class="chart-caption">{{ pdfView === "stacked" ? "按年份分布 · 堆叠统计" : "按年份趋势 · 完成量与目标量" }}</span>
            </div>
          </div>
        </header>
        <div class="summary-grid">
          <article class="summary-card summary-card--strong">
            <small>总量</small>
            <strong>{{ pdfSummary.total }}</strong>
            <span>本阶段目标总数</span>
          </article>
          <article class="summary-card">
            <small>已完成</small>
            <strong>{{ pdfSummary.completed }}</strong>
            <span>{{ pdfSummary.percentText }}</span>
          </article>
          <article class="summary-card">
            <small>当前高亮年份</small>
            <strong>{{ pdfSummary.activeYearText }}</strong>
            <span>{{ pdfSummary.activeYearSubtext }}</span>
          </article>
          <article class="summary-card">
            <small>失败 / 跳过</small>
            <strong>{{ pdfSummary.failedSkipped }}</strong>
            <span>异常与跳过合计</span>
          </article>
        </div>
        <BaseChart :option="pdfOption" />
      </article>

      <article class="surface chart-card chart-card--extract">
        <header class="section-header section-header--chart">
          <div>
            <p class="section-kicker">提取</p>
            <h3>文本提取实时进度</h3>
          </div>
          <div class="chart-header-right">
            <div class="view-switch">
              <button :class="{ active: extractView === 'stacked' }" @click="extractView = 'stacked'">堆叠柱状</button>
              <button :class="{ active: extractView === 'trend' }" @click="extractView = 'trend'">趋势曲线</button>
            </div>
            <div class="chart-header-meta">
              <span class="speed-badge speed-badge--extract">{{ extractSpeedLabel }}</span>
              <span class="chart-caption">{{ extractView === "stacked" ? "按年份分布 · 堆叠统计" : "按年份趋势 · 完成量与目标量" }}</span>
            </div>
          </div>
        </header>
        <div class="summary-grid">
          <article class="summary-card summary-card--strong">
            <small>总量</small>
            <strong>{{ extractSummary.total }}</strong>
            <span>本阶段目标总数</span>
          </article>
          <article class="summary-card">
            <small>已完成</small>
            <strong>{{ extractSummary.completed }}</strong>
            <span>{{ extractSummary.percentText }}</span>
          </article>
          <article class="summary-card">
            <small>当前高亮年份</small>
            <strong>{{ extractSummary.activeYearText }}</strong>
            <span>{{ extractSummary.activeYearSubtext }}</span>
          </article>
          <article class="summary-card">
            <small>失败数量</small>
            <strong>{{ extractSummary.failed }}</strong>
            <span>提取异常总数</span>
          </article>
        </div>
        <BaseChart :option="extractOption" />
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import BaseChart from "@/components/BaseChart.vue";
import LogConsole from "@/components/LogConsole.vue";
import StageCard from "@/components/StageCard.vue";
import { formatDateTime } from "@/services/datetime";
import { getErrorMessage } from "@/services/errors";
import { useAppStore } from "@/stores/app";
import { useTaskStore } from "@/stores/task";
import type { RunMode } from "@/services/types";

const taskStore = useTaskStore();
const appStore = useAppStore();
const displayedProgress = ref(0);
const pdfView = ref<"stacked" | "trend">("stacked");
const extractView = ref<"stacked" | "trend">("stacked");
let animationFrameId = 0;

const progressPercentText = computed(() => `${Math.round(displayedProgress.value * 100)}%`);
const progressGaugeOption = computed(() => ({
  backgroundColor: "transparent",
  tooltip: {
    formatter: "{a} <br/>{b} : {c}%",
  },
  series: [
    {
      name: "Progress",
      type: "gauge",
      min: 0,
      max: 100,
      startAngle: 225,
      endAngle: -45,
      progress: {
        show: true,
        width: 9,
        roundCap: false,
      },
      axisLine: {
        lineStyle: {
          width: 9,
          color: [[1, "#e5e7eb"]],
        },
      },
      radius: "86%",
      center: ["50%", "56%"],
      pointer: {
        show: true,
        length: "48%",
        width: 4,
        itemStyle: {
          color: "#597ef7",
        },
      },
      anchor: {
        show: false,
      },
      itemStyle: {
        color: "#597ef7",
      },
      axisTick: {
        show: true,
        splitNumber: 5,
        distance: -12,
        length: 7,
        lineStyle: {
          color: "#6b7280",
          width: 1,
        },
      },
      splitLine: {
        show: true,
        distance: -14,
        length: 14,
        lineStyle: {
          color: "#6b7280",
          width: 1.6,
        },
      },
      axisLabel: {
        distance: -34,
        color: "#6b7280",
        fontSize: 12,
        fontWeight: 500,
      },
      title: {
        show: true,
        offsetCenter: [0, "46%"],
        fontSize: 14,
        fontWeight: 500,
        color: "#6b7280",
      },
      detail: {
        valueAnimation: true,
        offsetCenter: [0, "70%"],
        fontSize: 26,
        fontWeight: 700,
        color: "#374151",
        formatter: "{value}",
      },
      data: [
        {
          value: Math.round(displayedProgress.value * 100),
          name: "进度",
        },
      ],
    },
  ],
}));

const COLORS = {
  teal: "#15847a",
  tealLight: "#3fb7ab",
  blue: "#3c6df0",
  blueLight: "#6b93ff",
  red: "#ef4444",
  redLight: "#fb7185",
  orange: "#f59e0b",
  orangeLight: "#fbbf24",
  grid: "rgba(148, 163, 184, 0.18)",
  axis: "#64748b",
  text: "#334155",
};

function gradientColor(top: string, bottom: string) {
  return {
    type: "linear",
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: top },
      { offset: 1, color: bottom },
    ],
  };
}

function makeTooltipFormatter(mode: "live" | "pdf" | "extract") {
  return (params: any[]) => {
    const items = Array.isArray(params) ? params : [params];
    if (!items.length) return "";
    const title = items[0]?.axisValueLabel || items[0]?.name || "";
    const lines = items
      .filter((item) => Number(item?.value || 0) > 0 || mode === "live")
      .map((item) => {
        const marker = `<span style="display:inline-block;width:10px;height:10px;border-radius:999px;background:${item.color};margin-right:8px;"></span>`;
        return `${marker}${item.seriesName}：<b>${Number(item.value || 0)}</b>`;
      });
    return `
      <div style="min-width:160px">
        <div style="margin-bottom:8px;font-weight:700;color:#0f172a;">${title}</div>
        ${lines.join("<br/>")}
      </div>
    `;
  };
}

function baseBarOption(categories: string[]) {
  return {
    backgroundColor: "transparent",
    animationDurationUpdate: 240,
    animationEasingUpdate: "cubicOut",
    legend: {
      bottom: 0,
      itemWidth: 14,
      itemHeight: 14,
      icon: "roundRect",
      textStyle: {
        color: COLORS.axis,
        fontSize: 13,
        fontWeight: 600,
      },
    },
    grid: {
      left: 26,
      right: 10,
      top: 26,
      bottom: 52,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: categories,
      axisLabel: {
        color: COLORS.axis,
        fontSize: 12,
        margin: 12,
      },
      axisLine: {
        lineStyle: {
          color: "rgba(148, 163, 184, 0.35)",
        },
      },
      axisTick: {
        show: false,
      },
    },
    yAxis: {
      type: "value",
      axisLabel: {
        color: COLORS.axis,
        fontSize: 12,
        margin: 12,
      },
      axisLine: {
        show: false,
      },
      axisTick: {
        show: false,
      },
      splitLine: {
        lineStyle: {
          color: COLORS.grid,
          type: "dashed",
        },
      },
    },
  };
}

function findActiveBucket(buckets: any[]) {
  return buckets.find((item: any) => item?.active) || null;
}

function compactValueLabel(position: "inside" | "insideTop" | "top" = "insideTop") {
  return {
    show: true,
    position,
    color: position === "top" ? COLORS.text : "#ffffff",
    fontSize: 11,
    fontWeight: 700,
    distance: 6,
    formatter: ({ value }: any) => (Number(value || 0) > 0 ? String(value) : ""),
  };
}

async function start(mode: RunMode) {
  const modeText = {
    links: "公告链接抓取",
    pdf: "PDF 下载",
    extract: "文本提取",
    pipeline: "完整流程",
  }[mode];
  appStore.showAlert(`已提交${modeText}任务，正在启动...`, "info", "任务通知");
  try {
    await taskStore.startRun(mode);
    appStore.showAlert(`${modeText}任务已启动`, "success", "任务通知");
  } catch (error) {
    appStore.showAlert(getErrorMessage(error, "启动任务失败"), "error");
  }
}

async function togglePause() {
  try {
    if (taskStore.isResumable) {
      await taskStore.resumeRun();
      appStore.showAlert("任务已继续", "success");
      return;
    }
    if (taskStore.isPausable) {
      await taskStore.pauseRun();
      appStore.showAlert("任务已暂停", "info");
    }
  } catch (error) {
    appStore.showAlert(getErrorMessage(error, "操作失败"), "error");
  }
}

async function terminateRun() {
  try {
    await taskStore.cancelRun();
    appStore.showAlert("任务终止中", "info");
  } catch (error) {
    appStore.showAlert(getErrorMessage(error, "终止任务失败"), "error");
  }
}

const runStatusText = computed(() => ({
  idle: "空闲",
  running: "运行中",
  paused: "已暂停",
  completed: "已完成",
  failed: "失败",
  cancelling: "终止中",
  cancelled: "已终止",
}[taskStore.run.status]));

const modeLabel = computed(() => ({
  links: "公告链接抓取",
  pdf: "PDF 下载",
  extract: "文本提取",
  pipeline: "完整流程",
  null: "尚未启动",
}[String(taskStore.run.mode)]));

const progressLogicLabel = computed(() => {
  if (!taskStore.run.mode) return "等待任务启动";
  if (taskStore.run.mode === "pipeline") {
    return "按当前执行阶段计算";
  }
  return "按当前单任务计算";
});

const outputDirLabel = computed(() => {
  const outputs = taskStore.run.outputs || {};
  if (taskStore.run.mode === "extract") return outputs.textOutputDir || "-";
  if (taskStore.run.mode === "pipeline") return outputs.textOutputDir || outputs.annualReportDir || "-";
  return outputs.annualReportDir || "-";
});

const resolvedLiveYearBuckets = computed(() => taskStore.liveYearBuckets || []);
const resolvedLiveTotal = computed(() => taskStore.liveYearTotal || 0);
const livePdfBuckets = computed(() => taskStore.livePdf?.yearBuckets || []);
const liveExtractBuckets = computed(() => taskStore.liveExtract?.yearBuckets || []);

const liveCrawlLabel = computed(() => {
  if (taskStore.run.status === "paused") return "任务已暂停";
  if (taskStore.run.currentStage !== "links" && taskStore.run.status !== "completed") {
    return "链接阶段空闲";
  }
  if (!taskStore.liveCrawl) return "等待实时数据";
  return `${Math.round(Number(taskStore.liveCrawl.overallPercent || 0) * 100)}%`;
});

const yearStepLabel = computed(() => {
  if (!taskStore.liveCrawl) return "等待实时数据";
  return `第 ${taskStore.liveCrawl.currentYearIndex || 0} / ${taskStore.liveCrawl.yearTotal || 0} 年`;
});

const windowStepLabel = computed(() => {
  if (!taskStore.liveCrawl) return "等待区间信息";
  return `${taskStore.liveCrawl.rangeCurrent || 0} / ${taskStore.liveCrawl.rangeTotal || 0}`;
});

const currentYearCount = computed(() => {
  const currentYear = taskStore.liveCrawl?.currentYear;
  if (!currentYear) return 0;
  const bucket = resolvedLiveYearBuckets.value.find((item: any) => Number(item.year) === Number(currentYear));
  return Number(bucket?.count || 0);
});

const pdfSpeedLabel = computed(() => {
  const speed = Number(taskStore.livePdf?.speedPerMinute || 0);
  const eta = Number(taskStore.livePdf?.etaSeconds || 0);
  const speedText = speed > 0 ? `${Math.round(speed)} 份/分钟` : "速度统计中";
  const etaText = eta > 0 ? `，预计剩余 ${Math.round(eta)} 秒` : "";
  return `${speedText}${etaText}`;
});

const extractSpeedLabel = computed(() => {
  const speed = Number(taskStore.liveExtract?.speedPerMinute || 0);
  const eta = Number(taskStore.liveExtract?.etaSeconds || 0);
  const speedText = speed > 0 ? `${Math.round(speed)} 份/分钟` : "速度统计中";
  const etaText = eta > 0 ? `，预计剩余 ${Math.round(eta)} 秒` : "";
  return `${speedText}${etaText}`;
});

const pdfSummary = computed(() => {
  const buckets = livePdfBuckets.value;
  const active = findActiveBucket(buckets);
  const total = buckets.reduce((sum: number, item: any) => sum + Number(item.total || 0), 0);
  const completed = buckets.reduce((sum: number, item: any) => sum + Number(item.completed || 0), 0);
  const failed = buckets.reduce((sum: number, item: any) => sum + Number(item.failed || 0), 0);
  const skipped = buckets.reduce((sum: number, item: any) => sum + Number(item.skipped || 0), 0);
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0;
  return {
    total,
    completed,
    failedSkipped: `${failed + skipped}`,
    percentText: total > 0 ? `${percent}% 已完成` : "等待数据",
    activeYearText: active ? String(active.year) : "-",
    activeYearSubtext: active ? `该年已完成 ${active.completed || 0} / ${active.total || 0}` : "暂无高亮年份",
  };
});

const extractSummary = computed(() => {
  const buckets = liveExtractBuckets.value;
  const active = findActiveBucket(buckets);
  const total = buckets.reduce((sum: number, item: any) => sum + Number(item.total || 0), 0);
  const completed = buckets.reduce((sum: number, item: any) => sum + Number(item.completed || 0), 0);
  const failed = buckets.reduce((sum: number, item: any) => sum + Number(item.failed || 0), 0);
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0;
  return {
    total,
    completed,
    failed,
    percentText: total > 0 ? `${percent}% 已完成` : "等待数据",
    activeYearText: active ? String(active.year) : "-",
    activeYearSubtext: active ? `该年已完成 ${active.completed || 0} / ${active.total || 0}` : "暂无高亮年份",
  };
});

const liveYearOption = computed(() => {
  const categories = resolvedLiveYearBuckets.value.map((item: any) => String(item.year));
  return {
    ...baseBarOption(categories),
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(255,255,255,0.96)",
      borderColor: "rgba(148,163,184,0.2)",
      borderWidth: 1,
      textStyle: { color: COLORS.text },
      extraCssText: "box-shadow: 0 16px 40px rgba(15, 23, 42, 0.14); border-radius: 14px;",
      formatter: makeTooltipFormatter("live"),
    },
    legend: { show: false },
    series: [{
      name: "公告数",
      type: "bar",
      barWidth: 28,
      showBackground: true,
      backgroundStyle: {
        color: "rgba(148, 163, 184, 0.08)",
        borderRadius: [14, 14, 0, 0],
      },
      label: {
        show: true,
        position: "top",
        color: COLORS.text,
        fontSize: 12,
        fontWeight: 700,
        formatter: ({ value }: any) => (Number(value || 0) > 0 ? String(value) : ""),
      },
      itemStyle: {
        borderRadius: [14, 14, 4, 4],
        shadowBlur: 18,
        shadowColor: "rgba(21, 132, 122, 0.18)",
      },
      data: resolvedLiveYearBuckets.value.map((item: any) => ({
        value: Number(item.count || 0),
        itemStyle: {
          color: item.active
            ? gradientColor("#1f9d8f", "#0f766e")
            : item.status === "completed"
              ? gradientColor("#4f7ef7", "#2d5bdb")
              : gradientColor("#c5d2e6", "#94a3b8"),
        },
      })),
    }],
  };
});

const pdfOption = computed(() => {
  const categories = livePdfBuckets.value.map((item: any) => String(item.year));
  const activeYear = findActiveBucket(livePdfBuckets.value)?.year;
  const completedLine = livePdfBuckets.value.map((item: any) => Number(item.completed || 0));
  const totalLine = livePdfBuckets.value.map((item: any) => Number(item.total || 0));

  if (pdfView.value === "trend") {
    return {
      ...baseBarOption(categories),
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(255,255,255,0.97)",
        borderColor: "rgba(148,163,184,0.2)",
        borderWidth: 1,
        textStyle: { color: COLORS.text },
        extraCssText: "box-shadow: 0 16px 40px rgba(15, 23, 42, 0.14); border-radius: 14px;",
        formatter: makeTooltipFormatter("pdf"),
      },
      series: [
        {
          name: "目标量",
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 7,
          lineStyle: { width: 2, type: "dashed", color: COLORS.blue },
          itemStyle: { color: COLORS.blue },
          data: totalLine,
        },
        {
          name: "已完成",
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 9,
          areaStyle: {
            color: gradientColor("rgba(63,183,171,0.28)", "rgba(63,183,171,0.02)"),
          },
          lineStyle: { width: 3, color: COLORS.teal },
          itemStyle: { color: COLORS.teal, borderColor: "#fff", borderWidth: 2 },
          data: completedLine.map((value, index) => ({
            value,
            itemStyle: Number(categories[index]) === Number(activeYear) ? {
              shadowBlur: 18,
              shadowColor: "rgba(21,132,122,0.35)",
            } : undefined,
          })),
        },
      ],
    };
  }

  return {
    ...baseBarOption(categories),
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(15, 23, 42, 0.04)" } },
      backgroundColor: "rgba(255,255,255,0.97)",
      borderColor: "rgba(148,163,184,0.2)",
      borderWidth: 1,
      textStyle: { color: COLORS.text },
      extraCssText: "box-shadow: 0 16px 40px rgba(15, 23, 42, 0.14); border-radius: 14px;",
      formatter: makeTooltipFormatter("pdf"),
    },
    series: [
      {
        name: "已完成（下载+已存在）",
        type: "bar",
        stack: "pdf",
        barWidth: 24,
        itemStyle: {
          color: gradientColor(COLORS.tealLight, COLORS.teal),
          borderRadius: [10, 10, 0, 0],
        },
        data: livePdfBuckets.value.map((item: any) => ({
          value: Number(item.downloaded || 0) + Number(item.exists || 0),
          itemStyle: Number(item.year) === Number(activeYear) ? {
            borderColor: "rgba(255,255,255,0.95)",
            borderWidth: 2,
            shadowBlur: 24,
            shadowColor: "rgba(21, 132, 122, 0.28)",
          } : undefined,
        })),
      },
      {
        name: "失败",
        type: "bar",
        stack: "pdf",
        itemStyle: {
          color: gradientColor(COLORS.redLight, COLORS.red),
        },
        data: livePdfBuckets.value.map((item: any) => ({
          value: Number(item.failed || 0),
          itemStyle: Number(item.year) === Number(activeYear) ? {
            borderColor: "rgba(255,255,255,0.95)",
            borderWidth: 2,
          } : undefined,
        })),
      },
      {
        name: "跳过",
        type: "bar",
        stack: "pdf",
        label: {
          ...compactValueLabel("top"),
          formatter: (_: any) => "",
        },
        itemStyle: {
          color: gradientColor(COLORS.orangeLight, COLORS.orange),
          borderRadius: [10, 10, 0, 0],
        },
        data: livePdfBuckets.value.map((item: any) => ({
          value: Number(item.skipped || 0),
          label: {
            ...compactValueLabel("top"),
            formatter: () => {
              const total = Number(item.downloaded || 0) + Number(item.exists || 0) + Number(item.failed || 0) + Number(item.skipped || 0);
              return total > 0 ? String(total) : "";
            },
          },
          itemStyle: Number(item.year) === Number(activeYear) ? {
            borderColor: "rgba(255,255,255,0.95)",
            borderWidth: 2,
            shadowBlur: 20,
            shadowColor: "rgba(245, 158, 11, 0.25)",
          } : undefined,
        })),
      },
    ],
  };
});

const extractOption = computed(() => {
  const categories = liveExtractBuckets.value.map((item: any) => String(item.year));
  const activeYear = findActiveBucket(liveExtractBuckets.value)?.year;
  const completedLine = liveExtractBuckets.value.map((item: any) => Number(item.completed || 0));
  const totalLine = liveExtractBuckets.value.map((item: any) => Number(item.total || 0));

  if (extractView.value === "trend") {
    return {
      ...baseBarOption(categories),
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(255,255,255,0.97)",
        borderColor: "rgba(148,163,184,0.2)",
        borderWidth: 1,
        textStyle: { color: COLORS.text },
        extraCssText: "box-shadow: 0 16px 40px rgba(15, 23, 42, 0.14); border-radius: 14px;",
        formatter: makeTooltipFormatter("extract"),
      },
      series: [
        {
          name: "目标量",
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 7,
          lineStyle: { width: 2, type: "dashed", color: COLORS.blue },
          itemStyle: { color: COLORS.blue },
          data: totalLine,
        },
        {
          name: "已完成",
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 9,
          areaStyle: {
            color: gradientColor("rgba(58,155,214,0.24)", "rgba(58,155,214,0.02)"),
          },
          lineStyle: { width: 3, color: "#155e75" },
          itemStyle: { color: "#155e75", borderColor: "#fff", borderWidth: 2 },
          data: completedLine.map((value, index) => ({
            value,
            itemStyle: Number(categories[index]) === Number(activeYear) ? {
              shadowBlur: 18,
              shadowColor: "rgba(21,94,117,0.32)",
            } : undefined,
          })),
        },
      ],
    };
  }

  return {
    ...baseBarOption(categories),
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(15, 23, 42, 0.04)" } },
      backgroundColor: "rgba(255,255,255,0.97)",
      borderColor: "rgba(148,163,184,0.2)",
      borderWidth: 1,
      textStyle: { color: COLORS.text },
      extraCssText: "box-shadow: 0 16px 40px rgba(15, 23, 42, 0.14); border-radius: 14px;",
      formatter: makeTooltipFormatter("extract"),
    },
    series: [
      {
        name: "已完成（提取+已存在）",
        type: "bar",
        stack: "extract",
        barWidth: 24,
        itemStyle: {
          color: gradientColor("#3a9bd6", "#155e75"),
          borderRadius: [10, 10, 0, 0],
        },
        data: liveExtractBuckets.value.map((item: any) => ({
          value: Number(item.extracted || 0) + Number(item.exists || 0),
          itemStyle: Number(item.year) === Number(activeYear) ? {
            borderColor: "rgba(255,255,255,0.95)",
            borderWidth: 2,
            shadowBlur: 24,
            shadowColor: "rgba(21, 94, 117, 0.26)",
          } : undefined,
        })),
      },
      {
        name: "失败",
        type: "bar",
        stack: "extract",
        label: {
          ...compactValueLabel("top"),
          formatter: (_: any) => "",
        },
        itemStyle: {
          color: gradientColor(COLORS.redLight, COLORS.red),
          borderRadius: [10, 10, 0, 0],
        },
        data: liveExtractBuckets.value.map((item: any) => ({
          value: Number(item.failed || 0),
          label: {
            ...compactValueLabel("top"),
            formatter: () => {
              const total = Number(item.extracted || 0) + Number(item.exists || 0) + Number(item.failed || 0);
              return total > 0 ? String(total) : "";
            },
          },
          itemStyle: Number(item.year) === Number(activeYear) ? {
            borderColor: "rgba(255,255,255,0.95)",
            borderWidth: 2,
            shadowBlur: 20,
            shadowColor: "rgba(239, 68, 68, 0.22)",
          } : undefined,
        })),
      },
    ],
  };
});

watch(
  () => taskStore.currentTaskProgress,
  (target) => {
    const start = displayedProgress.value;
    const end = target;
    const startedAt = performance.now();
    const duration = 180;
    cancelAnimationFrame(animationFrameId);
    const tick = (now: number) => {
      const elapsed = Math.min((now - startedAt) / duration, 1);
      const eased = 1 - Math.pow(1 - elapsed, 3);
      displayedProgress.value = start + (end - start) * eased;
      if (elapsed < 1) animationFrameId = requestAnimationFrame(tick);
    };
    animationFrameId = requestAnimationFrame(tick);
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  cancelAnimationFrame(animationFrameId);
  taskStore.stopIncrementalPolling();
});
</script>

<style scoped>
.console-page { --command-log-panel-height: 560px; display: grid; gap: 24px; }
.console-head { display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 28px; }
.console-head__copy { display: grid; align-content: center; min-width: 0; }
.console-head__copy h2 { margin: 8px 0 12px; font-size: 40px; line-height: 1.02; }
.console-head__copy p:last-child { margin: 0; max-width: 760px; color: var(--muted); line-height: 1.7; }
.console-head__actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; align-content: start; }
.action { min-height: 58px; border: 0; border-radius: 18px; font-weight: 700; cursor: pointer; }
.action.subtle { background: #edf2ff; color: #1d4ed8; }
.action.primary { background: linear-gradient(135deg, #0f766e, #155e75); color: white; }
.action.warning { background: #fff7ed; color: #c2410c; }
.action.danger { background: #991b1b; color: white; }
.action:disabled { opacity: 0.45; cursor: not-allowed; }
.console-grid { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 24px; align-items: stretch; }
.overview-stack { display: flex; flex-direction: column; justify-content: flex-start; gap: 22px; height: 100%; }
.overview-stack__logs { display: grid; grid-template-rows: auto minmax(0, 1fr); gap: 14px; height: var(--command-log-panel-height); min-height: var(--command-log-panel-height); max-height: var(--command-log-panel-height); min-width: 0; flex: none; }
.overview-stack__logs :deep(.console) { height: 100%; min-height: 100%; max-height: 100%; }
.focus-panel { display: grid; grid-template-columns: 1fr; gap: 20px; align-items: start; flex: 1; min-height: 0; }
.focus-panel__gauge { display: grid; place-items: center; width: 100%; }
.gauge-card { width: 100%; max-width: 560px; padding-top: 0; }
.gauge-card :deep(.chart) { min-height: 320px; }
.focus-panel__meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; align-content: start; }
.focus-panel__meta article,.live-card { display: flex; flex-direction: column; justify-content: flex-start; min-height: 168px; padding: 18px 20px; border-radius: 20px; background: var(--panel-alt); box-sizing: border-box; }
.focus-panel__meta small,.live-card small { display: block; color: var(--muted); margin-bottom: 10px; }
.focus-panel__meta strong,.live-card strong { display: block; line-height: 1.4; }
.live-card span { display: block; margin-top: 10px; color: var(--muted); font-size: 13px; line-height: 1.5; }
.live-card--accent { background: linear-gradient(135deg, rgba(15,118,110,0.14), rgba(37,99,235,0.1)); }
.section-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; margin-bottom: 18px; }
.section-header h3 { margin: 4px 0 0; font-size: 24px; }
.section-header--chart { margin-bottom: 10px; }
.chart-header-right { display: grid; justify-items: end; gap: 10px; }
.chart-header-meta { display: grid; justify-items: end; gap: 8px; }
.view-switch { display: inline-flex; gap: 6px; padding: 5px; border-radius: 999px; background: rgba(241, 245, 249, 0.94); border: 1px solid rgba(226, 232, 240, 0.95); }
.view-switch button { border: 0; min-height: 34px; padding: 0 14px; border-radius: 999px; background: transparent; color: #64748b; font-size: 13px; font-weight: 700; cursor: pointer; transition: all .18s ease; }
.view-switch button.active { background: linear-gradient(135deg, rgba(15,118,110,0.12), rgba(59,130,246,0.12)); color: #0f766e; box-shadow: inset 0 0 0 1px rgba(15,118,110,0.12); }
.speed-badge { display: inline-flex; align-items: center; min-height: 40px; padding: 0 16px; border-radius: 999px; font-size: 14px; font-weight: 700; letter-spacing: 0.01em; }
.speed-badge--pdf { background: linear-gradient(135deg, rgba(21, 132, 122, 0.14), rgba(60, 109, 240, 0.12)); color: #155e75; }
.speed-badge--extract { background: linear-gradient(135deg, rgba(21, 94, 117, 0.12), rgba(99, 102, 241, 0.12)); color: #334155; }
.chart-caption { color: var(--muted); font-size: 12px; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 6px 0 8px; }
.summary-card { position: relative; overflow: hidden; min-height: 90px; padding: 16px 18px; border-radius: 18px; border: 1px solid rgba(226, 232, 240, 0.9); background: linear-gradient(180deg, rgba(255,255,255,0.9), rgba(248,250,252,0.9)); }
.summary-card::after { content: ""; position: absolute; inset: 0; background: radial-gradient(circle at top right, rgba(255,255,255,0.8), transparent 34%); pointer-events: none; }
.summary-card small { display: block; margin-bottom: 8px; color: var(--muted); }
.summary-card strong { display: block; font-size: 28px; line-height: 1.1; color: #0f172a; }
.summary-card span { display: block; margin-top: 8px; color: #64748b; font-size: 12px; line-height: 1.45; }
.summary-card--strong { background: linear-gradient(135deg, rgba(15,118,110,0.12), rgba(59,130,246,0.08)); border-color: rgba(125, 211, 252, 0.32); }
.mono { font-family: Consolas, "Courier New", monospace; color: var(--muted); }
.stage-stack { display: grid; gap: 16px; align-content: start; }
.status-wall,.live-strip { display: grid; gap: 14px; }
.status-wall { height: 100%; align-content: start; }
.live-layout { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(0, 0.9fr); gap: 18px; }
.live-chart-card,.chart-card { position: relative; overflow: hidden; }
.live-chart-card::before,.chart-card::before { content: ""; position: absolute; inset: 0; background: radial-gradient(circle at top right, rgba(255,255,255,0.75), transparent 38%); pointer-events: none; }
.live-chart-card { border-radius: 24px; background: linear-gradient(180deg, rgba(247, 250, 252, 0.92), rgba(241, 245, 249, 0.85)); padding: 10px 14px 4px; border: 1px solid rgba(226, 232, 240, 0.75); }
.chart-card { border: 1px solid rgba(226, 232, 240, 0.75); background: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(248,250,252,0.92)); box-shadow: 0 18px 44px rgba(15, 23, 42, 0.06); }
.chart-card--pdf { background-image: radial-gradient(circle at top right, rgba(59,130,246,0.08), transparent 34%), linear-gradient(180deg, rgba(255,255,255,0.96), rgba(248,250,252,0.92)); }
.chart-card--extract { background-image: radial-gradient(circle at top right, rgba(21,132,122,0.08), transparent 34%), linear-gradient(180deg, rgba(255,255,255,0.96), rgba(248,250,252,0.92)); }
.live-chart-card,.chart-card,.status-wall,.live-strip,.overview-stack { min-width: 0; }
.live-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; grid-auto-rows: 168px; }
.metrics-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px; }
.mini-link { border: 0; background: #eef2ff; color: #1d4ed8; border-radius: 999px; padding: 10px 14px; cursor: pointer; }
@media (max-width: 1180px) {
  .console-head,.console-grid,.metrics-grid,.live-layout,.focus-panel,.focus-panel__meta,.live-grid,.summary-grid { grid-template-columns: 1fr; }
  .console-head__copy h2 { font-size: 36px; }
  .console-page { --command-log-panel-height: 460px; }
  .overview-stack__logs { height: var(--command-log-panel-height); min-height: var(--command-log-panel-height); max-height: var(--command-log-panel-height); }
  .gauge-card { max-width: 100%; }
  .gauge-card :deep(.chart) { min-height: 280px; }
  .chart-header-right,.chart-header-meta { justify-items: start; }
}
</style>
