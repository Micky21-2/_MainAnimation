param(
    [string]$Image1 = "../inputs/Dr.Pisut_img_1.png",
    [string]$Image2 = "../inputs/Dr.Pisut_img_2.png",
    [string]$Narration = "../inputs/Visualization.m4a",
    [string]$ReferenceVideo = "../inputs/Visualization.mp4",
    [string]$Prompt = "A professor is teaching naturally with consistent lip sync and mouth expression with gestures. The background is white."
)

$RunName = [System.IO.Path]::GetFileNameWithoutExtension($Narration)

python run_pipeline.py `
  --run-name "$RunName" `
  --image1 "$Image1" `
  --image2 "$Image2" `
  --narration "$Narration" `
  --reference-video "$ReferenceVideo" `
  --prompt "$Prompt" `
  --comfy-output-dir "../../ComfyUI/output" `
  --comfyui-url "http://127.0.0.1:8188" `
  --base-dir .. `
  --signature-method layout `
  --detect-demo-segments `
  --vary-layout `
  --side-flip-threshold 210 `
  --transition-anchor alternating `
  --character-anchor-duration 10 `
  --slide-anchor-duration 10 `
  --crossfade-duration 2.0 `
  --talking-head-ratio 0.3 `
  --subtitles `
  --subtitle-font-size 10
