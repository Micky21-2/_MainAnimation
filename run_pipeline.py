"""
run_pipeline.py
================
Orchestrates the full lecture-video pipeline end to end, for ANY set of
inputs (any character images, any narration audio, any reference video for
slide detection). No filenames or paths are hardcoded — everything comes
from CLI arguments, or from the run's own working/output directories.

USAGE:
    python run_pipeline.py \\
        --run-name my_lecture \\
        --image1 inputs/pose1.jpg \\
        --image2 inputs/pose2.jpg \\
        --narration inputs/narration.wav \\
        --reference-video inputs/recording.mp4 \\
        --comfy-output-dir /path/to/ComfyUI/output \\
        --base-dir .

This runs, in order:
  1. ltx_pipeline.py           -> talking-head animation (outputs/<run>/final.mp4)
  2. generate_transcript.py    -> transcript.srt (only if --subtitles)
  3. slide detection (01,02,03,06) -> segments.csv (skipped if --skip-slides)
  4. classify_segments.py      -> segments_classified.csv (only if --detect-demo-segments)
  5. build_slide_timeline.py   -> timeline.json + extracted slide images / demo clips
  6. compose_lecture.py        -> outputs/<run>/lecture_final.mp4

Every intermediate file lands under <base-dir>/work/<run-name>/, and final
outputs land under <base-dir>/outputs/<run-name>/.

You can also run each phase independently by calling the individual scripts
directly — see the printed commands as this script runs, or the pipeline
README, for the equivalent standalone invocations.
"""

import os
import sys
import argparse
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run_step(description, cmd):
    print(f"\n{'=' * 60}")
    print(f"STEP: {description}")
    print(f"{'=' * 60}")
    print(" ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\nERROR: step failed -> {description}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Run the full lecture pipeline end to end.")
    parser.add_argument("--run-name", required=True, help="Name for this run (used to namespace all output/work dirs)")
    parser.add_argument("--image1", required=True, help="First character image (opening frame)")
    parser.add_argument("--image2", required=True, help="Second character image (stable frame for rest of video)")
    parser.add_argument("--narration", required=True, help="Narration audio file (WAV/MP3) for the talking-head video")
    parser.add_argument("--reference-video", required=True, help="Reference/recording video to detect slide transitions from")
    parser.add_argument("--comfy-output-dir", required=True, help="ComfyUI output directory")
    parser.add_argument("--comfy-input-dir", default=None, help="ComfyUI input directory (optional, for cleanup between segments)")
    parser.add_argument("--comfyui-url", default="http://127.0.0.1:8188", help="ComfyUI server URL")
    parser.add_argument("--base-dir", default=".", help="Base directory containing work/ and outputs/ (default: current directory)")
    parser.add_argument("--prompt", default=None, help="Custom generation prompt for the talking-head video (optional)")
    parser.add_argument("--segment-secs", type=int, default=20, help="Audio chunk length for the talking-head pipeline (default: 20)")
    parser.add_argument("--frame-interval-sec", type=float, default=1.0, help="Sampling interval for slide-detection frames (default: 1.0)")
    parser.add_argument("--similarity-threshold", type=float, default=None, help="Manual similarity threshold for slide transition detection (optional -- automatic detection is used if omitted)")
    parser.add_argument("--expected-slides", type=int, default=None, help="Known slide count to auto-tune detection sensitivity (optional -- automatic detection is used if omitted)")
    parser.add_argument("--detection-sensitivity", type=float, default=6.0, help="Sensitivity for automatic slide-transition detection (lower = more transitions found, default: 6.0). Only used when neither --similarity-threshold nor --expected-slides is given.")
    parser.add_argument(
        "--signature-method", choices=["histogram", "layout"], default="layout",
        help="Slide-change detection method: 'layout' (grayscale content-based, recommended for "
             "slides/screen recordings, default) or 'histogram' (color-based, better for videos "
             "cutting between visually distinct colored scenes)"
    )
    parser.add_argument("--whisper-model", default="medium", help="Whisper model size for transcription (default: medium)")
    parser.add_argument("--subtitles", action="store_true", help="Generate and burn in transcript captions")
    parser.add_argument("--skip-slides", action="store_true", help="Skip slide detection (use an existing timeline.json in the work dir instead)")
    parser.add_argument("--detect-demo-segments", action="store_true", help="Classify segments as 'slide' vs 'demo' and render demo segments full-screen (without the talking head). If omitted, all segments are treated as slides (previous behavior).")
    parser.add_argument("--width", type=int, default=1920, help="Final output canvas width (default: 1920)")
    parser.add_argument("--height", type=int, default=1080, help="Final output canvas height (default: 1080)")
    parser.add_argument("--talking-head-ratio", type=float, default=0.28, help="Fraction of canvas width for the talking head (default: 0.28 -- talking head 28%% / slides 72%%)")
    parser.add_argument("--vary-layout", action="store_true", help="Add layout variety: a slide's side only swaps once THAT slide has been on screen longer than --side-flip-threshold, via a smooth full-screen-anchor + crossfade (see --side-flip-threshold, --transition-anchor)")
    parser.add_argument(
        "--side-flip-threshold",
        type=float,
        default=210.0,
        help=(
            "With --vary-layout: cumulative lecture seconds spent on the "
            "current side before changing sides. Time accumulates across "
            "multiple slides. Default: 210 seconds."
        )
    )    
    parser.add_argument(
        "--transition-anchor",
        choices=["character", "slide", "alternating"],
        default="alternating",
        help=(
            "With --vary-layout: what to show full-screen before a side swap. "
            "character = always talking head, "
            "slide = always full-screen slide, "
            "alternating = character, slide, character, slide, ..."
        )
    )    
    parser.add_argument(
        "--character-anchor-duration",
        type=float,
        default=5.0,
        help="With --vary-layout: full-screen character duration in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--slide-anchor-duration",
        type=float,
        default=10.0,
        help="With --vary-layout: full-screen slide duration in seconds (default: 10.0)",
    )
    parser.add_argument("--crossfade-duration", type=float, default=2.0, help="With --vary-layout: seconds the crossfade dissolve itself takes (default: 1.0)")
    parser.add_argument("--subtitle-font-size", type=int, default=10, help="Subtitle font size in pixels (default: 10)")
    parser.add_argument("--subtitle-margin", type=int, default=None, help="Explicit subtitle margin from the bottom of its caption bar, in pixels (default: auto-centered in the bar)")
    parser.add_argument("--subtitle-bar-height", type=int, default=None, help="Height (px) of the dedicated caption bar reserved below the content when --subtitles is used (default: 9%% of --height)")

    args = parser.parse_args()

    work_dir = os.path.join(args.base_dir, "work", args.run_name)
    output_dir = os.path.join(args.base_dir, "outputs", args.run_name)

    frames_dir = os.path.join(work_dir, "frames")
    histograms_dir = os.path.join(work_dir, "histograms")
    results_dir = os.path.join(work_dir, "results")
    slides_dir = os.path.join(work_dir, "slides")
    demo_clips_dir = os.path.join(work_dir, "demo_clips")

    similarity_csv = os.path.join(results_dir, "similarity.csv")
    segments_csv = os.path.join(results_dir, "segments.csv")
    segments_classified_csv = os.path.join(results_dir, "segments_classified.csv")
    timeline_json = os.path.join(work_dir, "timeline.json")
    transcript_srt = os.path.join(work_dir, "transcript.srt")

    final_animation = os.path.join(output_dir, "final.mp4")
    final_lecture = os.path.join(output_dir, "lecture_final.mp4")

    for d in [work_dir, results_dir, output_dir]:
        os.makedirs(d, exist_ok=True)

    # ---------- Phase 1: talking-head animation ----------
    ltx_cmd = [
        sys.executable, os.path.join(SCRIPT_DIR, "ltx_pipeline.py"),
        "--image1", args.image1,
        "--image2", args.image2,
        "--audio", args.narration,
        "--run-name", args.run_name,
        "--comfy-output-dir", args.comfy_output_dir,
        "--work-dir", os.path.join(args.base_dir, "work_ltx"),
        "--output-dir", os.path.join(args.base_dir, "outputs"),
        "--comfyui-url", args.comfyui_url,
        "--segment-secs", str(args.segment_secs),
    ]
    if args.comfy_input_dir:
        ltx_cmd += ["--comfy-input-dir", args.comfy_input_dir]
    if args.prompt:
        ltx_cmd += ["--prompt", args.prompt]

    run_step("Generate talking-head animation", ltx_cmd)

    # ---------- Phase 2: transcript ----------
    if args.subtitles:
        run_step("Generate transcript", [
            sys.executable, os.path.join(SCRIPT_DIR, "generate_transcript.py"),
            "--audio", args.narration,
            "--output", transcript_srt,
            "--model", args.whisper_model,
        ])

    # ---------- Phase 3: slide detection ----------
    if not args.skip_slides:
        run_step("Extract frames from reference video", [
            sys.executable, os.path.join(SCRIPT_DIR, "01_extract_frames.py"),
            "--video", args.reference_video,
            "--output-dir", frames_dir,
            "--interval-sec", str(args.frame_interval_sec),
        ])

        run_step("Generate histograms", [
            sys.executable, os.path.join(SCRIPT_DIR, "02_generate_histograms.py"),
            "--frames-dir", frames_dir,
            "--output-dir", histograms_dir,
            "--method", args.signature_method,
        ])

        run_step("Compare histograms", [
            sys.executable, os.path.join(SCRIPT_DIR, "03_compare_histograms.py"),
            "--histograms-dir", histograms_dir,
            "--output-csv", similarity_csv,
            "--method", args.signature_method,
        ])

        detect_cmd = [
            sys.executable, os.path.join(SCRIPT_DIR, "06_generate_segments.py"),
            "--input-csv", similarity_csv,
            "--video", args.reference_video,
            "--output-csv", segments_csv,
        ]
        if args.expected_slides is not None:
            detect_cmd += ["--expected-slides", str(args.expected_slides)]
        elif args.similarity_threshold is not None:
            detect_cmd += ["--threshold", str(args.similarity_threshold)]
        else:
            detect_cmd += ["--sensitivity", str(args.detection_sensitivity)]

        run_step("Detect segments", detect_cmd)

        if args.detect_demo_segments:
            run_step("Classify segments (slide vs demo)", [
                sys.executable, os.path.join(SCRIPT_DIR, "classify_segments.py"),
                "--segments", segments_csv,
                "--similarity-csv", similarity_csv,
                "--output-csv", segments_classified_csv,
            ])
            timeline_source_csv = segments_classified_csv
        else:
            timeline_source_csv = segments_csv

        run_step("Build lecture timeline", [
            sys.executable, os.path.join(SCRIPT_DIR, "build_slide_timeline.py"),
            "--segments", timeline_source_csv,
            "--source-video", args.reference_video,
            "--slides-out-dir", slides_dir,
            "--demo-clips-out-dir", demo_clips_dir,
            "--timeline-out", timeline_json,
        ])
    else:
        if not os.path.exists(timeline_json):
            print(f"ERROR: --skip-slides was set but no timeline.json found at {timeline_json}")
            sys.exit(1)
        print(f"\nSkipping slide detection, using existing {timeline_json}")

    # ---------- Phase 3.5: optional layout variation ----------
    final_timeline_json = timeline_json
    if args.vary_layout:
        varied_timeline_json = os.path.join(work_dir, "timeline_varied.json")
        run_step("Vary layout (per-slide side-swap with smooth transition)", [
            sys.executable, os.path.join(SCRIPT_DIR, "vary_layout.py"),
            "--timeline", timeline_json,
            "--output", varied_timeline_json,
            "--side-flip-threshold", str(args.side_flip_threshold),
            "--transition-anchor", args.transition_anchor,
            "--character-anchor-duration", str(args.character_anchor_duration),
            "--slide-anchor-duration", str(args.slide_anchor_duration),
            "--crossfade-duration", str(args.crossfade_duration),
        ])
        final_timeline_json = varied_timeline_json

    # ---------- Phase 4: composite final lecture video ----------
    compose_cmd = [
        sys.executable, os.path.join(SCRIPT_DIR, "compose_lecture.py"),
        "--talking-head", final_animation,
        "--timeline", final_timeline_json,
        "--output", final_lecture,
        "--width", str(args.width),
        "--height", str(args.height),
        "--talking-head-ratio", str(args.talking_head_ratio),
    ]
    if args.subtitles:
        compose_cmd += ["--subtitles", transcript_srt]
    if args.subtitle_font_size is not None:
        compose_cmd += ["--subtitle-font-size", str(args.subtitle_font_size)]
    if args.subtitle_margin is not None:
        compose_cmd += ["--subtitle-margin", str(args.subtitle_margin)]
    if args.subtitle_bar_height is not None:
        compose_cmd += ["--subtitle-bar-height", str(args.subtitle_bar_height)]

    run_step("Composite final lecture video", compose_cmd)

    print(f"\n{'=' * 60}")
    print("PIPELINE COMPLETE")
    print(f"{'=' * 60}")
    print(f"Talking-head animation: {final_animation}")
    print(f"Final lecture video:    {final_lecture}")


if __name__ == "__main__":
    main()
