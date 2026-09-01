"""VoiceIn — 极简中文语音输入工具"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from config import load
from hotkey import GlobalHotkey
from pet_tray import PetTray
from pet_integration import create_integration, destroy_integration
from orchestrator import Orchestrator


def _log(msg: str) -> None:
    try:
        log_path = os.path.join(tempfile.gettempdir(), "voicein.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _alert(title: str, msg: str) -> None:
    import ctypes
    ctypes.windll.user32.MessageBoxW(0, msg, title, 0x30)


def main() -> None:
    cfg = load()
    _log(f"=== VoiceIn start, engine={cfg.engine} device={cfg.device_id} ===")

    orch: Orchestrator | None = None
    pet = None

    def _on_quit() -> None:
        nonlocal orch, pet
        hotkey.stop()
        if pet:
            pet.destroy()
        if orch:
            orch.stop()

    tray = PetTray(
        tip="VoiceIn — Ctrl+Alt+S 开始语音输入",
        on_left_click=lambda: orch and orch.on_hotkey(),
        on_quit=_on_quit,
    )

    hotkey = GlobalHotkey(
        modifiers=cfg.hotkey_modifiers,
        vk=cfg.hotkey_vk,
        callback=lambda: orch and orch.on_hotkey(),
    )

    # Synchronous load — show full traceback on failure
    try:
        orch = Orchestrator(cfg, tray)
    except Exception as e:
        detail = traceback.format_exc()
        _log(detail)
        _alert("VoiceIn 错误", f"模型加载失败:\n\n{e}\n\n完整日志:\n{tempfile.gettempdir()}\\voicein.log")
        return

    # Initialize pet integration after orchestrator is ready
    try:
        pet = create_integration(
            config=cfg.__dict__,
            hotkey_callback=lambda: orch.on_hotkey(),
        )
        pet.start()

        # Register pet state callback with orchestrator
        def _on_orch_state(state: str) -> None:
            if pet and pet.is_running:
                pet.on_orchestrator_state_changed(state)

        orch.register_state_callback(_on_orch_state)

        _log("pet integration started OK")
    except Exception as e:
        import traceback
        _log(f"pet integration failed: {e}\n{traceback.format_exc()}")
        pet = None

    _log("model loaded OK")
    hotkey.start()
    tray.run()


if __name__ == "__main__":
    main()
