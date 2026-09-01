# -*- mode: python ; coding: utf-8 -*-

import sys
import importlib
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

# Find funasr package directory for data files
_funasr_dir = Path(importlib.util.find_spec("funasr").origin).parent

# Collect full funasr + modelscope packages (source files included,
# so funasr's register.py inspect.getsourcelines works at runtime)
_funasr_datas, _funasr_bins, _funasr_hidden = collect_all("funasr")
_modelscope_datas, _modelscope_bins, _modelscope_hidden = collect_all("modelscope")

# ---- hidden imports for funasr + torch + sherpa-onnx ----

hiddenimports = [
    # funasr (SenseVoice + model loading)
    "funasr",
    "funasr.auto.auto_model",
    "funasr.models.sense_voice",
    "funasr.models.sense_voice.model",
    "funasr.models.sense_voice.whisper_lib",
    "funasr.utils.postprocess_utils",
    "funasr.frontends",
    "funasr.tokenizer",
    "funasr.tokenizer.whisper_tokenizer",
    "funasr.tokenizer.sentencepiece_tokenizer",
    "funasr.utils",
    # modelscope (model hub)
    "modelscope",
    "modelscope.hub",
    "modelscope.hub.snapshot_download",
    "modelscope.hub.api",
    "modelscope.hub.file_download",
    "modelscope.utils",
    "modelscope.utils.oss_service",
    "modelscope.utils.config",
    # sherpa-onnx (native .pyd)
    "sherpa_onnx",
    "sherpa_onnx.lib._sherpa_onnx",
    # pystray + Pillow (tray icon)
    "pystray",
    "pystray._win32",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    # audio
    "soundfile",
    "audioread",
    "librosa",
    "librosa.core",
    "librosa.core.audio",
    # numpy (sherpa-onnx needs it)
    "numpy",
    "numpy.core",
    "numpy.core._multiarray_umath",
    # tokenizer / encoding
    "tiktoken",
    "tiktoken_ext",
    "tiktoken_ext.openai_public",
    "sentencepiece",
    "onnxruntime",
    # scipy / sklearn (may be used by librosa or funasr)
    "scipy",
    "sklearn",
    "sklearn.preprocessing",
    # tkinter (pystray backend)
    "tkinter",
    "tkinter.ttk",
    "tkinter.messagebox",
    "_tkinter",
    # additional torch internals that may get missed
    "torch",
    "torchaudio",
    "torchvision",
]

# ---- collect binaries (audio_capture.dll) ----

dll_path = str((Path("src") / "app" / "audio_capture.dll").resolve())
binaries = [(dll_path, ".")]

# ---- Analysis ----

a = Analysis(
    ["src/app/main.py"],
    pathex=["src/app"],
    binaries=binaries + _funasr_bins + _modelscope_bins,
    datas=[
        (str(_funasr_dir / "version.txt"), "funasr"),
    ] + _funasr_datas + _modelscope_datas,

    hiddenimports=hiddenimports + _funasr_hidden + _modelscope_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# ---- PYZ ----

pyz = PYZ(a.pure)

# ---- EXE ----

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VoiceIn",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # no terminal window for tray app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

# ---- COLLECT (for --onedir output) ----

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="VoiceIn",
)
