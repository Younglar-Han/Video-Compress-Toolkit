import subprocess
import csv
import re
from pathlib import Path
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

from src.utils.console import error, info, phase_start, progress, success, warn
from src.utils.naming import strip_param_suffix

class VMAFAnalyzer:
    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe"):
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin
        self._check_vmaf_support()

    @lru_cache(maxsize=1024)
    def _get_resolution_cached(self, file_path_str: str) -> Optional[tuple[int, int]]:
        """使用 ffprobe 获取视频分辨率（宽, 高），带缓存以减少重复探测。"""

        try:
            cmd = [
                self.ffprobe_bin,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0:s=x",
                file_path_str,
            ]
            output = subprocess.check_output(cmd).decode().strip()
            match = re.match(r"^(\d+)x(\d+)$", output)
            if not match:
                return None
            return int(match.group(1)), int(match.group(2))
        except Exception:
            return None

    def get_resolution(self, file_path: Path) -> Optional[tuple[int, int]]:
        """获取视频分辨率（宽, 高）。"""

        return self._get_resolution_cached(str(file_path))

    def _should_use_4k_model(self, file_path: Path) -> bool:
        """判断是否应该使用 4K VMAF 模型。

        规则：当分辨率像素总数 >= 3840*2160（UHD 4K）时，视为“等于或高于 4K”。
        """

        res = self.get_resolution(file_path)
        if not res:
            return False
        width, height = res
        return (width * height) >= (3840 * 2160)

    def _build_vmaf_model_str(self, ref_file: Path, use_neg_model: bool) -> str:
        """根据参考视频分辨率构建 VMAF 模型字符串。"""

        base_model = "vmaf_4k_v0.6.1" if self._should_use_4k_model(ref_file) else "vmaf_v0.6.1"
        if use_neg_model:
            base_model = f"{base_model}neg"
        return f"version={base_model}"

    def get_vmaf_model_str(self, ref_file: Path, use_neg_model: bool = False) -> str:
        """获取当前视频将使用的 VMAF 模型字符串（用于日志或外部调用）。"""

        return self._build_vmaf_model_str(ref_file, use_neg_model)

    def get_vmaf_model_selection(
        self, ref_file: Path, use_neg_model: bool = False
    ) -> tuple[Optional[tuple[int, int]], str]:
        """统一接口：获取参考视频分辨率与将使用的 VMAF 模型字符串。"""

        resolution = self.get_resolution(ref_file)
        model_str = self._build_vmaf_model_str(ref_file, use_neg_model)
        return resolution, model_str

    def format_resolution_for_log(
        self,
        resolution: Optional[tuple[int, int]],
        mode: str = "paren",
    ) -> str:
        """统一格式化分辨率日志片段。

        - mode="paren": 返回 "(3840x2160)" 或 "(分辨率未知)"
        - mode="kv": 返回 "参考分辨率=3840x2160" 或 "参考分辨率未知"
        """

        if resolution:
            width, height = resolution
            if mode == "kv":
                return f"参考分辨率={width}x{height}"
            return f"({width}x{height})"

        if mode == "kv":
            return "参考分辨率未知"
        return "(分辨率未知)"

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
                warn(f"检测到当前的 FFmpeg ('{self.ffmpeg_bin}') 不支持 'libvmaf'。", leading_blank=True)
                warn("VMAF 计算将会失败。")
                warn("请安装支持 VMAF 的版本，例如使用 Homebrew: brew install ffmpeg-full")
                warn("如果你已经安装了 ffmpeg-full，请确保它在 PATH 中。")
        except FileNotFoundError:
            error(f"找不到 FFmpeg 二进制文件 '{self.ffmpeg_bin}'。")
        except Exception as e:
            warn(f"无法验证 VMAF 支持: {e}")

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
            return float(output) / 1000.0  # bit 转 kbps
        except Exception:
            return None

    def calculate_vmaf(
        self, 
        ref_file: Path, 
        main_file: Path, 
        use_neg_model: bool = False
    ) -> Optional[float]:
        """计算 VMAF 分数。"""

        # 根据分辨率自动选择模型：低于 4K 用默认模型，等于或高于 4K 用 4K 模型
        # 优先以参考视频分辨率为准；探测失败则回退默认模型
        model_str = self._build_vmaf_model_str(ref_file, use_neg_model)
        
        # libvmaf 期望输入顺序为 [distorted][reference]
        # 这里 distorted=压缩视频(main_file)，reference=原视频(ref_file)
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
            lines = result.stderr.splitlines()
            for line in reversed(lines):
                if "VMAF score" in line:
                    match = re.search(r"VMAF score[:=]\s*([0-9.]+)", line)
                    if match:
                        return float(match.group(1))
            
            return None
        except Exception as e:
            warn(f"计算 VMAF 失败: {main_file.name} | {e}")
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

        phase_start("批量分析", f"开始 VMAF 分析，共 {len(comp_files)} 个文件")

        # 建立参考视频索引：stem -> Path（按扩展名优先级选择）
        ref_index: dict[str, Path] = {}
        preferred_exts = [".mp4", ".mkv", ".mov", ".avi"]
        if ref_dir.exists():
            for ext in preferred_exts:
                for p in ref_dir.glob(f"*{ext}"):
                    if p.is_file() and p.stem not in ref_index:
                        ref_index[p.stem] = p
        
        with ThreadPoolExecutor(max_workers=jobs) as executor:
            future_to_file = {}
            for comp_file in comp_files:
                # 通过文件名寻找参考文件：去除压缩后缀后再匹配
                clean_stem = strip_param_suffix(comp_file.stem)
                ref_file = ref_index.get(clean_stem)

                if not ref_file:
                    warn(f"未找到参考视频 {comp_file.name} (期望 {clean_stem}.[mp4|mkv|...])")
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
                        progress(completed_count, len(future_to_file), f"完成 {comp_file.name}")
                except Exception as exc:
                    warn(f"任务异常: {exc}")

        # 写入 CSV（保持绘图脚本兼容格式）
        with open(output_csv, "w", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(["FileSpec", "VMAF-Value", "Bitrate"])
            
            for r in results:
                writer.writerow(r)
                
        success(f"分析完成，结果已保存到 {output_csv}", leading_blank=True)

    def _analyze_single(self, ref_file: Path, comp_file: Path, use_neg_model: bool):
        resolution, model_str = self.get_vmaf_model_selection(ref_file, use_neg_model)

        res_part = self.format_resolution_for_log(resolution, mode="paren")
        phase_start(comp_file.name, f"开始 VMAF: 参考={ref_file.name} {res_part} | 模型={model_str}")

        vmaf = self.calculate_vmaf(ref_file, comp_file, use_neg_model)
        bitrate = self.get_bitrate(comp_file)
        
        if vmaf is not None and bitrate is not None:
            # 与绘图脚本兼容的输出格式
            return [comp_file.name, vmaf, bitrate]
        return None
