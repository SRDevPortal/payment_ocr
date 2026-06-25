import frappe

from payment_ocr.services.processor import (
	get_logs,
	process_patient_encounter_by_name,
	reset_row_logs,
)
from payment_ocr.services.settings import get_settings


@frappe.whitelist()
def process_patient_encounter(encounter_name):
	_validate_manual_ocr_enabled()
	return process_patient_encounter_by_name(encounter_name, force=True)


@frappe.whitelist()
def process_payment_row(encounter_name, row_name):
	_validate_manual_ocr_enabled()
	return process_patient_encounter_by_name(encounter_name, force=True, row_name=row_name)


@frappe.whitelist()
def get_ocr_availability():
	settings = get_settings()
	return {
		"payment_ocr_enabled": bool(settings.enable_payment_ocr),
		"manual_ocr_enabled": bool(settings.enable_payment_ocr and settings.enable_manual_ocr),
		"auto_ocr_enabled": bool(settings.enable_payment_ocr and settings.enable_auto_ocr),
		"gateway_verification_enabled": bool(
			settings.enable_payment_ocr and settings.enable_gateway_verification
		),
		"partial_gateway_match_enabled": bool(
			settings.enable_payment_ocr
			and settings.enable_gateway_verification
			and settings.enable_partial_gateway_match
		),
	}


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


def _validate_manual_ocr_enabled():
	settings = get_settings()
	if not settings.enable_payment_ocr:
		frappe.throw("Payment OCR is disabled in Payment OCR Settings.")
	if not settings.enable_manual_ocr:
		frappe.throw("Manual Payment OCR is disabled in Payment OCR Settings.")
