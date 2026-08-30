from __future__ import annotations

import threading
import time
from typing import Callable, Literal

import pystray
from PIL import Image

from pet import PetDrawer


class PetTray:
    def __init__(
        self,
        tip: str = "VoiceIn",
        on_left_click: Callable[[], None] | None = None,
        on_right_click: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
    ) -> None:
        self._tip = tip
        self._on_left_click = on_left_click
        self._on_right_click = on_right_click
        self._on_quit = on_quit

        self._pet_drawer = PetDrawer()
        self._frames: list[Image.Image] = self._pet_drawer.get_frames("idle")
        self._frame_index = 0
        self._state: Literal["idle", "recording", "thinking"] = "idle"
        self._running = False
        self._lock = threading.Lock()

        # Left-click = first menu item (default action)
        # Right-click = full menu
        menu = pystray.Menu(
            pystray.MenuItem("开始/停止录音", self._on_left_click_menu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("关于 VoiceIn", self._on_about),
            pystray.MenuItem("退出", self._on_quit_menu),
        )

        self._icon = pystray.Icon(
            "VoiceIn",
            self._frames[0],
            self._tip,
            menu,
        )

        # Animation
        self._running = True
        self._anim_thread = threading.Thread(target=self._animator_loop, daemon=True)
        self._anim_thread.start()

    # ----- animation -----

    def _animator_loop(self) -> None:
        interval = 0.1
        while True:
            with self._lock:
                if not self._running:
                    break
            self._advance_frame()
            time.sleep(interval)

    def _advance_frame(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._frame_index = (self._frame_index + 1) % len(self._frames)
            frame = self._frames[self._frame_index]

        self._icon.icon = frame

    def set_state(self, state: Literal["idle", "recording", "thinking"]) -> None:
        with self._lock:
            if state == self._state:
                return
            self._state = state
            self._frames = self._pet_drawer.get_frames(state)
            self._frame_index = 0

    def set_recording(self, recording: bool) -> None:
        self.set_state("recording" if recording else "idle")

    # ----- menu actions -----

    def _on_left_click_menu(self, icon: pystray.Icon) -> None:
        if self._on_left_click:
            self._on_left_click()

    def _on_about(self, icon: pystray.Icon) -> None:
        self.notify("VoiceIn", "极简中英文语音输入工具\nCtrl+Alt+S 开始")

    def _on_quit_menu(self, icon: pystray.Icon) -> None:
        if self._on_quit:
            self._on_quit()
        icon.stop()

    def notify(self, title: str, msg: str) -> None:
        try:
            self._icon.notify(msg, title)
        except Exception:
            pass

    def run(self) -> None:
        self._icon.run()

    def stop(self) -> None:
        with self._lock:
            self._running = False

        try:
            self._icon.stop()
        except Exception:
            pass
