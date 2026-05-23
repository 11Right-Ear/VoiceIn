"""Test: tray icon + global hotkey integration"""
import sys
from tray import TrayIcon
from hotkey import GlobalHotkey

press_count = 0

def on_hotkey():
    global press_count
    press_count += 1
    print(f"\r热键触发! (第 {press_count} 次)    ")

def on_quit():
    print("\n退出...")
    hotkey.stop()

# Show instructions
print("=" * 50)
print("  VoiceIn 测试模式")
print("  托盘图标已出现 — 查看任务栏右下角")
print("  按 Ctrl+Shift+V 测试热键")
print("  右键托盘图标 → 退出")
print("=" * 50)

# Start hotkey
hotkey = GlobalHotkey(callback=on_hotkey)
hotkey.start()
print("热键已注册: Ctrl+Shift+V")

# Start tray (blocks until quit)
tray = TrayIcon(on_quit=on_quit)
try:
    tray.run()
finally:
    hotkey.stop()
    print("已退出")
