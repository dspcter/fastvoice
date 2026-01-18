#!/usr/bin/env python3
# test_injection.py - 文字注入功能测试工具
#
# 用于测试 macOS 原生按键模拟功能

import sys
import time
import logging

# 添加项目路径
sys.path.insert(0, '.')

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QComboBox, QSpinBox, QGroupBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

logging.basicConfig(level=logging.DEBUG)


class InjectionTester(QMainWindow):
    """文字注入测试工具"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("快人快语 - 文字注入测试工具")
        self.setGeometry(100, 100, 600, 500)

        # 初始化注入器
        from core.text_injector_macos import get_macos_injector, NATIVE_AVAILABLE
        self.injector = get_macos_injector()
        self.NATIVE_AVAILABLE = NATIVE_AVAILABLE

        self.setup_ui()
        self.log("测试工具已启动")

        # 显示注入器状态
        if self.NATIVE_AVAILABLE:
            if self.injector:
                self.log(f"✓ macOS 原生按键模拟器已加载")
                self.log(f"  事件源: {self.injector._event_source}")
                self.log(f"  组合键延迟: {self.injector._combo_delay}s")
                self.log(f"  按键后延迟: {self.injector._post_delay}s")
            else:
                self.log("✗ 按键模拟器初始化失败")
        else:
            self.log("✗ PyObjC 不可用")

    def setup_ui(self):
        """设置 UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        # 先创建日志输出框（避免按钮连接时未定义）
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(250)

        # 测试文本
        text_group = QGroupBox("测试文本")
        text_layout = QVBoxLayout()
        self.text_input = QTextEdit()
        self.text_input.setPlainText("测试文字123")
        self.text_input.setMaximumHeight(80)
        text_layout.addWidget(self.text_input)
        text_group.setLayout(text_layout)
        layout.addWidget(text_group)

        # 测试按钮
        button_group = QGroupBox("测试功能")
        button_layout = QVBoxLayout()

        # 1. 测试剪贴板
        btn_clipboard = QPushButton("1. 测试剪贴板操作")
        btn_clipboard.clicked.connect(self.test_clipboard)
        button_layout.addWidget(btn_clipboard)

        # 2. 测试 Command+V
        btn_cmdv = QPushButton("2. 测试 Command+V 模拟")
        btn_cmdv.clicked.connect(self.test_cmd_v)
        button_layout.addWidget(btn_cmdv)

        # 3. 测试完整注入
        btn_inject = QPushButton("3. 测试完整文字注入")
        btn_inject.clicked.connect(self.test_full_injection)
        button_layout.addWidget(btn_inject)

        # 4. 测试延迟设置
        delay_layout = QHBoxLayout()
        delay_layout.addWidget(QLabel("粘贴后延迟(毫秒):"))
        self.delay_spinbox = QSpinBox()
        self.delay_spinbox.setRange(100, 2000)
        self.delay_spinbox.setValue(300)
        self.delay_spinbox.setSuffix(" ms")
        delay_layout.addWidget(self.delay_spinbox)
        button_layout.addLayout(delay_layout)

        # 5. 清空日志
        btn_clear = QPushButton("清空日志")
        btn_clear.clicked.connect(self.log_output.clear)
        button_layout.addWidget(btn_clear)

        button_group.setLayout(button_layout)
        layout.addWidget(button_group)

        # 日志输出
        log_group = QGroupBox("日志输出")
        log_layout = QVBoxLayout()
        log_layout.addWidget(self.log_output)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        # 提示
        hint = QLabel("提示：点击测试按钮后，将光标放到任何文本输入框中查看效果")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        layout.addWidget(hint)

    def log(self, message):
        """添加日志"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_output.append(f"[{timestamp}] {message}")
        # 自动滚动到底部
        self.log_output.verticalScrollBar().setValue(
            self.log_output.verticalScrollBar().maximum()
        )

    def test_clipboard(self):
        """测试剪贴板操作"""
        import pyperclip

        text = self.text_input.toPlainText()

        self.log("=" * 50)
        self.log("测试 1: 剪贴板操作")
        self.log(f"测试文本: {text}")

        # 保存原剪贴板
        original = pyperclip.paste()
        self.log(f"原剪贴板长度: {len(original)} 字符")

        # 设置新内容
        pyperclip.copy(text)
        time.sleep(0.1)

        # 验证
        current = pyperclip.paste()
        if current == text:
            self.log(f"✓ 剪贴板设置成功")
        else:
            self.log(f"✗ 剪贴板设置失败: '{current}'")

        # 恢复
        pyperclip.copy(original)
        self.log("剪贴板已恢复")

    def test_cmd_v(self):
        """测试 Command+V 模拟"""
        if not self.injector:
            self.log("✗ 按键模拟器不可用")
            return

        self.log("=" * 50)
        self.log("测试 2: Command+V 模拟")
        self.log("3秒后将发送 Command+V...")
        self.log("请确保光标在文本输入框中")

        # 先设置剪贴板
        import pyperclip
        test_text = "【Command+V测试】"
        pyperclip.copy(test_text)
        self.log(f"剪贴板已设置为: {test_text}")

        time.sleep(3)

        # 发送 Command+V
        self.log("发送 Command+V...")
        result = self.injector.paste()

        if result:
            self.log("✓ Command+V 发送成功")
        else:
            self.log("✗ Command+V 发送失败")

    def test_full_injection(self):
        """测试完整文字注入"""
        if not self.injector:
            self.log("✗ 按键模拟器不可用")
            return

        text = self.text_input.toPlainText()

        self.log("=" * 50)
        self.log("测试 3: 完整文字注入流程")
        self.log(f"测试文本: {text}")
        self.log("3秒后将开始注入...")
        self.log("请确保光标在文本输入框中")

        time.sleep(3)

        # 获取延迟设置
        delay_ms = self.delay_spinbox.value()
        self.log(f"粘贴后延迟: {delay_ms}ms")

        # 临时修改延迟
        original_delay = self.injector._post_delay

        try:
            # 更新延迟
            self.injector._post_delay = delay_ms / 1000.0

            # 执行注入
            self.log("开始注入...")
            result = self.injector.paste_with_clipboard(text, verify=True)

            if result:
                self.log("✓ 文字注入成功")
            else:
                self.log("✗ 文字注入失败")

        finally:
            # 恢复延迟
            self.injector._post_delay = original_delay

    def test_direct_event(self):
        """直接测试 Quartz 事件"""
        from Quartz import (
            CGEventCreateKeyboardEvent,
            CGEventSetFlags,
            CGEventPost,
            CGEventSourceCreate,
            kCGHIDEventTap,
            kCGEventFlagMaskCommand,
        )

        self.log("=" * 50)
        self.log("测试 4: 直接 Quartz 事件")
        self.log("3秒后将发送 Command+V...")
        self.log("请确保光标在文本输入框中")

        time.sleep(3)

        # 设置剪贴板
        import pyperclip
        test_text = "【直接事件测试】"
        pyperclip.copy(test_text)
        self.log(f"剪贴板已设置为: {test_text}")

        # 创建事件
        event_source = CGEventSourceCreate(0)
        v_key = 0x6E

        self.log("创建键盘事件...")
        key_down = CGEventCreateKeyboardEvent(event_source, v_key, True)
        key_up = CGEventCreateKeyboardEvent(event_source, v_key, False)

        self.log("设置 Command 标志...")
        CGEventSetFlags(key_down, kCGEventFlagMaskCommand)
        CGEventSetFlags(key_up, kCGEventFlagMaskCommand)

        self.log("发送事件...")
        CGEventPost(kCGHIDEventTap, key_down)
        time.sleep(0.05)
        CGEventPost(kCGHIDEventTap, key_up)

        self.log("✓ 事件已发送")


def main():
    app = QApplication(sys.argv)
    window = InjectionTester()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
