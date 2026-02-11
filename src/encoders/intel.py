from pathlib import Path
from typing import List
from .base import BaseEncoder

class IntelEncoder(BaseEncoder):
    @property
    def name(self) -> str:
        return "intel"
    
    @property
    def codec_name(self) -> str:
        return "hevc_qsv"

    @property
    def default_quality(self) -> int:
        return 25

    @property
    def quality_step(self) -> int:
        return -1  # global_quality 越小质量越高

    @property
    def quality_range(self) -> tuple[int, int]:
        return (1, 51)

    def get_ffmpeg_args(self, input_path: Path, output_path: Path, quality: int = 21, **kwargs) -> List[str]:
        # Intel QSV 模式
        return [
            "ffmpeg",
            "-hwaccel", "qsv",
            "-hwaccel_output_format", "qsv",
            "-i", str(input_path),
            "-c:v", self.codec_name,
            "-vtag", "hvc1",
            "-preset", "veryslow",
            "-global_quality", str(quality),
            "-c:a", "copy",
            "-map_metadata", "0",
            "-y",
            str(output_path),
        ]
