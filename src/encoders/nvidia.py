from pathlib import Path
from typing import List
from .base import BaseEncoder

class NvidiaEncoder(BaseEncoder):
    @property
    def name(self) -> str:
        return "nvidia"
    
    @property
    def codec_name(self) -> str:
        return "hevc_nvenc"

    @property
    def default_quality(self) -> int:
        return 24

    @property
    def quality_step(self) -> int:
        return -1  # QP 越小质量越高

    @property
    def quality_range(self) -> tuple[int, int]:
        return (0, 51)

    def get_ffmpeg_args(
        self, 
        input_path: Path, 
        output_path: Path, 
        quality: int = 24,  # QP 值
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

        # 使用 Constant QP (CQP) 模式进行质量控制
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
