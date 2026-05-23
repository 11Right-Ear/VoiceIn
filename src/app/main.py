"""VoiceIn — 极简中文语音输入工具"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure local imports work regardless of how the script is invoked
_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from config import load
from hotkey import GlobalHotkey
from tray import TrayIcon
from orchestrator import Orchestrator


def main() -> None:
    cfg = load()

    orch: Orchestrator | None = None

    def _on_quit() -> None:
        nonlocal orch
        hotkey.stop()

    tray = TrayIcon(on_quit=_on_quit)
    hotkey = GlobalHotkey(
        modifiers=cfg.hotkey_modifiers,
        vk=cfg.hotkey_vk,
        callback=lambda: orch and orch.on_hotkey(),
    )
    orch = Orchestrator(cfg, tray)

    hotkey.start()
    tray.run()


if __name__ == "__main__":
    main()
