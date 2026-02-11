from pathlib import Path
from typing import List, Generator

def find_videos(directory: Path, extensions: List[str] = [".mp4"], recursive: bool = False) -> List[Path]:
    """在目录中查找视频文件。"""
    directory = directory.resolve()
    if not directory.exists():
        return []
    
    files = []
    
    # 定义辅助函数检查扩展名
    def is_video(p: Path) -> bool:
        return p.is_file() and p.suffix.lower() in extensions

    if recursive:
        for p in directory.rglob("*"):
             if is_video(p):
                 files.append(p)
    else:
        for p in directory.iterdir():
            if is_video(p):
                files.append(p)
                
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
