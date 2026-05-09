from __future__ import annotations

from pathlib import Path

from .bridge import Bridge
from .infra.config_store import ConfigStore
from .infra.event_pusher import EventPusher
from .paths import config_path, frontend_dist_dir
from .runtime import Runtime


def launch() -> None:
    try:
        import webview
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pywebview is required. Install dependencies from webview_console/requirements.txt") from exc

    frontend_index = frontend_dist_dir() / "index.html"
    if not frontend_index.exists():
        raise FileNotFoundError(f"Frontend build not found: {frontend_index}")

    config_store = ConfigStore(config_path())
    event_pusher = EventPusher()
    runtime = Runtime(config_store, event_pusher)
    bridge = Bridge(runtime)

    window = webview.create_window(
        title="Report Spider Webview Console",
        url=frontend_index.as_uri(),
        js_api=bridge,
        width=1540,
        height=980,
        min_size=(1280, 820),
    )
    runtime.attach_window(window)

    def _on_closing():
        return runtime.request_window_close()

    try:
        window.events.closing += _on_closing
    except Exception:
        pass

    webview.start(debug=False)
