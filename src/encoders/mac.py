from pathlib import Path
from typing import List
from .base import BaseEncoder

class MacEncoder(BaseEncoder):
    @property
    def name(self) -> str:
        return "mac"
    
    @property
    def codec_name(self) -> str:
        return "hevc_videotoolbox"

    def get_ffmpeg_args(self, input_path: Path, output_path: Path, quality: int = 58, **kwargs) -> List[str]:
        # macOS VideoToolbox mode
        return [
            "ffmpeg",
            "-hwaccel", "videotoolbox",
            "-i", str(input_path),
            "-c:v", self.codec_name,
            "-vtag", "hvc1",
            "-q:v", str(quality),
            "-c:a", "copy",
            "-map_metadata", "0",
            "-y",
            str(output_path),
        ]
