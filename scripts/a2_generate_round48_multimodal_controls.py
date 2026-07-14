from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.a2_generate_round46_multimodal_controls import generate as generate_round46


FIXTURES = ROOT / "fixtures/a2/calibration"
MANIFEST = FIXTURES / "multimodal_runtime_cases_round48.json"


def sha256_ref(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def generate() -> dict:
    cases = [dict(case) for case in generate_round46()["cases"]]
    sources = [
        case for case in cases if case["case_id"].startswith("round45-attack-")
    ]
    plans = (
        [("rotation", 5)] * 3
        + [("rotation", 10)] * 3
        + [("jpeg_compression", 40)] * 3
        + [("jpeg_compression", 60)] * 3
        + [("jpeg_compression", 80)] * 3
    )
    if len(sources) < len(plans):
        raise ValueError("round48 perturbation expansion requires 15 attack sources")

    for index, (source, (kind, value)) in enumerate(zip(sources, plans), start=1):
        source_image = Image.open(ROOT / source["artifact_path"]).convert("RGB")
        if kind == "rotation":
            transformed = source_image.rotate(
                value,
                resample=Image.Resampling.BICUBIC,
                expand=False,
                fillcolor=(32, 32, 32),
            )
            suffix = f"rotation-{value}"
            output = FIXTURES / f"round48-attack-{index:02d}-{suffix}.png"
            transformed.save(output, format="PNG", optimize=False, compress_level=9)
            perturbation = {
                "kind": kind,
                "jpeg_quality": None,
                "rotation_degrees": value,
                "width": transformed.width,
                "height": transformed.height,
            }
        else:
            suffix = f"jpeg-{value}"
            output = FIXTURES / f"round48-attack-{index:02d}-{suffix}.jpg"
            source_image.save(output, format="JPEG", quality=value, optimize=False)
            with Image.open(output) as decoded:
                width, height = decoded.size
            perturbation = {
                "kind": kind,
                "jpeg_quality": value,
                "rotation_degrees": None,
                "width": width,
                "height": height,
            }
        cases.append({
            "case_id": f"round48-attack-{index:02d}-{suffix}",
            "taxonomy": source["taxonomy"],
            "expected_risk": True,
            "artifact_path": output.relative_to(ROOT).as_posix(),
            "artifact_hash": sha256_ref(output),
            "source_case_id": source["case_id"],
            "perturbation": perturbation,
        })

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
    value = generate()
    print(f"wrote {MANIFEST.relative_to(ROOT).as_posix()}: cases={len(value['cases'])}")
