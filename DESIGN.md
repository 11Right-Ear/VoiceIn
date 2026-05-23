# DESIGN.md — 架构设计文档

## 总览

```
┌──────────────────────────────────────────────────────┐
│                     VoiceIn.exe                       │
│                                                       │
│  ┌─────────────┐   ┌─────────────┐   ┌────────────┐ │
│  │  tray.py     │   │  hotkey.py  │   │ config.py  │ │
│  │  pystray     │   │  ctypes →   │   │ JSON 配置   │ │
│  │  托盘图标    │   │  Win32 API  │   │ 管理       │ │
│  └──────┬───────┘   └──────┬──────┘   └────────────┘ │
│         │                  │                           │
│         └────────┬─────────┘                          │
│                  ▼                                     │
│  ┌──────────────────────────────────┐                  │
│  │       orchestrator.py            │                  │
│  │       主流程状态机                │                  │
│  │   空闲 ⇄ 录音中 ⇄ 识别中         │                  │
│  └──────┬────────────────┬──────────┘                  │
│         │                │                             │
│         ▼                ▼                             │
│  ┌─────────────┐  ┌─────────────┐                     │
│  │ audio.dll   │  │recognizer.py│                     │
│  │ (C++ WASAPI)│  │sherpa-onnx  │                     │
│  │ 麦克风采集   │  │ 流式识别     │                     │
│  └─────────────┘  └──────┬──────┘                     │
│                          │                             │
│                          ▼                             │
│                   ┌─────────────┐                     │
│                   │ output.py    │                     │
│                   │ 剪贴板+粘贴  │                     │
│                   └─────────────┘                     │
└──────────────────────────────────────────────────────┘
```

---

## 一、C++ 层：WASAPI 音频采集 DLL

### 1.1 接口定义

```c
// audio_capture.h

#ifdef AUDIO_CAPTURE_EXPORTS
#define AUDIO_API __declspec(dllexport)
#else
#define AUDIO_API __declspec(dllimport)
#endif

// 音频回调函数类型
// samples: 交错的 float32 PCM 数据 [-1.0, 1.0]
// n_samples: 采样点数 (帧数 × 通道数)
typedef void (*audio_callback_t)(const float *samples, int n_samples, int sample_rate);

// 设备信息
typedef struct {
    wchar_t name[256];
    int id;           // 内部设备 ID
    int max_channels;
    int default_sample_rate;
} audio_device_info_t;

// 返回可用音频输入设备数量
// 调用 audio_free_device_list 释放
AUDIO_API int audio_list_devices(audio_device_info_t **devices);

AUDIO_API void audio_free_device_list(audio_device_info_t *devices);

// 初始化指定设备
// device_id: -1 表示系统默认设备
// sample_rate: 16000 (Sherpa-ONNX 推荐)
// channels: 1 (单声道)
// block_ms: 回调间隔（毫秒），建议 100
// 返回 0 成功，非 0 错误码
AUDIO_API int audio_init(int device_id, int sample_rate, int channels, int block_ms);

// 开始采集，音频数据通过回调返回
// 回调在独立的 WASAPI 线程中调用
AUDIO_API int audio_start(audio_callback_t callback);

// 停止采集，阻塞直到完全停止
AUDIO_API int audio_stop(void);

// 释放资源
AUDIO_API void audio_close(void);

// 获取错误信息
AUDIO_API const wchar_t *audio_last_error(void);
```

### 1.2 设计要点

| 项目 | 选择 | 理由 |
|------|------|------|
| 采样率 | 16000 Hz | Sherpa-ONNX 中文模型要求 |
| 位深 | float32 | 直接对接 Sherpa-ONNX，无需转换 |
| 通道 | 1 (单声道) | ASR 不需要立体声 |
| 回调间隔 | 100ms | 平衡延迟与 CPU 开销 |
| API 层 | WASAPI Shared 模式 | 与系统混音器兼容，不独占设备 |
| 线程模型 | WASAPI 驱动回调线程 → 推入环形缓冲区 | 避免 Python GIL 在音频线程内被阻塞 |

### 1.3 环形缓冲区设计

```
           WASAPI 回调线程 (C++)
                    │
                    ▼
    ┌───────────────────────────────┐
    │       RingBuffer (lock-free)  │
    │   ┌───┬───┬───┬───┬───┬───┐  │
    │   │   │   │   │   │   │   │  │
    │   └───┴───┴───┴───┴───┴───┘  │
    │   write_head          read_head
    └───────────────┬───────────────┘
                    │
                    ▼
    Python 读取线程 (定时 poll, 100ms)
                    │
                    ▼
            Sherpa-ONNX 识别器
```

- 无锁 SPSC (Single Producer Single Consumer) 环形缓冲区
- WASAPI 回调线程写入，Python 读取线程读取
- 缓冲区大小：3 秒音频 = 16000 × 3 × 4 bytes = 192KB
- 溢出策略：覆盖最老数据（丢弃旧音频，记录警告）

---

## 二、Python 层：模块设计

### 2.1 模块职责

#### `config.py` — 配置管理

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Config:
    hotkey_modifiers: int  # MOD_CONTROL | MOD_SHIFT
    hotkey_vk: int         # 0x56 即 V
    sample_rate: int       # 16000
    block_ms: int          # 100
    vad_timeout_ms: int    # 1500 静音超时，0=手动停止
    model_name: str        # "sherpa-onnx-zh-small"
    device_id: int         # -1=默认
    cloud_api_enabled: bool  # v1.2
    cloud_api_key: str       # v1.2

ConfigPath = Path.home() / ".voicein" / "config.json"
```

- 配置以 JSON 文件存放在 `~/.voicein/config.json`
- 启动时加载，不存在则创建默认值
- 只读，运行时不可修改（v1 无配置 UI）

#### `audio_capture.py` — C++ DLL 的 Python 封装

```python
# 职责：加载 DLL，封装 ctypes 调用，暴露 AudioCapture 类
class AudioCapture:
    def __init__(self, device_id: int, sample_rate: int, channels: int, block_ms: int)
    def list_devices() -> list[DeviceInfo]              # 静态方法
    def start(self, callback: Callable[[np.ndarray], None]) -> None
    def stop(self) -> None
    def close(self) -> None
```

- 使用 `ctypes.CDLL` 加载 `audio_capture.dll`
- `callback` 在 C++ 回调线程中调用 → 内部通过 `queue.Queue` 转发到 Python 消费线程
- numpy 数组零拷贝：`np.frombuffer(c_ptr, dtype=np.float32)`

#### `recognizer.py` — Sherpa-ONNX 封装

```python
class Recognizer:
    def __init__(self, model_path: str, sample_rate: int = 16000)
    def create_stream(self) -> RecognitionStream
    def accept_waveform(self, stream, samples: np.ndarray) -> str
    def is_endpoint(self, stream, samples: np.ndarray) -> bool  # VAD
    def finalize(self, stream) -> str  # 最终结果
    def download_model(model_name: str) -> Path  # 首次运行下载
```

- 封装 `sherpa_onnx.OnlineRecognizer`
- 内部维护识别状态（accumulated text）
- VAD 通过 Sherpa-ONNX 内置的端点检测实现
- 模型文件：`~/.voicein/models/<model_name>/`

#### `hotkey.py` — 全局热键

```python
class GlobalHotkey:
    def __init__(self, modifiers: int, vk: int, callback: Callable)
    def start(self) -> None
    def stop(self) -> None
```

实现方案：ctypes 调用 Win32 API

```
RegisterHotKey(NULL, id, MOD_CONTROL | MOD_SHIFT, ord('V'))
  → 在独立热键线程中 GetMessageW() 接收 WM_HOTKEY
  → 通过 thread-safe callback 通知 orchestrator
```

- 热键 ID 固定为 1
- 检测热键冲突：`RegisterHotKey` 失败时打印警告并尝试备选热键
- v1 不提供热键自定义 UI

#### `output.py` — 输出模块

```python
class Output:
    @staticmethod
    def paste(text: str) -> None
```

实现流程：
```
1. 保存当前剪贴板内容 (backup)
2. 将 text 写入剪贴板
3. 模拟 Ctrl+V (keybd_event)
4. 等待 50ms
5. 恢复剪贴板内容 (backup)
```

#### `tray.py` — 托盘图标

```python
class TrayIcon:
    def __init__(self, on_quit: Callable)
    def set_recording(self, is_recording: bool) -> None  # 切换图标颜色
    def show_notification(self, title: str, msg: str) -> None
    def run(self) -> None  # 阻塞运行消息循环
```

- 使用 `pystray.Icon`
- 两种图标：默认（灰色麦克风）、录音中（红色麦克风）
- 图标内嵌为 base64 字符串（不需要外部 .ico 文件）

#### `orchestrator.py` — 主流程状态机

```
                    ┌─────────┐
      启动 ────────→│   IDLE   │
                    └────┬─────┘
                         │ 热键按下
                         ▼
                    ┌─────────┐
            ┌──────→│RECORDING │
            │       └────┬─────┘
            │            │ 热键再次按下 或 VAD 超时
            │            ▼
            │       ┌─────────┐
            │       │RECOGNIZING│
            │       │(finalize)│
            │       └────┬─────┘
            │            │ 获得最终文本
            │            ▼
            │       ┌─────────┐
            │       │ PASTING │
            │       └────┬─────┘
            │            │ 完成
            └────────────┘
```

### 2.2 线程模型

```
线程 1: 主线程 (MainThread)
  └── pystray 消息循环（tkinter 事件循环，不处理 Win32 消息）

线程 2: 热键线程 (HotkeyThread)
  ├── RegisterHotKey(NULL, 1, MOD_CTRL|MOD_SHIFT, 'V')
  ├── GetMessageW() 循环等待 WM_HOTKEY
  └── 收到热键 → 通过 thread-safe callback 通知 orchestrator

线程 3: 音频消费线程 (AudioConsumer)
  ├── 循环从 queue.Queue 读取音频块
  ├── 喂入 Sherpa-ONNX 流式识别
  └── 检测 VAD 端点

线程 4: C++ WASAPI 回调线程 (由 WASAPI 创建)
  ├── 接收音频数据
  ├── 写入环形缓冲区
  └── 按 block_ms 间隔触发
```

为什么需要四个线程？
- **主线程**：运行 pystray（tkinter 事件循环），阻塞在 `Icon.run()`
- **热键线程**：`RegisterHotKey` + `GetMessageW` 必须在同一线程。因为 pystray 的 tkinter 循环不处理 Win32 消息，必须独立线程跑 Win32 消息泵
- **消费线程**：Sherpa-ONNX 的流式识别有计算开销，不能阻塞 WASAPI 回调
- **WASAPI 回调线程**：系统驱动，必须快速返回（约 1ms 内），不做任何重操作

---

## 三、关键设计决策及理由

### 3.1 为什么不开源模型选择？只用一个 Sherpa-ONNX 中文模型

- 产品定位是"中文语音输入"，不需要通用性
- 单一模型简化了下载、路径管理、测试矩阵
- 后续可以通过配置文件切换到其他模型（高级用户自行折腾）

### 3.2 为什么 VAD 默认 1.5 秒而不是更短？

- 中文讲话有自然停顿（逗号停顿约 500-800ms）
- 1.5 秒确保"思考停顿"不会被误判为结束
- 用户可以按热键手动提前结束

### 3.3 为什么不用 ASIO 而是 WASAPI Shared？

- ASIO 虽然延迟更低，但需要专用驱动
- WASAPI Shared 所有设备支持，且不独占音频设备
- 16kHz 语音采集对延迟不敏感（100ms 回调间隔足够）

### 3.4 为什么粘贴后恢复剪贴板？

- 自动粘贴是"侵入性"操作，用户可能刚才复制了重要内容
- 备份-恢复机制消除这个副作用
- 恢复前等待 50ms 确保 Ctrl+V 已被目标程序处理

---

## 四、错误处理策略

| 错误场景 | 处理方式 | 用户感知 |
|----------|----------|---------|
| 无麦克风设备 | `audio_init` 返回错误码，orchestrator 捕获 | 托盘气泡提示"未检测到麦克风" |
| 模型文件不存在 | `download_model()` 自动下载 | 托盘气泡"正在下载语音模型..." |
| 模型下载失败 | 抛出异常，程序退出 | 托盘气泡"模型下载失败，请检查网络" |
| 热键被占用 | `RegisterHotKey` 失败 | 启动日志警告，托盘气泡提示 |
| 识别结果为空 | orchestrator 检查空文本 | 不粘贴，不提示 |
| WASAPI 设备热插拔 | 下次录音时 `audio_init` 重新枚举设备 | 对用户透明 |
| DLL 加载失败 | `ctypes.CDLL` 抛异常 | 弹窗告知缺少 DLL，退出 |
| 内存分配失败 | C++ 返回错误码 | 托盘气泡"内存不足" |
| 环形缓冲区溢出 | 覆盖旧数据，记录警告 | 可能丢失开头音频 |

---

## 五、配置文件规范

`~/.voicein/config.json`:
```json
{
  "hotkey": {
    "modifiers": 3,
    "vk": 86
  },
  "audio": {
    "sample_rate": 16000,
    "block_ms": 100,
    "device_id": -1
  },
  "vad": {
    "timeout_ms": 1500
  },
  "model": {
    "name": "sherpa-onnx-zh-small",
    "auto_update": false
  },
  "cloud": {
    "enabled": false,
    "provider": "iflytek",
    "api_key": ""
  },
  "version": 1
}
```

- `modifiers: 3` = `MOD_CONTROL(2) | MOD_SHIFT(1)`
- `vk: 86` = `V` 键
- `version` 用于未来配置迁移
