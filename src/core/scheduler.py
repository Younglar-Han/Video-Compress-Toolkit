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
    
    # State tracking
    current_q: int
    step_direction: int
    min_q: int
    max_q: int
    
    # Runtime artifacts
    temp_file: Optional[Path] = None
    best_effort_file: Optional[Path] = None
    best_effort_score: float = -1.0
    
    # Metadata
    src_size: int = 0
    attempts: int = 0

class SmartScheduler:
    def __init__(self, compressor: Compressor, vmaf: VMAFAnalyzer, 
                 target_vmaf: float, size_limit: float, max_analyze_workers: int = 4):
        self.compressor = compressor
        self.vmaf = vmaf
        self.target_vmaf = target_vmaf
        self.size_limit = size_limit
        
        # Queues
        self.comp_queue = queue.Queue()
        self.analyze_queue = queue.Queue()
        
        # Synchronization
        self.active_tasks_count = 0
        self.lock = threading.Lock()
        self.workers: List[threading.Thread] = []
        self.shutdown_flag = False

    def start(self, videos: List[Tuple[Path, Path]]):
        """Starts the processing loop blockingly until all tasks are done."""
        if not videos:
            return

        print(f"Initializing scheduler with {len(videos)} videos.")
        print(f"Compressor: Sequential (1 thread), Analyzer: Parallel (4 threads)")

        # 1. Enqueue all initial tasks
        for inp, out in videos:
            self._create_and_queue_task(inp, out)

        # 2. Start Threads
        # Compression Thread (Producer -> Consumer -> Producer)
        t_comp = threading.Thread(target=self._compression_worker, name="Worker-Compress")
        t_comp.daemon = True
        t_comp.start()
        self.workers.append(t_comp)

        # Analysis Threads (Consumer -> Producer)
        for i in range(4):
            t_ana = threading.Thread(target=self._analysis_worker, name=f"Worker-Analyze-{i}")
            t_ana.daemon = True
            t_ana.start()
            self.workers.append(t_ana)

        # 3. Main Loop Monitor
        try:
            while True:
                with self.lock:
                    if self.active_tasks_count == 0 and self.comp_queue.empty() and self.analyze_queue.empty():
                        break
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[Scheduler] Interrupted by user. Stopping...")
            self.shutdown_flag = True
        
        print("[Scheduler] All tasks completed.")

    def _create_and_queue_task(self, inp: Path, out: Path):
        if not inp.exists():
            print(f"Error: Input {inp} missing.")
            return

        enc = self.compressor.encoder
        
        # Optimization:
        # We want to start from a quality that is slightly WORSE (smaller size) than the default,
        # and iterate towards BETTER quality (larger size) until VMAF >= Target or Size > Limit.
        
        step = enc.quality_step
        min_q, max_q = enc.quality_range
        
        if step > 0:
            # Case Mac/Bitrate: Higher value = Better Quality.
            # Start lower: default - 1
            start_q = enc.default_quality - 1
        else:
            # Case Intel/Nvidia/QP: Lower value = Better Quality.
            # Start higher (worse quality): default + 1
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
                # Timeout allows checking shutdown flag occasionally
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
        """Handle compression step for a task."""
        # Check limits before compressing
        if not (task.min_q <= task.current_q <= task.max_q):
            print(f"[{task.input_path.name}] Quality limit reached (Q={task.current_q}). Stopping.")
            self._finalize_task(task, use_best_effort=True)
            return

        # Skip invalid qualities (Mac specific usually)
        if not self.compressor.encoder.is_valid_quality(task.current_q):
            print(f"[{task.input_path.name}] Skipping invalid Q={task.current_q}")
            task.current_q += task.step_direction
            self.comp_queue.put(task) # Re-queue immediately
            return

        print("")
        print(f"[{task.input_path.name}] Compressing @ Q={task.current_q}...")
        
        # Temp output path
        task.temp_file = task.output_path.with_name(
            f"{task.output_path.stem}_temp_q{task.current_q}{task.output_path.suffix}"
        )
        
        # Run compression (blocking relative to this thread)
        # We DO NOT use max_ratio here, we check it manually after
        success = self.compressor.compress_file(task.input_path, task.temp_file, quality=task.current_q)
        
        print("")
        print(f"[{task.input_path.name}] Compression finished.")
        
        if not success:
            print(f"[{task.input_path.name}] Compression failed.")
            # Try next quality? Or fail completely? 
            # Let's try skipping this Q
            task.current_q += task.step_direction
            self.comp_queue.put(task) 
            return

        # Check size immediately
        if not task.temp_file.exists(): 
             # Should not happen if success=True
             self._finalize_task(task, use_best_effort=True)
             return

        dst_size = task.temp_file.stat().st_size
        ratio = dst_size / task.src_size if task.src_size > 0 else 1.0
        
        if ratio > self.size_limit:
            print(f"[{task.input_path.name}] Size limit exceeded ({ratio:.2%}).")
            task.temp_file.unlink() # Discard this attempt
            
            # User requirement: If size limit is hit during iteration (meaning higher quality made it too big),
            # strictly discard everything and use original file.
            print(f"[{task.input_path.name}] Reverting to original file due to size limit.")
            self._finalize_task(task, use_best_effort=False)
            return
            
        # If size is OK, move to VMAF analysis
        
        # But wait, logic check: 
        # The user said "If VMAF not enough, improve quality".
        # Improving quality usually increases size.
        # So iterating is correct.
        
        self.analyze_queue.put(task)

    def _process_analysis(self, task: VideoTask):
        """Handle VMAF analysis."""
        print("")
        print(f"[{task.input_path.name}] Analyzing VMAF...")
        
        score = self.vmaf.calculate_vmaf(task.input_path, task.temp_file)
        print("")
        print(f"[{task.input_path.name}] VMAF analysis finished.")
        
        # Calculate ratio for reporting
        current_ratio_str = "N/A"
        if task.temp_file.exists() and task.src_size > 0:
             current_ratio = task.temp_file.stat().st_size / task.src_size
             current_ratio_str = f"{current_ratio:.2%}"

        if score is None:
            print(f"[{task.input_path.name}] VMAF failed.")
            if task.temp_file.exists(): task.temp_file.unlink()
            self._finalize_task(task, use_best_effort=True)
            return
            
        print("")
        print(f"[{task.input_path.name}] VMAF={score:.2f} | Size={current_ratio_str}")

        if score >= self.target_vmaf:
            print(f"[{task.input_path.name}] Success! Target reached.")
            # Set this as the winner
            if task.output_path.exists(): task.output_path.unlink()
            task.temp_file.rename(task.output_path)
            
            # Cleanup best effort if exists
            if task.best_effort_file and task.best_effort_file.exists():
                task.best_effort_file.unlink()
                
            self._finalize_task(task)
            return
        
        # Score not met. 
        # Since this file (task.temp_file) passed the size check (in compression step), 
        # it is a valid "Best Effort" candidate (better than previous because quality param improved).
        
        if task.best_effort_file and task.best_effort_file.exists():
            task.best_effort_file.unlink()
            
        task.best_effort_file = task.output_path.with_name(f"{task.output_path.stem}_best_effort{task.output_path.suffix}")
        task.temp_file.rename(task.best_effort_file)
        task.best_effort_score = score
        task.temp_file = None # Pointer moved
        
        # Prepare for next iteration
        task.current_q += task.step_direction
        self.comp_queue.put(task)

    def _finalize_task(self, task: VideoTask, use_best_effort: bool = False):
        # Determine the source to copy/move to output_path
        final_source = None
        
        if use_best_effort and task.best_effort_file and task.best_effort_file.exists():
            final_source = task.best_effort_file
            print(f"[{task.input_path.name}] Finishing with Best Effort (VMAF={task.best_effort_score:.2f})")
        else:
            final_source = task.input_path
            if use_best_effort:
                print(f"[{task.input_path.name}] Failed to find suitable compression. Using original.")
            else:
                print(f"[{task.input_path.name}] Aborting compression (e.g. size limit). Using original.")

        # Ensure output directory exists (should already be there but safe to check)
        task.output_path.parent.mkdir(parents=True, exist_ok=True)
            
        if task.output_path.exists():
            task.output_path.unlink()
            
        if final_source == task.input_path:
             shutil.copy2(task.input_path, task.output_path)
        elif final_source:
             final_source.rename(task.output_path)
             
        # Cleanup
        if task.best_effort_file and task.best_effort_file.exists():
            task.best_effort_file.unlink()
        
        with self.lock:
            self.active_tasks_count -= 1
