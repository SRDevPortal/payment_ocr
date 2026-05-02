import unittest

from payment_ocr.services.textract import _format_raw_section, _get_image_variants, _merge_unique_lines


class TestTextractPreprocessing(unittest.TestCase):
	def test_merge_unique_lines_keeps_first_seen_text(self):
		lines = _merge_unique_lines(["Payment Successful", " payment   successful ", "02 May 2026 at 01:55 PM"])

		self.assertEqual(lines, ["Payment Successful", "02 May 2026 at 01:55 PM"])

	def test_image_variants_include_enhanced_crops(self):
		try:
			from PIL import Image
		except ImportError:
			self.skipTest("Pillow is not installed")

		from io import BytesIO

		buffer = BytesIO()
		Image.new("RGB", (300, 600), "green").save(buffer, format="JPEG")

		variants = _get_image_variants(buffer.getvalue())

		self.assertGreaterEqual(len(variants), 3)

	def test_raw_section_keeps_ocr_pass_label(self):
		raw_text = _format_raw_section("Enhanced Top Crop", ["Payment Successful", "02 May 2026 at 01:55 PM"])

		self.assertEqual(raw_text, "--- Enhanced Top Crop ---\nPayment Successful\n02 May 2026 at 01:55 PM")


if __name__ == "__main__":
	unittest.main()
