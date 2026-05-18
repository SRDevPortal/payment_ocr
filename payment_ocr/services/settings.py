import frappe


def get_settings():
	defaults = frappe._dict(
		enable_payment_ocr=1,
		enable_auto_ocr=1,
		enable_manual_ocr=1,
		enable_gateway_verification=1,
		enable_partial_gateway_match=0,
		use_app_level_ocr_config=0,
		use_app_level_gateway_config=0,
		openai_model=frappe.conf.get("payment_ocr_openai_model") or "gpt-4.1-mini",
		textract_access_key_id=frappe.conf.get("aws_textract_access_key_id"),
		textract_secret_access_key=frappe.conf.get("aws_textract_secret_access_key"),
		textract_region=frappe.conf.get("aws_textract_region"),
		amount_mismatch_behavior="Warn Only",
		openai_api_key=None,
		gateway_webhook_secret=frappe.conf.get("payment_ocr_gateway_webhook_secret"),
	)

	if not frappe.db.exists("DocType", "Payment OCR Settings"):
		return defaults

	doc = frappe.get_single("Payment OCR Settings")
	settings = frappe._dict(defaults)
	settings.enable_payment_ocr = doc.get("enable_payment_ocr")
	settings.enable_auto_ocr = doc.get("enable_auto_ocr")
	settings.enable_manual_ocr = doc.get("enable_manual_ocr")
	settings.enable_gateway_verification = doc.get("enable_gateway_verification")
	settings.enable_partial_gateway_match = doc.get("enable_partial_gateway_match")
	settings.use_app_level_ocr_config = doc.get("use_app_level_ocr_config")
	settings.use_app_level_gateway_config = doc.get("use_app_level_gateway_config")
	if settings.enable_payment_ocr is None:
		settings.enable_payment_ocr = defaults.enable_payment_ocr
	if settings.enable_auto_ocr is None:
		settings.enable_auto_ocr = defaults.enable_auto_ocr
	if settings.enable_manual_ocr is None:
		settings.enable_manual_ocr = defaults.enable_manual_ocr
	if settings.enable_gateway_verification is None:
		settings.enable_gateway_verification = defaults.enable_gateway_verification
	if settings.enable_partial_gateway_match is None:
		settings.enable_partial_gateway_match = defaults.enable_partial_gateway_match
	if settings.use_app_level_ocr_config is None:
		settings.use_app_level_ocr_config = defaults.use_app_level_ocr_config
	if settings.use_app_level_gateway_config is None:
		settings.use_app_level_gateway_config = defaults.use_app_level_gateway_config
	if settings.use_app_level_ocr_config:
		settings.openai_model = doc.get("openai_model") or "gpt-4.1-mini"
		settings.textract_access_key_id = doc.get("textract_access_key_id")
		settings.textract_secret_access_key = _get_password(doc, "textract_secret_access_key")
		settings.textract_region = doc.get("textract_region")
		settings.openai_api_key = _get_password(doc, "openai_api_key")
	else:
		settings.openai_model = defaults.openai_model
		settings.textract_access_key_id = defaults.textract_access_key_id
		settings.textract_secret_access_key = defaults.textract_secret_access_key
		settings.textract_region = defaults.textract_region
		settings.openai_api_key = frappe.conf.get("payment_ocr_openai_api_key")
	settings.amount_mismatch_behavior = doc.get("amount_mismatch_behavior") or defaults.amount_mismatch_behavior
	settings.enable_llm_fallback = bool(settings.openai_api_key)
	if settings.use_app_level_gateway_config:
		settings.gateway_webhook_secret = _get_password(doc, "gateway_webhook_secret")
	else:
		settings.gateway_webhook_secret = defaults.gateway_webhook_secret
	return settings


def _get_password(doc, fieldname):
	if not doc.get(fieldname):
		return None

	try:
		return doc.get_password(fieldname)
	except frappe.AuthenticationError:
		return None


def get_s3_config():
	config = frappe._dict(
		aws_access_key_id=frappe.conf.get("aws_s3_access_key_id") or frappe.conf.get("aws_access_key_id"),
		aws_secret_access_key=frappe.conf.get("aws_s3_secret_access_key") or frappe.conf.get("aws_secret_access_key"),
		aws_region=frappe.conf.get("aws_s3_region") or frappe.conf.get("aws_region"),
		aws_s3_bucket=frappe.conf.get("aws_s3_bucket") or frappe.conf.get("aws_bucket"),
	)

	missing = [key for key, value in config.items() if not value]
	if missing:
		frappe.throw("Missing S3 configuration: " + ", ".join(missing))

	return config


def get_textract_config(region_override=None):
	settings = get_settings()
	config = frappe._dict(
		aws_access_key_id=settings.textract_access_key_id,
		aws_secret_access_key=settings.textract_secret_access_key,
		aws_region=region_override or settings.textract_region,
	)

	missing = [key for key, value in config.items() if not value]
	if missing:
		frappe.throw("Missing Textract configuration: " + ", ".join(missing))

	return config
