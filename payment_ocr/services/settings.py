import frappe


def get_settings():
	defaults = frappe._dict(
		enable_auto_ocr=1,
		enable_gateway_verification=1,
		enable_partial_gateway_match=0,
		enable_llm_fallback=0,
		openai_model="gpt-4.1-mini",
		textract_region=frappe.conf.get("aws_textract_region"),
		amount_mismatch_behavior="Warn Only",
		openai_api_key=None,
		gateway_webhook_secret=frappe.conf.get("payment_ocr_gateway_webhook_secret"),
	)

	if not frappe.db.exists("DocType", "Payment OCR Settings"):
		return defaults

	doc = frappe.get_single("Payment OCR Settings")
	settings = frappe._dict(defaults)
	settings.enable_auto_ocr = doc.get("enable_auto_ocr")
	settings.enable_gateway_verification = doc.get("enable_gateway_verification")
	settings.enable_partial_gateway_match = doc.get("enable_partial_gateway_match")
	settings.enable_llm_fallback = doc.get("enable_llm_fallback")
	if settings.enable_auto_ocr is None:
		settings.enable_auto_ocr = defaults.enable_auto_ocr
	if settings.enable_gateway_verification is None:
		settings.enable_gateway_verification = defaults.enable_gateway_verification
	if settings.enable_partial_gateway_match is None:
		settings.enable_partial_gateway_match = defaults.enable_partial_gateway_match
	if settings.enable_llm_fallback is None:
		settings.enable_llm_fallback = defaults.enable_llm_fallback
	settings.openai_model = doc.get("openai_model") or defaults.openai_model
	settings.textract_region = doc.get("textract_region")
	settings.amount_mismatch_behavior = doc.get("amount_mismatch_behavior") or defaults.amount_mismatch_behavior
	settings.openai_api_key = None
	if doc.enable_llm_fallback:
		settings.openai_api_key = doc.get_password("openai_api_key") or frappe.conf.get("payment_ocr_openai_api_key")
	settings.gateway_webhook_secret = doc.get_password("gateway_webhook_secret") or defaults.gateway_webhook_secret
	return settings


def get_s3_config():
	config = frappe._dict(
		aws_access_key_id=frappe.conf.get("aws_s3_access_key_id") or frappe.conf.get("aws_access_key_id"),
		aws_secret_access_key=frappe.conf.get("aws_s3_secret_access_key") or frappe.conf.get("aws_secret_access_key"),
		aws_region=frappe.conf.get("aws_s3_region") or frappe.conf.get("aws_region"),
		aws_s3_bucket=frappe.conf.get("aws_s3_bucket"),
	)

	missing = [key for key, value in config.items() if not value]
	if missing:
		frappe.throw("Missing S3 configuration: " + ", ".join(missing))

	return config


def get_textract_config(region_override=None):
	config = frappe._dict(
		aws_access_key_id=frappe.conf.get("aws_textract_access_key_id"),
		aws_secret_access_key=frappe.conf.get("aws_textract_secret_access_key"),
		aws_region=region_override or frappe.conf.get("aws_textract_region"),
	)

	missing = [key for key, value in config.items() if not value]
	if missing:
		frappe.throw("Missing Textract configuration: " + ", ".join(missing))

	return config
