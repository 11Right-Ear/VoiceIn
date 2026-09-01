"""Desktop pet animation system with frame-based animations and sound wave visualization."""

import asyncio
import logging
import threading
import time
from collections import OrderedDict
from enum import Enum
from functools import lru_cache
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter

logger = logging.getLogger(__name__)


class AnimationState(Enum):
    """Animation state enumeration."""
    IDLE = "idle"
    RECORDING = "recording"
    RECOGNIZING = "recognizing"
    COMPLETED = "completed"
    ERROR = "error"
    DRAG = "drag"


class AnimationController:
    """Frame animation controller with multi-state support and sound wave visualization."""

    # Default frame counts for each state
    DEFAULT_FRAME_COUNTS = {
        AnimationState.IDLE: 6,
        AnimationState.RECORDING: 10,
        AnimationState.RECOGNIZING: 8,
        AnimationState.COMPLETED: 6,
        AnimationState.ERROR: 4,
        AnimationState.DRAG: 4,
    }

    # Frame rates for each state
    DEFAULT_FRAME_RATES = {
        AnimationState.IDLE: 8,
        AnimationState.RECORDING: 15,
        AnimationState.RECOGNIZING: 10,
        AnimationState.COMPLETED: 8,
        AnimationState.ERROR: 6,
        AnimationState.DRAG: 12,
    }

    def __init__(self, skin_path: Optional[str] = None, frame_rate: int = 60):
        """
        Initialize animation controller.

        Args:
            skin_path: Path to skin folder containing PNG sequences. If None, uses generated frames.
            frame_rate: Target frame rate for the animation display.
        """
        self._skin_path = skin_path
        self._frame_rate = frame_rate
        self._frame_duration = 1.0 / frame_rate

        # Animation data: state -> list of frames
        self._animations: dict[AnimationState, list[Image.Image]] = {}
        self._frame_counts: dict[AnimationState, int] = {}
        self._frame_rates: dict[AnimationState, int] = {}

        # Current animation state
        self._current_state: AnimationState = AnimationState.IDLE
        self._current_frame_index: int = 0
        self._loop: bool = True
        self._is_playing: bool = True
        self._is_paused: bool = False

        # Transition state
        self._is_transitioning: bool = False
        self._transition_progress: float = 0.0
        self._transition_duration: float = 0.2  # 200ms
        self._previous_frame: Optional[Image.Image] = None

        # Audio level for sound wave visualization
        self._audio_level: float = 0.0
        self._sound_wave_offset: float = 0.0

        # Frame cache for performance
        self._frame_cache: OrderedDict[str, Image.Image] = OrderedDict()
        self._cache_max_size: int = 100

        # Thread safety
        self._lock = threading.RLock()

        # Background task for animation playback
        self._animation_task: Optional[asyncio.Task] = None
        self._running: bool = False

        # Frame size (will be set during loading)
        self._frame_size: tuple[int, int] = (64, 64)

        # Load animations
        self._load_all_animations()

    def _load_all_animations(self) -> None:
        """Load all animation sequences."""
        if self._skin_path:
            self._load_from_skin()
        else:
            self._generate_default_animations()

    def _load_from_skin(self) -> None:
        """Load animations from skin folder."""
        import os

        for state in AnimationState:
            state_folder = os.path.join(self._skin_path, state.value)
            if os.path.isdir(state_folder):
                frame_files = sorted([
                    f for f in os.listdir(state_folder)
                    if f.endswith('.png')
                ])
                if frame_files:
                    self.load_animation(state, frame_files)
                    logger.info(f"Loaded {len(frame_files)} frames for state {state.value}")
            else:
                logger.warning(f"Skin folder not found for state {state.value}, using default")
                self._generate_animation(state)

        if not self._animations:
            logger.warning("No valid animations found in skin, using defaults")
            self._generate_default_animations()

    def _generate_default_animations(self) -> None:
        """Generate default pixel pet animations."""
        for state in AnimationState:
            self._generate_animation(state)
        logger.info("Generated default pixel pet animations")

    def _generate_animation(self, state: AnimationState) -> None:
        """Generate a default animation for a specific state."""
        frame_count = self.DEFAULT_FRAME_COUNTS[state]
        frame_rate = self.DEFAULT_FRAME_RATES[state]

        self._frame_counts[state] = frame_count
        self._frame_rates[state] = frame_rate

        frames = []
        for i in range(frame_count):
            frame = self._generate_pixel_pet(state, i, frame_count)
            frames.append(frame)

        self._animations[state] = frames
        if self._frame_size == (64, 64):
            self._frame_size = frames[0].size

    def _generate_pixel_pet(
        self, state: AnimationState, frame_index: int, total_frames: int
    ) -> Image.Image:
        """Generate a pixel pet frame for the given state."""
        size = self._frame_size
        frame = Image.new('RGBA', size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)

        center_x, center_y = size[0] // 2, size[1] // 2

        # Animation parameters based on state
        if state == AnimationState.IDLE:
            # Breathing animation - slow up/down floating
            offset_y = int(2 * (frame_index % 3 - 1))  # -2, 0, 2 pixels
            self._draw_idle_pet(draw, center_x, center_y + offset_y, frame_index, total_frames)

        elif state == AnimationState.RECORDING:
            # Talking animation - mouth movement
            self._draw_recording_pet(draw, center_x, center_y, frame_index, total_frames)

        elif state == AnimationState.RECOGNIZING:
            # Thinking animation - eyes/head micro movement
            offset_x = int(1.5 * (frame_index % 3 - 1))  # -1.5, 0, 1.5 pixels
            self._draw_thinking_pet(draw, center_x + offset_x, center_y, frame_index, total_frames)

        elif state == AnimationState.COMPLETED:
            # Smile animation - happy expression
            self._draw_completed_pet(draw, center_x, center_y, frame_index, total_frames)

        elif state == AnimationState.ERROR:
            # Error animation - red blinking
            self._draw_error_pet(draw, center_x, center_y, frame_index, total_frames)

        elif state == AnimationState.DRAG:
            # Dragging animation - slight sway
            offset_x = int(2 * (frame_index % 2 - 0.5))  # -1, 1 pixels
            self._draw_drag_pet(draw, center_x + offset_x, center_y, frame_index, total_frames)

        return frame

    def _draw_idle_pet(
        self, draw: ImageDraw.Draw, cx: int, cy: int, frame_idx: int, total: int
    ) -> None:
        """Draw idle/breathe animation frame."""
        # Body - soft gray oval
        body_color = (120, 120, 140, 255)
        draw.ellipse([cx - 20, cy - 15, cx + 20, cy + 15], fill=body_color)

        # Head - slightly lighter
        head_color = (140, 140, 160, 255)
        draw.ellipse([cx - 15, cy - 25, cx + 15, cy - 5], fill=head_color)

        # Eyes - blink occasionally
        eye_openness = 1.0 if frame_idx % 6 != 0 else 0.1  # Blink every 6 frames
        eye_height = int(4 * eye_openness)
        eye_color = (40, 40, 50, 255)

        if eye_height > 0:
            draw.ellipse([cx - 8, cy - 18, cx - 3, cy - 18 + eye_height], fill=eye_color)
            draw.ellipse([cx + 3, cy - 18, cx + 8, cy - 18 + eye_height], fill=eye_color)

        # Small ears
        ear_color = (130, 130, 150, 255)
        draw.polygon([(cx - 12, cy - 25), (cx - 18, cy - 32), (cx - 6, cy - 28)], fill=ear_color)
        draw.polygon([(cx + 12, cy - 25), (cx + 18, cy - 32), (cx + 6, cy - 28)], fill=ear_color)

    def _draw_recording_pet(
        self, draw: ImageDraw.Draw, cx: int, cy: int, frame_idx: int, total: int
    ) -> None:
        """Draw recording/talking animation frame."""
        # Body - slightly warm tone
        body_color = (140, 130, 150, 255)
        draw.ellipse([cx - 20, cy - 15, cx + 20, cy + 15], fill=body_color)

        # Head
        head_color = (160, 150, 170, 255)
        draw.ellipse([cx - 15, cy - 25, cx + 15, cy - 5], fill=head_color)

        # Eyes - alert and open
        eye_color = (50, 50, 60, 255)
        draw.ellipse([cx - 8, cy - 18, cx - 3, cy - 14], fill=eye_color)
        draw.ellipse([cx + 3, cy - 18, cx + 8, cy - 14], fill=eye_color)

        # Mouth - opens and closes (talking)
        mouth_open = abs(frame_idx % 4 - 1.5) * 0.5 + 0.3  # 0.3 to 1.3
        mouth_height = int(5 * mouth_open)
        mouth_color = (80, 50, 60, 255)

        if mouth_height > 1:
            draw.ellipse([cx - 5, cy - 5, cx + 5, cy - 5 + mouth_height], fill=mouth_color)
        else:
            draw.line([cx - 4, cy - 3, cx + 4, cy - 3], fill=mouth_color, width=2)

        # Ears
        ear_color = (150, 140, 160, 255)
        draw.polygon([(cx - 12, cy - 25), (cx - 18, cy - 32), (cx - 6, cy - 28)], fill=ear_color)
        draw.polygon([(cx + 12, cy - 25), (cx + 18, cy - 32), (cx + 6, cy - 28)], fill=ear_color)

    def _draw_thinking_pet(
        self, draw: ImageDraw.Draw, cx: int, cy: int, frame_idx: int, total: int
    ) -> None:
        """Draw thinking/recognizing animation frame."""
        # Body
        body_color = (130, 135, 145, 255)
        draw.ellipse([cx - 20, cy - 15, cx + 20, cy + 15], fill=body_color)

        # Head - tilted slightly
        head_color = (150, 155, 165, 255)
        draw.ellipse([cx - 15, cy - 25, cx + 15, cy - 5], fill=head_color)

        # Eyes - looking to the side (thinking)
        eye_offset = (frame_idx % 3 - 1) * 2  # -2, 0, 2
        eye_color = (45, 45, 55, 255)
        draw.ellipse([cx - 8 + eye_offset, cy - 18, cx - 3 + eye_offset, cy - 14], fill=eye_color)
        draw.ellipse([cx + 3 + eye_offset, cy - 18, cx + 8 + eye_offset, cy - 14], fill=eye_color)

        # Small '...' or motion lines
        dot_y = cy - 8
        for i, dx in enumerate([-3, 0, 3]):
            opacity = (frame_idx // 2 + i) % 3
            if opacity > 0:
                draw.ellipse([cx + dx - 1, dot_y - 1, cx + dx + 1, dot_y + 1], fill=(100, 100, 110, 255))

        # Ears
        ear_color = (140, 145, 155, 255)
        draw.polygon([(cx - 12, cy - 25), (cx - 18, cy - 32), (cx - 6, cy - 28)], fill=ear_color)
        draw.polygon([(cx + 12, cy - 25), (cx + 18, cy - 32), (cx + 6, cy - 28)], fill=ear_color)

    def _draw_completed_pet(
        self, draw: ImageDraw.Draw, cx: int, cy: int, frame_idx: int, total: int
    ) -> None:
        """Draw completed/happy animation frame."""
        # Body - warm and content
        body_color = (150, 160, 140, 255)
        draw.ellipse([cx - 20, cy - 15, cx + 20, cy + 15], fill=body_color)

        # Head
        head_color = (170, 180, 160, 255)
        draw.ellipse([cx - 15, cy - 25, cx + 15, cy - 5], fill=head_color)

        # Eyes - happy closed crescents
        eye_color = (50, 50, 60, 255)
        # Left eye arc
        draw.arc([cx - 9, cy - 18, cx - 2, cy - 13], start=0, end=180, fill=eye_color, width=2)
        # Right eye arc
        draw.arc([cx + 2, cy - 18, cx + 9, cy - 13], start=0, end=180, fill=eye_color, width=2)

        # Smile - gets bigger then stays
        smile_progress = min(frame_idx / (total - 2), 1.0) if total > 2 else 1.0
        smile_width = int(6 * smile_progress)
        smile_depth = int(4 * smile_progress)
        smile_color = (80, 60, 70, 255)

        if smile_width > 2:
            draw.arc(
                [cx - smile_width, cy - 5 - smile_depth, cx + smile_width, cy - 5 + smile_depth],
                start=0, end=180, fill=smile_color, width=2
            )

        # Blush marks
        if smile_progress > 0.5:
            blush_color = (220, 150, 150, 150)
            draw.ellipse([cx - 12, cy - 12, cx - 8, cy - 8], fill=blush_color)
            draw.ellipse([cx + 8, cy - 12, cx + 12, cy - 8], fill=blush_color)

        # Ears
        ear_color = (160, 170, 150, 255)
        draw.polygon([(cx - 12, cy - 25), (cx - 18, cy - 32), (cx - 6, cy - 28)], fill=ear_color)
        draw.polygon([(cx + 12, cy - 25), (cx + 18, cy - 32), (cx + 6, cy - 28)], fill=ear_color)

    def _draw_error_pet(
        self, draw: ImageDraw.Draw, cx: int, cy: int, frame_idx: int, total: int
    ) -> None:
        """Draw error animation frame with red blinking."""
        # Flash red on alternate frames
        flash_on = frame_idx % 2 == 0

        if flash_on:
            body_color = (180, 100, 100, 255)
            head_color = (200, 120, 120, 255)
            eye_color = (40, 20, 20, 255)
            ear_color = (190, 110, 110, 255)
        else:
            body_color = (140, 100, 100, 255)
            head_color = (160, 120, 120, 255)
            eye_color = (50, 30, 30, 255)
            ear_color = (150, 110, 110, 255)

        # Body
        draw.ellipse([cx - 20, cy - 15, cx + 20, cy + 15], fill=body_color)

        # Head
        draw.ellipse([cx - 15, cy - 25, cx + 15, cy - 5], fill=head_color)

        # X eyes
        eye_color_inner = (20, 10, 10, 255)
        # Left X
        draw.line([cx - 9, cy - 17, cx - 2, cy - 13], fill=eye_color_inner, width=2)
        draw.line([cx - 9, cy - 13, cx - 2, cy - 17], fill=eye_color_inner, width=2)
        # Right X
        draw.line([cx + 2, cy - 17, cx + 9, cy - 13], fill=eye_color_inner, width=2)
        draw.line([cx + 2, cy - 13, cx + 9, cy - 17], fill=eye_color_inner, width=2)

        # Worried mouth
        mouth_color = (60, 30, 30, 255)
        draw.arc([cx - 5, cy - 3, cx + 5, cy + 4], start=180, end=360, fill=mouth_color, width=2)

        # Ears
        draw.polygon([(cx - 12, cy - 25), (cx - 18, cy - 32), (cx - 6, cy - 28)], fill=ear_color)
        draw.polygon([(cx + 12, cy - 25), (cx + 18, cy - 32), (cx + 6, cy - 28)], fill=ear_color)

    def _draw_drag_pet(
        self, draw: ImageDraw.Draw, cx: int, cy: int, frame_idx: int, total: int
    ) -> None:
        """Draw dragging animation frame with sway."""
        # Body - slightly stretched horizontally
        body_color = (145, 145, 155, 255)
        draw.ellipse([cx - 22, cy - 13, cx + 18, cy + 13], fill=body_color)

        # Head
        head_color = (165, 165, 175, 255)
        draw.ellipse([cx - 15, cy - 25, cx + 15, cy - 5], fill=head_color)

        # Eyes - looking up (being dragged)
        eye_color = (45, 45, 55, 255)
        draw.ellipse([cx - 8, cy - 19, cx - 3, cy - 15], fill=eye_color)
        draw.ellipse([cx + 3, cy - 19, cx + 8, cy - 15], fill=eye_color)

        # Motion lines
        line_color = (180, 180, 190, 200)
        for i in range(3):
            line_x = cx - 25 - i * 3
            line_top = cy - 5 + i * 5
            draw.line([line_x, line_top, line_x - 5, line_top], fill=line_color, width=1)

        # Ears
        ear_color = (155, 155, 165, 255)
        draw.polygon([(cx - 12, cy - 25), (cx - 18, cy - 32), (cx - 6, cy - 28)], fill=ear_color)
        draw.polygon([(cx + 12, cy - 25), (cx + 18, cy - 32), (cx + 6, cy - 28)], fill=ear_color)

    def load_animation(self, state: AnimationState, frame_files: list[str]) -> None:
        """
        Load animation frames for a specific state from skin folder.

        Args:
            state: The animation state.
            frame_files: List of frame file names to load.
        """
        import os

        if not self._skin_path:
            return

        state_folder = os.path.join(self._skin_path, state.value)
        frames = []

        for filename in frame_files:
            filepath = os.path.join(state_folder, filename)
            cache_key = f"{state.value}:{filename}"

            if cache_key in self._frame_cache:
                frames.append(self._frame_cache[cache_key])
            else:
                try:
                    img = Image.open(filepath)
                    w, h = img.size
                    if w > 2048 or h > 2048:
                        raise ValueError(f"Image size {w}x{h} exceeds maximum 2048x2048")
                    img = img.convert('RGBA')

                    # Resize if needed to match other frames
                    if self._frame_size == (64, 64):
                        self._frame_size = img.size

                    frames.append(img)
                    self._cache_frame(cache_key, img)
                except Exception as e:
                    logger.error(f"Failed to load frame {filepath}: {e}")

        if frames:
            self._animations[state] = frames
            self._frame_counts[state] = len(frames)
            self._frame_rates[state] = self._frame_rates.get(state, 10)

    def _cache_frame(self, key: str, frame: Image.Image) -> None:
        """Cache a frame with LRU eviction."""
        while len(self._frame_cache) >= self._cache_max_size:
            self._frame_cache.popitem(last=False)
        self._frame_cache[key] = frame

    @lru_cache(maxsize=32)
    def _get_cached_frame(self, state: str, index: int) -> Optional[Image.Image]:
        """Get a cached frame (for performance)."""
        try:
            state_enum = AnimationState(state)
        except ValueError:
            return None
        if state_enum in self._animations:
            frames = self._animations[state_enum]
            if 0 <= index < len(frames):
                return frames[index]
        return None

    def play(self, state: AnimationState, loop: bool = True) -> None:
        """
        Play animation for a specific state.

        Args:
            state: The state to play.
            loop: Whether to loop the animation (True) or play once (False).
        """
        with self._lock:
            if state == self._current_state and self._is_playing and not self._is_paused:
                return

            target_state = state if isinstance(state, AnimationState) else AnimationState(state)

            if target_state not in self._animations or not self._animations[target_state]:
                logger.warning(f"No animation frames for state {target_state.value}")
                return

            # Start transition if currently playing a different state
            if target_state != self._current_state:
                self._previous_frame = self.get_current_frame()
                self._transition_progress = 0.0
                self._is_transitioning = True

            self._current_state = target_state
            self._current_frame_index = 0
            self._loop = loop
            self._is_playing = True
            self._is_paused = False

            logger.debug(f"Playing animation: {target_state.value}, loop={loop}")

    def pause(self) -> None:
        """Pause the current animation."""
        with self._lock:
            if self._is_playing and not self._is_paused:
                self._is_paused = True
                logger.debug("Animation paused")

    def resume(self) -> None:
        """Resume the paused animation."""
        with self._lock:
            if self._is_playing and self._is_paused:
                self._is_paused = False
                logger.debug("Animation resumed")

    def stop(self) -> None:
        """Stop animation and return to idle state."""
        with self._lock:
            self._is_playing = False
            self._is_paused = False
            self._is_transitioning = False
            self._transition_progress = 0.0
            self._previous_frame = None
            self.play(AnimationState.IDLE)
            logger.debug("Animation stopped, returned to idle")

    def set_audio_level(self, level: float) -> None:
        """
        Set audio energy level for sound wave visualization.

        Args:
            level: Audio energy level from 0.0 (silence) to 1.0 (max).
        """
        with self._lock:
            self._audio_level = max(0.0, min(1.0, level))

    def get_current_frame(self) -> Image.Image:
        """
        Get the current animation frame with sound wave overlay if recording.

        Returns:
            Current frame image with all overlays applied.
        """
        with self._lock:
            if not self._animations.get(self._current_state):
                # Return a blank frame if no animation
                return Image.new('RGBA', self._frame_size, (0, 0, 0, 0))

            frames = self._animations[self._current_state]
            if not frames:
                return Image.new('RGBA', self._frame_size, (0, 0, 0, 0))
            frame = frames[self._current_frame_index % len(frames)].copy()

            # Apply transition fade if transitioning
            if self._is_transitioning and self._previous_frame:
                frame = self._apply_transition(frame)

            # Apply sound wave visualization if recording and audio level > 0
            if self._current_state == AnimationState.RECORDING and self._audio_level > 0:
                frame = self._apply_sound_waves(frame)

            return frame

    def _apply_transition(self, current_frame: Image.Image) -> Image.Image:
        """Apply cross-fade transition between states."""
        if not self._previous_frame:
            return current_frame

        # Resize previous frame to match current if needed
        prev_frame = self._previous_frame.copy()
        if prev_frame.size != current_frame.size:
            prev_frame = prev_frame.resize(current_frame.size, Image.LANCZOS)

        # Blend frames based on transition progress
        alpha = self._transition_progress
        result = Image.new('RGBA', current_frame.size)

        # Blend pixel by pixel for proper alpha handling
        current_pixels = current_frame.load()
        prev_pixels = prev_frame.load()
        result_pixels = result.load()

        for y in range(current_frame.height):
            for x in range(current_frame.width):
                r1, g1, b1, a1 = prev_pixels[x, y]
                r2, g2, b2, a2 = current_pixels[x, y]

                # Alpha blend
                out_a = int(a1 * (1 - alpha) + a2 * alpha)
                if out_a > 0:
                    out_r = int(r1 * (1 - alpha) + r2 * alpha)
                    out_g = int(g1 * (1 - alpha) + g2 * alpha)
                    out_b = int(b1 * (1 - alpha) + b2 * alpha)
                    result_pixels[x, y] = (out_r, out_g, out_b, out_a)
                else:
                    result_pixels[x, y] = (0, 0, 0, 0)

        return result

    def _apply_sound_waves(self, frame: Image.Image) -> Image.Image:
        """Apply sound wave visualization to the frame."""
        result = frame.copy()
        draw = ImageDraw.Draw(result, 'RGBA')

        cx, cy = frame.width // 2, frame.height // 2

        # Update wave offset for animation
        self._sound_wave_offset += 0.15

        # Generate 3 layers of wave rings
        for layer in range(3):
            # Layer offset creates staggered animation
            phase = self._sound_wave_offset + layer * 0.8

            # Base radius grows with audio level and layer
            base_radius = 30 + layer * 12 + int(15 * self._audio_level)

            # Wave effect - radius oscillates
            radius_offset = int(8 * self._audio_level * abs(1 - (phase % 2)))
            radius = base_radius + radius_offset

            # Alpha decreases for outer layers
            alpha = int(180 * (1 - layer * 0.25) * self._audio_level)

            # Color: cyan-ish for sound waves
            color = (100, 200, 255, alpha)

            # Draw arc (partial ring for a more dynamic look)
            start_angle = (phase * 30) % 360
            end_angle = start_angle + 180

            draw.arc(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                start=int(start_angle), end=int(end_angle),
                fill=color, width=2
            )

        return result

    def get_frame_size(self) -> tuple[int, int]:
        """Get the frame size of the animation."""
        return self._frame_size

    def start(self) -> None:
        """Start the animation playback loop (call from main thread or asyncio loop)."""
        self._running = True

    def update(self, dt: float) -> None:
        """
        Update animation state. Call this regularly in your main loop.

        Args:
            dt: Delta time since last update in seconds.
        """
        with self._lock:
            if not self._is_playing or self._is_paused:
                return

            # Update transition
            if self._is_transitioning:
                self._transition_progress += dt / self._transition_duration
                if self._transition_progress >= 1.0:
                    self._is_transitioning = False
                    self._transition_progress = 1.0
                    self._previous_frame = None

            # Get frame rate for current state
            frame_rate = self._frame_rates.get(self._current_state, 10)
            frame_duration = 1.0 / frame_rate

            # Advance frame based on time
            self._frame_duration += dt
            if self._frame_duration >= frame_duration:
                self._frame_duration = 0.0
                self._advance_frame()

    def _advance_frame(self) -> None:
        """Advance to the next animation frame."""
        if self._current_state not in self._animations:
            return

        frames = self._animations[self._current_state]
        max_index = len(frames) - 1

        if self._current_frame_index >= max_index:
            if self._loop:
                self._current_frame_index = 0
            else:
                # For non-looping animations (like COMPLETED), stay on last frame
                self._current_frame_index = max_index
                self._is_playing = False
        else:
            self._current_frame_index += 1

    async def animation_loop(self) -> None:
        """Async animation loop for use with asyncio."""
        self._running = True
        last_time = time.monotonic()

        while self._running:
            current_time = time.monotonic()
            dt = current_time - last_time
            last_time = current_time

            self.update(dt)

            # Calculate sleep time to maintain frame rate
            await asyncio.sleep(1.0 / self._frame_rate)

    def destroy(self) -> None:
        """Release all resources."""
        self._running = False

        with self._lock:
            self._animations.clear()
            self._frame_cache.clear()
            self._previous_frame = None

            logger.debug("AnimationController resources released")


# Module-level convenience functions for quick access
_default_controller: Optional[AnimationController] = None


def get_default_controller() -> AnimationController:
    """Get or create the default animation controller."""
    global _default_controller
    if _default_controller is None:
        _default_controller = AnimationController()
    return _default_controller


def destroy_default_controller() -> None:
    """Destroy the default animation controller."""
    global _default_controller
    if _default_controller is not None:
        _default_controller.destroy()
        _default_controller = None
