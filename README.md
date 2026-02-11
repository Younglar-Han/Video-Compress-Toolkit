# Video Compress Toolkit

本项目是一套基于 FFmpeg 搭建的 **视频压缩 + 画质评估 + 可视化分析** 工具箱。支持 Intel QSV、NVIDIA NVENC、macOS VideoToolbox 多平台硬件编码，并提供 VMAF 批量画质评估与压缩效率可视化功能。

代码已经完全重构，统一入口，模块化设计，更加易用。

## 核心功能

1.  **多平台压缩**：支持 Intel, Nvidia, Mac 硬件加速编码。
2.  **批量测试**：一键生成不同参数（QP/CRF/Bitrate）下的压缩样本。
3.  **画质评估**：批量计算 VMAF 分数。
4.  **可视化**：生成压缩效率曲线（VMAF vs Bitrate）。

## 快速开始

### 1. 环境准备

- Python 3.8+
- FFmpeg (需支持对应的硬件编码器，如 `hevc_nvenc`, `hevc_qsv`, `hevc_videotoolbox`)
  - 建议安装完整版 FFmpeg，包含 `libvmaf` 支持。
- Python 依赖:
  ```bash
  pip install pandas matplotlib
  ```

### 2. 统一入口 `main.py`

所有功能均通过 `python main.py` 调用。

查看帮助：
```bash
python main.py -h
```

### 3. 命令详解与示例

#### 1. Compress 命令 (普通压缩 / 递归压缩)

用于压缩单个文件，或者递归压缩整个目录下的所有视频。

**参数说明**：
- `input`: 输入文件路径或文件夹路径
- `output`: 输出文件路径或文件夹路径
- ` --encoder`: 编码器 (`intel`, `nvidia`, `mac`)
- `--quality`: 质量参考值 (Nvidia=QP, Intel=GlobalQuality, Mac=q:v)

**示例**：
```bash
# macOS 递归压缩 Videos 目录到 Compressed 目录
# 推荐质量参数：q:v 58 (范围推荐 50-70)
python main.py compress Videos Compressed --encoder mac --quality 58

# Nvidia 递归压缩
# 推荐质量参数：QP 24 (范围推荐 19-30, 值越小画质越好体积越大)
python main.py compress Videos Compressed --encoder nvidia --quality 24

# Intel 递归压缩
# 推荐质量参数：Global Priority 21 (范围推荐 18-25)
python main.py compress Videos Compressed --encoder intel --quality 21
```

#### 2. Batch 命令 (批量参数测试)

专用于压缩测试。会自动在指定范围内（start 到 end）生成所有参数的样本。
生成的视频文件名会自动带上参数后缀（如 `_nvidia_qp24.mp4`），以便后续自动分析。

**参数说明**：
- `--source`: 源视频目录（不递归，仅扫描根目录 .mp4）
- `--output`: 输出目录
- `--encoder`: 编码器
- `--start`: 参数起始值
- `--end`: 参数结束值 (包含)

**示例**：
```bash
# Nvidia 批量生成 QP 19 到 QP 30 的所有样本
python main.py batch --source Videos --output Results/NVENC --encoder nvidia --start 19 --end 30

# macOS 批量生成 q:v 50 到 70 的所有样本
python main.py batch --source Videos --output Results/MAC --encoder mac --start 50 --end 70

# Intel 批量生成 Quality 18 到 25 的所有样本
python main.py batch --source Videos --output Results/Intel --encoder intel --start 18 --end 25
```

#### 3. Analyze 命令 (计算 VMAF)

计算压缩视频的 VMAF 分数（Netflix 开源的感知画质指标）。
它会自动扫描 `--comp-dirs` 里的视频，尝试在 `--ref-dir` 中找到对应的原片进行对比。

**参数说明**：
- `--ref-dir`: 原始无损视频目录
- `--comp-dirs`: 包含压缩视频的目录列表（可传多个）
- `--output`: 结果 CSV 路径
- `--jobs`: 并行处理数（推荐等于 CPU 核数）

**示例**：
```bash
# 扫描 NVENC Intel MAC 目录，与 Videos 里的原片对比
python main.py analyze --ref-dir Videos --comp-dirs Results/NVENC Results/Intel Results/MAC --output Results/scores.csv --jobs 4
```

#### 4. Plot 命令 (绘制图表)

读取 Analyze 生成的 CSV，画出 **VMAF vs Bitrate** 的效率曲线图。越靠左上角的曲线效率越高（同样的码率画质更好，或者同样的画质码率更低）。

**参数说明**：
- `--csv`: 输入的 CSV 文件路径
- `--output-dir`: 图表输出目录

**示例**：
```bash
python main.py plot --csv Results/scores.csv --output-dir Results/Plots
```

## 目录结构说明

```
.
├── main.py                 # 统一入口脚本
├── src/                    # 源代码包
│   ├── analysis/           # 分析模块 (VMAF, Plotting)
│   ├── core/               # 核心压缩逻辑
│   ├── encoders/           # 编码器实现 (Intel, Nvidia, Mac)
│   └── utils/              # 工具函数
├── Videos/                 # (建议) 存放原始视频
└── Results/                # (建议) 存放结果与图表
```

## 不再需要的旧脚本
旧的 `batch_*.py`, `test_vmaf_scores.py`, `plot_compression_efficiency.py` 等功能已全部整合进 `main.py`，可以使用 `main.py` 替代它们。

## 常见问题

- **找不到编码器？**
  请确保 `ffmpeg -CODECS` 能看到 `hevc_nvenc` (Nvidia), `hevc_qsv` (Intel), 或 `hevc_videotoolbox` (Mac)。
- **VMAF 计算失败？**
  请确保你的 ffmpeg 编译时开启了 `--enable-libvmaf`。

## 关于 Nvidia 编码模式

**已移除 `qmax` 模式**：
本项目移除了基于 `qmax` 的 Nvidia 编码模式。
**原因**：在 NVENC 中，当设置了固定的目标质量（例如 `-cq 27`）后，`qmax` 参数仅作为 QP 的上限（Ceiling）。如果 `qmax` 大于目标 CQ 值，实际上不会对编码结果产生任何影响（因为编码器已经满足了 CQ 要求）。只有当 `qmax` 小于目标 CQ 时才会生效，但这违背了“质量控制”的初衷。因此，使用固定 QP (`constqp`) 模式是控制和测试 NVENC 编码质量更有效、直接的方法。且 `cq` 模式由于未知的原因经常失效，不论 `cq` 设置多少，实际 `q` 值都在30左右，导致压缩效果很差。

**已移除 AQ (Adaptive Quantization) 模式**：
**原因**：经过实测，在当前测试环境下，开启 Spatial AQ 或 Temporal AQ 后，在同等参数下压缩效率（Size/Quality ratio）并未提升，甚至在某些情况下表现更差。为了保持工具简洁，移除了对 AQ 参数的支持，默认使用 NVENC 的标准 `constqp` 模式。
