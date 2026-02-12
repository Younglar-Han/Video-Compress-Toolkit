from pathlib import Path
from typing import List
from .base import BaseEncoder


class MacEncoder(BaseEncoder):
    # 基于实测（Apple Silicon + VideoToolbox）确认的“重复输出参数”。
    # 这些 q:v 在当前环境下会产生与相邻参数相同的结果，适合直接跳过。
    _KNOWN_DUPLICATE_QUALITIES = {
        3, 4, 6, 7, 9, 10, 12, 13, 15, 16,
        18, 20, 21, 23, 24, 26, 27, 29, 31, 32,
        34, 35, 37, 39, 40,
        42, 44, 45, 47, 49, 50,
        52, 54, 56, 58, 59, 61, 63, 65, 67, 69,
        71, 73, 75, 77, 80, 82, 85,
    }

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
        return 1  # q:v 越大质量越高

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
        某些参数会得到重复输出。

        当前策略：
        - 对已实测确认的重复参数直接返回 False（跳过）。
        - 其他参数默认返回 True，避免在未测区间过度假设。
        """
        if quality in self._KNOWN_DUPLICATE_QUALITIES:
            return False

        # 对于尚未测量的范围，默认返回 True（不做假设）
        return True
