"""Figure segmentation seam: component outlines for true-to-paper 3D.

A segmentation backend (Meta SAM 3.1 via the bundled adapter) traces
the drawn outline of named components in a figure's own pixels. The
3D view extrudes those outlines instead of generic procedural
stand-ins, so parts look like the paper drew them. Segmentation runs
on demand per (figure, prompts) and caches to disk; when no backend
is configured the API says so honestly and the UI keeps its
procedural models.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Protocol

from bizora.contracts.figures import FigureSegment

logger = logging.getLogger(__name__)

#: Bumped when the segmentation contract or cache layout changes.
SEGMENTATION_VERSION = 1

#: Prompt budget per request: SAM concept prompting degrades past a
#: handful of concepts, and each figure needs only its visible parts.
MAX_PROMPTS = 12

#: Long prompts are truncated, never rejected: the cache key uses the
#: truncated form so repeats hit.
MAX_PROMPT_CHARS = 64

#: Polygon vertices per segment: stride-sampled down to this cap so
#: responses stay small and extrusion stays cheap.
MAX_POLYGON_POINTS = 128

#: Weights path plus overrides. The checkpoint is gated on Hugging
#: Face and never auto-downloads; see docs/SAM_SETUP.md.
WEIGHTS_ENV_VAR = "BIZORA_SAM3_WEIGHTS"
DEVICE_ENV_VAR = "BIZORA_SAM3_DEVICE"


class SegmentationError(Exception):
    """Raised when segmentation runs but cannot produce outlines."""


class SegmentationUnavailableError(SegmentationError):
    """Raised when no segmentation backend is configured."""


class SegmentationProvider(Protocol):
    """A backend that outlines named components in figure pixels."""

    name: str

    def available(self) -> tuple[bool, str | None]:
        """Return (True, None) when ready, else (False, setup reason)."""
        ...

    def segment(
        self, image_bytes: bytes, prompts: tuple[str, ...]
    ) -> tuple[FigureSegment, ...]:
        """Outline each prompt's best component; may raise SegmentationError."""
        ...


def segmentation_cache_dir() -> Path:
    """Return the segments cache directory, honoring test overrides."""
    override = os.environ.get("BIZORA_CACHE_DIR")
    if override:
        return Path(override) / "bizora" / "segments"
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "bizora" / "segments"


def clean_prompts(prompts: tuple[str, ...]) -> tuple[str, ...]:
    """Trim, truncate, dedupe, and cap one request's concept prompts."""
    cleaned: list[str] = []
    for prompt in prompts:
        text = " ".join(prompt.split())[:MAX_PROMPT_CHARS]
        if text and text not in cleaned:
            cleaned.append(text)
        if len(cleaned) >= MAX_PROMPTS:
            break
    return tuple(cleaned)


def segment_cache_key(image_sha256: str, prompts: tuple[str, ...]) -> str:
    """Build a stable cache key for one (figure bytes, prompts) request."""
    digest = hashlib.sha256("\n".join(prompts).encode("utf-8")).hexdigest()[:16]
    safe_sha = re.sub(r"[^0-9a-f]", "", image_sha256.lower())[:64] or "unknown"
    return f"{safe_sha}-seg-{digest}-v{SEGMENTATION_VERSION}"


def load_cached_segments(key: str) -> tuple[FigureSegment, ...] | None:
    """Return cached segments for key, or None on any miss or mismatch."""
    path = segmentation_cache_dir() / f"{key}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("version") != SEGMENTATION_VERSION
        ):
            return None
        raw = payload.get("segments")
        if not isinstance(raw, list):
            return None
        return tuple(FigureSegment.model_validate(item) for item in raw)
    except (OSError, ValueError):
        return None


def save_cached_segments(
    key: str, segments: tuple[FigureSegment, ...]
) -> None:
    """Persist segments for key; cache failures never fail the request."""
    try:
        directory = segmentation_cache_dir()
        directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": SEGMENTATION_VERSION,
            "segments": [segment.model_dump(mode="json") for segment in segments],
        }
        (directory / f"{key}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("segment cache write failed: %s", exc)


def simplify_polygon(
    points: list[tuple[float, float]], limit: int = MAX_POLYGON_POINTS
) -> list[tuple[float, float]]:
    """Stride-sample a polygon ring down to at most limit vertices."""
    if len(points) <= limit:
        return points
    stride = len(points) / limit
    picked = [points[int(round(i * stride))] for i in range(limit)]
    # Stride rounding can repeat the closing vertex; keep ring order.
    deduped = list(dict.fromkeys(picked))
    if len(deduped) < 3:
        return points[:3]
    return deduped


class Sam3SegmentationProvider:
    """Meta SAM 3.1 concept segmentation via the ultralytics adapter.

    Prompts are concept names ("nmos transistor", "capacitor"); SAM
    returns one mask per concept, converted here to normalized
    polygons. The ultralytics package and the gated checkpoint load
    lazily, so importing this module never requires either: without
    them the provider simply reports unavailable.
    """

    name = "sam3"

    def __init__(
        self,
        weights_path: str | None = None,
        device: str | None = None,
    ) -> None:
        self._weights_path = weights_path or os.environ.get(WEIGHTS_ENV_VAR)
        self._device = device or os.environ.get(DEVICE_ENV_VAR)
        self._model: Any = None
        self._unavailable_reason: str | None = None

    def available(self) -> tuple[bool, str | None]:
        try:
            import ultralytics  # type: ignore[import-not-found] # noqa: F401
        except ImportError:
            return False, (
                "The ultralytics package is not installed "
                "(pip install 'ultralytics>=8.3.237'). See docs/SAM_SETUP.md."
            )
        if not self._weights_path:
            return False, (
                f"Set {WEIGHTS_ENV_VAR} to a downloaded SAM 3.1 checkpoint "
                "(sam3.1_multiplex.pt). The weights are gated on Hugging "
                "Face and never auto-download. See docs/SAM_SETUP.md."
            )
        if not Path(self._weights_path).exists():
            return False, (
                f"SAM 3.1 checkpoint not found at {self._weights_path}. "
                "See docs/SAM_SETUP.md."
            )
        if self._unavailable_reason is not None:
            return False, self._unavailable_reason
        return True, None

    def segment(
        self, image_bytes: bytes, prompts: tuple[str, ...]
    ) -> tuple[FigureSegment, ...]:
        ok, reason = self.available()
        if not ok:
            raise SegmentationUnavailableError(reason or "SAM 3.1 unavailable.")
        started = time.monotonic()
        try:
            from PIL import Image
        except ImportError as exc:
            raise SegmentationError(
                "Pillow is required to decode figure images."
            ) from exc
        try:
            from ultralytics import SAM
        except ImportError as exc:  # pragma: no cover - checked above
            raise SegmentationUnavailableError(
                "The ultralytics package is not installed."
            ) from exc
        try:
            from io import BytesIO

            with Image.open(BytesIO(image_bytes)) as image:
                width, height = image.size
                pixels = image.convert("RGB")
        except Exception as exc:
            raise SegmentationError(
                f"Figure bytes are not a decodable image: {exc}"
            ) from exc
        if width < 1 or height < 1:
            raise SegmentationError("Figure image has no pixels.")
        try:
            if self._model is None:
                self._model = SAM(self._weights_path)
            results = self._model.predict(
                pixels, texts=list(prompts), device=self._device
            )
        except Exception as exc:
            self._unavailable_reason = str(exc)
            raise SegmentationError(f"SAM 3.1 inference failed: {exc}") from exc
        segments = _segments_from_results(
            results, prompts, width=width, height=height
        )
        elapsed_ms = (time.monotonic() - started) * 1000
        logger.info(
            "sam3 segmented %d prompts into %d outlines in %.0fms",
            len(prompts),
            len(segments),
            elapsed_ms,
        )
        return segments


def _segments_from_results(
    results: object,
    prompts: tuple[str, ...],
    *,
    width: int,
    height: int,
) -> tuple[FigureSegment, ...]:
    """Convert ultralytics SAM results to normalized figure segments.

    Prefers mask polygons (masks.xy); when a result carries only a
    box, the box rectangle becomes the polygon so the outline still
    matches the paper's placement. Results that carry neither are
    skipped, never fabricated.
    """
    items = results if isinstance(results, list) else [results]
    segments: list[FigureSegment] = []
    for index, result in enumerate(items):
        label = prompts[index] if index < len(prompts) else f"part-{index + 1}"
        masks = getattr(result, "masks", None)
        boxes = getattr(result, "boxes", None)
        polygons: list[list[tuple[float, float]]] = []
        if masks is not None:
            raw_polygons = getattr(masks, "xy", None) or []
            for raw in raw_polygons:
                points = [
                    (float(px) / width, float(py) / height)
                    for px, py in raw
                    if width > 0 and height > 0
                ]
                points = [
                    (min(max(px, 0.0), 1.0), min(max(py, 0.0), 1.0))
                    for px, py in points
                ]
                if len(points) >= 3:
                    polygons.append(simplify_polygon(points))
        score: float | None = None
        box: tuple[float, float, float, float] | None = None
        if boxes is not None:
            raw_boxes = getattr(boxes, "xyxy", None) or []
            raw_conf = getattr(boxes, "conf", None) or []
            if len(raw_boxes) > 0:
                x1, y1, x2, y2 = (float(v) for v in raw_boxes[0])
                box = (
                    min(max(x1 / width, 0.0), 1.0),
                    min(max(y1 / height, 0.0), 1.0),
                    min(max((x2 - x1) / width, 0.0), 1.0),
                    min(max((y2 - y1) / height, 0.0), 1.0),
                )
            if len(raw_conf) > 0:
                try:
                    score = min(max(float(raw_conf[0]), 0.0), 1.0)
                except (TypeError, ValueError):
                    score = None
        if not polygons and box is not None:
            x, y, w, h = box
            if w > 0 and h > 0:
                polygons.append([(x, y), (x + w, y), (x + w, y + h), (x, y + h)])
        if not polygons:
            continue
        for part_index, polygon in enumerate(polygons):
            xs = [px for px, _ in polygon]
            ys = [py for _, py in polygon]
            derived = (
                min(xs),
                min(ys),
                max(xs) - min(xs),
                max(ys) - min(ys),
            )
            final_box = box if box is not None else derived
            if final_box[2] <= 0 or final_box[3] <= 0:
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "part"
            segments.append(
                FigureSegment(
                    segment_id=f"{slug}-{index + 1}-{part_index + 1}"[:128],
                    label=label[:256],
                    bbox=final_box,
                    polygon=tuple(polygon),
                    score=score,
                )
            )
    return tuple(segments)
