#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快人快语 (FastVoice) - 主程序入口
本地优先的 AI 语音输入法
"""

import logging
import sys
import threading
from enum import Enum
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QWidget
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QTimer, pyqtSignal, QObject

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import (
    get_log_path,
    LOG_FORMAT,
    LOG_DATE_FORMAT,
    LOG_LEVEL,
    APP_NAME,
    VERSION,
    get_settings,
    IS_MACOS,
    STORAGE_DIR,
)
from core import (
    HotkeyManager,
    HotkeyAction,
    AudioCapture,
    get_asr_engine,
    get_text_injector,
    get_text_postprocessor,
    get_marianmt_engine,
)
from core.asr_worker import ASRWorker
from core.memory_manager import get_memory_manager
from models import get_model_manager, ModelType
from ui import SettingsWindow


# v1.4.3: 全局应用实例引用（用于其他模块访问应用状态）
_app_instance: Optional['FastVoiceApp'] = None


class AppState(Enum):
    """
    应用状态机

    状态转换:
    IDLE → VOICE_RECORDING → FINALIZING → IDLE
    IDLE → TRANSLATE_RECORDING → FINALIZING → IDLE
    """
    IDLE = "idle"                           # 空闲，无录音
    VOICE_RECORDING = "voice_recording"     # 语音输入录音中
    TRANSLATE_RECORDING = "translate_recording"  # 翻译录音中
    FINALIZING = "finalizing"               # 处理中（ASR/翻译）

# 配置日志
def setup_logging():
    """配置日志系统（带滚动）"""
    from logging.handlers import RotatingFileHandler

    # 确保日志目录存在
    log_path = get_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 创建滚动文件处理器（单个文件最大 10MB，保留 3 个备份）
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=3,
        encoding='utf-8',
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LOG_LEVEL))
    root_logger.handlers.clear()  # 清除现有处理器
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return file_handler  # 返回以便后续使用


# 初始化日志
setup_logging()
logger = logging.getLogger(__name__)


class FastVoiceApp(QObject):
    """快人快语主应用类"""

    # 定义信号（跨线程调用）
    _asr_result_signal = pyqtSignal(str)  # ASR 识别结果
    _asr_error_signal = pyqtSignal()  # ASR 错误（回到 IDLE）

    def __init__(self):
        super().__init__()  # 必须调用 QObject 的 __init__

        # 连接信号到槽（跨线程调用）
        self._asr_result_signal.connect(self._handle_asr_result_on_main_thread)
        self._asr_error_signal.connect(self._return_to_idle)

        # v1.4.3: 关闭标志（防止退出时混乱注入）
        self._is_shutting_down = False
        self._shutdown_lock = threading.Lock()

        self.settings = get_settings()
        self.hotkey_manager = HotkeyManager()
        self.audio_capture = None
        self.asr_engine = get_asr_engine()
        self.text_injector = get_text_injector(method=self.settings.injection_method)
        self.text_postprocessor = get_text_postprocessor()
        self.model_manager = get_model_manager()

        # ASR Worker - 异步处理
        self.asr_worker = ASRWorker(
            on_result=self._on_asr_result,
            on_error=self._on_asr_error
        )

        # 内存管理器 - 防止内存泄漏
        self.memory_manager = get_memory_manager()

        # MarianMT 翻译引擎（按需加载）
        self._marianmt_engines = {}

        # 最后一次识别的文字 (用于按键翻译模式)
        self._last_recognized_text = ""

        # 设置窗口
        self.settings_window = None

        # 状态机（替代布尔标志）
        self._state = AppState.IDLE
        self._state_lock = threading.RLock()  # 可重入锁，防止死锁
        self._current_audio_capture = None  # 当前录音采集器
        self._current_translate = False  # 当前任务是否需要翻译

        logger.info(f"{APP_NAME} v{VERSION} 初始化完成")

    def is_shutting_down(self) -> bool:
        """
        检查应用是否正在关闭

        Returns:
            True 如果应用正在关闭
        """
        with self._shutdown_lock:
            return self._is_shutting_down

    def _transition_state(self, new_state: AppState) -> bool:
        """
        状态转换（线程安全）

        Args:
            new_state: 新状态

        Returns:
            是否转换成功
        """
        with self._state_lock:
            old_state = self._state

            # 检查状态转换是否合法
            if new_state == AppState.VOICE_RECORDING and old_state != AppState.IDLE:
                logger.warning(f"非法状态转换: {old_state.value} → {new_state.value}")
                return False

            if new_state == AppState.TRANSLATE_RECORDING and old_state != AppState.IDLE:
                logger.warning(f"非法状态转换: {old_state.value} → {new_state.value}")
                return False

            self._state = new_state
            logger.info(f"状态转换: {old_state.value} → {new_state.value}")
            return True

    def _get_state(self) -> AppState:
        """获取当前状态（线程安全）"""
        with self._state_lock:
            return self._state

    def _finalize_recording(self, audio_data: bytes = None, force: bool = False):
        """
        统一的录音结束处理（幂等）

        on_auto_stop 和 on_release 都调用这个函数

        Args:
            audio_data: 音频数据（如果已提供）
            force: 是否强制执行（忽略状态检查）
        """
        with self._state_lock:
            old_state = self._state

            # v1.4.2: 诊断日志
            logger.info(f"[_finalize_recording] 进入，当前状态: {old_state.value}, force={force}")

            if not force and self._state == AppState.IDLE:
                logger.info(f"[_finalize_recording] 已经是 IDLE，幂等返回")
                return  # 已经是 IDLE，幂等返回

            if self._state not in [AppState.VOICE_RECORDING, AppState.TRANSLATE_RECORDING]:
                logger.warning(f"[_finalize_recording] 当前状态不允许 finalize: {self._state.value}")

                # v1.4.2: 如果是 FINALIZING 状态，可能已经在处理中了，直接返回
                if self._state == AppState.FINALIZING:
                    logger.info(f"[_finalize_recording] 已在 FINALIZING 状态，跳过")
                    return

                # v1.4.2: 强制模式下，尝试继续处理
                if not force:
                    return

                # 强制模式：从 FINALIZING 或其他状态继续
                logger.warning(f"[_finalize_recording] 强制模式，继续处理")

            # 转换到 FINALIZING 状态
            self._state = AppState.FINALIZING

        logger.info(f"结束录音，当前状态: {old_state.value}")

        # 停止录音并获取音频数据
        if audio_data is None and self._current_audio_capture:
            try:
                audio_data = self._current_audio_capture.stop_recording()
            except Exception as e:
                logger.error(f"停止录音失败: {e}")
                audio_data = None

        # 保存音频文件
        if audio_data:
            try:
                filepath = self._current_audio_capture.save_audio(audio_data)
                logger.info(f"音频已保存: {filepath}")
            except Exception as e:
                logger.error(f"保存音频失败: {e}")

        # 提交到 ASR Worker 异步处理
        if audio_data:
            try:
                self._current_translate = (old_state == AppState.TRANSLATE_RECORDING)
                self.asr_worker.process_audio(audio_data)
                logger.info(f"[_finalize_recording] 已提交 ASR 任务，translate={self._current_translate}")
            except Exception as e:
                logger.error(f"提交 ASR 任务失败: {e}")
                # 异常时立即回到 IDLE
                with self._state_lock:
                    self._state = AppState.IDLE
        else:
            logger.warning("没有录制到音频")
            # 直接回到 IDLE
            with self._state_lock:
                self._state = AppState.IDLE

        # 最后清理录音采集器（确保状态已处理完毕）
        self._current_audio_capture = None

        logger.info(f"[_finalize_recording] 完成，最终状态: {self._get_state().value}")

    def initialize(self):
        """初始化应用"""
        # 启动 ASR Worker 并预热模型
        logger.info("启动 ASR Worker...")
        if not self.asr_worker.start():
            logger.error("ASR Worker 启动失败")
            return False

        logger.info("预热 ASR 模型...")
        if not self.asr_worker.warmup():
            logger.warning("ASR 模型预热失败，首次识别可能较慢")

        # v1.3.5: 预热音频流，解决第一次按键录音延迟问题
        logger.info("预热音频流...")
        self._warmup_audio_stream()

        # v1.3.5: 预热翻译模型，解决第一次翻译慢的问题
        logger.info("预热翻译模型...")
        self._warmup_translation_model()

        # 启动内存自动清理
        logger.info("启动内存自动清理...")
        self.memory_manager.start_auto_cleanup()

        # 注册快捷键回调
        self.hotkey_manager.register_callback(
            HotkeyAction.VOICE_INPUT_PRESS, self._on_voice_press
        )
        self.hotkey_manager.register_callback(
            HotkeyAction.VOICE_INPUT_RELEASE, self._on_voice_release
        )
        # 翻译也改为长按模式
        self.hotkey_manager.register_callback(
            HotkeyAction.QUICK_TRANSLATE_PRESS, self._on_translate_press
        )
        self.hotkey_manager.register_callback(
            HotkeyAction.QUICK_TRANSLATE_RELEASE, self._on_translate_release
        )

        # 启动快捷键监听
        # v1.4.2: 获取快捷键配置（包含模式）
        voice_hotkey = self.settings.voice_input_hotkey
        translate_hotkey = self.settings.quick_translate_hotkey
        voice_mode = self.settings.voice_input_mode
        translate_mode = self.settings.translate_mode

        if not self.hotkey_manager.start(
            voice_hotkey,
            translate_hotkey,
            voice_mode=voice_mode,
            translate_mode=translate_mode
        ):
            logger.error("启动快捷键监听失败")
            return False

        logger.info(f"快捷键监听已启动: voice={voice_hotkey}({voice_mode}), "
                   f"translate={translate_hotkey}({translate_mode})")
        return True

    def _warmup_audio_stream(self):
        """预热音频流"""
        try:
            # 创建临时 AudioCapture 进行预热
            temp_capture = AudioCapture(
                sample_rate=self.settings.sample_rate,
                vad_threshold=self.settings.vad_threshold,
                device=self.settings.microphone_device or None,
            )
            temp_capture.warmup()
            # 临时对象会自动被 GC 清理
        except Exception as e:
            logger.warning(f"音频流预热失败: {e}")

    def _warmup_translation_model(self):
        """预热翻译模型"""
        try:
            target_lang = self.settings.target_language
            source_lang = self.settings.source_language
            direction = f"{source_lang}-{target_lang}"

            logger.info(f"预热翻译模型 ({direction})...")

            # 检查模型是否存在
            model_id = f"marianmt-{direction}"
            if not self.model_manager.check_translation_model(model_id):
                logger.info(f"翻译模型 {model_id} 未下载，跳过预热")
                return

            # 创建并加载翻译引擎（会缓存到 _marianmt_engines）
            engine = get_marianmt_engine(direction)
            if engine.load_model():
                self._marianmt_engines[direction] = engine
                logger.info(f"✓ 翻译模型预热完成 ({direction})")
            else:
                logger.warning(f"翻译模型预热失败 ({direction})")
        except Exception as e:
            logger.warning(f"翻译模型预热失败: {e}")

    def _on_voice_press(self):
        """语音输入按键按下 - 开始录音"""
        try:
            # 检查状态，只允许从 IDLE 转换到 RECORDING
            if not self._transition_state(AppState.VOICE_RECORDING):
                logger.warning("当前状态不允许开始录音: %s", self._get_state().value)
                return

            logger.info("开始录音 (语音输入)")

            # P0: 递增 generation，使旧任务失效
            self.asr_worker.start_session()

            # 创建音频采集器，传入自动停止回调
            def on_auto_stop(audio_data: bytes):
                """录音超时自动停止时的处理"""
                logger.info("录音自动停止（超时）")
                self._finalize_recording(audio_data)

            self._current_audio_capture = AudioCapture(
                sample_rate=self.settings.sample_rate,
                vad_threshold=self.settings.vad_threshold,
                device=self.settings.microphone_device or None,
                on_auto_stop=on_auto_stop,
            )

            # 开始录音
            self._current_audio_capture.start_recording()

        except Exception as e:
            logger.error(f"启动录音失败: {e}")
            # 异常时强制回到 IDLE
            with self._state_lock:
                self._state = AppState.IDLE
            self._current_audio_capture = None

    def _on_voice_release(self):
        """语音输入按键释放 - 停止录音并识别"""
        try:
            # v1.4.2: 诊断日志 - 记录当前状态
            current_state = self._get_state()
            logger.info(f"[_on_voice_release] 当前状态: {current_state.value}")

            if current_state != AppState.VOICE_RECORDING:
                logger.warning(f"[_on_voice_release] 状态不匹配，期望: voice_recording, 实际: {current_state.value}")
                # v1.4.2: 如果状态不匹配，但有正在进行的录音，仍然尝试停止
                if self._current_audio_capture and self._current_audio_capture.is_recording():
                    logger.warning(f"[_on_voice_release] 检测到录音仍在进行，强制停止")
                    self._finalize_recording(force=True)
                return

            logger.info("停止录音 (语音输入)")
            # 调用统一的 finalize 函数
            self._finalize_recording()

        except Exception as e:
            logger.error(f"停止录音失败: {e}")
            # 异常时强制回到 IDLE
            with self._state_lock:
                self._state = AppState.IDLE
            self._current_audio_capture = None

    def _on_translate_press(self):
        """翻译按键按下 - 开始录音用于翻译"""
        try:
            # 检查状态，只允许从 IDLE 转换到 RECORDING
            if not self._transition_state(AppState.TRANSLATE_RECORDING):
                logger.warning("当前状态不允许开始翻译录音: %s", self._get_state().value)
                return

            logger.info("开始录音 (翻译)")

            # P0: 递增 generation，使旧任务失效
            self.asr_worker.start_session()

            # 创建音频采集器，传入自动停止回调
            def on_auto_stop(audio_data: bytes):
                """录音超时自动停止时的处理"""
                logger.info("翻译录音自动停止（超时）")
                self._finalize_recording(audio_data)

            self._current_audio_capture = AudioCapture(
                sample_rate=self.settings.sample_rate,
                vad_threshold=self.settings.vad_threshold,
                device=self.settings.microphone_device or None,
                on_auto_stop=on_auto_stop,
            )

            # 开始录音
            self._current_audio_capture.start_recording()

        except Exception as e:
            logger.error(f"启动翻译录音失败: {e}")
            # 异常时强制回到 IDLE
            with self._state_lock:
                self._state = AppState.IDLE
            self._current_audio_capture = None

    def _on_translate_release(self):
        """翻译按键释放 - 停止录音并翻译"""
        try:
            # v1.4.2: 诊断日志 - 记录当前状态
            current_state = self._get_state()
            logger.info(f"[_on_translate_release] 当前状态: {current_state.value}")

            if current_state != AppState.TRANSLATE_RECORDING:
                logger.warning(f"[_on_translate_release] 状态不匹配，期望: translate_recording, 实际: {current_state.value}")
                # v1.4.2: 如果状态不匹配，但有正在进行的录音，仍然尝试停止
                if self._current_audio_capture and self._current_audio_capture.is_recording():
                    logger.warning(f"[_on_translate_release] 检测到录音仍在进行，强制停止")
                    self._finalize_recording(force=True)
                return

            logger.info("停止录音 (翻译)")
            # 调用统一的 finalize 函数
            self._finalize_recording()

        except Exception as e:
            logger.error(f"停止翻译录音失败: {e}")
            # 异常时强制回到 IDLE
            with self._state_lock:
                self._state = AppState.IDLE
            self._current_audio_capture = None

    def _process_voice_input(self, audio_data: bytes, translate: bool = False):
        """
        处理语音输入 - 异步提交到 ASR Worker

        Args:
            audio_data: 音频数据
            translate: 是否需要翻译
        """
        # 计算音频时长（约等于）
        import wave
        import io
        try:
            with io.BytesIO(audio_data) as wav_io:
                with wave.open(wav_io, "rb") as wav_file:
                    frames = wav_file.getnframes()
                    sample_rate = wav_file.getframerate()
                    audio_duration = frames / sample_rate
        except:
            audio_duration = 0.0

        logger.info(f"提交语音识别任务，音频数据大小: {len(audio_data)} bytes，时长约 {audio_duration:.2f}s")

        # 提交到 ASR Worker 异步处理（不阻塞 UI）
        # 注意：翻译逻辑暂时在 _on_asr_result 回调中处理
        self._current_translate = translate  # 保存翻译标志
        self.asr_worker.process_audio(audio_data)

    def show_settings(self):
        """显示设置窗口"""
        logger.info("=== 打开设置窗口 ===")

        # 清空按键状态，避免按键状态不同步
        self.hotkey_manager.clear_pressed_keys()

        if self.settings_window is None:
            logger.info("创建新的设置窗口")
            self.settings_window = SettingsWindow(apply_callback=self.apply_settings)
        else:
            logger.info("使用已存在的设置窗口")

        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()
        logger.info("=== 设置窗口已显示 ===")

    def apply_settings(self, changed_settings: dict = None) -> bool:
        """
        应用设置更改（v1.4.2 新增）

        用于在不重启应用的情况下应用设置更改

        Args:
            changed_settings: 已更改的设置项字典

        Returns:
            是否应用成功
        """
        if changed_settings is None:
            changed_settings = {}

        logger.info(f"应用设置更改: {list(changed_settings.keys())}")

        try:
            # 1. 重新配置快捷键
            if "hotkeys" in changed_settings:
                voice_hotkey = self.settings.voice_input_hotkey
                translate_hotkey = self.settings.quick_translate_hotkey
                voice_mode = self.settings.voice_input_mode
                translate_mode = self.settings.translate_mode

                success = self.hotkey_manager.reconfigure(
                    voice_hotkey,
                    translate_hotkey,
                    voice_mode=voice_mode,
                    translate_mode=translate_mode
                )
                if not success:
                    logger.error("重新配置快捷键失败")
                    return False
                logger.info("✓ 快捷键已重新配置")

            # 2. 重新加载注入器
            if "injection_method" in changed_settings:
                # 清理旧的注入器
                if self.text_injector:
                    try:
                        self.text_injector.cleanup()
                    except Exception as e:
                        logger.warning(f"清理旧注入器时出错: {e}")

                # 创建新注入器
                new_method = self.settings.injection_method
                self.text_injector = get_text_injector(method=new_method)
                logger.info(f"✓ 文字注入方式已更改为: {new_method}")

            # 3. 其他设置可以立即生效
            # - VAD 阈值：AudioCapture 会在下次录音时使用新值
            # - 翻译目标语言：翻译引擎会在下次翻译时使用新值
            # - 自动清理：MemoryManager 会在下次检查时使用新值

            logger.info("✓ 设置已应用")
            return True

        except Exception as e:
            logger.error(f"应用设置失败: {e}")
            return False

    def shutdown(self):
        """
        关闭应用

        v1.4.3: 优化关闭流程，防止退出时混乱注入
        """
        logger.info("=" * 60)
        logger.info("🚪 [shutdown] 开始关闭应用...")
        logger.info("=" * 60)

        # 步骤1: 首先设置关闭标志（阻止新的注入操作）
        with self._shutdown_lock:
            self._is_shutting_down = True
        logger.info("⛔ [shutdown] 已设置关闭标志，阻止新的注入操作")

        # 步骤2: 停止快捷键监听（防止新的录音触发）
        try:
            logger.info("🛑 [shutdown] 停止快捷键监听...")
            self.hotkey_manager.stop()
            logger.info("✓ [shutdown] 快捷键监听已停止")
        except Exception as e:
            logger.error(f"✗ [shutdown] 停止快捷键监听失败: {e}")

        # 步骤3: 停止 ASR Worker（关键：阻止新任务，等待当前任务完成）
        try:
            logger.info("🛑 [shutdown] 停止 ASR Worker...")
            self.asr_worker.stop()
            logger.info("✓ [shutdown] ASR Worker 已发出停止信号")

            # 等待 ASR Worker 完全停止
            logger.info("⏳ [shutdown] 等待 ASR Worker 完全停止...")
            if hasattr(self.asr_worker, 'wait_until_stopped'):
                stopped = self.asr_worker.wait_until_stopped(timeout=5.0)
                if stopped:
                    logger.info("✓ [shutdown] ASR Worker 已完全停止")
                else:
                    logger.warning("⚠ [shutdown] ASR Worker 停止超时，继续关闭流程")
            else:
                # 后备：简单等待
                import time
                for i in range(50):  # 最多等待5秒
                    if not self.asr_worker._running:
                        logger.info(f"✓ [shutdown] ASR Worker 已停止（耗时 {i*0.1:.1f}s）")
                        break
                    time.sleep(0.1)
                else:
                    logger.warning("⚠ [shutdown] ASR Worker 停止超时")
        except Exception as e:
            logger.error(f"✗ [shutdown] 停止 ASR Worker 失败: {e}")

        # 步骤4: 停止录音（如果正在录音）
        try:
            logger.info("🛑 [shutdown] 检查是否有正在进行的录音...")
            if self._current_audio_capture and self._current_audio_capture.is_recording():
                logger.info("⏹ [shutdown] 停止正在进行的录音...")
                self._current_audio_capture.stop_recording()
                logger.info("✓ [shutdown] 录音已停止")
            else:
                logger.info("✓ [shutdown] 没有正在进行的录音")
        except Exception as e:
            logger.error(f"✗ [shutdown] 停止录音失败: {e}")

        # 步骤5: 停止内存自动清理
        try:
            logger.info("🛑 [shutdown] 停止内存自动清理...")
            self.memory_manager.stop_auto_cleanup()
            logger.info("✓ [shutdown] 内存自动清理已停止")
        except Exception as e:
            logger.error(f"✗ [shutdown] 停止内存清理失败: {e}")

        # 步骤6: 清理注入器（防止退出时残留按键状态）
        try:
            logger.info("🧹 [shutdown] 清理注入器状态...")
            if self.text_injector:
                self.text_injector.cleanup()
                logger.info("✓ [shutdown] 注入器已清理")
            else:
                logger.info("✓ [shutdown] 注入器为空，跳过清理")
        except Exception as e:
            logger.error(f"✗ [shutdown] 清理注入器失败: {e}")

        # 步骤7: 最终状态报告
        logger.info("=" * 60)
        logger.info("✅ [shutdown] 应用关闭完成")
        logger.info(f"   - 状态: {self._get_state().value}")
        logger.info(f"   - 关闭标志: {self._is_shutting_down}")
        logger.info("=" * 60)

    def _on_asr_result(self, text: str):
        """
        ASR Worker 识别结果回调（在 worker 线程执行）

        P0 线程安全：发射信号到主线程执行

        v1.4.7: 添加关闭检查，防止退出后混乱注入

        Args:
            text: 识别出的文本
        """
        try:
            # v1.4.7: 首先检查应用是否正在关闭
            with self._shutdown_lock:
                if self._is_shutting_down:
                    logger.info("🛑 [ASR回调] 应用正在关闭，忽略 ASR 结果: '%s'", text)
                    return

            if not text:
                logger.debug("ASR 识别结果为空")
                # 空结果也要回到 IDLE
                self._asr_error_signal.emit()
                return

            # 发射信号到主线程（Qt 信号是线程安全的）
            logger.info("发射 ASR 结果信号: '%s'", text)
            self._asr_result_signal.emit(text)

        except Exception as e:
            logger.error("ASR 结果处理失败: %s", e)
            self._asr_error_signal.emit()

    def _handle_asr_result_on_main_thread(self, text: str):
        """
        在主线程处理 ASR 结果（线程安全）

        P0: 此函数在主线程执行，可以安全调用 UI 操作

        v1.4.3: 添加关闭检查，防止退出时混乱注入

        Args:
            text: 识别出的文本
        """
        try:
            # v1.4.3: 首先检查应用是否正在关闭
            with self._shutdown_lock:
                if self._is_shutting_down:
                    logger.info("🛑 [主线程] 应用正在关闭，跳过 ASR 结果处理")
                    return

            logger.info(f"📥 [主线程] 收到 ASR 结果: '{text}'")

            # 文本后处理
            processed_text = self.text_postprocessor.process(text)
            self._last_recognized_text = processed_text

            logger.info("ASR 识别结果: %s", text)
            logger.info("后处理结果: %s", processed_text)

            # 如果需要翻译
            if self._current_translate:
                final_text = self._translate_text(processed_text)
            else:
                final_text = processed_text

            # 注入文字（现在在主线程，安全）
            logger.info("准备注入文字: '%s'", final_text)
            self.text_injector.inject(final_text)

        except Exception as e:
            logger.error("处理 ASR 结果失败: %s", e)
        finally:
            # 无论成功失败，都要回到 IDLE（在主线程）
            self._return_to_idle()

    def _return_to_idle(self):
        """回到 IDLE 状态（在主线程调用）"""
        with self._state_lock:
            if self._state == AppState.FINALIZING:
                self._state = AppState.IDLE
                logger.info("处理完成，状态回到 IDLE")

    def _on_asr_error(self, error: Exception):
        """
        ASR Worker 错误回调（在 worker 线程执行）

        P0: 发射信号到主线程恢复状态

        v1.4.7: 添加关闭检查，防止退出时混乱注入

        Args:
            error: 异常对象
        """
        # v1.4.7: 检查应用是否正在关闭
        with self._shutdown_lock:
            if self._is_shutting_down:
                logger.info("🛑 [ASR错误回调] 应用正在关闭，忽略 ASR 错误")
                return

        logger.error("ASR Worker 错误: %s", error)

        # 判断异常类型并给出提示
        from core.asr_engine import ASRSilentError, ASREmptyResult

        if isinstance(error, ASRSilentError):
            logger.warning("提示: 请检查麦克风音量")
        elif isinstance(error, ASREmptyResult):
            logger.debug("音频太短或无有效语音")

        # 错误时也要回到 IDLE（发射信号到主线程）
        self._asr_error_signal.emit()

    def _translate_text(self, text: str) -> str:
        """
        翻译文本（在主线程执行，因为 _handle_asr_result_on_main_thread 在主线程）

        注意：翻译模型加载和执行都是同步操作，但因为已经通过 QTimer 调度到主线程，
        所以不会阻塞 ASR worker 线程。

        Args:
            text: 要翻译的文本

        Returns:
            翻译结果，失败则返回原文
        """
        try:
            target_lang = self.settings.target_language
            source_lang = self.settings.source_language

            # 确定翻译方向
            direction = f"{source_lang}-{target_lang}"

            logger.info(f"翻译: {source_lang} → {target_lang}")

            # 获取对应的 MarianMT 引擎
            engine_key = direction

            if engine_key not in self._marianmt_engines:
                # 检查模型是否已下载
                model_id = f"marianmt-{direction}"
                if not self.model_manager.check_translation_model(model_id):
                    logger.warning(f"翻译模型 {model_id} 未下载，请在设置中下载")
                    return text  # 返回原文

                # 创建翻译引擎
                self._marianmt_engines[engine_key] = get_marianmt_engine(direction)

            # 执行翻译
            engine = self._marianmt_engines[engine_key]
            translated = engine.translate(text)

            if translated:
                return translated
            else:
                logger.warning("翻译失败，返回原文")
                return text

        except Exception as e:
            logger.error(f"翻译异常: {e}，返回原文")
            return text


def create_menu_bar(app: FastVoiceApp, qt_app: QApplication):
    """
    创建 macOS 应用菜单栏

    暂时禁用，因为会触发 HIToolbox 崩溃
    """
    # 暂时禁用菜单栏功能以避免 HIToolbox 崩溃
    return


def create_tray_icon(app: FastVoiceApp, qt_app: QApplication) -> QSystemTrayIcon:
    """
    创建系统托盘图标

    Args:
        app: 主应用实例
        qt_app: Qt 应用实例

    Returns:
        托盘图标
    """
    import os
    # 创建托盘图标
    tray_icon = QSystemTrayIcon()

    # 创建菜单
    menu = QMenu()

    # 打开设置
    settings_action = QAction("打开设置", qt_app)
    settings_action.triggered.connect(app.show_settings)
    menu.addAction(settings_action)

    menu.addSeparator()

    # 退出
    quit_action = QAction("退出", qt_app)
    quit_action.triggered.connect(qt_app.quit)
    menu.addAction(quit_action)

    tray_icon.setContextMenu(menu)

    # 设置图标 - 优先使用资源目录，否则使用项目目录
    icon_path = None
    possible_paths = [
        Path(sys.executable).parent.parent / "Resources" / "assets" / "appicon.icns",  # 打包后
        PROJECT_ROOT / "assets" / "appicon.icns",  # 开发环境
    ]
    for path in possible_paths:
        if path.exists():
            icon_path = path
            break

    if icon_path:
        tray_icon.setIcon(QIcon(str(icon_path)))
        logger.info(f"托盘图标已加载: {icon_path}")
    else:
        logger.warning("未找到托盘图标文件")

    # 双击托盘图标打开设置
    def on_tray_activated(reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            app.show_settings()

    tray_icon.activated.connect(on_tray_activated)

    # 显示提示
    tray_icon.setToolTip(f"{APP_NAME} v{VERSION}")

    tray_icon.show()

    return tray_icon


def check_first_run() -> bool:
    """检查是否首次运行

    如果模型已下载，即使标记文件不存在也跳过向导
    """
    import traceback
    logger.info("=== check_first_run() 被调用 ===")
    logger.info(f"调用栈:\n{''.join(traceback.format_stack())}")

    marker_file = STORAGE_DIR / ".first_run_completed"

    # 如果标记文件存在，直接跳过
    if marker_file.exists():
        logger.info(f"标记文件已存在: {marker_file}")
        return False

    # 检查 ASR 模型是否已存在
    try:
        model_manager = get_model_manager()
        if model_manager.check_asr_model("sense-voice"):
            logger.info("检测到 ASR 模型已存在，跳过首次运行向导")
            # 创建标记文件
            marker_file.parent.mkdir(parents=True, exist_ok=True)
            marker_file.touch()
            return False
    except Exception as e:
        logger.warning(f"检查模型时出错: {e}")

    # 标记文件不存在且模型也不存在，需要运行向导
    logger.info("需要运行首次运行向导")
    return True


def main():
    """主函数"""
    logger.info(f"{APP_NAME} v{VERSION} 启动中...")

    # 创建 Qt 应用
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)  # 关闭窗口不退出应用

    # 检查首次运行
    wizard_completed = False
    if check_first_run():
        from ui.first_run_wizard import FirstRunWizard
        logger.info("=== 首次运行，显示设置向导 ===")
        wizard = FirstRunWizard()
        result = wizard.exec()
        logger.info(f"=== 向导关闭，返回值: {result} ===")
        if result != 1:  # 用户取消
            logger.info("用户取消首次运行向导")
            return 1
        logger.info("=== 首次运行向导完成 ===")
        wizard_completed = True

    # 创建主应用
    app = FastVoiceApp()

    # v1.4.3: 设置全局应用实例引用（供其他模块访问）
    global _app_instance
    _app_instance = app
    logger.info("✓ 全局应用实例已设置")

    # 创建托盘图标
    tray_icon = create_tray_icon(app, qt_app)

    # 在 QApplication 创建后再初始化快捷键监听
    # 这样可以确保 Qt 事件循环已经准备好
    if not app.initialize():
        logger.error("应用初始化失败")
        return 1

    # 创建 macOS 应用菜单栏
    create_menu_bar(app, qt_app)

    # 不显示设置窗口，让应用在后台运行
    # app.show_settings()  # 注释掉，用户可通过托盘图标打开

    logger.info("应用启动完成 - 请通过托盘图标打开设置")

    # 添加应用心跳定时器（每 60 秒输出一次，用于诊断应用是否还活着）
    heartbeat_timer = QTimer()
    heartbeat_count = [0]  # 使用列表以便在闭包中修改

    def heartbeat():
        heartbeat_count[0] += 1

        # 使用 lazy logging 避免字符串累积（只在真正需要输出时才格式化）
        # 合并日志减少对象创建
        watchdog_alive = app.hotkey_manager.is_watchdog_alive()
        listener_status = app.hotkey_manager.get_listener_status()
        memory_stats = app.memory_manager.get_stats()

        # 单行日志输出 - 使用 lazy logging
        logger.info(
            "心跳 %ds | Watchdog:%s Listener:%s(%.0fs) 内存:%.1fMB",
            heartbeat_count[0] * 60,
            '✓' if watchdog_alive else '✗',
            listener_status['health'][0] if listener_status['thread_alive'] else '✗',
            listener_status['seconds_since_last_key_event'],
            memory_stats['memory_mb']
        )

        # 检查是否需要恢复
        need_recovery = (
            not watchdog_alive or
            not listener_status['thread_alive'] or
            listener_status['health'] == '可能已静默失效'
        )

        if need_recovery:
            logger.warning("检测到系统异常，尝试自动恢复...")
            app.hotkey_manager.recover()

    heartbeat_timer.timeout.connect(heartbeat)
    heartbeat_timer.start(60000)  # 60 秒

    # 添加更频繁的健康检查（每 10 秒）
    health_check_timer = QTimer()
    health_check_count = [0]

    def health_check():
        health_check_count[0] += 1
        # 仅在检测到问题时输出日志
        if health_check_count[0] % 6 == 0:  # 每分钟输出一次
            logger.debug(f"💚 健康检查: Qt 事件循环运行正常 ({health_check_count[0] * 10}s)")

    health_check_timer.timeout.connect(health_check)
    health_check_timer.start(10000)  # 10 秒

    # 运行事件循环
    exit_code = qt_app.exec()

    # 清理
    app.shutdown()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
