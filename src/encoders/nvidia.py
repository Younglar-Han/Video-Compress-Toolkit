from pathlib import Path
from typing import List, Optional
from .base import BaseEncoder

class NvidiaEncoder(BaseEncoder):
    @property
    def name(self) -> str:
        return "nvidia"
    
    @property
    def codec_name(self) -> str:
        return "hevc_nvenc"

    def get_ffmpeg_args(
        self, 
        input_path: Path, 
        output_path: Path, 
        quality: int = 24, # This is the QP value
        **kwargs
    ) -> List[str]:
        
        cmd = [
            "ffmpeg",
            "-i", str(input_path),
            "-c:v", self.codec_name,
            "-vtag", "hvc1",
            "-preset", "p7",
            "-multipass", "fullres",
        ]

        # Always use constqp mode
        # "qmax" mode was removed because it's ineffective for quality control
        # AQ modes were removed because they often degrade quality/size ratio
        cmd.extend([
            "-rc", "constqp",
            "-qp", str(quality)
        ])
        
        cmd.extend([
            "-c:a", "copy",
            "-map_metadata", "0",
            "-y",
            str(output_path)
        ])
        
        return cmd
