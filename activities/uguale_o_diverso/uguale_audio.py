"""Approved speech plus small synthesized effects for Same or Different.

Speech uses only recorded, approved clips and is never required:

* picture names from the platform's shared vocabulary audio bank
  (``shared_vocab_audio_path``; the package carries no noun clips) with the
  usual locale -> base -> English fallback; a name without a recording stays
  silent;
* Momo's shared takes (``ready.go``, ``praise.general``, ``celebrate.success``,
  ``encourage.retry``, ``encourage.progress``) from the shared character
  library.

The Activity ships no new voice line: how to play is shown (the reference
bounces, Momo points, the right card glows), never only said. Effects (tap,
chime, gentle miss, whoosh, fanfare) are synthesized once, after the first
frame. Every call fails soft without a mixer.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import random
from typing import Final, Iterable

import pygame

from greia_platform.localization import shared_character_audio_path, shared_vocab_audio_path
from greia_platform.pygame_audio import (
    DeferredSoundBank,
    chord_sound,
    current_pcm16_mixer_spec,
    fanfare_sound,
    sweep_sound,
)

SPEECH_CHANNEL: Final = 0
FIRST_SFX_CHANNEL: Final = 2
LAST_SFX_CHANNEL: Final = 4
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
HOST: Final = "momo"
MOMO_CUES: Final = ("ready.go", "celebrate.success", "encourage.retry", "encourage.progress", "praise.general")
NAME_CACHE_LIMIT: Final = 12


class UgualeAudio:
    """Own the sound bank and speech for one Same or Different visit."""

    def __init__(
        self,
        *,
        locale: str = "en",
        project_root: Path = PROJECT_ROOT,
        rng: random.Random | None = None,
    ) -> None:
        self.locale = locale.split("-")[0]
        self._project_root = project_root
        self._rng = rng if rng is not None else random.Random()
        self._sounds = DeferredSoundBank()
        self._momo: dict[str, list[pygame.mixer.Sound]] = {}
        self._names: OrderedDict[str, pygame.mixer.Sound | None] = OrderedDict()
        self._available = False
        self.last_speech: str | None = None
        try:
            if pygame.mixer.get_init() is not None:
                pygame.mixer.set_num_channels(max(pygame.mixer.get_num_channels(), LAST_SFX_CHANNEL + 1))
                self._build_sounds()
                self._load_momo()
                self._available = True
        except (pygame.error, RuntimeError, OSError):
            self._available = False

    # -- speech -------------------------------------------------------------

    def prepare_names(self, nouns: Iterable[str]) -> None:
        """Decode the picture-name clips of the coming round once (bounded)."""

        if not self._available:
            return
        for noun in nouns:
            if noun in self._names:
                self._names.move_to_end(noun)
                continue
            self._names[noun] = self._load_name(noun)
            while len(self._names) > NAME_CACHE_LIMIT:
                self._names.popitem(last=False)

    def say_name(self, noun: str) -> bool:
        """Speak the picture's name; returns False (silent) without a recording."""

        self.last_speech = f"noun.{noun}"
        if not self._available:
            return False
        if noun not in self._names:
            self.prepare_names((noun,))
        return self._speak(self._names.get(noun))

    def momo(self, cue: str) -> bool:
        """Play one of Momo's approved shared takes (random variant)."""

        self.last_speech = cue
        takes = self._momo.get(cue)
        if not self._available or not takes:
            return False
        return self._speak(self._rng.choice(takes))

    def speech_busy(self) -> bool:
        if not self._available:
            return False
        try:
            return pygame.mixer.Channel(SPEECH_CHANNEL).get_busy()
        except (pygame.error, RuntimeError):
            return False

    def stop_speech(self) -> None:
        if not self._available:
            return
        try:
            pygame.mixer.Channel(SPEECH_CHANNEL).stop()
        except (pygame.error, RuntimeError):
            return

    def _speak(self, sound: pygame.mixer.Sound | None) -> bool:
        if sound is None:
            return False
        try:
            pygame.mixer.Channel(SPEECH_CHANNEL).play(sound)
        except (pygame.error, RuntimeError):
            return False
        return True

    # -- effects ------------------------------------------------------------

    def play(self, name: str) -> None:
        if not self._available:
            return
        sound = self._sounds.get(name)
        if sound is None:
            return
        try:
            for index in range(FIRST_SFX_CHANNEL, LAST_SFX_CHANNEL + 1):
                channel = pygame.mixer.Channel(index)
                if not channel.get_busy():
                    channel.play(sound)
                    return
            pygame.mixer.Channel(FIRST_SFX_CHANNEL).play(sound)
        except (pygame.error, RuntimeError):
            return

    # -- loading ------------------------------------------------------------

    def _load_name(self, noun: str) -> pygame.mixer.Sound | None:
        try:
            path = shared_vocab_audio_path(self._project_root, noun, self.locale)
        except Exception:
            return None
        if path is None:
            return None
        try:
            return pygame.mixer.Sound(str(path))
        except (pygame.error, OSError):
            return None

    def _load_momo(self) -> None:
        for cue in MOMO_CUES:
            first = shared_character_audio_path(self._project_root, HOST, cue, self.locale)
            if first is None:
                continue
            # Sibling takes of the same family in the same accepted folder.
            prefix = first.name.split("__")
            pattern = "__".join(prefix[:3]) + "__*.wav"
            takes: list[pygame.mixer.Sound] = []
            for path in sorted(first.parent.glob(pattern))[:3]:
                try:
                    takes.append(pygame.mixer.Sound(str(path)))
                except (pygame.error, OSError):
                    continue
            if takes:
                self._momo[cue] = takes

    def _build_sounds(self) -> None:
        spec = current_pcm16_mixer_spec()
        if spec is None:
            return
        rate, channels = spec
        self._sounds.define("tap", lambda: sweep_sound(rate, channels, 0.09, 700.0, 1100.0, 5200))
        self._sounds.define("match", lambda: chord_sound(rate, channels, (659.25, 783.99, 1046.5), 0.42))
        self._sounds.define("miss", lambda: sweep_sound(rate, channels, 0.2, 420.0, 330.0, 6000))
        self._sounds.define("whoosh", lambda: sweep_sound(rate, channels, 0.26, 900.0, 1500.0, 3800))
        self._sounds.define("hint", lambda: chord_sound(rate, channels, (880.0, 1318.5), 0.5))
        self._sounds.define("fanfare", lambda: fanfare_sound(rate, channels))


__all__ = ["HOST", "MOMO_CUES", "UgualeAudio"]
