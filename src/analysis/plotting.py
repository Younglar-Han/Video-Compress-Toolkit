import pandas as pd
import matplotlib.pyplot as plt
import re
from pathlib import Path
from typing import List, Optional

class EfficiencyPlotter:
    def __init__(self, csv_path: Path, output_dir: Path):
        self.csv_path = csv_path
        self.output_dir = output_dir

    def extract_info(self, filename: str):
        """
        Device, Param, Source, AQ
        """
        stem = Path(filename).stem

        aq = False
        if stem.endswith("_aq"):
            aq = True
            stem = re.sub(r"_aq$", "", stem)

        device = "Unknown"
        param_value = 0
        source = stem
        mode = "Unknown"

        # 匹配文件名约定的正则模式
        patterns = [
            ("Intel", "qsv", r"^(?P<source>.+)_intel_q(?P<param>\d+)$"),
            ("Intel", "qsv", r"^(?P<source>.+)_qsv_(?P<param>\d+)$"),
            ("Nvidia", "qmax", r"^(?P<source>.+)_nvidia_qmax(?P<param>\d+)$"),
            ("Nvidia", "qmax", r"^(?P<source>.+)_max_(?P<param>\d+)$"),
            ("Nvidia", "constqp", r"^(?P<source>.+)_nvidia_qp(?P<param>\d+)$"),
            ("MAC", "videotoolbox", r"^(?P<source>.+)_mac_qv(?P<param>\d+)$"),
            ("MAC", "videotoolbox", r"^(?P<source>.+)_mac_(?P<param>\d+)$"),
        ]

        for dev, m, pat in patterns:
            match = re.match(pat, stem)
            if match:
                device = dev
                mode = m
                param_value = int(match.group("param"))
                source = match.group("source")
                break
        
        # 优化设备显示名称
        if device == "Nvidia":
            if mode == "qmax":
                device = "Nvidia (qmax)"
            elif mode == "constqp":
                if aq:
                    device = "Nvidia (QP+AQ)"
                else:
                    device = "Nvidia (QP)"

        return device, param_value, source, aq

    def plot(self, sources: Optional[List[str]] = None):
        if not self.csv_path.exists():
            print(f"Error: CSV file {self.csv_path} not found.")
            return

        print("Loading data...")
        try:
            df = pd.read_csv(self.csv_path, sep="\t")
        except Exception as e:
            print(f"Error reading CSV: {e}")
            return

        # 扩充数据
        data_rows = []
        for _, row in df.iterrows():
            fspec = row["FileSpec"]
            device, param, source, aq = self.extract_info(fspec)
            if device != "Unknown":
                data_rows.append({
                    "Device": device,
                    "Param": param,
                    "Source": source,
                    "VMAF": row["VMAF-Value"],
                    "Bitrate": row["Bitrate"],
                    "AQ": aq
                })
        
        clean_df = pd.DataFrame(data_rows)
        if clean_df.empty:
            print("No valid data parsed.")
            return

        # 如果请求则过滤源
        if sources:
            clean_df = clean_df[clean_df["Source"].isin(sources)]

        unique_sources = clean_df["Source"].unique()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 为每个源绘图
        for src in unique_sources:
            subset = clean_df[clean_df["Source"] == src]
            self._plot_single_source(src, subset)

        # 绘制整体图表（如果有多个源）
        if len(unique_sources) > 1:
            self._plot_overall(clean_df)

    def _get_color(self, device_name: str) -> Optional[str]:
        """返回对应设备的固定颜色"""
        dev_lower = device_name.lower()
        if "nvidia" in dev_lower:
            return "tab:green"
        elif "intel" in dev_lower:
            return "tab:blue"
        elif "mac" in dev_lower:
            return "tab:orange"
        return None

    def _plot_single_source(self, source: str, df: pd.DataFrame):
        plt.figure(figsize=(10, 6))
        
        devices = df["Device"].unique()
        for dev in devices:
            d = df[df["Device"] == dev].sort_values("Bitrate")
            color = self._get_color(dev)
            
            # 绘制线条和点
            plt.plot(d["Bitrate"], d["VMAF"], marker='o', label=dev, color=color)
            
            # 标注质量参数
            for _, row in d.iterrows():
                plt.text(
                    row["Bitrate"], 
                    row["VMAF"], 
                    str(row["Param"]), 
                    fontsize=9, 
                    color=color,
                    weight='bold',
                    ha='right', 
                    va='bottom'
                )

        plt.title(f"Compression Efficiency: {source}")
        plt.xlabel("Bitrate (kbps)")
        plt.ylabel("VMAF Score")
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.legend()
        
        # 清理文件名（将反斜杠/斜杠替换为下划线）
        safe_source = source.replace("\\", "_").replace("/", "_")
        out_path = self.output_dir / f"compression_efficiency_{safe_source}.png"
        plt.savefig(out_path, dpi=100)
        plt.close()
        print(f"Saved plot: {out_path}")

    def _plot_overall(self, df: pd.DataFrame):
        # 计算每个设备在近似比特率区间的平均 VMAF？
        # 实际上，只绘制所有点或聚合趋势线更简单。
        # 但由于不同视频的比特率差异巨大，
        # 简单的散点图虽然可能混乱，但能提供信息。
        # 或者更好：相对于原始比特率归一化？我们这里不容易获取原始比特率。
        # 所以我们跳过复杂的聚合，目前只做散点图。
        
        plt.figure(figsize=(12, 8))
        
        devices = df["Device"].unique()
        for dev in devices:
            d = df[df["Device"] == dev]
            color = self._get_color(dev)
            plt.scatter(d["Bitrate"], d["VMAF"], alpha=0.5, label=dev, color=color)

        plt.title("Overall Compression Efficiency (All Sources)")
        plt.xlabel("Bitrate (kbps)")
        plt.ylabel("VMAF Score")
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.legend()

        out_path = self.output_dir / "compression_efficiency_overall.png"
        plt.savefig(out_path, dpi=100)
        plt.close()
        print(f"Saved plot: {out_path}")
