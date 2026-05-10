/// <reference types="vite/client" />

declare global {
  interface Window {
    pywebview?: {
      api: Record<string, (...args: any[]) => Promise<any> | any>;
    };
    __DESKTOP_EVENT__?: (event: any) => void;
  }
}

declare module "*.png" {
  const src: string;
  export default src;
}

declare module "*.jpg" {
  const src: string;
  export default src;
}

declare module "*.jpeg" {
  const src: string;
  export default src;
}

declare module "*.svg" {
  const src: string;
  export default src;
}

declare module "*.vue" {
  import type { DefineComponent } from "vue";

  const component: DefineComponent<Record<string, never>, Record<string, never>, any>;
  export default component;
}

export {};
