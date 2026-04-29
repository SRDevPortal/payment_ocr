import frappe

from payment_ocr.services.processor import (
	get_logs,
	process_patient_encounter_by_name,
	reset_row_logs,
)


@frappe.whitelist()
def process_patient_encounter(encounter_name):
	return process_patient_encounter_by_name(encounter_name, force=True)


@frappe.whitelist()
def process_payment_row(encounter_name, row_name):
	return process_patient_encounter_by_name(encounter_name, force=True, row_name=row_name)


@frappe.whitelist()
def get_payment_ocr_logs(encounter_name):
	doc = frappe.get_doc("Patient Encounter", encounter_name)
	doc.check_permission("read")
	return get_logs(encounter_name)


@frappe.whitelist()
def reset_payment_row_ocr(row_name):
	if not frappe.db.exists("SR Multi Mode Payment", row_name):
		frappe.throw("Payment row not found.")

	row = frappe.get_doc("SR Multi Mode Payment", row_name)
	parent = frappe.get_doc(row.parenttype, row.parent)
	parent.check_permission("write")
	deleted = reset_row_logs(row_name)
	frappe.db.commit()
	return {"deleted": deleted}
