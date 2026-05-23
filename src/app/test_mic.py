"""麦克风自测脚本：录音 → 显示电平 → 模型识别"""
import numpy as np
import time
from pathlib import Path
from audio_capture import AudioCapture

# 1. 列出设备
print("=== 输入设备 ===")
for d in AudioCapture.list_devices():
    print(f"  [{d.id}] {d.name}")

# 2. 选择设备
device_id = 1  # 改成你的麦克风 ID，或 -1 用系统默认
print(f"\n使用设备 ID={device_id}")

# 3. 录音
print("\n=== 录音 5 秒 — 请说中文 ===")
chunks = []
def on_audio(samples, sr):
    chunks.append(samples.copy())

cap = AudioCapture(device_id=device_id, sample_rate=16000, channels=1, block_ms=100)
cap.start(on_audio)
time.sleep(5)
cap.stop()
cap.close()

all_audio = np.concatenate(chunks)
peak = np.abs(all_audio).max()
rms = np.sqrt(np.mean(all_audio ** 2))

print(f"\n样本数: {len(all_audio)} ({len(all_audio)/16000:.1f}s)")
print(f"电平:   peak={peak:.4f}  rms={rms:.6f}")

if peak < 0.01:
    print("\n❌ 音量太低！几乎没有声音。请检查：")
    print("  1. Windows 设置 → 系统 → 声音 → 输入 → 选对麦克风")
    print("  2. 对着麦克风说话时测试条是否跳动")
    print("  3. 录制设备属性 → 级别 → 调到 80-100")
    print(f"  4. 换 device_id（当前={device_id}），试试 0 或 -1")
elif peak < 0.05:
    print("\n⚠️ 音量偏低，但可以试试识别")
elif peak < 0.2:
    print("\n✅ 音量尚可")
else:
    print("\n✅ 音量正常")

# 4. 识别
if peak > 0.005:
    print("\n=== 语音识别 ===")
    from recognizer import Recognizer

    model_dir = Path.home() / ".voicein" / "models" / "zh-small-zipformer"
    if not (model_dir / "tokens.txt").exists():
        print(f"模型不存在: {model_dir}")
        print("请先下载模型放到该目录")
    else:
        print("加载模型...")
        rec = Recognizer(model_dir, sample_rate=16000, enable_vad=False)
        stream = rec.create_stream()
        rec.accept_waveform(stream, all_audio)
        rec.decode(stream)
        text = rec.get_text(stream)
        print(f"\n识别结果: '{text}'")
        if not text.strip():
            print("(空 — 模型未识别到语音)")
else:
    print("\n跳过识别（音量太低）")
