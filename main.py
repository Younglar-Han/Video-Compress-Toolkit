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

def cmd_compress(args):
    """处理递归或单文件压缩。"""
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    
    if not input_path.exists():
        print(f"Error: Input {input_path} does not exist.")
        return

    encoder = get_encoder(args.encoder)
    compressor = Compressor(encoder)
    
    # 准备参数
    kwargs = {}
    if args.quality:
        kwargs['quality'] = args.quality
        
    # 如果输入是目录则使用递归模式
    if input_path.is_dir():
        videos = find_videos(input_path, recursive=True)
        print(f"Found {len(videos)} videos in {input_path}")
        
        for vid in videos:
            # 在输出中复制目录结构
            rel_path = vid.relative_to(input_path)
            out_file = output_path / rel_path
            
            # 如果存在则跳过
            if out_file.exists() and not args.force:
                print(f"Skipping {out_file.name} (exists)")
                continue
                
            compressor.compress_file(vid, out_file, **kwargs)
    else:
        # 单个文件
        if output_path.is_dir():
            output_path = output_path / input_path.name
        
        compressor.compress_file(input_path, output_path, **kwargs)

def cmd_batch(args):
    """批量处理带有参数范围的压缩。"""
    source_dir = Path(args.source).resolve()
    output_dir = Path(args.output).resolve()
    
    encoder = get_encoder(args.encoder)
    compressor = Compressor(encoder)
    
    videos = find_videos(source_dir, recursive=False)
    
    start = args.range_start
    end = args.range_end
    
    print(f"Batch Request: {encoder.name} | Range: {start}-{end}")
    
    for vid in videos:
        print(f"\nScanning: {vid.name}")
        stem = vid.stem
        
        for q in range(start, end + 1):
            # 这里的命名约定必须与 src/analysis/plotting.py 中的正则匹配保持一致
            suffix = ""
            if encoder.name == "intel":
                suffix = f"_intel_q{q}"
            elif encoder.name == "mac":
                suffix = f"_mac_qv{q}"
            elif encoder.name == "nvidia":
                suffix = f"_nvidia_qp{q}"
            
            out_name = f"{stem}{suffix}.mp4"
            out_file = output_dir / out_name
            
            if out_file.exists() and not args.force:
                print(f"Skipping {out_name} (exists)")
                continue
            
            # Prepare kwargs
            kwargs = {'quality': q}

            compressor.compress_file(vid, out_file, **kwargs)

def cmd_analyze(args):
    analyzer = VMAFAnalyzer(
        ffmpeg_bin=args.ffmpeg,
        ffprobe_bin=args.ffprobe
    )
    
    ref_dir = Path(args.ref_dir).resolve()
    comp_dirs = [Path(p).resolve() for p in args.comp_dirs]
    output_csv = Path(args.output).resolve()
    
    # 收集所有压缩视频
    all_comp_videos = []
    for d in comp_dirs:
        if d.exists():
            all_comp_videos.extend(find_videos(d, recursive=True))
    
    if not all_comp_videos:
        print("No compressed videos found.")
        return
        
    analyzer.process_files(
        ref_dir=ref_dir,
        comp_files=all_comp_videos,
        output_csv=output_csv,
        jobs=args.jobs,
        use_neg_model=args.use_neg_model
    )

def cmd_plot(args):
    plotter = EfficiencyPlotter(
        csv_path=Path(args.csv).resolve(),
        output_dir=Path(args.output_dir).resolve()
    )
    plotter.plot(sources=args.sources)

def main():
    parser = argparse.ArgumentParser(prog="VideoCompressToolkit", description="All-in-one Video Compression & Analysis Toolkit")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # 压缩命令
    p_compress = subparsers.add_parser("compress", help="Compress video(s)")
    p_compress.add_argument("input", help="Input file or directory")
    p_compress.add_argument("output", help="Output file or directory")
    p_compress.add_argument("--encoder", choices=["intel", "nvidia", "mac"], required=True, help="Encoder to use")
    p_compress.add_argument("--quality", type=int, help="Quality parameter (QP, Global Quality, etc.)")
    p_compress.add_argument("--force", action="store_true", help="Overwrite existing files")
    p_compress.set_defaults(func=cmd_compress)

    # 批量命令
    p_batch = subparsers.add_parser("batch", help="Run batch compression test")
    p_batch.add_argument("--source", default="Videos", help="Source directory")
    p_batch.add_argument("--output", required=True, help="Output directory")
    p_batch.add_argument("--encoder", choices=["intel", "nvidia", "mac"], required=True)
    p_batch.add_argument("--start", dest="range_start", type=int, required=True, help="Start of parameter range")
    p_batch.add_argument("--end", dest="range_end", type=int, required=True, help="End of parameter range")
    p_batch.add_argument("--force", action="store_true", help="Overwrite existing files")
    p_batch.set_defaults(func=cmd_batch)

    # 分析命令
    p_analyze = subparsers.add_parser("analyze", help="Calculate VMAF scores")
    p_analyze.add_argument("--ref-dir", default="Videos", help="Reference videos directory")
    p_analyze.add_argument("--comp-dirs", nargs="+", default=["QSV_Compressed", "NVENC_Compressed", "NVENC_QP_Compressed", "MAC_Compressed"], help="Compressed directories to scan")
    p_analyze.add_argument("--output", default="Results/FFMetrics.Results.csv", help="Output CSV file")
    p_analyze.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg binary")
    p_analyze.add_argument("--ffprobe", default="ffprobe", help="ffprobe binary")
    p_analyze.add_argument("--jobs", type=int, default=1, help="Parallel jobs")
    p_analyze.add_argument("--use-neg-model", action="store_true", help="Use VMAF NEG model")
    p_analyze.set_defaults(func=cmd_analyze)

    # 绘图命令
    p_plot = subparsers.add_parser("plot", help="Plot efficiency graphs")
    p_plot.add_argument("--csv", default="Results/FFMetrics.Results.csv", help="Input CSV file")
    p_plot.add_argument("--output-dir", default="Results", help="Output directory for plots")
    p_plot.add_argument("--sources", nargs="*", help="Filter by specific source names")
    p_plot.set_defaults(func=cmd_plot)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
