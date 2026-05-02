import frappe


def execute():
	if not frappe.db.exists("DocType", "Payment OCR Settings"):
		return

	settings = frappe.get_single("Payment OCR Settings")
	settings.enable_payment_ocr = 1
	settings.enable_manual_ocr = 1
	settings.save(ignore_permissions=True)
