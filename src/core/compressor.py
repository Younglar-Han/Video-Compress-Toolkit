import subprocess
import time
import shutil
import threading
from typing import Optional
from pathlib import Path
from src.encoders.base import BaseEncoder
from src.analysis.vmaf import VMAFAnalyzer
from src.utils.file_ops import human_size


class Compressor:
    def __init__(self, encoder: BaseEncoder, gpu_semaphore: Optional[threading.Semaphore] = None):
        self.encoder = encoder
        self.gpu_semaphore = gpu_semaphore

    def _run_ffmpeg(self, cmd: list[str]) -> subprocess.CompletedProcess:
        """执行 ffmpeg 命令并返回结果。"""
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False
        )

    def _start_quality_for_smart(self) -> int:
        """根据步长方向计算智能压缩的起始质量参数。"""
        if self.encoder.quality_step > 0:
            return self.encoder.default_quality - 1
        return self.encoder.default_quality + 1

    def smart_compress_file(
        self,
        input_file: Path,
        output_file: Path,
        vmaf_analyzer: VMAFAnalyzer,
        target_vmaf: float = 95.0,
        max_size_ratio: float = 0.8
    ) -> bool:
        """
        智能压缩模式：
        1. 从推荐参数的“更低质量”起步（推荐值±1）
        2. 压缩并计算 VMAF
        3. 如果 VMAF 未达标，按步长提高质量，直到达标或触发体积限制
        """

        current_q = self._start_quality_for_smart()
        improve_step = self.encoder.quality_step
        min_q, max_q = self.encoder.quality_range

        print(f"\n[智能压缩] 开始处理: {input_file.name}")
        
        src_size = input_file.stat().st_size
        best_effort_file = None
        best_effort_score = -1.0
        
        while True:
            # 1. 范围检查
            if self.encoder.quality_step > 0:
                if current_q > max_q:
                    break
            else:
                if current_q < min_q:
                    break
                
            # 2. 有效性检查
            if not self.encoder.is_valid_quality(current_q):
                current_q += improve_step
                continue

            print(f"  > 尝试质量参数: {current_q}")
            
            # 3. 压缩
            temp_output = output_file.with_name(f"{output_file.stem}_temp_q{current_q}{output_file.suffix}")
            
            # 构建参数字典，注意这里 key 是 'quality'，encoder 内部会处理
            success = self.compress_file(input_file, temp_output, quality=current_q)
            
            if not success:
                print("    压缩失败。")
                current_q += improve_step
                continue
                
            # 4. 体积检查
            dst_size = temp_output.stat().st_size
            size_ratio = dst_size / src_size
            
            if size_ratio > max_size_ratio:
                print(f"    [停止] 体积比例 {size_ratio:.2%} > {max_size_ratio:.2%}。")
                temp_output.unlink()
                
                # 体积超标，根据需求直接使用原视频
                print("    [结果] 体积超标，使用原视频。")
                if output_file.exists():
                    output_file.unlink()
                shutil.copy2(input_file, output_file)
                
                # 清理之前的 best effort 如果有
                if best_effort_file and best_effort_file.exists():
                    best_effort_file.unlink()
                return True
                
            # 5. VMAF 检查
            score = vmaf_analyzer.calculate_vmaf(input_file, temp_output)
            if score is None:
                print("    [错误] VMAF 计算失败。")
                temp_output.unlink()
                break
                
            print(f"    结果: VMAF={score:.2f}, 体积={size_ratio:.2%}")
            
            if score >= target_vmaf:
                print(f"    [成功] 达到目标 VMAF ({score:.2f} >= {target_vmaf})")
                if output_file.exists():
                    output_file.unlink()
                temp_output.rename(output_file)
                
                if best_effort_file and best_effort_file.exists():
                    best_effort_file.unlink()
                return True
            
            # 没达到目标 VMAF，但体积合规，作为当前最佳候选
            if best_effort_file and best_effort_file.exists():
                best_effort_file.unlink()
            
            best_effort_file = output_file.with_name(f"{output_file.stem}_best_effort{output_file.suffix}")
            temp_output.rename(best_effort_file)
            best_effort_score = score
            
            # 提高质量继续尝试
            current_q += improve_step
            
            # 防止死循环（虽然有范围检查）
            if (improve_step > 0 and current_q > max_q) or (improve_step < 0 and current_q < min_q):
                print("    [停止] 达到质量参数上限。")
                # 到头了，返回最好的
                if best_effort_file and best_effort_file.exists():
                    print(f"    [结果] 达到质量上限，返回最佳候选 (VMAF {best_effort_score:.2f})")
                    if output_file.exists():
                        output_file.unlink()
                    best_effort_file.rename(output_file)
                    return True
                break

        print("  [结束] 未能在体积限制内达到目标 VMAF。")
        if best_effort_file and best_effort_file.exists():
            best_effort_file.unlink()
        return False

    def compress_file(
        self, 
        input_file: Path, 
        output_file: Path, 
        max_ratio: float = 0.8,
        **kwargs
    ) -> bool:
        """
        压缩单个文件。
        如果成功返回 True，否则返回 False。
        :param max_ratio: 如果设置 (0.0-1.0)，当压缩后体积 > 原体积 * max_ratio 时，放弃压缩，直接使用原视频。
        """
        if not input_file.exists():
            print(f"错误: 输入文件不存在 {input_file}")
            return False

        # 如果输出目录不存在则创建
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 构建命令
        cmd = self.encoder.get_ffmpeg_args(input_file, output_file, **kwargs)
        
        print(f"\n开始压缩: {input_file.name} -> {output_file.name}")
        print(f"编码器: {self.encoder.name}")

        start_time = time.time()
        
        try:
            if self.gpu_semaphore:
                with self.gpu_semaphore:
                    result = self._run_ffmpeg(cmd)
            else:
                result = self._run_ffmpeg(cmd)
            
            if result.returncode != 0:
                print("")
                print(f"[失败] 压缩失败: {input_file.name}")
                print(result.stderr.decode(errors="ignore"))
                if output_file.exists():
                    output_file.unlink()
                return False
                
            elapsed = time.time() - start_time
            src_size = input_file.stat().st_size
            dst_size = output_file.stat().st_size
            ratio = dst_size / src_size if src_size > 0 else 0
            ratio_percent = ratio * 100
            
            print("")
            print(f"[成功] 用时: {elapsed:.2f}s | 体积: {human_size(src_size)} -> {human_size(dst_size)} ({ratio_percent:.2f}%)")
            
            # 检查体积限制
            if max_ratio is not None and ratio > max_ratio:
                print(f"    [体积限制] 比例 {ratio_percent:.2f}% > {max_ratio*100}%，回退到原视频。")
                if output_file.exists():
                    output_file.unlink()
                shutil.copy2(input_file, output_file)
            
            return True

        except Exception as e:
            print(f"执行 ffmpeg 出错: {e}")
            return False
