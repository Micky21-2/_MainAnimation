"""
preview_detection.py
======================
Creates a copy of the source video with the detected segment info burned in
as an on-screen label (top of frame) throughout -- e.g. "Segment 12 [SLIDE]
145.0s - 160.0s". Play it once, full speed or scrubbing, and watch whether
the label changes exactly when the real content actually changes on screen.
This is the fastest way to eyeball whether detection timing/boundaries are
accurate across a WHOLE video, instead of opening many separate clips.

Works with either segments.csv (no type) or segments_classified.csv (with
slide/demo type) -- type is shown in the label automatically if present.

USAGE:
    python preview_detection.py \\
        --segments path/to/segments.csv \\
        --video path/to/source_video.mp4 \\
        --output path/to/preview.mp4

Optional: --scale-width to shrink the output for a smaller/faster file
(detection accuracy doesn't need full resolution to verify visually).
"""

import os
import csv
import argparse
import subprocess


def run(cmd):
    subprocess.run(cmd, check=True)


def format_timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours = millis // 3_600_000
    millis %= 3_600_000
    minutes = millis // 60_000
    millis %= 60_000
    secs = millis // 1000
    millis %= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


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
                "type": row["type"].upper() if has_type else None,
            })
    return segments


def build_label_srt(segments, srt_path):
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            type_part = f"[{seg['type']}] " if seg["type"] else ""
            text = f"Segment {seg['segment']} {type_part}{seg['start_sec']:.1f}s - {seg['end_sec']:.1f}s"
            f.write(f"{i}\n")
            f.write(f"{format_timestamp(seg['start_sec'])} --> {format_timestamp(seg['end_sec'])}\n")
            f.write(f"{text}\n\n")


def escape_path(path: str) -> str:
    abs_path = os.path.abspath(path)
    return abs_path.replace("\\", "/").replace(":", "\\:")


def main():
    parser = argparse.ArgumentParser(description="Burn detected segment info onto the source video for visual accuracy checking.")
    parser.add_argument("--segments", required=True, help="Path to segments.csv or segments_classified.csv")
    parser.add_argument("--video", required=True, help="Path to the source video")
    parser.add_argument("--output", required=True, help="Path for the labeled preview video")
    parser.add_argument("--scale-width", type=int, default=None, help="Optional: shrink output to this width (height auto), for a smaller/faster file")

    args = parser.parse_args()

    if not os.path.exists(args.segments):
        print(f"ERROR: segments file not found: {args.segments}")
        exit(1)
    if not os.path.exists(args.video):
        print(f"ERROR: video not found: {args.video}")
        exit(1)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    segments = load_segments(args.segments)
    if not segments:
        print("ERROR: no segments found in CSV.")
        exit(1)

    srt_path = args.output + ".labels.srt"
    build_label_srt(segments, srt_path)
    print(f"Built label track: {len(segments)} segments -> {srt_path}")

    escaped_srt = escape_path(srt_path)
    style = (
        "FontName=Arial,FontSize=22,PrimaryColour=&H0000FFFF,"
        "OutlineColour=&H00000000,BorderStyle=3,Outline=1,Shadow=0,"
        "BackColour=&H80000000,Alignment=6,MarginV=20"
    )

    if args.scale_width:
        video_filter = f"scale={args.scale_width}:-2,subtitles=filename='{escaped_srt}':force_style='{style}'"
    else:
        video_filter = f"subtitles=filename='{escaped_srt}':force_style='{style}'"

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", args.video,
        "-vf", video_filter,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        args.output,
    ]

    print("Burning labels onto video (this may take a while for a long video)...")
    run(cmd)

    os.remove(srt_path)
    print(f"\nDone! Preview video: {args.output}")
    print("Play it and watch the top-left label -- it should change exactly when the real content on screen changes.")


if __name__ == "__main__":
    main()