"""Phase 3 Kanban card metadata enrichment.

This module is intentionally metadata-only. It calls the Phase 2 compatibility
resolver when a new card is created, then returns fields that are stored beside
the legacy ``assignee``. Dispatch/routing continues to use ``tasks.assignee``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

RESOLVER_DIR = Path("/srv/hermes/data/scripts")
REGISTRY_PATH = Path("/srv/hermes/data/agent_registry.yaml")

V2_METADATA_FIELDS = (
    "canonical_assignee",
    "lane",
    "task_type",
    "mode",
    "tags",
    "provider_hint",
    "model_hint",
    "model_class",
    "reasoning_effort",
    "reasoning_effort_schema",
    "executor_hint",
    "verification",
    "legacy_assignee",
    "resolution_type",
    "confidence",
    "needs_review",
    "resolver_reason",
)


def _load_resolver():
    """Import the runtime resolver from /srv without making it a package dep."""
    resolver_dir = str(RESOLVER_DIR)
    if resolver_dir not in sys.path:
        sys.path.insert(0, resolver_dir)
    from agent_registry_resolver import resolve_assignee  # type: ignore

    return resolve_assignee


def enrich_card_metadata(
    *,
    assignee: Optional[str],
    title: str,
    body: Optional[str] = None,
    task_type: Optional[str] = None,
    lane: Optional[str] = None,
    tags: Optional[Iterable[str]] = None,
    mode: Optional[str] = None,
) -> dict[str, Any]:
    """Return v2 metadata for a new Kanban card.

    ``assignee`` is never changed by this helper. Unknown or ambiguous labels
    keep the legacy assignee in the caller's row and return ``needs_review``
    instead of fabricating canonical routing.
    """
    overrides: dict[str, Any] = {}
    if task_type is not None:
        overrides["task_type"] = task_type
    if lane is not None:
        overrides["lane"] = lane
    if mode is not None:
        overrides["mode"] = mode
    if tags is not None:
        overrides["tags"] = [str(tag) for tag in tags if str(tag).strip()]

    resolve_assignee = _load_resolver()
    result = resolve_assignee(
        assignee,
        registry_path=REGISTRY_PATH,
        title=title or "",
        body=body or "",
        overrides=overrides or None,
    )

    canonical = result.get("canonical_assignee")
    legacy = assignee if assignee and assignee != canonical else None

    return {
        "canonical_assignee": canonical,
        "lane": result.get("lane"),
        "task_type": result.get("task_type"),
        "mode": result.get("mode"),
        "tags": list(result.get("tags") or []),
        "provider_hint": result.get("provider_hint"),
        "model_hint": result.get("model_hint"),
        "model_class": result.get("model_class"),
        "reasoning_effort": result.get("reasoning_effort"),
        "reasoning_effort_schema": result.get("reasoning_effort_schema"),
        "executor_hint": result.get("executor_hint"),
        "verification": result.get("verification"),
        "legacy_assignee": legacy,
        "resolution_type": result.get("resolution_type"),
        "confidence": result.get("confidence"),
        "needs_review": bool(result.get("needs_review")),
        "resolver_reason": result.get("reason"),
    }


def empty_metadata(reason: str) -> dict[str, Any]:
    """Fallback metadata if enrichment itself fails.

    Creation should remain backward-compatible even if the resolver file is
    missing or temporarily broken; the card is marked for review instead.
    """
    return {
        "canonical_assignee": None,
        "lane": None,
        "task_type": None,
        "mode": None,
        "tags": [],
        "provider_hint": None,
        "model_hint": None,
        "model_class": None,
        "reasoning_effort": None,
        "reasoning_effort_schema": None,
        "executor_hint": None,
        "verification": None,
        "legacy_assignee": None,
        "resolution_type": "unmappable",
        "confidence": 0.0,
        "needs_review": True,
        "resolver_reason": reason,
    }
