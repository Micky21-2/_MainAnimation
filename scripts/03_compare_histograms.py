"""
03_compare_histograms.py
==========================
Compares consecutive frame signatures (from 02_generate_histograms.py) and
outputs a similarity score per frame transition. Lower similarity = more
different = more likely a real transition. Works with either signature type
produced by 02_generate_histograms.py:

  histogram - flat 1D vectors -> compared via Pearson correlation
  layout    - 2D grayscale arrays -> compared via normalized pixel similarity
              (1 - mean absolute difference), which is far more sensitive to
              actual content/layout changes (recommended for slides/screen
              recordings)

Fully argument-driven — no hardcoded input/output paths.

USAGE:
    python 03_compare_histograms.py \
        --histograms-dir path/to/histograms \
        --output-csv path/to/similarity.csv \
        --method layout
"""

import os
import argparse
import numpy as np
import pandas as pd


def compare_histogram(h1, h2):
    return np.corrcoef(h1.flatten(), h2.flatten())[0, 1]


def compare_layout(s1, s2):
    diff = np.mean(np.abs(s1.astype(np.float32) - s2.astype(np.float32)))
    return 1.0 - diff


def main():
    parser = argparse.ArgumentParser(description="Compare consecutive frame signatures.")
    parser.add_argument("--histograms-dir", required=True, help="Directory containing .npy signature files")
    parser.add_argument("--output-csv", required=True, help="Path to save similarity.csv")
    parser.add_argument(
        "--method", choices=["histogram", "layout"], default="histogram",
        help="Must match the --method used in 02_generate_histograms.py (default: histogram)"
    )

    args = parser.parse_args()

    if not os.path.isdir(args.histograms_dir):
        print(f"ERROR: histograms directory not found: {args.histograms_dir}")
        exit(1)

    files = sorted(f for f in os.listdir(args.histograms_dir) if f.endswith(".npy"))

    if len(files) < 2:
        print("ERROR: need at least 2 signature files to compare.")
        exit(1)

    compare_fn = compare_histogram if args.method == "histogram" else compare_layout

    results = []

    for i in range(1, len(files)):
        s1 = np.load(os.path.join(args.histograms_dir, files[i - 1]))
        s2 = np.load(os.path.join(args.histograms_dir, files[i]))

        similarity = compare_fn(s1, s2)

        results.append([i, similarity])

    df = pd.DataFrame(results, columns=["frame", "similarity"])

    os.makedirs(os.path.dirname(os.path.abspath(args.output_csv)), exist_ok=True)
    df.to_csv(args.output_csv, index=False)

    print(f"Compared {len(files)} frames using '{args.method}' method -> {len(df)} transitions")
    print(df.head())
    print(f"\nSimilarity stats:\n{df['similarity'].describe()}")
    print(f"\nSaved to {args.output_csv}")


if __name__ == "__main__":
    main()
