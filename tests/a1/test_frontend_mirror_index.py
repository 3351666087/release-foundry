from __future__ import annotations

import json
from pathlib import Path


def test_frontend_mirror_index_is_public_safe_and_actionable():
    root = Path(__file__).resolve().parents[2]
    index = json.loads((root / "docs" / "a1" / "frontend_mirror" / "frontend_mirror_index.json").read_text(encoding="utf-8"))
    schema = json.loads((root / "docs" / "a1" / "frontend_mirror" / "index.schema.json").read_text(encoding="utf-8"))

    for field in schema["required"]:
        assert field in index
    assert index["schema_version"] == "releasefoundry.frontend_mirror_index.v1"
    assert index["raw_files_committed"] is False
    assert index["public_safe_summary"] is True
    assert index["secret_policy"]["tokens_included"] is False
    assert "https://api.releasefoundry.example/testing-platform-api" in index["api_entrypoints"]
    assert "create_request" in index["api_functions"]
    assert "list_requests" in index["api_functions"]
    assert {"audio", "file", "image", "text", "video"}.issubset(set(index["media_terms"]))
    assert "Images" in index["usage_labels"]
    assert "Audio" in index["usage_labels"]
    assert index["important_assets"]
    assert not any("authToken" in json.dumps(asset) for asset in index["important_assets"])
