from pathlib import Path
from typing import List, Generator

def find_videos(directory: Path, extensions: List[str] = [".mp4"], recursive: bool = False) -> List[Path]:
    """Find video files in a directory."""
    directory = directory.resolve()
    if not directory.exists():
        return []
    
    files = []
    
    # Define a helper to check extensions
    def is_video(p: Path) -> bool:
        return p.is_file() and p.suffix.lower() in extensions

    if recursive:
        for ext in extensions:
             # rglob is case sensitive on some platforms, keeping it simple or doing manual walk
             # Standard Path.rglob("*") and filter is safer
             pass
        for p in directory.rglob("*"):
             if is_video(p):
                 files.append(p)
    else:
        for p in directory.iterdir():
            if is_video(p):
                files.append(p)
                
    return sorted(files)

def human_size(size_bytes: int) -> str:
    """Convert bytes to human readable string (MB)."""
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = 0
    p = float(size_bytes)
    while p >= 1024 and i < len(size_name) - 1:
        p /= 1024
        i += 1
    return f"{p:.2f} {size_name[i]}"
