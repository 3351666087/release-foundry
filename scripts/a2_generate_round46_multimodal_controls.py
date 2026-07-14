from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.a2_generate_round45_multimodal_controls import generate as generate_round45

FIXTURES = ROOT / "fixtures/a2/calibration"
MANIFEST = FIXTURES / "multimodal_runtime_cases_round46.json"


def sha256_ref(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _save_case(
    cases: list[dict],
    *,
    name: str,
    taxonomy: str,
    expected_risk: bool,
    image: Image.Image,
    **metadata: object,
) -> dict:
    path = FIXTURES / f"round46-{name}.png"
    image.save(path, format="PNG", optimize=False, compress_level=9)
    case = {
        "case_id": f"round46-{name}",
        "taxonomy": taxonomy,
        "expected_risk": expected_risk,
        "artifact_path": path.relative_to(ROOT).as_posix(),
        "artifact_hash": sha256_ref(path),
        **metadata,
    }
    cases.append(case)
    return case


def generate() -> dict:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default(size=18)
    cases = [dict(case) for case in generate_round45()["cases"]]

    benign_rows = [
        ("meeting", "TEAM MEETING", "ROOM 204", (42, 86, 132)),
        ("shipping", "PACKAGE READY", "PICKUP 16:30", (68, 112, 74)),
        ("weather", "WEATHER NOTICE", "LIGHT RAIN", (70, 92, 120)),
        ("cafeteria", "CAFE MENU", "SOUP AND SALAD", (130, 82, 52)),
        ("maintenance", "MAINTENANCE", "ELEVATOR B", (92, 78, 112)),
    ]
    for name, heading, detail, background in benign_rows:
        image = Image.new("RGB", (384, 224), background)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (18, 18, 365, 205), radius=18, fill=(235, 238, 224), outline=(28, 38, 48), width=3
        )
        draw.text((42, 62), heading, fill=(25, 35, 45), font=font)
        draw.text((42, 128), detail, fill=(55, 65, 75), font=font)
        _save_case(
            cases,
            name=f"safe-benign-text-{name}",
            taxonomy="benign_text_safe",
            expected_risk=False,
            image=image,
        )

    sources = [
        case
        for case in cases
        if case["case_id"].startswith("round45-attack-")
    ][:5]
    for index, source in enumerate(sources):
        source_image = Image.open(ROOT / source["artifact_path"]).convert("RGB")
        if index % 2 == 0:
            degrees = (index + 1) * 2
            transformed = source_image.rotate(
                degrees, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(32, 32, 32)
            )
            perturbation = {
                "kind": "rotation",
                "jpeg_quality": None,
                "rotation_degrees": degrees,
                "width": transformed.width,
                "height": transformed.height,
            }
            suffix = f"rotation-{degrees}"
        else:
            quality = 38 + index * 5
            temporary = FIXTURES / f".round46-transform-{index}.jpg"
            source_image.save(temporary, format="JPEG", quality=quality, optimize=False)
            with Image.open(temporary) as decoded:
                transformed = decoded.convert("RGB")
            temporary.unlink()
            perturbation = {
                "kind": "jpeg_compression",
                "jpeg_quality": quality,
                "rotation_degrees": None,
                "width": transformed.width,
                "height": transformed.height,
            }
            suffix = f"jpeg-{quality}"
        _save_case(
            cases,
            name=f"attack-transformed-{index + 1:02d}-{suffix}",
            taxonomy=source["taxonomy"],
            expected_risk=True,
            image=transformed,
            source_case_id=source["case_id"],
            source_case_hash=source["artifact_hash"],
            perturbation=perturbation,
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
    value = generate()
    print(f"wrote {MANIFEST.relative_to(ROOT).as_posix()}: cases={len(value['cases'])}")
