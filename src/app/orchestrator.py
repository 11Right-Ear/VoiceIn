from __future__ import annotations

import threading
from enum import Enum, auto
from pathlib import Path

import numpy as np

from config import Config
from audio_capture import AudioCapture
from output import paste
from tray import TrayIcon


class State(Enum):
    IDLE = auto()
    RECORDING = auto()


class Orchestrator:
    """常驻语音服务：模型/采集器/VAD 在启动时加载一次，热键开关录音。

    sensevoice 引擎：录音期间 EnergyVad 分段，每段独立识别 + 粘贴，连续多句。
    streaming 引擎：录音期间累积，停止时一次性识别粘贴（备选）。
    """

    def __init__(self, cfg: Config, tray: TrayIcon) -> None:
        self._cfg = cfg
        self._tray = tray
        self._state = State.IDLE
        self._lock = threading.Lock()

        # 常驻加载（一次性，几秒）
        self._audio = AudioCapture(
            cfg.device_id, cfg.sample_rate,
            channels=1, block_ms=cfg.block_ms,
        )

        if cfg.engine == "streaming":
            from recognizer import Recognizer
            model_dir = cfg.model_dir or str(
                Path.home() / ".voicein" / "models" / "zh-small-zipformer"
            )
            self._rec = Recognizer(
                model_dir, cfg.sample_rate,
                enable_vad=False, vad_timeout_ms=cfg.vad_timeout_ms,
            )
            self._vad = None
        else:
            from recognizer import FunAsrRecognizer
            from vad import EnergyVad
            self._rec = FunAsrRecognizer(
                sample_rate=cfg.sample_rate,
                language=cfg.language or None,  # 空字符串 → None → 让模型自动检测
            )
            self._vad = EnergyVad(
                threshold=cfg.vad_threshold,
                block_ms=cfg.block_ms, sample_rate=cfg.sample_rate,
            )

        # streaming 累积状态
        self._stream = None
        self._acc_samples = 0
        self._can_decode = False

    # ----- public: called from hotkey thread -----

    def on_hotkey(self) -> None:
        with self._lock:
            if self._state == State.IDLE:
                self._start_recording()
            else:
                self._stop_recording()

    # ----- recording control -----

    def _start_recording(self) -> None:
        try:
            if self._vad is not None:
                self._vad.reset()
            else:
                self._stream = self._rec.create_stream()
                self._acc_samples = 0
                self._can_decode = False
            self._audio.start(self._on_audio)
        except Exception as e:
            self._tray.notify("VoiceIn 错误", f"启动录音失败: {e}")
            return

        self._state = State.RECORDING
        self._tray.set_recording(True)

    def _stop_recording(self) -> None:
        self._state = State.IDLE
        try:
            self._audio.stop()
        except Exception:
            pass

        if self._vad is not None:
            # flush 剩余段
            for seg in self._vad.flush():
                self._recognize_and_paste(seg)
        elif self._stream is not None:
            # streaming：停止时一次性识别
            self._recognize_and_paste_stream()

        self._tray.set_recording(False)

    # ----- audio callback (runs on AudioCapture consumer thread) -----

    def _on_audio(self, samples: np.ndarray, sample_rate: int) -> None:
        if self._state != State.RECORDING:
            return

        if self._vad is not None:
            for seg in self._vad.feed(samples):
                self._recognize_and_paste(seg)
        else:
            self._on_audio_streaming(samples)

    def _recognize_and_paste(self, seg: np.ndarray) -> None:
        try:
            text = self._rec.recognize(seg)
        except Exception as e:
            self._tray.notify("VoiceIn 错误", f"识别失败: {e}")
            return
        if text.strip():
            paste(text)
            if self._cfg.auto_enter:
                _press_enter()

    # ----- streaming fallback path -----

    def _on_audio_streaming(self, samples: np.ndarray) -> None:
        self._rec.accept_waveform(self._stream, samples)
        self._acc_samples += len(samples)
        if not self._can_decode:
            if self._acc_samples < 16000:
                return
            self._can_decode = True
        self._rec.decode(self._stream)

    def _recognize_and_paste_stream(self) -> None:
        try:
            self._rec.decode(self._stream)
            text = self._rec.get_text(self._stream).strip()
        except Exception:
            return
        if text:
            paste(text)
            if self._cfg.auto_enter:
                _press_enter()


def _press_enter() -> None:
    """模拟回车键。"""
    import ctypes
    user32 = ctypes.windll.user32
    VK_RETURN = 0x0D
    KEYEVENTF_KEYUP = 0x0002
    user32.keybd_event(VK_RETURN, 0, 0, 0)
    user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
