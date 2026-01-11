# ui/settings_window.py
# PyQt6 设置窗口

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QSpinBox,
    QGroupBox,
    QMessageBox,
    QProgressBar,
    QListWidget,
    QListWidgetItem,
    QDialog,
    QHeaderView,
    QScrollArea,
    QButtonGroup,
    QRadioButton,
    QFrame,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QKeyEvent

from config import get_settings, IS_MACOS, LANGUAGE_NAMES, HOTKEY_PRESETS
from core import AudioCapture
from models import get_model_manager, ModelType
from storage import get_audio_manager

logger = logging.getLogger(__name__)


class ModelDownloadThread(QThread):
    """模型下载线程"""
    progress = pyqtSignal(int, int)  # current, total
    finished = pyqtSignal(bool)  # success

    def __init__(self, model_type: str, model_id: str):
        super().__init__()
        self.model_type = model_type
        self.model_id = model_id

    def run(self):
        manager = get_model_manager()

        if self.model_type == ModelType.ASR:
            success = manager.download_asr_model(
                self.model_id,
                lambda c, t: self.progress.emit(c, t),
            )
        else:
            success = manager.download_translation_model(
                self.model_id,
                lambda c, t: self.progress.emit(c, t),
            )

        self.finished.emit(success)


class SettingsWindow(QWidget):
    """
    设置窗口

    包含:
    - 快捷键设置
    - 音频设置
    - 翻译设置
    - 音频管理

    v1.4.2 改进：音频统计异步更新，防止主线程阻塞
    """

    # 定义信号（跨线程安全更新 UI）
    _update_stats_signal = pyqtSignal(int, int)  # total_size, file_count

    def __init__(self, apply_callback=None):
        """
        初始化设置窗口

        Args:
            apply_callback: 设置应用回调函数，签名为 (changed_settings: dict) -> bool
        """
        super().__init__()
        self.settings = get_settings()
        self.model_manager = get_model_manager()
        self.audio_manager = get_audio_manager()
        self.download_thread: Optional[ModelDownloadThread] = None
        self._apply_callback = apply_callback  # v1.4.2: 设置应用回调

        # v1.4.2: 缓存的统计值（用于快速显示）
        self._cached_stats = None  # (total_size, file_count)
        self._stats_update_pending = False  # 是否有待处理的更新请求

        # 连接信号到槽（线程安全）
        self._update_stats_signal.connect(self._display_stats)

        self.init_ui()
        self.load_settings()

    def closeEvent(self, event):
        """
        窗口关闭事件 - 只隐藏而不退出应用

        这样可以保持应用在后台运行，快捷键仍然可用
        """
        logger.info("设置窗口关闭事件触发，隐藏窗口")
        self.hide()
        event.ignore()  # 忽略关闭事件，阻止窗口被销毁

    def showEvent(self, event):
        """
        窗口显示事件 - 重新加载音频统计信息

        v1.4.2 改进：使用缓存值快速显示，后台异步更新
        """
        super().showEvent(event)
        logger.info("设置窗口显示事件触发，更新音频统计")

        # 立即显示缓存值（如果有）
        if self._cached_stats:
            total_size, file_count = self._cached_stats
            self._display_stats(total_size, file_count)

        # 如果没有待处理的更新请求，启动后台更新
        if not self._stats_update_pending:
            self._stats_update_pending = True
            # 延迟 100ms 后更新，避免阻塞窗口显示动画
            QTimer.singleShot(100, self._update_audio_stats_async)

    def init_ui(self):
        """初始化 UI"""
        self.setWindowTitle("快人快语 设置")
        self.setMinimumSize(680, 720)
        self.resize(680, 720)

        # 创建滚动区域，防止内容超出
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        # 主容器
        container = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        container.setLayout(layout)

        # 快捷键设置
        layout.addWidget(self._create_hotkey_group())

        # 音频设置
        layout.addWidget(self._create_audio_group())

        # 翻译设置
        layout.addWidget(self._create_translation_group())

        # 文本处理
        layout.addWidget(self._create_text_processing_group())

        # 文字注入
        layout.addWidget(self._create_injection_group())

        # 音频管理
        layout.addWidget(self._create_audio_management_group())

        # 日志管理
        layout.addWidget(self._create_log_management_group())

        # 添加弹性空间
        layout.addStretch()

        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        save_btn = QPushButton("保存")
        save_btn.setMinimumWidth(90)
        save_btn.clicked.connect(self.save_settings)
        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumWidth(90)
        cancel_btn.clicked.connect(self.close)
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        # 设置滚动区域
        scroll.setWidget(container)

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _create_hotkey_group(self) -> QGroupBox:
        """
        创建快捷键设置组 (v1.4.2 改进版)

        改进:
        - 使用 QComboBox 预设选项
        - 使用 QButtonGroup + QRadioButton 选择模式
        - 使用 QLabel buddy 关系提高可访问性
        """
        group = QGroupBox("快捷键")
        layout = QGridLayout()
        layout.setVerticalSpacing(15)  # 增加垂直间距
        layout.setHorizontalSpacing(10)

        # ===== 语音输入快捷键 =====
        voice_label = QLabel("&语音输入:")
        voice_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(voice_label, 0, 0)

        # 快捷键预设下拉框
        hotkey_label = QLabel("快捷键:")
        layout.addWidget(hotkey_label, 1, 0)

        self.voice_hotkey_combo = QComboBox()
        self._populate_hotkey_presets(self.voice_hotkey_combo)
        hotkey_label.setBuddy(self.voice_hotkey_combo)  # 设置 buddy 关系
        layout.addWidget(self.voice_hotkey_combo, 1, 1, 1, 2)

        # 触发模式选择（使用单选按钮）
        mode_label = QLabel("触发方式:")
        layout.addWidget(mode_label, 2, 0)

        self.voice_mode_group = QButtonGroup(self)
        self.voice_mode_single = QRadioButton("一次长按")
        self.voice_mode_double = QRadioButton("两次按键")

        # 添加说明子标签
        single_desc = QLabel("按下开始，松开停止")
        single_desc.setStyleSheet("color: gray; font-size: 9px; margin-left: 20px;")
        double_desc = QLabel("双击后长按开始录音")
        double_desc.setStyleSheet("color: gray; font-size: 9px; margin-left: 20px;")

        self.voice_mode_group.addButton(self.voice_mode_single, 0)
        self.voice_mode_group.addButton(self.voice_mode_double, 1)
        self.voice_mode_group.setExclusive(True)

        layout.addWidget(self.voice_mode_single, 2, 1)
        layout.addWidget(single_desc, 2, 2)
        layout.addWidget(self.voice_mode_double, 3, 1)
        layout.addWidget(double_desc, 3, 2)

        # ===== 分隔线 =====
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator, 4, 0, 1, 3)

        # ===== 快速翻译快捷键 =====
        translate_label = QLabel("&快速翻译:")
        translate_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(translate_label, 5, 0)

        # 快捷键预设下拉框
        translate_hotkey_label = QLabel("快捷键:")
        layout.addWidget(translate_hotkey_label, 6, 0)

        self.translate_hotkey_combo = QComboBox()
        self._populate_hotkey_presets(self.translate_hotkey_combo)
        translate_hotkey_label.setBuddy(self.translate_hotkey_combo)
        layout.addWidget(self.translate_hotkey_combo, 6, 1, 1, 2)

        # 触发模式选择
        translate_mode_label = QLabel("触发方式:")
        layout.addWidget(translate_mode_label, 7, 0)

        self.translate_mode_group = QButtonGroup(self)
        self.translate_mode_single = QRadioButton("一次长按")
        self.translate_mode_double = QRadioButton("两次按键")

        translate_single_desc = QLabel("按下开始，松开停止")
        translate_single_desc.setStyleSheet("color: gray; font-size: 9px; margin-left: 20px;")
        translate_double_desc = QLabel("双击后长按开始录音")
        translate_double_desc.setStyleSheet("color: gray; font-size: 9px; margin-left: 20px;")

        self.translate_mode_group.addButton(self.translate_mode_single, 0)
        self.translate_mode_group.addButton(self.translate_mode_double, 1)
        self.translate_mode_group.setExclusive(True)

        layout.addWidget(self.translate_mode_single, 7, 1)
        layout.addWidget(translate_single_desc, 7, 2)
        layout.addWidget(self.translate_mode_double, 8, 1)
        layout.addWidget(translate_double_desc, 8, 2)

        # ===== 恢复快捷键监听按钮 =====
        recover_btn = QPushButton("🔄 恢复快捷键监听")
        recover_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff9800;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #fb8c00;
            }
        """)
        recover_btn.clicked.connect(self._on_recover_hotkey)
        layout.addWidget(recover_btn, 9, 0, 1, 3)

        group.setLayout(layout)
        return group

    def _populate_hotkey_presets(self, combo: QComboBox):
        """填充快捷键预设选项"""
        presets = HOTKEY_PRESETS["macos"] if IS_MACOS else HOTKEY_PRESETS["windows"]
        for key, label in presets:
            combo.addItem(label, key)  # label 显示，key 存储

    def _create_audio_group(self) -> QGroupBox:
        """创建音频设置组"""
        group = QGroupBox("音频设置")
        layout = QGridLayout()

        # 麦克风设备
        layout.addWidget(QLabel("麦克风设备:"), 0, 0)
        self.microphone_combo = QComboBox()
        self._refresh_microphones()
        layout.addWidget(self.microphone_combo, 0, 1)

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_microphones)
        layout.addWidget(refresh_btn, 0, 2)

        # VAD 灵敏度
        layout.addWidget(QLabel("VAD 灵敏度 (毫秒):"), 1, 0)
        self.vad_spinbox = QSpinBox()
        self.vad_spinbox.setRange(200, 2000)
        self.vad_spinbox.setSuffix(" ms")
        layout.addWidget(self.vad_spinbox, 1, 1)

        group.setLayout(layout)
        return group

    def _create_translation_group(self) -> QGroupBox:
        """创建翻译设置组"""
        group = QGroupBox("翻译设置")
        layout = QGridLayout()

        # 目标语言
        layout.addWidget(QLabel("目标语言:"), 0, 0)
        self.target_lang_combo = QComboBox()
        for code, name in LANGUAGE_NAMES.items():
            self.target_lang_combo.addItem(name, code)
        layout.addWidget(self.target_lang_combo, 0, 1)

        # 翻译模型状态
        layout.addWidget(QLabel("翻译模型:"), 1, 0)
        model_status_layout = QVBoxLayout()
        self.zh_en_model_label = QLabel("中文→英文: 未下载")
        self.en_zh_model_label = QLabel("英文→中文: 未下载")
        model_status_layout.addWidget(self.zh_en_model_label)
        model_status_layout.addWidget(self.en_zh_model_label)
        layout.addLayout(model_status_layout, 1, 1)

        # 下载模型按钮
        download_btn_layout = QHBoxLayout()
        self.download_zh_en_btn = QPushButton("下载中→英")
        self.download_zh_en_btn.clicked.connect(lambda: self._download_marianmt_model("zh-en"))
        self.download_en_zh_btn = QPushButton("下载英→中")
        self.download_en_zh_btn.clicked.connect(lambda: self._download_marianmt_model("en-zh"))
        download_btn_layout.addWidget(self.download_zh_en_btn)
        download_btn_layout.addWidget(self.download_en_zh_btn)
        layout.addLayout(download_btn_layout, 2, 1)

        # 下载进度
        self.download_progress = QProgressBar()
        self.download_progress.setVisible(False)
        layout.addWidget(self.download_progress, 3, 1)

        group.setLayout(layout)
        return group

    def _create_text_processing_group(self) -> QGroupBox:
        """创建文本处理设置组"""
        group = QGroupBox("文本处理")
        layout = QGridLayout()

        # 说明文字
        description = QLabel(
            "自动处理识别结果："
            "• 去除语气词（嗯嗯、啊啊等）"
            "• 智能添加标点符号"
        )
        description.setStyleSheet("color: #333; font-size: 11px;")
        layout.addWidget(description, 0, 0, 1, 3)

        # 状态说明
        status = QLabel("文本处理已启用（基于规则）")
        status.setStyleSheet("color: green; font-size: 10px;")
        layout.addWidget(status, 1, 0, 1, 3)

        group.setLayout(layout)
        return group

    def _create_injection_group(self) -> QGroupBox:
        """
        创建文字注入设置组 (v1.4.2 改进版)

        改进:
        - 明确标注 typing 模式仅支持英文
        - 添加警告提示
        - 使用 QLabel buddy 关系
        """
        group = QGroupBox("文字注入")
        layout = QGridLayout()

        # 说明文字
        description = QLabel("选择文字注入方式：")
        description.setStyleSheet("color: #333; font-size: 11px;")
        layout.addWidget(description, 0, 0, 1, 2)

        # 注入方式选择
        method_label = QLabel("&注入方式:")
        layout.addWidget(method_label, 1, 0)

        self.injection_method_combo = QComboBox()
        method_label.setBuddy(self.injection_method_combo)

        from config import IS_WINDOWS
        from core.text_injector import TextInjector

        injector = TextInjector()
        available_methods = injector.get_available_methods()

        # 改进名称，明确标注 typing 的限制
        method_names = {
            "clipboard": "中文输入（剪贴板模式）",
            "typing": "仅英文输入（typing 模式）⚠️",
            "win32_native": "Windows 原生（不污染剪贴板）"
        }

        for method in available_methods:
            self.injection_method_combo.addItem(method_names.get(method, method), method)

        layout.addWidget(self.injection_method_combo, 1, 1)

        # 警告提示（typing 模式）
        self.typing_warning = QLabel("⚠️ typing 模式仅支持英文字符，无法输入中文")
        self.typing_warning.setStyleSheet("color: #ff9800; font-size: 10px;")
        self.typing_warning.setVisible(False)
        layout.addWidget(self.typing_warning, 2, 0, 1, 2)

        # 通用说明
        help_text = QLabel(
            "提示: Windows 原生方式不会污染剪贴板，但仅在 Windows 上可用"
        )
        help_text.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(help_text, 3, 0, 1, 2)

        # 连接信号：当选中 typing 时显示警告
        self.injection_method_combo.currentIndexChanged.connect(
            self._on_injection_method_changed
        )

        group.setLayout(layout)
        return group

    def _on_injection_method_changed(self, index: int):
        """注入方式改变时的处理"""
        method = self.injection_method_combo.itemData(index)
        # 显示 typing 警告
        self.typing_warning.setVisible(method == "typing")

    def _create_audio_management_group(self) -> QGroupBox:
        """创建音频管理组"""
        group = QGroupBox("音频管理")
        layout = QGridLayout()

        # 统计信息
        self.audio_stats_label = QLabel()
        self._update_audio_stats()
        layout.addWidget(self.audio_stats_label, 0, 0, 1, 4)

        # 自动清理
        self.auto_cleanup_checkbox = QCheckBox("自动清理")
        layout.addWidget(self.auto_cleanup_checkbox, 1, 0)

        self.cleanup_days_spinbox = QSpinBox()
        self.cleanup_days_spinbox.setRange(1, 90)
        self.cleanup_days_spinbox.setSuffix(" 天")
        layout.addWidget(self.cleanup_days_spinbox, 1, 1)

        cleanup_btn = QPushButton("立即清理")
        cleanup_btn.clicked.connect(self._cleanup_audio)
        layout.addWidget(cleanup_btn, 1, 2)

        # 查看音频列表
        list_btn = QPushButton("查看音频列表...")
        list_btn.clicked.connect(self._show_audio_list)
        layout.addWidget(list_btn, 1, 3)

        group.setLayout(layout)
        return group

    def _create_log_management_group(self) -> QGroupBox:
        """创建日志管理组"""
        group = QGroupBox("日志管理")
        layout = QGridLayout()

        # 日志文件信息
        self.log_stats_label = QLabel()
        self._update_log_stats()
        layout.addWidget(self.log_stats_label, 0, 0, 1, 2)

        # 清空日志按钮
        clear_logs_btn = QPushButton("清空日志文件")
        clear_logs_btn.clicked.connect(self._clear_logs)
        layout.addWidget(clear_logs_btn, 0, 2)

        group.setLayout(layout)
        return group

    def _update_log_stats(self):
        """更新日志统计信息"""
        logs_dir = Path("logs")
        if not logs_dir.exists():
            self.log_stats_label.setText("日志文件夹不存在")
            return

        log_files = list(logs_dir.glob("*.log"))
        if not log_files:
            self.log_stats_label.setText("暂无日志文件")
            return

        # 计算总大小
        total_size = sum(f.stat().st_size for f in log_files)
        size_mb = total_size / (1024 * 1024)
        self.log_stats_label.setText(f"日志文件: {len(log_files)} 个，共 {size_mb:.2f} MB")

    def _clear_logs(self):
        """清空日志文件"""
        logs_dir = Path("logs")
        if not logs_dir.exists():
            QMessageBox.information(self, "提示", "日志文件夹不存在")
            return

        # 获取所有日志文件
        log_files = list(logs_dir.glob("*.log"))
        if not log_files:
            QMessageBox.information(self, "提示", "没有日志文件")
            return

        # 计算总大小
        total_size = sum(f.stat().st_size for f in log_files)
        size_mb = total_size / (1024 * 1024)

        reply = QMessageBox.question(
            self,
            "确认清空",
            f"确定要清空所有日志文件吗？\n共 {len(log_files)} 个文件，{size_mb:.2f} MB\n\n清空后日志文件会保留，但内容会被清空。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # 清空每个日志文件（而不是删除文件）
                for log_file in log_files:
                    log_file.write_text("")
                QMessageBox.information(self, "完成", f"已清空 {len(log_files)} 个日志文件")
                self._update_log_stats()
            except Exception as e:
                QMessageBox.warning(self, "错误", f"清空日志失败: {e}")

    def _refresh_microphones(self):
        """刷新麦克风列表"""
        self.microphone_combo.clear()
        devices = AudioCapture.list_devices()

        for device in devices:
            self.microphone_combo.addItem(device["name"], device["index"])

    def _update_audio_stats(self):
        """
        更新音频统计信息（同步版本，已废弃）

        v1.4.2: 此方法会阻塞主线程，建议使用 _update_audio_stats_async
        保留此方法仅用于向后兼容
        """
        total_size = self.audio_manager.get_total_size()
        file_count = self.audio_manager.get_file_count()

        # 缓存统计值
        self._cached_stats = (total_size, file_count)

        size_mb = total_size / (1024 * 1024)
        self.audio_stats_label.setText(f"存储: {size_mb:.1f} MB ({file_count} 个文件)")

    def _display_stats(self, total_size: int, file_count: int):
        """
        显示统计信息（线程安全）

        v1.4.2 新增：通过信号从后台线程安全更新 UI

        Args:
            total_size: 总大小（字节）
            file_count: 文件数量
        """
        size_mb = total_size / (1024 * 1024)
        self.audio_stats_label.setText(f"存储: {size_mb:.1f} MB ({file_count} 个文件)")

    def _update_audio_stats_async(self):
        """
        异步更新音频统计信息

        v1.4.2 新增：在后台线程执行，防止阻塞主线程
        """
        def update():
            try:
                # 在后台线程执行耗时操作
                total_size = self.audio_manager.get_total_size()
                file_count = self.audio_manager.get_file_count()

                # 更新缓存
                self._cached_stats = (total_size, file_count)

                # 使用 Qt 信号更新 UI（线程安全）
                self._update_stats_signal.emit(total_size, file_count)

                logger.debug(f"音频统计异步更新完成: {file_count} 个文件")
            except Exception as e:
                logger.error(f"异步更新音频统计失败: {e}")
            finally:
                self._stats_update_pending = False

        # 在后台线程执行
        import threading
        thread = threading.Thread(target=update, daemon=True)
        thread.start()

    def _download_marianmt_model(self, direction: str):
        """下载 MarianMT 翻译模型"""
        if self.download_thread and self.download_thread.isRunning():
            QMessageBox.warning(self, "提示", "模型正在下载中...")
            return

        model_id = f"marianmt-{direction}"
        model_size = self.model_manager.get_model_size(ModelType.TRANSLATION, model_id)

        lang_name = "中文→英文" if direction == "zh-en" else "英文→中文"

        reply = QMessageBox.question(
            self,
            "确认下载",
            f"确定要下载 {lang_name} 翻译模型吗？\n模型大小: {model_size}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.download_progress.setVisible(True)
            self.download_progress.setValue(0)

            if direction == "zh-en":
                self.download_zh_en_btn.setEnabled(False)
            else:
                self.download_en_zh_btn.setEnabled(False)

            self.download_thread = ModelDownloadThread(ModelType.TRANSLATION, model_id)
            self.download_thread.progress.connect(self._on_download_progress)
            self.download_thread.finished.connect(lambda success: self._on_download_finished(success, direction))
            self.download_thread.start()

    def _on_download_progress(self, current: int, total: int):
        """下载进度回调"""
        if total > 0:
            progress = int(current * 100 / total)
            self.download_progress.setValue(progress)

    def _on_download_finished(self, success: bool, direction: str):
        """模型下载完成处理"""
        if success:
            QMessageBox.information(self, "成功", f"{direction} 模型下载完成！")
            self.refresh_model_list()
        else:
            QMessageBox.warning(self, "失败", f"{direction} 模型下载失败！")

    def _on_recover_hotkey(self):
        """恢复快捷键监听"""
        try:
            from core import get_hotkey_manager
            hotkey_manager = get_hotkey_manager()

            if hotkey_manager:
                success = hotkey_manager.recover()
                if success:
                    QMessageBox.information(
                        self,
                        "恢复成功",
                        "✓ 快捷键监听已恢复！\n\n现在可以尝试使用快捷键了。"
                    )
                    logger.info("用户手动恢复了快捷键监听")
                else:
                    QMessageBox.warning(
                        self,
                        "恢复失败",
                        "✗ 恢复快捷键监听失败\n\n请尝试重启应用。"
                    )
                    logger.warning("用户手动恢复快捷键监听失败")
            else:
                QMessageBox.warning(
                    self,
                    "错误",
                    "✗ 无法获取快捷键管理器\n\n请尝试重启应用。"
                )
        except Exception as e:
            logger.error(f"恢复快捷键监听时发生错误: {e}")
            QMessageBox.critical(
                self,
                "错误",
                f"✗ 恢复快捷键监听时发生错误:\n{str(e)}\n\n请尝试重启应用。"
            )

    def _update_model_status(self):
        """更新模型状态显示"""
        # 更新中文→英文模型状态
        if self.model_manager.check_translation_model("marianmt-zh-en"):
            self.zh_en_model_label.setText("中文→英文: 已下载 ✓")
            self.download_zh_en_btn.setEnabled(False)
        else:
            self.zh_en_model_label.setText("中文→英文: 未下载")
            self.download_zh_en_btn.setEnabled(True)

        # 更新英文→中文模型状态
        if self.model_manager.check_translation_model("marianmt-en-zh"):
            self.en_zh_model_label.setText("英文→中文: 已下载 ✓")
            self.download_en_zh_btn.setEnabled(False)
        else:
            self.en_zh_model_label.setText("英文→中文: 未下载")
            self.download_en_zh_btn.setEnabled(True)

    def _cleanup_audio(self):
        """清理音频文件"""
        days = self.cleanup_days_spinbox.value()
        file_count = self.audio_manager.get_file_count()

        if file_count == 0:
            QMessageBox.information(self, "提示", "当前没有音频文件")
            return

        reply = QMessageBox.question(
            self,
            "确认清理",
            f"确定要删除 {days} 天前（含）的音频文件吗？\n共 {file_count} 个文件",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            count = self.audio_manager.delete_by_days(days)
            QMessageBox.information(self, "完成", f"已删除 {count} 个文件")
            self._update_audio_stats()

    def _show_audio_list(self):
        """显示音频列表"""
        dialog = AudioListDialog(self.audio_manager, self)
        dialog.exec()
        # 对话框关闭后更新统计信息
        self._update_audio_stats()

    def load_settings(self):
        """加载配置到 UI"""
        # ===== 快捷键配置 (v1.4.2) =====
        voice_key = self.settings.voice_input_hotkey
        voice_mode = self.settings.voice_input_mode

        # 设置快捷键下拉框
        for i in range(self.voice_hotkey_combo.count()):
            if self.voice_hotkey_combo.itemData(i) == voice_key:
                self.voice_hotkey_combo.setCurrentIndex(i)
                break

        # 设置触发模式单选按钮
        if voice_mode == "double_press":
            self.voice_mode_double.setChecked(True)
        else:
            self.voice_mode_single.setChecked(True)

        # 翻译快捷键
        translate_key = self.settings.quick_translate_hotkey
        translate_mode = self.settings.translate_mode

        # 设置快捷键下拉框
        for i in range(self.translate_hotkey_combo.count()):
            if self.translate_hotkey_combo.itemData(i) == translate_key:
                self.translate_hotkey_combo.setCurrentIndex(i)
                break

        # 设置触发模式单选按钮
        if translate_mode == "double_press":
            self.translate_mode_double.setChecked(True)
        else:
            self.translate_mode_single.setChecked(True)

        # 音频
        self.vad_spinbox.setValue(self.settings.vad_threshold)

        # 翻译
        # 目标语言
        for i in range(self.target_lang_combo.count()):
            if self.target_lang_combo.itemData(i) == self.settings.target_language:
                self.target_lang_combo.setCurrentIndex(i)
                break

        # 音频清理
        self.auto_cleanup_checkbox.setChecked(self.settings.cleanup_enabled)
        self.cleanup_days_spinbox.setValue(self.settings.cleanup_days)

        # 注入方式
        current_method = self.settings.injection_method
        for i in range(self.injection_method_combo.count()):
            if self.injection_method_combo.itemData(i) == current_method:
                self.injection_method_combo.setCurrentIndex(i)
                break

        # 模型状态
        self._update_model_status()

    def save_settings(self):
        """
        保存 UI 配置

        v1.4.2: 新增快捷键验证机制 + 立即应用设置
        """
        try:
            # ===== 验证快捷键配置 =====
            is_valid, error_msg = self._validate_hotkey_config()
            if not is_valid:
                QMessageBox.warning(self, "配置错误", f"快捷键配置无效：\n\n{error_msg}")
                return

            # ===== 检查 typing 模式警告 =====
            injection_method = self.injection_method_combo.currentData()
            if injection_method == "typing":
                reply = QMessageBox.question(
                    self,
                    "确认使用 typing 模式",
                    "⚠️ typing 模式仅支持英文字符输入，无法输入中文。\n\n"
                    "您确定要使用此模式吗？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

            # ===== 跟踪哪些设置发生了变化 =====
            changed_settings = {}

            # ===== 保存语音输入配置 =====
            voice_key = self.voice_hotkey_combo.currentData()
            voice_mode = "double_press" if self.voice_mode_double.isChecked() else "single_press"
            old_voice_config = self.settings.get("hotkeys.voice_input", {})

            # 检查快捷键或模式是否改变
            voice_changed = (
                isinstance(old_voice_config, dict) and (
                    old_voice_config.get("key") != voice_key or
                    old_voice_config.get("mode") != voice_mode
                )
            ) or (
                isinstance(old_voice_config, str) and old_voice_config != voice_key
            )

            voice_config = {"key": voice_key, "mode": voice_mode}
            self.settings.set("hotkeys.voice_input", voice_config)

            # ===== 保存翻译配置 =====
            translate_key = self.translate_hotkey_combo.currentData()
            translate_mode = "double_press" if self.translate_mode_double.isChecked() else "single_press"
            old_translate_config = self.settings.get("hotkeys.quick_translate", {})

            # 检查快捷键或模式是否改变
            translate_changed = (
                isinstance(old_translate_config, dict) and (
                    old_translate_config.get("key") != translate_key or
                    old_translate_config.get("mode") != translate_mode
                )
            ) or (
                isinstance(old_translate_config, str) and old_translate_config != translate_key
            )

            translate_config = {"key": translate_key, "mode": translate_mode}
            self.settings.set("hotkeys.quick_translate", translate_config)

            if voice_changed or translate_changed:
                changed_settings["hotkeys"] = True

            # 音频
            old_vad = self.settings.vad_threshold
            self.settings.vad_threshold = self.vad_spinbox.value()
            if old_vad != self.settings.vad_threshold:
                changed_settings["vad_threshold"] = True

            # 翻译
            old_target = self.settings.target_language
            self.settings.target_language = self.target_lang_combo.currentData()
            if old_target != self.settings.target_language:
                changed_settings["target_language"] = True

            # 音频清理
            self.settings.cleanup_enabled = self.auto_cleanup_checkbox.isChecked()
            self.settings.cleanup_days = self.cleanup_days_spinbox.value()

            # 注入方式
            old_injection = self.settings.injection_method
            self.settings.injection_method = injection_method
            if old_injection != self.settings.injection_method:
                changed_settings["injection_method"] = True

            # 保存到文件
            self.settings.save()

            # ===== 应用设置更改（如果提供了回调）=====
            if self._apply_callback and changed_settings:
                try:
                    success = self._apply_callback(changed_settings)
                    if success:
                        QMessageBox.information(self, "成功", "设置已保存并已立即生效！")
                    else:
                        QMessageBox.warning(
                            self,
                            "部分成功",
                            "设置已保存，但部分设置应用失败。\n\n"
                            "请尝试重启应用以应用所有设置。"
                        )
                except Exception as e:
                    logger.error(f"应用设置回调失败: {e}")
                    QMessageBox.warning(
                        self,
                        "部分成功",
                        f"设置已保存，但应用设置时出错：{e}\n\n"
                        "请尝试重启应用以应用所有设置。"
                    )
            else:
                QMessageBox.information(self, "成功", "设置已保存，部分设置需要重启应用后生效")

            # 不关闭窗口，用户可以继续修改或手动关闭

        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存设置失败: {e}")

    def _validate_hotkey_config(self) -> tuple[bool, str]:
        """
        验证快捷键配置

        Returns:
            (is_valid, error_message)
        """
        voice_key = self.voice_hotkey_combo.currentData()
        translate_key = self.translate_hotkey_combo.currentData()

        # 检查是否使用相同的快捷键
        if voice_key == translate_key:
            return False, "语音输入和快速翻译不能使用相同的快捷键"

        # 检查快捷键是否有效
        presets = HOTKEY_PRESETS["macos"] if IS_MACOS else HOTKEY_PRESETS["windows"]
        valid_keys = [key for key, _ in presets]

        if voice_key not in valid_keys:
            return False, f"无效的语音输入快捷键: {voice_key}"

        if translate_key not in valid_keys:
            return False, f"无效的翻译快捷键: {translate_key}"

        return True, ""


class AudioListDialog(QDialog):
    """音频文件管理对话框"""

    def __init__(self, audio_manager, parent=None):
        super().__init__(parent)
        self.audio_manager = audio_manager
        self.setWindowTitle("音频文件管理")
        self.setMinimumSize(700, 500)
        self._setup_ui()
        self._load_files()

    def _setup_ui(self):
        """设置界面"""
        layout = QVBoxLayout(self)

        # 统计信息
        total_size = self.audio_manager.get_total_size()
        file_count = self.audio_manager.get_file_count()
        size_mb = total_size / (1024 * 1024)
        stats_label = QLabel(f"存储: {size_mb:.1f} MB ({file_count} 个文件)")
        layout.addWidget(stats_label)

        # 文件列表
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        layout.addWidget(self.file_list)

        # 按钮区域
        btn_layout = QHBoxLayout()

        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self._select_all)
        btn_layout.addWidget(self.select_all_btn)

        self.invert_btn = QPushButton("反选")
        self.invert_btn.clicked.connect(self._invert_selection)
        btn_layout.addWidget(self.invert_btn)

        self.delete_btn = QPushButton("删除选中")
        self.delete_btn.clicked.connect(self._delete_selected)
        btn_layout.addWidget(self.delete_btn)

        self.open_folder_btn = QPushButton("打开音频文件夹")
        self.open_folder_btn.clicked.connect(self._open_audio_folder)
        btn_layout.addWidget(self.open_folder_btn)

        layout.addLayout(btn_layout)

    def _load_files(self):
        """加载文件列表"""
        self.file_list.clear()
        files = self.audio_manager.list_audio_files()

        if not files:
            item = QListWidgetItem("暂无音频文件")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            self.file_list.addItem(item)
            self.delete_btn.setEnabled(False)
            return

        self.delete_btn.setEnabled(True)

        for file_info in files:
            item = QListWidgetItem()
            # 显示: 文件名 | 大小 | 日期
            text = f"{file_info.name} | {file_info.size_mb:.2f} MB | {file_info.created_time.strftime('%Y-%m-%d %H:%M')}"
            item.setText(text)
            item.setData(Qt.ItemDataRole.UserRole, file_info.path)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.file_list.addItem(item)

    def _select_all(self):
        """全选"""
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                item.setCheckState(Qt.CheckState.Checked)

    def _invert_selection(self):
        """反选"""
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                state = item.checkState()
                item.setCheckState(
                    Qt.CheckState.Unchecked if state == Qt.CheckState.Checked else Qt.CheckState.Checked
                )

    def _delete_selected(self):
        """删除选中的文件"""
        selected_paths = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                path = item.data(Qt.ItemDataRole.UserRole)
                if path:
                    selected_paths.append(path)

        if not selected_paths:
            QMessageBox.information(self, "提示", "请先选择要删除的文件")
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除选中的 {len(selected_paths)} 个文件吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            count = self.audio_manager.delete_files(selected_paths)
            QMessageBox.information(self, "完成", f"已删除 {count} 个文件")
            self._load_files()

    def _open_audio_folder(self):
        """打开音频文件夹"""
        audio_dir = str(self.audio_manager.audio_dir)

        try:
            if IS_MACOS:
                # macOS 使用 open
                subprocess.run(["open", audio_dir])
            else:
                # Windows 使用 explorer
                subprocess.run(["explorer", audio_dir])
        except Exception as e:
            QMessageBox.warning(self, "错误", f"无法打开文件夹: {e}")


# ==================== 使用示例 ====================

if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = SettingsWindow()
    window.show()
    sys.exit(app.exec())
