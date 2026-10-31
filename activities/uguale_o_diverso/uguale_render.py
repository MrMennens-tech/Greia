"""Frame composition for Same or Different (blits only).

``RoundMotion`` holds the short-lived presentation state (cards dealing in,
wrong-tap wiggles, glow halos, the reference's attention pulse, FX);
``MomoCast`` wraps the shared ``CastFeedback`` with Momo's point pose;
``UgualeRenderer`` draws a round from the model plus that motion state. Every
surface comes prepared from ``UgualeArt`` -- the only per-frame work is
choosing which cached surface to blit where.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
import math

import pygame

from greia_platform.activity_feedback import CastFeedback, CastPose

if __package__:
    from .uguale_art import UgualeArt
    from .uguale_content import Twist
    from .uguale_layout import MOMO_HEIGHT, MOMO_MIDBOTTOM, RoundLayout
    from .uguale_model import Round
else:
    from uguale_art import UgualeArt
    from uguale_content import Twist
    from uguale_layout import MOMO_HEIGHT, MOMO_MIDBOTTOM, RoundLayout
    from uguale_model import Round

WOBBLE_SECONDS = 0.5
PULSE_SECONDS = 1.3
DEAL_STAGGER = 0.06
FX_SECONDS = 0.6
MAX_FX = 12
TABLE = (255, 251, 235, 120)


@dataclass(slots=True)
class RoundMotion:
    """Presentation-only timers for the current round (bounded, cleared per round)."""

    deal_start: float = -10.0
    wobbles: dict[int, float] = field(default_factory=dict)
    halos: dict[int, tuple[float, float]] = field(default_factory=dict)
    pulse: tuple[float, float] | None = None
    fx: deque = field(default_factory=lambda: deque(maxlen=MAX_FX))

    def clear(self) -> None:
        self.deal_start = -10.0
        self.wobbles.clear()
        self.halos.clear()
        self.pulse = None
        self.fx.clear()

    def add_fx(self, name: str, position: tuple[int, int], start: float) -> None:
        self.fx.append((name, position, start))

    def active(self, now: float, card_count: int) -> bool:
        if now - self.deal_start < DEAL_STAGGER * card_count + 0.3:
            return True
        if any(now - start < WOBBLE_SECONDS for start in self.wobbles.values()):
            return True
        if any(start <= now + 0.05 and now < end for start, end in self.halos.values()):
            return True
        if self.pulse is not None and now < self.pulse[1]:
            return True
        return any(now - start < FX_SECONDS for _, _, start in self.fx)

    def prune(self, now: float) -> None:
        for index in [i for i, start in self.wobbles.items() if now - start >= WOBBLE_SECONDS]:
            del self.wobbles[index]
        for index in [i for i, (_, end) in self.halos.items() if now >= end]:
            del self.halos[index]
        if self.pulse is not None and now >= self.pulse[1]:
            self.pulse = None
        while self.fx and now - self.fx[0][2] >= FX_SECONDS:
            self.fx.popleft()


class MomoCast:
    """Momo: shared cheer/think feedback plus a point pose for the hints."""

    def __init__(self, feedback: CastFeedback, art: UgualeArt, clock: Callable[[], float]) -> None:
        self.feedback = feedback
        self._clock = clock
        self._point = art.cast_pose("pose_point", MOMO_HEIGHT)
        self._loader = art.loader
        self._point_until = 0.0

    @property
    def pose(self) -> CastPose:
        return self.feedback.pose

    @property
    def pointing(self) -> bool:
        return self._clock() < self._point_until and self.feedback.pose is CastPose.IDLE

    @property
    def animating(self) -> bool:
        return self.feedback.animating or self.pointing

    def correct(self) -> None:
        self._point_until = 0.0
        self.feedback.correct()

    def try_again(self) -> None:
        self._point_until = 0.0
        self.feedback.try_again()

    def point(self, seconds: float) -> None:
        self.feedback.reset()
        self._point_until = self._clock() + seconds

    def reset(self) -> None:
        self._point_until = 0.0
        self.feedback.reset()

    def update(self) -> bool:
        changed = self.feedback.update()
        if self._point_until and self._clock() >= self._point_until:
            self._point_until = 0.0
            changed = True
        return changed

    def draw(self, surface: pygame.Surface) -> None:
        if self.pointing and self._point is not None:
            bob = int(math.sin((self._point_until - self._clock()) * 7.0) * 3)
            surface.blit(
                self._loader.presentable(self._point, surface),
                self._point.get_rect(midbottom=(MOMO_MIDBOTTOM[0], MOMO_MIDBOTTOM[1] + bob)),
            )
            return
        self.feedback.draw(surface, MOMO_MIDBOTTOM)


class UgualeRenderer:
    """Compose the play screen from prepared art."""

    def __init__(self, art: UgualeArt, cast: MomoCast, clock: Callable[[], float]) -> None:
        self._art = art
        self._cast = cast
        self._clock = clock
        self._backdrop_key: tuple | None = None
        self._backdrop: pygame.Surface | None = None

    def draw_round(
        self,
        surface: pygame.Surface,
        current: Round,
        twist: Twist,
        layout: RoundLayout,
        motion: RoundMotion,
    ) -> None:
        now = self._clock()
        surface.blit(self._table(layout), (0, 0))
        ref = layout.reference
        reference = self._art.reference(ref.width, current.reference, twist)
        bounce = 0
        if motion.pulse is not None and now < motion.pulse[1]:
            bounce = int(abs(math.sin((now - motion.pulse[0]) * 7.0)) * 12 * max(0.0, (motion.pulse[1] - now) / PULSE_SECONDS))
        surface.blit(reference, (ref.x, ref.y - bounce))
        for index, (halo_start, halo_end) in motion.halos.items():
            if halo_start <= now < halo_end and index < len(layout.cards):
                rect = layout.cards[index]
                surface.blit(self._art.halo(rect.size), (rect.x - 14, rect.y - 14))
        for index, face in enumerate(current.choices):
            if index < len(layout.cards):
                self._draw_card(surface, index, face, twist, layout, motion, now)
        for name, position, start in motion.fx:
            elapsed = now - start
            frames = self._art.fx_frames(name)
            if 0 <= elapsed < FX_SECONDS and frames:
                frame = frames[min(len(frames) - 1, int(elapsed / FX_SECONDS * len(frames)))]
                surface.blit(frame, frame.get_rect(center=position))
        self._cast.draw(surface)

    def draw_blank(self, surface: pygame.Surface) -> None:
        surface.blit(self._art.background(), (0, 0))
        self._cast.draw(surface)

    def _table(self, layout: RoundLayout) -> pygame.Surface:
        """Playroom scene + a soft cream table behind the row, composed once per layout."""

        key = tuple(layout.cards)
        if self._backdrop is None or key != self._backdrop_key:
            base = self._art.background().copy()
            area = layout.cards[0].unionall(layout.cards[1:]).inflate(32, 36)
            area.clamp_ip(base.get_rect().inflate(-8, -8))
            table = pygame.Surface(area.size, pygame.SRCALPHA)
            pygame.draw.rect(table, TABLE, table.get_rect(), border_radius=34)
            base.blit(table, area.topleft)
            self._backdrop = base
            self._backdrop_key = key
        return self._backdrop

    def _draw_card(
        self,
        surface: pygame.Surface,
        index: int,
        face,
        twist: Twist,
        layout: RoundLayout,
        motion: RoundMotion,
        now: float,
    ) -> None:
        rect = layout.cards[index]
        if now < motion.deal_start + DEAL_STAGGER * index:
            return
        x = rect.x
        wobble = motion.wobbles.get(index)
        if wobble is not None and now - wobble < WOBBLE_SECONDS:
            elapsed = now - wobble
            x += int(8 * (1 - elapsed / WOBBLE_SECONDS) * math.sin(elapsed * 42))
        surface.blit(self._art.card(rect.size, face, twist), (x, rect.y))


__all__ = ["MomoCast", "RoundMotion", "UgualeRenderer"]
