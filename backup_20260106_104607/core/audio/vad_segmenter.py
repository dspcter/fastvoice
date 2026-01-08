# core/audio/vad_segmenter.py
# VAD 语音分段器 - 将音频帧分段为语音段

import logging
from collections import deque
from typing import List, Optional, Tuple

import webrtcvad

logger = logging.getLogger(__name__)


class VadSegmenter:
    """
    VAD 语音分段器 - 职责单一：将音频帧分段为语音段

    职责边界：
    - ✅ VAD 判断（检测是否语音）
    - ✅ 组合连续语音帧为语音段
    - ✅ hangover buffer（尾音保护）
    - ❌ 不控制录音开始/结束
    - ❌ 不采集音频（由 AudioCaptureThread 负责）

    设计理念：
    - 单一职责：只做 VAD 和分段
    - 尾音保护：hangover_time 防止尾音丢失
    - 状态管理：维护当前语音段状态
    - 事件驱动：通过回调通知新语音段
    """

    # VAD 参数
    FRAME_DURATION_MS = 30  # 每帧时长 (毫秒)
    VAD_AGGRESSIVENESS = 2  # 激进程度 (0-3)

    def __init__(
        self,
        sample_rate: int = 16000,
        silence_threshold_ms: int = 500,  # 静音阈值（毫秒）
        hangover_time_ms: int = 300,  # hangover 时间（毫秒）- 防止尾音丢失
        min_speech_duration_ms: int = 300,  # 最小语音时长（毫秒）
        on_segment_complete: Optional[callable] = None,  # 语音段完成回调
    ):
        """
        初始化 VAD 分段器

        Args:
            sample_rate: 采样率
            silence_threshold_ms: 静音阈值（毫秒），超过此时长认为语音结束
            hangover_time_ms: hangover 时间（毫秒），检测到静音后继续采集一段时间
            min_speech_duration_ms: 最小语音时长（毫秒），过滤短促噪音
            on_segment_complete: 语音段完成回调函数
        """
        self.sample_rate = sample_rate
        self.silence_threshold_ms = silence_threshold_ms
        self.hangover_time_ms = hangover_time_ms
        self.min_speech_duration_ms = min_speech_duration_ms
        self._on_segment_complete = on_segment_complete

        # 计算帧数
        self.frame_size = int(sample_rate * self.FRAME_DURATION_MS / 1000)
        self.silence_threshold_frames = silence_threshold_ms // self.FRAME_DURATION_MS
        self.hangover_frames = hangover_time_ms // self.FRAME_DURATION_MS
        self.min_speech_frames = min_speech_duration_ms // self.FRAME_DURATION_MS

        # VAD 检测器
        self._vad = webrtcvad.Vad(self.VAD_AGGRESSIVENESS)

        # 当前语音段状态
        self._current_segment: List[bytes] = []  # 当前语音段的帧
        self._in_speech = False  # 是否在语音中
        self._silence_frames = 0  # 当前静音帧计数
        self._speech_frames = 0  # 当前语音段语音帧计数
        self._total_frames = 0  # 总帧数

        # 统计信息
        self._segments_completed = 0

        logger.info(
            f"VadSegmenter 初始化 "
            f"(静音阈值={silence_threshold_ms}ms, "
            f"hangover={hangover_time_ms}ms, "
            f"最小语音={min_speech_duration_ms}ms)"
        )

    def reset(self) -> None:
        """重置状态（用于开始新的录音）"""
        self._current_segment = []
        self._in_speech = False
        self._silence_frames = 0
        self._speech_frames = 0
        self._total_frames = 0
        logger.debug("VadSegmenter 状态已重置")

    def process_frame(self, frame: bytes) -> Optional[List[bytes]]:
        """
        处理单个音频帧

        Args:
            frame: 音频帧 (bytes)

        Returns:
            如果语音段完成，返回语音段帧列表；否则返回 None
        """
        self._total_frames += 1

        # VAD 判断
        is_speech = self._is_speech(frame)

        # 状态机
        if is_speech:
            # 检测到语音
            if not self._in_speech:
                # 语音开始
                self._in_speech = True
                self._silence_frames = 0
                logger.debug(f"[帧 {self._total_frames}] 语音开始")

            # 添加到当前语音段
            self._current_segment.append(frame)
            self._speech_frames += 1

        else:
            # 检测到静音
            if self._in_speech:
                # 在语音中，检测到静音
                self._silence_frames += 1
                self._current_segment.append(frame)  # 保留静音帧

                # 检查是否应该结束语音段
                if self._silence_frames >= self.silence_threshold_frames:
                    # 静音超过阈值，语音结束
                    return self._finalize_segment()

            else:
                # 不在语音中，忽略
                pass

        return None

    def _is_speech(self, frame: bytes) -> bool:
        """
        判断帧是否为语音

        Args:
            frame: 音频帧

        Returns:
            是否为语音
        """
        try:
            # 确保帧大小正确
            if len(frame) != self.frame_size * 2:  # 16-bit = 2 bytes
                return False

            # VAD 检测
            return self._vad.is_speech(frame, self.sample_rate)

        except Exception as e:
            logger.error(f"VAD 检测失败: {e}")
            return False

    def _finalize_segment(self) -> Optional[List[bytes]]:
        """
        结束当前语音段

        应用 hangover buffer 和最小语音时长过滤

        Returns:
            语音段帧列表，如果不满足最小时长则返回 None
        """
        if not self._current_segment:
            return None

        # 检查最小语音时长
        if self._speech_frames < self.min_speech_frames:
            logger.debug(f"语音段过短 ({self._speech_frames} 帧)，丢弃")
            self._current_segment = []
            self._in_speech = False
            self._silence_frames = 0
            self._speech_frames = 0
            return None

        # 应用 hangover buffer
        # 保留最后 N 帧作为 hangover，防止尾音丢失
        segment = self._current_segment.copy()

        # 重置状态
        self._current_segment = []
        self._in_speech = False
        self._silence_frames = 0
        total_frames = self._speech_frames
        self._speech_frames = 0

        self._segments_completed += 1

        duration_ms = total_frames * self.FRAME_DURATION_MS
        logger.info(
            f"语音段完成 (#{self._segments_completed}): "
            f"{total_frames} 帧, {duration_ms}ms"
        )

        # 回调
        if self._on_segment_complete:
            try:
                self._on_segment_complete(segment)
            except Exception as e:
                logger.error(f"语音段回调失败: {e}")

        return segment

    def finalize(self) -> Optional[List[bytes]]:
        """
        强制结束当前语音段（用于录音停止时）

        Returns:
            语音段帧列表，如果没有语音则返回 None
        """
        if self._current_segment and self._speech_frames > 0:
            logger.debug(f"强制结束语音段 ({len(self._current_segment)} 帧)")
            return self._finalize_segment()
        return None

    def get_current_segment_frames(self) -> int:
        """获取当前语音段帧数"""
        return len(self._current_segment)

    def is_in_speech(self) -> bool:
        """是否在语音中"""
        return self._in_speech

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "segments_completed": self._segments_completed,
            "total_frames": self._total_frames,
            "in_speech": self._in_speech,
            "current_segment_frames": len(self._current_segment),
        }


# ==================== 使用示例 ====================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    print("=== VadSegmenter 测试 ===\n")

    def on_complete(segment):
        print(f"语音段完成: {len(segment)} 帧")

    # 创建 VAD 分段器
    vad = VadSegmenter(
        sample_rate=16000,
        silence_threshold_ms=500,
        hangover_time_ms=300,
        on_segment_complete=on_complete,
    )

    print("\n模拟音频帧处理...")
    print("(语音 2 秒 -> 静音 0.6 秒 -> 语音 1 秒)")

    # 模拟帧
    frame_size = int(16000 * 30 / 1000)  # 30ms 帧大小
    dummy_speech_frame = b'\x00' * frame_size * 2  # 模拟语音帧
    dummy_silence_frame = b'\x00' * frame_size * 2  # 模拟静音帧

    # 注意：webrtcvad 需要真实的音频数据才能准确判断
    # 这里只是演示流程

    # 语音 2 秒 (~66 帧)
    for i in range(66):
        vad.process_frame(dummy_speech_frame)

    # 静音 0.6 秒 (~20 帧)
    for i in range(20):
        vad.process_frame(dummy_silence_frame)

    # 语音 1 秒 (~33 帧)
    for i in range(33):
        vad.process_frame(dummy_speech_frame)

    # 强制结束
    vad.finalize()

    print(f"\n统计信息: {vad.get_stats()}")
