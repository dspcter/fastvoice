#!/usr/bin/env python3
"""
按键监听测试工具
用于测试 pynput 是否能够识别左右修饰键

功能:
1. 实时显示当前按下的所有按键
2. 特别标识左右 Command/Control/Alt/Shift 键
3. 显示按键事件的时间戳
4. 统计按键次数

使用方法:
    python3 test_key_listener.py

按 Ctrl+C 或 ESC 退出
"""

import sys
import time
from datetime import datetime
from pynput import keyboard
from pynput.keyboard import Key, KeyCode

# ANSI 颜色代码 - 高对比度配色
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    # 高对比度颜色
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    GREEN = '\033[32m'
    RED = '\033[31m'


# 左右修饰键映射
MODIFIER_KEYS = {
    Key.cmd_l: "左 Command (⌘)",
    Key.cmd_r: "右 Command (⌘)",
    Key.ctrl_l: "左 Control (⌃)",
    Key.ctrl_r: "右 Control (⌃)",
    Key.alt_l: "左 Option/Alt (⌥)",
    Key.alt_r: "右 Option/Alt (⌥)",
    Key.shift_l: "左 Shift (⇧)",
    Key.shift_r: "右 Shift (⇧)",
    Key.cmd: "Command (⌘)",
    Key.ctrl: "Control (⌃)",
    Key.alt: "Option/Alt (⌥)",
    Key.shift: "Shift (⇧)",
}


class KeyListenerTester:
    """按键监听测试器"""

    def __init__(self):
        self.pressed_keys = set()
        self.key_press_count = {}
        self.start_time = time.time()
        self.last_event_time = None

        # 清屏并显示标题
        self.print_header()

    def print_header(self):
        """打印标题"""
        print("\n" + "=" * 80)
        print(f"{Colors.BOLD}{Colors.CYAN}按键监听测试工具 - 左右修饰键识别测试{Colors.ENDC}")
        print("=" * 80)
        print(f"\n{Colors.BOLD}测试目标:{Colors.ENDC}")
        print("  • 验证 pynput 是否能识别左右修饰键")
        print("  • 实时显示按键按下/释放事件")
        print(f"\n{Colors.BOLD}测试重点:{Colors.ENDC}")
        print(f"  {Colors.YELLOW}• 请分别测试 左Command 和 右Command{Colors.ENDC}")
        print(f"  {Colors.YELLOW}• 请分别测试 左Option 和 右Option{Colors.ENDC}")
        print(f"  {Colors.YELLOW}• 请测试组合键（如 Command+Option）{Colors.ENDC}")
        print(f"\n{Colors.BOLD}退出方式:{Colors.ENDC}")
        print("  • 按 {Colors.BOLD}{Colors.RED}ESC{Colors.ENDC} 或 {Colors.BOLD}{Colors.RED}Ctrl+C{Colors.ENDC} 退出")
        print("\n" + "=" * 80 + "\n")

        print(f"{Colors.BOLD}{Colors.GREEN}开始监听...{Colors.ENDC}\n")

    def get_key_name(self, key):
        """获取按键的友好名称"""
        # 检查左右修饰键
        if key in MODIFIER_KEYS:
            return MODIFIER_KEYS[key]

        # 检查普通按键
        if isinstance(key, KeyCode):
            if key.char:
                return f"'{key.char}'"
            return f"KeyCode({key.vk})"

        if isinstance(key, Key):
            return str(key).replace("Key.", "")

        return str(key)

    def format_timestamp(self):
        """格式化时间戳"""
        now = datetime.now()
        return now.strftime("%H:%M:%S.%f")[:-3]

    def update_display(self):
        """更新显示"""
        # 清屏（移动光标到开头）
        sys.stdout.write("\033[H\033[J")

        # 重新打印标题（保持静态）
        self.print_header()

        # 统计信息
        elapsed = time.time() - self.start_time
        total_presses = sum(self.key_press_count.values())

        print(f"{Colors.BOLD}{Colors.BLUE}📊 统计信息{Colors.ENDC}")
        print(f"  运行时间: {elapsed:.1f} 秒")
        print(f"  总按键次数: {total_presses}")
        print()

        # 当前按下的键
        if self.pressed_keys:
            print(f"{Colors.BOLD}{Colors.GREEN}⌨️  当前按下的键:{Colors.ENDC}")
            for key in sorted(self.pressed_keys, key=lambda k: str(k)):
                key_name = self.get_key_name(key)

                # 高亮左右修饰键
                if key in [Key.cmd_l, Key.cmd_r]:
                    print(f"  {Colors.YELLOW}{Colors.BOLD}★ {key_name}{Colors.ENDC}")
                elif key in [Key.alt_l, Key.alt_r]:
                    print(f"  {Colors.CYAN}{Colors.BOLD}★ {key_name}{Colors.ENDC}")
                elif key in [Key.ctrl_l, Key.ctrl_r]:
                    print(f"  {Colors.MAGENTA}{Colors.BOLD}★ {key_name}{Colors.ENDC}")
                else:
                    print(f"  • {Colors.WHITE}{key_name}{Colors.ENDC}")
            print()
        else:
            print(f"{Colors.BOLD}当前按下的键:{Colors.ENDC} (无)")
            print()

        # 按键统计
        if self.key_press_count:
            print(f"{Colors.BOLD}{Colors.BLUE}📈 按键统计:{Colors.ENDC}")

            # 按次数排序
            sorted_keys = sorted(self.key_press_count.items(),
                               key=lambda x: x[1],
                               reverse=True)

            for key, count in sorted_keys[:20]:  # 只显示前20个
                key_name = self.get_key_name(key)

                # 高亮修饰键
                if key in [Key.cmd_l, Key.cmd_r]:
                    print(f"  {Colors.YELLOW}{Colors.BOLD}{key_name}: {count} 次{Colors.ENDC}")
                elif key in [Key.alt_l, Key.alt_r]:
                    print(f"  {Colors.CYAN}{key_name}: {count} 次{Colors.ENDC}")
                elif key in [Key.ctrl_l, Key.ctrl_r]:
                    print(f"  {Colors.MAGENTA}{key_name}: {count} 次{Colors.ENDC}")
                else:
                    print(f"  {Colors.WHITE}{key_name}: {count} 次{Colors.ENDC}")
            print()

        # 最后事件
        if self.last_event_time:
            print(f"{Colors.BOLD}最后事件:{Colors.ENDC} {self.last_event_time}")

        print("\n" + "-" * 80)
        print(f"{Colors.CYAN}提示: 分别测试左右修饰键，观察是否能正确识别{Colors.ENDC}")

    def on_press(self, key):
        """按键按下事件"""
        timestamp = self.format_timestamp()
        key_name = self.get_key_name(key)

        # 记录按键
        self.pressed_keys.add(key)
        self.key_press_count[key] = self.key_press_count.get(key, 0) + 1
        self.last_event_time = f"[{timestamp}] 按下: {key_name}"

        # 特别处理修饰键
        if key in [Key.cmd_l, Key.cmd_r, Key.alt_l, Key.alt_r]:
            side = "左" if "_l" in str(key) else "右"
            key_type = "Command" if "cmd" in str(key) else "Option"
            print(f"{Colors.GREEN}{Colors.BOLD}✓ 检测到: {side}{key_type}{Colors.ENDC}")

        # 更新显示
        self.update_display()

    def on_release(self, key):
        """按键释放事件"""
        timestamp = self.format_timestamp()
        key_name = self.get_key_name(key)

        # 移除按键
        if key in self.pressed_keys:
            self.pressed_keys.remove(key)
        self.last_event_time = f"[{timestamp}] 释放: {key_name}"

        # 检查是否退出
        if key == Key.esc:
            print(f"\n{Colors.GREEN}{Colors.BOLD}检测到 ESC 键，退出程序...{Colors.ENDC}")
            return False  # 停止监听

        # 更新显示
        self.update_display()

    def start(self):
        """启动监听"""
        print(f"{Colors.BOLD}{Colors.CYAN}监听器启动中...{Colors.ENDC}\n")

        # 稍微延迟，让用户看到启动信息
        time.sleep(0.5)

        # 启动监听器
        with keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release,
            suppress=False  # 不拦截按键，让系统正常处理
        ) as listener:
            listener.join()


def main():
    """主函数"""
    tester = KeyListenerTester()

    try:
        tester.start()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.GREEN}{Colors.BOLD}程序已退出 (Ctrl+C){Colors.ENDC}")
    except Exception as e:
        print(f"\n\n{Colors.RED}{Colors.BOLD}错误: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
