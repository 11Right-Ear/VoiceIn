"""录音状态可视化组件"""
import logging
import math
import time
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter

logger = logging.getLogger(__name__)


class RecordingVisualizer:
    """录音状态可视化组件"""

    def __init__(self, frame_size: tuple[int, int]):
        self.width, self.height = frame_size
        self.audio_level: float = 0.0
        self.state: str = "idle"
        self.completion_animation_active: bool = False
        self.completion_start_time: float = 0.0
        self.completion_enabled: bool = True

        self._ring_phases: list[float] = [0.0, 0.0, 0.0]
        self._volume_bar_height: float = 0.0
        self._fade_alpha: float = 1.0
        self._scale: float = 1.0
        self._blink_on: bool = True
        self._last_update_time: float = time.time()

        self._visual_layer: Optional[Image.Image] = None
        self._generate_visual_layer()

    def _generate_visual_layer(self):
        self._visual_layer = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))

    def render(self, frame: Image.Image, state: str, audio_level: float) -> Image.Image:
        """渲染可视化效果到帧图像上"""
        self.state = state
        self.audio_level = audio_level

        result = frame.convert("RGBA")
        if result.size != (self.width, self.height):
            result = result.resize((self.width, self.height), Image.LANCZOS)

        self._update_animation_params()

        if state == "recording":
            visual = self._render_recording_visual()
        elif state == "idle":
            visual = self._render_idle_visual()
        elif state == "completing":
            visual = self._render_completing_visual()
        else:
            visual = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))

        if self._fade_alpha < 1.0:
            visual = self._apply_fade(visual, self._fade_alpha)

        if self._scale != 1.0:
            visual = self._apply_scale(visual, self._scale)

        result = Image.alpha_composite(result, visual)
        return result.convert("RGB")

    def _render_recording_visual(self) -> Image.Image:
        layer = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)

        center_x = self.width // 2
        center_y = self.height // 2

        self._render_sound_waves(draw, center_x, center_y)

        self._render_volume_bar(draw, center_x, center_y - self.height // 4)

        return layer

    def _render_sound_waves(self, draw: ImageDraw.ImageDraw, cx: int, cy: int):
        base_radius = min(self.width, self.height) // 6
        max_expansion = base_radius * 0.8

        for i, phase in enumerate(self._ring_phases):
            energy_factor = max(0.3, self.audio_level)
            radius = base_radius + max_expansion * energy_factor * (1.0 - i * 0.2)

            alpha = int(180 * energy_factor * (1.0 - i * 0.25))
            alpha = max(30, min(200, alpha))

            r = int(0 * (1 - energy_factor) + 0 * energy_factor)
            g = int(255 * energy_factor)
            b = int(255 * (1 - energy_factor * 0.5))

            color = (r, g, b, alpha)

            ring_width = max(2, int(4 * energy_factor))
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                outline=color,
                width=ring_width
            )

    def _render_volume_bar(self, draw: ImageDraw.ImageDraw, cx: int, cy: int):
        bar_width = 8
        max_height = 40
        current_height = int(max_height * self.audio_level)

        current_height = max(2, current_height)

        x1 = cx - bar_width // 2
        x2 = cx + bar_width // 2
        y_base = cy
        y_top = cy - current_height

        if current_height > 0:
            for y in range(y_top, y_base):
                ratio = (y - y_top) / max(1, current_height)

                if ratio < 0.33:
                    r, g, b = 0, 255, 0
                elif ratio < 0.66:
                    r, g, b = 255, 255, 0
                else:
                    r, g, b = 255, 0, 0

                alpha = int(200 * self.audio_level)
                alpha = max(80, min(220, alpha))
                draw.line([(x1, y), (x2, y)], fill=(r, g, b, alpha))

    def _render_idle_visual(self) -> Image.Image:
        layer = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        return layer

    def _render_completing_visual(self) -> Image.Image:
        layer = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        if not self.completion_enabled:
            return layer

        draw = ImageDraw.Draw(layer)

        if self.completion_animation_active:
            elapsed = time.time() - self.completion_start_time
            progress = min(1.0, elapsed / 1.0)

            if progress < 1.0:
                self._render_completion_stars(draw, progress)

        return layer

    def _render_completion_stars(self, draw: ImageDraw.ImageDraw, progress: float):
        center_x = self.width // 2
        center_y = self.height // 2
        base_radius = min(self.width, self.height) // 4

        num_stars = 8
        for i in range(num_stars):
            angle = (2 * math.pi * i) / num_stars + progress * math.pi
            star_radius = base_radius * (0.5 + 0.5 * progress)

            sx = int(center_x + math.cos(angle) * star_radius)
            sy = int(center_y + math.sin(angle) * star_radius)

            star_size = int(6 * (1 - progress) + 2)
            alpha = int(255 * (1 - progress))

            gold = (255, 215, 0, alpha)
            draw.ellipse(
                [sx - star_size, sy - star_size, sx + star_size, sy + star_size],
                fill=gold
            )

            if i % 2 == 0 and progress > 0.3:
                check_size = int(4 * (1 - progress))
                if check_size > 0:
                    check_color = (255, 255, 255, alpha)
                    draw.ellipse(
                        [sx - check_size, sy - check_size, sx + check_size, sy + check_size],
                        fill=check_color
                    )

    def _apply_fade(self, layer: Image.Image, alpha: float) -> Image.Image:
        if alpha >= 1.0:
            return layer
        fade_layer = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        fade_alpha = int(255 * alpha)
        for y in range(layer.size[1]):
            for x in range(layer.size[0]):
                pixel = layer.getpixel((x, y))
                fade_layer.putpixel((x, y), (*pixel[:3], int(pixel[3] * alpha)))
        return fade_layer

    def _apply_scale(self, layer: Image.Image, scale: float) -> Image.Image:
        if abs(scale - 1.0) < 0.01:
            return layer

        w, h = layer.size
        new_w = int(w * scale)
        new_h = int(h * scale)

        scaled = layer.resize((new_w, new_h), Image.LANCZOS)

        result = Image.new("RGBA", (w, h), (0, 0, 0, 0))

        offset_x = (w - new_w) // 2
        offset_y = (h - new_h) // 2

        result.paste(scaled, (offset_x, offset_y))
        return result

    def _update_animation_params(self):
        now = time.time()
        delta = now - self._last_update_time
        self._last_update_time = now

        for i in range(len(self._ring_phases)):
            self._ring_phases[i] += delta * 3.0
            if self._ring_phases[i] > 2 * math.pi:
                self._ring_phases[i] -= 2 * math.pi

        target_volume = self.audio_level
        smoothing = 0.15
        self._volume_bar_height += (target_volume - self._volume_bar_height) * smoothing

        if self.state == "recording":
            self._fade_alpha = min(1.0, self._fade_alpha + delta * 5)
            self._scale = min(1.0, self._scale + delta * 3)
        elif self.state == "idle":
            self._fade_alpha = max(0.0, self._fade_alpha - delta * 3)
            self._scale = max(1.0, self._scale - delta * 2)

        if self.state == "completing":
            self._blink_on = int(now * 4) % 2 == 0

    def set_audio_level(self, level: float):
        """设置音频能量等级 (0.0-1.0)"""
        self.audio_level = max(0.0, min(1.0, level))

    def trigger_completion_animation(self):
        """触发完成动画"""
        if self.completion_enabled:
            self.completion_animation_active = True
            self.completion_start_time = time.time()
            self.state = "completing"
            logger.debug("Completion animation triggered")

    def update(self, delta_time: float):
        """更新动画状态（每帧调用）"""
        self._last_update_time = time.time() - delta_time
        self._update_animation_params()

        if self.completion_animation_active:
            elapsed = time.time() - self.completion_start_time
            if elapsed >= 1.0:
                self.completion_animation_active = False
                logger.debug("Completion animation finished")

    def get_current_visual_frame(self) -> Optional[Image.Image]:
        """获取当前可视化层图像（不含基础帧）"""
        if self._visual_layer is None:
            return None

        layer_copy = self._visual_layer.copy()

        if self.state == "recording":
            draw = ImageDraw.Draw(layer_copy)
            self._render_sound_waves(draw, self.width // 2, self.height // 2)
            self._render_volume_bar(draw, self.width // 2, self.height // 4)

        return layer_copy

    def destroy(self):
        """释放资源"""
        self._visual_layer = None
        logger.debug("RecordingVisualizer resources released")
