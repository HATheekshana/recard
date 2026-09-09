from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

_PKG_ROOT = Path(__file__).resolve().parent.parent

def draw_build_column(canvas, start_x, data, talent_icons, constellation_icons):
    draw = ImageDraw.Draw(canvas)
    font_path = f"{_PKG_ROOT}/assets/fonts/Genshin_Impact.ttf"
    skill_font = ImageFont.truetype(font_path, 18)

    entry_bg = Image.open(f"{_PKG_ROOT}/assets/talents/bg.png").convert("RGBA")
    ten_bg = Image.open(f"{_PKG_ROOT}/assets/talents/10.png").convert("RGBA")
    con_bg = Image.open(f"{_PKG_ROOT}/assets/constant/const_adapt.png").convert("RGBA")
    lock_bg = Image.open(f"{_PKG_ROOT}/assets/constant/closed/CLOSED.png").convert("RGBA")
    mask = Image.open(f"{_PKG_ROOT}/assets/constant/maska_constant.png").convert("L")

    talent_x = start_x + 30
    talent_y_base = 330
    for index, icon in enumerate(talent_icons):
        if not icon:
            continue
        y = talent_y_base + index * 105
        level = data["talents"][index] if index < len(data["talents"]) else 1
        draw.ellipse([talent_x + 10, y + 10, talent_x + 80, y + 80], fill=(0, 0, 0, 180))
        frame = ten_bg if level >= 10 else entry_bg
        canvas.paste(frame.resize((90, 90), Image.Resampling.LANCZOS), (talent_x, y), frame.resize((90, 90), Image.Resampling.LANCZOS))
        icon_resized = icon.resize((60, 60), Image.Resampling.LANCZOS)
        canvas.paste(icon_resized, (talent_x + 15, y + 15), icon_resized)
        bubble_color = (255, 215, 0) if level >= 10 else (255, 255, 255)
        _draw_circle_bubble(draw, f"{level}", (talent_x + 45, y + 85), skill_font, text_color=bubble_color)

    const_x = start_x - 600
    const_y_base = 250
    for index, icon in enumerate(constellation_icons):
        if not icon:
            continue
        y = const_y_base + index * 95
        is_locked = not data["cons_unlocked"][index]
        draw.ellipse([const_x + 5, y + 5, const_x + 65, y + 65], fill=(0, 0, 0, 180))
        icon_resized = icon.resize((60, 60), Image.Resampling.LANCZOS)
        if is_locked:
            lock_frame = lock_bg.resize((70, 70), Image.Resampling.LANCZOS)
            gray_icon = icon_resized.convert("L").convert("RGBA")
            canvas.paste(gray_icon, (const_x + 5, y + 5), mask.resize((60, 60), Image.Resampling.LANCZOS))
            canvas.paste(lock_frame, (const_x, y), lock_frame)
        else:
            con_frame = con_bg.resize((70, 70), Image.Resampling.LANCZOS)
            canvas.paste(con_frame, (const_x, y), con_frame)
            canvas.paste(icon_resized, (const_x + 5, y + 5), mask.resize((60, 60), Image.Resampling.LANCZOS))


def _draw_circle_bubble(draw, text, position, font, padding=10, text_color=(255, 255, 255, 255), anchor="mm"):
    bbox = draw.textbbox(position, text, font=font, anchor=anchor)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    diameter = max(width, height) + padding * 2
    left = position[0] - diameter // 2
    top = position[1] - diameter // 2
    right = position[0] + diameter // 2
    bottom = position[1] + diameter // 2
    draw.ellipse([left, top, right, bottom], fill=(20, 20, 30, 200), outline=(255, 255, 255, 150), width=1)
    draw.text(position, text, font=font, fill=text_color, anchor=anchor)