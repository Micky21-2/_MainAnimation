"""
classify_segments.py
======================
Classifies each detected segment (from 06_generate_segments.py) as either:

  "slide" - static content (a slide sitting still while narrated). Internal
            frame-to-frame similarity stays essentially perfect throughout
            the segment.

  "demo"  - continuously changing content (screen recording: mouse movement,
            typing, scrolling, etc.). Internal frame-to-frame similarity is
            measurably lower than a static slide, even though it never dips
            low enough to register as a scene TRANSITION.

Classification is fully automatic: each segment gets a "how static is it
internally" score, and segments are split into two groups by the largest
natural gap in that score across all segments -- no manual threshold needed.
If a video only has one segment total, automatic clustering isn't possible;
it defaults to "slide" and prints a warning (override manually if wrong).

You can also force specific segments manually with --force-demo / --force-slide,
in case the automatic split gets one wrong.

USAGE:
    python classify_segments.py \\
        --segments path/to/segments.csv \\
        --similarity-csv path/to/similarity_layout.csv \\
        --output-csv path/to/segments_classified.csv \\
        --force-demo 3,7 \\
        --force-slide 1
"""

import os
import argparse
import numpy as np
import pandas as pd


def compute_internal_similarity(similarity_df, start_sec, end_sec):
    """Mean similarity of frames strictly inside the segment (excludes the
    transition-boundary frame itself, which is expected to be low for every
    segment and would bias the score)."""
    mask = (similarity_df["frame"] > start_sec + 1) & (similarity_df["frame"] < end_sec)
    interior = similarity_df.loc[mask, "similarity"]

    if len(interior) == 0:
        return None  # too short to judge internally

    return float(interior.mean())


def auto_classify(scores):
    """Split segment indices into 'slide' (higher internal similarity) and
    'demo' (lower) groups via the largest gap in sorted scores."""
    valid = {i: s for i, s in scores.items() if s is not None}

    if len(valid) < 2:
        return {i: "slide" for i in scores}  # can't cluster with <2 data points

    sorted_items = sorted(valid.items(), key=lambda kv: kv[1], reverse=True)
    values = [v for _, v in sorted_items]

    gaps = [values[i] - values[i + 1] for i in range(len(values) - 1)]
    split_idx = int(np.argmax(gaps))  # largest drop -> boundary between groups

    slide_indices = {sorted_items[i][0] for i in range(0, split_idx + 1)}

    result = {}
    for i in scores:
        if i not in valid:
            result[i] = "slide"  # fallback for segments too short to score
        else:
            result[i] = "slide" if i in slide_indices else "demo"

    return result


def main():
    parser = argparse.ArgumentParser(description="Classify segments as 'slide' (static) or 'demo' (continuously changing).")
    parser.add_argument("--segments", required=True, help="Path to segments.csv from 06_generate_segments.py")
    parser.add_argument("--similarity-csv", required=True, help="Path to the similarity.csv used to detect these segments (must be the SAME file/method used in 06_generate_segments.py)")
    parser.add_argument("--output-csv", required=True, help="Path to save segments_classified.csv")
    parser.add_argument("--force-demo", default="", help="Comma-separated segment numbers to force as 'demo', overriding automatic classification")
    parser.add_argument("--force-slide", default="", help="Comma-separated segment numbers to force as 'slide', overriding automatic classification")

    args = parser.parse_args()

    if not os.path.exists(args.segments):
        print(f"ERROR: segments file not found: {args.segments}")
        exit(1)
    if not os.path.exists(args.similarity_csv):
        print(f"ERROR: similarity file not found: {args.similarity_csv}")
        exit(1)

    segments_df = pd.read_csv(args.segments)
    similarity_df = pd.read_csv(args.similarity_csv)

    scores = {}
    for _, row in segments_df.iterrows():
        seg = int(row["segment"])
        scores[seg] = compute_internal_similarity(similarity_df, row["start_sec"], row["end_sec"])

    classification = auto_classify(scores)

    force_demo = {int(x) for x in args.force_demo.split(",") if x.strip()}
    force_slide = {int(x) for x in args.force_slide.split(",") if x.strip()}

    overlap = force_demo & force_slide
    if overlap:
        print(f"ERROR: segments {overlap} appear in both --force-demo and --force-slide")
        exit(1)

    for seg in force_demo:
        classification[seg] = "demo"
    for seg in force_slide:
        classification[seg] = "slide"

    segments_df["mean_internal_similarity"] = segments_df["segment"].map(scores)
    segments_df["type"] = segments_df["segment"].map(classification)

    os.makedirs(os.path.dirname(os.path.abspath(args.output_csv)), exist_ok=True)
    segments_df.to_csv(args.output_csv, index=False)

    print("\nClassified segments:")
    print(segments_df[["segment", "start_sec", "end_sec", "duration_sec", "mean_internal_similarity", "type"]])

    n_slide = (segments_df["type"] == "slide").sum()
    n_demo = (segments_df["type"] == "demo").sum()
    print(f"\n{n_slide} slide segment(s), {n_demo} demo segment(s)")
    print(f"Saved to {args.output_csv}")

    if len(scores) < 2:
        print(
            "\nWARNING: only one segment total, so automatic slide/demo "
            "classification wasn't possible (defaulted to 'slide'). If this "
            "is actually a demo, rerun with --force-demo 1"
        )


if __name__ == "__main__":
    main()
