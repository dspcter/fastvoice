# core/native_keyboard_listener.py
# PyObjC 原生键盘监听器 - 原型实现
#
# 目标：替换 pynput，实现：
# 1. 更快的启动速度（目标 <100ms）
# 2. 更低的内存占用（目标 <5MB）
# 3. 完全的线程安全（解决 TSM API 问题）
# 4. 可控的资源管理（无泄漏）

import ctypes
import logging
import queue
import threading
import time
from typing import Callable, Dict, Optional, Set, Tuple

from Quartz import (
    CGEventTapCreate,
    CGEventTapEnable,
    CGEventGetFlags,
    CGEventGetIntegerValueField,
    CGEventGetType,
    CGEventKeyboardGetUnicodeString,
    CGEventMaskBit,
    CGEventPost,
    kCGEventKeyDown,
    kCGEventKeyUp,
    kCGEventFlagsChanged,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskControl,
    kCGEventFlagMaskShift,
    kCGHeadInsertEventTap,
    kCGSessionEventTap,
    kCGEventTapOptionListenOnly,
    kCGEventTapOptionDefault,
    kCGHIDEventTap,
    kCGKeyboardEventKeycode,
)

from CoreFoundation import (
    CFRelease,
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    CFRunLoopRemoveSource,
    CFRunLoopRun,
    CFRunLoopStop,
    CFMachPortCreateRunLoopSource,
    kCFRunLoopDefaultMode,
)

from pynput._util.darwin import (
    keycode_context,
    keycode_to_string,
)

logger = logging.getLogger(__name__)


# ==================== 常量定义 ====================

# macOS 系统定义事件（媒体键等）
NSSystemDefined = 14  # 从 pynput 获取


# ==================== 键码映射 ====================

# 从 pynput 借鉴的键码定义
class KeyCode:
    """键盘按键码"""

    # 修饰键
    ALT_L = 0x3A
    ALT_R = 0x3D
    CMD_L = 0x37
    CMD_R = 0x36
    CTRL_L = 0x3B
    CTRL_R = 0x3E
    SHIFT_L = 0x38
    SHIFT_R = 0x3C

    # 功能键
    ENTER = 0x24
    ESC = 0x35
    SPACE = 0x31
    TAB = 0x30
    BACKSPACE = 0x33

    # 方向键
    UP = 0x7E
    DOWN = 0x7D
    LEFT = 0x7B
    RIGHT = 0x7C


class Key:
    """特殊按键枚举"""

    alt = KeyCode.from_vk = lambda vk: KeyCode
    alt_l = KeyCode.ALT_L
    alt_r = KeyCode.ALT_R
    cmd = KeyCode.CMD_L
    cmd_l = KeyCode.CMD_L
    cmd_r = KeyCode.CMD_R
    ctrl = KeyCode.CTRL_L
    ctrl_l = KeyCode.CTRL_L
    ctrl_r = KeyCode.CTRL_R
    shift = KeyCode.SHIFT_L
    shift_l = KeyCode.SHIFT_L
    shift_r = KeyCode.SHIFT_R


# ==================== 辅助函数 ====================

def keycode_to_key_name(keycode: int) -> str:
    """将键码转换为键名（用于日志）"""

    # 修饰键
    if keycode == KeyCode.ALT_L:
        return "left_alt"
    elif keycode == KeyCode.ALT_R:
        return "right_alt"
    elif keycode == KeyCode.CMD_L:
        return "left_cmd"
    elif keycode == KeyCode.CMD_R:
        return "right_cmd"
    elif keycode == KeyCode.CTRL_L:
        return "left_ctrl"
    elif keycode == KeyCode.CTRL_R:
        return "right_ctrl"
    elif keycode == KeyCode.SHIFT_L:
        return "left_shift"
    elif keycode == KeyCode.SHIFT_R:
        return "right_shift"
    else:
        return f"key_{keycode}"


# ==================== 核心监听器 ====================

class NativeKeyboardListener:
    """
    PyObjC 原生键盘监听器

    核心特性：
    1. TSM API 在主线程调用，无线程安全问题
    2. 显式资源管理，正确调用 CFRelease
    3. 线程安全队列通信
    4. 详细的性能监控和日志

    性能目标：
    - 启动时间: <100ms (pynput: ~508ms)
    - 事件延迟: P99 <3ms (pynput: ~5.2ms)
    - 内存占用: <5MB (pynput: ~8-12MB)
    """

    def __init__(
        self,
        on_press: Optional[Callable] = None,
        on_release: Optional[Callable] = None,
        suppress: bool = False,
    ):
        """
        初始化监听器

        Args:
            on_press: 按键按下回调 (参数: key_name)
            on_release: 按键释放回调 (参数: key_name)
            suppress: 是否拦截事件（不传递给其他应用）
        """
        self.on_press = on_press
        self.on_release = on_release
        self.suppress = suppress

        # Event Tap 相关
        self._tap = None
        self._loop_source = None
        self._loop = None

        # 监听线程
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # 键盘上下文（在主线程初始化）
        self._keycode_context = None
        self._keyboard_type = None

        # 线程安全的事件队列
        self._event_queue = queue.Queue()

        # 修饰键状态追踪
        self._modifier_flags: int = 0

        # 性能统计
        self._stats = {
            "events_processed": 0,
            "events_dropped": 0,
            "callback_errors": 0,
            "last_event_time": None,
            "startup_time_ms": 0,
        }

        logger.info("NativeKeyboardListener 初始化完成")

    def start(self) -> bool:
        """
        启动监听器

        Returns:
            是否启动成功
        """
        if self._running:
            logger.warning("监听器已在运行")
            return True

        start_time = time.perf_counter()

        try:
            # 1. 在主线程加载键盘上下文（解决 TSM 线程问题）
            if not self._load_keycode_context():
                logger.error("加载键盘上下文失败")
                return False

            # 2. 创建 Event Tap
            if not self._create_event_tap():
                logger.error("创建 Event Tap 失败")
                return False

            # 3. 启动监听线程
            self._running = True
            self._thread = threading.Thread(
                target=self._run_event_loop,
                name="NativeKeyboardListener",
                daemon=False,  # 非守护线程，确保正确清理
            )
            self._thread.start()

            # 4. 等待线程启动（最多 1 秒）
            deadline = time.time() + 1.0
            while self._loop is None and time.time() < deadline:
                time.sleep(0.01)

            if self._loop is None:
                logger.error("监听线程启动超时")
                self.stop()
                return False

            # 记录启动时间
            startup_time = (time.perf_counter() - start_time) * 1000
            self._stats["startup_time_ms"] = startup_time

            logger.info(f"✓ 监听器启动成功 (耗时: {startup_time:.2f}ms)")
            return True

        except Exception as e:
            logger.error(f"启动监听器失败: {e}", exc_info=True)
            self.stop()
            return False

    def stop(self) -> None:
        """停止监听器"""
        if not self._running:
            return

        logger.info("停止监听器...")
        self._running = False

        # 停止 Run Loop
        if self._loop is not None:
            try:
                CFRunLoopStop(self._loop)
            except Exception as e:
                logger.warning(f"停止 Run Loop 失败: {e}")

        # 等待线程结束（最多 2 秒）
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                logger.warning("监听线程停止超时")

        # 清理资源
        self._cleanup_resources()

        logger.info("监听器已停止")

    def is_alive(self) -> bool:
        """检查监听器是否存活"""
        return self._running and self._thread is not None and self._thread.is_alive()

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            **self._stats,
            "is_alive": self.is_alive(),
            "queue_size": self._event_queue.qsize(),
        }

    # ==================== 内部方法 ====================

    def _load_keycode_context(self) -> bool:
        """
        加载键盘上下文（在主线程调用）

        这是关键：TSM API 必须在主线程调用！

        Returns:
            是否成功
        """
        try:
            # 验证当前在主线程
            if threading.current_thread() is not threading.main_thread():
                logger.warning("⚠️ 警告：_load_keycode_context 不在主线程调用！")

            # 使用 pynput 的 keycode_context（已验证正确）
            with keycode_context() as context:
                self._keycode_context = context
                self._keyboard_type = context[0]

            logger.debug(f"键盘上下文加载成功 (type: {self._keyboard_type})")
            return True

        except Exception as e:
            logger.error(f"加载键盘上下文失败: {e}", exc_info=True)
            return False

    def _create_event_tap(self) -> bool:
        """
        创建 Event Tap

        Returns:
            是否成功
        """
        try:
            # 定义事件掩码
            event_mask = (
                CGEventMaskBit(kCGEventKeyDown)
                | CGEventMaskBit(kCGEventKeyUp)
                | CGEventMaskBit(kCGEventFlagsChanged)
            )

            # 创建 Event Tap
            self._tap = CGEventTapCreate(
                kCGSessionEventTap,
                kCGHeadInsertEventTap,
                kCGEventTapOptionListenOnly if not self.suppress else kCGEventTapOptionDefault,
                event_mask,
                self._event_callback,
                None,
            )

            if self._tap is None:
                # 可能需要辅助功能权限
                logger.error("无法创建 Event Tap（可能需要辅助功能权限）")
                return False

            logger.debug("Event Tap 创建成功")
            return True

        except Exception as e:
            logger.error(f"创建 Event Tap 失败: {e}", exc_info=True)
            return False

    def _run_event_loop(self) -> None:
        """
        运行事件循环（在专用线程中）

        这是监听器的核心循环
        """
        thread_id = threading.get_ident()
        logger.info(f"事件循环线程启动 (thread_id: {thread_id})")

        try:
            # 获取当前线程的 Run Loop
            self._loop = CFRunLoopGetCurrent()

            # 创建 Run Loop Source
            self._loop_source = CFMachPortCreateRunLoopSource(None, self._tap, 0)

            # 添加到 Run Loop
            CFRunLoopAddSource(
                self._loop,
                self._loop_source,
                kCFRunLoopDefaultMode
            )

            # 启用 Event Tap
            CGEventTapEnable(self._tap, True)

            logger.debug("事件循环开始运行")

            # 运行事件循环（阻塞，直到调用 CFRunLoopStop）
            CFRunLoopRun()

            logger.debug("事件循环已停止")

        except Exception as e:
            logger.error(f"事件循环异常: {e}", exc_info=True)
        finally:
            logger.info(f"事件循环线程退出 (thread_id: {thread_id})")

    def _event_callback(self, proxy, event_type, event, refcon):
        """
        事件回调函数（在监听线程中调用）

        Args:
            proxy: Event Tap 代理
            event_type: 事件类型
            event: 事件对象
            refcon: 用户数据

        Returns:
            事件对象（如果不拦截）或 None（如果拦截）
        """
        try:
            # 更新统计
            self._stats["events_processed"] += 1
            self._stats["last_event_time"] = time.time()

            # 获取键码
            keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)

            # 转换为键名
            key_name = keycode_to_key_name(keycode)

            # 判断是按下还是释放
            if event_type == kCGEventKeyDown:
                # 检查是否是修饰键
                flags = CGEventGetFlags(event)
                is_modifier = keycode in [
                    KeyCode.ALT_L,
                    KeyCode.ALT_R,
                    KeyCode.CMD_L,
                    KeyCode.CMD_R,
                    KeyCode.CTRL_L,
                    KeyCode.CTRL_R,
                    KeyCode.SHIFT_L,
                    KeyCode.SHIFT_R,
                ]

                # 调用回调
                if self.on_press:
                    try:
                        self.on_press(key_name)
                    except Exception as e:
                        self._stats["callback_errors"] += 1
                        logger.error(f"on_press 回调异常: {e}")

            elif event_type == kCGEventKeyUp:
                # 调用回调
                if self.on_release:
                    try:
                        self.on_release(key_name)
                    except Exception as e:
                        self._stats["callback_errors"] += 1
                        logger.error(f"on_release 回调异常: {e}")

            elif event_type == kCGEventFlagsChanged:
                # 修饰键状态变化
                # 这里可以添加更复杂的修饰键追踪逻辑
                pass

            # 返回事件（传递给其他应用）
            # 如果要拦截，返回 None
            return event if not self.suppress else None

        except Exception as e:
            logger.error(f"事件回调异常: {e}", exc_info=True)
            self._stats["callback_errors"] += 1
            return event

    def _cleanup_resources(self) -> None:
        """
        清理资源（防止内存泄漏）

        ⚠️ 必须在 Run Loop 停止后调用！
        """
        try:
            # 释放 Loop Source（必须先从 Run Loop 移除）
            if self._loop_source is not None and self._loop is not None:
                try:
                    # 从 Run Loop 移除 Source（防止崩溃）
                    CFRunLoopRemoveSource(
                        self._loop,
                        self._loop_source,
                        kCFRunLoopDefaultMode
                    )
                    logger.debug("Loop Source 已从 Run Loop 移除")
                except Exception as e:
                    logger.warning(f"移除 Loop Source 失败: {e}")
                finally:
                    # 释放 Source
                    try:
                        CFRelease(self._loop_source)
                        logger.debug("Loop Source 已释放")
                    except Exception as e:
                        logger.warning(f"释放 Loop Source 失败: {e}")
                    finally:
                        self._loop_source = None

            # 释放 Event Tap
            if self._tap is not None:
                try:
                    CFRelease(self._tap)
                    logger.debug("Event Tap 已释放")
                except Exception as e:
                    logger.warning(f"释放 Event Tap 失败: {e}")
                finally:
                    self._tap = None

            # 清空引用
            self._loop = None

        except Exception as e:
            logger.error(f"清理资源时出错: {e}")


# ==================== 使用示例 ====================

if __name__ == "__main__":
    import logging

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("=" * 60)
    print("PyObjC 原生键盘监听器 - 原型测试")
    print("=" * 60)

    # 创建监听器
    listener = NativeKeyboardListener(
        on_press=lambda key: print(f"🔵 按下: {key}"),
        on_release=lambda key: print(f"⚪ 松开: {key}"),
    )

    # 启动监听器
    print("\n启动监听器...")
    if not listener.start():
        print("❌ 启动失败")
        exit(1)

    print(f"✓ 启动成功 (耗时: {listener._stats['startup_time_ms']:.2f}ms)")
    print("\n监听中... 按 Ctrl+C 退出\n")

    try:
        # 运行 30 秒
        time.sleep(30)

    except KeyboardInterrupt:
        print("\n\n收到退出信号...")

    finally:
        # 停止监听器
        print("\n停止监听器...")
        listener.stop()

        # 输出统计
        stats = listener.get_stats()
        print("\n统计信息:")
        print(f"  处理事件数: {stats['events_processed']}")
        print(f"  回调错误数: {stats['callback_errors']}")
        print(f"  启动耗时: {stats['startup_time_ms']:.2f}ms")

        print("\n✓ 测试完成")
