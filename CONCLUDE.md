# VoiceIn 开发总结

## 项目概述

极简中文语音输入工具。Windows 系统托盘应用，全局热键触发录音，本地 Sherpa-ONNX 引擎流式识别，自动粘贴到光标处。

**技术栈：** Python 3.12 + C++ WASAPI + Sherpa-ONNX

---

## 项目结构

```
VoiceIn/
├── AGENT.md, PRODUCT_SENSE.md, DESIGN.md, FRONTEND.md, PLAN.md  # 工程文档
├── CONCLUDE.md                                                   # 本文件
├── src/
│   ├── native/                    # C++ WASAPI 音频采集 DLL
│   │   ├── audio_capture.h/cpp    # WASAPI Shared 模式，float32 采集
│   │   ├── ring_buffer.h          # 无锁 SPSC 环形缓冲区
│   │   ├── CMakeLists.txt
│   │   └── build/Release/audio_capture.dll
│   └── app/                       # Python 主程序
│       ├── main.py                # 入口
│       ├── orchestrator.py        # 状态机：IDLE → RECORDING → PASTING
│       ├── config.py              # JSON 配置 (~/.voicein/config.json)
│       ├── audio_capture.py       # C++ DLL 的 ctypes 封装
│       ├── recognizer.py          # Sherpa-ONNX 封装（transducer + zipformer2_ctc）
│       ├── hotkey.py              # Win32 RegisterHotKey 全局热键
│       ├── tray.py                # pystray 托盘图标
│       └── output.py              # 剪贴板备份 → 写入 → Ctrl+V → 恢复
└── models/                        # ASR 模型文件（外置，首次运行下载）
```

---

## 关键架构决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 音频采集 | C++ WASAPI Shared | 最低延迟，不独占设备 |
| 采样格式 | 16000Hz mono float32 | 模型要求 |
| 格式回退 | 设备不支持时自动用 mix format + 内部转换 | 兼容所有麦克风 |
| 本地 ASR | Sherpa-ONNX Zipformer Transducer | 中文优化，~55MB 模型 |
| 系统托盘 | pystray + Pillow 绘制图标 | 零外部文件依赖 |
| 全局热键 | ctypes → Win32 RegisterHotKey | 无第三方依赖 |
| 剪贴板 | ctypes → Win32 Clipboard API | 无第三方依赖，64 位兼容 |
| 首帧缓冲 | 积累 16000 样本（1 秒）后首次 decode | 模型 T=39 帧 + left_context 需求 |

## 四线程模型

1. **主线程** — pystray 消息循环
2. **热键线程** — GetMessageW 接收 WM_HOTKEY
3. **音频消费线程** — 从 queue 取数据 → 用户回调
4. **WASAPI 回调线程** — C++ 系统驱动 → 环形缓冲区

---

## 关键问题及解决方案

### 1. WASAPI 格式不兼容
- **现象：** `AUDCLNT_E_UNSUPPORTED_FORMAT`，设备不支持 16000Hz float32
- **解决：** 先尝试请求格式，失败则获取设备原生 mix format（如 48000Hz/2ch），在 C++ 层做重采样+通道合并

### 2. 64 位句柄溢出
- **现象：** `GlobalAlloc` 返回大指针导致 `OverflowError`
- **解决：** 显式设置 `ctypes` 的 `argtypes`/`restype` 为 `c_void_p` 等 64 位类型

### 3. 线程自 join 死锁
- **现象：** VAD 在 consumer 线程触发 `_stop()` → `audio.stop()` → `thread.join()` 自己
- **解决：** `join()` 前检查 `threading.current_thread()` 是否为 consumer 线程，是则跳过

### 4. 麦克风设备选错
- **现象：** 默认设备是 ToDesk Virtual Audio（无声），不是英特尔麦克风阵列
- **解决：** config 默认 `device_id=1`（英特尔智音技术），提供设备列表 API

### 5. 模型 chunk 崩溃
- **现象：** `features.cc:GetFrames:188 0 + 39 > 9`，100ms chunk 不够模型第一帧
- **解决：** orchestrator 积累 16000 样本（1 秒）后才首次调用 `decode()`，后续每 100ms 正常流式识别

### 6. 热键被占用
- **现象：** `RegisterHotKey failed: 1409`（Ctrl+Alt+S 已注册）
- **解决：** 启动时先 `UnregisterHotKey` 清除残留，注册失败时重试并提示

### 7. 模型测试陷阱
- **现象：** 用 440Hz 正弦波测试，模型始终无输出
- **原因：** Zipformer 模型只对真人语音特征输出文本，对合成信号不响应
- **教训：** ASR 模型测试必须用真实语音

---

## 运行方式

```bash
# 编译 DLL（首次）
cd src/native
cmake -B build -S .
cmake --build build --config Release

# 安装 Python 依赖
pip install sherpa-onnx pystray Pillow numpy

# 下载模型到 ~/.voicein/models/zh-small-zipformer/
# （tokens.txt + encoder.onnx + decoder.onnx + joiner.onnx）

# 运行
cd src/app && python main.py
```

**使用：**
1. 托盘出现灰色麦克风
2. 按 `Ctrl+Alt+S` → 图标变红 → 说中文
3. 再按 `Ctrl+Alt+S`（或静音 1.5s）→ 文字自动粘贴到光标处
4. 右键托盘 → 退出

---

## 模型信息

- **名称：** sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23
- **架构：** Zipformer Transducer（T=39, decode_chunk_len=32）
- **文件：** encoder.onnx (40MB) + decoder.onnx (7MB) + joiner.onnx (7MB) + tokens.txt (48KB)
- **推理：** CPU，~2 线程，内存 ~150MB

---

## v1 达成功能

- [x] C++ WASAPI 麦克风采集，自动格式适配
- [x] Sherpa-ONNX 本地中文流式识别
- [x] 系统托盘图标（空闲/录音 双状态）
- [x] 全局热键触发/停止录音
- [x] 自动粘贴到光标处（剪贴板备份恢复）
- [x] VAD 静音自动停止
- [x] JSON 配置文件

## v1 未做（有意）

- 云端 ASR、GUI 设置窗口、历史记录、多语言、自动更新、标点添加、开机自启
