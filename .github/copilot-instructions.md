# Copilot Instructions for Video Compress Toolkit

This project is a Python-based toolkit for batch video compression (using FFmpeg hardware acceleration) and quality analysis (VMAF).

## Project Architecture
- **Entry Point**: `main.py` is the unified CLI. Logic is modularized in `src/`.
- **Encoders (`src/encoders/`)**: Strategy pattern via `BaseEncoder`.
  - **Required Properties**: `name`, `codec_name`, `default_quality`, `quality_step` (direction), `quality_range`.
  - **Intel (`intel.py`)**: Uses `hevc_qsv` with `global_quality`. Start: 25, Step: -1.
  - **Mac (`mac.py`)**: Uses `hevc_videotoolbox` with `q:v`. Start: 58, Step: +1. Has specific `is_valid_quality` logic.
  - **Nvidia (`nvidia.py`)**: Uses `hevc_nvenc` with `constqp`. Start: 24, Step: -1.
- **Core Logic (`src/core/`)**:
  - `compressor.py`: Handles file processing.
    - `compress_file`: Standard compression. **Defaults to reverting to original file if size > 80% source** (checked via `max_ratio`).
    - `smart_compress_file`: Iterative optimization loop (Quality ± step) until VMAF >= 95 or size > 80%.
- **Analysis (`src/analysis/`)**:
  - `vmaf.py`: Wrapper for `libvmaf`. **Requires `ffmpeg` with `--enable-libvmaf`**.
  - `plotting.py`: Extracts metadata from filenames. **Tightly coupled to filename suffixes** set in `main.py`.

## Key Conventions
- **Language**: Comments and docstrings should be in **Chinese**.
- **Path Handling**: Use `pathlib.Path` exclusively. Convert to `str` only when calling `subprocess`.
- **Filename Protocol**: Analysis scripts rely on specific filename patterns.
  - Intel: `_intel_q{quality}`
  - Nvidia: `_nvidia_qp{qp}`
  - Mac: `_mac_qv{q}`
  - **CRITICAL**: If you change naming in `main.py` (`cmd_batch`), you MUST update regex in `src/analysis/plotting.py`.
- **Size Limit Policy**:
  - If a compressed file exceeds `max_size_ratio` (default 0.8), the system **MUST** discard the compressed version and copy the original file instead (implemented in `src/core/compressor.py`).

## Workflows
- **Environment**: Python 3.9+, `ffmpeg`, `ffprobe`.
- **Dependencies**: `pandas`, `matplotlib`, `ffmpeg-full` (for VMAF).
- **Commands**:
  - **Standard**: `python main.py compress <in> <out> --encoder <name>` (Automatic 80% limit check).
  - **Smart Mode**: `python main.py smart <in> <out> --encoder <name>` (Auto-tunes quality for VMAF>=95).
  - **Batch Test**: `python main.py batch ...` (Generates range of files for plotting).
  - **Analysis/Plot**: `python main.py analyze ...`, `python main.py plot ...`.

## Adding Encoders
1. Subclass `BaseEncoder` in `src/encoders/`.
2. Implement `get_ffmpeg_args` and configuration properties (`default_quality`, `quality_step`, `quality_range`).
3. Register in `src/encoders/__init__.py`.
4. Update `cmd_batch` in `main.py` to handle naming.
5. Update `EfficiencyPlotter` patterns in `src/analysis/plotting.py`.
