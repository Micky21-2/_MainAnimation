"""
compose_lecture.py
==================

Compose:

    talking-head video
        +
    slide/demo timeline
        +
    full-screen transition anchors
        +
    crossfades
        +
    subtitles

Supported timeline types:

    slide
    slide_full
    character
    demo
    transition

All timeline entries MUST use:

    start
    duration

Transition format:

    {
        "type": "transition",
        "start": ...,
        "duration": ...,
        "from": {...},
        "to": {...}
    }

The original talking-head audio is attached at the end.
"""

import os
import json
import shutil
import argparse
import subprocess


# ============================================================
# COMMAND RUNNER
# ============================================================

def run(cmd):

    print(
        " ".join(str(x) for x in cmd)
    )

    subprocess.run(
        cmd,
        check=True
    )


# ============================================================
# VIDEO DURATION
# ============================================================

def get_video_duration(path):

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    info = json.loads(
        result.stdout
    )

    return float(
        info["format"]["duration"]
    )


# ============================================================
# TIMELINE LOADER
# ============================================================

def load_composite_timeline(
    path,
    total_duration
):

    print(
        f"Loading timeline JSON: {path}"
    )

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        entries = json.load(f)

    if not entries:

        raise ValueError(
            "Timeline is empty."
        )

    print(
        f"  Raw timeline entries: "
        f"{len(entries)}"
    )

    normalized = []

    for i, entry in enumerate(entries):

        e = dict(entry)

        # ----------------------------------------------------
        # Only the standard format is accepted.
        # ----------------------------------------------------

        if "start" not in e:

            # Give a useful error instead of the old
            # KeyError: 'start'.

            raise ValueError(
                f"Timeline entry {i} has no "
                f"'start'. Entry: {e}"
            )

        if "duration" not in e:

            raise ValueError(
                f"Timeline entry {i} has no "
                f"'duration'. Entry: {e}"
            )

        if "type" not in e:

            raise ValueError(
                f"Timeline entry {i} has no "
                f"'type'. Entry: {e}"
            )

        e["start"] = float(
            e["start"]
        )

        e["duration"] = float(
            e["duration"]
        )

        if e["duration"] <= 0:

            raise ValueError(
                f"Timeline entry {i} has "
                f"non-positive duration: {e}"
            )

        # ----------------------------------------------------
        # Check timeline entry types.
        # ----------------------------------------------------

        etype = e["type"]

        if etype == "slide":

            if not e.get("image"):

                raise ValueError(
                    f"Slide entry {i} has no image."
                )

            if not os.path.exists(
                e["image"]
            ):

                raise FileNotFoundError(
                    f"Slide image not found: "
                    f"{e['image']}"
                )

        elif etype == "slide_full":

            if not e.get("image"):

                raise ValueError(
                    f"Full-screen slide entry "
                    f"{i} has no image."
                )

            if not os.path.exists(
                e["image"]
            ):

                raise FileNotFoundError(
                    f"Full-screen slide image "
                    f"not found: {e['image']}"
                )

        elif etype == "character":

            pass

        elif etype == "demo":

            if not e.get("video"):

                raise ValueError(
                    f"Demo entry {i} has no video."
                )

            if not os.path.exists(
                e["video"]
            ):

                raise FileNotFoundError(
                    f"Demo video not found: "
                    f"{e['video']}"
                )

        elif etype == "transition":

            from_desc = e.get("from")

            to_desc = e.get("to")

            if not isinstance(
                from_desc,
                dict
            ):

                raise ValueError(
                    f"Transition entry {i} "
                    f"has invalid 'from': {from_desc}"
                )

            if not isinstance(
                to_desc,
                dict
            ):

                raise ValueError(
                    f"Transition entry {i} "
                    f"has invalid 'to': {to_desc}"
                )

            validate_transition_endpoint(
                from_desc,
                i,
                "from"
            )

            validate_transition_endpoint(
                to_desc,
                i,
                "to"
            )

        else:

            raise ValueError(
                f"Unknown timeline type "
                f"'{etype}' at entry {i}"
            )

        # ----------------------------------------------------
        # Duration bounds
        # ----------------------------------------------------

        if e["start"] < -0.001:

            raise ValueError(
                f"Timeline entry {i} starts "
                f"before zero: {e}"
            )

        if (
            e["start"] + e["duration"]
            > total_duration + 1.0
        ):

            raise ValueError(
                f"Timeline entry {i} extends "
                f"past video duration.\n"
                f"Entry: {e}\n"
                f"Video duration: "
                f"{total_duration:.3f}s"
            )

        normalized.append(e)

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    normalized.sort(
        key=lambda e: e["start"]
    )

    print(
        f"  Normalized timeline entries: "
        f"{len(normalized)}"
    )

    return normalized


# ============================================================
# TRANSITION VALIDATION
# ============================================================

def validate_transition_endpoint(
    desc,
    index,
    label
):

    etype = desc.get("type")

    if not etype:

        raise ValueError(
            f"Transition entry {index} "
            f"has no type for '{label}'."
        )

    if etype == "slide":

        if not desc.get("image"):

            raise ValueError(
                f"Transition entry {index} "
                f"'{label}' slide has no image."
            )

        if not os.path.exists(
            desc["image"]
        ):

            raise FileNotFoundError(
                f"Transition entry {index} "
                f"'{label}' slide image not found: "
                f"{desc['image']}"
            )

    elif etype == "slide_full":

        if not desc.get("image"):

            raise ValueError(
                f"Transition entry {index} "
                f"'{label}' slide_full has no image."
            )

        if not os.path.exists(
            desc["image"]
        ):

            raise FileNotFoundError(
                f"Transition entry {index} "
                f"'{label}' slide_full image "
                f"not found: {desc['image']}"
            )

    elif etype == "character":

        pass

    else:

        raise ValueError(
            f"Transition entry {index} "
            f"'{label}' has unsupported type: "
            f"{etype}"
        )


# ============================================================
# PATH ESCAPING
# ============================================================

def escape_path(path):

    path = os.path.abspath(path)

    return (
        path
        .replace("\\", "/")
        .replace(":", "\\:")
        .replace("'", "\\'")
    )


# ============================================================
# COVER FILTER
# ============================================================

def cover_filter(
    width,
    height,
    fps,
    input_label,
    output_label
):

    return (
        f"[{input_label}]"
        f"scale={width}:{height}:"
        f"force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"setsar=1,"
        f"setpts=PTS-STARTPTS,"
        f"fps={fps}"
        f"[{output_label}];"
    )


# ============================================================
# CHARACTER FIT
# ============================================================

def character_fit_filter(
    width,
    height,
    fps,
    input_label,
    output_label,
    character_scale=0.78
):
    """
    Fit the complete talking-head frame into the canvas.

    Unlike cover(), this NEVER crops the character.
    """

    safe_width = int(
        width * character_scale
    )

    safe_height = int(
        height * character_scale
    )

    safe_width -= (
        safe_width % 2
    )

    safe_height -= (
        safe_height % 2
    )

    safe_width = max(
        safe_width,
        2
    )

    safe_height = max(
        safe_height,
        2
    )

    return (
        f"[{input_label}]"
        f"scale={safe_width}:{safe_height}:"
        f"force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:"
        f"(ow-iw)/2:"
        f"(oh-ih)/2:"
        f"color=black,"
        f"setsar=1,"
        f"setpts=PTS-STARTPTS,"
        f"fps={fps}"
        f"[{output_label}];"
    )


# ============================================================
# RENDER BASIC LAYOUT
# ============================================================

def render_layout_clip(
    kind,
    start,
    duration,
    talking_head_path,
    out_path,
    width,
    height,
    fps,
    th_width,
    slide_width,
    image=None,
    side="left"
):

    # ========================================================
    # FULL-SCREEN CHARACTER
    # ========================================================

    if kind == "character":

        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",

            "-ss",
            str(start),

            "-t",
            str(duration),

            "-i",
            talking_head_path,
        ]

        filt = character_fit_filter(
            width,
            height,
            fps,
            "0:v",
            "out",
            character_scale=0.78
        )

        cmd += [
            "-filter_complex",
            filt,

            "-map",
            "[out]",

            "-an",

            "-c:v",
            "libx264",

            "-pix_fmt",
            "yuv420p",

            "-r",
            str(fps),

            out_path,
        ]

        run(cmd)

        return out_path

    # ========================================================
    # FULL-SCREEN SLIDE
    # ========================================================

    if kind == "slide_full":

        if not image:

            raise ValueError(
                "slide_full requires an image."
            )

        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",

            "-loop",
            "1",

            "-t",
            str(duration),

            "-i",
            image,
        ]

        filt = cover_filter(
            width,
            height,
            fps,
            "0:v",
            "out"
        )

        cmd += [
            "-filter_complex",
            filt,

            "-map",
            "[out]",

            "-an",

            "-c:v",
            "libx264",

            "-pix_fmt",
            "yuv420p",

            "-r",
            str(fps),

            out_path,
        ]

        run(cmd)

        return out_path

    # ========================================================
    # NORMAL SPLIT SCREEN
    # ========================================================

    if kind == "slide":

        if not image:

            raise ValueError(
                "slide requires an image."
            )

        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",

            # Talking head
            "-ss",
            str(start),

            "-t",
            str(duration),

            "-i",
            talking_head_path,

            # Slide
            "-loop",
            "1",

            "-t",
            str(duration),

            "-i",
            image,
        ]

        filt = ""

        filt += cover_filter(
            th_width,
            height,
            fps,
            "0:v",
            "th"
        )

        filt += cover_filter(
            slide_width,
            height,
            fps,
            "1:v",
            "sl"
        )

        if side == "right":

            filt += (
                "[sl][th]"
                "hstack=inputs=2,"
                "setpts=PTS-STARTPTS"
                "[out]"
            )

        else:

            filt += (
                "[th][sl]"
                "hstack=inputs=2,"
                "setpts=PTS-STARTPTS"
                "[out]"
            )

        cmd += [
            "-filter_complex",
            filt,

            "-map",
            "[out]",

            "-an",

            "-c:v",
            "libx264",

            "-pix_fmt",
            "yuv420p",

            "-r",
            str(fps),

            out_path,
        ]

        run(cmd)

        return out_path

    raise ValueError(
        f"Unsupported layout kind: {kind}"
    )


# ============================================================
# RENDER TIMELINE ENTRY
# ============================================================

def render_segment(
    entry,
    index,
    talking_head_path,
    work_dir,
    width,
    height,
    fps,
    th_width,
    slide_width
):

    out_path = os.path.join(
        work_dir,
        f"seg_{index:05d}.mp4"
    )

    etype = entry["type"]

    start = float(
        entry["start"]
    )

    duration = float(
        entry["duration"]
    )

    # ========================================================
    # NORMAL SLIDE
    # ========================================================

    if etype == "slide":

        return render_layout_clip(
            "slide",
            start,
            duration,
            talking_head_path,
            out_path,
            width,
            height,
            fps,
            th_width,
            slide_width,
            image=entry["image"],
            side=entry.get(
                "side",
                "left"
            )
        )

    # ========================================================
    # FULL-SCREEN SLIDE
    # ========================================================

    if etype == "slide_full":

        return render_layout_clip(
            "slide_full",
            start,
            duration,
            talking_head_path,
            out_path,
            width,
            height,
            fps,
            th_width,
            slide_width,
            image=entry["image"]
        )

    # ========================================================
    # FULL-SCREEN CHARACTER
    # ========================================================

    if etype == "character":

        return render_layout_clip(
            "character",
            start,
            duration,
            talking_head_path,
            out_path,
            width,
            height,
            fps,
            th_width,
            slide_width
        )

    # ========================================================
    # DEMO
    # ========================================================

    if etype == "demo":

        offset = float(
            entry.get(
                "offset",
                0.0
            )
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",

            "-ss",
            str(offset),

            "-t",
            str(duration),

            "-i",
            entry["video"],
        ]

        filt = cover_filter(
            width,
            height,
            fps,
            "0:v",
            "out"
        )

        cmd += [
            "-filter_complex",
            filt,

            "-map",
            "[out]",

            "-an",

            "-c:v",
            "libx264",

            "-pix_fmt",
            "yuv420p",

            "-r",
            str(fps),

            out_path,
        ]

        run(cmd)

        return out_path

    # ========================================================
    # CROSSFADE
    # ========================================================

    if etype == "transition":

        from_desc = entry["from"]

        to_desc = entry["to"]

        tmp_a = (
            out_path
            + ".from.mp4"
        )

        tmp_b = (
            out_path
            + ".to.mp4"
        )

        # ----------------------------------------------------
        # OLD LAYOUT
        # ----------------------------------------------------

        render_layout_clip(
            from_desc["type"],
            start,
            duration,
            talking_head_path,
            tmp_a,
            width,
            height,
            fps,
            th_width,
            slide_width,
            image=from_desc.get(
                "image"
            ),
            side=from_desc.get(
                "side",
                "left"
            )
        )

        # ----------------------------------------------------
        # NEW LAYOUT
        # ----------------------------------------------------

        render_layout_clip(
            to_desc["type"],
            start,
            duration,
            talking_head_path,
            tmp_b,
            width,
            height,
            fps,
            th_width,
            slide_width,
            image=to_desc.get(
                "image"
            ),
            side=to_desc.get(
                "side",
                "left"
            )
        )

        # ----------------------------------------------------
        # CROSSFADE
        # ----------------------------------------------------

        xfade_duration = max(
            duration - (
                1.0 / fps
            ),
            1.0 / fps
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",

            "-i",
            tmp_a,

            "-i",
            tmp_b,

            "-filter_complex",

            (
                "[0:v][1:v]"
                "xfade="
                "transition=fade:"
                f"duration={xfade_duration:.3f}:"
                "offset=0,"
                "format=yuv420p"
                "[out]"
            ),

            "-map",
            "[out]",

            "-an",

            "-c:v",
            "libx264",

            "-pix_fmt",
            "yuv420p",

            "-r",
            str(fps),

            out_path,
        ]

        run(cmd)

        if os.path.exists(tmp_a):
            os.remove(tmp_a)

        if os.path.exists(tmp_b):
            os.remove(tmp_b)

        return out_path

    raise ValueError(
        f"Unknown timeline entry type: "
        f"{etype}"
    )


# ============================================================
# CONCAT
# ============================================================

def concat_segments(
    segment_paths,
    output_path,
    fps
):

    list_path = (
        output_path
        + ".concat.txt"
    )

    with open(
        list_path,
        "w",
        encoding="utf-8"
    ) as f:

        for path in segment_paths:

            abs_path = os.path.abspath(
                path
            )

            safe_path = (
                abs_path
                .replace("'", "'\\''")
            )

            f.write(
                f"file '{safe_path}'\n"
            )

    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",

        "-f",
        "concat",

        "-safe",
        "0",

        "-i",
        list_path,

        "-c:v",
        "libx264",

        "-pix_fmt",
        "yuv420p",

        "-r",
        str(fps),

        output_path,
    ]

    run(cmd)

    os.remove(
        list_path
    )


# ============================================================
# AUDIO + SUBTITLES
# ============================================================

def attach_audio_and_subtitles(
    video_only_path,
    talking_head_path,
    output_path,
    subtitles_path=None,
    subtitle_font_size=10,
    subtitle_margin_v=None,
    full_height=1080,
    subtitle_bar_height=0,
    subtitle_bar_color="black"
):

    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",

        "-i",
        video_only_path,

        "-i",
        talking_head_path,
    ]

    filters = []

    # --------------------------------------------------------
    # Subtitle bar
    # --------------------------------------------------------

    if (
        subtitles_path
        and subtitle_bar_height > 0
    ):

        filters.append(
            f"pad=iw:{full_height}:"
            f"0:0:"
            f"color={subtitle_bar_color}"
        )

    # --------------------------------------------------------
    # Subtitles
    # --------------------------------------------------------

    if subtitles_path:

        subtitle_path = escape_path(
            subtitles_path
        )

        if subtitle_margin_v is not None:

            margin_v = (
                subtitle_margin_v
            )

        else:

            margin_v = max(
                int(
                    subtitle_bar_height
                    / 2
                ),
                4
            )

        style = (
            "FontName=Roboto,"
            f"FontSize={subtitle_font_size},"
            "PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "BorderStyle=3,"
            "Outline=1,"
            "Shadow=0,"
            "BackColour=&H80404040,"
            "Alignment=2,"
            f"MarginV={margin_v}"
        )

        filters.append(
            "subtitles="
            f"filename='{subtitle_path}':"
            f"force_style='{style}'"
        )

    # --------------------------------------------------------
    # Video
    # --------------------------------------------------------

    cmd += [
        "-map",
        "0:v"
    ]

    if filters:

        cmd += [
            "-vf",
            ",".join(filters),

            "-c:v",
            "libx264",

            "-pix_fmt",
            "yuv420p"
        ]

    else:

        cmd += [
            "-c:v",
            "copy"
        ]

    # --------------------------------------------------------
    # ORIGINAL AUDIO
    # --------------------------------------------------------

    cmd += [
        "-map",
        "1:a?",

        "-c:a",
        "aac",

        "-shortest",

        output_path
    ]

    run(cmd)


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Compose talking-head video "
            "with slides, demos and "
            "full-screen transitions."
        )
    )

    parser.add_argument(
        "--talking-head",
        required=True
    )

    parser.add_argument(
        "--timeline",
        required=True
    )

    parser.add_argument(
        "--output",
        required=True
    )

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
        "--fps",
        type=int,
        default=24
    )

    parser.add_argument(
        "--talking-head-ratio",
        type=float,
        default=0.28
    )

    parser.add_argument(
        "--subtitles",
        default=None
    )

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

    parser.add_argument(
        "--subtitle-bar-color",
        default="black"
    )

    parser.add_argument(
        "--keep-temp",
        action="store_true"
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    if not os.path.exists(
        args.talking_head
    ):

        raise FileNotFoundError(
            args.talking_head
        )

    if not os.path.exists(
        args.timeline
    ):

        raise FileNotFoundError(
            args.timeline
        )

    if (
        args.subtitles
        and not os.path.exists(
            args.subtitles
        )
    ):

        raise FileNotFoundError(
            args.subtitles
        )

    # --------------------------------------------------------
    # Duration
    # --------------------------------------------------------

    print(
        "Reading talking-head video duration..."
    )

    total_duration = get_video_duration(
        args.talking_head
    )

    print(
        f"  Duration: "
        f"{total_duration:.3f}s"
    )

    # --------------------------------------------------------
    # Timeline
    # --------------------------------------------------------

    timeline = load_composite_timeline(
        args.timeline,
        total_duration
    )

    # --------------------------------------------------------
    # Print timeline
    # --------------------------------------------------------

    print()

    for i, e in enumerate(
        timeline
    ):

        etype = e["type"]

        start = e["start"]

        end = (
            start
            + e["duration"]
        )

        if etype == "slide":

            description = (
                f"{e['image']} "
                f"(side={e.get('side', 'left')})"
            )

        elif etype == "slide_full":

            description = (
                f"{e['image']} "
                "(FULL SCREEN SLIDE)"
            )

        elif etype == "character":

            description = (
                "FULL SCREEN CHARACTER"
            )

        elif etype == "demo":

            description = (
                f"{e['video']} "
                "(DEMO)"
            )

        elif etype == "transition":

            description = (
                f"{e['from']['type']} "
                "-> "
                f"{e['to']['type']} "
                "(CROSSFADE)"
            )

        else:

            description = ""

        print(
            f"{i + 1:3d}. "
            f"[{etype.upper():10s}] "
            f"{start:8.2f}s -> "
            f"{end:8.2f}s "
            f"({e['duration']:6.2f}s) "
            f"{description}"
        )

    # --------------------------------------------------------
    # Subtitle area
    # --------------------------------------------------------

    subtitle_bar_height = 0

    content_height = (
        args.height
    )

    if args.subtitles:

        subtitle_bar_height = (
            args.subtitle_bar_height
            if args.subtitle_bar_height
            is not None
            else max(
                int(
                    args.height * 0.09
                ),
                60
            )
        )

        content_height = (
            args.height
            - subtitle_bar_height
        )

    # --------------------------------------------------------
    # Even dimensions
    # --------------------------------------------------------

    width = (
        args.width
        - args.width % 2
    )

    content_height = (
        content_height
        - content_height % 2
    )

    # --------------------------------------------------------
    # Talking-head width
    # --------------------------------------------------------

    th_width = int(
        width
        * args.talking_head_ratio
    )

    th_width -= (
        th_width % 2
    )

    slide_width = (
        width
        - th_width
    )

    # --------------------------------------------------------
    # Temporary directory
    # --------------------------------------------------------

    work_dir = (
        args.output
        + ".segments"
    )

    os.makedirs(
        work_dir,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Render
    # --------------------------------------------------------

    print()

    print(
        f"Rendering {len(timeline)} "
        f"timeline entries..."
    )

    segment_paths = []

    for i, entry in enumerate(
        timeline
    ):

        print(
            f"  Rendering "
            f"{i + 1}/{len(timeline)} "
            f"({entry['type']})..."
        )

        path = render_segment(
            entry,
            i,
            args.talking_head,
            work_dir,
            width,
            content_height,
            args.fps,
            th_width,
            slide_width
        )

        segment_paths.append(
            path
        )

    # --------------------------------------------------------
    # Concatenate
    # --------------------------------------------------------

    concatenated = os.path.join(
        work_dir,
        "_concatenated.mp4"
    )

    print()
    print(
        "Concatenating segments..."
    )

    concat_segments(
        segment_paths,
        concatenated,
        args.fps
    )

    # --------------------------------------------------------
    # Attach audio
    # --------------------------------------------------------

    print(
        "Attaching original audio..."
    )

    attach_audio_and_subtitles(
        concatenated,
        args.talking_head,
        args.output,

        subtitles_path=args.subtitles,

        subtitle_font_size=(
            args.subtitle_font_size
        ),

        subtitle_margin_v=(
            args.subtitle_margin
        ),

        full_height=args.height,

        subtitle_bar_height=(
            subtitle_bar_height
        ),

        subtitle_bar_color=(
            args.subtitle_bar_color
        )
    )

    # --------------------------------------------------------
    # Cleanup
    # --------------------------------------------------------

    if not args.keep_temp:

        shutil.rmtree(
            work_dir,
            ignore_errors=True
        )

    print()
    print(
        "=" * 60
    )

    print(
        "COMPOSITION COMPLETE"
    )

    print(
        f"Output: {args.output}"
    )

    print(
        "=" * 60
    )


if __name__ == "__main__":
    main()