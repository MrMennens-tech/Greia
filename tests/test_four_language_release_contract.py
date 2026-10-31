"""Release contract for every manifest-advertised Greia language.

Every selector uses the manifest registry; each offered language must have the
same Activity text keys, declarations, and accepted shared spoken banks.
Provider-free and display-free: it reads source, bundles and committed files only.
"""
from __future__ import annotations

import json
import re
import tomllib
import unittest
from pathlib import Path

from greia_platform.localization import (
    shared_character_audio_path,
    shared_character_intro_path,
    shared_number_audio_path,
    shared_vocab_audio_path,
)
from greia_platform.system_language import (
    SUPPORTED_SYSTEM_LANGUAGES,
    SUPPORTED_SYSTEM_LOCALES,
)

ROOT = Path(__file__).resolve().parents[1]
RELEASED = SUPPORTED_SYSTEM_LOCALES
_PLACEHOLDER = re.compile(r"\$\{?\w+\}?|\{\w+\}")


def _builtin_activities() -> list[Path]:
    return sorted(path.parent for path in (ROOT / "activities").glob("*/activity.toml"))


class RegistryAndSelectorTests(unittest.TestCase):
    def test_registry_matches_manifest_inventory(self) -> None:
        from greia_platform.system_language import load_system_languages
        self.assertEqual(load_system_languages(), SUPPORTED_SYSTEM_LANGUAGES)
        self.assertEqual(tuple(item.locale for item in SUPPORTED_SYSTEM_LANGUAGES), RELEASED)
        for original in ("en", "it", "es", "fr"):
            self.assertIn(original, RELEASED)

    def test_every_selector_reads_the_single_registry(self) -> None:
        # Installer language-first screen, on-device Parent panel and the
        # developer simulator must not carry their own language lists.
        for relative in (
            "src/greia_installer/entrypoint.py",
            "src/greia_launcher/parent_panel.py",
            "src/greia_simulator/app.py",
        ):
            with self.subTest(source=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("SUPPORTED_SYSTEM_LANGUAGES", source)
                self.assertNotIn('"Deutsch', source)

    def test_parent_panel_and_shell_tables_cover_every_released_language(self) -> None:
        from greia_launcher.achievement_localization import missing_supported_locales
        from greia_launcher.panel_localization import LOCALES

        self.assertEqual(tuple(LOCALES), RELEASED)
        self.assertEqual(missing_supported_locales(), ())

    def test_creations_gallery_copy_covers_every_released_language(self) -> None:
        from greia_platform.creation_gallery_painter import _GALLERY_TEXT

        from greia_platform.system_language import language_ui
        for key, options in _GALLERY_TEXT.items():
            with self.subTest(key=key):
                for locale in RELEASED:
                    text = language_ui(locale, "gallery").get(key, options.get(locale, ""))
                    self.assertTrue(text.strip(), f"{key}/{locale}")

    def test_installer_catalogues_cover_spanish_and_french(self) -> None:
        from greia_installer.i18n import InstallerTranslator

        self.assertEqual(InstallerTranslator("es").text("Continue"), "Continuar")
        self.assertEqual(InstallerTranslator("fr").text("Continue"), "Continuer")


class ActivityLanguageTests(unittest.TestCase):
    def test_every_builtin_activity_declares_exactly_the_released_languages(self) -> None:
        activities = _builtin_activities()
        self.assertEqual(len(activities), 46)
        for root in activities:
            with self.subTest(activity=root.name):
                manifest = tomllib.loads((root / "activity.toml").read_text(encoding="utf-8"))
                declared = manifest["activity"]["languages"]
                if declared == ["*"]:
                    continue
                self.assertEqual(sorted(declared), sorted(RELEASED))

    def test_four_way_text_key_and_placeholder_parity(self) -> None:
        for root in _builtin_activities():
            bundles = {
                locale: json.loads((root / "locales" / f"{locale}.json").read_text(encoding="utf-8"))["strings"]
                for locale in RELEASED
            }
            keys = set(bundles["en"])
            for locale in RELEASED:
                with self.subTest(activity=root.name, locale=locale):
                    self.assertEqual(set(bundles[locale]), keys)
                    for key, value in bundles[locale].items():
                        self.assertTrue(str(value).strip(), key)
                        self.assertEqual(
                            set(_PLACEHOLDER.findall(value)),
                            set(_PLACEHOLDER.findall(bundles["en"][key])),
                            key,
                        )


class SpokenAssetParityTests(unittest.TestCase):
    """Shared banks resolve in the requested language, not via English fallback."""

    def _assert_in_language(self, path: Path | None, locale: str) -> None:
        self.assertIsNotNone(path)
        self.assertIn(f"/{locale}/", path.as_posix())

    def test_shared_character_library_and_intros(self) -> None:
        manifest = tomllib.loads(
            (ROOT / "assets/audio/characters/shared/v0.2/manifest.toml").read_text(encoding="utf-8")
        )
        cues = {
            (row["character"], row["family"])
            for row in manifest["utterance"]
            if row["locale"] == "en" and row["family"] != "character.intro"
        }
        self.assertEqual(len(cues), 30)
        for character, family in sorted(cues):
            for locale in RELEASED:
                with self.subTest(character=character, family=family, locale=locale):
                    self._assert_in_language(
                        shared_character_audio_path(ROOT, character, family, locale), locale
                    )
        for character in ("leo", "lilli", "flash", "tito", "momo", "dani"):
            for locale in RELEASED:
                with self.subTest(intro=character, locale=locale):
                    self._assert_in_language(shared_character_intro_path(ROOT, character, locale), locale)

    def test_vocabulary_bank_has_every_noun_in_every_language(self) -> None:
        nouns = sorted(path.stem for path in (ROOT / "assets/audio/vocab/v1/en").glob("*.wav"))
        self.assertGreaterEqual(len(nouns), 100)
        for noun in nouns:
            for locale in RELEASED:
                with self.subTest(noun=noun, locale=locale):
                    self._assert_in_language(shared_vocab_audio_path(ROOT, noun, locale), locale)

    def test_number_bank_zero_to_twenty_five(self) -> None:
        for number in range(26):
            for locale in RELEASED:
                with self.subTest(number=number, locale=locale):
                    self._assert_in_language(shared_number_audio_path(ROOT, number, locale), locale)
        self.assertIsNone(shared_number_audio_path(ROOT, 26, "en"))
        self.assertIsNone(shared_number_audio_path(ROOT, -1, "en"))
        self.assertIsNone(shared_number_audio_path(ROOT, True, "en"))  # type: ignore[arg-type]
        self.assertEqual(
            shared_number_audio_path(ROOT, 7, "es-MX"),
            ROOT / "assets/audio/numbers/v1/es/7.wav",
        )

    def test_first_boot_and_launcher_labels(self) -> None:
        from greia_launcher.first_profile_copy import FIRST_PROFILE_AUDIO_ROOT, FIRST_PROFILE_CUES

        for cue in FIRST_PROFILE_CUES:
            name = cue.split(".", 1)[1]
            for locale in RELEASED:
                with self.subTest(cue=cue, locale=locale):
                    self.assertTrue((ROOT / FIRST_PROFILE_AUDIO_ROOT / locale / f"{name}.wav").is_file())
        from tools.audit_launcher_spoken_labels import audit_activities, audit_collections

        titles = audit_activities()
        self.assertEqual(titles["ACTIVITY_TITLE_COMPLETE"], titles["ACTIVITY_TITLE_LOCALE_COMBINATIONS"])
        self.assertEqual(titles["ACTIVITY_TITLE_LOCALE_COMBINATIONS"], 46 * len(RELEASED))
        labels = audit_collections()
        self.assertEqual(labels["COLLECTION_MISSING"], [])


if __name__ == "__main__":
    unittest.main()
