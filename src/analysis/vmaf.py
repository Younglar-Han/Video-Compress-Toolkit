import subprocess
import csv
import re
from pathlib import Path
from typing import List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

class VMAFAnalyzer:
    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe"):
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin

    def get_bitrate(self, file_path: Path) -> Optional[float]:
        """Get video bitrate in kbps using ffprobe."""
        try:
            cmd = [
                self.ffprobe_bin,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "format=bit_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ]
            output = subprocess.check_output(cmd).decode().strip()
            if not output or output == "N/A":
                return None
            return float(output) / 1000.0  # bits -> kbps
        except Exception:
            return None

    def calculate_vmaf(
        self, 
        ref_file: Path, 
        main_file: Path, 
        use_neg_model: bool = False
    ) -> Optional[float]:
        """Calculate VMAF score."""
        
        # Construct VMAF model string
        model_str = "version=vmaf_v0.6.1neg" if use_neg_model else "version=vmaf_v0.6.1"
        
        # Simple filter complex
        # [0:v] is reference, [1:v] is distorted
        filter_complex = f"[1:v][0:v]libvmaf=model={model_str}:n_threads=4"

        cmd = [
            self.ffmpeg_bin,
            "-i", str(ref_file),
            "-i", str(main_file),
            "-filter_complex", filter_complex,
            "-f", "null",
            "-"
        ]

        try:
            result = subprocess.run(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                encoding="utf-8",
                errors="ignore"
            )
            
            # Parse output for VMAF score
            # Looking for: "VMAF score: 95.123456"
            lines = result.stderr.splitlines()
            for line in reversed(lines):
                if "VMAF score" in line:
                    match = re.search(r"VMAF score[:=]\s*([0-9.]+)", line)
                    if match:
                        return float(match.group(1))
            
            return None
        except Exception as e:
            print(f"Error calculating VMAF for {main_file.name}: {e}")
            return None

    def process_files(
        self, 
        ref_dir: Path, 
        comp_files: List[Path], 
        output_csv: Path,
        jobs: int = 1,
        use_neg_model: bool = False
    ):
        """Batch process VMAF calculation."""
        
        results = []
        
        # Ensure output directory exists
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        
        # Prepare task list
        tasks = []
        
        print(f"Starting VMAF analysis for {len(comp_files)} files...")
        
        with ThreadPoolExecutor(max_workers=jobs) as executor:
            future_to_file = {}
            for comp_file in comp_files:
                # Find matching reference file
                # Assuming naming convention <original_name>_<something>.mp4
                # We need to extract the original name.
                # Heuristic: split by known suffixes or just try to match prefix
                
                # Simple heuristic: find a file in ref_dir that is a prefix of comp_file
                ref_file = None
                
                # Check specifics first
                stem = comp_file.stem
                
                # Logic from original script:
                # "test.mp4" -> "test_intel_q20.mp4"
                # Remove known suffixes
                
                possible_ref = None
                
                # Verify if any file in ref_dir matches the start of the filename
                # This is tricky because "video_1" could match "video_1_encoded.mp4"
                # but "video" could also match "video_1_encoded.mp4" (imperfect match)
                
                # Let's clean suffixes
                # _intel_q*, _nvidia_q*, _mac_qv*
                # use regex to strip suffix
                param_pattern = re.compile(
                    r"_(intel_q\d+|nvidia_qmax\d+|nvidia_qp\d+(_aq)?|mac_qv\d+)$"
                )
                
                clean_stem = param_pattern.sub("", stem)
                
                possible_ref = ref_dir / f"{clean_stem}.mp4"
                
                if possible_ref.exists():
                    ref_file = possible_ref
                else:
                    # Fallback or loop find?
                    print(f"Warning: Reference file not found for {comp_file.name} (Expected {clean_stem}.mp4)")
                    continue
                
                future = executor.submit(self._analyze_single, ref_file, comp_file, use_neg_model)
                future_to_file[future] = comp_file
                
            # Collect results
            completed_count = 0
            for future in as_completed(future_to_file):
                comp_file = future_to_file[future]
                try:
                    res = future.result()
                    if res:
                        results.append(res)
                        completed_count += 1
                        print(f"[{completed_count}/{len(future_to_file)}] Finished {comp_file.name}")
                except Exception as exc:
                    print(f"Task generated an exception: {exc}")

        # Write to CSV
        # Format: FileSpec, VMAF, Bitrate
        # Matching original format for compatibility with plotting script
        with open(output_csv, "w", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(["FileSpec", "VMAF-Value", "Bitrate"])
            
            for r in results:
                writer.writerow(r)
                
        print(f"Analysis complete. Results saved to {output_csv}")

    def _analyze_single(self, ref_file: Path, comp_file: Path, use_neg_model: bool):
        vmaf = self.calculate_vmaf(ref_file, comp_file, use_neg_model)
        bitrate = self.get_bitrate(comp_file)
        
        if vmaf is not None and bitrate is not None:
            # We return output compatible with plotting script
            # Plotting script expects 'FileSpec' which is effectively the filename
            return [comp_file.name, vmaf, bitrate]
        return None
