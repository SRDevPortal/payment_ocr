import frappe


def execute():
	frappe.db.delete(
		"Singles",
		{
			"doctype": "Payment OCR Settings",
			"field": "enable_llm_fallback",
		},
	)
