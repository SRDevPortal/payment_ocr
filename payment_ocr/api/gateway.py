import frappe

from payment_ocr.services.gateway import ingest_transactions, reconcile_existing_payments, reconcile_payment_row
from payment_ocr.services.settings import get_settings


@frappe.whitelist(allow_guest=True)
def receive_gateway_transactions():
	payload = frappe.local.form_dict or {}
	if frappe.request and frappe.request.is_json:
		payload = frappe.request.get_json(silent=True) or payload
	results = ingest_transactions(payload)
	frappe.db.commit()
	return {"processed": len(results), "results": results}


@frappe.whitelist()
def reconcile_payment_verification(row_name):
	_validate_gateway_verification_enabled()

	if not frappe.db.exists("SR Multi Mode Payment", row_name):
		frappe.throw("Payment row not found.")

	row = frappe.get_doc("SR Multi Mode Payment", row_name)
	parent = frappe.get_doc(row.parenttype, row.parent)
	parent.check_permission("write")
	result = reconcile_payment_row(row_name)
	frappe.db.commit()
	return result


@frappe.whitelist()
def reconcile_patient_encounter_payment_verifications(encounter_name):
	_validate_gateway_verification_enabled()

	doc = frappe.get_doc("Patient Encounter", encounter_name)
	doc.check_permission("write")
	results = []
	for row in doc.get("enc_multi_payments") or []:
		results.append(reconcile_payment_row(row.name))
	frappe.db.commit()
	return results


@frappe.whitelist()
def reconcile_existing_payment_verifications(limit=200):
	_validate_gateway_verification_enabled()

	frappe.only_for("System Manager")
	results = reconcile_existing_payments(limit=int(limit or 200))
	frappe.db.commit()
	return results


def _validate_gateway_verification_enabled():
	settings = get_settings()
	if not settings.enable_payment_ocr:
		frappe.throw("Payment OCR is disabled in Payment OCR Settings.")
	if not settings.enable_gateway_verification:
		frappe.throw("Gateway verification is disabled in Payment OCR Settings.")
