"""Same or Different (Uguale o Diverso) — thin Greia composition root.

Build the collaborators (resources, audio, storage-backed progress, events,
canvas) and enter the Activity lifecycle. The real work lives in
:mod:`uguale_app` (flow), :mod:`uguale_model` (rules), :mod:`uguale_render`
and :mod:`uguale_art` (presentation), :mod:`uguale_controls` (shared control
kit), :mod:`uguale_audio`, :mod:`uguale_services` and :mod:`uguale_content`.
"""

from __future__ import annotations

from pathlib import Path
import random

import pygame

from greia_platform.activity_api import get_profile_locale
from greia_platform.localization import LocalizedResources, activity_resources
from greia_platform.pygame_canvas import PygameReferenceCanvas
from greia_platform.typography import GreiaTypography

if __package__:
    from .uguale_app import UgualeApp
    from .uguale_audio import UgualeAudio
    from .uguale_content import LEVELS, REFERENCE_HEIGHT, REFERENCE_WIDTH
    from .uguale_services import GreiaUgualeEvents, GreiaUgualeProgress
else:
    from uguale_app import UgualeApp
    from uguale_audio import UgualeAudio
    from uguale_content import LEVELS, REFERENCE_HEIGHT, REFERENCE_WIDTH
    from uguale_services import GreiaUgualeEvents, GreiaUgualeProgress

__all__ = ["LEVELS", "REFERENCE_HEIGHT", "REFERENCE_WIDTH", "UgualeApp", "UgualeAudio", "main"]


def _resources() -> LocalizedResources | None:
    try:
        return activity_resources(Path(__file__).resolve().parent, requested_locale=get_profile_locale())
    except Exception:
        return None


def main() -> int:
    pygame.init()
    screen = pygame.display.get_surface()
    if screen is None:
        screen = pygame.display.set_mode((REFERENCE_WIDTH, REFERENCE_HEIGHT), pygame.RESIZABLE)
    pygame.mouse.set_visible(True)

    resources = _resources()
    locale = resources.context.selected.language if resources is not None else "en"
    rng = random.Random()
    app = UgualeApp(
        screen=screen,
        canvas=PygameReferenceCanvas(screen, hires=True),
        typography=GreiaTypography(),
        resources=resources,
        audio=UgualeAudio(locale=locale, rng=rng),
        progress=GreiaUgualeProgress(),
        events=GreiaUgualeEvents(),
        rng=rng,
    )
    try:
        return app.run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())
