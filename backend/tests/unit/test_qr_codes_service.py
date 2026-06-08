"""Unit tests for the service-layer QR code helpers."""

from opendlp.service_layer import qr_codes


class TestGenerateQrCodeBase64:
    def test_returns_data_url(self):
        result = qr_codes.generate_qr_code_base64("https://example.com")

        assert result.startswith("data:image/png;base64,")
        assert len(result) > 100

    def test_different_urls_produce_different_output(self):
        a = qr_codes.generate_qr_code_base64("https://example.com/a")
        b = qr_codes.generate_qr_code_base64("https://example.com/b")

        assert a != b


class TestGenerateQrCodePng:
    def test_returns_png_bytes(self):
        result = qr_codes.generate_qr_code_png("https://example.com")

        assert isinstance(result, bytes)
        assert result[:4] == b"\x89PNG"  # PNG magic bytes

    def test_different_urls_produce_different_bytes(self):
        a = qr_codes.generate_qr_code_png("https://example.com/a")
        b = qr_codes.generate_qr_code_png("https://example.com/b")

        assert a != b
