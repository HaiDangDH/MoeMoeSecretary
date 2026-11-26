"""Trình phát giọng nói siêu nhẹ dựa trên ``miniaudio`` (không cần pygame).

- Chỉ mở thiết bị âm thanh khi cần phát và đóng ngay khi phát xong, nên lúc nghỉ
  không tốn CPU/RAM cho luồng âm thanh.
- Mọi lỗi (thiếu thư viện, file hỏng, không có loa...) chỉ được ghi log, không làm
  hỏng ứng dụng.
"""
from __future__ import annotations

import array
import logging
import threading
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

SAMPLE_RATE = 44100
CHANNELS = 2


def _chunks(samples: "array.array", gain: float):
    """Generator cấp dữ liệu cho miniaudio, áp dụng âm lượng theo từng khối nhỏ."""
    pos, total = 0, len(samples)
    required_frames = yield b""  # khởi tạo generator
    while pos < total:
        count = (required_frames or 1024) * CHANNELS
        chunk = samples[pos : pos + count]
        pos += count
        if gain < 0.999:
            chunk = array.array("h", [int(s * gain) for s in chunk])
        required_frames = yield chunk


class VoicePlayer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._device = None
        self._timer: threading.Timer | None = None

    # ------------------------------------------------------------------
    def play(self, path: Path, volume: int, still_current: Callable[[], bool] | None = None) -> None:
        """Phát file âm thanh (không chặn). ``volume``: 0-100.

        ``still_current`` được hỏi BÊN TRONG khoá ngay trước khi mở thiết bị: nếu câu thoại này đã
        bị câu mới hơn thay thế thì không phát. Nhờ vậy ``stop()`` của câu mới (gọi ở luồng giao
        diện) và ``play()`` của câu cũ (đang chạy ở luồng nền) không thể chồng tiếng lên nhau,
        kể cả khi nhấp chuột liên tiếp rất nhanh.
        """
        if volume <= 0:
            return
        try:
            import miniaudio
        except ImportError:
            log.warning("Thiếu thư viện miniaudio - bỏ qua phát giọng nói")
            return

        try:
            decoded = miniaudio.decode_file(
                str(path),
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=CHANNELS,
                sample_rate=SAMPLE_RATE,
            )
        except Exception as exc:
            log.warning("Không giải mã được %s: %s", path.name, exc)
            return

        samples = decoded.samples
        duration = len(samples) / (CHANNELS * SAMPLE_RATE)
        gain = (max(1, min(100, volume)) / 100.0) ** 2  # đường cong tự nhiên hơn tuyến tính

        with self._lock:
            if still_current is not None and not still_current():
                return
            self._stop_locked()
            try:
                device = miniaudio.PlaybackDevice(
                    output_format=miniaudio.SampleFormat.SIGNED16,
                    nchannels=CHANNELS,
                    sample_rate=SAMPLE_RATE,
                )
                gen = _chunks(samples, gain)
                next(gen)  # làm "nóng" generator (an toàn dù thư viện có tự gọi next hay không)
                device.start(gen)
            except Exception as exc:
                log.warning("Không mở được thiết bị âm thanh: %s", exc)
                return
            self._device = device
            self._timer = threading.Timer(duration + 0.3, self._finish, args=(device,))
            self._timer.daemon = True
            self._timer.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    shutdown = stop

    # ------------------------------------------------------------------
    def _finish(self, device) -> None:
        with self._lock:
            if self._device is device:
                self._stop_locked()

    def _stop_locked(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        device, self._device = self._device, None
        if device is not None:
            try:
                device.stop()
                device.close()
            except Exception as exc:  # pragma: no cover
                log.debug("Lỗi khi đóng thiết bị âm thanh: %s", exc)
