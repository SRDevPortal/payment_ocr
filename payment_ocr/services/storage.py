import os
from urllib.parse import unquote, urlparse

import frappe
from frappe.utils.file_manager import get_file_path

from payment_ocr.services.settings import get_s3_config


SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def get_file_bytes(file_url, region_override=None):
	if not file_url:
		frappe.throw("Payment proof URL is missing.")

	ext = _get_extension(file_url)
	if ext and ext not in SUPPORTED_IMAGE_EXTENSIONS:
		frappe.throw(f"Unsupported payment proof file type: {ext}")

	if file_url.startswith("s3://") or _looks_like_s3_http_url(file_url):
		return _get_s3_object(file_url, region_override)

	return _get_local_or_http_file(file_url)


def _get_s3_object(file_url, region_override=None):
	try:
		import boto3
	except ImportError:
		frappe.throw("boto3 is required for Payment OCR S3/Textract access.")

	config = get_s3_config()
	keys = _extract_s3_keys(file_url, config.aws_s3_bucket)
	if not keys:
		frappe.throw("Could not resolve S3 key from payment proof URL.")

	s3 = boto3.client(
		"s3",
		aws_access_key_id=config.aws_access_key_id,
		aws_secret_access_key=config.aws_secret_access_key,
		region_name=config.aws_region,
	)
	last_error = None
	for key in keys:
		try:
			response = s3.get_object(Bucket=config.aws_s3_bucket, Key=key)
			content = response["Body"].read()
			_validate_max_size(content, config.aws_s3_max_mb)
			return content
		except Exception as exc:
			last_error = exc

	raise last_error


def _get_local_or_http_file(file_url):
	if file_url.startswith(("http://", "https://")):
		import requests

		response = requests.get(file_url, timeout=30)
		response.raise_for_status()
		_validate_max_size(response.content, frappe.conf.get("aws_s3_max_mb"))
		return response.content

	local_path = get_file_path(file_url)
	if not local_path or not os.path.exists(local_path):
		frappe.throw("Payment proof file was not found locally or on S3.")

	with open(local_path, "rb") as file_obj:
		content = file_obj.read()
		_validate_max_size(content, frappe.conf.get("aws_s3_max_mb"))
		return content


def _looks_like_s3_http_url(file_url):
	parsed = urlparse(file_url)
	if parsed.scheme not in ("http", "https"):
		return False
	return "amazonaws.com" in parsed.netloc or "s3." in parsed.netloc


def _extract_s3_key(file_url, bucket):
	if file_url.startswith("s3://"):
		key = file_url.replace("s3://", "", 1)
	else:
		parsed = urlparse(file_url)
		key = parsed.path.lstrip("/")

	key = unquote(key or "")
	if bucket and key.startswith(f"{bucket}/"):
		key = key[len(bucket) + 1 :]
	return key


def _extract_s3_keys(file_url, bucket):
	keys = []
	for candidate_bucket in (bucket, None):
		key = _extract_s3_key(file_url, candidate_bucket)
		if key and key not in keys:
			keys.append(key)
	return keys


def _get_extension(file_url):
	parsed = urlparse(file_url)
	path = parsed.path if parsed.scheme else file_url
	_, ext = os.path.splitext(path.split("?", 1)[0])
	return ext.lower()


def _validate_max_size(content, max_mb):
	if not max_mb:
		return

	try:
		max_bytes = int(float(max_mb) * 1024 * 1024)
	except (TypeError, ValueError):
		return

	if max_bytes > 0 and len(content) > max_bytes:
		frappe.throw(f"Payment proof file is larger than the allowed S3 limit of {max_mb} MB.")
