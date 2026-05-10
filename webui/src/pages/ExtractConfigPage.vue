<template>
  <section class="editor-page" v-if="settings">
    <header class="editor-head">
      <div>
        <p class="section-kicker">提取阶段</p>
        <h2>文本提取控制面板</h2>
        <p>这里集中配置文本提取的并发数和断点策略，便于在 PDF 已落盘后单独调优。</p>
      </div>
      <button class="save-button" @click="settingsStore.save()" :disabled="settingsStore.saving">
        {{ settingsStore.saving ? "保存中..." : "保存提取配置" }}
      </button>
    </header>

    <div class="config-grid">
      <section class="surface config-card left-card">
        <header class="section-header">
          <div>
            <p class="section-kicker">并发</p>
            <h3>提取并发数</h3>
          </div>
        </header>

        <label class="field">
          <span>工作线程数</span>
          <input type="number" v-model.number="settings.extract.concurrency" @input="settingsStore.touch()" />
        </label>
      </section>

      <section class="surface config-card">
        <header class="section-header">
          <div>
            <p class="section-kicker">断点</p>
            <h3>断点行为</h3>
          </div>
        </header>

        <div class="toggle-stack">
          <label class="toggle-row">
            <input type="checkbox" v-model="settings.extract.resetCheckpoint" @change="settingsStore.touch()" />
            <div>
              <strong>运行前重置断点</strong>
              <p>当文本提取阶段需要全量重跑时启用。</p>
            </div>
          </label>
          <label class="toggle-row">
            <input type="checkbox" v-model="settings.extract.deleteCheckpointOnSuccess" @change="settingsStore.touch()" />
            <div>
              <strong>成功后删除断点</strong>
              <p>适合固定批处理流程，保持状态目录整洁。</p>
            </div>
          </label>
        </div>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useSettingsStore } from "@/stores/settings";

const settingsStore = useSettingsStore();
const settings = computed(() => settingsStore.data);
</script>

<style scoped>
.editor-page { display: grid; gap: 24px; }
.editor-head { display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; }
.editor-head h2 { margin: 6px 0 12px; font-size: 40px; }
.editor-head p:last-child { margin: 0; color: var(--muted); max-width: 760px; }
.save-button { border: 0; border-radius: 999px; padding: 16px 22px; background: linear-gradient(135deg, #0f766e, #155e75); color: white; font-weight: 700; cursor: pointer; }
.config-grid { display: grid; grid-template-columns: 0.8fr 1.2fr; gap: 24px; }
.config-card { display: grid; gap: 18px; }
.left-card { align-content: start; gap: 10px; }
.left-card .section-header { margin-bottom: -4px; }
.field { display: grid; gap: 10px; }
.field span { color: var(--muted); font-size: 13px; }
.field input { width: 100%; border: 1px solid var(--line); border-radius: 18px; padding: 14px 16px; background: #fff; }
.toggle-stack { display: grid; gap: 16px; }
.toggle-row { display: grid; grid-template-columns: auto 1fr; gap: 16px; align-items: start; padding: 18px; border-radius: 20px; background: var(--panel-alt); }
.toggle-row strong { display: block; margin-bottom: 6px; }
.toggle-row p { margin: 0; color: var(--muted); line-height: 1.6; }
@media (max-width: 1180px) {
  .config-grid { grid-template-columns: 1fr; }
  .editor-head { flex-direction: column; }
}
</style>
