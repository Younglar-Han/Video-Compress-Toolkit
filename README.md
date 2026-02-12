# Video Compress Toolkit

一个面向实战的视频工具箱：**硬件加速压缩 + VMAF 质量评估 + 压缩效率绘图**。

支持编码器：
- Intel QSV (`hevc_qsv`)
- Nvidia NVENC (`hevc_nvenc`)
- macOS VideoToolbox (`hevc_videotoolbox`)

统一入口：`main.py`

---

## 功能概览

- `compress`：普通压缩（单文件 / 目录递归），默认 80% 体积限制回退。
- `batch`：参数扫描批量压缩，自动生成可分析/可绘图的文件名。
- `smart`：智能压缩调度（1 个压缩线程 + 多个 VMAF 线程），以目标 VMAF + 体积上限为停止条件。
- `analyze`：批量计算 VMAF 与码率，输出 TSV（制表符分隔 CSV）。
- `plot`：基于分析结果绘制压缩效率图（单源与总体图）。

---

## 环境要求

- Python 3.9+
- FFmpeg / FFprobe
  - 需支持对应硬件编码器（`hevc_qsv` / `hevc_nvenc` / `hevc_videotoolbox`）
  - **VMAF 功能要求 FFmpeg 启用 `libvmaf`**
- Python 依赖：

```bash
pip install pandas matplotlib
```

> `analyze` 与 `smart` 依赖 VMAF；若 `ffmpeg -filters` 中没有 `libvmaf`，会出现告警并导致 VMAF 计算失败。

---

## 快速开始

查看帮助：

```bash
python main.py -h
```

### 1) 普通压缩

```bash
# 单文件
python main.py compress input.mp4 output.mp4 --encoder mac

# 目录递归压缩
python main.py compress Videos Compressed --encoder nvidia
```

说明：
- `compress` 默认体积上限 `0.8`（80%）。
- 若压缩后体积比例大于上限，会自动回退为原视频。

### 2) 智能压缩

```bash
python main.py smart Videos Compressed_smart --encoder mac
```

可选参数：
- `--vmaf-target`：目标 VMAF，默认 `95.0`
- `--size-limit`：体积上限，默认 `0.8`

### 3) 批量参数测试

```bash
# Nvidia: QP 19~30
python main.py batch --source Videos --output Results/NVENC --encoder nvidia --start 19 --end 30

# Intel: global_quality 18~25
python main.py batch --source Videos --output Results/Intel --encoder intel --start 18 --end 25

# Mac: q:v 50~70
python main.py batch --source Videos --output Results/MAC --encoder mac --start 50 --end 70
```

### 4) 批量 VMAF 分析

```bash
python main.py analyze \
  --ref-dir Videos \
  --comp-dirs Results/NVENC Results/Intel Results/MAC \
  --output Results/scores.csv \
  --jobs 4
```

### 5) 绘图

```bash
python main.py plot --csv Results/scores.csv --output-dir Results/Plots
```

---

## 命令参数（与当前实现一致）

### `compress`

```bash
python main.py compress <input> <output> --encoder {intel,nvidia,mac} [--quality N] [--force]
```

- `input`：输入文件或目录
- `output`：输出文件或目录
- `--quality`：编码质量参数（可选）
- `--force`：覆盖已存在文件

### `batch`

```bash
python main.py batch --source Videos --output <dir> --encoder {intel,nvidia,mac} --start N --end N [--force]
```

- `--source` 默认 `Videos`
- 非递归扫描，仅处理源目录顶层（默认仅 `.mp4`）

### `analyze`

```bash
python main.py analyze [--ref-dir Videos] [--comp-dirs ...] [--output Results/FFMetrics.Results.csv] [--ffmpeg ffmpeg] [--ffprobe ffprobe] [--jobs 1] [--use-neg-model]
```

默认 `--comp-dirs`：
- `QSV_Compressed`
- `NVENC_Compressed`
- `NVENC_QP_Compressed`
- `MAC_Compressed`

### `smart`

```bash
python main.py smart [input=Videos] [output=Compressed_smart] --encoder {intel,nvidia,mac} [--vmaf-target 95.0] [--size-limit 0.8] [--force]
```

### `plot`

```bash
python main.py plot [--csv Results/FFMetrics.Results.csv] [--output-dir Results] [--sources ...]
```

---

## 智能压缩关键行为（重要）

`smart` 使用 `SmartScheduler`，行为如下：

1. 初始质量从“更差质量、更小体积”起步（推荐值 ±1）
   - Mac（`quality_step > 0`）：起点 `default_quality - 1`，逐步 `+1`
   - Intel / Nvidia（`quality_step < 0`）：起点 `default_quality + 1`，逐步 `-1`
2. 每轮先压缩，再做体积检查，再做 VMAF 评估。
3. 若体积比例 `> size_limit`：**立即放弃压缩结果，回退原视频**。
4. 若 VMAF 达到目标：保存当前压缩结果并停止。
5. 若未达目标但体积合规：保留 best-effort，继续提升质量；到达边界后返回 best-effort。

---

## 文件命名规则（与绘图兼容）

批量压缩输出文件名后缀必须符合：

- Intel：`_intel_q{quality}`
- Nvidia：`_nvidia_qp{qp}`
- Mac：`_mac_qv{q}`

示例：
- `demo_intel_q25.mp4`
- `demo_nvidia_qp24.mp4`
- `demo_mac_qv58.mp4`

这些规则由 `src/utils/naming.py` 统一维护，并被 `batch` / `analyze` / `plot` 共同使用。

---

## VMAF 模型自动选择

`VMAFAnalyzer.calculate_vmaf()` 会按**参考视频分辨率**自动选择模型：

- 像素总数 `< 3840×2160`：`vmaf_v0.6.1`（或 NEG 版本）
- 像素总数 `>= 3840×2160`：`vmaf_4k_v0.6.1`（或 NEG 版本）

启用 NEG 模型：`--use-neg-model`

---

## 输出文件说明

- `analyze` 输出为制表符分隔文件（TSV），列名：
  - `FileSpec`
  - `VMAF-Value`
  - `Bitrate`
- `plot` 在输出目录生成：
  - 单源图：`compression_efficiency_<source>.png`
  - 总体图（多源时）：`compression_efficiency_overall.png`

---

## 项目结构

```text
.
├── main.py
├── src/
│   ├── analysis/
│   │   ├── plotting.py
│   │   └── vmaf.py
│   ├── core/
│   │   ├── compressor.py
│   │   └── scheduler.py
│   ├── encoders/
│   │   ├── base.py
│   │   ├── intel.py
│   │   ├── nvidia.py
│   │   └── mac.py
│   └── utils/
│       ├── file_ops.py
│       ├── naming.py
│       └── console.py
└── README.md
```

---

## 常见问题

### 1) 找不到硬件编码器

检查：

```bash
ffmpeg -codecs | grep -E "hevc_qsv|hevc_nvenc|hevc_videotoolbox"
```

### 2) VMAF 计算失败

检查 FFmpeg 是否包含 `libvmaf`：

```bash
ffmpeg -filters | grep libvmaf
```

### 3) 为什么 batch 没扫到某些视频

当前默认只匹配 `.mp4`，且 `batch` 为非递归扫描。

