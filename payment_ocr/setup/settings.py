import frappe


def apply():
	if not frappe.db.exists("DocType", "Payment OCR Settings"):
		return

	settings = frappe.get_single("Payment OCR Settings")
	if settings.get("enable_auto_ocr") is None:
		settings.enable_auto_ocr = 1
	if settings.get("enable_gateway_verification") is None:
		settings.enable_gateway_verification = 1
	if settings.get("enable_partial_gateway_match") is None:
		settings.enable_partial_gateway_match = 0
	if not settings.openai_model:
		settings.openai_model = "gpt-4.1-mini"
	if not settings.amount_mismatch_behavior:
		settings.amount_mismatch_behavior = "Warn Only"
	settings.save(ignore_permissions=True)
