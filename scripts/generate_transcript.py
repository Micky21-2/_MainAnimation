"""
generate_transcript.py
=======================
Transcribes the narration audio into a timestamped .srt subtitle file, ready
to be burned into the bottom of the final lecture video by compose_lecture.py.

Requires faster-whisper:
    pip install faster-whisper

USAGE:
    python generate_transcript.py \\
        --audio narration.wav \\
        --output transcript.srt \\
        --model medium

Model options (speed vs accuracy tradeoff): tiny, base, small, medium, large-v3
"medium" is a good default balance for lecture-style narration.
"""

import argparse


def format_timestamp(seconds: float) -> str:
    """Convert seconds -> SRT timestamp format HH:MM:SS,mmm"""
    millis = int(round(seconds * 1000))
    hours = millis // 3_600_000
    millis %= 3_600_000
    minutes = millis // 60_000
    millis %= 60_000
    secs = millis // 1000
    millis %= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(segments, output_path: str):
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            f.write(f"{i}\n")
            f.write(f"{format_timestamp(seg['start'])} --> {format_timestamp(seg['end'])}\n")
            f.write(f"{seg['text'].strip()}\n\n")


def main():
    parser = argparse.ArgumentParser(
        description="Generate a timestamped .srt transcript from narration audio using Whisper"
    )
    parser.add_argument("--audio", required=True, help="Path to the narration audio file")
    parser.add_argument("--output", required=True, help="Path for the output .srt file")
    parser.add_argument(
        "--model",
        default="medium",
        choices=["tiny", "base", "small", "medium", "large-v3"],
        help="Whisper model size (default: medium)"
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Force a language code (e.g. 'en'). Default: auto-detect."
    )
    parser.add_argument(
        "--max-line-chars",
        type=int,
        default=42,
        help="Roughly how many characters per caption line before Whisper's natural segment breaks are used as-is (default: 42, just informational — Whisper handles its own segmentation)"
    )

    args = parser.parse_args()

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("ERROR: faster-whisper is not installed.")
        print("Install it with: pip install faster-whisper")
        exit(1)

    import os
    if not os.path.exists(args.audio):
        print(f"ERROR: audio file not found: {args.audio}")
        exit(1)

    print(f"Loading Whisper model '{args.model}'...")
    model = WhisperModel(args.model, device="auto", compute_type="auto")

    print(f"Transcribing {args.audio}...")
    segments_gen, info = model.transcribe(
        args.audio,
        language=args.language,
        vad_filter=True,  # trims silence, keeps captions tighter to speech
    )

    print(f"Detected language: {info.language} (probability {info.language_probability:.2f})")

    segments = []
    for seg in segments_gen:
        segments.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
        })
        print(f"  [{format_timestamp(seg.start)} --> {format_timestamp(seg.end)}] {seg.text.strip()}")

    if not segments:
        print("WARNING: no speech detected — transcript will be empty.")

    write_srt(segments, args.output)
    print(f"\nDone. Transcript saved to {args.output} ({len(segments)} caption lines)")


if __name__ == "__main__":
    main()