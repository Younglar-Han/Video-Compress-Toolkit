#!/usr/bin/env python3
"""批量计算压缩视频相对于原片的 VMAF 分数，并生成 FFMetrics.Results.csv。

依赖：
- 已安装带 libvmaf 的 ffmpeg / ffprobe
- 原始视频与压缩视频为同分辨率、同帧率（推荐）
- 压缩文件命名规则与本仓库批量脚本一致：
    - Intel QSV : <原文件名>_intel_q<数值>.mp4              （来自 batch_intel_qsv_gq.py）
    - Nvidia    : <原文件名>_nvidia_qmax<数值>.mp4           （来自 batch_nvidia_qmax.py）
    - Nvidia    : <原文件名>_nvidia_qp<数值>.mp4             （来自 batch_nvidia_constqp.py）
    - Nvidia(AQ) : <原文件名>_nvidia_qp<数值>_aq.mp4         （来自 batch_nvidia_constqp_aq.py）
    - Mac       : <原文件名>_mac_qv<数值>.mp4                （来自 batch_mac_qv.py）

输出：
- 默认生成 Results/FFMetrics.Results.csv（制表符分隔，字段：FileSpec, VMAF-Value, Bitrate）
    可直接被 plot_compression_efficiency.py 读取使用。

用法示例：

    python test_vmaf_scores.py \
        --ref-dir ./Videos \
        --comp-dirs QSV_Compressed NVENC_Compressed MAC_Compressed \
        --output Results/FFMetrics.Results.csv

如果不指定 --comp-dirs，则会自动检测当前目录下是否存在：
    QSV_Compressed, NVENC_Compressed, NVENC_QP_Compressed, NVENC_QP_AQ_Compressed, MAC_Compressed 并遍历其中的 .mp4。
"""

import argparse
import csv
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Tuple, List


KNOWN_COMP_DIR_NAMES = [
    "QSV_Compressed",
    "NVENC_Compressed",
    "NVENC_QP_Compressed",
    "NVENC_QP_AQ_Compressed",
    "MAC_Compressed",
    "Compressed",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="批量计算压缩视频相对于原片的 VMAF 分数，并导出为 FFMetrics.Results.csv",
    )
    parser.add_argument(
        "--ref-dir",
        type=Path,
        default=Path("./Videos"),
        help="原始视频所在目录（默认：./Videos，仅按文件名匹配同名 .mp4 作为参考）",
    )
    parser.add_argument(
        "--comp-dirs",
        type=Path,
        nargs="*",
        help=(
            "压缩视频所在目录列表（可多个）。"
            "若不指定，则自动使用当前目录下存在的 QSV_Compressed、NVENC_Compressed、NVENC_QP_Compressed、NVENC_QP_AQ_Compressed、MAC_Compressed。"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("Results/FFMetrics.Results.csv"),
        help="输出 TSV 文件路径（默认：Results/FFMetrics.Results.csv）",
    )
    parser.add_argument(
        "--ffmpeg-bin",
        type=str,
        default="ffmpeg",
        help="ffmpeg 可执行文件名称或路径（默认：ffmpeg）",
    )
    parser.add_argument(
        "--ffprobe-bin",
        type=str,
        default="ffprobe",
        help="ffprobe 可执行文件名称或路径（默认：ffprobe）",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help=(
            "并行任务数（同时开启多少个 ffmpeg 进程，默认 1）。"
            "建议不要超过 CPU 物理核心数。"
        ),
    )
    parser.add_argument(
        "--use-neg-model",
        action="store_true",
        help=(
            "使用 libvmaf 的 neg 模型 (model=version=vmaf_v0.6.1neg)。"
            "需要 ffmpeg/libvmaf 已内置该模型。"
        ),
    )
    return parser.parse_args()


def guess_comp_dirs() -> List[Path]:
    """在当前目录下猜测压缩目录列表。"""

    candidates = [
        Path("QSV_Compressed"),
        Path("NVENC_Compressed"),
        Path("NVENC_QP_Compressed"),
        Path("NVENC_QP_AQ_Compressed"),
        Path("MAC_Compressed"),
        Path("Compressed"),
    ]
    return [p for p in candidates if p.exists() and p.is_dir()]


def normalize_filespec(filespec: str) -> str:
    """把 FileSpec 归一化为稳定格式：<压缩目录>\\<相对路径/文件名>。

    目的：
    - 避免 Windows 绝对路径、macOS/Linux 绝对路径导致重复计算/无法增量跳过
    - 保证同一压缩文件在不同机器上有一致的键
    """

    s = str(filespec).replace("/", "\\")
    for dir_name in KNOWN_COMP_DIR_NAMES:
        token = f"\\{dir_name}\\"
        idx = s.lower().find(token.lower())
        if idx != -1:
            return s[idx + 1 :]

        if s.lower().startswith(f"{dir_name.lower()}\\"):
            return s

    # 兜底：只保留文件名
    return s.split("\\")[-1]


def match_original_from_name(ref_dir: Path, comp_file: Path) -> Optional[Path]:
    """根据压缩文件名推断原始文件路径。

    支持的命名：
    - <stem>_intel_q<数值>.mp4
    - <stem>_nvidia_qmax<数值>.mp4
    - <stem>_nvidia_qp<数值>.mp4
    - <stem>_nvidia_qp<数值>_aq.mp4
    - <stem>_mac_qv<数值>.mp4
    若均不匹配，则尝试直接使用同名 stem 的 .mp4 作为原片。
    """

    stem = comp_file.stem
    # AQ 输出会在末尾加 _aq（例如 *_nvidia_qp25_aq.mp4），这里先去掉该后缀以便匹配原片名
    stem = re.sub(r"_aq$", "", stem)
    patterns = [
        re.compile(r"^(?P<base>.+)_intel_q\d+$"),
        re.compile(r"^(?P<base>.+)_nvidia_qmax\d+$"),
        re.compile(r"^(?P<base>.+)_nvidia_qp\d+$"),
        re.compile(r"^(?P<base>.+)_mac_qv\d+$"),
    ]

    base_stem = None
    for pat in patterns:
        m = pat.match(stem)
        if m:
            base_stem = m.group("base")
            break

    if base_stem is None:
        base_stem = stem

    candidates = [
        ref_dir / f"{base_stem}.mp4",
        ref_dir / f"{base_stem}.MP4",
        ref_dir / f"{base_stem}.mov",
        ref_dir / f"{base_stem}.MOV",
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    return None


def run_ffprobe_bitrate(ffprobe_bin: str, video: Path) -> Optional[float]:
    """使用 ffprobe 获取视频平均码率（kbps）。

    优先尝试视频流 bit_rate，若没有则退回到容器总体 bit_rate。
    """

    # 先试流级
    cmd_stream = [
        ffprobe_bin,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=bit_rate",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video),
    ]
    try:
        res = subprocess.run(cmd_stream, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        txt = res.stdout.decode().strip()
        if txt:
            return float(txt) / 1000.0
    except Exception:
        pass

    # 再试整体
    cmd_format = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=bit_rate",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video),
    ]
    try:
        res = subprocess.run(cmd_format, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        txt = res.stdout.decode().strip()
        if txt:
            return float(txt) / 1000.0
    except Exception:
        pass

    return None


def run_vmaf(ffmpeg_bin: str, distorted: Path, reference: Path, use_neg_model: bool) -> Optional[float]:
    """调用 ffmpeg+libvmaf 计算 VMAF 分数。

    使用 stderr 中的 `VMAF score:` 行做解析。
    distorted: 压缩后视频
    reference: 原始参考视频
    """

    if use_neg_model:
        # 使用官方内置的 neg 模型版本号
        filter_str = "libvmaf=model=version=vmaf_v0.6.1neg"
    else:
        filter_str = "libvmaf"

    # 注意：ffmpeg 通常要求先传入失真(distorted)，再传入参考(reference)
    cmd = [
        ffmpeg_bin,
        "-i",
        str(distorted),
        "-i",
        str(reference),
        "-lavfi",
        filter_str,
        "-f",
        "null",
        "-",
    ]

    print(f"计算 VMAF: {distorted.name} vs {reference.name}")
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

    if proc.returncode != 0:
        print(f"[错误] ffmpeg 计算 VMAF 失败：{distorted} -> returncode={proc.returncode}")
        print(proc.stderr.decode(errors="ignore"))
        return None

    stderr_text = proc.stderr.decode(errors="ignore")
    # 新版 ffmpeg+libvmaf 通常会包含 "VMAF score: 95.4321"
    m = re.search(r"VMAF score:\s*([0-9.]+)", stderr_text)
    if not m:
        print("[警告] 未在 ffmpeg 输出中找到 VMAF score 字样，原始输出：")
        print(stderr_text)
        return None

    return float(m.group(1))


def file_spec_for_row(comp_file: Path) -> str:
    """生成写入 CSV 的 FileSpec 字段。

    为了兼容原先 Windows 工具生成的结果，这里使用类似
    "目录\\文件名" 的反斜杠分隔格式。
    """

    # 优先使用相对路径（相对当前工作目录），让结果更可移植
    try:
        rel = comp_file.relative_to(Path.cwd())
        spec = rel.as_posix()
    except Exception:
        # 兜底：绝对路径
        spec = comp_file.as_posix()

    return normalize_filespec(spec)


def process_one(
    comp_file: Path,
    orig: Path,
    ffmpeg_bin: str,
    ffprobe_bin: str,
    use_neg_model: bool,
) -> Optional[Tuple[str, float, float]]:
    """处理单个压缩文件：算码率 + VMAF，返回一行结果。"""

    bitrate = run_ffprobe_bitrate(ffprobe_bin, comp_file)
    if bitrate is None:
        print(f"[警告] 无法获取码率，跳过: {comp_file}")
        return None

    vmaf = run_vmaf(ffmpeg_bin, comp_file, orig, use_neg_model)
    if vmaf is None:
        print(f"[警告] 无法计算 VMAF，跳过: {comp_file}")
        return None

    file_spec = file_spec_for_row(comp_file)
    print(f"[OK] {file_spec}  VMAF={vmaf:.3f}  Bitrate={bitrate:.2f} kbps")
    return file_spec, vmaf, bitrate


def main() -> None:
    args = parse_args()

    out_path = args.output.resolve()

    # 如果已存在结果文件，则先读取其中的 FileSpec，后续对这些视频跳过重复计算
    existing_rows_by_spec: dict[str, Tuple[str, str]] = {}
    existing_specs: set[str] = set()
    if out_path.exists():
        print(f"检测到已存在的结果文件，将跳过已测试视频: {out_path}")
        with out_path.open("r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            header = next(reader, None)

            if header and "FileSpec" in header:
                idx_spec = header.index("FileSpec")
                idx_vmaf = header.index("VMAF-Value") if "VMAF-Value" in header else None
                idx_bitrate = header.index("Bitrate") if "Bitrate" in header else None
            else:
                idx_spec, idx_vmaf, idx_bitrate = 0, 1, 2

            for row in reader:
                if not row:
                    continue
                raw_spec = row[idx_spec]
                spec = normalize_filespec(raw_spec)

                v_str = row[idx_vmaf] if idx_vmaf is not None and idx_vmaf < len(row) else ""
                b_str = row[idx_bitrate] if idx_bitrate is not None and idx_bitrate < len(row) else ""
                # 若存在重复（常见于不同机器绝对路径不同），保留第一次出现的
                if spec not in existing_rows_by_spec:
                    existing_rows_by_spec[spec] = (v_str, b_str)
                existing_specs.add(spec)

    ref_dir = args.ref_dir.resolve()
    if args.comp_dirs:
        comp_dirs = [p.resolve() for p in args.comp_dirs]
    else:
        comp_dirs = [p.resolve() for p in guess_comp_dirs()]

    if not comp_dirs:
        raise SystemExit(
            "没有找到压缩目录，请通过 --comp-dirs 显式指定，"
            "或者在当前目录下创建 QSV_Compressed / NVENC_Compressed / MAC_Compressed。"
        )

    print(f"参考目录(ref-dir): {ref_dir}")
    print("压缩目录(comp-dirs):")
    for d in comp_dirs:
        print(f"  - {d}")

    # 收集所有待计算的任务
    tasks: list[Tuple[Path, Path]] = []
    for comp_root in comp_dirs:
        for comp_file in comp_root.rglob("*.mp4"):
            orig = match_original_from_name(ref_dir, comp_file)
            if orig is None:
                print(f"[跳过] 找不到原片，对应压缩文件: {comp_file}")
                continue

            file_spec = file_spec_for_row(comp_file)
            if file_spec in existing_specs:
                print(f"[跳过] 已有 VMAF 结果: {file_spec}")
                continue

            tasks.append((comp_file, orig))

    if not tasks:
        print("没有找到任何可用的压缩文件/原片配对，退出。")
        return

    print(f"共需计算 {len(tasks)} 个文件，使用并行任务数: {max(1, args.jobs)}")

    rows: list[Tuple[str, float, float]] = []
    # 使用线程池并行跑多个 ffmpeg 进程（外部进程为主，GIL 影响很小）
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as executor:
        future_to_file = {
            executor.submit(
                process_one,
                comp_file,
                orig,
                args.ffmpeg_bin,
                args.ffprobe_bin,
                args.use_neg_model,
            ): comp_file
            for comp_file, orig in tasks
        }

        for future in as_completed(future_to_file):
            try:
                result = future.result()
            except Exception as exc:  # 防御性：某个任务异常不中断整体
                comp_file = future_to_file[future]
                print(f"[错误] 处理 {comp_file} 时出现异常: {exc}")
                continue

            if result is not None:
                rows.append(result)

    if not rows and not existing_rows_by_spec:
        print("没有成功计算到任何 VMAF 结果，未写出 CSV。")
        return

    print(f"\n写出结果到: {out_path}")

    # 使用制表符分隔，列名与 plot_compression_efficiency.py 一致
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["FileSpec", "VMAF-Value", "Bitrate"])

        # 先写入已有记录
        for spec, (v_str, b_str) in existing_rows_by_spec.items():
            writer.writerow([spec, v_str, b_str])

        # 再写入本次新增的结果
        for file_spec, vmaf, bitrate in rows:
            writer.writerow([file_spec, f"{vmaf:.4f}", f"{bitrate:.2f}"])

    total = len(existing_rows_by_spec) + len(rows)
    print(f"完成，本次新增 {len(rows)} 条记录，总计 {total} 条。")


if __name__ == "__main__":
    main()
