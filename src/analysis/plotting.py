import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as font_manager
import re
from pathlib import Path
from typing import List, Optional

class EfficiencyPlotter:
    def __init__(self, csv_path: Path, output_dir: Path):
        self.csv_path = csv_path
        self.output_dir = output_dir
        self._configure_fonts()

    def _configure_fonts(self):
        """配置中文字体，避免图表中文缺失。"""
        preferred_fonts = [
            "PingFang SC",
            "Heiti SC",
            "Songti SC",
            "Arial Unicode MS",
            "DejaVu Sans",
        ]
        available_fonts = {font.name for font in font_manager.fontManager.ttflist}
        selected_fonts = [font for font in preferred_fonts if font in available_fonts]
        if not selected_fonts:
            selected_fonts = ["DejaVu Sans"]

        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["font.sans-serif"] = selected_fonts
        plt.rcParams["axes.unicode_minus"] = False

    def extract_info(self, filename: str):
        """
        提取设备、参数、来源、AQ 标记
        """
        stem = Path(filename).stem

        aq = False
        if stem.endswith("_aq"):
            aq = True
            stem = re.sub(r"_aq$", "", stem)

        device = "未知"
        param_value = 0
        source = stem
        mode = "未知"

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
            print(f"错误: 未找到 CSV 文件 {self.csv_path}。")
            return

        print("正在加载数据...")
        try:
            df = pd.read_csv(self.csv_path, sep="\t")
        except Exception as e:
            print(f"读取 CSV 失败: {e}")
            return

        # 扩充数据
        data_rows = []
        for _, row in df.iterrows():
            fspec = row["FileSpec"]
            device, param, source, aq = self.extract_info(fspec)
            if device != "未知":
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
            print("未解析到有效数据。")
            return

        # 根据参数过滤源
        if sources:
            clean_df = clean_df[clean_df["Source"].isin(sources)]

        unique_sources = clean_df["Source"].unique()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 为每个源绘图
        for src in unique_sources:
            subset = clean_df[clean_df["Source"] == src]
            self._plot_single_source(src, subset)

        # 绘制整体图表（多个源时）
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

        plt.title(f"压缩效率: {source}")
        plt.xlabel("码率 (kbps)")
        plt.ylabel("VMAF 分数")
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.legend()
        
        # 清理文件名（将反斜杠/斜杠替换为下划线）
        safe_source = source.replace("\\", "_").replace("/", "_")
        out_path = self.output_dir / f"compression_efficiency_{safe_source}.png"
        plt.savefig(out_path, dpi=300)
        plt.close()
        print(f"已保存图表: {out_path}")

    def _plot_overall(self, df: pd.DataFrame):
        # 由于不同视频的比特率差异较大，这里使用散点图展示整体分布
        
        plt.figure(figsize=(12, 8))
        
        devices = df["Device"].unique()
        for dev in devices:
            d = df[df["Device"] == dev]
            color = self._get_color(dev)
            plt.scatter(d["Bitrate"], d["VMAF"], alpha=0.5, label=dev, color=color)

        plt.title("整体压缩效率（所有源）")
        plt.xlabel("码率 (kbps)")
        plt.ylabel("VMAF 分数")
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.legend()

        out_path = self.output_dir / "compression_efficiency_overall.png"
        plt.savefig(out_path, dpi=300)
        plt.close()
        print(f"已保存图表: {out_path}")
