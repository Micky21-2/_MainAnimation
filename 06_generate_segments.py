"""
06_generate_segments.py
=========================
Detects transition points and produces segments.csv with start/end seconds
per segment. Optionally also cuts the source video into per-segment clips.
Fully argument-driven -- no hardcoded video name or output paths.

THREE DETECTION MODES:

  (default, no flag needed) -- AUTOMATIC
      Uses robust statistics (median absolute deviation) to find transitions
      that are genuine outliers relative to THIS video's own noise floor --
      no manual threshold and no need to know the slide count in advance.
      Works because real transitions are always more extreme than whatever
      the normal frame-to-frame jitter looks like, even if that jitter level
      differs from video to video. Optionally tune sensitivity with
      --sensitivity (lower = more transitions detected, default: 6.0).

  --threshold VALUE
      Manual global cutoff: flags any frame where similarity < VALUE.

  --expected-slides N
      If you already know the slide count, auto-tunes sensitivity to match.

Requires scipy (pip install scipy).

USAGE:
    python 06_generate_segments.py \\
        --input-csv path/to/similarity.csv \\
        --video path/to/any_video.mp4 \\
        --output-csv path/to/segments.csv \\
        --generate-videos \\
        --segments-dir path/to/video_segments
"""

import os
import argparse
import subprocess
import pandas as pd
import numpy as np
import cv2


def sec_to_filename(sec):
    """110 sec -> 150, 202 sec -> 322, 3661 sec -> 10101"""
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60

    if h > 0:
        return f"{h}{m:02d}{s:02d}"
    return f"{m}{s:02d}"


def detect_by_threshold(df, threshold):
    return sorted(int(f) for f in df[df["similarity"] < threshold]["frame"])


def detect_automatic(df, sensitivity=6.0, min_gap_frames=3):
    """
    Robust-statistics outlier detection, no prior knowledge required.

    1. Work in "dip space": x = 1 - similarity (so transitions are peaks, not valleys).
    2. Compute the median and median absolute deviation (MAD) of x -- these
       describe the video's own normal frame-to-frame noise level, and are
       robust to the transitions themselves (unlike mean/std, a handful of
       big transitions won't drag the median/MAD around).
    3. Flag local peaks whose modified z-score, 0.6745*(x-median)/MAD,
       exceeds `sensitivity`. This adapts automatically to how noisy or
       clean this particular video's baseline is.
    4. min_gap_frames enforces a minimum spacing so one transition (which
       may span a couple of blurry frames) isn't counted multiple times.
    """
    try:
        from scipy.signal import find_peaks
    except ImportError:
        print("ERROR: automatic detection requires scipy. Install with: pip install scipy")
        exit(1)

    similarity = df["similarity"].to_numpy()
    x = 1.0 - similarity

    median = np.median(x)
    mad = np.median(np.abs(x - median))

    if mad == 0:
        # Degenerate case: essentially no noise at all in the baseline.
        # Fall back to a tiny absolute epsilon above the median so we don't
        # divide by zero, while still only catching real deviations.
        mad = 1e-9

    modified_z = 0.6745 * (x - median) / mad

    height_x = median + (sensitivity * mad / 0.6745)

    peaks, _ = find_peaks(x, height=height_x, distance=max(min_gap_frames, 1))

    frame_numbers = df["frame"].to_numpy()
    transitions = sorted(int(frame_numbers[i]) for i in peaks)

    print(
        f"Automatic detection: median dip={median:.6f}, MAD={mad:.6f}, "
        f"sensitivity={sensitivity} -> {len(transitions)} transitions found"
    )

    return transitions


def detect_by_expected_count(df, expected_slides):
    """Binary-search over peak prominence to find ~expected_slides-1 transitions."""
    try:
        from scipy.signal import find_peaks
    except ImportError:
        print("ERROR: --expected-slides requires scipy. Install with: pip install scipy")
        exit(1)

    target = max(expected_slides - 1, 1)
    similarity = df["similarity"].to_numpy()
    inverted = 1.0 - similarity

    lo, hi = 1e-6, 1.0
    best_peaks = np.array([], dtype=int)
    best_diff = None

    for _ in range(40):
        mid = (lo + hi) / 2
        peaks, _ = find_peaks(inverted, prominence=mid)

        diff = abs(len(peaks) - target)
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_peaks = peaks

        if len(peaks) == target:
            best_peaks = peaks
            break
        elif len(peaks) > target:
            lo = mid
        else:
            hi = mid

    frame_numbers = df["frame"].to_numpy()
    transitions = sorted(int(frame_numbers[i]) for i in best_peaks)

    print(f"Peak-prominence search: target {target} transitions, found {len(transitions)}")
    if len(transitions) != target:
        print(
            f"  NOTE: could not hit the exact target -- got closest match."
        )

    return transitions


def main():
    parser = argparse.ArgumentParser(description="Detect transition points and generate segment metadata (and optionally video clips).")
    parser.add_argument("--input-csv", required=True, help="Path to similarity.csv from 03_compare_histograms.py")
    parser.add_argument("--video", required=True, help="Path to the source video")
    parser.add_argument("--output-csv", required=True, help="Path to save segments.csv")

    detection_group = parser.add_mutually_exclusive_group(required=False)
    detection_group.add_argument("--threshold", type=float, help="Similarity below this value marks a transition (manual mode)")
    detection_group.add_argument("--expected-slides", type=int, help="Known number of slides -- auto-tunes detection to match")

    parser.add_argument("--sensitivity", type=float, default=6.0, help="Sensitivity for automatic mode (lower = more transitions detected, default: 6.0). Ignored if --threshold or --expected-slides is set.")
    parser.add_argument("--min-gap-sec", type=float, default=3.0, help="Minimum seconds between detected transitions in automatic mode, to avoid double-counting one transition (default: 3.0)")

    parser.add_argument("--generate-videos", action="store_true", help="Also cut the source video into per-segment clips")
    parser.add_argument("--segments-dir", default=None, help="Directory to save video clips (required if --generate-videos is set)")

    args = parser.parse_args()

    if args.generate_videos and not args.segments_dir:
        print("ERROR: --segments-dir is required when --generate-videos is set")
        exit(1)

    if not os.path.exists(args.video):
        print(f"ERROR: video not found: {args.video}")
        exit(1)

    df = pd.read_csv(args.input_csv)

    if args.expected_slides is not None:
        transitions = detect_by_expected_count(df, args.expected_slides)
    elif args.threshold is not None:
        transitions = detect_by_threshold(df, args.threshold)
    else:
        transitions = detect_automatic(df, sensitivity=args.sensitivity, min_gap_frames=int(args.min_gap_sec))

    print("\nTransition Points (seconds):")
    print(transitions)

    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    video_length_sec = int(frame_count / fps)
    cap.release()

    print(f"\nVideo Length = {video_length_sec} sec")

    segments = []
    start = 0
    for point in transitions:
        segments.append((start, point))
        start = point
    segments.append((start, video_length_sec))

    segment_rows = []
    for idx, (start, end) in enumerate(segments):
        duration = end - start
        segment_rows.append({
            "segment": idx + 1,
            "start_sec": start,
            "end_sec": end,
            "duration_sec": duration,
        })

    segment_df = pd.DataFrame(segment_rows)

    os.makedirs(os.path.dirname(os.path.abspath(args.output_csv)), exist_ok=True)
    segment_df.to_csv(args.output_csv, index=False)

    print("\nSegments Saved:")
    print(segment_df)
    print(f"\nSaved to {args.output_csv}")

    if args.generate_videos:
        os.makedirs(args.segments_dir, exist_ok=True)

        for idx, (start, end) in enumerate(segments):
            duration = end - start
            start_name = sec_to_filename(start)
            end_name = sec_to_filename(end)

            output_file = os.path.join(args.segments_dir, f"{start_name}_{end_name}.mp4")

            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-i", args.video,
                "-t", str(duration),
                "-c:v", "libx264",
                "-c:a", "aac",
                output_file,
            ]

            print(f"\nCreating: {os.path.basename(output_file)} ({start}s - {end}s, {duration}s)")

            result = subprocess.run(cmd, capture_output=True, text=True)
            print("Return Code:", result.returncode)
            if result.returncode != 0:
                print(result.stderr)

    print("\nDone.")


if __name__ == "__main__":
    main()
