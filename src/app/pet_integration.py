"""VoiceIn 桌面宠物 — 主程序集成层

将 pet_window、pet_animation、pet_skin、pet_recording_visual、pet_storage
与 VoiceIn 主程序（orchestrator、hotkey）整合。

状态映射:
    VoiceIn State    -> Pet State
    ─────────────────────────────────
    IDLE             -> idle
    RECORDING        -> recording
    (识别中)          -> recognizing
    (粘贴完成)        -> completed
    (错误)           -> error
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from pet_animation import AnimationController, AnimationState
from pet_recording_visual import RecordingVisualizer
from pet_skin import SkinManager
from pet_storage import PetPosition, PetStats, PetStorage
from pet_window import PetWindow

_logger = logging.getLogger("pet_integration")


class PetIntegration:
    """VoiceIn 宠物集成器

    封装宠物功能，负责：
    - 与 orchestrator 状态同步
    - 音频能量可视化
    - 粘贴完成动画
    - 热键触发（点击宠物 = 按下录音热键）
    - 宠物窗口生命周期管理
    """

    def __init__(
        self,
        config: dict,
        hotkey_callback: Callable[[], None],
    ) -> None:
        """
        Args:
            config: VoiceIn 配置字典（从 ~/.voicein/config.json 加载）
            hotkey_callback: 热键回调，通常是 orchestrator.on_hotkey
        """
        self._config = config
        self._hotkey_callback = hotkey_callback

        # ── Pet components ────────────────────────────────────────────────
        self._storage: PetStorage | None = None
        self._window: PetWindow | None = None
        self._animation: AnimationController | None = None
        self._visualizer: RecordingVisualizer | None = None
        self._skin_manager: SkinManager | None = None

        # ── State ─────────────────────────────────────────────────────────
        self._visible = False
        self._running = False
        self._restart_attempts = 0
        self._max_restart_attempts = 3

        # ── Internal state tracking ────────────────────────────────────────
        self._orchestrator_state: str = "idle"
        self._audio_level: float = 0.0
        self._is_recognizing: bool = False
        self._recognizing_start_time: float = 0.0
        self._last_paste_time: float = 0.0

        # ── Animation thread ────────────────────────────────────────────────
        self._anim_lock = threading.Lock()
        self._anim_running = False
        self._anim_thread: threading.Thread | None = None

        # ── Load pet config ────────────────────────────────────────────────
        pet_cfg = config.get("pet", {})
        self._pet_enabled = pet_cfg.get("enabled", True)
        self._pet_skin = pet_cfg.get("skin", "pixel_robot")
        self._frame_rate = pet_cfg.get("frame_rate", 60)
        self._always_on_top = pet_cfg.get("always_on_top", True)

    # ── public: lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """启动宠物窗口，加载配置。"""
        if not self._pet_enabled:
            _logger.info("Pet integration disabled in config")
            return

        if self._running:
            _logger.warning("PetIntegration.start() called but already running")
            return

        try:
            self._init_storage()
            self._init_animation()
            self._init_visualizer()
            self._init_window()
            self._restore_position()
            self._start_animation_thread()

            self._running = True
            self._restart_attempts = 0
            _logger.info("PetIntegration started successfully")
        except Exception as e:
            _logger.error("Failed to start PetIntegration: %s", e)
            self._cleanup_components()
            raise

    def stop(self) -> None:
        """停止宠物，保存状态。"""
        if not self._running:
            return

        _logger.info("Stopping PetIntegration")
        self._running = False

        self._save_state()
        self._stop_animation_thread()
        self._destroy_window()
        self._cleanup_components()

        _logger.info("PetIntegration stopped")

    def show(self) -> None:
        """显示宠物。"""
        if self._window is None:
            return
        try:
            self._window.show()
            self._visible = True
            _logger.debug("Pet shown")
        except Exception as e:
            _logger.error("Failed to show pet: %s", e)

    def hide(self) -> None:
        """隐藏宠物。"""
        if self._window is None:
            return
        try:
            self._window.hide()
            self._visible = False
            _logger.debug("Pet hidden")
        except Exception as e:
            _logger.error("Failed to hide pet: %s", e)

    def toggle(self) -> None:
        """切换显示/隐藏。"""
        if self._visible:
            self.hide()
        else:
            self.show()

    def is_visible(self) -> bool:
        """宠物是否可见。"""
        return self._visible

    def destroy(self) -> None:
        """销毁宠物，释放所有资源。"""
        self.stop()
        self._storage = None
        self._animation = None
        self._visualizer = None
        self._skin_manager = None
        _logger.debug("PetIntegration destroyed")

    # ── public: orchestrator callbacks ───────────────────────────────────────

    def on_orchestrator_state_changed(self, state: str) -> None:
        """orchestrator 状态变化回调（由外部调用）。

        Args:
            state: VoiceIn 状态字符串: "idle", "recording"
        """
        if not self._running:
            return

        old_state = self._orchestrator_state
        self._orchestrator_state = state

        _logger.debug("Orchestrator state changed: %s -> %s", old_state, state)

        # Map VoiceIn state to pet state
        pet_state = self._map_state(state)
        self._set_pet_state(pet_state)

        # Handle recognizing -> completed transition
        if old_state == "recording" and state == "idle":
            # Recording just stopped, recognizer will process
            # completed state will be triggered by on_paste_completed
            pass

    def on_audio_level_changed(self, level: float) -> None:
        """音频能量变化回调（由外部调用）。

        Args:
            level: 音频能量等级 (0.0–1.0)
        """
        if not self._running:
            return

        self._audio_level = max(0.0, min(1.0, level))

        if self._window is not None:
            self._window.set_audio_level(self._audio_level)

        if self._animation is not None:
            self._animation.set_audio_level(self._audio_level)

        if self._visualizer is not None:
            self._visualizer.set_audio_level(self._audio_level)

    def on_paste_completed(self) -> None:
        """粘贴完成回调（由外部调用）。"""
        if not self._running:
            return

        self._last_paste_time = time.time()
        _logger.debug("Paste completed at %.2f", self._last_paste_time)

        # Trigger completion animation
        self._trigger_completion_animation()

        # Update stats
        if self._storage is not None:
            try:
                self._storage.update_stats(
                    recording_time=0.0,  # Time tracked by orchestrator
                    skin_id=self._pet_skin,
                )
            except Exception as e:
                _logger.warning("Failed to update pet stats: %s", e)

    def on_error(self, error_msg: str | None = None) -> None:
        """错误回调（由外部调用）。"""
        if not self._running:
            return

        _logger.warning("VoiceIn error: %s", error_msg)
        self._set_pet_state("error")

        # Reset to idle after a delay
        def _reset_state() -> None:
            time.sleep(2.0)
            if self._running:
                self._set_pet_state("idle")

        threading.Thread(target=_reset_state, daemon=True).start()

    # ── public: hotkey integration ───────────────────────────────────────────

    def on_pet_clicked(self) -> None:
        """宠物被点击时调用（由 PetWindow 触发）。"""
        _logger.debug("Pet clicked, triggering hotkey callback")
        if self._hotkey_callback:
            try:
                self._hotkey_callback()
            except Exception as e:
                _logger.error("Hotkey callback failed: %s", e)

    # ── internal: component initialization ──────────────────────────────────

    def _init_storage(self) -> None:
        """初始化存储模块。"""
        try:
            self._storage = PetStorage()
            _logger.debug("PetStorage initialized")
        except Exception as e:
            _logger.error("Failed to initialize PetStorage: %s", e)
            self._storage = None

    def _init_animation(self) -> None:
        """初始化动画控制器。"""
        try:
            self._animation = AnimationController(frame_rate=self._frame_rate)
            self._animation.play(AnimationState.IDLE)
            _logger.debug("AnimationController initialized")
        except Exception as e:
            _logger.error("Failed to initialize AnimationController: %s", e)
            self._animation = None

    def _init_visualizer(self) -> None:
        """初始化录音可视化组件。"""
        try:
            frame_size = (128, 128)  # Default pet window size
            self._visualizer = RecordingVisualizer(frame_size=frame_size)
            _logger.debug("RecordingVisualizer initialized")
        except Exception as e:
            _logger.error("Failed to initialize RecordingVisualizer: %s", e)
            self._visualizer = None

    def _init_window(self) -> None:
        """初始化宠物窗口。"""
        if self._window is not None:
            return

        try:
            pet_config = {
                "always_on_top": self._always_on_top,
                "hide_hotkey_modifiers": self._config.get("hotkey_modifiers", 3),
                "hide_hotkey_vk": self._config.get("hotkey_vk", 0x48),
                "default_size": self._config.get("pet", {}).get("size", 128),
            }

            self._window = PetWindow(config=pet_config)
            self._window.register_state_callback(self._on_window_state_changed)
            self._window.register_click_callback(self.on_pet_clicked)
            self._window.show()
            self._visible = True

            _logger.debug("PetWindow initialized")
        except Exception as e:
            _logger.error("Failed to initialize PetWindow: %s", e)
            self._window = None
            raise

    def _restore_position(self) -> None:
        """从存储恢复宠物位置。"""
        if self._storage is None or self._window is None:
            return

        try:
            position = self._storage.load_position()
            self._window.set_position(position.x, position.y)

            # Load skin
            if position.skin_id:
                self._pet_skin = position.skin_id

            _logger.debug("Restored pet position: (%d, %d)", position.x, position.y)
        except Exception as e:
            _logger.warning("Failed to restore pet position: %s", e)

    def _save_state(self) -> None:
        """保存宠物状态到存储。"""
        if self._storage is None or self._window is None:
            return

        try:
            x, y = self._window.get_position()
            position = PetPosition(
                x=x,
                y=y,
                skin_id=self._pet_skin,
                always_on_top=self._always_on_top,
                scale=1.0,
            )
            self._storage.save_position(position)
            _logger.debug("Saved pet state")
        except Exception as e:
            _logger.warning("Failed to save pet state: %s", e)

    # ── internal: animation thread ──────────────────────────────────────────

    def _start_animation_thread(self) -> None:
        """启动独立动画渲染线程。"""
        if self._anim_thread is not None and self._anim_thread.is_alive():
            return

        self._anim_running = True
        self._anim_thread = threading.Thread(
            target=self._animation_loop,
            daemon=True,
            name="PetAnimationThread",
        )
        self._anim_thread.start()
        _logger.debug("Animation thread started")

    def _stop_animation_thread(self) -> None:
        """停止动画渲染线程。"""
        self._anim_running = False
        if self._anim_thread is not None:
            self._anim_thread.join(timeout=2.0)
            self._anim_thread = None
        _logger.debug("Animation thread stopped")

    def _animation_loop(self) -> None:
        """独立动画渲染循环（目标帧率 60fps）。"""
        target_dt = 1.0 / self._frame_rate
        last_update = time.monotonic()

        while self._anim_running:
            try:
                now = time.monotonic()
                dt = now - last_update
                last_update = now

                # Update animation state
                if self._animation is not None:
                    self._animation.update(dt)

                # Update visualizer
                if self._visualizer is not None:
                    self._visualizer.update(dt)

                # Render to window
                self._render_frame()

            except Exception as e:
                _logger.warning("Animation loop error: %s", e)

            # Maintain frame rate
            elapsed = time.monotonic() - now
            sleep_time = target_dt - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _render_frame(self) -> None:
        """渲染当前帧到窗口。"""
        if self._window is None or not self._running:
            return

        try:
            # Get current frame from animation
            if self._animation is not None:
                frame = self._animation.get_current_frame()
            else:
                return

            # Apply recording visualization if in recording state
            if self._orchestrator_state == "recording" and self._visualizer is not None:
                frame = self._visualizer.render(
                    frame,
                    state="recording",
                    audio_level=self._audio_level,
                )

            # Update window image
            # Note: PetWindow handles its own rendering via _update_window_image
            # This method is for additional visual processing if needed

        except Exception as e:
            _logger.warning("Render frame error: %s", e)

    # ── internal: state management ──────────────────────────────────────────

    def _map_state(self, state: str) -> str:
        """将 VoiceIn 状态映射到宠物状态。"""
        mapping = {
            "idle": "idle",
            "recording": "recording",
        }
        return mapping.get(state, "idle")

    def _set_pet_state(self, state: str) -> None:
        """设置宠物状态。"""
        if self._window is not None:
            try:
                self._window.set_state(state)
            except Exception as e:
                _logger.warning("Failed to set pet window state: %s", e)

        if self._animation is not None:
            try:
                state_enum = AnimationState(state)
                self._animation.play(state_enum)
            except ValueError:
                # Fallback to idle
                self._animation.play(AnimationState.IDLE)
            except Exception as e:
                _logger.warning("Failed to set animation state: %s", e)

    def _trigger_completion_animation(self) -> None:
        """触发粘贴完成动画。"""
        # Set to completed state briefly
        self._set_pet_state("completed")

        # Trigger visualizer completion effect
        if self._visualizer is not None:
            self._visualizer.trigger_completion_animation()

        # Return to idle after animation
        def _return_to_idle() -> None:
            time.sleep(2.0)  # Let completion animation play
            if self._running and self._orchestrator_state == "idle":
                self._set_pet_state("idle")

        threading.Thread(target=_return_to_idle, daemon=True).start()

    def _on_window_state_changed(self, state: str) -> None:
        """PetWindow 状态变化回调。"""
        _logger.debug("Window state changed: %s", state)
        # Could be used to sync state back to orchestrator if needed

    # ── internal: crash recovery ────────────────────────────────────────────

    def _handle_crash(self, error: Exception) -> None:
        """处理宠物组件崩溃。"""
        _logger.error("Pet component crashed: %s", error)

        if self._restart_attempts < self._max_restart_attempts:
            self._restart_attempts += 1
            _logger.info(
                "Attempting pet restart (%d/%d)",
                self._restart_attempts,
                self._max_restart_attempts,
            )

            # Save current state before restart
            self._save_state()

            # Cleanup and restart
            self._cleanup_components()
            time.sleep(1.0)

            try:
                self.start()
            except Exception as e:
                _logger.error("Pet restart failed: %s", e)
        else:
            _logger.error(
                "Pet restart limit reached (%d), giving up",
                self._max_restart_attempts,
            )

    # ── internal: cleanup ───────────────────────────────────────────────────

    def _destroy_window(self) -> None:
        """销毁宠物窗口。"""
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception as e:
                _logger.warning("Error destroying pet window: %s", e)
            self._window = None

    def _cleanup_components(self) -> None:
        """清理所有宠物组件。"""
        if self._animation is not None:
            try:
                self._animation.destroy()
            except Exception:
                pass
            self._animation = None

        if self._visualizer is not None:
            try:
                self._visualizer.destroy()
            except Exception:
                pass
            self._visualizer = None

        if self._storage is not None:
            try:
                self._storage.destroy()
            except Exception:
                pass
            self._storage = None

        if self._skin_manager is not None:
            try:
                self._skin_manager.destroy()
            except Exception:
                pass
            self._skin_manager = None

    # ── properties ──────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """宠物是否正在运行。"""
        return self._running

    @property
    def current_state(self) -> str:
        """当前宠物状态。"""
        return self._orchestrator_state

    @property
    def audio_level(self) -> float:
        """当前音频能量等级。"""
        return self._audio_level

    @property
    def storage(self) -> Optional[PetStorage]:
        """宠物存储模块（如果有）。"""
        return self._storage

    @property
    def window(self) -> Optional[PetWindow]:
        """宠物窗口（如果有）。"""
        return self._window

    @property
    def animation(self) -> Optional[AnimationController]:
        """动画控制器（如果有）。"""
        return self._animation


# ── Module-level convenience function ───────────────────────────────────────


_default_integration: Optional[PetIntegration] = None


def get_default_integration() -> Optional[PetIntegration]:
    """获取默认宠物集成实例。"""
    return _default_integration


def create_integration(
    config: dict,
    hotkey_callback: Callable[[], None],
) -> PetIntegration:
    """创建宠物集成实例的便捷函数。"""
    global _default_integration
    _default_integration = PetIntegration(config, hotkey_callback)
    return _default_integration


def destroy_integration() -> None:
    """销毁默认宠物集成实例。"""
    global _default_integration
    if _default_integration is not None:
        _default_integration.destroy()
        _default_integration = None
