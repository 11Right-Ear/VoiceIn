"""VoiceIn 桌面宠物 — 数据持久化"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

CONFIG_DIR = Path.home() / ".voicein"
POSITION_PATH = CONFIG_DIR / "pet_position.json"
STATS_PATH = CONFIG_DIR / "pet_stats.json"
CONFIG_PATH = CONFIG_DIR / "config.json"

_logger = logging.getLogger("pet_storage")


@dataclass
class PetStats:
    """宠物统计数据"""
    total_recordings: int = 0
    total_recording_time: float = 0.0
    total_usage_days: int = 0
    last_used: float = 0.0
    favorite_skin: str = "pixel_bird"


@dataclass
class PetPosition:
    """宠物位置信息"""
    x: int = 0
    y: int = 0
    skin_id: str = "pixel_bird"
    always_on_top: bool = True
    scale: float = 1.0


class PetStorage:
    """宠物数据持久化管理器

    线程安全：所有文件操作通过单一写队列串行化。
    配置变更支持回调通知。
    """

    def __init__(self, config_dir: str = "~/.voicein") -> None:
        self._config_dir = Path(config_dir).expanduser()
        self._position_path = self._config_dir / "pet_position.json"
        self._stats_path = self._config_dir / "pet_stats.json"
        self._config_path = self._config_dir / "config.json"

        self._write_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._write_thread = threading.Thread(target=self._write_worker, daemon=True)
        self._write_thread.start()

        self._config_callbacks: list[Callable[[str, Any], None]] = []
        self._config_lock = threading.RLock()
        self._loaded_config: dict[str, Any] = {}

        self._load_initial_config()

    def _load_initial_config(self) -> None:
        """启动时加载配置到内存，避免后续读操作竞争文件。"""
        with self._config_lock:
            self._loaded_config = self._read_json(self._config_path, {})

    # ── public: position ──────────────────────────────────────────────────────

    def load_position(self) -> PetPosition:
        """加载宠物位置信息。"""
        data = self._read_json(self._position_path, {})
        return PetPosition(
            x=data.get("x", 0),
            y=data.get("y", 0),
            skin_id=data.get("skin_id", "pixel_bird"),
            always_on_top=data.get("always_on_top", True),
            scale=data.get("scale", 1.0),
        )

    def save_position(self, position: PetPosition) -> None:
        """保存宠物位置信息（异步写入）。"""
        self._enqueue_write(
            "position",
            self._position_path,
            asdict(position),
        )

    # ── public: stats ─────────────────────────────────────────────────────────

    def load_stats(self) -> PetStats:
        """加载统计数据。"""
        data = self._read_json(self._stats_path, {})
        return PetStats(
            total_recordings=data.get("total_recordings", 0),
            total_recording_time=data.get("total_recording_time", 0.0),
            total_usage_days=data.get("total_usage_days", 0),
            last_used=data.get("last_used", 0.0),
            favorite_skin=data.get("favorite_skin", "pixel_bird"),
        )

    def save_stats(self, stats: PetStats) -> None:
        """保存统计数据（异步写入）。"""
        self._enqueue_write(
            "stats",
            self._stats_path,
            asdict(stats),
        )

    def update_stats(self, recording_time: float = 0.0, skin_id: str = "pixel_bird") -> None:
        """更新统计数据（录音次数+1，时长累加，使用天数更新）。"""
        stats = self.load_stats()
        stats.total_recordings += 1
        stats.total_recording_time += recording_time
        stats.last_used = time.time()

        current_day = int(stats.last_used / 86400)
        last_day = int(stats.last_used / 86400) if stats.last_used > 0 else 0
        if current_day > last_day:
            stats.total_usage_days += 1

        if skin_id:
            if stats.favorite_skin == "pixel_bird":
                stats.favorite_skin = skin_id
            else:
                stats.favorite_skin = skin_id

        self.save_stats(stats)

    # ── public: config ────────────────────────────────────────────────────────

    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置项（支持嵌套键，如 pet.skin_id）。"""
        with self._config_lock:
            if not self._loaded_config:
                self._loaded_config = self._read_json(self._config_path, {})
            keys = key.split(".")
            value = self._loaded_config
            for k in keys:
                if isinstance(value, dict):
                    value = value.get(k)
                else:
                    return default
                if value is None:
                    return default
            return value

    def set_config(self, key: str, value: Any) -> None:
        """设置配置项（支持嵌套键），自动触发回调。"""
        with self._config_lock:
            if not self._loaded_config:
                self._loaded_config = self._read_json(self._config_path, {})

            keys = key.split(".")
            target = self._loaded_config
            for k in keys[:-1]:
                if k not in target:
                    target[k] = {}
                target = target[k]
            old_value = target.get(keys[-1])
            target[keys[-1]] = value

            self._enqueue_write(
                "config",
                self._config_path,
                self._loaded_config,
            )

            for callback in self._config_callbacks:
                try:
                    callback(key, value)
                except Exception as e:
                    _logger.warning("Config callback error for key=%s: %s", key, e)

    def register_config_change_callback(self, callback: Callable[[str, Any], None]) -> None:
        """注册配置变化回调 (callback(key, value))。"""
        with self._config_lock:
            self._config_callbacks.append(callback)

    # ── public: lifecycle ─────────────────────────────────────────────────────

    def destroy(self) -> None:
        """关闭存储，确保所有待写入数据落盘。"""
        self._write_queue.put(None)
        if self._write_thread.is_alive():
            self._write_thread.join(timeout=5.0)
        _logger.info("PetStorage destroyed")

    # ── internal: write queue ─────────────────────────────────────────────────

    def _enqueue_write(self, tag: str, path: Path, data: dict[str, Any]) -> None:
        """将写操作加入队列。"""
        self._write_queue.put((tag, path, data))

    def _write_worker(self) -> None:
        """后台写线程，从队列取任务串行写文件。"""
        while True:
            item = self._write_queue.get()
            if item is None:
                break
            tag, path, data = item
            try:
                self._write_json(path, data)
                _logger.debug("PetStorage write complete: tag=%s", tag)
            except Exception as e:
                _logger.error("PetStorage write failed: tag=%s error=%s", tag, e)

    # ── internal: JSON file I/O ───────────────────────────────────────────────

    def _read_json(self, path: Path, default: dict[str, Any]) -> dict[str, Any]:
        """安全读取 JSON 文件，失败时返回默认值。"""
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                return json.loads(text) if text.strip() else default
        except Exception as e:
            _logger.warning("Failed to read %s: %s", path, e)
        return default

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        """原子写入 JSON 文件（先写临时文件再替换）。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            tmp.replace(path)
        except OSError:
            pass
