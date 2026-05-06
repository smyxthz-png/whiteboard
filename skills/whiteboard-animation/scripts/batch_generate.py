#!/usr/bin/env python3
"""Batch whiteboard animation generator.

Generates each segment in an isolated scratch directory, then promotes the
result into a deterministic filename so interrupted runs can resume cleanly.
"""

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
GENERATE_SCRIPT = SCRIPT_DIR / "generate_whiteboard.py"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def media_duration(path):
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=30,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def is_valid_file(path, min_bytes=50 * 1024):
    try:
        return Path(path).exists() and Path(path).stat().st_size > min_bytes
    except OSError:
        return False


def is_valid_video_file(path):
    return is_valid_file(path) and media_duration(path) > 0.05


def deterministic_segment_path(output_dir, index):
    return Path(output_dir) / f"scene_{index + 1:03d}_h264.mp4"


def segment_manifest_path(output_dir, index):
    return Path(output_dir) / f"scene_{index + 1:03d}_h264.json"


def segment_fingerprint(image_path, duration, fps, no_hand):
    return {
        "image_path": str(Path(image_path).resolve()),
        "image_sha256": sha256_file(image_path),
        "duration": int(duration),
        "fps": int(fps),
        "no_hand": bool(no_hand),
    }


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except Exception:
        return None


def write_json_atomic(path, payload):
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def reuse_existing_segment(output_dir, index, force, fingerprint):
    if force:
        return None
    path = deterministic_segment_path(output_dir, index)
    manifest = read_json(segment_manifest_path(output_dir, index))
    if (
        isinstance(manifest, dict)
        and manifest.get("fingerprint") == fingerprint
        and is_valid_video_file(path)
    ):
        return str(path)
    return None


def latest_generated_video(work_dir):
    candidates = []
    for pattern in ("*_h264.mp4", "*.mp4"):
        candidates.extend(path for path in Path(work_dir).glob(pattern) if is_valid_video_file(path))
    if not candidates:
        return None
    return str(sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0])


def run_generate_whiteboard(image_path, output_dir, duration, fps, no_hand=False):
    cmd = [
        sys.executable,
        str(GENERATE_SCRIPT),
        image_path,
        "--output-dir",
        output_dir,
        "--duration",
        str(duration),
        "--fps",
        str(fps),
    ]
    if no_hand:
        cmd.append("--no-hand")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return result.returncode == 0, result.stdout, result.stderr


def generate_segment(task):
    index = task["index"]
    image = task["image"]
    duration = task["duration"]
    output_dir = task["output_dir"]
    fps = task["fps"]
    force = task["force"]
    no_hand = task["no_hand"]
    fingerprint = task["fingerprint"]

    reused = reuse_existing_segment(output_dir, index, force, fingerprint)
    if reused:
        return {"index": index, "success": True, "video": reused, "reused": True}

    segment_dir = Path(output_dir) / "_segments" / f"scene_{index + 1:03d}"
    if segment_dir.exists():
        shutil.rmtree(segment_dir, ignore_errors=True)
    segment_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{index + 1}] Rendering {Path(image).name} ({duration}ms)")
    ok, stdout, stderr = run_generate_whiteboard(image, str(segment_dir), duration, fps, no_hand=no_hand)
    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if not ok:
        if stderr:
            print(stderr, file=sys.stderr, end="" if stderr.endswith("\n") else "\n")
        return {"index": index, "success": False, "error": f"render failed for {image}"}

    generated = latest_generated_video(segment_dir)
    if not generated:
        return {"index": index, "success": False, "error": f"no video produced for {image}"}

    final_path = deterministic_segment_path(output_dir, index)
    os.replace(generated, final_path)
    write_json_atomic(segment_manifest_path(output_dir, index), {
        "fingerprint": fingerprint,
        "video": str(final_path),
    })
    shutil.rmtree(segment_dir, ignore_errors=True)
    print(f"[{index + 1}] Saved {final_path}")
    return {"index": index, "success": True, "video": str(final_path), "reused": False}


def main():
    parser = argparse.ArgumentParser(description="批量白板手绘动画生成器")
    parser.add_argument("--images", nargs="+", required=True, help="图片路径列表")
    parser.add_argument("--durations", nargs="+", type=int, required=True, help="时长列表，单位毫秒")
    parser.add_argument("--output-dir", default="./output", help="输出目录")
    parser.add_argument("--fps", type=int, default=30, help="生成视频帧率")
    parser.add_argument("--jobs", type=int, default=2, help="并发任务数")
    parser.add_argument("--force", action="store_true", help="忽略已存在的分段结果")
    parser.add_argument("--no-hand", action="store_true", help="禁用手部覆盖效果")
    args = parser.parse_args()

    images = args.images
    durations = args.durations
    if len(images) != len(durations):
        print(f"错误: 图片数量 ({len(images)}) 与时长数量 ({len(durations)}) 不一致")
        sys.exit(1)

    for i, image_path in enumerate(images):
        if not os.path.exists(image_path):
            print(f"错误: 第 {i + 1} 张图片不存在: {image_path}")
            sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(images)
    jobs = max(1, min(args.jobs, total))

    print("=" * 60)
    print(f"批量白板手绘动画生成器 - 共 {total} 个任务")
    print(f"并发: {jobs}, 帧率: {args.fps}fps")
    print("=" * 60)

    tasks = [
        {
            "index": i,
            "image": image,
            "duration": duration,
            "output_dir": str(output_dir),
            "fps": args.fps,
            "force": args.force,
            "no_hand": args.no_hand,
            "fingerprint": segment_fingerprint(image, duration, args.fps, args.no_hand),
        }
        for i, (image, duration) in enumerate(zip(images, durations))
    ]

    results = [None] * total
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
        future_map = {executor.submit(generate_segment, task): task["index"] for task in tasks}
        for future in concurrent.futures.as_completed(future_map):
            index = future_map[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {"index": index, "success": False, "error": str(exc)}
            results[index] = result
            if result["success"]:
                status = "reused" if result.get("reused") else "completed"
                print(f"[{index + 1}/{total}] {status}: {Path(result['video']).name}")
            else:
                print(f"[{index + 1}/{total}] failed: {result.get('error')}", file=sys.stderr)

    succeeded = sum(1 for r in results if r and r["success"])
    failed = sum(1 for r in results if not r or not r["success"])

    print(f"\n{'=' * 60}")
    print("批量生成完成 - 汇总")
    print(f"{'=' * 60}")
    print(f"  成功: {succeeded}/{total}")
    if failed > 0:
        print(f"  失败: {failed}/{total}")
        for r in results:
            if not r or not r["success"]:
                print(f"    - {r.get('error') if r else 'unknown error'}")

    video_files = [r["video"] for r in results if r and r["success"]]
    print(f"\n输出目录: {os.path.abspath(args.output_dir)}")
    print(f"\n__RESULTS__{json.dumps(video_files, ensure_ascii=False)}")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
