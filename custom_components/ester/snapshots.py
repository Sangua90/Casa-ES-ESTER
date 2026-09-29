"""Versioned E.S.T.E.R. configuration snapshots and rollback."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from uuid import uuid4

SNAPSHOT_KEYS = (
    "preferences", "classifications", "usage_profiles", "knowledge",
    "context_events", "flexible_loads",
)


def portable_memory(data: dict) -> dict:
    return {key: deepcopy(data.get(key, {} if key in {"preferences", "classifications"} else []))
            for key in SNAPSHOT_KEYS}


def create_snapshot(data: dict, now: datetime, label: str, reason: str) -> dict:
    snapshot = {
        "snapshot_id": str(uuid4()),
        "created_at": now.isoformat(),
        "label": label[:100],
        "reason": reason[:500],
        "memory": portable_memory(data),
    }
    versions = data.setdefault("memory_versions", [])
    versions.append(snapshot)
    del versions[:-50]
    return snapshot


def restore_snapshot(data: dict, snapshot_id: str) -> dict:
    versions = data.setdefault("memory_versions", [])
    snapshot = next((s for s in versions if s.get("snapshot_id") == snapshot_id), None)
    if snapshot is None:
        raise KeyError("unknown_snapshot")
    for key, value in snapshot["memory"].items():
        data[key] = deepcopy(value)
    return snapshot
