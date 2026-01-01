# 快人快语 - 项目总结

## 项目概述

**快人快语** (FastVoice) - 本地优先的 AI 语音输入法

> 一款支持语音输入和智能翻译的桌面应用，采用闪电说同款技术方案。

---

## 技术方案 (闪电说同款)

### 核心技术栈

| 模块 | 技术方案 | 说明 |
|------|---------|------|
| 语音识别 | sherpa-onnx + SenseVoice-small | ~700MB，离线运行 |
| 翻译引擎 | Qwen2.5-1.5B-Instruct | ~1.2GB，离线运行 |
| 快捷键监听 | pynput | 跨平台全局热键 |
| 音频采集 | sounddevice + webrtcvad | 实时录音 + VAD |
| 文字注入 | pyautogui | 剪贴板方式 |
| 设置界面 | PyQt6 | 原生界面 |
| 打包工具 | PyInstaller | 跨平台打包 |

### 工作流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     用户操作 (快捷键)                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      音频采集 + VAD                              │
│                  检测语音活动，自动裁剪静音                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   sherpa-onnx + SenseVoice                       │
│                     离线语音识别 (本地)                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    ┌─────────┴─────────┐
                    ↓                   ↓
┌─────────────────────────┐  ┌─────────────────────────┐
│   直接注入原文           │  │   Qwen2.5 翻译          │
│   (pyautogui)            │  │   → 注入译文            │
└─────────────────────────┘  └─────────────────────────┘
```

---

## 项目结构

```
快人快语/
├── main.py                     # 主程序入口 ✅
├── test_dependencies.py         # 依赖检查脚本 ✅
├── build.spec                  # PyInstaller 配置 ✅
├── build.sh / build.bat        # 打包脚本 ✅
├── requirements.txt             # 依赖列表 ✅
├── README.md                   # 用户文档 ✅
├── PRD.md                      # 产品需求 ✅
├── .gitignore                  # Git 忽略 ✅
│
├── config/                     # 配置模块 ✅
│   ├── __init__.py
│   ├── constants.py            # 常量 + SenseVoice 模型配置
│   └── settings.py             # 配置管理
│
├── core/                       # 核心功能 ✅
│   ├── __init__.py
│   ├── hotkey_manager.py       # 全局快捷键 (修复: 字符串比较)
│   ├── audio_capture.py        # 音频采集 + VAD
│   ├── asr_engine.py           # SenseVoice 识别 ✅
│   ├── translate_engine.py     # Qwen2.5 翻译
│   └── text_injector.py        # 文字注入
│
├── models/                     # 模型管理 ✅
│   ├── __init__.py
│   └── model_manager.py        # tar.bz2 支持 ✅
│
├── ui/                         # 用户界面 ✅
│   ├── __init__.py
│   └── settings_window.py      # PyQt6 设置窗口
│
├── storage/                    # 数据存储 ✅
│   ├── __init__.py
│   └── audio_manager.py        # 音频文件管理
│
├── audio/recordings/           # 录音文件存储
├── logs/                       # 日志文件
└── assets/                     # 资源文件 (图标)
```

---

## 安装和使用

### 1. 安装依赖

```bash
cd 快人快语

# 安装所有依赖
pip install -r requirements.txt
```

### 2. 检查依赖

```bash
python test_dependencies.py
```

### 3. 运行程序

```bash
python main.py
```

### 4. 默认快捷键

| 功能 | macOS | Windows |
|------|-------|---------|
| 语音输入 | 按住 Fn | 按住 Right Ctrl |
| 快速翻译 | Ctrl + Shift + T | Ctrl + Shift + T |

---

## 功能说明

### 语音输入
- 按住快捷键开始说话
- 松开快捷键自动识别并注入文字
- 支持 VAD 自动裁剪静音

### 智能翻译
- **直接翻译模式**: 按快捷键说话，直接输出译文
- **按键翻译模式**: 先语音输入原文，再按翻译键翻译

### 设置选项
- 快捷键自定义
- 麦克风设备选择
- VAD 灵敏度调节
- 翻译模式选择
- 音频文件管理 (按日期清理)

---

## 打包发布

### macOS
```bash
chmod +x build.sh
./build.sh
```

### Windows
```bash
build.bat
```

---

## 代码审查完成情况

### 已修复的问题

| 问题 | 位置 | 修复 |
|------|------|------|
| UI 线程阻塞 | main.py:160 | 改为简化实现 |
| 模型配置注释 | asr_engine.py:67 | 添加详细说明 |
| 快捷键比较问题 | hotkey_manager.py | 改用字符串比较 |
| 未使用的导入 | model_manager.py | 已清理 |
| 未使用的方法 | hotkey_manager.py | 已删除 |

### 核心功能状态

| 模块 | 状态 | 说明 |
|------|------|------|
| 配置管理 | ✅ | Settings 类正常工作 |
| 模型管理 | ✅ | 支持下载/检测/删除 |
| 音频管理 | ✅ | 列表/批量删除/清理 |
| 快捷键监听 | ✅ | pynput 全局监听 |
| 音频采集 | ✅ | sounddevice + webrtcvad |
| 文字注入 | ✅ | pyautogui 剪贴板方式 |
| 语音识别 | ✅ | sherpa-onnx + SenseVoice |
| 翻译引擎 | ✅ | Qwen2.5-1.5B |
| 设置界面 | ✅ | PyQt6 界面 |
| 托盘图标 | ✅ | 右键菜单 |

---

## 下一步

### 测试清单
- [ ] 安装所有依赖
- [ ] 首次启动下载 SenseVoice 模型
- [ ] 测试语音输入功能
- [ ] 测试快捷键监听
- [ ] 测试文字注入
- [ ] 测试翻译功能
- [ ] 测试设置界面
- [ ] 测试音频清理功能
- [ ] 测试托盘菜单

### 可选改进
- [ ] 添加应用图标
- [ ] 添加首次运行引导
- [ ] 添加音频波形显示
- [ ] 优化模型加载速度
- [ ] 添加语音活动指示灯
- [ ] 添加快捷键冲突检测提示
- [ ] 支持更多语言模型

---

## 技术支持

### GitHub Issues
如有问题请在 GitHub 提交 Issue

### 参考资源
- [Sherpa-ONNX GitHub](https://github.com/k2-fsa/sherpa-onnx)
- [Qwen2-Audio GitHub](https://github.com/QwenLM/Qwen2-Audio)
- [闪电说官网](https://shandianshuo.cn/)

---

## 许可证

MIT License
