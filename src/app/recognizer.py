from __future__ import annotations

import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

import numpy as np
from sherpa_onnx import OnlineRecognizer as _SherpaOnline, OnlineStream


DEFAULT_MODEL_NAME = "zh-small-zipformer"
DEFAULT_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23.tar.bz2"
)
MODEL_FILES = ["tokens.txt", "model.onnx"]


def _check_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found. Download the model first."
        )


def _detect_model_type(model_dir: Path) -> str:
    has = lambda f: (model_dir / f).is_file()
    if has("encoder.onnx") and has("decoder.onnx") and has("joiner.onnx"):
        return "transducer"
    if has("model.onnx"):
        return "zipformer2_ctc"
    raise FileNotFoundError(
        f"Cannot detect model type in {model_dir}. "
        f"Expected: tokens.txt + (model.onnx | encoder.onnx+decoder.onnx+joiner.onnx)"
    )


def ensure_model(
    model_dir: Path | None = None,
    url: str = DEFAULT_MODEL_URL,
) -> Path:
    model_dir = Path(model_dir or (Path.home() / ".voicein" / "models" / DEFAULT_MODEL_NAME))
    model_dir.mkdir(parents=True, exist_ok=True)
    if all((model_dir / f).exists() for f in MODEL_FILES):
        return model_dir
    # Check transducer files too
    if (model_dir / "tokens.txt").exists() and (model_dir / "encoder.onnx").exists():
        return model_dir

    print(f"Model not found at {model_dir}")
    print(f"Downloading from: {url}")
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "model.tar.bz2"
        def _progress(n: int, bs: int, total: int) -> None:
            if total > 0 and n % 20 == 0:
                pct = min(100, n * bs * 100 // total)
                print(f"\r  {pct}%", end="", flush=True)
        try:
            urllib.request.urlretrieve(url, str(archive), _progress)
        except Exception as e:
            print(f"\nDownload failed: {e}")
            print(f"Please download manually from: {url}")
            print(f"Extract to: {model_dir}")
            sys.exit(1)
        print("\r  Extracting...")
        with tarfile.open(archive, "r:bz2") as tar:
            tar.extractall(model_dir)
        for item in model_dir.iterdir():
            if item.is_dir() and item.name.startswith("sherpa-onnx"):
                for sub in item.iterdir():
                    shutil.move(str(sub), str(model_dir / sub.name))
                shutil.rmtree(str(item))
                break
        print(f"  Done. Model at: {model_dir}")
    return model_dir


class Recognizer:
    """Streaming Chinese ASR via Sherpa-ONNX."""

    def __init__(
        self,
        model_dir: str | Path,
        sample_rate: int = 16000,
        enable_vad: bool = True,
        vad_timeout_ms: int = 1500,
        num_threads: int = 2,
    ) -> None:
        model_dir = Path(model_dir)
        _check_file(model_dir / "tokens.txt")
        model_type = _detect_model_type(model_dir)
        timeout_sec = vad_timeout_ms / 1000.0

        if model_type == "transducer":
            self._rec = _SherpaOnline.from_transducer(
                tokens=str(model_dir / "tokens.txt"),
                encoder=str(model_dir / "encoder.onnx"),
                decoder=str(model_dir / "decoder.onnx"),
                joiner=str(model_dir / "joiner.onnx"),
                sample_rate=sample_rate,
                num_threads=num_threads,
                model_type="",
                modeling_unit="cjkchar",
                snip_edges=True,
                enable_endpoint_detection=enable_vad,
                rule1_min_trailing_silence=timeout_sec,
                rule2_min_trailing_silence=timeout_sec * 0.6,
                rule3_min_utterance_length=0.5,
            )
        else:
            self._rec = _SherpaOnline.from_zipformer2_ctc(
                tokens=str(model_dir / "tokens.txt"),
                model=str(model_dir / "model.onnx"),
                sample_rate=sample_rate,
                num_threads=num_threads,
                snip_edges=True,
                enable_endpoint_detection=enable_vad,
                rule1_min_trailing_silence=timeout_sec,
                rule2_min_trailing_silence=timeout_sec * 0.6,
                rule3_min_utterance_length=0.5,
            )
        self._sample_rate = sample_rate

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def create_stream(self) -> OnlineStream:
        return self._rec.create_stream()

    def accept_waveform(self, stream: OnlineStream, samples: np.ndarray) -> None:
        stream.accept_waveform(self._sample_rate, samples)

    def decode(self, stream: OnlineStream) -> None:
        self._rec.decode_stream(stream)

    def get_text(self, stream: OnlineStream) -> str:
        return self._rec.get_result(stream)

    def is_endpoint(self, stream: OnlineStream) -> bool:
        return self._rec.is_endpoint(stream)

    def reset(self, stream: OnlineStream) -> None:
        self._rec.reset(stream)
