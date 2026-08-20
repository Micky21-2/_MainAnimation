"""
vary_layout.py

Adds controlled side changes to an existing lecture timeline.

Behavior:
    - Character starts on the LEFT.
    - After --side-flip-threshold seconds of cumulative SLIDE time,
      the character changes to the other side.
    - Every side change is wrapped in two smooth crossfades:
          split-screen -> full-screen anchor
          full-screen anchor -> split-screen on the new side
    - Side-change anchors alternate:
          1st -> full-screen character
          2nd -> full-screen slide
          3rd -> full-screen character
          4th -> full-screen slide
          ...
    - Full-screen character duration defaults to 5 seconds.
    - Full-screen slide duration defaults to 10 seconds.
    - Crossfade duration defaults to 1.5 seconds.
    - Demo entries are copied unchanged and do NOT count toward the
      side-change threshold.

The output timeline uses ONE consistent format throughout:
    {"type": ..., "start": ..., "duration": ...}

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


def flip_side(side):
    return "right" if side == "left" else "left"


def get_anchor_type(side_swap_count, transition_anchor):
    if transition_anchor == "character":
        return "character"
    if transition_anchor == "slide":
        return "slide_full"
    return "character" if side_swap_count % 2 == 1 else "slide_full"


def build_anchor(anchor_type, image):
    if anchor_type == "character":
        return {"type": "character"}
    return {"type": "slide_full", "image": image}


def vary_timeline(
    timeline,
    side_flip_threshold=210.0,
    character_anchor_duration=5.0,
    slide_anchor_duration=10.0,
    crossfade_duration=1.5,
    transition_anchor="alternating",
):
    """Return a timeline with side changes and full-screen transitions."""

    if side_flip_threshold <= 0:
        raise ValueError("side_flip_threshold must be greater than 0.")
    if character_anchor_duration <= 0:
        raise ValueError("character_anchor_duration must be greater than 0.")
    if slide_anchor_duration <= 0:
        raise ValueError("slide_anchor_duration must be greater than 0.")
    if crossfade_duration <= 0:
        raise ValueError("crossfade_duration must be greater than 0.")

    varied = []
    current_side = "left"
    time_since_flip = 0.0
    side_swap_count = 0
    eps = 0.01

    for original in timeline:
        entry = dict(original)

        # Demos and any non-slide entries are left untouched.
        if entry.get("type") != "slide":
            varied.append(entry)
            continue

        image = entry["image"]
        cursor = float(entry["start"])
        remaining = float(entry["duration"])

        while remaining > eps:
            until_flip = side_flip_threshold - time_since_flip

            # Normal portion before the next side change.
            if until_flip > eps and remaining <= until_flip + eps:
                varied.append({
                    "type": "slide",
                    "image": image,
                    "start": cursor,
                    "duration": remaining,
                    "side": current_side,
                })
                time_since_flip += remaining
                cursor += remaining
                remaining = 0.0
                continue

            # If the threshold is reached exactly at a slide boundary,
            # the next slide should perform the side change rather than
            # getting stuck forever at the threshold.
            side_swap_count += 1
            new_side = flip_side(current_side)
            anchor_type = get_anchor_type(
                side_swap_count,
                transition_anchor,
            )
            anchor = build_anchor(anchor_type, image)

            anchor_duration = (
                character_anchor_duration
                if anchor_type == "character"
                else slide_anchor_duration
            )

            desired_total = (
                2.0 * crossfade_duration + anchor_duration
            )

            # If there is enough room after the point where the threshold
            # is reached, begin the transition early enough that the SIDE
            # CHANGE itself happens at the threshold.
            if until_flip > eps:
                before_transition = until_flip - desired_total
            else:
                before_transition = 0.0

            # If the full transition cannot fit before the end of the
            # current slide, compress it proportionally. This keeps the
            # timeline duration exactly equal to the original slide.
            available_for_transition = remaining - max(before_transition, 0.0)

            if available_for_transition <= eps:
                # This should only occur due to numerical edge cases.
                # Emit the remaining time and let the next slide continue.
                varied.append({
                    "type": "slide",
                    "image": image,
                    "start": cursor,
                    "duration": remaining,
                    "side": current_side,
                })
                time_since_flip += remaining
                cursor += remaining
                remaining = 0.0
                side_swap_count -= 1
                continue

            if before_transition > eps:
                varied.append({
                    "type": "slide",
                    "image": image,
                    "start": cursor,
                    "duration": before_transition,
                    "side": current_side,
                })
                cursor += before_transition
                remaining -= before_transition
                time_since_flip += before_transition

            # At this point we have enough time for the transition, or the
            # transition is being compressed to fit the current slide.
            available = remaining
            local_anchor = anchor_duration
            local_crossfade = crossfade_duration
            required = desired_total

            if available < required:
                scale = available / required
                local_anchor *= scale
                local_crossfade *= scale

            # Crossfade INTO the full-screen anchor.
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

            # Full-screen character or full-screen slide.
            varied.append({
                **anchor,
                "start": cursor,
                "duration": local_anchor,
            })
            cursor += local_anchor
            remaining -= local_anchor

            # Crossfade OUT to the new side.
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

            current_side = new_side
            time_since_flip = 0.0

            # Avoid tiny floating-point leftovers.
            if remaining < eps:
                remaining = 0.0

    return varied


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Change talking-head side after cumulative slide time "
            "using alternating full-screen character/slide anchors."
        )
    )

    parser.add_argument("--timeline", required=True, help="Input timeline.json")
    parser.add_argument("--output", required=True, help="Output timeline_varied.json")
    parser.add_argument(
        "--side-flip-threshold",
        type=float,
        default=210.0,
        help="Cumulative slide seconds before changing side. Default: 210.",
    )
    parser.add_argument(
        "--transition-anchor",
        choices=["character", "slide", "alternating"],
        default="alternating",
        help=(
            "Full-screen anchor: character, slide, or alternating. "
            "Default: alternating."
        ),
    )
    parser.add_argument(
        "--character-anchor-duration",
        type=float,
        default=5.0,
        help="Full-screen character duration. Default: 5 seconds.",
    )
    parser.add_argument(
        "--slide-anchor-duration",
        type=float,
        default=10.0,
        help="Full-screen slide duration. Default: 10 seconds.",
    )
    parser.add_argument(
        "--crossfade-duration",
        type=float,
        default=1.5,
        help="Duration of each crossfade. Default: 1.5 seconds.",
    )

    args = parser.parse_args()

    with open(args.timeline, "r", encoding="utf-8") as f:
        timeline = json.load(f)

    if not timeline:
        raise ValueError("Input timeline is empty.")

    varied = vary_timeline(
        timeline=timeline,
        side_flip_threshold=args.side_flip_threshold,
        character_anchor_duration=args.character_anchor_duration,
        slide_anchor_duration=args.slide_anchor_duration,
        crossfade_duration=args.crossfade_duration,
        transition_anchor=args.transition_anchor,
    )

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(varied, f, indent=2)

    n_slide = sum(e.get("type") == "slide" for e in varied)
    n_demo = sum(e.get("type") == "demo" for e in varied)
    n_character = sum(e.get("type") == "character" for e in varied)
    n_slide_full = sum(e.get("type") == "slide_full" for e in varied)
    n_transition = sum(e.get("type") == "transition" for e in varied)

    print()
    print("=" * 60)
    print("VARY LAYOUT RESULT")
    print("=" * 60)
    print(f"  Slide segments:              {n_slide}")
    print(f"  Demo segments:               {n_demo}")
    print(f"  Full-screen character:       {n_character}")
    print(f"  Full-screen slide:           {n_slide_full}")
    print(f"  Crossfade transitions:       {n_transition}")
    print()
    print(f"Side-change threshold: {args.side_flip_threshold:.1f} seconds")
    print(f"Full-screen character: {args.character_anchor_duration:.1f} seconds")
    print(f"Full-screen slide:     {args.slide_anchor_duration:.1f} seconds")
    print(f"Crossfade duration:    {args.crossfade_duration:.1f} seconds")
    print()
    print("Anchor sequence:")
    if args.transition_anchor == "alternating":
        print("  1st side change -> FULL-SCREEN CHARACTER (5s)")
        print("  2nd side change -> FULL-SCREEN SLIDE     (10s)")
        print("  3rd side change -> FULL-SCREEN CHARACTER (5s)")
        print("  4th side change -> FULL-SCREEN SLIDE     (10s)")
        print("  ...")
    else:
        print(f"  {args.transition_anchor}")
    print()
    print(f"Saved to: {args.output}")
    print("=" * 60)


if __name__ == "__main__":
    main()
