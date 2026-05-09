import { defineStore } from "pinia";
import { bridge } from "@/services/bridge";
import { getErrorMessage } from "@/services/errors";
import type { AppSettings } from "@/services/types";
import { useAppStore } from "@/stores/app";

export const useSettingsStore = defineStore("settings", {
  state: () => ({
    data: null as AppSettings | null,
    loading: false,
    saving: false,
    dirty: false,
  }),
  actions: {
    async load() {
      this.loading = true;
      try {
        this.data = await bridge.getSettings();
        this.dirty = false;
      } finally {
        this.loading = false;
      }
    },
    async save() {
      if (!this.data || this.saving) return;
      const appStore = useAppStore();
      this.saving = true;
      try {
        await bridge.updateSettings(this.data);
        this.dirty = false;
        appStore.showAlert("配置已保存", "success");
      } catch (error) {
        appStore.showAlert(getErrorMessage(error, "保存配置失败"), "error");
        throw error;
      } finally {
        this.saving = false;
      }
    },
    touch() {
      this.dirty = true;
    },
  },
});
