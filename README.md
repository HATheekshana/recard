# recard

Async Genshin Impact character card generator, built the same way you'd use
[`zenka`](https://pypi.org/project/zenka/) for Zenless Zone Zero: give it a
UID, get back rendered card images.

```bash
pip install ./recard   # local build, see "Installing" below
```

```python
import asyncio
import recard

async def main():
    async with recard.Client() as client:
        # list everything currently in the player's public showcase
        showcase = await client.get_api(700000000)
        for char in showcase:
            print(char.id, char.name, char.element)

        # render one character by name
        result = await client.card(700000000, "Hu Tao")
        for card in result.cards:
            card.card.save(f"{card.name}.png")   # card.card is a PIL.Image

        # ...or by exact avatar ID, same call shape
        result = await client.card(700000000, 10000046)

        # or render the whole showcase at once
        result = await client.card(700000000)
        for card in result.cards:
            card.card.save(f"{card.name}.png")

asyncio.run(main())
```

## How it works / limitations

- Data comes from Enka.Network's **public** showcase API - no login, no
  cookies, just a UID. This means (same limitation `zenka` has for ZZZ):
  only the up-to-8 characters a player has pinned to their in-game
  showcase are available, and only their most recently synced build.
- `data/char.json`, `data/data.json`, `data/new.json`, `data/avatars.json`
  are point-in-time snapshots of Genshin's character/namecard data. Refresh
  them after a new patch:
  ```bash
  python -m recard.data.update_data
  ```
  (or just `python recard/data/update_data.py` if you're working from a
  checkout instead of an installed package).
- Custom splash art (equivalent of `!add_splash` in the original bot) is
  read from `~/.recard/custom_splash/<char_id>.(png|jpg|jpeg|webp)`.
- HoYoLAB-cookie-authenticated fallbacks (used for brand-new characters not
  yet in `char.json`, or characters not in the public showcase at all) are
  intentionally left out of this library to keep it credential-free, same
  as `zenka`. If you need that, call `cards.character_card
  .CharacterCardGenerator._lookup_character_info` / `_ensure_character_
  record` directly with your own authenticated `genshin.Client`.

## Installing

This isn't published to PyPI yet. Until then:

```bash
pip install ./recard
# or, for local editing:
pip install -e ./recard
```

Once published:

```bash
pip install recard
```

## License

MIT - see `LICENSE`.
