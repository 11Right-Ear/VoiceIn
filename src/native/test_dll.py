"""Quick smoke test for audio_capture.dll"""
import ctypes
from ctypes import wintypes
import os
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Load DLL
dll_path = os.path.join(os.path.dirname(__file__), "build", "Release", "audio_capture.dll")
dll = ctypes.CDLL(dll_path)

# --- audio_callback_t ---
callback_t = ctypes.CFUNCTYPE(None, ctypes.POINTER(ctypes.c_float), ctypes.c_int, ctypes.c_int)

# --- audio_device_info_t ---
class DeviceInfo(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_wchar * 256),
        ("id", ctypes.c_int),
        ("max_channels", ctypes.c_int),
        ("default_sample_rate", ctypes.c_int),
    ]

# --- Bind functions ---
# audio_list_devices
dll.audio_list_devices.argtypes = [ctypes.POINTER(ctypes.POINTER(DeviceInfo))]
dll.audio_list_devices.restype = ctypes.c_int

# audio_free_device_list
dll.audio_free_device_list.argtypes = [ctypes.POINTER(DeviceInfo)]
dll.audio_free_device_list.restype = None

# audio_init
dll.audio_init.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
dll.audio_init.restype = ctypes.c_int

# audio_last_error
dll.audio_last_error.argtypes = []
dll.audio_last_error.restype = ctypes.c_wchar_p

# --- Test device enumeration ---
print("=== Device Enumeration ===")
devices_ptr = ctypes.POINTER(DeviceInfo)()
count = dll.audio_list_devices(ctypes.byref(devices_ptr))
if count < 0:
    print(f"ERROR: {dll.audio_last_error()}")
else:
    print(f"Found {count} device(s):")
    for i in range(count):
        d = devices_ptr[i]
        print(f"  [{d.id}] {d.name}  (ch={d.max_channels}, sr={d.default_sample_rate})")
    dll.audio_free_device_list(devices_ptr)
    print()

# --- Test audio_init ---
print("=== Audio Init ===")
rc = dll.audio_init(-1, 16000, 1, 100)
if rc != 0:
    print(f"ERROR: {dll.audio_last_error()}")
else:
    print("audio_init succeeded (16000Hz, mono, 100ms blocks)")
print()

# Cleanup (can't test start/stop without proper callback handling)
dll.audio_close()
print("=== Done ===")
