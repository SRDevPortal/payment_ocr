import frappe
from frappe.utils import add_to_date, now_datetime

from payment_ocr.services.processor import process_patient_encounter_doc
from payment_ocr.services.settings import get_settings


def on_update_patient_encounter(doc, method=None):
	if _is_unsaved_encounter(doc):
		return
	if doc.docstatus == 1:
		return

	_run_auto_ocr(doc, persist=True)


def after_insert_patient_encounter(doc, method=None):
	_relink_temp_files(doc)
	_run_auto_ocr(doc, persist=True)


def _run_auto_ocr(doc, persist=False):
	settings = get_settings()
	if not settings.enable_auto_ocr:
		return

	results = process_patient_encounter_doc(doc, force=False, persist=persist)
	mismatches = [
		result
		for result in results
		if result.get("amount_match_status") == "Mismatched"
	]
	failed = [result for result in results if result.get("status") == "Failed"]
	duplicates = [result for result in results if result.get("duplicate_log_name")]

	if mismatches:
		rows = ", ".join(result.get("row_name") or "" for result in mismatches)
		frappe.msgprint(
			f"Payment OCR amount mismatch detected for payment row(s): {rows}. Please verify paid amount manually.",
			title="Payment OCR Warning",
			indicator="orange",
		)

	if failed:
		rows = ", ".join(result.get("row_name") or "" for result in failed)
		frappe.msgprint(
			f"Payment OCR could not read payment proof for row(s): {rows}. Encounter save is allowed. "
			"Check Payment OCR Log for details.",
			title="Payment OCR Failed",
			indicator="orange",
		)

	if duplicates:
		rows = ", ".join(result.get("row_name") or "" for result in duplicates)
		frappe.msgprint(
			f"Duplicate payment proof detected for payment row(s): {rows}. "
			"Duplicate attachment was removed, and reference number/date were left blank.",
			title="Duplicate Payment Proof",
			indicator="red",
		)


def _is_unsaved_encounter(doc):
	return doc.is_new() or not doc.name or str(doc.name).startswith("new-")


def _relink_temp_files(doc):
	temp_doc_name = doc.get("__temporary_name")
	if not temp_doc_name or temp_doc_name == doc.name:
		return

	file_names = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": doc.doctype,
			"attached_to_name": temp_doc_name,
			"creation": ("between", [add_to_date(date=now_datetime(), minutes=-60), now_datetime()]),
		},
		pluck="name",
	)
	for file_name in file_names:
		frappe.db.set_value("File", file_name, "attached_to_name", doc.name, update_modified=False)
