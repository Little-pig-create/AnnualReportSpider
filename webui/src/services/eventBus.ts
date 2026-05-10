export function mountDesktopEventBus(taskStore: { handleEvent: (event: any) => void }) {
  const POLL_INTERVAL_MS = 120;
  const MAX_BATCH_SIZE = 240;
  let pullTimer: number | null = null;
  let pulling = false;

  const flush = (items: any[]) => {
    items.forEach((event) => taskStore.handleEvent(event));
  };

  const pull = async () => {
    if (pulling) return;
    pulling = true;
    try {
      const bridge = window.pywebview?.api as any;
      if (!bridge || typeof bridge.get_pending_events !== "function") {
        return;
      }
      const result = await bridge.get_pending_events({ limit: MAX_BATCH_SIZE });
      if (!result?.ok) {
        return;
      }
      const items = Array.isArray(result?.data?.items) ? result.data.items : [];
      if (items.length > 0) {
        flush(items);
      }
    } catch {
      return;
    } finally {
      pulling = false;
    }
  };

  if (pullTimer !== null) {
    window.clearInterval(pullTimer);
  }
  pullTimer = window.setInterval(() => {
    void pull();
  }, POLL_INTERVAL_MS);

  window.__DESKTOP_EVENT__ = (event) => {
    taskStore.handleEvent(event);
  };

  void pull();
}
