"""Every built-in Activity's progression idempotency key must fit the history limit.

Shape Garden's completion event was once silently dropped because its key was 76
bytes against the 64-byte ``max_idempotency_key_bytes`` limit in
``runtime/history-policy.toml``. This audit statically finds every idempotency
key an Activity builds (keyword ``idempotency_key=`` arguments plus the key
argument of the Activities' ``_emit``/``emit``/``_submit`` wrappers), computes the
worst-case byte length from declared per-expression bounds, and fails for any
key that can exceed the limit or whose interpolated expression has no declared
bound. A new key therefore forces its author to state a bound here.
"""

from __future__ import annotations

import ast
import io
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from greia_platform import activity_api
from greia_platform.event_client import (
    ActivityEventClientError,
    ActivityEventServiceUnavailable,
    EventFailureReporter,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACTIVITIES = PROJECT_ROOT / "activities"
LIMIT = tomllib.loads((PROJECT_ROOT / "runtime" / "history-policy.toml").read_text())[
    "max_idempotency_key_bytes"
]

# Activity-side session ids: "<10-digit epoch>-<up to 4-digit counter>-<6 digits>".
SESSION_CHARS = 10 + 1 + 4 + 1 + 6
UUID_HEX = 32

# Worst-case character counts for interpolated expressions (all keys are ASCII).
BOUNDS: dict[str, int] = {
    "session_id": SESSION_CHARS,
    "self.session_id": SESSION_CHARS,
    "visit_id": UUID_HEX,
    "journey_id": UUID_HEX,
    "delivery_id": UUID_HEX,
    "night_id": UUID_HEX,
    "index": 4,
    "index + 1": 4,
    "maze": 4,
    "star": 4,
    "run": 4,
    "test": 4,
    "checkpoint": 4,
    "self._placed": 4,
    "self._game_serial": 6,
    "self._concerts_heard": 4,
    "len(game.history)": 4,
    "chapter_number": 4,
    "payload.get('course', 0)": 4,
    "payload.get('index', 0)": 4,
    "payload.get('pairs', 0)": 4,
    "payload.get('found', 0)": 4,
    "payload.get('order', 0)": 4,
    "payload.get('round', 0)": 4,
    "char": 1,
    "value": 2,
    "category.value": len("open_closed"),
    "emotion": 24,
    "instrument": len("tambourine"),
    "board_id": len("ramps.3"),
    "crossing_id": 3,
    "figure_id": 9,  # longest constellation id ("cassiopea")
    "fact_id": 30,  # longest Dolphin Journey fact id
    "card.card_id": len("card-") + 10 + 1 + 6,
    "saved_meta['id']": 12,
    "show_id": 12,
    "int(self.play_start_time * 1000)": 13,
    "time.time_ns()": 19,
}
# Per-file bounds for pass-through ``key`` parameters built by the caller.
FILE_BOUNDS: dict[tuple[str, str], int] = {
    # orchestra_app builds f"{session_id}-song{n}"
    ("orchestra_services.py", "key"): SESSION_CHARS + len("-song") + 4,
    # quattro_app has a fixed "<epoch>-<6 digits>" session id and builds
    # "game-<n>-move-<n>" or "match-<sid>-<n>"
    ("quattro_app.py", "self.session_id"): 10 + 1 + 6,
    ("quattro_app.py", "key"): len("match-") + (10 + 1 + 6) + 1 + 6,
}
KEY_CALL_NAMES = {"_emit", "emit", "_submit", "emit_activity_event", "concert_performed"}
KEY_BUILDER_FUNCTIONS = {"composition_event_key", "cake_event_key"}


def _call_name(call: ast.Call) -> str:
    function = call.func
    if isinstance(function, ast.Attribute):
        return function.attr
    return getattr(function, "id", "")


def _key_expressions(tree: ast.AST) -> list[ast.expr]:
    found: list[ast.expr] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node) not in KEY_CALL_NAMES:
            continue
        found.extend(k.value for k in node.keywords if k.arg == "idempotency_key")
        found.extend(a for a in node.args if isinstance(a, ast.JoinedStr))
    return found


def _worst_case(expression: ast.expr, filename: str, builders: dict[str, str]) -> int:
    """Return the worst-case byte length of a key expression, or raise KeyError."""

    if isinstance(expression, ast.JoinedStr):
        total = 0
        for part in expression.values:
            if isinstance(part, ast.Constant):
                total += len(str(part.value).encode("utf-8"))
                continue
            assert isinstance(part, ast.FormattedValue)
            source = ast.unparse(part.value)
            bound = FILE_BOUNDS.get((filename, source), BOUNDS.get(source))
            if bound is None:
                raise KeyError(source)
            total += bound
        return total
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        return len(expression.value.encode("utf-8"))
    if (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Name)
        and expression.func.id in builders
    ):
        namespace: dict[str, object] = {}
        exec(builders[expression.func.id], namespace)  # noqa: S102 - repo-owned source
        return len(str(namespace[expression.func.id]("f" * 64)).encode("utf-8"))
    raise KeyError(ast.unparse(expression))


class ActivityEventKeyBoundsTests(unittest.TestCase):
    def test_every_activity_key_fits_the_history_limit(self) -> None:
        builders: dict[str, str] = {}
        trees: list[tuple[Path, ast.AST]] = []
        for path in sorted(ACTIVITIES.glob("*/*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            trees.append((path, tree))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name in KEY_BUILDER_FUNCTIONS:
                    builders[node.name] = ast.unparse(node)

        checked = 0
        problems: list[str] = []
        for path, tree in trees:
            for expression in _key_expressions(tree):
                if isinstance(expression, ast.Name):
                    continue  # pass-through of a key built (and checked) elsewhere
                label = f"{path.relative_to(PROJECT_ROOT)}:{expression.lineno} {ast.unparse(expression)}"
                try:
                    size = _worst_case(expression, path.name, builders)
                except KeyError as missing:
                    problems.append(f"{label}: no declared bound for {missing}")
                    continue
                checked += 1
                if size > LIMIT:
                    problems.append(f"{label}: worst case {size} bytes > {LIMIT}")
        self.assertGreaterEqual(checked, 80, "key scan found suspiciously few keys")
        self.assertEqual(problems, [])

    def test_bakery_picture_key_is_stable_and_fits(self) -> None:
        from activities.pasticceria_magica.pasticceria_services import cake_event_key

        digest = "ab" * 32
        self.assertEqual(cake_event_key(digest), cake_event_key(digest))
        self.assertNotEqual(cake_event_key(digest), cake_event_key("cd" * 32))
        self.assertLessEqual(len(cake_event_key(digest).encode()), LIMIT)

    def test_default_key_fits_even_for_long_event_ids(self) -> None:
        with patch.object(activity_api, "get_events") as get_events:
            activity_api.emit_activity_event("x" * 120)
            activity_api.emit_activity_event("pet.fed")
        keys = [c.kwargs["idempotency_key"] for c in get_events.return_value.emit.call_args_list]
        self.assertTrue(all(len(key.encode()) <= LIMIT for key in keys))
        self.assertTrue(keys[1].startswith("pet.fed-"))


class EventFailureReporterTests(unittest.TestCase):
    def test_reports_each_distinct_reason_once(self) -> None:
        stream = io.StringIO()
        reporter = EventFailureReporter(stream)
        error = ActivityEventClientError("invalid_event: event was rejected by Greia policy")
        self.assertTrue(reporter.report("garden.done", "k" * 76, error))
        self.assertFalse(reporter.report("garden.done", "k" * 76, error))
        self.assertTrue(reporter.report("other.event", "k", error))
        lines = stream.getvalue().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("garden.done", lines[0])
        self.assertIn("idempotency_key=76 bytes", lines[0])

    def test_unavailable_service_is_not_a_rejection(self) -> None:
        stream = io.StringIO()
        reporter = EventFailureReporter(stream)
        self.assertFalse(
            reporter.report("a.b", "k", ActivityEventServiceUnavailable("not launched"))
        )
        self.assertEqual(stream.getvalue(), "")

    def test_distinct_reasons_are_bounded(self) -> None:
        stream = io.StringIO()
        reporter = EventFailureReporter(stream)
        for index in range(EventFailureReporter.MAX_DISTINCT + 50):
            reporter.report(f"event.{index}", "k", ActivityEventClientError("boom"))
        lines = stream.getvalue().splitlines()
        self.assertEqual(len(lines), EventFailureReporter.MAX_DISTINCT + 1)
        self.assertIn("suppressed", lines[-1])

    def test_emit_activity_event_reports_rejection_and_stays_fail_soft(self) -> None:
        stream = io.StringIO()
        client = patch.object(activity_api, "get_events").start()
        self.addCleanup(patch.stopall)
        client.return_value.emit.side_effect = ActivityEventClientError(
            "invalid_event: event was rejected by Greia policy"
        )
        with patch.object(activity_api, "_EVENT_FAILURES", EventFailureReporter(stream)):
            for _ in range(3):
                result = activity_api.emit_activity_event(
                    "garden.done", idempotency_key="k" * 76
                )
                self.assertIsNone(result)
        self.assertEqual(len(stream.getvalue().splitlines()), 1)
        self.assertIn("garden.done", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
