# Copilot Instructions for Video Compress Toolkit

Python 工具箱：FFmpeg 硬件加速批量压缩 + VMAF 质量评估 + 效率曲线绘图。

## Big Picture
- 统一入口 CLI：`main.py`，核心实现都在 `src/`。
- 编码器策略：`src/encoders/`（接口见 `src/encoders/base.py`；实现：intel/nvidia/mac）。
- 智能压缩调度器：`src/core/scheduler.py`（1 个压缩线程 + 多个 VMAF 分析线程；反馈式调参）。`main.py smart` 走这条链路。
- VMAF：`src/analysis/vmaf.py`（ffprobe 探测 + ffmpeg/libvmaf 计算 + 批量并发）。
- 绘图：`src/analysis/plotting.py` 通过“文件名后缀正则”解析设备/参数。

## Hard Rules (Project-specific)
- 注释和 docstring 必须使用中文。
- 路径统一用 `pathlib.Path`；仅在 `subprocess` 参数里转 `str(path)`。
- 关键阶段日志前要先空行：`print("")`（压缩开始/结束、VMAF 开始/结束）。

## File Naming (Plotting compatibility)
批量压缩生成的文件名后缀必须匹配 `src/analysis/plotting.py` 的正则（否则 plot/分析解析不到参数）：
- Intel: `_intel_q{quality}`
- Nvidia: `_nvidia_qp{qp}`
- Mac: `_mac_qv{q}`

## Smart Compression (Critical behavior)
- 起点与步长：从“更差质量/更小体积”的推荐值 ±1 开始，按 `encoder.quality_step` 逐步提高质量。
  - Mac（`quality_step>0`）：start `default-1`，step `+1`；Intel/Nvidia：start `default+1`，step `-1`。
- 体积上限严格：默认 `size_limit=0.8`，一旦超过立即放弃并回退到原视频（见 `src/core/scheduler.py`）。
- VMAF 目标默认 `95.0`，达到即停止并保留当前压缩结果。

## VMAF Model Selection (Auto)
`VMAFAnalyzer.calculate_vmaf()` 会按参考视频分辨率自动选模型（见 `src/analysis/vmaf.py`）：
- `< 3840*2160`：`version=vmaf_v0.6.1`（或 `...neg`）
- `>= 3840*2160`：`version=vmaf_4k_v0.6.1`（或 `...neg`）
统一查询接口：`get_vmaf_model_selection(ref_file, use_neg_model=False)` 返回 `(resolution, model_str)`；日志分辨率格式用 `format_resolution_for_log(...)`。

## Workflows
- 依赖：Python 3.9+；FFmpeg 必须启用 `libvmaf`（否则 VMAF 会失败）；绘图依赖 `pandas`、`matplotlib`（见 `README.md`）。
- 常用命令（都在 `main.py`）：
  - `python main.py compress ...`
  - `python main.py batch ...`
  - `python main.py analyze ... --use-neg-model`
  - `python main.py smart ...`
  - `python main.py plot ...`

## Adding an Encoder
1) 继承 `BaseEncoder` 实现 `get_ffmpeg_args`、`name`、`default_quality`、`quality_step`、`quality_range`。
2) 在 `src/encoders/__init__.py` 注册到 `get_encoder()`。
