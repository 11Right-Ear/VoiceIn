"""Quick test: record 5s, feed to model, check recognition"""
import time, numpy as np
from pathlib import Path
from audio_capture import AudioCapture
from recognizer import Recognizer

chunks = []
def on_audio(samples, sr):
    chunks.append(samples.copy())

print("Recording 5s — speak Chinese now...")
cap = AudioCapture(device_id=-1, sample_rate=16000, channels=1, block_ms=100)
cap.start(on_audio)
time.sleep(5)
cap.stop()
cap.close()

if not chunks:
    print("No audio!")
    exit(1)

all_audio = np.concatenate(chunks)
print(f"Recorded {len(all_audio)} samples ({len(all_audio)/16000:.1f}s)")

print("Loading model...")
rec = Recognizer(Path.home() / ".voicein" / "models" / "zh-small-zipformer", sample_rate=16000, enable_vad=False)

stream = rec.create_stream()
rec.accept_waveform(stream, all_audio)
print(f"Fed {len(all_audio)} samples, decoding...")
rec.decode(stream)
text = rec.get_text(stream)
print(f"\nResult: '{text}'")
if not text.strip():
    print("(empty — model produced no output)")
