import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "@/App.vue";
import "@/styles/tokens.css";
import "@/styles/app.css";
import "element-plus/es/components/dialog/style/css";
import "element-plus/es/components/message-box/style/css";
import "element-plus/es/components/notification/style/css";
import "element-plus/es/components/timeline/style/css";
import "element-plus/es/components/tag/style/css";
import "element-plus/es/components/pagination/style/css";

const app = createApp(App);
app.use(createPinia());
app.mount("#app");
