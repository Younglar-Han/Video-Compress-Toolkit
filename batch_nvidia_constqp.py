#!/usr/bin/env python3
"""批量使用 NVIDIA NVENC (hevc_nvenc) 以固定 QP (constqp) 压缩目录下的视频。

用途：
- 适合在 NVIDIA 平台上做“恒定质量”(Constant QP) 的压缩实验，
  同一组 QP 下不同素材的主观质量会比较接近，但码率会随内容复杂度变化。

用法示例（在项目根目录执行）::

    python batch_nvidia_constqp.py

默认行为：
- 扫描 ./Videos 目录下所有 .mp4 文件（不递归子目录）
- 对每个文件用 hevc_nvenc，QP 从 19~25 依次压缩（可用参数改）
- 使用 constqp 码控模式：-rc constqp -qp <值>
- 其它参数固定：preset=p7, multipass=fullres
- 输出到 ./NVENC_QP_Compressed 目录下，命名为：原文件名去扩展名 + _nvidia_qp{值}.mp4

注意：
- 需要在有 NVIDIA 显卡且 ffmpeg 支持 hevc_nvenc 的环境下运行。
- 如果输出文件已存在，则会跳过该 QP 以避免重复压缩。
"""

import argparse
import subprocess
from pathlib import Path


def build_nvidia_constqp_cmd(input_file: Path, output_file: Path, qp: int) -> list[str]:
    """构造一条 NVIDIA hevc_nvenc 固定 QP (constqp) 压缩命令。"""

    return [
        "ffmpeg",
        "-i",
        str(input_file),
        "-c:v",
        "hevc_nvenc",
        "-vtag",
        "hvc1",
        "-rc",
        "constqp",       # 固定 QP 模式
        "-preset",
        "p7",            # 质量最好、最慢
        "-multipass",
        "fullres",       # 多遍编码
        "-qp",
        str(qp),          # 本次遍历的 QP
        "-c:a",
        "copy",
        "-map_metadata",
        "0",
        "-y",
        str(output_file),
    ]


def compress_with_qp_range(source_dir: Path, output_dir: Path, qp_min: int, qp_max: int) -> None:
    """对 source_dir 下的所有 .mp4 文件用 qp_min~qp_max 逐个压缩。"""

    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"源目录: {source_dir}")
    print(f"输出目录: {output_dir}")
    print(f"QP 范围: {qp_min} ~ {qp_max}")

    videos = sorted(p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() == ".mp4")

    if not videos:
        print("当前目录下没有找到 .mp4 文件。")
        return

    for video in videos:
        print(f"\n=== 处理源文件: {video.name} ===")
        stem = video.stem

        for qp in range(qp_min, qp_max + 1):
            out_name = f"{stem}_nvidia_qp{qp}.mp4"
            out_path = output_dir / out_name

            if out_path.exists():
                print(f"[跳过] {out_name} 已存在，略过 QP={qp}。")
                continue

            cmd = build_nvidia_constqp_cmd(video, out_path, qp)
            print(f"\n--> 压缩为 QP={qp}")
            print("命令:", " ".join(cmd))

            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            if result.returncode != 0:
                print(f"[失败] {video.name} (QP={qp}) 压缩失败。")
                print(result.stderr.decode(errors="ignore"))
                if out_path.exists():
                    out_path.unlink(missing_ok=True)
                continue

            print(f"[成功] {video.name} -> {out_name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用 NVIDIA hevc_nvenc(constqp) 对目录下所有 .mp4 按 QP 区间批量压缩",
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
        default=Path("./NVENC_QP_Compressed"),
        help="压缩输出目录（默认：./NVENC_QP_Compressed）",
    )
    parser.add_argument(
        "--qp-min",
        type=int,
        default=25,
        help="QP 最小值（默认 25）",
    )
    parser.add_argument(
        "--qp-max",
        type=int,
        default=32,
        help="QP 最大值（默认 32）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.qp_min > args.qp_max:
        raise SystemExit("qp-min 不能大于 qp-max")

    compress_with_qp_range(args.source_dir, args.output_dir, args.qp_min, args.qp_max)


if __name__ == "__main__":
    main()
