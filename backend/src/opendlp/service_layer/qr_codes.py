"""ABOUTME: QR code generation helpers used across the service layer
ABOUTME: Wraps the `qrcode` library to produce data URLs and raw PNG bytes"""

import base64
import io

import qrcode


def _make_png_bytes(data: str) -> bytes:
    """Render arbitrary data as a QR code and return raw PNG bytes."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer)  # qrcode images always save as PNG
    buffer.seek(0)
    return buffer.getvalue()


def generate_qr_code_base64(url: str) -> str:
    """Generate a QR code for the given URL and return it as a base64-encoded PNG data URL."""
    img_base64 = base64.b64encode(_make_png_bytes(url)).decode("utf-8")
    return f"data:image/png;base64,{img_base64}"


def generate_qr_code_png(url: str) -> bytes:
    """Generate a QR code for the given URL and return it as PNG bytes."""
    return _make_png_bytes(url)
