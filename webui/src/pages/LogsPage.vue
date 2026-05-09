<template>
  <section class="logs-page">
    <header class="logs-head">
      <div>
        <p class="section-kicker">日志</p>
        <h2>运行日志中心</h2>
        <p>按级别和阶段筛选日志，方便在任务运行期间快速定位下载或提取问题。</p>
      </div>
      <div class="filters">
        <select v-model="levelFilter">
          <option value="ALL">全部级别</option>
          <option value="INFO">信息</option>
          <option value="WARN">警告</option>
          <option value="ERROR">错误</option>
        </select>
        <select v-model="stageFilter">
          <option value="ALL">全部阶段</option>
          <option value="links">链接</option>
          <option value="pdf">PDF</option>
          <option value="extract">提取</option>
        </select>
      </div>
    </header>
    <section class="surface">
      <LogConsole :items="filteredLogs" />
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import LogConsole from "@/components/LogConsole.vue";
import { useTaskStore } from "@/stores/task";

const taskStore = useTaskStore();
const levelFilter = ref("ALL");
const stageFilter = ref("ALL");

const filteredLogs = computed(() =>
  taskStore.logs.filter((item) => {
    const levelOk = levelFilter.value === "ALL" || item.level === levelFilter.value;
    const stageOk = stageFilter.value === "ALL" || item.stage === stageFilter.value;
    return levelOk && stageOk;
  }),
);
</script>

<style scoped>
.logs-page { display: grid; gap: 24px; }
.logs-head { display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; }
.logs-head h2 { margin: 6px 0 12px; font-size: 40px; }
.logs-head p:last-child { margin: 0; color: var(--muted); max-width: 720px; }
.filters { display: flex; gap: 12px; }
select {
  border: 1px solid rgba(29, 78, 216, 0.12);
  border-radius: 16px;
  padding: 12px 40px 12px 14px;
  background-color: #eef2ff;
  color: #1d4ed8;
  appearance: none;
  -webkit-appearance: none;
  -moz-appearance: none;
  background-image:
    linear-gradient(45deg, transparent 50%, #1d4ed8 50%),
    linear-gradient(135deg, #1d4ed8 50%, transparent 50%);
  background-position:
    calc(100% - 22px) calc(50% - 3px),
    calc(100% - 14px) calc(50% - 3px);
  background-size: 8px 8px, 8px 8px;
  background-repeat: no-repeat;
}

select option {
  color: #1d4ed8;
  background: #eef2ff;
}
@media (max-width: 1180px) {
  .logs-head { flex-direction: column; }
}
</style>
