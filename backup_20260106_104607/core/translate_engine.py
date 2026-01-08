# core/translate_engine.py
# 翻译引擎 (基于 Qwen2.5)

import logging
from typing import Optional

from config import TRANSLATION_MODEL_DIR
from models import get_model_manager, ModelType

logger = logging.getLogger(__name__)


class TranslateEngine:
    """
    翻译引擎

    使用 Qwen2.5-1.5B-Instruct 进行离线翻译
    """

    def __init__(self, model_id: str = "qwen2.5-1.5b"):
        """
        初始化翻译引擎

        Args:
            model_id: 模型 ID
        """
        self.model_id = model_id
        self.model_manager = get_model_manager()
        self._model = None
        self._tokenizer = None

        logger.info(f"翻译引擎初始化完成 (模型: {model_id})")

    def load_model(self) -> bool:
        """
        加载翻译模型

        Returns:
            是否加载成功
        """
        if not self.model_manager.check_translation_model(self.model_id):
            logger.error(f"翻译模型 {self.model_id} 不存在")
            return False

        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer

            model_path = self.model_manager.get_model_path(ModelType.TRANSLATION, self.model_id)

            # 加载 tokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(
                str(model_path),
                trust_remote_code=True,
            )

            # 加载模型
            self._model = AutoModelForCausalLM.from_pretrained(
                str(model_path),
                torch_dtype="auto",
                device_map="auto",
                trust_remote_code=True,
            )

            logger.info("翻译模型加载成功")
            return True

        except ImportError:
            logger.error("transformers 未安装，请先安装: pip install transformers torch")
            return False
        except Exception as e:
            logger.error(f"加载翻译模型失败: {e}")
            return False

    def translate(
        self,
        text: str,
        target_language: str = "en",
        source_language: str = "zh",
    ) -> Optional[str]:
        """
        翻译文本

        Args:
            text: 源文本
            target_language: 目标语言 ("en" 或 "zh")
            source_language: 源语言

        Returns:
            翻译结果
        """
        if self._model is None or self._tokenizer is None:
            if not self.load_model():
                return None

        try:
            import torch

            # 构建翻译提示词（简洁明了）
            lang_map = {
                "en": "English",
                "zh": "中文",
            }

            target_lang = lang_map.get(target_language, target_language)

            # 使用简单直接的格式：源文本 -> 目标语言
            if target_language == "en":
                prompt = f"{text}\n\nTranslate to English:"
            else:
                prompt = f"{text}\n\n翻译成中文："

            # 编码输入
            inputs = self._tokenizer(prompt, return_tensors="pt")
            inputs = {k: v.to(self._model.device) for k, v in inputs.items()}

            # 生成翻译（使用更保守的参数）
            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=128,  # 减少最大长度
                    temperature=0.1,  # 更低的温度
                    top_p=0.95,
                    do_sample=False,  # 使用贪婪解码，更稳定
                    repetition_penalty=1.1,
                )

            # 解码输出
            result = self._tokenizer.decode(outputs[0], skip_special_tokens=True)

            # 提取翻译结果 (去除提示词部分)
            if prompt in result:
                result = result.replace(prompt, "").strip()

            logger.info(f"翻译结果: {result}")
            return result

        except Exception as e:
            logger.error(f"翻译失败: {e}")
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

        logger.info("翻译模型已卸载")

    def _generate_with_model(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        temperature: float = 0.7,
    ) -> Optional[str]:
        """
        使用模型生成文本（用于文本处理等任务）

        Args:
            prompt: 提示词
            max_new_tokens: 最大生成 token 数
            temperature: 生成温度

        Returns:
            生成的文本结果
        """
        if self._model is None or self._tokenizer is None:
            if not self.load_model():
                return None

        try:
            import torch

            # 编码输入
            inputs = self._tokenizer(prompt, return_tensors="pt")
            inputs = {k: v.to(self._model.device) for k, v in inputs.items()}

            # 生成文本
            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    top_p=0.9,
                    do_sample=True,
                )

            # 解码输出
            result = self._tokenizer.decode(outputs[0], skip_special_tokens=True)

            # 提取生成结果（去除提示词部分）
            if prompt in result:
                result = result.replace(prompt, "").strip()

            return result

        except Exception as e:
            logger.error(f"模型生成失败: {e}")
            return None


# ==================== 单例 ====================

_translate_engine = None


def get_translate_engine(model_id: str = "qwen2.5-1.5b") -> TranslateEngine:
    """获取全局翻译引擎实例"""
    global _translate_engine
    if _translate_engine is None:
        _translate_engine = TranslateEngine(model_id)
    return _translate_engine


# ==================== 使用示例 ====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    engine = get_translate_engine()

    # 测试翻译
    test_cases = [
        ("今天天气很好", "en"),
        ("Hello, how are you?", "zh"),
    ]

    for text, target_lang in test_cases:
        result = engine.translate(text, target_lang)
        print(f"{text} -> {result}")
