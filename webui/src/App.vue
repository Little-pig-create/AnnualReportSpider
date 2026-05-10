<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="topbar__brand">
        <p class="topbar__eyebrow">REPORT SPIDER</p>
        <h1>桌面控制台</h1>
        <span>用于公告链接抓取、PDF 下载与文本提取的一体化桌面工作台。</span>
        <div class="topbar__author">
          <p class="topbar__author-title">开发者信息</p>
          <div class="topbar__author-tags">
            <div class="topbar__author-item topbar__author-item--highlight">
              <small>项目作者</small>
              <strong>xiaomaojian</strong>
            </div>
            <div class="topbar__author-item topbar__author-item--highlight topbar__author-item--version">
              <small>版本号</small>
              <strong>{{ appStore.about?.version || "-" }}</strong>
            </div>
            <a
              class="topbar__author-item topbar__author-item--link topbar__author-item--gitee"
              href="https://gitee.com/xiaozhusir/AnnualReportSpider"
              target="_blank"
              rel="noreferrer"
            >
              <small>项目仓库</small>
              <strong>https://gitee.com/xiaozhusir/AnnualReportSpider</strong>
            </a>
            <a
              class="topbar__author-item topbar__author-item--link topbar__author-item--github"
              href="https://github.com/Little-pig-create/AnnualReportSpider"
              target="_blank"
              rel="noreferrer"
            >
              <small>项目仓库</small>
              <strong>https://github.com/Little-pig-create/AnnualReportSpider</strong>
            </a>
          </div>
        </div>
      </div>

      <div class="topbar__meta">
        <div class="status-chip" :data-state="taskStore.run.status">
          <strong>{{ runStatusText }}</strong>
          <small>{{ currentStageText }}</small>
        </div>
        <div class="status-chip muted">
          <strong>{{ runModeText }}</strong>
          <small>{{ formatDateTime(taskStore.run.startedAt, "等待任务启动") }}</small>
        </div>
      </div>
    </header>

    <nav class="dock">
      <button
        v-for="item in navItems"
        :key="item.key"
        :class="{ active: appStore.currentPage === item.key }"
        @click="appStore.setPage(item.key)"
      >
        <span>{{ item.eyebrow }}</span>
        <strong>{{ item.label }}</strong>
      </button>
    </nav>

    <main class="content-frame">
      <component :is="currentPage" />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, watch } from "vue";
import { bridge } from "@/services/bridge";
import { formatDateTime } from "@/services/datetime";
import { getErrorMessage } from "@/services/errors";
import { mountDesktopEventBus } from "@/services/eventBus";
import { useAppStore } from "@/stores/app";
import { useHistoryStore } from "@/stores/history";
import { useSettingsStore } from "@/stores/settings";
import { useTaskStore } from "@/stores/task";
import type { PageKey } from "@/services/types";

const appStore = useAppStore();
const historyStore = useHistoryStore();
const settingsStore = useSettingsStore();
const taskStore = useTaskStore();

const pageMap = {
  command: defineAsyncComponent(() => import("@/pages/CommandCenter.vue")),
  workspace: defineAsyncComponent(() => import("@/pages/WorkspacePage.vue")),
  links: defineAsyncComponent(() => import("@/pages/LinksConfigPage.vue")),
  pdf: defineAsyncComponent(() => import("@/pages/PdfConfigPage.vue")),
  extract: defineAsyncComponent(() => import("@/pages/ExtractConfigPage.vue")),
  logs: defineAsyncComponent(() => import("@/pages/LogsPage.vue")),
  history: defineAsyncComponent(() => import("@/pages/HistoryPage.vue")),
  about: defineAsyncComponent(() => import("@/pages/AboutPage.vue")),
};

const navItems: Array<{ key: PageKey; label: string; eyebrow: string }> = [
  { key: "command", label: "任务总览", eyebrow: "总览" },
  { key: "workspace", label: "工作区", eyebrow: "路径" },
  { key: "links", label: "链接配置", eyebrow: "链接" },
  { key: "pdf", label: "PDF 配置", eyebrow: "PDF" },
  { key: "extract", label: "提取配置", eyebrow: "提取" },
  { key: "logs", label: "日志中心", eyebrow: "日志" },
  { key: "history", label: "历史任务", eyebrow: "历史" },
  { key: "about", label: "关于软件", eyebrow: "说明" },
];

const currentPage = computed(() => pageMap[appStore.currentPage]);

const runStatusText = computed(() => ({
  idle: "空闲",
  running: "运行中",
  paused: "已暂停",
  completed: "已完成",
  failed: "失败",
  cancelling: "终止中",
  cancelled: "已终止",
}[taskStore.run.status]));

const currentStageText = computed(() => ({
  links: "公告链接抓取",
  pdf: "PDF 下载",
  extract: "文本提取",
  null: taskStore.run.status === "paused" ? "任务暂停中" : "空闲",
}[String(taskStore.run.currentStage)]));

const runModeText = computed(() => ({
  links: "仅抓链接",
  pdf: "仅下载 PDF",
  extract: "仅提取文本",
  pipeline: "完整流程",
  null: "未启动",
}[String(taskStore.run.mode)]));

onMounted(async () => {
  mountDesktopEventBus(taskStore);
  taskStore.loadNotificationPrefs();
  const originalHandleEvent = taskStore.handleEvent.bind(taskStore);
  taskStore.handleEvent = ((event: any) => {
    if (event?.event === "app.close_requested") {
      void appStore.showConfirm({
        title: "确认关闭当前窗口",
        message: ["running", "paused", "cancelling"].includes(String(event?.data?.status || "idle"))
          ? "检测到当前仍有任务正在运行或暂停。关闭窗口后，已完成进度会保留，但当前执行步骤会被中断。"
          : "当前没有正在执行的任务，确认后将直接关闭窗口。",
        type: "warning",
        confirmText: "确认关闭",
        cancelText: "取消",
      }).then(async () => {
        try {
          await bridge.confirmCloseWindow();
        } catch (error) {
          appStore.showAlert(getErrorMessage(error, "关闭窗口失败"), "error");
        }
      }).catch(() => {
        bridge.cancelCloseWindowRequest().catch(() => {});
      });
      return;
    }
    originalHandleEvent(event);
  }) as typeof taskStore.handleEvent;

  try {
    await bridge.waitUntilReady();
    await Promise.all([
      appStore.loadAbout().catch(() => {}),
      settingsStore.load(),
      taskStore.hydrateActiveRun(),
      taskStore.loadVisualizationIndex().catch(() => {}),
      historyStore.load(),
      appStore.autoCheckUpdate().catch(() => {}),
    ]);
    appStore.bridgeReady = true;
  } catch (error) {
    appStore.bridgeReady = false;
    appStore.showAlert(getErrorMessage(error, "桥接初始化失败"), "error");
  }
});

watch(
  () => taskStore.run.status,
  (status) => {
    if (["running", "paused", "cancelling"].includes(status)) {
      historyStore.startAutoRefresh();
      return;
    }
    historyStore.stopAutoRefresh();
    historyStore.load().catch(() => {});
  },
  { immediate: true },
);
</script>
