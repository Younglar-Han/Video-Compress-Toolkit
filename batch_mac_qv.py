#!/usr/bin/env python3
"""批量使用 macOS VideoToolbox (hevc_videotoolbox) 按不同 q:v 压缩目录下的视频。

用法示例（在项目根目录执行）::

    python batch_mac_qv.py

默认行为：
- 扫描 ./Videos 目录下所有 .mp4 文件（不递归子目录）
- 对每个文件用 hevc_videotoolbox，q:v 从 54~75 依次压缩
- 输出到 ./MAC_Compressed 目录下，命名为：原文件名去扩展名 + _mac_qv{值}.mp4

注意：
- 需要在 macOS + 支持 VideoToolbox 的 ffmpeg 环境下运行。
- 如果输出文件已存在，则会跳过该 q:v 以避免重复压缩。
"""

import argparse
import subprocess
from pathlib import Path


def build_mac_cmd(input_file: Path, output_file: Path, qv: int) -> list[str]:
    """构造一条 macOS hevc_videotoolbox 压缩命令。"""

    return [
        "ffmpeg",
        "-hwaccel",
        "videotoolbox",
        "-i",
        str(input_file),
        "-c:v",
        "hevc_videotoolbox",
        "-vtag",
        "hvc1",
        "-q:v",
        str(qv),      # 数值越大质量越高，体积越大（与你现有脚本保持一致）
        "-c:a",
        "copy",
        "-map_metadata",
        "0",
        "-y",
        str(output_file),
    ]


def compress_with_qv_range(source_dir: Path, output_dir: Path, qv_min: int, qv_max: int) -> None:
    """对 source_dir 下的所有 .mp4 文件用 qv_min~qv_max 逐个压缩。"""

    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"源目录: {source_dir}")
    print(f"输出目录: {output_dir}")
    print(f"q:v 范围: {qv_min} ~ {qv_max}")

    videos = sorted(p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() == ".mp4")

    if not videos:
        print("当前目录下没有找到 .mp4 文件。")
        return

    for video in videos:
        print(f"\n=== 处理源文件: {video.name} ===")
        stem = video.stem

        for qv in range(qv_min, qv_max + 1):
            out_name = f"{stem}_mac_qv{qv}.mp4"
            out_path = output_dir / out_name

            if out_path.exists():
                print(f"[跳过] {out_name} 已存在，略过 q:v={qv}。")
                continue

            cmd = build_mac_cmd(video, out_path, qv)
            print(f"\n--> 压缩为 q:v={qv}")
            print("命令:", " ".join(cmd))

            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            if result.returncode != 0:
                print(f"[失败] {video.name} (q:v={qv}) 压缩失败。")
                print(result.stderr.decode(errors="ignore"))
                if out_path.exists():
                    out_path.unlink(missing_ok=True)
                continue

            print(f"[成功] {video.name} -> {out_name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用 macOS hevc_videotoolbox 对目录下所有 .mp4 按 q:v 区间批量压缩",
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
        default=Path("./MAC_Compressed"),
        help="压缩输出目录（默认：./MAC_Compressed）",
    )
    parser.add_argument(
        "--qv-min",
        type=int,
        default=54,
        help="q:v 最小值（默认 54）",
    )
    parser.add_argument(
        "--qv-max",
        type=int,
        default=75,
        help="q:v 最大值（默认 75）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.qv_min > args.qv_max:
        raise SystemExit("qv-min 不能大于 qv-max")

    compress_with_qv_range(args.source_dir, args.output_dir, args.qv_min, args.qv_max)


if __name__ == "__main__":
    main()
