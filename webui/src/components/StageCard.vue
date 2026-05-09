<template>
  <article class="stage-card" :data-status="stage.status" :data-name="stage.name">
    <div class="stage-card__head">
      <div>
        <p>{{ stage.title }}</p>
        <strong class="stage-card__title">
          <span v-if="stage.status === 'completed'" class="stage-card__check">✓</span>
          {{ statusLabel }}
        </strong>
      </div>
      <span class="stage-card__percent">{{ percentText }}</span>
    </div>

    <div class="stage-card__meter">
      <i :style="{ width: `${clampedPercent * 100}%` }"></i>
    </div>

    <div class="stage-card__foot">
      <small>{{ displayHint }}</small>
      <code>{{ progressText }}</code>
    </div>

    <div class="stage-card__details" :class="{ 'stage-card__details--empty': !detailLines.length }">
      <small v-for="line in detailLines" :key="line">{{ line }}</small>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { StageState } from "@/services/types";

const props = defineProps<{
  stage: StageState;
}>();

const clampedPercent = computed(() => Math.min(1, Math.max(0, Number(props.stage.progress.percent || 0))));

const statusLabel = computed(() => ({
  pending: "等待中",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
}[props.stage.status]));

const percentText = computed(() => `${Math.round(clampedPercent.value * 100)}%`);

const displayHint = computed(() => {
  if (props.stage.status === "completed") return "该阶段已完成";
  if (props.stage.status === "cancelled") return props.stage.hint || "任务已取消，保留当前进度";
  if (props.stage.status === "failed") return props.stage.hint || "执行失败";
  return props.stage.hint || progressText.value;
});

const linkLive = computed(() => {
  const result = props.stage.result || {};
  if (result.live && Array.isArray(result.live.yearBuckets)) return result.live;
  if (Array.isArray(result.yearBuckets)) return result;
  return null;
});

const currentYearBucket = computed(() => {
  const currentYear = Number(linkLive.value?.currentYear || 0);
  if (!currentYear) return null;
  return (linkLive.value?.yearBuckets || []).find((item: any) => Number(item?.year) === currentYear) || null;
});

const yearCompletedCount = computed(() => {
  const buckets = linkLive.value?.yearBuckets || [];
  return buckets.filter((item: any) => item?.status === "completed").length;
});

const progressText = computed(() => {
  if (props.stage.name === "links" && linkLive.value) {
    const currentYearIndex = Number(linkLive.value.currentYearIndex || 0);
    const yearTotal = Number(linkLive.value.yearTotal || 0);
    if (yearTotal > 0) {
      const shown = currentYearIndex > 0 ? Math.min(currentYearIndex, yearTotal) : yearCompletedCount.value;
      return `${shown}/${yearTotal} 年`;
    }
  }

  const current = Number(props.stage.progress.current || 0);
  const total = Number(props.stage.progress.total || 0);
  if (total > 0) {
    return `${Math.min(current, total)}/${total}`;
  }
  return `${Math.round(clampedPercent.value * 100)}/100`;
});

const detailLines = computed(() => {
  if (props.stage.name === "pdf") {
    const result = props.stage.result || {};
    const total = Number(result.pdfTotal || 0);
    const completed = Number(result.downloaded || 0) + Number(result.exists || 0);
    const skipped = Number(result.skipped || 0);
    const failed = Number(result.failed || 0);
    const lines: string[] = [];

    if (total > 0) {
      lines.push(`PDF 总量：${total} 份`);
      lines.push(`已完成：${completed} · 跳过：${skipped} · 失败：${failed}`);
    }
    return lines;
  }

  if (props.stage.name === "extract") {
    const result = props.stage.result || {};
    const total = Number(result.pdfTotal || 0);
    const completed = Number(result.extracted || 0) + Number(result.exists || 0);
    const failed = Number(result.failed || 0);
    const lines: string[] = [];

    if (total > 0) {
      lines.push(`文本总量：${total} 份`);
      lines.push(`已完成：${completed} · 失败：${failed}`);
    }
    return lines;
  }

  if (props.stage.name !== "links" || !linkLive.value) return [];

  const lines: string[] = [];
  const yearTotal = Number(linkLive.value.yearTotal || 0);
  const currentYearIndex = Number(linkLive.value.currentYearIndex || 0);
  const rangeCurrent = Number(linkLive.value.rangeCurrent || 0);
  const rangeTotal = Number(linkLive.value.rangeTotal || 0);
  const currentYear = Number(linkLive.value.currentYear || 0);

  if (yearTotal > 0) {
    const yearDisplay = currentYearIndex > 0 ? Math.min(currentYearIndex, yearTotal) : yearCompletedCount.value;
    lines.push(`年份进度：${yearDisplay}/${yearTotal} 年`);
  }

  if (currentYear > 0 && rangeTotal > 0) {
    lines.push(`当前年份区间：${currentYear} 年 ${rangeCurrent}/${rangeTotal}`);
  }

  const currentBucket = currentYearBucket.value;
  if (currentBucket) {
    lines.push(`当前年份公告数：${Number(currentBucket.count || 0)} 条`);
  }

  return lines;
});
</script>

<style scoped>
.stage-card {
  display: grid;
  grid-template-rows: auto 12px auto auto;
  gap: 12px;
  padding: 18px;
  border-radius: 22px;
  border: 1px solid rgba(20, 28, 45, 0.08);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.96));
  transition:
    box-shadow 0.22s ease,
    border-color 0.22s ease,
    background-color 0.22s ease,
    transform 0.22s ease;
}

.stage-card__head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.stage-card__head p,
.stage-card__head strong {
  margin: 0;
}

.stage-card__head p {
  color: var(--muted);
  font-size: 13px;
  margin-bottom: 6px;
}

.stage-card__head strong {
  font-size: 22px;
  line-height: 1.15;
  color: #0f172a;
}

.stage-card__title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.stage-card__check {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: rgba(34, 197, 94, 0.14);
  color: #15803d;
  font-size: 15px;
  font-weight: 900;
}

.stage-card__percent {
  align-self: start;
  min-width: 72px;
  text-align: center;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.9);
  font-weight: 800;
  color: #1f2937;
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.9);
}

.stage-card__meter {
  height: 12px;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(148, 163, 184, 0.16);
}

.stage-card__meter i {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #94a3b8, #cbd5e1);
  transition: width 0.55s ease;
}

.stage-card__foot {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.stage-card__foot small {
  color: var(--muted);
  flex: 1;
  min-height: 42px;
  overflow: hidden;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.stage-card__foot code {
  padding: 4px 10px;
  border-radius: 10px;
  background: rgba(17, 24, 39, 0.06);
  color: #334155;
  font-family: Consolas, "Courier New", monospace;
  white-space: nowrap;
  min-width: 92px;
  text-align: center;
}

.stage-card__details {
  display: grid;
  gap: 6px;
  padding: 10px 12px;
  min-height: 64px;
  overflow: hidden;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.55);
  align-content: start;
}

.stage-card__details small {
  color: var(--muted);
  line-height: 1.45;
}

.stage-card__details--empty {
  background: transparent;
  border: 1px solid transparent;
}

.stage-card[data-status="pending"] {
  border-color: rgba(226, 232, 240, 0.95);
}

.stage-card[data-status="pending"] .stage-card__meter i {
  background: linear-gradient(90deg, #cbd5e1, #e2e8f0);
}

.stage-card[data-status="running"] {
  border-color: rgba(37, 99, 235, 0.24);
  background: linear-gradient(180deg, rgba(239, 246, 255, 0.96), rgba(248, 250, 252, 0.98));
  box-shadow: 0 18px 34px rgba(37, 99, 235, 0.12);
  transform: translateY(-1px);
  animation: stagePulse 1.8s ease-in-out infinite;
}

.stage-card[data-status="running"] .stage-card__percent {
  background: rgba(219, 234, 254, 0.95);
  color: #1d4ed8;
  box-shadow: inset 0 0 0 1px rgba(147, 197, 253, 0.95);
}

.stage-card[data-status="running"] .stage-card__meter i {
  background: linear-gradient(90deg, #2563eb, #38bdf8);
}

.stage-card[data-status="completed"] {
  border-color: rgba(34, 197, 94, 0.22);
  background: linear-gradient(180deg, rgba(240, 253, 244, 0.98), rgba(248, 250, 252, 0.98));
  box-shadow: 0 16px 30px rgba(34, 197, 94, 0.08);
}

.stage-card[data-status="completed"] .stage-card__head strong {
  color: #166534;
}

.stage-card[data-status="completed"] .stage-card__percent {
  background: rgba(220, 252, 231, 0.96);
  color: #166534;
  box-shadow: inset 0 0 0 1px rgba(134, 239, 172, 0.95);
}

.stage-card[data-status="completed"] .stage-card__meter i {
  background: linear-gradient(90deg, #16a34a, #22c55e);
}

.stage-card[data-status="failed"] {
  border-color: rgba(239, 68, 68, 0.2);
  background: linear-gradient(180deg, rgba(254, 242, 242, 0.98), rgba(248, 250, 252, 0.98));
}

.stage-card[data-status="failed"] .stage-card__percent {
  background: rgba(254, 226, 226, 0.96);
  color: #b91c1c;
  box-shadow: inset 0 0 0 1px rgba(252, 165, 165, 0.95);
}

.stage-card[data-status="failed"] .stage-card__meter i {
  background: linear-gradient(90deg, #dc2626, #fb7185);
}

.stage-card[data-status="cancelled"] {
  border-color: rgba(245, 158, 11, 0.24);
  background: linear-gradient(180deg, rgba(255, 247, 237, 0.98), rgba(248, 250, 252, 0.98));
}

.stage-card[data-status="cancelled"] .stage-card__head strong {
  color: #9a3412;
}

.stage-card[data-status="cancelled"] .stage-card__percent {
  background: rgba(255, 237, 213, 0.96);
  color: #9a3412;
  box-shadow: inset 0 0 0 1px rgba(253, 186, 116, 0.95);
}

.stage-card[data-status="cancelled"] .stage-card__meter i {
  background: linear-gradient(90deg, #ea580c, #f59e0b);
}

@keyframes stagePulse {
  0%, 100% {
    box-shadow: 0 18px 34px rgba(37, 99, 235, 0.1);
  }
  50% {
    box-shadow: 0 22px 42px rgba(37, 99, 235, 0.18);
  }
}
</style>
