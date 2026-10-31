"""Same or Different content: the picture pool and the five-step ladder.

Every picture is shared library art addressed by semantic ID (``prop.*``,
``creature.marine.*``); the Activity draws no subject itself. A picture's
spoken name comes from the platform's shared vocabulary bank through its
language-neutral ``noun`` id (the last segment of the art ID unless a
different concept id is given).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

REFERENCE_WIDTH: Final = 1024
REFERENCE_HEIGHT: Final = 600
STORAGE_KEY: Final = "uguale_o_diverso.progress.v1"
ROUNDS_PER_VISIT: Final = 6


@dataclass(frozen=True, slots=True)
class Picture:
    """One library picture: stable id, art ID and vocabulary noun id."""

    picture_id: str
    asset_id: str
    noun: str


def _picture(asset_id: str, noun: str | None = None) -> Picture:
    last = asset_id.rsplit(".", 1)[1]
    return Picture(last, asset_id, noun or last)


PICTURES: Final[tuple[Picture, ...]] = (
    # animals
    _picture("prop.vocab.cat"),
    _picture("prop.vocab.dog"),
    _picture("prop.vocab.lion"),
    _picture("prop.vocab.elephant"),
    _picture("prop.vocab.pig"),
    _picture("prop.vocab.frog"),
    _picture("prop.vocab.penguin"),
    _picture("prop.vocab.mouse"),
    # sea
    _picture("creature.marine.clownfish", "fish"),
    _picture("creature.marine.turtle"),
    _picture("creature.marine.octopus"),
    _picture("creature.marine.jellyfish"),
    _picture("creature.marine.seahorse"),
    _picture("creature.marine.crab"),
    _picture("creature.marine.starfish"),
    _picture("creature.marine.dolphin"),
    # food
    _picture("prop.food.apple"),
    _picture("prop.food.banana"),
    _picture("prop.food.carrot"),
    _picture("prop.vocab.grapes"),
    _picture("prop.vocab.pear"),
    _picture("prop.vocab.cake"),
    _picture("prop.vocab.pizza"),
    _picture("prop.vocab.ice_cream"),
    # vehicles
    _picture("prop.vocab.car"),
    _picture("prop.vocab.bus"),
    _picture("prop.vocab.train"),
    _picture("prop.vocab.boat"),
    _picture("prop.vocab.plane"),
    _picture("prop.vocab.rocket"),
    _picture("prop.vocab.bicycle"),
    _picture("prop.vocab.kite"),
    # nature
    _picture("prop.nature.flower"),
    _picture("prop.nature.mushroom"),
    _picture("prop.nature.sun"),
    _picture("prop.vocab.moon"),
    _picture("prop.nature.rainbow"),
    _picture("prop.nature.leaf_autumn", "leaf"),
    _picture("prop.nature.snowflake"),
)

PICTURES_BY_ID: Final[dict[str, Picture]] = {picture.picture_id: picture for picture in PICTURES}


class Twist(StrEnum):
    """What makes this rung different from the plain "find the same picture"."""

    PLAIN = "plain"  # three different pictures
    SIZE = "size"  # the same picture in three sizes
    SHADOW = "shadow"  # a shadow asks for its picture
    MIRROR = "mirror"  # the picture and its mirror image among others
    SHADOW_MIRROR = "shadow_mirror"  # a shadow among pictures and mirror images


@dataclass(frozen=True, slots=True)
class LevelSpec:
    twist: Twist
    choices: int


# Leerzone's five levels, in the same order: normal, size, shadow, mirror, combination.
LEVELS: Final[tuple[LevelSpec, ...]] = (
    LevelSpec(Twist.PLAIN, 3),
    LevelSpec(Twist.SIZE, 3),
    LevelSpec(Twist.SHADOW, 3),
    LevelSpec(Twist.MIRROR, 5),
    LevelSpec(Twist.SHADOW_MIRROR, 5),
)
MAX_LEVEL: Final = len(LEVELS) - 1

# Picture scale (fraction of the frame) for the three sizes of the size rung.
SIZE_STEPS: Final[tuple[float, ...]] = (0.42, 0.68, 0.94)

assert len({picture.picture_id for picture in PICTURES}) == len(PICTURES)
assert max(spec.choices for spec in LEVELS) + 1 <= len(PICTURES)


__all__ = [
    "LEVELS",
    "LevelSpec",
    "MAX_LEVEL",
    "PICTURES",
    "PICTURES_BY_ID",
    "Picture",
    "REFERENCE_HEIGHT",
    "REFERENCE_WIDTH",
    "ROUNDS_PER_VISIT",
    "SIZE_STEPS",
    "STORAGE_KEY",
    "Twist",
]
