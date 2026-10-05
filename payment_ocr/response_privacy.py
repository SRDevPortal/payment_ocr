"""Scrub Payment OCR fields embedded in Patient Encounter Desk responses."""
from __future__ import annotations

import frappe

from payment_ocr.number_privacy import restricted


def scrub_response():
    if not restricted():
        return

    from privacy_shield.display_text import mask_display

    docs = frappe.response.get("docs") or []
    for index, doc in enumerate(docs):
        data = doc.as_dict() if callable(getattr(doc, "as_dict", None)) else doc
        docs[index] = data
        if not isinstance(data, dict) or data.get("doctype") != "Patient Encounter":
            continue
        for row in data.get("enc_multi_payments") or []:
            if not isinstance(row, dict) or "mmp_verified_payer" not in row:
                continue
            row["mmp_verified_payer"] = mask_display(row["mmp_verified_payer"])
