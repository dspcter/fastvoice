# config/constants.py
# 常量定义

import platform
from pathlib import Path

# ==================== 项目信息 ====================
APP_NAME = "快人快语"
APP_NAME_EN = "FastVoice"
VERSION = "1.0.1"

# ==================== 路径配置 ====================
# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 各模块路径
CORE_DIR = PROJECT_ROOT / "core"
MODELS_DIR = PROJECT_ROOT / "models" / "models"
AUDIO_DIR = PROJECT_ROOT / "audio" / "recordings"
STORAGE_DIR = PROJECT_ROOT / "storage"
LOGS_DIR = PROJECT_ROOT / "logs"
CONFIG_DIR = PROJECT_ROOT / "config"
ASSETS_DIR = PROJECT_ROOT / "assets"

# 模型子目录
ASR_MODEL_DIR = MODELS_DIR / "asr"
TRANSLATION_MODEL_DIR = MODELS_DIR / "translation"

# ==================== 平台信息 ====================
PLATFORM = platform.system()
IS_MACOS = PLATFORM == "Darwin"
IS_WINDOWS = PLATFORM == "Windows"
IS_LINUX = PLATFORM == "Linux"

# ==================== 默认配置 ====================
# 快捷键默认值
# pynput 支持左右 Option 键辨别
# 左 Option 用于语音输入（一次按键）
# 右 Option 用于翻译（双击+长按）
DEFAULT_HOTKEYS = {
    "voice_input": "left_alt" if IS_MACOS else "right_ctrl",  # 左 Option 用于语音输入（macOS）
    "quick_translate": "right_alt" if IS_MACOS else "ctrl+shift+t",  # 右 Option 用于翻译（macOS）
}

# 音频默认配置
DEFAULT_AUDIO = {
    "sample_rate": 16000,
    "channels": 1,
    "chunk_duration": 30,  # 最大录音时长(秒)
    "vad_threshold": 500,  # VAD 静音阈值(毫秒)
    "vad_padding": 300,    # VAD 前后填充(毫秒)
}

# 翻译默认配置
DEFAULT_TRANSLATION = {
    "mode": "button",  # "direct" | "button"
    "target_language": "en",  # "en" | "zh"
    "source_language": "zh",  # "zh" | "en"
}

# 音频清理默认配置
DEFAULT_CLEANUP = {
    "enabled": True,
    "days": 7,  # 保留天数
}

# 文本处理默认配置
DEFAULT_TEXT_PROCESSING = {
    "use_ai": False,  # 默认不使用 AI，使用简单规则
}

# 文字注入默认配置
DEFAULT_INJECTION = {
    "method": "win32_native" if IS_WINDOWS else "clipboard",  # Windows 优先使用原生注入
}

# ==================== 模型信息 ====================
# ASR 模型 (sherpa-onnx + SenseVoice) - 闪电说同款方案
ASR_MODELS = {
    "sense-voice": {
        "name": "SenseVoice-small",
        "size": "700MB",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2",
        "format": "tar.bz2",
        "files": [
            "model.onnx",
            "tokens.txt",
        ],
        "languages": ["zh", "en", "ja", "ko", "yue"],  # 支持的语言
    }
}

# 翻译模型
TRANSLATION_MODELS = {
    # MarianMT 专用翻译模型（推荐）
    "marianmt-zh-en": {
        "name": "MarianMT 中文→英文",
        "size": "300MB",
        "model_id": "Helsinki-NLP/opus-mt-zh-en",
        "type": "marianmt",
        "direction": "zh-en",
        "requires_download": True,
    },
    "marianmt-en-zh": {
        "name": "MarianMT 英文→中文",
        "size": "300MB",
        "model_id": "Helsinki-NLP/opus-mt-en-zh",
        "type": "marianmt",
        "direction": "en-zh",
        "requires_download": True,
    },
    # Qwen 通用模型（不推荐用于翻译，保留用于其他功能）
    "qwen2.5-1.5b": {
        "name": "Qwen2.5-1.5B-Instruct",
        "size": "2.9GB",
        "model_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "type": "qwen",
        "requires_download": True,
    },
}

# ==================== 语言配置 ====================
LANGUAGE_NAMES = {
    "zh": "中文",
    "en": "English",
}

LANGUAGE_PAIRS = [
    ("zh", "en"),  # 中文 → 英文
    ("en", "zh"),  # 英文 → 中文
]

# ==================== UI 配置 ====================
WINDOW_MIN_WIDTH = 600
WINDOW_MIN_HEIGHT = 500
SETTINGS_WINDOW_WIDTH = 700
SETTINGS_WINDOW_HEIGHT = 650

# ==================== 日志配置 ====================
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_LEVEL = "INFO"

# ==================== 其他常量 ====================
# 支持的快捷键修饰符
MODIFIER_KEYS = ["ctrl", "alt", "shift", "cmd", "win"]

# VAD 灵敏度范围
VAD_MIN_THRESHOLD = 200  # 毫秒
VAD_MAX_THRESHOLD = 2000  # 毫秒

# 自动清理天数范围
CLEANUP_MIN_DAYS = 1
CLEANUP_MAX_DAYS = 90

# ==================== 辅助函数 ====================


def get_config_path():
    """获取配置文件路径"""
    return CONFIG_DIR / "settings.json"


def get_log_path():
    """获取日志文件路径"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR / f"{APP_NAME_EN}.log"


def ensure_directories():
    """确保所有必需的目录存在"""
    directories = [
        MODELS_DIR,
        ASR_MODEL_DIR,
        TRANSLATION_MODEL_DIR,
        AUDIO_DIR,
        STORAGE_DIR,
        LOGS_DIR,
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


# 启动时确保目录存在
ensure_directories()
