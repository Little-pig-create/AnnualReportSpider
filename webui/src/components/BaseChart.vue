<template>
  <div ref="container" class="chart"></div>
</template>

<script setup lang="ts">
import { BarChart, GaugeChart, LineChart, PieChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { use } from "echarts/core";
import { init, type ECharts } from "echarts/core";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

use([BarChart, LineChart, PieChart, GaugeChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

const props = defineProps<{
  option: Record<string, any>;
}>();

const container = ref<HTMLElement | null>(null);
let chart: ECharts | null = null;
let resizeObserver: ResizeObserver | null = null;

function renderChart() {
  if (!container.value) return;
  if (!chart) {
    chart = init(container.value, undefined, {
      renderer: "canvas",
      useDirtyRect: true,
    });
  }
  chart.setOption(props.option, true);
}

function onResize() {
  chart?.resize({
    animation: {
      duration: 180,
    },
  });
}

onMounted(() => {
  renderChart();
  window.addEventListener("resize", onResize);
  if (container.value && typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(() => onResize());
    resizeObserver.observe(container.value);
  }
});

watch(() => props.option, renderChart, { deep: true });

onBeforeUnmount(() => {
  window.removeEventListener("resize", onResize);
  resizeObserver?.disconnect();
  resizeObserver = null;
  chart?.dispose();
  chart = null;
});
</script>

<style scoped>
.chart {
  width: 100%;
  min-height: 320px;
}
</style>
