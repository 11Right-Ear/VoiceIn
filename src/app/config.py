from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path.home() / ".voicein"
CONFIG_PATH = CONFIG_DIR / "config.json"


@dataclass
class Config:
    hotkey_modifiers: int = 3   # MOD_ALT(1) | MOD_CONTROL(2)
    hotkey_vk: int = 0x53       # S key
    sample_rate: int = 16000
    block_ms: int = 100
    vad_timeout_ms: int = 1500
    device_id: int = 1    # Intel mic array (not ToDesk virtual)
    model_dir: str = ""


def load() -> Config:
    if CONFIG_PATH.is_file():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return Config(
                hotkey_modifiers=data.get("hotkey_modifiers", 3),
                hotkey_vk=data.get("hotkey_vk", 0x56),
                sample_rate=data.get("sample_rate", 16000),
                block_ms=data.get("block_ms", 100),
                vad_timeout_ms=data.get("vad_timeout_ms", 1500),
                device_id=data.get("device_id", -1),
                model_dir=data.get("model_dir", ""),
            )
        except Exception:
            pass
    return Config()


def save(cfg: Config) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(
            {
                "hotkey_modifiers": cfg.hotkey_modifiers,
                "hotkey_vk": cfg.hotkey_vk,
                "sample_rate": cfg.sample_rate,
                "block_ms": cfg.block_ms,
                "vad_timeout_ms": cfg.vad_timeout_ms,
                "device_id": cfg.device_id,
                "model_dir": cfg.model_dir,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
