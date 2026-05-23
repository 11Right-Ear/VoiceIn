from __future__ import annotations

import ctypes
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

# ---------------------------------------------------------------------------
# DLL load — search relative to this file for development, next to exe for distribution
# ---------------------------------------------------------------------------
_dll_dir = Path(__file__).resolve().parent
_dll_candidates = [
    _dll_dir / "audio_capture.dll",
    _dll_dir.parent / "native" / "build" / "Release" / "audio_capture.dll",
]

_dll_path = None
for _p in _dll_candidates:
    if _p.exists():
        _dll_path = str(_p)
        break

if _dll_path is None:
    raise RuntimeError(
        "Cannot find audio_capture.dll. "
        "Build it with: cmake -B src/native/build -S src/native && cmake --build src/native/build --config Release"
    )

_dll = ctypes.CDLL(_dll_path)

# ---------------------------------------------------------------------------
# C type bindings
# ---------------------------------------------------------------------------

class _CDeviceInfo(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_wchar * 256),
        ("id", ctypes.c_int),
        ("max_channels", ctypes.c_int),
        ("default_sample_rate", ctypes.c_int),
    ]

_CallbackType = ctypes.CFUNCTYPE(
    None,
    ctypes.POINTER(ctypes.c_float),  # samples
    ctypes.c_int,                     # n_samples
    ctypes.c_int,                     # sample_rate
)

# --- Bind function signatures ---

_dll.audio_list_devices.argtypes = [ctypes.POINTER(ctypes.POINTER(_CDeviceInfo))]
_dll.audio_list_devices.restype = ctypes.c_int

_dll.audio_free_device_list.argtypes = [ctypes.POINTER(_CDeviceInfo)]
_dll.audio_free_device_list.restype = None

_dll.audio_init.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
_dll.audio_init.restype = ctypes.c_int

_dll.audio_start.argtypes = [_CallbackType]
_dll.audio_start.restype = ctypes.c_int

_dll.audio_stop.argtypes = []
_dll.audio_stop.restype = ctypes.c_int

_dll.audio_close.argtypes = []
_dll.audio_close.restype = None

_dll.audio_last_error.argtypes = []
_dll.audio_last_error.restype = ctypes.c_wchar_p


def _check(rc: int) -> None:
    if rc != 0:
        msg = _dll.audio_last_error()
        raise RuntimeError(f"audio_capture error (code={rc}): {msg}")


# ---------------------------------------------------------------------------
# Python types
# ---------------------------------------------------------------------------

@dataclass
class DeviceInfo:
    id: int
    name: str
    max_channels: int
    default_sample_rate: int


Callback = Callable[[np.ndarray, int], None]
"""Callback(samples: np.ndarray[dtype=float32], sample_rate: int) -> None"""


# ---------------------------------------------------------------------------
# AudioCapture
# ---------------------------------------------------------------------------

class AudioCapture:
    def __init__(
        self,
        device_id: int = -1,
        sample_rate: int = 16000,
        channels: int = 1,
        block_ms: int = 100,
    ) -> None:
        self._device_id = device_id
        self._sample_rate = sample_rate
        self._channels = channels
        self._block_ms = block_ms

        self._initialized = False

        # Consumer thread state
        self._consumer_thread: threading.Thread | None = None
        self._queue: queue.Queue[np.ndarray | None] | None = None
        self._user_callback: Callback | None = None
        self._running = False

    # ----- device enumeration -----

    @staticmethod
    def list_devices() -> list[DeviceInfo]:
        devices_ptr = ctypes.POINTER(_CDeviceInfo)()
        count = _dll.audio_list_devices(ctypes.byref(devices_ptr))
        if count < 0:
            raise RuntimeError(f"audio_list_devices failed: {_dll.audio_last_error()}")
        result = []
        for i in range(count):
            cd = devices_ptr[i]
            result.append(DeviceInfo(
                id=cd.id,
                name=cd.name,
                max_channels=cd.max_channels,
                default_sample_rate=cd.default_sample_rate,
            ))
        _dll.audio_free_device_list(devices_ptr)
        return result

    # ----- lifecycle -----

    def start(self, callback: Callback) -> None:
        if self._running:
            raise RuntimeError("Already capturing")
        if not callback:
            raise ValueError("callback must not be None")

        if not self._initialized:
            _check(_dll.audio_init(self._device_id, self._sample_rate, self._channels, self._block_ms))
            self._initialized = True

        self._user_callback = callback
        self._queue = queue.Queue()
        self._running = True

        # Keep a reference to prevent GC on the ctypes callback
        self._c_callback = _CallbackType(self._on_audio_c)

        self._consumer_thread = threading.Thread(target=self._consumer_loop, daemon=True)
        self._consumer_thread.start()

        _check(_dll.audio_start(self._c_callback))

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False

        _dll.audio_stop()

        if self._queue is not None:
            # Signal consumer to exit
            try:
                self._queue.put(None, timeout=1.0)
            except queue.Full:
                pass

        if self._consumer_thread is not None:
            self._consumer_thread.join(timeout=3.0)
            self._consumer_thread = None

        self._queue = None
        self._user_callback = None
        self._c_callback = None

    def close(self) -> None:
        self.stop()
        _dll.audio_close()
        self._initialized = False

    # ----- internal -----

    def _on_audio_c(self, c_samples: ctypes.POINTER(ctypes.c_float), n_samples: int, sample_rate: int) -> None:
        """Called from C++ capture thread. Copy data and enqueue immediately."""
        if self._queue is None or n_samples <= 0:
            return
        # Copy — the C pointer is only valid during this callback
        data = np.ctypeslib.as_array(c_samples, shape=(n_samples,)).copy()
        try:
            self._queue.put_nowait(data)
        except queue.Full:
            pass  # drop if consumer can't keep up

    def _consumer_loop(self) -> None:
        """Runs on dedicated Python thread. Dequeues and calls user callback."""
        while self._running:
            try:
                data = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if data is None:
                break  # stop signal
            if self._user_callback is not None and len(data) > 0:
                self._user_callback(data, self._sample_rate)

        # Drain remaining items
        if self._queue is not None and self._user_callback is not None:
            while not self._queue.empty():
                try:
                    data = self._queue.get_nowait()
                except queue.Empty:
                    break
                if data is not None and len(data) > 0:
                    self._user_callback(data, self._sample_rate)
