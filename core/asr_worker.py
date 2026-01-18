# core/asr_worker.py
# ASR 异步处理线程 (P0 重构)

import logging
import queue
import threading
import time
import wave
from io import BytesIO
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np

from core.asr_engine import ASREngine

logger = logging.getLogger(__name__)


class ASRWorker:
    """
    ASR 异步处理线程 - P0 重构

    职责边界：
    - ✅ 异步处理音频识别
    - ✅ 流式接收音频 segment
    - ✅ 预热模型（启动时加载）
    - ✅ 松键即出字（主流程不阻塞）
    - ❌ 不采集音频（由 AudioCaptureThread 负责）
    - ❌ 不做 VAD 判断（由 VadSegmenter 负责）

    P0 目标：
    - ASR 不阻塞主流程
    - 采集过程中推送 segment，提前处理
    - 松键时 ASR 已处理 80-90% 音频
    - 启动时预热模型
    """

    def __init__(
        self,
        model_id: str = "sense-voice",
        sample_rate: int = 16000,
        channels: int = 1,
        on_result: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ):
        """
        初始化 ASR Worker

        Args:
            model_id: ASR 模型 ID
            sample_rate: 采样率
            channels: 声道数
            on_result: 识别结果回调（参数：识别文本）
            on_error: 错误回调
        """
        self.model_id = model_id
        self.sample_rate = sample_rate
        self.channels = channels
        self._on_result = on_result
        self._on_error = on_error

        # ASR 引擎（懒加载）
        self._asr_engine: Optional[ASREngine] = None

        # 工作线程
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False

        # 音频段队列（流式输入）
        self._segment_queue: queue.Queue = queue.Queue(maxsize=100)

        # 当前会话的音频段
        self._current_session_segments: List[bytes] = []
        self._session_lock = threading.Lock()

        # P0: 任务幂等机制 - generation_id
        self._generation = 0  # 当前任务代号，每次 start_session 递增

        # 统计
        self._total_processed = 0
        self._total_segments = 0

        logger.info("ASRWorker 初始化完成")

    def warmup(self) -> bool:
        """
        预热 ASR 模型 - P0 关键改进

        启动时立即加载模型，避免首次识别延迟

        Returns:
            是否预热成功
        """
        logger.info("开始 ASR 模型预热...")

        if self._asr_engine is None:
            self._asr_engine = ASREngine(model_id=self.model_id)

        success = self._asr_engine.load_model()

        if success:
            # 用空音频测试一次，确保模型真正就绪
            try:
                dummy_result = self._asr_engine.recognize_bytes(b'\x00' * 3200)  # 100ms 静音
                logger.info(f"ASR 模型预热完成 (测试结果: '{dummy_result or '(empty)'}')")
            except Exception as e:
                logger.warning(f"ASR 预热测试失败: {e}")

        return success

    def start(self) -> bool:
        """
        启动 ASR Worker 线程

        Returns:
            是否启动成功
        """
        if self._running:
            logger.warning("ASRWorker 已在运行")
            return True

        self._running = True

        # 启动工作线程
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="ASRWorker"
        )
        self._worker_thread.start()

        logger.info("ASRWorker 已启动")
        return True

    def stop(self) -> None:
        """停止 ASR Worker"""
        if not self._running:
            return

        logger.info("停止 ASRWorker...")
        self._running = False

        # 等待线程结束（最多 2 秒）
        if self._worker_thread:
            self._worker_thread.join(timeout=2.0)
            self._worker_thread = None

        logger.info("ASRWorker 已停止")

    def wait_until_stopped(self, timeout: float = 5.0) -> bool:
        """
        等待 Worker 完全停止

        v1.4.3: 用于应用退出时确保 ASR 处理完成

        Args:
            timeout: 超时时间（秒）

        Returns:
            是否在超时前停止
        """
        logger.info(f"⏳ [ASRWorker] 等待完全停止 (超时 {timeout}s)...")

        deadline = time.time() + timeout
        while self._running:
            if time.time() > deadline:
                logger.warning(f"⚠ [ASRWorker] 等待停止超时 (running={self._running})")
                return False
            time.sleep(0.05)  # 50ms 检查一次

        # 确认线程也已结束
        if self._worker_thread and self._worker_thread.is_alive():
            logger.info("⏳ [ASRWorker] Worker 线程仍在运行，等待线程结束...")
            thread_deadline = time.time() + 2.0  # 额外等待 2 秒
            while self._worker_thread.is_alive():
                if time.time() > thread_deadline:
                    logger.warning("⚠ [ASRWorker] Worker 线程停止超时")
                    return False
                time.sleep(0.05)

        logger.info("✓ [ASRWorker] 已完全停止")
        return True

    def restart(self) -> bool:
        """
        重启 ASR Worker（幂等操作）

        Returns:
            是否重启成功
        """
        logger.info("重启 ASRWorker...")
        self.stop()
        return self.start()

    def start_session(self) -> None:
        """
        开始新的识别会话

        每次按键按下时调用，重置会话状态并递增 generation

        P0 幂等机制：递增 generation，使旧任务失效
        """
        with self._session_lock:
            self._generation += 1
            self._current_session_segments = []
            logger.debug("ASR 会话已开始 (generation=%d)", self._generation)

    def push_segment(self, segment: List[bytes]) -> None:
        """
        推送音频段 - 流式处理

        在音频采集过程中调用，提前推送 segment 到队列

        Args:
            segment: 音频帧列表
        """
        try:
            # 将 segment 合并为单个音频块
            audio_bytes = b''.join(segment)

            # 非阻塞放入队列
            self._segment_queue.put_nowait(audio_bytes)

            # 保存到当前会话
            with self._session_lock:
                self._current_session_segments.append(audio_bytes)

            self._total_segments += 1

            logger.debug(f"推送音频段: {len(segment)} 帧, 队列大小: {self._segment_queue.qsize()}")

        except queue.Full:
            logger.warning("ASR 队列已满，丢弃音频段")

    def finalize_session(self) -> None:
        """
        完成当前会话 - 触发最终识别

        松键时调用，触发 ASR 处理所有已收集的音频

        P0 目标：松键即出字
        """
        with self._session_lock:
            if not self._current_session_segments:
                logger.debug("会话无音频，跳过")
                return

            logger.info(f"完成会话: {len(self._current_session_segments)} 个段")

            # 合并所有段
            all_audio = b''.join(self._current_session_segments)

            # 放入队列进行异步处理
            try:
                self._segment_queue.put_nowait(all_audio)
            except queue.Full:
                logger.error("ASR 队列已满，无法处理最终音频")

    def process_audio(self, audio_data: bytes) -> None:
        """
        直接处理完整音频 - 简化接口

        用于非流式场景，一次性提交完整音频进行异步识别

        P0 幂等机制：附带当前 generation，防止旧任务覆盖新任务

        Args:
            audio_data: 完整的音频数据（bytes）
        """
        if not audio_data:
            logger.warning("音频数据为空，跳过处理")
            return

        try:
            # 获取当前 generation
            with self._session_lock:
                generation = self._generation

            # 非阻塞放入队列（附带 generation）
            self._segment_queue.put_nowait((audio_data, generation))
            logger.debug("音频已提交到 ASR 队列，大小: %d bytes, generation=%d",
                        len(audio_data), generation)
        except queue.Full:
            logger.error("ASR 队列已满，无法处理音频")

    def _worker_loop(self):
        """
        ASR 工作循环 - 在独立线程中运行

        持续从队列获取音频段并识别

        P0 幂等机制：检查 generation，丢弃过期任务
        """
        logger.info("ASR Worker 线程已启动")

        while self._running:
            try:
                # 阻塞获取音频段（超时 0.1 秒，避免永久阻塞）
                try:
                    item = self._segment_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                # 解包 audio_data 和 generation
                if isinstance(item, tuple) and len(item) == 2:
                    audio_data, generation = item
                else:
                    # 兼容旧格式（只有 audio_data）
                    audio_data = item
                    generation = 0

                # P0: 检查 generation 是否过期
                with self._session_lock:
                    current_generation = self._generation

                if generation != current_generation:
                    logger.debug("任务已过期 (generation=%d, current=%d)，丢弃",
                               generation, current_generation)
                    continue  # 跳过过期任务

                # 识别音频
                self._process_audio(audio_data)

                self._total_processed += 1

            except Exception as e:
                logger.error("ASR Worker 处理失败: %s", e)
                if self._on_error:
                    self._on_error(e)

        logger.info("ASR Worker 线程已退出")

    def _process_audio(self, audio_data: bytes):
        """
        处理音频识别

        Args:
            audio_data: 音频数据（bytes）
        """
        if not audio_data:
            return

        try:
            # 懒加载 ASR 引擎
            if self._asr_engine is None:
                self._asr_engine = ASREngine(model_id=self.model_id)
                if not self._asr_engine.load_model():
                    raise RuntimeError("ASR 模型加载失败")

            # 识别
            result = self._asr_engine.recognize_bytes(audio_data)

            if result:
                logger.info("ASR 识别: '%s'", result)
                logger.info("_on_result 回调: %s", self._on_result)

                # 回调
                if self._on_result:
                    logger.info("调用 _on_result 回调...")
                    try:
                        self._on_result(result)
                        logger.info("_on_result 回调完成")
                    except Exception as cb_error:
                        logger.error("_on_result 回调异常: %s", cb_error)
                        raise
                else:
                    logger.error("_on_result 回调未注册！")
            else:
                logger.info("ASR 识别结果为空")

        except Exception as e:
            logger.error(f"ASR 识别失败: {e}")
            raise

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "running": self._running,
            "total_processed": self._total_processed,
            "total_segments": self._total_segments,
            "queue_size": self._segment_queue.qsize(),
            "model_loaded": self._asr_engine is not None and self._asr_engine._recognizer is not None,
        }


# ==================== 使用示例 ====================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    def on_result(text):
        print(f"识别结果: {text}")

    def on_error(e):
        print(f"错误: {e}")

    # 创建 ASR Worker
    worker = ASRWorker(on_result=on_result, on_error=on_error)

    # 预热模型
    print("预热模型...")
    worker.warmup()

    # 启动 Worker
    worker.start()

    print("\n模拟流式音频输入...")
    print("发送 3 个音频段...")

    # 模拟音频段（30ms 帧，16kHz，单声道）
    frame_size = int(16000 * 30 / 1000) * 2  # bytes
    dummy_audio = b'\x00' * frame_size

    # 开始会话
    worker.start_session()

    # 推送 3 个段
    for i in range(3):
        segment = [dummy_audio] * 10  # 每段 10 帧 = 300ms
        worker.push_segment(segment)
        time.sleep(0.1)

    # 完成会话
    worker.finalize_session()

    print("\n等待处理...")
    time.sleep(2)

    print(f"\n统计: {worker.get_stats()}")

    worker.stop()
