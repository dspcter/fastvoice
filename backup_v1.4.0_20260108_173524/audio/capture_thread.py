# core/audio/capture_thread.py
# 音频采集线程 - 纯采集到 ring buffer

import logging
import threading
import time
from collections import deque
from typing import Optional, Callable

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


class AudioCaptureThread:
    """
    音频采集线程 - 职责单一：只采集音频帧到 ring buffer

    职责边界：
    - ✅ 采集音频帧
    - ✅ 写入 ring buffer (deque with maxlen)
    - ❌ 不做 VAD 判断
    - ❌ 不控制录音开始/结束
    - ❌ 不处理音频数据

    设计理念：
    - 单一职责：只负责采集
    - 有界缓冲：使用 deque(maxlen=N) 防止内存无限增长
    - 线程安全：通过 deque 的线程安全操作
    - 独立运行：与 VAD、控制逻辑解耦
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        device: Optional[str] = None,
        buffer_maxlen: int = 1000,  # 最大缓存帧数 (~30秒)
        on_error: Optional[Callable] = None,
    ):
        """
        初始化音频采集线程

        Args:
            sample_rate: 采样率 (默认 16000Hz)
            channels: 声道数 (默认 1)
            device: 麦克风设备名称
            buffer_maxlen: ring buffer 最大长度 (帧数)
            on_error: 错误回调函数
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.device = device
        self._on_error = on_error

        # Ring buffer - 有界队列，防止内存无限增长
        # 使用 deque 替代 list，自动丢弃最老的帧
        self._buffer = deque(maxlen=buffer_maxlen)

        # 音频流和线程
        self._stream: Optional[sd.InputStream] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        # 设备信息
        self._device_info = self._get_device_info(device)
        self._device_index = self._device_info["index"] if self._device_info else None

        # 统计信息
        self._frames_captured = 0
        self._start_time: Optional[float] = None

        logger.info(f"AudioCaptureThread 初始化 (设备: {self._device_info['name'] if self._device_info else '默认'}, maxlen={buffer_maxlen})")

    def _get_device_info(self, device_name: Optional[str]) -> Optional[dict]:
        """获取音频设备信息"""
        try:
            devices = sd.query_devices()

            if device_name:
                for i, dev in enumerate(devices):
                    if dev["name"] == device_name and dev["max_input_channels"] > 0:
                        return {"index": i, "name": dev["name"], "channels": dev["max_input_channels"]}
                logger.warning(f"未找到设备: {device_name}，使用默认设备")

            default_device = sd.query_devices(kind="input")
            return {
                "index": None,
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

    def start(self) -> bool:
        """
        启动音频采集线程

        Returns:
            是否启动成功
        """
        with self._lock:
            if self._running:
                logger.warning("AudioCaptureThread 已在运行")
                return True

            try:
                # 清空 buffer
                self._buffer.clear()
                self._frames_captured = 0
                self._start_time = time.time()
                self._running = True

                # 创建音频流
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    device=self._device_index,
                    dtype=np.int16,
                    callback=self._audio_callback,
                )
                self._stream.start()

                logger.info("AudioCaptureThread 已启动")
                return True

            except Exception as e:
                logger.error(f"启动 AudioCaptureThread 失败: {e}")
                self._running = False
                if self._on_error:
                    self._on_error(e)
                return False

    def stop(self) -> None:
        """停止音频采集线程"""
        with self._lock:
            if not self._running:
                return

            self._running = False

            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception as e:
                    logger.warning(f"停止音频流出错: {e}")
                finally:
                    self._stream = None

            duration = time.time() - self._start_time if self._start_time else 0
            logger.info(f"AudioCaptureThread 已停止 (采集 {self._frames_captured} 帧, {duration:.2f}s)")

    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running

    def _audio_callback(self, indata, frames, time_info, status):
        """
        音频流回调函数 - 只负责写入 buffer

        职责单一：
        - ✅ 将音频帧写入 ring buffer
        - ❌ 不做 VAD 判断
        - ❌ 不控制录音状态
        """
        if status:
            logger.debug(f"音频流状态: {status}")

        try:
            # 转换为 bytes
            audio_bytes = indata.tobytes()

            # 写入 ring buffer
            # deque 是线程安全的，append 操作自动加锁
            self._buffer.append(audio_bytes)
            self._frames_captured += 1

        except Exception as e:
            logger.error(f"音频回调出错: {e}")
            if self._on_error:
                self._on_error(e)

    def get_frames(self, max_frames: Optional[int] = None) -> list:
        """
        获取 buffer 中的音频帧

        Args:
            max_frames: 最大获取帧数 (None 则获取全部)

        Returns:
            音频帧列表 (bytes)
        """
        # deque 转 list
        frames = list(self._buffer)

        if max_frames and len(frames) > max_frames:
            frames = frames[-max_frames:]  # 取最新的 N 帧

        return frames

    def clear_buffer(self) -> None:
        """清空 buffer"""
        self._buffer.clear()

    def get_buffer_size(self) -> int:
        """获取当前 buffer 大小"""
        return len(self._buffer)

    def get_duration(self) -> float:
        """
        获取采集时长（秒）

        Returns:
            采集时长，未启动时返回 0
        """
        if not self._start_time:
            return 0.0
        return time.time() - self._start_time


# ==================== 使用示例 ====================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    print("=== AudioCaptureThread 测试 ===\n")

    # 列出可用设备
    print("可用音频设备:")
    devices = AudioCaptureThread.list_devices()
    for dev in devices:
        print(f"  [{dev['index']}] {dev['name']}")

    # 创建采集线程
    capture = AudioCaptureThread(sample_rate=16000)

    print("\n启动采集线程...")
    capture.start()

    print("采集 5 秒...")
    time.sleep(5)

    print(f"\n停止采集，共采集 {capture.get_buffer_size()} 帧")
    capture.stop()

    print(f"\n获取前 100 帧:")
    frames = capture.get_frames(max_frames=100)
    print(f"获取到 {len(frames)} 帧")
    if frames:
        print(f"第一帧大小: {len(frames[0])} bytes")
