"""ABOUTME: QR code generation helpers shared across backoffice blueprints
ABOUTME: Wraps the `qrcode` library to produce data URLs and raw PNG bytes"""

import base64
import io

import qrcode


def generate_qr_code_base64(url: str) -> str:
    """Generate a QR code for the given URL and return it as a base64-encoded PNG data URL."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer)  # qrcode images always save as PNG
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{img_base64}"


def generate_qr_code_png(url: str) -> bytes:
    """Generate a QR code for the given URL and return it as PNG bytes."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer)  # qrcode images always save as PNG
    buffer.seek(0)
    return buffer.getvalue()
