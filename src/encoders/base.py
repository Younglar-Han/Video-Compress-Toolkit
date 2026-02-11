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
