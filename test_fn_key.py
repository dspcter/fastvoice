#!/usr/bin/env python3
"""
测试 pynput 能否监听到 Fn 键
"""

from pynput import keyboard
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(message)s')

print("=" * 60)
print("按键监听测试")
print("=" * 60)
print("\n请按下以下键测试：")
print("  - Fn 键")
print("  - Option/Alt 键")
print("  - Ctrl 键")
print("  - Command 键")
print("  - Shift 键")
print("\n按 Ctrl+C 退出\n")

def on_press(key):
    try:
        if hasattr(key, 'char') and key.char:
            print(f"  按下: {key.char} (字符键)")
        else:
            print(f"  按下: {key} (特殊键)")
    except Exception as e:
        print(f"  错误: {e}")

def on_release(key):
    try:
        if hasattr(key, 'char') and key.char:
            print(f"  释放: {key.char} (字符键)")
        else:
            print(f"  释放: {key} (特殊键)")
    except Exception as e:
        print(f"  错误: {e}")

# 启动监听
with keyboard.Listener(
    on_press=on_press,
    on_release=on_release,
    suppress=False
) as listener:
    listener.join()
