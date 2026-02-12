"""文件命名与解析工具。

本模块用于集中管理“压缩输出文件名后缀”的规则，确保与分析/绘图模块的正则兼容。

硬规则（绘图兼容）：
- Intel: _intel_q{quality}
- Nvidia: _nvidia_qp{qp}
- Mac: _mac_qv{q}
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


# 兼容历史遗留后缀：nvidia_qmax、qsv_、mac_ 等在 plotting/vmaf 中仍可能出现。
_PARAM_SUFFIX_RE = re.compile(
    r"_(intel_q\d+|qsv_\d+|nvidia_qmax\d+|max_\d+|nvidia_qp\d+(_aq)?|mac_qv\d+|mac_\d+)$"
)


def strip_param_suffix(stem: str) -> str:
    """去除文件名 stem 中的编码参数后缀。

    例如：
    - "demo_intel_q25" -> "demo"
    - "demo_nvidia_qp24" -> "demo"
    - "demo_mac_qv58" -> "demo"
    """

    return _PARAM_SUFFIX_RE.sub("", stem)


def build_param_suffix(encoder_name: str, quality: int) -> str:
    """构造与绘图模块兼容的参数后缀。"""

    if encoder_name == "intel":
        return f"_intel_q{quality}"
    if encoder_name == "mac":
        return f"_mac_qv{quality}"
    if encoder_name == "nvidia":
        return f"_nvidia_qp{quality}"
    raise ValueError(f"未知编码器: {encoder_name}")


@dataclass(frozen=True)
class OutputName:
    """输出文件名构造结果。"""

    filename: str
    suffix: str


def build_output_filename(input_file: Path, encoder_name: str, quality: int) -> OutputName:
    """基于输入文件生成带参数后缀的输出文件名（保持扩展名不变）。"""

    suffix = build_param_suffix(encoder_name, quality)
    return OutputName(filename=f"{input_file.stem}{suffix}{input_file.suffix}", suffix=suffix)
