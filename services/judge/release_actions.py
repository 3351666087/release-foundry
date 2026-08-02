"""Canonical release actions shared by A2 producers and consumers."""

from __future__ import annotations

from typing import Any


CANONICAL_RELEASE_ACTIONS = (
    "allow",
    "staged_rollout",
    "restrict_capability",
    "retest",
    "human_review",
    "block",
)
RELEASE_ACTION_ALIASES = {
    "canary": "staged_rollout",
    "limit_capability": "restrict_capability",
}


class ReleaseActionError(ValueError):
    """Raised when an external release action cannot be normalized safely."""


def normalize_release_action(value: Any) -> str:
    """Return one canonical action while failing closed on unknown values."""
    if not isinstance(value, str):
        raise ReleaseActionError("release_action_must_be_string")
    action = value.strip()
    if action in CANONICAL_RELEASE_ACTIONS:
        return action
    if action in RELEASE_ACTION_ALIASES:
        return RELEASE_ACTION_ALIASES[action]
    raise ReleaseActionError("release_action_not_supported")
