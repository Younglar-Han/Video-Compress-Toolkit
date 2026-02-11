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
