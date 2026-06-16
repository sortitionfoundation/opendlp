"""ABOUTME: Unit tests for the registration image processing pipeline
ABOUTME: Uses real Pillow-generated images to exercise validation and re-encoding"""

from io import BytesIO

import pytest
from PIL import Image

from opendlp.domain.registration_image import ImageValidationError
from opendlp.service_layer.image_processing import process_image

_BIG = 10 * 1024 * 1024
_EDGE = 2048


def _encode(image: Image.Image, fmt: str, **kwargs) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()


def _png(width: int = 50, height: int = 40, color=(255, 0, 0), mode: str = "RGB") -> bytes:
    return _encode(Image.new(mode, (width, height), color), "PNG")


def _opened(data: bytes) -> Image.Image:
    return Image.open(BytesIO(data))


class TestProcessImage:
    def test_reencodes_valid_png_returns_png(self):
        result = process_image(_png(), max_bytes=_BIG, max_edge_px=_EDGE)
        assert _opened(result.data).format == "PNG"
        assert (result.width, result.height) == (50, 40)
        assert len(result.sha256) == 64
        assert result.byte_size == len(result.data)

    def test_jpeg_input_returns_png(self):
        jpeg = _encode(Image.new("RGB", (60, 30), (0, 128, 0)), "JPEG")
        result = process_image(jpeg, max_bytes=_BIG, max_edge_px=_EDGE)
        assert _opened(result.data).format == "PNG"

    def test_webp_input_returns_png(self):
        webp = _encode(Image.new("RGB", (40, 40), (0, 0, 255)), "WEBP")
        result = process_image(webp, max_bytes=_BIG, max_edge_px=_EDGE)
        assert _opened(result.data).format == "PNG"

    def test_transparent_png_keeps_alpha(self):
        data = _png(mode="RGBA", color=(255, 0, 0, 0))
        result = process_image(data, max_bytes=_BIG, max_edge_px=_EDGE)
        assert _opened(result.data).mode == "RGBA"

    def test_downscales_oversized_image(self):
        result = process_image(_png(800, 600), max_bytes=_BIG, max_edge_px=100)
        assert max(result.width, result.height) == 100
        assert (result.width, result.height) == (100, 75)

    def test_small_image_not_upscaled(self):
        result = process_image(_png(30, 20), max_bytes=_BIG, max_edge_px=100)
        assert (result.width, result.height) == (30, 20)

    def test_rejects_oversized_bytes(self):
        with pytest.raises(ImageValidationError) as exc:
            process_image(_png(), max_bytes=5, max_edge_px=_EDGE)
        assert exc.value.reason == "too_large"

    def test_rejects_non_image_bytes(self):
        with pytest.raises(ImageValidationError) as exc:
            process_image(b"not an image at all", max_bytes=_BIG, max_edge_px=_EDGE)
        assert exc.value.reason in {"unsupported_format", "decode_failed"}

    def test_rejects_svg_bytes(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        with pytest.raises(ImageValidationError):
            process_image(svg, max_bytes=_BIG, max_edge_px=_EDGE)

    def test_rejects_gif_input(self):
        gif = _encode(Image.new("RGB", (20, 20), (1, 2, 3)), "GIF")
        with pytest.raises(ImageValidationError) as exc:
            process_image(gif, max_bytes=_BIG, max_edge_px=_EDGE)
        assert exc.value.reason == "unsupported_format"

    def test_rejects_decompression_bomb(self, monkeypatch):
        monkeypatch.setattr("PIL.Image.MAX_IMAGE_PIXELS", 10)
        with pytest.raises(ImageValidationError) as exc:
            process_image(_png(50, 50), max_bytes=_BIG, max_edge_px=_EDGE)
        assert exc.value.reason == "too_many_pixels"

    def test_strips_exif(self):
        exif = Image.Exif()
        exif[0x0112] = 6
        with_exif = _encode(Image.new("RGB", (40, 40), (10, 20, 30)), "JPEG", exif=exif)
        result = process_image(with_exif, max_bytes=_BIG, max_edge_px=_EDGE)
        assert dict(_opened(result.data).getexif()) == {}

    def test_same_input_same_sha(self):
        data = _png()
        first = process_image(data, max_bytes=_BIG, max_edge_px=_EDGE)
        second = process_image(data, max_bytes=_BIG, max_edge_px=_EDGE)
        assert first.sha256 == second.sha256

    def test_different_input_different_sha(self):
        red = process_image(_png(color=(255, 0, 0)), max_bytes=_BIG, max_edge_px=_EDGE)
        blue = process_image(_png(color=(0, 0, 255)), max_bytes=_BIG, max_edge_px=_EDGE)
        assert red.sha256 != blue.sha256
