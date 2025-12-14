#!/usr/bin/env python3
"""批量使用 Intel QSV 按不同 global_quality 压缩根目录下的视频。

用法示例（在项目根目录执行）::

    python batch_intel_qsv_gq.py

默认行为：
- 扫描 ./Videos 目录下所有 .mp4 文件（不递归子目录）
- 对每个文件用 Intel QSV (hevc_qsv) 分别以 global_quality 18~25 压缩
- 输出到 ./QSV_Compressed 目录下，命名为：原文件名去扩展名 + _q{质量}.mp4

注意：
- 需要在 **Intel + 支持 QSV 的 ffmpeg** 环境下运行；macOS 上是没有 intel_qsv 的。
- 如果输出文件已存在，则会跳过该质量以避免重复压缩。
"""

import argparse
import subprocess
from pathlib import Path


def build_intel_qsv_cmd(input_file: Path, output_file: Path, gq: int) -> list[str]:
    """构造一条 Intel QSV hevc_qsv 压缩命令。"""

    return [
        "ffmpeg",
        "-hwaccel",
        "qsv",
        "-hwaccel_output_format",
        "qsv",
        "-i",
        str(input_file),
        "-c:v",
        "hevc_qsv",
        "-vtag",
        "hvc1",
        "-preset",
        "veryslow",
        "-global_quality",
        str(gq),
        "-c:a",
        "copy",
        "-map_metadata",
        "0",
        "-y",
        str(output_file),
    ]


def compress_with_gq_range(source_dir: Path, output_dir: Path, gq_min: int, gq_max: int) -> None:
    """对 source_dir 下的所有 .mp4 文件用 gq_min~gq_max 逐个压缩。"""

    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"源目录: {source_dir}")
    print(f"输出目录: {output_dir}")
    print(f"global_quality 范围: {gq_min} ~ {gq_max}")

    videos = sorted(p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() == ".mp4")

    if not videos:
        print("当前目录下没有找到 .mp4 文件。")
        return

    for video in videos:
        print(f"\n=== 处理源文件: {video.name} ===")
        stem = video.stem

        for gq in range(gq_min, gq_max + 1):
            out_name = f"{stem}_intel_q{gq}.mp4"
            out_path = output_dir / out_name

            if out_path.exists():
                print(f"[跳过] {out_name} 已存在，略过该质量等级 {gq}。")
                continue

            cmd = build_intel_qsv_cmd(video, out_path, gq)
            print(f"\n--> 压缩为 global_quality={gq}")
            print("命令:", " ".join(cmd))

            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            if result.returncode != 0:
                print(f"[失败] {video.name} (gq={gq}) 压缩失败。")
                print(result.stderr.decode(errors="ignore"))
                # 失败就删除可能残留的坏文件
                if out_path.exists():
                    out_path.unlink(missing_ok=True)
                continue

            print(f"[成功] {video.name} -> {out_name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用 Intel QSV 对当前目录下所有 .mp4 按 global_quality 区间批量压缩",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path("./Videos"),
        help="源视频所在目录（默认：./Videos，仅扫描该目录下的 .mp4，不递归）",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./QSV_Compressed"),
        help="压缩输出目录（默认：./QSV_Compressed）",
    )
    parser.add_argument(
        "--gq-min",
        type=int,
        default=18,
        help="global_quality 最小值（默认 18）",
    )
    parser.add_argument(
        "--gq-max",
        type=int,
        default=25,
        help="global_quality 最大值（默认 25）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.gq_min > args.gq_max:
        raise SystemExit("gq-min 不能大于 gq-max")

    compress_with_gq_range(args.source_dir, args.output_dir, args.gq_min, args.gq_max)


if __name__ == "__main__":
    main()
