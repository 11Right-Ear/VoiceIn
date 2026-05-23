# PLAN.md — 实施计划

## 总体策略

分 7 个 Step 逐层搭建，每个 Step 独立可验证。遵循"先跑通再优化"的原则，每个 Step 产出可运行的最小单元。

---

## Step 1: C++ WASAPI 音频采集 DLL

### 目标
编译一个 `audio_capture.dll`，Python 能通过 ctypes 加载并调用。

### 文件
```
src/native/
├── CMakeLists.txt
├── audio_capture.h
├── audio_capture.cpp        # WASAPI 采集实现
└── ring_buffer.h            # 无锁环形缓冲区
```

### 关键实现点
- `CoInitializeEx` + `IMMDeviceEnumerator` 枚举音频设备
- `IAudioClient::Initialize` 使用 `AUDCLNT_SHAREMODE_SHARED`
- `IAudioCaptureClient::GetBuffer` 获取 float32 PCM
- 定时器线程（`CreateTimerQueueTimer`）模拟回调周期
- 环形缓冲区：`std::atomic<size_t>` 实现 SPSC 无锁读写
- 导出 C 函数供 ctypes 调用

### 验证
```python
import ctypes
dll = ctypes.CDLL("./audio_capture.dll")
# 列出设备
# 初始化默认设备
# 录制 5 秒
# 检查输出 float32 数组的值范围在 [-1.0, 1.0]
```

### 依赖
- CMake ≥ 3.16
- Visual Studio Build Tools 2022 (MSVC)
- Windows SDK (自带 WASAPI 头文件)

### 预计文件量
- audio_capture.cpp: ~300 行
- ring_buffer.h: ~50 行
- CMakeLists.txt: ~20 行

---

## Step 2: Python 音频采集封装

### 目标
封装 ctypes 调用，提供 Pythonic 的 `AudioCapture` 类，支持回调式数据消费。

### 文件
```
src/app/
├── __init__.py
└── audio_capture.py
```

### 关键实现点
- `ctypes.CDLL` 加载 DLL，设置 `argtypes` / `restype`
- 回调函数用 `ctypes.CFUNCTYPE` 注册
- 回调中 `queue.Queue.put_nowait()` 将数据交给消费线程
- `AudioCapture.list_devices()` 静态方法解析设备结构体数组
- 错误处理：每个 C 调用后检查返回值

### 验证
```python
from audio_capture import AudioCapture
devices = AudioCapture.list_devices()
print(devices)
cap = AudioCapture(device_id=-1, sample_rate=16000, channels=1, block_ms=100)
# 录制 5 秒，保存 WAV
# 用 scipy.io.wavfile.write 听效果
```

### 依赖
- Step 1 完成（audio_capture.dll 可加载）
- Python 3.10+

---

## Step 3: Sherpa-ONNX 识别引擎

### 目标
封装 Sherpa-ONNX 在线流式识别，支持实时输入音频块并输出增量文本。

### 文件
```
src/app/
└── recognizer.py
models/
└── .gitkeep
```

### 关键实现点
- `pip install sherpa-onnx`
- 模型下载函数：从 GitHub Releases/HuggingFace 下载到 `~/.voicein/models/`
- 下载进度用 tqdm 或手动进度回调
- 流式识别：`recognizer.create_stream()` → `recognizer.accept_waveform(stream, samples)` → 返回增量文本
- VAD 端点检测：`recognizer.is_endpoint(stream, samples)`
- 最终化：`recognizer.finalize(stream)` 返回完整文本

### 验证
```python
from recognizer import Recognizer
rec = Recognizer()
rec.download_model("sherpa-onnx-zh-small")  # 首次运行
stream = rec.create_stream()
# 从 WAV 文件读取数据，模拟流式输入
# 检查输出中文文本准确率
```

### 依赖
- `sherpa-onnx` Python 包
- 网络连接（首次下载模型，约 30-50MB）

---

## Step 4: 全局热键 + 系统托盘

### 目标
托盘图标常驻，按全局热键触发回调函数。

### 文件
```
src/app/
├── hotkey.py
├── tray.py
├── icons/
│   ├── mic_gray.png    (base64 嵌入在 tray.py 中)
│   └── mic_red.png     (base64 嵌入在 tray.py 中)
```

### 关键实现点

**hotkey.py:**
- `ctypes.windll.user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_SHIFT, 0x56)` 注册 Ctrl+Shift+V
- `ctypes.windll.user32.GetMessageW` 等待 `WM_HOTKEY` 消息
- `GetMessageW` 有阻塞性，需要在一个可被 `PostThreadMessage` 打断的线程中运行

**tray.py:**
- `pystray.Icon("VoiceIn", image, "VoiceIn - Ctrl+Shift+V", menu)`
- 菜单项：关于、退出
- 与 hotkey 的线程集成——这是最大的挑战

### 线程集成方案

```
主线程:
  pystray.Icon.run()  ← 阻塞主线程

子线程 (HotkeyThread):
  GetMessageW() 循环
  → 收到 WM_HOTKEY → 通过线程安全的回调通知 orchestrator
```

- pystray 内部使用 `tkinter` 或 `gtk` 的消息循环
- 热键线程独立运行 `GetMessageW`
- 两者通过 `queue.Queue` 或回调函数通信

### 验证
```python
from tray import TrayIcon
from hotkey import GlobalHotkey

def on_hotkey():
    print("热键被按下!")

tray = TrayIcon(on_quit=lambda: exit(0))
hotkey = GlobalHotkey(modifiers=3, vk=0x56, callback=on_hotkey)
hotkey.start()
tray.run()
# 按 Ctrl+Shift+V → 控制台打印 "热键被按下!"
# 托盘出现灰色麦克风图标
# 右键菜单可退出
```

### 依赖
- `pystray` + `Pillow` (用于托盘图标)
- Step 1-2（此 Step 可独立于 Step 3 开发测试）

---

## Step 5: 输出模块

### 目标
将文本写入剪贴板，模拟 Ctrl+V 粘贴，粘贴后恢复原剪贴板内容。

### 文件
```
src/app/
└── output.py
```

### 关键实现点
1. `win32clipboard.OpenClipboard()` / `GetClipboardData()` 备份当前剪贴板
2. `pyperclip.copy(text)` 写入新内容
3. `pyautogui.hotkey('ctrl', 'v')` 模拟粘贴
4. `time.sleep(0.05)` 等待粘贴生效
5. 恢复备份的剪贴板内容

### 降级策略
- 如果模拟粘贴失败（某些应用拦截快捷键），降级为只写剪贴板
- pyautogui 可能被安全软件拦截，备选 `ctypes.windll.user32.keybd_event`

### 验证
```python
from output import Output

# 1. 在剪贴板放点东西 "Hello"
# 2. Output.paste("你好世界")
# 3. 检查：当前焦点窗口出现 "你好世界"
# 4. 检查：剪贴板恢复为 "Hello"
```

### 依赖
- `pyperclip`
- `pyautogui`

---

## Step 6: 主流程串联 (orchestrator)

### 目标
将所有模块串联成完整状态机：热键 → 录音 → 识别 → 粘贴。

### 文件
```
src/app/
├── orchestrator.py
├── config.py
└── main.py                  # 程序入口
```

### 状态机实现

```python
class Orchestrator:
    class State(Enum):
        IDLE = auto()
        RECORDING = auto()
        FINALIZING = auto()
        PASTING = auto()

    def __init__(self, config: Config):
        self.state = State.IDLE
        self.audio = AudioCapture(...)
        self.rec = Recognizer(...)
        self.tray = TrayIcon(...)
        self.hotkey = GlobalHotkey(..., callback=self._on_hotkey)
        self.output = Output()

    def _on_hotkey(self):
        if self.state == State.IDLE:
            self._start_recording()
        elif self.state == State.RECORDING:
            self._stop_recording()

    def _start_recording(self):
        self.state = State.RECORDING
        self.tray.set_recording(True)
        self.stream = self.rec.create_stream()
        self.audio.start(callback=self._on_audio)

    def _on_audio(self, samples: np.ndarray):
        text = self.rec.accept_waveform(self.stream, samples)
        if self.rec.is_endpoint(self.stream, samples):
            self._stop_recording()

    def _stop_recording(self):
        self.state = State.FINALIZING
        self.audio.stop()
        final_text = self.rec.finalize(self.stream)
        if final_text.strip():
            self.state = State.PASTING
            self.output.paste(final_text)
        self.tray.set_recording(False)
        self.state = State.IDLE
```

### 验证
端到端测试：
```
1. 启动 python main.py
2. 打开记事本，光标放在编辑区
3. 按 Ctrl+Shift+V，说话 "今天天气不错"
4. 按 Ctrl+Shift+V 停止，或等待静音自动停止
5. 记事本中出现 "今天天气不错"
```

### 依赖
- Step 1-5 全部完成

---

## Step 7: 构建与打包

### 目标
一键构建 C++ DLL + Python 脚本 → 单个 exe 文件。

### 文件
```
build.py                      # 构建脚本
src/requirements.txt
```

### 构建流程
```
build.py:
  1. cmake --build src/native/build --config Release
  2. 复制 audio_capture.dll 到 app 目录
  3. PyInstaller --onefile --windowed --add-data audio_capture.dll src/app/main.py
  4. 输出 dist/VoiceIn.exe
```

### PyInstaller 配置
```python
# VoiceIn.spec
a = Analysis(
    ['src/app/main.py'],
    binaries=[('src/native/build/Release/audio_capture.dll', '.')],
    datas=[],
    hiddenimports=['sherpa_onnx', 'pystray', 'PIL'],
    ...
)
```

### 最终产物
```
dist/
├── VoiceIn.exe           # 主程序 (~15MB Python + 15MB sherpa-onnx + 200KB DLL)
└── 首次运行后:
    ~/.voicein/
    ├── config.json
    └── models/
        └── sherpa-onnx-zh-small/  (~35MB)
```

- 总体积（不含模型）：~30MB
- 首次运行下载模型：~35MB
- 运行时内存：~150MB（含模型推理）

### 验证
- 在一台干净的 Windows 机器上运行 `VoiceIn.exe`
- 首次启动自动下载模型
- 按热键 → 说话 → 文字出现
- 右键退出，再次启动正常

---

## 里程碑与时间预估

| Step | 内容 | 工作量 | 产出 |
|------|------|--------|------|
| 1 | C++ WASAPI DLL | 1 天 | audio_capture.dll |
| 2 | Python 封装 | 0.5 天 | audio_capture.py |
| 3 | Sherpa-ONNX 引擎 | 0.5 天 | recognizer.py |
| 4 | 热键 + 托盘 | 1 天 | hotkey.py + tray.py |
| 5 | 输出模块 | 0.5 天 | output.py |
| 6 | 主流程串联 | 0.5 天 | orchestrator.py + main.py |
| 7 | 打包 | 0.5 天 | VoiceIn.exe |

**总计约 4.5 天开发时间。**

---

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| Sherpa-ONNX 中文模型流式识别率不达标 | 中 | 高 | 备选 faster-whisper 方案 |
| pystray 与热键消息循环冲突 | 中 | 中 | 备选：用 tkinter 手动托盘（Python 自带） |
| PyInstaller 打包 sherpa-onnx 依赖复杂 | 中 | 低 | 提前验证，备选 nuitka |
| WASAPI Shared 模式延迟偏高 | 低 | 中 | 实测后决定是否切 Exclusive 模式或增大 block_ms |
| 全局热键被杀毒软件拦截 | 中 | 低 | 提供备选热键配置，文档说明 |
