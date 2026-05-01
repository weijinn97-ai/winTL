# -*- coding: utf-8 -*-
"""
screen_stream.py — Capture màn hình qua scrcpy H264 stream.

Dùng scrcpy-client để stream video từ device, decode H264, trả numpy array.
Nhanh hơn 10-50x so với adb screencap vì:
  - H264 encoding (GPU trên device) thay vì PNG
  - Stream liên tục thay vì spawn process mỗi lần
  - Không gây tải ADB server

Cài đặt: pip install scrcpy-client
Yêu cầu: adb đang kết nối device

Nếu không cài scrcpy-client, bot tự động dùng ADB screencap (chậm hơn).
"""
import threading
import time
import logging


class ScreenStream:
    """Stream màn hình qua scrcpy. Thread-safe."""

    def __init__(self, device_serial):
        self.device_serial = device_serial
        self._frame = None
        self._frame_time = 0.0
        self._lock = threading.Lock()
        self._client = None
        self._active = False

    def start(self):
        """Khởi động scrcpy stream. Nếu lỗi thì is_active = False."""
        try:
            import scrcpy
            self._client = scrcpy.Client(
                device=self.device_serial,
                max_fps=15,
                bitrate=2_000_000,
            )
            self._client.add_listener(scrcpy.EVENT_FRAME, self._on_frame)
            self._client.start(threaded=True)
            self._active = True
            logging.info("📹 Scrcpy stream OK — capture nhanh hơn 10-50x")
        except ImportError:
            logging.info(
                "💡 Cài scrcpy-client để tăng tốc capture: "
                "pip install scrcpy-client"
            )
        except Exception as e:
            logging.warning(f"Scrcpy stream lỗi: {e}. Dùng ADB screencap.")

    def _on_frame(self, frame):
        if frame is not None:
            with self._lock:
                self._frame = frame
                self._frame_time = time.time()

    def get_frame(self, max_age=0.5):
        """Trả frame mới nhất nếu còn fresh (< max_age giây). Trả None nếu cũ."""
        with self._lock:
            if self._frame is not None and time.time() - self._frame_time < max_age:
                return self._frame.copy()
        return None

    def stop(self):
        self._active = False
        if self._client:
            try:
                self._client.stop()
            except Exception:
                pass
            self._client = None

    @property
    def is_active(self):
        return self._active
