from __future__ import annotations

import queue
import threading
from typing import Callable

import numpy as np


class LlmRefiner:
    def __init__(
        self,
        api_url: str,
        api_key: str,
        api_model: str,
        api_prompt: str,
        result_queue: queue.Queue[str],
        sample_rate: int = 16000,
    ) -> None:
        self._api_url = api_url
        self._api_key = api_key
        self._api_model = api_model
        self._api_prompt = api_prompt
        self._result_queue = result_queue
        self._sample_rate = sample_rate
        self._pending_queue: queue.Queue[tuple[str, np.ndarray]] = queue.Queue()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def enqueue(self, text: str, audio: np.ndarray) -> None:
        self._pending_queue.put((text, audio))

    def stop(self) -> None:
        self._running = False
        self._thread.join(timeout=5.0)

    def _run(self) -> None:
        import os
        import requests

        while self._running:
            try:
                text, audio = self._pending_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                refined = self._call_api(text, audio)
            except Exception:
                refined = text

            try:
                self._result_queue.put_nowait(refined)
            except queue.Full:
                pass

    def _call_api(self, text: str, audio: np.ndarray) -> str:
        import os

        for k in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "http_proxy",
            "https_proxy",
            "ALL_PROXY",
            "all_proxy",
        ):
            os.environ.pop(k, None)

        prompt = self._api_prompt.format(text=text)

        payload = {
            "model": self._api_model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        resp = requests.post(
            self._api_url, json=payload, headers=headers, timeout=20
        )
        resp.raise_for_status()
        result = resp.json()

        try:
            return result["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError):
            return result.get("text", text).strip()


class LlmRecognizer:
    def __init__(
        self,
        local_rec,  # FunAsrRecognizer instance
        api_url: str,
        api_key: str,
        api_model: str,
        api_prompt: str,
        result_queue: queue.Queue[str],
        sample_rate: int = 16000,
    ) -> None:
        self._local = local_rec
        self._refiner = LlmRefiner(
            api_url=api_url,
            api_key=api_key,
            api_model=api_model,
            api_prompt=api_prompt,
            result_queue=result_queue,
            sample_rate=sample_rate,
        )
        self._sample_rate = sample_rate

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def recognize(self, samples: np.ndarray) -> str:
        text = self._local.recognize(samples)
        if not text.strip():
            return ""
        # enqueue 到 LLM，结果通过 result_queue 回传（带 segment id 去重）
        self._refiner.enqueue(text, samples)
        # 立即返回本地结果用于同步粘贴
        return text

    def stop(self) -> None:
        self._refiner.stop()
