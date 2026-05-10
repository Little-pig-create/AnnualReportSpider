import { defineStore } from "pinia";
import { bridge } from "@/services/bridge";
import { getErrorMessage } from "@/services/errors";
import { useAppStore } from "@/stores/app";
import type { HistoryItem } from "@/services/types";

export const useHistoryStore = defineStore("history", {
  state: () => ({
    items: [] as HistoryItem[],
    loading: false,
    exporting: false,
    autoRefreshTimer: null as number | null,
  }),
  actions: {
    async load() {
      this.loading = true;
      try {
        const payload = await bridge.getRunHistory();
        this.items = payload.items || [];
      } finally {
        this.loading = false;
      }
    },
    startAutoRefresh(intervalMs = 2200) {
      if (this.autoRefreshTimer !== null) return;
      this.autoRefreshTimer = window.setInterval(() => {
        if (this.loading || this.exporting) return;
        this.load().catch(() => {});
      }, intervalMs);
    },
    stopAutoRefresh() {
      if (this.autoRefreshTimer === null) return;
      window.clearInterval(this.autoRefreshTimer);
      this.autoRefreshTimer = null;
    },
    async exportJson() {
      if (this.exporting) return;
      const appStore = useAppStore();
      this.exporting = true;
      try {
        const payload = await bridge.exportRunHistory();
        appStore.showAlert(`历史任务已导出：${payload.count} 条`, "success");
        await bridge.openPath(payload.path);
        return payload;
      } catch (error) {
        appStore.showAlert(getErrorMessage(error, "导出历史任务失败"), "error");
        throw error;
      } finally {
        this.exporting = false;
      }
    },
  },
});
