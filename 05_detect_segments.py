"""
05_detect_segments.py
=======================
Diagnostic-only: prints detected transition points above a given threshold,
without generating any files. Useful for quickly sanity-checking a threshold
before committing to 06_generate_segments.py. Fully argument-driven.

USAGE:
    python 05_detect_segments.py \\
        --input-csv path/to/similarity.csv \\
        --threshold 0.90
"""

import argparse
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description="Print detected transition points from a similarity CSV.")
    parser.add_argument("--input-csv", required=True, help="Path to similarity.csv")
    parser.add_argument("--threshold", type=float, default=0.90, help="Similarity below this value is flagged (default: 0.90)")

    args = parser.parse_args()

    df = pd.read_csv(args.input_csv)

    drops = df[df["similarity"] < args.threshold]

    print(f"\nDetected Transition Points (threshold < {args.threshold})")
    print("-" * 50)

    for _, row in drops.iterrows():
        frame = int(row["frame"])
        seconds = frame
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60

        print(f"Frame {frame:5d} | {h:02}:{m:02}:{s:02} | Similarity = {row['similarity']:.3f}")

    print(f"\nTotal transitions flagged: {len(drops)}")


if __name__ == "__main__":
    main()
