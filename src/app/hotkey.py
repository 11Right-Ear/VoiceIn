from __future__ import annotations

import ctypes
import threading
from typing import Callable

# --- Win32 constants ---
MOD_ALT      = 0x0001
MOD_CONTROL  = 0x0002
MOD_SHIFT    = 0x0004
MOD_WIN      = 0x0008
WM_HOTKEY    = 0x0312

VK_S         = 0x53
HOTKEY_ID    = 1

# --- Win32 types & functions ---
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_ulonglong),
        ("lParam", ctypes.c_longlong),
        ("time", ctypes.c_uint),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
    ]


class GlobalHotkey:
    """Register a system-wide hotkey. Runs GetMessageW on a dedicated thread."""

    def __init__(
        self,
        modifiers: int = MOD_ALT | MOD_CONTROL,
        vk: int = VK_S,
        callback: Callable[[], None] | None = None,
    ) -> None:
        self._modifiers = modifiers
        self._vk = vk
        self._callback = callback
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._running = False

    # ----- public -----

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._thread_id:
            _user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    # ----- internal -----

    def _run(self) -> None:
        self._thread_id = _kernel32.GetCurrentThreadId()

        if not _user32.RegisterHotKey(None, HOTKEY_ID, self._modifiers, self._vk):
            print(f"[hotkey] RegisterHotKey failed: {_kernel32.GetLastError()}")
            return

        try:
            msg = _MSG()
            while self._running:
                # GetMessageW returns 0 for WM_QUIT, -1 on error, >0 otherwise
                ret = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:
                    break
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    if self._callback:
                        self._callback()
        finally:
            _user32.UnregisterHotKey(None, HOTKEY_ID)
