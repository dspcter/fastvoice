# storage/audio_manager.py
# 音频文件管理模块

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from config import AUDIO_DIR

logger = logging.getLogger(__name__)


@dataclass
class AudioFileInfo:
    """音频文件信息"""
    path: Path
    name: str
    size: int
    created_time: datetime

    @property
    def size_mb(self) -> float:
        """文件大小 (MB)"""
        return self.size / (1024 * 1024)

    @property
    def age_days(self) -> int:
        """文件年龄 (天)"""
        return (datetime.now() - self.created_time).days


class AudioManager:
    """
    音频文件管理器

    功能:
    - 列出音频文件
    - 批量删除
    - 按日期自动清理
    """

    # 音频文件扩展名
    AUDIO_EXTENSIONS = [".wav", ".mp3", ".m4a", ".ogg", ".flac"]

    def __init__(self, audio_dir: Path = None):
        """
        初始化音频管理器

        Args:
            audio_dir: 音频文件目录
        """
        self.audio_dir = audio_dir or AUDIO_DIR
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"音频管理器初始化完成 (目录: {self.audio_dir})")

    def list_audio_files(self, sort_by: str = "date") -> List[AudioFileInfo]:
        """
        列出所有音频文件

        Args:
            sort_by: 排序方式 ("date", "name", "size")

        Returns:
            音频文件信息列表
        """
        files = []

        for ext in self.AUDIO_EXTENSIONS:
            for file_path in self.audio_dir.glob(f"*{ext}"):
                try:
                    stat = file_path.stat()
                    created_time = datetime.fromtimestamp(stat.st_ctime)

                    info = AudioFileInfo(
                        path=file_path,
                        name=file_path.name,
                        size=stat.st_size,
                        created_time=created_time,
                    )
                    files.append(info)

                except Exception as e:
                    logger.warning(f"无法读取文件信息: {file_path} - {e}")

        # 排序
        if sort_by == "date":
            files.sort(key=lambda x: x.created_time, reverse=True)
        elif sort_by == "name":
            files.sort(key=lambda x: x.name)
        elif sort_by == "size":
            files.sort(key=lambda x: x.size, reverse=True)

        return files

    def get_total_size(self) -> int:
        """
        获取音频文件总大小

        Returns:
            总大小 (bytes)
        """
        total = 0
        for ext in self.AUDIO_EXTENSIONS:
            for file_path in self.audio_dir.glob(f"*{ext}"):
                try:
                    total += file_path.stat().st_size
                except Exception:
                    pass
        return total

    def get_file_count(self) -> int:
        """
        获取音频文件数量

        Returns:
            文件数量
        """
        count = 0
        for ext in self.AUDIO_EXTENSIONS:
            count += len(list(self.audio_dir.glob(f"*{ext}")))
        return count

    def delete_file(self, file_path: Path) -> bool:
        """
        删除单个文件

        Args:
            file_path: 文件路径

        Returns:
            是否删除成功
        """
        try:
            if file_path.exists():
                file_path.unlink()
                logger.info(f"已删除: {file_path.name}")
                return True
            return False
        except Exception as e:
            logger.error(f"删除文件失败: {e}")
            return False

    def delete_files(self, file_paths: List[Path]) -> int:
        """
        批量删除文件

        Args:
            file_paths: 文件路径列表

        Returns:
            成功删除的数量
        """
        count = 0
        for file_path in file_paths:
            if self.delete_file(file_path):
                count += 1
        return count

    def delete_by_days(self, days: int) -> int:
        """
        删除 N 天前（含）的文件

        Args:
            days: 天数（设置为1时会删除今天及之前的所有文件）

        Returns:
            删除的文件数量
        """
        cutoff_time = datetime.now() - timedelta(days=days)
        count = 0

        for file_info in self.list_audio_files():
            # 使用 <= 来包含 N 天前的文件
            if file_info.created_time <= cutoff_time:
                if self.delete_file(file_info.path):
                    count += 1

        logger.info(f"已删除 {count} 个 {days} 天前（含）的文件")
        return count

    def delete_all(self) -> int:
        """
        删除所有音频文件

        Returns:
            删除的文件数量
        """
        count = 0
        for ext in self.AUDIO_EXTENSIONS:
            for file_path in self.audio_dir.glob(f"*{ext}"):
                if self.delete_file(file_path):
                    count += 1
        return count

    def get_old_files(self, days: int) -> List[AudioFileInfo]:
        """
        获取 N 天前（含）的文件列表

        Args:
            days: 天数

        Returns:
            文件信息列表
        """
        cutoff_time = datetime.now() - timedelta(days=days)
        old_files = []

        for file_info in self.list_audio_files():
            if file_info.created_time <= cutoff_time:
                old_files.append(file_info)

        return old_files


# ==================== 单例 ====================

_audio_manager = None


def get_audio_manager() -> AudioManager:
    """获取全局音频管理器实例"""
    global _audio_manager
    if _audio_manager is None:
        _audio_manager = AudioManager()
    return _audio_manager


# ==================== 使用示例 ====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    manager = get_audio_manager()

    # 列出文件
    files = manager.list_audio_files()
    print(f"共 {len(files)} 个音频文件:")

    for file_info in files:
        print(f"  {file_info.name}")
        print(f"    大小: {file_info.size_mb:.2f} MB")
        print(f"    创建: {file_info.created_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"    年龄: {file_info.age_days} 天")

    # 统计信息
    total_size = manager.get_total_size()
    file_count = manager.get_file_count()

    print(f"\n总大小: {total_size / (1024*1024):.2f} MB")
    print(f"总数量: {file_count} 个")

    # 测试清理 (7天前的文件)
    # manager.delete_by_days(7)
