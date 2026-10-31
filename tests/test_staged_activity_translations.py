"""Staged multilingual Activity copy: key parity without false voice claims.

These locale bundles are intentionally not advertised in activity.toml
while mandatory title WAVs and remaining dialog/visual acceptance are missing.
"""
from __future__ import annotations

from pathlib import Path
from string import Formatter
import ast
import json
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
STAGED = (
    "painting", "writing", "shape_garden", "piccola_serra",
    "memory_meraviglie", "clinica_cuccioli", "acquario_magico",
    "torre_forme", "volo_draghetto", "colline_allegre",
    "quattro_stagioni", "corsa_bacche", "bottega_delle_misure",
    "bosco_numeri", "il_giardino_dei_numeri", "faccine_momo",
    "luci_di_momo", "costruiamo_ponti", "casa_del_dieci",
    "workshop_settings", "specchi_magici", "nascondino_bosco",
    "nanna_delle_nuvolette", "orchestra_animali", "treno_numeri", "uguale_o_diverso",
    "quattro_amici", "pasticceria_magica",
    "baia_delle_orche", "cucciolo_mio", "la_discesa_della_biglia",
    "labirinto_magico", "mondo_contrari", "morbidi_mostriciattoli",
    "posta_di_leo", "stelle_incantate", "storie_della_mia_voce",
    "teatrino_fiabe", "viaggio_delfino", "sottomarino_giramondo",
    "enciclopedia_greia", "foresta_parole",
)

# Four games have translated UI but their lesson engines still depend on
# original-language sound/spelling assumptions; source text parity alone
# is not classroom or gameplay adaptation.
CURRICULUM_UI_ONLY = (
    "alfabeto_leo", "festa_delle_rime", "officina_dei_suoni",
    "sillabe_magiche",
)

# Source-key parity alone does not establish accurate narration or pedagogy.

# Activities that draw no locale-specific text declare the platform's
# language-neutral marker instead of a locale list. That is not an ES/FR claim.
LANGUAGE_NEUTRAL_MANIFESTS = {"shape_garden": ["*"]}

# Per-language lesson vocabulary: Word Forest teaches each language's own
# letter->word examples (EN "cat", IT "gatto"), so these keys are curriculum
# data and legitimately differ between the EN and IT bundles. They are still
# compared against the English bundle and must be non-empty in every locale.
LANGUAGE_SPECIFIC_KEY_PREFIXES = {"foresta_parole": ("word.",)}


def _fields(text: str) -> set[str]:
    return {
        name for _, name, _, _ in Formatter().parse(text)
        if name is not None
    }


class StagedActivityTranslationTests(unittest.TestCase):
    def test_staged_bundles_have_same_keys_and_placeholders_as_source(self) -> None:
        for activity in STAGED:
            root = ROOT / "activities" / activity
            english = json.loads((root / "locales/en.json").read_text(encoding="utf-8"))
            italian = json.loads((root / "locales/it.json").read_text(encoding="utf-8"))
            for locale in ("es", "fr"):
                with self.subTest(activity=activity, locale=locale):
                    path = root / f"locales/{locale}.json"
                    localized = json.loads(path.read_text(encoding="utf-8"))
                    self.assertEqual(localized["schema_version"], 1)
                    self.assertEqual(localized["locale"], locale)
                    self.assertEqual(localized["direction"], "ltr")
                    self.assertEqual(set(localized["strings"]), set(english["strings"]))
                    specific = LANGUAGE_SPECIFIC_KEY_PREFIXES.get(activity, ())
                    shared = lambda strings: {
                        key for key in strings if not key.startswith(specific)
                    }
                    self.assertEqual(
                        shared(localized["strings"]), shared(italian["strings"])
                    )
                    for key, value in localized["strings"].items():
                        self.assertTrue(isinstance(value, str) and value.strip())
                        self.assertEqual(
                            _fields(value), _fields(english["strings"][key]),
                            f"{activity}/{locale}/{key}: missing interpolation placeholders"
                        )
                    # A declared ES/FR audio cue must be a real file in that
                    # language (never an English clip reused under ES/FR).
                    for key, entry in localized["audio"].items():
                        relative = entry["path"]
                        self.assertIn(f"/{locale}/", f"/{relative}", key)
                        self.assertTrue((root / relative).is_file(), relative)

    def test_submarine_orders_and_spoken_aliases_have_consistent_translation(self) -> None:
        package = ROOT / "activities/sottomarino_giramondo/locales"
        reference = json.loads((package / "en.json").read_text(encoding="utf-8"))
        self.assertEqual(len(reference["audio"]), 55)
        for locale in ("es", "fr"):
            strings = json.loads((package / f"{locale}.json").read_text(encoding="utf-8"))["strings"]
            for direction in ("ahead", "stop", "left", "right", "compliment"):
                self.assertEqual(
                    strings[f"order.{direction}"], strings[f"voice.order.{direction}"],
                    f"{locale}: spoken instruction and on-screen instruction disagree"
                )
            for kind in ("coral", "kelp", "krill"):
                self.assertEqual(
                    strings[f"voice.creature.{kind}"],
                    strings[f"voice.creature_{kind}"],
                    f"{locale}: old and new voice cue aliases disagree",
                )
            for creature in ("whale", "turtle", "dolphin", "manta",
                             "clownfish", "coral", "kelp", "krill"):
                for number in range(1, 5):
                    self.assertTrue(strings[f"voice.fact.{creature}.{number}"].strip())
            # Source audio contains explicit button/encounter cues whose
            # approved recordings/transcripts still need manual extraction.
            self.assertIn("voice.btn.light", reference["audio"])
            self.assertNotIn("voice.btn.light", strings)

    def test_curriculum_ui_translations_do_not_claim_lesson_adaptation(self) -> None:
        for activity in CURRICULUM_UI_ONLY:
            base = ROOT / "activities" / activity
            source = json.loads((base / "locales/en.json").read_text(encoding="utf-8"))
            manifest = tomllib.loads((base / "activity.toml").read_text(encoding="utf-8"))
            self.assertEqual(set(manifest["activity"]["languages"]), {"en", "it", "es", "fr"})
            for locale in ("es", "fr"):
                with self.subTest(activity=activity, locale=locale):
                    bundle = json.loads((base / "locales" / f"{locale}.json").read_text(encoding="utf-8"))
                    self.assertEqual(bundle["locale"], locale)
                    self.assertEqual(bundle["audio"], {})
                    self.assertTrue(bundle["strings"])
                    self.assertEqual(set(bundle["strings"]) - set(source["strings"]), set())
                    for key, value in bundle["strings"].items():
                        self.assertTrue(value.strip())
                        for token in ("$letter", "$word", "$score", "$stars", "$char"):
                            self.assertEqual(
                                token in value, token in source["strings"][key],
                                f"{activity}/{locale}/{key}/{token}",
                            )

    def test_word_forest_real_language_examples_match_letter_targets(self) -> None:
        """Real ES/FR letter lessons are data, not a translation of EN labels."""
        source = ast.parse(
            (ROOT / "activities/foresta_parole/foresta_content.py")
            .read_text(encoding="utf-8")
        )
        definitions = [
            node for node in source.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "PHONICS_DATA"
        ]
        self.assertEqual(len(definitions), 1)
        curricula = ast.literal_eval(definitions[0].value)
        base = ROOT / "activities/foresta_parole/locales"
        for locale in ("es", "fr"):
            with self.subTest(locale=locale):
                lessons = curricula[locale]
                self.assertGreaterEqual(len(lessons), 20)
                keys = set()
                words = set()
                strings = json.loads(
                    (base / f"{locale}.json").read_text(encoding="utf-8")
                )["strings"]
                for lesson in lessons:
                    self.assertEqual(len(lesson), 6)
                    letter, stem, prompt, example, emoji, word_audio = lesson
                    self.assertEqual(letter, letter.upper())
                    self.assertEqual(stem, letter.lower())
                    self.assertEqual(prompt, f"find_{stem}")
                    self.assertTrue(example.casefold().startswith(letter.casefold()))
                    self.assertTrue(emoji)
                    self.assertTrue(word_audio.isascii() and word_audio.islower())
                    self.assertTrue(word_audio.isalpha())
                    self.assertNotIn(stem, keys)
                    self.assertNotIn(example.casefold(), words)
                    keys.add(stem)
                    words.add(example.casefold())
                    if f"phonics.{stem}" in strings:
                        self.assertEqual(strings[f"phonics.{stem}"], example)
                self.assertEqual(len(keys), len(lessons))
                self.assertEqual(len(words), len(lessons))
                self.assertEqual(
                    set(strings),
                    set(json.loads((base / "en.json").read_text(encoding="utf-8"))["strings"]),
                )
                self.assertTrue(all(strings[key] for key in strings if key.startswith("word.")))
                manifest = tomllib.loads(
                    (ROOT / "activities/foresta_parole/activity.toml")
                    .read_text(encoding="utf-8")
                )
                self.assertEqual(
                    set(manifest["activity"]["languages"]), {"en", "it", "es", "fr"},
                    "Word Forest advertises the four released languages",
                )

    def test_existing_dolphin_voice_cues_use_exact_caption_keys_in_both_base_locales(self) -> None:
        base = ROOT / "activities/viaggio_delfino/locales"
        for locale in ("en", "it"):
            data = json.loads((base / f"{locale}.json").read_text(encoding="utf-8"))
            cues = {k: v for k, v in data["audio"].items() if k.endswith(".voice")}
            self.assertEqual(len(cues), 7)
            for key, value in cues.items():
                caption = key[:-6] + ".caption"
                self.assertEqual(value["caption_key"], caption)
                self.assertIn(caption, data["strings"])
                self.assertTrue(data["strings"][caption].strip())

    def test_all_built_in_activities_are_accounted_for_by_source_stage(self) -> None:
        actual = {
            path.name for path in (ROOT / "activities").iterdir()
            if path.is_dir() and (path / "activity.toml").is_file()
        }
        registered = set(STAGED) | set(CURRICULUM_UI_ONLY)
        self.assertEqual(actual, registered)
        self.assertTrue(set(STAGED).isdisjoint(CURRICULUM_UI_ONLY))
        self.assertEqual(len(actual), 46)

    def test_encyclopedia_complete_written_catalogue_is_not_spoken_acceptance(self) -> None:
        base = ROOT / "activities/enciclopedia_greia"
        en = json.loads((base / "locales/en.json").read_text(encoding="utf-8"))
        it = json.loads((base / "locales/it.json").read_text(encoding="utf-8"))
        self.assertEqual(len(en["strings"]), 260)
        self.assertEqual(len(en["audio"]), 200)
        manifest = tomllib.loads((base / "activity.toml").read_text(encoding="utf-8"))
        self.assertEqual(set(manifest["activity"]["languages"]), {"en", "it", "es", "fr"})
        for locale in ("es", "fr"):
            with self.subTest(locale=locale):
                staged = json.loads((base / "locales" / f"{locale}.json").read_text(encoding="utf-8"))
                strings = staged["strings"]
                self.assertEqual(staged["audio"], {})
                self.assertEqual(len(strings), 260)
                self.assertEqual(set(strings), set(en["strings"]))
                self.assertEqual(set(strings), set(it["strings"]))
                self.assertTrue(all(isinstance(value, str) and value.strip() for value in strings.values()))
                for category in ("animals", "space", "earth", "body", "machines", "history"):
                    self.assertTrue(strings[f"section.{category}"])
                for category in ("lion", "elephant", "octopus", "bee", "penguin", "frog",
                                 "sun", "moon", "mars", "jupiter", "volcano",
                                 "heart", "lungs", "gears", "airplane", "dinosaurs"):
                    self.assertTrue(strings[f"{category}.title"])
                    self.assertTrue(strings[f"{category}.intro"])
                # Narration is still withheld: 200 source audio cues each
                # require actual scripts/voices, never English clip reuse.
                self.assertFalse(staged["audio"])

    def test_numeric_template_targets_remain_intact(self) -> None:
        """Dollar targets are consumed by old activities, not Python format()."""
        for activity in ("bosco_numeri", "casa_del_dieci"):
            root = ROOT / "activities" / activity / "locales"
            source = json.loads((root / "en.json").read_text(encoding="utf-8"))["strings"]
            for locale in ("es", "fr"):
                text = json.loads((root / f"{locale}.json").read_text(encoding="utf-8"))["strings"]
                for key, original in source.items():
                    for token in ("$num", "$target"):
                        if token in original:
                            self.assertIn(token, text[key], f"{activity}/{locale}/{key}")

    def test_number_train_has_no_dormant_plural_copy(self) -> None:
        """The reworked train asks pictorially (numeral + dot card, chimes).

        The old dormant ``prompt.load`` "{count} {item}" string and emoji item
        plurals are gone, so no singular/plural form can be mistranslated now
        that orders start at 1. Spoken orders wait for approved voice.
        """
        for locale in ("en", "it", "es", "fr"):
            text = json.loads(
                (ROOT / "activities/treno_numeri/locales" / f"{locale}.json").read_text(encoding="utf-8")
            )["strings"]
            self.assertNotIn("prompt.load", text, locale)
            self.assertFalse([key for key in text if key.startswith("item.")], locale)

    def test_dollar_variables_remain_unchanged_in_every_staged_locale(self) -> None:
        """Legacy activity strings use Template($name), not str.format()."""
        for activity in STAGED:
            base = ROOT / "activities" / activity / "locales"
            source = json.loads((base / "en.json").read_text(encoding="utf-8"))["strings"]
            for locale in ("es", "fr"):
                translated = json.loads((base / f"{locale}.json").read_text(encoding="utf-8"))["strings"]
                for key, original in source.items():
                    for token in ("$num", "$target", "$word", "$letter", "$score", "$stars", "$count"):
                        if token in original:
                            self.assertIn(token, translated[key], f"{activity}/{locale}/{key}")

    def test_translation_stage_does_not_falsely_advertise_speech(self) -> None:
        for activity in STAGED:
            manifest = tomllib.loads(
                (ROOT / "activities" / activity / "activity.toml").read_text(encoding="utf-8")
            )
            declared = manifest["activity"]["languages"]
            if activity in LANGUAGE_NEUTRAL_MANIFESTS:
                self.assertEqual(
                    declared, LANGUAGE_NEUTRAL_MANIFESTS[activity],
                    f"{activity}: neutral declaration changed",
                )
                continue
            self.assertEqual(set(declared), {"en", "it", "es", "fr"},
                             f"{activity}: must declare exactly the four released languages")

    def test_staging_does_not_duplicate_english_copy_for_all_strings(self) -> None:
        for activity in STAGED:
            english = json.loads(
                (ROOT / "activities" / activity / "locales/en.json").read_text(encoding="utf-8")
            )["strings"]
            for locale in ("es", "fr"):
                translated = json.loads(
                    (ROOT / "activities" / activity / "locales" / f"{locale}.json").read_text(
                        encoding="utf-8"
                    )
                )["strings"]
                # Grid dimensions and international emoji are not translated,
                # but at least one actual UI phrase must be distinct.
                self.assertTrue(
                    any(translated[key] != value for key, value in english.items()),
                    f"{activity}/{locale} appears copied wholesale from English"
                )


if __name__ == "__main__":
    unittest.main()
