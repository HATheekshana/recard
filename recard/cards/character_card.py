import asyncio
import logging
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps, ImageChops, ImageEnhance, ImageFont

from .build import draw_build_column
from .artifacts import draw_horizontal_artifacts
from .watermark import apply_watermark
from ..services.enka import PlayerDataProvider, character_stats, artifact_record
from ..services.net import new_session
from ..services.images import load_custom_image

_PKG_ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger("recard")

W_STAT_ICONS = {
    "FIGHT_PROP_BASE_ATTACK": f"{_PKG_ROOT}/assets/icons/atk.png",
    "FIGHT_PROP_CHARGE_EFFICIENCY": f"{_PKG_ROOT}/assets/icons/er.png",
    "FIGHT_PROP_ELEMENT_MASTERY": f"{_PKG_ROOT}/assets/icons/em.png",
    "FIGHT_PROP_CRITICAL": f"{_PKG_ROOT}/assets/icons/cr.png",
    "FIGHT_PROP_CRITICAL_HURT": f"{_PKG_ROOT}/assets/icons/cd.png",
    "FIGHT_PROP_ATTACK_PERCENT": f"{_PKG_ROOT}/assets/icons/atk.png",
    "FIGHT_PROP_HP_PERCENT": f"{_PKG_ROOT}/assets/icons/hp.png",
    "FIGHT_PROP_DEFENSE_PERCENT": f"{_PKG_ROOT}/assets/icons/def.png",
}

def draw_text_with_shadow(draw, text, position, font_path, font_size, text_color=(255, 255, 255, 255), shadow_color=(0, 0, 0, 180), anchor="mm", shadow_offset=(2, 2)):
    font = ImageFont.truetype(font_path, font_size)
    shadow_position = (position[0] + shadow_offset[0], position[1] + shadow_offset[1])
    draw.text(shadow_position, text, font=font, fill=shadow_color, anchor=anchor)
    draw.text(position, text, font=font, fill=text_color, anchor=anchor)


def paste_splash_left(ui_layer, splash_image, size, left_align=False):
    """Paste a splash image into the left side of the card.

    left_align controls sizing/positioning:
      - False (default): resize to full card height, then crop a
        760px-wide slice from the horizontal *center*, with a 160px
        fade-out on the right edge. This matches enka.network's official
        gacha splash art, which is wide and keeps the character centered.
      - True: custom user-supplied splash (from custom_splash/). Resized
        directly to a fixed 730x890, pasted flush at x=0, with a 50px
        fade-out on the right edge to blend into the background. Custom
        splashes aren't framed the same way as the official art, so
        centering/cropping them shifts the subject to the right of where
        it should be - this keeps them flush at x=0 as expected.
    """
    card_width, card_height = size

    if left_align:
        left_width, fade_width = 730, 150
        # Cover-crop (not stretch) to left_width x card_height so the
        # custom image's aspect ratio is preserved - scale up until it
        # fills the box, then crop the overflow off centered.
        splash_image = ImageOps.fit(splash_image, (left_width, card_height), method=Image.Resampling.LANCZOS)
    else:
        left_width, fade_width = 760, 160
        scale = card_height / splash_image.height
        splash_image = splash_image.resize((int(splash_image.width * scale), card_height), Image.Resampling.LANCZOS)
        crop_x0 = (splash_image.width - left_width) // 2
        splash_image = splash_image.crop((crop_x0, 0, crop_x0 + left_width, card_height))

    mask = Image.new("L", (left_width, card_height), 255)
    draw = ImageDraw.Draw(mask)
    for index in range(fade_width):
        draw.line([(left_width - fade_width + index, 0), (left_width - fade_width + index, card_height)], fill=int(255 * (1 - index / fade_width)))

    splash_image.putalpha(ImageChops.multiply(splash_image.getchannel("A"), mask))
    ui_layer.paste(splash_image, (0, 0), splash_image)
    return ui_layer


def namecard_urls(character):
    # Mondstadt: Whistling Wind (210024), for Aether and Lumine in all elements.
    if int(character.id) in (10000005, 10000007):
        full = "https://enka.network/ui/UI_NameCardPic_Md_P.png"
    elif character.namecard:
        full = character.namecard.full
    else:
        return []
    return [full.replace("NameCardPic", "NameCardBanner"), full]


class CharacterCardGenerator:
    def __init__(self, splash_directory=None, font_path=None, player_data_provider=None):
        self.splash_directory = Path(splash_directory) if splash_directory is not None else Path.home() / ".recard" / "custom_splash"
        self.font_path = str(font_path or _PKG_ROOT / "assets/fonts/Genshin_Impact.ttf")
        self.player_data_provider = player_data_provider or PlayerDataProvider()

    async def _load_custom_splash(self, char_id):
        for extension in (".png", ".jpg", ".jpeg", ".webp"):
            custom_file = self.splash_directory / f"{char_id}{extension}"
            if custom_file.exists():
                with Image.open(custom_file) as image:
                    return image.convert("RGBA")
        return None

    async def _load_image(self, session, url):
        if not url:
            return None
        try:
            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    return None
                return Image.open(BytesIO(await response.read())).convert("RGBA")
        except Exception:
            return None

    async def generate_card(self, uid, char_id, *, profile=None, custom_image=None):
        if profile is None:
            profile = await self.player_data_provider.fetch_player_profile(uid)
        character = next((c for c in profile.characters if str(c.id) == str(char_id)), None)
        if character is None:
            raise RuntimeError(f"Character {char_id} is not in uid={uid}'s public showcase")
        if character.icon is None or not character.icon.side_icon_ui_path or not character.name:
            raise RuntimeError(f"Missing Enka assets for character {char_id}; run await client.update_assets()")

        talents_by_id = {talent.id: talent for talent in character.talents}
        talents = [talents_by_id[i] for i in character.talent_order if i in talents_by_id][:3]
        build_data = {
            "talents": [talent.level for talent in talents],
            "cons_count": character.constellations_unlocked,
            "cons_unlocked": [const.unlocked for const in character.constellations],
        }
        async with new_session() as session:
            talent_icons = await asyncio.gather(*[self._load_image(session, t.icon) for t in talents])
            constellation_icons = await asyncio.gather(*[self._load_image(session, c.icon) for c in character.constellations])
        stats = character_stats(character)
        avatar_record = artifact_record(character)
        character_name = character.name
        character_level = stats.get("char_level", 1)
        friendship_level = stats.get("friendship", 1)
        target_size = (1875, 890)
        font_small = ImageFont.truetype(self.font_path, 20)

        async with new_session() as session:
            custom_splash = load_custom_image(custom_image) if custom_image is not None else await self._load_custom_splash(char_id)
            splash_image = custom_splash or await self._load_image(session, character.icon.gacha)
            background_url = namecard_urls(character)
            background_image = None
            for url in background_url:
                background_image = await self._load_image(session, url)
                if background_image:
                    break

            weapon_image = await self._load_image(session, character.weapon.icon)

            if not background_image:
                background_image = Image.new("RGBA", target_size, (30, 30, 45, 255))

            background_image = ImageOps.fit(background_image, target_size, method=Image.Resampling.LANCZOS).convert("RGBA")
            background_image = ImageEnhance.Brightness(background_image).enhance(0.45)
            ui_layer = Image.new("RGBA", target_size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(ui_layer)

            if splash_image:
                # Custom splashes (from custom_splash/) are left-aligned so
                # they sit flush at x=0 instead of being cropped from the
                # center like enka.network's official gacha splash art.
                ui_layer = paste_splash_left(ui_layer, splash_image, target_size, left_align=bool(custom_splash))

            # Character name, then the player nickname placed right after it
            # (measured, not a fixed x) so the two never overlap regardless of
            # how long the character's name is.
            name_font_size = 36
            name_font = ImageFont.truetype(self.font_path, name_font_size)
            name_width = draw.textlength(character_name, font=name_font)
            draw_text_with_shadow(draw, text=character_name, position=(50, 50), font_path=self.font_path, font_size=name_font_size, anchor="lm")
            draw_text_with_shadow(draw, text=profile.player.nickname, position=(50 + name_width + 20, 52), font_path=self.font_path, font_size=24, text_color=(205, 205, 215, 255), anchor="lm")
            level_label = f"Lvl: {character_level}" + (f"/{character.max_level}" if character.max_level else "")
            draw_text_with_shadow(draw, text=level_label, position=(50, 90), font_path=self.font_path, font_size=24, anchor="lm")
            draw_text_with_shadow(draw, text=f"Friendship: {friendship_level}", position=(50, 125), font_path=self.font_path, font_size=24, anchor="lm")

            # Shared left edge for the whole right-hand panel so the weapon
            # header lines up with the stat list directly beneath it.
            panel_x = 950
            weapon_text_x = panel_x + 160

            weapon_position = (panel_x, 18)
            weapon_stats = []
            if weapon_image:
                weapon_icon_resized = ImageOps.contain(weapon_image, (135, 135))
                ui_layer.paste(weapon_icon_resized, weapon_position, weapon_icon_resized)
                draw_text_with_shadow(draw, character.weapon.name, (weapon_text_x, 45), self.font_path, 30, anchor="lm")
                refinement = stats["weapon"].get("refinement", 1)
                weapon_level = stats["weapon"].get("level", 1)
                max_level = character.weapon.max_level
                level_text = f"R{refinement}   Lv.{weapon_level}" + (f"/{max_level}" if max_level else "")
                draw_text_with_shadow(draw, level_text, (weapon_text_x, 88), self.font_path, 22, anchor="lm")
                weapon_stats = stats["weapon"].get("stats", [])

            star_icon_path = f"{_PKG_ROOT}/assets/icons/stars/Star{stats['weapon'].get('rarity', 5)}.png"
            try:
                star_image = Image.open(star_icon_path).convert("RGBA").resize((120, 34), Image.Resampling.LANCZOS)
                ui_layer.paste(star_image, (panel_x + 8, 150), star_image)
            except Exception as error:
                logger.warning("CharacterCardGenerator: error loading star image %s: %s", star_icon_path, error)

            stat_x_start = weapon_text_x
            stat_y = 108
            for index, stat in enumerate(weapon_stats):
                current_x = stat_x_start + index * 125
                draw.rounded_rectangle([current_x, stat_y, current_x + 115, stat_y + 38], radius=5, fill=(255, 255, 255, 100))
                stat_icon_path = W_STAT_ICONS.get(stat["prop"], f"{_PKG_ROOT}/assets/icons/atk.png")
                try:
                    stat_icon = Image.open(stat_icon_path).convert("RGBA").resize((22, 22), Image.Resampling.LANCZOS)
                    ui_layer.paste(stat_icon, (current_x + 5, stat_y + 9), stat_icon)
                except Exception:
                    pass
                stat_value = f"{stat['val']}"
                if any(token in str(stat["prop"]) for token in ["PERCENT", "CHARGE", "CRITICAL"]):
                    stat_value += "%"
                draw.text((current_x + 40, stat_y + 19), stat_value, font=font_small, fill=(255, 255, 255), anchor="lm")

            stat_config = [
                ("Max HP", "hp", "{:.0f}", f"{_PKG_ROOT}/assets/icons/hp.png"),
                ("ATK", "atk", "{:.0f}", f"{_PKG_ROOT}/assets/icons/atk.png"),
                ("DEF", "def", "{:.0f}", f"{_PKG_ROOT}/assets/icons/def.png"),
                ("CRIT Rate", "cr", "{:.1f}%", f"{_PKG_ROOT}/assets/icons/cr.png"),
                ("CRIT DMG", "cd", "{:.1f}%", f"{_PKG_ROOT}/assets/icons/cd.png"),
                ("Energy Recharge", "er", "{:.1f}%", f"{_PKG_ROOT}/assets/icons/er.png"),
                (f"{stats['element']} DMG Bonus", "elem_bonus", "{:.1f}%", f"{_PKG_ROOT}/assets/icons/{stats['element'].lower()}.png"),
                ("Elemental Mastery", "em", "{:.0f}", f"{_PKG_ROOT}/assets/icons/em.png"),
            ]
            stat_start_x = 950
            stat_spacing = 50
            for index, (label, key, fmt, icon_path) in enumerate(stat_config):
                row_y = 220 + index * stat_spacing
                try:
                    icon = Image.open(icon_path).convert("RGBA").resize((35, 35), Image.Resampling.LANCZOS)
                    ui_layer.paste(icon, (stat_start_x + 10, row_y + 10), icon)
                except Exception:
                    pass
                draw_text_with_shadow(draw, label, (stat_start_x + 60, row_y + 18), self.font_path, 24, text_color=(230, 230, 230), anchor="lm")
                value_text = fmt.format(stats.get(key, 0))
                draw_text_with_shadow(draw, value_text, (stat_start_x + 660, row_y + 18), self.font_path, 26, anchor="rm")

            await draw_horizontal_artifacts(session, ui_layer, avatar_record, 150, 650, ImageFont.truetype(self.font_path, 22))
            final_image = Image.alpha_composite(background_image, ui_layer)
            draw_build_column(final_image, 650, build_data, talent_icons, constellation_icons)
            apply_watermark(final_image, position="top-right")

            buffer = BytesIO()
            final_image.convert("RGB").save(buffer, format="JPEG", quality=95)
            buffer.seek(0)
            buffer.name = f"{char_id}.jpg"
            return buffer
