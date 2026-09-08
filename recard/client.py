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

Only characters the player has pinned to their public Enka.Network
showcase (max 8 in-game) are available - the same limitation every
Enka-based tool (including zenka for ZZZ) has, since it's all read from
the same public, no-login API.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO
from typing import List, Optional

from PIL import Image

from .cards.character_card import CharacterCardGenerator

__all__ = [
    "Client",
    "ShowcaseCharacter",
    "Card",
    "CardResult",
    "CharacterNotFound",
]


def _normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name.replace("-", " ").strip().casefold())


@dataclass
class ShowcaseCharacter:
    """One character pinned to a player's public showcase."""
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
    """Raised by Client.card() when the requested character isn't in the
    player's showcase (or the uid has no public showcase at all)."""


class Client:
    """Async client for generating Genshin Impact character cards."""

    def __init__(self):
        self._classic = CharacterCardGenerator()

    async def __aenter__(self) -> "Client":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def get_api(self, uid: int) -> List[ShowcaseCharacter]:
        """Fetch a player's public showcase: nickname + pinned characters.

        Returns an empty list if the uid has no public showcase, or Enka
        can't be reached.
        """
        profile = await self._classic.player_data_provider.fetch_player_profile(uid)
        if not profile or not profile.get("avatarInfoList"):
            return []

        results: List[ShowcaseCharacter] = []
        for entry in profile["avatarInfoList"]:
            char_id = entry.get("avatarId")
            if char_id is None:
                continue
            try:
                info = await self._classic._lookup_character_info(char_id, uid)
            except Exception:
                # Unknown/very new character and no live HoYoLAB fallback
                # available (needs cookies) - skip it rather than fail the
                # whole showcase listing.
                continue
            results.append(
                ShowcaseCharacter(
                    id=char_id,
                    name=info.get("name", "Unknown"),
                    element=info.get("element", "Anemo"),
                    rarity=info.get("rarity"),
                )
            )
        return results

    async def card(
        self,
        uid: int,
        character: Optional[str] = None,
        character_id: Optional[int] = None,
    ) -> CardResult:
        """Generate one or more character cards for `uid`.

        `character` accepts either a name or an ID - use whichever you have:

            await client.card(uid, "Hu Tao")   # by name
            await client.card(uid, 10000046)   # by ID (same as character_id=)

        - Neither `character` nor `character_id`: renders every showcased
          character.
        - `character_id` (or an int passed positionally as `character`):
          exact Enka/HoYoLAB avatar ID.
        - `character` as a string: case-insensitive name match.

        Raises `CharacterNotFound` if a specific character/character_id was
        requested and it isn't in the showcase.
        """
        # A bare int passed positionally (`client.card(uid, 10000046)`) is a
        # character_id, not a name - detect that here so callers don't have
        # to remember which keyword to use.
        if isinstance(character, int) and character_id is None:
            character_id = character
            character = None

        generator = self._classic
        showcase = await self.get_api(uid)
        if not showcase:
            if character or character_id:
                raise CharacterNotFound(
                    f"uid={uid} has no public showcase (or it couldn't be reached)"
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
                f"Character {character or character_id!r} not found in uid={uid}'s showcase"
            )

        cards: List[Card] = []
        for target in targets:
            buffer = await generator.generate_card(uid, target.id)
            image = Image.open(buffer)
            image.load()
            buffer.seek(0)
            cards.append(Card(id=target.id, name=target.name, card=image, buffer=buffer))

        return CardResult(cards=cards)
