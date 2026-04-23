import frappe

from payment_ocr.services.settings import get_textract_config


def detect_document_text(image_bytes, region_override=None):
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
	try:
		response = client.detect_document_text(Document={"Bytes": image_bytes})
	except Exception as exc:
		error = getattr(exc, "response", {}).get("Error", {})
		code = error.get("Code")
		message = error.get("Message") or str(exc)

		if code == "AccessDeniedException":
			frappe.throw(
				"AWS Textract permission is missing. Add textract:DetectDocumentText permission "
				"to the IAM user configured for this site."
			)

		frappe.throw(f"AWS Textract failed: {message}")

	return [
		block.get("Text", "")
		for block in response.get("Blocks", [])
		if block.get("BlockType") == "LINE" and block.get("Text")
	]
