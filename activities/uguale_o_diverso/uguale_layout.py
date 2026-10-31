"""Geometry for Same or Different in 1024x600 logical pixels.

Momo stands on the lawn at the bottom left. The reference picture sits in a
dashed frame at the top centre of the play area and the choice cards form one
row beneath it (three or five cards). Every zone is derived from the platform
protected Home/Back rectangle (mapped into logical space by
``ControlLayout.for_canvas``), so nothing enters it at any resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pygame

if __package__:
    from .uguale_content import REFERENCE_HEIGHT, REFERENCE_WIDTH
else:
    from uguale_content import REFERENCE_HEIGHT, REFERENCE_WIDTH

MARGIN: Final = 12
MOMO_HEIGHT: Final = 210
MOMO_MIDBOTTOM: Final[tuple[int, int]] = (106, REFERENCE_HEIGHT - 6)
AREA_LEFT: Final = 214
DOTS_HEIGHT: Final = 40
CARD_MAX: Final = 178
GAP: Final = 16


@dataclass(frozen=True, slots=True)
class RoundLayout:
    reference: pygame.Rect
    cards: tuple[pygame.Rect, ...]
    dots: pygame.Rect
    area: pygame.Rect

    @classmethod
    def build(cls, choices: int, protected: pygame.Rect) -> "RoundLayout":
        top = max(70, protected.bottom + 8) if protected.right > AREA_LEFT else 70
        area = pygame.Rect(AREA_LEFT, top, REFERENCE_WIDTH - MARGIN - AREA_LEFT, REFERENCE_HEIGHT - 12 - top)
        card = int(min(CARD_MAX, (area.width - (choices - 1) * GAP) / choices))
        card_h = int(card * 1.08)
        ref = int(min(area.height - card_h - 3 * GAP, 190))
        total = ref + GAP * 2 + card_h
        y0 = area.top + max(0, (area.height - total) // 2)
        reference = pygame.Rect(area.centerx - ref // 2, y0, ref, ref)
        row_w = choices * card + (choices - 1) * GAP
        left = area.centerx - row_w // 2
        row_y = reference.bottom + GAP * 2
        cards = tuple(pygame.Rect(left + i * (card + GAP), row_y, card, card_h) for i in range(choices))
        dots = pygame.Rect(protected.right + 14, MARGIN, 10, DOTS_HEIGHT)
        return cls(reference, cards, dots, area)


__all__ = ["MARGIN", "MOMO_HEIGHT", "MOMO_MIDBOTTOM", "RoundLayout"]
