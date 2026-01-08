# core/audio_capture.py
# 音频采集模块 (含 VAD)

import array
import logging
import queue
import threading
import time
import wave
import webrtcvad
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Tuple

import sounddevice as sd
import numpy as np

from config import AUDIO_DIR

logger = logging.getLogger(__name__)


class AudioCapture:
    """
    音频采集类

    功能:
    - 麦克风音频采集
    - WebRTC VAD 语音活动检测
    - 音频数据保存
    - 支持多麦克风设备
    """

    # VAD 参数
    VAD_FRAME_DURATION_MS = 30  # 每帧时长 (毫秒)
    VAD_AGGRESSIVENESS = 2      # 激进程度 (0-3)
    MAX_RECORDING_DURATION = 29  # 最大录音时长（秒）- 防止按键释放丢失导致录音卡住
    MIN_RECORDING_DURATION = 0.2  # 最小录音时长（秒）- 防止按键太短导致没录到音频

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        vad_threshold: int = 500,
        device: Optional[str] = None,
        max_recording_duration: int = MAX_RECORDING_DURATION,
        on_auto_stop: Optional[Callable] = None,
    ):
        """
        初始化音频采集器

        Args:
            sample_rate: 采样率 (默认 16000Hz)
            channels: 声道数 (默认 1)
            vad_threshold: VAD 静音阈值 (毫秒)
            device: 麦克风设备名称
            max_recording_duration: 最大录音时长（秒），防止按键释放丢失
            on_auto_stop: 自动停止时的回调函数（参数为音频数据）
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.vad_threshold = vad_threshold
        self.max_recording_duration = max_recording_duration
        self._on_auto_stop = on_auto_stop

        # 音频帧大小
        self.frame_size = int(sample_rate * self.VAD_FRAME_DURATION_MS / 1000)

        # VAD 检测器
        self._vad = webrtcvad.Vad(self.VAD_AGGRESSIVENESS)

        # 音频设备
        self._device_info = self._get_device_info(device)
        self._device_index = self._device_info["index"] if self._device_info else None

        # 录音状态
        self._is_recording = False
        self._audio_queue = queue.Queue()
        self._record_thread: Optional[threading.Thread] = None
        self._stream: Optional[sd.InputStream] = None
        self._timeout_thread: Optional[threading.Thread] = None

        # 录音开始时间（用于超时检测）
        self._recording_start_time: Optional[float] = None

        # 音频数据缓冲
        self._audio_buffer = []
        self._silence_frames = 0
        self._voice_detected = False

        # 诊断统计
        self._callback_count = 0  # 回调被调用次数
        self._last_callback_time: Optional[float] = None  # 最后一次回调时间

        # v1.3.5: 预热标志
        self._is_warmed = False

        # 确保音频目录存在
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)

        logger.info(f"音频采集器初始化完成 (设备: {self._device_info['name'] if self._device_info else '默认'})")

    def _get_device_info(self, device_name: Optional[str]) -> Optional[dict]:
        """
        获取音频设备信息

        Args:
            device_name: 设备名称 (None 则使用默认设备)

        Returns:
            设备信息字典
        """
        try:
            devices = sd.query_devices()

            # 查找指定设备
            if device_name:
                for i, dev in enumerate(devices):
                    if dev["name"] == device_name and dev["max_input_channels"] > 0:
                        return {
                            "index": i,
                            "name": dev["name"],
                            "channels": dev["max_input_channels"],
                        }
                logger.warning(f"未找到设备: {device_name}，使用默认设备")

            # 使用默认输入设备
            default_device = sd.query_devices(kind="input")
            return {
                "index": None,  # None 表示使用默认设备
                "name": default_device["name"],
                "channels": default_device["max_input_channels"],
            }

        except Exception as e:
            logger.error(f"获取音频设备失败: {e}")
            return None

    @staticmethod
    def list_devices() -> list:
        """列出所有可用的音频输入设备"""
        try:
            devices = sd.query_devices()
            input_devices = []

            for i, dev in enumerate(devices):
                if dev["max_input_channels"] > 0:
                    input_devices.append({
                        "index": i,
                        "name": dev["name"],
                        "channels": dev["max_input_channels"],
                        "sample_rate": int(dev["default_samplerate"]),
                    })

            return input_devices

        except Exception as e:
            logger.error(f"获取设备列表失败: {e}")
            return []

    def warmup(self) -> bool:
        """
        预热音频流

        v1.3.5 新增：通过创建并立即关闭测试流，触发 sounddevice 初始化
        这样后续 start_recording() 就能快速启动

        Returns:
            是否预热成功
        """
        if self._is_warmed:
            logger.debug("音频流已预热，跳过")
            return True

        logger.info("开始预热音频流...")
        warmup_start = time.perf_counter()

        try:
            # 创建测试流
            test_stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                device=self._device_index,
                dtype=np.int16,
                callback=lambda indata, frames, time, status: None,  # 空回调
            )

            # 启动流（触发 sounddevice 初始化）
            test_stream.start()

            # 等待流稳定（100ms 足够）
            time.sleep(0.1)

            # 立即停止并关闭
            test_stream.stop()
            test_stream.close()

            warmup_time = (time.perf_counter() - warmup_start) * 1000
            self._is_warmed = True

            logger.info(f"✓ 音频流预热完成 (耗时: {warmup_time:.2f}ms)")
            return True

        except Exception as e:
            logger.error(f"音频流预热失败: {e}")
            return False

    def start_recording(self) -> bool:
        """
        开始录音

        v1.3.5 改进：移除复杂的超时逻辑，因为预热后流创建会很快（<50ms）

        Returns:
            是否启动成功
        """
        if self._is_recording:
            logger.warning("录音已在进行中")
            return True

        try:
            # 重置缓冲和统计
            self._audio_buffer = []
            self._silence_frames = 0
            self._voice_detected = False
            self._callback_count = 0
            self._last_callback_time = None
            self._recording_start_time = time.time()
            self._is_recording = True  # 先设置为 True，让超时监控可以工作

            # 启动超时保护线程（在创建流之前启动，防止卡死）
            self._start_timeout_monitor()

            # v1.3.5: 直接创建流（预热后应该很快，<50ms）
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                device=self._device_index,
                dtype=np.int16,
                callback=self._audio_callback,
            )
            self._stream.start()

            logger.info("开始录音")
            return True

        except Exception as e:
            logger.error(f"启动录音失败: {e}")
            self._is_recording = False
            self._recording_start_time = None
            return False

    def stop_recording(self) -> Optional[bytes]:
        """
        停止录音并返回音频数据

        Returns:
            WAV 格式音频数据 (bytes)
        """
        if not self._is_recording:
            return None

        try:
            # 检查录音时长，如果太短则等待
            if self._recording_start_time:
                elapsed = time.time() - self._recording_start_time
                if elapsed < self.MIN_RECORDING_DURATION:
                    # 等待直到达到最小录音时长
                    wait_time = self.MIN_RECORDING_DURATION - elapsed
                    logger.debug(f"录音时长 {elapsed:.3f}s 太短，等待 {wait_time:.3f}s")
                    time.sleep(wait_time)

            # 先保存音频缓冲区和状态，防止后续操作失败
            audio_buffer = self._audio_buffer.copy() if self._audio_buffer else []

            # 计算实际录音时长
            recording_duration = 0.0
            if self._recording_start_time:
                recording_duration = time.time() - self._recording_start_time

            self._is_recording = False
            self._recording_start_time = None

            # 停止超时监控线程
            self._timeout_thread = None

            # 输出诊断信息
            logger.info(f"停止录音，时长: {recording_duration:.3f}s")
            logger.info(f"  回调调用次数: {self._callback_count}")
            logger.info(f"  缓冲区帧数: {len(audio_buffer)}")
            if self._last_callback_time:
                time_since_last = time.time() - self._last_callback_time
                logger.info(f"  最后回调: {time_since_last:.3f}s 前")

            # 停止音频流（带超时保护）
            if self._stream:
                try:
                    # 使用线程来避免阻塞
                    stop_result = {'done': False, 'error': None}

                    def stop_stream():
                        try:
                            self._stream.stop()
                            self._stream.close()
                            stop_result['done'] = True
                        except Exception as e:
                            stop_result['error'] = e
                        finally:
                            self._stream = None

                    # 启动停止线程
                    stop_thread = threading.Thread(target=stop_stream, daemon=True)
                    stop_thread.start()

                    # 等待最多 2 秒
                    stop_thread.join(timeout=2.0)

                    if not stop_result['done']:
                        logger.warning("音频流停止超时，强制跳过")
                        # 强制清理
                        self._stream = None
                    elif stop_result['error']:
                        raise stop_result['error']

                    logger.debug("音频流已停止")

                except Exception as e:
                    logger.warning(f"停止音频流时出错: {e}，继续处理")
                    self._stream = None

            # 检查是否有音频数据
            if not audio_buffer:
                logger.warning(f"❌ 没有录制到音频数据 (录音时长: {recording_duration:.3f}s)")
                logger.warning(f"诊断信息:")
                logger.warning(f"  回调调用次数: {self._callback_count}")

                if self._callback_count == 0:
                    logger.warning(f"  问题: 音频回调从未被调用！")
                    logger.warning(f"  可能原因:")
                    logger.warning(f"    1. 音频流创建失败但未报错")
                    logger.warning(f"    2. 麦克风设备被其他应用占用")
                    logger.warning(f"    3. 麦克风驱动程序问题")
                    logger.warning(f"  建议: 尝试重启应用或更换麦克风设备")
                else:
                    logger.warning(f"  问题: 回调被调用了 {self._callback_count} 次，但缓冲区为空！")
                    logger.warning(f"  可能原因:")
                    logger.warning(f"    1. 回调函数抛出异常")
                    logger.warning(f"    2. 内存不足")
                    logger.warning(f"    3. 音频流内部错误")

                return None

            # 转换为 WAV 格式
            logger.debug("开始转换音频为 WAV 格式")
            wav_data = self._convert_to_wav(audio_buffer)

            # 计算音频时长
            audio_duration = len(audio_buffer) * self.VAD_FRAME_DURATION_MS / 1000
            logger.info(f"录音完成: 时长 {recording_duration:.2f}s, 音频 {audio_duration:.2f}s, {len(audio_buffer)} 帧")

            return wav_data

        except Exception as e:
            logger.error(f"停止录音失败: {e}")
            # 确保状态被重置
            self._is_recording = False
            self._stream = None
            return None

    def _audio_callback(self, indata, frames, time_info, status):
        """
        音频流回调函数

        Args:
            indata: 输入音频数据
            frames: 帧数
            time_info: 时间信息
            status: 状态
        """
        try:
            # 更新统计信息
            self._callback_count += 1
            self._last_callback_time = time.time()

            if status:
                logger.warning(f"音频流状态: {status}")

            # 转换为 bytes
            audio_bytes = indata.tobytes()

            # 添加到队列（用于音量检测等）
            self._audio_queue.put(audio_bytes)

            # 直接添加到音频缓冲区
            self._audio_buffer.append(audio_bytes)

            # 每 100 次回调输出一次日志（约每 3 秒）
            if self._callback_count % 100 == 0:
                logger.debug(f"音频回调已调用 {self._callback_count} 次，缓冲区大小: {len(self._audio_buffer)}")

        except Exception as e:
            logger.error(f"音频回调异常: {e}，但继续录音")

    def _convert_to_wav(self, audio_frames: list) -> bytes:
        """
        将音频帧转换为 WAV 格式

        Args:
            audio_frames: 音频帧列表

        Returns:
            WAV 格式音频数据
        """
        import io

        # 创建内存缓冲区
        buffer = io.BytesIO()

        # 写入 WAV 文件
        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(self.sample_rate)

            # 写入音频数据
            for frame in audio_frames:
                wf.writeframes(frame)

        return buffer.getvalue()

    def save_audio(self, audio_data: bytes, filename: Optional[str] = None) -> Path:
        """
        保存音频到文件

        Args:
            audio_data: WAV 格式音频数据
            filename: 文件名 (None 则自动生成)

        Returns:
            保存的文件路径
        """
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

    def is_recording(self) -> bool:
        """是否正在录音"""
        return self._is_recording

    def get_audio_level(self) -> float:
        """
        获取当前音频音量等级

        Returns:
            音量等级 (0.0 - 1.0)
        """
        if not self._is_recording or self._audio_queue.empty():
            return 0.0

        try:
            # 获取最新的音频帧
            audio_bytes = self._audio_queue.get_nowait()

            # 计算音量 (RMS)
            samples = np.frombuffer(audio_bytes, dtype=np.int16)
            rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
            level = min(rms / 32768, 1.0)

            return level

        except queue.Empty:
            return 0.0

    def detect_voice_activity(self, audio_bytes: bytes) -> bool:
        """
        检测音频中是否包含语音

        Args:
            audio_bytes: 音频数据 (必须为 frame_size 大小)

        Returns:
            是否包含语音
        """
        try:
            # 确保数据长度正确
            if len(audio_bytes) != self.frame_size * 2:  # 16-bit = 2 bytes
                return False

            # VAD 检测
            is_speech = self._vad.is_speech(audio_bytes, self.sample_rate)

            if is_speech:
                self._voice_detected = True
                self._silence_frames = 0
            else:
                self._silence_frames += 1

            return is_speech

        except Exception as e:
            logger.error(f"VAD 检测失败: {e}")
            return False

    def should_stop_by_silence(self) -> bool:
        """
        检查是否应该因静音而停止录音

        Returns:
            是否应该停止
        """
        if not self._voice_detected:
            # 还没有检测到语音，不停止
            return False

        # 计算静音时长
        silence_duration = self._silence_frames * self.VAD_FRAME_DURATION_MS

        return silence_duration >= self.vad_threshold

    def _start_timeout_monitor(self) -> None:
        """启动录音超时监控线程"""
        def monitor():
            while self._is_recording and self._recording_start_time:
                elapsed = time.time() - self._recording_start_time
                if elapsed >= self.max_recording_duration:
                    logger.warning(f"录音超过最大时长 ({self.max_recording_duration}秒)，自动停止")

                    # 检查是否有音频流（处理流创建卡住的情况）
                    if self._stream is None:
                        logger.error("音频流未创建，强制重置状态")
                        self._is_recording = False
                        self._recording_start_time = None
                        # 不调用回调，因为没有音频数据
                        break

                    # 自动停止录音并获取音频数据
                    audio_data = self.stop_recording()
                    # 如果有回调且获取到音频数据，调用回调
                    if self._on_auto_stop and audio_data:
                        try:
                            self._on_auto_stop(audio_data)
                        except Exception as e:
                            logger.error(f"自动停止回调执行失败: {e}")
                    break
                time.sleep(0.5)  # 每秒检查两次

        self._timeout_thread = threading.Thread(target=monitor, daemon=True)
        self._timeout_thread.start()

    def get_recording_duration(self) -> float:
        """
        获取当前录音时长（秒）

        Returns:
            录音时长，未录音时返回 0
        """
        if not self._is_recording or not self._recording_start_time:
            return 0.0
        return time.time() - self._recording_start_time


# ==================== 使用示例 ====================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # 列出可用设备
    print("可用音频设备:")
    devices = AudioCapture.list_devices()
    for dev in devices:
        print(f"  [{dev['index']}] {dev['name']}")

    # 创建音频采集器
    capture = AudioCapture(
        sample_rate=16000,
        vad_threshold=500,
    )

    print("\n按回车开始录音，再按回车停止...")

    # 等待用户输入
    input()

    # 开始录音
    if capture.start_recording():
        print("录音中...")

        # 实时显示音量
        import time
        start_time = time.time()

        while capture.is_recording():
            level = capture.get_audio_level()
            elapsed = time.time() - start_time
            print(f"\r音量: [{level*100:6.2f}%] 时长: {elapsed:.1f}s", end="")

            # 检查是否应该停止（用户按回车）
            if capture._audio_queue.qsize() > 100:  # 模拟用户输入
                break

            time.sleep(0.1)

        # 停止录音
        audio_data = capture.stop_recording()

        if audio_data:
            # 保存音频
            filepath = capture.save_audio(audio_data)
            print(f"\n音频已保存到: {filepath}")
            print(f"文件大小: {len(audio_data)} bytes")
        else:
            print("\n没有录制到音频")
