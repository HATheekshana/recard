"""Optional, account-scoped HoYoLAB access. Cookies are never persisted."""
from collections.abc import Mapping
from types import SimpleNamespace as Record

from enka.gi import Element, EquipmentType, StatType


class HoYoLABError(RuntimeError):
    """Authentication, account access, or incomplete character data."""


def _number(value, *, fraction=False):
    text = str(value).strip().replace(',', '')
    percentage = text.endswith('%')
    try:
        number = float(text.rstrip('%'))
    except ValueError:
        raise HoYoLABError('HoYoLAB returned an invalid stat value.') from None
    return number / 100 if percentage and fraction else number


def _element(value):
    try:
        return Element[str(value).upper()]
    except KeyError:
        raise HoYoLABError('HoYoLAB returned an unsupported character element.') from None


def _stat(prop, value_key):
    from enka.gi import FightPropType
    try:
        kind = StatType[FightPropType(int(prop['property_type'])).name]
    except (KeyError, ValueError, TypeError):
        raise HoYoLABError('HoYoLAB returned an unsupported equipment stat.') from None
    return Record(type=kind, value=_number(prop[value_key]))


def _max_level(data):
    stage = data.get('promote_level')
    return {0: 20, 1: 40, 2: 50, 3: 60, 4: 70, 5: 80, 6: 90}.get(stage)


def roster_character(data):
    return Record(id=int(data['id']), name=data['name'],
                  element=_element(data['element']), rarity=data['rarity'])


def adapt_character(data):
    """Convert detail data to the renderer's interface, without Enka parsing.

    HoYoLAB already supplies talent bonuses and display-ready equipment stats.
    Only character percentage stats need conversion to fractions.
    """
    try:
        base = data['base']
        character = roster_character(base)
        props = {}
        for section in ('base_properties', 'extra_properties', 'element_properties', 'selected_properties'):
            for prop in data.get(section, []):
                props[int(prop['property_type'])] = Record(value=_number(prop['final'], fraction=True))
        if not all(key in props for key in (2000, 2001, 2002)):
            raise HoYoLABError('HoYoLAB did not return full HP, ATK and DEF stats for this character.')
        weapon = data['weapon']
        weapon_stats = [_stat(weapon['main_property'], 'final')]
        if weapon.get('sub_property'):
            weapon_stats.append(_stat(weapon['sub_property'], 'final'))
        character.weapon = Record(
            item_id=weapon['id'], name=weapon['name'], icon=weapon['icon'],
            level=weapon['level'], max_level=_max_level(weapon), rarity=weapon['rarity'],
            refinement=weapon['affix_level'], stats=weapon_stats)
        slots = list(EquipmentType)
        character.artifacts = []
        for relic in data.get('relics', []):
            pos = int(relic['pos'])
            if not 1 <= pos <= 5:
                raise HoYoLABError('HoYoLAB returned an invalid artifact slot.')
            character.artifacts.append(Record(
                level=relic['level'], icon=relic['icon'], rarity=relic['rarity'],
                equip_type=slots[pos - 1], main_stat=_stat(relic['main_property'], 'value'),
                sub_stats=[_stat(p, 'value') for p in relic.get('sub_property_list', [])]))
        skills = [s for s in data.get('skills', []) if s['skill_type'] == 1][:3]
        character.talents = [Record(id=s['skill_id'], level=s['level'], icon=s['icon']) for s in skills]
        character.talent_order = [s.id for s in character.talents]
        consts = sorted(data.get('constellations', []), key=lambda c: c['pos'])
        character.constellations = [Record(icon=c['icon'], unlocked=bool(c['is_actived'])) for c in consts]
        character.constellations_unlocked = sum(c.unlocked for c in character.constellations)
        character.stats = props
        character.level = base['level']
        character.max_level = _max_level(base)
        character.friendship_level = base.get('fetter', 0)
        # HoYoLAB provides its own display artwork; no showcase or local JSON
        # lookup is necessary. Keep it distinct from Enka's wide gacha artwork.
        artwork = data.get('image') or base.get('image') or base.get('icon')
        if not artwork:
            raise HoYoLABError('HoYoLAB did not return character artwork.')
        character.icon = Record(side_icon_ui_path=artwork, gacha=artwork)
        character.namecard = None
        return character
    except (KeyError, TypeError, ValueError):
        raise HoYoLABError('HoYoLAB returned incomplete or unsupported character details.') from None


class HoYoLABProvider:
    def __init__(self, cookies, *, region='os'):
        if not isinstance(cookies, Mapping) or not cookies:
            raise ValueError('cookies must be a non-empty mapping of cookie names to values.')
        if region not in ('os', 'cn'):
            raise ValueError("region must be 'os' or 'cn'.")
        self._cookies = dict(cookies)
        self._region = region

    async def fetch_player_profile(self, uid, *, roster_only=False, character_ids=None):
        try:
            import genshin
        except ImportError:
            raise HoYoLABError('Install the optional dependency with: pip install "recard[hoyolab]"') from None
        region = genshin.types.Region.CHINESE if self._region == 'cn' else genshin.types.Region.OVERSEAS
        # genshin.py uses a context-managed HTTP session for each request.
        client = genshin.Client(cookies=dict(self._cookies), region=region,
                                game=genshin.types.Game.GENSHIN, lang='en-us')
        try:
            accounts = await client.get_game_accounts()
            account = next((a for a in accounts if a.game == genshin.types.Game.GENSHIN
                            and str(a.uid) == str(uid)), None)
            if account is None:
                raise HoYoLABError('This Genshin UID is not linked to the supplied cookie account.')
            if roster_only or character_ids is None:
                roster = await client.get_genshin_characters(int(uid), lang='en-us')
                if roster_only:
                    characters = [Record(id=c.id, name=c.name, element=_element(c.element), rarity=c.rarity)
                                  for c in roster]
                    return Record(characters=characters, player=Record(nickname=account.nickname))
                character_ids = [c.id for c in roster]
            characters = []
            # Bound each detail request; selected cards fetch only their IDs.
            for offset in range(0, len(character_ids), 8):
                raw = await client.get_genshin_detailed_characters(
                    int(uid), characters=character_ids[offset:offset + 8],
                    lang='en-us', return_raw_data=True)
                characters.extend(adapt_character(c) for c in raw['list'])
            returned = {c.id for c in characters}
            if any(int(i) not in returned for i in character_ids):
                raise HoYoLABError('HoYoLAB did not return details for every requested character.')
            return Record(characters=characters, player=Record(nickname=account.nickname))
        except HoYoLABError:
            raise
        except Exception:
            # Do not expose response bodies, request objects, or cookie values
            # in user-visible exceptions. Cancellation still propagates.
            raise HoYoLABError('HoYoLAB request failed. Check cookie validity, region, privacy settings, or verification requirements.') from None
