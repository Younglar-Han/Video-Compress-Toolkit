import subprocess
import time
from pathlib import Path
from typing import Optional, Callable
from src.encoders.base import BaseEncoder
from src.utils.file_ops import human_size

class Compressor:
    def __init__(self, encoder: BaseEncoder):
        self.encoder = encoder

    def compress_file(
        self, 
        input_file: Path, 
        output_file: Path, 
        **kwargs
    ) -> bool:
        """
        Compress a single file.
        Returns True if successful, False otherwise.
        """
        if not input_file.exists():
            print(f"Error: Input file {input_file} does not exist.")
            return False

        # Create output directory if it doesn't exist
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Build command
        cmd = self.encoder.get_ffmpeg_args(input_file, output_file, **kwargs)
        
        print(f"\nCompressing: {input_file.name} -> {output_file.name}")
        print(f"Encoder: {self.encoder.name}")
        # print(f"Command: {' '.join(cmd)}") # Verbose

        start_time = time.time()
        
        try:
            # Run FFmpeg
            result = subprocess.run(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                check=False
            )
            
            if result.returncode != 0:
                print(f"[FAILED] Compression failed for {input_file.name}")
                print(result.stderr.decode(errors="ignore"))
                if output_file.exists():
                    output_file.unlink()
                return False
                
            elapsed = time.time() - start_time
            src_size = input_file.stat().st_size
            dst_size = output_file.stat().st_size
            ratio = (dst_size / src_size) * 100 if src_size > 0 else 0
            
            print(f"[SUCCESS] Time: {elapsed:.2f}s | Size: {human_size(src_size)} -> {human_size(dst_size)} ({ratio:.2f}%)")
            return True

        except Exception as e:
            print(f"Error executing ffmpeg: {e}")
            return False
