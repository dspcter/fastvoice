# config/settings.py
# 配置管理模块

import json
import logging
from pathlib import Path
from typing import Any, Dict

from .constants import (
    DEFAULT_AUDIO,
    DEFAULT_CLEANUP,
    DEFAULT_HOTKEYS,
    DEFAULT_HOTKEY_CONFIG,  # v1.4.2 新增
    DEFAULT_TEXT_PROCESSING,
    DEFAULT_TRANSLATION,
    DEFAULT_INJECTION,
    get_config_path,
)

logger = logging.getLogger(__name__)


class Settings:
    """配置管理类"""

    def __init__(self, config_path: Path = None):
        self.config_path = config_path or get_config_path()
        self._config: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """加载配置文件"""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
                logger.info(f"配置已加载: {self.config_path}")
            except Exception as e:
                logger.error(f"加载配置失败: {e}")
                self._config = self._get_default_config()
        else:
            self._config = self._get_default_config()
            self.save()

    def save(self) -> None:
        """保存配置到文件"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            logger.info(f"配置已保存: {self.config_path}")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "version": "1.0.1",
            "hotkeys": DEFAULT_HOTKEYS.copy(),
            "audio": DEFAULT_AUDIO.copy(),
            "translation": DEFAULT_TRANSLATION.copy(),
            "cleanup": DEFAULT_CLEANUP.copy(),
            "text_processing": DEFAULT_TEXT_PROCESSING.copy(),
            "injection": DEFAULT_INJECTION.copy(),
            "models": {
                "asr": None,  # 当前使用的 ASR 模型
                "translation": None,  # 当前使用的翻译模型
            },
        }

    # ==================== 通用方法 ====================

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值（支持点号分隔的路径）"""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def set(self, key: str, value: Any) -> None:
        """设置配置值（支持点号分隔的路径）"""
        keys = key.split(".")
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
        self.save()

    def update(self, updates: Dict[str, Any]) -> None:
        """批量更新配置"""
        def _deep_update(base: Dict, updates: Dict):
            for key, value in updates.items():
                if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                    _deep_update(base[key], value)
                else:
                    base[key] = value

        _deep_update(self._config, updates)
        self.save()

    def reset(self) -> None:
        """重置为默认配置"""
        self._config = self._get_default_config()
        self.save()
        logger.info("配置已重置为默认值")

    def to_dict(self) -> Dict[str, Any]:
        """返回配置的字典副本"""
        return self._config.copy()

    # ==================== 快捷键配置 ====================

    @property
    def voice_input_hotkey(self) -> str:
        """获取语音输入快捷键（向后兼容）"""
        default = DEFAULT_HOTKEY_CONFIG["voice_input"]
        config = self.get("hotkeys.voice_input", default)
        if isinstance(config, dict):
            return config.get("key", default["key"])
        return config  # 兼容旧格式（字符串）

    @voice_input_hotkey.setter
    def voice_input_hotkey(self, value: str):
        """设置语音输入快捷键"""
        current = self.get("hotkeys.voice_input", DEFAULT_HOTKEY_CONFIG["voice_input"])
        if isinstance(current, dict):
            current["key"] = value
            self.set("hotkeys.voice_input", current)
        else:
            # 旧格式，转换为新的字典格式
            self.set("hotkeys.voice_input", {"key": value, "mode": "single_press"})

    @property
    def voice_input_mode(self) -> str:
        """获取语音输入触发模式"""
        default = DEFAULT_HOTKEY_CONFIG["voice_input"]
        config = self.get("hotkeys.voice_input", default)
        if isinstance(config, dict):
            return config.get("mode", default["mode"])
        return "single_press"  # 默认一次按键

    @voice_input_mode.setter
    def voice_input_mode(self, value: str):
        """设置语音输入触发模式"""
        current = self.get("hotkeys.voice_input", DEFAULT_HOTKEY_CONFIG["voice_input"])
        if isinstance(current, dict):
            current["mode"] = value
            self.set("hotkeys.voice_input", current)
        else:
            # 旧格式，转换为新的字典格式
            self.set("hotkeys.voice_input", {"key": current, "mode": value})

    @property
    def quick_translate_hotkey(self) -> str:
        """获取翻译快捷键（向后兼容）"""
        default = DEFAULT_HOTKEY_CONFIG["quick_translate"]
        config = self.get("hotkeys.quick_translate", default)
        if isinstance(config, dict):
            return config.get("key", default["key"])
        return config  # 兼容旧格式（字符串）

    @quick_translate_hotkey.setter
    def quick_translate_hotkey(self, value: str):
        """设置翻译快捷键"""
        current = self.get("hotkeys.quick_translate", DEFAULT_HOTKEY_CONFIG["quick_translate"])
        if isinstance(current, dict):
            current["key"] = value
            self.set("hotkeys.quick_translate", current)
        else:
            # 旧格式，转换为新的字典格式
            self.set("hotkeys.quick_translate", {"key": value, "mode": "double_press"})

    @property
    def translate_mode(self) -> str:
        """获取翻译触发模式"""
        default = DEFAULT_HOTKEY_CONFIG["quick_translate"]
        config = self.get("hotkeys.quick_translate", default)
        if isinstance(config, dict):
            return config.get("mode", default["mode"])
        return "double_press"  # 默认双击+长按

    @translate_mode.setter
    def translate_mode(self, value: str):
        """设置翻译触发模式"""
        current = self.get("hotkeys.quick_translate", DEFAULT_HOTKEY_CONFIG["quick_translate"])
        if isinstance(current, dict):
            current["mode"] = value
            self.set("hotkeys.quick_translate", current)
        else:
            # 旧格式，转换为新的字典格式
            self.set("hotkeys.quick_translate", {"key": current, "mode": value})

    # ==================== 音频配置 ====================

    @property
    def sample_rate(self) -> int:
        return self.get("audio.sample_rate", DEFAULT_AUDIO["sample_rate"])

    @sample_rate.setter
    def sample_rate(self, value: int):
        self.set("audio.sample_rate", value)

    @property
    def vad_threshold(self) -> int:
        return self.get("audio.vad_threshold", DEFAULT_AUDIO["vad_threshold"])

    @vad_threshold.setter
    def vad_threshold(self, value: int):
        self.set("audio.vad_threshold", value)

    @property
    def microphone_device(self) -> str:
        return self.get("audio.microphone_device", "")

    @microphone_device.setter
    def microphone_device(self, value: str):
        self.set("audio.microphone_device", value)

    # ==================== 翻译配置 ====================

    @property
    def translation_mode(self) -> str:
        """翻译模式: 'direct' 或 'button'"""
        return self.get("translation.mode", DEFAULT_TRANSLATION["mode"])

    @translation_mode.setter
    def translation_mode(self, value: str):
        if value not in ["direct", "button"]:
            raise ValueError("翻译模式必须是 'direct' 或 'button'")
        self.set("translation.mode", value)

    @property
    def target_language(self) -> str:
        return self.get("translation.target_language", DEFAULT_TRANSLATION["target_language"])

    @target_language.setter
    def target_language(self, value: str):
        self.set("translation.target_language", value)

    @property
    def source_language(self) -> str:
        return self.get("translation.source_language", DEFAULT_TRANSLATION["source_language"])

    @source_language.setter
    def source_language(self, value: str):
        self.set("translation.source_language", value)

    # ==================== 清理配置 ====================

    @property
    def cleanup_enabled(self) -> bool:
        return self.get("cleanup.enabled", DEFAULT_CLEANUP["enabled"])

    @cleanup_enabled.setter
    def cleanup_enabled(self, value: bool):
        self.set("cleanup.enabled", value)

    @property
    def cleanup_days(self) -> int:
        return self.get("cleanup.days", DEFAULT_CLEANUP["days"])

    @cleanup_days.setter
    def cleanup_days(self, value: int):
        self.set("cleanup.days", value)

    # ==================== 模型配置 ====================

    @property
    def asr_model(self) -> str:
        return self.get("models.asr")

    @asr_model.setter
    def asr_model(self, value: str):
        self.set("models.asr", value)

    @property
    def translation_model(self) -> str:
        return self.get("models.translation")

    @translation_model.setter
    def translation_model(self, value: str):
        self.set("models.translation", value)

    # ==================== 文本处理配置 ====================

    @property
    def use_ai_text_processing(self) -> bool:
        """是否使用 AI 进行文本后处理（去除语气词、添加标点等）"""
        return self.get("text_processing.use_ai", DEFAULT_TEXT_PROCESSING["use_ai"])

    @use_ai_text_processing.setter
    def use_ai_text_processing(self, value: bool):
        self.set("text_processing.use_ai", value)

    # ==================== 文字注入配置 ====================

    @property
    def injection_method(self) -> str:
        """文字注入方式: 'clipboard', 'typing', 'win32_native'"""
        return self.get("injection.method", DEFAULT_INJECTION["method"])

    @injection_method.setter
    def injection_method(self, value: str):
        valid_methods = ["clipboard", "typing", "win32_native"]
        if value not in valid_methods:
            raise ValueError(f"注入方式必须是 {valid_methods} 之一")
        self.set("injection.method", value)


# 全局配置实例
_settings = None


def get_settings() -> Settings:
    """获取全局配置实例（单例模式）"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
