import argparse
import pandas as pd
import matplotlib.pyplot as plt
import re
import subprocess
from pathlib import Path


SOURCE_ROOT = Path("Videos")
FFPROBE_BIN = "ffprobe"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "从 Results/FFMetrics.Results.csv 读取 VMAF 与码率数据，绘制每个素材图与总体平均图。"
            "可通过参数筛选只绘制指定素材/平台。"
        )
    )
    parser.add_argument(
        "--sources",
        nargs="*",
        help=(
            "只绘制指定 Source（素材名，等于原文件名去扩展名）。"
            "示例：--sources DJI_0046 DJI_0048"
        ),
    )
    parser.add_argument(
        "--devices",
        nargs="*",
        help=(
            "只绘制指定平台（Intel / Nvidia / MAC）。"
            "示例：--devices Nvidia MAC"
        ),
    )
    parser.add_argument(
        "--aq",
        action="store_true",
        help="绘制 AQ 数据（adaptive quantization，自适应量化），否则仅绘制非 AQ 数据。",
    )
    return parser.parse_args()


def extract_info(filepath):
    """从 FileSpec 中提取 设备(Device)、参数值(Param) 和 原始素材名(Source)。

    兼容多种命名：
    - *_intel_q22.mp4 / *_qsv_22.mp4        -> Intel
    - *_nvidia_qmax23.mp4 / *_max_23.mp4    -> Nvidia (qmax)
    - *_nvidia_qp25.mp4                     -> Nvidia (constqp / QP)
    - *_mac_qv54.mp4 / *_mac_54.mp4         -> MAC
    """

    # 只取文件名部分，兼容 Windows 反斜杠
    filename = filepath.split("\\")[-1].split("/")[-1]
    stem = filename.rsplit(".", 1)[0]

    # AQ 输出会带 _aq 后缀（例如 *_nvidia_qp25_aq.mp4），需要识别并剥离后再解析参数
    aq = False
    if stem.endswith("_aq"):
        aq = True
        stem_no_aq = re.sub(r"_aq$", "", stem)
    else:
        stem_no_aq = stem

    # 默认值
    device = "Unknown"
    param_value = 0
    source = stem

    patterns = [
        ("Intel", r"^(?P<source>.+)_intel_q(?P<param>\d+)$"),
        ("Intel", r"^(?P<source>.+)_qsv_(?P<param>\d+)$"),
        ("Nvidia", r"^(?P<source>.+)_nvidia_qmax(?P<param>\d+)$"),
        ("Nvidia", r"^(?P<source>.+)_max_(?P<param>\d+)$"),
        ("Nvidia", r"^(?P<source>.+)_nvidia_qp(?P<param>\d+)$"),
        ("MAC", r"^(?P<source>.+)_mac_qv(?P<param>\d+)$"),
        ("MAC", r"^(?P<source>.+)_mac_(?P<param>\d+)$"),
    ]

    for dev, pat in patterns:
        m = re.match(pat, stem_no_aq)
        if m:
            device = dev
            param_value = int(m.group("param"))
            source = m.group("source")
            break

    return device, param_value, source, aq


def normalize_device_name(name: str) -> str:
    key = str(name).strip().lower()
    mapping = {
        "intel": "Intel",
        "qsv": "Intel",
        "nvidia": "Nvidia",
        "nvenc": "Nvidia",
        "mac": "MAC",
        "macos": "MAC",
        "videotoolbox": "MAC",
    }
    return mapping.get(key, name)


def find_original_video(source_stem: str) -> Path | None:
    """根据 Source 名推测原始视频路径，尝试多种扩展名。"""

    candidates = [
        SOURCE_ROOT / f"{source_stem}.mp4",
        SOURCE_ROOT / f"{source_stem}.MP4",
        SOURCE_ROOT / f"{source_stem}.mov",
        SOURCE_ROOT / f"{source_stem}.MOV",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def run_ffprobe_bitrate(ffprobe_bin: str, video: Path) -> float | None:
    """使用 ffprobe 获取视频平均码率（kbps）。"""

    # 优先视频流 bit_rate
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

    # 再退回整体 bit_rate
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


def main() -> None:
    args = parse_args()

    # 读取 Results 目录下的 CSV 文件
    results_path = Path("Results") / "FFMetrics.Results.csv"
    if not results_path.exists():
        raise SystemExit(
            f"未找到结果文件：{results_path}。请先运行 test_vmaf_scores.py 生成 Results/FFMetrics.Results.csv"
        )
    df = pd.read_csv(results_path, sep="\t")

    # 如果存在旧的 NVIDIA qmax 数据（_nvidia_qmax 或 _max_ 命名），在绘图时统一过滤掉，
    # 仅保留新的 constqp (_nvidia_qpXX) 等结果。
    mask_old_nvidia = (
        df["FileSpec"].astype(str).str.contains("nvidia_qmax", case=False)
        | df["FileSpec"].astype(str).str.contains("_max_", case=False)
    )
    df = df.loc[~mask_old_nvidia].copy()

    # 解析 FileSpec -> Device/Param/Source/AQ
    info_df = pd.DataFrame(
        list(df["FileSpec"].apply(extract_info)),
        columns=["Device", "Param", "Source", "AQ"],
        index=df.index,
    )
    df[["Device", "Param", "Source", "AQ"]] = info_df

    # 可选：按素材/平台筛选
    if args.sources:
        df = df[df["Source"].isin(args.sources)].copy()
    if args.devices:
        wanted_devices = {normalize_device_name(d) for d in args.devices}
        df = df[df["Device"].isin(wanted_devices)].copy()

    if not args.aq:
        df = df.loc[~df["AQ"].astype(bool)].copy()

    if df.empty:
        raise SystemExit("筛选后没有任何可绘制数据，请检查 --sources / --devices 参数是否正确。")

    # 设置中文字体支持
    plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    output_dir = Path("Results")
    output_dir.mkdir(parents=True, exist_ok=True)

    colors = {"Intel": "#1f77b4", "Nvidia": "#2ca02c", "MAC": "#ff7f0e"}
    target_vmaf = 95

    # 预先为每个 Source 计算并缓存原片码率，并据此得到压缩百分比
    orig_bitrate_map: dict[str, float | None] = {}
    for source in sorted(df["Source"].unique()):
        orig_video = find_original_video(source)
        if orig_video is None:
            print(f"[警告] 找不到原始视频文件（按 {source}.mp4 / .MP4 等尝试），将仅使用码率坐标。")
            orig_bitrate_map[source] = None
            continue

        bitrate = run_ffprobe_bitrate(FFPROBE_BIN, orig_video)
        if bitrate is None:
            print(f"[警告] 无法获取原片码率: {orig_video}")
            orig_bitrate_map[source] = None
        else:
            orig_bitrate_map[source] = bitrate

    df["OrigBitrate"] = df["Source"].map(orig_bitrate_map)
    df["CompressPercent"] = df["Bitrate"] / df["OrigBitrate"] * 100.0

    # 针对每条原视频分别画一张 VMAF vs 码率 折线图
    for source in sorted(df["Source"].unique()):
        sub = df[df["Source"] == source].copy()

        # 复用预先计算好的原片码率 / 压缩百分比
        orig_bitrate = None
        if sub["OrigBitrate"].notna().any():
            orig_bitrate = float(sub["OrigBitrate"].dropna().iloc[0])

        if orig_bitrate:
            sub["CompressPercent"] = sub["Bitrate"] / orig_bitrate * 100.0

        fig, ax = plt.subplots(figsize=(8, 6))

        for device in sub["Device"].unique():
            device_data = sub[sub["Device"] == device].sort_values("Bitrate")
            color = colors.get(device, "#000000")

            # AQ / 非 AQ 分开画（不做混合平均），用线型区分
            for aq_status, grp in device_data.groupby("AQ"):
                grp = grp.sort_values("Bitrate")
                linestyle = "--" if aq_status else "-"
                label = f"{device} (AQ)" if aq_status else device

                x = grp["Bitrate"].values
                y = grp["VMAF-Value"].values

                # 折线 + 点
                ax.plot(
                    x,
                    y,
                    marker="o",
                    linewidth=1.8,
                    linestyle=linestyle,
                    alpha=0.85,
                    color=color,
                    label=label,
                )

                # 在点旁边标注参数；AQ 的点额外标识 (AQ)
                for _, row in grp.iterrows():
                    ann = f"{row['Param']}"
                    if row.get("AQ", False):
                        ann = f"{ann} (AQ)"
                    ax.annotate(
                        ann,
                        (row["Bitrate"], row["VMAF-Value"]),
                        textcoords="offset points",
                        xytext=(4, 4),
                        fontsize=8,
                        alpha=0.7,
                    )

        ax.set_xlabel("码率 (Bitrate)", fontsize=12)
        ax.set_ylabel("VMAF 分数", fontsize=12)
        ax.set_title(f"{source}：VMAF vs 码率", fontsize=14, fontweight="bold")
        ax.legend(fontsize=11)
        ax.grid(True, alpha=0.3)

        # 目标 VMAF 基准线
        ax.axhline(y=target_vmaf, color="red", linestyle="--", linewidth=1.2, alpha=0.8)
        x_min, _ = ax.get_xlim()
        ax.text(
            x_min,
            target_vmaf + 0.2,
            f"VMAF = {target_vmaf}",
            color="red",
            fontsize=9,
            va="bottom",
        )

        # 顶部增加一个横轴，显示“压缩百分比”（码率 / 原码率）
        if orig_bitrate:

            def bitrate_to_percent(x):
                return x / orig_bitrate * 100.0

            def percent_to_bitrate(p):
                return p / 100.0 * orig_bitrate

            secax = ax.secondary_xaxis("top", functions=(bitrate_to_percent, percent_to_bitrate))
            secax.set_xlabel("压缩码率 / 原码率 (%)", fontsize=11)

        plt.tight_layout()
        out_file = output_dir / f"compression_efficiency_{source}.png"
        plt.savefig(out_file, dpi=300, bbox_inches="tight")
        print(f"图表已保存为 {out_file}")

    # 额外绘制一张“总体平均图”：按 平台(Device)+参数(Param)+AQ 聚合后，使用压缩百分比
    fig, ax = plt.subplots(figsize=(8, 6))

    # 仅保留已成功获取原片码率的样本
    df_avg_src = df[df["CompressPercent"].notna()].copy()

    # 先按 Device + Param + AQ 聚合，计算该平台该参数在所有素材上的平均“压缩百分比”和平均 VMAF
    grouped = df_avg_src.groupby(["Device", "Param", "AQ"], as_index=False)[
        ["CompressPercent", "VMAF-Value"]
    ].mean()

    for device in grouped["Device"].unique():
        device_data = grouped[grouped["Device"] == device].sort_values("CompressPercent")
        color = colors.get(device, "#000000")

        # AQ / 非 AQ 分开画（不做混合平均），用线型区分
        for aq_status, grp in device_data.groupby("AQ"):
            linestyle = "--" if aq_status else "-"
            label = f"{device} 平均(按参数聚合) (AQ)" if aq_status else f"{device} 平均(按参数聚合)"

            x = grp["CompressPercent"].values
            y = grp["VMAF-Value"].values

            ax.plot(
                x,
                y,
                marker="o",
                linewidth=2.0,
                alpha=0.9,
                color=color,
                linestyle=linestyle,
                label=label,
            )

    ax.set_xlabel("压缩码率 / 原码率 (%)", fontsize=12)
    ax.set_ylabel("VMAF 分数 (按平台+参数平均)", fontsize=12)
    ax.set_title("总体：VMAF vs 压缩百分比 (同平台同参数取平均)", fontsize=14, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9)

    ax.axhline(y=target_vmaf, color="red", linestyle="--", linewidth=1.2, alpha=0.8)
    x_min, _ = ax.get_xlim()
    ax.text(
        x_min,
        target_vmaf + 0.2,
        f"VMAF = {target_vmaf}",
        color="red",
        fontsize=9,
        va="bottom",
    )

    plt.tight_layout()
    overall_file = output_dir / "compression_efficiency_overall.png"
    plt.savefig(overall_file, dpi=300, bbox_inches="tight")
    print(f"总体平均图已保存为 {overall_file}")


if __name__ == "__main__":
    main()


# 预先为每个 Source 计算并缓存原片码率，并据此得到压缩百分比
