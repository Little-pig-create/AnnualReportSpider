<template>
  <section class="editor-page" v-if="settings">
    <header class="editor-head">
      <div>
        <p class="section-kicker">PDF 阶段</p>
        <h2>下载并发与依赖说明</h2>
        <p>这里配置 PDF 下载阶段的核心并发参数，并补充与链接抓取阶段的依赖关系说明。</p>
      </div>
      <button class="save-button" @click="settingsStore.save()" :disabled="settingsStore.saving">
        {{ settingsStore.saving ? "保存中..." : "保存 PDF 配置" }}
      </button>
    </header>

    <div class="config-grid">
      <section class="surface config-card left-card">
        <header class="section-header">
          <div>
            <p class="section-kicker">并发</p>
            <h3>下载并发数</h3>
          </div>
        </header>

        <label class="field">
          <span>工作线程数</span>
          <input type="number" v-model.number="settings.pdf.downloadConcurrency" @input="settingsStore.touch()" />
        </label>
      </section>

      <section class="surface config-card note-card">
        <header class="section-header">
          <div>
            <p class="section-kicker">依赖</p>
            <h3>阶段关系</h3>
          </div>
        </header>

        <div class="note-block">
          <strong>输入来源</strong>
          <p>PDF 阶段依赖链接抓取阶段，读取每个年份目录下生成的清单和元数据文件。</p>
        </div>

        <div class="note-block">
          <strong>建议流程</strong>
          <p>建议先用较低并发完成一次完整验证，再在下载路径稳定后提高并发。</p>
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
.note-card { align-content: start; }
.note-block { padding: 18px; border-radius: 20px; background: var(--panel-alt); }
.note-block strong { display: block; margin-bottom: 8px; }
.note-block p { margin: 0; color: var(--muted); line-height: 1.7; }
@media (max-width: 1180px) {
  .config-grid { grid-template-columns: 1fr; }
  .editor-head { flex-direction: column; }
}
</style>
