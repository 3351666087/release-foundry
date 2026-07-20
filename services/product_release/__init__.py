"""Fail-closed contracts for releasing the Ashr product itself.

This package deliberately does not implement the customer-agent release gate.
Customer-agent releases consume a verified ``product_release_id`` and manifest
digest produced by this package.
"""

from .contracts import (
    PRODUCT_RELEASE_MANIFEST_SCHEMA,
    PRODUCT_RELEASE_VERIFICATION_SCHEMA,
    VERIFICATION_RECEIPT_SCHEMA,
    verify_product_release_manifest,
)
from .web_surface import (
    WEB_SURFACE_POLICY_ID,
    WEB_SURFACE_RECEIPT_ID,
    WEB_SURFACE_VERIFICATION_SCHEMA,
    verify_web_production_surface,
)

__all__ = [
    "PRODUCT_RELEASE_MANIFEST_SCHEMA",
    "PRODUCT_RELEASE_VERIFICATION_SCHEMA",
    "VERIFICATION_RECEIPT_SCHEMA",
    "WEB_SURFACE_POLICY_ID",
    "WEB_SURFACE_RECEIPT_ID",
    "WEB_SURFACE_VERIFICATION_SCHEMA",
    "verify_product_release_manifest",
    "verify_web_production_surface",
]
