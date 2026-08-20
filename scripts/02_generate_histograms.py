"""
02_generate_histograms.py
===========================
Computes a per-frame "signature" used later to detect scene/slide changes.
Two methods are supported via --method:

  histogram (default) - normalized RGB color histogram. Good for videos that
                         cut between visually distinct scenes/colors. WEAK for
                         slide decks or screen recordings where consecutive
                         slides share a similar color palette (e.g. white
                         background, black text) even though the content
                         (layout, diagrams, text) changed completely.

  layout               - downsized grayscale image of the frame. Sensitive to
                          actual content/layout changes regardless of color
                          palette. Recommended for slide/screen-recording
                          detection.

Fully argument-driven — no hardcoded frame/output directories.

USAGE:
    python 02_generate_histograms.py \
        --frames-dir path/to/frames \
        --output-dir path/to/histograms \
        --method layout
"""

import cv2
import os
import argparse
import numpy as np


def compute_histogram_signature(img):
    hist_b = cv2.calcHist([img], [0], None, [256], [0, 256])
    hist_g = cv2.calcHist([img], [1], None, [256], [0, 256])
    hist_r = cv2.calcHist([img], [2], None, [256], [0, 256])

    cv2.normalize(hist_b, hist_b)
    cv2.normalize(hist_g, hist_g)
    cv2.normalize(hist_r, hist_r)

    return np.concatenate([hist_b.flatten(), hist_g.flatten(), hist_r.flatten()])


def compute_layout_signature(img, size=(64, 36)):
    """Downsized grayscale image -- captures layout/content changes,
    insensitive to color-palette similarity between frames."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, size, interpolation=cv2.INTER_AREA)
    return small.astype(np.float32) / 255.0


def main():
    parser = argparse.ArgumentParser(description="Generate per-frame signatures for scene-change detection.")
    parser.add_argument("--frames-dir", required=True, help="Directory containing extracted frames")
    parser.add_argument("--output-dir", required=True, help="Directory to save signature .npy files")
    parser.add_argument(
        "--method", choices=["histogram", "layout"], default="histogram",
        help="Signature method: 'histogram' (color-based, default) or 'layout' "
             "(grayscale downsized, better for slides/screen recordings). (default: histogram)"
    )

    args = parser.parse_args()

    if not os.path.isdir(args.frames_dir):
        print(f"ERROR: frames directory not found: {args.frames_dir}")
        exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    files = sorted(
        f for f in os.listdir(args.frames_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    )

    if not files:
        print(f"ERROR: no image files found in {args.frames_dir}")
        exit(1)

    print(f"Processing {len(files)} frames using '{args.method}' method...")

    for file in files:
        path = os.path.join(args.frames_dir, file)
        img = cv2.imread(path)

        if img is None:
            print(f"  WARNING: could not read {file}, skipping")
            continue

        if args.method == "histogram":
            signature = compute_histogram_signature(img)
        else:
            signature = compute_layout_signature(img)

        out_name = os.path.splitext(file)[0] + ".npy"
        np.save(os.path.join(args.output_dir, out_name), signature)

    print(f"Done. Signatures saved to {args.output_dir}")


if __name__ == "__main__":
    main()
