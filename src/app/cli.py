"""VoiceIn 终端模式：说话即出字，实时显示在终端"""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from config import Config, load
from audio_capture import AudioCapture


# Default model location for streaming engine
STREAMING_DEFAULT = (Path.home() / ".voicein" / "models" / "zh-small-zipformer")


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="VoiceIn 终端模式")
    parser.add_argument("--cli", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--list-devices", action="store_true", help="列出麦克风设备")
    parser.add_argument("--device", type=int, default=None, help="设备 ID")
    parser.add_argument(
        "--engine", choices=["sensevoice", "streaming"], default="sensevoice",
        help="识别引擎（sensevoice=离线高精度，streaming=流式低延迟）",
    )
    parser.add_argument("--model-dir", type=str, default="", help="ASR 模型目录（streaming 引擎用）")
    parser.add_argument(
        "--threshold", type=float, default=None,
        help="VAD 能量阈值（默认 0.006，环境噪声大时调高）",
    )
    parser.add_argument("--newline", action="store_true", help="每句换行（默认同一行累积）")
    args = parser.parse_args()

    # --list-devices
    if args.list_devices:
        print("=== 输入设备 ===")
        for d in AudioCapture.list_devices():
            print(f"  [{d.id}] {d.name}")
        return

    cfg = load()
    if args.device is not None:
        cfg.device_id = args.device

    # Resolve device name for display
    device_name = "?"
    try:
        for d in AudioCapture.list_devices():
            if d.id == cfg.device_id:
                device_name = d.name
                break
    except Exception:
        pass

    print("🎤 VoiceIn 终端模式")
    print(f"   设备: [{cfg.device_id}] {device_name}")
    print(f"   引擎: {args.engine}")
    print("   按 Ctrl+C 退出")
    print()

    use_sensevoice = args.engine == "sensevoice"

    # --- Load recognizer + VAD ---
    print("加载模型...", end="", flush=True)
    try:
        if use_sensevoice:
            from recognizer import FunAsrRecognizer
            from vad import EnergyVad

            rec = FunAsrRecognizer(sample_rate=cfg.sample_rate)
            vad_kwargs = dict(block_ms=cfg.block_ms, sample_rate=cfg.sample_rate)
            if args.threshold is not None:
                vad_kwargs["threshold"] = args.threshold
            vad = EnergyVad(**vad_kwargs)
        else:
            from recognizer import Recognizer

            model_dir = args.model_dir or str(STREAMING_DEFAULT)
            rec = Recognizer(
                model_dir, cfg.sample_rate,
                enable_vad=True, vad_timeout_ms=cfg.vad_timeout_ms,
            )
            vad = None
    except Exception as e:
        print(f"\n模型加载失败: {e}")
        sys.exit(1)
    print(" OK")

    # --- Shared output state ---
    committed = ""      # accumulated finalized text
    last_line = ""      # last printed line (for overwrite padding)
    stop_event = threading.Event()

    def emit(text: str) -> None:
        """Print text (same-line overwrite or newline depending on flag)."""
        nonlocal committed, last_line
        committed += text
        if args.newline:
            print(f"  {text}")
            last_line = ""
        else:
            line = f"  {committed}"
            pad = max(0, len(last_line) - len(line))
            print(f"\r{line}{' ' * pad}", end="", flush=True)
            last_line = line

    # --- Audio callback ---
    if use_sensevoice:
        def on_audio(samples, sample_rate):
            if stop_event.is_set():
                return
            for seg in vad.feed(samples):
                text = rec.recognize(seg)
                if text.strip():
                    emit(text)
    else:
        stream = rec.create_stream()
        state = {"acc": 0, "can_decode": False}

        def on_audio(samples, sample_rate):
            nonlocal stream
            if stop_event.is_set():
                return
            rec.accept_waveform(stream, samples)
            state["acc"] += len(samples)
            if not state["can_decode"]:
                if state["acc"] < 16000:
                    return
                state["can_decode"] = True
            rec.decode(stream)
            text = rec.get_text(stream)
            if rec.is_endpoint(stream):
                if text.strip():
                    emit(text)
                rec.reset(stream)
                stream = rec.create_stream()
                state["acc"] = 0
                state["can_decode"] = False

    # --- Start recording ---
    audio = AudioCapture(
        cfg.device_id, cfg.sample_rate,
        channels=1, block_ms=cfg.block_ms,
    )
    audio.start(on_audio)

    print("🎤 正在听... (Ctrl+C 停止)")

    try:
        while not stop_event.wait(0.3):
            pass
    except KeyboardInterrupt:
        stop_event.set()

    # --- Stop + flush ---
    print("\n已停止")
    audio.stop()

    if use_sensevoice:
        for seg in vad.flush():
            text = rec.recognize(seg)
            if text.strip():
                emit(text)

    if not args.newline:
        print()  # final newline after the accumulated line
    audio.close()


if __name__ == "__main__":
    run_cli()
