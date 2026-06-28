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
    device_id: int = 1          # Intel mic array (not ToDesk virtual)
    model_dir: str = ""
    engine: str = "sensevoice"  # sensevoice | streaming
    auto_enter: bool = False    # paste 后是否自动回车
    vad_threshold: float = 0.006  # EnergyVad 阈值，环境噪声大时调高
    vad_silence_ms: int = 1000   # EnergyVad 连续静音多久切段（毫秒）
    language: str = ""          # 识别语言；空 = 自动检测，也可指定 zh / en / ja / ko
    corrections: dict[str, str] = field(default_factory=dict)  # 纠错字典 {"APi": "API", "dome": "demo"}
    deny_words: list[str] = field(default_factory=list)        # 禁用词列表，输出中被过滤
    merge_short_segments: bool = True     # 是否合并短段（< N 字的不立刻粘贴，等下一段）
    merge_short_threshold: int = 3        # 少于多少字视为「短段」


def load() -> Config:
    if CONFIG_PATH.is_file():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return Config(
                hotkey_modifiers=data.get("hotkey_modifiers", 3),
                hotkey_vk=data.get("hotkey_vk", 0x53),
                sample_rate=data.get("sample_rate", 16000),
                block_ms=data.get("block_ms", 100),
                vad_timeout_ms=data.get("vad_timeout_ms", 1500),
                device_id=data.get("device_id", 1),
                model_dir=data.get("model_dir", ""),
                engine=data.get("engine", "sensevoice"),
                auto_enter=data.get("auto_enter", False),
                vad_threshold=data.get("vad_threshold", 0.006),
                vad_silence_ms=data.get("vad_silence_ms", 1000),
                language=data.get("language", ""),
                corrections=data.get("corrections", {}),
                deny_words=data.get("deny_words", []),
                merge_short_segments=data.get("merge_short_segments", True),
                merge_short_threshold=data.get("merge_short_threshold", 3),
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
                "engine": cfg.engine,
                "auto_enter": cfg.auto_enter,
                "vad_threshold": cfg.vad_threshold,
                "vad_silence_ms": cfg.vad_silence_ms,
                "language": cfg.language,
                "corrections": cfg.corrections,
                "deny_words": cfg.deny_words,
                "merge_short_segments": cfg.merge_short_segments,
                "merge_short_threshold": cfg.merge_short_threshold,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
