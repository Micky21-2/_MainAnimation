# LTX-2.3 Two-Image Video Pipeline
## Simplified for Presentation with Audio Segments

"""
Pipeline Architecture:
- Segment 1: Image1 (first) -> Image2 (last)  + Audio[0-20s]
- Segment 2: Image2 (first) -> Image2 (last)  + Audio[20-40s]
- Segment 3: Image2 (first) -> Image2 (last)  + Audio[40-60s]
- ...
- SegmentN: Image2 (first) -> Image2 (last)  + Audio[duration]

Result: Smooth first transition, then stable Image2 throughout rest of presentation.

All inputs (images, audio, run name, ComfyUI output dir) are passed via CLI
arguments -- nothing about a specific video or run is hardcoded.
"""

import os
import time
import json
import shutil
import argparse
import requests
import subprocess
from pathlib import Path
import random
import secrets



# SETTINGS
COMFYUI_URL = "http://127.0.0.1:8188"

# FIXED_SEED = secrets.randbelow(1_000_000_000)
# print(f"Seed Number: {FIXED_SEED}")

FIXED_SEED = 11395556


SEGMENT_SECS = 20  # Audio segment duration

WIDTH = 720
HEIGHT = 1080
FPS = 24

# Model names
CKPT_NAME = "ltx-2.3-22b-dev-fp8.safetensors"
DISTILLED_LORA = "ltx-2.3-22b-distilled-lora-384.safetensors"
TEXT_ENCODER = "gemma_3_12B_it_fp4_mixed.safetensors"
UPSCALE_MODEL = "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"

NEGATIVE_PROMPT = (
    "pc game, console game, video game, cartoon, childish, ugly, "
    "inconsistent character, morphing face, changing appearance, "
    "zoom in, zoom out, camera zoom, close up, push in, dolly in, "
    "camera movement, camera pan, camera shake, moving camera, "
    "dolly zoom, smash zoom, crash zoom, animated zoom, slow zoom, "
    "creeping zoom, truck in, scale change, growing larger, shrinking, "
    "closed mouth, no lip movement, static face, expressionless, "
    "stiff motion, frozen pose, no movement, rigid, white background"
    "Four fingers, three fingers, button in the coat, white noise"
)


# UTILS

def run(cmd):
    """Execute shell command"""
    subprocess.run(cmd, check=True)


def get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds"""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        audio_path,
    ]
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True
    )
    
    info = json.loads(result.stdout)
    
    for stream in info.get("streams", []):
        if "duration" in stream:
            return float(stream["duration"])
    
    raise RuntimeError("Could not determine audio duration.")


def split_audio(audio_path: str, segment_secs: int, out_dir: str):
    """Split audio into chunks of segment_secs duration"""
    os.makedirs(out_dir, exist_ok=True)
    
    duration = get_audio_duration(audio_path)
    chunks = []
    start = 0.0
    idx = 0
    
    total = int(duration / segment_secs) + 1
    print(f"\n[1/4] Splitting audio into ~{total} chunks ({segment_secs}s each)")
    
    while start < duration:
        out_path = os.path.join(out_dir, f"chunk_{idx:04d}.wav")
        
        if not os.path.exists(out_path):
            actual_duration = min(segment_secs, duration - start)
            
            cmd = [
                "ffmpeg",
                "-y",
                "-loglevel", "error",
                "-i", audio_path,
                "-ss", str(start),
                "-t", str(actual_duration),
                "-acodec", "pcm_s16le",
                "-ar", "44100",
                "-ac", "2",
                out_path,
            ]
            
            run(cmd)
        
        try:
            test = subprocess.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    out_path,
                ],
                capture_output=True,
                text=True,
                check=True
            )
            
            duration_check = float(test.stdout.strip())
            
            if duration_check > 1.0:
                chunks.append((out_path, start))
            else:
                print(f"Skipping short chunk {idx}")
                os.remove(out_path)
        
        except Exception:
            print(f"Skipping invalid chunk {idx}")
            if os.path.exists(out_path):
                os.remove(out_path)
        
        start += segment_secs
        idx += 1
    
    print(f"Ready {len(chunks)} chunks")
    return chunks


def upload_file_to_comfyui(file_path: str):
    """Upload file to ComfyUI input folder"""
    ext = Path(file_path).suffix.lower()
    
    if ext == ".png":
        mime = "image/png"
    elif ext in [".jpg", ".jpeg"]:
        mime = "image/jpeg"
    elif ext == ".wav":
        mime = "audio/wav"
    else:
        mime = "audio/mpeg"
    
    with open(file_path, "rb") as f:
        r = requests.post(
            f"{COMFYUI_URL}/upload/image",
            files={
                "image": (
                    os.path.basename(file_path),
                    f,
                    mime
                )
            },
        )
    
    r.raise_for_status()
    return r.json()["name"]


def clear_comfyui_inputs(comfyui_input_dir: str):
    """Clear temporary input files"""
    for f in Path(comfyui_input_dir).glob("chunk_*"):
        f.unlink()
    for f in Path(comfyui_input_dir).glob("image_*"):
        f.unlink()


# FL2V WORKFLOW (First-Last Frame with Custom Audio)

def build_fl2v_workflow(
    first_image_name,
    last_image_name,
    audio_name,
    prompt,
    output_prefix,
    noise_seed_1,
    noise_seed_2,
    duration_seconds,
):
    """
    Build First-Last Frame to Video workflow with custom audio.
    """
    
    # Calculate frame count from duration
    frame_count = int(duration_seconds * FPS) + 1
    
    return {
        # INPUTS: IMAGES AND AUDIO        
        "269": {
            "class_type": "LoadImage",
            "inputs": {"image": first_image_name}
        },
        
        "270": {
            "class_type": "LoadImage",
            "inputs": {"image": last_image_name}
        },
        
        "276": {
            "class_type": "LoadAudio",
            "inputs": {"audio": audio_name}
        },
        
        # PRIMITIVES: VIDEO SETTINGS        
        "340:330": {
            "class_type": "PrimitiveInt",
            "inputs": {"value": WIDTH}
        },
        
        "340:324": {
            "class_type": "PrimitiveInt",
            "inputs": {"value": HEIGHT}
        },
        
        "340:323": {
            "class_type": "PrimitiveInt",
            "inputs": {"value": FPS}
        },
        
        "340:331": {
            "class_type": "PrimitiveInt",
            "inputs": {"value": frame_count}
        },
        
        "340:319": {
            "class_type": "PrimitiveStringMultiline",
            "inputs": {"value": prompt}
        },
        
        # NOISE SEEDS
        
        "340:285": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": noise_seed_1}
        },
        
        "340:286": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": noise_seed_2}
        },
        
        # MODEL LOADERS        
        "340:317": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": CKPT_NAME}
        },
        
        "340:293": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "lora_name": DISTILLED_LORA,
                "strength_model": 0.5,
                "model": ["340:317", 0]
            }
        },
        
        "340:318": {
            "class_type": "LTXAVTextEncoderLoader",
            "inputs": {
                "text_encoder": TEXT_ENCODER,
                "ckpt_name": CKPT_NAME,
                "device": "default"
            }
        },
        
        "340:313": {
            "class_type": "LatentUpscaleModelLoader",
            "inputs": {"model_name": UPSCALE_MODEL}
        },
        
        "340:335": {
            "class_type": "LTXVAudioVAELoader",
            "inputs": {"ckpt_name": CKPT_NAME}
        },
        
        # TEXT ENCODING
        "340:306": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": ["340:319", 0],
                "clip": ["340:318", 0]
            }
        },
        
        "340:314": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": NEGATIVE_PROMPT,
                "clip": ["340:318", 0]
            }
        },
        
        # IMAGE PREPROCESSING        
        "340:297_first": {
            "class_type": "ResizeImageMaskNode",
            "inputs": {
                "resize_type": "scale dimensions",
                "resize_type.width": ["340:330", 0],
                "resize_type.height": ["340:324", 0],
                "resize_type.crop": "center",
                "scale_method": "lanczos",
                "input": ["269", 0]
            }
        },
        
        "340:297_last": {
            "class_type": "ResizeImageMaskNode",
            "inputs": {
                "resize_type": "scale dimensions",
                "resize_type.width": ["340:330", 0],
                "resize_type.height": ["340:324", 0],
                "resize_type.crop": "center",
                "scale_method": "lanczos",
                "input": ["270", 0]
            }
        },
        
        "340:294_first": {
            "class_type": "ResizeImagesByLongerEdge",
            "inputs": {
                "longer_edge": 1536,
                "images": ["340:297_first", 0]
            }
        },
        
        "340:294_last": {
            "class_type": "ResizeImagesByLongerEdge",
            "inputs": {
                "longer_edge": 1536,
                "images": ["340:297_last", 0]
            }
        },
        
        "340:334_first": {
            "class_type": "LTXVPreprocess",
            "inputs": {
                "img_compression": 18,
                "image": ["340:294_first", 0]
            }
        },
        
        "340:334_last": {
            "class_type": "LTXVPreprocess",
            "inputs": {
                "img_compression": 18,
                "image": ["340:294_last", 0]
            }
        },
        
        # AUDIO PROCESSING        
        "340:332": {
            "class_type": "TrimAudioDuration",
            "inputs": {
                "start_index": 0,
                "duration": duration_seconds,
                "audio": ["276", 0]
            }
        },
        
        "340:328": {
            "class_type": "LTXVAudioVAEEncode",
            "inputs": {
                "audio": ["340:332", 0],
                "audio_vae": ["340:335", 0]
            }
        },
                # LATENT CALCULATIONS        
        "340:299": {
            "class_type": "ComfyMathExpression",
            "inputs": {
                "expression": "a/2",
                "values.a": ["340:330", 0]
            }
        },
        
        "340:301": {
            "class_type": "ComfyMathExpression",
            "inputs": {
                "expression": "a/2",
                "values.a": ["340:324", 0]
            }
        },
        
        "340:304": {
            "class_type": "ComfyMathExpression",
            "inputs": {
                "expression": "a",
                "values.a": ["340:323", 0]
            }
        },
        
        "340:329": {
            "class_type": "ComfyMathExpression",
            "inputs": {
                "expression": "a",
                "values.a": ["340:331", 0]
            }
        },
        
        # EMPTY LATENTS        
        "340:302": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": ["340:299", 1],
                "height": ["340:301", 1],
                "length": ["340:329", 1],
                "batch_size": 1
            }
        },
        
        "340:333": {
            "class_type": "SolidMask",
            "inputs": {
                "value": 0,
                "width": ["340:330", 0],
                "height": ["340:324", 0]
            }
        },
        
        "340:327": {
            "class_type": "SetLatentNoiseMask",
            "inputs": {
                "samples": ["340:328", 0],
                "mask": ["340:333", 0]
            }
        },
        
        # CONDITIONING        
        "340:307": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "frame_rate": ["340:304", 0],
                "positive": ["340:306", 0],
                "negative": ["340:314", 0]
            }
        },
        
        # PASS 1: GENERATION WITH FIRST-LAST FRAME CONDITIONING        
        "340:325": {
            "class_type": "LTXVImgToVideoInplace",
            "inputs": {
                "strength": 0.7,
                "bypass": False,
                "vae": ["340:317", 2],
                "image": ["340:334_first", 0],
                "latent": ["340:302", 0]
            }
        },
        
        "340:325_last": {
            "class_type": "LTXVImgToVideoInplace",
            "inputs": {
                "strength": 0.7,
                "bypass": False,
                "vae": ["340:317", 2],
                "image": ["340:334_last", 0],
                "latent": ["340:325", 0]
            }
        },
        
        "340:326": {
            "class_type": "LTXVConcatAVLatent",
            "inputs": {
                "video_latent": ["340:325_last", 0],
                "audio_latent": ["340:327", 0]
            }
        },
        
        # SAMPLING PASS 1
        "340:288": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "euler_cfg_pp"}
        },
        
        "340:289": {
            "class_type": "ManualSigmas",
            "inputs": {"sigmas": "0.85, 0.7250, 0.4219, 0.0"}
        },
        
        "340:292": {
            "class_type": "LTXVCropGuides",
            "inputs": {
                "positive": ["340:307", 0],
                "negative": ["340:307", 1],
                "latent": ["340:302", 0]
            }
        },
        
        "340:290": {
            "class_type": "CFGGuider",
            "inputs": {
                "cfg": 1,
                "model": ["340:293", 0],
                "positive": ["340:292", 0],
                "negative": ["340:292", 1]
            }
        },
        
        "340:310": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["340:285", 0],
                "guider": ["340:290", 0],
                "sampler": ["340:288", 0],
                "sigmas": ["340:289", 0],
                "latent_image": ["340:326", 0]
            }
        },
        
        "340:311": {
            "class_type": "LTXVSeparateAVLatent",
            "inputs": {"av_latent": ["340:310", 0]}
        },
        
        # UPSCALE        
        "340:295": {
            "class_type": "LTXVLatentUpsampler",
            "inputs": {
                "samples": ["340:311", 0],
                "upscale_model": ["340:313", 0],
                "vae": ["340:317", 2]
            }
        },
        
        "340:296": {
            "class_type": "LTXVImgToVideoInplace",
            "inputs": {
                "strength": 1,
                "bypass": False,
                "vae": ["340:317", 2],
                "image": ["340:334_first", 0],
                "latent": ["340:295", 0]
            }
        },
        
        "340:296_last": {
            "class_type": "LTXVImgToVideoInplace",
            "inputs": {
                "strength": 1,
                "bypass": False,
                "vae": ["340:317", 2],
                "image": ["340:334_last", 0],
                "latent": ["340:296", 0]
            }
        },
        
        "340:287": {
            "class_type": "LTXVConcatAVLatent",
            "inputs": {
                "video_latent": ["340:296_last", 0],
                "audio_latent": ["340:311", 1]
            }
        },
        
        # PASS 2: REFINEMENT        
        "340:298": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "euler_ancestral_cfg_pp"}
        },
        
        "340:308": {
            "class_type": "ManualSigmas",
            "inputs": {
                "sigmas": (
                    "1.0, 0.99375, 0.9875, "
                    "0.98125, 0.975, 0.909375, "
                    "0.725, 0.421875, 0.0"
                )
            }
        },
        
        "340:315": {
            "class_type": "CFGGuider",
            "inputs": {
                "cfg": 1,
                "model": ["340:293", 0],
                "positive": ["340:307", 0],
                "negative": ["340:307", 1]
            }
        },
        
        "340:291": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["340:286", 0],
                "guider": ["340:315", 0],
                "sampler": ["340:298", 0],
                "sigmas": ["340:308", 0],
                "latent_image": ["340:287", 0]
            }
        },
        
        "340:309": {
            "class_type": "LTXVSeparateAVLatent",
            "inputs": {"av_latent": ["340:291", 0]}
        },
        
        # DECODE        
        "340:316": {
            "class_type": "VAEDecodeTiled",
            "inputs": {
                "tile_size": 768,
                "overlap": 64,
                "temporal_size": 4096,
                "temporal_overlap": 4,
                "samples": ["340:309", 0],
                "vae": ["340:317", 2]
            }
        },
        
        # CREATE VIDEO WITH ORIGINAL AUDIO        
        "340:312": {
            "class_type": "CreateVideo",
            "inputs": {
                "fps": ["340:304", 0],
                "images": ["340:316", 0],
                "audio": ["340:332", 0]
            }
        },
        
        # SAVE        
        "341": {
            "class_type": "SaveVideo",
            "inputs": {
                "filename_prefix": output_prefix,
                "format": "auto",
                "codec": "auto",
                "video": ["340:312", 0]
            }
        },
    }


# COMFYUI API
def queue_prompt(workflow):
    """Queue prompt in ComfyUI"""
    payload = {"prompt": workflow}
    
    r = requests.post(f"{COMFYUI_URL}/prompt", json=payload)
    
    if r.status_code != 200:
        print(r.text)
        r.raise_for_status()
    
    return r.json()["prompt_id"]


def wait_for_completion(prompt_id, poll_interval=5):
    """Wait for ComfyUI to finish generation"""
    print("Waiting for ComfyUI", end="", flush=True)
    
    while True:
        r = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
        r.raise_for_status()
        history = r.json()
        
        if prompt_id in history:
            print(" done")
            return history[prompt_id]
        
        print(".", end="", flush=True)
        time.sleep(poll_interval)


def get_output_video_path(history_entry, comfy_output_dir):
    """Find generated video in output directory"""
    outputs = history_entry.get("outputs", {})

    checked_paths = []

    for _, node_output in outputs.items():
        for key in ["videos", "gifs", "images"]:
            if key not in node_output:
                continue

            for item in node_output[key]:
                filename = item.get("filename", "")
                subfolder = item.get("subfolder", "")

                full_path = os.path.join(
                    comfy_output_dir,
                    subfolder,
                    filename
                )
                checked_paths.append(full_path)

                if os.path.exists(full_path):
                    return full_path

    if not os.path.isdir(comfy_output_dir):
        raise RuntimeError(
            f"Could not locate generated video: --comfy-output-dir "
            f"'{comfy_output_dir}' is not a real directory on this machine. "
            f"Check that it points to your actual ComfyUI output folder "
            f"(e.g. /home/<user>/ComfyUI/output), not a placeholder path."
        )

    if not checked_paths:
        raise RuntimeError(
            "Could not locate generated video: ComfyUI's history response "
            "for this prompt contained no video/gif/image outputs at all. "
            "The generation may have failed inside ComfyUI itself -- check "
            "the ComfyUI server logs/console for errors on this prompt."
        )

    raise RuntimeError(
        "Could not locate generated video. --comfy-output-dir "
        f"'{comfy_output_dir}' exists, but none of the expected output "
        f"files were found there. Checked:\n  " + "\n  ".join(checked_paths) +
        "\nThis usually means --comfy-output-dir points to the wrong "
        "ComfyUI instance/output folder, or ComfyUI is writing outputs "
        "with subfolders this script isn't accounting for."
    )


# VIDEO CONCATENATION
def concat_videos(video_paths, output_path):
    """Concatenate multiple videos into one"""
    concat_txt = output_path + "_concat.txt"
    
    with open(concat_txt, "w") as f:
        for vp in video_paths:
            f.write(f"file '{os.path.abspath(vp)}'\n")
    
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel", "error",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_txt,
        "-c", "copy",
        output_path,
    ]
    
    run(cmd)
    os.remove(concat_txt)


# MAIN PIPELINE
def main():
    global COMFYUI_URL

    parser = argparse.ArgumentParser(
        description="LTX-2.3 Two-Image Video Pipeline with Audio Segments"
    )
    
    parser.add_argument(
        "--image1",
        required=True,
        help="First image (used in first segment)"
    )
    parser.add_argument(
        "--image2",
        required=True,
        help="Second image (used in first segment as last frame, and all other segments)"
    )
    parser.add_argument(
        "--audio",
        required=True,
        help="Audio file path (MP3 or WAV)"
    )
    parser.add_argument(
        "--run-name",
        required=True,
        help="Name for this run (creates working directory)"
    )
    parser.add_argument(
        "--comfy-output-dir",
        required=True,
        help="ComfyUI output directory"
    )
    parser.add_argument(
        "--comfy-input-dir",
        default=None,
        help="ComfyUI input directory (used to clear stale uploads between segments; if omitted, this cleanup step is skipped)"
    )
    parser.add_argument(
        "--work-dir",
        default="pipeline_workdir",
        help="Base working directory for intermediate files (default: pipeline_workdir)"
    )
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Base output directory for the final stitched video (default: outputs)"
    )
    parser.add_argument(
        "--comfyui-url",
        default=COMFYUI_URL,
        help=f"ComfyUI server URL (default: {COMFYUI_URL})"
    )
    parser.add_argument(
        "--prompt",
        default=(
            "A professor is teaching naturally with consistent lip sync and mouth expression with gestures. The background is white."
        ),
        help="Prompt for video generation"
    )
    parser.add_argument(
        "--segment-secs",
        type=int,
        default=20,
        help="Audio segment duration in seconds (default: 20)"
    )
    
    args = parser.parse_args()

    COMFYUI_URL = args.comfyui_url
    
    # Verify images exist
    if not os.path.exists(args.image1):
        print(f"ERROR: Image1 not found: {args.image1}")
        exit(1)
    if not os.path.exists(args.image2):
        print(f"ERROR: Image2 not found: {args.image2}")
        exit(1)
    
    # Verify audio exists
    if not os.path.exists(args.audio):
        print(f"ERROR: Audio file not found: {args.audio}")
        exit(1)
    
    # Create directories
    work_dir = os.path.join(args.work_dir, args.run_name)
    audio_dir = os.path.join(work_dir, "audio_chunks")
    videos_dir = os.path.join(work_dir, "segments")
    
    output = os.path.join(args.output_dir, args.run_name, "final.mp4")
    
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(videos_dir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    
    print("LTX-2.3 Two-Image Video Pipeline")
    print("First Transition + Stable Content")
    print(f"Image 1 (first): {os.path.basename(args.image1)}")
    print(f"Image 2 (main):  {os.path.basename(args.image2)}")
    print(f"Audio duration: {get_audio_duration(args.audio):.1f} seconds")
    print(f"Segment duration: {args.segment_secs} seconds")
    
    # Split audio into chunks
    chunks = split_audio(args.audio, args.segment_secs, audio_dir)
    
    generated_videos = []
    
    # Check for existing segments to resume
    existing_segments = sorted(Path(videos_dir).glob("segment_*.mp4"))
    resume_from = len(existing_segments)
    
    if resume_from > 0:
        print(f"Resuming from segment {resume_from}")
        for seg in existing_segments:
            generated_videos.append(str(seg))
    
    # Generate each segment
    print(f"\n[2/4] Generating {len(chunks)} video segments...\n")
    
    for i, (audio_chunk, audio_start) in enumerate(chunks):
        
        if i < resume_from:
            continue
        
        # Segment 1: Image1 -> Image2
        # All other segments: Image2 -> Image2
        if i == 0:
            first_image = args.image1
            last_image = args.image2
            print(f"\nSegment {i+1}/{len(chunks)} (TRANSITION)")
            print(f"  First Frame: {os.path.basename(first_image)}")
            print(f"  Last Frame:  {os.path.basename(last_image)}")
        else:
            first_image = args.image2
            last_image = args.image2
            print(f"\nSegment {i+1}/{len(chunks)} (STABLE)")
            print(f"  Frame: {os.path.basename(first_image)}")
        
        print(f"  Audio: {os.path.basename(audio_chunk)}")
        
        # Get audio duration for this chunk
        audio_duration = get_audio_duration(audio_chunk)
        
        seed_1 = FIXED_SEED
        seed_2 = FIXED_SEED + i
        
        if args.comfy_input_dir:
            clear_comfyui_inputs(args.comfy_input_dir)
        
        # Upload files
        first_img_name = upload_file_to_comfyui(first_image)
        last_img_name = upload_file_to_comfyui(last_image)
        audio_name = upload_file_to_comfyui(audio_chunk)
        
        # Build workflow
        workflow = build_fl2v_workflow(
            first_image_name=first_img_name,
            last_image_name=last_img_name,
            audio_name=audio_name,
            prompt=args.prompt,
            output_prefix=f"video/{args.run_name}_segment_{i:04d}",
            noise_seed_1=seed_1,
            noise_seed_2=seed_2,
            duration_seconds=audio_duration,
        )
        
        # Queue and wait
        pid = queue_prompt(workflow)
        history = wait_for_completion(pid)
        
        # Save locally
        seg_video = get_output_video_path(history, args.comfy_output_dir)
        local_seg = os.path.join(videos_dir, f"segment_{i:04d}.mp4")
        
        shutil.copy(seg_video, local_seg)
        generated_videos.append(local_seg)
        
        print(f"  Saved: {local_seg}")
    
    # Concatenate all segments
    print(f"\n[3/4] Stitching {len(generated_videos)} segments...")
    concat_videos(generated_videos, output)
    
    print("\n[4/4] DONE!\n")
    print(f"Final video: {output}")
    print(f"Duration: {get_audio_duration(args.audio):.1f} seconds")

if __name__ == "__main__":
    main()
