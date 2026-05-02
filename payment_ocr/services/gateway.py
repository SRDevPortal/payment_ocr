import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import frappe
from frappe.utils import get_datetime, now_datetime

from payment_ocr.services.settings import get_settings


GATEWAY_DOCTYPE = "Payment Gateway Transaction"
PARENT_DOCTYPE = "Patient Encounter"
CHILD_DOCTYPE = "SR Multi Mode Payment"

RECEIVED_STATUSES = {"success", "successful", "completed", "complete", "paid", "received", "credited"}
PENDING_STATUSES = {"scheduled", "pending", "processing", "initiated", "new"}
FAILED_STATUSES = {"failed", "failure", "declined", "cancelled", "canceled", "reversed", "refunded"}

VERIFICATION_FIELDS = (
	"mmp_reference_no",
	"mmp_reference_date",
	"mmp_payment_verification_status",
	"mmp_verified_transaction_id",
	"mmp_verified_amount",
	"mmp_verified_date",
	"mmp_verified_payer",
	"mmp_verified_source",
	"mmp_verified_at",
	"mmp_verification_note",
)


def ingest_transactions(payload):
	payload = _normalize_payload(payload)
	_validate_webhook_secret(payload)
	body = _get_body(payload)
	transactions = body.get("transactions") or []
	if not isinstance(transactions, list):
		frappe.throw("transactions must be a list.")

	results = []
	for transaction in transactions:
		doc = upsert_gateway_transaction(
			transaction,
			source=body.get("source") or payload.get("source"),
		)
		match = reconcile_gateway_transaction(doc.name)
		results.append(
			{
				"name": doc.name,
				"transaction_id": doc.transaction_id,
				"verification_status": match.get("verification_status"),
				"matched_payment_row": match.get("matched_payment_row"),
				"match_reason": match.get("match_reason"),
			}
		)
	return results


def upsert_gateway_transaction(transaction, source=None):
	if not isinstance(transaction, dict):
		frappe.throw("Each transaction must be an object.")

	normalized = normalize_gateway_transaction(transaction, source=source)
	transaction_id = normalized.get("transaction_id")
	if not transaction_id:
		frappe.throw("Transaction ID is required.")

	existing = frappe.db.get_value(GATEWAY_DOCTYPE, {"transaction_id": transaction_id}, "name")
	if existing:
		doc = frappe.get_doc(GATEWAY_DOCTYPE, existing)
		doc.update(normalized)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": GATEWAY_DOCTYPE, **normalized})
		doc.insert(ignore_permissions=True)

	return doc


def normalize_gateway_transaction(transaction, source=None):
	transaction_datetime = _parse_gateway_datetime(transaction.get("date"))
	scraped_at = _parse_gateway_datetime(transaction.get("scraped_at"))
	raw_status = str(transaction.get("status") or "").strip()

	return {
		"transaction_id": _normalize_reference(transaction.get("transaction_id")),
		"amount": _normalize_amount(transaction.get("amount")),
		"transaction_datetime": transaction_datetime,
		"transaction_date": transaction_datetime.date() if transaction_datetime else None,
		"payer": _clean_text(transaction.get("payer")),
		"payment_app": _clean_text(transaction.get("payment_app")),
		"status": raw_status,
		"source": source or _clean_text(transaction.get("source")) or "gpay_sync_extension",
		"scraped_at": scraped_at,
		"raw_text": transaction.get("raw_text"),
		"raw_json": json.dumps(transaction, indent=2, sort_keys=True, default=str),
		"verification_status": _status_to_verification(raw_status),
	}


def reconcile_gateway_transaction(transaction_name):
	if not _gateway_available():
		return {}

	doc = frappe.get_doc(GATEWAY_DOCTYPE, transaction_name)
	match = _find_best_ocr_match(doc)
	if not match:
		_update_gateway_match(
			doc,
			{
				"verification_status": _status_to_verification(doc.status),
				"match_score": 0,
				"match_reason": "No matching OCR payment row found.",
			},
		)
		return _result_from_gateway(doc)

	duplicate_row = _find_existing_verified_row(doc.transaction_id, exclude_row=match.payment_row_name)
	if duplicate_row:
		status = "Duplicate"
		reason = f"Transaction already verified on payment row {duplicate_row}."
	elif _is_failed_status(doc.status):
		status = "Failed"
		reason = f"Gateway transaction status is {doc.status}."
	elif getattr(match, "partial_match", False):
		status = "Partial Matched" if not match.amount_mismatch else "Amount Mismatch"
		reason = match.match_reason
	else:
		status = "Verified" if not match.amount_mismatch else "Amount Mismatch"
		reason = match.match_reason

	_update_gateway_match(
		doc,
		{
			"verification_status": status,
			"matched_patient_encounter": match.patient_encounter,
			"matched_payment_row": match.payment_row_name,
			"matched_payment_ocr_log": match.name,
			"match_score": match.match_score,
			"match_reason": reason,
			"verified_at": now_datetime() if _is_verified_status(status) else None,
		},
	)
	_sync_ocr_log_amount_status(match)
	_update_payment_row_verification(doc, match, status, reason)
	return _result_from_gateway(doc)


def reconcile_payment_row(row_name, ocr_log_name=None):
	if not _gateway_available():
		return {}

	ocr_log = _get_latest_ocr_log(row_name, ocr_log_name=ocr_log_name)
	if not ocr_log:
		return {}

	transaction = _find_gateway_transaction(ocr_log.reference_no, ocr_log.reference_date, ocr_log.extracted_amount)
	if not transaction and get_settings().get("enable_partial_gateway_match"):
		transaction = _find_partial_gateway_transaction(ocr_log)
		if not transaction:
			transaction = _find_receiver_gateway_transaction(ocr_log)
	if not transaction:
		_update_payment_row_by_name(
			row_name,
			{
				"mmp_payment_verification_status": "Unverified",
				"mmp_verification_note": "OCR reference was extracted, but no gateway transaction has been received yet.",
			},
		)
		return {
			"verification_status": "Unverified",
			"match_reason": "No gateway transaction found.",
		}

	return reconcile_gateway_transaction(transaction.name)


def reconcile_existing_payments(limit=200):
	logs = frappe.get_all(
		"Payment OCR Log",
		filters={"reference_no": ("is", "set")},
		fields=["name", "payment_row_name"],
		order_by="creation desc",
		limit_page_length=limit,
	)
	return [reconcile_payment_row(log.payment_row_name, ocr_log_name=log.name) for log in logs]


def _validate_webhook_secret(payload):
	settings = get_settings()
	expected = settings.get("gateway_webhook_secret")
	if not expected:
		frappe.throw("Payment OCR gateway webhook secret is not configured.")

	received = (
		frappe.get_request_header("X-Payment-OCR-Token")
		or frappe.get_request_header("X-GPay-Sync-Token")
		or payload.get("secret")
		or payload.get("token")
		or _get_body(payload).get("secret")
		or _get_body(payload).get("token")
	)
	if received != expected:
		frappe.throw("Invalid payment gateway webhook secret.")


def _get_body(payload):
	body = payload.get("body") if isinstance(payload, dict) else None
	if isinstance(body, dict):
		return body
	return payload if isinstance(payload, dict) else {}


def _normalize_payload(payload):
	if isinstance(payload, list):
		return payload[0] if payload else {}
	return payload if isinstance(payload, dict) else {}


def _find_best_ocr_match(transaction_doc):
	if not frappe.db.exists("DocType", "Payment OCR Log"):
		return None

	reference_no = _normalize_reference(transaction_doc.transaction_id)
	if reference_no:
		match = _find_reference_ocr_match(transaction_doc, reference_no)
		if match:
			return match

	if get_settings().get("enable_partial_gateway_match"):
		match = _find_partial_ocr_match(transaction_doc)
		if match:
			return match
		return _find_receiver_ocr_match(transaction_doc)

	return None


def _find_reference_ocr_match(transaction_doc, reference_no):
	candidates = frappe.get_all(
		"Payment OCR Log",
		filters={"reference_no": reference_no},
		fields=[
			"name",
			"patient_encounter",
			"payment_row_name",
			"reference_no",
			"reference_date",
			"extracted_amount",
			"amount_match_status",
		],
		order_by="creation desc",
		limit_page_length=20,
	)
	if not candidates:
		return None

	transaction_amount = _round_paise(transaction_doc.amount)
	transaction_date = transaction_doc.transaction_date
	best = None
	best_score = -1
	for candidate in candidates:
		score = 70
		reasons = ["Same transaction ID"]
		candidate_amount = _round_paise(candidate.extracted_amount)
		amount_mismatch = False

		if transaction_amount is not None and candidate_amount is not None:
			if transaction_amount == candidate_amount:
				score += 20
				reasons.append("same amount")
			else:
				amount_mismatch = True
				reasons.append("amount mismatch")

		if transaction_date and candidate.reference_date:
			if str(transaction_date) == str(candidate.reference_date):
				score += 10
				reasons.append("same date")
			else:
				reasons.append("date differs")

		if score > best_score:
			candidate.match_score = score
			candidate.match_reason = ", ".join(reasons) + "."
			candidate.amount_mismatch = amount_mismatch
			candidate.partial_match = False
			best = candidate
			best_score = score

	return best


def _find_partial_ocr_match(transaction_doc):
	transaction_amount = _round_paise(transaction_doc.amount)
	transaction_datetime = _to_datetime(transaction_doc.transaction_datetime)
	if transaction_amount is None or not transaction_datetime:
		return None

	filters = {"status": "Completed"}
	if transaction_doc.transaction_date:
		filters["reference_date"] = transaction_doc.transaction_date

	candidates = frappe.get_all(
		"Payment OCR Log",
		filters=filters,
		fields=[
			"name",
			"patient_encounter",
			"payment_row_name",
			"reference_no",
			"reference_date",
			"extracted_amount",
			"amount_match_status",
			"extracted_json",
			"raw_ocr_text",
		],
		order_by="creation desc",
		limit_page_length=200,
	)

	for candidate in candidates:
		ocr_data = _get_ocr_match_data(candidate)
		if _round_paise(ocr_data.get("amount")) != transaction_amount:
			continue
		if not _timestamp_matches(transaction_datetime, ocr_data.get("transaction_datetime")):
			continue
		if not _text_matches(transaction_doc.payer, ocr_data.get("payer")):
			continue
		if not _text_matches(transaction_doc.payment_app, ocr_data.get("payment_app")):
			continue

		candidate.match_score = 95
		candidate.match_reason = (
			"Partial matched by same amount, same timestamp within 1 second, "
			"same payer, and same payment app."
		)
		candidate.amount_mismatch = False
		candidate.partial_match = True
		return candidate

	return None


def _find_receiver_ocr_match(transaction_doc):
	transaction_amount = _round_paise(transaction_doc.amount)
	transaction_datetime = _to_datetime(transaction_doc.transaction_datetime)
	if transaction_amount is None or not transaction_datetime:
		return None

	filters = {"status": "Completed"}
	if transaction_doc.transaction_date:
		filters["processed_at"] = ("between", [_day_start(transaction_doc.transaction_date), _day_end(transaction_doc.transaction_date)])

	candidates = frappe.get_all(
		"Payment OCR Log",
		filters=filters,
		fields=[
			"name",
			"patient_encounter",
			"payment_row_name",
			"reference_no",
			"reference_date",
			"extracted_amount",
			"amount_match_status",
			"extracted_json",
			"raw_ocr_text",
			"processed_at",
			"creation",
		],
		order_by="creation desc",
		limit_page_length=200,
	)

	matches = []
	for candidate in candidates:
		ocr_data = _get_ocr_match_data(candidate)
		if _round_paise(ocr_data.get("amount")) != transaction_amount:
			continue
		if not _exact_timestamp_matches(transaction_datetime, ocr_data.get("transaction_datetime")):
			continue
		matches.append(candidate)

	if len(matches) != 1:
		return None

	match = matches[0]
	match.match_score = 90
	match.match_reason = "Partial matched by same amount and exact timestamp; unique OCR candidate found."
	match.amount_mismatch = False
	match.partial_match = True
	return match


def _find_gateway_transaction(reference_no, reference_date=None, amount=None):
	reference_no = _normalize_reference(reference_no)
	if not reference_no:
		return None

	filters = {"transaction_id": reference_no}
	transactions = frappe.get_all(
		GATEWAY_DOCTYPE,
		filters=filters,
		fields=["name", "transaction_id", "transaction_date", "amount"],
		limit_page_length=5,
	)
	if not transactions:
		return None

	for transaction in transactions:
		if reference_date and transaction.transaction_date and str(reference_date) != str(transaction.transaction_date):
			continue
		if amount and transaction.amount and _round_paise(amount) != _round_paise(transaction.amount):
			continue
		return transaction

	return transactions[0]


def _find_partial_gateway_transaction(ocr_log):
	ocr_data = _get_ocr_match_data(ocr_log)
	ocr_amount = _round_paise(ocr_data.get("amount"))
	ocr_datetime = _to_datetime(ocr_data.get("transaction_datetime"))
	if ocr_amount is None or not ocr_datetime:
		return None

	filters = {}
	if ocr_log.reference_date:
		filters["transaction_date"] = ocr_log.reference_date

	transactions = frappe.get_all(
		GATEWAY_DOCTYPE,
		filters=filters,
		fields=["name", "amount", "transaction_datetime", "payer", "payment_app"],
		order_by="creation desc",
		limit_page_length=200,
	)

	for transaction in transactions:
		if _round_paise(transaction.amount) != ocr_amount:
			continue
		if not _timestamp_matches(transaction.transaction_datetime, ocr_datetime):
			continue
		if not _text_matches(transaction.payer, ocr_data.get("payer")):
			continue
		if not _text_matches(transaction.payment_app, ocr_data.get("payment_app")):
			continue
		return transaction

	return None


def _find_receiver_gateway_transaction(ocr_log):
	ocr_data = _get_ocr_match_data(ocr_log)
	ocr_amount = _round_paise(ocr_data.get("amount"))
	ocr_datetime = _to_datetime(ocr_data.get("transaction_datetime"))
	if ocr_amount is None or not ocr_datetime:
		return None

	transactions = frappe.get_all(
		GATEWAY_DOCTYPE,
		filters={"transaction_date": ocr_datetime.date()},
		fields=["name", "amount", "transaction_datetime"],
		order_by="creation desc",
		limit_page_length=200,
	)

	matches = []
	for transaction in transactions:
		if _round_paise(transaction.amount) != ocr_amount:
			continue
		if not _exact_timestamp_matches(transaction.transaction_datetime, ocr_datetime):
			continue
		matches.append(transaction)

	return matches[0] if len(matches) == 1 else None


def _get_latest_ocr_log(row_name, ocr_log_name=None):
	if ocr_log_name:
		return frappe.get_doc("Payment OCR Log", ocr_log_name)

	logs = frappe.get_all(
		"Payment OCR Log",
		filters={"payment_row_name": row_name},
		fields=[
			"name",
			"reference_no",
			"reference_date",
			"extracted_amount",
			"payment_row_name",
			"extracted_json",
			"raw_ocr_text",
			"processed_at",
			"creation",
		],
		order_by="creation desc",
		limit=1,
	)
	return logs[0] if logs else None


def _update_gateway_match(doc, values):
	doc.update(values)
	doc.save(ignore_permissions=True)


def _update_payment_row_verification(transaction_doc, ocr_log, status, reason):
	is_verified = _is_verified_status(status)
	existing_verified_at = _get_existing_verified_at(ocr_log.payment_row_name) if is_verified else None
	values = {
		"mmp_payment_verification_status": status,
		"mmp_verified_transaction_id": transaction_doc.transaction_id if is_verified else None,
		"mmp_verified_amount": transaction_doc.amount if is_verified else None,
		"mmp_verified_date": transaction_doc.transaction_date if is_verified else None,
		"mmp_verified_payer": transaction_doc.payer if is_verified else None,
		"mmp_verified_source": transaction_doc.source,
		"mmp_verified_at": (existing_verified_at or now_datetime()) if is_verified else None,
		"mmp_verification_note": reason,
	}
	if is_verified:
		values.update(_get_missing_reference_updates(ocr_log.payment_row_name, transaction_doc))
	_update_payment_row_by_name(ocr_log.payment_row_name, values)


def _sync_ocr_log_amount_status(ocr_log):
	if not ocr_log or not ocr_log.get("name"):
		return

	amount_status = _get_ocr_log_amount_status(ocr_log)
	if not amount_status or ocr_log.get("amount_match_status") == amount_status:
		return

	frappe.db.set_value(
		"Payment OCR Log",
		ocr_log.name,
		"amount_match_status",
		amount_status,
		update_modified=False,
	)


def _get_ocr_log_amount_status(ocr_log):
	paid_amount = _get_payment_row_paid_amount(ocr_log.get("payment_row_name"))
	ocr_data = _get_ocr_match_data(ocr_log)
	extracted_amount = ocr_data.get("amount")

	if paid_amount in (None, "") or extracted_amount in (None, ""):
		return "Not Checked"

	return "Matched" if _round_paise(paid_amount) == _round_paise(extracted_amount) else "Mismatched"


def _get_payment_row_paid_amount(row_name):
	if not row_name or not frappe.db.exists(CHILD_DOCTYPE, row_name):
		return None

	meta = frappe.get_meta(CHILD_DOCTYPE)
	if not meta.has_field("mmp_paid_amount"):
		return None

	return frappe.db.get_value(CHILD_DOCTYPE, row_name, "mmp_paid_amount")


def _get_existing_verified_at(row_name):
	if not row_name or not frappe.db.exists(CHILD_DOCTYPE, row_name):
		return None
	return frappe.db.get_value(CHILD_DOCTYPE, row_name, "mmp_verified_at")


def _get_missing_reference_updates(row_name, transaction_doc):
	if not row_name or not frappe.db.exists(CHILD_DOCTYPE, row_name):
		return {}

	row = frappe.get_doc(CHILD_DOCTYPE, row_name)
	updates = {}
	if not row.get("mmp_reference_no") and transaction_doc.transaction_id:
		updates["mmp_reference_no"] = transaction_doc.transaction_id
	if not row.get("mmp_reference_date") and transaction_doc.transaction_date:
		updates["mmp_reference_date"] = transaction_doc.transaction_date
	return updates


def _update_payment_row_by_name(row_name, values):
	if not row_name or not frappe.db.exists(CHILD_DOCTYPE, row_name):
		return

	valid_values = _filter_existing_child_fields(values)
	if valid_values:
		frappe.db.set_value(CHILD_DOCTYPE, row_name, valid_values, update_modified=False)


def _filter_existing_child_fields(values):
	if not frappe.db.exists("DocType", CHILD_DOCTYPE):
		return {}

	meta = frappe.get_meta(CHILD_DOCTYPE)
	return {field: value for field, value in values.items() if field in VERIFICATION_FIELDS and meta.has_field(field)}


def _find_existing_verified_row(transaction_id, exclude_row=None):
	if not transaction_id or not frappe.db.exists("DocType", CHILD_DOCTYPE):
		return None

	meta = frappe.get_meta(CHILD_DOCTYPE)
	if not meta.has_field("mmp_verified_transaction_id"):
		return None

	filters = {
		"mmp_verified_transaction_id": transaction_id,
		"mmp_payment_verification_status": ("in", ["Verified", "Partial Matched"]),
	}
	if exclude_row:
		filters["name"] = ("!=", exclude_row)

	return frappe.db.get_value(CHILD_DOCTYPE, filters, "name")


def _status_to_verification(status):
	if _is_received_status(status):
		return "Unmatched"
	if _is_failed_status(status):
		return "Failed"
	if _is_pending_status(status):
		return "Pending"
	return "Unmatched"


def _is_verified_status(status):
	return status in {"Verified", "Partial Matched"}


def _is_received_status(status):
	return _normalize_status(status) in RECEIVED_STATUSES


def _is_pending_status(status):
	return _normalize_status(status) in PENDING_STATUSES


def _is_failed_status(status):
	return _normalize_status(status) in FAILED_STATUSES


def _normalize_status(status):
	return str(status or "").strip().lower()


def _normalize_reference(value):
	return " ".join(str(value or "").strip().upper().split())


def _normalize_amount(value):
	if value in (None, ""):
		return None
	text = str(value).replace(",", "")
	match = re.search(r"(\d+(?:\.\d{1,2})?)", text)
	if not match:
		return None
	try:
		return float(Decimal(match.group(1)))
	except (InvalidOperation, ValueError):
		return None


def _round_paise(value):
	if value in (None, ""):
		return None
	try:
		return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	except (InvalidOperation, ValueError, TypeError):
		return None


def _get_ocr_match_data(ocr_log):
	data = {}
	if ocr_log.get("extracted_json"):
		try:
			data = json.loads(ocr_log.extracted_json) or {}
		except (TypeError, ValueError):
			data = {}

	raw_data = _parse_raw_payment_text(ocr_log.get("raw_ocr_text"))
	for key, value in raw_data.items():
		if value not in (None, "") and not data.get(key):
			data[key] = value

	if not data.get("amount"):
		data["amount"] = ocr_log.get("extracted_amount")
	if not data.get("date"):
		data["date"] = ocr_log.get("reference_date")
	if not data.get("date"):
		data["date"] = _date_from_datetime(ocr_log.get("processed_at") or ocr_log.get("creation"))
	if not data.get("transaction_datetime"):
		data["transaction_datetime"] = _combine_date_time(data.get("date"), data.get("time"))

	return data


def _parse_raw_payment_text(raw_text):
	lines = [line.strip() for line in str(raw_text or "").splitlines() if line.strip()]
	data = {
		"time": None,
		"date": None,
		"transaction_datetime": None,
		"payer": None,
		"payment_app": None,
	}

	for index, line in enumerate(lines):
		if not data["time"]:
			data["time"] = _extract_time(line)
		if not data["date"]:
			data["date"] = _extract_date_text(line)
		if not data["payment_app"]:
			data["payment_app"] = _extract_payment_app(line)
		if not data["payer"]:
			data["payer"] = _extract_raw_payer(lines, index)

	data["transaction_datetime"] = _combine_date_time(data.get("date"), data.get("time"))
	return data


def _extract_time(text):
	match = re.search(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)\b", str(text or ""), flags=re.IGNORECASE)
	return match.group(0) if match else None


def _extract_date_text(text):
	patterns = (
		r"\b[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}\b",
		r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b",
		r"\b\d{4}-\d{1,2}-\d{1,2}\b",
		r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
	)
	for pattern in patterns:
		match = re.search(pattern, str(text or ""))
		if match:
			return match.group(0)
	return None


def _extract_payment_app(text):
	apps = ("Google Pay", "PhonePe", "Paytm", "Whatsapp", "WhatsApp", "Generic (Other)")
	for app in apps:
		if app.lower() in str(text or "").lower():
			return app
	return None


def _extract_raw_payer(lines, index):
	line = str(lines[index] or "").strip()
	previous_line = str(lines[index - 1] or "").strip() if index > 0 else ""
	next_line = str(lines[index + 1] or "").strip() if index + 1 < len(lines) else ""
	if not (_extract_date_text(previous_line) and "@" in next_line):
		return None
	if _extract_payment_app(line) or _extract_time(line) or _extract_date_text(line):
		return None
	if _normalize_amount(line) is not None:
		return None
	return line


def _combine_date_time(date_value, time_value):
	if not (date_value and time_value):
		return None
	return _parse_gateway_datetime(f"{time_value} {date_value}")


def _timestamp_matches(left, right):
	left_datetime = _to_datetime(left)
	right_datetime = _to_datetime(right)
	if not (left_datetime and right_datetime):
		return False
	return abs((left_datetime - right_datetime).total_seconds()) <= 1


def _exact_timestamp_matches(left, right):
	left_datetime = _to_datetime(left)
	right_datetime = _to_datetime(right)
	if not (left_datetime and right_datetime):
		return False
	return left_datetime == right_datetime


def _text_matches(left, right):
	left_value = _normalize_match_text(left)
	right_value = _normalize_match_text(right)
	return bool(left_value and right_value and left_value == right_value)


def _normalize_match_text(value):
	return re.sub(r"\s+", " ", str(value or "").strip().upper())


def _to_datetime(value):
	if not value:
		return None
	if isinstance(value, datetime):
		return value
	try:
		return get_datetime(value)
	except Exception:
		return _parse_gateway_datetime(value)


def _date_from_datetime(value):
	value = _to_datetime(value)
	return value.date() if value else None


def _day_start(value):
	return f"{value} 00:00:00"


def _day_end(value):
	return f"{value} 23:59:59"


def _parse_gateway_datetime(value):
	if not value:
		return None

	text = _clean_text(value)
	text = text.replace("\u202f", " ").replace("\xa0", " ")
	text = re.sub(r"\s+", " ", text).strip()
	formats = (
		"%I:%M %p %b %d, %Y",
		"%I:%M%p %b %d, %Y",
		"%I:%M %p %Y-%m-%d",
		"%I:%M%p %Y-%m-%d",
		"%I:%M:%S %p %Y-%m-%d",
		"%b %d, %Y %I:%M %p",
		"%Y-%m-%dT%H:%M:%S.%fZ",
		"%Y-%m-%dT%H:%M:%SZ",
		"%Y-%m-%d %H:%M:%S",
		"%Y-%m-%d",
	)
	for date_format in formats:
		try:
			return datetime.strptime(text, date_format)
		except ValueError:
			pass

	try:
		return get_datetime(text)
	except Exception:
		return None


def _clean_text(value):
	if value in (None, ""):
		return None
	return str(value).strip()


def _result_from_gateway(doc):
	return {
		"verification_status": doc.verification_status,
		"matched_patient_encounter": doc.matched_patient_encounter,
		"matched_payment_row": doc.matched_payment_row,
		"matched_payment_ocr_log": doc.matched_payment_ocr_log,
		"match_score": doc.match_score,
		"match_reason": doc.match_reason,
	}


def _gateway_available():
	return frappe.db.exists("DocType", GATEWAY_DOCTYPE) and frappe.db.exists("DocType", "Payment OCR Log")
