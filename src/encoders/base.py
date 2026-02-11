from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any, Optional

class BaseEncoder(ABC):
    @abstractmethod
    def get_ffmpeg_args(self, input_path: Path, output_path: Path, **kwargs) -> List[str]:
        """为特定编码器生成 ffmpeg 参数。"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """编码器/平台名称。"""
        pass

    @property
    @abstractmethod
    def default_quality(self) -> int:
        """推荐的默认质量参数。"""
        pass

    @property
    @abstractmethod
    def quality_step(self) -> int:
        """
        质量调整步长。
        正数表示增加该值会提高质量（例如 bitrate, q:v）。
        负数表示减少该值会提高质量（例如 CRF, QP, global_quality）。
        """
        pass
    
    @property
    def quality_range(self) -> tuple[int, int]:
        """质量参数的有效范围 (min, max)。"""
        return (0, 100)

    @property
    def codec_name(self) -> str:
        """FFmpeg 编解码器名称（例如 hevc_nvenc）。"""
        return "" 

    def is_valid_quality(self, quality: int) -> bool:
        """
        检查给定的质量参数是否能产生有效（非重复）的结果。
        默认情况下，所有质量值都被视为有效。
        子类可以重写此方法以通过跳过冗余值（例如，在 macOS VideoToolbox 上）来优化批处理。
        """
        return True 
