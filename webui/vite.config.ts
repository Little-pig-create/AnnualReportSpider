import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [vue()],
  base: "./",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/element-plus/es/components/dialog")) return "element-plus-dialog";
          if (id.includes("node_modules/element-plus/es/components/pagination")) return "element-plus-pagination";
          if (id.includes("node_modules/element-plus/es/components/message-box")) return "element-plus-message-box";
          if (id.includes("node_modules/element-plus/es/components/notification")) return "element-plus-notification";
          if (id.includes("node_modules/echarts")) return "charts";
          if (id.includes("node_modules/vue") || id.includes("node_modules/pinia")) return "vue";
          if (id.includes("node_modules/element-plus")) return "element-plus-core";
          if (id.includes("node_modules")) return "vendor";
          return undefined;
        },
      },
    },
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
});
