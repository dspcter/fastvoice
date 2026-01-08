# core/recovery.py
# 状态恢复和异常处理模块 (P0 重构)

import logging
import threading
from typing import Callable, Optional, TypeVar

from core.exceptions import (
    FastVoiceError,
    AudioError,
    ASRError,
    HotkeyError,
    StateError,
    is_recoverable,
    format_error,
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


class StateRecoveryManager:
    """
    状态恢复管理器 - P0 重构

    职责：
    - 统一异常捕获
    - 自动状态恢复到 IDLE
    - 确保所有异常可恢复

    P0 目标：
    - 任何异常都不能导致状态坏掉
    - 异常后必须能恢复到 IDLE
    - 支持幂等的 reset 操作
    """

    def __init__(self):
        # 需要恢复的组件
        self._reset_callbacks: list = []
        self._lock = threading.Lock()

        # 统计
        self._recovery_count = 0
        self._error_count = 0

        logger.info("StateRecoveryManager 初始化完成")

    def register_reset_callback(self, callback: Callable[[], None]) -> None:
        """
        注册 reset 回调

        当需要恢复状态时，所有注册的回调都会被调用

        Args:
            callback: 无参数的回调函数
        """
        with self._lock:
            self._reset_callbacks.append(callback)
            logger.debug(f"注册 reset 回调: {callback.__name__}")

    def reset_all(self, reason: str = "手动重置") -> None:
        """
        重置所有状态到初始状态（幂等操作）

        Args:
            reason: 重置原因
        """
        with self._lock:
            logger.warning(f"开始重置所有状态 (原因: {reason})")

            # 调用所有 reset 回调
            for callback in self._reset_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Reset 回调失败 ({callback.__name__}): {e}")

            self._recovery_count += 1
            logger.info(f"状态重置完成 (总计: {self._recovery_count} 次)")

    def handle_exception(self, error: Exception, context: str = "") -> bool:
        """
        统一异常处理

        Args:
            error: 异常对象
            context: 上下文信息（在哪里发生的异常）

        Returns:
            是否成功恢复
        """
        self._error_count += 1

        # 格式化异常信息
        error_msg = format_error(error)
        logger.error(f"异常捕获 [{context}]: {error_msg}")

        # 检查是否可恢复
        if not is_recoverable(error):
            logger.critical(f"不可恢复异常: {error_msg}")
            return False

        # 尝试恢复状态
        try:
            self.reset_all(reason=f"异常恢复: {error_msg}")
            return True
        except Exception as e:
            logger.critical(f"状态恢复失败: {e}")
            return False

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "recovery_count": self._recovery_count,
            "error_count": self._error_count,
            "registered_callbacks": len(self._reset_callbacks),
        }


# 全局单例
_recovery_manager: Optional[StateRecoveryManager] = None


def get_recovery_manager() -> StateRecoveryManager:
    """获取全局状态恢复管理器"""
    global _recovery_manager
    if _recovery_manager is None:
        _recovery_manager = StateRecoveryManager()
    return _recovery_manager


def safe_execute(context: str = ""):
    """
    异常安全装饰器 - 自动捕获异常并恢复状态

    Args:
        context: 上下文信息（用于日志）

    Usage:
        @safe_execute("语音输入")
        def start_voice_input():
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args, **kwargs) -> Optional[T]:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                recovery_manager = get_recovery_manager()
                recovered = recovery_manager.handle_exception(e, context or func.__name__)
                if not recovered:
                    # 不可恢复异常，重新抛出
                    raise
                return None

        return wrapper

    return decorator


class StateGuard:
    """
    状态保护上下文管理器

    用法:
        with StateGuard("录音操作"):
            # 可能失败的代码
            do_something()
        # 异常时自动恢复状态
    """

    def __init__(self, context: str = ""):
        """
        初始化状态保护

        Args:
            context: 上下文信息
        """
        self.context = context
        self.recovery_manager = get_recovery_manager()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # 发生异常，尝试恢复
            self.recovery_manager.handle_exception(exc_val, self.context)
        # 返回 False 表示异常已处理，不需要继续传播
        return exc_type is None or is_recoverable(exc_val)


# ==================== 辅助函数 ====================

def with_recovery(context: str, func: Callable[[], T], default: T = None) -> T:
    """
    带状态恢复的函数执行

    Args:
        context: 上下文信息
        func: 要执行的函数
        default: 异常时的默认返回值

    Returns:
        函数结果或默认值
    """
    try:
        return func()
    except Exception as e:
        recovery_manager = get_recovery_manager()
        recovery_manager.handle_exception(e, context)
        return default


def safe_reset_all(reason: str = "手动重置") -> None:
    """
    安全重置所有状态

    Args:
        reason: 重置原因
    """
    recovery_manager = get_recovery_manager()
    recovery_manager.reset_all(reason)


# ==================== 使用示例 ====================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 创建恢复管理器
    manager = get_recovery_manager()

    # 注册一些 mock reset 回调
    def reset_audio():
        print("  → 重置音频状态")

    def reset_hotkey():
        print("  → 重置快捷键状态")

    def reset_asr():
        print("  → 重置 ASR 状态")

    manager.register_reset_callback(reset_audio)
    manager.register_reset_callback(reset_hotkey)
    manager.register_reset_callback(reset_asr)

    # 测试异常处理
    print("\n=== 测试 1: 模拟异常 ===")

    @safe_execute("测试操作")
    def test_function():
        print("执行测试函数...")
        raise AudioError("模拟音频设备错误")

    test_function()

    print(f"\n统计: {manager.get_stats()}")

    # 测试手动重置
    print("\n=== 测试 2: 手动重置 ===")
    manager.reset_all("测试重置")

    # 测试上下文管理器
    print("\n=== 测试 3: StateGuard ===")

    with StateGuard("录音操作"):
        print("执行可能失败的操作...")
        # raise HotkeyError("模拟快捷键错误")
        print("操作成功")

    print(f"\n最终统计: {manager.get_stats()}")
