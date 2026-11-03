"""Regenerate the site's artwork with Muse Image (muse-image-1.0).

Renders the hero and login illustrations from locked art-direction
prompts — warm ivory paper, hand-sketched copper and olive circuit
line art, no text — then crops to 3:2 and writes 1920x1280 JPEGs over
``frontend/public/images/``. Each render also stores its turn id in a
sibling ``.resp.json`` file so a later run can refine it with
``--from-resp-id`` instead of starting over.

Requires ``MUSE_API_KEY`` in the environment (``.env`` is loaded).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

from bizora.providers.muse_image import ImageProviderError, MuseImageProvider

STYLE = (
    "Flat editorial illustration on a warm ivory paper background. "
    "Hand-sketched engineering line art in burnt copper and olive green "
    "with fine charcoal outlines. Clean, minimal, calm. Absolutely no "
    "purple, indigo, blue, or neon gradients; no photorealism; no text, "
    "words, letters, numbers, or logos."
)

PROMPTS = {
    "hero-papers.jpg": (
        f"{STYLE} Three overlapping ivory paper sheets fanned across the "
        "right two-thirds of the frame, each sheet carrying delicate "
        "sketches of circuit traces, chip blocks, and graph nodes "
        "connected by thin lines. The left third is empty warm paper, "
        "calm negative space for a headline. Wide 3:2 landscape composition."
    ),
    "login-layers.jpg": (
        f"{STYLE} A neat cascading stack of ivory paper sheets floating in "
        "the center of the frame, each layer showing chip floorplan and "
        "circuit sketches, soft paper shadows between layers. Centered, "
        "symmetric, calm. Wide 3:2 landscape composition."
    ),
}

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1280
JPEG_QUALITY = 88


def cover_crop(image: Image.Image, width: int, height: int) -> Image.Image:
    """Center-crop to an aspect ratio, then resize to it."""
    target = width / height
    current = image.width / image.height
    if current > target:
        crop = int(image.height * target)
        left = (image.width - crop) // 2
        image = image.crop((left, 0, left + crop, image.height))
    else:
        crop = int(image.width / target)
        top = (image.height - crop) // 2
        image = image.crop((0, top, image.width, top + crop))
    return image.resize((width, height), Image.LANCZOS)


async def render_one(
    provider: MuseImageProvider,
    name: str,
    out_dir: Path,
    *,
    from_resp_id: str | None,
    instruction: str | None,
) -> None:
    prompt = PROMPTS[name]
    if instruction:
        prompt = f"{prompt} Change request: {instruction}"
    print(f"rendering {name} ...", flush=True)
    try:
        result = await provider.generate(prompt, previous_response_id=from_resp_id)
    except ImageProviderError as exc:
        raise SystemExit(f"error: {name}: {exc}") from exc
    with tempfile.NamedTemporaryFile(suffix=".webp", delete=False) as handle:
        handle.write(result.data)
        source_path = handle.name
    try:
        with Image.open(source_path) as webp:
            jpg = cover_crop(webp.convert("RGB"), TARGET_WIDTH, TARGET_HEIGHT)
            target = out_dir / name
            with tempfile.NamedTemporaryFile(dir=out_dir, suffix=".jpg", delete=False) as handle:
                jpg.save(handle, format="JPEG", quality=JPEG_QUALITY)
                staged = handle.name
            os.replace(staged, target)
    finally:
        os.unlink(source_path)
    if result.response_id is not None:
        (out_dir / f"{name}.resp.json").write_text(
            json.dumps({"response_id": result.response_id}) + "\n", encoding="utf-8"
        )
    usage = result.usage
    tokens = (
        f"{usage.input_tokens} in / {usage.output_tokens} out"
        if usage is not None
        else "usage unknown"
    )
    print(f"wrote {target} ({TARGET_WIDTH}x{TARGET_HEIGHT}, {tokens})")


async def main_async(args: argparse.Namespace) -> None:
    out_dir = Path(args.out)
    names = [args.only] if args.only else sorted(PROMPTS)
    if args.dry_run:
        for name in names:
            print(f"--- {name} ---\n{PROMPTS[name]}\n")
        return
    from_resp_id = args.from_resp_id
    if args.refine and not from_resp_id:
        sidecar = out_dir / f"{names[0]}.resp.json"
        if not sidecar.exists():
            raise SystemExit(f"error: no prior turn stored at {sidecar}; render first.")
        from_resp_id = json.loads(sidecar.read_text(encoding="utf-8"))["response_id"]
    try:
        provider = MuseImageProvider()
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from exc
    for name in names:
        await render_one(
            provider, name, out_dir, from_resp_id=from_resp_id, instruction=args.instruction
        )


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="frontend/public/images", help="output directory")
    parser.add_argument("--only", choices=sorted(PROMPTS), help="render one file only")
    parser.add_argument("--dry-run", action="store_true", help="print prompts and exit")
    parser.add_argument(
        "--refine",
        action="store_true",
        help="refine the stored turn for --only instead of rendering fresh",
    )
    parser.add_argument("--from-resp-id", default=None, help="chain from an explicit turn id")
    parser.add_argument("--instruction", default=None, help="change request appended to the prompt")
    args = parser.parse_args(argv)
    if (args.refine or args.from_resp_id) and not args.only:
        parser.error("--refine/--from-resp-id need --only: one turn chains one file.")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
