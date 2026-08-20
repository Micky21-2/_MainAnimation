"""
04_plot_similarity.py
=======================
Plots frame-to-frame similarity over the video, to help you sanity-check the
detection threshold before running 06_generate_segments.py.
Fully argument-driven — no hardcoded input path.

USAGE:
    python 04_plot_similarity.py \\
        --input-csv path/to/similarity.csv \\
        --output-image path/to/similarity_plot.png

    (omit --output-image to just display it interactively instead)
"""

import argparse
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description="Plot histogram similarity across a video.")
    parser.add_argument("--input-csv", required=True, help="Path to similarity.csv")
    parser.add_argument(
        "--output-image", default=None,
        help="Path to save the plot as an image instead of showing it interactively (recommended for headless/server environments)"
    )

    args = parser.parse_args()

    if args.output_image:
        matplotlib.use("Agg")  # headless-safe backend

    df = pd.read_csv(args.input_csv)

    plt.figure(figsize=(12, 5))
    plt.plot(df["similarity"])
    plt.xlabel("Frame")
    plt.ylabel("Similarity")
    plt.title("Histogram Similarity Across Video")
    plt.grid()

    if args.output_image:
        plt.savefig(args.output_image, dpi=150, bbox_inches="tight")
        print(f"Saved plot to {args.output_image}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
