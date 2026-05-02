from io import BytesIO

import frappe

from payment_ocr.services.settings import get_textract_config


def detect_document_text(image_bytes, region_override=None):
	lines, _raw_text = detect_document_text_with_details(image_bytes, region_override)
	return lines


def detect_document_text_with_details(image_bytes, region_override=None):
	client = _get_textract_client(region_override)
	all_lines = []
	raw_sections = []
	errors = []

	for label, variant in _get_labeled_image_variants(image_bytes):
		try:
			lines = _detect_document_text(client, variant)
			all_lines.extend(lines)
			if lines:
				raw_sections.append(_format_raw_section(label, lines))
		except Exception as exc:
			errors.append(exc)

	if not all_lines and errors:
		_raise_textract_error(errors[0])

	return _merge_unique_lines(all_lines), "\n\n".join(raw_sections)


def _get_textract_client(region_override=None):
	try:
		import boto3
	except ImportError:
		frappe.throw("boto3 is required for Payment OCR S3/Textract access.")

	config = get_textract_config(region_override)
	client = boto3.client(
		"textract",
		aws_access_key_id=config.aws_access_key_id,
		aws_secret_access_key=config.aws_secret_access_key,
		region_name=config.aws_region,
	)
	return client


def _detect_document_text(client, image_bytes):
	try:
		response = client.detect_document_text(Document={"Bytes": image_bytes})
	except Exception as exc:
		_raise_textract_error(exc)

	return [
		block.get("Text", "")
		for block in response.get("Blocks", [])
		if block.get("BlockType") == "LINE" and block.get("Text")
	]


def _get_image_variants(image_bytes):
	return [variant for _label, variant in _get_labeled_image_variants(image_bytes)]


def _get_labeled_image_variants(image_bytes):
	variants = [image_bytes]

	try:
		from PIL import Image
	except ImportError:
		return [("Original Image", image_bytes)]

	try:
		image = Image.open(BytesIO(image_bytes))
		image.load()
	except Exception:
		return [("Original Image", image_bytes)]

	if image.mode not in ("RGB", "L"):
		image = image.convert("RGB")

	width, height = image.size
	if width < 1 or height < 1:
		return [("Original Image", image_bytes)]

	full_image = _enhance_for_ocr(image)
	variants.append(_image_to_jpeg_bytes(full_image))

	top_crop = image.crop((0, 0, width, max(1, int(height * 0.34))))
	variants.append(_image_to_jpeg_bytes(_enhance_for_ocr(top_crop, scale=3)))

	upper_crop = image.crop((0, 0, width, max(1, int(height * 0.52))))
	variants.append(_image_to_jpeg_bytes(_enhance_for_ocr(upper_crop, scale=2)))

	labels = (
		"Original Image",
		"Enhanced Full Image",
		"Enhanced Top Crop",
		"Enhanced Upper Crop",
	)
	return [(label, variant) for label, variant in zip(labels, variants) if variant]


def _enhance_for_ocr(image, scale=2):
	from PIL import ImageEnhance, ImageOps

	if scale > 1:
		image = image.resize((image.width * scale, image.height * scale))

	image = ImageOps.autocontrast(image)
	image = ImageEnhance.Contrast(image).enhance(1.8)
	image = ImageEnhance.Sharpness(image).enhance(2.0)
	return image


def _image_to_jpeg_bytes(image):
	buffer = BytesIO()
	image.convert("RGB").save(buffer, format="JPEG", quality=92, optimize=True)
	return buffer.getvalue()


def _merge_unique_lines(lines):
	merged = []
	seen = set()
	for line in lines or []:
		line = str(line or "").strip()
		if not line:
			continue
		key = " ".join(line.lower().split())
		if key in seen:
			continue
		seen.add(key)
		merged.append(line)
	return merged


def _format_raw_section(label, lines):
	return f"--- {label} ---\n" + "\n".join(str(line or "").strip() for line in lines if str(line or "").strip())


def _raise_textract_error(exc):
	error = getattr(exc, "response", {}).get("Error", {})
	code = error.get("Code")
	message = error.get("Message") or str(exc)

	if code == "AccessDeniedException":
		frappe.throw(
			"AWS Textract permission is missing. Add textract:DetectDocumentText permission "
			"to the IAM user configured for this site."
		)

	frappe.throw(f"AWS Textract failed: {message}")
