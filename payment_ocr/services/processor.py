import json
import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import frappe
from frappe.utils import flt, get_files_path, now_datetime

from payment_ocr.services.llm import cleanup_with_llm
from payment_ocr.services.parser import clean_result, parse_payment_text
from payment_ocr.services.settings import get_settings
from payment_ocr.services.storage import get_file_bytes
from payment_ocr.services.textract import detect_document_text
from payment_ocr.services.gateway import reconcile_payment_row


PARENT_DOCTYPE = "Patient Encounter"
CHILD_DOCTYPE = "SR Multi Mode Payment"
CHILD_TABLE_FIELD = "enc_multi_payments"


def process_patient_encounter_doc(doc, force=False, persist=False, row_name=None):
	if not _integration_available():
		return []

	settings = get_settings()
	results = []

	for row in doc.get(CHILD_TABLE_FIELD) or []:
		if row_name and row.name != row_name:
			continue

		if not row.get("mmp_payment_proof"):
			continue

		existing_log = None if force else _get_existing_processed_log(row.name, row.mmp_payment_proof)
		if existing_log:
			results.append(_refresh_existing_log(doc, row, existing_log, settings, persist=persist))
			continue

		results.append(_process_row(doc, row, settings, persist=persist))

	return results


def process_patient_encounter_by_name(encounter_name, force=False, row_name=None):
	doc = frappe.get_doc(PARENT_DOCTYPE, encounter_name)
	doc.check_permission("write")
	results = process_patient_encounter_doc(doc, force=force, persist=True, row_name=row_name)
	frappe.db.commit()
	return results


def reset_row_logs(row_name):
	if not frappe.db.exists("DocType", "Payment OCR Log"):
		return 0

	log_names = frappe.get_all(
		"Payment OCR Log",
		filters={"payment_row_name": row_name},
		pluck="name",
	)
	for log_name in log_names:
		frappe.delete_doc("Payment OCR Log", log_name, ignore_permissions=True, force=True)
	return len(log_names)


def get_logs(encounter_name):
	if not frappe.db.exists("DocType", "Payment OCR Log"):
		return []

	return frappe.get_all(
		"Payment OCR Log",
		filters={"patient_encounter": encounter_name},
		fields=[
			"name",
			"status",
			"payment_row_name",
			"payment_proof_url",
			"reference_no",
			"reference_date",
			"extracted_amount",
			"amount_match_status",
			"error_message",
			"processed_at",
			"creation",
		],
		order_by="creation desc",
		limit_page_length=200,
	)


def _process_row(doc, row, settings, persist=False):
	proof_url = row.get("mmp_payment_proof")
	base_log = {
		"patient_encounter": doc.name,
		"payment_row_name": row.name,
		"payment_proof_url": proof_url,
	}

	try:
		image_bytes = get_file_bytes(proof_url, settings.textract_region)
		lines = detect_document_text(image_bytes, settings.textract_region)
		raw_text = "\n".join(lines)
		extracted = parse_payment_text(lines)

		if _needs_llm(extracted, settings):
			llm_data = cleanup_with_llm(raw_text, settings)
			if llm_data:
				extracted = _merge_extracted(extracted, clean_result(llm_data))

		duplicate_log = _find_duplicate_log(row.name, extracted)
		if duplicate_log:
			amount_status = _compare_amounts(extracted.get("amount"), row.get("mmp_paid_amount"))
			updates, deleted_files = _clear_duplicate_row(doc, row, proof_url, persist=persist)
			log_name = _create_log(
				{
					**base_log,
					"status": "Skipped",
					"raw_ocr_text": raw_text,
					"extracted_json": json.dumps(extracted, indent=2, sort_keys=True),
					"extracted_amount": extracted.get("amount"),
					"amount_match_status": amount_status,
					"reference_no": extracted.get("transaction_id"),
					"reference_date": extracted.get("date"),
					"error_message": _duplicate_message(duplicate_log, deleted_files),
				}
			)
			return {
				"row_name": row.name,
				"status": "Skipped",
				"log_name": log_name,
				"updates": updates,
				"amount_match_status": amount_status,
				"duplicate_log_name": duplicate_log.name,
				"duplicate_patient_encounter": duplicate_log.patient_encounter,
				"duplicate_match_rule": duplicate_log.match_rule,
				"deleted_file_names": deleted_files,
				"extracted": extracted,
			}

		amount_status = _compare_amounts(extracted.get("amount"), row.get("mmp_paid_amount"))
		updates = _apply_reference_updates(
			row,
			extracted,
			amount_status=amount_status,
			persist=persist,
		)
		status = "Skipped" if amount_status == "Mismatched" else "Completed"
		error_message = _mismatch_message(extracted.get("amount"), row.get("mmp_paid_amount")) if amount_status == "Mismatched" else None

		log_name = _create_log(
			{
				**base_log,
				"status": status,
				"raw_ocr_text": raw_text,
				"extracted_json": json.dumps(extracted, indent=2, sort_keys=True),
				"extracted_amount": extracted.get("amount"),
				"amount_match_status": amount_status,
				"reference_no": extracted.get("transaction_id"),
				"reference_date": extracted.get("date"),
				"error_message": error_message,
			}
		)
		verification = _reconcile_payment_verification(row.name, log_name, settings, persist=persist)
		deleted_files = []
		_delete_local_payment_proof_copies(doc, proof_url)

		return {
			"row_name": row.name,
			"status": status,
			"log_name": log_name,
			"updates": updates,
			"amount_match_status": amount_status,
			"deleted_file_names": deleted_files,
			"verification": verification,
			"extracted": extracted,
		}

	except Exception as exc:
		error_message = _clean_error_message(exc)
		log_name = _create_log(
			{
				**base_log,
				"status": "Failed",
				"amount_match_status": "Not Checked",
				"error_message": error_message,
			}
		)
		return {
			"row_name": row.name,
			"status": "Failed",
			"log_name": log_name,
			"error": str(exc),
		}


def _refresh_existing_log(doc, row, log, settings, persist=False):
	extracted_amount = _get_log_extracted_amount(log)
	amount_status = _compare_amounts(extracted_amount, row.get("mmp_paid_amount"))
	updates = {}

	if log.status == "Completed":
		updates = _apply_reference_updates(
			row,
			{
				"amount": extracted_amount,
				"transaction_id": log.reference_no,
				"date": log.reference_date,
			},
			amount_status=amount_status,
			persist=persist,
		)

	if persist and log.amount_match_status != amount_status:
		frappe.db.set_value(
			"Payment OCR Log",
			log.name,
			"amount_match_status",
			amount_status,
			update_modified=False,
		)

	verification = {}
	if log.status == "Completed":
		verification = _reconcile_payment_verification(row.name, log.name, settings, persist=persist)

	return {
		"row_name": row.name,
		"status": log.status,
		"log_name": log.name,
		"updates": updates,
		"amount_match_status": amount_status,
		"verification": verification,
		"existing_log": True,
	}


def _get_log_extracted_amount(log):
	if log.get("extracted_json"):
		try:
			data = json.loads(log.extracted_json) or {}
			if "amount" in data:
				return data.get("amount")
		except (TypeError, ValueError):
			pass
	return log.extracted_amount


def _apply_reference_updates(row, extracted, amount_status="Not Checked", persist=False):
	updates = {}
	manual_amount_blank = _is_blank_amount(row.get("mmp_paid_amount"))

	# If OCR amount does not match the manually entered amount,
	# do not auto-fill any values on the payment row.
	if amount_status == "Mismatched":
		return updates

	amount = extracted.get("amount")
	if amount not in (None, "") and manual_amount_blank:
		row.mmp_paid_amount = amount
		updates["mmp_paid_amount"] = amount

	transaction_id = extracted.get("transaction_id")
	if transaction_id and row.get("mmp_reference_no") != transaction_id:
		row.mmp_reference_no = transaction_id
		updates["mmp_reference_no"] = transaction_id

	reference_date = extracted.get("date")
	if reference_date and row.get("mmp_reference_date") != reference_date:
		row.mmp_reference_date = reference_date
		updates["mmp_reference_date"] = reference_date

	if persist and updates:
		frappe.db.set_value(CHILD_DOCTYPE, row.name, updates, update_modified=False)

	return updates


def _clear_reference_updates(row, persist=False):
	updates = {}
	if row.get("mmp_reference_no"):
		row.mmp_reference_no = None
		updates["mmp_reference_no"] = None

	if row.get("mmp_reference_date"):
		row.mmp_reference_date = None
		updates["mmp_reference_date"] = None

	if persist and updates:
		frappe.db.set_value(CHILD_DOCTYPE, row.name, updates, update_modified=False)

	return updates


def _clear_duplicate_row(doc, row, proof_url, persist=False):
	updates = _clear_reference_updates(row, persist=False)
	if row.get("mmp_payment_proof"):
		row.mmp_payment_proof = None
		updates["mmp_payment_proof"] = None

	if persist and updates:
		frappe.db.set_value(CHILD_DOCTYPE, row.name, updates, update_modified=False)

	deleted_files = _delete_payment_proof_file_records(doc, proof_url)
	return updates, deleted_files


def _compare_amounts(extracted_amount, entered_amount):
	if extracted_amount in (None, "") or entered_amount in (None, ""):
		return "Not Checked"

	extracted = _round_rupees(extracted_amount)
	entered = _round_rupees(entered_amount)
	if extracted is None or entered is None:
		return "Not Checked"

	return "Matched" if extracted == entered else "Mismatched"


def _is_blank_amount(value):
	if value in (None, ""):
		return True
	try:
		return flt(value) == 0
	except (ValueError, TypeError):
		return False


def _round_rupees(value):
	try:
		decimal_value = Decimal(str(flt(value)))
		return int(decimal_value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
	except (InvalidOperation, ValueError, TypeError):
		return None


def _needs_llm(extracted, settings):
	if not settings.get("enable_llm_fallback"):
		return False
	return not (extracted.get("amount") and extracted.get("date") and extracted.get("transaction_id"))


def _merge_extracted(primary, fallback):
	merged = dict(primary or {})
	for key, value in (fallback or {}).items():
		if value not in (None, "") and not merged.get(key):
			merged[key] = value
	return clean_result(merged)


def _find_duplicate_log(row_name, extracted):
	if not frappe.db.exists("DocType", "Payment OCR Log"):
		return None

	reference_no = _normalize_reference(extracted.get("transaction_id"))
	reference_date = extracted.get("date")
	amount = _round_paise(extracted.get("amount"))
	if not (reference_no and reference_date):
		return None

	candidates = frappe.get_all(
		"Payment OCR Log",
		filters={
			"status": "Completed",
			"reference_date": reference_date,
		},
		fields=[
			"name",
			"patient_encounter",
			"payment_row_name",
			"payment_proof_url",
			"reference_no",
			"extracted_amount",
		],
		order_by="creation desc",
		limit_page_length=20,
	)
	for candidate in candidates:
		if candidate.payment_row_name == row_name:
			continue
		if _normalize_reference(candidate.reference_no) != reference_no:
			continue

		candidate_amount = _round_paise(candidate.extracted_amount)
		if amount is not None and candidate_amount == amount:
			candidate.match_rule = "Same Amount + Same Reference No + Same Reference Date"
			return candidate

		candidate.match_rule = "Same Reference No + Same Reference Date"
		if amount is not None and candidate_amount is not None and candidate_amount != amount:
			candidate.match_rule += " (Amount Mismatch)"
		return candidate
	return None


def _normalize_reference(value):
	return " ".join(str(value or "").strip().upper().split())


def _round_paise(value):
	try:
		return Decimal(str(flt(value))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	except (InvalidOperation, ValueError, TypeError):
		return None


def _delete_payment_proof_file_records(doc, proof_url):
	if not proof_url or not frappe.db.exists("DocType", "File"):
		return []

	filters = {
		"file_url": proof_url,
		"attached_to_doctype": doc.doctype,
		"attached_to_name": doc.name,
	}
	file_names = frappe.get_all("File", filters=filters, pluck="name")

	deleted = []
	for file_name in file_names:
		try:
			frappe.delete_doc("File", file_name, ignore_permissions=True, force=True)
			deleted.append(file_name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Payment OCR File Cleanup Failed")
	return deleted


def _delete_local_payment_proof_copies(doc, proof_url):
	if not proof_url or not str(proof_url).startswith("s3://") or not frappe.db.exists("DocType", "File"):
		return []

	file_names = frappe.get_all(
		"File",
		filters={
			"file_url": proof_url,
			"attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name,
		},
		fields=["file_name"],
	)

	deleted_paths = []
	for file_doc in file_names:
		for is_private in (0, 1):
			path = get_files_path(file_doc.file_name, is_private=is_private)
			if not os.path.exists(path):
				continue
			try:
				os.remove(path)
				deleted_paths.append(path)
			except OSError:
				frappe.log_error(frappe.get_traceback(), "Payment OCR Local File Cleanup Failed")
	return deleted_paths


def _duplicate_message(duplicate_log, deleted_files=None):
	message = f"Duplicate payment proof detected. Rule: {duplicate_log.match_rule}. Matching OCR Log: {duplicate_log.name}"
	if duplicate_log.patient_encounter:
		message += f", Patient Encounter: {duplicate_log.patient_encounter}"
	if deleted_files:
		message += f". Duplicate attachment deleted: {', '.join(deleted_files)}"
	return message


def _get_existing_processed_log(row_name, proof_url):
	if not frappe.db.exists("DocType", "Payment OCR Log"):
		return None

	log = frappe.get_all(
		"Payment OCR Log",
		filters={"payment_row_name": row_name, "payment_proof_url": proof_url},
		fields=[
			"name",
			"status",
			"reference_no",
			"reference_date",
			"extracted_amount",
			"extracted_json",
			"amount_match_status",
		],
		order_by="creation desc",
		limit=1,
	)
	if log and log[0].status in {"Completed", "Failed", "Skipped"}:
		return log[0]
	return None


def _create_log(values):
	if not frappe.db.exists("DocType", "Payment OCR Log"):
		return None

	values = _prepare_log_values(values)
	existing_log_name = _get_existing_log_name(values)
	if existing_log_name:
		frappe.db.set_value(
			"Payment OCR Log",
			existing_log_name,
			values,
		)
		return existing_log_name

	insert_kwargs = {"ignore_permissions": True}
	patient_encounter = values.get("patient_encounter")
	if patient_encounter and not frappe.db.exists(PARENT_DOCTYPE, patient_encounter):
		# During Patient Encounter insert, before_save runs before the parent row exists.
		insert_kwargs["ignore_links"] = True

	doc = frappe.get_doc(
		{
			"doctype": "Payment OCR Log",
			**values,
		}
	)
	doc.insert(**insert_kwargs)
	return doc.name


def _prepare_log_values(values):
	defaults = {
		"raw_ocr_text": None,
		"extracted_json": None,
		"amount_match_status": "Not Checked",
		"reference_no": None,
		"reference_date": None,
		"error_message": None,
	}
	prepared = {
		**defaults,
		**values,
		"processed_at": now_datetime(),
	}
	if prepared.get("extracted_amount") is None:
		prepared.pop("extracted_amount", None)
	return prepared


def _get_existing_log_name(values):
	row_name = values.get("payment_row_name")
	proof_url = values.get("payment_proof_url")
	if not (row_name and proof_url):
		return None

	logs = frappe.get_all(
		"Payment OCR Log",
		filters={
			"payment_row_name": row_name,
			"payment_proof_url": proof_url,
		},
		pluck="name",
		order_by="creation desc",
		limit=1,
	)
	return logs[0] if logs else None


def _clean_error_message(exc):
	message = str(exc).strip()
	if message:
		return message
	return exc.__class__.__name__


def _mismatch_message(extracted_amount, entered_amount):
	return (
		f"Amount mismatch detected. Entered amount: {entered_amount}, "
		f"extracted amount: {extracted_amount}. Payment fields were not updated."
	)


def _integration_available():
	return (
		frappe.db.exists("DocType", PARENT_DOCTYPE)
		and frappe.db.exists("DocType", CHILD_DOCTYPE)
		and frappe.db.exists("DocType", "Payment OCR Log")
	)


def _reconcile_payment_verification(row_name, log_name, settings, persist=False):
	if not persist or not settings.get("enable_gateway_verification"):
		return {}

	try:
		return reconcile_payment_row(row_name, ocr_log_name=log_name)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Payment OCR Gateway Verification Failed")
		return {}
