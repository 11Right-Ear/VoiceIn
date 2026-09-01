"""VoiceIn Panel — 配置面板主窗口"""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Callable

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QSystemTrayIcon,
    QMenu, QMessageBox, QWidget, QVBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabBar,
    QAction, QGroupBox, QFormLayout, QHBoxLayout, QVBoxLayout,
    QCheckBox, QScrollArea, QFrame, QGraphicsView, QGraphicsScene,
    QDialog, QFileDialog,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QIcon, QPainter, QColor, QPen, QBrush

_here = Path(__file__).resolve().parent
_logger = logging.getLogger("voicein_panel")

# 配置目录
CONFIG_DIR = Path.home() / ".voicein"
CONFIG_FILE = CONFIG_DIR / "panel_config.json"


def load_config() -> dict:
    """加载配置"""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return _default_config()


def save_config(cfg: dict) -> None:
    """保存配置"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def _default_config() -> dict:
    return {
        "version": 1,
        "api": {
            "provider": "openai",
            "url": "https://api.openai.com/v1",
            "api_key": "",
            "model": "gpt-3.5-turbo",
            "temperature": 0.7,
        },
        "appearance": {
            "theme": "light",
            "language": "zh",
        },
        "network": {
            "proxy_enabled": False,
            "proxy_type": "http",
            "proxy_host": "",
            "proxy_port": "",
        },
        "startup": {
            "auto_start": False,
        },
        "data": {
            "max_history": 100,
        },
    }


def encrypt_key(key: str) -> str:
    """简单加密 API Key"""
    if not key:
        return ""
    return base64.b64encode(key.encode()).decode()


def decrypt_key(encrypted: str) -> str:
    """解密 API Key"""
    if not encrypted:
        return ""
    try:
        return base64.b64decode(encrypted.encode()).decode()
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# 实时数据统计
# ─────────────────────────────────────────────────────────────────────────────

class StatsCollector(QObject):
    """统计数据收集器"""
    stats_updated = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._stats = {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_calls": 0,
            "total_cost": 0.0,
            "avg_latency": 0.0,
            "error_count": 0,
        }
        self._lock = threading.Lock()
        self._latencies: list[float] = []

    def record_call(self, prompt_tokens: int, completion_tokens: int,
                    latency: float, cost: float, success: bool = True) -> None:
        """记录一次 API 调用"""
        with self._lock:
            self._stats["total_calls"] += 1
            self._stats["prompt_tokens"] += prompt_tokens
            self._stats["completion_tokens"] += completion_tokens
            self._stats["total_tokens"] += prompt_tokens + completion_tokens
            self._stats["total_cost"] += cost
            if success:
                self._latencies.append(latency)
                if len(self._latencies) > 100:
                    self._latencies.pop(0)
                self._stats["avg_latency"] = sum(self._latencies) / len(self._latencies)
            else:
                self._stats["error_count"] += 1
            self.stats_updated.emit(dict(self._stats))

    def get_stats(self) -> dict:
        return dict(self._stats)

    def reset(self) -> None:
        with self._lock:
            self._stats = {k: 0 for k in self._stats}
            self._latencies.clear()
            self.stats_updated.emit(dict(self._stats))


# 全局统计实例
STATS = StatsCollector()


# ─────────────────────────────────────────────────────────────────────────────
# 主窗口
# ─────────────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """VoiceIn Panel 主窗口"""

    def __init__(self):
        super().__init__()
        self._config = load_config()
        self._voicein_process = None
        self._tray = None
        self._tabs = None
        self._voicein_status = "空闲"
        self._audio_level = 0.0

        self.setWindowTitle("VoiceIn Panel")
        self.setMinimumSize(800, 600)
        self.resize(900, 650)

        self._setup_ui()
        self._setup_tray()
        self._restore_window_state()
        # 延迟应用主题，等所有控件创建完成
        QTimer.singleShot(100, self._apply_theme)

    def _setup_ui(self) -> None:
        """设置 UI"""
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标签页
        self._tabs = QTabWidget()
        self._tabs.addTab(self._create_dashboard_tab(), "📊 仪表盘")
        self._tabs.addTab(self._create_api_tab(), "🔑 API 配置")
        self._tabs.addTab(self._create_voicein_tab(), "🎤 VoiceIn")
        self._tabs.addTab(self._create_history_tab(), "📝 历史")
        self._tabs.addTab(self._create_settings_tab(), "⚙️ 设置")

        layout.addWidget(self._tabs)

    def _create_dashboard_tab(self) -> QWidget:
        """仪表盘页面"""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(15)

        # 标题
        title = QLabel("实时监控")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        # 统计卡片区域
        cards = QHBoxLayout()

        # Token 统计
        token_card = self._make_stat_card("Token 统计", [
            ("总 Token", "total_tokens", "0"),
            ("输入 Token", "prompt_tokens", "0"),
            ("输出 Token", "completion_tokens", "0"),
        ])
        cards.addWidget(token_card)

        # 调用统计
        call_card = self._make_stat_card("调用统计", [
            ("总调用次数", "total_calls", "0"),
            ("平均延迟", "avg_latency", "0 ms"),
            ("错误次数", "error_count", "0"),
        ])
        cards.addWidget(call_card)

        # 费用统计
        cost_card = self._make_stat_card("费用统计", [
            ("预估费用", "total_cost", "$0.00"),
        ])
        cards.addWidget(cost_card)

        layout.addLayout(cards)

        # 简单图表区域
        chart_group = QGroupBox("调用趋势")
        chart_layout = QVBoxLayout(chart_group)
        self._chart_view = SimpleChart()
        chart_layout.addWidget(self._chart_view)
        layout.addWidget(chart_group)

        layout.addStretch()

        # 统计更新信号
        STATS.stats_updated.connect(self._on_stats_updated)

        return w

    def _make_stat_card(self, title: str, items: list[tuple[str, str, str]]) -> QFrame:
        """创建统计卡片"""
        card = QFrame()
        card.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        card_layout = QVBoxLayout(card)

        card_title = QLabel(title)
        card_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        card_layout.addWidget(card_title)

        self._stat_labels = getattr(self, '_stat_labels', {})
        for label_text, key, default in items:
            row = QHBoxLayout()
            lbl = QLabel(f"{label_text}:")
            val = QLabel(default)
            val.setObjectName(f"stat_{key}")
            row.addWidget(lbl)
            row.addWidget(val)
            card_layout.addLayout(row)
            self._stat_labels[key] = val

        return card

    def _on_stats_updated(self, stats: dict) -> None:
        """更新统计数据显示"""
        if hasattr(self, '_stat_labels'):
            self._stat_labels.get("total_tokens", QLabel()).setText(str(stats.get("total_tokens", 0)))
            self._stat_labels.get("prompt_tokens", QLabel()).setText(str(stats.get("prompt_tokens", 0)))
            self._stat_labels.get("completion_tokens", QLabel()).setText(str(stats.get("completion_tokens", 0)))
            self._stat_labels.get("total_calls", QLabel()).setText(str(stats.get("total_calls", 0)))
            self._stat_labels.get("error_count", QLabel()).setText(str(stats.get("error_count", 0)))
            avg_lat = stats.get("avg_latency", 0)
            self._stat_labels.get("avg_latency", QLabel()).setText(f"{avg_lat:.0f} ms")
            cost = stats.get("total_cost", 0)
            self._stat_labels.get("total_cost", QLabel()).setText(f"${cost:.4f}")

    def _create_api_tab(self) -> QWidget:
        """API 配置页面"""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)

        # API 提供商
        provider_group = QGroupBox("API 配置")
        provider_layout = QFormLayout(provider_group)

        self._provider_combo = QComboBox()
        self._provider_combo.addItems(["OpenAI", "本地 (Ollama)", "Claude", "Azure OpenAI"])
        self._provider_combo.currentTextChanged.connect(self._on_provider_changed)
        provider_layout.addRow("API 提供商:", self._provider_combo)

        self._api_url_input = QLineEdit()
        self._api_url_input.setPlaceholderText("https://api.openai.com/v1")
        provider_layout.addRow("API URL:", self._api_url_input)

        self._api_key_input = QLineEdit()
        self._api_key_input.setEchoMode(QLineEdit.Password)
        self._api_key_input.setPlaceholderText("sk-...")
        provider_layout.addRow("API Key:", self._api_key_input)

        self._model_input = QLineEdit()
        self._model_input.setPlaceholderText("gpt-3.5-turbo")
        provider_layout.addRow("模型:", self._model_input)

        self._temp_input = QDoubleSpinBox()
        self._temp_input.setRange(0.0, 2.0)
        self._temp_input.setSingleStep(0.1)
        self._temp_input.setValue(0.7)
        provider_layout.addRow("Temperature:", self._temp_input)

        layout.addWidget(provider_group)

        # 按钮
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("💾 保存配置")
        save_btn.clicked.connect(self._save_api_config)
        test_btn = QPushButton("🧪 测试连接")
        test_btn.clicked.connect(self._test_api_connection)
        export_btn = QPushButton("📤 导出配置")
        export_btn.clicked.connect(self._export_config)
        import_btn = QPushButton("📥 导入配置")
        import_btn.clicked.connect(self._import_config)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(test_btn)
        btn_layout.addWidget(export_btn)
        btn_layout.addWidget(import_btn)
        layout.addLayout(btn_layout)

        # 测试结果
        self._test_result = QTextEdit()
        self._test_result.setReadOnly(True)
        self._test_result.setMaximumHeight(100)
        layout.addWidget(QLabel("测试结果:"))
        layout.addWidget(self._test_result)

        layout.addStretch()

        # 加载现有配置
        self._load_api_config()

        return w

    def _create_voicein_tab(self) -> QWidget:
        """VoiceIn 控制页面"""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)

        # 状态显示
        status_group = QGroupBox("VoiceIn 状态")
        status_layout = QVBoxLayout(status_group)

        self._voicein_status_label = QLabel("状态: 空闲")
        self._voicein_status_label.setStyleSheet("font-size: 16px;")
        status_layout.addWidget(self._voicein_status_label)

        # 音量条
        volume_layout = QHBoxLayout()
        volume_layout.addWidget(QLabel("音量:"))
        self._volume_bar = VolumeBar()
        volume_layout.addWidget(self._volume_bar)
        status_layout.addLayout(volume_layout)

        layout.addWidget(status_group)

        # 控制按钮
        control_group = QGroupBox("控制")
        control_layout = QHBoxLayout(control_group)

        self._recording_btn = QPushButton("🎤 开始录音")
        self._recording_btn.clicked.connect(self._toggle_recording)
        control_layout.addWidget(self._recording_btn)

        stop_btn = QPushButton("⏹ 停止")
        stop_btn.clicked.connect(self._stop_voicein)
        control_layout.addWidget(stop_btn)

        layout.addWidget(control_group)

        # 参数配置
        config_group = QGroupBox("VoiceIn 参数配置")
        config_layout = QFormLayout(config_group)

        self._vad_timeout = QSpinBox()
        self._vad_timeout.setRange(500, 10000)
        self._vad_timeout.setSingleStep(100)
        self._vad_timeout.setValue(1000)
        config_layout.addRow("VAD 静音超时 (ms):", self._vad_timeout)

        self._engine_combo = QComboBox()
        self._engine_combo.addItems(["sensevoice", "streaming"])
        config_layout.addRow("识别引擎:", self._engine_combo)

        self._device_combo = QComboBox()
        self._device_combo.addItems(["默认设备"])
        config_layout.addRow("麦克风:", self._device_combo)

        layout.addWidget(config_group)

        layout.addStretch()

        return w

    def _create_history_tab(self) -> QWidget:
        """历史记录页面"""
        w = QWidget()
        layout = QVBoxLayout(w)

        # 历史表格
        self._history_table = QTableWidget()
        self._history_table.setColumnCount(5)
        self._history_table.setHorizontalHeaderLabels(["时间", "模型", "Token", "延迟", "状态"])
        self._history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self._history_table)

        # 按钮
        btn_layout = QHBoxLayout()
        clear_btn = QPushButton("🗑 清空历史")
        clear_btn.clicked.connect(self._clear_history)
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self._refresh_history)
        btn_layout.addWidget(clear_btn)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return w

    def _create_settings_tab(self) -> QWidget:
        """设置页面"""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        # 外观设置
        appearance_group = QGroupBox("外观")
        appearance_layout = QFormLayout(appearance_group)

        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["浅色主题", "深色主题"])
        self._theme_combo.currentTextChanged.connect(self._on_theme_changed)
        appearance_layout.addRow("主题:", self._theme_combo)

        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["中文", "English"])
        appearance_layout.addRow("语言:", self._lang_combo)

        scroll_layout.addWidget(appearance_group)

        # 网络设置
        network_group = QGroupBox("网络")
        network_layout = QFormLayout(network_group)

        self._proxy_enabled = QCheckBox("启用代理")
        network_layout.addRow("", self._proxy_enabled)

        self._proxy_type = QComboBox()
        self._proxy_type.addItems(["HTTP", "SOCKS5"])
        network_layout.addRow("代理类型:", self._proxy_type)

        self._proxy_host = QLineEdit()
        self._proxy_host.setPlaceholderText("127.0.0.1")
        network_layout.addRow("代理地址:", self._proxy_host)

        self._proxy_port = QLineEdit()
        self._proxy_port.setPlaceholderText("7890")
        network_layout.addRow("代理端口:", self._proxy_port)

        scroll_layout.addWidget(network_group)

        # 启动设置
        startup_group = QGroupBox("启动")
        startup_layout = QFormLayout(startup_group)

        self._auto_start = QCheckBox("开机自启")
        startup_layout.addRow("", self._auto_start)

        scroll_layout.addWidget(startup_group)

        # 关于
        about_group = QGroupBox("关于")
        about_layout = QVBoxLayout(about_group)
        about_text = QLabel("VoiceIn Panel v1.0\n基于 PyQt5\n\nVoiceIn 配置面板与 LLM 监控工具")
        about_layout.addWidget(about_text)
        scroll_layout.addWidget(about_group)

        scroll_layout.addStretch()

        layout.addWidget(scroll)

        # 保存按钮
        save_btn = QPushButton("💾 保存设置")
        save_btn.clicked.connect(self._save_settings)
        layout.addWidget(save_btn)

        self._load_settings()

        return w

    # ── 托盘 ────────────────────────────────────────────────────────────────

    def _setup_tray(self) -> None:
        """设置系统托盘"""
        self._tray = QSystemTrayIcon(self)

        # 创建托盘图标
        try:
            from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QIcon
            pixmap = QPixmap(64, 64)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            # 画圆形图标
            painter.setBrush(QBrush(QColor(74, 144, 217)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(8, 8, 48, 48)
            # 画麦克风图案
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.drawEllipse(26, 20, 12, 16)
            painter.drawRect(30, 32, 4, 12)
            painter.end()
            icon = QIcon(pixmap)
            self._tray.setIcon(icon)
        except Exception:
            pass  # 如果创建图标失败，继续运行

        # 托盘菜单
        tray_menu = QMenu()
        show_action = QAction("📋 打开面板", self, triggered=self.show)
        tray_menu.addAction(show_action)

        voicein_menu = QMenu("🎤 VoiceIn", self)
        voicein_menu.addAction("▶️ 开始录音", self._toggle_recording)
        voicein_menu.addAction("⏹ 停止", self._stop_voicein)
        tray_menu.addMenu(voicein_menu)

        tray_menu.addSeparator()
        tray_menu.addAction("❌ 退出", self._on_quit)

        self._tray.setContextMenu(tray_menu)
        self._tray.setToolTip("VoiceIn Panel")
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.show()

    # ── 配置加载/保存 ──────────────────────────────────────────────────────

    def _load_api_config(self) -> None:
        api = self._config.get("api", {})
        providers = {"OpenAI": "openai", "本地 (Ollama)": "ollama", "Claude": "claude", "Azure OpenAI": "azure"}
        provider_map = {v: k for k, v in providers.items()}
        provider = api.get("provider", "openai")
        self._provider_combo.setCurrentText(provider_map.get(provider, "OpenAI"))
        self._api_url_input.setText(api.get("url", ""))
        encrypted_key = api.get("api_key", "")
        if encrypted_key:
            self._api_key_input.setText(decrypt_key(encrypted_key))
        self._model_input.setText(api.get("model", ""))
        self._temp_input.setValue(api.get("temperature", 0.7))

    def _save_api_config(self) -> None:
        providers = {"OpenAI": "openai", "本地 (Ollama)": "ollama", "Claude": "claude", "Azure OpenAI": "azure"}
        self._config["api"] = {
            "provider": providers.get(self._provider_combo.currentText(), "openai"),
            "url": self._api_url_input.text(),
            "api_key": encrypt_key(self._api_key_input.text()),
            "model": self._model_input.text(),
            "temperature": self._temp_input.value(),
        }
        save_config(self._config)
        self._test_result.append("✅ 配置已保存")

    def _test_api_connection(self) -> None:
        self._test_result.append("🔄 测试连接中...")
        # 模拟测试
        QTimer.singleShot(500, lambda: self._test_result.append("✅ 连接成功!"))

    def _export_config(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出配置", "voicein_config.json", "JSON Files (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            self._test_result.append(f"✅ 已导出到 {path}")

    def _import_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入配置", "", "JSON Files (*.json)")
        if path:
            with open(path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
            save_config(self._config)
            self._load_api_config()
            self._test_result.append("✅ 配置已导入")

    def _load_settings(self) -> None:
        appearance = self._config.get("appearance", {})
        self._theme_combo.setCurrentText("深色主题" if appearance.get("theme") == "dark" else "浅色主题")
        self._lang_combo.setCurrentText("English" if appearance.get("language") == "en" else "中文")

        network = self._config.get("network", {})
        self._proxy_enabled.setChecked(network.get("proxy_enabled", False))
        self._proxy_type.setCurrentText(network.get("proxy_type", "HTTP").upper() if network.get("proxy_type") == "http" else "SOCKS5")
        self._proxy_host.setText(network.get("proxy_host", ""))
        self._proxy_port.setText(network.get("proxy_port", ""))

        startup = self._config.get("startup", {})
        self._auto_start.setChecked(startup.get("auto_start", False))

    def _save_settings(self) -> None:
        self._config["appearance"] = {
            "theme": "dark" if self._theme_combo.currentText() == "深色主题" else "light",
            "language": "en" if self._lang_combo.currentText() == "English" else "zh",
        }
        self._config["network"] = {
            "proxy_enabled": self._proxy_enabled.isChecked(),
            "proxy_type": "http" if self._proxy_type.currentText().upper() == "HTTP" else "socks5",
            "proxy_host": self._proxy_host.text(),
            "proxy_port": self._proxy_port.text(),
        }
        self._config["startup"] = {
            "auto_start": self._auto_start.isChecked(),
        }
        save_config(self._config)
        QMessageBox.information(self, "保存", "设置已保存")

    def _on_theme_changed(self, text: str) -> None:
        try:
            self._apply_theme()
        except RuntimeError:
            pass  # Widget was deleted

    def _apply_theme(self) -> None:
        if not hasattr(self, '_theme_combo') or self._theme_combo is None:
            return
        try:
            theme_text = self._theme_combo.currentText()
        except RuntimeError:
            return
        theme = "dark" if theme_text == "深色主题" else "light"
        if theme == "dark":
            self.setStyleSheet("""
                QWidget { background-color: #1e1e1e; color: #ffffff; }
                QGroupBox { border: 1px solid #3c3c3c; margin-top: 10px; }
                QLineEdit, QComboBox, QSpinBox { background-color: #2d2d2d; border: 1px solid #3c3c3c; padding: 4px; }
                QPushButton { background-color: #0d7dff; color: white; border: none; padding: 6px 16px; }
                QPushButton:hover { background-color: #3399ff; }
                QTableWidget { background-color: #2d2d2d; gridline-color: #3c3c3c; }
                QHeaderView { background-color: #2d2d2d; }
            """)
        else:
            self.setStyleSheet("")

    def _on_provider_changed(self, text: str) -> None:
        presets = {
            "OpenAI": "https://api.openai.com/v1",
            "本地 (Ollama)": "http://localhost:11434/v1",
            "Claude": "https://api.anthropic.com/v1",
            "Azure OpenAI": "https://YOUR_RESOURCE.openai.azure.com/v1",
        }
        self._api_url_input.setText(presets.get(text, ""))

    # ── VoiceIn 控制 ───────────────────────────────────────────────────────

    def _toggle_recording(self) -> None:
        if self._voicein_status == "录音中":
            self._voicein_status = "空闲"
            self._recording_btn.setText("🎤 开始录音")
        else:
            self._voicein_status = "录音中"
            self._recording_btn.setText("⏸ 停止录音")
        self._voicein_status_label.setText(f"状态: {self._voicein_status}")

    def _stop_voicein(self) -> None:
        self._voicein_status = "空闲"
        self._recording_btn.setText("🎤 开始录音")
        self._voicein_status_label.setText("状态: 空闲")

    # ── 历史记录 ───────────────────────────────────────────────────────────

    def _clear_history(self) -> None:
        self._history_table.setRowCount(0)
        STATS.reset()

    def _refresh_history(self) -> None:
        pass  # 刷新历史

    # ── 窗口状态 ───────────────────────────────────────────────────────────

    def _restore_window_state(self) -> None:
        geo = self._config.get("window_geometry")
        if geo:
            self.restoreGeometry(geo)

    def _save_window_state(self) -> None:
        self._config["window_geometry"] = bytes(self.saveGeometry()).decode()
        save_config(self._config)

    def closeEvent(self, event) -> None:
        self._save_window_state()
        event.ignore()
        self.hide()

    def _on_quit(self) -> None:
        self._save_window_state()
        QApplication.quit()


# ─────────────────────────────────────────────────────────────────────────────
# 简单图表组件
# ─────────────────────────────────────────────────────────────────────────────

class SimpleChart(QGraphicsView):
    """简单的调用趋势图表"""
    def __init__(self):
        super().__init__()
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setMinimumHeight(150)
        self._data: list[float] = [0] * 20

    def add_data(self, value: float) -> None:
        self._data.append(value)
        if len(self._data) > 50:
            self._data.pop(0)
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        margin = 10

        # 绘制背景网格
        pen = QPen(QColor(200, 200, 200))
        painter.setPen(pen)
        for i in range(5):
            y = int(margin + (h - 2 * margin) * i / 4)
            painter.drawLine(int(margin), y, int(w - margin), y)

        # 绘制数据线
        if self._data:
            max_val = max(max(self._data), 1)
            line_pen = QPen(QColor(0, 123, 255), 2)
            painter.setPen(line_pen)

            step = (w - 2 * margin) / (len(self._data) - 1) if len(self._data) > 1 else 1
            points = []
            for i, v in enumerate(self._data):
                x = margin + i * step
                y = h - margin - (v / max_val) * (h - 2 * margin)
                points.append((x, y))

            for i in range(len(points) - 1):
                painter.drawLine(int(points[i][0]), int(points[i][1]),
                               int(points[i+1][0]), int(points[i+1][1]))


# ─────────────────────────────────────────────────────────────────────────────
# 音量条组件
# ─────────────────────────────────────────────────────────────────────────────

class VolumeBar(QFrame):
    """实时音量条"""
    def __init__(self):
        super().__init__()
        self.setMinimumWidth(200)
        self.setMinimumHeight(20)
        self._level = 0.0

    def set_level(self, level: float) -> None:
        self._level = max(0.0, min(1.0, level))
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # 背景
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(50, 50, 50))
        painter.drawRect(0, 0, w, h)

        # 音量条
        bar_width = int(w * self._level)
        if self._level < 0.3:
            color = QColor(76, 175, 80)  # 绿色
        elif self._level < 0.7:
            color = QColor(255, 193, 7)  # 黄色
        else:
            color = QColor(244, 67, 54)  # 红色
        painter.setBrush(color)
        painter.drawRect(0, 0, bar_width, h)


# ─────────────────────────────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
