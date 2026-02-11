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

    @property
    def default_quality(self) -> int:
        return 58

    @property
    def quality_step(self) -> int:
        return 1 # Higher is better for q:v

    @property
    def quality_range(self) -> tuple[int, int]:
        return (1, 100)

    def get_ffmpeg_args(self, input_path: Path, output_path: Path, quality: int = 58, **kwargs) -> List[str]:
        # macOS VideoToolbox 模式
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

    def is_valid_quality(self, quality: int) -> bool:
        """
        macOS VideoToolbox 编码器的 'q:v' 参数不是线性的，
        并且某些值的输出结果是完全相同的（重复）。
        根据观察（在 Apple Silicon 上），以下范围内的有效值步骤如下：
        
        Range 50-70:
        50, 51, 53, 55, 57, 60, 62, 64, 66, 68, 70
        """
        # 已知不重复的“有效”值集合
        # 50 到 51 (step 1)
        # 51 到 57 (step 2: 51, 53, 55, 57)
        # 57 到 60 (gap 3)
        # 60 到 70 (step 2: 60, 62, 64, 66, 68, 70)
        
        if 50 <= quality <= 70:
            if quality == 50: return True
            if 51 <= quality <= 57: return quality % 2 == 1  # 51, 53, 55, 57
            if 58 <= quality <= 59: return False             # 58, 59 are dupes of 57
            if 60 <= quality <= 70: return quality % 2 == 0  # 60, 62, ... 70
        
        # 对于尚未测量的范围，默认返回 True (不做假设)
        return True
