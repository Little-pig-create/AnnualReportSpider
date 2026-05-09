<template>
  <section class="about-page">
    <header class="about-hero surface">
      <div class="about-hero__main">
        <p class="section-kicker">关于软件</p>
        <h2>{{ about?.appName || "桌面控制台" }}</h2>
        <p class="about-hero__desc">
          面向年报公告抓取、PDF 下载与文本提取的一体化桌面工作台。
        </p>
      </div>
      <div class="about-hero__meta">
        <div class="meta-item">
          <span>版本号</span>
          <strong>{{ about?.version || "-" }}</strong>
        </div>
        <a
          v-if="about?.githubUrl"
          class="meta-link"
          :href="about.githubUrl"
          target="_blank"
          rel="noreferrer"
        >
          打开 GitHub
        </a>
      </div>
    </header>

    <div class="about-grid">
      <article class="surface about-card">
        <header class="section-header">
          <div>
            <p class="section-kicker">功能</p>
            <h3>核心能力</h3>
          </div>
        </header>
        <ul class="feature-list">
          <li>支持公告链接抓取、PDF 下载、文本提取三阶段串联执行。</li>
          <li>支持仅执行单阶段任务，便于补跑、校验与调试。</li>
          <li>支持工作目录、输出目录、年份范围等参数的图形化配置。</li>
          <li>支持运行状态、阶段进度、日志与图表的可视化查看。</li>
        </ul>
      </article>

      <article class="surface about-card">
        <header class="section-header">
          <div>
            <p class="section-kicker">流程</p>
            <h3>标准使用流程</h3>
          </div>
        </header>
        <ol class="step-list">
          <li>先在“工作区”中选择项目目录、数据目录与结果目录。</li>
          <li>按需配置公告链接抓取、PDF 下载、文本提取三个阶段参数。</li>
          <li>在“任务总览”启动任务，并实时查看进度、图表与最近日志。</li>
          <li>任务完成后，到对应输出目录检查抓取结果与提取文本。</li>
        </ol>
      </article>

      <article class="surface about-card">
        <header class="section-header">
          <div>
            <p class="section-kicker">目录</p>
            <h3>数据说明</h3>
          </div>
        </header>
        <ul class="feature-list">
          <li>公告链接结果：用于保存抓取到的公告链接与过滤后的记录。</li>
          <li>PDF 文件目录：用于保存已下载的公告 PDF 文件。</li>
          <li>文本输出目录：用于保存提取后的纯文本结果。</li>
          <li>运行日志：用于追踪任务执行过程、异常信息与阶段状态。</li>
        </ul>
      </article>

      <article class="surface about-card">
        <header class="section-header">
          <div>
            <p class="section-kicker">说明</p>
            <h3>使用建议</h3>
          </div>
        </header>
        <ul class="feature-list">
          <li>首次使用建议先仅运行公告链接抓取，确认目录与年份配置正确。</li>
          <li>若中途中断，可按阶段单独重跑，无需每次都执行完整流程。</li>
          <li>日志区域展示最近运行信息，适合快速判断当前卡点与异常位置。</li>
          <li>图表区域更适合观察不同年份的抓取分布与阶段推进情况。</li>
        </ul>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useAppStore } from "@/stores/app";

const appStore = useAppStore();
const about = computed(() => appStore.about);

onMounted(() => {
  appStore.loadAbout();
});
</script>

<style scoped>
.about-page { display: grid; gap: 24px; }
.about-hero { display: flex; justify-content: space-between; gap: 24px; align-items: stretch; }
.about-hero__main { display: grid; gap: 10px; }
.about-hero__main h2 { margin: 0; font-size: 38px; }
.about-hero__desc { margin: 0; color: var(--muted); line-height: 1.7; max-width: 720px; }
.about-hero__meta {
  display: grid;
  gap: 14px;
  width: 260px;
  min-width: 260px;
  justify-items: stretch;
  align-content: end;
}
.meta-item {
  display: grid;
  gap: 6px;
  width: 100%;
  padding: 18px 20px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.meta-item span { font-size: 12px; color: var(--muted); }
.meta-item strong { font-size: 20px; line-height: 1.2; }
.meta-link {
  display: inline-flex;
  width: 100%;
  align-items: center;
  justify-content: center;
  min-height: 52px;
  padding: 0 18px;
  border-radius: 14px;
  color: #fff;
  text-decoration: none;
  background: linear-gradient(135deg, #4f8cff, #6f7cff);
}
.about-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px; }
.about-card { display: grid; gap: 18px; }
.feature-list, .step-list { margin: 0; padding-left: 20px; color: var(--muted); line-height: 1.8; }
.feature-list li + li, .step-list li + li { margin-top: 8px; }
@media (max-width: 1180px) {
  .about-hero { flex-direction: column; }
  .about-hero__meta { width: 100%; min-width: 0; justify-items: stretch; align-content: start; }
  .about-grid { grid-template-columns: 1fr; }
}
</style>
