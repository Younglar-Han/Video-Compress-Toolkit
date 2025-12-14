#!/usr/bin/env python3
"""递归压缩当前（或指定）目录下所有 .mp4 文件。

根据不同硬件选择 ffmpeg 的三种模式：
- intel  : Windows + Intel QSV 硬件编码
- nvidia : Windows + NVIDIA NVENC 硬件编码
- mac    : macOS + Apple VideoToolbox 硬件编码 #参数未测试
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path


def build_ffmpeg_cmd(mode: str, input_file: Path, output_file: Path) -> list[str]:
    """根据模式构造一条 ffmpeg 命令行。"""
    input_str = str(input_file)
    output_str = str(output_file)

    if mode == "intel":
        # Intel QSV 模式，压缩效果最好，但最慢
        return [
            "ffmpeg",
            "-hwaccel",
            "qsv",
            "-hwaccel_output_format",
            "qsv",
            "-i",
            input_str,
            "-c:v",
            "hevc_qsv",
            "-vtag",
            "hvc1",
            "-preset",
            "veryslow",
            "-global_quality",  # 质量参数，数值越小质量越好、体积越大
            "21",  # 目标VMAF分数95，已校准
            "-c:a",
            "copy",
            "-map_metadata",
            "0",
            "-y",
            output_str,
        ]
    elif mode == "nvidia":
        # NVIDIA NVENC 模式，压缩效果次之，速度中等
        return [
            "ffmpeg",
            "-i",
            input_str,
            "-c:v",
            "hevc_nvenc",
            "-vtag",
            "hvc1",
            "-preset",
            "p7",  # 预设 p1(最快) ~ p7(最慢，质量最好)
            "-multipass",
            "fullres",  # 多遍编码，质量更好
            "-rc",
            "constqp",  # 固定 QP 模式（vbr模式及rc失效因此不采用）
            "-qp",  # 质量参数，数值越小质量越好，体积越大
            "24",  # 目标VMAF分数95，已校准
            "-c:a",
            "copy",
            "-map_metadata",
            "0",
            "-y",
            output_str,
        ]
    elif mode == "mac":
        # Apple M 系列芯片，使用 VideoToolbox 硬件编码 HEVC，效果最差，相同体积下质量最低
        # 使用质量模式（-q:v），数值越大质量越高、体积越大
        return [
            "ffmpeg",
            "-hwaccel",
            "videotoolbox",
            "-i",
            input_str,
            "-c:v",
            "hevc_videotoolbox",
            "-vtag",
            "hvc1",
            "-q:v",  # 质量参数，数值越大质量越高、体积越大
            "58",  # 目标VMAF分数95，已校准
            "-c:a",
            "copy",
            "-map_metadata",
            "0",
            "-y",
            output_str,
        ]
    else:
        raise ValueError(f"Unknown mode: {mode}")


def human_mb(size_bytes: int) -> float:
    """帮助函数：把字节数转换为 MB（仅用于打印显示）。"""

    return size_bytes / (1024 * 1024)


def compress_all_videos(source_root: Path, target_root: Path, mode: str) -> None:
    """递归遍历 source_root，压缩所有 .mp4 到 target_root。"""

    source_root = source_root.resolve()
    target_root = target_root.resolve()

    # 确保目标根目录存在
    target_root.mkdir(parents=True, exist_ok=True)

    for dirpath, _, filenames in os.walk(source_root):
        current_dir = Path(dirpath)

        # 跳过目标压缩目录本身及其子目录，避免重复压缩
        if current_dir == target_root or target_root in current_dir.parents:
            continue

        try:
            # 计算相对路径，从而在目标目录中镜像出同样的结构
            relative_dir = current_dir.relative_to(source_root)
        except ValueError:
            # 理论上不会发生，只是防御性处理
            relative_dir = Path("")

        target_dir = target_root / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        for name in filenames:
            # 只处理 .mp4 文件，其它类型直接跳过
            if not name.lower().endswith(".mp4"):
                continue

            input_file = current_dir / name
            output_file = target_dir / name

            # 根据模式拼出一条 ffmpeg 命令
            cmd = build_ffmpeg_cmd(mode, input_file, output_file)
            print(f"\n==> Compressing: {input_file}")
            print("Command:", " ".join(cmd))

            # 运行 ffmpeg，不在终端输出，把信息收集在内存里
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            if result.returncode != 0:
                print(f"Failed to compress {name}.")
                print(result.stderr.decode(errors="ignore"))
                continue

            size_orig = input_file.stat().st_size
            size_comp = output_file.stat().st_size

            size_orig_mb = human_mb(size_orig)
            size_comp_mb = human_mb(size_comp)

            print(
                f"{name} has been compressed successfully. "
                f"Original size: {size_orig_mb:.2f} MB, "
                f"Compressed size: {size_comp_mb:.2f} MB."
            )

            # 如果压缩后更大，则用原文件替换，避免“越压越大”
            if size_comp >= size_orig:
                print(
                    f"{name} is larger after compression, "
                    "replacing by original file."
                )
                shutil.copy2(input_file, output_file)
            else:
                print(f"{name} is smaller after compression.")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""

    parser = argparse.ArgumentParser(
        description=(
            "Recursively compress all .mp4 files under SOURCE_ROOT "
            "and mirror the structure under TARGET_ROOT using ffmpeg."
        )
    )
    parser.add_argument(
        "--mode",
        choices=["intel", "nvidia", "mac"],
        default="mac",
        help=(
            "ffmpeg 硬件加速模式：intel(QSV) / nvidia(NVENC) / mac(VideoToolbox) "
            "(default: mac)"
        ),
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("./Videos"),
        help="要遍历的视频源目录，默认 ./Videos",
    )
    parser.add_argument(
        "--target-root",
        type=Path,
        default=Path("./Compressed"),
        help="压缩后输出的根目录，默认 ./Compressed",
    )
    return parser.parse_args()


def main() -> None:
    """脚本入口：解析参数并启动压缩流程。"""

    args = parse_args()
    print(f"Source root : {args.source_root.resolve()}")
    print(f"Target root : {args.target_root.resolve()}")
    print(f"Mode        : {args.mode}")

    compress_all_videos(args.source_root, args.target_root, args.mode)


if __name__ == "__main__":
    main()
