"""
run_pipeline.py
===============

Runs the complete lecture-video generation pipeline.

Pipeline:

0. Clean narration audio (denoise + remove long pauses) and cut the
   reference video to match, so audio/video stay frame-accurate in sync
1. Generate talking-head animation
2. Generate transcript
3. Detect slides
4. Classify slide/demo segments
5. Build lecture timeline
6. Add layout variation
7. Composite final lecture video

Every step after Phase 0 runs on the CLEANED audio/video, not the originals
(pass --skip-audio-cleanup to opt out and use the raw files instead).

Layout variation:

    1st side change
        -> character full-screen 5s

    2nd side change
        -> slide full-screen 10s

    3rd side change
        -> character full-screen 5s

    4th side change
        -> slide full-screen 10s

All side changes use 1.5s crossfades.
"""

import os
import sys
import argparse
import subprocess


SCRIPT_DIR = os.path.dirname(
    os.path.abspath(__file__)
)


# ============================================================
# RUN STEP
# ============================================================

def run_step(
    description,
    cmd
):

    print()
    print("=" * 60)
    print(
        f"STEP: {description}"
    )
    print("=" * 60)

    print(
        " ".join(
            str(x)
            for x in cmd
        )
    )

    result = subprocess.run(
        cmd
    )

    if result.returncode != 0:

        print()
        print(
            f"ERROR: step failed -> "
            f"{description}"
        )

        sys.exit(
            result.returncode
        )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Run the complete lecture "
            "video pipeline."
        )
    )

    # --------------------------------------------------------
    # INPUTS
    # --------------------------------------------------------

    parser.add_argument(
        "--run-name",
        required=True
    )

    parser.add_argument(
        "--image1",
        required=True
    )

    parser.add_argument(
        "--image2",
        required=True
    )

    parser.add_argument(
        "--narration",
        required=True
    )

    parser.add_argument(
        "--reference-video",
        required=True
    )

    # --------------------------------------------------------
    # COMFYUI
    # --------------------------------------------------------

    parser.add_argument(
        "--comfy-output-dir",
        required=True
    )

    parser.add_argument(
        "--comfy-input-dir",
        default=None
    )

    parser.add_argument(
        "--comfyui-url",
        default="http://127.0.0.1:8188"
    )

    # --------------------------------------------------------
    # DIRECTORIES
    # --------------------------------------------------------

    parser.add_argument(
        "--base-dir",
        default="."
    )

    # --------------------------------------------------------
    # LTX
    # --------------------------------------------------------

    parser.add_argument(
        "--prompt",
        default=None
    )

    parser.add_argument(
        "--segment-secs",
        type=int,
        default=20
    )

    # --------------------------------------------------------
    # SLIDE DETECTION
    # --------------------------------------------------------

    parser.add_argument(
        "--frame-interval-sec",
        type=float,
        default=1.0
    )

    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=None
    )

    parser.add_argument(
        "--expected-slides",
        type=int,
        default=None
    )

    parser.add_argument(
        "--detection-sensitivity",
        type=float,
        default=6.0
    )

    parser.add_argument(
        "--signature-method",
        choices=[
            "histogram",
            "layout"
        ],
        default="layout"
    )

    # --------------------------------------------------------
    # TRANSCRIPTION
    # --------------------------------------------------------

    parser.add_argument(
        "--whisper-model",
        default="medium"
    )

    parser.add_argument(
        "--subtitles",
        action="store_true"
    )

    # --------------------------------------------------------
    # SLIDE / DEMO
    # --------------------------------------------------------

    parser.add_argument(
        "--skip-slides",
        action="store_true"
    )

    parser.add_argument(
        "--detect-demo-segments",
        action="store_true"
    )

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    parser.add_argument(
        "--width",
        type=int,
        default=1920
    )

    parser.add_argument(
        "--height",
        type=int,
        default=1080
    )

    parser.add_argument(
        "--talking-head-ratio",
        type=float,
        default=0.30
    )

    # --------------------------------------------------------
    # LAYOUT VARIATION
    # --------------------------------------------------------

    parser.add_argument(
        "--vary-layout",
        action="store_true",
        help=(
            "Enable side changes and "
            "full-screen transitions."
        )
    )

    parser.add_argument(
        "--side-flip-threshold",
        type=float,
        default=210.0,
        help=(
            "Cumulative slide time before "
            "changing sides."
        )
    )

    parser.add_argument(
        "--transition-anchor",
        choices=[
            "character",
            "slide",
            "alternating"
        ],
        default="alternating",
        help=(
            "Full-screen transition type. "
            "Alternating gives character, "
            "slide, character, slide..."
        )
    )

    parser.add_argument(
        "--character-anchor-duration",
        type=float,
        default=5.0,
        help=(
            "Full-screen character duration."
        )
    )

    parser.add_argument(
        "--slide-anchor-duration",
        type=float,
        default=10.0,
        help=(
            "Full-screen slide duration."
        )
    )

    parser.add_argument(
        "--crossfade-duration",
        type=float,
        default=1.5,
        help=(
            "Crossfade duration."
        )
    )

    # --------------------------------------------------------
    # AUDIO CLEANUP (PHASE 0: pause removal, denoise, enhance)
    # --------------------------------------------------------

    parser.add_argument(
        "--skip-audio-cleanup",
        action="store_true",
        help=(
            "Skip Phase 0 entirely and use --narration / --reference-video "
            "as-is for the rest of the pipeline."
        )
    )

    parser.add_argument(
        "--pause-threshold-db",
        type=float,
        default=-30.0,
        help="Volume (dB) below which audio counts as silence (default: -30)"
    )

    parser.add_argument(
        "--min-pause-sec",
        type=float,
        default=0.7,
        help="Only pauses at least this long get cut (default: 0.7s)"
    )

    parser.add_argument(
        "--keep-pause-sec",
        type=float,
        default=0.15,
        help=(
            "Shrink each long pause to this length instead of deleting it "
            "entirely, for a natural-sounding cut (default: 0.15s, use 0 "
            "to remove pauses completely)."
        )
    )

    parser.add_argument(
        "--denoise-strength",
        type=float,
        default=12.0,
        help="Background-noise reduction strength in dB (default: 12)"
    )

    parser.add_argument(
        "--disable-denoise",
        action="store_true"
    )

    parser.add_argument(
        "--disable-loudnorm",
        action="store_true"
    )

    parser.add_argument(
        "--disable-pause-removal",
        action="store_true",
        help="Still enhances/denoises audio, but skips cutting pauses."
    )

    # --------------------------------------------------------
    # SUBTITLE OPTIONS
    # --------------------------------------------------------

    parser.add_argument(
        "--subtitle-font-size",
        type=int,
        default=10
    )

    parser.add_argument(
        "--subtitle-margin",
        type=int,
        default=None
    )

    parser.add_argument(
        "--subtitle-bar-height",
        type=int,
        default=None
    )

    args = parser.parse_args()

    # ========================================================
    # DIRECTORIES
    # ========================================================

    work_dir = os.path.join(
        args.base_dir,
        "work",
        args.run_name
    )

    output_dir = os.path.join(
        args.base_dir,
        "outputs",
        args.run_name
    )

    frames_dir = os.path.join(
        work_dir,
        "frames"
    )

    histograms_dir = os.path.join(
        work_dir,
        "histograms"
    )

    results_dir = os.path.join(
        work_dir,
        "results"
    )

    slides_dir = os.path.join(
        work_dir,
        "slides"
    )

    demo_clips_dir = os.path.join(
        work_dir,
        "demo_clips"
    )

    audio_process_dir = os.path.join(
        work_dir,
        "audio_process"
    )

    processed_narration = os.path.join(
        audio_process_dir,
        "narration_clean.wav"
    )

    processed_reference_video = os.path.join(
        audio_process_dir,
        "reference_clean.mp4"
    )

    similarity_csv = os.path.join(
        results_dir,
        "similarity.csv"
    )

    segments_csv = os.path.join(
        results_dir,
        "segments.csv"
    )

    classified_csv = os.path.join(
        results_dir,
        "segments_classified.csv"
    )

    timeline_json = os.path.join(
        work_dir,
        "timeline.json"
    )

    varied_timeline_json = os.path.join(
        work_dir,
        "timeline_varied.json"
    )

    transcript_srt = os.path.join(
        work_dir,
        "transcript.srt"
    )

    final_animation = os.path.join(
        output_dir,
        "final.mp4"
    )

    final_lecture = os.path.join(
        output_dir,
        "lecture_final.mp4"
    )

    for directory in [
        work_dir,
        output_dir,
        results_dir
    ]:

        os.makedirs(
            directory,
            exist_ok=True
        )

    # ========================================================
    # PHASE 0
    # AUDIO CLEANUP (denoise + remove long pauses) & VIDEO SYNC
    #
    # Runs before everything else: every later step assumes the
    # narration audio and reference video share one timeline, so any
    # time we cut from the audio has to be cut from the video too.
    # ========================================================

    if args.skip_audio_cleanup:

        print(
            "\nSkipping audio cleanup (--skip-audio-cleanup). "
            "Using original narration/reference video."
        )

        narration_for_pipeline = args.narration
        reference_video_for_pipeline = args.reference_video

    else:

        os.makedirs(
            audio_process_dir,
            exist_ok=True
        )

        audio_process_cmd = [
            sys.executable,

            os.path.join(
                SCRIPT_DIR,
                "00_process_audio.py"
            ),

            "--audio",
            args.narration,

            "--video",
            args.reference_video,

            "--output-dir",
            audio_process_dir,

            "--processed-audio-out",
            processed_narration,

            "--processed-video-out",
            processed_reference_video,

            "--pause-threshold-db",
            str(args.pause_threshold_db),

            "--min-pause-sec",
            str(args.min_pause_sec),

            "--keep-pause-sec",
            str(args.keep_pause_sec),

            "--denoise-strength",
            str(args.denoise_strength),
        ]

        if args.disable_denoise:
            audio_process_cmd += ["--disable-denoise"]

        if args.disable_loudnorm:
            audio_process_cmd += ["--disable-loudnorm"]

        if args.disable_pause_removal:
            audio_process_cmd += ["--disable-pause-removal"]

        run_step(
            "Clean narration audio (denoise + remove long pauses) "
            "and sync reference video",
            audio_process_cmd
        )

        narration_for_pipeline = processed_narration
        reference_video_for_pipeline = processed_reference_video

    # Everything downstream uses the CLEANED, IN-SYNC audio/video --
    # never the original args.narration / args.reference_video directly.

    # ========================================================
    # PHASE 1
    # TALKING HEAD
    # ========================================================

    ltx_cmd = [
        sys.executable,

        os.path.join(
            SCRIPT_DIR,
            "ltx_pipeline.py"
        ),

        "--image1",
        args.image1,

        "--image2",
        args.image2,

        "--audio",
        narration_for_pipeline,

        "--run-name",
        args.run_name,

        "--comfy-output-dir",
        args.comfy_output_dir,

        "--work-dir",
        os.path.join(
            args.base_dir,
            "work_ltx"
        ),

        "--output-dir",
        os.path.join(
            args.base_dir,
            "outputs"
        ),

        "--comfyui-url",
        args.comfyui_url,

        "--segment-secs",
        str(args.segment_secs)
    ]

    if args.comfy_input_dir:

        ltx_cmd += [
            "--comfy-input-dir",
            args.comfy_input_dir
        ]

    if args.prompt:

        ltx_cmd += [
            "--prompt",
            args.prompt
        ]

    run_step(
        "Generate talking-head animation",
        ltx_cmd
    )

    # ========================================================
    # PHASE 2
    # TRANSCRIPT
    # ========================================================

    if args.subtitles:

        run_step(
            "Generate transcript",
            [
                sys.executable,

                os.path.join(
                    SCRIPT_DIR,
                    "generate_transcript.py"
                ),

                "--audio",
                narration_for_pipeline,

                "--output",
                transcript_srt,

                "--model",
                args.whisper_model
            ]
        )

    # ========================================================
    # PHASE 3
    # SLIDE DETECTION
    # ========================================================

    if not args.skip_slides:

        run_step(
            "Extract frames",
            [
                sys.executable,

                os.path.join(
                    SCRIPT_DIR,
                    "01_extract_frames.py"
                ),

                "--video",
                reference_video_for_pipeline,

                "--output-dir",
                frames_dir,

                "--interval-sec",
                str(
                    args.frame_interval_sec
                )
            ]
        )

        run_step(
            "Generate slide signatures",
            [
                sys.executable,

                os.path.join(
                    SCRIPT_DIR,
                    "02_generate_histograms.py"
                ),

                "--frames-dir",
                frames_dir,

                "--output-dir",
                histograms_dir,

                "--method",
                args.signature_method
            ]
        )

        run_step(
            "Compare slide signatures",
            [
                sys.executable,

                os.path.join(
                    SCRIPT_DIR,
                    "03_compare_histograms.py"
                ),

                "--histograms-dir",
                histograms_dir,

                "--output-csv",
                similarity_csv,

                "--method",
                args.signature_method
            ]
        )

        detect_cmd = [
            sys.executable,

            os.path.join(
                SCRIPT_DIR,
                "06_generate_segments.py"
            ),

            "--input-csv",
            similarity_csv,

            "--video",
            reference_video_for_pipeline,

            "--output-csv",
            segments_csv
        ]

        if (
            args.expected_slides
            is not None
        ):

            detect_cmd += [
                "--expected-slides",
                str(
                    args.expected_slides
                )
            ]

        elif (
            args.similarity_threshold
            is not None
        ):

            detect_cmd += [
                "--threshold",
                str(
                    args.similarity_threshold
                )
            ]

        else:

            detect_cmd += [
                "--sensitivity",
                str(
                    args.detection_sensitivity
                )
            ]

        run_step(
            "Detect segments",
            detect_cmd
        )

        # ----------------------------------------------------
        # Classify slide / demo
        # ----------------------------------------------------

        if args.detect_demo_segments:

            run_step(
                "Classify slide/demo segments",
                [
                    sys.executable,

                    os.path.join(
                        SCRIPT_DIR,
                        "classify_segments.py"
                    ),

                    "--segments",
                    segments_csv,

                    "--similarity-csv",
                    similarity_csv,

                    "--output-csv",
                    classified_csv
                ]
            )

            timeline_source = (
                classified_csv
            )

        else:

            timeline_source = (
                segments_csv
            )

        # ----------------------------------------------------
        # Build timeline
        # ----------------------------------------------------

        run_step(
            "Build lecture timeline",
            [
                sys.executable,

                os.path.join(
                    SCRIPT_DIR,
                    "build_slide_timeline.py"
                ),

                "--segments",
                timeline_source,

                "--source-video",
                reference_video_for_pipeline,

                "--slides-out-dir",
                slides_dir,

                "--demo-clips-out-dir",
                demo_clips_dir,

                "--timeline-out",
                timeline_json
            ]
        )

    else:

        if not os.path.exists(
            timeline_json
        ):

            raise FileNotFoundError(
                f"--skip-slides was used, "
                f"but timeline does not exist: "
                f"{timeline_json}"
            )

        print(
            f"Skipping slide detection. "
            f"Using {timeline_json}"
        )

    # ========================================================
    # PHASE 3.5
    # VARY LAYOUT
    # ========================================================

    final_timeline = timeline_json

    if args.vary_layout:

        run_step(
            "Vary layout "
            "(alternating full-screen transitions)",
            [
                sys.executable,

                os.path.join(
                    SCRIPT_DIR,
                    "vary_layout.py"
                ),

                "--timeline",
                timeline_json,

                "--output",
                varied_timeline_json,

                "--side-flip-threshold",
                str(
                    args.side_flip_threshold
                ),

                "--transition-anchor",
                args.transition_anchor,

                "--character-anchor-duration",
                str(
                    args.character_anchor_duration
                ),

                "--slide-anchor-duration",
                str(
                    args.slide_anchor_duration
                ),

                "--crossfade-duration",
                str(
                    args.crossfade_duration
                )
            ]
        )

        final_timeline = (
            varied_timeline_json
        )

    # ========================================================
    # PHASE 4
    # COMPOSE
    # ========================================================

    compose_cmd = [
        sys.executable,

        os.path.join(
            SCRIPT_DIR,
            "compose_lecture.py"
        ),

        "--talking-head",
        final_animation,

        "--timeline",
        final_timeline,

        "--output",
        final_lecture,

        "--width",
        str(args.width),

        "--height",
        str(args.height),

        "--talking-head-ratio",
        str(
            args.talking_head_ratio
        )
    ]

    if args.subtitles:

        compose_cmd += [
            "--subtitles",
            transcript_srt
        ]

    compose_cmd += [
        "--subtitle-font-size",
        str(
            args.subtitle_font_size
        )
    ]

    if args.subtitle_margin is not None:

        compose_cmd += [
            "--subtitle-margin",
            str(
                args.subtitle_margin
            )
        ]

    if (
        args.subtitle_bar_height
        is not None
    ):

        compose_cmd += [
            "--subtitle-bar-height",
            str(
                args.subtitle_bar_height
            )
        ]

    run_step(
        "Composite final lecture video",
        compose_cmd
    )

    # ========================================================
    # COMPLETE
    # ========================================================

    print()
    print("=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)

    print(
        f"Talking-head animation: "
        f"{final_animation}"
    )

    print(
        f"Final lecture video:    "
        f"{final_lecture}"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()