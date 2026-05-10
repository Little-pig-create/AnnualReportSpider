<template>
  <section class="editor-page" v-if="settings">
    <header class="editor-head">
      <div>
        <p class="section-kicker">链接阶段</p>
        <h2>链接抓取策略</h2>
        <p>这里统一配置公告抓取范围、查询日期、分页、请求节奏和断点策略。</p>
      </div>
      <button class="save-button" @click="settingsStore.save()" :disabled="settingsStore.saving">
        {{ settingsStore.saving ? "保存中..." : "保存链接配置" }}
      </button>
    </header>

    <div class="config-grid">
      <section class="surface config-card left-card">
        <header class="section-header">
          <div>
            <p class="section-kicker">请求参数</p>
            <h3>请求设置</h3>
          </div>
        </header>

        <div class="form-grid two-cols">
          <div class="field field--full">
            <span>公告链接抓取模式</span>
            <div class="checkbox-group">
              <label class="checkbox-card">
                <input type="checkbox" value="a_share" v-model="settings.links.marketScopes" @change="ensureMarketScopes" />
                <div>
                  <strong>沪深 A 股</strong>
                  <p>包含深主板、创业板、沪主板、科创板。</p>
                </div>
              </label>

              <label class="checkbox-card">
                <input type="checkbox" value="b_share" v-model="settings.links.marketScopes" @change="ensureMarketScopes" />
                <div>
                  <strong>B 股</strong>
                  <p>包含沪市 B 股和深市 B 股。</p>
                </div>
              </label>

              <label class="checkbox-card">
                <input type="checkbox" value="bjse" v-model="settings.links.marketScopes" @change="ensureMarketScopes" />
                <div>
                  <strong>北交所</strong>
                  <p>包含北京证券交易所公告。</p>
                </div>
              </label>
            </div>
          </div>

          <label class="field">
            <span>查询日期</span>
            <input v-model="settings.links.seDate" @input="settingsStore.touch()" placeholder="可选，例如 2024-12-31" />
          </label>

          <label class="field">
            <span>分页大小</span>
            <input type="number" v-model.number="settings.links.pageSize" @input="settingsStore.touch()" />
          </label>

          <label class="field">
            <span>请求间隔（秒）</span>
            <input type="number" step="0.1" v-model.number="settings.links.requestInterval" @input="settingsStore.touch()" />
          </label>

          <label class="field">
            <span>公告并发数</span>
            <input type="number" v-model.number="settings.links.announcementConcurrency" @input="settingsStore.touch()" />
          </label>
        </div>
      </section>

      <section class="surface config-card right-card">
        <header class="section-header">
          <div>
            <p class="section-kicker">断点恢复</p>
            <h3>断点控制</h3>
          </div>
        </header>

        <div class="toggle-stack">
          <label class="toggle-row">
            <input type="checkbox" v-model="settings.links.resetCheckpoint" @change="settingsStore.touch()" />
            <div>
              <strong>运行前重置断点</strong>
              <p>当链接抓取阶段需要全量重跑时启用。</p>
            </div>
          </label>

          <label class="toggle-row">
            <input type="checkbox" v-model="settings.links.deleteCheckpointOnSuccess" @change="settingsStore.touch()" />
            <div>
              <strong>成功后删除断点</strong>
              <p>抓取成功后自动清理状态文件。</p>
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

function ensureMarketScopes() {
  if (!settings.value) return;
  if (settings.value.links.marketScopes.length === 0) {
    settings.value.links.marketScopes = ["a_share"];
  }
  settingsStore.touch();
}
</script>

<style scoped>
.editor-page { display: grid; gap: 24px; }
.editor-head { display: flex; justify-content: space-between; gap: 20px; align-items: center; }
.editor-head h2 { margin: 6px 0 12px; font-size: 40px; }
.editor-head p:last-child { margin: 0; color: var(--muted); max-width: 760px; }
.save-button { border: 0; border-radius: 999px; min-height: 52px; padding: 0 22px; display: inline-flex; align-items: center; justify-content: center; background: linear-gradient(135deg, #0f766e, #155e75); color: white; font-weight: 700; cursor: pointer; }
.config-grid { display: grid; grid-template-columns: 1.05fr 0.95fr; gap: 24px; }
.config-card { display: grid; gap: 18px; }
.left-card,
.right-card { align-content: start; gap: 10px; }
.left-card .section-header,
.right-card .section-header { margin-bottom: -4px; }
.form-grid.two-cols { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.field { display: grid; gap: 10px; }
.field--full { grid-column: 1 / -1; }
.field span { color: var(--muted); font-size: 13px; }
.field input { width: 100%; border: 1px solid var(--line); border-radius: 18px; padding: 14px 16px; background: #fff; }
.checkbox-group { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.checkbox-card { display: grid; grid-template-columns: auto 1fr; gap: 12px; align-items: start; padding: 16px 18px; border-radius: 18px; border: 1px solid var(--line); background: #fff; }
.checkbox-card strong { display: block; margin-bottom: 4px; }
.checkbox-card p { margin: 0; color: var(--muted); line-height: 1.5; font-size: 13px; }
.toggle-stack { display: grid; gap: 16px; }
.toggle-row { display: grid; grid-template-columns: auto 1fr; gap: 16px; align-items: start; padding: 18px; border-radius: 20px; background: var(--panel-alt); }
.toggle-row strong { display: block; margin-bottom: 6px; }
.toggle-row p { margin: 0; color: var(--muted); line-height: 1.6; }
@media (max-width: 1180px) {
  .config-grid, .form-grid.two-cols, .checkbox-group { grid-template-columns: 1fr; }
  .editor-head { flex-direction: column; }
}
</style>
