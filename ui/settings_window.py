# ui/settings_window.py
# PyQt6 设置窗口

import logging
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
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QKeyEvent

from config import get_settings, IS_MACOS, LANGUAGE_NAMES
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
    """

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.model_manager = get_model_manager()
        self.audio_manager = get_audio_manager()
        self.download_thread: Optional[ModelDownloadThread] = None

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        """初始化 UI"""
        self.setWindowTitle("快人快语 设置")
        self.setMinimumSize(700, 650)

        layout = QVBoxLayout()
        self.setLayout(layout)

        # 快捷键设置
        layout.addWidget(self._create_hotkey_group())

        # 音频设置
        layout.addWidget(self._create_audio_group())

        # 翻译设置
        layout.addWidget(self._create_translation_group())

        # 文本处理设置
        layout.addWidget(self._create_text_processing_group())

        # 音频管理
        layout.addWidget(self._create_audio_management_group())

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.save_settings)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.close)
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

    def _create_hotkey_group(self) -> QGroupBox:
        """创建快捷键设置组"""
        group = QGroupBox("快捷键")
        layout = QGridLayout()

        # 语音输入快捷键
        layout.addWidget(QLabel("语音输入快捷键:"), 0, 0)
        self.voice_hotkey_input = QLineEdit()
        self.voice_hotkey_input.setPlaceholderText("例如: fn 或 right_ctrl")
        layout.addWidget(self.voice_hotkey_input, 0, 1)

        # 快速翻译快捷键
        layout.addWidget(QLabel("快速翻译快捷键:"), 1, 0)
        self.translate_hotkey_input = QLineEdit()
        self.translate_hotkey_input.setPlaceholderText("例如: ctrl+shift+t")
        layout.addWidget(self.translate_hotkey_input, 1, 1)

        # 常用快捷键示例
        examples = QLabel("常用格式: fn, ctrl, alt, shift, ctrl+shift+t, cmd+space")
        examples.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(examples, 2, 0, 1, 2)

        group.setLayout(layout)
        return group

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

    def _create_audio_management_group(self) -> QGroupBox:
        """创建音频管理组"""
        group = QGroupBox("音频管理")
        layout = QGridLayout()

        # 统计信息
        self.audio_stats_label = QLabel()
        self._update_audio_stats()
        layout.addWidget(self.audio_stats_label, 0, 0, 1, 3)

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
        layout.addWidget(list_btn, 2, 0, 1, 3)

        group.setLayout(layout)
        return group

    def _refresh_microphones(self):
        """刷新麦克风列表"""
        self.microphone_combo.clear()
        devices = AudioCapture.list_devices()

        for device in devices:
            self.microphone_combo.addItem(device["name"], device["index"])

    def _update_audio_stats(self):
        """更新音频统计信息"""
        total_size = self.audio_manager.get_total_size()
        file_count = self.audio_manager.get_file_count()

        size_mb = total_size / (1024 * 1024)
        self.audio_stats_label.setText(f"存储: {size_mb:.1f} MB ({file_count} 个文件)")

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
        """下载完成回调"""
        self.download_progress.setVisible(False)

        if direction == "zh-en":
            self.download_zh_en_btn.setEnabled(True)
        else:
            self.download_en_zh_btn.setEnabled(True)

        if success:
            QMessageBox.information(self, "成功", "模型下载完成！")
            self._update_model_status()
        else:
            QMessageBox.warning(self, "失败", "模型下载失败，请检查网络连接。")

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
        # 快捷键
        self.voice_hotkey_input.setText(self.settings.voice_input_hotkey)
        self.translate_hotkey_input.setText(self.settings.quick_translate_hotkey)

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

        # 模型状态
        self._update_model_status()

    def save_settings(self):
        """保存 UI 配置"""
        try:
            # 快捷键
            self.settings.voice_input_hotkey = self.voice_hotkey_input.text()
            self.settings.quick_translate_hotkey = self.translate_hotkey_input.text()

            # 音频
            self.settings.vad_threshold = self.vad_spinbox.value()

            # 翻译
            self.settings.target_language = self.target_lang_combo.currentData()

            # 音频清理
            self.settings.cleanup_enabled = self.auto_cleanup_checkbox.isChecked()
            self.settings.cleanup_days = self.cleanup_days_spinbox.value()

            # 保存到文件
            self.settings.save()

            QMessageBox.information(self, "成功", "设置已保存，部分设置需要重启应用后生效")
            # 不关闭窗口，用户可以继续修改或手动关闭

        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存设置失败: {e}")


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


# ==================== 使用示例 ====================

if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = SettingsWindow()
    window.show()
    sys.exit(app.exec())
