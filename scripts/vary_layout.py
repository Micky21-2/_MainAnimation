"""
vary_layout.py
==============

Adds controlled side changes to an existing lecture timeline.

Behavior
--------
- Character starts on the LEFT.
- After --side-flip-threshold seconds of cumulative SLIDE time,
  the character changes to the other side.
- Side changes alternate between:

      1st -> full-screen character
      2nd -> full-screen slide
      3rd -> full-screen character
      4th -> full-screen slide
      ...

- Full-screen character duration: 5 seconds by default.
- Full-screen slide duration: 10 seconds by default.
- Crossfade duration: 1.5 seconds by default.
- Each side change has:

      split-screen
          ↓ crossfade
      full-screen character/slide
          ↓ crossfade
      split-screen on new side

- Demo segments are copied unchanged.
- Demo time does NOT count toward the side-change threshold.

IMPORTANT
---------
Every output timeline entry uses:

    {
        "type": "...",
        "start": ...,
        "duration": ...
    }

Transition entries use:

    {
        "type": "transition",
        "start": ...,
        "duration": ...,
        "from": {...},
        "to": {...}
    }
"""

import argparse
import json


# ============================================================
# SIDE
# ============================================================

def flip_side(side):
    if side == "left":
        return "right"
    return "left"


# ============================================================
# ANCHOR
# ============================================================

def get_anchor_type(side_swap_count, transition_anchor):
    """
    Decide what appears full-screen during a side change.
    """

    if transition_anchor == "character":
        return "character"

    if transition_anchor == "slide":
        return "slide_full"

    # alternating
    if side_swap_count % 2 == 1:
        return "character"

    return "slide_full"


def build_anchor(anchor_type, image):
    """
    Build the timeline description for the full-screen anchor.
    """

    if anchor_type == "character":
        return {
            "type": "character"
        }

    return {
        "type": "slide_full",
        "image": image
    }


# ============================================================
# MAIN TIMELINE PROCESSING
# ============================================================

def vary_timeline(
    timeline,
    side_flip_threshold=210.0,
    character_anchor_duration=5.0,
    slide_anchor_duration=10.0,
    crossfade_duration=1.5,
    transition_anchor="alternating",
):
    """
    Add side changes and full-screen transitions.
    """

    if side_flip_threshold <= 0:
        raise ValueError(
            "side_flip_threshold must be greater than 0."
        )

    if character_anchor_duration <= 0:
        raise ValueError(
            "character_anchor_duration must be greater than 0."
        )

    if slide_anchor_duration <= 0:
        raise ValueError(
            "slide_anchor_duration must be greater than 0."
        )

    if crossfade_duration <= 0:
        raise ValueError(
            "crossfade_duration must be greater than 0."
        )

    varied = []

    current_side = "left"

    # Cumulative time spent showing slides while the
    # character is on the current side.
    time_since_flip = 0.0

    side_swap_count = 0

    EPS = 0.01

    # --------------------------------------------------------
    # Process original timeline
    # --------------------------------------------------------

    for original in timeline:

        entry = dict(original)

        # ----------------------------------------------------
        # Demos and other non-slide entries are copied exactly.
        # ----------------------------------------------------

        if entry.get("type") != "slide":

            varied.append(entry)

            continue

        image = entry["image"]

        cursor = float(entry["start"])
        remaining = float(entry["duration"])

        # ----------------------------------------------------
        # A single slide can contain:
        #
        # normal slide
        # transition
        # full-screen anchor
        # transition
        # new-side slide
        #
        # if the threshold occurs inside the slide.
        # ----------------------------------------------------

        while remaining > EPS:

            until_flip = (
                side_flip_threshold
                - time_since_flip
            )

            # =================================================
            # NORMAL SLIDE
            # =================================================

            if until_flip > EPS:

                normal_duration = min(
                    remaining,
                    until_flip
                )

                varied.append({
                    "type": "slide",
                    "image": image,
                    "start": cursor,
                    "duration": normal_duration,
                    "side": current_side,
                })

                cursor += normal_duration
                remaining -= normal_duration
                time_since_flip += normal_duration

                continue

            # =================================================
            # SIDE CHANGE
            # =================================================

            side_swap_count += 1

            new_side = flip_side(
                current_side
            )

            anchor_type = get_anchor_type(
                side_swap_count,
                transition_anchor
            )

            anchor = build_anchor(
                anchor_type,
                image
            )

            if anchor_type == "character":
                anchor_duration = (
                    character_anchor_duration
                )
            else:
                anchor_duration = (
                    slide_anchor_duration
                )

            desired_total = (
                2.0 * crossfade_duration
                + anchor_duration
            )

            # =================================================
            # We need enough time in the current slide to fit:
            #
            # crossfade
            # anchor
            # crossfade
            #
            # If there is enough room, use the requested
            # durations.
            #
            # If not, scale them proportionally.
            # =================================================

            available = remaining

            local_anchor = anchor_duration
            local_crossfade = crossfade_duration

            if available < desired_total:

                scale = (
                    available
                    / desired_total
                )

                local_anchor *= scale
                local_crossfade *= scale

            # =================================================
            # CROSSFADE INTO FULL-SCREEN ANCHOR
            # =================================================

            varied.append({
                "type": "transition",

                "start": cursor,

                "duration": local_crossfade,

                "from": {
                    "type": "slide",
                    "image": image,
                    "side": current_side,
                },

                "to": anchor,
            })

            cursor += local_crossfade
            remaining -= local_crossfade

            # =================================================
            # FULL-SCREEN CHARACTER OR SLIDE
            # =================================================

            varied.append({
                **anchor,

                "start": cursor,

                "duration": local_anchor,
            })

            cursor += local_anchor
            remaining -= local_anchor

            # =================================================
            # CROSSFADE INTO NEW SIDE
            # =================================================

            varied.append({
                "type": "transition",

                "start": cursor,

                "duration": local_crossfade,

                "from": anchor,

                "to": {
                    "type": "slide",
                    "image": image,
                    "side": new_side,
                },
            })

            cursor += local_crossfade
            remaining -= local_crossfade

            # =================================================
            # SIDE HAS NOW CHANGED
            # =================================================

            current_side = new_side

            time_since_flip = 0.0

            if remaining < EPS:
                remaining = 0.0

    return varied


# ============================================================
# COMMAND LINE
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Add cumulative side changes with "
            "alternating full-screen transitions."
        )
    )

    parser.add_argument(
        "--timeline",
        required=True,
        help="Input timeline.json"
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Output timeline_varied.json"
    )

    parser.add_argument(
        "--side-flip-threshold",
        type=float,
        default=210.0,
        help=(
            "Cumulative slide seconds before changing side. "
            "Default: 210."
        )
    )

    parser.add_argument(
        "--transition-anchor",
        choices=[
            "character",
            "slide",
            "alternating",
        ],
        default="alternating",
        help=(
            "Full-screen transition anchor. "
            "Default: alternating."
        )
    )

    parser.add_argument(
        "--character-anchor-duration",
        type=float,
        default=5.0,
        help=(
            "Full-screen character duration. "
            "Default: 5 seconds."
        )
    )

    parser.add_argument(
        "--slide-anchor-duration",
        type=float,
        default=10.0,
        help=(
            "Full-screen slide duration. "
            "Default: 10 seconds."
        )
    )

    parser.add_argument(
        "--crossfade-duration",
        type=float,
        default=1.5,
        help=(
            "Crossfade duration. "
            "Default: 1.5 seconds."
        )
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # Load timeline
    # --------------------------------------------------------

    with open(
        args.timeline,
        "r",
        encoding="utf-8"
    ) as f:

        timeline = json.load(f)

    if not timeline:

        raise ValueError(
            "Input timeline is empty."
        )

    # --------------------------------------------------------
    # Create varied timeline
    # --------------------------------------------------------

    varied = vary_timeline(
        timeline=timeline,

        side_flip_threshold=(
            args.side_flip_threshold
        ),

        character_anchor_duration=(
            args.character_anchor_duration
        ),

        slide_anchor_duration=(
            args.slide_anchor_duration
        ),

        crossfade_duration=(
            args.crossfade_duration
        ),

        transition_anchor=(
            args.transition_anchor
        ),
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    with open(
        args.output,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            varied,
            f,
            indent=2
        )

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    n_slide = sum(
        e.get("type") == "slide"
        for e in varied
    )

    n_demo = sum(
        e.get("type") == "demo"
        for e in varied
    )

    n_character = sum(
        e.get("type") == "character"
        for e in varied
    )

    n_slide_full = sum(
        e.get("type") == "slide_full"
        for e in varied
    )

    n_transition = sum(
        e.get("type") == "transition"
        for e in varied
    )

    print()
    print("=" * 60)
    print("VARY LAYOUT RESULT")
    print("=" * 60)

    print(
        f"  Slide segments:              {n_slide}"
    )

    print(
        f"  Demo segments:               {n_demo}"
    )

    print(
        f"  Full-screen character:       {n_character}"
    )

    print(
        f"  Full-screen slide:           {n_slide_full}"
    )

    print(
        f"  Crossfade transitions:       {n_transition}"
    )

    print()

    print(
        f"Side-change threshold: "
        f"{args.side_flip_threshold:.1f} seconds"
    )

    print(
        f"Full-screen character: "
        f"{args.character_anchor_duration:.1f} seconds"
    )

    print(
        f"Full-screen slide:     "
        f"{args.slide_anchor_duration:.1f} seconds"
    )

    print(
        f"Crossfade duration:    "
        f"{args.crossfade_duration:.1f} seconds"
    )

    print()

    if args.transition_anchor == "alternating":

        print(
            "  1st side change -> "
            "FULL-SCREEN CHARACTER (5s)"
        )

        print(
            "  2nd side change -> "
            "FULL-SCREEN SLIDE (10s)"
        )

        print(
            "  3rd side change -> "
            "FULL-SCREEN CHARACTER (5s)"
        )

        print(
            "  4th side change -> "
            "FULL-SCREEN SLIDE (10s)"
        )

    print()

    print(
        f"Saved to: {args.output}"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()