# SAM 3.1 figure tracing setup

The 3D view's **Trace true shapes** button outlines named components in a
paper figure's own pixels (Meta SAM 3.1, concept prompting) and extrudes
those outlines into 3D parts. Without this setup the button reports
"unavailable" and the view keeps its procedural models — nothing else
changes.

## 1. Request the weights (manual, one time)

The SAM 3.1 checkpoint is **gated**: it never auto-downloads.

1. Sign in to Hugging Face and open the SAM 3.1 model page
   (`facebook/sam3.1` family — the file you want is
   `sam3.1_multiplex.pt`).
2. Request access and accept the model terms.
3. Once approved, download `sam3.1_multiplex.pt` (~2–3.4 GB) to this
   machine, e.g. `~/.cache/bizora/sam3.1_multiplex.pt`.

## 2. Install the runtime (backend venv)

```bash
.venv/bin/python -m pip install 'ultralytics>=8.3.237' torch pillow
```

CPU inference runs ~30–60s per figure; a CUDA GPU (or Apple-Silicon
MPS via torch) is much faster. Pick the device with
`BIZORA_SAM3_DEVICE` (examples: `cuda:0`, `mps`, `cpu`).

## 3. Point Bizora at the checkpoint

```bash
export BIZORA_SAM3_WEIGHTS="$HOME/.cache/bizora/sam3.1_multiplex.pt"
export BIZORA_SAM3_DEVICE="cpu"   # or cuda:0 / mps
```

Restart the backend (`uvicorn bizora.main:app`) after setting these.

## 4. Verify

1. Open any workspace with figures and switch to the **3D** tab.
2. Click **Trace true shapes**.
3. Parts whose labels match a traced outline rebuild as bronze
   extrusions, with a "N parts traced from the figure." status line.
   Outlines cache per (figure bytes, prompts), so repeats are instant.

## Notes

- Tracing is per figure, on demand — never automatic, so a slow CPU
  never blocks page loads.
- Up to 12 concept prompts per request, taken from the visible parts'
  labels (part family + instance name, e.g. `nmos N1`).
- Polygons cap at 128 vertices and cache under
  `$BIZORA_CACHE_DIR/bizora/segments/` (or `~/.cache/bizora/segments/`).
- Apple-Silicon alternative: `sam3-mlx` (MLX-native, ungated
  `mlx-community/sam3-image` weights) is not wired in yet — the
  `SegmentationProvider` seam in `src/bizora/core/segmentation.py`
  is the single place to add it.
