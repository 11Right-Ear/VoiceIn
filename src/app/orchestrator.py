from __future__ import annotations

import threading
import time
from enum import Enum, auto
from pathlib import Path

import numpy as np

from config import Config
from audio_capture import AudioCapture
from recognizer import Recognizer
from output import paste
from tray import TrayIcon


class State(Enum):
    IDLE = auto()
    RECORDING = auto()
    FINALIZING = auto()
    PASTING = auto()


class Orchestrator:
    def __init__(self, cfg: Config, tray: TrayIcon) -> None:
        self._cfg = cfg
        self._tray = tray
        self._state = State.IDLE
        self._lock = threading.Lock()

        self._audio: AudioCapture | None = None
        self._rec: Recognizer | None = None

    # ----- public API (called from hotkey thread) -----

    def on_hotkey(self) -> None:
        with self._lock:
            if self._state == State.IDLE:
                self._start()
            elif self._state == State.RECORDING:
                self._stop()

    # ----- internal -----

    def _start(self) -> None:
        model_dir = self._cfg.model_dir or str(
            Path.home() / ".voicein" / "models" / "zh-small-zipformer"
        )

        try:
            self._rec = Recognizer(
                model_dir, self._cfg.sample_rate,
                enable_vad=True, vad_timeout_ms=self._cfg.vad_timeout_ms,
            )
            self._audio = AudioCapture(
                self._cfg.device_id, self._cfg.sample_rate,
                channels=1, block_ms=self._cfg.block_ms,
            )
        except Exception as e:
            self._tray.notify("VoiceIn 错误", f"初始化失败: {e}")
            print(f"[DEBUG] init error: {e}")
            return

        self._state = State.RECORDING
        self._tray.set_recording(True)

        self._stream = self._rec.create_stream()
        self._final_text = ""
        self._text = ""

        try:
            self._audio.start(self._on_audio)
            print("[DEBUG] recording started")
        except Exception as e:
            self._state = State.IDLE
            self._tray.set_recording(False)
            self._tray.notify("VoiceIn 错误", f"启动录音失败: {e}")
            print(f"[DEBUG] start error: {e}")

    def _stop(self) -> None:
        print(f"[DEBUG] _stop called, state={self._state}")
        self._state = State.FINALIZING
        if self._audio:
            print("[DEBUG] stopping audio...")
            self._audio.stop()
            print("[DEBUG] audio stopped")

        if self._rec:
            self._final_text = self._rec.get_text(self._stream).strip()
            print(f"[DEBUG] final_text='{self._final_text}'")

        if self._final_text:
            self._state = State.PASTING
            print(f"[DEBUG] pasting: '{self._final_text}'")
            paste(self._final_text)
            print("[DEBUG] paste done")
        else:
            print("[DEBUG] no text to paste")

        self._cleanup()
        print("[DEBUG] cleanup done")

    def _cleanup(self) -> None:
        if self._audio:
            self._audio.close()
            self._audio = None
        self._rec = None
        self._stream = None
        self._tray.set_recording(False)
        self._state = State.IDLE

    _audio_call_count = 0

    def _on_audio(self, samples: np.ndarray, sample_rate: int) -> None:
        self._audio_call_count += 1
        with self._lock:
            if self._state != State.RECORDING:
                return
            self._rec.accept_waveform(self._stream, samples)
            self._rec.decode(self._stream)
            new_text = self._rec.get_text(self._stream)
            if new_text != self._text:
                self._text = new_text
                print(f"[DEBUG] text so far: '{new_text}'")

            if self._rec.is_endpoint(self._stream):
                print(f"[DEBUG] VAD endpoint at call #{self._audio_call_count}")
                self._stop()
