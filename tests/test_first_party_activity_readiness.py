from __future__ import annotations

import ast
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
ACTIVITIES = ROOT / "activities"


def _call_name(node: ast.Call) -> tuple[str, ...]:
    parts: list[str] = []
    value: ast.expr = node.func
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if isinstance(value, ast.Name):
        parts.append(value.id)
    return tuple(reversed(parts))


def _entrypoints() -> tuple[Path, ...]:
    result: list[Path] = []
    for manifest_path in sorted(ACTIVITIES.glob("*/activity.toml")):
        with manifest_path.open("rb") as handle:
            raw = tomllib.load(handle)
        runtime = raw.get("runtime", {})
        if not isinstance(runtime, dict):
            continue
        entrypoint = runtime.get("entrypoint")
        if not isinstance(entrypoint, str) or not entrypoint:
            continue
        path = manifest_path.parent / entrypoint
        if path.suffix == ".py":
            result.append(path)
    return tuple(result)


def _nearest_parent(
    node: ast.AST,
    parents: dict[ast.AST, ast.AST],
    kinds: tuple[type[ast.AST], ...],
) -> ast.AST | None:
    cursor: ast.AST | None = node
    while cursor is not None:
        if isinstance(cursor, kinds):
            return cursor
        cursor = parents.get(cursor)
    return None


class FirstPartyActivityReadinessTests(unittest.TestCase):
    def test_ready_is_published_only_after_a_frame_presentation(self) -> None:
        checked: list[str] = []
        for entrypoint in _entrypoints():
            candidate_paths = [entrypoint] + [
                p for p in sorted(entrypoint.parent.glob("*.py")) if p != entrypoint
            ]
            ready_path = next(
                (
                    p
                    for p in candidate_paths
                    if "mark_activity_ready" in p.read_text(encoding="utf-8")
                ),
                None,
            )
            self.assertIsNotNone(
                ready_path,
                f"{entrypoint.parent.name} must publish mark_activity_ready in its source",
            )
            assert ready_path is not None
            source = ready_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(ready_path))
            parents: dict[ast.AST, ast.AST] = {}
            for parent in ast.walk(tree):
                for child in ast.iter_child_nodes(parent):
                    parents[child] = parent

            ready_calls = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and _call_name(node) == ("mark_activity_ready",)
            ]
            self.assertEqual(
                len(ready_calls),
                1,
                f"{ready_path.relative_to(ROOT)} must publish READY exactly once in source",
            )
            ready = ready_calls[0]

            function = _nearest_parent(
                ready,
                parents,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
            self.assertIsNotNone(
                function,
                f"{ready_path.relative_to(ROOT)} READY call must live inside its launch function",
            )
            assert isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))

            ready_loop = _nearest_parent(ready, parents, (ast.While, ast.For, ast.AsyncFor))
            self.assertIsNotNone(
                ready_loop,
                f"{ready_path.relative_to(ROOT)} READY call must be tied to its presentation loop",
            )

            presentations = [
                node
                for node in ast.walk(function)
                if isinstance(node, ast.Call)
                and _call_name(node) in {
                    ("pygame", "display", "flip"),
                    ("pygame", "display", "update"),
                }
                and _nearest_parent(
                    node, parents, (ast.While, ast.For, ast.AsyncFor)
                )
                is ready_loop
            ]
            if not presentations:
                # Thin bootstraps (e.g. acquario_magico/main.py) delegate the
                # actual flip to app._draw() which internally presents. Treat a
                # draw/present call in the same loop as presentation proxy.
                # ``_present`` is the dirty-rectangle Activities' own helper
                # that flips (full frame) or pushes just the changed regions.
                draw_calls = [
                    node
                    for node in ast.walk(function)
                    if isinstance(node, ast.Call)
                    and _call_name(node)
                    and _call_name(node)[-1] in {"_draw", "draw", "present", "_present"}
                    and _nearest_parent(
                        node, parents, (ast.While, ast.For, ast.AsyncFor)
                    )
                    is ready_loop
                ]
                if draw_calls:
                    presentations = draw_calls
            self.assertTrue(
                presentations,
                f"{ready_path.relative_to(ROOT)} publishes READY without presenting in the same loop",
            )
            self.assertLess(
                min(node.lineno for node in presentations),
                ready.lineno,
                f"{ready_path.relative_to(ROOT)} must present its first usable frame before READY",
            )
            checked.append(entrypoint.parent.name)

        self.assertEqual(
            set(checked),
            {
                "acquario_magico",
                "alfabeto_leo",
                "baia_delle_orche",
                "bosco_numeri",
                "bottega_delle_misure",
                "casa_del_dieci",
                "clinica_cuccioli",
                "colline_allegre",
                "corsa_bacche",
                "costruiamo_ponti",
                "cucciolo_mio",
                "enciclopedia_greia",
                "faccine_momo",
                "festa_delle_rime",
                "foresta_parole",
                "il_giardino_dei_numeri",
                "la_discesa_della_biglia",
                "labirinto_magico",
                "luci_di_momo",
                "memory_meraviglie",
                "mondo_contrari",
                "morbidi_mostriciattoli",
                "nanna_delle_nuvolette",
                "nascondino_bosco",
                "officina_dei_suoni",
                "orchestra_animali",
                "painting",
                "pasticceria_magica",
                "piccola_serra",
                "posta_di_leo",
                "quattro_amici",
                "quattro_stagioni",
                "shape_garden",
                "sillabe_magiche",
                "sottomarino_giramondo",
                "specchi_magici",
                "stelle_incantate",
                "storie_della_mia_voce",
                "teatrino_fiabe",
                "torre_forme",
                "treno_numeri",
                "uguale_o_diverso",
                "viaggio_delfino",
                "volo_draghetto",
                "workshop_settings",
                "writing",
            },
            "new/removed first-party Python Activities must explicitly reconcile readiness coverage",
        )


if __name__ == "__main__":
    unittest.main()
