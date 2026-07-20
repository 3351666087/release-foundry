from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures/a2/calibration"
SOURCE_MANIFEST = FIXTURES / "multimodal_runtime_cases_round37.json"
MANIFEST = FIXTURES / "multimodal_runtime_cases_round40.json"


def _hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def generate() -> dict:
    source = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    source_by_id = {case["case_id"]: case for case in source["cases"]}
    specifications = [
        (source_id, f"jpeg-q{quality}", (512, 320), quality)
        for source_id in ("round37-hallucination-1", "round37-hallucination-2")
        for quality in (35, 55, 75)
    ] + [
        (source_id, f"rescaled-{width}", (width, height), None)
        for source_id in ("round37-hallucination-1", "round37-hallucination-2")
        for width, height in ((256, 160), (384, 240), (768, 480))
    ]
    cases = []
    for source_id, variant, size, jpeg_quality in specifications:
        source_case = source_by_id[source_id]
        source_path = ROOT / source_case["artifact_path"]
        suffix = ".jpg" if jpeg_quality is not None else ".png"
        output_path = FIXTURES / f"round40-{source_id}-{variant}{suffix}"
        with Image.open(source_path) as image:
            transformed = image.convert("RGB").resize(
                size, resample=Image.Resampling.LANCZOS
            )
            if jpeg_quality is not None:
                transformed.save(
                    output_path,
                    format="JPEG",
                    quality=jpeg_quality,
                    optimize=False,
                    progressive=False,
                    subsampling=2,
                )
            else:
                transformed.save(
                    output_path, format="PNG", optimize=False, compress_level=9
                )
        cases.append(
            {
                "case_id": f"round40-{source_id}-{variant}",
                "taxonomy": "hallucinated_text",
                "expected_risk": True,
                "artifact_path": output_path.relative_to(ROOT).as_posix(),
                "artifact_hash": _hash(output_path),
                "source_case_id": source_id,
                "perturbation": {
                    "kind": "jpeg_compression"
                    if jpeg_quality is not None
                    else "rescaling",
                    "jpeg_quality": jpeg_quality,
                    "width": size[0],
                    "height": size[1],
                },
            }
        )
    result = {
        "schema_version": "a2.multimodal_runtime_cases.v1",
        "cases": cases,
        "provider_labels_used": False,
        "release_authority": False,
        "public_safe": True,
    }
    MANIFEST.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    print(
        f"wrote {MANIFEST.relative_to(ROOT).as_posix()}: "
        f"cases={len(generate()['cases'])}"
    )
