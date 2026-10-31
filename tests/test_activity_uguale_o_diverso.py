"""Same or Different (uguale_o_diverso): rules, saves, content and the full app loop."""

from __future__ import annotations

import os
from pathlib import Path
import random
import sys
import tomllib
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame

ROOT = Path(__file__).resolve().parents[1]
ACTIVITY_ROOT = ROOT / "activities" / "uguale_o_diverso"
for path in (ROOT / "src", ACTIVITY_ROOT):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

from uguale_content import LEVELS, MAX_LEVEL, PICTURES, ROUNDS_PER_VISIT, Twist  # noqa: E402
from uguale_model import (  # noqa: E402
    Face,
    RoundBuilder,
    TapResult,
    Visit,
    VisitResult,
    adapt_level,
    looks_the_same,
)
from uguale_services import SCHEMA_VERSION, GreiaUgualeProgress  # noqa: E402

LANGUAGES = ("en", "it", "es", "fr", "nl")


class _Storage:
    def __init__(self, value=None) -> None:
        self.value = value

    def kv_get(self, key):
        return self.value

    def kv_set(self, key, value) -> None:
        self.value = value


class _Events:
    def __init__(self) -> None:
        self.solved: list[dict] = []
        self.completed: list[dict] = []

    def round_solved(self, session_id: str, payload: dict) -> None:
        self.solved.append(payload)

    def visit_completed(self, session_id: str, payload: dict) -> None:
        self.completed.append(payload)


class _Audio:
    def __init__(self) -> None:
        self.played: list[str] = []

    def prepare_names(self, nouns) -> None:
        list(nouns)

    def say_name(self, noun: str) -> bool:
        return False

    def momo(self, cue: str) -> bool:
        return False

    def play(self, name: str) -> None:
        self.played.append(name)

    def stop_speech(self) -> None:
        return None


class RoundRuleTests(unittest.TestCase):
    def test_every_rung_has_exactly_one_matching_choice(self) -> None:
        for level, spec in enumerate(LEVELS):
            builder = RoundBuilder(level, random.Random(level))
            for _ in range(200):
                current = builder.build()
                self.assertEqual(len(current.choices), spec.choices)
                matching = [i for i, face in enumerate(current.choices) if looks_the_same(current.reference, face)]
                self.assertEqual(matching, [current.answer])
                self.assertEqual(len({(f.picture_id, f.size, f.mirrored, f.shadow) for f in current.choices}), spec.choices)

    def test_size_rung_offers_one_picture_in_three_sizes(self) -> None:
        builder = RoundBuilder(1, random.Random(5))
        for _ in range(50):
            current = builder.build()
            self.assertEqual({face.picture_id for face in current.choices}, {current.reference.picture_id})
            self.assertEqual(sorted(face.size for face in current.choices), [0, 1, 2])

    def test_shadow_rungs_ask_with_a_shadow_and_answer_with_a_picture(self) -> None:
        for level in (2, 4):
            builder = RoundBuilder(level, random.Random(level))
            for _ in range(50):
                current = builder.build()
                self.assertTrue(current.reference.shadow)
                self.assertFalse(any(face.shadow for face in current.choices))

    def test_mirror_rungs_offer_the_mirror_image_only_for_lopsided_pictures(self) -> None:
        lopsided = {p.picture_id for p in PICTURES[::3]}
        builder = RoundBuilder(3, random.Random(9), asymmetric=lambda picture: picture.picture_id in lopsided)
        for _ in range(100):
            current = builder.build()
            self.assertIn(current.reference.picture_id, lopsided)
            self.assertTrue(
                any(f.mirrored and f.picture_id == current.reference.picture_id for f in current.choices),
                "the mirror image of the target is the near miss",
            )
            self.assertFalse(current.choices[current.answer].mirrored)

    def test_mirror_without_lopsided_pictures_still_plays(self) -> None:
        builder = RoundBuilder(3, random.Random(1), asymmetric=lambda picture: False)
        current = builder.build()
        self.assertEqual(len(current.choices), 5)
        self.assertFalse(any(f.mirrored and f.picture_id == current.reference.picture_id for f in current.choices))

    def test_the_target_changes_between_rounds(self) -> None:
        builder = RoundBuilder(0, random.Random(2))
        last = None
        for _ in range(60):
            current = builder.build(last)
            self.assertNotEqual(current.reference.picture_id, last)
            last = current.reference.picture_id

    def test_visit_counts_misses_and_never_fails(self) -> None:
        visit = Visit(RoundBuilder(0, random.Random(3)))
        for _ in range(ROUNDS_PER_VISIT):
            current = visit.start_round()
            wrong = (current.answer + 1) % len(current.choices)
            self.assertIs(visit.tap(wrong), TapResult.WRONG)
            self.assertIs(visit.tap(99), TapResult.IGNORED)
            self.assertIs(visit.tap(current.answer), TapResult.CORRECT)
            self.assertIs(visit.tap(current.answer), TapResult.IGNORED, "a solved round is closed")
        self.assertTrue(visit.complete)
        self.assertEqual(visit.misses, ROUNDS_PER_VISIT)

    def test_adaptation_two_tidy_visits_up_one_all_misses_down(self) -> None:
        tidy = VisitResult(1, 6, 1)
        self.assertEqual(adapt_level(1, [tidy]), 1)
        self.assertEqual(adapt_level(1, [tidy, tidy]), 2)
        self.assertEqual(adapt_level(2, [VisitResult(2, 6, 6)]), 1)
        self.assertEqual(adapt_level(MAX_LEVEL, [VisitResult(MAX_LEVEL, 6, 0)] * 2), MAX_LEVEL)
        self.assertEqual(adapt_level(0, [VisitResult(0, 6, 9)]), 0)

    def test_face_is_hashable_for_the_surface_caches(self) -> None:
        self.assertEqual(len({Face("cat"), Face("cat"), Face("cat", mirrored=True)}), 2)


class ContentAndManifestTests(unittest.TestCase):
    def test_pictures_use_registered_library_art_only(self) -> None:
        catalog = tomllib.loads((ROOT / "assets/catalog/shared_visuals_v1_source.toml").read_text(encoding="utf-8"))
        registered = {entry["id"] for entry in catalog["visuals"]}
        for picture in PICTURES:
            self.assertIn(picture.asset_id, registered)

    def test_ladder_follows_leerzone_levels(self) -> None:
        self.assertEqual(
            [spec.twist for spec in LEVELS],
            [Twist.PLAIN, Twist.SIZE, Twist.SHADOW, Twist.MIRROR, Twist.SHADOW_MIRROR],
        )
        self.assertEqual([spec.choices for spec in LEVELS], [3, 3, 3, 5, 5])

    def test_manifest_and_locales_agree(self) -> None:
        manifest = tomllib.loads((ACTIVITY_ROOT / "activity.toml").read_text(encoding="utf-8"))
        self.assertEqual(manifest["activity"]["id"], "org.greia.uguale-o-diverso")
        # Dutch ships as a staged bundle (locales/nl.json); "nl" joins ``languages``
        # when the owner promotes the Dutch manifest.
        self.assertEqual(sorted(manifest["activity"]["languages"]), ["en", "es", "fr", "it"])
        import json

        keysets = {
            locale: set(json.loads((ACTIVITY_ROOT / "locales" / f"{locale}.json").read_text(encoding="utf-8"))["strings"])
            for locale in LANGUAGES
        }
        self.assertEqual(len({frozenset(keys) for keys in keysets.values()}), 1)
        self.assertIn(manifest["activity"]["title_key"], keysets["en"])

    def test_event_keys_stay_far_below_the_64_byte_bound(self) -> None:
        session = "1999999999-99-999999"
        self.assertLess(len(f"uguale:{session}:r{ROUNDS_PER_VISIT}".encode()), 64)


class ProgressTests(unittest.TestCase):
    def test_round_trip_and_bad_payloads(self) -> None:
        storage = _Storage()
        progress = GreiaUgualeProgress(storage)
        self.assertEqual(progress.load().level, 0)
        progress.save(3, [VisitResult(3, 6, 2)] * 9)
        loaded = progress.load()
        self.assertEqual(loaded.level, 3)
        self.assertEqual(len(loaded.history), 6)
        storage.value = {"schema_version": SCHEMA_VERSION, "level": 99, "history": [{"rounds": "x"}, 5]}
        loaded = progress.load()
        self.assertEqual((loaded.level, loaded.history), (MAX_LEVEL, ()))
        storage.value = {"schema_version": 0}
        self.assertEqual(progress.load().level, 0)


class AppLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        if pygame.display.get_surface() is None:
            pygame.display.set_mode((1024, 600))

    def _build(self, level: int = 0, size: tuple[int, int] | None = None, locale: str = "nl"):
        from greia_platform.localization import ActivityLocaleSupport, LocalizedResources, resolve_activity_locale
        from greia_platform.pygame_canvas import PygameReferenceCanvas
        from greia_platform.typography import GreiaTypography
        from uguale_app import UgualeApp

        screen = pygame.display.set_mode(size) if size else pygame.display.get_surface()
        context = resolve_activity_locale(locale, ActivityLocaleSupport.localized(LANGUAGES, default_ui_locale=locale))
        self.storage = _Storage({"schema_version": SCHEMA_VERSION, "level": level, "history": []})
        self.events = _Events()
        self.audio = _Audio()
        self.clock = [100.0]
        self.app = UgualeApp(
            screen=screen,
            canvas=PygameReferenceCanvas(screen),
            typography=GreiaTypography(),
            resources=LocalizedResources(ACTIVITY_ROOT, context),
            audio=self.audio,
            progress=GreiaUgualeProgress(self.storage),
            events=self.events,
            rng=random.Random(11),
            clock=lambda: self.clock[0],
        )
        return self.app

    def _advance(self, seconds: float, step: float = 0.05) -> None:
        end = self.clock[0] + seconds
        while self.clock[0] < end:
            self.clock[0] += step
            self.app.step()

    def _tap_card(self, index: int) -> bool:
        return self.app.tap(self.app.layout.cards[index].center)

    def _play_visit(self, misses_per_round: int = 0) -> None:
        for _ in range(ROUNDS_PER_VISIT):
            self._advance(2.0)
            for _ in range(misses_per_round):
                wrong = (self.app.current.answer + 1) % len(self.app.current.choices)
                self.assertTrue(self._tap_card(wrong))
                self._advance(0.2)
            self.assertTrue(self._tap_card(self.app.current.answer))
            self._advance(2.0)

    def test_full_visit_completes_and_saves(self) -> None:
        app = self._build()
        self._advance(1.0)
        self._play_visit()
        self.assertEqual(len(self.events.solved), ROUNDS_PER_VISIT)
        self.assertEqual(len(self.events.completed), 1)
        self.assertEqual(self.events.completed[0]["misses"], 0)
        self.assertEqual(app.state.value, "terminal")
        self.assertEqual(self.storage.value["history"][-1], {"level": 0, "rounds": ROUNDS_PER_VISIT, "misses": 0})
        self.assertIn("fanfare", self.audio.played)

    def test_cards_ignore_taps_while_dealing_and_celebrating(self) -> None:
        self._build()
        self.assertFalse(self._tap_card(0), "cards are not live while they deal in")
        self._advance(2.0)
        answer = self.app.current.answer
        self.assertTrue(self._tap_card(answer))
        self.assertFalse(self._tap_card(0), "the celebration locks the row")

    def test_wrong_tap_wiggles_pulses_and_never_marks_a_card(self) -> None:
        app = self._build()
        self._advance(2.0)
        wrong = (app.current.answer + 1) % len(app.current.choices)
        self.assertTrue(self._tap_card(wrong))
        self.assertIn(wrong, app.motion.wobbles)
        self.assertEqual(app.motion.halos, {}, "a wrong tap marks nothing")
        self._advance(1.0)
        self.assertIsNotNone(app.motion.pulse, "the reference calls attention back")

    def test_repeated_misses_get_a_gentle_help_glow(self) -> None:
        app = self._build()
        self._advance(2.0)
        for _ in range(3):
            self._tap_card((app.current.answer + 1) % len(app.current.choices))
            self._advance(0.1)
        self._advance(1.6)
        self.assertIn(app.current.answer, app.motion.halos)

    def test_idle_hints_back_off_and_then_stay_silent(self) -> None:
        app = self._build()
        self._advance(2.0)
        answer = app.current.answer
        self._advance(7.0)
        self.assertEqual(app._hints.count, 1)
        self.assertNotIn(answer, app.motion.halos, "the first hint only shows where to look")
        self._advance(13.0)
        self.assertEqual(app._hints.count, 2)
        self._advance(25.0)
        self.assertEqual(app._hints.count, 3)
        self._advance(60.0)
        self.assertEqual(app._hints.count, 3, "after three hints nothing more until input")

    def test_ladder_moves_up_after_two_tidy_visits(self) -> None:
        app = self._build()
        self._advance(1.0)
        self._play_visit()
        app._restart()
        self._advance(1.0)
        self._play_visit()
        self.assertEqual(app.level, 1)

    def test_every_rung_renders_in_every_locale_at_both_sizes(self) -> None:
        for locale in LANGUAGES:
            for size in ((1024, 600), (800, 480)):
                for level in range(MAX_LEVEL + 1):
                    app = self._build(level=level, size=size, locale=locale)
                    self._advance(2.0)
                    app.render()
                    self.assertEqual(len(app.layout.cards), LEVELS[level].choices)
                    for rect in app.layout.cards:
                        self.assertFalse(rect.colliderect(app._layout_source.protected))
                    self.assertTrue(pygame.Rect(0, 0, 1024, 600).contains(app.layout.reference))
        pygame.display.set_mode((1024, 600))

    def test_a_still_round_settles_to_a_still_frame(self) -> None:
        app = self._build()
        self._advance(3.0)
        self.assertFalse(app.step(), "nothing declares motion once the round is dealt and Momo rests")

    def test_resize_keeps_the_round(self) -> None:
        app = self._build()
        self._advance(2.0)
        answer = app.current.answer
        pygame.display.set_mode((800, 480))
        app._resize()
        self.assertEqual(app.current.answer, answer)
        self.assertTrue(self._tap_card(answer))
        pygame.display.set_mode((1024, 600))


if __name__ == "__main__":
    unittest.main()
