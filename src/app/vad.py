"""VAD 语音分段：把连续音频切成完整语音段"""
from __future__ import annotations

from pathlib import Path

import numpy as np


class EnergyVad:
    """Simple energy-based VAD. No model file required.

    Splits audio into speech segments using RMS energy threshold:
    speech starts when energy exceeds threshold, ends after a run of
    silent blocks.
    """

    def __init__(
        self,
        threshold: float = 0.006,
        block_ms: int = 100,
        sample_rate: int = 16000,
        silence_blocks_to_stop: int = 5,
        min_speech_blocks: int = 3,
    ) -> None:
        self.threshold = threshold
        self.silence_blocks_to_stop = silence_blocks_to_stop
        self.min_speech_blocks = min_speech_blocks
        self._block_samples = sample_rate * block_ms // 1000

        self._buffer: list[np.ndarray] = []
        self._speech_blocks = 0
        self._silence_count = 0
        self._in_speech = False

    def feed(self, samples: np.ndarray) -> list[np.ndarray]:
        """Feed a block of audio. Returns any complete speech segments."""
        samples = samples.astype(np.float32)
        rms = float(np.sqrt(np.mean(samples ** 2)))
        segments: list[np.ndarray] = []

        if rms >= self.threshold:
            self._buffer.append(samples)
            self._in_speech = True
            self._speech_blocks += 1
            self._silence_count = 0
        else:
            if self._in_speech:
                self._buffer.append(samples)  # keep trailing silence
                self._silence_count += 1
                if self._silence_count >= self.silence_blocks_to_stop:
                    if self._speech_blocks >= self.min_speech_blocks:
                        segments.append(np.concatenate(self._buffer))
                    self._reset()

        return segments

    def flush(self) -> list[np.ndarray]:
        """Return any in-progress segment. Call when stopping."""
        segments: list[np.ndarray] = []
        if self._in_speech and self._speech_blocks >= self.min_speech_blocks:
            segments.append(np.concatenate(self._buffer))
        self._reset()
        return segments

    def reset(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._buffer = []
        self._speech_blocks = 0
        self._silence_count = 0
        self._in_speech = False


class VadSegmenter:
    """Silero VAD segmenter (requires silero_vad.onnx). Used optionally."""

    WINDOW = 512

    def __init__(
        self,
        silero_model_path: str | Path,
        sample_rate: int = 16000,
        threshold: float = 0.5,
        min_silence_duration: float = 0.5,
        min_speech_duration: float = 0.25,
        max_speech_duration: float = 20.0,
    ) -> None:
        from sherpa_onnx import VoiceActivityDetector, VadModelConfig
        from sherpa_onnx.lib._sherpa_onnx import SileroVadModelConfig

        config = VadModelConfig()
        config.silero_vad = SileroVadModelConfig(
            model=str(silero_model_path),
            threshold=threshold,
            min_silence_duration=min_silence_duration,
            min_speech_duration=min_speech_duration,
            window_size=self.WINDOW,
            max_speech_duration=max_speech_duration,
        )
        config.sample_rate = sample_rate
        config.num_threads = 1
        self._vad = VoiceActivityDetector(config)
        self._sample_rate = sample_rate
        self._buffer = np.zeros(0, dtype=np.float32)

    def feed(self, samples: np.ndarray) -> list[np.ndarray]:
        self._buffer = np.concatenate([self._buffer, samples.astype(np.float32)])
        segments: list[np.ndarray] = []
        n = (len(self._buffer) // self.WINDOW) * self.WINDOW
        if n > 0:
            chunks = self._buffer[:n].reshape(-1, self.WINDOW)
            self._buffer = self._buffer[n:]
            for chunk in chunks:
                self._vad.accept_waveform(chunk)
                segments.extend(self._drain())
        return segments

    def flush(self) -> list[np.ndarray]:
        if len(self._buffer) > 0:
            pad = self.WINDOW - (len(self._buffer) % self.WINDOW or self.WINDOW)
            if pad and pad < self.WINDOW:
                self._buffer = np.concatenate(
                    [self._buffer, np.zeros(pad, dtype=np.float32)]
                )
            self._vad.accept_waveform(self._buffer)
            self._buffer = np.zeros(0, dtype=np.float32)
        self._vad.flush()
        return self._drain()

    def reset(self) -> None:
        self._vad.reset()
        self._buffer = np.zeros(0, dtype=np.float32)

    def _drain(self) -> list[np.ndarray]:
        segs: list[np.ndarray] = []
        while not self._vad.empty():
            seg = self._vad.pop()
            segs.append(np.array(seg.samples, dtype=np.float32))
        return segs

