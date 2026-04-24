import re
from datetime import datetime
from decimal import Decimal, InvalidOperation


EMPTY_RESULT = {
	"amount": None,
	"date": None,
	"transaction_id": None,
	"status": None,
	"payer": None,
	"receiver": None,
}

IGNORED_TRANSACTION_CANDIDATES = {
	"transaction",
	"reference",
	"payment",
	"success",
	"completed",
}


def parse_payment_text(lines):
	result = dict(EMPTY_RESULT)
	lines = [line.strip() for line in (lines or []) if str(line or "").strip()]

	for index, line in enumerate(lines):
		lower_line = line.lower()
		next_line = _next_line(lines, index)

		if result["amount"] is None:
			result["amount"] = _extract_amount(line)

		if result["date"] is None:
			result["date"] = _extract_date(line)

		if result["transaction_id"] is None:
			result["transaction_id"] = _extract_transaction_id(line, next_line)

		if result["status"] is None:
			result["status"] = _extract_status(lower_line)

		if result["payer"] is None:
			result["payer"] = _extract_labeled_value(line, ("from", "paid by", "payer"), next_line)

		if result["receiver"] is None:
			result["receiver"] = _extract_labeled_value(line, ("to", "paid to", "receiver"), next_line)

	return clean_result(result)


def clean_result(data):
	result = dict(EMPTY_RESULT)
	result.update(data or {})

	result["amount"] = normalize_amount(result.get("amount"))
	result["date"] = normalize_date(result.get("date"))
	result["transaction_id"] = _clean_transaction_id(result.get("transaction_id"))
	result["status"] = _clean_status(result.get("status"))
	result["payer"] = _clean_name(result.get("payer"))
	result["receiver"] = _clean_name(result.get("receiver"))
	return result


def normalize_amount(value):
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


def normalize_date(value):
	if not value:
		return None

	text = str(value).strip()
	text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text, flags=re.IGNORECASE)
	formats = (
		"%Y-%m-%d",
		"%d-%m-%Y",
		"%d/%m/%Y",
		"%d.%m.%Y",
		"%d %b %Y",
		"%d %B %Y",
		"%b %d, %Y",
		"%B %d, %Y",
	)

	for date_format in formats:
		try:
			return datetime.strptime(text, date_format).strftime("%Y-%m-%d")
		except ValueError:
			pass

	match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2})\b", text)
	if match:
		day, month, year = match.groups()
		return normalize_date(f"{day}-{month}-20{year}")

	return None


def _extract_amount(line):
	patterns = (
		r"(?:rs\.?|inr|\u20b9)\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
		r"(?:amount|paid)\D{0,12}([0-9][0-9,]*(?:\.\d{1,2})?)",
	)
	for pattern in patterns:
		match = re.search(pattern, line, flags=re.IGNORECASE)
		if match:
			return match.group(1)
	return None


def _extract_date(line):
	patterns = (
		r"\b\d{4}-\d{1,2}-\d{1,2}\b",
		r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
		r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b",
		r"\b[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}\b",
	)
	for pattern in patterns:
		match = re.search(pattern, line)
		if match:
			return match.group(0)
	return None


def _extract_transaction_id(line, next_line=None):
	label_pattern = r"(upi\s*)?(transaction|txn|utr|reference|ref|bank\s*ref)\s*(id|no|number)?"
	if not re.search(label_pattern, line, flags=re.IGNORECASE):
		return None

	same_line = re.search(r"[:#-]\s*([A-Z0-9][A-Z0-9/-]{5,})\b", line, flags=re.IGNORECASE)
	if same_line:
		return same_line.group(1)

	all_candidates = re.findall(r"\b[A-Z0-9][A-Z0-9/-]{7,}\b", line, flags=re.IGNORECASE)
	for candidate in all_candidates:
		if candidate.lower() not in IGNORED_TRANSACTION_CANDIDATES and not _looks_like_date(candidate):
			return candidate

	if next_line:
		next_candidate = re.search(r"\b[A-Z0-9][A-Z0-9/-]{7,}\b", next_line, flags=re.IGNORECASE)
		if next_candidate and not _looks_like_date(next_candidate.group(0)):
			return next_candidate.group(0)

	return None


def _extract_status(lower_line):
	if any(word in lower_line for word in ("success", "completed", "paid", "done")):
		return "SUCCESS"
	if any(word in lower_line for word in ("failed", "declined", "failure", "cancelled")):
		return "FAILED"
	return None


def _extract_labeled_value(line, labels, next_line=None):
	for label in labels:
		match = re.search(rf"\b{re.escape(label)}\b\s*:?\s*(.+)$", line, flags=re.IGNORECASE)
		if match:
			value = match.group(1).strip()
			if _should_extend_name(value, next_line):
				value = f"{value} {next_line.strip()}"
			if value and not re.fullmatch(r"[:\-\s]+", value):
				return value
	return None


def _clean_transaction_id(value):
	if not value:
		return None
	value = str(value).strip().strip(":#- ")
	if len(value) < 6 or _looks_like_date(value):
		return None
	return value


def _clean_status(value):
	if not value:
		return None
	lower_value = str(value).lower()
	if any(word in lower_value for word in ("success", "completed", "paid", "done")):
		return "SUCCESS"
	if any(word in lower_value for word in ("failed", "declined", "failure", "cancelled")):
		return "FAILED"
	return None


def _clean_name(value):
	if not value:
		return None
	value = str(value).strip()
	if len(value) < 3:
		return None
	return value


def _should_extend_name(value, next_line):
	if not value or not next_line:
		return False

	next_line = str(next_line).strip()
	if not next_line:
		return False

	if value.count("(") > value.count(")"):
		return not _looks_like_new_section(next_line)

	return False


def _looks_like_new_section(line):
	line = str(line or "").strip()
	if not line:
		return True

	lower_line = line.lower()
	prefixes = (
		"to ",
		"from ",
		"paid to",
		"paid by",
		"payer",
		"receiver",
		"upi ",
		"transaction",
		"txn ",
		"reference",
		"ref ",
		"bank ref",
		"google ",
		"phonepe",
		"paytm",
		"pay again",
		"completed",
		"success",
		"failed",
	)
	if lower_line.startswith(prefixes):
		return True

	if "@" in line:
		return True

	if _extract_amount(line) is not None:
		return True

	if _extract_date(line) is not None:
		return True

	return False


def _looks_like_date(value):
	return bool(re.fullmatch(r"\d{1,4}[/-]\d{1,2}[/-]\d{1,4}", str(value)))


def _next_line(lines, index):
	if index + 1 >= len(lines):
		return None
	return lines[index + 1]
