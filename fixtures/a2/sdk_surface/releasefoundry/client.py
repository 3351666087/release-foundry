from __future__ import annotations

from typing import Any


class ReleaseFoundryLabsClient:
    """Static compatibility surface used by the committed evidence audit."""

    @classmethod
    def from_env(cls, timeout: int = 30) -> ReleaseFoundryLabsClient:
        raise RuntimeError(
            "The committed SDK surface fixture cannot perform network requests."
        )

    def init(self) -> dict[str, Any]:
        raise RuntimeError(
            "The committed SDK surface fixture cannot perform network requests."
        )

    def create_request(
        self,
        request_name: str,
        request: dict[str, Any],
        request_input_schema: dict[str, Any],
        tenant_id: int,
        requestor_id: int,
    ) -> dict[str, Any]:
        return {
            "request_name": request_name,
            "request": request,
            "request_input_schema": request_input_schema,
            "tenant_id": tenant_id,
            "requestor_id": requestor_id,
            "accepted_inputs": [],
            "generation_options": {},
        }
