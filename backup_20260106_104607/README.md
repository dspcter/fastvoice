# 快人快语 (FastVoice) 项目备份

## 备份信息
- **备份时间**: $(date '+%Y-%m-%d %H:%M:%S')
- **备份原因**: 双模式快捷键功能开发（左右 Option 键分离功能）

## 当前配置

### 快捷键配置
```json
{
  "voice_input": "left_alt",      // 左 Option - 语音输入（一次按键模式）
  "quick_translate": "right_alt"  // 右 Option - 翻译（双击+长按模式）
}
```

### 功能特性
1. **语音输入**：左 Option 键，一次按键触发
   - 按下开始录音
   - 松开后等待 200ms 收集尾音
   - 停止录音并进行 ASR 识别

2. **快速翻译**：右 Option 键，双击+长按触发
   - 第一次轻按（<150ms 释放）
   - 第二次长按（>350ms）
   - 松开后等待 200ms 收集尾音
   - 停止录音并翻译

3. **左右修饰键支持**：pynput 完全支持左右修饰键识别
   - 左/右 Option (⌥)
   - 左/右 Command (⌘)
   - 左/右 Control (⌃)
   - 左/右 Shift (⇧)

## 已修改的文件
- `core/hotkey_manager.py` - 支持双模式快捷键
- `config/constants.py` - 默认快捷键配置
- `config/settings.json` - 用户配置文件
- `test_key_listener.py` - 按键监听测试工具

## 已知问题
- 右 Option 键的双击模式可能存在超时问题
- 需要调整 FIRST_RELEASE_TIMEOUT 参数（当前 150ms）

## 技术栈
- Python 3.x
- pynput - 全局快捷键监听
- sherpa-onnx - 语音识别
- MarianMT - 翻译模型
- PyQt6 - GUI 框架

## 恢复方法
```bash
# 从备份恢复核心文件
cp -r backup_YYYYMMDD_HHMMSS/core/* ./
cp -r backup_YYYYMMDD_HHMMSS/config/* ./
cp -r backup_YYYYMMDD_HHMMSS/ui/* ./
```
