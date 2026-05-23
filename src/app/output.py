from __future__ import annotations

import ctypes
import time

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

# --- Win32 type setup (required for 64-bit) ---
HANDLE = ctypes.c_void_p
HGLOBAL = HANDLE
LPVOID = ctypes.c_void_p
BOOL = ctypes.c_int
UINT = ctypes.c_uint

_user32.OpenClipboard.argtypes = [HANDLE]
_user32.OpenClipboard.restype = BOOL
_user32.CloseClipboard.argtypes = []
_user32.CloseClipboard.restype = BOOL
_user32.EmptyClipboard.argtypes = []
_user32.EmptyClipboard.restype = BOOL
_user32.GetClipboardData.argtypes = [UINT]
_user32.GetClipboardData.restype = HANDLE
_user32.SetClipboardData.argtypes = [UINT, HANDLE]
_user32.SetClipboardData.restype = HANDLE

_kernel32.GlobalAlloc.argtypes = [UINT, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = HGLOBAL
_kernel32.GlobalLock.argtypes = [HGLOBAL]
_kernel32.GlobalLock.restype = LPVOID
_kernel32.GlobalUnlock.argtypes = [HGLOBAL]
_kernel32.GlobalUnlock.restype = BOOL

# Keyboard
_user32.keybd_event.argtypes = [ctypes.c_byte, ctypes.c_byte, ctypes.c_uint, ctypes.c_void_p]
_user32.keybd_event.restype = None

CF_UNICODETEXT = 13
VK_CONTROL = 0x11
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002
GMEM_MOVEABLE = 0x0002


def paste(text: str) -> None:
    """Paste text at the current cursor position, preserving clipboard contents."""

    if not text.strip():
        return

    backup = _get_clipboard_text()
    _set_clipboard_text(text)
    _send_ctrl_v()
    time.sleep(0.05)

    if backup is not None:
        _set_clipboard_text(backup)


def _get_clipboard_text() -> str | None:
    if not _user32.OpenClipboard(None):
        return None
    try:
        handle = _user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = _kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            _kernel32.GlobalUnlock(handle)
    finally:
        _user32.CloseClipboard()


def _set_clipboard_text(text: str) -> bool:
    if not _user32.OpenClipboard(None):
        return False
    try:
        _user32.EmptyClipboard()
        size = (len(text) + 1) * ctypes.sizeof(ctypes.c_wchar)
        handle = _kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not handle:
            return False
        ptr = _kernel32.GlobalLock(handle)
        if not ptr:
            _kernel32.GlobalFree(handle)
            return False
        ctypes.memmove(ptr, text, size - ctypes.sizeof(ctypes.c_wchar))
        _kernel32.GlobalUnlock(handle)
        _user32.SetClipboardData(CF_UNICODETEXT, handle)
        return True
    finally:
        _user32.CloseClipboard()


def _send_ctrl_v() -> None:
    _user32.keybd_event(VK_CONTROL, 0, 0, 0)
    _user32.keybd_event(VK_V, 0, 0, 0)
    _user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    _user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
