# core/punctuation_restorer.py
# 中文标点恢复模块 - 基于 CT-Transformer

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class PunctuationRestorer:
    """
    中文标点恢复器 - 基于 CT-Transformer ONNX 模型

    使用 CT-Transformer (来自 FunASR) 进行中文标点恢复
    模型特点：
    - 支持 CPU 推理，延迟 0.6-3.5ms
    - 模型大小 ~292MB
    - 支持中英混合
    """

    def __init__(self, model_path: Optional[str] = None):
        """
        初始化标点恢复器

        Args:
            model_path: ONNX 模型路径，如果为 None 则使用默认路径
        """
        self._punctuator = None
        self._model_path = model_path or self._get_default_model_path()
        self._initialized = False

    def _get_default_model_path(self) -> str:
        """获取默认模型路径"""
        # 默认使用项目外部的 CT-Transformer 模型
        # 从 core/punctuation_restorer.py 上溯两级到 fastvoice 目录
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        model_path = os.path.join(
            project_root,
            "external",
            "CT-Transformer-punctuation",
            "cttpunctuator",
            "src",
            "onnx",
            "punc.onnx"
        )
        return model_path

    def initialize(self) -> bool:
        """
        初始化模型（延迟加载，避免启动时加载）

        Returns:
            bool: 是否初始化成功
        """
        if self._initialized:
            return True

        try:
            # 检查模型文件是否存在
            if not os.path.exists(self._model_path):
                logger.error(f"标点恢复模型不存在: {self._model_path}")
                return False

            # 导入 CT-Transformer
            try:
                from cttPunctuator import CttPunctuator
            except ImportError as e:
                logger.error(f"无法导入 CT-Transformer: {e}")
                logger.error("请先安装: cd external/CT-Transformer-punctuation && pip install -e .")
                return False

            logger.info("初始化标点恢复模型...")
            self._punctuator = CttPunctuator()
            self._initialized = True
            logger.info("标点恢复模型初始化完成")
            return True

        except Exception as e:
            logger.error(f"标点恢复模型初始化失败: {e}")
            return False

    def restore(self, text: str) -> str:
        """
        恢复文本标点

        Args:
            text: 无标点的文本

        Returns:
            str: 带标点的文本

        Raises:
            RuntimeError: 如果模型未初始化
        """
        if not self._initialized:
            if not self.initialize():
                raise RuntimeError(
                    "标点恢复模型未初始化，且无法自动加载。"
                    "请检查模型路径或配置。"
                )

        if not text or not text.strip():
            return text

        try:
            # 使用 CT-Transformer 进行标点恢复
            result = self._punctuator.punctuate(text)[0]
            logger.debug(f"标点恢复: '{text}' → '{result}'")
            return result

        except Exception as e:
            logger.error(f"标点恢复失败: {e}")
            # 出错时返回原文
            return text

    def is_available(self) -> bool:
        """
        检查标点恢复功能是否可用

        Returns:
            bool: 是否可用
        """
        try:
            return self.initialize()
        except Exception:
            return False


# 单例模式
_instance: Optional[PunctuationRestorer] = None


def get_punctuation_restorer() -> PunctuationRestorer:
    """
    获取标点恢复器单例

    Returns:
        PunctuationRestorer: 标点恢复器实例
    """
    global _instance
    if _instance is None:
        _instance = PunctuationRestorer()
    return _instance
