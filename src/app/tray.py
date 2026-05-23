from __future__ import annotations

from PIL import Image, ImageDraw
import pystray


# ---------------------------------------------------------------------------
# Generate microphone icons at runtime (no external files)
# ---------------------------------------------------------------------------

def _make_mic_icon(color: str, size: int = 32) -> Image.Image:
    """Draw a simple microphone icon."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = size // 2
    r = size // 6

    # Mic body (rounded rect / circle top + rect bottom)
    body_top = m - r - 2
    body_bottom = m + r - 2
    body_left = m - r + 2
    body_right = m + r - 2
    d.rounded_rectangle([body_left, body_top, body_right, body_bottom],
                        radius=r, fill=color)

    # Mic stand (line down)
    stand_top = body_bottom
    stand_bottom = size - 4
    d.arc([m - r, stand_top, m + r, stand_top + r * 2],
          start=180, end=360, fill=color, width=3)

    # Base line
    base_y = stand_bottom
    d.line([m - r, base_y, m + r, base_y], fill=color, width=3)

    return img


# ---------------------------------------------------------------------------
# TrayIcon
# ---------------------------------------------------------------------------

class TrayIcon:
    def __init__(self, on_quit=None) -> None:
        self._icon_idle = _make_mic_icon("#888888")
        self._icon_rec = _make_mic_icon("#E74C3C")
        self._recording = False
        self._on_quit = on_quit

        menu = pystray.Menu(
            pystray.MenuItem("关于 VoiceIn", self._about),
            pystray.MenuItem("退出", self._quit),
        )

        self._tray = pystray.Icon(
            "VoiceIn",
            self._icon_idle,
            "VoiceIn — Ctrl+Alt+S 开始语音输入",
            menu,
        )

    # ----- public -----

    def run(self) -> None:
        self._tray.run()

    def stop(self) -> None:
        self._tray.stop()

    def set_recording(self, recording: bool) -> None:
        if recording == self._recording:
            return
        self._recording = recording
        icon = self._icon_rec if recording else self._icon_idle
        self._tray.icon = icon
        if recording:
            self._tray.title = "VoiceIn — 正在录音... 再次按热键停止"
        else:
            self._tray.title = "VoiceIn — Ctrl+Alt+S 开始语音输入"

    def notify(self, title: str, msg: str) -> None:
        self._tray.notify(title, msg)

    # ----- internal -----

    def _about(self, icon, item) -> None:
        self.notify("VoiceIn v1.0", "中文语音输入工具\n本地引擎: Sherpa-ONNX")

    def _quit(self, icon, item) -> None:
        if self._on_quit:
            self._on_quit()
        self._tray.stop()
