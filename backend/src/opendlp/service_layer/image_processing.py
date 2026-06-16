"""ABOUTME: Image validation and re-encoding pipeline for registration images
ABOUTME: Validates, strips metadata, downscales and re-encodes uploads to PNG"""

import hashlib
import warnings
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from opendlp.domain.registration_image import ALLOWED_INPUT_FORMATS, ImageValidationError, ProcessedImage
from opendlp.translations import gettext as _


def process_image(raw: bytes, *, max_bytes: int, max_edge_px: int) -> ProcessedImage:
    if len(raw) > max_bytes:
        raise ImageValidationError("too_large", _("The image file is too large"))

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            opened = Image.open(BytesIO(raw))
            if opened.format not in ALLOWED_INPUT_FORMATS:
                raise ImageValidationError("unsupported_format", _("The image must be a PNG, JPEG or WebP file"))
            image = ImageOps.exif_transpose(opened)
            image.load()
            image.thumbnail((max_edge_px, max_edge_px), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            image.save(buffer, format="PNG", optimize=True)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageValidationError("too_many_pixels", _("The image has too many pixels")) from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageValidationError("decode_failed", _("The image could not be read")) from exc

    data = buffer.getvalue()
    return ProcessedImage(
        data=data,
        width=image.width,
        height=image.height,
        sha256=hashlib.sha256(data).hexdigest(),
        byte_size=len(data),
    )
