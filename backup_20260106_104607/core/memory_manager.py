# core/memory_manager.py
# 内存管理和清理模块

import gc
import logging
import os
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    内存管理器

    职责：
    - 定期清理临时文件
    - 监控内存使用
    - 强制垃圾回收
    """

    def __init__(
        self,
        max_audio_files: int = 50,           # 最多保留音频文件数
        max_audio_size_mb: float = 500,      # 音频文件夹最大大小 (MB)
        max_log_size_mb: float = 10,         # 单个日志文件最大大小 (MB)
        max_log_files: int = 3,              # 最多保留日志文件数
        cleanup_interval: int = 300,         # 清理间隔 (秒，默认 5 分钟)
        force_gc_interval: int = 60,         # 强制 GC 间隔 (秒，默认 1 分钟)
    ):
        """
        初始化内存管理器

        Args:
            max_audio_files: 最多保留音频文件数
            max_audio_size_mb: 音频文件夹最大大小
            max_log_size_mb: 单个日志文件最大大小
            max_log_files: 最多保留日志文件数
            cleanup_interval: 清理间隔（秒）
        """
        self.max_audio_files = max_audio_files
        self.max_audio_size_mb = max_audio_size_mb
        self.max_log_size_mb = max_log_size_mb
        self.max_log_files = max_log_files
        self.cleanup_interval = cleanup_interval

        # 路径配置
        from config import AUDIO_DIR, STORAGE_DIR
        self.audio_dir = AUDIO_DIR
        self.log_dir = STORAGE_DIR

        # 清理线程
        self._cleanup_thread: Optional[threading.Thread] = None
        self._running = False

        # 缓存 psutil.Process 对象，避免每次 get_stats() 都创建新对象
        try:
            import psutil
            self._process = psutil.Process()
        except ImportError:
            self._process = None

        logger.info(
            f"内存管理器初始化完成 "
            f"(音频: {max_audio_files}个/{max_audio_size_mb}MB, "
            f"日志: {max_log_files}个/{max_log_size_mb}MB, "
            f"清理间隔: {cleanup_interval}s)"
        )

    def start_auto_cleanup(self) -> None:
        """启动自动清理线程"""
        if self._running:
            logger.warning("自动清理已在运行")
            return

        self._running = True

        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="MemoryCleanup"
        )
        self._cleanup_thread.start()

        logger.info(f"自动清理已启动 (间隔: {self.cleanup_interval}s)")

    def stop_auto_cleanup(self) -> None:
        """停止自动清理线程"""
        if not self._running:
            return

        logger.info("停止自动清理...")
        self._running = False

        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5.0)
            self._cleanup_thread = None

        logger.info("自动清理已停止")

    def _cleanup_loop(self) -> None:
        """清理循环"""
        while self._running:
            try:
                self.cleanup_all()
            except Exception as e:
                logger.error(f"清理失败: {e}")

            # 等待下次清理
            for _ in range(self.cleanup_interval):
                if not self._running:
                    break
                import time
                time.sleep(1)

    def cleanup_all(self) -> None:
        """执行所有清理任务"""
        logger.debug("开始清理任务...")

        audio_freed = self.cleanup_audio_files()
        log_freed = self.cleanup_log_files()

        # 强制垃圾回收
        gc.collect()

        # 输出内存使用情况
        memory_mb = self._get_memory_usage_mb()
        logger.info(
            f"清理完成: 释放音频 {audio_freed}MB, 日志 {log_freed}MB, "
            f"当前内存: {memory_mb:.1f}MB"
        )

    def cleanup_audio_files(self) -> float:
        """
        清理音频文件

        Returns:
            释放的空间（MB）
        """
        if not self.audio_dir.exists():
            return 0.0

        try:
            # 获取所有 wav 文件
            audio_files = list(self.audio_dir.glob("*.wav"))
            if not audio_files:
                return 0.0

            # 按修改时间排序
            audio_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            # 计算当前总大小
            total_size = sum(f.stat().st_size for f in audio_files)
            total_size_mb = total_size / 1024 / 1024

            # 如果文件数量或总大小超过限制，删除旧文件
            freed_bytes = 0
            files_to_keep = []

            for i, audio_file in enumerate(audio_files):
                # 保留最新的 max_audio_files 个文件
                if i < self.max_audio_files:
                    files_to_keep.append(audio_file)
                    continue

                # 计算删除后的大小
                remaining_size = total_size - freed_bytes - audio_file.stat().st_size
                remaining_size_mb = remaining_size / 1024 / 1024

                # 如果剩余大小还在限制内，继续删除
                if remaining_size_mb < self.max_audio_size_mb:
                    try:
                        file_size = audio_file.stat().st_size
                        audio_file.unlink()
                        freed_bytes += file_size
                        logger.debug(f"删除音频: {audio_file.name}")
                    except Exception as e:
                        logger.error(f"删除音频失败 {audio_file}: {e}")
                else:
                    # 大小已在限制内，停止删除
                    break

            freed_mb = freed_bytes / 1024 / 1024
            if freed_mb > 0:
                logger.info(f"音频清理: 释放 {freed_mb:.1f}MB ({len(audio_files) - len(files_to_keep)} 个文件)")

            return freed_mb

        except Exception as e:
            logger.error(f"音频清理失败: {e}")
            return 0.0

    def cleanup_log_files(self) -> float:
        """
        清理日志文件

        Returns:
            释放的空间（MB）
        """
        if not self.log_dir.exists():
            return 0.0

        try:
            # 获取所有日志文件
            log_files = list(self.log_dir.glob("*.log"))
            if not log_files:
                return 0.0

            freed_bytes = 0

            # 检查每个日志文件大小
            for log_file in log_files:
                try:
                    size_mb = log_file.stat().st_size / 1024 / 1024

                    # 如果文件过大，轮转
                    if size_mb > self.max_log_size_mb:
                        # 备份旧内容
                        backup_path = log_file.with_suffix('.log.1')
                        try:
                            if backup_path.exists():
                                backup_path.unlink()
                            log_file.rename(backup_path)
                            logger.debug(f"日志轮转: {log_file.name}")
                        except Exception as e:
                            logger.error(f"日志轮转失败 {log_file}: {e}")
                except Exception as e:
                    logger.error(f"检查日志失败 {log_file}: {e}")

            # 清理旧的备份文件（保留 max_log_files 个）
            all_log_files = list(self.log_dir.glob("*.log*"))
            all_log_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            for log_file in all_log_files[self.max_log_files:]:
                try:
                    freed_bytes += log_file.stat().st_size
                    log_file.unlink()
                    logger.debug(f"删除旧日志: {log_file.name}")
                except Exception as e:
                    logger.error(f"删除日志失败 {log_file}: {e}")

            freed_mb = freed_bytes / 1024 / 1024
            if freed_mb > 0:
                logger.info(f"日志清理: 释放 {freed_mb:.1f}MB")

            return freed_mb

        except Exception as e:
            logger.error(f"日志清理失败: {e}")
            return 0.0

    def _get_memory_usage_mb(self) -> float:
        """
        获取当前进程内存使用（MB）

        Returns:
            内存使用量（MB）
        """
        if self._process is None:
            return 0.0

        try:
            return self._process.memory_info().rss / 1024 / 1024
        except Exception as e:
            logger.error("获取内存使用失败: %s", e)
            return 0.0

    def get_stats(self) -> dict:
        """获取统计信息"""
        audio_count = 0
        audio_size_mb = 0
        if self.audio_dir.exists():
            audio_files = list(self.audio_dir.glob("*.wav"))
            audio_count = len(audio_files)
            audio_size_mb = sum(f.stat().st_size for f in audio_files) / 1024 / 1024

        log_size_mb = 0
        if self.log_dir.exists():
            log_files = list(self.log_dir.glob("*.log*"))
            log_size_mb = sum(f.stat().st_size for f in log_files) / 1024 / 1024

        return {
            "audio_files": audio_count,
            "audio_size_mb": round(audio_size_mb, 2),
            "log_size_mb": round(log_size_mb, 2),
            "memory_mb": round(self._get_memory_usage_mb(), 2),
            "auto_cleanup_running": self._running,
        }


# ==================== 全局单例 ====================

_memory_manager: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    """获取全局内存管理器"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager
