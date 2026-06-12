# VoiceIn v1.0

Minimal Chinese speech-to-text input tool for Windows. Press a hotkey, speak, and your words appear wherever your cursor is.

## Installation

1. Download `VoiceIn-windows-amd64.zip` from [Releases](https://github.com/11Right-Ear/VoiceIn/releases)
2. Extract the zip
3. Run `VoiceIn.exe`
4. On first launch, the SenseVoice model (~900 MB) will download automatically (one-time)
5. A gray microphone icon appears in the system tray — you're ready

## Usage

In **any application** (terminal, notepad, browser, IDE, Claude Code...):

| Action | Result |
|--------|--------|
| Press **Ctrl+Alt+S** | Tray icon turns red — start speaking |
| Speak a sentence | Text appears at the cursor after a pause |
| Speak multiple sentences | Each sentence pastes automatically |
| Press **Ctrl+Alt+S** again | Stop recording |

To exit, right-click the tray icon → Quit.

By default, text is pasted **without pressing Enter** — review and send manually.

## How It Works

VoiceIn uses [FunASR](https://github.com/modelscope/FunASR) with the **SenseVoiceSmall** model (local, offline) for Chinese speech recognition. Audio capture is handled by a C++ WASAPI DLL for low-latency microphone input. The system tray UI is built with pystray.

No internet required after the initial model download. All processing runs on your CPU.

## Configuration

Edit `C:\Users\<username>\.voicein\config.json`:

```json
{
  "hotkey_modifiers": 3,
  "hotkey_vk": 83,
  "engine": "sensevoice",
  "device_id": 1,
  "vad_threshold": 0.006,
  "auto_enter": false,
  "sample_rate": 16000
}
```

| Key | Description |
|-----|-------------|
| `hotkey_modifiers` | 1=Alt, 2=Ctrl, 4=Shift (e.g. 3=Alt+Ctrl) |
| `hotkey_vk` | Virtual key code (0x53=S) |
| `device_id` | Microphone device (-1=default, 0/1=first/second) |
| `vad_threshold` | Voice detection sensitivity (lower = more sensitive, 0.006 default) |
| `auto_enter` | Auto-press Enter after paste (`false` recommended) |

## Terminal / CLI Mode

For real-time text display in the terminal (no tray, no paste):

```bash
VoiceIn.exe --cli
```

List available microphones:

```bash
VoiceIn.exe --cli --list-devices
```

Press Ctrl+C to exit.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Hotkey not working | Check if another app is using Ctrl+Alt+S |
| Poor recognition | Increase mic volume in Windows Settings → Sound |
| Model download fails | Check network; ensure `modelscope.cn` is reachable |
| No audio detected | Set `device_id` correctly in `config.json` |
| Icon not visible | Taskbar settings → Show hidden icons → VoiceIn |

## Tech Stack

- **ASR Engine:** FunASR + SenseVoiceSmall (RTF ≈ 0.06 on CPU)
- **Audio Capture:** C++ WASAPI (Windows Audio Session API)
- **UI:** pystray system tray
- **Format:** Python 3.12, PyTorch, modelscope

## Build from Source

```bash
# Compile audio DLL
cmake -B src/native/build -S src/native
cmake --build src/native/build --config Release

# Install deps
pip install torch torchaudio funasr modelscope pystray Pillow numpy sherpa-onnx

# Run
python src/app/main.py
```

## License

MIT
