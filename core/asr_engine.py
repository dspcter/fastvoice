# core/asr_engine.py
# 语音识别引擎 (基于 sherpa-onnx + SenseVoice)

import logging
import wave
from pathlib import Path
from typing import Optional

import numpy as np

from config import ASR_MODEL_DIR
from models import get_model_manager, ModelType

logger = logging.getLogger(__name__)


class ASREngine:
    """
    语音识别引擎

    使用 sherpa-onnx + SenseVoice 进行离线语音识别
    闪电说同款方案
    """

    def __init__(self, model_id: str = "sense-voice"):
        """
        初始化 ASR 引擎

        Args:
            model_id: 模型 ID (默认 sense-voice)
        """
        self.model_id = model_id
        self.model_manager = get_model_manager()
        self._recognizer = None

        # 检查模型
        if not self.model_manager.check_asr_model(model_id):
            logger.warning(f"ASR 模型 {model_id} 不存在，需要先下载")

        logger.info(f"ASR 引擎初始化完成 (模型: {model_id})")

    def load_model(self) -> bool:
        """
        加载 ASR 模型

        Returns:
            是否加载成功
        """
        if not self.model_manager.check_asr_model(self.model_id):
            logger.error(f"ASR 模型 {self.model_id} 不存在")
            return False

        try:
            import sherpa_onnx

            model_path = self.model_manager.get_model_path(ModelType.ASR, self.model_id)

            # 使用 sherpa-onnx 1.12+ 的工厂方法创建 SenseVoice 识别器
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(model_path / "model.onnx"),
                tokens=str(model_path / "tokens.txt"),
                language="auto",  # 自动检测语言 (zh/en/ja/ko/yue)
                use_itn=False,  # 不使用 ITN
                sample_rate=16000,
                feature_dim=80,
                decoding_method="greedy_search",
                debug=False,
                provider="cpu",
                num_threads=1,
            )

            logger.info("ASR 模型加载成功")
            return True

        except ImportError:
            logger.error("sherpa_onnx 未安装，请先安装: pip install sherpa-onnx")
            return False
        except Exception as e:
            logger.error(f"加载 ASR 模型失败: {e}")
            return False

    def recognize_file(self, audio_file: Path) -> Optional[str]:
        """
        识别音频文件

        Args:
            audio_file: 音频文件路径 (WAV 格式)

        Returns:
            识别文本
        """
        if self._recognizer is None:
            if not self.load_model():
                return None

        try:
            # 读取音频文件
            samples = self._load_audio_file(audio_file)
            if samples is None:
                return None

            # sherpa-onnx 1.12+ 使用 stream 模式
            stream = self._recognizer.create_stream()
            stream.accept_waveform(16000, samples)
            self._recognizer.decode_stream(stream)
            result = stream.result
            text = result.text.strip()

            logger.info(f"识别结果: {text}")
            return text if text else None

        except Exception as e:
            logger.error(f"识别音频失败: {e}")
            return None

    def recognize_bytes(self, audio_data: bytes) -> Optional[str]:
        """
        识别音频数据 (bytes)

        Args:
            audio_data: WAV 格式音频数据

        Returns:
            识别文本
        """
        if self._recognizer is None:
            if not self.load_model():
                return None

        try:
            import io

            # 将 bytes 转换为音频数组
            with io.BytesIO(audio_data) as wav_io:
                with wave.open(wav_io, "rb") as wav_file:
                    # 获取音频参数
                    frames = wav_file.getnframes()
                    sample_rate = wav_file.getframerate()
                    channels = wav_file.getnchannels()

                    # 读取音频数据
                    audio_bytes = wav_file.readframes(frames)
                    samples = np.frombuffer(audio_bytes, dtype=np.int16)

                    # 转换为 float32 并归一化
                    samples = samples.astype(np.float32) / 32768.0

                    # 如果是立体声，转换为单声道
                    if channels > 1:
                        samples = samples.reshape(-1, channels).mean(axis=1)

                    # 如果采样率不是 16kHz，重采样
                    if sample_rate != 16000:
                        # 简单重采样 (需要更好的方法可以用 resampy)
                        num_samples = int(len(samples) * 16000 / sample_rate)
                        samples = np.interp(
                            np.linspace(0, len(samples), num_samples),
                            np.arange(len(samples)),
                            samples
                        )

            # sherpa-onnx 1.12+ 使用 stream 模式
            stream = self._recognizer.create_stream()
            stream.accept_waveform(16000, samples)
            self._recognizer.decode_stream(stream)
            result = stream.result
            text = result.text.strip()

            logger.info(f"识别结果: {text}")
            return text if text else None

        except Exception as e:
            logger.error(f"识别音频数据失败: {e}")
            return None

    def _load_audio_file(self, audio_file: Path) -> Optional[np.ndarray]:
        """
        加载音频文件

        Args:
            audio_file: 音频文件路径

        Returns:
            音频数组 (float32)
        """
        try:
            with wave.open(str(audio_file), "rb") as wf:
                frames = wf.getnframes()
                sample_rate = wf.getframerate()
                channels = wf.getnchannels()

                # 读取音频数据
                audio_bytes = wf.readframes(frames)
                samples = np.frombuffer(audio_bytes, dtype=np.int16)

                # 转换为 float32 并归一化
                samples = samples.astype(np.float32) / 32768.0

                # 如果是立体声，转换为单声道
                if channels > 1:
                    samples = samples.reshape(-1, channels).mean(axis=1)

                # 如果采样率不是 16kHz，重采样
                if sample_rate != 16000:
                    num_samples = int(len(samples) * 16000 / sample_rate)
                    samples = np.interp(
                        np.linspace(0, len(samples), num_samples),
                        np.arange(len(samples)),
                        samples
                    )

            return samples

        except Exception as e:
            logger.error(f"加载音频文件失败: {e}")
            return None

    def is_model_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self._recognizer is not None

    def unload_model(self) -> None:
        """卸载模型"""
        self._recognizer = None
        logger.info("ASR 模型已卸载")


# ==================== 单例 ====================

_asr_engine = None


def get_asr_engine(model_id: str = "sense-voice") -> ASREngine:
    """获取全局 ASR 引擎实例"""
    global _asr_engine
    if _asr_engine is None:
        _asr_engine = ASREngine(model_id)
    return _asr_engine


# ==================== 使用示例 ====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    engine = get_asr_engine()

    # 测试识别
    test_audio = Path("test.wav")

    if test_audio.exists():
        text = engine.recognize_file(test_audio)
        print(f"识别文本: {text}")
    else:
        print(f"测试音频文件不存在: {test_audio}")
        print("请将测试音频命名为 test.wav 放在当前目录")
