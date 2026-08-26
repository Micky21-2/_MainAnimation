#!/bin/bash

python run_pipeline.py \
  --run-name "$(basename "$3" .MP3)" \
  --image1 "$1" \
  --image2 "$2" \
  --narration "$3" \
  --reference-video "$4" \
  --comfy-output-dir "/home/glider/ComfyUI/output" \
  --comfyui-url "http://127.0.0.1:8188" \
  --base-dir .. \
  --signature-method layout \
  --detect-demo-segments \
  --vary-layout \
  --side-flip-threshold 210 \
  --transition-anchor alternating \
  --character-anchor-duration 5 \
  --slide-anchor-duration 10 \
  --crossfade-duration 1.5 \
  --talking-head-ratio 0.3 \
  --subtitles \
  --subtitle-font-size 10