#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试依赖和模块导入
用于检查项目是否能正常工作
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def check_imports():
    """检查所有模块导入"""
    results = {}

    # 第三方库
    third_party = [
        ("PyQt6", "PyQt6.QtWidgets"),
        ("pynput", "pynput"),
        ("sounddevice", "sounddevice"),
        ("webrtcvad", "webrtcvad"),
        ("pyautogui", "pyautogui"),
        ("pyperclip", "pyperclip"),
        ("numpy", "numpy"),
        ("requests", "requests"),
    ]

    # 检查第三方库
    for name, module in third_party:
        try:
            __import__(module)
            results[name] = "OK"
        except ImportError as e:
            results[name] = f"MISSING: {e}"

    # 检查可选库
    optional = [
        ("transformers", "transformers"),
        ("torch", "torch"),
        ("huggingface_hub", "huggingface_hub"),
        ("sherpa_onnx", "sherpa_onnx"),
    ]

    optional_results = {}
    for name, module in optional:
        try:
            __import__(module)
            optional_results[name] = "OK"
        except ImportError:
            optional_results[name] = "NOT INSTALLED (optional)"

    # 检查项目模块
    project_modules = [
        ("config", "config"),
        ("models", "models"),
        ("storage", "storage"),
    ]

    project_results = {}
    for name, module in project_modules:
        try:
            __import__(module)
            project_results[name] = "OK"
        except Exception as e:
            project_results[name] = f"ERROR: {e}"

    # 检查核心模块 (可能依赖 pynput)
    core_results = {}
    try:
        from config import get_settings
        core_results["config.settings"] = "OK"
    except Exception as e:
        core_results["config.settings"] = f"ERROR: {e}"

    try:
        from models import get_model_manager
        core_results["models.manager"] = "OK"
    except Exception as e:
        core_results["models.manager"] = f"ERROR: {e}"

    try:
        from storage import get_audio_manager
        core_results["storage.manager"] = "OK"
    except Exception as e:
        core_results["storage.manager"] = f"ERROR: {e}"

    return results, optional_results, project_results, core_results


def print_results():
    """打印检查结果"""
    print("=" * 60)
    print("快人快语 - 依赖检查")
    print("=" * 60)

    required, optional, project, core = check_imports()

    # 必需的第三方库
    print("\n【必需的第三方库】")
    all_ok = True
    for name, status in required.items():
        if status != "OK":
            all_ok = False
            print(f"  ❌ {name}: {status}")
        else:
            print(f"  ✅ {name}: OK")

    if not all_ok:
        print("\n⚠️  缺少必需依赖！请运行:")
        print("   pip install -r requirements.txt")

    # 可选库
    print("\n【可选库 (AI 功能)】")
    for name, status in optional.items():
        if "NOT INSTALLED" in status:
            print(f"  ⚠️  {name}: 未安装")
        else:
            print(f"  ✅ {name}: OK")

    # 项目模块
    print("\n【项目模块】")
    for name, status in project.items():
        if "ERROR" in status:
            print(f"  ❌ {name}: {status}")
        else:
            print(f"  ✅ {name}: OK")

    # 核心功能
    print("\n【核心功能】")
    for name, status in core.items():
        if "ERROR" in status:
            print(f"  ❌ {name}: {status}")
        else:
            print(f"  ✅ {name}: OK")

    print("\n" + "=" * 60)

    if all_ok:
        print("✅ 所有必需依赖已安装！")
        print("\n下一步:")
        print("1. 安装 AI 功能依赖:")
        print("   pip install transformers torch huggingface_hub sherpa-onnx")
        print("2. 运行主程序:")
        print("   python main.py")
    else:
        print("❌ 请先安装必需依赖:")
        print("   pip install -r requirements.txt")

    print("=" * 60)


if __name__ == "__main__":
    print_results()
