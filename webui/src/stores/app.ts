import { defineStore } from "pinia";
import type { PageKey } from "@/services/types";
import { bridge } from "@/services/bridge";
import { ElMessageBox } from "element-plus/es/components/message-box/index";
import { ElNotification } from "element-plus/es/components/notification/index";

export type AppDialogType = "success" | "error" | "info" | "warning";

export const useAppStore = defineStore("app", {
  state: () => ({
    currentPage: "command" as PageKey,
    bridgeReady: false,
    loading: false,
    about: null as Record<string, any> | null,
  }),
  actions: {
    setPage(page: PageKey) {
      this.currentPage = page;
    },
    async loadAbout() {
      if (this.about) return;
      this.about = await bridge.getAbout();
    },
    showAlert(message: string, type: AppDialogType = "info", title?: string) {
      ElNotification({
        title: title || "系统通知",
        message,
        type,
        duration: 2600,
        position: "top-right",
      });
    },
    async showConfirm(payload: {
      title: string;
      message: string;
      type?: AppDialogType;
      confirmText?: string;
      cancelText?: string;
    }) {
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
