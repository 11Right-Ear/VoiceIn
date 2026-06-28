# VoiceIn — 极简中英文语音输入

> 按一下热键，说话，文字出现在光标处。Windows 原生托盘小工具。

支持**中英混杂识别**、自动过滤语气词（嗯/呃/唔）、纠错字典、短句合并。纯离线运行，无需联网。

## 安装

1. 从 [Releases](https://github.com/11Right-Ear/VoiceIn/releases) 下载 `VoiceIn-windows-amd64.zip`
2. 解压后运行 `VoiceIn.exe`
3. **首次启动**会自动下载 SenseVoice 模型（~900 MB，一次下载即可）
4. 托盘出现灰色麦克风图标 → 就绪

## 基本用法

在**任何应用**中（终端、记事本、浏览器、IDE、Claude Code……）：

| 操作 | 结果 |
|------|------|
| 按 **Ctrl+Alt+S** | 图标变红 → 开始录音 |
| 说一句话 | 停顿后文字出现在光标处 |
| 连续说多句 | 每句自动粘贴 |
| 再按 **Ctrl+Alt+S** | 停止录音 |

右键托盘图标 → Quit 退出。

## 高级用法：中英混杂

VoiceIn 默认**自动检测语言**，中英混杂表述无需任何设置：

| 你说 | 得到 |
|------|------|
| "这个API的response返回了一个200 OK" | 原文保留，不丢英文 |
| "帮我review一下这个PR的commit" | 中英正常共存 |
| "嗯我觉得嗯这个方案可以的" | 语气词 **嗯/呃/唔** 自动过滤 |
| "我…觉得…可以"（停顿较长）| 自动合并，不切成三段 |

如果模型对某段文字识别不准，可以用纠错字典修复（见下方配置）。

## 配置

编辑 `C:\Users\你的用户名\.voicein\config.json`：

```json
{
  "hotkey_modifiers": 3,
  "hotkey_vk": 83,
  "engine": "sensevoice",
  "device_id": 1,
  "vad_threshold": 0.006,
  "vad_silence_ms": 1000,
  "merge_short_segments": true,
  "merge_short_threshold": 3,
  "language": "",
  "corrections": {},
  "deny_words": [],
  "auto_enter": false
}
```

### 完整配置项

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `hotkey_modifiers` | `3` | 1=Alt, 2=Ctrl, 4=Shift（3=Alt+Ctrl） |
| `hotkey_vk` | `83` | 按键虚拟键码（83=S） |
| `device_id` | `1` | 麦克风设备号（-1=默认, 0/1=第一/第二） |
| `sample_rate` | `16000` | 采样率（一般不改） |
| `engine` | `"sensevoice"` | `"sensevoice"` 或 `"streaming"`（备选引擎） |

**VAD / 分句相关：**

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `vad_threshold` | `0.006` | 静音检测灵敏度（环境噪声大时调高，如 `0.01`） |
| `vad_silence_ms` | `1000` | 连续静音多久切段（毫秒）。说话爱停顿可调大到 `1500` |
| `merge_short_segments` | `true` | 是否合并短段。开启后「我…觉得…可以」不会切成三段粘贴 |
| `merge_short_threshold` | `3` | 少于多少字算「短段」 |

**识别优化相关：**

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `language` | `""` | 识别语言。`""` = 自动检测，也可指定 `"zh"` / `"en"` / `"ja"` / `"ko"` |
| `corrections` | `{}` | 纠错字典。修复模型固定 bad case，如 `{"APi": "API", "dome": "demo"}` |
| `deny_words` | `[]` | 禁用词列表。模型幻觉出来的噪声词可加到这里过滤掉 |
| `auto_enter` | `false` | 粘贴后是否自动回车（建议 `false`，手动确认后再发送） |

### 配置示例：中英混合 + 纠错 + 长停顿

```json
{
  "vad_silence_ms": 1500,
  "language": "",
  "corrections": {
    "APi": "API",
    "apI": "API",
    "dome": "demo"
  },
  "deny_words": ["噼", "啪"],
  "merge_short_segments": true
}
```

### 配置示例：纯英文模式

```json
{
  "language": "en",
  "vad_threshold": 0.004
}
```

## 终端 / CLI 模式

在终端实时显示识别文字（无托盘、不粘贴）：

```bash
VoiceIn.exe --cli
```

列出可用麦克风：

```bash
VoiceIn.exe --cli --list-devices
```

按 Ctrl+C 退出。

## 工作原理

- **ASR 引擎：** FunASR + SenseVoiceSmall（纯离线，CPU 运行，RTF ≈ 0.06）
- **音频采集：** C++ WASAPI DLL（低延迟 Windows 音频 API）
- **VAD：** 能量阈值检测，自动切分语音段
- **后处理流水线：**
  1. 模型原始输出
  2. `rich_transcription_postprocess`（ITN 文字正常化）
  3. `remove_fillers`（过滤 嗯/呃/唔 语气词）
  4. `apply_corrections`（用户纠错字典 + 禁用词）
  5. 短段合并（< 阈值字数的段缓存后重新识别）

启动时模型加载一次，录音期间音频流实时处理，全流程 CPU 执行，无需 GPU。

## 常见问题

| 问题 | 解决 |
|------|------|
| 热键无反应 | 检查其他应用是否占用了 Ctrl+Alt+S |
| 识别不准 | ① 增大麦克风音量 ② 用 `corrections` 加纠错 ③ 试试调 `vad_threshold` |
| 说话被切段 | 增大 `vad_silence_ms`（如 `1500`）；关闭 `merge_short_segments` 不会影响 |
| 中英混杂丢失英文 | 确认 `language` 为 `""`（自动检测），不要设成 `"zh"` |
| 模型下载失败 | 检查网络代理，确保能访问 `modelscope.cn` |
| 没声音 | `device_id` 设为 `-1`（默认设备）或用 `--list-devices` 查看 |
| 图标不显示 | 任务栏设置 → 显示隐藏的图标 → VoiceIn |
| 总是贴成一段 | 把 `vad_silence_ms` 调小到 `600`，让 VAD 更积极切段 |

## 从源码构建

```bash
# 编译音频采集 DLL
cmake -B src/native/build -S src/native
cmake --build src/native/build --config Release

# 安装依赖
pip install torch torchaudio funasr modelscope pystray Pillow numpy sherpa-onnx

# 运行
python src/app/main.py
```

## 技术栈

- **ASR：** FunASR + SenseVoiceSmall（离线，CPU）
- **音频：** C++ WASAPI（Windows 原生低延迟）
- **UI：** pystray 托盘图标
- **语言：** Python 3.12 + PyTorch

## License

MIT
