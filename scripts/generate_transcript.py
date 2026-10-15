"""
generate_transcript.py
=======================
Transcribes the narration audio into a timestamped .srt subtitle file with
exact word-level synchronization using faster-whisper.

Subtitles are grouped into concise, natural reading lines whose start
and end timestamps match the exact speech timing of the speaker.

Requires faster-whisper:
    pip install faster-whisper

USAGE:
    python generate_transcript.py \\
        --audio narration.wav \\
        --output transcript.srt \\
        --model medium
"""

import os
import argparse


def format_timestamp(seconds: float) -> str:
    """Convert seconds -> SRT timestamp format HH:MM:SS,mmm"""
    seconds = max(0.0, seconds)
    millis = int(round(seconds * 1000))
    hours = millis // 3_600_000
    millis %= 3_600_000
    minutes = millis // 60_000
    millis %= 60_000
    secs = millis // 1000
    millis %= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(cues, output_path: str):
    """Write subtitle cues to SRT format."""
    with open(output_path, "w", encoding="utf-8") as f:
        for i, cue in enumerate(cues, start=1):
            f.write(f"{i}\n")
            f.write(f"{format_timestamp(cue['start'])} --> {format_timestamp(cue['end'])}\n")
            f.write(f"{cue['text'].strip()}\n\n")


def build_cues_from_segments(
    segments_gen,
    max_line_chars: int = 42,
    max_line_words: int = 8,
    max_line_duration: float = 3.5,
    pause_threshold: float = 0.45,
    min_cue_duration: float = 0.8,
    time_offset: float = 0.0,
):
    """
    Groups word-level timestamps from faster-whisper into clean, concise
    subtitle cues that appear and disappear exactly on time with speech.
    """
    raw_cues = []
    current_words = []

    def flush_words():
        if not current_words:
            return
        cue_text = "".join(w.word for w in current_words).strip()
        if not cue_text:
            current_words.clear()
            return
        start = current_words[0].start
        end = current_words[-1].end
        # Ensure minimum duration so viewer can comfortably read
        if end - start < min_cue_duration:
            end = start + min_cue_duration
        raw_cues.append({
            "start": start,
            "end": end,
            "text": cue_text,
        })
        current_words.clear()

    for seg in segments_gen:
        # Fallback if model did not produce word timestamps
        if not getattr(seg, "words", None):
            flush_words()
            seg_text = seg.text.strip()
            if seg_text:
                start = seg.start
                end = max(seg.end, start + min_cue_duration)
                raw_cues.append({
                    "start": start,
                    "end": end,
                    "text": seg_text,
                })
            continue

        for w in seg.words:
            if not w.word.strip():
                continue

            if not current_words:
                current_words.append(w)
                continue

            gap = w.start - current_words[-1].end
            accumulated_text = "".join(cw.word for cw in current_words)
            new_text_len = len(accumulated_text + w.word)
            duration = w.end - current_words[0].start
            prev_word = current_words[-1].word.strip()

            should_split = False
            # Natural pause between words
            if gap >= pause_threshold:
                should_split = True
            # Terminal punctuation (. ? ! ;)
            elif prev_word.endswith((".", "?", "!", ";")):
                should_split = True
            # Comma after moderate length
            elif prev_word.endswith(",") and len(accumulated_text.strip()) >= 22:
                should_split = True
            # Length or duration boundary
            elif (
                new_text_len > max_line_chars
                or len(current_words) >= max_line_words
                or duration >= max_line_duration
            ):
                should_split = True

            if should_split:
                flush_words()

            current_words.append(w)

    flush_words()

    # Post-process cues: resolve any overlap, apply time offset
    final_cues = []
    for cue in raw_cues:
        start = max(0.0, cue["start"] + time_offset)
        end = max(start + 0.2, cue["end"] + time_offset)

        if final_cues:
            prev_end = final_cues[-1]["end"]
            if start < prev_end:
                final_cues[-1]["end"] = max(final_cues[-1]["start"] + 0.3, start)

        final_cues.append({
            "start": start,
            "end": end,
            "text": cue["text"],
        })

    return final_cues


def main():
    parser = argparse.ArgumentParser(
        description="Generate an exact timestamped .srt transcript from narration audio using Whisper word timestamps"
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
        default="en",
        help="Force a language code (e.g. 'en'). Default: en."
    )
    parser.add_argument(
        "--max-line-chars",
        type=int,
        default=42,
        help="Maximum characters per subtitle line (default: 42)"
    )
    parser.add_argument(
        "--max-line-words",
        type=int,
        default=8,
        help="Maximum words per subtitle line (default: 8)"
    )
    parser.add_argument(
        "--max-line-duration",
        type=float,
        default=3.5,
        help="Maximum duration in seconds for a single subtitle line (default: 3.5)"
    )
    parser.add_argument(
        "--pause-threshold",
        type=float,
        default=0.45,
        help="Pause gap in seconds between words to split subtitle lines (default: 0.45)"
    )
    parser.add_argument(
        "--time-offset",
        type=float,
        default=0.0,
        help="Time offset in seconds to adjust subtitle timing (positive: delay, negative: advance)"
    )

    args = parser.parse_args()

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("ERROR: faster-whisper is not installed.")
        print("Install it with: pip install faster-whisper")
        exit(1)

    if not os.path.exists(args.audio):
        print(f"ERROR: audio file not found: {args.audio}")
        exit(1)

    print(f"Loading Whisper model '{args.model}'...")
    model = WhisperModel(args.model, device="auto", compute_type="auto")

    print(f"Transcribing {args.audio} with word-level timestamps...")
    segments_gen, info = model.transcribe(
        args.audio,
        language=args.language,
        vad_filter=True,
        word_timestamps=True,
    )

    print(f"Detected language: {info.language} (probability {info.language_probability:.2f})")

    cues = build_cues_from_segments(
        segments_gen,
        max_line_chars=args.max_line_chars,
        max_line_words=args.max_line_words,
        max_line_duration=args.max_line_duration,
        pause_threshold=args.pause_threshold,
        time_offset=args.time_offset,
    )

    for cue in cues[:10]:
        print(f"  [{format_timestamp(cue['start'])} --> {format_timestamp(cue['end'])}] {cue['text']}")

    if len(cues) > 10:
        print(f"  ... ({len(cues) - 10} more caption lines) ...")

    if not cues:
        print("WARNING: no speech detected — transcript will be empty.")

    write_srt(cues, args.output)
    print(f"\nDone. Transcript saved to {args.output} ({len(cues)} caption lines)")


if __name__ == "__main__":
    main()