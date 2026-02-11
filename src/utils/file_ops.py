from pathlib import Path
from typing import List, Optional


def find_videos(directory: Path, extensions: Optional[List[str]] = None, recursive: bool = False) -> List[Path]:
    """在目录中查找视频文件，按路径排序后返回。"""
    directory = directory.resolve()
    if not directory.exists():
        return []

    if extensions is None:
        extensions = [".mp4"]

    files: List[Path] = []

    def is_video(path_item: Path) -> bool:
        return path_item.is_file() and path_item.suffix.lower() in extensions

    if recursive:
        for path_item in directory.rglob("*"):
            if is_video(path_item):
                files.append(path_item)
    else:
        for path_item in directory.iterdir():
            if is_video(path_item):
                files.append(path_item)

    return sorted(files)

def human_size(size_bytes: int) -> str:
    """将字节转换为人类可读的字符串 (MB)。"""
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = 0
    p = float(size_bytes)
    while p >= 1024 and i < len(size_name) - 1:
        p /= 1024
        i += 1
    return f"{p:.2f} {size_name[i]}"
