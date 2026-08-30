# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本代码仓库中工作时提供指导。

## 项目概述

**VoiceIn** — 极简中英文语音输入工具，运行于 Windows 系统托盘。按下全局热键录音，语音在本地识别后直接粘贴到光标位置。纯离线运行。

**核心原则：极简优先。任何新增复杂度必须带来 10 倍用户价值。**

---

## 构建与运行命令

```bash
# 编译 C++ WASAPI 音频采集 DLL
cmake -B src/native/build -S src/native
cmake --build src/native/build --config Release

# 安装 Python 依赖
pip install -r requirements.txt

# 开发模式运行
python src/app/main.py

# CLI 模式运行（无托盘，终端输出）
python -m src.app.cli

# 列出可用麦克风
python -m src.app.cli --list-devices

# PyInstaller 打包
pyinstaller VoiceIn.spec

# 清理构建产物
rm -rf src/native/build dist
```

---

## 架构

### 线程模型（4 线程，固定不变）

1. **主线程** — pystray/tkinter 消息循环（阻塞在 `Icon.run()`）
2. **热键线程** — `RegisterHotKey` + `GetMessageW` 循环；通过回调触发热键事件
3. **音频消费线程** — 从 `queue.Queue` 取数据，调用用户回调
4. **WASAPI 回调线程** — C++ 系统线程，写入环形缓冲区

跨线程通信只使用 `queue.Queue`，不用原始锁或 Condition。

### 状态机

```
IDLE ↔ RECORDING
```

状态转换只由 `orchestrator.py` 触发，其他模块不感知全局状态。

### 组件职责

| 文件 | 职责 |
|------|------|
| `main.py` | 入口 — 加载配置，启动热键 + 托盘 + orchestrator |
| `orchestrator.py` | 状态机，协调音频/VAD/识别/粘贴 |
| `audio_capture.py` | C++ WASAPI DLL 的 ctypes 封装 |
| `recognizer.py` | ASR 引擎：`FunAsrRecognizer`（FunASR+SenseVoice，PyTorch）和 `Recognizer`/`SenseVoiceRecognizer`（sherpa-onnx 流式） |
| `vad.py` | `EnergyVad`（RMS 阈值）和 `VadSegmenter`（Silero VAD） |
| `hotkey.py` | `GlobalHotkey`，Win32 `RegisterHotKey` 实现 |
| `tray.py` | pystray 图标，动态绘制麦克风图标（灰色=空闲，红色=录音中） |
| `output.py` | 剪贴板备份 → 写入文字 → `Ctrl+V` → 恢复剪贴板 |
| `config.py` | 将 `~/.voicein/config.json` 加载为 `Config` 数据类 |
| `cli.py` | CLI 模式入口（无托盘，终端输出） |

### 语音识别引擎

通过配置项 `engine` 选择：
- `"sensevoice"`（默认）— FunASR + SenseVoiceSmall（PyTorch），离线逐段识别
- `"streaming"` — sherpa-onnx `OnlineRecognizer`，持续累积音频，停止后识别

### 语音识别后处理流水线（每段）

1. `rich_transcription_postprocess` — ITN 文字正常化
2. `remove_fillers` — 过滤语气词（嗯/呃/唔）
3. `apply_corrections` — 用户纠错字典 + 禁用词过滤
4. 短段合并 — 少于 `merge_short_threshold` 字的段缓存，与下一段合并后重新识别

### Native 组件

```
src/native/
├── CMakeLists.txt
├── audio_capture.h
├── audio_capture.cpp      # WASAPI 采集 + 环形缓冲区
└── ring_buffer.h          # SPSC 无锁环形缓冲区
```

### 测试

`src/app/` 下有独立的测试模块（直接用 Python 运行）：

```bash
python src/app/test_rec.py          # 麦克风录音测试
python src/app/test_recognizer.py   # ASR 引擎测试
python src/app/test_capture.py      # WASAPI DLL 封装测试
python src/app/test_hotkey_tray.py  # 热键 + 托盘集成测试
python src/app/test_mic.py          # 列出麦克风设备
```

---

## 代码规范

### Python

- 所有公开函数完整类型注解
- `snake_case` 命名函数/变量，`PascalCase` 命名类
- 不加 docstring（类名 + 类型已足够自文档化）
- 跨线程通信用 `logging`，不用 `print`
- 只在系统边界处理错误（文件 I/O、网络、DLL 调用）

### C++

- `extern "C"` 导出供 ctypes 调用
- 固定大小结构体（跨 DLL 边界不用 STL）
- `snake_case` 命名函数，`PascalCase` 命名类型
- 返回码，不跨 DLL 边界抛异常
- 目标：Release `/MT` 静态 CRT

---

## 配置

- 路径：`~/.voicein/config.json`
- 运行时只读
- 带版本号（`"version": 1`）
- 无 UI，直接编辑 JSON

关键默认值：

| 键 | 默认值 | 含义 |
|-----|--------|------|
| `hotkey_modifiers` | `3` | Alt+Ctrl |
| `hotkey_vk` | `0x53` (S) | 热键为 Alt+Ctrl+S |
| `device_id` | `1` | 第二个采集设备（规避 ToDesk 虚拟设备） |
| `engine` | `"sensevoice"` | FunASR 后端 |
| `vad_silence_ms` | `1000` | 静音多久切段（毫秒） |
| `merge_short_segments` | `true` | 短段与下一段合并 |

---

## v1 硬约束

1. **新增第三方依赖必须先更新 PLAN.md**
2. **无弹窗**（About 除外）— 反馈仅通过托盘图标和通知气泡
3. **不存储用户数据** — 不录音、不保存识别历史、不写日志
4. **安装包 < 50MB**（不含模型文件）
5. **运行时内存 < 200MB**
6. **不修改 `~/.voicein/` 外的任何文件**

---

## 重要提示

- 模型首次运行自动下载 — `FunAsrRecognizer` 从 ModelScope（`iic/SenseVoiceSmall`）拉取。sherpa-onnx 模型需手动放入 `~/.voicein/models/`
- 图标在运行时通过 Pillow 的 `ImageDraw` 生成（无 `.ico` 文件）
- 模型加载前清除 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量，避免 modelscope.cn 下载失败
- RTF ≈ 0.06 — SenseVoice 在 CPU 上以 0.06x 实时比运行（每 1 秒音频约需 60ms）
