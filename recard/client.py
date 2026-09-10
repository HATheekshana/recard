"""
recard.client
=============

The async `Client` you actually import and use. Modeled after zenka's
Client for ZZZ, but for Genshin Impact:

    import asyncio
    import recard

    async def main():
        async with recard.Client() as client:
            showcase = await client.get_api(700000000)
            for char in showcase:
                print(char.id, char.name)

            result = await client.card(700000000, "Hu Tao")
            # or by exact avatar ID: await client.card(700000000, 10000046)
            for card in result.cards:
                card.card.save(f"{card.name}.png")

    asyncio.run(main())

Public showcase access is the default. Supply cookies and source="hoyolab"
to render owned characters from the linked HoYoLAB account.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO
from typing import List, Optional

from PIL import Image

from .cards.character_card import CharacterCardGenerator
from .cards.chevron import ChevronCardGenerator, TexturedCardGenerator
from .services.hoyolab import HoYoLABError, HoYoLABProvider
from .services.enka import enrich_namecards
from .services.images import save_custom_image, remove_custom_image

__all__ = [
    "Client",
    "ShowcaseCharacter",
    "Card",
    "CardResult",
    "CharacterNotFound",
    "HoYoLABError",
]


def _normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name.replace("-", " ").strip().casefold())


@dataclass
class ShowcaseCharacter:
    """One character from the selected public showcase or owned roster."""
    id: int
    name: str
    element: str
    rarity: Optional[int] = None


@dataclass
class Card:
    """One rendered card. `card` is a ready-to-use Pillow Image;
    `buffer` is the same image already encoded as JPEG bytes."""
    id: int
    name: str
    card: Image.Image
    buffer: BytesIO


@dataclass
class CardResult:
    cards: List[Card] = field(default_factory=list)


class CharacterNotFound(Exception):
    """The requested character is absent from the selected source."""


class Client:
    """Async client for generating Genshin Impact character cards."""

    def __init__(self, *, cookies=None, region="os", splash_directory=None):
        self._classic = CharacterCardGenerator(splash_directory=splash_directory)
        self._hoyolab = HoYoLABProvider(cookies, region=region) if cookies is not None else None

    async def __aenter__(self) -> "Client":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def update_assets(self):
        """Refresh enka-py's cached game metadata after a game patch."""
        await self._classic.player_data_provider.update_assets()

    def set_custom_image(self, character_id, image):
        """Save a local path, encoded image bytes, or Pillow image for reuse."""
        return save_custom_image(self._classic.splash_directory, character_id, image)

    def remove_custom_image(self, character_id):
        """Remove the saved override; return whether an image was removed."""
        return remove_custom_image(self._classic.splash_directory, character_id)

    @staticmethod
    def _showcase_characters(profile):
        return [ShowcaseCharacter(
            id=c.id, name=c.name, element=c.element.name.capitalize(), rarity=c.rarity
        ) for c in profile.characters]

    async def _profile(self, uid, source, *, roster_only=False, character_ids=None):
        if source == "enka":
            return await self._classic.player_data_provider.fetch_player_profile(uid)
        if source != "hoyolab":
            raise ValueError("source must be 'enka' or 'hoyolab'.")
        if self._hoyolab is None:
            raise HoYoLABError("HoYoLAB mode requires cookies passed to recard.Client(cookies=...).")
        return await self._hoyolab.fetch_player_profile(
            uid, roster_only=roster_only, character_ids=character_ids)

    async def get_api(self, uid: int, *, source="enka") -> List[ShowcaseCharacter]:
        """List the public showcase or the authenticated account's roster."""
        profile = await self._profile(uid, source, roster_only=True)
        return self._showcase_characters(profile)

    async def card(
        self,
        uid: int,
        character: Optional[str | int] = None,
        character_id: Optional[int] = None,
        *,
        source: str = "enka",
        custom_image=None,
        style="classic",
    ) -> CardResult:
        """Generate one or more character cards for `uid`.

        `character` accepts either a name or an ID - use whichever you have:

            await client.card(uid, "Hu Tao")   # by name
            await client.card(uid, 10000046)   # by ID (same as character_id=)

        - Neither `character` nor `character_id`: renders every character
          available from the selected source.
        - `character_id` (or an int passed positionally as `character`):
          exact Enka/HoYoLAB avatar ID.
        - `character` as a string: case-insensitive name match.

        Raises `CharacterNotFound` if a specific character/character_id was
        requested and it is absent from the selected source.
        `source="hoyolab"` requires cookies and a UID linked to that account.
        `custom_image` overrides the splash for this call without saving it.
        `style="chevron"` selects the sketch layout; the default is "classic".
        """
        # A bare int passed positionally (`client.card(uid, 10000046)`) is a
        # character_id, not a name - detect that here so callers don't have
        # to remember which keyword to use.
        if isinstance(character, int) and character_id is None:
            character_id = character
            character = None

        if style not in ("classic", "chevron", "textured"):
            raise ValueError("style must be 'classic', 'chevron', or 'textured'.")
        generator = self._classic if style == "classic" else (TexturedCardGenerator if style == "textured" else ChevronCardGenerator)(
            splash_directory=self._classic.splash_directory,
            font_path=self._classic.font_path,
            player_data_provider=self._classic.player_data_provider)
        profile = await self._profile(uid, source, roster_only=True)
        showcase = self._showcase_characters(profile)
        if not showcase:
            if character is not None or character_id is not None:
                raise CharacterNotFound(
                    f"uid={uid} has no available characters from {source}"
                )
            return CardResult(cards=[])

        targets = showcase
        if character_id is not None:
            targets = [c for c in showcase if str(c.id) == str(character_id)]
        elif character is not None:
            wanted = _normalize(character)
            targets = [c for c in showcase if _normalize(c.name) == wanted]
            if not targets:
                targets = [c for c in showcase if wanted in _normalize(c.name)]

        if not targets:
            raise CharacterNotFound(
                f"Character {character or character_id!r} not found for uid={uid} in {source}"
            )

        if source == "hoyolab":
            profile = await self._profile(uid, source, character_ids=[c.id for c in targets])
            await enrich_namecards(profile.characters)

        cards: List[Card] = []
        for target in targets:
            buffer = await generator.generate_card(uid, target.id, profile=profile, custom_image=custom_image)
            image = Image.open(buffer)
            image.load()
            buffer.seek(0)
            cards.append(Card(id=target.id, name=target.name, card=image, buffer=buffer))

        return CardResult(cards=cards)
