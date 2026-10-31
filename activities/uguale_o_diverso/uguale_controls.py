"""Shared control-kit wiring for Same or Different (ADR 0037).

The Activity draws its own cards, but every interactive element goes through
``greia_platform.activity_controls``: the choice cards are ``ExternalTarget``s
(pointer activation plus keyboard / D-pad / stick focus and the shared focus
ring) and the visit progress is ``ProgressDots`` (one dot per round). The
rules stay in ``Visit``; this class only maps controls to app callbacks.
"""

from __future__ import annotations

from collections.abc import Callable

import pygame

from greia_platform.activity_controls import ControlKit, ControlLayer, ExternalTarget, ProgressDots

if __package__:
    from .uguale_layout import RoundLayout
else:
    from uguale_layout import RoundLayout


def card_id(index: int) -> str:
    return f"card.{index}"


class UgualeControls:
    """Own the kit controls and the single ``ControlLayer`` of the play screen."""

    def __init__(self, kit: ControlKit, *, on_card: Callable[[int], object]) -> None:
        self._kit = kit
        self._on_card = on_card
        self.cards: tuple[ExternalTarget, ...] = ()
        self.progress: ProgressDots = kit.progress_dots("progress", pygame.Rect(0, 0, 40, 40), total=2)
        self.layer: ControlLayer = kit.layer((), layer_id="uguale.controls")

    def show_round(self, layout: RoundLayout, total_rounds: int, done: int, *, keep_focus: bool = False) -> None:
        focused, visible = self.layer.focused_id, self.layer.focus_visible
        self.cards = tuple(
            ExternalTarget(card_id(index), rect, (lambda i=index: self._on_card(i)), focus_radius=16)
            for index, rect in enumerate(layout.cards)
        )
        self.progress.total = total_rounds
        width = ProgressDots.preferred_width(total_rounds, layout.dots.height)
        self.progress.rect = pygame.Rect(layout.dots.x, layout.dots.y, width, layout.dots.height)
        self.progress.set_progress(done)
        self.layer.set_targets((*self.cards, self.progress))
        if keep_focus and focused is not None:
            self.layer.focus(focused, visible=visible)
        else:
            self.layer.focus(card_id(0))
        self.layer.ensure_focus()
        self.layer.invalidation.invalidate()

    def set_enabled(self, enabled: bool) -> None:
        for target in self.cards:
            target.enabled = enabled
        self.layer.invalidation.invalidate()

    def set_done(self, done: int) -> None:
        self.progress.set_progress(done)
        self.layer.invalidation.invalidate()

    def focused_card(self) -> int | None:
        focused = self.layer.focused_id
        if focused is None or not focused.startswith("card."):
            return None
        return int(focused.split(".", 1)[1])


__all__ = ["UgualeControls", "card_id"]
