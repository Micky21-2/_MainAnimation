"""
build_slide_timeline.py
========================
Builds the final composite timeline consumed by compose_lecture.py, from a
classified segments CSV (segments_classified.csv, from classify_segments.py).

For each segment:
  "slide" segments -> extracts one representative still frame as the slide image
  "demo"  segments -> extracts the actual video clip (with motion) from the source

Output is composite_timeline.json, e.g.:
[
  {"type": "slide", "image": "slides/slide_001.png", "start": 0.0, "duration": 14.0},
  {"type": "demo",  "video": "demo_clips/demo_002.mp4", "start": 14.0, "duration": 22.5},
  {"type": "slide", "image": "slides/slide_003.png", "start": 36.5, "duration": 9.0}
]

Backward compatible: if the input CSV has no "type" column, every segment is
treated as "slide" (matches the old behavior).

USAGE:
    python build_slide_timeline.py \\
        --segments data/results/segments_classified.csv \\
        --source-video data/videos/recording.mp4 \\
        --slides-out-dir slides \\
        --demo-clips-out-dir demo_clips \\
        --timeline-out composite_timeline.json
"""

import os
import csv
import json
import argparse
import subprocess


def run(cmd):
    subprocess.run(cmd, check=True)


def extract_frame(video_path: str, timestamp: float, output_path: str):
    """Grab a single frame from video_path at timestamp seconds."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", str(timestamp),
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        output_path,
    ]
    run(cmd)


def extract_clip(video_path: str, start: float, duration: float, output_path: str):
    """Cut a video-only (no audio) clip from video_path."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", str(start),
        "-i", video_path,
        "-t", str(duration),
        "-an",
        "-c:v", "libx264",
        output_path,
    ]
    run(cmd)


def load_segments(csv_path: str):
    segments = []
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        has_type = "type" in reader.fieldnames
        for row in reader:
            segments.append({
                "segment": int(row["segment"]),
                "start_sec": float(row["start_sec"]),
                "end_sec": float(row["end_sec"]),
                "duration_sec": float(row["duration_sec"]),
                "type": row["type"] if has_type else "slide",
            })
    return segments


def main():
    parser = argparse.ArgumentParser(
        description="Build a composite (slide + demo) timeline for compose_lecture.py from classified segments."
    )
    parser.add_argument("--segments", required=True, help="Path to segments.csv or segments_classified.csv")
    parser.add_argument("--source-video", required=True, help="Path to the reference video the segments were detected from")
    parser.add_argument("--slides-out-dir", default="slides", help="Directory to save extracted slide images (default: slides)")
    parser.add_argument("--demo-clips-out-dir", default="demo_clips", help="Directory to save extracted demo video clips (default: demo_clips)")
    parser.add_argument("--timeline-out", default="composite_timeline.json", help="Output path for the timeline JSON (default: composite_timeline.json)")
    parser.add_argument(
        "--grab-offset",
        type=float,
        default=1.0,
        help="Seconds into each slide segment to grab the still frame from, avoiding transition blur (default: 1.0)"
    )

    args = parser.parse_args()

    if not os.path.exists(args.segments):
        print(f"ERROR: segments file not found: {args.segments}")
        exit(1)
    if not os.path.exists(args.source_video):
        print(f"ERROR: source video not found: {args.source_video}")
        exit(1)

    os.makedirs(args.slides_out_dir, exist_ok=True)
    os.makedirs(args.demo_clips_out_dir, exist_ok=True)

    segments = load_segments(args.segments)
    if not segments:
        print("ERROR: no segments found in CSV.")
        exit(1)

    timeline = []

    print(f"Building composite timeline for {len(segments)} segments...\n")

    for seg in segments:
        start = seg["start_sec"]
        end = seg["end_sec"]
        duration = seg["duration_sec"]
        seg_type = seg["type"]

        if seg_type == "demo":
            clip_path = os.path.join(args.demo_clips_out_dir, f"demo_{seg['segment']:03d}.mp4")
            print(f"  Segment {seg['segment']:3d} [DEMO]:  {start:.1f}s - {end:.1f}s -> extracting clip -> {clip_path}")
            extract_clip(args.source_video, start, duration, clip_path)

            timeline.append({
                "type": "demo",
                "video": clip_path,
                "start": start,
                "duration": duration,
            })
        else:
            grab_time = min(start + args.grab_offset, start + max(duration / 2, 0.1))
            image_path = os.path.join(args.slides_out_dir, f"slide_{seg['segment']:03d}.png")
            print(f"  Segment {seg['segment']:3d} [SLIDE]: {start:.1f}s - {end:.1f}s -> grabbing frame at {grab_time:.1f}s -> {image_path}")
            extract_frame(args.source_video, grab_time, image_path)

            timeline.append({
                "type": "slide",
                "image": image_path,
                "start": start,
                "duration": duration,
            })

    with open(args.timeline_out, "w") as f:
        json.dump(timeline, f, indent=2)

    n_slide = sum(1 for t in timeline if t["type"] == "slide")
    n_demo = sum(1 for t in timeline if t["type"] == "demo")
    print(f"\nDone. Wrote timeline: {n_slide} slide segment(s), {n_demo} demo segment(s) -> {args.timeline_out}")


if __name__ == "__main__":
    main()
