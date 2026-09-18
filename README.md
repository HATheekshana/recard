# recard

Async Genshin Impact character cards from a public Enka showcase or a
cookie-authenticated HoYoLAB account.

This README describes the current **0.6.1** source. Python **3.10+** is required.

## Installation

Install the published package:

```bash
python -m pip install --upgrade recard
```

For owned characters outside the public showcase, install the optional HoYoLAB extra:

```bash
python -m pip install --upgrade "recard[hoyolab]"
```

To install this source version, run from the folder containing pyproject.toml:

```bash
python -m pip install .
# With HoYoLAB support:
python -m pip install ".[hoyolab]"
```

## Quick start

```python
import asyncio
import recard

async def main():
    uid = 700000000  # Replace with your Genshin UID.
    async with recard.Client() as client:
        characters = await client.get_api(uid)
        for character in characters:
            print(character.id, character.name, character.element)

        result = await client.card(uid, "Hu Tao", style="chevron")
        for card in result.cards:
            card.card.save(f"{card.id}.png")
            # card.buffer contains the same rendered image encoded as JPEG.
            # jpeg_bytes = card.buffer.getvalue()

asyncio.run(main())
```

Select by name, positional numeric ID, or character_id:

```python
result = await client.card(uid, 10000046)
result = await client.card(uid, character_id=10000046)
result = await client.card(uid)  # All available characters.
```

Names are matched without case sensitivity, with partial matching as a fallback.
A partial name can return multiple cards. Prefer exact names or IDs.

## Card designs

| Style | Layout |
| --- | --- |
| classic | Original single-character card; default. |
| chevron | Angled talent/constellation divider, namecard background and translucent information panels. |
| textured | Angled layout with a dark patterned information background and element accents. |
| team | One compact 2400 × 600 character row. Use client.team() to combine rows. |

Chevron and textured cards include artifact CV beside the main stat,
glowing unlocked constellations, lock icons for locked constellations,
and talent glow when the displayed talent level is at least 10.
Artifact CV uses substats: **2 × CRIT Rate + CRIT DMG**.

Traveler namecard backgrounds use **Mondstadt: Whistling Wind**.
Missing namecard artwork falls back to the renderer's background.

## Team cards: one to four characters

```python
import asyncio
import recard

async def main():
    async with recard.Client() as client:
        image = await client.team(700000000, ["Nahida", "Yelan"])
        image.save("team.jpg", quality=95)

asyncio.run(main())
```

The result is one Pillow image, with rows in your requested order.
Width is 2400 pixels; height is 600 multiplied by the character count.
One character produces one row, with no empty slots for the other three.

Each row uses large splash art, the character name below it, a darkened namecard
background, and translucent artifact, weapon and stat panels.
Choose 1–4 distinct characters. Invalid counts, duplicate characters or
ambiguous names raise ValueError.

## HoYoLAB: characters outside the showcase

```python
import asyncio
import os
import recard

async def main():
    uid = 700000000  # Must belong to the cookie account.
    cookies = {
        "ltuid_v2": os.environ["LTUID_V2"],
        "ltoken_v2": os.environ["LTOKEN_V2"],
    }
    async with recard.Client(cookies=cookies) as client:
        roster = await client.get_api(uid, source="hoyolab")
        result = await client.card(
            uid, "Hu Tao", source="hoyolab", style="textured"
        )
        for card in result.cards:
            card.card.save(f"{card.id}.png")

        team = await client.team(
            uid, ["Nahida", "Yelan"], source="hoyolab"
        )
        team.save("hoyolab-team.png")

asyncio.run(main())
```

source="enka" is always the default, even when cookies are supplied.
Use source="hoyolab" explicitly for the owned roster.
Use region="cn" for Miyoushe; the default region is "os".

The library checks that the UID belongs to the authenticated account.
Cookies are held in memory; the library does not save them to disk.
A multi-user bot should use each requesting user's own cookies.
Requesting the entire owned roster can take longer than selecting one character.

## Custom artwork

Local image paths, encoded image bytes and Pillow images are accepted.

```python
async with recard.Client(splash_directory="custom_splash") as client:
    # Save a reusable override by character ID.
    client.set_custom_image(10000046, "hu-tao.png")

    # Override this call without changing the saved image.
    result = await client.card(
        uid, 10000046, style="chevron", custom_image="portrait.webp"
    )

    # Mapping keys must match the names or IDs used in the character list.
    team = await client.team(
        uid, [10000046, 10000060],
        custom_images={10000046: "hu-tao.png", 10000060: "yelan.png"},
    )
    team.save("custom-team.png")

    client.remove_custom_image(10000046)
```

Default directory: ~/.recard/custom_splash.
ID-named PNG, JPG, JPEG and WebP files are recognized.
Saved overrides are normalized to PNG.
Priority: per-call override, saved custom image, official artwork.
An override supplied to card() applies to every character selected by that call.
Use a separate splash directory per user in a multi-user bot.

## Return values and errors

- get_api(): list of ShowcaseCharacter objects with id, name, element and rarity.
- card(): CardResult with a cards list. Each Card has id, name, card
  (Pillow image) and buffer (JPEG BytesIO).
- team(): a single Pillow image.
- CharacterNotFound: the requested character is unavailable in the selected source.
- HoYoLABError: missing/invalid cookies, account mismatch or authenticated data failure.
- ValueError: invalid source, style or team selection.

An empty showcase returns an empty list or CardResult when no specific
character was requested. Network and parsing failures can propagate to callers.

## Game metadata and updates

Character metadata comes from enka-py; the old bundled character/avatar metadata
JSON files are no longer required. Initial asset downloads need internet access
and a writable working directory for .enka_py/assets.

Refresh metadata after a game update:

```python
async with recard.Client() as client:
    await client.update_assets()
```

Or run:

```bash
python -m recard.data.update_data
```

New content depends on upstream data availability. Metadata refresh does not
upgrade the installed recard package.

## Development

From the source root:

```bash
python -m pip install -e ".[hoyolab]"
python -m unittest discover -s tests -v
```

HoYoLAB tests use mocked authenticated responses; they are not proof of live
cookie access. Card generation requires network access for uncached data/artwork.

## License

The code in this repository is MIT-licensed - see `LICENSE`.

**Note on bundled assets:** `recard/assets/` ships
fonts, icons, and character art from Genshin Impact,
© COGNOSPHERE PTE. LTD. / HoYoverse. These are included for card
rendering purposes only, are not covered by this project's MIT license,
and all rights to them remain with their original owner. This project
is an unofficial fan tool and is not affiliated with or endorsed by
HoYoverse.

The enka-py dependency has its own GPL-3.0 license; see its repository for details.
