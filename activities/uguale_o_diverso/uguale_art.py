"""Prepared, bounded art for Same or Different.

The cards are kit painter tiles; every picture, backdrop, FX and Momo pose is
shared library art resolved by semantic ID. A picture is scaled once per size,
mirrored with one ``transform.flip`` and turned into a shadow with two fills
when a card is first built; the finished card (tile + picture) and the
reference frame are cached per size and face in hard-bounded LRU caches, so
drawing only blits. Nothing is scaled, flipped or tinted on a frame path.
"""

from __future__ import annotations

from typing import Final

import pygame

from greia_platform.activity_controls import BodyShape, ControlArt, ControlPainter
from greia_platform.ui_core import BoundedCache

if __package__:
    from .uguale_content import PICTURES_BY_ID, REFERENCE_HEIGHT, REFERENCE_WIDTH, SIZE_STEPS, Twist
    from .uguale_model import Face
else:
    from uguale_content import PICTURES_BY_ID, REFERENCE_HEIGHT, REFERENCE_WIDTH, SIZE_STEPS, Twist
    from uguale_model import Face

HOST: Final = "momo"
INK: Final = (75, 55, 47)
CREAM: Final = (255, 251, 235)
HALO: Final = (255, 226, 138)
SHADOW: Final = (58, 66, 108)
PLAIN_SCALE: Final = 0.8
# A picture counts as lopsided (its mirror image is visibly different) above this share.
ASYMMETRY_MIN: Final = 0.16
FX_SIZES: Final[dict[str, int]] = {"sparkle": 120, "star_burst": 150, "confetti": 240}
SCENE: Final[tuple[str, ...]] = ("bg.indoor_room.wall_playroom", "bg.indoor_room.floor_wood")


class UgualeArt:
    """Own every prepared surface the renderer blits (bounded, built lazily once)."""

    def __init__(self, painter: ControlPainter, *, art: ControlArt | None = None) -> None:
        self._painter = painter
        # Content art gets its own bounded loader so it never evicts kit glyphs.
        self._art = art if art is not None else ControlArt(max_entries=96)
        self._faces: BoundedCache[tuple, pygame.Surface] = BoundedCache(40)
        self._frames: BoundedCache[tuple, pygame.Surface] = BoundedCache(8)
        self._misc: BoundedCache[tuple, pygame.Surface] = BoundedCache(16)
        self._asymmetry: dict[str, float] = {}
        self._backgrounds: BoundedCache[tuple[str, ...], pygame.Surface] = BoundedCache(2)
        self._fx: dict[str, tuple[pygame.Surface, ...]] = {}

    @property
    def loader(self) -> ControlArt:
        return self._art

    # -- pictures ---------------------------------------------------------------

    def asymmetry(self, picture_id: str) -> float:
        """Share of the shape that does not overlap its mirror image (0 = symmetric)."""

        cached = self._asymmetry.get(picture_id)
        if cached is not None:
            return cached
        value = 0.0
        picture = PICTURES_BY_ID.get(picture_id)
        image = self._art.image(picture.asset_id, 64) if picture is not None else None
        if image is not None:
            mask = pygame.mask.from_surface(image, 64)
            rects = mask.get_bounding_rects()
            if rects:
                box = rects[0].unionall(rects[1:])
                shape = image.subsurface(box).copy()
                original = pygame.mask.from_surface(shape, 64)
                flipped = pygame.mask.from_surface(pygame.transform.flip(shape, True, False), 64)
                area = max(1, original.count())
                value = 1.0 - original.overlap_area(flipped, (0, 0)) / area
        self._asymmetry[picture_id] = value
        return value

    def is_lopsided(self, picture_id: str) -> bool:
        return self.asymmetry(picture_id) >= ASYMMETRY_MIN

    def _picture(self, face: Face, side: int, scale: float) -> pygame.Surface | None:
        picture = PICTURES_BY_ID[face.picture_id]
        pixels = max(8, int(side * scale))
        image = self._art.image(picture.asset_id, pixels)
        if image is None:
            return None
        if face.mirrored or face.shadow:
            image = pygame.transform.flip(image, True, False) if face.mirrored else image.copy()
        if face.shadow:
            image.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGB_MULT)
            image.fill((*SHADOW, 0), special_flags=pygame.BLEND_RGB_ADD)
        return image

    def _scale(self, face: Face, twist: Twist) -> float:
        return SIZE_STEPS[face.size] if twist is Twist.SIZE else PLAIN_SCALE

    def card(self, size: tuple[int, int], face: Face, twist: Twist) -> pygame.Surface:
        """One choice card: cream tile + the face's picture."""

        key = (size, face, twist is Twist.SIZE)
        cached = self._faces.get(key)
        if cached is None:
            tile = self._painter.body(BodyShape.TILE, size, CREAM, lip=max(3, size[1] // 30))
            cached = tile.copy()
            side = min(size)
            image = self._picture(face, side, self._scale(face, twist))
            if image is not None:
                cached.blit(image, image.get_rect(center=(size[0] // 2, (size[1] - max(3, size[1] // 30)) // 2)))
            self._faces[key] = cached
        return cached

    def reference(self, size: int, face: Face, twist: Twist) -> pygame.Surface:
        """The reference: a dashed frame around the face's picture."""

        key = ("reference", size, face, twist is Twist.SIZE)
        cached = self._frames.get(key)
        if cached is None:
            cached = pygame.Surface((size, size), pygame.SRCALPHA)
            rect = cached.get_rect().inflate(-6, -6)
            pygame.draw.rect(cached, (255, 253, 247, 170), rect, border_radius=max(14, size // 8))
            _dashed_frame(cached, rect, INK, width=4, dash=14, gap=9)
            image = self._picture(face, size, self._scale(face, twist))
            if image is not None:
                cached.blit(image, image.get_rect(center=(size // 2, size // 2)))
            self._frames[key] = cached
        return cached

    def halo(self, size: tuple[int, int]) -> pygame.Surface:
        """Warm glow ring around a card (hints, the right card, the reference)."""

        key = ("halo", *size)
        cached = self._misc.get(key)
        if cached is None:
            width, height = size[0] + 28, size[1] + 28
            cached = pygame.Surface((width, height), pygame.SRCALPHA)
            for inset, alpha in ((0, 70), (5, 130), (10, 200)):
                pygame.draw.rect(
                    cached,
                    (*HALO, alpha),
                    pygame.Rect(inset, inset, width - 2 * inset, height - 2 * inset),
                    width=5,
                    border_radius=max(10, 30 - inset),
                )
            self._misc[key] = cached
        return cached

    # -- scenes / cast / FX -------------------------------------------------------

    def background(self, layers: tuple[str, ...] = SCENE) -> pygame.Surface:
        """Shared scene layers flattened once into one opaque frame."""

        cached = self._backgrounds.get(layers)
        if cached is not None:
            return cached
        surface = pygame.Surface((REFERENCE_WIDTH, REFERENCE_HEIGHT))
        surface.fill((207, 234, 247))
        loader = ControlArt(max_entries=len(layers) + 1)
        for asset_id in layers:
            image = loader.image(asset_id, (REFERENCE_WIDTH, REFERENCE_HEIGHT))
            if image is not None:
                surface.blit(image, (0, 0))
        loader.clear()
        if pygame.display.get_surface() is not None:
            surface = surface.convert()
        self._backgrounds[layers] = surface
        return surface

    def cast_pose(self, variant: str, height: int) -> pygame.Surface | None:
        return self._art.image(f"character.{HOST}", height, variant=variant)

    def fx_frames(self, name: str) -> tuple[pygame.Surface, ...]:
        cached = self._fx.get(name)
        if cached is not None:
            return cached
        size = FX_SIZES.get(name, 128)
        frames = []
        for variant in ("default", "frame_2", "frame_3"):
            image = self._art.image(f"fx.{name}", size, variant=variant)
            if image is not None:
                frames.append(image)
        self._fx[name] = tuple(frames)
        return self._fx[name]

    def clear(self) -> None:
        self._faces.clear()
        self._frames.clear()
        self._misc.clear()
        self._backgrounds.clear()
        self._fx.clear()


def _dashed_frame(surface: pygame.Surface, rect: pygame.Rect, color, *, width: int, dash: int, gap: int) -> None:
    """Dashed outline drawn once into a prepared surface."""

    def run(start: tuple[int, int], end: tuple[int, int]) -> None:
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = max(abs(dx), abs(dy))
        step = dash + gap
        position = 0
        while position < length:
            a = position / length
            b = min(length, position + dash) / length
            pygame.draw.line(
                surface,
                color,
                (start[0] + dx * a, start[1] + dy * a),
                (start[0] + dx * b, start[1] + dy * b),
                width,
            )
            position += step

    inset = max(10, rect.width // 14)
    left, top, right, bottom = rect.left + inset, rect.top, rect.right - inset, rect.bottom
    run((left, top), (right, top))
    run((left, bottom - 1), (right, bottom - 1))
    run((rect.left, top + inset), (rect.left, bottom - inset))
    run((rect.right - 1, top + inset), (rect.right - 1, bottom - inset))


__all__ = ["HOST", "UgualeArt"]
