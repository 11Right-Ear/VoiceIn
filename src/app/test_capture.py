"""Test AudioCapture: record 3 seconds, save to WAV"""
import time
import wave
import numpy as np
from audio_capture import AudioCapture

print("=== Device List ===")
devices = AudioCapture.list_devices()
for d in devices:
    print(f"  [{d.id}] {d.name}")

# Collect audio chunks
chunks: list[np.ndarray] = []

def on_audio(samples: np.ndarray, sample_rate: int) -> None:
    chunks.append(samples.copy())
    print(f"  received {len(samples)} samples ({len(samples)/sample_rate*1000:.0f}ms)")

cap = AudioCapture(device_id=-1, sample_rate=16000, channels=1, block_ms=100)
print(f"\n=== Recording 3 seconds (16000Hz, mono, 100ms blocks) ===")

cap.start(on_audio)
time.sleep(3.0)
cap.stop()
cap.close()

print(f"\n=== Results ===")
if chunks:
    all_data = np.concatenate(chunks)
    duration = len(all_data) / 16000
    peak = np.max(np.abs(all_data))
    print(f"  Total samples: {len(all_data)} ({duration:.1f}s)")
    print(f"  Peak amplitude: {peak:.3f}")

    # Save WAV
    wav_path = __file__.replace(".py", ".wav")
    with wave.open(wav_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(4)  # float32
        wf.setframerate(16000)
        wf.writeframes(all_data.astype(np.float32).tobytes())
    print(f"  Saved to: {wav_path}")
else:
    print("  No audio data received — check microphone access in Windows privacy settings")
    print("  设置 → 隐私和安全性 → 麦克风 → 允许桌面应用访问麦克风")
