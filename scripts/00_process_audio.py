"""
00_process_audio.py
====================
PHASE 0 of the pipeline. Runs BEFORE everything else, because every later
step (talking-head generation, transcript, slide detection, timeline
building, composition) assumes the narration audio and the reference video
share the same timeline.

What it does to the narration audio:
  1. Enhances it   -> highpass rumble filter, FFT denoise (afftdn), loudness
                       normalization (loudnorm).
  2. Removes long pauses -> detects silences longer than --min-pause-sec via
                       ffmpeg's silencedetect, then cuts them down to a short
                       --keep-pause-sec gap (or fully out if 0).

What it does to the reference video:
  - Cuts out EXACTLY the same time ranges that were removed from the audio,
    so every timestamp in the processed video still lines up with the
    processed audio, frame-accurate. This is what everything downstream
    (slide timeline, demo clip extraction, talking-head sync) relies on.

Both cuts come from a single "cutlist" computed once from the audio, so the
two outputs can never drift apart.

USAGE:
    python 00_process_audio.py \\
        --audio narration.wav \\
        --video reference.mp4 \\
        --output-dir work/run1/audio_process \\
        --processed-audio-out work/run1/audio_process/narration_clean.wav \\
        --processed-video-out work/run1/audio_process/reference_clean.mp4
"""

import os
import re
import json
import argparse
import subprocess
import tempfile


# ============================================================
# FFMPEG / FFPROBE HELPERS
# ============================================================

def run(cmd, capture=False):
    if capture:
        return subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    subprocess.run(cmd, check=True)


def get_duration(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        path,
    ]
    out = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, text=True).stdout
    return float(json.loads(out)["format"]["duration"])


# ============================================================
# STEP 1: ENHANCE + DENOISE AUDIO
# ============================================================

def enhance_audio(
    input_audio,
    output_audio,
    highpass_freq,
    denoise_strength,
    loudnorm_target,
    disable_denoise,
    disable_loudnorm,
):
    """Clean up the narration audio: remove low-frequency rumble, denoise
    background noise, and normalize loudness so levels are consistent."""

    filters = [f"highpass=f={highpass_freq}"]

    if not disable_denoise:
        # afftdn: FFT-based denoiser. nr = noise reduction amount in dB.
        filters.append(f"afftdn=nr={denoise_strength}:nf=-25")

    if not disable_loudnorm:
        # Single-pass loudnorm is good enough for narration cleanup; it's
        # not broadcast-exact but keeps levels consistent and free of clips.
        filters.append(f"loudnorm=I={loudnorm_target}:TP=-1.5:LRA=11")

    filter_chain = ",".join(filters)

    print(f"  Filters: {filter_chain}")

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", input_audio,
        "-af", filter_chain,
        "-ar", "48000",
        output_audio,
    ]
    run(cmd)


# ============================================================
# STEP 2: DETECT LONG PAUSES
# ============================================================

SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")
SILENCE_END_RE = re.compile(r"silence_end:\s*([0-9.]+)")


def detect_silences(audio_path, threshold_db, min_silence_sec):
    """Run ffmpeg silencedetect and parse silence_start/silence_end pairs."""

    cmd = [
        "ffmpeg", "-hide_banner", "-i", audio_path,
        "-af", f"silencedetect=noise={threshold_db}dB:d={min_silence_sec}",
        "-f", "null", "-",
    ]

    result = run(cmd, capture=True)
    log = result.stdout

    starts = [float(m) for m in SILENCE_START_RE.findall(log)]
    ends = [float(m) for m in SILENCE_END_RE.findall(log)]

    # ffmpeg may report a trailing silence_start with no matching
    # silence_end if the file ends in silence -> close it at duration.
    if len(starts) > len(ends):
        duration = get_duration(audio_path)
        ends.append(duration)

    silences = list(zip(starts, ends))
    return silences


# ============================================================
# STEP 3: BUILD KEEP-SEGMENT CUTLIST FROM PAUSES
# ============================================================

def build_keep_segments(duration, silences, keep_pause_sec, edge_pad_sec):
    """
    Turn a list of (silence_start, silence_end) pauses into a list of
    (start, end) segments to KEEP, where every pause has been shrunk down to
    `keep_pause_sec` seconds instead of being fully removed (a tiny gap
    sounds natural; a hard cut to zero can feel jarring / can clip words).

    edge_pad_sec: small buffer subtracted from the removed portion on both
    sides of each pause, so we never bite into the actual speech.
    """

    if not silences:
        return [(0.0, duration)]

    keep_segments = []
    cursor = 0.0

    for silence_start, silence_end in silences:
        pause_len = silence_end - silence_start
        if pause_len <= keep_pause_sec:
            # Nothing meaningful to trim, leave this pause untouched.
            continue

        # Shrink the pause: keep speech up to (silence_start + half the
        # kept gap), resume speech at (silence_end - half the kept gap).
        trim_from = min(silence_start + edge_pad_sec + keep_pause_sec / 2, silence_end)
        trim_to = max(silence_end - edge_pad_sec - keep_pause_sec / 2, trim_from)

        if trim_from <= cursor:
            # Overlaps a previous cut (can happen with back-to-back pauses).
            continue

        keep_segments.append((cursor, trim_from))
        cursor = trim_to

    if cursor < duration:
        keep_segments.append((cursor, duration))

    # Drop degenerate/zero-length segments.
    keep_segments = [(s, e) for s, e in keep_segments if e - s > 0.02]

    return keep_segments


# ============================================================
# STEP 4: CUT AUDIO AND VIDEO USING THE SAME KEEP-SEGMENT LIST
# ============================================================

def cut_media(input_path, keep_segments, output_path, is_video, fade_sec=0.02):
    """
    Cuts `input_path` down to exactly `keep_segments` and concatenates the
    pieces back together in one ffmpeg call (frame-accurate, single
    re-encode). Used identically for audio and video so both come out with
    the exact same resulting timeline.
    """

    n = len(keep_segments)
    filter_parts = []
    concat_inputs = []

    stream = "v" if is_video else "a"

    for i, (start, end) in enumerate(keep_segments):
        label_in = f"{stream}{i}"
        if is_video:
            filter_parts.append(
                f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[{label_in}]"
            )
        else:
            # Tiny fade in/out at each cut point avoids audible clicks.
            filter_parts.append(
                f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,"
                f"afade=t=in:st=0:d={fade_sec},"
                f"afade=t=out:st={max(end - start - fade_sec, 0):.4f}:d={fade_sec}[{label_in}]"
            )
        concat_inputs.append(f"[{label_in}]")

    concat_v = "1" if is_video else "0"
    concat_a = "0" if is_video else "1"

    filter_parts.append(
        f"{''.join(concat_inputs)}concat=n={n}:v={concat_v}:a={concat_a}[out]"
    )

    filter_complex = ";".join(filter_parts)

    map_stream = "[out]"

    # Write the filter graph to a temp file rather than passing it
    # directly on the command line. Videos with many kept segments
    # (i.e. many detected pauses) produce a very long filter string --
    # long enough to exceed Windows' ~32,767-character command-line
    # limit (surfaces as "WinError 206: filename or extension too
    # long"). Linux/macOS allow much longer command lines and never
    # hit this, which is why this only shows up on some machines/
    # videos and not others. Using -filter_complex_script sidesteps
    # the limit entirely, on every platform, with identical output.
    filter_script_fd, filter_script_path = tempfile.mkstemp(
        suffix=".txt",
        prefix="ffmpeg_filter_",
        text=True,
    )

    try:
        with os.fdopen(filter_script_fd, "w", encoding="utf-8") as f:
            f.write(filter_complex)

        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", input_path,
            "-filter_complex_script", filter_script_path,
            "-map", map_stream,
        ]

        if is_video:
            cmd += ["-an", "-c:v", "libx264", "-preset", "fast", "-crf", "18"]
        else:
            cmd += ["-c:a", "pcm_s16le", "-ar", "48000"]

        cmd.append(output_path)

        run(cmd)

    finally:
        try:
            os.remove(filter_script_path)
        except OSError:
            pass


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Phase 0: clean narration audio (denoise + remove long pauses) "
            "and cut the reference video to match, so both stay in sync."
        )
    )

    parser.add_argument("--audio", required=True, help="Path to raw narration audio")
    parser.add_argument("--video", required=True, help="Path to raw reference video")
    parser.add_argument("--output-dir", required=True, help="Working directory for intermediate files")

    parser.add_argument("--processed-audio-out", required=True)
    parser.add_argument("--processed-video-out", required=True)

    # --- pause detection / removal ---
    parser.add_argument(
        "--pause-threshold-db", type=float, default=-30.0,
        help="Volume (dB) below which audio is considered silence (default: -30)"
    )
    parser.add_argument(
        "--min-pause-sec", type=float, default=0.7,
        help="Only pauses at least this long are cut (default: 0.7s, keeps natural short breaths/pauses)"
    )
    parser.add_argument(
        "--keep-pause-sec", type=float, default=0.15,
        help="Shrink each long pause down to this length instead of deleting it entirely, "
             "for a natural-sounding cut (default: 0.15s, use 0 to remove pauses completely)"
    )
    parser.add_argument(
        "--edge-pad-sec", type=float, default=0.05,
        help="Safety buffer kept on each side of a cut so speech onsets/decays are never clipped (default: 0.05s)"
    )

    # --- audio enhancement ---
    parser.add_argument("--highpass-freq", type=float, default=80.0, help="Highpass cutoff to remove low rumble (default: 80Hz)")
    parser.add_argument("--denoise-strength", type=float, default=12.0, help="afftdn noise reduction in dB (default: 12)")
    parser.add_argument("--loudnorm-target", type=float, default=-16.0, help="Target integrated loudness LUFS (default: -16, good for speech)")
    parser.add_argument("--disable-denoise", action="store_true")
    parser.add_argument("--disable-loudnorm", action="store_true")
    parser.add_argument("--disable-pause-removal", action="store_true", help="Still enhances/denoises audio, but skips cutting pauses")

    parser.add_argument("--cutlist-out", default=None, help="Optional path to dump the computed cutlist as JSON")

    args = parser.parse_args()

    if not os.path.exists(args.audio):
        print(f"ERROR: audio not found: {args.audio}")
        exit(1)
    if not os.path.exists(args.video):
        print(f"ERROR: video not found: {args.video}")
        exit(1)

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.processed_audio_out)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.processed_video_out)), exist_ok=True)

    enhanced_audio = os.path.join(args.output_dir, "narration_enhanced.wav")

    # --------------------------------------------------------
    # 1. Enhance / denoise
    # --------------------------------------------------------
    print("\n[1/4] Enhancing + denoising narration audio...")
    enhance_audio(
        args.audio,
        enhanced_audio,
        args.highpass_freq,
        args.denoise_strength,
        args.loudnorm_target,
        args.disable_denoise,
        args.disable_loudnorm,
    )

    audio_duration = get_duration(enhanced_audio)
    video_duration = get_duration(args.video)

    print(f"  Narration duration: {audio_duration:.2f}s")
    print(f"  Reference video duration: {video_duration:.2f}s")

    if abs(audio_duration - video_duration) > 1.0:
        print(
            "  WARNING: narration and reference video durations differ by "
            f"{abs(audio_duration - video_duration):.2f}s. Pause cuts are computed "
            "from the audio timeline -- if these two aren't already aligned at t=0, "
            "the video cuts will be off."
        )

    # --------------------------------------------------------
    # 2. Detect long pauses
    # --------------------------------------------------------
    if args.disable_pause_removal:
        print("\n[2/4] Skipping pause detection (--disable-pause-removal).")
        silences = []
    else:
        print("\n[2/4] Detecting long pauses...")
        silences = detect_silences(enhanced_audio, args.pause_threshold_db, args.min_pause_sec)
        print(f"  Found {len(silences)} pause(s) >= {args.min_pause_sec}s")
        for s, e in silences:
            print(f"    pause: {s:.2f}s -> {e:.2f}s  ({e - s:.2f}s)")

    # --------------------------------------------------------
    # 3. Build shared cutlist
    # --------------------------------------------------------
    print("\n[3/4] Building shared cutlist for audio + video...")
    keep_segments = build_keep_segments(
        audio_duration, silences, args.keep_pause_sec, args.edge_pad_sec
    )

    kept_total = sum(e - s for s, e in keep_segments)
    removed_total = audio_duration - kept_total

    print(f"  Keeping {len(keep_segments)} segment(s)")
    print(f"  Original duration: {audio_duration:.2f}s")
    print(f"  New duration:      {kept_total:.2f}s")
    print(f"  Removed:           {removed_total:.2f}s")

    cutlist_report = {
        "source_audio": os.path.abspath(args.audio),
        "source_video": os.path.abspath(args.video),
        "original_duration_sec": audio_duration,
        "processed_duration_sec": kept_total,
        "removed_sec": removed_total,
        "pauses_detected": [{"start": s, "end": e} for s, e in silences],
        "keep_segments": [{"start": s, "end": e} for s, e in keep_segments],
    }

    cutlist_path = args.cutlist_out or os.path.join(args.output_dir, "cutlist.json")
    with open(cutlist_path, "w") as f:
        json.dump(cutlist_report, f, indent=2)
    print(f"  Wrote cutlist -> {cutlist_path}")

    # --------------------------------------------------------
    # 4. Apply the SAME cutlist to audio and video
    # --------------------------------------------------------
    print("\n[4/4] Cutting audio and video to the shared cutlist...")

    if len(keep_segments) == 1 and keep_segments[0] == (0.0, audio_duration):
        # No cuts needed -- just carry the enhanced audio through and copy
        # the video as-is (still re-encode video to keep output predictable).
        print("  No pauses removed. Audio: using enhanced version as-is.")
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", enhanced_audio, args.processed_audio_out])
        print("  Video: copying through unchanged.")
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", args.video, "-an", "-c:v", "copy", args.processed_video_out])
    else:
        print("  Cutting audio...")
        cut_media(enhanced_audio, keep_segments, args.processed_audio_out, is_video=False)

        # Video keep_segments are computed from the audio timeline; clamp
        # against the video's own duration so we never request a range past
        # the end of the (possibly shorter) source video.
        video_keep_segments = [
            (min(s, video_duration), min(e, video_duration))
            for s, e in keep_segments
        ]
        video_keep_segments = [(s, e) for s, e in video_keep_segments if e - s > 0.02]

        print("  Cutting video...")
        cut_media(args.video, video_keep_segments, args.processed_video_out, is_video=True)

    print("\nDone.")
    print(f"  Processed audio -> {args.processed_audio_out}")
    print(f"  Processed video -> {args.processed_video_out}")


if __name__ == "__main__":
    main()
