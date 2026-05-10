<template>
  <section class="editor-page" v-if="settings">
    <header class="editor-head">
      <div>
        <p class="section-kicker">工作区</p>
        <h2>路径与年份范围</h2>
        <p>这里集中配置项目路径和抓取年份范围，适合在批量运行前完成一次统一检查。</p>
      </div>
      <button class="save-button" @click="settingsStore.save()" :disabled="settingsStore.saving">
        {{ settingsStore.saving ? "保存中..." : "保存工作区" }}
      </button>
    </header>

    <div class="editor-layout">
      <section class="surface editor-card core-card">
        <header class="section-header">
          <div>
            <p class="section-kicker">路径</p>
            <h3>核心目录</h3>
          </div>
        </header>

        <div class="form-grid">
          <PathField
            label="项目根目录"
            v-model="settings.workspace.projectRoot"
            openable
            selectable
            @open="open(settings.workspace.projectRoot)"
            @select="pickDirectory('projectRoot')"
            @update:model-value="settingsStore.touch()"
          />
          <PathField
            label="年报输出目录"
            v-model="settings.workspace.annualReportDir"
            openable
            selectable
            @open="openResolved(settings.workspace.annualReportDir)"
            @select="pickDirectory('annualReportDir')"
            @update:model-value="settingsStore.touch()"
          />
          <PathField
            label="文本输出目录"
            v-model="settings.workspace.textOutputDir"
            openable
            selectable
            @open="openResolved(settings.workspace.textOutputDir)"
            @select="pickDirectory('textOutputDir')"
            @update:model-value="settingsStore.touch()"
          />
          <PathField
            label="状态目录"
            v-model="settings.workspace.stateDir"
            openable
            selectable
            @open="openResolved(settings.workspace.stateDir)"
            @select="pickDirectory('stateDir')"
            @update:model-value="settingsStore.touch()"
          />
        </div>
      </section>

      <div class="right-stack">
        <section class="surface editor-card range-card">
          <header class="section-header">
            <div>
              <p class="section-kicker">年份范围</p>
              <h3>抓取窗口</h3>
            </div>
          </header>

          <div class="range-grid">
            <label class="field">
              <span>开始年份</span>
              <input type="number" v-model.number="settings.workspace.startYear" @input="settingsStore.touch()" />
            </label>
            <label class="field">
              <span>结束年份</span>
              <input type="number" v-model.number="settings.workspace.endYear" @input="settingsStore.touch()" />
            </label>
          </div>

          <div class="range-band">
            <div class="range-band__line"></div>
            <div class="range-band__marker">
              <strong>{{ settings.workspace.startYear }}</strong>
              <span>开始</span>
            </div>
            <div class="range-band__marker">
              <strong>{{ settings.workspace.endYear }}</strong>
              <span>结束</span>
            </div>
          </div>
        </section>

        <section class="surface editor-card notify-card">
          <header class="section-header">
            <div>
              <p class="section-kicker">通知</p>
              <h3>任务完成提醒</h3>
            </div>
          </header>

          <label class="notify-item">
            <input
              type="checkbox"
              :checked="taskStore.notificationPrefs.desktopEnabled"
              @change="toggleDesktopNotify(($event.target as HTMLInputElement).checked)"
            />
            <div>
              <strong>系统通知</strong>
              <p>任务完成/失败/终止时显示系统消息通知</p>
            </div>
          </label>

          <label class="notify-item">
            <input
              type="checkbox"
              :checked="taskStore.notificationPrefs.soundEnabled"
              @change="toggleSoundNotify(($event.target as HTMLInputElement).checked)"
            />
            <div>
              <strong>提示音</strong>
              <p>任务结束时播放提示音（可与系统通知独立开关）</p>
            </div>
          </label>

          <p class="notify-status">通知权限：{{ notifyPermissionText }}</p>
          <div class="notify-actions">
            <button class="ghost-button" @click="testSound">测试提示音</button>
          </div>
        </section>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";
import PathField from "@/components/PathField.vue";
import { bridge } from "@/services/bridge";
import { getErrorMessage } from "@/services/errors";
import { useAppStore } from "@/stores/app";
import { useSettingsStore } from "@/stores/settings";
import { useTaskStore } from "@/stores/task";

const appStore = useAppStore();
const settingsStore = useSettingsStore();
const taskStore = useTaskStore();
const settings = computed(() => settingsStore.data);
const notifyPermissionText = computed(() => ({
  granted: "已授权",
  denied: "已拒绝",
  default: "未请求",
  unsupported: "当前环境不支持",
}[taskStore.notificationPrefs.permission]));

function open(path: string) {
  bridge.openPath(path);
}

function resolvePath(raw: string) {
  const value = (raw || "").trim();
  if (!settings.value) return value;
  if (!value) return settings.value.workspace.projectRoot;
  if (/^[a-zA-Z]:[\\/]/.test(value) || value.startsWith("\\\\") || value.startsWith("/")) {
    return value;
  }
  return `${settings.value.workspace.projectRoot}/${value}`.replace(/\\/g, "/");
}

function openResolved(path: string) {
  bridge.openPath(resolvePath(path));
}

async function pickDirectory(field: "projectRoot" | "annualReportDir" | "textOutputDir" | "stateDir") {
  if (!settings.value) return;
  const current = settings.value.workspace[field];
  const selected = await bridge.selectDirectory(resolvePath(current));
  if (!selected.path) return;
  settings.value.workspace[field] = selected.path;
  settingsStore.touch();
}

async function toggleDesktopNotify(enabled: boolean) {
  try {
    await taskStore.updateNotificationPrefs({ desktopEnabled: enabled });
    if (enabled && taskStore.notificationPrefs.desktopEnabled) {
      appStore.showAlert("系统通知已开启", "success");
      return;
    }
    if (enabled && !taskStore.notificationPrefs.desktopEnabled) {
      appStore.showAlert("系统通知未开启：请先授权通知权限", "warning");
      return;
    }
    appStore.showAlert("系统通知已关闭", "info");
  } catch (error) {
    appStore.showAlert(getErrorMessage(error, "更新系统通知设置失败"), "error");
  }
}

async function toggleSoundNotify(enabled: boolean) {
  try {
    await taskStore.updateNotificationPrefs({ soundEnabled: enabled });
    appStore.showAlert(enabled ? "提示音已开启" : "提示音已关闭", "info");
  } catch (error) {
    appStore.showAlert(getErrorMessage(error, "更新提示音设置失败"), "error");
  }
}

function testSound() {
  taskStore.playCompletionSound();
}
</script>

<style scoped>
.editor-page { display: grid; gap: 20px; }
.editor-head { display: flex; justify-content: space-between; gap: 20px; align-items: center; }
.editor-head h2 { margin: 2px 0 10px; font-size: 40px; }
.editor-head p:last-child { margin: 0; color: var(--muted); max-width: 820px; }
.save-button { border: 0; border-radius: 999px; min-height: 52px; padding: 0 22px; display: inline-flex; align-items: center; justify-content: center; background: linear-gradient(135deg, #0f766e, #155e75); color: white; font-weight: 700; cursor: pointer; }
.editor-layout { display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 24px; }
.right-stack { display: grid; gap: 24px; align-content: start; }
.editor-card { display: grid; gap: 14px; }
.form-grid { display: grid; gap: 16px; margin-top: -12px; }
.core-card { gap: 6px; align-content: start; }
.core-card .section-header { margin-bottom: -6px; }
.core-card .form-grid { margin-top: 0; }
.range-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.field { display: grid; gap: 10px; }
.field span { font-size: 13px; color: var(--muted); }
.field input { width: 100%; border: 1px solid var(--line); border-radius: 18px; padding: 14px 16px; background: #fff; }
.range-band { position: relative; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; padding-top: 24px; }
.range-band__line { position: absolute; top: 0; left: 0; right: 0; height: 14px; border-radius: 999px; background: linear-gradient(90deg, #1d4ed8, #0f766e); }
.range-band__marker { padding: 18px 20px; border-radius: 22px; background: var(--panel-alt); }
.range-band__marker strong { display: block; font-size: 32px; margin-bottom: 6px; }
.range-band__marker span { color: var(--muted); letter-spacing: 0.16em; font-size: 11px; }
.notify-card { align-content: start; }
.notify-item { display: grid; grid-template-columns: 20px 1fr; gap: 12px; align-items: start; }
.notify-item input { margin-top: 3px; }
.notify-item strong { display: block; margin-bottom: 4px; }
.notify-item p { margin: 0; color: var(--muted); }
.notify-status { margin: 0; color: var(--muted); }
.notify-actions { display: flex; }
.ghost-button { border: 0; border-radius: 999px; padding: 10px 16px; background: #eef6f3; color: #0f766e; font-weight: 700; cursor: pointer; }
@media (max-width: 1180px) {
  .editor-layout, .range-grid { grid-template-columns: 1fr; }
  .editor-head { flex-direction: column; }
}
</style>
