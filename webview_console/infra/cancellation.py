from __future__ import annotations

import threading


class CancelledError(Exception):
    pass


class CancelToken:
    def __init__(self) -> None:
        self._cancel_event = threading.Event()
        self._resume_event = threading.Event()
        self._resume_event.set()

    def cancel(self) -> None:
        self._cancel_event.set()
        self._resume_event.set()

    def pause(self) -> None:
        if not self._cancel_event.is_set():
            self._resume_event.clear()

    def resume(self) -> None:
        self._resume_event.set()

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def is_paused(self) -> bool:
        return not self._resume_event.is_set() and not self._cancel_event.is_set()

    def wait_if_paused(self) -> None:
        self._resume_event.wait()

    def cancel_requested(self) -> bool:
        self.wait_if_paused()
        return self.is_cancelled()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise CancelledError("run cancelled")
