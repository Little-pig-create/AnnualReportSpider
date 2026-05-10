<template>
  <section class="logs-page">
    <header class="logs-head">
      <div class="logs-head__copy">
        <p class="section-kicker">日志</p>
        <h2>运行日志中心</h2>
        <p>按级别和阶段筛选日志，使用与首页一致的日志面板样式，方便快速定位问题。</p>
      </div>

      <div class="filters">
        <select v-model="levelFilter">
          <option value="ALL">全部级别</option>
          <option value="INFO">信息</option>
          <option value="WARN">警告</option>
          <option value="ERROR">错误</option>
          <option value="DEBUG">调试</option>
        </select>
        <select v-model="stageFilter">
          <option value="ALL">全部阶段</option>
          <option value="system">系统</option>
          <option value="links">链接</option>
          <option value="pdf">PDF</option>
          <option value="extract">提取</option>
        </select>
      </div>
    </header>

    <section class="surface logs-panel">
      <div class="logs-summary">
        <strong>共 {{ filteredLogs.length }} 条</strong>
        <span>日志中心样式已与首页同步</span>
      </div>

      <LogConsole :items="filteredLogs" class="logs-console" />
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
.logs-page {
  display: grid;
  gap: 24px;
}

.logs-head {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: flex-start;
}

.logs-head__copy {
  display: grid;
  gap: 8px;
}

.logs-head h2 {
  margin: 6px 0 0;
  font-size: 40px;
}

.logs-head p:last-child {
  margin: 0;
  color: var(--muted);
  max-width: 720px;
  line-height: 1.7;
}

.filters {
  display: flex;
  gap: 12px;
}

.filters select {
  min-width: 148px;
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

.filters select option {
  color: #1d4ed8;
  background: #eef2ff;
}

.logs-panel {
  display: grid;
  gap: 16px;
}

.logs-summary {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  color: var(--muted);
}

.logs-console {
  width: 100%;
}

.logs-console:deep(.console) {
  height: calc(100vh - 360px);
  min-height: 520px;
  max-height: calc(100vh - 360px);
}

@media (max-width: 1180px) {
  .logs-head {
    flex-direction: column;
  }

  .filters {
    width: 100%;
    flex-wrap: wrap;
  }

  .filters select {
    flex: 1 1 220px;
  }

  .logs-console:deep(.console) {
    height: 520px;
    min-height: 520px;
    max-height: 520px;
  }
}
</style>
