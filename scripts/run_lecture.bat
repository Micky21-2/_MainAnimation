@echo off
setlocal

set IMAGE1=%~1
if "%IMAGE1%"=="" set IMAGE1=..\inputs\Dr.Pisut_img_1.png

set IMAGE2=%~2
if "%IMAGE2%"=="" set IMAGE2=..\inputs\Dr.Pisut_img_2.png

set NARRATION=%~3
if "%NARRATION%"=="" set NARRATION=..\inputs\Visualization.m4a

set REF_VIDEO=%~4
if "%REF_VIDEO%"=="" set REF_VIDEO=..\inputs\Visualization.mp4

for %%F in ("%NARRATION%") do set RUN_NAME=%%~nxF

python run_pipeline.py ^
  --run-name "%RUN_NAME%" ^
  --image1 "%IMAGE1%" ^
  --image2 "%IMAGE2%" ^
  --narration "%NARRATION%" ^
  --reference-video "%REF_VIDEO%" ^
  --prompt "A professor is teaching naturally with consistent lip sync and mouth expression with gestures. The background is white." ^
  --comfy-output-dir "../../ComfyUI/output" ^
  --comfyui-url "http://127.0.0.1:8188" ^
  --base-dir .. ^
  --signature-method layout ^
  --detect-demo-segments ^
  --vary-layout ^
  --side-flip-threshold 210 ^
  --transition-anchor alternating ^
  --character-anchor-duration 10 ^
  --slide-anchor-duration 10 ^
  --crossfade-duration 2.0 ^
  --talking-head-ratio 0.3 ^
  --subtitles ^
  --subtitle-font-size 10
