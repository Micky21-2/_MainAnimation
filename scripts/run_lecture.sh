#!/bin/bash

FILENAME=$(basename "$3")
RUN_NAME="${FILENAME%.*}"

python run_pipeline.py \
  --run-name "$RUN_NAME" \
  --image1 "$1" \
  --image2 "$2" \
  --narration "$3" \
  --reference-video "$4" \
  --comfy-output-dir "../../ComfyUI/output" \
  --comfyui-url "http://127.0.0.1:8188" \
  --base-dir .. \
  --signature-method layout \
  --detect-demo-segments \
  --vary-layout \
  --side-flip-threshold 210 \
  --transition-anchor alternating \
  --character-anchor-duration 10 \
  --slide-anchor-duration 10 \
  --crossfade-duration 2.0 \
  --talking-head-ratio 0.3 \
  --subtitles \
  --subtitle-font-size 10