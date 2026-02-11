from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any, Optional

class BaseEncoder(ABC):
    @abstractmethod
    def get_ffmpeg_args(self, input_path: Path, output_path: Path, **kwargs) -> List[str]:
        """Generate ffmpeg arguments for the specific encoder."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the encoder/platform."""
        pass

    @property
    def codec_name(self) -> str:
        """The ffmpeg codec name (e.g., hevc_nvenc)."""
        return "" 
