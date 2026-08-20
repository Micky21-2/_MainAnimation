"""
compose_lecture.py
==================

Combines a talking-head video with a timeline containing:

    slide
    slide_full
    character
    transition
    demo

The timeline is produced by build_slide_timeline.py and vary_layout.py.

Important behavior
------------------

Normal slide:
    [ talking head | slide ]
    or
    [ slide | talking head ]

Full-screen character:
    Entire talking-head frame is fitted inside the canvas.
    NO crop is performed.

Full-screen slide:
    Slide fills the entire canvas using cover/crop.

Transition:
    Two complete layouts are rendered over the same time interval and
    crossfaded using FFmpeg xfade.

Audio:
    Video segments are rendered WITHOUT audio.
    The original continuous talking-head audio is attached at the end.

Subtitles:
    A dedicated bottom subtitle bar is reserved when subtitles are enabled.
"""

import os
import json
import shutil
import argparse
import subprocess


# =========================================================================
# BASIC COMMAND RUNNER
# =========================================================================

def run(cmd):
    print(" ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)


# =========================================================================
# VIDEO DURATION
# =========================================================================

def get_video_duration(path):
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        path,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
    )

    info = json.loads(result.stdout)

    return float(info["format"]["duration"])


# =========================================================================
# TIMELINE LOADING
# =========================================================================

def load_composite_timeline(path, total_duration):

    with open(path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    if not entries:
        raise ValueError("Timeline is empty.")

    print(f"  Raw timeline entries: {len(entries)}")

    # ---------------------------------------------------------------------
    # Legacy timeline
    # ---------------------------------------------------------------------

    if "type" not in entries[0]:

        entries = sorted(
            entries,
            key=lambda e: float(e["start"]),
        )

        timeline = []

        for i, e in enumerate(entries):

            start = float(e["start"])

            if i + 1 < len(entries):
                end = float(entries[i + 1]["start"])
            else:
                end = total_duration

            timeline.append({
                "type": "slide",
                "image": e["image"],
                "start": start,
                "duration": max(end - start, 0.05),
                "side": e.get("side", "left"),
            })

        return timeline

    # ---------------------------------------------------------------------
    # New timeline
    # ---------------------------------------------------------------------

    timeline = []

    for index, raw in enumerate(entries):

        e = dict(raw)

        # -------------------------------------------------------------
        # Normalize start/duration.
        #
        # Some older versions used:
        #
        #     start_sec
        #     duration_sec
        #
        # The current vary_layout.py uses:
        #
        #     start
        #     duration
        #
        # Accept both so old timelines do not break.
        # -------------------------------------------------------------

        if "start" not in e:

            if "start_sec" in e:
                e["start"] = float(e["start_sec"])

            else:
                raise ValueError(
                    f"Timeline entry {index} has no 'start'. "
                    f"Entry: {e}"
                )

        if "duration" not in e:

            if "duration_sec" in e:
                e["duration"] = float(e["duration_sec"])

            elif "end_sec" in e:
                e["duration"] = (
                    float(e["end_sec"])
                    - float(e["start"])
                )

            else:
                raise ValueError(
                    f"Timeline entry {index} has no 'duration'. "
                    f"Entry: {e}"
                )

        e["start"] = float(e["start"])
        e["duration"] = float(e["duration"])

        if e["duration"] <= 0:
            raise ValueError(
                f"Timeline entry {index} has invalid duration: "
                f"{e['duration']}"
            )

        etype = e.get("type")

        if not etype:
            raise ValueError(
                f"Timeline entry {index} has no 'type'. "
                f"Entry: {e}"
            )

        # -------------------------------------------------------------
        # Normalize transition endpoint descriptions.
        #
        # Current vary_layout.py already creates:
        #
        #     {
        #       "type": "slide",
        #       "image": "...",
        #       "side": "left"
        #     }
        #
        # This also supports older layout strings.
        # -------------------------------------------------------------

        if etype == "transition":

            for key in ("from", "to"):

                if key not in e:
                    raise ValueError(
                        f"Transition entry {index} has no '{key}'."
                    )

                desc = e[key]

                if not isinstance(desc, dict):
                    raise ValueError(
                        f"Transition entry {index} '{key}' "
                        f"must be an object."
                    )

                if "type" not in desc:

                    layout = desc.get("layout")

                    if layout == "character_fullscreen":
                        desc["type"] = "character"

                    elif layout == "slide_fullscreen":
                        desc["type"] = "slide_full"

                    elif layout == "slide_left":
                        desc["type"] = "slide"
                        desc.setdefault("side", "left")

                    elif layout == "slide_right":
                        desc["type"] = "slide"
                        desc.setdefault("side", "right")

                    else:
                        raise ValueError(
                            f"Transition entry {index} has no type "
                            f"for '{key}'. Entry: {e}"
                        )

        # -------------------------------------------------------------
        # Validate files
        # -------------------------------------------------------------

        if etype in ("slide", "slide_full"):

            image = e.get("image")

            if not image:
                raise ValueError(
                    f"Timeline entry {index} ({etype}) "
                    f"has no image."
                )

            if not os.path.exists(image):
                raise FileNotFoundError(
                    f"Slide image not found: {image}"
                )

        elif etype == "demo":

            video = e.get("video")

            if not video:
                raise ValueError(
                    f"Timeline entry {index} (demo) "
                    f"has no video."
                )

            if not os.path.exists(video):
                raise FileNotFoundError(
                    f"Demo clip not found: {video}"
                )

        elif etype == "character":
            pass

        elif etype == "transition":

            for key in ("from", "to"):

                desc = e[key]

                dtype = desc["type"]

                if dtype == "slide":

                    image = desc.get("image")

                    if not image:
                        raise ValueError(
                            f"Transition entry {index} "
                            f"'{key}' slide has no image."
                        )

                    if not os.path.exists(image):
                        raise FileNotFoundError(
                            f"Transition slide image not found: "
                            f"{image}"
                        )

                elif dtype == "slide_full":

                    image = desc.get("image")

                    if not image:
                        raise ValueError(
                            f"Transition entry {index} "
                            f"'{key}' slide_full has no image."
                        )

                    if not os.path.exists(image):
                        raise FileNotFoundError(
                            f"Transition slide image not found: "
                            f"{image}"
                        )

                elif dtype == "character":
                    pass

                else:
                    raise ValueError(
                        f"Unknown transition endpoint type "
                        f"'{dtype}' in entry {index}."
                    )

        else:

            raise ValueError(
                f"Unknown timeline entry type '{etype}' "
                f"at entry {index}."
            )

        # -------------------------------------------------------------
        # Duration validation
        # -------------------------------------------------------------

        end = e["start"] + e["duration"]

        if e["start"] > total_duration + 0.1:

            raise ValueError(
                f"Timeline entry {index} starts at "
                f"{e['start']:.3f}s, after video duration "
                f"{total_duration:.3f}s."
            )

        if end > total_duration + 0.5:

            print(
                f"WARNING: timeline entry {index} ends at "
                f"{end:.3f}s, slightly after video duration "
                f"{total_duration:.3f}s."
            )

        timeline.append(e)

    timeline.sort(key=lambda e: e["start"])

    print(
        f"  Normalized timeline entries: "
        f"{len(timeline)}"
    )

    return timeline


# =========================================================================
# PATH ESCAPING
# =========================================================================

def escape_path(path):

    path = os.path.abspath(path)

    return (
        path
        .replace("\\", "/")
        .replace(":", "\\:")
        .replace("'", "\\'")
    )


# =========================================================================
# COVER SCALE
# =========================================================================

def cover_filter(
    width,
    height,
    fps,
    input_label,
    output_label,
):
    """
    Cover the complete rectangle.

    This intentionally crops the source.

    Used for:
        - split-screen talking head
        - split-screen slide
        - full-screen slide
        - demo
    """

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


# =========================================================================
# CHARACTER FIT
# =========================================================================

def character_fit_filter(
    width,
    height,
    fps,
    input_label,
    output_label,
    character_scale=0.78,
):
    """
    Fit the ENTIRE talking-head frame into the full-screen canvas.

    IMPORTANT:
        This filter NEVER crops the character.

    The source is first fitted into a smaller safe rectangle and then
    padded onto the full output canvas.

    character_scale:
        1.0 = maximum possible fit
        0.78 = safer visual size
        0.70 = smaller character

    This is intentionally different from cover_filter().
    """

    safe_width = max(
        int(width * character_scale),
        2,
    )

    safe_height = max(
        int(height * character_scale),
        2,
    )

    # Make dimensions encoder-friendly.
    safe_width -= safe_width % 2
    safe_height -= safe_height % 2

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


# =========================================================================
# RENDER COMPLETE LAYOUT
# =========================================================================

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
    side="left",
    character_scale=0.78,
):
    """
    Render one complete layout as a video-only clip.
    """

    # =====================================================================
    # FULL-SCREEN CHARACTER
    # =====================================================================

    if kind == "character":

        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel", "error",

            "-ss", str(start),
            "-t", str(duration),

            "-i", talking_head_path,
        ]

        filt = character_fit_filter(
            width=width,
            height=height,
            fps=fps,
            input_label="0:v",
            output_label="out",
            character_scale=character_scale,
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

            "-movflags",
            "+faststart",

            out_path,
        ]

        run(cmd)

        return out_path

    # =====================================================================
    # FULL-SCREEN SLIDE
    # =====================================================================

    if kind == "slide_full":

        if not image:
            raise ValueError(
                "slide_full layout requires an image."
            )

        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel", "error",

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
            "out",
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

            "-movflags",
            "+faststart",

            out_path,
        ]

        run(cmd)

        return out_path

    # =====================================================================
    # SPLIT-SCREEN SLIDE
    # =====================================================================

    if kind == "slide":

        if not image:
            raise ValueError(
                "slide layout requires an image."
            )

        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel", "error",

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

        filter_complex = (
            cover_filter(
                th_width,
                height,
                fps,
                "0:v",
                "th",
            )
            +
            cover_filter(
                slide_width,
                height,
                fps,
                "1:v",
                "slide",
            )
        )

        if side == "right":

            filter_complex += (
                "[slide][th]"
                "hstack=inputs=2,"
                "setpts=PTS-STARTPTS"
                "[out]"
            )

        else:

            filter_complex += (
                "[th][slide]"
                "hstack=inputs=2,"
                "setpts=PTS-STARTPTS"
                "[out]"
            )

        cmd += [
            "-filter_complex",
            filter_complex,

            "-map",
            "[out]",

            "-an",

            "-c:v",
            "libx264",

            "-pix_fmt",
            "yuv420p",

            "-r",
            str(fps),

            "-movflags",
            "+faststart",

            out_path,
        ]

        run(cmd)

        return out_path

    raise ValueError(
        f"Unsupported layout type: {kind}"
    )


# =========================================================================
# RENDER TIMELINE ENTRY
# =========================================================================

def render_segment(
    entry,
    index,
    talking_head_path,
    work_dir,
    width,
    height,
    fps,
    th_width,
    slide_width,
    character_scale,
):

    out_path = os.path.join(
        work_dir,
        f"seg_{index:05d}.mp4",
    )

    etype = entry["type"]

    # =====================================================================
    # NORMAL SLIDE
    # =====================================================================

    if etype == "slide":

        return render_layout_clip(
            kind="slide",
            start=entry["start"],
            duration=entry["duration"],
            talking_head_path=talking_head_path,
            out_path=out_path,
            width=width,
            height=height,
            fps=fps,
            th_width=th_width,
            slide_width=slide_width,
            image=entry["image"],
            side=entry.get("side", "left"),
            character_scale=character_scale,
        )

    # =====================================================================
    # FULL-SCREEN SLIDE
    # =====================================================================

    if etype == "slide_full":

        return render_layout_clip(
            kind="slide_full",
            start=entry["start"],
            duration=entry["duration"],
            talking_head_path=talking_head_path,
            out_path=out_path,
            width=width,
            height=height,
            fps=fps,
            th_width=th_width,
            slide_width=slide_width,
            image=entry["image"],
            character_scale=character_scale,
        )

    # =====================================================================
    # FULL-SCREEN CHARACTER
    # =====================================================================

    if etype == "character":

        return render_layout_clip(
            kind="character",
            start=entry["start"],
            duration=entry["duration"],
            talking_head_path=talking_head_path,
            out_path=out_path,
            width=width,
            height=height,
            fps=fps,
            th_width=th_width,
            slide_width=slide_width,
            character_scale=character_scale,
        )

    # =====================================================================
    # CROSSFADE TRANSITION
    # =====================================================================

    if etype == "transition":

        from_desc = entry["from"]
        to_desc = entry["to"]

        transition_start = entry["start"]
        transition_duration = entry["duration"]

        temp_a = (
            out_path +
            ".from.mp4"
        )

        temp_b = (
            out_path +
            ".to.mp4"
        )

        # -------------------------------------------------------------
        # FROM layout
        # -------------------------------------------------------------

        render_layout_clip(
            kind=from_desc["type"],
            start=transition_start,
            duration=transition_duration,
            talking_head_path=talking_head_path,
            out_path=temp_a,
            width=width,
            height=height,
            fps=fps,
            th_width=th_width,
            slide_width=slide_width,
            image=from_desc.get("image"),
            side=from_desc.get("side", "left"),
            character_scale=character_scale,
        )

        # -------------------------------------------------------------
        # TO layout
        # -------------------------------------------------------------

        render_layout_clip(
            kind=to_desc["type"],
            start=transition_start,
            duration=transition_duration,
            talking_head_path=talking_head_path,
            out_path=temp_b,
            width=width,
            height=height,
            fps=fps,
            th_width=th_width,
            slide_width=slide_width,
            image=to_desc.get("image"),
            side=to_desc.get("side", "left"),
            character_scale=character_scale,
        )

        # -------------------------------------------------------------
        # Crossfade
        # -------------------------------------------------------------

        fade_duration = max(
            transition_duration - (1.0 / fps),
            1.0 / fps,
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel", "error",

            "-i",
            temp_a,

            "-i",
            temp_b,

            "-filter_complex",
            (
                f"[0:v][1:v]"
                f"xfade="
                f"transition=fade:"
                f"duration={fade_duration:.3f}:"
                f"offset=0,"
                f"format=yuv420p"
                f"[out]"
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

            "-movflags",
            "+faststart",

            out_path,
        ]

        run(cmd)

        if os.path.exists(temp_a):
            os.remove(temp_a)

        if os.path.exists(temp_b):
            os.remove(temp_b)

        return out_path

    # =====================================================================
    # DEMO
    # =====================================================================

    if etype == "demo":

        offset = float(
            entry.get(
                "offset",
                0.0,
            )
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel", "error",

            "-ss",
            str(offset),

            "-t",
            str(entry["duration"]),

            "-i",
            entry["video"],
        ]

        filt = cover_filter(
            width,
            height,
            fps,
            "0:v",
            "out",
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

            "-movflags",
            "+faststart",

            out_path,
        ]

        run(cmd)

        return out_path

    raise ValueError(
        f"Unknown timeline entry type: {etype}"
    )


# =========================================================================
# CONCATENATE VIDEO SEGMENTS
# =========================================================================

def concat_segments(
    segment_paths,
    output_path,
    fps,
):

    list_path = (
        output_path +
        ".concat.txt"
    )

    with open(
        list_path,
        "w",
        encoding="utf-8",
    ) as f:

        for path in segment_paths:

            absolute = os.path.abspath(path)

            # FFmpeg concat format.
            escaped = absolute.replace(
                "'",
                "'\\''"
            )

            f.write(
                f"file '{escaped}'\n"
            )

    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel", "error",

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

        "-movflags",
        "+faststart",

        output_path,
    ]

    run(cmd)

    os.remove(list_path)


# =========================================================================
# AUDIO + SUBTITLES
# =========================================================================

def attach_audio_and_subtitles(
    video_only_path,
    talking_head_path,
    output_path,
    subtitles_path=None,
    subtitle_font_size=10,
    subtitle_margin_v=None,
    full_height=1080,
    subtitle_bar_height=0,
    subtitle_bar_color="black",
):

    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel", "error",

        "-i",
        video_only_path,

        "-i",
        talking_head_path,
    ]

    filters = []

    # =====================================================================
    # SUBTITLE BAR
    # =====================================================================

    if (
        subtitles_path
        and subtitle_bar_height > 0
    ):

        filters.append(
            f"pad="
            f"iw:{full_height}:"
            f"0:0:"
            f"color={subtitle_bar_color}"
        )

    # =====================================================================
    # SUBTITLES
    # =====================================================================

    if subtitles_path:

        subtitle_file = escape_path(
            subtitles_path
        )

        font_size = max(
            int(subtitle_font_size),
            1,
        )

        if subtitle_margin_v is not None:

            margin_v = int(
                subtitle_margin_v
            )

        elif subtitle_bar_height > 0:

            margin_v = max(
                int(
                    (
                        subtitle_bar_height
                        - font_size
                    ) / 2
                ),
                4,
            )

        else:

            margin_v = int(
                full_height * 0.05
            )

        style = (
            f"FontName=Roboto,"
            f"FontSize={font_size},"
            f"PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,"
            f"BorderStyle=3,"
            f"Outline=1,"
            f"Shadow=0,"
            f"BackColour=&H80404040,"
            f"Alignment=2,"
            f"MarginV={margin_v}"
        )

        filters.append(
            "subtitles="
            f"filename='{subtitle_file}':"
            f"force_style='{style}'"
        )

    # =====================================================================
    # VIDEO ENCODING
    # =====================================================================

    if filters:

        cmd += [
            "-vf",
            ",".join(filters),

            "-c:v",
            "libx264",

            "-pix_fmt",
            "yuv420p",

            "-r",
            "24",
        ]

    else:

        cmd += [
            "-c:v",
            "copy",
        ]

    # =====================================================================
    # AUDIO
    #
    # IMPORTANT:
    # Audio comes directly from the original talking-head video.
    # Nothing is cut/reassembled.
    # =====================================================================

    cmd += [
        "-map",
        "0:v",

        "-map",
        "1:a?",

        "-c:a",
        "aac",

        "-shortest",

        "-movflags",
        "+faststart",

        output_path,
    ]

    run(cmd)


# =========================================================================
# MAIN
# =========================================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Composite talking-head video, slides, demos, "
            "full-screen anchors and crossfade transitions."
        )
    )

    # ---------------------------------------------------------------------
    # INPUT
    # ---------------------------------------------------------------------

    parser.add_argument(
        "--talking-head",
        required=True,
    )

    parser.add_argument(
        "--timeline",
        default=None,
    )

    parser.add_argument(
        "--slides-timeline",
        default=None,
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    # ---------------------------------------------------------------------
    # OUTPUT
    # ---------------------------------------------------------------------

    parser.add_argument(
        "--width",
        type=int,
        default=1920,
    )

    parser.add_argument(
        "--height",
        type=int,
        default=1080,
    )

    parser.add_argument(
        "--fps",
        type=int,
        default=24,
    )

    parser.add_argument(
        "--talking-head-ratio",
        type=float,
        default=0.28,
    )

    # ---------------------------------------------------------------------
    # CHARACTER
    # ---------------------------------------------------------------------

    parser.add_argument(
        "--character-scale",
        type=float,
        default=0.78,
        help=(
            "Scale of full-screen character inside the canvas. "
            "0.78 prevents excessive enlargement/cropping. "
            "Default: 0.78."
        ),
    )

    # ---------------------------------------------------------------------
    # SUBTITLES
    # ---------------------------------------------------------------------

    parser.add_argument(
        "--subtitles",
        default=None,
    )

    parser.add_argument(
        "--subtitle-font-size",
        type=int,
        default=10,
    )

    parser.add_argument(
        "--subtitle-margin",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--subtitle-bar-height",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--subtitle-bar-color",
        default="black",
    )

    # ---------------------------------------------------------------------
    # DEBUG
    # ---------------------------------------------------------------------

    parser.add_argument(
        "--keep-temp",
        action="store_true",
    )

    args = parser.parse_args()

    # =====================================================================
    # CHECK TIMELINE
    # =====================================================================

    timeline_path = (
        args.timeline
        or args.slides_timeline
    )

    if not timeline_path:

        raise SystemExit(
            "ERROR: --timeline is required."
        )

    # =====================================================================
    # CHECK FILES
    # =====================================================================

    if not os.path.exists(
        args.talking_head
    ):

        raise SystemExit(
            f"ERROR: talking-head not found: "
            f"{args.talking_head}"
        )

    if not os.path.exists(
        timeline_path
    ):

        raise SystemExit(
            f"ERROR: timeline not found: "
            f"{timeline_path}"
        )

    if (
        args.subtitles
        and not os.path.exists(
            args.subtitles
        )
    ):

        raise SystemExit(
            f"ERROR: subtitles not found: "
            f"{args.subtitles}"
        )

    # =====================================================================
    # VALIDATE CHARACTER SCALE
    # =====================================================================

    if not (
        0.1
        <= args.character_scale
        <= 1.0
    ):

        raise SystemExit(
            "ERROR: --character-scale must be "
            "between 0.1 and 1.0."
        )

    # =====================================================================
    # OUTPUT DIRECTORY
    # =====================================================================

    output_parent = os.path.dirname(
        os.path.abspath(
            args.output
        )
    )

    os.makedirs(
        output_parent,
        exist_ok=True,
    )

    # =====================================================================
    # VIDEO DURATION
    # =====================================================================

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

    # =====================================================================
    # LOAD TIMELINE
    # =====================================================================

    print(
        f"Loading timeline JSON: "
        f"{timeline_path}"
    )

    timeline = load_composite_timeline(
        timeline_path,
        total_duration,
    )

    # =====================================================================
    # PRINT TIMELINE SUMMARY
    # =====================================================================

    print()

    counts = {}

    for e in timeline:

        etype = e["type"]

        counts[etype] = (
            counts.get(etype, 0)
            + 1
        )

    print(
        "Timeline summary:"
    )

    for key in sorted(counts):

        print(
            f"  {key:15s}: "
            f"{counts[key]}"
        )

    print()

    # =====================================================================
    # SUBTITLE BAR
    # =====================================================================

    subtitle_bar_height = 0

    content_height = args.height

    if args.subtitles:

        if (
            args.subtitle_bar_height
            is not None
        ):

            subtitle_bar_height = (
                args.subtitle_bar_height
            )

        else:

            subtitle_bar_height = max(
                int(args.height * 0.09),
                60,
            )

        content_height = (
            args.height
            - subtitle_bar_height
        )

    # =====================================================================
    # EVEN DIMENSIONS
    # =====================================================================

    if args.width % 2:

        args.width -= 1

    if content_height % 2:

        content_height -= 1

    # =====================================================================
    # TALKING HEAD / SLIDE WIDTHS
    # =====================================================================

    th_width = int(
        args.width
        * args.talking_head_ratio
    )

    th_width -= (
        th_width % 2
    )

    slide_width = (
        args.width
        - th_width
    )

    if slide_width % 2:

        slide_width -= 1

        th_width = (
            args.width
            - slide_width
        )

    print()
    print(
        f"Canvas: "
        f"{args.width}x{args.height}"
    )

    print(
        f"Content height: "
        f"{content_height}"
    )

    print(
        f"Talking-head width: "
        f"{th_width}"
    )

    print(
        f"Slide width: "
        f"{slide_width}"
    )

    print(
        f"Full-screen character scale: "
        f"{args.character_scale:.2f}"
    )

    # =====================================================================
    # TEMP DIRECTORY
    # =====================================================================

    work_dir = (
        args.output
        + ".segments"
    )

    if os.path.exists(work_dir):

        print(
            f"\nRemoving previous temporary "
            f"directory: {work_dir}"
        )

        shutil.rmtree(
            work_dir,
            ignore_errors=True,
        )

    os.makedirs(
        work_dir,
        exist_ok=True,
    )

    # =====================================================================
    # RENDER SEGMENTS
    # =====================================================================

    print()
    print(
        f"Rendering {len(timeline)} "
        f"timeline segments..."
    )

    segment_paths = []

    for index, entry in enumerate(
        timeline
    ):

        print(
            f"\n[{index + 1}/"
            f"{len(timeline)}] "
            f"{entry['type']} "
            f"start={entry['start']:.3f}s "
            f"duration={entry['duration']:.3f}s"
        )

        if entry["type"] == "slide":

            print(
                f"  side: "
                f"{entry.get('side', 'left')}"
            )

        elif entry["type"] == "transition":

            print(
                f"  transition: "
                f"{entry['from']['type']} "
                f"-> "
                f"{entry['to']['type']}"
            )

        segment_path = render_segment(
            entry=entry,
            index=index,
            talking_head_path=args.talking_head,
            work_dir=work_dir,
            width=args.width,
            height=content_height,
            fps=args.fps,
            th_width=th_width,
            slide_width=slide_width,
            character_scale=args.character_scale,
        )

        segment_paths.append(
            segment_path
        )

    # =====================================================================
    # CONCATENATE
    # =====================================================================

    concatenated_path = os.path.join(
        work_dir,
        "_concatenated.mp4",
    )

    print()
    print(
        "Concatenating video segments..."
    )

    concat_segments(
        segment_paths,
        concatenated_path,
        args.fps,
    )

    # =====================================================================
    # ATTACH AUDIO + SUBTITLES
    # =====================================================================

    print()
    print(
        "Attaching original continuous audio..."
    )

    attach_audio_and_subtitles(
        video_only_path=concatenated_path,

        talking_head_path=args.talking_head,

        output_path=args.output,

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
        ),
    )

    # =====================================================================
    # CLEANUP
    # =====================================================================

    if not args.keep_temp:

        print(
            "\nRemoving temporary files..."
        )

        shutil.rmtree(
            work_dir,
            ignore_errors=True,
        )

    # =====================================================================
    # COMPLETE
    # =====================================================================

    print()
    print("=" * 60)
    print("COMPOSITE COMPLETE")
    print("=" * 60)
    print(
        f"Output: {args.output}"
    )
    print(
        f"Character scale: "
        f"{args.character_scale:.2f}"
    )
    print("=" * 60)


# =========================================================================
# ENTRY POINT
# =========================================================================

if __name__ == "__main__":
    main()