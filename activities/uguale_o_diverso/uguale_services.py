"""Greia persistence and event adapters for Same or Different.

Progress is one small profile-scoped record: the current ladder rung and a
short history of recent visits (rounds and misses), which ``adapt_level``
reads. The events are the milestone and completion facts the manifest
declares; their idempotency keys stay far below 64 bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence

from greia_platform.activity_api import emit_activity_event, get_storage

if __package__:
    from .uguale_content import MAX_LEVEL, ROUNDS_PER_VISIT, STORAGE_KEY
    from .uguale_model import HISTORY_LIMIT, VisitResult
else:
    from uguale_content import MAX_LEVEL, ROUNDS_PER_VISIT, STORAGE_KEY
    from uguale_model import HISTORY_LIMIT, VisitResult

SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class UgualeProgress:
    level: int = 0
    history: tuple[VisitResult, ...] = field(default_factory=tuple)


class ProgressPort(Protocol):
    def load(self) -> UgualeProgress: ...
    def save(self, level: int, history: Sequence[VisitResult]) -> None: ...


class EventPort(Protocol):
    def round_solved(self, session_id: str, payload: dict[str, Any]) -> None: ...
    def visit_completed(self, session_id: str, payload: dict[str, Any]) -> None: ...


def _int(value: object, default: int, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return max(low, min(high, value))


class GreiaUgualeProgress:
    """Map bounded progress onto profile-scoped Greia Storage."""

    def __init__(self, storage=None) -> None:
        if storage is None:
            try:
                storage = get_storage()
            except Exception:
                storage = None
        self._storage = storage

    def load(self) -> UgualeProgress:
        if self._storage is None:
            return UgualeProgress()
        try:
            raw = self._storage.kv_get(STORAGE_KEY)
        except Exception:
            return UgualeProgress()
        if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
            return UgualeProgress()
        history: list[VisitResult] = []
        items = raw.get("history")
        if isinstance(items, list):
            for item in items[-HISTORY_LIMIT:]:
                if not isinstance(item, dict):
                    continue
                rounds = _int(item.get("rounds"), -1, -1, 99)
                if rounds < 1:
                    continue
                history.append(
                    VisitResult(
                        _int(item.get("level"), 0, 0, MAX_LEVEL),
                        min(rounds, ROUNDS_PER_VISIT * 4),
                        _int(item.get("misses"), 0, 0, 999),
                    )
                )
        return UgualeProgress(_int(raw.get("level"), 0, 0, MAX_LEVEL), tuple(history))

    def save(self, level: int, history: Sequence[VisitResult]) -> None:
        if self._storage is None:
            return
        payload = {
            "schema_version": SCHEMA_VERSION,
            "level": max(0, min(MAX_LEVEL, int(level))),
            "history": [
                {"level": item.level, "rounds": item.rounds, "misses": item.misses}
                for item in tuple(history)[-HISTORY_LIMIT:]
            ],
        }
        try:
            self._storage.kv_set(STORAGE_KEY, payload)
        except Exception:
            return


class GreiaUgualeEvents:
    """Publish the milestone and completion facts declared by the manifest."""

    def round_solved(self, session_id: str, payload: dict[str, Any]) -> None:
        try:
            emit_activity_event(
                "uguale.round_solved",
                payload,
                idempotency_key=f"uguale:{session_id}:r{payload.get('round', 0)}",
            )
        except Exception:
            return

    def visit_completed(self, session_id: str, payload: dict[str, Any]) -> None:
        try:
            emit_activity_event(
                "uguale.visit_completed",
                payload,
                idempotency_key=f"uguale:{session_id}",
            )
        except Exception:
            return


__all__ = [
    "EventPort",
    "GreiaUgualeEvents",
    "GreiaUgualeProgress",
    "ProgressPort",
    "SCHEMA_VERSION",
    "UgualeProgress",
]
