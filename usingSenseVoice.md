# FunASR + SenseVoice Auto Install Guide

## Overview

This guide installs:

* FunASR
* SenseVoiceSmall
* PyTorch
* Optional API Server

After installation you will be able to:

* Speech Recognition (ASR)
* Language Detection
* Emotion Recognition
* Audio Event Detection

---

# 1. Create Python Environment

Recommended:

* Python 3.10
* Conda

```bash
conda create -n funasr python=3.10 -y
conda activate funasr
```

Or:

```bash
python -m venv funasr
```

Windows:

```bash
funasr\Scripts\activate
```

Linux/macOS:

```bash
source funasr/bin/activate
```

---

# 2. Install PyTorch

## NVIDIA GPU (CUDA 12.1)

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

## CPU Only

```bash
pip install torch torchvision torchaudio
```

Verify:

```bash
python -c "import torch;print(torch.cuda.is_available())"
```

Expected:

```text
True
```

for GPU users.

---

# 3. Install FunASR

```bash
pip install -U funasr
```

Optional:

```bash
pip install -U modelscope huggingface_hub
```

---

# 4. Verify Installation

Create:

test.py

```python
from funasr import AutoModel

model = AutoModel(
    model="iic/SenseVoiceSmall",
    trust_remote_code=True,
    device="cuda:0"
)

print("SenseVoice Loaded Successfully")
```

Run:

```bash
python test.py
```

The first run automatically downloads the model.

---

# 5. SenseVoice Example

Create:

sensevoice_demo.py

```python
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess

model = AutoModel(
    model="iic/SenseVoiceSmall",
    trust_remote_code=True,
    device="cuda:0"
)

res = model.generate(
    input="test.wav",
    language="auto",
    use_itn=True
)

print(rich_transcription_postprocess(res[0]["text"]))
```

Run:

```bash
python sensevoice_demo.py
```

---

# 6. Auto Download Location

Windows:

```text
C:\Users\<username>\.cache\modelscope\
```

Linux:

```text
~/.cache/modelscope/
```

---

# 7. Install FFmpeg

Required for many audio formats.

## Windows

```bash
winget install ffmpeg
```

or

```bash
choco install ffmpeg
```

## Ubuntu

```bash
sudo apt update
sudo apt install ffmpeg -y
```

## macOS

```bash
brew install ffmpeg
```

Verify:

```bash
ffmpeg -version
```

---

# 8. Start OpenAI-Compatible API Server

Install:

```bash
pip install funasr fastapi uvicorn python-multipart
```

Start:

```bash
funasr-server --model sensevoice --device cuda
```

Server:

```text
http://localhost:8000
```

---

# 9. OpenAI SDK Example

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="dummy"
)

with open("test.wav", "rb") as f:
    result = client.audio.transcriptions.create(
        model="sensevoice",
        file=f
    )

print(result.text)
```

---

# 10. Quick Health Check

```bash
python - <<EOF
from funasr import AutoModel

model = AutoModel(
    model="iic/SenseVoiceSmall",
    trust_remote_code=True,
    device="cpu"
)

print("OK")
EOF
```

If "OK" appears, installation succeeded.

---

# Recommended Agent Architecture

```text
Microphone
     ↓
 SenseVoice
     ↓
     LLM
     ↓
 Planner
     ↓
 Robot Controller
```

SenseVoice acts as the robot's hearing system and provides:

* Text
* Language
* Emotion
* Audio Events

through a single model.
