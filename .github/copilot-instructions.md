# Copilot Instructions for Video Compress Toolkit

This project is a Python-based toolkit for batch video compression (using FFmpeg hardware acceleration) and quality analysis (VMAF).

## Project Architecture
- **Entry Point**: `main.py` is the unified CLI. Logic is modularized in `src/`.
- **Encoders (`src/encoders/`)**: Strategy pattern via `BaseEncoder`.
  - **Required Properties**: `name`, `codec_name`, `default_quality`, `quality_step` (direction), `quality_range`.
  - **Values**: Intel (global_quality start 25, step -1), Mac (q:v start 58, step +1), Nvidia (constqp start 24, step -1).
- **Core Logic (`src/core/`)**:
  - `compressor.py`: Wraps FFmpeg calls. `compress_file` handles basic compression.
  - **Scheduler (`scheduler.py`)**: Implements **Producer-Consumer Pipeline** for `smart` compression.
    - **Compression Thread (1)**: Serial execution (GPU bound). Produces tasks for analysis.
    - **Analysis Threads (4)**: Parallel execution (CPU bound). Consumes video for VMAF calculation.
    - **Feedback Loop**: If VMAF < target, re-queues task to Compression Thread with improved quality parameters.
- **Analysis (`src/analysis/`)**:
  - `vmaf.py`: Wrapper for `libvmaf`. **Requires `ffmpeg` with `--enable-libvmaf`**.
  - `plotting.py`: Extracts metadata from filenames (RegEx coupled to `main.py`).

## Key Conventions
- **Language**: Comments and docstrings MUST be in **Chinese**.
- **Path Handling**: Use `pathlib.Path` exclusively. Convert to `str` only when calling `subprocess`.
- **Logging Format**:
  - Distinct events (Start Compress, End Compress, Start VMAF, End VMAF) MUST BE preceded by a **newline (`print("")`)** for visual separation.
- **Consistent Naming**:
  - Intel: `_intel_q{quality}` | Nvidia: `_nvidia_qp{qp}` | Mac: `_mac_qv{q}`
  - Changes to naming in `main.py` MUST be reflected in `src/analysis/plotting.py`.

## Smart Compression Logic (Critical)
1.  **Iteration Strategy**: Always start from **Lower Quality/Smaller Size** (Recommended Q ± 1) and iterate towards **Higher Quality**.
    - *Mac*: Start `default - 1`, Step `+1`.
    - *Nvidia/Intel*: Start `default + 1`, Step `-1`.
2.  **Size Limit Policy**:
    - Strict 80% limit (`max_size_ratio=0.8`).
    - **Immediate Revert**: If ANY iteration step exceeds the size limit, **ABORT** the entire task and strictly copy the **Original File** to output. Do NOT fallback to previous "best effort" checks.
3.  **VMAF Target**: Defaults to 95.0. If met, stop and save.

## Workflows
- **Environment**: Python 3.9+, `ffmpeg` + `libvmaf`.
- **CLI Commands (`main.py`)**:
  - **Smart (Pipeline)**: `python main.py smart ...` (Defaults: in=`Videos`, out=`Compressed_smart`).
  - **Compress**: `python main.py compress ...` (Standard recursive compression).
- **Adding Encoders**:
  1. Subclass `BaseEncoder`.
  2. Implement `get_ffmpeg_args` + quality config properties.
  3. Register in `src/encoders/__init__.py`.
