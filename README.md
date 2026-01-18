# 快人快语 (FastVoice)

> 本地优先的 AI 语音输入法 - 毫秒响应，隐私安全

[![Version](https://img.shields.io/badge/version-1.4.7-blue.svg)](https://github.com/dspcter/fastvoice)
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
| 🍎 **原生体验** | macOS 原生键盘操作，可靠稳定 |
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
| **macOS 特定** | 需要 PyObjC（已包含在依赖中） |

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
| **快捷键监听** | PyObjC (macOS 原生) |
| **音频采集** | sounddevice + webrtcvad |
| **文字注入** | PyObjC Quartz CGEvent (macOS 原生) |
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
│   ├── hotkey_manager.py       # 全局快捷键管理
│   ├── pyobjc_keyboard_listener.py  # PyObjC 原生键盘监听 (macOS)
│   ├── audio_capture.py        # 音频采集 + VAD
│   ├── asr_engine.py           # SenseVoice 语音识别
│   ├── marianmt_engine.py      # MarianMT 翻译
│   ├── translate_engine.py     # Qwen2.5 翻译
│   ├── text_injector.py        # 文字注入器
│   ├── text_injector_macos.py  # macOS 原生按键模拟
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

### v1.4.7 (2026-01-18)

**🐛 致命 Bug 修复**
- 🐛 修复 V 键键码错误（0x76 → 0x09）
- 🐛 修复退出时连续输入 'v' 的问题
- ✅ 完善注入事件检测逻辑，防止应用监听到自己的 Command+V

**问题说明**
- 之前使用错误的键码 0x76（F17 键）检测注入事件
- 导致应用自己的 Command+V 注入没有被正确忽略
- 监听器接收到注入事件后触发热键回调，造成重复注入
- 现已修正为正确的 V 键键码 0x09

**影响范围**
- `core/pyobjc_keyboard_listener.py`

### v1.4.0 (2026-01-08)

**🎉 重大更新 - 完全迁移到 PyObjC 原生键盘操作**

**核心重构**
- ✨ 完全使用 PyObjC 进行键盘监听和模拟（macOS 原生）
- ✨ 使用 Quartz CGEvent API 实现可靠的按键模拟
- ✨ 修复组合键识别问题（Command+V 等快捷键）
- ✨ 修复 V 键 keycode 错误（0x6E → 0x09）

**依赖优化**
- 🗑️ 移除 pynput 依赖
- 🗑️ 移除 pyautogui 依赖
- ✅ PyObjC 成为唯一的键盘操作依赖

**新增模块**
- 📦 `core/text_injector_macos.py` - macOS 原生按键模拟器
- 📦 `core/pyobjc_keyboard_listener.py` - PyObjC 键盘监听器

**技术改进**
- 📝 使用正确的组合键序列（修饰键按下 → 主键按下 → 主键释放 → 修饰键释放）
- 🛡️ 内置注入事件过滤机制，防止监听器拦截自己的事件
- 📊 增强日志输出，便于调试
- 🔧 优化按键时序控制（combo_delay: 50ms, post_delay: 100ms）

**测试验证**
- ✅ PyObjC 文字注入正常工作
- ✅ Command+V 等组合键可靠识别
- ✅ 完全移除第三方键盘依赖

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

**A**: macOS 需要在「系统设置 → 隐私与安全性 → 辅助功能」中授权：
1. 打开「系统设置」
2. 进入「隐私与安全性」
3. 选择「辅助功能」
4. 找到「快人快语」并勾选

### Q: 文字注入失败怎么办？

**A**: v1.4.0 使用 macOS 原生 PyObjC 框架，通常不需要额外配置。如果遇到问题：
1. 确认已安装 PyObjC：`pip install PyObjC`
2. 检查是否有其他应用占用剪贴板
3. 查看日志文件 `logs/*.log` 获取详细错误信息

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
- [PyObjC](https://github.com/ronaldoussoren/pyobjc) - Python-Objective-C 桥接

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
