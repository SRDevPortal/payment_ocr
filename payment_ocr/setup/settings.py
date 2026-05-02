import frappe


def apply():
	if not frappe.db.exists("DocType", "Payment OCR Settings"):
		return

	settings = frappe.get_single("Payment OCR Settings")
	if not _single_value_exists("Payment OCR Settings", "enable_payment_ocr"):
		settings.enable_payment_ocr = 1
	if settings.get("enable_auto_ocr") is None:
		settings.enable_auto_ocr = 1
	if not _single_value_exists("Payment OCR Settings", "enable_manual_ocr"):
		settings.enable_manual_ocr = 1
	if not _single_value_exists("Payment OCR Settings", "use_app_level_ocr_config"):
		settings.use_app_level_ocr_config = 0
	if not _single_value_exists("Payment OCR Settings", "use_app_level_gateway_config"):
		settings.use_app_level_gateway_config = 0
	if settings.get("enable_gateway_verification") is None:
		settings.enable_gateway_verification = 1
	if settings.get("enable_partial_gateway_match") is None:
		settings.enable_partial_gateway_match = 0
	if not settings.openai_model:
		settings.openai_model = "gpt-4.1-mini"
	if not settings.amount_mismatch_behavior:
		settings.amount_mismatch_behavior = "Warn Only"
	settings.save(ignore_permissions=True)


def _single_value_exists(doctype, fieldname):
	return bool(
		frappe.db.sql(
			"select value from `tabSingles` where doctype = %s and field = %s limit 1",
			(doctype, fieldname),
		)
	)
