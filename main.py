#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

# 添加 src 到路径以便导入模块
sys.path.append(str(Path(__file__).parent))

from src.encoders import get_encoder
from src.core.compressor import Compressor
from src.utils.file_ops import find_videos
from src.analysis.vmaf import VMAFAnalyzer
from src.analysis.plotting import EfficiencyPlotter

DEFAULT_SIZE_LIMIT = 0.8


def _resolve_path(path_str: str) -> Path:
    return Path(path_str).expanduser().resolve()


def _should_skip(output_file: Path, force: bool) -> bool:
    if output_file.exists() and not force:
        print(f"跳过 {output_file.name} (已存在)")
        return True
    return False


def _resolve_output_for_file(input_file: Path, output_path: Path) -> Path:
    if output_path.is_dir():
        return output_path / input_file.name
    return output_path


def cmd_compress(args):
    """处理递归或单文件压缩。"""
    input_path = _resolve_path(args.input)
    output_path = _resolve_path(args.output)

    if not input_path.exists():
        print(f"错误: 输入路径不存在 {input_path}")
        return

    encoder = get_encoder(args.encoder)
    compressor = Compressor(encoder)

    kwargs = {}
    if args.quality is not None:
        kwargs["quality"] = args.quality

    max_ratio = DEFAULT_SIZE_LIMIT

    if input_path.is_dir():
        videos = find_videos(input_path, recursive=True)
        print(f"在 {input_path} 中找到 {len(videos)} 个视频")

        for vid in videos:
            rel_path = vid.relative_to(input_path)
            out_file = output_path / rel_path

            if _should_skip(out_file, args.force):
                continue

            compressor.compress_file(vid, out_file, max_ratio=max_ratio, **kwargs)
    else:
        out_file = _resolve_output_for_file(input_path, output_path)
        compressor.compress_file(input_path, out_file, max_ratio=max_ratio, **kwargs)

def cmd_batch(args):
    """批量处理带有参数范围的压缩。"""
    source_dir = _resolve_path(args.source)
    output_dir = _resolve_path(args.output)
    
    encoder = get_encoder(args.encoder)
    compressor = Compressor(encoder)
    
    videos = find_videos(source_dir, recursive=False)
    
    start = args.range_start
    end = args.range_end
    
    print(f"批量请求: {encoder.name} | 参数范围: {start}-{end}")
    
    for vid in videos:
        print(f"\n扫描: {vid.name}")
        stem = vid.stem
        
        for q in range(start, end + 1):
            # 这里的命名约定必须与 src/analysis/plotting.py 中的正则匹配保持一致
            suffix = ""
            if encoder.name == "intel":
                suffix = f"_intel_q{q}"
            elif encoder.name == "mac":
                # 检查参数是否有效（针对 macOS 编码器的重复值跳过机制）
                if not encoder.is_valid_quality(q):
                    print(f"跳过参数 {q} (已知 {encoder.name} 在此参数下产生重复结果)")
                    continue
                suffix = f"_mac_qv{q}"
            elif encoder.name == "nvidia":
                suffix = f"_nvidia_qp{q}"
            
            out_name = f"{stem}{suffix}.mp4"
            out_file = output_dir / out_name
            
            if _should_skip(out_file, args.force):
                continue
            
            kwargs = {'quality': q}

            compressor.compress_file(vid, out_file, **kwargs)

def cmd_analyze(args):
    analyzer = VMAFAnalyzer(
        ffmpeg_bin=args.ffmpeg,
        ffprobe_bin=args.ffprobe
    )
    
    ref_dir = _resolve_path(args.ref_dir)
    comp_dirs = [_resolve_path(p) for p in args.comp_dirs]
    output_csv = _resolve_path(args.output)
    
    # 收集所有压缩视频
    all_comp_videos = []
    for d in comp_dirs:
        if d.exists():
            all_comp_videos.extend(find_videos(d, recursive=True))
    
    if not all_comp_videos:
        print("未找到已压缩视频。")
        return
        
    analyzer.process_files(
        ref_dir=ref_dir,
        comp_files=all_comp_videos,
        output_csv=output_csv,
        jobs=args.jobs,
        use_neg_model=args.use_neg_model
    )

from src.core.scheduler import SmartScheduler

def cmd_smart(args):
    """处理智能压缩模式。"""
    input_path = _resolve_path(args.input)
    output_path = _resolve_path(args.output)
    
    if not input_path.exists():
        print(f"错误: 输入路径不存在 {input_path}")
        return

    encoder = get_encoder(args.encoder)
    compressor = Compressor(encoder)
    vmaf = VMAFAnalyzer()
    
    scheduler = SmartScheduler(
        compressor=compressor,
        vmaf=vmaf,
        target_vmaf=args.vmaf_target,
        size_limit=args.size_limit,
        max_analyze_workers=4
    )
    
    tasks = []

    # 如果输入是目录
    if input_path.is_dir():
        videos = find_videos(input_path, recursive=True)
        print(f"在 {input_path} 中找到 {len(videos)} 个视频")
        
        for vid in videos:
            rel_path = vid.relative_to(input_path)
            out_file = output_path / rel_path
            
            # 确保父目录存在
            out_file.parent.mkdir(parents=True, exist_ok=True)

            if _should_skip(out_file, args.force):
                continue
                
            tasks.append((vid, out_file))
            
    else:
        # 单文件
        out_file = _resolve_output_for_file(input_path, output_path)
        if _should_skip(out_file, args.force):
            return

        out_file.parent.mkdir(parents=True, exist_ok=True)
        tasks.append((input_path, out_file))

    # 启动调度器
    if tasks:
        scheduler.start(tasks)
    else:
        print("没有需要处理的任务。")

def cmd_plot(args):
    plotter = EfficiencyPlotter(
        csv_path=_resolve_path(args.csv),
        output_dir=_resolve_path(args.output_dir)
    )
    plotter.plot(sources=args.sources)

def main():
    parser = argparse.ArgumentParser(prog="VideoCompressToolkit", description="视频压缩与分析工具")
    subparsers = parser.add_subparsers(dest="command", help="要执行的命令")

    # 压缩命令
    p_compress = subparsers.add_parser("compress", help="压缩视频")
    p_compress.add_argument("input", help="输入文件或目录")
    p_compress.add_argument("output", help="输出文件或目录")
    p_compress.add_argument("--encoder", choices=["intel", "nvidia", "mac"], required=True, help="编码器")
    p_compress.add_argument("--quality", type=int, help="质量参数（QP、global_quality 等）")
    p_compress.add_argument("--force", action="store_true", help="覆盖已存在文件")
    p_compress.set_defaults(func=cmd_compress)

    # 批量命令
    p_batch = subparsers.add_parser("batch", help="批量压缩测试")
    p_batch.add_argument("--source", default="Videos", help="输入目录")
    p_batch.add_argument("--output", required=True, help="输出目录")
    p_batch.add_argument("--encoder", choices=["intel", "nvidia", "mac"], required=True)
    p_batch.add_argument("--start", dest="range_start", type=int, required=True, help="参数范围起点")
    p_batch.add_argument("--end", dest="range_end", type=int, required=True, help="参数范围终点")
    p_batch.add_argument("--force", action="store_true", help="覆盖已存在文件")
    p_batch.set_defaults(func=cmd_batch)

    # 分析命令
    p_analyze = subparsers.add_parser("analyze", help="计算 VMAF 分数")
    p_analyze.add_argument("--ref-dir", default="Videos", help="参考视频目录")
    p_analyze.add_argument("--comp-dirs", nargs="+", default=["QSV_Compressed", "NVENC_Compressed", "NVENC_QP_Compressed", "MAC_Compressed"], help="压缩视频目录")
    p_analyze.add_argument("--output", default="Results/FFMetrics.Results.csv", help="输出 CSV 文件")
    p_analyze.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg 可执行文件")
    p_analyze.add_argument("--ffprobe", default="ffprobe", help="ffprobe 可执行文件")
    p_analyze.add_argument("--jobs", type=int, default=1, help="并行任务数")
    p_analyze.add_argument("--use-neg-model", action="store_true", help="使用 VMAF NEG 模型")
    p_analyze.set_defaults(func=cmd_analyze)

    # 智能压缩命令
    p_smart = subparsers.add_parser("smart", help="智能压缩（质量/体积优化）")
    p_smart.add_argument("input", nargs="?", default="Videos", help="输入文件或目录（默认: Videos）")
    p_smart.add_argument("output", nargs="?", default="Compressed_smart", help="输出文件或目录（默认: Compressed_smart）")
    p_smart.add_argument("--encoder", choices=["intel", "nvidia", "mac"], required=True, help="编码器")
    p_smart.add_argument("--vmaf-target", type=float, default=95.0, help="目标 VMAF 分数（默认: 95）")
    p_smart.add_argument("--size-limit", type=float, default=0.8, help="最大体积比例（默认: 0.8）")
    p_smart.add_argument("--force", action="store_true", help="覆盖已存在文件")
    p_smart.set_defaults(func=cmd_smart)

    # 绘图命令
    p_plot = subparsers.add_parser("plot", help="绘制压缩效率图表")
    p_plot.add_argument("--csv", default="Results/FFMetrics.Results.csv", help="输入 CSV 文件")
    p_plot.add_argument("--output-dir", default="Results", help="图表输出目录")
    p_plot.add_argument("--sources", nargs="*", help="按源名称过滤")
    p_plot.set_defaults(func=cmd_plot)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
