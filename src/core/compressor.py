import subprocess
import time
import shutil
import threading
from typing import Optional, TYPE_CHECKING
from pathlib import Path
from src.encoders.base import BaseEncoder
from src.utils.console import error, info, success, warn
from src.utils.file_ops import human_size

if TYPE_CHECKING:
    from src.analysis.vmaf import VMAFAnalyzer


class Compressor:
    def __init__(self, encoder: BaseEncoder, gpu_semaphore: Optional[threading.Semaphore] = None):
        self.encoder = encoder
        self.gpu_semaphore = gpu_semaphore
        self._process_lock = threading.Lock()
        self._running_processes: set[subprocess.Popen[bytes]] = set()

    def _run_ffmpeg(self, cmd: list[str]) -> subprocess.CompletedProcess:
        """执行 ffmpeg 命令并返回结果。"""
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        with self._process_lock:
            self._running_processes.add(proc)

        try:
            stdout, stderr = proc.communicate()
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=proc.returncode,
                stdout=stdout,
                stderr=stderr,
            )
        finally:
            with self._process_lock:
                self._running_processes.discard(proc)

    def terminate_running_processes(self, grace_timeout: float = 2.0) -> int:
        """终止当前所有运行中的 ffmpeg 子进程，返回处理数量。"""

        with self._process_lock:
            processes = list(self._running_processes)

        if not processes:
            return 0

        for proc in processes:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    continue

        deadline = time.monotonic() + grace_timeout
        for proc in processes:
            if proc.poll() is not None:
                continue
            remain = max(0.0, deadline - time.monotonic())
            try:
                proc.wait(timeout=remain)
            except Exception:
                if proc.poll() is None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    try:
                        proc.wait(timeout=1.0)
                    except Exception:
                        pass

        return len(processes)

    def _should_direct_copy(self, input_file: Path) -> bool:
        """判断当前输入是否应直接复制而非压缩。"""

        return input_file.suffix.lower() in {".jpg", ".jpeg"}

    def smart_compress_file(
        self,
        input_file: Path,
        output_file: Path,
        vmaf_analyzer: "VMAFAnalyzer",
        target_vmaf: float = 95.0,
        max_size_ratio: float = 0.8,
    ) -> bool:
        """智能压缩（兼容旧接口）。

        该方法保留是为了兼容可能的外部调用；核心策略统一由 `SmartScheduler` 负责，
        避免出现两套实现产生行为偏差。
        """

        # 延迟导入以避免与 scheduler 的循环依赖
        from src.core.scheduler import SmartScheduler

        scheduler = SmartScheduler(
            compressor=self,
            vmaf=vmaf_analyzer,
            target_vmaf=target_vmaf,
            size_limit=max_size_ratio,
            max_analyze_workers=1,
        )
        scheduler.start([(input_file, output_file)])
        return output_file.exists()

    def compress_file(
        self, 
        input_file: Path, 
        output_file: Path, 
        max_ratio: Optional[float] = 0.8,
        verbose: bool = True,
        **kwargs
    ) -> bool:
        """
        压缩单个文件。
        如果成功返回 True，否则返回 False。
        :param max_ratio: 如果设置为 (0.0-1.0)，当压缩后体积 > 原体积 * max_ratio 时，放弃压缩，直接使用原视频；传 None 表示禁用该回退。
        """
        if not input_file.exists():
            error(f"输入文件不存在 {input_file}")
            return False

        # 如果输出目录不存在则创建
        output_file.parent.mkdir(parents=True, exist_ok=True)

        if self._should_direct_copy(input_file):
            try:
                if output_file.exists():
                    output_file.unlink()
                shutil.copy2(input_file, output_file)
                if verbose:
                    info(f"检测到 JPG，直接复制: {input_file.name} -> {output_file.name}", leading_blank=True)
                return True
            except Exception as exc:
                if verbose:
                    error(f"JPG 直接复制失败: {exc}")
                return False
        
        # 构建命令
        cmd = self.encoder.get_ffmpeg_args(input_file, output_file, **kwargs)

        if verbose:
            info(f"开始压缩: {input_file.name} -> {output_file.name}", leading_blank=True)
            info(f"编码器: {self.encoder.name}")

        start_time = time.time()
        
        try:
            if self.gpu_semaphore:
                with self.gpu_semaphore:
                    result = self._run_ffmpeg(cmd)
            else:
                result = self._run_ffmpeg(cmd)
            
            if result.returncode != 0:
                if verbose:
                    error(f"压缩失败: {input_file.name}", leading_blank=True)
                    error(result.stderr.decode(errors="ignore"))
                if output_file.exists():
                    output_file.unlink()
                return False
                
            elapsed = time.time() - start_time
            src_size = input_file.stat().st_size
            dst_size = output_file.stat().st_size
            ratio = dst_size / src_size if src_size > 0 else 0
            ratio_percent = ratio * 100
            
            if verbose:
                success(
                    f"用时: {elapsed:.2f}s | 体积: {human_size(src_size)} -> {human_size(dst_size)} ({ratio_percent:.2f}%)",
                    leading_blank=True,
                )
            
            # 检查体积限制
            if max_ratio is not None and ratio > max_ratio:
                if verbose:
                    warn(f"体积限制触发: 比例 {ratio_percent:.2f}% > {max_ratio*100}%，回退到原视频。")
                if output_file.exists():
                    output_file.unlink()
                shutil.copy2(input_file, output_file)
            
            return True

        except Exception as e:
            if output_file.exists():
                try:
                    output_file.unlink()
                except Exception:
                    pass
            if verbose:
                error(f"执行 ffmpeg 出错: {e}")
            return False
