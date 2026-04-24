import frappe


def execute():
	if not frappe.db.exists("DocType", "Payment OCR Log"):
		return

	logs = frappe.get_all(
		"Payment OCR Log",
		filters={
			"status": "Completed",
			"amount_match_status": "Mismatched",
		},
		fields=["name", "extracted_amount", "error_message"],
	)

	for log in logs:
		updates = {"status": "Skipped"}
		if not log.error_message:
			updates["error_message"] = (
				f"Amount mismatch detected. Extracted amount: {log.extracted_amount}. "
				"Payment fields were not updated."
			)
		frappe.db.set_value("Payment OCR Log", log.name, updates, update_modified=False)

