# ui/first_run_wizard.py
# 首次运行向导 - 引导用户下载模型

import logging
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QWizard,
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QCheckBox,
    QProgressBar,
    QGroupBox,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import get_settings, STORAGE_DIR
from models import get_model_manager, ModelType

logger = logging.getLogger(__name__)


class ModelDownloadThread(QThread):
    """模型下载线程"""
    progress = pyqtSignal(int, int)  # current, total
    finished = pyqtSignal(bool, str)  # success, message
    status = pyqtSignal(str)  # status message

    def __init__(self, download_asr: bool, download_zh_en: bool, download_en_zh: bool):
        super().__init__()
        self.download_asr = download_asr
        self.download_zh_en = download_zh_en
        self.download_en_zh = download_en_zh

    def run(self):
        manager = get_model_manager()

        try:
            # 下载 ASR 模型
            if self.download_asr:
                self.status.emit("正在下载 ASR 模型（SenseVoice）...")
                if not manager.check_asr_model("sense-voice"):
                    success = manager.download_asr_model(
                        "sense-voice",
                        lambda c, t: self.progress.emit(c, t),
                    )
                    if not success:
                        self.finished.emit(False, "ASR 模型下载失败")
                        return
                else:
                    self.status.emit("ASR 模型已存在，跳过下载")

            # 下载中文→英文翻译模型
            if self.download_zh_en:
                self.status.emit("正在下载中文→英文翻译模型...")
                model_id = "marianmt-zh-en"
                if not manager.check_translation_model(model_id):
                    success = manager.download_translation_model(
                        model_id,
                        lambda c, t: self.progress.emit(c, t),
                    )
                    if not success:
                        self.finished.emit(False, "翻译模型下载失败")
                        return
                else:
                    self.status.emit("中文→英文翻译模型已存在，跳过下载")

            # 下载英文→中文翻译模型
            if self.download_en_zh:
                self.status.emit("正在下载英文→中文翻译模型...")
                model_id = "marianmt-en-zh"
                if not manager.check_translation_model(model_id):
                    success = manager.download_translation_model(
                        model_id,
                        lambda c, t: self.progress.emit(c, t),
                    )
                    if not success:
                        self.finished.emit(False, "翻译模型下载失败")
                        return
                else:
                    self.status.emit("英文→中文翻译模型已存在，跳过下载")

            self.finished.emit(True, "所有模型下载完成")

        except Exception as e:
            logger.error(f"模型下载错误: {e}")
            self.finished.emit(False, f"下载出错: {e}")


class WelcomePage(QWizardPage):
    """欢迎页面"""

    def __init__(self):
        super().__init__()
        self.setTitle("欢迎使用快人快语")
        layout = QVBoxLayout()

        # 标题
        title = QLabel("快人快语 v1.0.1")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # 说明
        description = QLabel(
            "<p>快人快语是一款本地优先的 AI 语音输入法，"
            "支持语音转文字和实时翻译功能。</p>"
            "<p><b>主要功能：</b></p>"
            "<ul>"
            "<li>🎤 高精度语音识别（支持中英混合）</li>"
            "<li>🌐 实时翻译（中文↔英文）</li>"
            "<li>⌨️ 全局快捷键输入</li>"
            "<li>🔒 本地处理，保护隐私</li>"
            "</ul>"
            "<p>首次使用需要下载 AI 模型文件（约 700MB），"
            "下载完成后即可离线使用。</p>"
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        layout.addStretch()
        self.setLayout(layout)


class ModelSelectionPage(QWizardPage):
    """模型选择页面"""

    def __init__(self):
        super().__init__()
        self.setTitle("选择要下载的模型")
        self.setSubTitle("请选择需要的功能模块")

        layout = QVBoxLayout()

        # ASR 模型（必需）
        asr_group = QGroupBox("语音识别模型（必需）")
        asr_layout = QHBoxLayout()
        self.asr_checkbox = QCheckBox("SenseVoice 语音识别模型 (~700MB)")
        self.asr_checkbox.setChecked(True)
        self.asr_checkbox.setEnabled(False)  # 必需，不可取消
        asr_layout.addWidget(self.asr_checkbox)
        asr_group.setLayout(asr_layout)
        layout.addWidget(asr_group)

        # 翻译模型（可选）
        trans_group = QGroupBox("翻译模型（可选）")
        trans_layout = QVBoxLayout()
        self.zh_en_checkbox = QCheckBox("中文 → 英文 翻译模型 (~1.1GB)")
        self.zh_en_checkbox.setChecked(True)
        self.en_zh_checkbox = QCheckBox("英文 → 中文 翻译模型 (~1.1GB)")
        self.en_zh_checkbox.setChecked(True)
        trans_layout.addWidget(self.zh_en_checkbox)
        trans_layout.addWidget(self.en_zh_checkbox)
        trans_group.setLayout(trans_layout)
        layout.addWidget(trans_group)

        # 提示
        tip = QLabel(
            "<p><b>提示：</b>翻译模型是可选的。如果只需要语音识别功能，"
            "可以取消勾选翻译模型以节省下载时间和存储空间。</p>"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        layout.addStretch()
        self.setLayout(layout)

    def get_selection(self):
        return {
            "asr": True,
            "zh_en": self.zh_en_checkbox.isChecked(),
            "en_zh": self.en_zh_checkbox.isChecked(),
        }


class DownloadPage(QWizardPage):
    """下载页面"""

    def __init__(self):
        super().__init__()
        self.setTitle("下载模型")
        self.setSubTitle("正在下载 AI 模型文件...")
        self.download_thread = None
        self.selection = {}
        self._initialized = False  # 防止重复初始化
        self._wizard = None  # 保存向导引用，用于清理

        layout = QVBoxLayout()

        # 状态标签
        self.status_label = QLabel("准备开始下载...")
        layout.addWidget(self.status_label)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # 详细信息
        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        layout.addStretch()
        self.setLayout(layout)

    def initializePage(self):
        """页面初始化时启动下载"""
        # 防止重复初始化
        if self._initialized:
            return

        self._initialized = True

        # 获取选择
        wizard = self.wizard()
        if wizard and hasattr(wizard, "selection"):
            self.selection = wizard.selection
            self._wizard = wizard  # 保存引用用于清理

        # 启动下载线程
        self.download_thread = ModelDownloadThread(
            download_asr=True,
            download_zh_en=self.selection.get("zh_en", False),
            download_en_zh=self.selection.get("en_zh", False),
        )
        # 使用 Qt.UniqueConnection 避免重复连接
        self.download_thread.progress.connect(
            self._on_progress,
            Qt.ConnectionType.UniqueConnection
        )
        self.download_thread.status.connect(
            self._on_status,
            Qt.ConnectionType.UniqueConnection
        )
        self.download_thread.finished.connect(
            self._on_finished,
            Qt.ConnectionType.UniqueConnection
        )
        self.download_thread.start()

        # 禁用取消按钮
        if self.wizard():
            self.wizard().setOption(QWizard.WizardOption.NoCancelButton, True)

    def cleanupPage(self):
        """页面清理时终止下载线程"""
        if self.download_thread and self.download_thread.isRunning():
            logger.info("正在清理下载线程...")
            # 请求线程终止（优雅退出）
            self.download_thread.terminate()
            # 等待线程结束，最多等待5秒
            if not self.download_thread.wait(5000):
                logger.warning("下载线程未能在5秒内结束，强制终止")
                # 如果还在运行，强制终止
                if self.download_thread.isRunning():
                    self.download_thread.kill()
                    self.download_thread.wait(1000)  # 等待kill生效
            logger.info("下载线程已清理")

    def _on_progress(self, current: int, total: int):
        """更新进度"""
        if total > 0:
            percent = int(current * 100 / total)
            self.progress_bar.setValue(percent)
            self.info_label.setText(f"已下载: {current}/{total} 字节")

    def _on_status(self, message: str):
        """更新状态"""
        self.status_label.setText(message)

    def _on_finished(self, success: bool, message: str):
        """下载完成"""
        if success:
            self.status_label.setText("✓ " + message)
            self.progress_bar.setValue(100)
            # 标记完成
            if self.wizard():
                self.wizard().download_success = True
            # 通知向导更新按钮状态
            self.completeChanged.emit()
        else:
            self.status_label.setText("✗ " + message)
            if self.wizard():
                self.wizard().download_success = False
            QMessageBox.warning(self, "下载失败", f"{message}\n请检查网络连接后重试。")

    def isComplete(self):
        """页面是否完成"""
        return hasattr(self.wizard(), "download_success") and self.wizard().download_success


class CompletionPage(QWizardPage):
    """完成页面"""

    def __init__(self):
        super().__init__()
        self.setTitle("设置完成")
        layout = QVBoxLayout()

        # 成功消息
        success_label = QLabel(
            "<h2>🎉 恭喜！</h2>"
            "<p>快人快语已安装完成，现在可以开始使用了。</p>"
        )
        success_label.setWordWrap(True)
        layout.addWidget(success_label)

        # 使用提示
        tips_group = QGroupBox("使用提示")
        tips_layout = QVBoxLayout()
        tips = QLabel(
            "<p><b>快捷键：</b></p>"
            "<ul>"
            "<li>🎤 语音输入：按住 <b>Option</b> 键说话</li>"
            "<li>🌐 快速翻译：按住 <b>右 Cmd</b> 键说话</li>"
            "</ul>"
            "<p><b>权限设置：</b></p>"
            "<ul>"
            "<li>首次使用时，系统会请求麦克风权限，请点击「允许」</li>"
            "<li>如果快捷键无效，请在「系统设置 → 隐私与安全性 → 辅助功能」中添加 FastVoice</li>"
            "</ul>"
        )
        tips.setWordWrap(True)
        tips_layout.addWidget(tips)
        tips_group.setLayout(tips_layout)
        layout.addWidget(tips_group)

        # 未签名提示
        warning_label = QLabel(
            "<p><b>首次打开提示：</b><br>"
            "由于应用未签名，首次打开需要在 Finder 中<strong>右键点击应用 → 选择「打开」</strong>。<br>"
            "之后就可以正常双击打开了。</p>"
        )
        warning_label.setWordWrap(True)
        warning_label.setStyleSheet("color: #d97706; background: #fef3c7; padding: 10px; border-radius: 5px;")
        layout.addWidget(warning_label)

        layout.addStretch()
        self.setLayout(layout)


class FirstRunWizard(QWizard):
    """首次运行向导"""

    def __init__(self):
        import traceback
        logger.info("=== FirstRunWizard.__init__() 被调用 ===")
        logger.info(f"向导创建调用栈:\n{''.join(traceback.format_stack())}")

        super().__init__()
        self.setWindowTitle("快人快语 - 首次运行向导")
        self.setMinimumSize(600, 450)
        self.selection = {}
        self.download_success = False

        # 添加页面
        self.addPage(WelcomePage())
        self.addPage(ModelSelectionPage())
        self.addPage(DownloadPage())
        self.addPage(CompletionPage())

        # 设置向导选项
        self.setOption(QWizard.WizardOption.HaveHelpButton, False)
        self.setOption(QWizard.WizardOption.NoCancelButton, False)

        # 获取模型选择
        self.currentIdChanged.connect(self._on_page_changed)

        logger.info("=== FirstRunWizard 初始化完成 ===")

    def _on_page_changed(self, page_id):
        """页面切换时处理"""
        page = self.page(page_id)
        if isinstance(page, ModelSelectionPage):
            # 保存选择
            self.selection = page.get_selection()

    def reject(self):
        """用户取消时清理资源"""
        # 清理下载线程
        download_page = self.page(2)  # DownloadPage 是第3页（索引2）
        if isinstance(download_page, DownloadPage):
            download_page.cleanupPage()
        return super().reject()

    def accept(self):
        """完成时创建标记文件"""
        # 先清理下载线程，确保所有后台线程已停止
        download_page = self.page(2)  # DownloadPage 是第3页（索引2）
        if isinstance(download_page, DownloadPage):
            download_page.cleanupPage()

        # 创建标记文件（在主线程执行）
        try:
            marker_file = STORAGE_DIR / ".first_run_completed"
            marker_file.parent.mkdir(parents=True, exist_ok=True)
            marker_file.touch()
            logger.info("首次运行向导完成，已创建标记文件")
        except Exception as e:
            logger.error(f"创建标记文件失败: {e}")

        # 调用父类 accept（关闭向导）
        super().accept()


# ==================== 使用示例 ====================

if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    wizard = FirstRunWizard()
    wizard.exec()
