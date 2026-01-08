#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyObjC 原生键盘监听器 - 单元测试
"""

import sys
import time
import logging
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.native_keyboard_listener import NativeKeyboardListener

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


class TestNativeListener:
    """原生监听器测试"""

    def __init__(self):
        self.key_press_count = 0
        self.key_release_count = 0
        self.last_key = None

    def on_press(self, key):
        """按键按下回调"""
        self.key_press_count += 1
        self.last_key = key
        logger.info(f"✓ 按下: {key}")

    def on_release(self, key):
        """按键释放回调"""
        self.key_release_count += 1
        logger.info(f"✓ 松开: {key}")

    def test_startup(self):
        """测试启动"""
        logger.info("\n" + "="*60)
        logger.info("测试 1: 启动测试")
        logger.info("="*60)

        listener = NativeKeyboardListener(
            on_press=self.on_press,
            on_release=self.on_release,
        )

        start = time.time()
        success = listener.start()
        startup_time = (time.time() - start) * 1000

        assert success, "启动失败"
        assert listener.is_alive(), "监听器未运行"

        stats = listener.get_stats()
        logger.info(f"✓ 启动成功")
        logger.info(f"  启动耗时: {stats['startup_time_ms']:.2f}ms")
        logger.info(f"  监听器存活: {listener.is_alive()}")

        listener.stop()

        return True

    def test_listen(self):
        """测试监听功能"""
        logger.info("\n" + "="*60)
        logger.info("测试 2: 监听功能测试")
        logger.info("="*60)

        listener = NativeKeyboardListener(
            on_press=self.on_press,
            on_release=self.on_release,
        )

        if not listener.start():
            logger.error("启动失败")
            return False

        logger.info("监听中... 请按 Option 键测试 (5秒)")
        logger.info("-"*60)

        time.sleep(5)

        listener.stop()

        stats = listener.get_stats()
        logger.info("-"*60)
        logger.info(f"✓ 测试完成")
        logger.info(f"  处理事件: {stats['events_processed']} 个")
        logger.info(f"  按下次数: {self.key_press_count}")
        logger.info(f"  松开次数: {self.key_release_count}")

        return True

    def test_performance(self):
        """测试性能"""
        logger.info("\n" + "="*60)
        logger.info("测试 3: 性能测试")
        logger.info("="*60)

        # 多次启动测试
        startup_times = []
        iterations = 10

        for i in range(iterations):
            listener = NativeKeyboardListener(
                on_press=self.on_press,
                on_release=self.on_release,
            )

            success = listener.start()
            assert success, f"第 {i+1} 次启动失败"

            stats = listener.get_stats()
            startup_times.append(stats['startup_time_ms'])

            listener.stop()
            time.sleep(0.1)  # 冷却

        # 计算统计数据
        import statistics
        p50 = statistics.median(startup_times)
        p95 = max(startup_times)

        logger.info(f"✓ 性能测试完成 ({iterations} 次启动)")
        logger.info(f"  P50 启动时间: {p50:.2f}ms")
        logger.info(f"  P95 启动时间: {p95:.2f}ms")
        logger.info(f"  平均启动时间: {sum(startup_times)/len(startup_times):.2f}ms")

        # 验证性能目标
        assert p50 < 100, f"P50 启动时间 {p50}ms 超过目标 100ms"

        return True


def main():
    """主测试函数"""
    logger.info("\n" + "="*60)
    logger.info("PyObjC 原生键盘监听器 - 测试套件")
    logger.info("="*60)

    tester = TestNativeListener()

    tests = [
        ("启动测试", tester.test_startup),
        ("监听功能测试", tester.test_listen),
        ("性能测试", tester.test_performance),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
                logger.info(f"✓ {name} 通过")
            else:
                failed += 1
                logger.error(f"✗ {name} 失败")
        except Exception as e:
            failed += 1
            logger.error(f"✗ {name} 异常: {e}", exc_info=True)

    logger.info("\n" + "="*60)
    logger.info(f"测试结果: {passed} 通过, {failed} 失败")
    logger.info("="*60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
