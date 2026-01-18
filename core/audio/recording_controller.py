# core/audio/recording_controller.py
# 录音控制器 - 统一状态管理和协调

import logging
import queue
import threading
import time
import wave
from datetime import datetime
from enum import Enum
from io import BytesIO
from pathlib import Path
from typing import Callable, List, Optional

from .capture_thread import AudioCaptureThread
from .vad_segmenter import VadSegmenter

from config import AUDIO_DIR

logger = logging.getLogger(__name__)


class RecordingState(Enum):
    """录音状态枚举"""
    IDLE = "idle"  # 空闲
    RECORDING = "recording"  # 录音中
    FINALIZING = "finalizing"  # 完成中（处理剩余数据）


class RecordingController:
    """
    录音控制器 - 统一状态管理和协调

    职责边界：
    - ✅ 管理录音状态机 (IDLE → RECORDING → FINALIZING → IDLE)
    - ✅ 协调 AudioCaptureThread 和 VadSegmenter
    - ✅ 处理 start/stop/finalize 操作
    - ✅ 提供最终音频数据
    - ❌ 不采集音频（由 AudioCaptureThread 负责）
    - ❌ 不做 VAD 判断（由 VadSegmenter 负责）

    设计理念：
    - 状态机模式：显式状态转换
    - 单一职责：只负责协调
    - 线程安全：通过锁保护状态
    - 幂等性：重复操作安全
    """

    # 超时设置
    MAX_RECORDING_DURATION = 60  # 最大录音时长（秒）
    FINALIZE_TIMEOUT = 2  # finalize 超时（秒）

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        device: Optional[str] = None,
        silence_threshold_ms: int = 500,
        hangover_time_ms: int = 300,
        on_segment_complete: Optional[Callable] = None,
        on_recording_complete: Optional[Callable] = None,
    ):
        """
        初始化录音控制器

        Args:
            sample_rate: 采样率
            channels: 声道数
            device: 麦克风设备名称
            silence_threshold_ms: 静音阈值（毫秒）
            hangover_time_ms: hangover 时间（毫秒）
            on_segment_complete: 语音段完成回调
            on_recording_complete: 录音完成回调（参数：音频数据 bytes）
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self._on_recording_complete = on_recording_complete

        # 状态
        self._state = RecordingState.IDLE
        self._lock = threading.Lock()
        self._state_change_event = threading.Event()

        # 音频采集线程
        self._capture: Optional[AudioCaptureThread] = None
        self._capture_thread: Optional[threading.Thread] = None

        # VAD 分段器
        self._vad: Optional[VadSegmenter] = None

        # 数据收集
        self._all_frames: List[bytes] = []  # 所有帧
        self._segments: List[List[bytes]] = []  # 语音段

        # 统计
        self._start_time: Optional[float] = None
        self._stop_time: Optional[float] = None

        # 确保音频目录存在
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)

        logger.info("RecordingController 初始化完成")

    def _create_components(self):
        """创建音频采集和VAD组件"""
        # 音频采集线程
        self._capture = AudioCaptureThread(
            sample_rate=self.sample_rate,
            channels=self.channels,
            device=None,  # TODO: 从配置读取
            buffer_maxlen=1000,
            on_error=self._on_capture_error,
        )

        # VAD 分段器
        self._vad = VadSegmenter(
            sample_rate=self.sample_rate,
            silence_threshold_ms=500,
            hangover_time_ms=300,
            on_segment_complete=self._on_segment_complete,
        )

    def start(self) -> bool:
        """
        开始录音

        Returns:
            是否成功启动
        """
        with self._lock:
            # 幂等性检查
            if self._state != RecordingState.IDLE:
                logger.warning(f"start() 调用时状态不是 IDLE，当前状态: {self._state.value}")
                return self._state == RecordingState.RECORDING

            try:
                logger.info("开始录音")

                # 创建组件
                self._create_components()

                # 重置数据
                self._all_frames = []
                self._segments = []
                self._start_time = time.time()
                self._stop_time = None

                # 启动采集线程
                if not self._capture.start():
                    logger.error("启动音频采集失败")
                    return False

                # 状态转换
                self._state = RecordingState.RECORDING
                self._state_change_event.set()

                # 启动处理线程
                self._capture_thread = threading.Thread(
                    target=self._processing_loop,
                    daemon=True,
                    name="RecordingProcessor"
                )
                self._capture_thread.start()

                logger.info("录音已启动")
                return True

            except Exception as e:
                logger.error(f"启动录音失败: {e}")
                self._state = RecordingState.IDLE
                return False

    def stop(self) -> None:
        """
        停止录音

        注意：此方法是异步的，实际处理在 _processing_loop 中完成
        """
        with self._lock:
            if self._state != RecordingState.RECORDING:
                logger.warning(f"stop() 调用时状态不是 RECORDING，当前状态: {self._state.value}")
                return

            logger.info("停止录音")
            self._state = RecordingState.FINALIZING
            self._stop_time = time.time()
            self._state_change_event.set()

    def get_state(self) -> RecordingState:
        """获取当前状态"""
        return self._state

    def _processing_loop(self):
        """
        处理循环 - 从采集线程获取帧并送入VAD

        在独立线程中运行，持续处理直到状态变为 FINALIZING
        """
        logger.debug("处理循环已启动")

        try:
            while self._state == RecordingState.RECORDING:
                # 从 buffer 获取帧
                frames = self._capture.get_frames(max_frames=10)

                if not frames:
                    time.sleep(0.01)
                    continue

                # 处理每帧
                for frame in frames:
                    # 收集所有帧
                    self._all_frames.append(frame)

                    # VAD 处理
                    segment = self._vad.process_frame(frame)
                    if segment:
                        self._segments.append(segment)

            # 录音结束，finalize
            self._finalize()

        except Exception as e:
            logger.error(f"处理循环出错: {e}")
            self._state = RecordingState.IDLE

    def _finalize(self):
        """完成录音处理"""
        logger.info("开始 finalize 录音")

        try:
            # 停止采集
            if self._capture:
                self._capture.stop()

            # 获取VAD剩余的语音段
            final_segment = self._vad.finalize()
            if final_segment:
                self._segments.append(final_segment)

            # 合并所有语音段
            if self._segments:
                all_audio_frames = []
                for segment in self._segments:
                    all_audio_frames.extend(segment)

                # 转换为 WAV
                wav_data = self._convert_to_wav(all_audio_frames)

                # 回调
                if self._on_recording_complete:
                    self._on_recording_complete(wav_data)

                logger.info(f"录音完成: {len(all_audio_frames)} 帧")
            else:
                logger.warning("没有语音段")

        except Exception as e:
            logger.error(f"finalize 失败: {e}")
        finally:
            # 状态回 IDLE
            with self._lock:
                self._state = RecordingState.IDLE
                self._state_change_event.set()

    def _convert_to_wav(self, frames: List[bytes]) -> bytes:
        """将音频帧转换为 WAV 格式"""
        buffer = BytesIO()

        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)

            for frame in frames:
                wf.writeframes(frame)

        return buffer.getvalue()

    def _on_segment_complete(self, segment: List[bytes]):
        """语音段完成回调"""
        logger.debug(f"语音段完成: {len(segment)} 帧")
        # 可以在这里做流式处理，比如推送到 ASR

    def _on_capture_error(self, error: Exception):
        """音频采集错误回调"""
        logger.error(f"音频采集错误: {error}")
        # 停止录音
        if self._state == RecordingState.RECORDING:
            self.stop()

    def get_duration(self) -> float:
        """获取录音时长（秒）"""
        if not self._start_time:
            return 0.0

        end_time = self._stop_time or time.time()
        return end_time - self._start_time

    def save_audio(self, audio_data: bytes, filename: Optional[str] = None) -> Path:
        """保存音频到文件"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"voice_{timestamp}.wav"

        filepath = AUDIO_DIR / filename

        try:
            with open(filepath, "wb") as f:
                f.write(audio_data)

            logger.info(f"音频已保存: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"保存音频失败: {e}")
            raise

    def reset(self) -> None:
        """强制重置状态（幂等操作）"""
        with self._lock:
            logger.warning("强制重置 RecordingController 状态")

            # 停止采集
            if self._capture:
                try:
                    self._capture.stop()
                except:
                    pass
                self._capture = None

            # 清理
            self._all_frames = []
            self._segments = []
            self._start_time = None
            self._stop_time = None

            # 状态回 IDLE
            self._state = RecordingState.IDLE
            self._state_change_event.set()


# ==================== 使用示例 ====================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    print("=== RecordingController 测试 ===\n")

    def on_complete(wav_data):
        print(f"录音完成回调: {len(wav_data)} bytes")

    # 创建控制器
    controller = RecordingController(on_recording_complete=on_complete)

    print("\n开始录音...")
    controller.start()

    print("录音 5 秒...")
    time.sleep(5)

    print("停止录音...")
    controller.stop()

    print("等待 finalize...")
    time.sleep(1)

    print(f"最终状态: {controller.get_state().value}")
    print(f"录音时长: {controller.get_duration():.2f}s")
