## ComfyUI Setup

This project uses [ComfyUI](https://github.com/Comfy-Org/ComfyUI) as the backend for AI video generation. ComfyUI is a separate open-source project and is **not included in this repository**.

The pipeline uses **LTX-2.3** for generating video segments from lecture images and narration audio.

### 1. Install ComfyUI

ComfyUI must be installed separately from this repository.

Clone the official ComfyUI repository:

```bash
git clone https://github.com/Comfy-Org/ComfyUI.git
cd ComfyUI
```

Create and activate a Python virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install the ComfyUI dependencies:

```bash
pip install -r requirements.txt
```

For NVIDIA GPUs, make sure that a compatible CUDA-enabled version of PyTorch is installed.

For more information, see the official ComfyUI repository:

https://github.com/Comfy-Org/ComfyUI

---

### 2. Install LTXVideo Custom Nodes

The pipeline uses the LTXVideo custom nodes for LTX-2.3 generation.

From the ComfyUI directory:

```bash
cd custom_nodes
git clone https://github.com/Lightricks/ComfyUI-LTXVideo.git
```

Install the custom-node dependencies:

```bash
cd ComfyUI-LTXVideo
pip install -r requirements.txt
```

Then return to the ComfyUI directory:

```bash
cd ../..
```

---

### 3. Download the Required Models

The pipeline requires the following LTX-2.3 models:

| Model                    | Filename                                      | ComfyUI Directory               |
| ------------------------ | --------------------------------------------- | ------------------------------- |
| LTX-2.3 checkpoint       | `ltx-2.3-22b-dev-fp8.safetensors`             | `models/checkpoints/`           |
| Distilled LoRA           | `ltx-2.3-22b-distilled-lora-384.safetensors`  | `models/loras/`                 |
| Gemma 3 12B text encoder | `gemma_3_12B_it_fp4_mixed.safetensors`        | `models/text_encoders/`         |
| LTX-2.3 spatial upscaler | `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` | `models/latent_upscale_models/` |

#### LTX-2.3 Checkpoint

Download:

```text
ltx-2.3-22b-dev-fp8.safetensors
```

Place it in:

```text
ComfyUI/models/checkpoints/
```

#### Distilled LoRA

Download:

```text
ltx-2.3-22b-distilled-lora-384.safetensors
```

Place it in:

```text
ComfyUI/models/loras/
```

#### Gemma 3 12B Text Encoder

Download:

```text
gemma_3_12B_it_fp4_mixed.safetensors
```

Place it in:

```text
ComfyUI/models/text_encoders/
```

#### LTX-2.3 Spatial Upscaler

Download:

```text
ltx-2.3-spatial-upscaler-x2-1.1.safetensors
```

Place it in:

```text
ComfyUI/models/latent_upscale_models/
```

Official model and workflow information can be found in the [LTX-2.3 ComfyUI documentation](https://docs.comfy.org/tutorials/video/ltx/ltx-2-3).

---

### 4. Required ComfyUI Directory Structure

After installing ComfyUI and downloading the models, the relevant directories should look like:

```text
ComfyUI/
├── custom_nodes/
│   └── ComfyUI-LTXVideo/
│
└── models/
    ├── checkpoints/
    │   └── ltx-2.3-22b-dev-fp8.safetensors
    │
    ├── loras/
    │   └── ltx-2.3-22b-distilled-lora-384.safetensors
    │
    ├── text_encoders/
    │   └── gemma_3_12B_it_fp4_mixed.safetensors
    │
    └── latent_upscale_models/
        └── ltx-2.3-spatial-upscaler-x2-1.1.safetensors
```

---

### 5. Start ComfyUI

Activate the ComfyUI environment:

```bash
cd /path/to/ComfyUI
source venv/bin/activate
```

Start the ComfyUI server:

```bash
python main.py
```

By default, the ComfyUI server runs at:

```text
http://127.0.0.1:8188
```

Keep the ComfyUI server running while using the lecture video pipeline.

---

### 6. Run the Lecture Video Pipeline

Once ComfyUI is running, open a second terminal and activate the pipeline environment.

For example:

```bash
cd /path/to/mainscripts
source scripts/pipeline_venv/bin/activate
```

Then run the pipeline using the provided script:

```bash
./scripts/run_lecture.sh
```

The pipeline communicates with the ComfyUI server through:

```text
http://127.0.0.1:8188
```

The ComfyUI URL can also be specified directly when running `run_pipeline.py`:

```bash
python run_pipeline.py \
    --run-name MyLecture \
    --image1 "../inputs/img1.png" \
    --image2 "../inputs/img2.png" \
    --narration "../inputs/lecture.mp3" \
    --comfyui-url "http://127.0.0.1:8188"
```
---

### 7. GPU Requirements

LTX-2.3 is a large video-generation model and requires a GPU with sufficient VRAM.

The development and testing environment for this project used:

* **GPU:** NVIDIA A100-SXM4 40 GB
* **CUDA:** 12.8
* **Python:** 3.10
* **PyTorch:** 2.11.0 + CUDA 12.8

Other NVIDIA GPUs may work, but generation speed and VRAM requirements may vary.

---

### 8. Important Notes

* ComfyUI is **not included** in this repository.
* ComfyUI is a third-party open-source project and remains under its own license.
* The LTX-2.3 model weights are also third-party assets and are not included in this repository.
* Make sure ComfyUI is running before starting the lecture video pipeline.
* If models are added while ComfyUI is running, restart ComfyUI if they do not appear in the model selection menus.

### References

* [ComfyUI](https://github.com/Comfy-Org/ComfyUI)
* [ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo)
* [LTX-2.3 ComfyUI Documentation](https://docs.comfy.org/tutorials/video/ltx/ltx-2-3)
* [LTX-2 Documentation](https://docs.ltx.io/)
