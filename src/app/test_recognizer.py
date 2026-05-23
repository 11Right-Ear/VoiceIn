"""Test Recognizer: record audio, recognize with Sherpa-ONNX"""
import time
import numpy as np
from pathlib import Path

from audio_capture import AudioCapture
from recognizer import Recognizer

# 1. Load model
model_dir = Path.home() / ".voicein" / "models" / "zh-small-zipformer"
print("Loading model...")
rec = Recognizer(model_dir, sample_rate=16000, enable_vad=True, vad_timeout_ms=1500)
print(f"Model loaded (sample_rate={rec.sample_rate}, VAD enabled)")

# 2. Record 5s of speech
print("\n=== Recording 5 seconds — speak Chinese ===")
chunks: list[np.ndarray] = []

def on_audio(samples: np.ndarray, sr: int) -> None:
    chunks.append(samples.copy())

cap = AudioCapture(device_id=-1, sample_rate=16000, channels=1, block_ms=100)
cap.start(on_audio)
time.sleep(5.0)
cap.stop()
cap.close()

if not chunks:
    print("No audio captured.")
    exit(1)

total_samples = sum(len(c) for c in chunks)
print(f"Got {len(chunks)} blocks, {total_samples} samples ({total_samples/16000:.1f}s)")

# 3. Streaming recognition
print("\n=== Recognition ===")
stream = rec.create_stream()
final_text = ""

for i, chunk in enumerate(chunks):
    rec.accept_waveform(stream, chunk)
    rec.decode(stream)
    text = rec.get_text(stream)
    if text != final_text:
        print(f"  [{i:2d}] {text}")
        final_text = text
    if rec.is_endpoint(stream):
        print(f"  [VAD endpoint detected at chunk {i}]")
        break

print(f"\n=== Final text ===\n{final_text}")
if not final_text.strip():
    print("(No text — did you speak? Try again louder or closer to mic)")
