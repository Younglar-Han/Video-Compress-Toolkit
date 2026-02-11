from abc import ABC, abstractmethod
from pathlib import Path
from typing import List


class BaseEncoder(ABC):
    @abstractmethod
    def get_ffmpeg_args(self, input_path: Path, output_path: Path, **kwargs) -> List[str]:
        """为特定编码器生成 ffmpeg 参数。"""
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str:
        """编码器或平台名称。"""
        raise NotImplementedError

    @property
    @abstractmethod
    def default_quality(self) -> int:
        """推荐的默认质量参数。"""
        raise NotImplementedError

    @property
    @abstractmethod
    def quality_step(self) -> int:
        """质量调整步长（正数表示增大提升质量，负数表示减小提升质量）。"""
        raise NotImplementedError

    @property
    def quality_range(self) -> tuple[int, int]:
        """质量参数的有效范围 (min, max)。"""
        return (0, 100)

    @property
    def codec_name(self) -> str:
        """FFmpeg 编解码器名称（例如 hevc_nvenc）。"""
        return ""

    def is_valid_quality(self, quality: int) -> bool:
        """检查质量参数是否有效（默认全部有效，子类可覆盖）。"""
        return True
