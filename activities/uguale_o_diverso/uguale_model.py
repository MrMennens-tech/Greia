"""Same or Different rules: rounds, one visit and the ladder adaptation.

Pure Python (no Pygame). A ``Face`` is one picture as the child sees it
(which picture, which of the three sizes, mirrored, as a shadow). A ``Round``
has one reference face and the choices, exactly one of which looks the same
(same picture in the same size, not mirrored; a shadow reference asks for its
normal picture). Distractors are near misses (the mirror image, another size)
or other pictures, and a choice that would also be right is never offered.
Nothing can fail a child: a wrong tap is counted and the round continues.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
import random

if __package__:
    from .uguale_content import LEVELS, MAX_LEVEL, PICTURES, ROUNDS_PER_VISIT, Picture, Twist
else:
    from uguale_content import LEVELS, MAX_LEVEL, PICTURES, ROUNDS_PER_VISIT, Picture, Twist

HISTORY_LIMIT = 6
NORMAL_SIZE = 1  # index into SIZE_STEPS


@dataclass(frozen=True, slots=True)
class Face:
    picture_id: str
    size: int = NORMAL_SIZE
    mirrored: bool = False
    shadow: bool = False


@dataclass(frozen=True, slots=True)
class Round:
    reference: Face
    choices: tuple[Face, ...]
    answer: int  # index into ``choices``


class TapResult(StrEnum):
    IGNORED = "ignored"
    CORRECT = "correct"
    WRONG = "wrong"


def looks_the_same(reference: Face, choice: Face) -> bool:
    """A shadow reference is satisfied by the normal picture of its shape."""

    return (
        reference.picture_id == choice.picture_id
        and reference.size == choice.size
        and reference.mirrored == choice.mirrored
        and not choice.shadow
    )


class RoundBuilder:
    """Draw rounds for one rung; ``asymmetric`` says whether a mirror image differs."""

    def __init__(
        self,
        level: int,
        rng: random.Random,
        asymmetric: Callable[[Picture], bool] = lambda picture: True,
        pool: Sequence[Picture] = PICTURES,
    ) -> None:
        self.spec = LEVELS[max(0, min(MAX_LEVEL, level))]
        self._rng = rng
        self._asymmetric = asymmetric
        self._pool = tuple(pool)

    def build(self, previous: str | None = None) -> Round:
        twist = self.spec.twist
        count = self.spec.choices
        rng = self._rng
        candidates = [p for p in self._pool if p.picture_id != previous] or list(self._pool)
        if twist in (Twist.MIRROR, Twist.SHADOW_MIRROR):
            lopsided = [p for p in candidates if self._asymmetric(p)]
            candidates = lopsided or candidates
        target = rng.choice(candidates)
        others = [p for p in self._pool if p.picture_id != target.picture_id]

        if twist is Twist.SIZE:
            size = rng.randrange(3)
            choices = [Face(target.picture_id, size=step) for step in range(3)]
            reference = Face(target.picture_id, size=size)
        else:
            reference = Face(target.picture_id, shadow=twist in (Twist.SHADOW, Twist.SHADOW_MIRROR))
            choices = [Face(target.picture_id)]
            extra = count - 1
            if twist in (Twist.MIRROR, Twist.SHADOW_MIRROR) and self._asymmetric(target):
                choices.append(Face(target.picture_id, mirrored=True))
                extra -= 1
            for picture in rng.sample(others, extra):
                mirrored = twist in (Twist.MIRROR, Twist.SHADOW_MIRROR) and rng.random() < 0.4
                choices.append(Face(picture.picture_id, mirrored=mirrored))
        rng.shuffle(choices)
        answer = next(index for index, face in enumerate(choices) if looks_the_same(reference, face))
        assert sum(looks_the_same(reference, face) for face in choices) == 1
        return Round(reference, tuple(choices), answer)


class Visit:
    """One visit: a few rounds, a miss counter, and the tap rule."""

    def __init__(self, builder: RoundBuilder, rounds: int = ROUNDS_PER_VISIT) -> None:
        self._builder = builder
        self.total = rounds
        self.done = 0
        self.misses = 0
        self.round_misses = 0
        self.round: Round | None = None
        self._last: str | None = None

    @property
    def complete(self) -> bool:
        return self.done >= self.total

    def start_round(self) -> Round:
        self.round = self._builder.build(self._last)
        self._last = self.round.reference.picture_id
        self.round_misses = 0
        return self.round

    def tap(self, index: int) -> TapResult:
        current = self.round
        if current is None or not 0 <= index < len(current.choices):
            return TapResult.IGNORED
        if index == current.answer:
            self.done += 1
            self.round = None
            return TapResult.CORRECT
        self.misses += 1
        self.round_misses += 1
        return TapResult.WRONG


@dataclass(frozen=True, slots=True)
class VisitResult:
    level: int
    rounds: int
    misses: int


def adapt_level(level: int, history: Sequence[VisitResult]) -> int:
    """Two tidy visits at a rung move up; one visit full of misses moves down."""

    level = max(0, min(MAX_LEVEL, level))
    recent = [item for item in history if item.level == level][-2:]
    if history and history[-1].level == level and history[-1].misses >= history[-1].rounds:
        return max(0, level - 1)
    if len(recent) == 2 and all(item.misses <= max(1, item.rounds // 3) for item in recent):
        return min(MAX_LEVEL, level + 1)
    return level


__all__ = [
    "Face",
    "HISTORY_LIMIT",
    "NORMAL_SIZE",
    "Round",
    "RoundBuilder",
    "TapResult",
    "Visit",
    "VisitResult",
    "adapt_level",
    "looks_the_same",
]
