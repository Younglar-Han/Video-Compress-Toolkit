import subprocess
import time
import shutil
from pathlib import Path
from src.encoders.base import BaseEncoder
from src.analysis.vmaf import VMAFAnalyzer
from src.utils.file_ops import human_size

class Compressor:
    def __init__(self, encoder: BaseEncoder):
        self.encoder = encoder

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
        1. 从推荐参数-1开始
        2. 压缩并计算 VMAF
        3. 如果 VMAF < 95，提高质量（q += step），直到 VMAF >= 95 或 体积 > 80% 原视频
        """
        
        # 初始质量参数：推荐值
        current_q = self.encoder.default_quality
        
        improve_step = self.encoder.quality_step
        # 验证步长方向：
        # Mac: step=1. q increases -> Quality increases.
        # Nvidia: step=-1. q decreases -> Quality increases.
        
        min_q, max_q = self.encoder.quality_range
        
        print(f"\n[Smart Compress] Start processing: {input_file.name}")
        
        src_size = input_file.stat().st_size
        best_effort_file = None
        best_effort_score = -1.0
        
        while True:
            # 1. 范围检查
            if self.encoder.quality_step > 0: # Increasing q
                if current_q > max_q: break
            else: # Decreasing q
                if current_q < min_q: break
                
            # 2. 有效性检查
            if not self.encoder.is_valid_quality(current_q):
                current_q += improve_step
                continue

            print(f"  > Attempting Quality: {current_q}")
            
            # 3. 压缩
            temp_output = output_file.with_name(f"{output_file.stem}_temp_q{current_q}{output_file.suffix}")
            
            # 构建参数字典，注意这里 key 是 'quality'，encoder 内部会处理
            success = self.compress_file(input_file, temp_output, quality=current_q)
            
            if not success:
                print("    Compression failed.")
                current_q += improve_step
                continue
                
            # 4. 体积检查
            dst_size = temp_output.stat().st_size
            size_ratio = dst_size / src_size
            
            if size_ratio > max_size_ratio:
                print(f"    [Stop] Size ratio {size_ratio:.2%} > {max_size_ratio:.2%}. Stopping.")
                temp_output.unlink()
                
                # 体积超标，根据需求直接使用原视频
                print("    [Result] Compression not efficient enough (size > 80%). Using original video.")
                if output_file.exists(): output_file.unlink()
                # 使用 shutil.copy2 复制原文件
                shutil.copy2(input_file, output_file)
                
                # 清理之前的 best effort 如果有
                if best_effort_file and best_effort_file.exists():
                    best_effort_file.unlink()
                return True
                
            # 5. VMAF 检查
            score = vmaf_analyzer.calculate_vmaf(input_file, temp_output)
            if score is None:
                print("    [Error] VMAF failed.")
                temp_output.unlink()
                break
                
            print(f"    Result: VMAF={score:.2f}, Size={size_ratio:.2%}")
            
            if score >= target_vmaf:
                print(f"    [Success] Target VMAF reached! ({score:.2f} >= {target_vmaf})")
                if output_file.exists():
                    output_file.unlink()
                temp_output.rename(output_file)
                
                if best_effort_file and best_effort_file.exists():
                    best_effort_file.unlink()
                return True
            
            # 没达到目标 VMAF，但体积合规。
            # 这是目前为止最好的合规结果（因为我们在不断提高质量）
            # 保存为备选 'best_effort'
            if best_effort_file and best_effort_file.exists():
                best_effort_file.unlink()
            
            best_effort_file = output_file.with_name(f"{output_file.stem}_best_effort{output_file.suffix}")
            temp_output.rename(best_effort_file)
            best_effort_score = score
            
            # 提高质量继续尝试
            current_q += improve_step
            
            # 防止死循环（虽然有范围检查）
            if (improve_step > 0 and current_q > max_q) or (improve_step < 0 and current_q < min_q):
                print("    [Stop] Reached quality parameter limit.")
                # 到头了，返回最好的
                if best_effort_file and best_effort_file.exists():
                     print(f"    [Result] Reached max quality. Returning best effort result (VMAF {best_effort_score:.2f})")
                     if output_file.exists(): output_file.unlink()
                     best_effort_file.rename(output_file)
                     return True
                break

        print("  [Finished] Unable to meet VMAF target within size limit.")
        if best_effort_file and best_effort_file.exists():
            best_effort_file.unlink()
        return False

    def compress_file(
        self, 
        input_file: Path, 
        output_file: Path, 
        max_ratio: float = None,
        **kwargs
    ) -> bool:
        """
        压缩单个文件。
        如果成功返回 True，否则返回 False。
        :param max_ratio: 如果设置 (0.0-1.0)，当压缩后体积 > 原体积 * max_ratio 时，放弃压缩，直接使用原视频。
        """
        if not input_file.exists():
            print(f"Error: Input file {input_file} does not exist.")
            return False

        # 如果输出目录不存在则创建
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 构建命令
        cmd = self.encoder.get_ffmpeg_args(input_file, output_file, **kwargs)
        
        print(f"\nCompressing: {input_file.name} -> {output_file.name}")
        print(f"Encoder: {self.encoder.name}")

        start_time = time.time()
        
        try:
            # 运行 FFmpeg
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
            ratio = dst_size / src_size if src_size > 0 else 0
            ratio_percent = ratio * 100
            
            print(f"[SUCCESS] Time: {elapsed:.2f}s | Size: {human_size(src_size)} -> {human_size(dst_size)} ({ratio_percent:.2f}%)")
            
            # 检查体积限制
            if max_ratio is not None and ratio > max_ratio:
                 print(f"    [Size Limit] Ratio {ratio_percent:.2f}% > {max_ratio*100}%. Reverting to original video.")
                 if output_file.exists(): output_file.unlink()
                 shutil.copy2(input_file, output_file)
            
            return True

        except Exception as e:
            print(f"Error executing ffmpeg: {e}")
            return False
