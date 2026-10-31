"""Lifecycle, timing and shared-kit input for Same or Different.

Momo shows one picture in a dashed frame; the child taps the card that looks
exactly the same. The ladder follows Leerzone's five levels -- plain pictures,
the same picture in three sizes, a shadow that asks for its picture, a picture
among its mirror images, and a shadow among mirror images -- and moves up and
down by itself from recent visits. A visit is six rounds with one progress dot
each, no timer, no score and nothing that can fail.

How to play is shown, never only said: every round starts with the reference
bouncing and Momo pointing. A right tap makes the card glow, speaks the
picture's name when an approved recording exists, Momo cheers and the next round
deals in. A wrong tap wiggles that card, Momo thinks and the reference bounces
again -- no card is ever marked wrong. Idle hints back off (6 s, +12 s, +24 s):
the reference bounces, then two cards glow, then the right one. A finished visit
ends on the shared cast completion scene.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from enum import StrEnum
import random
import time

import pygame

from greia_platform.activity_api import activity_stop_requested, mark_activity_ready
from greia_platform.frame_governor import FrameGovernor, FrameKind
from greia_platform.activity_controls import (
    ControlKit,
    ControlLayout,
    ControlTheme,
    KitPointer,
    PointerPhase,
    PygameControlInput,
)
from greia_platform.activity_feedback import CastFeedback, IdleHintScheduler
from greia_platform.localization import LocalizedResources
from greia_platform.pygame_canvas import PygameReferenceCanvas, activity_viewport_for_surface
from greia_platform.pygame_completion import (
    CompletionContent,
    CompletionOverlay,
    CompletionPalette,
    CompletionScene,
    PygameCompletionScreen,
)
from greia_platform.typography import GreiaTypography
from greia_platform.ui_core import SurfaceNavigator, UiEventResult

if __package__:
    from .uguale_art import HOST, UgualeArt
    from .uguale_audio import UgualeAudio
    from .uguale_content import LEVELS, MAX_LEVEL, PICTURES_BY_ID, REFERENCE_HEIGHT, REFERENCE_WIDTH, ROUNDS_PER_VISIT
    from .uguale_controls import UgualeControls
    from .uguale_layout import MOMO_HEIGHT, RoundLayout
    from .uguale_model import (
        HISTORY_LIMIT,
        Round,
        RoundBuilder,
        TapResult,
        Visit,
        VisitResult,
        adapt_level,
    )
    from .uguale_render import PULSE_SECONDS, MomoCast, RoundMotion, UgualeRenderer
    from .uguale_services import EventPort, ProgressPort
else:
    from uguale_art import HOST, UgualeArt
    from uguale_audio import UgualeAudio
    from uguale_content import LEVELS, MAX_LEVEL, PICTURES_BY_ID, REFERENCE_HEIGHT, REFERENCE_WIDTH, ROUNDS_PER_VISIT
    from uguale_controls import UgualeControls
    from uguale_layout import MOMO_HEIGHT, RoundLayout
    from uguale_model import (
        HISTORY_LIMIT,
        Round,
        RoundBuilder,
        TapResult,
        Visit,
        VisitResult,
        adapt_level,
    )
    from uguale_render import PULSE_SECONDS, MomoCast, RoundMotion, UgualeRenderer
    from uguale_services import EventPort, ProgressPort

CELEBRATE_SECONDS = 1.35
HINT_GLOW = 1.6
HELP_AFTER_MISSES = 3
MAX_SCHEDULED = 16
NAVY = (37, 59, 89)


class AppState(StrEnum):
    PLAYING = "playing"
    TERMINAL = "terminal"


class Timeline:
    """Tiny bounded scheduler for the scripted moments."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._entries: deque[tuple[float, Callable[[], object]]] = deque(maxlen=MAX_SCHEDULED)

    def after(self, delay: float, action: Callable[[], object]) -> None:
        self._entries.append((self._clock() + delay, action))

    def run_due(self) -> bool:
        now = self._clock()
        due = [entry for entry in self._entries if entry[0] <= now]
        if not due:
            return False
        for entry in due:
            self._entries.remove(entry)
        for _, action in sorted(due, key=lambda entry: entry[0]):
            action()
        return True

    @property
    def busy(self) -> bool:
        return bool(self._entries)

    def clear(self) -> None:
        self._entries.clear()


class UgualeApp:
    """Coordinate the visit model, kit controls, art and lifecycle."""

    def __init__(
        self,
        *,
        screen: pygame.Surface,
        canvas: PygameReferenceCanvas,
        typography: GreiaTypography,
        resources: LocalizedResources | None,
        audio: UgualeAudio,
        progress: ProgressPort,
        events: EventPort,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
        kit: ControlKit | None = None,
        art: UgualeArt | None = None,
        session_prefix: str | None = None,
        level: int | None = None,
    ) -> None:
        self.screen = screen
        self.canvas = canvas
        self.typography = typography
        self.resources = resources
        self.audio = audio
        self.progress = progress
        self.events = events
        self.rng = rng if rng is not None else random.Random()
        self.clock = clock
        self._session_prefix = session_prefix or f"{int(time.time())}"
        self._visits_played = 0
        self.session_id = self._new_session_id()

        saved = progress.load()
        self.level = saved.level if level is None else max(0, min(MAX_LEVEL, level))
        self.history: list[VisitResult] = list(saved.history)

        # Shared control kit (ADR 0037): learn Collection -> orange accent.
        self.kit = kit if kit is not None else ControlKit(typography, ControlTheme.for_accent("orange"))
        self.art = art if art is not None else UgualeArt(self.kit.painter)
        feedback = CastFeedback(HOST, height=MOMO_HEIGHT, art=self.art.loader, clock=clock)
        self.cast = MomoCast(feedback, self.art, clock)
        self.renderer = UgualeRenderer(self.art, self.cast, clock)
        self.motion = RoundMotion()
        self.timeline = Timeline(clock)
        self.controls = UgualeControls(self.kit, on_card=self._on_card)
        self._surfaces = SurfaceNavigator(self.controls.layer)
        self._input = PygameControlInput(to_logical=canvas.pointer, is_safe=lambda pos: _safe_point(self.screen, pos))
        self._layout_source = ControlLayout.for_canvas(canvas, screen.get_size())
        self.visit: Visit | None = None
        self.current: Round | None = None
        self.layout: RoundLayout | None = None
        self.completion: PygameCompletionScreen | None = None
        self.state = AppState.PLAYING
        self._running = True
        self.ready_published = False
        self._dirty = True
        self._activated = False
        self._busy = False
        self._last_activity = clock()
        self._hints = IdleHintScheduler(now=self._last_activity)
        self._start_visit(first=True)

    # -- main loop --------------------------------------------------------------

    def run(self) -> int:
        frames = FrameGovernor()
        try:
            while self._running and not activity_stop_requested():
                for event in frames.events():
                    self.handle_event(event)
                repeat = self._input.poll()
                if repeat is not None:
                    self._dispatch(repeat)
                animating = self.step()
                frame = frames.frame(dirty=self._dirty, animating=animating)
                if frame is FrameKind.FULL:
                    self.render()
                    self.canvas.present()
                    pygame.display.flip()
                    self._dirty = False
                    if not self.ready_published:
                        mark_activity_ready()
                        self.ready_published = True
                elif frame is FrameKind.POINTER:
                    self.canvas.present_pointer()
                frames.wait(polling=self._input.repeating)
        finally:
            self.persist()
            self.typography.clear()
        return 0

    def step(self) -> bool:
        """Advance timers; return True while something on screen is moving."""

        now = self.clock()
        if self.timeline.run_due():
            self._dirty = True
        if self.cast.update():
            self._dirty = True
        self.motion.prune(now)
        if self.state is AppState.PLAYING:
            self._maybe_hint(now)
        if self.controls.layer.invalidation.should_draw:
            self._dirty = True
        cards = len(self.current.choices) if self.current is not None else 0
        return (self.state is AppState.PLAYING and self.motion.active(now, cards)) or self.cast.animating

    def render(self) -> None:
        surface = self.canvas.surface
        if self.state is AppState.PLAYING and self.current is not None and self.layout is not None:
            self.renderer.draw_round(surface, self.current, LEVELS[self.level].twist, self.layout, self.motion)
        else:
            self.renderer.draw_blank(surface)
        self._surfaces.draw(surface)

    def persist(self) -> None:
        self.progress.save(self.level, self.history)

    # -- input --------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self._running = False
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._running = False
            return
        if event.type == pygame.VIDEORESIZE:
            self._resize()
            return
        translated = self._input.translate(event)
        if translated is not None:
            self._dispatch(translated)

    def _resize(self) -> None:
        self.screen = pygame.display.get_surface() or self.screen
        self.canvas = PygameReferenceCanvas(self.screen, hires=True)
        self._input = PygameControlInput(to_logical=self.canvas.pointer, is_safe=lambda pos: _safe_point(self.screen, pos))
        self._layout_source = ControlLayout.for_canvas(self.canvas, self.screen.get_size())
        if self.current is not None and self.visit is not None:
            self.layout = self._round_layout()
            self.controls.show_round(self.layout, self.visit.total, self.visit.done, keep_focus=True)
            self.controls.set_enabled(not self._busy)
        self._dirty = True

    def _dispatch(self, kit_input) -> bool:
        if not isinstance(kit_input, KitPointer) or kit_input.phase is not PointerPhase.MOVE:
            self._note_activity()
        result = self._surfaces.dispatch(kit_input)
        if self.controls.layer.invalidation.should_draw:
            self._dirty = True
        return result is not UiEventResult.IGNORED

    def tap(self, logical: tuple[int, int]) -> bool:
        """Deliver one complete tap at a logical position (tests/tools)."""

        point = (int(logical[0]), int(logical[1]))
        self._activated = False
        self._dispatch(KitPointer(PointerPhase.DOWN, point))
        self._dispatch(KitPointer(PointerPhase.UP, point))
        return self._activated

    def press(self, key: int) -> bool:
        """Deliver one key press through the shared navigation mapping."""

        self._activated = False
        translated = self._input.translate(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=""))
        if translated is not None:
            self._dispatch(translated)
        return self._activated

    def _note_activity(self) -> None:
        self._last_activity = self.clock()
        self._hints.reset(self._last_activity)

    # -- visit flow ---------------------------------------------------------------

    def _round_layout(self) -> RoundLayout:
        return RoundLayout.build(LEVELS[self.level].choices, self._layout_source.protected)

    def _start_visit(self, *, first: bool = False) -> None:
        self.timeline.clear()
        self.motion.clear()
        self.cast.reset()
        self.session_id = self._new_session_id()
        builder = RoundBuilder(self.level, self.rng, lambda picture: self.art.is_lopsided(picture.picture_id))
        self.visit = Visit(builder, ROUNDS_PER_VISIT)
        self.state = AppState.PLAYING
        self._next_round(first=first)

    def _next_round(self, *, first: bool = False) -> None:
        visit = self.visit
        if visit is None:
            return
        now = self.clock()
        self.timeline.clear()
        self.motion.clear()
        self.cast.reset()
        self.current = visit.start_round()
        self.layout = self._round_layout()
        self.audio.prepare_names(PICTURES_BY_ID[face.picture_id].noun for face in self.current.choices)
        self.controls.show_round(self.layout, visit.total, visit.done)
        self.motion.deal_start = now
        deal = 0.06 * len(self.current.choices) + 0.3
        self._busy = True
        self.controls.set_enabled(False)
        self.timeline.after(deal, self._end_busy)
        self.motion.pulse = (now + deal, now + deal + PULSE_SECONDS)
        self.audio.play("whoosh")
        if first:
            self.audio.momo("ready.go")
        self.cast.point(deal + 1.4)
        self._note_activity()
        self._dirty = True

    def _end_busy(self) -> None:
        self._busy = False
        self.controls.set_enabled(True)
        self._note_activity()
        self._dirty = True

    def _on_card(self, index: int) -> None:
        visit = self.visit
        current = self.current
        if visit is None or current is None or self.state is not AppState.PLAYING or self._busy:
            return
        face = current.choices[index]
        noun = PICTURES_BY_ID[face.picture_id].noun
        outcome = visit.tap(index)
        if outcome is TapResult.IGNORED:
            return
        self._activated = True
        now = self.clock()
        self.audio.play("tap")
        if outcome is TapResult.CORRECT:
            self._busy = True
            self.controls.set_enabled(False)
            self.controls.set_done(visit.done)
            self.motion.halos[index] = (now, now + CELEBRATE_SECONDS)
            rect = self.layout.cards[index] if self.layout is not None else None
            if rect is not None:
                self.motion.add_fx("sparkle", (rect.right - rect.width // 5, rect.top + rect.height // 5), now)
            self.audio.play("match")
            if not self.audio.say_name(noun) and visit.done % 2 == 1:
                self.audio.momo("praise.general")
            self.cast.correct()
            self.events.round_solved(
                self.session_id,
                {"round": visit.done, "total": visit.total, "level": self.level + 1, "misses": visit.round_misses},
            )
            if visit.complete:
                self.timeline.after(CELEBRATE_SECONDS, self._complete_visit)
            else:
                self.timeline.after(CELEBRATE_SECONDS, self._next_round)
        else:
            self.motion.wobbles[index] = now
            self.audio.play("miss")
            self.audio.say_name(noun)
            self.cast.try_again()
            self.timeline.after(0.7, self._pulse_reference)
            if visit.round_misses % HELP_AFTER_MISSES == 0:
                self.timeline.after(1.4, self._help)
                self.audio.momo("encourage.retry")
        self._dirty = True

    def _pulse_reference(self) -> None:
        now = self.clock()
        self.motion.pulse = (now, now + PULSE_SECONDS)
        self._dirty = True

    def _help(self) -> None:
        """After a few wrong tries Momo points and the right card glows."""

        current = self.current
        if current is None or self._busy:
            return
        now = self.clock()
        self.cast.point(HINT_GLOW + 0.4)
        self.motion.halos[current.answer] = (now, now + HINT_GLOW)
        self.audio.play("hint")
        self._dirty = True

    def _complete_visit(self) -> None:
        visit = self.visit
        if visit is None or self.state is not AppState.PLAYING:
            return
        result = VisitResult(self.level, visit.total, visit.misses)
        self.history = (self.history + [result])[-HISTORY_LIMIT:]
        played_level = self.level
        self.level = adapt_level(self.level, self.history)
        self.persist()
        self.events.visit_completed(
            self.session_id,
            {"rounds": visit.total, "misses": visit.misses, "level": played_level + 1},
        )
        self.audio.play("fanfare")
        self.audio.momo("celebrate.success")
        self.cast.correct()
        self.completion = PygameCompletionScreen(
            self.typography,
            width=REFERENCE_WIDTH,
            height=REFERENCE_HEIGHT,
            palette=CompletionPalette(background=NAVY),
            scene=CompletionScene(self.kit, character=HOST, star_total=visit.total),
        )
        self.completion.prepare(
            CompletionContent(
                title=self._text("victory.title", "★"),
                primary_label=self._text("button.play_again", "↻"),
                body_lines=(self._text("victory.subtitle", "★"),),
                achievement_count=visit.total,
            )
        )
        self._surfaces.push_overlay(CompletionOverlay(self.completion, on_primary=self._restart, on_secondary=None))
        self.timeline.clear()
        self.state = AppState.TERMINAL
        self._busy = False
        self._dirty = True

    def _restart(self) -> None:
        self._activated = True
        if self.completion is not None:
            self._surfaces.pop_overlay()
            self.completion.clear()
            self.completion = None
        self._start_visit(first=True)

    # -- hints ----------------------------------------------------------------------

    def _maybe_hint(self, now: float) -> None:
        current = self.current
        if current is None or self._busy:
            return
        step = self._hints.poll(now, self._last_activity)
        if not step:
            return
        self.cast.point(self._hints.animation_seconds(1.8))
        self.motion.pulse = (now, now + self._hints.animation_seconds(PULSE_SECONDS))
        if step == 2:
            wrong = [i for i in range(len(current.choices)) if i != current.answer]
            for index in (current.answer, self.rng.choice(wrong)):
                self.motion.halos[index] = (now, now + self._hints.animation_seconds(HINT_GLOW))
        elif step >= 3:
            self.motion.halos[current.answer] = (now, now + self._hints.animation_seconds(HINT_GLOW))
        self.audio.play("hint")
        self._dirty = True

    # -- helpers --------------------------------------------------------------------

    def _text(self, key: str, default: str) -> str:
        if self.resources is None:
            return default
        try:
            return self.resources.text(key) or default
        except Exception:
            return default

    def _new_session_id(self) -> str:
        self._visits_played += 1
        return f"{self._session_prefix}-{self._visits_played}-{self.rng.randrange(1_000_000):06d}"


def _safe_point(surface: pygame.Surface, position: tuple[int, int]) -> bool:
    """True inside the play surface and outside the Greia protected region(s)."""

    viewport = activity_viewport_for_surface(surface)
    x, y = position
    if not (0 <= x < viewport.surface.width and 0 <= y < viewport.surface.height):
        return False
    for protected in viewport.protected_regions:
        if protected.x <= x < protected.right and protected.y <= y < protected.bottom:
            return False
    return True


__all__ = ["AppState", "Timeline", "UgualeApp"]
