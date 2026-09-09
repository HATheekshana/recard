"""Fetch enriched enka-py models and adapt them for the existing renderer."""
import enka
import logging

from .net import new_session


def apply_namecards(characters, metadata):
    """Match owned characters to enka-py's metadata, without a showcase fetch."""
    for character in characters:
        entry = metadata.get(str(character.id))
        if entry is None:
            # Traveler and other multi-element avatars have composite keys.
            entry = next((value for key, value in metadata.items()
                          if str(key).startswith(f'{character.id}-')
                          and value.get('Element') == character.element.value), {})
        icon = entry.get('NamecardIcon')
        if icon:
            character.namecard = enka.gi.Namecard(ui_path=icon)


async def enrich_namecards(characters):
    # enka-py has no public character-metadata lookup method. Keep its asset
    # access isolated here so changes to the dependency need only one adapter.
    from enka.assets.gi.manager import GI_ASSETS
    try:
        async with new_session(timeout_seconds=30) as session:
            await GI_ASSETS.character_data.load(session)
        apply_namecards(characters, GI_ASSETS.character_data)
    except Exception:
        logging.getLogger('recard').warning(
            'Namecard metadata unavailable; using a neutral background. Refresh assets with client.update_assets().')


class PlayerDataProvider:
    async def fetch_player_profile(self, uid):
        # A per-request context also supports Client use without `async with`
        # and closes the connection if fetching or parsing fails.
        async with enka.GenshinClient(enka.gi.Language.ENGLISH, timeout=30) as client:
            return await client.fetch_showcase(uid)

    async def update_assets(self):
        async with enka.GenshinClient(enka.gi.Language.ENGLISH, timeout=60) as client:
            await client.update_assets()


def character_stats(character):
    """Keep fight-property ratios separate from equipment percentage points."""
    props = {int(key): stat.value for key, stat in character.stats.items()}
    element = character.element.name.capitalize()
    bonus_id = {"Pyro": 40, "Electro": 41, "Hydro": 42, "Dendro": 43,
                "Anemo": 44, "Geo": 45, "Cryo": 46, "Physical": 30}.get(element)
    weapon = character.weapon
    return {
        "char_level": character.level,
        "friendship": character.friendship_level,
        "hp": props.get(2000, 0), "atk": props.get(2001, 0),
        "def": props.get(2002, 0), "em": props.get(28, 0),
        "cr": props.get(20, 0) * 100, "cd": props.get(22, 0) * 100,
        "er": props.get(23, 0) * 100,
        "elem_bonus": props.get(bonus_id, 0) * 100,
        "element": element,
        "weapon": {
            "id": weapon.item_id, "level": weapon.level, "rarity": weapon.rarity,
            "icon_url": weapon.icon, "refinement": weapon.refinement,
            "stats": [{"prop": stat.type.value, "val": stat.value} for stat in weapon.stats],
        },
    }


def artifact_record(character):
    """Adapt equipment only; all names and icons have already been resolved."""
    return {"equipList": [
        {
            "reliquary": {"level": artifact.level + 1},
            "flat": {
                "icon_url": artifact.icon,
                "rankLevel": artifact.rarity,
                "equipType": artifact.equip_type.value,
                "reliquaryMainstat": {"mainPropId": artifact.main_stat.type.value,
                                      "statValue": artifact.main_stat.value},
                "reliquarySubstats": [
                    {"appendPropId": stat.type.value, "statValue": stat.value}
                    for stat in artifact.sub_stats
                ],
            },
        } for artifact in character.artifacts
    ]}
