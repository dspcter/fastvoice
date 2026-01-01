#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快人快语 (FastVoice) - 主程序入口
本地优先的 AI 语音输入法
"""

import logging
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QWidget
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QTimer

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
from models import get_model_manager, ModelType
from ui import SettingsWindow

# 配置日志
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[
        logging.FileHandler(get_log_path(), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


class FastVoiceApp:
    """快人快语主应用类"""

    def __init__(self):
        self.settings = get_settings()
        self.hotkey_manager = HotkeyManager()
        self.audio_capture = None
        self.asr_engine = get_asr_engine()
        self.text_injector = get_text_injector()
        self.text_postprocessor = get_text_postprocessor()
        self.model_manager = get_model_manager()

        # MarianMT 翻译引擎（按需加载）
        self._marianmt_engines = {}

        # 最后一次识别的文字 (用于按键翻译模式)
        self._last_recognized_text = ""

        # 设置窗口
        self.settings_window = None

        # 录音状态
        self._is_recording = False
        self._is_translating = False
        self._translate_capture = None  # 翻译用的音频采集器

        logger.info(f"{APP_NAME} v{VERSION} 初始化完成")

    def initialize(self):
        """初始化应用"""
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
        voice_hotkey = self.settings.voice_input_hotkey
        translate_hotkey = self.settings.quick_translate_hotkey

        if not self.hotkey_manager.start(voice_hotkey, translate_hotkey):
            logger.error("启动快捷键监听失败")
            return False

        logger.info("快捷键监听已启动")
        return True

    def _on_voice_press(self):
        """语音输入按键按下 - 开始录音"""
        if self._is_recording:
            return

        logger.info("开始录音 (语音输入)")
        self._is_recording = True

        # 创建音频采集器
        self.audio_capture = AudioCapture(
            sample_rate=self.settings.sample_rate,
            vad_threshold=self.settings.vad_threshold,
            device=self.settings.microphone_device or None,
        )

        # 开始录音
        self.audio_capture.start_recording()

    def _on_voice_release(self):
        """语音输入按键释放 - 停止录音并识别"""
        if not self._is_recording:
            return

        logger.info("停止录音 (语音输入)")
        self._is_recording = False

        # 停止录音
        audio_data = self.audio_capture.stop_recording()

        if audio_data:
            # 保存音频文件
            filepath = self.audio_capture.save_audio(audio_data)

            # 语音识别并直接注入原文
            self._process_voice_input(audio_data, translate=False)
        else:
            logger.warning("没有录制到音频")

    def _on_translate_press(self):
        """翻译按键按下 - 开始录音用于翻译"""
        if self._is_translating:
            return

        logger.info("开始录音 (翻译)")
        self._is_translating = True

        # 创建音频采集器
        self._translate_capture = AudioCapture(
            sample_rate=self.settings.sample_rate,
            vad_threshold=self.settings.vad_threshold,
            device=self.settings.microphone_device or None,
        )

        # 开始录音
        self._translate_capture.start_recording()

    def _on_translate_release(self):
        """翻译按键释放 - 停止录音并翻译"""
        if not self._is_translating:
            return

        logger.info("停止录音 (翻译)")
        self._is_translating = False

        # 停止录音
        audio_data = self._translate_capture.stop_recording()

        if audio_data:
            # 保存音频文件
            filepath = self._translate_capture.save_audio(audio_data)

            # 语音识别并翻译
            self._process_voice_input(audio_data, translate=True)
        else:
            logger.warning("没有录制到音频")

    def _process_voice_input(self, audio_data: bytes, translate: bool = False):
        """
        处理语音输入

        Args:
            audio_data: 音频数据
            translate: 是否需要翻译
        """
        # 语音识别
        text = self.asr_engine.recognize_bytes(audio_data)

        if text:
            # 文本后处理：去除语气词、添加标点、梳理逻辑
            processed_text = self.text_postprocessor.process(text)
            self._last_recognized_text = processed_text
            logger.info(f"识别结果: {text}")
            logger.info(f"后处理结果: {processed_text}")

            # 如果需要翻译
            if translate:
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
                        self.text_injector.inject(processed_text)
                        return

                    # 创建翻译引擎
                    self._marianmt_engines[engine_key] = get_marianmt_engine(direction)

                # 执行翻译
                engine = self._marianmt_engines[engine_key]
                translated = engine.translate(processed_text)

                if translated:
                    self.text_injector.inject(translated)
                else:
                    logger.warning("翻译失败，注入原文")
                    self.text_injector.inject(processed_text)
            else:
                # 直接注入处理后的文本
                self.text_injector.inject(processed_text)
        else:
            logger.warning("语音识别失败")

    def show_settings(self):
        """显示设置窗口"""
        logger.info("=== 打开设置窗口 ===")

        # 清空按键状态，避免按键状态不同步
        self.hotkey_manager.clear_pressed_keys()

        if self.settings_window is None:
            logger.info("创建新的设置窗口")
            self.settings_window = SettingsWindow()
        else:
            logger.info("使用已存在的设置窗口")

        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()
        logger.info("=== 设置窗口已显示 ===")

    def shutdown(self):
        """关闭应用"""
        logger.info("正在关闭应用...")

        # 停止快捷键监听
        self.hotkey_manager.stop()

        # 停止录音
        if self.audio_capture and self.audio_capture.is_recording():
            self.audio_capture.stop_recording()

        logger.info("应用已关闭")


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

    # 初始化
    if not app.initialize():
        logger.error("应用初始化失败")
        return 1

    # 创建托盘图标
    tray_icon = create_tray_icon(app, qt_app)

    # 创建 macOS 应用菜单栏
    create_menu_bar(app, qt_app)

    # 显示设置窗口
    app.show_settings()

    logger.info("应用启动完成")

    # 运行事件循环
    exit_code = qt_app.exec()

    # 清理
    app.shutdown()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
