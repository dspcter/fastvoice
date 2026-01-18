# core/__init__.py
# 核心功能模块初始化

from .hotkey_manager import HotkeyManager, HotkeyAction
from .audio_capture import AudioCapture
from .asr_engine import ASREngine, get_asr_engine
from .translate_engine import TranslateEngine, get_translate_engine
from .marianmt_engine import MarianMTEngine, get_marianmt_engine
from .text_injector import TextInjector, get_text_injector
from .text_postprocessor import TextPostProcessor, get_text_postprocessor

__all__ = [
    "HotkeyManager",
    "HotkeyAction",
    "AudioCapture",
    "ASREngine",
    "get_asr_engine",
    "TranslateEngine",
    "get_translate_engine",
    "MarianMTEngine",
    "get_marianmt_engine",
    "TextInjector",
    "get_text_injector",
    "TextPostProcessor",
    "get_text_postprocessor",
]
