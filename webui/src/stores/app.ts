import { defineStore } from "pinia";
import type { PageKey, UpdateCheckResult } from "@/services/types";
import { bridge } from "@/services/bridge";

export type AppDialogType = "success" | "error" | "info" | "warning";

let notificationModulePromise: Promise<typeof import("element-plus/es/components/notification/index")> | null = null;
let messageBoxModulePromise: Promise<typeof import("element-plus/es/components/message-box/index")> | null = null;

function loadNotificationModule() {
  notificationModulePromise ||= import("element-plus/es/components/notification/index");
  return notificationModulePromise;
}

function loadMessageBoxModule() {
  messageBoxModulePromise ||= import("element-plus/es/components/message-box/index");
  return messageBoxModulePromise;
}

export const useAppStore = defineStore("app", {
  state: () => ({
    currentPage: "command" as PageKey,
    bridgeReady: false,
    loading: false,
    about: null as Record<string, any> | null,
    updateChecking: false,
    updateInfo: null as UpdateCheckResult | null,
  }),
  actions: {
    setPage(page: PageKey) {
      this.currentPage = page;
    },
    async loadAbout() {
      if (this.about) return;
      this.about = await bridge.getAbout();
    },
    async checkUpdate() {
      if (this.updateChecking) return this.updateInfo;
      this.updateChecking = true;
      try {
        const result = await bridge.checkUpdate();
        this.updateInfo = result;
        if (result.status === "available") {
          this.showAlert(`发现新版本：${result.latestVersion}`, "success", "版本更新");
        } else if (result.status === "current") {
          this.showAlert("当前已是最新版本", "info", "版本更新");
        } else {
          this.showAlert(result.message || "未能获取更新信息", "warning", "版本更新");
        }
        return result;
      } finally {
        this.updateChecking = false;
      }
    },
    showAlert(message: string, type: AppDialogType = "info", title?: string) {
      void loadNotificationModule()
        .then(({ ElNotification }) => {
          ElNotification({
            title: title || "系统通知",
            message,
            type,
            duration: 2600,
            position: "top-right",
          });
        })
        .catch(() => {});
    },
    async showConfirm(payload: {
      title: string;
      message: string;
      type?: AppDialogType;
      confirmText?: string;
      cancelText?: string;
    }) {
      const { ElMessageBox } = await loadMessageBoxModule();
      await ElMessageBox.confirm(payload.message, payload.title, {
        type: payload.type || "warning",
        confirmButtonText: payload.confirmText || "确认",
        cancelButtonText: payload.cancelText || "取消",
        distinguishCancelAndClose: true,
        closeOnClickModal: false,
      });
    },
  },
});
