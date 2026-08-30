from __future__ import annotations

import math
from typing import Literal

from PIL import Image, ImageDraw


class PetDrawer:
    FRAME_SIZE = 32

    IDLE_FRAMES = 20
    REC_FRAMES = 6
    THINK_FRAMES = 4

    def __init__(self) -> None:
        self._idle_frames = self._generate_idle_frames()
        self._rec_frames = self._generate_rec_frames()
        self._think_frames = self._generate_think_frames()

    def get_frames(self, state: Literal["idle", "recording", "thinking"]) -> list[Image.Image]:
        if state == "idle":
            return self._idle_frames
        if state == "recording":
            return self._rec_frames
        if state == "thinking":
            return self._think_frames
        return self._idle_frames

    def _generate_idle_frames(self) -> list[Image.Image]:
        frames = []
        for i in range(self.IDLE_FRAMES):
            t = i / self.IDLE_FRAMES
            bob = round(2 * math.sin(2 * math.pi * t))
            frames.append(self._draw_robot(bob_offset=bob))
        return frames

    def _generate_rec_frames(self) -> list[Image.Image]:
        frames = []
        for i in range(self.REC_FRAMES):
            mouth_open = (i % 2 == 0)
            frames.append(self._draw_robot(mouth_open=mouth_open))
        return frames

    def _generate_think_frames(self) -> list[Image.Image]:
        frames = []
        for i in range(self.THINK_FRAMES):
            dots = (i % 3) + 1
            frames.append(self._draw_robot(think_dots=dots))
        return frames

    def _draw_robot(
        self,
        bob_offset: int = 0,
        mouth_open: bool = False,
        think_dots: int = 0,
    ) -> Image.Image:
        img = Image.new("RGBA", (self.FRAME_SIZE, self.FRAME_SIZE), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        cx = self.FRAME_SIZE // 2
        base_y = 8 + bob_offset

        head_color = "#4A90D9"
        d.rounded_rectangle([cx - 8, base_y, cx + 8, base_y + 14], radius=4, fill=head_color)

        eye_white = "#FFFFFF"
        d.ellipse([cx - 6, base_y + 3, cx - 3, base_y + 7], fill=eye_white)
        d.ellipse([cx + 3, base_y + 3, cx + 6, base_y + 7], fill=eye_white)
        d.ellipse([cx - 5, base_y + 4, cx - 4, base_y + 6], fill="#222222")
        d.ellipse([cx + 4, base_y + 4, cx + 5, base_y + 6], fill="#222222")

        if think_dots > 0:
            for j in range(think_dots):
                d.ellipse(
                    [cx - 4 + j * 4, base_y + 10, cx - 2 + j * 4, base_y + 12],
                    fill="#FFFFFF",
                )
        elif mouth_open:
            d.ellipse([cx - 3, base_y + 9, cx + 3, base_y + 13], fill="#222222")
        else:
            d.arc(
                [cx - 3, base_y + 9, cx + 3, base_y + 13],
                start=0,
                end=180,
                fill="#FFFFFF",
                width=1,
            )

        body_color = "#357ABD"
        d.polygon(
            [
                (cx - 6, base_y + 14),
                (cx + 6, base_y + 14),
                (cx + 5, base_y + 20),
                (cx - 5, base_y + 20),
            ],
            fill=body_color,
        )

        return img
