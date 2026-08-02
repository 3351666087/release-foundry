"""Fail-closed Customer Agent Release verification contracts."""

from .contracts import (
    CUSTOMER_AGENT_RELEASE_MANIFEST_SCHEMA,
    CUSTOMER_AGENT_RELEASE_VERIFICATION_SCHEMA,
    verify_customer_agent_release_manifest,
)

__all__ = [
    "CUSTOMER_AGENT_RELEASE_MANIFEST_SCHEMA",
    "CUSTOMER_AGENT_RELEASE_VERIFICATION_SCHEMA",
    "verify_customer_agent_release_manifest",
]
