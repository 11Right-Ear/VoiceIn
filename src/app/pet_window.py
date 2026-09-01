"""VoiceIn 桌面宠物 — tkinter 无边框透明窗口（独立线程运行）"""
from __future__ import annotations

import logging
import math
import queue
import threading
import time
from typing import Callable, Literal

try:
    import tkinter as tk
except ImportError:
    raise ImportError("tkinter is required for pet_window")

from PIL import Image, ImageTk, ImageDraw

_logger = logging.getLogger("pet_window")


def _default_pet_image(size: int = 128) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = size // 2
    base_y = size // 4
    head_color = "#4A90D9"
    head_r = size // 6
    d.rounded_rectangle(
        [cx - head_r, base_y, cx + head_r, base_y + head_r * 2],
        radius=head_r // 2,
        fill=head_color,
    )
    eye_y = base_y + head_r // 2
    eye_r = head_r // 4
    d.ellipse([cx - head_r + 4, eye_y, cx - 4, eye_y + eye_r * 2], fill="#FFFFFF")
    d.ellipse([cx + 4, eye_y, cx + head_r - 4, eye_y + eye_r * 2], fill="#FFFFFF")
    d.ellipse([cx - head_r + 6, eye_y + 2, cx - 6, eye_y + eye_r * 2 - 2], fill="#222222")
    d.ellipse([cx + 6, eye_y + 2, cx + head_r - 6, eye_y + eye_r * 2 - 2], fill="#222222")
    mouth_y = base_y + head_r + 4
    d.ellipse([cx - head_r // 2, mouth_y, cx + head_r // 2, mouth_y + head_r // 2], fill="#333333")
    return img


class PetWindow:
    """基于 tkinter 的无边框透明宠物窗口（独立线程运行）。"""

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or {}

        default_size = cfg.get("default_size", 128)
        self._default_size = max(16, min(512, default_size))

        self._always_on_top = cfg.get("always_on_top", True)
        self._hide_hotkey_modifiers = cfg.get("hide_hotkey_modifiers", 0)
        self._hide_hotkey_vk = cfg.get("hide_hotkey_vk", 0x48)

        self._state: Literal["idle", "recording", "recognizing", "completed"] = "idle"
        self._audio_level = 0.0
        self._state_callbacks: list[Callable[[str], None]] = []
        self._click_callback: Callable[[], None] | None = None

        self._running = False
        self._visible = False

        self._x = 0
        self._y = 0
        self._default_pos = cfg.get("default_pos", None)

        self._msg_queue: queue.Queue = queue.Queue()

        self._tk_thread: threading.Thread | None = None
        self._tk: tk.Tk | None = None
        self._canvas: tk.Canvas | None = None
        self._photo_image: ImageTk.PhotoImage | None = None

        # 水波涟漪动画时间
        self._ripple_time = 0.0
        self._ripple_lock = threading.Lock()

    def show(self) -> None:
        if self._running and self._visible:
            self._msg_queue.put(("show", None))
            return

        if not self._running:
            self._start_tk_thread()

        self._running = True
        self._visible = True
        self._msg_queue.put(("show", None))
        _logger.info("PetWindow shown")

    def hide(self) -> None:
        self._visible = False
        self._msg_queue.put(("hide", None))
        _logger.debug("Pet hidden")

    def toggle_visibility(self) -> None:
        if self._visible:
            self.hide()
        else:
            self.show()

    def set_state(self, state: str) -> None:
        if state not in ("idle", "recording", "recognizing", "completed"):
            return
        if state == self._state:
            return
        self._state = state
        self._msg_queue.put(("state", state))

    def set_audio_level(self, level: float) -> None:
        self._audio_level = max(0.0, min(1.0, level))
        self._msg_queue.put(("audio_level", level))

    def set_position(self, x: int, y: int) -> None:
        self._x = x
        self._y = y
        self._msg_queue.put(("position", (x, y)))

    def get_position(self) -> tuple[int, int]:
        return (self._x, self._y)

    def destroy(self) -> None:
        self._running = False
        self._msg_queue.put(("destroy", None))
        if self._tk_thread and self._tk_thread.is_alive():
            self._tk_thread.join(timeout=2.0)
        _logger.info("PetWindow destroyed")

    def register_state_callback(self, callback: Callable[[str], None]) -> None:
        self._state_callbacks.append(callback)

    def register_click_callback(self, callback: Callable[[], None]) -> None:
        """注册点击回调。"""
        self._click_callback = callback

    def _start_tk_thread(self) -> None:
        self._tk_thread = threading.Thread(target=self._tk_mainloop, daemon=True)
        self._tk_thread.start()

    def _tk_mainloop(self) -> None:
        self._tk = tk.Tk()
        self._tk.title("VoiceIn Pet")
        self._tk.configure(bg="#000000")

        if self._default_pos:
            x, y = self._default_pos
        else:
            sw = self._tk.winfo_screenwidth()
            sh = self._tk.winfo_screenheight()
            x = (sw - self._default_size) // 2
            y = (sh - self._default_size) // 2
        self._x = x
        self._y = y

        self._tk.geometry(f"{self._default_size}x{self._default_size}+{x}+{y}")
        self._tk.overrideredirect(True)
        self._tk.attributes("-transparentcolor", "#000000")
        self._tk.attributes("-topmost", self._always_on_top)

        self._canvas = tk.Canvas(
            self._tk,
            width=self._default_size,
            height=self._default_size,
            bg="#000000",
            highlightthickness=0,
            bd=0,
        )
        self._canvas.pack(fill="both", expand=True)

        self._canvas.bind("<Button-1>", self._on_click)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Button-3>", self._on_right_click)

        # 创建右键菜单
        self._create_context_menu()

        self._tk.protocol("WM_DELETE_WINDOW", lambda: None)
        self._tk.withdraw()

        self._start_time = time.time()

        def process_messages() -> None:
            if not self._running:
                self._tk.quit()
                return

            try:
                while True:
                    msg = self._msg_queue.get_nowait()
                    cmd, data = msg
                    if cmd == "show":
                        try:
                            self._tk.deiconify()
                        except tk.TclError:
                            pass
                    elif cmd == "hide":
                        try:
                            self._tk.withdraw()
                        except tk.TclError:
                            pass
                    elif cmd == "state":
                        self._render_frame()
                    elif cmd == "audio_level":
                        self._render_frame()
                    elif cmd == "position":
                        if data:
                            x, y = data
                            self._x, self._y = x, y
                            self._tk.geometry(f"{self._default_size}x{self._default_size}+{x}+{y}")
                    elif cmd == "destroy":
                        self._running = False
                        self._tk.quit()
                        return
            except queue.Empty:
                pass

            # 更新水波动画时间
            self._ripple_time = time.time() - self._start_time

            self._render_frame()

            self._tk.after(33, process_messages)

        self._render_frame()
        self._tk.after(33, process_messages)
        self._tk.mainloop()

    def _create_context_menu(self) -> None:
        """创建右键菜单。"""
        self._context_menu = tk.Menu(self._tk, tearoff=0, bg="#2d2d2d", fg="white", bd=0)
        self._context_menu.add_command(label="🎤 开始录音", command=self._on_menu_record)
        self._context_menu.add_command(label="📌 固定位置", command=self._on_menu_pin)
        self._context_menu.add_command(label="❌ 退出", command=self._on_menu_quit)

    def _on_menu_record(self) -> None:
        """菜单：开始/停止录音。"""
        if self._click_callback:
            self._click_callback()

    def _on_menu_pin(self) -> None:
        """菜单：固定/取消固定位置。"""
        self._msg_queue.put(("toggle_pin", None))

    def _on_menu_quit(self) -> None:
        """菜单：退出程序。"""
        self._msg_queue.put(("quit", None))

    def _render_frame(self) -> None:
        if self._canvas is None or not self._visible:
            return
        try:
            if self._state == "recording":
                img = self._recording_image()
            else:
                img = _default_pet_image(self._default_size)
            self._photo_image = ImageTk.PhotoImage(img)
            self._canvas.delete("all")
            self._canvas.create_image(
                self._default_size // 2,
                self._default_size // 2,
                image=self._photo_image,
                anchor="center",
            )
        except Exception as e:
            _logger.warning("Render error: %s", e)

    def _recording_image(self) -> Image.Image:
        """生成带水波涟漪效果的录音图像。"""
        img = _default_pet_image(self._default_size)
        d = ImageDraw.Draw(img)

        cx = self._default_size // 2
        cy = self._default_size // 2

        # 水波涟漪效果：多个波纹从中心向外扩散
        num_waves = 5
        base_radius = 15 + self._audio_level * 10

        for i in range(num_waves):
            # 波纹相位随时间和索引偏移，形成持续的涟漪
            phase = self._ripple_time * 3 + i * 0.8
            # 半径随时间周期性变化
            wave_radius = base_radius + i * 12 + math.sin(phase) * 8

            # 透明度从内到外递减，形成层次感
            alpha = int(180 * (1 - i / num_waves) * (0.4 + self._audio_level * 0.6))

            # 计算弧线的起点和终点，形成不完整的圆弧，更像真实水波
            start_angle = math.sin(phase * 0.7 + i) * 30
            end_angle = 360 - math.cos(phase * 0.5 + i * 0.5) * 30

            # 绘制椭圆弧线，模拟水波涟漪
            if wave_radius > 5:
                # 外层大波纹
                x1 = cx - wave_radius
                y1 = cy - wave_radius * 0.7  # 椭圆，模拟水面透视
                x2 = cx + wave_radius
                y2 = cy + wave_radius * 0.7

                # 颜色：青色到蓝色渐变
                blue = int(200 + 55 * (i / num_waves))
                color = (80, 180 + int(20 * (1 - i/num_waves)), blue, alpha)

                # 绘制弧线而不是完整椭圆，更有水波感
                d.arc([x1, y1, x2, y2], int(start_angle), int(end_angle), fill=color, width=2)

                # 在弧线上添加一些波动的点，模拟水面波光
                if i < 3 and self._audio_level > 0.3:
                    num_dots = 3
                    for j in range(num_dots):
                        dot_phase = phase + j * (math.pi * 2 / num_dots)
                        dot_x = cx + math.cos(dot_phase) * wave_radius * 0.8
                        dot_y = cy + math.sin(dot_phase) * wave_radius * 0.5
                        dot_alpha = int(alpha * 0.6 * (1 - j / num_dots))
                        dot_color = (100, 220, 255, dot_alpha)
                        d.ellipse([dot_x - 2, dot_y - 2, dot_x + 2, dot_y + 2], fill=dot_color)

        return img

    def _on_click(self, event) -> None:
        """左键点击：触发录音热键。"""
        self._msg_queue.put(("click", None))

    def _on_right_click(self, event) -> None:
        """右键点击：显示菜单。"""
        try:
            self._context_menu.tk_popup(event.x_root, event.y_root)
        except Exception:
            pass

    def _on_drag(self, event) -> None:
        new_x = event.x_root - self._default_size // 2
        new_y = event.y_root - self._default_size // 2
        self._x = new_x
        self._y = new_y
        self._tk.geometry(f"{self._default_size}x{self._default_size}+{new_x}+{new_y}")

    def _on_release(self, event) -> None:
        self._snap_to_nearest_edge()

    def _snap_to_nearest_edge(self) -> None:
        snap_distance = 20
        try:
            sw = self._tk.winfo_screenwidth()
            sh = self._tk.winfo_screenheight()
        except tk.TclError:
            return

        new_x, new_y = self._x, self._y

        if new_x < snap_distance:
            new_x = 0
        elif new_x + self._default_size > sw - snap_distance:
            new_x = sw - self._default_size

        if new_y < snap_distance:
            new_y = 0
        elif new_y + self._default_size > sh - snap_distance:
            new_y = sh - self._default_size

        if new_x != self._x or new_y != self._y:
            self._x = new_x
            self._y = new_y
            self._tk.geometry(f"{self._default_size}x{self._default_size}+{new_x}+{new_y}")
