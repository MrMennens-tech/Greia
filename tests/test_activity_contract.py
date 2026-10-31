from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from greia_platform.activities import ActivityRegistry, ActivityValidationError, RuntimeCatalogue
from greia_platform.trust import ActivitySource, PackageTrust

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = PROJECT_ROOT / "runtime" / "child-runtime.toml"


class ActivityContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = RuntimeCatalogue.load(RUNTIME_PATH)

    def test_sample_activities_are_discovered_from_built_in_source(self) -> None:
        source = ActivitySource(
            PROJECT_ROOT / "activities",
            trust=PackageTrust.BUILT_IN,
            source_id="builtin",
        )
        activities = ActivityRegistry([source], self.runtime).discover()
        self.assertEqual(
            [activity.activity_id for activity in activities],
            [
                "org.greia.acquario-magico",
                "org.greia.alfabeto-leo",
                "org.greia.baia-delle-orche",
                "org.greia.bosco-numeri",
                "org.greia.bottega-delle-misure",
                "org.greia.casa-del-dieci",
                "org.greia.clinica-cuccioli",
                "org.greia.colline-allegre",
                "org.greia.corsa-bacche",
                "org.greia.costruiamo-ponti",
                "org.greia.cucciolo-mio",
                "org.greia.enciclopedia",
                "org.greia.faccine-momo",
                "org.greia.festa-delle-rime",
                "org.greia.foresta-parole",
                "org.greia.il-giardino-dei-numeri",
                "org.greia.la-discesa-della-biglia",
                "org.greia.labirinto-magico",
                "org.greia.luci-di-momo",
                "org.greia.memory-meraviglie",
                "org.greia.mondo-contrari",
                "org.greia.morbidi-mostriciattoli",
                "org.greia.nanna-delle-nuvolette",
                "org.greia.nascondino-bosco",
                "org.greia.officina-dei-suoni",
                "org.greia.orchestra-animali",
                "org.greia.painting",
                "org.greia.pasticceria-magica",
                "org.greia.piccola-serra",
                "org.greia.posta-di-leo",
                "org.greia.quattro-amici",
                "org.greia.quattro-stagioni",
                "org.greia.shape-garden",
                "org.greia.sillabe-magiche",
                "org.greia.sottomarino-giramondo",
                "org.greia.specchi-magici",
                "org.greia.stelle-incantate",
                "org.greia.storie-della-mia-voce",
                "org.greia.teatrino-fiabe",
                "org.greia.torre-forme",
                "org.greia.treno-numeri",
                "org.greia.uguale-o-diverso",
                "org.greia.viaggio-delfino",
                "org.greia.volo-draghetto",
                "org.greia.workshop-settings",
                "org.greia.writing",
            ],
        )
        by_id = {activity.activity_id: activity for activity in activities}
        self.assertEqual(by_id["org.greia.shape-garden"].legacy_ids, ("shape_garden",))
        self.assertEqual(by_id["org.greia.shape-garden"].icon_id, "package:assets/icon.png")
        self.assertEqual(
            by_id["org.greia.shape-garden"].launcher_categories,
            ("create", "learn"),
        )
        self.assertEqual(
            by_id["org.greia.workshop-settings"].launcher_categories,
            ("my_greia",),
        )
        self.assertIn(
            "customization.manage",
            by_id["org.greia.workshop-settings"].requested_permissions,
        )

    def test_external_package_cannot_claim_legacy_alias(self) -> None:
        with self._copy_sample(keep_legacy_alias=True) as root:
            with self.assertRaisesRegex(
                ActivityValidationError,
                "legacy Activity aliases require built-in",
            ):
                ActivityRegistry([root.parent], self.runtime).validate_package(root)

    def test_launcher_categories_are_bounded_separately_from_education_tags(self) -> None:
        with self._copy_sample() as root:
            manifest = (root / "activity.toml").read_text(encoding="utf-8")
            manifest = manifest.replace(
                'categories = ["create", "learn"]',
                'categories = ["create", "play", "learn", "explore", "my_greia"]',
                1,
            )
            (root / "activity.toml").write_text(manifest, encoding="utf-8")
            with self.assertRaisesRegex(ActivityValidationError, "at most four"):
                ActivityRegistry([root.parent], self.runtime).validate_package(root)

    def test_executable_file_is_rejected(self) -> None:
        with self._copy_sample() as root:
            payload = root / "payload"
            payload.write_text("not executable code", encoding="utf-8")
            payload.chmod(0o755)
            with self.assertRaisesRegex(ActivityValidationError, "executable activity files"):
                ActivityRegistry([root.parent], self.runtime).validate_package(root)

    def test_unparseable_python_source_is_rejected(self) -> None:
        with self._copy_sample() as root:
            module = root / "broken_module.py"
            module.write_text("def broken(:\n    return cached        max_width = 470\n", encoding="utf-8")
            with self.assertRaisesRegex(ActivityValidationError, "cannot parse Python source"):
                ActivityRegistry([root.parent], self.runtime).validate_package(root)

    def test_entrypoint_escape_is_rejected(self) -> None:
        with self._copy_sample() as root:
            manifest = (root / "activity.toml").read_text(encoding="utf-8")
            manifest = manifest.replace('entrypoint = "main.py"', 'entrypoint = "../main.py"')
            (root / "activity.toml").write_text(manifest, encoding="utf-8")
            with self.assertRaisesRegex(ActivityValidationError, "safe relative path"):
                ActivityRegistry([root.parent], self.runtime).validate_package(root)

    def test_symlink_is_rejected(self) -> None:
        with self._copy_sample() as root:
            target = root / "linked.py"
            try:
                target.symlink_to(root / "main.py")
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(ActivityValidationError, "symlinks are forbidden"):
                ActivityRegistry([root.parent], self.runtime).validate_package(root)

    def test_unknown_capability_is_rejected(self) -> None:
        with self._copy_sample() as root:
            manifest = (root / "activity.toml").read_text(encoding="utf-8")
            manifest = manifest.replace(
                'required_capabilities = ["display", "pointer"]',
                'required_capabilities = ["display", "kernel.root"]',
            )
            (root / "activity.toml").write_text(manifest, encoding="utf-8")
            with self.assertRaisesRegex(ActivityValidationError, "unknown Activity capabilities"):
                ActivityRegistry([root.parent], self.runtime).validate_package(root)

    def test_duplicate_required_capabilities_are_rejected(self) -> None:
        with self._copy_sample() as root:
            manifest = (root / "activity.toml").read_text(encoding="utf-8")
            manifest = manifest.replace(
                'required_capabilities = ["display", "pointer"]',
                'required_capabilities = ["display", "display"]',
            )
            (root / "activity.toml").write_text(manifest, encoding="utf-8")
            with self.assertRaisesRegex(ActivityValidationError, "must not contain duplicates"):
                ActivityRegistry([root.parent], self.runtime).validate_package(root)

    def test_api_mismatch_is_rejected(self) -> None:
        with self._copy_sample() as root:
            manifest = (root / "activity.toml").read_text(encoding="utf-8")
            manifest = manifest.replace('api_version = "0.1"', 'api_version = "9.9"')
            (root / "activity.toml").write_text(manifest, encoding="utf-8")
            with self.assertRaisesRegex(ActivityValidationError, "does not match platform"):
                ActivityRegistry([root.parent], self.runtime).validate_package(root)

    def test_discovery_token_changes_when_manifest_changes(self) -> None:
        with self._copy_sample() as root:
            registry = ActivityRegistry([root.parent], self.runtime)
            before = registry.discovery_token()
            manifest = root / "activity.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            self.assertNotEqual(before, registry.discovery_token())

    def _copy_sample(self, *, keep_legacy_alias: bool = False):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name) / "shape_garden"
        shutil.copytree(PROJECT_ROOT / "activities" / "shape_garden", root)
        if not keep_legacy_alias:
            manifest = root / "activity.toml"
            text = manifest.read_text(encoding="utf-8").replace(
                'legacy_ids = ["shape_garden"]\n',
                'legacy_ids = []\n',
            )
            manifest.write_text(text, encoding="utf-8")

        class Context:
            def __enter__(self_nonlocal):
                return root

            def __exit__(self_nonlocal, *args: object):
                temporary.cleanup()

        return Context()


if __name__ == "__main__":
    unittest.main()
