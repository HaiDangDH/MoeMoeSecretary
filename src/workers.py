"""Chạy tác vụ mạng / đọc ghi file trên luồng nền để giao diện luôn mượt.

Một ``Dispatcher`` duy nhất sống ở luồng giao diện; kết quả của mọi tác vụ nền được
gửi về qua signal (queued) nên callback luôn chạy trên luồng giao diện.
Chỉ dùng tối đa 2 luồng nền, luồng rảnh tự thoát sau vài giây để tiết kiệm RAM.

Tác vụ có thể gắn ``key``: một key chỉ có tối đa MỘT tác vụ đang chờ/đang chạy (gọi trùng thì bị
bỏ qua) - dùng cho việc tải trước giọng nói để đổi trang phục liên tục không đẻ ra nhiều luồng
tải cùng một bộ thoại. Sổ key chỉ được đọc/ghi ở luồng giao diện (``submit`` và ``_deliver``) nên
không cần khoá.
"""
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

log = logging.getLogger(__name__)


class _Task(QRunnable):
    def __init__(self, job_id: int, fn: Callable[[], object], sink) -> None:
        super().__init__()
        self._job_id = job_id
        self._fn = fn
        self._sink = sink  # signal (int, object, object) của Dispatcher

    def run(self) -> None:  # chạy ở luồng nền
        value, error = None, None
        try:
            value = self._fn()
        except Exception as exc:  # noqa: BLE001 - gửi mọi lỗi về cho callback
            error = exc
        self._sink.emit(self._job_id, value, error)


class Dispatcher(QObject):
    _result = Signal(int, object, object)

    def __init__(self, max_threads: int = 2, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max_threads)
        self._pool.setExpiryTimeout(5000)
        self._callbacks: dict[int, tuple[Callable | None, Callable | None, str | None]] = {}
        self._active_keys: set[str] = set()
        self._closed = False
        self._counter = 0
        self._result.connect(self._deliver)

    def submit(
        self,
        fn: Callable[[], object],
        on_done: Callable[[object], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        key: str | None = None,
    ) -> int | None:
        """Chạy ``fn`` ở luồng nền. Trả None (không chạy) nếu đã đóng hoặc ``key`` đang có tác vụ."""
        if self._closed:
            return None
        if key is not None:
            if key in self._active_keys:
                return None
            self._active_keys.add(key)
        self._counter += 1
        job_id = self._counter
        self._callbacks[job_id] = (on_done, on_error, key)
        self._pool.start(_Task(job_id, fn, self._result))
        return job_id

    def is_active(self, key: str) -> bool:
        return key in self._active_keys

    @Slot(int, object, object)
    def _deliver(self, job_id: int, value: object, error: object) -> None:
        on_done, on_error, key = self._callbacks.pop(job_id, (None, None, None))
        if key is not None:
            self._active_keys.discard(key)  # giải phóng TRƯỚC callback để callback có thể đặt lại cùng key
        try:
            if error is not None:
                log.info("Tác vụ nền lỗi: %r", error)
                if on_error:
                    on_error(error)  # type: ignore[arg-type]
            elif on_done:
                on_done(value)
        except Exception:  # không để lỗi callback làm sập vòng lặp sự kiện
            log.exception("Lỗi trong callback tác vụ nền")

    def wait_done(self, ms: int = 1500) -> None:
        self._pool.waitForDone(ms)

    def shutdown(self, ms: int = 1500) -> None:
        """Ngừng nhận tác vụ, bỏ các tác vụ chưa chạy và chờ (tối đa ``ms``) tác vụ đang chạy."""
        self._closed = True
        self._pool.clear()
        self._pool.waitForDone(ms)
