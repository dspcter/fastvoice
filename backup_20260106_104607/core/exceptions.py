# core/exceptions.py
# 统一异常类型定义 (P0 重构)

"""
P0 异常兜底系统

设计理念：
- 所有异常必须可恢复到 IDLE 状态
- 明确异常类型，便于诊断和处理
- 所有关键链路异常都要覆盖
"""


class FastVoiceError(Exception):
    """
    快人快语基础异常类

    所有自定义异常的父类
    """

    def __init__(self, message: str, recoverable: bool = True):
        """
        初始化异常

        Args:
            message: 错误信息
            recoverable: 是否可恢复（默认 True）
        """
        super().__init__(message)
        self.recoverable = recoverable
        self.message = message

    def __str__(self):
        recoverable_str = "可恢复" if self.recoverable else "不可恢复"
        return f"[{recoverable_str}] {self.message}"


class AudioError(FastVoiceError):
    """
    音频相关异常

    触发场景：
    - 音频设备被占用
    - 音频采集失败
    - 音频流创建超时
    - 音频数据损坏

    可恢复性：可恢复（重试或切换设备）
    """

    def __init__(self, message: str, device: str = None):
        super().__init__(message, recoverable=True)
        self.device = device

    def __str__(self):
        msg = self.message
        if self.device:
            msg = f"{msg} (设备: {self.device})"
        return f"音频错误: {msg}"


class ASRError(FastVoiceError):
    """
    ASR 识别异常

    触发场景：
    - ASR 模型加载失败
    - ASR 识别超时
    - ASR 模型文件损坏
    - ASR 返回空结果

    可恢复性：可恢复（重试或重新加载模型）
    """

    def __init__(self, message: str, model_id: str = None):
        super().__init__(message, recoverable=True)
        self.model_id = model_id

    def __str__(self):
        msg = self.message
        if self.model_id:
            msg = f"{msg} (模型: {self.model_id})"
        return f"ASR 错误: {msg}"


class HotkeyError(FastVoiceError):
    """
    快捷键相关异常

    触发场景：
    - 快捷键监听器启动失败
    - 快捷键状态机卡死
    - Watchdog 触发（超时）
    - 快捷键冲突

    可恢复性：可恢复（重置状态或重启）
    """

    def __init__(self, message: str, state: str = None):
        super().__init__(message, recoverable=True)
        self.state = state

    def __str__(self):
        msg = self.message
        if self.state:
            msg = f"{msg} (状态: {self.state})"
        return f"快捷键错误: {msg}"


class InputError(FastVoiceError):
    """
    文字注入异常

    触发场景：
    - 剪贴板操作失败
    - 键盘模拟失败
    - 文字注入超时

    可恢复性：可恢复（重试或切换注入方式）
    """

    def __init__(self, message: str, method: str = None):
        super().__init__(message, recoverable=True)
        self.method = method

    def __str__(self):
        msg = self.message
        if self.method:
            msg = f"{msg} (方式: {self.method})"
        return f"注入错误: {msg}"


class StateError(FastVoiceError):
    """
    状态机异常

    触发场景：
    - 非法状态转换
    - 状态不一致
    - 状态死锁

    可恢复性：可恢复（强制重置到 IDLE）
    """

    def __init__(self, message: str, from_state: str = None, to_state: str = None):
        super().__init__(message, recoverable=True)
        self.from_state = from_state
        self.to_state = to_state

    def __str__(self):
        msg = self.message
        if self.from_state and self.to_state:
            msg = f"{msg} ({self.from_state} → {self.to_state})"
        return f"状态错误: {msg}"


class TimeoutError(FastVoiceError):
    """
    超时异常

    触发场景：
    - 操作超时
    - 资源获取超时
    - 响应超时

    可恢复性：可恢复（重试）
    """

    def __init__(self, message: str, operation: str = None, timeout_s: float = None):
        super().__init__(message, recoverable=True)
        self.operation = operation
        self.timeout_s = timeout_s

    def __str__(self):
        msg = self.message
        if self.operation and self.timeout_s:
            msg = f"{msg} ({self.operation}, {self.timeout_s}s)"
        return f"超时错误: {msg}"


class ConfigurationError(FastVoiceError):
    """
    配置异常

    触发场景：
    - 配置文件损坏
    - 配置项缺失
    - 配置值无效

    可恢复性：可恢复（使用默认配置）
    """

    def __init__(self, message: str, config_key: str = None):
        super().__init__(message, recoverable=True)
        self.config_key = config_key

    def __str__(self):
        msg = self.message
        if self.config_key:
            msg = f"{msg} (配置项: {self.config_key})"
        return f"配置错误: {msg}"


class ModelNotFoundError(FastVoiceError):
    """
    模型文件未找到异常

    触发场景：
    - ASR 模型文件不存在
    - 翻译模型文件不存在
    - 模型路径错误

    可恢复性：可恢复（下载模型）
    """

    def __init__(self, message: str, model_type: str = None, model_id: str = None):
        super().__init__(message, recoverable=True)
        self.model_type = model_type
        self.model_id = model_id

    def __str__(self):
        msg = self.message
        if self.model_type and self.model_id:
            msg = f"{msg} ({self.model_type}/{self.model_id})"
        return f"模型未找到: {msg}"


# ==================== 异常恢复工具 ====================

def is_recoverable(error: Exception) -> bool:
    """
    判断异常是否可恢复

    Args:
        error: 异常对象

    Returns:
        是否可恢复
    """
    if isinstance(error, FastVoiceError):
        return error.recoverable

    # 对于系统异常，默认认为不可恢复
    return False


def get_error_type(error: Exception) -> str:
    """
    获取异常类型名称

    Args:
        error: 异常对象

    Returns:
        异常类型名称
    """
    if isinstance(error, FastVoiceError):
        return error.__class__.__name__
    return type(error).__name__


def format_error(error: Exception) -> str:
    """
    格式化异常信息（用于日志或用户显示）

    Args:
        error: 异常对象

    Returns:
        格式化的错误信息
    """
    if isinstance(error, FastVoiceError):
        return str(error)

    # 对于标准异常，使用基础信息
    return f"{type(error).__name__}: {str(error)}"
