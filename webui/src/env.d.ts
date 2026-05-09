declare global {
  interface Window {
    pywebview?: {
      api: Record<string, (...args: any[]) => Promise<any> | any>;
    };
    __DESKTOP_EVENT__?: (event: any) => void;
  }
}

export {};
