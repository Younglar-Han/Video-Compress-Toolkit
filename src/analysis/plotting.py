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

        # Regex patterns to match filename conventions
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
        
        # Refine device display name
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

        # Augment data
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

        # Filter sources if requested
        if sources:
            clean_df = clean_df[clean_df["Source"].isin(sources)]

        unique_sources = clean_df["Source"].unique()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Plot for each source
        for src in unique_sources:
            subset = clean_df[clean_df["Source"] == src]
            self._plot_single_source(src, subset)

        # Plot overall (if multiple sources)
        if len(unique_sources) > 1:
            self._plot_overall(clean_df)

    def _plot_single_source(self, source: str, df: pd.DataFrame):
        plt.figure(figsize=(10, 6))
        
        devices = df["Device"].unique()
        for dev in devices:
            d = df[df["Device"] == dev].sort_values("Bitrate")
            plt.plot(d["Bitrate"], d["VMAF"], marker='o', label=dev)

        plt.title(f"Compression Efficiency: {source}")
        plt.xlabel("Bitrate (kbps)")
        plt.ylabel("VMAF Score")
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.legend()
        
        # Sanitize filename (replace backslashes/slashes with underscores)
        safe_source = source.replace("\\", "_").replace("/", "_")
        out_path = self.output_dir / f"compression_efficiency_{safe_source}.png"
        plt.savefig(out_path, dpi=100)
        plt.close()
        print(f"Saved plot: {out_path}")

    def _plot_overall(self, df: pd.DataFrame):
        # Calculate average VMAF per device per approximate bitrate bin?
        # Actually, simpler to just plot all points or aggregated trend lines.
        # But since different videos have drastically different bitrates, 
        # a simple scatter plot of everything might be messy but informative.
        # Or better: Normalize bitrate relative to original? We don't have original bitrate here easily.
        # So we'll skip complex aggregation and just do a scatter plot for now.
        
        plt.figure(figsize=(12, 8))
        
        devices = df["Device"].unique()
        for dev in devices:
            d = df[df["Device"] == dev]
            plt.scatter(d["Bitrate"], d["VMAF"], alpha=0.5, label=dev)

        plt.title("Overall Compression Efficiency (All Sources)")
        plt.xlabel("Bitrate (kbps)")
        plt.ylabel("VMAF Score")
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.legend()

        out_path = self.output_dir / "compression_efficiency_overall.png"
        plt.savefig(out_path, dpi=100)
        plt.close()
        print(f"Saved plot: {out_path}")
