"""Local custom splash images, shared by both card sources."""
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image

EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp')


def character_key(character_id):
    value = str(character_id)
    if not value.isdecimal() or int(value) <= 0:
        raise ValueError('A positive numeric character ID is required.')
    return str(int(value))


def load_custom_image(image):
    """Accept a local filename, encoded image bytes, or a Pillow image."""
    if isinstance(image, Image.Image):
        return image.convert('RGBA').copy()
    source = BytesIO(image) if isinstance(image, (bytes, bytearray)) else image
    with Image.open(source) as opened:
        return opened.convert('RGBA')


def save_custom_image(directory, character_id, image):
    key = character_key(character_id)
    converted = load_custom_image(image)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f'{key}.png'
    temporary = directory / f'.{key}-{uuid4().hex}.tmp'
    try:
        converted.save(temporary, format='PNG')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
        converted.close()
    # Remove only this character's older formats after the new image is saved.
    for extension in EXTENSIONS[1:]:
        (directory / f'{key}{extension}').unlink(missing_ok=True)
    return destination


def remove_custom_image(directory, character_id):
    key = character_key(character_id)
    removed = False
    for extension in EXTENSIONS:
        path = Path(directory) / f'{key}{extension}'
        if path.exists():
            path.unlink()
            removed = True
    return removed
