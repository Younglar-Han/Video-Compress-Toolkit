# Video Compress Toolkit

本项目是一套基于 FFmpeg 搭建的 **视频压缩 + 画质评估 + 可视化分析** 工具。支持批量视频压缩，支持 Intel QSV、NVIDIA NVENC、macOS VideoToolbox 多平台，并用 VMAF 指标统一比较不同平台与参数下的压缩效率。

## 快速开始

### 压缩效率测试
1. 准备原始视频到 `Videos/` 目录
2. 使用批量压缩脚本在不同平台、不同参数下生成压缩结果
3. 运行 VMAF 批量计算脚本，生成/更新 `Results/FFMetrics.Results.csv`
4. 运行绘图脚本，在 `Results/` 目录下生成各素材和总体的对比图

### 递归压缩日常使用
1. 准备原始视频到 `CompressScript/` 目录
2. 运行递归压缩脚本 `compress_video.py`，将压缩结果输出到 `Compressed/` 目录

---

## 目录结构约定

- `Videos/`：原始视频目录（手动创建并放入待测试的 `.mp4` 文件）
- `QSV_Compressed/`：Intel QSV 批量压缩输出
- `NVENC_Compressed/`：NVIDIA NVENC qmax 批量压缩输出
- `NVENC_QP_Compressed/`：NVIDIA NVENC constqp(QP) 批量压缩输出
- `NVENC_QP_AQ_Compressed/`：NVIDIA NVENC constqp(QP) + AQ 批量压缩输出
- `MAC_Compressed/`：macOS VideoToolbox 批量压缩输出
- `Compressed/`：`compress_video.py` 递归压缩脚本的默认输出根目录
- `Results/FFMetrics.Results.csv`：VMAF 计算结果（TSV 格式）
- `Results/compression_efficiency_*.png`：每个素材的压缩效率曲线图
- `Results/compression_efficiency_overall.png`：总体平均压缩效率对比图

> 说明：`Videos/` 与 `Results/` 目录需要你根据需要自己创建；压缩输出目录会在脚本运行时自动创建。

---

## 运行环境与依赖

- 操作系统：
  - macOS：可运行 macOS 批量压缩、递归压缩、VMAF 计算与绘图
  - Windows / Linux + Intel/NVIDIA：可运行对应平台的批量压缩脚本
- 必备软件：
  - `ffmpeg`：需编译支持：
    - macOS: `hevc_videotoolbox`
    - Intel: `hevc_qsv`
    - NVIDIA: `hevc_nvenc`
  - `ffprobe`：用于获取视频码率
  - `libvmaf`：ffmpeg 中需内置 VMAF 滤镜
- Python 依赖（建议放在虚拟环境/conda 环境中）：
  - `pandas`
  - `matplotlib`
  

---

## 各脚本功能说明

### 1. 批量压缩脚本（单层目录扫描）

#### 1.1 Intel：`batch_intel_qsv_gq.py`

- 功能：
  - 使用 Intel QSV (`hevc_qsv`) 按不同 `global_quality` 对 `Videos/` 下的 `.mp4` 批量压缩
- 默认行为：
  - 源目录：`./Videos`（不递归子目录）
  - 输出目录：`./QSV_Compressed`
  - 质量范围：`gq = 18 ~ 25`
  - 输出命名：`<原文件名>_intel_q<gq>.mp4`
- 示例用法：
  ```bash
  python batch_intel_qsv_gq.py \
    --source-dir ./Videos \
    --output-dir ./QSV_Compressed \
    --gq-min 18 --gq-max 25
  ```

#### 1.2 NVIDIA（qmax 扫描）：`batch_nvidia_qmax.py`

- 功能：
  - 使用 NVIDIA NVENC (`hevc_nvenc`) 按不同 `qmax` 对 `Videos/` 下的 `.mp4` 批量压缩
- 默认行为：
  - 源目录：`./Videos`
  - 输出目录：`./NVENC_Compressed`
  - 参数范围：`qmax = 25 ~ 32`
  - 其它固定参数：`preset=p7, multipass=fullres, cq=27, qmin=0`
  - 输出命名：`<原文件名>_nvidia_qmax<qmax>.mp4`
- 示例用法：
  ```bash
  python batch_nvidia_qmax.py \
    --source-dir ./Videos \
    --output-dir ./NVENC_Compressed \
    --qmax-min 25 --qmax-max 32
  ```

#### 1.3 NVIDIA（constqp / QP 扫描）：`batch_nvidia_constqp.py`

- 功能：
  - 使用 NVIDIA NVENC `-rc constqp`，按不同 `QP` 对 `Videos/` 下的 `.mp4` 批量压缩
  - 适合做“恒定质量”测试，不同素材在同一 QP 下主观质量接近
- 默认行为：
  - 源目录：`./Videos`
  - 输出目录：`./NVENC_QP_Compressed`
  - 参数范围：`QP = 25 ~ 32`
  - 其它固定参数：`-rc constqp -preset p7 -multipass fullres`
  - 输出命名：`<原文件名>_nvidia_qp<QP>.mp4`
- 示例用法：
  ```bash
  python batch_nvidia_constqp.py \
    --source-dir ./Videos \
    --output-dir ./NVENC_QP_Compressed \
    --qp-min 25 --qp-max 32
  ```

#### 1.4 macOS（VideoToolbox）：`batch_mac_qv.py`

- 功能：
  - 使用 macOS VideoToolbox (`hevc_videotoolbox`)，按不同 `-q:v` 对 `Videos/` 下的 `.mp4` 批量压缩
- 默认行为：
  - 源目录：`./Videos`
  - 输出目录：`./MAC_Compressed`
  - 参数范围：`q:v = 54 ~ 75`（数值越大质量越高、体积越大）
  - 输出命名：`<原文件名>_mac_qv<qv>.mp4`
- 示例用法：
  ```bash
  python batch_mac_qv.py \
    --source-dir ./Videos \
    --output-dir ./MAC_Compressed \
    --qv-min 54 --qv-max 75
  ```

---

#### 1.5 NVIDIA（constqp / QP 扫描 + AQ）：`batch_nvidia_constqp_aq.py`

- 功能：
  - 在 `batch_nvidia_constqp.py` 的基础上，支持启用 NVENC 的 AQ：`-spatial-aq` / `-temporal-aq` / `-aq-strength`
- 默认行为：
  - 源目录：`./Videos`
  - 输出目录默认：`./NVENC_QP_Compressed`
  - 当启用 AQ 且用户未显式指定 `--output-dir` 时，脚本会自动切换输出到：`./NVENC_QP_AQ_Compressed`
  - 输出命名：
    - 未启用 AQ：`<原文件名>_nvidia_qp<QP>.mp4`
    - 启用 AQ：`<原文件名>_nvidia_qp<QP>_aq.mp4`
- 示例用法：
  ```bash
  python batch_nvidia_constqp_aq.py \
    --source-dir ./Videos \
    --qp-min 25 --qp-max 32 \
    --spatial-aq --aq-strength 8 --temporal-aq
  ```

### 2. 递归压缩脚本：`compress_video.py`

- 功能：
  - 递归遍历 `source-root` 下的所有 `.mp4`，根据指定的硬件模式（Intel / NVIDIA / macOS）进行压缩，并在 `target-root` 下镜像目录结构
  - 如果压缩后文件比原片还大，会自动用原片替换，避免“越压越大”的情况
- 默认行为：
  - 模式：`mac`（VideoToolbox）
  - 源根目录：`./Videos`
  - 目标根目录：`./Compressed`
- 示例用法：
  ```bash
  # 递归压缩 Videos 到 Compressed，使用 macOS VideoToolbox
  python compress_video.py \
    --mode mac \
    --source-root ./Videos \
    --target-root ./Compressed

  # Windows/Intel 平台，使用 QSV 递归压缩
  python compress_video.py --mode intel --source-root ./Videos --target-root ./Compressed_QSV

  # NVIDIA 平台，使用 NVENC
  python compress_video.py --mode nvidia --source-root ./Videos --target-root ./Compressed_NVENC
  ```

---

### 3. VMAF 批量计算脚本：`test_vmaf_scores.py`

- 功能：
  - 批量计算各个平台、各参数下的压缩视频相对于原片的 VMAF 分数和码率，并输出到 `Results/FFMetrics.Results.csv`
  - 支持并行计算、增量更新（自动跳过 CSV 中已存在的结果）、可选 neg 模型
- 依赖前提：
  - 原片在 `./Videos` 中，压缩结果在以下一个或多个目录中：
    - `QSV_Compressed/`  （Intel）
    - `NVENC_Compressed/`  （NVIDIA qmax）
    - `NVENC_QP_Compressed/`（NVIDIA constqp）
    - `NVENC_QP_AQ_Compressed/`（NVIDIA constqp + AQ）
    - `MAC_Compressed/`   （macOS）
  - 文件命名规则：
    - Intel：`<原文件名>_intel_q<数值>.mp4`
    - NVIDIA qmax：`<原文件名>_nvidia_qmax<数值>.mp4`
    - NVIDIA constqp：`<原文件名>_nvidia_qp<数值>.mp4`
    - NVIDIA constqp + AQ：`<原文件名>_nvidia_qp<数值>_aq.mp4`
    - macOS：`<原文件名>_mac_qv<数值>.mp4`
- 主要特性：
  - 自动检测压缩目录：未指定 `--comp-dirs` 时，会自动从当前目录中启用存在的 `QSV_Compressed`、`NVENC_Compressed`、`NVENC_QP_Compressed`、`NVENC_QP_AQ_Compressed`、`MAC_Compressed`、`Compressed`
  - 用 `ffprobe` 获取每个压缩文件的平均码率（kbps）
  - 用 `ffmpeg + libvmaf` 计算 VMAF 分数，支持可选 neg 模型：`--use-neg-model`
  - 结果写入 `Results/FFMetrics.Results.csv`（TSV：`FileSpec`, `VMAF-Value`, `Bitrate`）
  - 若 CSV 已存在，会读取其中的 `FileSpec`，对已经出现过的压缩文件跳过计算，只追加新结果
- 示例用法：
  ```bash
  # 最常用：自动检测各个压缩目录，使用默认 VMAF 模型
  python test_vmaf_scores.py

  # 显式指定参考目录和压缩目录
  python test_vmaf_scores.py \
    --ref-dir ./Videos \
    --comp-dirs QSV_Compressed NVENC_Compressed NVENC_QP_Compressed MAC_Compressed \
    --output Results/FFMetrics.Results.csv

  # 使用 VMAF neg 模型（对高质量区间更敏感）并开启多线程
  python test_vmaf_scores.py --use-neg-model --jobs 4
  ```

---

### 4. 可视化脚本：`plot_compression_efficiency.py`

- 功能：
  - 从 `Results/FFMetrics.Results.csv` 中读取 VMAF 与码率数据，结合 `Videos/` 下原片的实际码率，绘制：
    - 每个素材单独的“VMAF vs 码率”曲线图
    - 一个按 `(平台, 参数)` 聚合的总体平均图（横轴为平均压缩百分比）
- 数据解析：
  - 从 `FileSpec` 提取：
    - `Device`：`Intel` / `Nvidia` / `MAC`
    - `Param`：
      - Intel：`global_quality` 值
      - Nvidia qmax：`qmax` 值
      - Nvidia constqp：`QP` 值（来自 `_nvidia_qpXX`）
      - Mac：`q:v` 值
    - `Source`：原始素材名（去掉后缀与参数部分）
  - 使用 `ffprobe` 从 `Videos/` 找到对应原片，计算原码率 `OrigBitrate`
  - 为每个点计算压缩百分比 `CompressPercent = Bitrate / OrigBitrate * 100`
- 单素材图：
  - 对同一个 `Source`：
    - x 轴：压缩后码率（kbps），y 轴：VMAF
    - 按平台分别画多条折线，并在每个点标注参数值（gq / qmax / QP / qv）
    - 顶部增加第二个 x 轴：显示压缩后码率占原始码率的百分比
    - 在 y=95 处画参考线，用于直观观察“高质量”区间
    - 输出到：`Results/compression_efficiency_<Source>.png`
- 总体平均图：
  - 对所有素材的数据，按 `(Device, Param, AQ)` 分组：
    - 对每一组计算平均压缩百分比和平均 VMAF（AQ 与非 AQ 不合并）
  - x 轴：平均压缩百分比，y 轴：平均 VMAF
  - 每个平台一条折线，用于整体观察不同平台在不同参数下的“质量 vs 压缩率”趋势
  - 输出到：`Results/compression_efficiency_overall.png`
- 示例用法：
  ```bash
  # 在已生成 Results/FFMetrics.Results.csv 之后运行
  python plot_compression_efficiency.py

  # 只画指定素材（Source=原文件名去扩展名）
  python plot_compression_efficiency.py --sources DJI_0046 DJI_0048

  # 只画指定平台
  python plot_compression_efficiency.py --devices Nvidia MAC

  # 不绘制 AQ（只保留非 AQ 曲线）
  python plot_compression_efficiency.py --no-aq
  ```

---

## 推荐使用顺序

1. **准备数据**
   - 在项目根目录下创建 `Videos/`，把待测试的 `.mp4` 原始视频放入其中（不必分子目录时可直接平铺）。

2. **批量压缩（可多平台并行）**
   - 根据平台选择对应脚本运行：
     - Windows/Intel：`batch_intel_qsv_gq.py`
     - NVIDIA：`batch_nvidia_qmax.py` 或 `batch_nvidia_constqp.py`
     - macOS：`batch_mac_qv.py`
   - 也可以使用 `compress_video.py` 做一次性的递归压缩，以便日常使用，不仅限于实验。

3. **计算 VMAF 分数**
   - 在所有压缩完成后运行：
     ```bash
     python test_vmaf_scores.py --jobs 4
     ```
   - 脚本会：
     - 自动找到 `QSV_Compressed/`、`NVENC_Compressed/`、`NVENC_QP_Compressed/`、`MAC_Compressed/`
     - 自动匹配 `Videos/` 中的原片
     - 将新结果追加到 `Results/FFMetrics.Results.csv`，同时跳过已计算过的 `FileSpec`

4. **绘图与分析**
   - 运行：
     ```bash
     python plot_compression_efficiency.py
     ```
   - 在 `Results/` 目录中查看生成的 PNG：
     - 针对每个素材的 `compression_efficiency_<Source>.png`
     - 总体趋势的 `compression_efficiency_overall.png`

---

## 命名与匹配规则小结

为了让脚本自动匹配原片与压缩文件，并在图中正确区分平台和参数，请尽量遵守以下命名规则：

- 原片：
  - 放在 `Videos/` 下，文件名形如：`DJI_0001.mp4`
- Intel QSV 批量压缩：
  - `DJI_0001_intel_q22.mp4`
- NVIDIA qmax 批量压缩：
  - `DJI_0001_nvidia_qmax28.mp4`
- NVIDIA constqp 批量压缩：
  - `DJI_0001_nvidia_qp25.mp4`
- macOS VideoToolbox 批量压缩：
  - `DJI_0001_mac_qv58.mp4`

脚本会根据这些后缀解析出：

- `Source`：`DJI_0001`
- `Device`：`Intel` / `Nvidia` / `MAC`
- `Param`：22 / 28 / 25 / 58 等

如果你有新的命名模式，可以在：

- `test_vmaf_scores.py` 的 `match_original_from_name()`
- `plot_compression_efficiency.py` 的 `extract_info()`

中按现有风格增加对应的正则规则即可让新模式也被自动识别。

---

## 备注

- 项目中所有脚本均假设 **原片在 `Videos/`，分析结果在 `Results/`**，尽量不要更改这一约定，便于维护整体流程。
- 运行前建议先确认 `ffmpeg` 与 `ffprobe` 在命令行中可用，并已正确启用相应硬件加速和 libvmaf 支持。
- 如果你在某个具体平台上遇到压缩失败或 VMAF 计算报错，可以根据脚本输出的 ffmpeg/ffprobe 命令行进行单独调试。
