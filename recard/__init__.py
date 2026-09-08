"""
recard - Genshin Impact character card generator.

Same usage pattern as zenka (the ZZZ card library):

    import asyncio
    import recard

    async def main():
        async with recard.Client() as client:
            result = await client.card(700000000, character="Hu Tao")
            for card in result.cards:
                card.card.save(f"{card.name}.png")

    asyncio.run(main())
"""

from .client import Card, CardResult, CharacterNotFound, Client, ShowcaseCharacter

__version__ = "0.1.2"

__all__ = [
    "Client",
    "ShowcaseCharacter",
    "Card",
    "CardResult",
    "CharacterNotFound",
    "__version__",
]
