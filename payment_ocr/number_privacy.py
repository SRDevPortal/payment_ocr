"""Customer-number privacy at Payment OCR browser boundaries."""
from __future__ import annotations

from copy import deepcopy
from functools import wraps

import frappe


RAW_KEYS = frozenset({"raw_ocr_text", "raw_text", "raw_json", "extracted_json"})
TEXT_KEYS = frozenset({
    "deleted_file_names",
    "error",
    "error_message",
    "match_reason",
    "mmp_verified_payer",
    "payer",
    "payment_proof_url",
    "receiver",
})


def enabled() -> bool:
    return bool(frappe.conf.get("privacy_shield_desk_enabled", False)) and (
        "privacy_shield" in frappe.get_installed_apps()
    )


def restricted(user=None) -> bool:
    if not enabled():
        return False

    from privacy_shield.policy import current_capabilities

    return not current_capabilities(user).view_full


def project_response(payload):
    """Copy and redact browser-visible OCR data without changing stored data."""
    if not restricted():
        return payload

    from privacy_shield.display_text import mask_display

    def clean(value, context=None):
        if isinstance(value, list):
            return [clean(item, context) for item in value]
        if isinstance(value, tuple):
            return tuple(clean(item, context) for item in value)
        if not isinstance(value, dict):
            if context in TEXT_KEYS and isinstance(value, str):
                return mask_display(value)
            return deepcopy(value)

        result = {}
        for key, item in value.items():
            if key in RAW_KEYS:
                continue
            result[key] = clean(item, key)
        return result

    return clean(payload)


def browser_response(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        return project_response(fn(*args, **kwargs))

    return wrapped


def mask_log_text(value):
    if not enabled() or not isinstance(value, str):
        return value

    from privacy_shield.display_text import mask_display

    return mask_display(value)
