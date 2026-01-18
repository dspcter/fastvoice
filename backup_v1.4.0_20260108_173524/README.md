# 快人快语 (FastVoice)

> 本地优先的 AI 语音输入法 - 毫秒响应，隐私安全

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 🎤 **语音输入** | 按住快捷键说话，松开即转换为文字 |
| 🌐 **智能翻译** | 本地离线翻译，支持中英互译 |
| 🔢 **数字转换** | 智能识别并转换中文数字（幺三八→138、零一二三→0123） |
| ⚡ **极速响应** | 端侧模型，毫秒级识别速度 |
| 🔒 **隐私安全** | 音频本地处理，不上传云端 |
| ⚙️ **灵活配置** | 自定义快捷键、麦克风、翻译模式 |
| 📁 **音频管理** | 自动清理和管理录音文件 |

---

## 📋 系统要求

| 项目 | 要求 |
|------|------|
| **操作系统** | macOS 10.15+ / Windows 10+ |
| **Python** | 3.10+ |
| **内存** | 8GB+ (推荐 16GB) |
| **磁盘空间** | 5GB+ (模型文件) |

---

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/dspcter/ai-automation-tools.git
cd ai-automation-tools/快人快语

# 安装依赖
pip install -r requirements.txt

# 启动程序
python main.py
```

### 首次运行

首次启动时会自动：
1. 下载 SenseVoice 语音识别模型 (~700MB)
2. 打开设置窗口进行初始配置
3. 引导完成自动创建标记文件

---

## ⌨️ 使用说明

### 默认快捷键

| 功能 | macOS | Windows |
|------|-------|---------|
| **语音输入** | 按住 `Option` | 按住 `Right Ctrl` |
| **快速翻译** | 按住 `Right Cmd` | 按住 `Right Cmd` |

### 使用示例

```
1. 按住 Option 键
2. 说话："今天天气真不错"
3. 松开 Option 键
4. 文字自动注入到光标位置
```

### 数字转换示例

| 输入 | 输出 | 说明 |
|------|------|------|
| 幺三八 | 138 | 电话号码 |
| 零一二三 | 0123 | 保留前导零 |
| 一二三四五 | 12345 | 连续数字 |
| 十一万 | 110000 | 大单位 |
| 一个亿 | 100000000 | 亿单位 |

---

## 🛠️ 技术栈

| 模块 | 技术方案 |
|------|---------|
| **语音识别** | sherpa-onnx + SenseVoice-small |
| **翻译引擎** | MarianMT (离线) / Qwen2.5-1.5B |
| **数字转换** | cn2an (自定义增强) |
| **快捷键监听** | pynput |
| **音频采集** | sounddevice + webrtcvad |
| **文字注入** | pyautogui (剪贴板方式) |
| **设置界面** | PyQt6 |
| **打包工具** | PyInstaller |

---

## 📁 项目结构

```
快人快语/
├── main.py                     # 主程序入口
├── requirements.txt            # 依赖列表
├── README.md                   # 项目说明
├── PRD.md                      # 产品需求文档
├── PROJECT_SUMMARY.md          # 项目总结
├── 安装说明.md                  # 安装指南
│
├── core/                       # 核心功能模块
│   ├── __init__.py
│   ├── hotkey_manager.py       # 全局快捷键监听
│   ├── audio_capture.py        # 音频采集 + VAD
│   ├── asr_engine.py           # SenseVoice 语音识别
│   ├── marianmt_engine.py      # MarianMT 翻译
│   ├── translate_engine.py     # Qwen2.5 翻译
│   ├── text_injector.py        # 文字注入
│   └── text_postprocessor.py    # 文本后处理 + 数字转换
│
├── models/                     # 模型管理
│   ├── __init__.py
│   ├── model_manager.py        # 模型下载/管理/检测
│   └── models/                 # 本地模型存储目录
│       ├── asr/               # 语音识别模型
│       └── translation/       # 翻译模型
│
├── ui/                         # 用户界面
│   ├── __init__.py
│   ├── settings_window.py      # PyQt6 设置窗口
│   └── first_run_wizard.py     # 首次运行向导
│
├── config/                     # 配置管理
│   ├── __init__.py
│   ├── constants.py            # 常量定义
│   └── settings.py             # 配置读写
│
├── storage/                    # 数据存储
│   ├── __init__.py
│   └── audio_manager.py        # 音频文件管理
│
├── audio/recordings/           # 录音文件存储
├── assets/                     # 资源文件 (图标)
└── logs/                       # 日志文件
```

---

## ⚙️ 配置说明

配置文件位于 `config/settings.json`:

```json
{
  "hotkeys": {
    "voice_input": "option",
    "quick_translate": "right_cmd"
  },
  "audio": {
    "sample_rate": 16000,
    "vad_threshold": 500
  },
  "translation": {
    "mode": "button",
    "target_language": "en",
    "source_language": "zh"
  },
  "cleanup": {
    "enabled": true,
    "days": 7
  }
}
```

### 快捷键配置

支持的快捷键格式：
- 单键: `fn`, `ctrl`, `alt`, `shift`, `cmd`
- 组合键: `ctrl+shift+t`, `cmd+space`
- 修饰键: `right_ctrl`, `right_alt`, `right_cmd`

---

## 🔧 开发

### 运行开发模式

```bash
cd 快人快语
python main.py
```

### 打包应用

```bash
# macOS
chmod +x build.sh
./build.sh

# Windows
build.bat
```

### 运行测试

```bash
# 测试语音识别
python test_dependencies.py

# 测试翻译引擎
python test_marianmt.py

# 测试数字转换
python3 -c "import cn2an; print(cn2an.transform('幺三八零一二三'))"
```

---

## 📝 更新日志

### v1.2.1 (2026-01-06)

**🎉 重大更新 - 快捷键系统全面重构**

**新功能**
- ✨ 双击+长按触发模式（翻译功能防误触）
- ✨ macOS 左右 Option 键独立识别和映射
- ✨ 尾音收集机制（松开后延迟 200ms 收集尾音）
- ✨ Watchdog 超时保护（10秒强制回 IDLE）
- ✨ Listener 静默失效检测和自动恢复
- ✨ ASR Worker 异步处理（独立线程，不阻塞 UI）
- ✨ 内存管理器（定期自动 GC，防止内存泄漏）
- ✨ Session 机制防止旧任务覆盖新任务

**状态机架构**
- 完整的状态机实现（IDLE → RECORDING → TAIL_COLLECTING → IDLE）
- 线程安全的状态锁（RLock）
- 防抖机制（50ms）
- 状态转换合法性验证

**核心改进**
- 重构 `hotkey_manager.py`（状态机架构）
- 重构 `main.py`（优化状态机流程）
- 新增 `core/asr_worker.py`（异步 ASR 处理）
- 新增 `core/memory_manager.py`（内存管理）
- 新增 `core/exceptions.py`（自定义异常）
- 新增 `core/audio/` 目录（录音相关模块）

**Bug 修复**
- 🐛 修复设置窗口打开时快捷键失效的问题
- 🐛 修复 macOS 右 Option 键无法监听的问题
- 🐛 修复状态机死锁问题（使用 RLock 替代 Lock）
- 🐛 修复 Listener 静默失效无法检测的问题
- 🐛 修复音频文件删除失败的问题

**默认快捷键调整**
- macOS: `left_alt`（语音输入）、`right_alt`（翻译）
- Windows: `right_ctrl`（语音输入）、`ctrl+shift+t`（翻译）

### v1.0.1 (2026-01-02)

**新功能**
- ✨ 智能中文数字转换（cn2an 集成）
- 🔢 支持"幺"→"1"转换
- 🔢 保留前导零（零一二三→0123）
- 🔢 连续数字转换（一二三四五→12345）

**修复**
- 🐛 修复 Right Command 键监听问题
- 🐛 修复音频文件删除功能
- 🐛 优化快捷键映射逻辑

---

## ❓ 常见问题

### Q: 首次启动提示权限错误？

**A**: macOS 需要在「系统设置 → 隐私与安全性 → 辅助功能」中授权

### Q: 模型下载失败？

**A**:
1. 检查网络连接
2. 手动下载：
   ```bash
   # SenseVoice 模型
   wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2
   tar -xf sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2
   mv sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/* models/models/asr/sense-voice/
   ```

### Q: 快捷键冲突？

**A**: 在设置窗口中自定义其他快捷键组合

### Q: 数字转换不工作？

**A**:
1. 确认已安装 `cn2an` 库：`pip install cn2an`
2. 检查日志文件 `logs/*.log`

---

## 🙏 致谢

本项目基于以下优秀的开源项目：

- [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx) - 语音识别框架
- [Qwen2.5](https://github.com/QwenLM/Qwen2.5) - 通义千问大模型
- [MarianMT](https://github.com/Helsinki-NLP/MarianMT) - 神经机器翻译
- [cn2an](https://github.com/Ailln/cn2an) - 中文数字转换工具
- [pynput](https://github.com/moses-palmer/pynput) - 全局快捷键监听

**产品灵感**: 闪电说

---

## 📄 许可证

MIT License

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📮 联系方式

- GitHub Issues: [提交问题](https://github.com/dspcter/ai-automation-tools/issues)
