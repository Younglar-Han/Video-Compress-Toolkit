# Copilot Instructions for Video Compress Toolkit

## 项目全景（先看这里）
- 统一 CLI 入口：`main.py`，子命令为 `compress / batch / smart / analyze / plot`。
- 核心数据流：压缩(`src/core/compressor.py`) → VMAF(`src/analysis/vmaf.py`) → 结果绘图(`src/analysis/plotting.py`)。
- 编码器抽象在 `src/encoders/base.py`，实现为 `intel.py / nvidia.py / mac.py`，通过 `src/encoders/__init__.py:get_encoder()` 注入。

## 智能压缩关键机制（改动高频区）
- `smart` 走 `src/core/scheduler.py:SmartScheduler`。
- 双队列：压缩队列与分析队列均为 `PriorityQueue`；规则一致但队列独立。
- 优先级规则：重试深度越高优先级越高（`attempts` 越大越先执行），同层按 `seq` FIFO。
- 背压：首轮任务在 `analyze_queue.qsize() >= max_pending_analyses` 时会暂缓，避免临时文件堆积。
- 中断(`Ctrl+C`)：未完成任务终止且清理中间文件，不回退复制原视频；尽量仅保留已完成输出。
- 队列调试：`--queue-debug` 会打印入/出队日志（`attempts/priority/seq/comp_q/analyze_q`）。

## 项目约束（必须遵守）
- 注释和 docstring 使用中文。
- 路径处理统一使用 `pathlib.Path`；仅在 `subprocess` 参数中转换为 `str(path)`。
- 关键阶段日志保持现有风格（通过 `src/utils/console.py` 的 `phase_start/phase_end/info/warn` 输出）。

## 输入输出与命名约定
- `compress` 与 `smart` 目录扫描会包含 `.mp4/.jpg/.jpeg`；JPG/JPEG 必须直接复制，不进入编码与 VMAF。
- `batch` 产物命名必须兼容绘图解析（`src/utils/naming.py` + `src/analysis/plotting.py`）：
  - Intel: `_intel_q{quality}`
  - Nvidia: `_nvidia_qp{qp}`
  - Mac: `_mac_qv{q}`
- 不要随意改动上述后缀格式，否则 `analyze/plot` 无法正确聚合。

## 开发与验证工作流
- 环境要求：Python 3.9+，FFmpeg/FFprobe；VMAF 依赖 `libvmaf`。
- 常用命令：
  - `python main.py smart Videos Compressed_smart --encoder mac --analyze-workers 2 --max-pending-analyses 4`
  - `python main.py analyze --ref-dir Videos --comp-dirs Compressed_smart --output Results/scores.csv`
  - `python main.py plot --csv Results/scores.csv --output-dir Results/Plots`
- 当前仓库无固定测试套件；修改后至少执行受影响命令做烟雾验证。

## 修改建议（给 AI 代理）
- 涉及调度逻辑时，优先修改 `SmartScheduler` 的入队策略方法（如 `_put_comp_queue/_put_analyze_queue`），避免在业务分支散落优先级逻辑。
- 涉及压缩回退或中断行为时，确认同时覆盖：临时文件清理、结果落盘、`active_tasks_count` 计数一致性。
- 新增编码器时，除实现 `BaseEncoder` 外，务必在 `get_encoder()` 注册并验证 `batch` 命名兼容性。
