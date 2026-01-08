#!/usr/bin/env python3
# test_pyobjc_v1.3.3.py
# 测试 PyObjC 原生键盘监听器 v1.3.3
#
# 测试目标：
# 1. 验证左 Option 键检测
# 2. 验证右 Option 键检测
# 3. 验证其他修饰键检测
# 4. 验证性能指标
# 5. 验证退出时无崩溃（v1.3.3 关键修复：__del__ 方法）

import logging
import sys
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.pyobjc_keyboard_listener import PyObjCKeyboardListener

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


# ==================== 测试统计 ====================

class TestStats:
    """测试统计"""

    def __init__(self):
        self.press_count = {}  # key_name -> count
        self.release_count = {}  # key_name -> count
        self.left_alt_pressed = 0
        self.right_alt_pressed = 0
        self.start_time = None
        self.end_time = None

    def record_press(self, key_name: str):
        """记录按键按下"""
        if key_name not in self.press_count:
            self.press_count[key_name] = 0
        self.press_count[key_name] += 1

        # 特殊计数
        if key_name == "alt_l":
            self.left_alt_pressed += 1
        elif key_name == "alt_r":
            self.right_alt_pressed += 1

    def record_release(self, key_name: str):
        """记录按键释放"""
        if key_name not in self.release_count:
            self.release_count[key_name] = 0
        self.release_count[key_name] += 1

    def print_summary(self):
        """打印测试总结"""
        print("\n" + "=" * 60)
        print("测试总结")
        print("=" * 60)

        # 时间统计
        if self.start_time and self.end_time:
            duration = self.end_time - self.start_time
            print(f"测试时长: {duration:.1f} 秒")

        # 按键统计
        print("\n按键按下次数:")
        if self.press_count:
            for key_name, count in sorted(self.press_count.items()):
                print(f"  {key_name}: {count} 次")
        else:
            print("  (无)")

        print("\n按键释放次数:")
        if self.release_count:
            for key_name, count in sorted(self.release_count.items()):
                print(f"  {key_name}: {count} 次")
        else:
            print("  (无)")

        # Option 键特别统计
        print("\nOption 键统计:")
        print(f"  左 Option (alt_l): {self.left_alt_pressed} 次")
        print(f"  右 Option (alt_r): {self.right_alt_pressed} 次")

        # 验证结果
        print("\n验证结果:")
        if self.left_alt_pressed > 0:
            print("  ✓ 左 Option 键检测正常")
        else:
            print("  ✗ 左 Option 键未检测到")

        if self.right_alt_pressed > 0:
            print("  ✓ 右 Option 键检测正常")
        else:
            print("  ✗ 右 Option 键未检测到")

        print("=" * 60)


# ==================== 测试主程序 ====================

def main():
    """主测试函数"""
    print("=" * 60)
    print("PyObjC 原生键盘监听器 v1.3.3 - 功能测试")
    print("=" * 60)

    # 创建统计对象
    stats = TestStats()

    # 创建监听器
    print("\n创建监听器...")
    listener = PyObjCKeyboardListener(
        on_press=lambda key: (
            logger.info(f"🔵 按下: {key}"),
            stats.record_press(key)
        )[-1],  # 只返回 None
        on_release=lambda key: (
            logger.info(f"⚪ 松开: {key}"),
            stats.record_release(key)
        )[-1],
    )

    # 启动监听器
    print("启动监听器...")
    if not listener.start():
        print("❌ 启动失败")
        return 1

    print(f"✓ 启动成功 (耗时: {listener.get_stats()['startup_time_ms']:.2f}ms)")
    print("\n" + "=" * 60)
    print("测试说明")
    print("=" * 60)
    print("请依次测试以下按键（每个按键测试3次）：")
    print("  1. 左 Option 键")
    print("  2. 右 Option 键")
    print("  3. 左 Command 键")
    print("  4. 右 Command 键")
    print("  5. 左 Shift 键")
    print("  6. 右 Shift 键")
    print("  7. 左 Control 键")
    print("  8. 右 Control 键")
    print("\n测试完成后按 Ctrl+C 退出")
    print("=" * 60)

    # 运行测试
    stats.start_time = time.time()
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\n收到退出信号...")
        stats.end_time = time.time()

    finally:
        # 停止监听器
        print("\n停止监听器...")
        listener.stop()

        # 输出统计
        listener_stats = listener.get_stats()
        print(f"\n监听器统计:")
        print(f"  处理事件数: {listener_stats['events_processed']}")
        print(f"  回调错误数: {listener_stats['callback_errors']}")

        # 打印测试总结
        stats.print_summary()

        print("\n✓ 测试完成")
        return 0


if __name__ == "__main__":
    sys.exit(main())
