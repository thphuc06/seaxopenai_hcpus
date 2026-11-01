"""Decode stored evidence images only inside the configured evidence root."""
from io import BytesIO
from pathlib import Path
import warnings

from PIL import Image, UnidentifiedImageError

from app.config import settings

MEDIA_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
MAX_IMAGE_BYTES = 10_000_000


def validate_image(data: bytes) -> tuple[str, int, int]:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Invalid image size")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                media = MEDIA_TYPES.get(image.format or "")
                width, height = image.size
                image.verify()
            with Image.open(BytesIO(data)) as image:
                image.load()
            if media is None:
                raise ValueError("Unsupported image format")
    except (OSError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError("Invalid image") from error
    return media, width, height


def read_image(raw_path: str) -> tuple[bytes, str, int, int]:
    path = Path(raw_path).resolve()
    if not path.is_relative_to(settings.fixtures_dir.resolve()):
        raise ValueError("Image is outside evidence storage")
    # A bounded read also prevents a malformed database path from loading a huge file.
    with path.open("rb") as stream:
        data = stream.read(MAX_IMAGE_BYTES + 1)
    media, width, height = validate_image(data)
    return data, media, width, height
