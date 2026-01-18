# core/marianmt_engine.py
# MarianMT 翻译引擎 - 专用的本地翻译模型

import logging
from typing import Optional

from config import TRANSLATION_MODEL_DIR
from models import get_model_manager, ModelType

logger = logging.getLogger(__name__)


class MarianMTEngine:
    """
    MarianMT 翻译引擎

    使用 MarianMT 模型进行高质量本地翻译
    """

    def __init__(self, direction: str = "zh-en"):
        """
        初始化 MarianMT 翻译引擎

        Args:
            direction: 翻译方向 ("zh-en" 或 "en-zh")
        """
        self.direction = direction
        self.model_manager = get_model_manager()

        # 根据方向确定模型 ID
        if direction == "zh-en":
            self.model_id = "marianmt-zh-en"
            self.hf_model_id = "Helsinki-NLP/opus-mt-zh-en"
        elif direction == "en-zh":
            self.model_id = "marianmt-en-zh"
            self.hf_model_id = "Helsinki-NLP/opus-mt-en-zh"
        else:
            raise ValueError(f"不支持的翻译方向: {direction}")

        self._model = None
        self._tokenizer = None

        logger.info(f"MarianMT 翻译引擎初始化完成 (方向: {direction})")

    def load_model(self) -> bool:
        """
        加载翻译模型

        Returns:
            是否加载成功
        """
        if not self.model_manager.check_translation_model(self.model_id):
            logger.error(f"翻译模型 {self.model_id} 不存在，请先下载")
            return False

        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            model_path = self.model_manager.get_model_path(ModelType.TRANSLATION, self.model_id)

            # 加载 tokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(
                str(model_path),
                trust_remote_code=True,
            )

            # 加载模型
            self._model = AutoModelForSeq2SeqLM.from_pretrained(
                str(model_path),
                torch_dtype="auto",
                device_map="auto",
                trust_remote_code=True,
            )

            logger.info(f"MarianMT 模型加载成功 ({self.direction})")
            return True

        except ImportError:
            logger.error("transformers 未安装，请先安装: pip install transformers torch")
            return False
        except Exception as e:
            logger.error(f"加载 MarianMT 模型失败: {e}")
            return False

    def translate(self, text: str) -> Optional[str]:
        """
        翻译文本

        Args:
            text: 源文本

        Returns:
            翻译结果
        """
        if self._model is None or self._tokenizer is None:
            if not self.load_model():
                return None

        try:
            import torch

            # 编码输入
            inputs = self._tokenizer(text, return_tensors="pt")
            inputs = {k: v.to(self._model.device) for k, v in inputs.items()}

            # 生成翻译
            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_length=128,
                    num_beams=4,
                    early_stopping=True,
                )

            # 解码输出
            result = self._tokenizer.decode(outputs[0], skip_special_tokens=True)

            # 清理可能的特殊标记
            if result.startswith(">>"):
                result = result.split(">>", 1)[-1].strip()

            logger.info(f"MarianMT 翻译: '{text}' → '{result}'")
            return result

        except Exception as e:
            logger.error(f"MarianMT 翻译失败: {e}")
            return None

    def is_model_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self._model is not None and self._tokenizer is not None

    def unload_model(self) -> None:
        """卸载模型以释放内存"""
        import gc

        self._model = None
        self._tokenizer = None
        gc.collect()

        logger.info("MarianMT 模型已卸载")


# ==================== 单例 ====================

_marianmt_engines = {}


def get_marianmt_engine(direction: str = "zh-en") -> MarianMTEngine:
    """
    获取 MarianMT 翻译引擎实例

    Args:
        direction: 翻译方向 ("zh-en" 或 "en-zh")

    Returns:
        翻译引擎实例
    """
    global _marianmt_engines

    if direction not in _marianmt_engines:
        _marianmt_engines[direction] = MarianMTEngine(direction)

    return _marianmt_engines[direction]


# ==================== 使用示例 ====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # 测试中文到英文
    zh_en_engine = get_marianmt_engine("zh-en")
    result = zh_en_engine.translate("今天天气很好")
    print(f"中文→英文: {result}")

    # 测试英文到中文
    en_zh_engine = get_marianmt_engine("en-zh")
    result = en_zh_engine.translate("Hello, how are you?")
    print(f"英文→中文: {result}")
