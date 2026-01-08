# 快人快语 v1.2.1 更新日志

**发布日期**: 2026-01-06
**版本号**: v1.2.1

---

## 🎉 重大更新

### 1. 快捷键系统全面重构

**两种触发模式支持**:
- **一次按键模式**（语音输入）: 按下 Option 开始录音，松开停止
- **双击+长按模式**（翻译）: 防误触的精确触发机制
  - 第一次快速释放（<300ms）
  - 两次按键间隔（<800ms）
  - 第二次长按确认（>300ms）

**新增功能**:
- ✅ macOS 左右 Option 键独立识别
- ✅ 尾音收集机制（松开后延迟 200ms 收集尾音）
- ✅ 防抖机制（50ms）
- ✅ 幂等性保证（重复 keydown 忽略）
- ✅ Watchdog 超时保护（10秒强制回 IDLE）
- ✅ Listener 静默失效检测和自动恢复

### 2. 状态机架构优化

**新增状态**:
```
IDLE → VOICE_RECORDING → VOICE_TAIL_COLLECTING → IDLE
IDLE → WAIT_FIRST_RELEASE → WAIT_SECOND_KEY → WAIT_LONG_PRESS → TRANSLATE_RECORDING → TRANSLATE_TAIL_COLLECTING → IDLE
```

**状态机特性**:
- 状态转换合法性验证
- 线程安全的状态锁（RLock）
- 异常时自动回 IDLE
- Watchdog 超时强制重置

### 3. ASR Worker 异步处理

**核心改进**:
- ✅ 独立线程处理语音识别（不阻塞 UI）
- ✅ Session 机制防止旧任务覆盖新任务
- ✅ 模型预加载和预热
- ✅ 线程安全的信号机制（Qt Signal）
- ✅ 自定义异常处理（静音/空结果）

### 4. 内存管理系统

**新增功能**:
- ✅ 定期内存自动清理（Python GC）
- ✅ 内存使用统计和监控
- ✅ ASR 模型卸载和重载
- ✅ 防止内存泄漏机制

### 5. 设置窗口优化

**修复问题**:
- ✅ 修复设置窗口打开时快捷键失效的问题
- ✅ 清空按键状态避免状态不同步
- ✅ 设置窗口不阻塞主应用事件循环

---

## 🔧 技术改进

### 核心模块

| 模块 | 改进 |
|------|------|
| `hotkey_manager.py` | 重构为状态机架构，新增双击+长按模式 |
| `asr_engine.py` | 新增音频质量检测，自定义异常类型 |
| `asr_worker.py` | 新增 ASR Worker 异步处理模块 |
| `memory_manager.py` | 新增内存管理器 |
| `main.py` | 优化状态机流程，修复线程安全问题 |

### 配置更新

**默认快捷键**:
- macOS: `left_alt`（语音输入）、`right_alt`（翻译）
- Windows: `right_ctrl`（语音输入）、`ctrl+shift+t`（翻译）

**新增配置**:
- `injection.method`: 文字注入方式（clipboard/typing/win32_native）

---

## 🐛 Bug 修复

1. ✅ 修复 macOS 右 Option 键无法监听的问题
2. ✅ 修复音频文件删除失败的问题
3. ✅ 修复设置窗口打开后快捷键失效的问题
4. ✅ 修复状态机死锁问题（使用 RLock 替代 Lock）
5. ✅ 修复 Listener 静默失效无法检测的问题

---

## 📊 性能优化

1. **响应速度**: 快捷键检测延迟 < 50ms
2. **尾音收集**: 200ms 延迟，避免截断语音
3. **内存占用**: 定期自动 GC，防止内存泄漏
4. **启动速度**: ASR 模型预热，首次识别更快

---

## 📝 已知问题

1. macOS 上需要在「系统设置 → 隐私与安全性 → 辅助功能」中授权
2. Windows 原生注入（win32_native）仅支持 Windows 平台
3. 翻译模型首次加载较慢（约 5-10 秒）

---

## 📦 备份说明

**备份内容**:
- ✅ 所有源代码文件
- ✅ 配置文件（settings.json）
- ✅ requirements.txt
- ✅ README.md
- ✅ 文档（docs/）

**已排除**:
- ❌ models/models/（模型文件，约 4GB，需单独下载）
- ❌ audio/（录音文件）
- ❌ logs/（日志文件）
- ❌ backup_*（之前的备份）

**备份大小**: 约 12MB（压缩后）

---

## 🚀 升级说明

从 v1.0.1 升级到 v1.2.1:

1. **配置兼容性**: 配置文件向后兼容，自动迁移
2. **模型文件**: 无需重新下载 ASR 模型
3. **快捷键**: 建议在设置中重新配置快捷键以使用新功能
4. **权限**: macOS 用户需要重新授权辅助功能权限

---

## 🙏 致谢

本项目基于以下优秀的开源项目：
- [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx) - 语音识别框架
- [Qwen2.5](https://github.com/QwenLM/Qwen2.5) - 通义千问大模型
- [MarianMT](https://github.com/Helsinki-NLP/MarianMT) - 神经机器翻译
- [pynput](https://github.com/moses-palmer/pynput) - 全局快捷键监听

**产品灵感**: 闪电说

---

*生成日期: 2026-01-06 17:03*
