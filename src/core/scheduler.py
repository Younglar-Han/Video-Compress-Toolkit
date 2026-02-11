import threading
import queue
import shutil
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Tuple

from src.core.compressor import Compressor
from src.analysis.vmaf import VMAFAnalyzer

@dataclass
class VideoTask:
    input_path: Path
    output_path: Path

    # 状态跟踪
    current_q: int
    step_direction: int
    min_q: int
    max_q: int

    # 运行时产物
    temp_file: Optional[Path] = None
    best_effort_file: Optional[Path] = None
    best_effort_score: float = -1.0

    # 元数据
    src_size: int = 0
    attempts: int = 0

class SmartScheduler:
    def __init__(self, compressor: Compressor, vmaf: VMAFAnalyzer, 
                 target_vmaf: float, size_limit: float, max_analyze_workers: int = 4):
        self.compressor = compressor
        self.vmaf = vmaf
        self.target_vmaf = target_vmaf
        self.size_limit = size_limit
        self.max_analyze_workers = max_analyze_workers

        # 队列
        self.comp_queue = queue.Queue()
        self.analyze_queue = queue.Queue()

        # 同步控制
        self.active_tasks_count = 0
        self.lock = threading.Lock()
        self.workers: List[threading.Thread] = []
        self.shutdown_flag = False

    def start(self, videos: List[Tuple[Path, Path]]):
        """启动调度器并阻塞等待所有任务完成。"""
        if not videos:
            return

        print(f"初始化调度器，共 {len(videos)} 个视频。")
        print(f"压缩线程: 1 | 分析线程: {self.max_analyze_workers}")

        # 1. 入队初始任务
        for inp, out in videos:
            self._create_and_queue_task(inp, out)

        # 2. 启动线程
        t_comp = threading.Thread(target=self._compression_worker, name="Worker-Compress")
        t_comp.daemon = True
        t_comp.start()
        self.workers.append(t_comp)

        # 分析线程（并行）
        for i in range(self.max_analyze_workers):
            t_ana = threading.Thread(target=self._analysis_worker, name=f"Worker-Analyze-{i}")
            t_ana.daemon = True
            t_ana.start()
            self.workers.append(t_ana)

        # 3. 主循环监控
        try:
            while True:
                with self.lock:
                    if self.active_tasks_count == 0 and self.comp_queue.empty() and self.analyze_queue.empty():
                        break
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[调度器] 用户中断，正在停止...")
            self.shutdown_flag = True

        print("[调度器] 全部任务完成。")

    def _create_and_queue_task(self, inp: Path, out: Path):
        if not inp.exists():
            print(f"错误: 输入文件缺失 {inp}")
            return

        enc = self.compressor.encoder
        
        # 起点策略：从“更差质量、更小体积”开始，逐步提高质量
        step = enc.quality_step
        min_q, max_q = enc.quality_range
        
        if step > 0:
            # Mac: q:v 越大质量越高
            start_q = enc.default_quality - 1
        else:
            # Intel/Nvidia: QP/global_quality 越小质量越高
            start_q = enc.default_quality + 1
        
        src_size = inp.stat().st_size
        
        task = VideoTask(
            input_path=inp,
            output_path=out,
            current_q=start_q,
            step_direction=step,
            min_q=min_q,
            max_q=max_q,
            src_size=src_size
        )
        
        with self.lock:
            self.active_tasks_count += 1
        
        self.comp_queue.put(task)

    def _compression_worker(self):
        while not self.shutdown_flag:
            try:
                # 使用超时便于检查退出标志
                task = self.comp_queue.get(timeout=1)
            except queue.Empty:
                continue

            self._process_compression(task)
            self.comp_queue.task_done()

    def _analysis_worker(self):
        while not self.shutdown_flag:
            try:
                task = self.analyze_queue.get(timeout=1)
            except queue.Empty:
                continue
                
            self._process_analysis(task)
            self.analyze_queue.task_done()

    def _process_compression(self, task: VideoTask):
        """执行压缩步骤。"""
        # 先做范围检查
        if not (task.min_q <= task.current_q <= task.max_q):
            print(f"[{task.input_path.name}] 已达到质量范围边界 (Q={task.current_q})，停止。")
            self._finalize_task(task, use_best_effort=True)
            return

        # 跳过无效质量值（主要针对 macOS）
        if not self.compressor.encoder.is_valid_quality(task.current_q):
            print(f"[{task.input_path.name}] 跳过无效参数 Q={task.current_q}")
            task.current_q += task.step_direction
            self.comp_queue.put(task)
            return

        print("")
        print(f"[{task.input_path.name}] 开始压缩 (Q={task.current_q})...")

        # 临时输出路径
        task.temp_file = task.output_path.with_name(
            f"{task.output_path.stem}_temp_q{task.current_q}{task.output_path.suffix}"
        )
        
        # 执行压缩（不使用 max_ratio，体积检查由调度器控制）
        success = self.compressor.compress_file(task.input_path, task.temp_file, quality=task.current_q)
        
        print("")
        print(f"[{task.input_path.name}] 压缩完成。")
        
        if not success:
            print(f"[{task.input_path.name}] 压缩失败。")
            # 失败后尝试下一个参数
            task.current_q += task.step_direction
            self.comp_queue.put(task) 
            return

        # 体积检查
        if not task.temp_file.exists(): 
            self._finalize_task(task, use_best_effort=True)
            return

        dst_size = task.temp_file.stat().st_size
        ratio = dst_size / task.src_size if task.src_size > 0 else 1.0
        
        if ratio > self.size_limit:
            print(f"[{task.input_path.name}] 超过体积限制 ({ratio:.2%})。")
            task.temp_file.unlink()

            # 触发体积限制后，严格回退到原视频
            print(f"[{task.input_path.name}] 触发体积限制，回退到原视频。")
            self._finalize_task(task, use_best_effort=False)
            return
            
        # 体积合规后进入 VMAF 分析
        self.analyze_queue.put(task)

    def _process_analysis(self, task: VideoTask):
        """执行 VMAF 分析。"""
        print("")
        print(f"[{task.input_path.name}] 开始 VMAF 分析...")
        
        score = self.vmaf.calculate_vmaf(task.input_path, task.temp_file)
        print("")
        print(f"[{task.input_path.name}] VMAF 分析完成。")
        
        # 计算体积占比用于日志
        current_ratio_str = "N/A"
        if task.temp_file.exists() and task.src_size > 0:
            current_ratio = task.temp_file.stat().st_size / task.src_size
            current_ratio_str = f"{current_ratio:.2%}"

        if score is None:
            print(f"[{task.input_path.name}] VMAF 计算失败。")
            if task.temp_file.exists(): task.temp_file.unlink()
            self._finalize_task(task, use_best_effort=True)
            return
            
        print("")
        print(f"[{task.input_path.name}] VMAF={score:.2f} | 体积={current_ratio_str}")

        if score >= self.target_vmaf:
            print(f"[{task.input_path.name}] 达到目标 VMAF。")
            if task.output_path.exists(): task.output_path.unlink()
            task.temp_file.rename(task.output_path)

            # 清理最佳候选
            if task.best_effort_file and task.best_effort_file.exists():
                task.best_effort_file.unlink()
                
            self._finalize_task(task)
            return
        
        # 未达标，但体积合规，作为当前最佳候选
        
        if task.best_effort_file and task.best_effort_file.exists():
            task.best_effort_file.unlink()
            
        task.best_effort_file = task.output_path.with_name(f"{task.output_path.stem}_best_effort{task.output_path.suffix}")
        task.temp_file.rename(task.best_effort_file)
        task.best_effort_score = score
        task.temp_file = None
        
        # 准备下一轮尝试
        task.current_q += task.step_direction
        self.comp_queue.put(task)

    def _finalize_task(self, task: VideoTask, use_best_effort: bool = False):
        # 根据策略确定最终输出
        final_source = None
        
        if use_best_effort and task.best_effort_file and task.best_effort_file.exists():
            final_source = task.best_effort_file
            print(f"[{task.input_path.name}] 使用最佳候选结果 (VMAF={task.best_effort_score:.2f})")
        else:
            final_source = task.input_path
            if use_best_effort:
                print(f"[{task.input_path.name}] 未找到合适压缩结果，使用原视频。")
            else:
                print(f"[{task.input_path.name}] 压缩终止（如体积限制），使用原视频。")

        # 确保输出目录存在
        task.output_path.parent.mkdir(parents=True, exist_ok=True)
            
        if task.output_path.exists():
            task.output_path.unlink()
            
        if final_source == task.input_path:
            shutil.copy2(task.input_path, task.output_path)
        elif final_source:
            final_source.rename(task.output_path)
             
        # 清理临时文件
        if task.best_effort_file and task.best_effort_file.exists():
            task.best_effort_file.unlink()
        
        with self.lock:
            self.active_tasks_count -= 1
