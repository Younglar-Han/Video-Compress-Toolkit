#!/usr/bin/env python3
"""批量使用 NVIDIA NVENC (hevc_nvenc) 按不同 qmax 压缩目录下的视频。

用法示例（在项目根目录执行）::

    python batch_nvidia_qmax.py

默认行为：
- 扫描 ./Videos 目录下所有 .mp4 文件（不递归子目录）
- 对每个文件用 hevc_nvenc，qmax 从 25~32 依次压缩
- 其它参数固定：preset=p7, multipass=fullres, cq=27, qmin=0
- 输出到 ./NVENC_Compressed 目录下，命名为：原文件名去扩展名 + _nvidia_qmax{值}.mp4

注意：
- 需要在有 NVIDIA 显卡且 ffmpeg 支持 hevc_nvenc 的环境下运行。
- 如果输出文件已存在，则会跳过该 qmax 以避免重复压缩。
"""

import argparse
import subprocess
from pathlib import Path


def build_nvidia_cmd(input_file: Path, output_file: Path, qmax: int) -> list[str]:
    """构造一条 NVIDIA hevc_nvenc 压缩命令。"""

    return [
        "ffmpeg",
        "-i",
        str(input_file),
        "-c:v",
        "hevc_nvenc",
        "-vtag",
        "hvc1",
        "-preset",
        "p7",          # 质量最好、最慢
        "-multipass",
        "fullres",     # 多遍编码
        "-cq",
        "27",          # 基础 CQ 固定
        "-qmin",
        "0",
        "-qmax",
        str(qmax),      # 本次遍历的 qmax
        "-c:a",
        "copy",
        "-map_metadata",
        "0",
        "-y",
        str(output_file),
    ]


def compress_with_qmax_range(source_dir: Path, output_dir: Path, qmax_min: int, qmax_max: int) -> None:
    """对 source_dir 下的所有 .mp4 文件用 qmax_min~qmax_max 逐个压缩。"""

    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"源目录: {source_dir}")
    print(f"输出目录: {output_dir}")
    print(f"qmax 范围: {qmax_min} ~ {qmax_max}")

    videos = sorted(p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() == ".mp4")

    if not videos:
        print("当前目录下没有找到 .mp4 文件。")
        return

    for video in videos:
        print(f"\n=== 处理源文件: {video.name} ===")
        stem = video.stem

        for qmax in range(qmax_min, qmax_max + 1):
            out_name = f"{stem}_nvidia_qmax{qmax}.mp4"
            out_path = output_dir / out_name

            if out_path.exists():
                print(f"[跳过] {out_name} 已存在，略过 qmax={qmax}。")
                continue

            cmd = build_nvidia_cmd(video, out_path, qmax)
            print(f"\n--> 压缩为 qmax={qmax}")
            print("命令:", " ".join(cmd))

            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            if result.returncode != 0:
                print(f"[失败] {video.name} (qmax={qmax}) 压缩失败。")
                print(result.stderr.decode(errors="ignore"))
                if out_path.exists():
                    out_path.unlink(missing_ok=True)
                continue

            print(f"[成功] {video.name} -> {out_name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用 NVIDIA hevc_nvenc 对目录下所有 .mp4 按 qmax 区间批量压缩",
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
        default=Path("./NVENC_Compressed"),
        help="压缩输出目录（默认：./NVENC_Compressed）",
    )
    parser.add_argument(
        "--qmax-min",
        type=int,
        default=25,
        help="qmax 最小值（默认 25）",
    )
    parser.add_argument(
        "--qmax-max",
        type=int,
        default=32,
        help="qmax 最大值（默认 32）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.qmax_min > args.qmax_max:
        raise SystemExit("qmax-min 不能大于 qmax-max")

    compress_with_qmax_range(args.source_dir, args.output_dir, args.qmax_min, args.qmax_max)


if __name__ == "__main__":
    main()
