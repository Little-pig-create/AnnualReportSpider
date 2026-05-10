<template>
  <div ref="container" class="console">
    <div v-for="(item, index) in items" :key="`${item.time}-${index}`" class="row" :data-level="item.level">
      <span>{{ formatLogTime(item.time) }}</span>
      <b>{{ levelText(item.level) }}</b>
      <em>{{ stageText(item.stage) }}</em>
      <p>{{ item.message }}</p>
    </div>
    <div v-if="items.length === 0" class="empty">暂无日志</div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { formatDateTime } from "@/services/datetime";
import type { LogItem } from "@/services/types";

const props = defineProps<{
  items: LogItem[];
}>();

const container = ref<HTMLElement | null>(null);

function levelText(level: string) {
  return {
    INFO: "信息",
    WARN: "警告",
    ERROR: "错误",
    DEBUG: "调试",
  }[level] || level;
}

function stageText(stage: string) {
  return {
    links: "链接",
    pdf: "PDF",
    extract: "提取",
    system: "系统",
  }[stage] || stage;
}

function formatLogTime(value: string) {
  return formatDateTime(value, value);
}

watch(
  () => props.items.length,
  async () => {
    const el = container.value;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const shouldStickToBottom = distanceFromBottom < 48;
    await nextTick();
    if (!container.value || !shouldStickToBottom) return;
    container.value.scrollTop = container.value.scrollHeight;
  },
  { immediate: true },
);
</script>

<style scoped>
.console {
  background: #101720;
  color: #ecf5ff;
  border-radius: 24px;
  padding: 18px;
  height: 360px;
  min-height: 360px;
  max-height: 360px;
  overflow: auto;
  overscroll-behavior: contain;
  overflow-anchor: none;
  scrollbar-gutter: stable;
  font-family: Consolas, "Courier New", monospace;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.console::-webkit-scrollbar {
  width: 0;
  height: 0;
}

.row {
  display: grid;
  grid-template-columns: 70px 58px 64px 1fr;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  font-size: 12px;
}

.row:last-child {
  border-bottom: 0;
}

.row span,
.row b,
.row em {
  color: #85a5c8;
  font-style: normal;
}

.row[data-level="ERROR"] b {
  color: #f87171;
}

.row[data-level="WARN"] b {
  color: #fbbf24;
}

.row[data-level="INFO"] b {
  color: #34d399;
}

.row p {
  margin: 0;
  color: #eff5ff;
  word-break: break-word;
}

.empty {
  color: #85a5c8;
}
</style>
