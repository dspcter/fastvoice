# models/model_manager.py
# 模型管理器 - 下载、缓存、检测

import logging
import os
import shutil
import tarfile
import threading
import zipfile
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests
from huggingface_hub import snapshot_download

from config import ASR_MODEL_DIR, TRANSLATION_MODEL_DIR, ASR_MODELS, TRANSLATION_MODELS

logger = logging.getLogger(__name__)


class ModelType:
    """模型类型"""
    ASR = "asr"
    TRANSLATION = "translation"


class ModelManager:
    """
    模型管理器

    功能:
    - 模型下载 (支持进度回调)
    - 模型缓存管理
    - 模型检测和验证
    - 支持 Hugging Face 和直接 URL 下载
    """

    def __init__(self):
        self._download_threads: Dict[str, threading.Thread] = {}
        self._downloading: Dict[str, bool] = {}

        # 确保目录存在
        ASR_MODEL_DIR.mkdir(parents=True, exist_ok=True)
        TRANSLATION_MODEL_DIR.mkdir(parents=True, exist_ok=True)

        logger.info("模型管理器初始化完成")

    # ==================== ASR 模型管理 ====================

    def check_asr_model(self, model_id: str = "sense-voice") -> bool:
        """
        检查 ASR 模型是否存在

        Args:
            model_id: 模型 ID

        Returns:
            模型是否存在
        """
        if model_id not in ASR_MODELS:
            logger.warning(f"未知的 ASR 模型: {model_id}")
            return False

        model_path = ASR_MODEL_DIR / model_id
        if not model_path.exists():
            return False

        # 检查必需文件
        required_files = ASR_MODELS[model_id].get("files", [])
        for file in required_files:
            if not (model_path / file).exists():
                return False

        return True

    def download_asr_model(
        self,
        model_id: str = "sense-voice",
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """
        下载 ASR 模型

        Args:
            model_id: 模型 ID
            progress_callback: 进度回调 (current, total)

        Returns:
            是否下载成功
        """
        if model_id not in ASR_MODELS:
            logger.error(f"未知的 ASR 模型: {model_id}")
            return False

        # 检查是否已在下载
        if model_id in self._downloading and self._downloading[model_id]:
            logger.warning(f"模型 {model_id} 正在下载中")
            return False

        # 检查是否已存在
        if self.check_asr_model(model_id):
            logger.info(f"模型 {model_id} 已存在")
            return True

        # 启动下载线程
        thread = threading.Thread(
            target=self._download_asr_model_thread,
            args=(model_id, progress_callback),
        )
        thread.daemon = True
        thread.start()

        self._download_threads[model_id] = thread
        self._downloading[model_id] = True

        return True

    def _download_asr_model_thread(
        self,
        model_id: str,
        progress_callback: Optional[Callable[[int, int], None]],
    ) -> None:
        """ASR 模型下载线程"""
        try:
            model_info = ASR_MODELS[model_id]
            url = model_info.get("url")
            file_format = model_info.get("format", "zip")

            if url:
                # 根据格式选择解压方法
                if file_format == "tar.bz2":
                    self._download_tar_bz2(url, ASR_MODEL_DIR, model_id, progress_callback)
                else:
                    self._download_zip(url, ASR_MODEL_DIR, model_id, progress_callback)
            else:
                logger.error(f"模型 {model_id} 没有 URL")

        except Exception as e:
            logger.error(f"下载 ASR 模型失败 ({model_id}): {e}")

        finally:
            self._downloading[model_id] = False

    # ==================== 翻译模型管理 ====================

    def check_translation_model(self, model_id: str = "qwen2.5-1.5b") -> bool:
        """
        检查翻译模型是否存在

        Args:
            model_id: 模型 ID

        Returns:
            模型是否存在
        """
        if model_id not in TRANSLATION_MODELS:
            logger.warning(f"未知的翻译模型: {model_id}")
            return False

        model_info = TRANSLATION_MODELS[model_id]
        model_path = TRANSLATION_MODEL_DIR / model_id

        # 检查模型文件
        required_files = [
            "config.json",
            "model.safetensors",  # 或 .bin 文件
        ]

        for file in required_files:
            # Hugging Face 模型可能使用不同命名
            if not any(model_path.glob(file.split(".")[0] + ".*")):
                # 至少要有 config
                if not (model_path / "config.json").exists():
                    return False

        return (model_path / "config.json").exists()

    def download_translation_model(
        self,
        model_id: str = "qwen2.5-1.5b",
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """
        下载翻译模型

        Args:
            model_id: 模型 ID
            progress_callback: 进度回调

        Returns:
            是否开始下载
        """
        if model_id not in TRANSLATION_MODELS:
            logger.error(f"未知的翻译模型: {model_id}")
            return False

        # 检查是否已在下载
        if model_id in self._downloading and self._downloading[model_id]:
            logger.warning(f"模型 {model_id} 正在下载中")
            return False

        # 检查是否已存在
        if self.check_translation_model(model_id):
            logger.info(f"模型 {model_id} 已存在")
            return True

        # 启动下载线程
        thread = threading.Thread(
            target=self._download_translation_model_thread,
            args=(model_id, progress_callback),
        )
        thread.daemon = True
        thread.start()

        self._download_threads[model_id] = thread
        self._downloading[model_id] = True

        return True

    def _download_translation_model_thread(
        self,
        model_id: str,
        progress_callback: Optional[Callable[[int, int], None]],
    ) -> None:
        """翻译模型下载线程"""
        try:
            model_info = TRANSLATION_MODELS[model_id]
            model_name = model_info.get("model_id")

            if model_name:
                # 从 Hugging Face 下载
                self._download_from_huggingface(
                    model_name,
                    TRANSLATION_MODEL_DIR / model_id,
                    progress_callback,
                )
            else:
                logger.error(f"模型 {model_id} 没有 model_id")

        except Exception as e:
            logger.error(f"下载翻译模型失败 ({model_id}): {e}")

        finally:
            self._downloading[model_id] = False

    # ==================== 通用下载方法 ====================

    def _download_zip(
        self,
        url: str,
        target_dir: Path,
        model_id: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """
        下载并解压 ZIP 文件

        Args:
            url: 下载 URL
            target_dir: 目标目录
            model_id: 模型 ID
            progress_callback: 进度回调

        Returns:
            是否成功
        """
        try:
            # 下载 ZIP 文件
            zip_path = target_dir / f"{model_id}.zip"

            logger.info(f"开始下载: {url}")
            self._download_file(url, zip_path, progress_callback)

            # 解压
            logger.info(f"解压文件: {zip_path}")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(target_dir)

            # 删除 ZIP 文件
            zip_path.unlink()

            logger.info(f"模型 {model_id} 下载完成")
            return True

        except Exception as e:
            logger.error(f"下载 ZIP 失败: {e}")
            return False

    def _download_tar_bz2(
        self,
        url: str,
        target_dir: Path,
        model_id: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """
        下载并解压 tar.bz2 文件

        Args:
            url: 下载 URL
            target_dir: 目标目录
            model_id: 模型 ID
            progress_callback: 进度回调

        Returns:
            是否成功
        """
        try:
            # 下载 tar.bz2 文件
            tar_path = target_dir / f"{model_id}.tar.bz2"

            logger.info(f"开始下载: {url}")
            self._download_file(url, tar_path, progress_callback)

            # 解压
            logger.info(f"解压文件: {tar_path}")
            with tarfile.open(tar_path, "r:bz2") as tf:
                # 创建模型目录
                model_path = target_dir / model_id
                model_path.mkdir(exist_ok=True)

                # 解压到模型目录
                for member in tf.getmembers():
                    # 跳过根目录，直接提取文件
                    member.name = member.name.split("/", 1)[-1] if "/" in member.name else member.name
                    if member.name:
                        tf.extract(member, model_path)

            # 删除 tar.bz2 文件
            tar_path.unlink()

            logger.info(f"模型 {model_id} 下载完成")
            return True

        except Exception as e:
            logger.error(f"下载 tar.bz2 失败: {e}")
            return False

    def _download_file(
        self,
        url: str,
        filepath: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """
        下载文件

        Args:
            url: 下载 URL
            filepath: 保存路径
            progress_callback: 进度回调 (current, total)
        """
        response = requests.get(url, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)

                    if progress_callback and total_size > 0:
                        progress_callback(downloaded, total_size)

    def _download_from_huggingface(
        self,
        model_id: str,
        target_dir: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """
        从 Hugging Face 下载模型

        Args:
            model_id: Hugging Face 模型 ID (如 "Qwen/Qwen2.5-1.5B-Instruct")
            target_dir: 目标目录
            progress_callback: 进度回调

        Returns:
            是否成功
        """
        try:
            target_dir.mkdir(parents=True, exist_ok=True)

            # 下载模型文件
            logger.info(f"从 Hugging Face 下载: {model_id}")

            # 简化版本：只下载 config.json 和模型文件
            # 实际使用时可以用 snapshot_download 下载完整模型
            from huggingface_hub import snapshot_download

            snapshot_download(
                repo_id=model_id,
                local_dir=str(target_dir),
                local_dir_use_symlinks=False,
            )

            logger.info(f"模型 {model_id} 下载完成")
            return True

        except Exception as e:
            logger.error(f"从 Hugging Face 下载失败: {e}")
            return False

    # ==================== 模型信息 ====================

    def get_model_path(self, model_type: str, model_id: str) -> Optional[Path]:
        """
        获取模型路径

        Args:
            model_type: 模型类型 ("asr" 或 "translation")
            model_id: 模型 ID

        Returns:
            模型路径
        """
        if model_type == ModelType.ASR:
            return ASR_MODEL_DIR / model_id
        elif model_type == ModelType.TRANSLATION:
            return TRANSLATION_MODEL_DIR / model_id
        return None

    def get_model_size(self, model_type: str, model_id: str) -> str:
        """
        获取模型大小

        Args:
            model_type: 模型类型
            model_id: 模型 ID

        Returns:
            模型大小描述
        """
        if model_type == ModelType.ASR:
            return ASR_MODELS.get(model_id, {}).get("size", "Unknown")
        elif model_type == ModelType.TRANSLATION:
            return TRANSLATION_MODELS.get(model_id, {}).get("size", "Unknown")
        return "Unknown"

    def is_downloading(self, model_id: str) -> bool:
        """检查模型是否正在下载"""
        return self._downloading.get(model_id, False)

    def list_models(self, model_type: str) -> List[str]:
        """
        列出指定类型的所有模型

        Args:
            model_type: 模型类型

        Returns:
            模型 ID 列表
        """
        if model_type == ModelType.ASR:
            return list(ASR_MODELS.keys())
        elif model_type == ModelType.TRANSLATION:
            return list(TRANSLATION_MODELS.keys())
        return []

    def delete_model(self, model_type: str, model_id: str) -> bool:
        """
        删除模型

        Args:
            model_type: 模型类型
            model_id: 模型 ID

        Returns:
            是否删除成功
        """
        try:
            model_path = self.get_model_path(model_type, model_id)
            if model_path and model_path.exists():
                import shutil
                shutil.rmtree(model_path)
                logger.info(f"模型 {model_id} 已删除")
                return True
            return False
        except Exception as e:
            logger.error(f"删除模型失败: {e}")
            return False


# ==================== 单例 ====================

_model_manager = None


def get_model_manager() -> ModelManager:
    """获取全局模型管理器实例"""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager


# ==================== 使用示例 ====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    manager = get_model_manager()

    # 测试 ASR 模型
    print("检查 ASR 模型:", manager.check_asr_model("qwen-asr"))

    # 测试翻译模型
    print("检查翻译模型:", manager.check_translation_model("qwen2.5-1.5b"))

    # 列出所有模型
    print("ASR 模型:", manager.list_models("asr"))
    print("翻译模型:", manager.list_models("translation"))
