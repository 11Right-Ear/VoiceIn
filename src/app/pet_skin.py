"""Desktop pet skin system with built-in and custom pixel art skins."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Skin info dataclass
# ---------------------------------------------------------------------------

@dataclass
class SkinInfo:
    """Skin information."""
    id: str
    name: str
    author: str
    version: str
    frame_size: tuple[int, int]
    frame_rate: int
    animations: dict[str, list[str]]

    @property
    def animation_states(self) -> list[str]:
        """Get list of animation state names."""
        return list(self.animations.keys())

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "author": self.author,
            "version": self.version,
            "frame_size": list(self.frame_size),
            "frame_rate": self.frame_rate,
            "animations": self.animations,
        }

    @classmethod
    def from_dict(cls, data: dict, skin_id: str) -> SkinInfo:
        """Create from dictionary."""
        # Validate frame_size
        frame_size_raw = data.get("frame_size", [64, 64])
        if not isinstance(frame_size_raw, (list, tuple)) or len(frame_size_raw) != 2:
            frame_size = (64, 64)
        else:
            frame_size = (int(frame_size_raw[0]), int(frame_size_raw[1]))

        # Validate animations
        animations_raw = data.get("animations", {})
        if not isinstance(animations_raw, dict):
            animations = {}
        else:
            animations = {}
            for state, frames in animations_raw.items():
                if isinstance(frames, list) and all(isinstance(f, str) for f in frames):
                    animations[state] = frames

        return cls(
            id=skin_id,
            name=data.get("name", "Unnamed Skin"),
            author=data.get("author", "Unknown"),
            version=data.get("version", "1.0"),
            frame_size=frame_size,
            frame_rate=data.get("frame_rate", 60),
            animations=animations,
        )


# ---------------------------------------------------------------------------
# Built-in skin generators
# ---------------------------------------------------------------------------

class BuiltInSkinGenerator:
    """Generates built-in pixel art skins using Pillow."""

    # Color palettes for each skin
    PALETTES = {
        "pixel_bird": {
            "body": "#4A90D9",
            "body_light": "#6BA3E0",
            "body_dark": "#357ABD",
            "eye": "#FFFFFF",
            "pupil": "#222222",
            "beak": "#F5A623",
            "cheek": "#FFB6C1",
        },
        "pixel_cat": {
            "body": "#F5A623",
            "body_light": "#F7B855",
            "body_dark": "#D4891A",
            "eye": "#50C878",
            "pupil": "#222222",
            "nose": "#FFB6C1",
            "whisker": "#FFFFFF",
        },
        "pixel_fox": {
            "body": "#E74C3C",
            "body_light": "#EC6A5E",
            "body_dark": "#C0392B",
            "eye": "#FFFFFF",
            "pupil": "#222222",
            "belly": "#FFFFFF",
            "ear_inner": "#FFB6C1",
        },
        "pixel_ghost": {
            "body": "#FFFFFF",
            "body_light": "#F8F8FF",
            "body_dark": "#E8E8F0",
            "eye": "#6B5B95",
            "blush": "#FFB6C1",
            "tail": "#E8E8F0",
        },
        "pixel_robot": {
            "body": "#4A90D9",
            "body_light": "#6BA3E0",
            "body_dark": "#357ABD",
            "eye": "#FFFFFF",
            "pupil": "#222222",
            "mouth": "#222222",
            "antenna": "#E74C3C",
        },
    }

    @classmethod
    def generate_skin(
        cls,
        skin_id: str,
        size: int = 64,
    ) -> dict[str, Image.Image]:
        """
        Generate all animation frames for a built-in skin.

        Returns:
            Dictionary mapping state names to lists of frames.
        """
        generator_map = {
            "pixel_bird": cls._generate_bird,
            "pixel_cat": cls._generate_cat,
            "pixel_fox": cls._generate_fox,
            "pixel_ghost": cls._generate_ghost,
            "pixel_robot": cls._generate_robot,
        }

        generator = generator_map.get(skin_id)
        if not generator:
            return cls._generate_robot(size)  # fallback

        return generator(size)

    @classmethod
    def _generate_bird(cls, size: int) -> dict[str, list[Image.Image]]:
        """Generate pixel bird animation frames."""
        frames: dict[str, list[Image.Image]] = {}
        palette = cls.PALETTES["pixel_bird"]
        cx, cy = size // 2, size // 2

        # Idle animation - gentle bobbing
        idle_frames = []
        for i in range(6):
            bob = (i % 3 - 1) * 2
            frame = cls._draw_bird_frame(cx, cy + bob, palette, mouth_open=False)
            idle_frames.append(frame)
        frames["idle"] = idle_frames

        # Recording animation - open mouth
        recording_frames = []
        for i in range(6):
            frame = cls._draw_bird_frame(cx, cy, palette, mouth_open=i % 2 == 0)
            recording_frames.append(frame)
        frames["recording"] = recording_frames

        # Recognizing animation - thinking eyes
        recognizing_frames = []
        for i in range(4):
            eye_offset = (i % 3 - 1) * 2
            frame = cls._draw_bird_frame(cx, cy, palette, mouth_open=False, eye_offset=eye_offset)
            recognizing_frames.append(frame)
        frames["recognizing"] = recognizing_frames

        # Completed animation - happy
        completed_frames = []
        for i in range(4):
            frame = cls._draw_bird_frame(cx, cy, palette, mouth_open=False, happy=True)
            completed_frames.append(frame)
        frames["completed"] = completed_frames

        # Error animation - X eyes
        error_frames = []
        for i in range(4):
            frame = cls._draw_bird_frame(cx, cy, palette, mouth_open=False, error=i % 2 == 0)
            error_frames.append(frame)
        frames["error"] = error_frames

        return frames

    @classmethod
    def _draw_bird_frame(
        cls,
        cx: int,
        cy: int,
        palette: dict[str, str],
        mouth_open: bool = False,
        eye_offset: int = 0,
        happy: bool = False,
        error: bool = False,
    ) -> Image.Image:
        """Draw a single bird frame."""
        size = cx * 2
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # Body (oval)
        body_color = palette["body"]
        d.ellipse([cx - 16, cy - 8, cx + 16, cy + 12], fill=body_color)

        # Head
        head_color = palette["body_light"]
        d.ellipse([cx - 10, cy - 18, cx + 10, cy - 2], fill=head_color)

        # Wing
        wing_color = palette["body_dark"]
        d.ellipse([cx - 18, cy - 4, cx - 4, cy + 8], fill=wing_color)

        # Eyes
        if error:
            # X eyes
            eye_color = palette["pupil"]
            d.line([cx - 7, cy - 14, cx - 3, cy - 10], fill=eye_color, width=2)
            d.line([cx - 7, cy - 10, cx - 3, cy - 14], fill=eye_color, width=2)
            d.line([cx + 3, cy - 14, cx + 7, cy - 10], fill=eye_color, width=2)
            d.line([cx + 3, cy - 10, cx + 7, cy - 14], fill=eye_color, width=2)
        else:
            eye_white = palette["eye"]
            d.ellipse([cx - 7, cy - 14, cx - 3, cy - 10], fill=eye_white)
            d.ellipse([cx + 3, cy - 14, cx + 7, cy - 10], fill=eye_white)
            pupil = palette["pupil"]
            offset_x = eye_offset if eye_offset else 0
            d.ellipse([cx - 6 + offset_x, cy - 13, cx - 4 + offset_x, cy - 11], fill=pupil)
            d.ellipse([cx + 4 + offset_x, cy - 13, cx + 6 + offset_x, cy - 11], fill=pupil)

            # Happy eyes (arcs)
            if happy:
                d.arc([cx - 7, cy - 14, cx - 3, cy - 10], start=0, end=180, fill=eye_white, width=1)
                d.arc([cx + 3, cy - 14, cx + 7, cy - 10], start=0, end=180, fill=eye_white, width=1)

        # Beak
        beak_color = palette["beak"]
        if mouth_open:
            d.ellipse([cx - 4, cy - 4, cx + 4, cy + 2], fill=beak_color)
        else:
            d.polygon([(cx - 4, cy - 2), (cx, cy + 4), (cx + 4, cy - 2)], fill=beak_color)

        # Cheek blush (when happy)
        if happy:
            blush_color = palette["cheek"]
            d.ellipse([cx - 12, cy - 8, cx - 8, cy - 4], fill=blush_color)
            d.ellipse([cx + 8, cy - 8, cx + 12, cy - 4], fill=blush_color)

        return img

    @classmethod
    def _generate_cat(cls, size: int) -> dict[str, list[Image.Image]]:
        """Generate pixel cat animation frames."""
        frames: dict[str, list[Image.Image]] = {}
        palette = cls.PALETTES["pixel_cat"]
        cx, cy = size // 2, size // 2

        # Idle - slow tail wag and blink
        idle_frames = []
        for i in range(8):
            blink = i % 6 == 0
            tail_wag = (i % 4) * 3
            frame = cls._draw_cat_frame(cx, cy, palette, blink=blink, tail_wag=tail_wag)
            idle_frames.append(frame)
        frames["idle"] = idle_frames

        # Recording - excited expression
        recording_frames = []
        for i in range(6):
            mouth_open = i % 2 == 0
            frame = cls._draw_cat_frame(cx, cy, palette, mouth_open=mouth_open, excited=True)
            recording_frames.append(frame)
        frames["recording"] = recording_frames

        # Recognizing - thinking
        recognizing_frames = []
        for i in range(4):
            eye_offset = (i % 3 - 1) * 2
            frame = cls._draw_cat_frame(cx, cy, palette, eye_offset=eye_offset)
            recognizing_frames.append(frame)
        frames["recognizing"] = recognizing_frames

        # Completed - happy closed eyes
        completed_frames = []
        for i in range(4):
            frame = cls._draw_cat_frame(cx, cy, palette, happy=True)
            completed_frames.append(frame)
        frames["completed"] = completed_frames

        # Error - worried
        error_frames = []
        for i in range(4):
            frame = cls._draw_cat_frame(cx, cy, palette, worried=True, error=i % 2 == 0)
            error_frames.append(frame)
        frames["error"] = error_frames

        return frames

    @classmethod
    def _draw_cat_frame(
        cls,
        cx: int,
        cy: int,
        palette: dict[str, str],
        blink: bool = False,
        tail_wag: int = 0,
        mouth_open: bool = False,
        excited: bool = False,
        happy: bool = False,
        worried: bool = False,
        error: bool = False,
        eye_offset: int = 0,
    ) -> Image.Image:
        """Draw a single cat frame."""
        s = cx * 2
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # Body (round)
        body_color = palette["body"]
        d.ellipse([cx - 18, cy - 6, cx + 18, cy + 16], fill=body_color)

        # Belly
        belly_color = palette["body_light"]
        d.ellipse([cx - 10, cy, cx + 10, cy + 12], fill=belly_color)

        # Head
        head_color = palette["body"]
        d.ellipse([cx - 14, cy - 20, cx + 14, cy - 2], fill=head_color)

        # Ears
        ear_color = palette["body"]
        ear_inner = palette["body_light"]
        # Left ear
        d.polygon([(cx - 12, cy - 18), (cx - 18, cy - 32), (cx - 4, cy - 22)], fill=ear_color)
        d.polygon([(cx - 11, cy - 18), (cx - 15, cy - 28), (cx - 5, cy - 21)], fill=ear_inner)
        # Right ear
        d.polygon([(cx + 12, cy - 18), (cx + 18, cy - 32), (cx + 4, cy - 22)], fill=ear_color)
        d.polygon([(cx + 11, cy - 18), (cx + 15, cy - 28), (cx + 5, cy - 21)], fill=ear_inner)

        # Eyes
        if error:
            # X eyes
            eye_color = palette["pupil"]
            d.line([cx - 10, cy - 16, cx - 4, cy - 12], fill=eye_color, width=2)
            d.line([cx - 10, cy - 12, cx - 4, cy - 16], fill=eye_color, width=2)
            d.line([cx + 4, cy - 16, cx + 10, cy - 12], fill=eye_color, width=2)
            d.line([cx + 4, cy - 12, cx + 10, cy - 16], fill=eye_color, width=2)
        elif happy or excited:
            # Closed happy eyes
            eye_color = palette["pupil"]
            d.arc([cx - 10, cy - 16, cx - 4, cy - 12], start=0, end=180, fill=eye_color, width=2)
            d.arc([cx + 4, cy - 16, cx + 10, cy - 12], start=0, end=180, fill=eye_color, width=2)
        elif blink:
            # Blinking - horizontal lines
            eye_color = palette["eye"]
            d.line([cx - 10, cy - 14, cx - 4, cy - 14], fill=eye_color, width=2)
            d.line([cx + 4, cy - 14, cx + 10, cy - 14], fill=eye_color, width=2)
        else:
            # Normal eyes
            eye_color = palette["eye"]
            d.ellipse([cx - 10, cy - 16, cx - 4, cy - 12], fill=eye_color)
            d.ellipse([cx + 4, cy - 16, cx + 10, cy - 12], fill=eye_color)
            pupil_color = palette["pupil"]
            offset_x = eye_offset if eye_offset else 0
            d.ellipse([cx - 9 + offset_x, cy - 15, cx - 5 + offset_x, cy - 13], fill=pupil_color)
            d.ellipse([cx + 5 + offset_x, cy - 15, cx + 9 + offset_x, cy - 13], fill=pupil_color)

        # Nose
        nose_color = palette["nose"]
        d.polygon([(cx - 2, cy - 6), (cx, cy - 4), (cx + 2, cy - 6)], fill=nose_color)

        # Mouth
        mouth_color = palette["body_dark"]
        if mouth_open:
            d.ellipse([cx - 4, cy - 4, cx + 4, cy + 2], fill=mouth_color)
        elif happy or excited:
            d.arc([cx - 5, cy - 4, cx + 5, cy + 2], start=0, end=180, fill=mouth_color, width=1)
        elif worried:
            d.arc([cx - 5, cy - 2, cx + 5, cy + 4], start=180, end=360, fill=mouth_color, width=1)
        else:
            d.line([cx, cy - 4, cx - 3, cy - 2], fill=mouth_color, width=1)
            d.line([cx, cy - 4, cx + 3, cy - 2], fill=mouth_color, width=1)

        # Whiskers
        whisker_color = palette["whisker"]
        for dx in [-1, 1]:
            d.line([cx + dx * 4, cy - 4, cx + dx * 14, cy - 6], fill=whisker_color, width=1)
            d.line([cx + dx * 4, cy - 2, cx + dx * 14, cy - 2], fill=whisker_color, width=1)
            d.line([cx + dx * 4, cy, cx + dx * 14, cy + 2], fill=whisker_color, width=1)

        # Tail
        tail_color = palette["body_dark"]
        tail_base_x = cx + 14
        tail_base_y = cy + 8
        tail_end_x = tail_base_x + 10 + tail_wag
        tail_end_y = tail_base_y - 12
        d.line([tail_base_x, tail_base_y, tail_end_x, tail_end_y], fill=tail_color, width=4)
        d.ellipse([tail_end_x - 2, tail_end_y - 2, tail_end_x + 2, tail_end_y + 2], fill=tail_color)

        return img

    @classmethod
    def _generate_fox(cls, size: int) -> dict[str, list[Image.Image]]:
        """Generate pixel fox animation frames."""
        frames: dict[str, list[Image.Image]] = {}
        palette = cls.PALETTES["pixel_fox"]
        cx, cy = size // 2, size // 2

        # Idle - ear twitch and tail sway
        idle_frames = []
        for i in range(8):
            ear_twitch = 1 if i % 5 < 2 else 0
            tail_sway = (i % 4 - 1.5) * 2
            frame = cls._draw_fox_frame(cx, cy, palette, ear_twitch=ear_twitch, tail_sway=tail_sway)
            idle_frames.append(frame)
        frames["idle"] = idle_frames

        # Recording - alert and open mouth
        recording_frames = []
        for i in range(6):
            mouth_open = i % 2 == 0
            frame = cls._draw_fox_frame(cx, cy, palette, mouth_open=mouth_open, alert=True)
            recording_frames.append(frame)
        frames["recording"] = recording_frames

        # Recognizing - thoughtful
        recognizing_frames = []
        for i in range(4):
            eye_offset = (i % 3 - 1) * 2
            frame = cls._draw_fox_frame(cx, cy, palette, eye_offset=eye_offset)
            recognizing_frames.append(frame)
        frames["recognizing"] = recognizing_frames

        # Completed - happy
        completed_frames = []
        for i in range(4):
            frame = cls._draw_fox_frame(cx, cy, palette, happy=True)
            completed_frames.append(frame)
        frames["completed"] = completed_frames

        # Error - sad
        error_frames = []
        for i in range(4):
            frame = cls._draw_fox_frame(cx, cy, palette, sad=True, error=i % 2 == 0)
            error_frames.append(frame)
        frames["error"] = error_frames

        return frames

    @classmethod
    def _draw_fox_frame(
        cls,
        cx: int,
        cy: int,
        palette: dict[str, str],
        ear_twitch: int = 0,
        tail_sway: float = 0,
        mouth_open: bool = False,
        alert: bool = False,
        happy: bool = False,
        sad: bool = False,
        error: bool = False,
        eye_offset: int = 0,
    ) -> Image.Image:
        """Draw a single fox frame."""
        s = cx * 2
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # Body
        body_color = palette["body"]
        d.ellipse([cx - 16, cy - 6, cx + 16, cy + 14], fill=body_color)

        # Belly
        belly_color = palette["belly"]
        d.ellipse([cx - 8, cy, cx + 8, cy + 10], fill=belly_color)

        # Head
        head_color = palette["body"]
        d.ellipse([cx - 12, cy - 22, cx + 12, cy - 6], fill=head_color)

        # Pointed ears
        ear_color = palette["body"]
        ear_inner = palette["ear_inner"]
        # Left ear (pointed)
        ear_twitch_offset = ear_twitch * 2
        d.polygon([(cx - 10, cy - 18), (cx - 16, cy - 34 + ear_twitch_offset), (cx - 2, cy - 22)], fill=ear_color)
        d.polygon([(cx - 9, cy - 18), (cx - 13, cy - 30 + ear_twitch_offset), (cx - 4, cy - 21)], fill=ear_inner)
        # Right ear (pointed)
        d.polygon([(cx + 10, cy - 18), (cx + 16, cy - 34 + ear_twitch_offset), (cx + 2, cy - 22)], fill=ear_color)
        d.polygon([(cx + 9, cy - 18), (cx + 13, cy - 30 + ear_twitch_offset), (cx + 4, cy - 21)], fill=ear_inner)

        # Eyes
        if error:
            eye_color = palette["pupil"]
            d.line([cx - 8, cy - 18, cx - 3, cy - 14], fill=eye_color, width=2)
            d.line([cx - 8, cy - 14, cx - 3, cy - 18], fill=eye_color, width=2)
            d.line([cx + 3, cy - 18, cx + 8, cy - 14], fill=eye_color, width=2)
            d.line([cx + 3, cy - 14, cx + 8, cy - 18], fill=eye_color, width=2)
        elif happy:
            d.arc([cx - 8, cy - 18, cx - 3, cy - 14], start=0, end=180, fill=palette["eye"], width=1)
            d.arc([cx + 3, cy - 18, cx + 8, cy - 14], start=0, end=180, fill=palette["eye"], width=1)
        else:
            eye_white = palette["eye"]
            d.ellipse([cx - 8, cy - 18, cx - 3, cy - 14], fill=eye_white)
            d.ellipse([cx + 3, cy - 18, cx + 8, cy - 14], fill=eye_white)
            pupil_color = palette["pupil"]
            offset_x = eye_offset if eye_offset else 0
            d.ellipse([cx - 7 + offset_x, cy - 17, cx - 4 + offset_x, cy - 15], fill=pupil_color)
            d.ellipse([cx + 4 + offset_x, cy - 17, cx + 7 + offset_x, cy - 15], fill=pupil_color)

        # Nose
        nose_color = palette["body_dark"]
        d.ellipse([cx - 2, cy - 8, cx + 2, cy - 4], fill=nose_color)

        # Mouth
        if mouth_open:
            d.ellipse([cx - 3, cy - 4, cx + 3, cy + 1], fill=nose_color)
        elif happy:
            d.arc([cx - 4, cy - 4, cx + 4, cy + 1], start=0, end=180, fill=nose_color, width=1)
        elif sad:
            d.arc([cx - 4, cy - 2, cx + 4, cy + 3], start=180, end=360, fill=nose_color, width=1)

        # Tail (bushy)
        tail_color = palette["body"]
        tail_tip = palette["belly"]
        tail_base_x = cx + 12
        tail_base_y = cy + 4
        tail_end_x = tail_base_x + 14 + int(tail_sway)
        tail_end_y = tail_base_y - 8
        d.line([tail_base_x, tail_base_y, tail_end_x, tail_end_y], fill=tail_color, width=5)
        d.ellipse([tail_end_x - 3, tail_end_y - 3, tail_end_x + 3, tail_end_y + 3], fill=tail_tip)

        return img

    @classmethod
    def _generate_ghost(cls, size: int) -> dict[str, list[Image.Image]]:
        """Generate pixel ghost animation frames."""
        frames: dict[str, list[Image.Image]] = {}
        palette = cls.PALETTES["pixel_ghost"]
        cx, cy = size // 2, size // 2

        # Idle - floating bob
        idle_frames = []
        for i in range(8):
            bob = (i % 4 - 1.5) * 3
            wave = i % 2
            frame = cls._draw_ghost_frame(cx, cy + bob, palette, wave=wave)
            idle_frames.append(frame)
        frames["idle"] = idle_frames

        # Recording - excited with waves
        recording_frames = []
        for i in range(8):
            wave = i % 2
            frame = cls._draw_ghost_frame(cx, cy, palette, wave=wave, excited=True)
            recording_frames.append(frame)
        frames["recording"] = recording_frames

        # Recognizing - thinking
        recognizing_frames = []
        for i in range(4):
            eye_offset = (i % 3 - 1) * 2
            frame = cls._draw_ghost_frame(cx, cy, palette, eye_offset=eye_offset)
            recognizing_frames.append(frame)
        frames["recognizing"] = recognizing_frames

        # Completed - happy
        completed_frames = []
        for i in range(4):
            frame = cls._draw_ghost_frame(cx, cy, palette, happy=True)
            completed_frames.append(frame)
        frames["completed"] = completed_frames

        # Error - worried
        error_frames = []
        for i in range(4):
            frame = cls._draw_ghost_frame(cx, cy, palette, worried=True, error=i % 2 == 0)
            error_frames.append(frame)
        frames["error"] = error_frames

        return frames

    @classmethod
    def _draw_ghost_frame(
        cls,
        cx: int,
        cy: int,
        palette: dict[str, str],
        wave: int = 0,
        excited: bool = False,
        happy: bool = False,
        worried: bool = False,
        error: bool = False,
        eye_offset: int = 0,
    ) -> Image.Image:
        """Draw a single ghost frame."""
        s = cx * 2
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # Ghost body (rounded top, wavy bottom)
        body_color = palette["body"]
        body_light = palette["body_light"]
        tail_color = palette["tail"]

        # Main body shape
        d.ellipse([cx - 16, cy - 22, cx + 16, cy + 10], fill=body_color)

        # Wavy tail at bottom
        tail_points = [
            (cx - 16, cy + 10),
            (cx - 12, cy + 16 + wave * 2),
            (cx - 6, cy + 10),
            (cx, cy + 16 - wave * 2),
            (cx + 6, cy + 10),
            (cx + 12, cy + 16 + wave * 2),
            (cx + 16, cy + 10),
        ]
        d.polygon(tail_points, fill=body_color)

        # Slight transparency gradient effect (darker at bottom)
        d.ellipse([cx - 12, cy + 4, cx + 12, cy + 12], fill=tail_color)

        # Eyes
        if error:
            # X eyes
            eye_color = palette["eye"]
            d.line([cx - 10, cy - 14, cx - 4, cy - 10], fill=eye_color, width=2)
            d.line([cx - 10, cy - 10, cx - 4, cy - 14], fill=eye_color, width=2)
            d.line([cx + 4, cy - 14, cx + 10, cy - 10], fill=eye_color, width=2)
            d.line([cx + 4, cy - 10, cx + 10, cy - 14], fill=eye_color, width=2)
        elif happy:
            # Happy closed eyes (arcs)
            eye_color = palette["eye"]
            d.arc([cx - 10, cy - 14, cx - 4, cy - 10], start=0, end=180, fill=eye_color, width=2)
            d.arc([cx + 4, cy - 14, cx + 10, cy - 10], start=0, end=180, fill=eye_color, width=2)
        else:
            eye_white = palette["eye"]
            d.ellipse([cx - 10, cy - 16, cx - 4, cy - 12], fill=eye_white)
            d.ellipse([cx + 4, cy - 16, cx + 10, cy - 12], fill=eye_white)
            pupil_color = "#222222"
            offset_x = eye_offset if eye_offset else 0
            d.ellipse([cx - 9 + offset_x, cy - 15, cx - 5 + offset_x, cy - 13], fill=pupil_color)
            d.ellipse([cx + 5 + offset_x, cy - 15, cx + 9 + offset_x, cy - 13], fill=pupil_color)

        # Blush
        blush_color = palette["blush"]
        if happy or excited:
            d.ellipse([cx - 14, cy - 8, cx - 10, cy - 4], fill=blush_color)
            d.ellipse([cx + 10, cy - 8, cx + 14, cy - 4], fill=blush_color)

        # Mouth
        if worried:
            d.arc([cx - 4, cy - 4, cx + 4, cy + 2], start=180, end=360, fill=eye_color, width=1)
        elif happy:
            d.arc([cx - 5, cy - 4, cx + 5, cy + 2], start=0, end=180, fill=eye_color, width=1)
        elif excited:
            d.ellipse([cx - 4, cy - 4, cx + 4, cy + 2], fill=eye_color)
        else:
            d.ellipse([cx - 2, cy - 4, cx + 2, cy - 2], fill=eye_color)

        return img

    @classmethod
    def _generate_robot(cls, size: int) -> dict[str, list[Image.Image]]:
        """Generate pixel robot animation frames."""
        frames: dict[str, list[Image.Image]] = {}
        palette = cls.PALETTES["pixel_robot"]
        cx, cy = size // 2, size // 2

        # Idle - antenna blink and gentle bob
        idle_frames = []
        for i in range(8):
            bob = (i % 3 - 1) * 2
            antenna_blink = i % 10 < 2
            frame = cls._draw_robot_frame(cx, cy + bob, palette, antenna_blink=antenna_blink)
            idle_frames.append(frame)
        frames["idle"] = idle_frames

        # Recording - mouth animation
        recording_frames = []
        for i in range(8):
            mouth_open = i % 2 == 0
            frame = cls._draw_robot_frame(cx, cy, palette, mouth_open=mouth_open, active=True)
            recording_frames.append(frame)
        frames["recording"] = recording_frames

        # Recognizing - processing indicator
        recognizing_frames = []
        for i in range(6):
            dots = (i % 3) + 1
            frame = cls._draw_robot_frame(cx, cy, palette, think_dots=dots)
            recognizing_frames.append(frame)
        frames["recognizing"] = recognizing_frames

        # Completed - happy
        completed_frames = []
        for i in range(4):
            frame = cls._draw_robot_frame(cx, cy, palette, happy=True)
            completed_frames.append(frame)
        frames["completed"] = completed_frames

        # Error - red flashing
        error_frames = []
        for i in range(6):
            frame = cls._draw_robot_frame(cx, cy, palette, error=True, error_flash=i % 2 == 0)
            error_frames.append(frame)
        frames["error"] = error_frames

        return frames

    @classmethod
    def _draw_robot_frame(
        cls,
        cx: int,
        cy: int,
        palette: dict[str, str],
        mouth_open: bool = False,
        active: bool = False,
        think_dots: int = 0,
        happy: bool = False,
        error: bool = False,
        error_flash: bool = True,
        antenna_blink: bool = False,
    ) -> Image.Image:
        """Draw a single robot frame."""
        s = cx * 2
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        body_color = palette["body"]
        body_light = palette["body_light"]
        body_dark = palette["body_dark"]

        if error and error_flash:
            body_color = "#E74C3C"
            body_light = "#EC6A5E"
            body_dark = "#C0392B"

        # Head (rounded rectangle)
        d.rounded_rectangle([cx - 12, cy - 22, cx + 12, cy - 4], radius=4, fill=body_color)

        # Antenna
        antenna_color = palette["antenna"] if not error else "#E74C3C"
        d.line([cx, cy - 22, cx, cy - 30], fill=body_dark, width=2)
        antenna_glow = antenna_color if antenna_blink else body_dark
        d.ellipse([cx - 3, cy - 33, cx + 3, cy - 27], fill=antenna_glow)

        # Eyes
        eye_white = palette["eye"]
        d.ellipse([cx - 9, cy - 18, cx - 4, cy - 14], fill=eye_white)
        d.ellipse([cx + 4, cy - 18, cx + 9, cy - 14], fill=eye_white)
        pupil_color = palette["pupil"]
        if happy:
            # Happy closed eyes
            d.arc([cx - 9, cy - 18, cx - 4, cy - 14], start=0, end=180, fill=eye_white, width=1)
            d.arc([cx + 4, cy - 18, cx + 9, cy - 14], start=0, end=180, fill=eye_white, width=1)
        elif error and error_flash:
            d.ellipse([cx - 8, cy - 17, cx - 5, cy - 15], fill="#FF6B6B")
            d.ellipse([cx + 5, cy - 17, cx + 8, cy - 15], fill="#FF6B6B")
        else:
            d.ellipse([cx - 8, cy - 17, cx - 5, cy - 15], fill=pupil_color)
            d.ellipse([cx + 5, cy - 17, cx + 8, cy - 15], fill=pupil_color)

        # Mouth
        mouth_color = palette["mouth"] if not error else "#FF6B6B"
        if mouth_open and active:
            d.ellipse([cx - 5, cy - 6, cx + 5, cy - 2], fill=mouth_color)
        elif happy:
            d.arc([cx - 5, cy - 6, cx + 5, cy - 2], start=0, end=180, fill=mouth_color, width=1)
        elif think_dots > 0:
            for i in range(think_dots):
                d.ellipse([cx - 6 + i * 5, cy - 6, cx - 4 + i * 5, cy - 4], fill=mouth_color)
        else:
            d.line([cx - 4, cy - 4, cx + 4, cy - 4], fill=mouth_color, width=1)

        # Body
        d.rounded_rectangle([cx - 10, cy, cx + 10, cy + 14], radius=3, fill=body_light)

        # Body detail (panel line)
        d.line([cx - 6, cy + 4, cx + 6, cy + 4], fill=body_dark, width=1)
        d.line([cx - 6, cy + 8, cx + 6, cy + 8], fill=body_dark, width=1)

        # Arms
        arm_color = body_dark
        d.rounded_rectangle([cx - 18, cy + 2, cx - 12, cy + 10], radius=2, fill=arm_color)
        d.rounded_rectangle([cx + 12, cy + 2, cx + 18, cy + 10], radius=2, fill=arm_color)

        # Legs
        d.rounded_rectangle([cx - 8, cy + 14, cx - 2, cy + 22], radius=2, fill=arm_color)
        d.rounded_rectangle([cx + 2, cy + 14, cx + 8, cy + 22], radius=2, fill=arm_color)

        # Active indicator
        if active:
            indicator_color = "#50C878"
            d.ellipse([cx - 2, cy + 2, cx + 2, cy + 4], fill=indicator_color)

        return img

    @classmethod
    def get_skin_info(cls, skin_id: str) -> SkinInfo:
        """Get SkinInfo for a built-in skin."""
        info_map = {
            "pixel_bird": SkinInfo(
                id="pixel_bird",
                name="像素小鸟",
                author="VoiceIn",
                version="1.0",
                frame_size=(64, 64),
                frame_rate=10,
                animations={
                    "idle": [f"idle_{i}.png" for i in range(6)],
                    "recording": [f"rec_{i}.png" for i in range(6)],
                    "recognizing": [f"recog_{i}.png" for i in range(4)],
                    "completed": [f"done_{i}.png" for i in range(4)],
                    "error": [f"err_{i}.png" for i in range(4)],
                },
            ),
            "pixel_cat": SkinInfo(
                id="pixel_cat",
                name="像素猫咪",
                author="VoiceIn",
                version="1.0",
                frame_size=(64, 64),
                frame_rate=8,
                animations={
                    "idle": [f"idle_{i}.png" for i in range(8)],
                    "recording": [f"rec_{i}.png" for i in range(6)],
                    "recognizing": [f"recog_{i}.png" for i in range(4)],
                    "completed": [f"done_{i}.png" for i in range(4)],
                    "error": [f"err_{i}.png" for i in range(4)],
                },
            ),
            "pixel_fox": SkinInfo(
                id="pixel_fox",
                name="像素狐狸",
                author="VoiceIn",
                version="1.0",
                frame_size=(64, 64),
                frame_rate=10,
                animations={
                    "idle": [f"idle_{i}.png" for i in range(8)],
                    "recording": [f"rec_{i}.png" for i in range(6)],
                    "recognizing": [f"recog_{i}.png" for i in range(4)],
                    "completed": [f"done_{i}.png" for i in range(4)],
                    "error": [f"err_{i}.png" for i in range(4)],
                },
            ),
            "pixel_ghost": SkinInfo(
                id="pixel_ghost",
                name="像素幽灵",
                author="VoiceIn",
                version="1.0",
                frame_size=(64, 64),
                frame_rate=8,
                animations={
                    "idle": [f"idle_{i}.png" for i in range(8)],
                    "recording": [f"rec_{i}.png" for i in range(8)],
                    "recognizing": [f"recog_{i}.png" for i in range(4)],
                    "completed": [f"done_{i}.png" for i in range(4)],
                    "error": [f"err_{i}.png" for i in range(4)],
                },
            ),
            "pixel_robot": SkinInfo(
                id="pixel_robot",
                name="像素机器人",
                author="VoiceIn",
                version="1.0",
                frame_size=(64, 64),
                frame_rate=12,
                animations={
                    "idle": [f"idle_{i}.png" for i in range(8)],
                    "recording": [f"rec_{i}.png" for i in range(8)],
                    "recognizing": [f"recog_{i}.png" for i in range(6)],
                    "completed": [f"done_{i}.png" for i in range(4)],
                    "error": [f"err_{i}.png" for i in range(6)],
                },
            ),
        }
        return info_map.get(skin_id, info_map["pixel_robot"])


# ---------------------------------------------------------------------------
# Clothing layer system
# ---------------------------------------------------------------------------

@dataclass
class ClothingLayer:
    """A single clothing layer that can be composited onto a skin."""
    name: str
    image: Image.Image
    offset_x: int = 0
    offset_y: int = 0
    alpha: float = 1.0
    blend_mode: str = "alpha"  # "alpha", "multiply", "screen"

    def apply(self, base: Image.Image) -> Image.Image:
        """Apply this clothing layer onto the base image."""
        result = base.copy()
        layer = self.image.copy()

        # Apply alpha
        if self.alpha < 1.0:
            layer.putalpha(int(255 * self.alpha))

        # Create output with same size
        if result.size != layer.size:
            layer = layer.resize(result.size, Image.LANCZOS)

        # Paste with alpha compositing
        if layer.mode == "RGBA":
            result.paste(layer, (self.offset_x, self.offset_y), layer)
        else:
            result.paste(layer, (self.offset_x, self.offset_y))

        return result


# ---------------------------------------------------------------------------
# Skin manager
# ---------------------------------------------------------------------------

class SkinManager:
    """Skin manager for loading and managing pet skins."""

    # Built-in skin IDs
    BUILT_IN_SKINS = ["pixel_bird", "pixel_cat", "pixel_fox", "pixel_ghost", "pixel_robot"]

    def __init__(self, skins_dir: str | None = None) -> None:
        """
        Initialize skin manager.

        Args:
            skins_dir: Directory to load custom skins from. If None, uses program directory.
        """
        if skins_dir:
            self._skins_dir = Path(skins_dir)
        else:
            # Default to program directory/skins
            self._skins_dir = Path(__file__).parent.parent.parent / "skins"

        self._current_skin_id: str | None = None
        self._current_skin: SkinInfo | None = None
        self._skin_frames: dict[str, dict[str, list[Image.Image]]] = {}
        self._clothing_layers: dict[str, list[ClothingLayer]] = {}
        self._change_callbacks: list[Callable[[str], None]] = []

        # Generate built-in skins
        self._generate_built_in_skins()

        # Load custom skins from disk
        self._load_custom_skins()

        # Load default skin
        if self._current_skin_id is None:
            self.load_skin("pixel_robot")

    def _generate_built_in_skins(self) -> None:
        """Generate all built-in skins."""
        for skin_id in self.BUILT_IN_SKINS:
            try:
                frames = BuiltInSkinGenerator.generate_skin(skin_id)
                self._skin_frames[skin_id] = frames
                logger.debug("Generated built-in skin: %s", skin_id)
            except Exception as e:
                logger.error("Failed to generate built-in skin %s: %s", skin_id, e)

    def _load_custom_skins(self) -> None:
        """Load custom skins from skins directory."""
        if not self._skins_dir.exists():
            logger.debug("Skins directory does not exist: %s", self._skins_dir)
            return

        for skin_folder in self._skins_dir.iterdir():
            if not skin_folder.is_dir():
                continue

            skin_id = skin_folder.name
            config_file = skin_folder / "skin.json"

            if not config_file.exists():
                logger.warning("Skin folder %s missing skin.json", skin_id)
                continue

            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)

                skin_info = SkinInfo.from_dict(config, skin_id)
                animations: dict[str, list[Image.Image]] = {}

                # Load animation frames
                for state, frame_files in skin_info.animations.items():
                    state_frames = []
                    for frame_file in frame_files:
                        frame_path = skin_folder / frame_file
                        # Path traversal check
                        try:
                            real_path = frame_path.resolve()
                            real_skin_folder = skin_folder.resolve()
                            if not str(real_path).startswith(str(real_skin_folder)):
                                logger.warning("Path traversal attempt detected: %s", frame_path)
                                continue
                        except Exception as e:
                            logger.warning("Failed to resolve path %s: %s", frame_path, e)
                            continue
                        if frame_path.exists():
                            try:
                                img = Image.open(frame_path).convert("RGBA")
                                state_frames.append(img)
                            except Exception as e:
                                logger.warning("Failed to load frame %s: %s", frame_path, e)
                        else:
                            logger.warning("Frame file not found: %s", frame_path)

                    if state_frames:
                        animations[state] = state_frames

                if animations:
                    self._skin_frames[skin_id] = animations
                    logger.info("Loaded custom skin: %s", skin_id)
                else:
                    logger.warning("No valid frames found for skin: %s", skin_id)

            except Exception as e:
                logger.error("Failed to load skin from %s: %s", skin_folder, e)

    def load_skin(self, skin_id: str) -> bool:
        """
        Load a skin by ID.

        Args:
            skin_id: The skin identifier.

        Returns:
            True if skin was loaded successfully, False otherwise.
        """
        if skin_id not in self._skin_frames:
            logger.warning("Skin not found: %s", skin_id)
            return False

        if skin_id in self.BUILT_IN_SKINS:
            self._current_skin = BuiltInSkinGenerator.get_skin_info(skin_id)
        else:
            # Try to load from file
            skin_folder = self._skins_dir / skin_id
            config_file = skin_folder / "skin.json"
            if config_file.exists():
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    self._current_skin = SkinInfo.from_dict(config, skin_id)
                except Exception as e:
                    logger.error("Failed to load skin config: %s", e)
                    return False
            else:
                logger.warning("Custom skin config not found: %s", config_file)
                return False

        self._current_skin_id = skin_id

        # Notify callbacks
        for callback in self._change_callbacks:
            try:
                callback(skin_id)
            except Exception as e:
                logger.warning("Skin change callback error: %s", e)

        logger.info("Loaded skin: %s", skin_id)
        return True

    def get_available_skins(self) -> list[SkinInfo]:
        """Get list of all available skins."""
        skins: list[SkinInfo] = []

        # Add built-in skins
        for skin_id in self.BUILT_IN_SKINS:
            if skin_id in self._skin_frames:
                skins.append(BuiltInSkinGenerator.get_skin_info(skin_id))

        # Add custom skins
        if self._skins_dir.exists():
            for skin_folder in self._skins_dir.iterdir():
                if not skin_folder.is_dir():
                    continue
                skin_id = skin_folder.name
                if skin_id not in self.BUILT_IN_SKINS:
                    config_file = skin_folder / "skin.json"
                    if config_file.exists():
                        try:
                            with open(config_file, "r", encoding="utf-8") as f:
                                config = json.load(f)
                            skins.append(SkinInfo.from_dict(config, skin_id))
                        except Exception as e:
                            logger.warning("Failed to load skin config %s: %s", config_file, e)

        return skins

    def get_current_skin(self) -> Optional[SkinInfo]:
        """Get current skin information."""
        return self._current_skin

    def next_skin(self) -> bool:
        """Switch to the next skin in the list."""
        available = self.get_available_skins()
        if not available or not self._current_skin_id:
            return False

        ids = [s.id for s in available]
        try:
            current_idx = ids.index(self._current_skin_id)
            next_idx = (current_idx + 1) % len(ids)
            return self.load_skin(ids[next_idx])
        except ValueError:
            return self.load_skin(ids[0]) if ids else False

    def previous_skin(self) -> bool:
        """Switch to the previous skin in the list."""
        available = self.get_available_skins()
        if not available or not self._current_skin_id:
            return False

        ids = [s.id for s in available]
        try:
            current_idx = ids.index(self._current_skin_id)
            prev_idx = (current_idx - 1) % len(ids)
            return self.load_skin(ids[prev_idx])
        except ValueError:
            return self.load_skin(ids[-1]) if ids else False

    def get_animation_frames(self, state: str) -> list[Image.Image]:
        """
        Get animation frames for a specific state.

        Args:
            state: Animation state name (e.g., "idle", "recording").

        Returns:
            List of animation frames for the state.
        """
        if not self._current_skin_id:
            return []

        skin_frames = self._skin_frames.get(self._current_skin_id, {})

        # Try exact state match first
        if state in skin_frames:
            return skin_frames[state].copy()

        # Try to find matching state
        state_mapping = {
            "thinking": "recognizing",
            "thinking": "recognizing",
            "drag": "idle",
        }
        mapped_state = state_mapping.get(state, state)
        if mapped_state in skin_frames:
            return skin_frames[mapped_state].copy()

        # Fallback to idle
        if "idle" in skin_frames:
            return skin_frames["idle"].copy()

        # Return empty list
        return []

    def generate_thumbnail(self, skin_id: str, size: tuple[int, int] = (64, 64)) -> Image.Image:
        """
        Generate a thumbnail for a skin.

        Args:
            skin_id: The skin identifier.
            size: Thumbnail size as (width, height).

        Returns:
            PIL Image of the thumbnail.
        """
        # Generate from built-in skin generator
        if skin_id in self.BUILT_IN_SKINS:
            frames = BuiltInSkinGenerator.generate_skin(skin_id, size=min(size))
            if "idle" in frames and frames["idle"]:
                thumb = frames["idle"][0]
                return thumb.resize(size, Image.LANCZOS)

        # Try to get first frame from loaded skin
        if skin_id in self._skin_frames:
            skin_frames = self._skin_frames[skin_id]
            for state_frames in skin_frames.values():
                if state_frames:
                    thumb = state_frames[0]
                    return thumb.resize(size, Image.LANCZOS)

        # Fallback: generate a placeholder
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        cx, cy = size[0] // 2, size[1] // 2
        d.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill="#888888")
        d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill="#555555")
        return img

    def register_skin_change_callback(self, callback: Callable[[str], None]) -> None:
        """
        Register a callback for skin change events.

        Args:
            callback: Function to call when skin changes. Receives skin_id as argument.
        """
        if callback not in self._change_callbacks:
            self._change_callbacks.append(callback)

    def unregister_skin_change_callback(self, callback: Callable[[str], None]) -> None:
        """Unregister a skin change callback."""
        if callback in self._change_callbacks:
            self._change_callbacks.remove(callback)

    def add_clothing_layer(
        self,
        layer_name: str,
        image: Image.Image,
        offset_x: int = 0,
        offset_y: int = 0,
        alpha: float = 1.0,
    ) -> None:
        """
        Add a clothing layer to the current skin.

        Args:
            layer_name: Unique name for this layer.
            image: PIL Image for the layer.
            offset_x: X offset from top-left corner.
            offset_y: Y offset from top-left corner.
            alpha: Layer opacity (0.0-1.0).
        """
        if not self._current_skin_id:
            return

        if self._current_skin_id not in self._clothing_layers:
            self._clothing_layers[self._current_skin_id] = []

        # Remove existing layer with same name
        self._clothing_layers[self._current_skin_id] = [
            l for l in self._clothing_layers[self._current_skin_id]
            if l.name != layer_name
        ]

        layer = ClothingLayer(
            name=layer_name,
            image=image,
            offset_x=offset_x,
            offset_y=offset_y,
            alpha=alpha,
        )
        self._clothing_layers[self._current_skin_id].append(layer)
        logger.debug("Added clothing layer: %s to skin: %s", layer_name, self._current_skin_id)

    def remove_clothing_layer(self, layer_name: str) -> None:
        """Remove a clothing layer from the current skin."""
        if not self._current_skin_id:
            return

        if self._current_skin_id in self._clothing_layers:
            self._clothing_layers[self._current_skin_id] = [
                l for l in self._clothing_layers[self._current_skin_id]
                if l.name != layer_name
            ]

    def get_clothing_layers(self) -> list[ClothingLayer]:
        """Get all clothing layers for the current skin."""
        if not self._current_skin_id:
            return []
        return self._clothing_layers.get(self._current_skin_id, []).copy()

    def apply_clothing_layers(self, frame: Image.Image) -> Image.Image:
        """
        Apply all clothing layers to a frame.

        Args:
            frame: Base frame image.

        Returns:
            Frame with all clothing layers applied.
        """
        if not self._current_skin_id:
            return frame

        result = frame
        layers = self._clothing_layers.get(self._current_skin_id, [])

        for layer in layers:
            result = layer.apply(result)

        return result

    def validate_skin(self, skin_id: str) -> tuple[bool, list[str]]:
        """
        Validate a skin's configuration and resources.

        Args:
            skin_id: The skin identifier to validate.

        Returns:
            Tuple of (is_valid, list_of_issues).
        """
        issues: list[str] = []

        # Check if skin exists
        if skin_id not in self._skin_frames:
            issues.append(f"Skin '{skin_id}' not found")
            return False, issues

        # Check if we have skin info
        if skin_id in self.BUILT_IN_SKINS:
            info = BuiltInSkinGenerator.get_skin_info(skin_id)
        else:
            skin_folder = self._skins_dir / skin_id
            config_file = skin_folder / "skin.json"
            if not config_file.exists():
                issues.append(f"Skin config not found: {config_file}")
            else:
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    info = SkinInfo.from_dict(config, skin_id)
                except Exception as e:
                    issues.append(f"Failed to parse skin config: {e}")
                    return False, issues

        # Check frame size consistency
        skin_frames = self._skin_frames[skin_id]
        expected_size = info.frame_size

        for state, frames in skin_frames.items():
            if not frames:
                issues.append(f"State '{state}' has no frames")
                continue

            for i, frame in enumerate(frames):
                if frame.size != expected_size:
                    issues.append(
                        f"State '{state}' frame {i} has size {frame.size}, "
                        f"expected {expected_size}"
                    )

        # Check required animations
        required_states = ["idle", "recording"]
        for state in required_states:
            if state not in skin_frames or not skin_frames[state]:
                issues.append(f"Required animation state '{state}' is missing or empty")

        return len(issues) == 0, issues

    def get_skin_ids(self) -> list[str]:
        """Get list of all skin IDs (both built-in and custom)."""
        ids = list(self.BUILT_IN_SKINS)

        if self._skins_dir.exists():
            for skin_folder in self._skins_dir.iterdir():
                if skin_folder.is_dir() and skin_folder.name not in self.BUILT_IN_SKINS:
                    ids.append(skin_folder.name)

        return ids

    def destroy(self) -> None:
        """Release all resources."""
        self._skin_frames.clear()
        self._clothing_layers.clear()
        self._change_callbacks.clear()
        self._current_skin_id = None
        self._current_skin = None
        logger.debug("SkinManager resources released")


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

_default_manager: Optional[SkinManager] = None


def get_default_manager() -> SkinManager:
    """Get or create the default skin manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = SkinManager()
    return _default_manager


def destroy_default_manager() -> None:
    """Destroy the default skin manager."""
    global _default_manager
    if _default_manager is not None:
        _default_manager.destroy()
        _default_manager = None
