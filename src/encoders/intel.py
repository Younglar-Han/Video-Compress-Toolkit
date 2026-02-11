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

    def get_ffmpeg_args(self, input_path: Path, output_path: Path, quality: int = 21, **kwargs) -> List[str]:
        # Intel QSV mode
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
