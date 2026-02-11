import subprocess
import csv
import re
from pathlib import Path
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

class VMAFAnalyzer:
    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe"):
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin
        self._check_vmaf_support()

    def _check_vmaf_support(self):
        """检查 FFmpeg 是否支持 libvmaf。"""
        try:
            cmd = [self.ffmpeg_bin, "-filters"]
            result = subprocess.run(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                encoding="utf-8", 
                errors="ignore",
                check=False
            )
            # 在滤镜列表中查找 libvmaf
            if "libvmaf" not in result.stdout:
                print("=================================================================")
                print(f"警告: 检测到当前的 FFmpeg ('{self.ffmpeg_bin}') 不支持 'libvmaf'。")
                print("VMAF 计算将会失败。")
                print("请安装支持 VMAF 的版本，例如使用 Homebrew:")
                print("  brew install ffmpeg-full")
                print("如果你已经安装了 ffmpeg-full，请确保它在你的 PATH 中。")
                print("=================================================================")
        except FileNotFoundError:
             print(f"Error: 找不到 FFmpeg 二进制文件 '{self.ffmpeg_bin}'。")
        except Exception as e:
             print(f"Warning: 无法验证 VMAF 支持: {e}")

    def get_bitrate(self, file_path: Path) -> Optional[float]:
        """使用 ffprobe 获取视频比特率（kbps）。"""
        try:
            cmd = [
                self.ffprobe_bin,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "format=bit_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ]
            output = subprocess.check_output(cmd).decode().strip()
            if not output or output == "N/A":
                return None
            return float(output) / 1000.0  # bits -> kbps
        except Exception:
            return None

    def calculate_vmaf(
        self, 
        ref_file: Path, 
        main_file: Path, 
        use_neg_model: bool = False
    ) -> Optional[float]:
        """计算 VMAF 分数。"""
        
        # 构建 VMAF 模型字符串
        model_str = "version=vmaf_v0.6.1neg" if use_neg_model else "version=vmaf_v0.6.1"
        
        # 简单的滤镜复合
        # [0:v] 是参考视频，[1:v] 是失真视频
        filter_complex = f"[1:v][0:v]libvmaf=model={model_str}:n_threads=4"

        cmd = [
            self.ffmpeg_bin,
            "-i", str(ref_file),
            "-i", str(main_file),
            "-filter_complex", filter_complex,
            "-f", "null",
            "-"
        ]

        try:
            result = subprocess.run(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                encoding="utf-8",
                errors="ignore"
            )
            
            # 解析 VMAF 分数输出
            # 寻找: "VMAF score: 95.123456"
            lines = result.stderr.splitlines()
            for line in reversed(lines):
                if "VMAF score" in line:
                    match = re.search(r"VMAF score[:=]\s*([0-9.]+)", line)
                    if match:
                        return float(match.group(1))
            
            return None
        except Exception as e:
            print(f"Error calculating VMAF for {main_file.name}: {e}")
            return None

    def process_files(
        self, 
        ref_dir: Path, 
        comp_files: List[Path], 
        output_csv: Path,
        jobs: int = 1,
        use_neg_model: bool = False
    ):
        """批量处理 VMAF 计算。"""
        
        results = []
        
        # 确保输出目录存在
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        
        # 准备任务列表
        tasks = []
        
        print(f"Starting VMAF analysis for {len(comp_files)} files...")
        
        with ThreadPoolExecutor(max_workers=jobs) as executor:
            future_to_file = {}
            for comp_file in comp_files:
                # 尝试根据文件名寻找参考文件
                # 逻辑：去除已知的压缩后缀，然后在参考目录中查找同名文件（忽略扩展名）
                
                stem = comp_file.stem
                
                # 匹配常见的压缩后缀模式
                # 支持：intel_q*, nvidia_qp*, nvidia_qmax* (legacy), mac_qv*
                param_pattern = re.compile(
                    r"_(intel_q\d+|nvidia_qmax\d+|nvidia_qp\d+(_aq)?|mac_qv\d+)$"
                )
                
                clean_stem = param_pattern.sub("", stem)
                
                ref_file = None
                # 在 ref_dir 中查找具有相同 stem 的视频文件
                # 优先匹配 .mp4，但也支持其他常见格式
                for ext in [".mp4", ".mkv", ".mov", ".avi"]:
                    candidate = ref_dir / f"{clean_stem}{ext}"
                    if candidate.exists():
                        ref_file = candidate
                        break
                
                if not ref_file:
                    print(f"Warning: Reference file not found for {comp_file.name} (Expected {clean_stem}.[mp4|mkv|...])")
                    continue
                
                future = executor.submit(self._analyze_single, ref_file, comp_file, use_neg_model)
                future_to_file[future] = comp_file
                
            # 收集结果
            completed_count = 0
            for future in as_completed(future_to_file):
                comp_file = future_to_file[future]
                try:
                    res = future.result()
                    if res:
                        results.append(res)
                        completed_count += 1
                        print(f"[{completed_count}/{len(future_to_file)}] Finished {comp_file.name}")
                except Exception as exc:
                    print(f"Task generated an exception: {exc}")

        # 写入 CSV
        # 格式: FileSpec, VMAF, Bitrate
        # 匹配原始格式以兼容绘图脚本
        with open(output_csv, "w", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(["FileSpec", "VMAF-Value", "Bitrate"])
            
            for r in results:
                writer.writerow(r)
                
        print(f"Analysis complete. Results saved to {output_csv}")

    def _analyze_single(self, ref_file: Path, comp_file: Path, use_neg_model: bool):
        vmaf = self.calculate_vmaf(ref_file, comp_file, use_neg_model)
        bitrate = self.get_bitrate(comp_file)
        
        if vmaf is not None and bitrate is not None:
            # 我们返回与绘图脚本兼容的输出
            # 绘图脚本需要 'FileSpec'，实际上就是文件名
            return [comp_file.name, vmaf, bitrate]
        return None
