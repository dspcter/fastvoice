# storage/__init__.py
# 存储模块初始化

from .audio_manager import AudioManager, AudioFileInfo, get_audio_manager

__all__ = [
    "AudioManager",
    "AudioFileInfo",
    "get_audio_manager",
]
