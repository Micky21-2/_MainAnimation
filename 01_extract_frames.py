"""
01_extract_frames.py
=====================
Samples frames from any video at a fixed interval, for later scene-change
detection. Fully argument-driven — no hardcoded video name or output path.

USAGE:
    python 01_extract_frames.py \\
        --video path/to/any_video.mp4 \\
        --output-dir path/to/frames \\
        --interval-sec 1.0
"""

import cv2
import os
import argparse


def main():
    parser = argparse.ArgumentParser(description="Sample frames from a video at a fixed interval.")
    parser.add_argument("--video", required=True, help="Path to the input video")
    parser.add_argument("--output-dir", required=True, help="Directory to save extracted frames")
    parser.add_argument(
        "--interval-sec", type=float, default=1.0,
        help="Seconds between sampled frames (default: 1.0, i.e. ~1 frame/sec)"
    )

    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(f"ERROR: video not found: {args.video}")
        exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERROR: could not open video: {args.video}")
        exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        print("ERROR: could not read FPS from video.")
        exit(1)

    interval = max(int(round(fps * args.interval_sec)), 1)

    print(f"Video FPS: {fps:.2f}")
    print(f"Sampling every {interval} frames (~{args.interval_sec}s apart)")

    frame_count = 0
    saved_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % interval == 0:
            output_path = os.path.join(args.output_dir, f"frame_{saved_count:05d}.jpg")
            cv2.imwrite(output_path, frame)
            saved_count += 1

        frame_count += 1

    cap.release()

    print(f"Saved {saved_count} frames to {args.output_dir}")


if __name__ == "__main__":
    main()
