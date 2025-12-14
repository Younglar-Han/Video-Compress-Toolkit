#!/usr/bin/env python3
"""批量使用 NVIDIA NVENC (hevc_nvenc) 以固定 QP (constqp) 并可选启用 AQ 压缩目录下的视频。

此脚本与 `batch_nvidia_constqp.py` 类似，但支持开启：
- `-spatial-aq`（空间自适应量化）
- `-temporal-aq`（时间自适应量化）
- `-aq-strength`（AQ 强度，常见范围 1-15，默认 8）

命名规则：
- 未启用 AQ：`<stem>_nvidia_qp{qp}.mp4`
- 启用 AQ：`<stem>_nvidia_qp{qp}_aq.mp4`

输出目录策略：
- 默认输出目录是 `./NVENC_QP_Compressed`（与非 AQ 脚本一致）
- 当启用 AQ 且用户未显式指定 `--output-dir` 时，脚本会自动切换到 `./NVENC_QP_AQ_Compressed`

用法示例::

        python batch_nvidia_constqp_aq.py \
            --source-dir ./Videos \
            --qp-min 23 --qp-max 28 \
            --spatial-aq --aq-strength 8 --temporal-aq

注意：不同版本的 ffmpeg/驱动对参数名支持可能略有差异，运行前可通过
`ffmpeg -h encoder=hevc_nvenc` 验证可用选项名称。
"""

import argparse
import subprocess
from pathlib import Path


def build_nvidia_constqp_aq_cmd(
    input_file: Path,
    output_file: Path,
    qp: int,
    spatial_aq: bool,
    spatial_aq_strength: int,
    temporal_aq: bool,
) -> list[str]:
    """构造启用了 AQ 的 NVENC constqp 命令。

    说明：参数名以常见的 ffmpeg 接受形式写出（例如 `-spatial-aq`），如果你的环境
    使用不同名称，请在调用脚本时自行调整或在本函数中修改。
    """

    cmd = [
        "ffmpeg",
        "-i",
        str(input_file),
        "-c:v",
        "hevc_nvenc",
        "-vtag",
        "hvc1",
        "-rc",
        "constqp",
        "-preset",
        "p7",
        "-multipass",
        "fullres",
        "-qp",
        str(qp),
    ]

    # 可选 AQ 参数
    if spatial_aq:
        cmd += ["-spatial-aq", "1"]
        # 使用 ffmpeg 支持的 AQ 强度参数名 -aq-strength（参见 encoder help）
        if spatial_aq_strength is not None:
            cmd += ["-aq-strength", str(spatial_aq_strength)]
    if temporal_aq:
        cmd += ["-temporal-aq", "1"]

    # 保持音频不变与元数据
    cmd += [
        "-c:a",
        "copy",
        "-map_metadata",
        "0",
        "-y",
        str(output_file),
    ]

    return cmd


def compress_with_qp_range(source_dir: Path, output_dir: Path, qp_min: int, qp_max: int, spatial_aq: bool, spatial_aq_strength: int, temporal_aq: bool) -> None:
    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"源目录: {source_dir}")
    print(f"输出目录: {output_dir}")
    print(f"QP 范围: {qp_min} ~ {qp_max}")
    print(f"spatial_aq={spatial_aq} (strength={spatial_aq_strength}), temporal_aq={temporal_aq}")

    videos = sorted(p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() == ".mp4")

    if not videos:
        print("当前目录下没有找到 .mp4 文件。")
        return

    for video in videos:
        print(f"\n=== 处理源文件: {video.name} ===")
        stem = video.stem

        for qp in range(qp_min, qp_max + 1):
            aq_suffix = "_aq" if (spatial_aq or temporal_aq) else ""
            out_name = f"{stem}_nvidia_qp{qp}{aq_suffix}.mp4"
            out_path = output_dir / out_name

            if out_path.exists():
                print(f"[跳过] {out_name} 已存在，略过 QP={qp}。")
                continue

            cmd = build_nvidia_constqp_aq_cmd(video, out_path, qp, spatial_aq, spatial_aq_strength, temporal_aq)
            print(f"\n--> 压缩为 QP={qp} (AQ: spatial={spatial_aq}, temporal={temporal_aq})")
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
        description="使用 NVIDIA hevc_nvenc(constqp) 对目录下所有 .mp4 按 QP 区间批量压缩，支持 AQ 参数",
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
        help=(
            "压缩输出目录（默认：./NVENC_QP_Compressed；若启用 AQ 且未显式指定 output-dir，"
            "会自动切换到 ./NVENC_QP_AQ_Compressed）"
        ),
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
    parser.add_argument(
        "--spatial-aq",
        action="store_true",
        help="开启 spatial adaptive quantization（空间自适应量化）",
    )
    parser.add_argument(
        "--spatial-aq-strength",
        "--aq-strength",
        type=int,
        default=8,
        help="AQ 强度（默认 8，常见范围 1-15，参见 encoder help）",
    )
    parser.add_argument(
        "--temporal-aq",
        action="store_true",
        help="开启 temporal adaptive quantization（时间自适应量化）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.qp_min > args.qp_max:
        raise SystemExit("qp-min 不能大于 qp-max")

    if args.spatial_aq and not (1 <= args.spatial_aq_strength <= 15):
        raise SystemExit("spatial-aq-strength/aq-strength 建议范围为 1-15")

    # 如果启用了 AQ 且用户没有显式修改输出目录（仍为默认 NVENC_QP_Compressed），
    # 则自动切换到 NVENC_QP_AQ_Compressed 以区分 AQ 与非 AQ 输出。
    default_out = Path("./NVENC_QP_Compressed")
    aq_out = Path("./NVENC_QP_AQ_Compressed")
    out_dir = args.output_dir
    if (args.spatial_aq or args.temporal_aq) and out_dir.resolve() == default_out.resolve():
        out_dir = aq_out
        print(f"检测到 AQ 已启用，自动将输出目录切换为: {out_dir}")

    compress_with_qp_range(
        args.source_dir,
        out_dir,
        args.qp_min,
        args.qp_max,
        args.spatial_aq,
        args.spatial_aq_strength,
        args.temporal_aq,
    )


if __name__ == "__main__":
    main()
